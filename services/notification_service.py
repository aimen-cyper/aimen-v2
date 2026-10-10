"""
خدمة الإشعارات (Outbox Pattern).

المبدأ: لا نرسل رسالة تيليجرام أثناء معاملة قاعدة البيانات — بل نضع الإشعار في طابور
داخل نفس المعاملة التي غيّرت الحالة. النتيجة:
    • لا حدث بلا إشعار (لأن الإشعار يُحفظ مع الحدث نفسه).
    • لا إشعار بلا حدث (لأن الإشعار يسقط مع تراجع المعاملة).
    • فشل تيليجرام لا يُسقط العملية المالية إطلاقاً.

الإرسال الفعلي يتم لاحقاً عبر `dispatch_pending` التي يستدعيها job دوري (المرحلة 6)،
وهي تأخذ دالة إرسال من الخارج حتى تبقى هذه الطبقة مستقلة تماماً عن مكتبة تيليجرام.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from core.constants import (
    NOTIF_KEY_MANUAL,
    NOTIF_KEY_ORDER,
    NOTIF_KEY_PAYMENT,
    NOTIF_KEY_TICKET,
)
from core.enums import NotificationType
from core.exceptions import (
    NotificationBlockedError,
    NotificationPermanentError,
    NotificationTemporaryError,
)
from database.database import Database, Tx
from database.models import Notification
from database.repositories import Repositories
from services.settings_service import SettingsService
from utils.logging_setup import get_logger
from utils.security import sanitize

logger = get_logger(__name__)

#: توقيع دالة الإرسال التي تُمرَّر من طبقة تيليجرام
#: تُرجع معرف الرسالة المرسلة (أو None) وترفع أحد استثناءات الإشعارات عند الفشل.
NotificationSender = Callable[[int, str, str], Awaitable[int | None]]

#: مفتاح منع التكرار لإشعارات الطلبات `order:<id>:<event>` ⇒ رقم الطلب (لزر «📦 عرض الطلب»)
_ORDER_NOTICE_KEY = re.compile(r"^order:(\d+):")

#: ردّ نداء بعد إرسال إشعار طلب: (order_id, kind, chat_id, message_id) — لتسجيل مرجع إشعار الإنشاء القابل للتحديث
OrderNoticeHook = Callable[..., Awaitable[Any]]


@dataclass(slots=True)
class DispatchReport:
    """حصيلة جولة إرسال واحدة من الطابور."""

    claimed: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0
    deferred: int = 0            # لم يتسع لها وقت الجولة فعادت للطابور فوراً

    def as_dict(self) -> dict[str, int]:
        """تحويل الحصيلة إلى قاموس للتسجيل في اللوق."""
        return {
            "claimed": self.claimed,
            "sent": self.sent,
            "failed": self.failed,
            "skipped": self.skipped,
            "deferred": self.deferred,
        }


class NotificationService:
    """إدراج الإشعارات في الطابور وإرسالها لاحقاً بأمان."""

    def __init__(self, db: Database, repos: Repositories, settings: SettingsService) -> None:
        """تهيئة الخدمة."""
        self.db = db
        self.repos = repos
        self.settings = settings
        #: يُضبط من `build_services` (خدمة رسائل الطلبات)؛ None ⇒ لا تسجيل مراجع
        self.order_notice_hook: OrderNoticeHook | None = None

    # ------------------------------- الإدراج ------------------------------ #

    async def enqueue(
        self,
        tx: Tx,
        *,
        user_id: int,
        type: str,
        title: str,
        message: str,
        dedupe_key: str,
        payload: dict[str, Any] | None = None,
    ) -> int | None:
        """
        وضع إشعار في الطابور داخل معاملة قائمة.

        المخرجات: معرف الإشعار، أو None إذا كان `dedupe_key` موجوداً مسبقاً
                  (أي أن الإشعار أُرسل أو مجدول أصلاً — وهذا سلوك مقصود لمنع التكرار).
        """
        import json

        return await self.repos.notifications.enqueue(
            tx,
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            dedupe_key=dedupe_key,
            payload_json=json.dumps(payload, ensure_ascii=False) if payload else None,
        )

    async def notify_order(
        self,
        tx: Tx,
        *,
        user_id: int,
        order_id: int,
        event: str,
        title: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> int | None:
        """إشعار متعلق بطلب، بمفتاح منع تكرار مبني على (الطلب + الحدث)."""
        return await self.enqueue(
            tx,
            user_id=user_id,
            type=event,
            title=title,
            message=message,
            dedupe_key=NOTIF_KEY_ORDER.format(order_id=order_id, event=event),
            payload=payload,
        )

    async def notify_payment(
        self,
        tx: Tx,
        *,
        user_id: int,
        payment_id: int,
        event: str,
        title: str,
        message: str,
    ) -> int | None:
        """إشعار متعلق بطلب شحن."""
        return await self.enqueue(
            tx,
            user_id=user_id,
            type=event,
            title=title,
            message=message,
            dedupe_key=NOTIF_KEY_PAYMENT.format(payment_id=payment_id, event=event),
        )

    async def notify_ticket(
        self, tx: Tx, *, user_id: int, ticket_id: int, event: str, title: str, message: str
    ) -> int | None:
        """إشعار متعلق بتذكرة دعم."""
        return await self.enqueue(
            tx,
            user_id=user_id,
            type=event,
            title=title,
            message=message,
            dedupe_key=NOTIF_KEY_TICKET.format(ticket_id=ticket_id, event=event),
        )

    async def notify_user_manual(
        self, tx: Tx, *, user_id: int, token: str, title: str, message: str, type: str = NotificationType.SYSTEM
    ) -> int | None:
        """إشعار يدوي/عام بمفتاح منع تكرار يحدده المتصل."""
        return await self.enqueue(
            tx,
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            dedupe_key=NOTIF_KEY_MANUAL.format(token=token),
        )

    async def notify_admins(
        self,
        tx: Tx,
        *,
        permission: str,
        token: str,
        title: str,
        message: str,
        type: str = NotificationType.SYSTEM,
        copy_to_channel: bool = True,
    ) -> int:
        """
        إرسال تنبيه لكل من يملك صلاحية معينة (مثل `orders.view` أو `payments.approve`).

        المخرجات: عدد الإشعارات التي أُدرجت فعلاً (المكررة لا تُحتسب).

        `copy_to_channel`: تُدرج نسخة في صندوق قناة تنبيهات الإدارة (دائم، يرسله job)؛ يُعطَّل لتنبيهات
        فشل القناة نفسها تفادياً للحلقة.

        ملاحظة: نستخدم الصلاحية لا الدور، حتى يصل التنبيه لمن مُنح الصلاحية استثناءً.
        """
        admins = await self._users_with_permission(permission)
        inserted = 0
        for user_id in admins:
            notification_id = await self.enqueue(
                tx,
                user_id=user_id,
                type=type,
                title=title,
                message=message,
                dedupe_key=NOTIF_KEY_MANUAL.format(token=f"{token}:{user_id}"),
            )
            if notification_id is not None:
                inserted += 1
        if inserted and copy_to_channel:
            # نسخة واحدة لقناة التنبيهات (لا لكل أدمن) في صندوق دائم، بنفس معاملة التنبيه
            await self.repos.channel_outbox.enqueue(
                tx, kind="admin_alert", title=title, message=message, dedupe_key=f"alert:{token}"
            )
        return inserted

    async def _users_with_permission(self, permission: str) -> list[int]:
        """
        جلب معرفات المستخدمين الذين يملكون صلاحية محددة (من الدور أو باستثناء فردي).

        يستثني المحظورين ومن حظروا البوت حتى لا نُراكم إشعارات لا تصل.
        """
        rows = await self.db.fetchall(
            """
            SELECT DISTINCT u.id
              FROM users u
              LEFT JOIN role_permissions rp ON rp.role_code = u.role AND rp.permission_code = ?
              LEFT JOIN user_permissions up ON up.user_id = u.id AND up.permission_code = ?
             WHERE u.is_banned = 0
               AND u.blocked_bot = 0
               AND (
                     (rp.permission_code IS NOT NULL AND COALESCE(up.allow, 1) = 1)
                  OR up.allow = 1
                   )
            """,
            (permission, permission),
        )
        return [row["id"] for row in rows]

    # ------------------------------- الإرسال ------------------------------ #

    async def dispatch_pending(
        self,
        sender: NotificationSender,
        *,
        limit: int = 25,
        lease_seconds: int = 60,
        budget_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> DispatchReport:
        """
        إرسال دفعة من الإشعارات المنتظرة.

        المدخلات:
            sender : دالة غير متزامنة (telegram_id, title, message) → معرف الرسالة.
                     يجب أن ترفع NotificationBlockedError إذا حظر المستخدم البوت،
                     وNotificationTemporaryError عند فشل قابل لإعادة المحاولة.

        budget_seconds : سقف زمن الجولة (اختياري). متى تجاوزته توقفت الجولة وأُعيد ما لم يُرسَل إلى الطابور
                         فوراً (`deferred`) بدل أن تتراكم جولات بطيئة وتحجب بقية المهام (WP7).

        المخرجات: تقرير مختصر بعدد ما أُرسل وفشل وتُخطّي.

        ملاحظة مهمة: الحجز والإرسال والتعليم تتم في معاملات منفصلة قصيرة،
        فلا تبقى قاعدة البيانات مقفولة أثناء انتظار الشبكة.
        """
        report = DispatchReport()

        async with self.db.transaction() as tx:
            batch = await self.repos.notifications.claim_batch(
                tx, limit=limit, lease_seconds=lease_seconds
            )
        report.claimed = len(batch)
        if not batch:
            return report

        started = clock()
        for position, notification in enumerate(batch):
            if budget_seconds is not None and clock() - started >= budget_seconds:
                rest = [item.id for item in batch[position:]]
                async with self.db.transaction() as tx:
                    await self.repos.notifications.release_claims(tx, rest)
                report.deferred = len(rest)
                logger.warning("نفدت ميزانية جولة الإشعارات (%.0fث): أُعيد %d إلى الطابور", budget_seconds, len(rest))
                break
            telegram_id = await self._telegram_id_for(notification.user_id)
            if telegram_id is None:
                async with self.db.transaction() as tx:
                    await self.repos.notifications.mark_skipped(
                        tx, notification.id, "المستخدم غير موجود"
                    )
                report.skipped += 1
                continue

            match = _ORDER_NOTICE_KEY.match(notification.dedupe_key or "")
            order_id = int(match.group(1)) if match else None
            try:
                if order_id is not None and getattr(sender, "supports_order_button", False):
                    message_id = await sender(
                        telegram_id, notification.title, notification.message, order_id=order_id
                    )
                else:
                    message_id = await sender(telegram_id, notification.title, notification.message)
            except NotificationBlockedError as exc:
                await self._handle_blocked(notification, str(exc))
                report.skipped += 1
            except NotificationTemporaryError as exc:
                async with self.db.transaction() as tx:
                    await self.repos.notifications.mark_failed(
                        tx, notification.id, error=sanitize(str(exc))
                    )
                report.failed += 1
            except NotificationPermanentError as exc:
                async with self.db.transaction() as tx:
                    await self.repos.notifications.mark_failed(
                        tx, notification.id, error=sanitize(str(exc)), permanent=True
                    )
                report.failed += 1
            else:
                async with self.db.transaction() as tx:
                    await self.repos.notifications.mark_sent(tx, notification.id, message_id)
                report.sent += 1
                if (
                    order_id is not None
                    and message_id
                    and notification.type == NotificationType.ORDER_CREATED
                    and self.order_notice_hook is not None
                ):
                    # إشعار الإنشاء يتجدد بحالة الطلب (بقية إشعارات الأحداث تبقى رسائل جديدة)
                    await self.order_notice_hook(
                        order_id=order_id, kind="user_notice", chat_id=telegram_id, message_id=message_id
                    )

        logger.info("جولة إرسال إشعارات: %s", report.as_dict())
        return report

    async def _handle_blocked(self, notification: Notification, error: str) -> None:
        """تعليم الإشعار كمتخطى وتسجيل أن المستخدم حظر البوت (فلا نزعجه بإشعارات لاحقة)."""
        async with self.db.transaction() as tx:
            await self.repos.notifications.mark_skipped(tx, notification.id, sanitize(error))
            await self.repos.users.set_blocked_bot(tx, notification.user_id, True)
        logger.info("المستخدم %s حظر البوت — تم تخطي الإشعار %s", notification.user_id, notification.id)

    async def _telegram_id_for(self, user_id: int) -> int | None:
        """جلب معرف تيليجرام لمستخدم داخلي."""
        user = await self.repos.users.get_by_id(user_id)
        return user.telegram_id if user else None

    # ------------------------------- القراءة ------------------------------ #

    async def user_inbox(self, user_id: int, *, limit: int = 10, offset: int = 0) -> list[Notification]:
        """آخر إشعارات المستخدم لعرضها داخل البوت."""
        return await self.repos.notifications.list_for_user(user_id, limit=limit, offset=offset)

    async def unread_count(self, user_id: int) -> int:
        """عدد الإشعارات غير المقروءة."""
        return await self.repos.notifications.count_unread(user_id)

    async def mark_all_read(self, user_id: int) -> int:
        """تعليم كل إشعارات المستخدم كمقروءة."""
        async with self.db.transaction() as tx:
            return await self.repos.notifications.mark_read_for_user(tx, user_id)

    async def queued_count(self) -> int:
        """عدد الإشعارات المنتظرة في الطابور (مؤشر صحة النظام)."""
        return await self.repos.notifications.count_queued()
