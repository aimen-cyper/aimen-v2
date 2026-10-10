"""
خدمة الطلبات — قلب النظام.

المسؤوليات:
    • إنشاء الطلب: تحقق كامل ثم خصم الرصيد وإنشاء الطلب وإشعار المستخدم في معاملة واحدة.
    • إرسال الطلبات للمزود عبر عمّال (workers) مع حجز آمن يمنع المعالجة المزدوجة.
    • متابعة الحالة دورياً حتى الحالة النهائية.
    • الاسترجاع الآمن عند الفشل أو الإلغاء أو التنفيذ الجزئي.
    • أدوات الأدمن: إلغاء، ربط رقم مزود، تأكيد فشل، تجاوز حالة (مع تدقيق إجباري).

قواعد لا تُكسر:
    • كل تغيير حالة يمر عبر `core.order_state` (جدول انتقالات) **و** تحديث مشروط في
      قاعدة البيانات (`expected_statuses`) — فلا سباق ولا كتابة فوق عمل جهة أخرى.
    • كل استرجاع يمر عبر `WalletService` ويُسجَّل كحركة مالية بمرجع فريد.
    • لا إعادة إرسال تلقائي عند نتيجة غير مؤكدة (منعاً لطلب مزدوج عند المزود).
    • لا تُفتح معاملة قاعدة بيانات أثناء انتظار شبكة المزود.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field, replace
from typing import Sequence

from core.constants import MAX_SUBMIT_ATTEMPTS, ORDER_LOCK_SECONDS
from core.enums import ActorType, NotificationType, OrderStatus
from core.exceptions import (
    DuplicateOperationError,
    InvalidStateTransitionError,
    OrderError,
    ProviderError,
    ProviderInsufficientFundsError,
    ProviderPermanentError,
    ProviderTemporaryError,
    ProviderUncertainError,
    RateLimitedError,
    ServiceNotAvailableError,
    ValidationError,
)
from core.money import format_units, partial_refund_units
from core.order_schedule import failure_delay_seconds, success_delay_seconds
from core.order_state import (
    OVERRIDE_FORBIDDEN_TARGETS,
    OVERRIDE_NEEDS_PROVIDER_ID,
    assert_transition,
    can_transition,
    is_final,
    map_provider_status,
)
from core.permissions import Permission
from database.database import Database, Tx
from database.models import Order, Provider, Service, User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.catalog_service import CatalogService
from services.channel_service import KIND_ORDERS_LOG, ChannelService
from services.notification_service import NotificationService
from services.provider_service import ProviderService
from services.settings_service import SettingsService
from services.wallet_service import WalletService
from texts import templates
from texts.channel_posts import order_post
from utils.datetime_utils import day_bounds_utc, iso_plus_seconds, parse_iso, utc_now
from utils.formatters import order_status_text
from utils.logging_setup import get_logger
from utils.security import new_token, sanitize
from utils.validators import validate_link

logger = get_logger(__name__)


#: الحالات التي يجوز منها «تعليم كفاشل + استرجاع» الإداري: الطلب لم يصل المزود فعلاً (أو فشل بلا استرجاع)
MARK_FAILED_ALLOWED_FROM: frozenset[str] = frozenset(
    {OrderStatus.PENDING, OrderStatus.SUBMIT_UNCERTAIN, OrderStatus.FAILED}
)

@dataclass(slots=True)
class BatchReport:
    """حصيلة جولة معالجة (إرسال أو فحص حالات)."""

    claimed: int = 0
    succeeded: int = 0
    retried: int = 0
    failed: int = 0
    uncertain: int = 0
    unchanged: int = 0
    completed: int = 0
    details: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, int]:
        """تحويل الحصيلة إلى قاموس للتسجيل."""
        return {
            "claimed": self.claimed,
            "succeeded": self.succeeded,
            "retried": self.retried,
            "failed": self.failed,
            "uncertain": self.uncertain,
            "unchanged": self.unchanged,
            "completed": self.completed,
        }


#: حالات يكون فيها الطلب عند المزود (لا يُسترجع ماله قبل تأكيد المزود)
_HELD_AT_PROVIDER = (OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS)


class OrderService:
    """دورة حياة الطلب كاملة من الإنشاء حتى الحالة النهائية."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        wallet: WalletService,
        catalog: CatalogService,
        providers: ProviderService,
        notifications: NotificationService,
        audit: AuditService,
        auth: AuthService,
        channels: ChannelService | None = None,
    ) -> None:
        """تهيئة الخدمة بكل الاعتماديات التي تحتاجها (`channels` لتوثيق الطلبات في القناة)."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.wallet = wallet
        self.catalog = catalog
        self.providers = providers
        self.notifications = notifications
        self.audit = audit
        self.auth = auth
        self.channels = channels

    # ===================================================================== #
    #                              الإنشاء                                  #
    # ===================================================================== #

    async def create_order(
        self,
        user: User,
        *,
        service_id: int,
        link: str,
        quantity: str | int,
        client_request_id: str | None = None,
    ) -> Order:
        """
        إنشاء طلب جديد: تحقق كامل ← خصم الرصيد ← إنشاء الطلب ← إشعار — كلها معاملة واحدة.

        المدخلات:
            client_request_id : مفتاح المستخدم لمنع التكرار عند الضغط المزدوج.
                                إذا تكرر نفس المفتاح يُعاد الطلب الأول نفسه دون خصم جديد.

        المخرجات: الطلب بعد إنشائه (حالته `pending`).

        الاستثناءات:
            UserBannedError · MaintenanceModeError : الحساب محظور أو النظام في صيانة.
            ServiceNotAvailableError               : الخدمة أو مزودها غير متاح.
            QuantityOutOfRangeError · InvalidLinkError · InvalidAmountError
            RateLimitedError                       : تجاوز الحد اليومي للطلبات.
            DuplicateOperationError                : طلب مطابق خلال نافذة التكرار.
            InsufficientBalanceError               : الرصيد لا يكفي (لا يُنشأ الطلب أصلاً).
        """
        await self.auth.guard(user)

        # 1) مفتاح منع التكرار: إن تكرر نفس المفتاح نُعيد الطلب الأصلي دون أي خصم جديد
        request_id = (client_request_id or f"u{user.id}:{new_token(8)}").strip()[:64]
        existing = await self.repos.orders.get_by_client_request_id(request_id)
        if existing is not None:
            logger.info("إعادة استخدام الطلب %s لنفس مفتاح الطلب %s", existing.id, request_id)
            return existing

        # 2) الخدمة والمزود
        service = await self.catalog.get_available_service(service_id)
        provider = await self.repos.providers.get(service.provider_id)
        if provider is None:
            raise ServiceNotAvailableError(f"مزود الخدمة {service_id} غير موجود")
        health = await self.providers.health(provider)
        if not health.is_usable:
            raise ServiceNotAvailableError(
                f"المزود {provider.name} غير متاح: {health.reason}",
                user_message="❌ هذه الخدمة متوقفة مؤقتاً. جرّب لاحقاً.",
            )

        if (
            service.provider_price_per_1000_units
            and service.price_per_1000_units < service.provider_price_per_1000_units
            and await self.settings.get_bool("block_negative_margin", False)
        ):
            raise ServiceNotAvailableError(
                f"خدمة {service.id} بهامش سالب (البيع {service.price_per_1000_units} < التكلفة {service.provider_price_per_1000_units})",
                user_message="❌ هذه الخدمة متوقفة مؤقتاً. جرّب لاحقاً.",
            )

        # 3) الرابط والكمية والتكلفة
        clean_link = validate_link(link, pattern=service.link_pattern, rule=service.link_rule)
        quote = await self.catalog.quote(service, quantity)

        symbol = await self.settings.money_symbol()
        min_order_units = await self.settings.get_money_units("min_order_amount_units", 0)
        if min_order_units and quote.cost_units < min_order_units:
            raise ValidationError(
                f"قيمة الطلب {quote.cost_units} أقل من الحد الأدنى {min_order_units}",
                user_message=(
                    "❌ الحد الأدنى لقيمة الطلب هو "
                    f"{format_units(min_order_units, symbol=symbol)}."
                ),
            )

        # 4) المعاملة الذرّية: فحوص الحدود ← إنشاء + خصم + سجل + إشعار
        async with self.db.transaction() as tx:
            # الفحوص الحاكمة داخل المعاملة نفسها: `BEGIN IMMEDIATE` يسلسل الكاتبين، فلا يمكن لنقرتين
            # متزامنتين أن تجتازا الفحص معاً ثم تُنشئا طلبين (ثغرة «افحص ثم نفّذ» التي كشفها اختبار التزامن)
            raced = await self.repos.orders.get_by_client_request_id(request_id)
            if raced is not None:
                logger.info("إعادة استخدام الطلب %s لنفس مفتاح الطلب %s (سباق)", raced.id, request_id)
                return raced
            await self._check_daily_limit(user)
            await self._check_duplicate(user, service.id, clean_link, quote.quantity)

            order = await self.repos.orders.create(
                tx,
                user_id=user.id,
                service_id=service.id,
                provider_id=provider.id,
                service_name_snapshot=service.name,
                price_per_1000_snapshot_units=service.price_per_1000_units,
                link=clean_link,
                quantity=quote.quantity,
                cost_units=quote.cost_units,
                client_request_id=request_id,
                provider_cost_units=self._provider_cost(service, quote.quantity),
            )
            public_code = f"ORD-{order.id:06d}"
            await self.repos.orders.update_fields(tx, order.id, public_code=public_code)

            await self.wallet.charge_for_order(
                tx,
                user_id=user.id,
                order_id=order.id,
                amount_units=quote.cost_units,
                description=f"طلب {service.name} × {quote.quantity}",
            )

            await self.repos.orders.add_history(
                tx,
                order_id=order.id,
                from_status=None,
                to_status=OrderStatus.PENDING,
                actor_type=ActorType.USER,
                actor_id=user.id,
                reason="إنشاء الطلب",
            )

            title, message = templates.order_created(
                code=public_code,
                service_name=service.name,
                quantity=quote.quantity,
                cost_units=quote.cost_units,
                symbol=symbol,
            )
            await self.notifications.notify_order(
                tx,
                user_id=user.id,
                order_id=order.id,
                event=NotificationType.ORDER_CREATED,
                title=title,
                message=message,
                payload={"order_id": order.id, "cost_units": quote.cost_units},
            )
            await self._log_order_to_channel(tx, user, service, order.id, public_code, clean_link, quote, symbol)

        created = await self.repos.orders.get(order.id)
        if created is None:  # لا يحدث عملياً، لكن لا نُرجع قيمة غير مؤكدة أبداً
            raise OrderError(f"تعذر قراءة الطلب {order.id} بعد إنشائه")
        logger.info(
            "أنشأ المستخدم %s الطلب %s (%s × %s) بتكلفة %s",
            user.id, created.id, service.name, quote.quantity, quote.cost_units,
        )
        return created

    async def _log_order_to_channel(
        self, tx: Tx, user: User, service: Service, order_id: int, public_code: str,
        link: str, quote, symbol: str,
    ) -> None:
        """
        إدراج منشور «طلب جديد» في صندوق قناة توثيق الطلبات (يُرسَل لاحقاً عبر job؛ يُنتظر الوجهة إن لم تُضبط).

        لا يحمل سراً: Telegram ID والرابط مقنَّعان، ولا مزود ولا مفاتيح. فشله لا يُسقط الطلب (يُسجَّل فقط).
        """
        if self.channels is None:
            return
        try:
            # لا نتخطّى عند غياب الوجهة: المنشور يبقى بالصندوق ويُنشر عند ضبطها (حتى `channel_post_ttl_hours`)،
            # وإلا ضاع توثيق كل طلب أُنشئ قبل ضبط القناة أو أثناء خطأ إعداد مؤقت.
            category = await self.repos.categories.get(service.category_id)
            title, message = order_post(
                category_name=category.name_ar if category else "",
                service_name=service.name,
                order_code=public_code,
                quantity=quote.quantity,
                cost_units=quote.cost_units,
                symbol=symbol,
                usd_rate=await self.settings.usd_rate(),
                user=user,
                link=link,
            )
            await self.channels.enqueue(
                tx, kind=KIND_ORDERS_LOG, title=title, message=message, dedupe_key=f"order:{order_id}"
            )
        except Exception:                                  # noqa: BLE001 - التوثيق لا يجوز أن يُسقط طلباً مدفوعاً
            logger.exception("تعذّر إدراج توثيق الطلب %s في صندوق القناة", order_id)

    def _provider_cost(self, service: Service, quantity: int) -> int | None:
        """حساب تكلفة الطلب علينا لدى المزود (للأرباح) إن كان سعر المزود معروفاً."""
        if not service.provider_price_per_1000_units:
            return None
        return (service.provider_price_per_1000_units * quantity + 500) // 1000

    async def _check_daily_limit(self, user: User) -> None:
        """
        التأكد من عدم تجاوز الحد اليومي لعدد الطلبات.

        الاستثناءات: RateLimitedError عند التجاوز.
        """
        max_per_day = await self.settings.get_int("max_orders_per_day", 0)
        if max_per_day <= 0:
            return
        start_today, _ = day_bounds_utc(0)
        today_count = await self.repos.orders.count_today_by_user(user.id, start_today)
        if today_count >= max_per_day:
            raise RateLimitedError(
                f"المستخدم {user.id} تجاوز {max_per_day} طلباً اليوم",
                user_message=f"⏳ وصلت إلى الحد اليومي ({max_per_day} طلب). حاول غداً.",
            )

    async def _check_duplicate(self, user: User, service_id: int, link: str, quantity: int) -> None:
        """
        منع إنشاء طلب مطابق تماماً خلال نافذة زمنية قصيرة (ضغط مزدوج أو خطأ).

        الاستثناءات: DuplicateOperationError عند وجود طلب مطابق حديث.
        """
        window_minutes = await self.settings.get_int("duplicate_order_window_minutes", 0)
        if window_minutes <= 0:
            return
        since = iso_plus_seconds(-window_minutes * 60)
        duplicate = await self.repos.orders.find_recent_duplicate(
            user_id=user.id, service_id=service_id, link=link, quantity=quantity, since_iso=since
        )
        if duplicate is not None:
            raise DuplicateOperationError(
                f"طلب مكرر خلال {window_minutes} دقيقة (الطلب {duplicate.id})",
                user_message=(
                    f"⚠️ لديك طلب مطابق قبل قليل ({duplicate.public_code or duplicate.id}). "
                    f"إن كنت تريد طلباً إضافياً انتظر {window_minutes} دقيقة."
                ),
            )

    # ===================================================================== #
    #                        أدوات تغيير الحالة                             #
    # ===================================================================== #

    async def _transition(
        self,
        tx: Tx,
        order: Order,
        new_status: str,
        *,
        actor_type: str,
        actor_id: int | None = None,
        reason: str | None = None,
        extra: dict | None = None,
        provider_status_raw: str | None = None,
    ) -> bool:
        """
        تنفيذ انتقال حالة واحد: تحقق من الجدول ثم تحديث مشروط ثم تسجيل في التاريخ.

        المخرجات: True إذا تم التغيير فعلاً، False إذا سبقتنا جهة أخرى لتغيير الحالة
                  (وهذا ليس خطأً — بل الحماية من السباق تعمل).

        الاستثناءات:
            InvalidStateTransitionError : الانتقال ممنوع في جدول الحالات.
        """
        assert_transition(order.status, new_status, order_id=order.id)
        if order.status == new_status:
            return False  # لا تغيير فعلي

        changed = await self.repos.orders.update_status(
            tx,
            order.id,
            new_status=new_status,
            expected_statuses=[order.status],
            extra_fields=extra,
        )
        if not changed:
            logger.warning(
                "تجاهل انتقال الطلب %s (%s ← %s): تغيّرت حالته من جهة أخرى",
                order.id, order.status, new_status,
            )
            return False

        await self.repos.orders.add_history(
            tx,
            order_id=order.id,
            from_status=order.status,
            to_status=new_status,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            provider_status_raw=provider_status_raw,
        )
        return True

    async def _refund_full(
        self, tx: Tx, order: Order, *, reason: str, actor_type: str, actor_id: int | None = None
    ) -> int:
        """
        استرجاع كامل المبلغ المتبقي للطلب ثم نقله إلى الحالة `refunded`.

        المخرجات: المبلغ المسترجع فعلياً (قد يكون صفراً إن سبق استرجاعه بالكامل).
        """
        remaining = order.refundable_units
        if remaining <= 0:
            return 0

        transaction = await self.wallet.refund_order(
            tx,
            user_id=order.user_id,
            order_id=order.id,
            amount_units=remaining,
            partial=False,
            description=f"استرجاع كامل: {reason}",
        )
        if transaction is None:
            return 0

        fresh = await self.repos.orders.get(order.id)
        if fresh is not None and can_transition(fresh.status, OrderStatus.REFUNDED):
            await self._transition(
                tx, fresh, OrderStatus.REFUNDED,
                actor_type=actor_type, actor_id=actor_id, reason=reason,
                extra={"refunded_at": self.repos.orders.now()},
            )
        return remaining

    async def _fail_order(
        self,
        order: Order,
        *,
        reason: str,
        actor_type: str = ActorType.SYSTEM,
        actor_id: int | None = None,
        notify_admins: bool = True,
        auto_refund: bool | None = None,
        audit: dict | None = None,
    ) -> int:
        """
        المسار الكامل لفشل طلب: تغيير الحالة ← استرجاع كامل ← إشعار المستخدم والأدمن.

        المدخلات:
            auto_refund : None تعني «اتبع الإعداد `auto_refund_on_provider_fail`»،
                          وTrue تفرض الاسترجاع (إجراء أدمن صريح).
                          عند تعطيل الاسترجاع التلقائي يبقى المال محجوزاً ويُنبَّه الأدمن
                          لتنفيذ الاسترجاع يدوياً — ولا يُفقد مال المستخدم في الحالتين.

        المخرجات: المبلغ المسترجع (صفر إذا كان الاسترجاع التلقائي معطّلاً).
        """
        symbol = await self.settings.money_symbol()
        clean_reason = sanitize(reason)[:300]
        if auto_refund is None:
            auto_refund = await self.settings.get_bool("auto_refund_on_provider_fail", True)
        refunded = 0

        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None or is_final(current.status):
                return 0

            if current.status == OrderStatus.FAILED:
                # فشل سابق بلا استرجاع (الاسترجاع التلقائي معطّل أو تجاوز إداري): هذا قرار الاسترجاع اليدوي.
                # قبل هذا الإصلاح كان الاستدعاء يعود بصفر بصمت ويبقى المال محجوزاً بلا أي مسار لاسترجاعه.
                if not auto_refund:
                    return 0
                refunded = await self._refund_full(
                    tx, current, reason=clean_reason, actor_type=actor_type, actor_id=actor_id
                )
                if refunded:
                    # حدث «ORDER_REFUNDED» وليس «ORDER_FAILED»: مفتاح منع التكرار (الطلب+الحدث) كان يبتلع هذا الإشعار
                    # لأن إشعار الفشل أُرسل سابقاً — فيُسترجع المال والعميل لا يعلم.
                    code = current.public_code or f"#{current.id}"
                    title, message = templates.order_refunded(code=code, refund_units=refunded, symbol=symbol)
                    await self.notifications.notify_order(
                        tx, user_id=current.user_id, order_id=current.id,
                        event=NotificationType.ORDER_REFUNDED, title=title, message=message,
                    )
                    await self._audit_in_tx(tx, audit, actor_id=actor_id, order_id=current.id, refunded=refunded)
                logger.warning("استرجاع يدوي لطلب فاشل %s: %s", order.id, refunded)
                return refunded

            moved = await self._transition(
                tx, current, OrderStatus.FAILED,
                actor_type=actor_type, actor_id=actor_id, reason=clean_reason,
                extra={"last_error": clean_reason, "locked_by": None, "locked_until": None},
            )
            if not moved:
                return 0

            failed_order = await self.repos.orders.get(order.id)
            if failed_order is None:
                return 0
            if auto_refund:
                refunded = await self._refund_full(
                    tx, failed_order, reason=clean_reason, actor_type=actor_type, actor_id=actor_id
                )

            code = current.public_code or f"#{current.id}"
            title, message = templates.order_failed(
                code=code, reason=clean_reason, refund_units=refunded, symbol=symbol
            )
            await self.notifications.notify_order(
                tx,
                user_id=current.user_id,
                order_id=current.id,
                event=NotificationType.ORDER_FAILED,
                title=title,
                message=message,
            )
            if notify_admins or not auto_refund:
                admin_reason = clean_reason if auto_refund else (
                    f"{clean_reason} — ⚠️ الاسترجاع التلقائي معطّل، نفّذ الاسترجاع يدوياً"
                )
                admin_title, admin_message = templates.admin_order_failed(
                    code=code, order_id=current.id, reason=admin_reason,
                    refund_units=refunded, symbol=symbol,
                )
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.ORDERS_VIEW,
                    token=f"order:{current.id}:failed",
                    title=admin_title,
                    message=admin_message,
                )
            await self.repos.error_logs.log(
                tx,
                message=f"فشل الطلب #{current.id}: {clean_reason}",
                level="ERROR",
                source="order_service",
                error_type="OrderFailed",
                user_id=current.user_id,
            )
            await self._audit_in_tx(tx, audit, actor_id=actor_id, order_id=current.id, refunded=refunded)
        logger.error("فشل الطلب %s: %s (استُرجع %s)", order.id, clean_reason, refunded)
        return refunded

    # ===================================================================== #
    #                        إرسال الطلبات للمزود                           #
    # ===================================================================== #

    async def process_pending_orders(self, *, worker: str = "submitter", limit: int = 5) -> BatchReport:
        """
        حجز دفعة من الطلبات المعلّقة وإرسالها إلى المزود.

        تُستدعى من job دوري. الحجز يمنع أن يعالج عاملان الطلب نفسه.
        """
        report = BatchReport()
        async with self.db.transaction() as tx:
            claimed = await self.repos.orders.claim_pending_for_submit(
                tx, worker=worker, limit=limit, lock_seconds=ORDER_LOCK_SECONDS
            )
        report.claimed = len(claimed)

        waiting = list(claimed)          # طلبات حُجزت ولم يبدأ إرسالها بعد
        try:
            while waiting:
                order = waiting.pop(0)   # يخرج من القائمة قبل الإرسال: مصيره صار بيد `_submit_one`
                outcome = await self._submit_one(order)
                self._count_outcome(report, outcome)
        except BaseException:
            # أُلغيت الجولة (مهلة/إيقاف) أو انهارت: الطلبات التي لم يُرسَل منها شيء بعد تعود لـpending
            # فوراً (آمن لأن أي طلب لم يصل المزود)، أما الذي كان قيد الإرسال فعالجه `_submit_one` بنفسه.
            await asyncio.shield(self._release_unsent(waiting))
            raise

        if report.claimed:
            logger.info("جولة إرسال الطلبات: %s", report.as_dict())
        return report

    @staticmethod
    def _count_outcome(report: "BatchReport", outcome: str) -> None:
        """تحديث عدّادات الجولة بحسب نتيجة إرسال طلب واحد."""
        if outcome == "submitted":
            report.succeeded += 1
        elif outcome == "retry":
            report.retried += 1
        elif outcome == "uncertain":
            report.uncertain += 1
        elif outcome == "failed":
            report.failed += 1
        else:
            report.unchanged += 1

    async def _release_unsent(self, orders: Sequence[Order]) -> None:
        """إعادة طلبات محجوزة لم يُرسل منها شيء إلى `pending` (تُستدعى عند إلغاء الجولة)."""
        for order in orders:
            try:
                await self._requeue(order, reason="أُوقفت جولة الإرسال قبل بدء هذا الطلب", delay_seconds=30)
            except Exception as exc:  # noqa: BLE001 - تعذّر الإرجاع ⇒ يلتقطه الاسترداد الدوري كغير مؤكد
                logger.error("تعذّر إرجاع الطلب %s إلى الانتظار بعد إيقاف الجولة: %s", order.id, exc)

    async def _submit_one(self, order: Order) -> str:
        """
        إرسال طلب واحد إلى المزود ومعالجة كل النتائج الممكنة.

        المخرجات: وصف مختصر للنتيجة: submitted / retry / uncertain / failed / skipped.
        """
        service = await self.repos.services.get(order.service_id)
        provider = await self.repos.providers.get(order.provider_id)
        if service is None or provider is None:
            await self._fail_order(order, reason="بيانات الخدمة أو المزود غير موجودة")
            return "failed"

        async with self.db.transaction() as tx:
            still_ours = await self.repos.orders.renew_submit_lock(
                tx, order.id, worker=order.locked_by or "submitter"
            )
        if not still_ours:
            logger.warning("الطلب %s لم يعد محجوزاً لهذا العامل — تخطّي الإرسال", order.id)
            return "skipped"

        health = await self.providers.health(provider)
        if not health.is_usable:
            await self._requeue(order, reason=f"المزود غير متاح: {health.reason}", delay_seconds=300)
            return "retry"

        try:
            result = await self.providers.submit_order(provider, service, order)
        except ProviderInsufficientFundsError as exc:
            await self._handle_insufficient_provider_funds(order, provider, str(exc))
            return "retry"
        except ProviderUncertainError as exc:
            await self._mark_uncertain(order, str(exc))
            return "uncertain"
        except ProviderPermanentError as exc:
            await self._fail_order(order, reason=f"رفض المزود الطلب: {exc}")
            return "failed"
        except ProviderTemporaryError as exc:
            if order.submit_attempts >= MAX_SUBMIT_ATTEMPTS:
                await self._fail_order(
                    order, reason=f"تعذر الإرسال بعد {order.submit_attempts} محاولات: {exc}"
                )
                return "failed"
            await self._requeue(order, reason=str(exc), delay_seconds=60 * order.submit_attempts)
            return "retry"
        except ProviderError as exc:
            # أي خطأ مزود غير مصنّف يُعامل معاملة الخطأ النهائي حفاظاً على مال المستخدم
            await self._fail_order(order, reason=f"خطأ غير متوقع من المزود: {exc}")
            return "failed"
        except asyncio.CancelledError:
            # أُلغيت الجولة (مهلة المهمة/إيقاف) والطلب ربما وصل المزود ⇒ «غير مؤكد» لا «معلّق للأبد».
            await asyncio.shield(
                self._mark_uncertain(order, "أُلغيت جولة الإرسال أثناء انتظار رد المزود")
            )
            raise
        except Exception as exc:  # noqa: BLE001 - لا نعرف أين انقطع الاتصال ⇒ نفترض الأسوأ (غير مؤكد)
            logger.exception("خطأ غير متوقع أثناء إرسال الطلب %s", order.id)
            await self._mark_uncertain(order, f"خطأ غير متوقع أثناء الإرسال: {type(exc).__name__}")
            return "uncertain"

        # نجاح عند المزود: يجب تسجيل رقمه محلياً. فشل الحفظ هنا أخطر نقطة في النظام (أثر جانبي خارجي
        # حدث ولم يُسجَّل) ⇒ نعيد المحاولة، وعند الفشل النهائي نسجّل الرقم في اللوق ونجعل الطلب «غير مؤكد».
        if await self._persist_submission(order, result):
            logger.info(
                "أُرسل الطلب %s إلى المزود %s برقم %s", order.id, provider.name, result.provider_order_id
            )
            return "submitted"
        return "uncertain"

    #: فواصل إعادة محاولة حفظ نتيجة الإرسال الناجح (ثوانٍ) — قصيرة لأن المزود قبل الطلب فعلاً
    PERSIST_RETRY_DELAYS: tuple[float, ...] = (0.0, 0.5, 1.5)

    async def _persist_submission(self, order: Order, result) -> bool:
        """
        حفظ نجاح الإرسال (رقم المزود + الانتقال إلى `submitted`) مع إعادة المحاولة.

        المخرجات: True إن حُفظ؛ False إن فشل كل شيء — وعندها يصبح الطلب `submit_uncertain` ورقم المزود
        مكتوب في اللوق ورسالة تنبيه الأدمن ليُربط يدوياً («🔗 ربط رقم المزود») بدل إعادة إرسال مكررة.
        """
        check_interval = await self.settings.get_int("order_check_interval_seconds", 120)
        last_error: Exception | None = None
        for delay in self.PERSIST_RETRY_DELAYS:
            if delay:
                await asyncio.sleep(delay)
            try:
                async with self.db.transaction() as tx:
                    current = await self.repos.orders.get(order.id)
                    if current is None:
                        return True
                    moved = await self._transition(
                        tx, current, OrderStatus.SUBMITTED,
                        actor_type=ActorType.JOB,
                        reason="قبل المزود الطلب",
                        extra={
                            "provider_order_id": result.provider_order_id,
                            "provider_cost_units": result.charge_units if result.charge_units else current.provider_cost_units,
                            "submitted_at": self.repos.orders.now(),
                            "next_check_at": iso_plus_seconds(check_interval),
                            "locked_by": None,
                            "locked_until": None,
                            "last_error": None,
                        },
                    )
                    if moved:
                        title, message = templates.order_submitted(
                            code=current.public_code or f"#{current.id}",
                            service_name=current.service_name_snapshot,
                        )
                        await self.notifications.notify_order(
                            tx,
                            user_id=current.user_id,
                            order_id=current.id,
                            event=NotificationType.ORDER_SUBMITTED,
                            title=title,
                            message=message,
                        )
                return True
            except Exception as exc:  # noqa: BLE001 - نعيد المحاولة ثم نصعّد للمسار الآمن
                last_error = exc
                logger.error("فشل حفظ نتيجة إرسال الطلب %s (محاولة)، رقم المزود=%s: %s",
                             order.id, result.provider_order_id, exc)

        logger.critical(
            "⚠️ قبل المزود الطلب %s برقم %s لكن تعذّر حفظه محلياً (%s) — اربطه يدوياً ولا تُعد إرساله",
            order.id, result.provider_order_id, last_error,
        )
        try:
            await self._mark_uncertain(
                order,
                f"قبل المزود الطلب برقم {result.provider_order_id} لكن تعذّر حفظه محلياً "
                f"({type(last_error).__name__}) — اربط الرقم يدوياً",
            )
        except Exception as exc:  # noqa: BLE001 - القاعدة معطّلة ⇒ يلتقطه الاسترداد الدوري لاحقاً
            logger.critical("تعذّر وسم الطلب %s غير مؤكد (رقم المزود %s): %s", order.id, result.provider_order_id, exc)
        return False

    async def _requeue(self, order: Order, *, reason: str, delay_seconds: int) -> None:
        """إعادة الطلب إلى `pending` مع تأجيل المحاولة القادمة (فشل مؤقت آمن)."""
        clean_reason = sanitize(reason)[:300]
        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None or current.status != OrderStatus.SUBMITTING:
                return
            await self._transition(
                tx, current, OrderStatus.PENDING,
                actor_type=ActorType.JOB,
                reason=f"إعادة جدولة: {clean_reason}",
                extra={
                    "last_error": clean_reason,
                    "locked_by": None,
                    "locked_until": None,
                    "next_check_at": iso_plus_seconds(max(30, delay_seconds)),
                },
            )
        logger.warning("أُعيد الطلب %s للانتظار: %s", order.id, clean_reason)

    async def _mark_uncertain(self, order: Order, error: str) -> None:
        """
        وضع الطلب في حالة «غير مؤكد» وتنبيه الأدمن فوراً.

        ⚠️ لا استرجاع ولا إعادة إرسال هنا: قد يكون الطلب أُنشئ فعلاً عند المزود،
        وإعادة الإرسال تعني دفع المبلغ مرتين.
        """
        clean_error = sanitize(error)[:300]
        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None or current.status != OrderStatus.SUBMITTING:
                return
            moved = await self._transition(
                tx, current, OrderStatus.SUBMIT_UNCERTAIN,
                actor_type=ActorType.JOB,
                reason=clean_error,
                extra={"last_error": clean_error, "locked_by": None, "locked_until": None},
            )
            if moved:
                code = current.public_code or f"#{current.id}"
                title, message = templates.admin_order_uncertain(
                    code=code, order_id=current.id, error=clean_error
                )
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.ORDERS_VIEW,
                    token=f"order:{current.id}:uncertain",
                    title=title,
                    message=message,
                )
                await self.repos.error_logs.log(
                    tx,
                    message=f"نتيجة إرسال غير مؤكدة للطلب #{current.id}: {clean_error}",
                    level="CRITICAL",
                    source="order_service",
                    error_type="ProviderUncertainError",
                    user_id=current.user_id,
                )
        logger.critical("الطلب %s بحالة غير مؤكدة: %s", order.id, clean_error)

    async def _handle_insufficient_provider_funds(
        self, order: Order, provider: Provider, error: str
    ) -> None:
        """
        معالجة «رصيد المزود غير كافٍ» حسب القرار D5:
        يبقى الطلب منتظراً حتى مهلة قصوى، وبعدها يفشل ويُسترجع المبلغ تلقائياً.
        """
        wait_hours = await self.settings.get_int("provider_insufficient_wait_hours", 6)
        created = parse_iso(order.created_at)
        age_hours = ((utc_now() - created).total_seconds() / 3600) if created else 0.0

        if age_hours >= wait_hours:
            await self._fail_order(
                order, reason=f"انتظر الطلب {wait_hours} ساعة ورصيد المزود لا يزال غير كافٍ"
            )
            return

        await self._requeue(order, reason=f"رصيد المزود غير كافٍ: {error}", delay_seconds=900)
        # رصيد المزود المخزَّن بعملة المزود نفسها ⇒ يُعرض برمز عملته لا برمز عملة النظام
        title, message = templates.admin_provider_low_balance(
            provider_name=provider.name, balance_units=provider.balance_units, symbol=provider.currency or ""
        )
        async with self.db.transaction() as tx:
            await self.notifications.notify_admins(
                tx,
                permission=Permission.PROVIDERS_VIEW,
                token=f"provider:{provider.id}:insufficient:{day_bounds_utc(0)[0][:10]}",
                title=title,
                message=message,
            )

    # ===================================================================== #
    #                          متابعة حالة الطلبات                          #
    # ===================================================================== #

    async def process_due_orders(self, *, worker: str = "checker", limit: int = 20) -> BatchReport:
        """
        حجز دفعة من الطلبات المستحقة للفحص وتحديث حالاتها من المزود.

        تُستدعى من job دوري حتى تصل كل الطلبات إلى حالة نهائية دون تدخل بشري.

        **المرحلة 6:** الطلبات تُجمَّع حسب المزود ويُستعلم عنها دفعة واحدة
        (`multi-status`) بدل استدعاء لكل طلب — يقلّ عدد طلبات HTTP بمقدار حجم
        الدفعة، فيخف الضغط على المزود ويقصر زمن الجولة. الفحص الفردي يبقى
        المسار الاحتياطي لكل طلب لم يُجب عنه المزود في الدفعة.
        """
        report = BatchReport()
        # ميزانية الجولة: تتوقف عن بدء نداءات شبكة جديدة بعدها وتُفرج عن الباقي (بدل بقائه محجوزاً حتى انتهاء القفل).
        # مهلة نداء المزود 30ث، فيُمدَّد القفل ليغطي الميزانية + أطول نداء قيد التنفيذ.
        budget = await self.settings.get_int("order_check_round_budget_seconds", 90)
        deadline = time.monotonic() + max(1, budget)
        async with self.db.transaction() as tx:
            claimed = await self.repos.orders.claim_due_for_check(
                tx, worker=worker, limit=limit, lock_seconds=max(ORDER_LOCK_SECONDS, budget + 60)
            )
        report.claimed = len(claimed)
        if not claimed:
            return report

        use_batch = await self.settings.get_bool("order_multi_status_enabled", True)
        groups: dict[int, list[Order]] = {}
        for order in claimed:
            groups.setdefault(order.provider_id, []).append(order)

        for provider_id, orders in groups.items():
            outcomes = await self._sync_provider_group(provider_id, orders, use_batch=use_batch, deadline=deadline)
            for outcome in outcomes:
                if outcome in {OrderStatus.COMPLETED, OrderStatus.PARTIAL}:
                    report.completed += 1
                elif outcome == OrderStatus.FAILED:
                    report.failed += 1
                elif outcome == "unchanged":
                    report.unchanged += 1
                else:
                    report.succeeded += 1

        if report.claimed:
            logger.info("جولة فحص الطلبات: %s", report.as_dict())
        return report

    async def _release_unprocessed(self, orders: Sequence[Order]) -> None:
        """إفراج فوري عن طلبات لم تُفحص لانتهاء ميزانية الجولة: تُفحص في الجولة التالية (بلا احتساب إخفاق ولا تغيير حالة)."""
        async with self.db.transaction() as tx:
            for order in orders:
                await self.repos.orders.release_lock(tx, order.id, next_check_at=iso_plus_seconds(5))
        logger.warning("انتهت ميزانية جولة الفحص: أُجّل %s طلباً للجولة التالية", len(orders))

    async def _sync_provider_group(
        self,
        provider_id: int | None,
        orders: list[Order],
        *,
        use_batch: bool,
        deadline: float | None = None,
    ) -> list[str]:
        """
        فحص مجموعة طلبات تخص مزوداً واحداً.

        المدخلات:
            provider_id : معرف المزود (قد يكون None لطلب غير مرتبط بمزود).
            orders      : الطلبات المحجوزة لهذا المزود.
            use_batch   : تفعيل الاستعلام الجماعي (إعداد `order_multi_status_enabled`).

        المخرجات: قائمة نتائج بنفس ترتيب الطلبات ("unchanged" أو الحالة الجديدة).
        """
        provider = await self.repos.providers.get(provider_id) if provider_id else None
        if provider is None:
            for order in orders:
                await self._fail_order(order, reason="المزود غير موجود")
            return [OrderStatus.FAILED] * len(orders)

        statuses: dict[str, object] = {}
        batchable = [order for order in orders if order.provider_order_id]
        if deadline is not None and time.monotonic() >= deadline:
            await self._release_unprocessed(orders)
            return ["unchanged"] * len(orders)
        if use_batch and len(batchable) > 1:
            try:
                statuses = await self.providers.fetch_multi_status(provider, batchable)
            except ProviderError as exc:
                # فشل على مستوى الاتصال: لا فائدة من إعادة المحاولة فردياً الآن
                logger.warning(
                    "فشل الفحص الجماعي للمزود %s (%s طلباً): %s",
                    provider.name,
                    len(batchable),
                    exc,
                )
                for order in orders:
                    await self._release_after_check(order, ok=False, error=str(exc))
                return ["unchanged"] * len(orders)

        outcomes: list[str] = []
        for order in orders:
            status = statuses.get(order.provider_order_id or "")
            if status is None:
                if deadline is not None and time.monotonic() >= deadline:
                    await self._release_unprocessed([order])      # لا نداء شبكة جديد بعد الميزانية
                    outcomes.append("unchanged")
                    continue
                outcomes.append(await self._sync_one(order))       # المسار الاحتياطي
            else:
                outcomes.append(await self._apply_status(order, status))
        return outcomes

    async def _sync_one(self, order: Order) -> str:
        """
        فحص حالة طلب واحد لدى المزود وتطبيق النتيجة.

        المخرجات: الحالة الجديدة، أو "unchanged" إذا لم يتغير شيء.
        """
        provider = await self.repos.providers.get(order.provider_id)
        if provider is None:
            await self._fail_order(order, reason="المزود غير موجود")
            return OrderStatus.FAILED

        try:
            status = await self.providers.fetch_status(provider, order)
        except ProviderPermanentError as exc:
            await self._release_after_check(order, ok=False, error=str(exc))
            logger.warning("فحص الطلب %s فشل نهائياً: %s", order.id, exc)
            return "unchanged"
        except ProviderError as exc:
            await self._release_after_check(order, ok=False, error=str(exc))
            return "unchanged"

        return await self._apply_status(order, status)

    async def _apply_status(self, order: Order, status) -> str:
        """
        تطبيق نتيجة حالة قادمة من المزود على طلب واحد.

        فُصلت عن `_sync_one` في المرحلة 6 ليشاركها الفحص الجماعي: مصدر الحالة
        يختلف (استدعاء فردي أو دفعة) بينما قواعد الانتقال والاسترجاع واحدة.

        المخرجات: الحالة الجديدة، أو "unchanged" إذا لم يتغير شيء.
        """
        mapped = map_provider_status(status.raw_status)
        if mapped is None:
            await self._handle_unknown_status(order, status.raw_status)
            return "unchanged"

        if mapped == order.status:
            await self._release_after_check(order, progress=status)
            return "unchanged"

        if mapped == OrderStatus.SUBMITTED and order.status == OrderStatus.IN_PROGRESS:
            # بعض اللوحات تعيد «Pending» لحظياً بعد «Processing» (ترتيب كاش/تأخر مزامنة): ليست رجوعاً حقيقياً
            # ولا خطأ — نبقى «قيد التنفيذ» ونحدّث التقدم فقط دون كتابة last_error مضلِّلة.
            await self._release_after_check(order, progress=status)
            return "unchanged"

        if mapped == OrderStatus.IN_PROGRESS:
            await self._apply_in_progress(order, status)
            return OrderStatus.IN_PROGRESS
        if mapped == OrderStatus.COMPLETED:
            await self._apply_completed(order, status)
            return OrderStatus.COMPLETED
        if mapped == OrderStatus.PARTIAL:
            await self._apply_partial(order, status)
            return OrderStatus.PARTIAL
        if mapped == OrderStatus.CANCELED:
            await self._apply_canceled(order, reason="ألغى المزود الطلب")
            return OrderStatus.CANCELED
        if mapped == OrderStatus.FAILED:
            await self._fail_order(order, reason=f"المزود أبلغ بفشل الطلب ({status.raw_status})")
            return OrderStatus.FAILED

        # حالة معروفة لكن الانتقال إليها غير منطقي من الحالة الحالية: نسجل ونؤجل
        await self._release_after_check(order, progress=status, note=f"انتقال غير مدعوم إلى {mapped}")
        return "unchanged"

    def _progress_fields(self, status, *, with_check_fields: bool = True) -> dict:
        """
        الحقول المستخرجة من رد المزود (حالته الخام وتقدّم التنفيذ).

        `with_check_fields`: يضيف علامات «فحص ناجح الآن» (آخر فحص، تصفير الإخفاقات، مسح خطأ الفحص السابق) —
        كل رد ناجح من المزود يمرّ من هنا فتبقى بيانات الفحص صادقة.
        """
        fields: dict = {"provider_status": status.raw_status}
        if with_check_fields:
            now_iso = self.repos.orders.now()
            fields.update({
                "last_checked_at": now_iso,
                "last_check_ok_at": now_iso,
                "check_fail_streak": 0,
                "last_check_error": None,
            })
        if status.start_count is not None:
            fields["start_count"] = status.start_count
        if status.remains is not None:
            fields["remains"] = status.remains
        if status.delivered is not None:
            fields["delivered_quantity"] = status.delivered
        return fields

    async def _apply_in_progress(self, order: Order, status) -> None:
        """نقل الطلب إلى «قيد التنفيذ» وإشعار المستخدم مرة واحدة."""
        check_interval = await self.settings.get_int("order_check_interval_seconds", 120)
        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None:
                return
            extra = self._progress_fields(status)
            extra.update({
                "locked_by": None,
                "locked_until": None,
                "next_check_at": iso_plus_seconds(check_interval),
            })
            moved = await self._transition(
                tx, current, OrderStatus.IN_PROGRESS,
                actor_type=ActorType.PROVIDER,
                reason="بدأ التنفيذ",
                extra=extra,
                provider_status_raw=status.raw_status,
            )
            if moved:
                title, message = templates.order_in_progress(
                    code=current.public_code or f"#{current.id}"
                )
                await self.notifications.notify_order(
                    tx,
                    user_id=current.user_id,
                    order_id=current.id,
                    event=NotificationType.ORDER_IN_PROGRESS,
                    title=title,
                    message=message,
                )

    async def _apply_completed(self, order: Order, status) -> None:
        """إنهاء الطلب بنجاح وإشعار المستخدم."""
        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None:
                return
            extra = self._progress_fields(status)
            extra.update({
                "completed_at": self.repos.orders.now(),
                "remains": 0,
                "delivered_quantity": status.delivered if status.delivered is not None else current.quantity,
                "locked_by": None,
                "locked_until": None,
                "next_check_at": None,
            })
            moved = await self._transition(
                tx, current, OrderStatus.COMPLETED,
                actor_type=ActorType.PROVIDER,
                reason="اكتمل التنفيذ",
                extra=extra,
                provider_status_raw=status.raw_status,
            )
            if moved:
                title, message = templates.order_completed(
                    code=current.public_code or f"#{current.id}",
                    service_name=current.service_name_snapshot,
                    quantity=current.quantity,
                )
                await self.notifications.notify_order(
                    tx,
                    user_id=current.user_id,
                    order_id=current.id,
                    event=NotificationType.ORDER_COMPLETED,
                    title=title,
                    message=message,
                )
        logger.info("اكتمل الطلب %s", order.id)

    async def _apply_partial(self, order: Order, status) -> None:
        """
        تنفيذ جزئي: حساب الاسترجاع بحسب المتبقي، تنفيذه، ثم إشعار المستخدم.

        الاسترجاع = (التكلفة × المتبقي) ÷ الكمية، مطروحاً منه ما سبق استرجاعه.
        """
        symbol = await self.settings.money_symbol()
        refund_enabled = await self.settings.get_bool("partial_refund_enabled", True)

        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None:
                return

            remains = status.remains if status.remains is not None else 0
            delivered = (
                status.delivered if status.delivered is not None else max(0, current.quantity - remains)
            )
            refund_units = 0
            if refund_enabled and remains > 0:
                refund_units = partial_refund_units(
                    cost_units=current.cost_units,
                    quantity=current.quantity,
                    remains=remains,
                    already_refunded_units=current.refund_amount_units,
                )

            extra = self._progress_fields(status)
            extra.update({
                "remains": remains,
                "delivered_quantity": delivered,
                "completed_at": self.repos.orders.now(),
                "locked_by": None,
                "locked_until": None,
                "next_check_at": None,
            })
            moved = await self._transition(
                tx, current, OrderStatus.PARTIAL,
                actor_type=ActorType.PROVIDER,
                reason=f"تنفيذ جزئي — المتبقي {remains}",
                extra=extra,
                provider_status_raw=status.raw_status,
            )
            if not moved:
                return

            refunded = 0
            if refund_units > 0:
                transaction = await self.wallet.refund_order(
                    tx,
                    user_id=current.user_id,
                    order_id=current.id,
                    amount_units=refund_units,
                    partial=True,
                    description=f"استرجاع جزئي للطلب #{current.id} (متبقي {remains})",
                )
                refunded = transaction.amount_units if transaction else 0

            title, message = templates.order_partial(
                code=current.public_code or f"#{current.id}",
                delivered=delivered,
                quantity=current.quantity,
                refund_units=refunded,
                symbol=symbol,
            )
            await self.notifications.notify_order(
                tx,
                user_id=current.user_id,
                order_id=current.id,
                event=NotificationType.ORDER_PARTIAL,
                title=title,
                message=message,
            )
        logger.info("الطلب %s نُفِّذ جزئياً (متبقي %s)", order.id, status.remains)

    async def _audit_in_tx(
        self, tx: Tx, audit: dict | None, *, actor_id: int | None, order_id: int, refunded: int
    ) -> None:
        """تسجيل التدقيق **داخل** معاملة الاسترجاع نفسها: إن فشل التدقيق سقط الاسترجاع كله (لا مال بلا أثر)."""
        if not audit:
            return
        await self.audit.log(
            tx,
            action=audit["action"],
            admin_id=actor_id,
            target_type="order",
            target_id=order_id,
            details={**audit.get("details", {}), "refunded_units": refunded},
            source="telegram",
        )

    async def _apply_canceled(
        self,
        order: Order,
        *,
        reason: str,
        actor_type: str = ActorType.PROVIDER,
        actor_id: int | None = None,
        audit: dict | None = None,
    ) -> int:
        """
        إلغاء الطلب مع استرجاع كامل المبلغ وإشعار المستخدم.

        `audit`: {"action": ..., "details": {...}} يُكتب في المعاملة نفسها (ذرّياً مع الاسترجاع).

        المخرجات: المبلغ المسترجع.
        """
        symbol = await self.settings.money_symbol()
        clean_reason = sanitize(reason)[:300]
        refunded = 0

        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None or is_final(current.status):
                return 0
            moved = await self._transition(
                tx, current, OrderStatus.CANCELED,
                actor_type=actor_type, actor_id=actor_id, reason=clean_reason,
                extra={
                    "cancelled_at": self.repos.orders.now(),
                    "locked_by": None,
                    "locked_until": None,
                    "next_check_at": None,
                },
            )
            if not moved:
                return 0

            canceled_order = await self.repos.orders.get(order.id)
            if canceled_order is None:
                return 0
            refunded = await self._refund_full(
                tx, canceled_order, reason=clean_reason, actor_type=actor_type, actor_id=actor_id
            )

            code = current.public_code or f"#{current.id}"
            title, message = templates.order_canceled(
                code=code, refund_units=refunded, symbol=symbol
            )
            await self.notifications.notify_order(
                tx,
                user_id=current.user_id,
                order_id=current.id,
                event=NotificationType.ORDER_CANCELED,
                title=title,
                message=message,
            )
            await self._audit_in_tx(tx, audit, actor_id=actor_id, order_id=order.id, refunded=refunded)
        logger.info("أُلغي الطلب %s (%s) واسترُجع %s", order.id, clean_reason, refunded)
        return refunded

    async def _handle_unknown_status(self, order: Order, raw_status: str | None) -> None:
        """تسجيل حالة مزود غير معروفة دون تغيير حالة الطلب (سلامة أولاً)."""
        clean = sanitize(str(raw_status))[:100]
        async with self.db.transaction() as tx:
            await self.repos.error_logs.log(
                tx,
                message=f"حالة مزود غير معروفة للطلب #{order.id}: {clean}",
                level="WARNING",
                source="order_service",
                error_type="UnknownProviderStatus",
                user_id=order.user_id,
            )
        # المزود ردّ فعلاً (الاتصال سليم) لكن بحالة لا نعرفها: فاصل الفحص العادي + ملاحظة ظاهرة للأدمن، بلا عدّاد إخفاق
        await self._release_after_check(order, note=f"حالة غير معروفة: {clean}")
        logger.warning("حالة مزود غير معروفة للطلب %s: %s", order.id, clean)

    async def _release_after_check(
        self,
        order: Order,
        *,
        progress=None,
        ok: bool = True,
        error: str | None = None,
        note: str | None = None,
    ) -> None:
        """
        فك حجز الطلب بعد محاولة فحص، وتحديد موعد الفحص القادم، وتسجيل نتيجة المحاولة.

        المدخلات:
            progress : حالة المزود الناجحة (تُحفظ أرقام التقدم وحالته الخام).
            ok       : False ⇒ **فشل اتصال** (مهلة/انقطاع/رفض مؤقت). لا يمس حالة الطلب ولا ماله ولا يعيد الإرسال.
            error    : نص الفشل (مع ok=False) ⇒ يُكتب في `last_check_error` لا `last_error`.
            note     : ملاحظة مع استعلام ناجح (حالة غير معروفة…) ⇒ تُكتب في `last_check_error` دون عدّ إخفاق.

        السياسة (انظر `core/order_schedule.py`): النجاح ⇒ فاصل أساسي يتدرج ببطء بعمر الطلب وبسقف صغير؛ الفشل ⇒ تباطؤ
        أسّي حسب الإخفاقات المتتالية لهذا الطلب بسقف قابل للضبط. ونجاح الاستعلام يمسح خطأ الفحص السابق.
        """
        now_iso = self.repos.orders.now()
        if ok:
            base = await self.settings.get_int("order_check_interval_seconds", 120)
            active_max = await self.settings.get_int("order_check_active_max_seconds", 300)
            reference = parse_iso(order.submitted_at) or parse_iso(order.created_at)
            age = (utc_now() - reference).total_seconds() if reference else 0.0
            delay = success_delay_seconds(base=base, active_max=active_max, age_seconds=age)
            fields: dict = {
                "last_checked_at": now_iso,
                "last_check_ok_at": now_iso,
                "check_fail_streak": 0,
                "last_check_error": sanitize(note)[:300] if note else None,
            }
        else:
            error_max = await self.settings.get_int("order_check_error_max_seconds", 600)
            streak = int(order.check_fail_streak or 0) + 1
            delay = failure_delay_seconds(streak=streak, error_max=error_max)
            fields = {
                "last_checked_at": now_iso,
                "check_fail_streak": streak,
                "last_check_error": sanitize(error or "تعذر الفحص")[:300],
            }
        if progress is not None:
            fields.update(self._progress_fields(progress, with_check_fields=False))
        async with self.db.transaction() as tx:
            await self.repos.orders.update_fields(tx, order.id, **fields)
            await self.repos.orders.release_lock(tx, order.id, next_check_at=iso_plus_seconds(delay))

    # ===================================================================== #
    #                        إجراءات المستخدم والأدمن                       #
    # ===================================================================== #

    async def cancel_by_user(self, user: User, order_id: int) -> int:
        """
        إلغاء المستخدم لطلبه قبل إرساله للمزود (القرار D11).

        المخرجات: المبلغ المسترجع.

        الاستثناءات:
            OrderError                  : الطلب ليس للمستخدم أو غير موجود.
            InvalidStateTransitionError : الطلب غادر حالة الانتظار (لا يمكن الإلغاء).
            ValidationError             : الإلغاء الذاتي معطّل من الإعدادات.
        """
        await self.auth.guard(user)
        if not await self.settings.get_bool("user_cancel_before_submit", True):
            raise ValidationError(
                "إلغاء المستخدم معطّل", user_message="⚠️ إلغاء الطلبات غير متاح حالياً."
            )

        order = await self.repos.orders.get(order_id)
        if order is None or order.user_id != user.id:
            raise OrderError("الطلب غير موجود", user_message="❌ لم يتم العثور على هذا الطلب.")
        if order.status != OrderStatus.PENDING:
            raise InvalidStateTransitionError(
                f"لا يمكن إلغاء الطلب {order_id} في الحالة {order.status}",
                user_message="⚠️ لا يمكن الإلغاء الآن — بدأ تنفيذ الطلب بالفعل.",
            )

        refunded = await self._apply_canceled(
            order, reason="إلغاء بطلب المستخدم", actor_type=ActorType.USER, actor_id=user.id
        )
        if refunded <= 0:
            # سبقنا إلغاء آخر (ضغطة مزدوجة) أو بدأ الإرسال بين الفحص والمعاملة: لا نُظهر «أُلغي واسترجع 0»
            raise InvalidStateTransitionError(
                f"الطلب {order_id} لم يعد قابلاً للإلغاء (سبقه إجراء آخر)",
                user_message="⚠️ هذا الطلب أُلغي أو تغيّرت حالته بالفعل — راجع «📦 طلباتي».",
            )
        return refunded

    async def admin_cancel(self, actor: User, order_id: int, reason: str) -> int:
        """
        إلغاء طلب من الأدمن مع استرجاع كامل (صلاحية `orders.cancel`).

        المخرجات: المبلغ المسترجع.
        """
        await self.auth.require_permission(actor, Permission.ORDERS_CANCEL, context=f"order:{order_id}")
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")
        await self.auth.ensure_not_self_dealing(
            actor, order.user_id, what="إلغاء واسترجاع طلبك", context=f"order:{order_id}"
        )
        if is_final(order.status):
            raise InvalidStateTransitionError(
                f"الطلب {order_id} في حالة نهائية ({order.status})",
                user_message="⚠️ هذا الطلب مغلق ولا يقبل الإلغاء.",
            )
        self._ensure_not_in_flight(order)

        if order.status in _HELD_AT_PROVIDER and order.provider_order_id:
            return await self._cancel_held_order(actor, order, reason)

        # لم يصل المزود بعد (pending) أو بلا رقم عنده: لا شيء يُتحقق منه لدى المزود
        return await self._apply_canceled(
            order, reason=reason, actor_type=ActorType.ADMIN, actor_id=actor.id,
            audit={"action": "orders.cancel", "details": {"reason": reason, "provider_verified": False}},
        )

    async def _block_cancel(self, actor: User, order: Order, *, why: str, message: str, raw_status: str | None = None) -> None:
        """رفض إلغاء بسبب غياب تأكيد المزود: يُدقَّق الرفض ولا يُمسّ أي رصيد."""
        await self.audit.log_standalone(
            action="orders.cancel_blocked",
            admin_id=actor.id,
            target_type="order",
            target_id=order.id,
            details={"why": why, "provider_status": raw_status, "status": order.status},
            source="telegram",
        )
        raise OrderError(f"رُفض إلغاء الطلب {order.id}: {why}", user_message=message)

    async def _cancel_held_order(self, actor: User, order: Order, reason: str) -> int:
        """
        إلغاء طلب موجود عند المزود — **لا استرجاع قبل تأكيد المزود**.

        الخطوات: (1) استعلام حي عن الحالة ⇒ (2) إن كانت نهائية طُبّقت كما هي (مكتمل/جزئي/فاشل/ملغى) ⇒
        (3) إن كان ما زال يعمل أُرسل طلب إلغاء ثم أُعيد الاستعلام ⇒ (4) الاسترجاع فقط إن أكّد المزود «Canceled».
        فشل الاستعلام أو الغموض يرفض العملية بلا أي حركة مالية (فشل الاستعلام ليس دليلاً على شيء).
        للاسترجاع رغم عدم التأكيد مسار منفصل صريح: `admin_force_refund`.
        """
        provider = await self.repos.providers.get(order.provider_id)
        if provider is None:
            await self._block_cancel(
                actor, order, why="provider_missing",
                message="⚠️ المزود غير موجود: تعذّر التحقق من الطلب. لم يُلغَ ولم يُسترجع شيء.",
            )
        try:
            live = await self.providers.fetch_status(provider, order)
        except ProviderError:
            await self._block_cancel(
                actor, order, why="provider_unreachable",
                message=(
                    "⚠️ تعذّر التحقق من حالة الطلب لدى المزود الآن، لذلك <b>لم يُلغَ ولم يُسترجع شيء</b>.\n"
                    "أعد المحاولة بعد قليل. (فشل الاستعلام لا يعني أن الطلب لم يُنفَّذ.)"
                ),
            )
        mapped = map_provider_status(live.raw_status)

        if mapped is None:
            await self._block_cancel(
                actor, order, why="unknown_provider_status", raw_status=live.raw_status,
                message="⚠️ حالة الطلب لدى المزود غير معروفة للنظام، لم يُلغَ ولم يُسترجع شيء. راجع لوحة المزود.",
            )
        if mapped == OrderStatus.CANCELED:
            return await self._confirmed_cancel(actor, order, reason, live.raw_status)
        if mapped in (OrderStatus.COMPLETED, OrderStatus.PARTIAL, OrderStatus.FAILED):
            # الحقيقة نُقلت إلى النظام (يتحدث الطلب ويُسترجع ما يلزم تلقائياً) ثم يُبلَّغ الأدمن بأن الإلغاء لم يعد مطروحاً
            await self._apply_status(order, live)
            fresh = await self.repos.orders.get(order.id)
            await self._block_cancel(
                actor, order, why=f"provider_reports_{mapped}", raw_status=live.raw_status,
                message=(
                    f"ℹ️ المزود يفيد أن الطلب «{order_status_text(mapped)}»؛ حُدّثت حالته في النظام "
                    f"({order_status_text(fresh.status if fresh else mapped)}). لا يمكن إلغاء ما نُفّذ — "
                    "إن رأيت أن للعميل حقاً في الاسترجاع فاستخدم «استرجاع إجباري» بصلاحية التجاوز."
                ),
            )

        # ما زال عند المزود (Pending / In progress): نطلب الإلغاء ثم نتحقق
        accepted = await self.providers.cancel_at_provider(provider, order)
        confirmed = None
        if accepted:
            try:
                confirmed = await self.providers.fetch_status(provider, order)
            except ProviderError:
                confirmed = None
        if confirmed is not None and map_provider_status(confirmed.raw_status) == OrderStatus.CANCELED:
            return await self._confirmed_cancel(actor, order, reason, confirmed.raw_status)

        await self._block_cancel(
            actor, order,
            why="cancel_accepted_unconfirmed" if accepted else "cancel_not_accepted",
            raw_status=(confirmed or live).raw_status,
            message=(
                "⏳ أُرسل طلب الإلغاء للمزود لكنه لم يؤكد الإلغاء بعد. لم يُسترجع شيء؛ "
                "ستستمر المتابعة التلقائية وإذا أكّد المزود «Canceled» يُسترجع المبلغ تلقائياً."
                if accepted else
                "⚠️ المزود لم يقبل الإلغاء (قد لا تدعمه الخدمة) والطلب ما زال قيد العمل لديه، فلم يُسترجع شيء.\n"
                "إن كنت تتحمّل خسارة التنفيذ وتريد الاسترجاع رغم ذلك فاستخدم «استرجاع إجباري»."
            ),
        )
        return 0  # لا يُبلَغ: _block_cancel يرفع دائماً

    async def _confirmed_cancel(self, actor: User, order: Order, reason: str, raw_status: str | None) -> int:
        """المزود أكّد الإلغاء ⇒ إلغاء + استرجاع كامل + تدقيق ذرّي."""
        return await self._apply_canceled(
            order, reason=f"{reason} (أكّد المزود الإلغاء)", actor_type=ActorType.ADMIN, actor_id=actor.id,
            audit={
                "action": "orders.cancel",
                "details": {"reason": reason, "provider_verified": True, "provider_status": raw_status},
            },
        )

    async def admin_force_refund(self, actor: User, order_id: int, reason: str) -> int:
        """
        استرجاع إجباري لطلب عند المزود **دون تأكيد إلغائه** (صلاحية `orders.status_override` للأدمن الأعلى).

        قد يحصل العميل على الخدمة ويستعيد ماله معاً: لذلك يُسجَّل في التدقيق (ذرّياً مع الاسترجاع) بعلامة
        `forced` وحالة المزود المعروفة وقت القرار، ويتطلب سبباً واضحاً.
        """
        await self.auth.require_permission(
            actor, Permission.ORDERS_STATUS_OVERRIDE, context=f"order:{order_id}"
        )
        clean_reason = (reason or "").strip()
        if len(clean_reason) < 5:
            raise ValidationError(
                "سبب الاسترجاع الإجباري مطلوب", user_message="❌ اكتب سبباً واضحاً (5 أحرف على الأقل)."
            )
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")
        await self.auth.ensure_not_self_dealing(
            actor, order.user_id, what="استرجاع قيمة طلبك", context=f"order:{order_id}"
        )
        if is_final(order.status):
            raise InvalidStateTransitionError(
                f"الطلب {order_id} في حالة نهائية ({order.status})",
                user_message="⚠️ هذا الطلب مغلق ولا يقبل الاسترجاع.",
            )
        self._ensure_not_in_flight(order)
        if order.status not in _HELD_AT_PROVIDER:
            raise InvalidStateTransitionError(
                f"الاسترجاع الإجباري مخصص للطلبات عند المزود ({order.status})",
                user_message="⚠️ الاسترجاع الإجباري مخصّص للطلبات «أُرسل للمزود/قيد التنفيذ». استخدم «❌ إلغاء» أو «تعليم كفاشل».",
            )

        provider_status = None
        provider = await self.repos.providers.get(order.provider_id)
        if provider is not None and order.provider_order_id:
            try:
                provider_status = (await self.providers.fetch_status(provider, order)).raw_status
            except ProviderError:
                provider_status = "unreachable"   # يُسجَّل كما هو: القرار اتُّخذ بلا تحقق

        return await self._apply_canceled(
            order, reason=f"استرجاع إجباري: {clean_reason}", actor_type=ActorType.ADMIN, actor_id=actor.id,
            audit={
                "action": "orders.force_refund",
                "details": {"reason": clean_reason, "forced": True, "provider_status": provider_status},
            },
        )

    async def admin_mark_failed(self, actor: User, order_id: int, reason: str) -> int:
        """
        تأكيد الأدمن أن الطلب لم يُنشأ عند المزود (للطلبات غير المؤكدة) ⇒ فشل + استرجاع.

        المخرجات: المبلغ المسترجع.
        """
        await self.auth.require_permission(actor, Permission.ORDERS_REFUND, context=f"order:{order_id}")
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")
        await self.auth.ensure_not_self_dealing(
            actor, order.user_id, what="استرجاع قيمة طلبك", context=f"order:{order_id}"
        )
        if is_final(order.status):
            raise InvalidStateTransitionError(
                f"الطلب {order_id} في حالة نهائية ({order.status})",
                user_message="⚠️ هذا الطلب مغلق مسبقاً.",
            )
        self._ensure_not_in_flight(order)
        if order.status not in MARK_FAILED_ALLOWED_FROM:
            raise InvalidStateTransitionError(
                f"لا يجوز تعليم الطلب {order_id} كفاشل من الحالة {order.status}",
                user_message=(
                    "⚠️ «تعليم كفاشل» مخصّص للطلبات التي لم تصل المزود (بانتظار الإرسال/غير مؤكدة/فاشلة بلا استرجاع). "
                    "هذا الطلب عند المزود — استخدم «❌ إلغاء + استرجاع» إن قررت ذلك بعد مراجعة لوحة المزود."
                ),
            )

        refunded = await self._fail_order(
            order,
            reason=reason,
            actor_type=ActorType.ADMIN,
            actor_id=actor.id,
            notify_admins=False,
            auto_refund=True,  # قرار أدمن صريح: المال يعود فوراً
            audit={"action": "orders.refund", "details": {"reason": reason}},   # ذرّي مع الاسترجاع
        )
        return refunded

    async def probe_provider_link(self, actor: User, order_id: int, provider_order_id: str) -> str:
        """
        استعلام إعلامي (بلا أي تغيير) عمّا يردّ به المزود عن الرقم الذي ينوي الأدمن ربطه، ليُعرض قبل/مع الربط.

        لا يمنع الربط (قد يكون المزود غير متاح لحظتها)، لكنه يكشف الخطأ الإملائي أو رقم طلب آخر قبل أن يُبنى عليه
        تتبع العميل. المخرجات: سطر عربي قصير بنتيجة الاستعلام.
        """
        await self.auth.require_permission(
            actor, Permission.ORDERS_LINK_PROVIDER_ID, context=f"order:{order_id}"
        )
        order = await self.repos.orders.get(order_id)
        clean_id = str(provider_order_id).strip()
        if order is None or not clean_id:
            return "—"
        provider = await self.repos.providers.get(order.provider_id)
        if provider is None:
            return "المزود غير موجود"
        try:
            status = await self.providers.fetch_status(provider, replace(order, provider_order_id=clean_id))
        except ProviderTemporaryError:
            return "تعذّر الاستعلام الآن (مشكلة اتصال) — الربط غير مؤكَّد، تُعاد المتابعة تلقائياً"
        except ProviderError:
            return "⚠️ المزود لم يتعرف على هذا الرقم — تأكد منه"
        remains = f" · المتبقي {status.remains}" if status.remains is not None else ""
        return f"المزود يردّ: {status.raw_status or '—'}{remains}"

    async def admin_link_provider_order(self, actor: User, order_id: int, provider_order_id: str) -> bool:
        """
        ربط رقم الطلب عند المزود يدوياً (لطلب بحالة غير مؤكدة تبيّن أنه أُنشئ فعلاً).

        الاستثناءات:
            OrderError                  : الطلب غير موجود أو الرقم مستخدم لطلب آخر.
            InvalidStateTransitionError : حالة الطلب لا تسمح بالربط.
        """
        await self.auth.require_permission(
            actor, Permission.ORDERS_LINK_PROVIDER_ID, context=f"order:{order_id}"
        )
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")

        clean_id = str(provider_order_id).strip()
        if not clean_id:
            raise ValidationError("رقم الطلب فارغ", user_message="❌ أرسل رقم الطلب عند المزود.")
        conflict = await self.repos.orders.get_by_provider_order_id(order.provider_id, clean_id)
        if conflict is not None and conflict.id != order.id:
            raise OrderError(
                f"رقم المزود {clean_id} مرتبط بالطلب {conflict.id}",
                user_message=f"❌ هذا الرقم مرتبط بالطلب {conflict.public_code or conflict.id}.",
            )

        check_interval = await self.settings.get_int("order_check_interval_seconds", 120)
        async with self.db.transaction() as tx:
            moved = await self._transition(
                tx, order, OrderStatus.SUBMITTED,
                actor_type=ActorType.ADMIN, actor_id=actor.id,
                reason=f"ربط يدوي برقم المزود {clean_id}",
                extra={
                    "provider_order_id": clean_id,
                    "submitted_at": self.repos.orders.now(),
                    "next_check_at": iso_plus_seconds(check_interval),
                    "locked_by": None,
                    "locked_until": None,
                },
            )
            if moved:
                await self.audit.log(
                    tx,
                    action="orders.link_provider_id",
                    admin_id=actor.id,
                    target_type="order",
                    target_id=order_id,
                    before={"status": order.status, "provider_order_id": order.provider_order_id},
                    after={"status": OrderStatus.SUBMITTED, "provider_order_id": clean_id},
                )
                title, message = templates.order_submitted(
                    code=order.public_code or f"#{order.id}",
                    service_name=order.service_name_snapshot,
                )
                await self.notifications.notify_order(
                    tx,
                    user_id=order.user_id,
                    order_id=order.id,
                    event=NotificationType.ORDER_SUBMITTED,
                    title=title,
                    message=message,
                )
        return moved

    async def admin_override_status(
        self, actor: User, order_id: int, new_status: str, reason: str
    ) -> bool:
        """
        تجاوز إداري لحالة الطلب (للأدمن الأعلى فقط) — مع سبب إجباري وتدقيق كامل.

        لا يُجري أي حركة مالية: الاسترجاع يتم عبر الأدوات المخصصة له،
        حتى لا يحدث تغيير رصيد خارج المسار المحاسبي.

        الاستثناءات:
            PermissionDeniedError · ValidationError · OrderError
        """
        await self.auth.require_permission(
            actor, Permission.ORDERS_STATUS_OVERRIDE, context=f"order:{order_id}"
        )
        clean_reason = (reason or "").strip()
        if len(clean_reason) < 5:
            raise ValidationError(
                "سبب التجاوز مطلوب", user_message="❌ اكتب سبباً واضحاً للتجاوز (5 أحرف على الأقل)."
            )
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")
        await self.auth.ensure_not_self_dealing(
            actor, order.user_id, what="تغيير حالة طلبك", context=f"order:{order_id}"
        )
        self._validate_override(order, new_status)

        # المسار الموحّد `_transition`: التحقق من الجدول + التحديث المشروط + التاريخ — كما في كل مصدر حالة آخر.
        # (كان التجاوز يكتب الحالة والتاريخ بنفسه فيتخطى أي تحسين/حماية تُضاف إلى `_transition`.)
        extra = None
        if is_final(new_status):
            extra = {"next_check_at": None, "locked_by": None, "locked_until": None}
        if new_status == OrderStatus.COMPLETED:
            # نفس حقول إكمال المزود (وقت الاكتمال والمنفَّذ) — لكن التاريخ يوسَم «تجاوز إداري» أي بلا دليل من المزود
            extra.update({
                "completed_at": self.repos.orders.now(),
                "remains": 0,
                "delivered_quantity": order.quantity,
            })
        async with self.db.transaction() as tx:
            changed = await self._transition(
                tx, order, new_status,
                actor_type=ActorType.ADMIN, actor_id=actor.id,
                reason=f"تجاوز إداري: {clean_reason}", extra=extra,
            )
            if changed:
                await self.audit.log(
                    tx,
                    action="orders.status.override",
                    admin_id=actor.id,
                    target_type="order",
                    target_id=order_id,
                    before={"status": order.status},
                    after={"status": new_status, "reason": clean_reason},
                )
                if new_status == OrderStatus.COMPLETED:
                    title, message = templates.order_completed(
                        code=order.public_code or f"#{order.id}",
                        service_name=order.service_name_snapshot,
                        quantity=order.quantity,
                    )
                    await self.notifications.notify_order(
                        tx, user_id=order.user_id, order_id=order.id,
                        event=NotificationType.ORDER_COMPLETED, title=title, message=message,
                    )
        if changed:
            logger.warning(
                "تجاوز إداري لحالة الطلب %s: %s ← %s بواسطة %s",
                order_id, order.status, new_status, actor.id,
            )
        return changed

    @staticmethod
    def _ensure_not_in_flight(order: Order) -> None:
        """
        رفض أي قرار إداري مالي على طلب قيد الإرسال الآن (`submitting`).

        طلب المزود قد يكون في الطريق؛ استرجاع المال أو إغلاق الطلب في هذه اللحظة يعني احتمال أن يُنفَّذ
        الطلب عند المزود والعميل استعاد ماله. الانتظار قصير: المهمة الدورية تنقل العالق إلى «غير مؤكد».
        """
        if order.status == OrderStatus.SUBMITTING:
            raise InvalidStateTransitionError(
                f"الطلب {order.id} قيد الإرسال للمزود الآن",
                user_message=(
                    "⏳ الطلب قيد الإرسال للمزود الآن. انتظر قليلاً: إن نجح الإرسال يصبح «أُرسل»، وإن لم يردّ المزود "
                    "يتحول خلال دقائق إلى «غير مؤكد» فتقرر حينها بعد مراجعة لوحة المزود."
                ),
            )

    @staticmethod
    def _validate_override(order: Order, new_status: str) -> None:
        """
        سياسة التجاوز الإداري: يلتزم بآلة الحالات ولا يلمس حالات الإرسال ولا المال.

        القواعد:
            1. الانتقال لا بدّ أن يكون مسموحاً في `ALLOWED_TRANSITIONS` (لا قفز).
            2. لا تجاوز من `submitting` (قيد الإرسال) ولا من `submit_uncertain` (مساره الخاص:
               «🔗 ربط رقم المزود» أو «⛔ تعليم كفاشل + استرجاع»).
            3. لا تجاوز إلى حالات الإرسال (`pending`/`submitting`/`submit_uncertain`) — إعادة الطلب لها قد تُرسله مرتين.
            4. لا تجاوز إلى `canceled`/`refunded`: حالتان ماليتان تُنفَّذان بأداتيهما فقط (حركة + استرجاع).
            5. الحالات التي تفترض وجود الطلب عند المزود تتطلب `provider_order_id`.
        """
        assert_transition(order.status, new_status, order_id=order.id)
        if order.status in (OrderStatus.SUBMITTING, OrderStatus.SUBMIT_UNCERTAIN):
            raise InvalidStateTransitionError(
                f"لا تجاوز يدوي من الحالة {order.status}",
                user_message=(
                    "⚠️ لا يمكن تغيير حالة طلب «قيد الإرسال/غير مؤكد» يدوياً. استخدم «🔗 ربط رقم المزود» "
                    "إن وصل الطلب، أو «⛔ تعليم كفاشل + استرجاع» إن لم يصل."
                ),
            )
        if new_status in OVERRIDE_FORBIDDEN_TARGETS:
            raise InvalidStateTransitionError(
                f"التجاوز إلى {new_status} ممنوع",
                user_message=(
                    "⚠️ هذه الحالة تتطلب مساراً مخصصاً (إلغاء/استرجاع بحركة مالية) ولا تُضبط بالتجاوز اليدوي."
                ),
            )
        if new_status in OVERRIDE_NEEDS_PROVIDER_ID and not order.provider_order_id:
            raise InvalidStateTransitionError(
                f"الحالة {new_status} تتطلب رقم طلب عند المزود",
                user_message="⚠️ لا رقم لهذا الطلب عند المزود — اربط الرقم أولاً («🔗 ربط رقم المزود»).",
            )

    async def recheck_now(self, actor: User, order_id: int) -> str:
        """
        إعادة فحص فورية لحالة طلب من لوحة الأدمن.

        المخرجات: وصف نصي للنتيجة.
        """
        await self.auth.require_permission(actor, Permission.ORDERS_RECHECK, context=f"order:{order_id}")
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")
        if not order.provider_order_id:
            return "لا يمكن الفحص: الطلب بلا رقم عند المزود."
        outcome = await self._sync_one(order)
        return await self._describe_recheck(order_id, outcome)

    async def _describe_recheck(self, order_id: int, outcome: str) -> str:
        """
        وصف نتيجة الفحص الفوري للأدمن: الحالة الجديدة، أو ما يقوله المزود فعلاً إن لم تتغير، أو سبب تعذّر الاتصال.

        (كانت تُعاد كلمة `unchanged` الخام ويُؤجَّل الفحص التالي ساعة؛ الآن النتيجة وصفية ولا تؤجّل شيئاً.)
        """
        fresh = await self.repos.orders.get(order_id)
        if fresh is None:
            return "الطلب غير موجود"
        if outcome != "unchanged":
            return f"تغيّرت الحالة إلى {order_status_text(fresh.status)}"
        label = order_status_text(fresh.status)
        if fresh.check_fail_streak and fresh.last_check_error:
            return f"تعذّر الاتصال بالمزود — الحالة المحفوظة: {label} (لم يتغير شيء). {fresh.last_check_error[:80]}"
        remains = f" · المتبقي: {fresh.remains}" if fresh.remains is not None else ""
        return f"لم تتغير الحالة ({label}) — المزود يردّ: {fresh.provider_status or '—'}{remains}"

    # ===================================================================== #
    #                        الاسترداد بعد إعادة التشغيل                     #
    # ===================================================================== #

    async def recover_after_restart(self) -> dict[str, int]:
        """
        استرداد الحالة بعد إعادة تشغيل البوت.

        • الطلبات العالقة في `submitting` تُنقل إلى `submit_uncertain` (لا نعرف مصيرها).
        • الأقفال منتهية الصلاحية تُحرَّر ليعاد التقاط الطلبات.

        المخرجات: عدّادات ما تم استرداده.
        """
        recovered = await self._recover_submitting(only_expired=False, reason="انقطع تشغيل البوت أثناء إرسال الطلب")
        async with self.db.transaction() as tx:
            released = await self.repos.orders.release_expired_locks(tx)
        if recovered or released:
            logger.warning(
                "استرداد بعد الإقلاع: %s طلب غير مؤكد، %s قفل محرَّر", len(recovered), released
            )
        return {"uncertain": len(recovered), "locks_released": released}

    async def recover_stale_submissions(self) -> int:
        """
        استرداد دوري (أثناء التشغيل) للطلبات العالقة في `submitting` بعد انتهاء قفلها.

        السبب: إن استغرقت جولة الإرسال أكثر من مهلة المهمة أو انقطعت لأي سبب بعد الحجز، بقي الطلب
        `submitting` بلا عامل ولا استرداد حتى إعادة التشغيل. هنا يتحول إلى `submit_uncertain` (قد يكون
        المزود استلمه) وتُنبَّه الإدارة — ولا يُعاد إرساله تلقائياً أبداً.

        المخرجات: عدد الطلبات التي نُقلت.
        """
        recovered = await self._recover_submitting(
            only_expired=True, reason="انتهت مهلة قفل الإرسال دون رد من المزود"
        )
        if recovered:
            logger.critical("استرداد دوري: %s طلب عالق في submitting صار غير مؤكد", len(recovered))
        return len(recovered)

    async def _recover_submitting(self, *, only_expired: bool, reason: str) -> list[int]:
        """نقل طلبات `submitting` العالقة إلى `submit_uncertain` وتنبيه الأدمن وتسجيل خطأ لكل منها."""
        async with self.db.transaction() as tx:
            recovered = await self.repos.orders.recover_submitting_orders(tx, only_expired=only_expired)

        for order_id in recovered:
            order = await self.repos.orders.get(order_id)
            if order is None:
                continue
            code = order.public_code or f"#{order.id}"
            title, message = templates.admin_order_uncertain(code=code, order_id=order.id, error=reason)
            async with self.db.transaction() as tx:
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.ORDERS_VIEW,
                    token=f"order:{order.id}:uncertain",
                    title=title,
                    message=message,
                )
                await self.repos.error_logs.log(
                    tx,
                    message=f"طلب #{order.id} عالق في submitting ⇒ غير مؤكد: {reason}",
                    level="CRITICAL",
                    source="order_service",
                    error_type="SubmitStalled",
                    user_id=order.user_id,
                )
        return recovered

    async def alert_stuck_orders(self) -> int:
        """
        تنبيه الأدمن بالطلبات التي توقفت بلا تقدم لفترة طويلة.

        المخرجات: عدد الطلبات المتوقفة.
        """
        hours = await self.settings.get_int("order_stuck_alert_hours", 24)
        before = iso_plus_seconds(-hours * 3600)
        stuck = await self.repos.orders.stuck_orders(before_iso=before, limit=50)
        if not stuck:
            return 0
        title, message = templates.admin_stuck_orders(count=len(stuck), hours=hours)
        async with self.db.transaction() as tx:
            await self.notifications.notify_admins(
                tx,
                permission=Permission.ORDERS_VIEW,
                token=f"stuck:{day_bounds_utc(0)[0][:13]}",
                title=title,
                message=message,
            )
        return len(stuck)

    # ===================================================================== #
    #                                القراءة                                #
    # ===================================================================== #

    async def get_for_user(self, user: User, order_id: int) -> Order:
        """
        جلب طلب يخص المستخدم (مع منع الاطلاع على طلبات غيره).

        الاستثناءات: OrderError إذا لم يكن الطلب موجوداً أو ليس له.
        """
        order = await self.repos.orders.get(order_id)
        if order is None or order.user_id != user.id:
            raise OrderError("الطلب غير موجود", user_message="❌ لم يتم العثور على هذا الطلب.")
        return order

    async def list_for_user(
        self, user: User, *, statuses: list[str] | None = None, limit: int = 8, offset: int = 0
    ) -> list[Order]:
        """قائمة طلبات المستخدم (مع إمكانية التصفية بالحالة)."""
        return await self.repos.orders.list_by_user(
            user.id, statuses=statuses, limit=limit, offset=offset
        )

    async def count_for_user(self, user: User, *, statuses: list[str] | None = None) -> int:
        """عدد طلبات المستخدم (للتصفح بالصفحات)."""
        return await self.repos.orders.count_by_user(user.id, statuses=statuses)

    async def admin_get(self, actor: User, order_id: int) -> Order:
        """
        جلب أي طلب في النظام لعرضه في لوحة الأدمن (بعد فحص صلاحية الاطلاع).

        الاستثناءات: PermissionDeniedError · OrderError
        """
        await self.auth.require_permission(
            actor, Permission.ORDERS_VIEW, context=f"order:{order_id}"
        )
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ لم يتم العثور على هذا الطلب.")
        return order

    async def admin_list(
        self,
        actor: User,
        *,
        statuses: Sequence[str] | None = None,
        user_id: int | None = None,
        limit: int = 8,
        offset: int = 0,
    ) -> list[Order]:
        """
        قائمة طلبات لكل المستخدمين (قوائم لوحة الأدمن) — مع تصفية بالحالة أو بالمستخدم.

        الاستثناءات: PermissionDeniedError
        """
        await self.auth.require_permission(actor, Permission.ORDERS_VIEW, context="orders:list")
        return await self.repos.orders.list_by_statuses(
            statuses, user_id=user_id, limit=limit, offset=offset
        )

    async def admin_count(
        self,
        actor: User,
        *,
        statuses: Sequence[str] | None = None,
        user_id: int | None = None,
    ) -> int:
        """عدد الطلبات المطابقة للتصفية نفسها (لحساب عدد الصفحات في لوحة الأدمن)."""
        await self.auth.require_permission(actor, Permission.ORDERS_VIEW, context="orders:count")
        return await self.repos.orders.count_by_statuses(statuses, user_id=user_id)

    async def history(self, order_id: int) -> list:
        """سجل تغيّر حالات الطلب (من ماذا إلى ماذا ومتى ومن نفّذ)."""
        return await self.repos.orders.history(order_id)

    async def status_counts(self) -> dict[str, int]:
        """عدد الطلبات في كل حالة (للوحة الأدمن)."""
        return await self.repos.orders.status_counts()
