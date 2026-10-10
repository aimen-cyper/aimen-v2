"""
خدمة المستخدمين: التسجيل التلقائي عند أول استخدام، وتحديث البيانات، والحظر.

ملاحظة: هذه الخدمة لا تلمس الرصيد إطلاقاً — كل ما يتعلق بالمال في `WalletService`.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.enums import NotificationType
from core.exceptions import ValidationError
from core.permissions import Permission
from database.database import Database, Tx
from database.models import User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.channel_service import KIND_ADMIN_ALERT, ChannelService
from services.notification_service import NotificationService
from services.settings_service import SettingsService
from texts import templates
from texts.channel_posts import new_user_post
from utils.datetime_utils import day_bounds_utc, utc_now_iso
from utils.logging_setup import get_logger
from utils.validators import clean_text, normalize_username

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class UserSummary:
    """ملخص حساب المستخدم كما يُعرض له أو للأدمن."""

    user: User
    orders_count: int
    active_orders: int
    tickets_open: int
    payments_count: int


class UserService:
    """كل ما يخص حساب المستخدم عدا المال."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        audit: AuditService,
        auth: AuthService,
        notifications: NotificationService,
        channels: ChannelService | None = None,
    ) -> None:
        """تهيئة الخدمة بالاعتماديات التي تحتاجها (`channels` لإعلان المستخدمين الجدد)."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.audit = audit
        self.auth = auth
        self.notifications = notifications
        self.channels = channels

    # ------------------------------ التسجيل ------------------------------- #

    async def get_or_create(
        self,
        *,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        referrer_telegram_id: int | None = None,
    ) -> tuple[User, bool]:
        """
        جلب المستخدم أو إنشاؤه عند أول تفاعل مع البوت.

        المخرجات: (المستخدم، هل أُنشئ الآن؟)

        الاستثناءات:
            ValidationError : التسجيل مغلق من الإعدادات ومحاولة إنشاء حساب جديد.
        """
        existing = await self.repos.users.get_by_telegram_id(telegram_id)
        clean_username = normalize_username(username)

        if existing is not None:
            await self._refresh_profile(existing, clean_username, first_name, last_name)
            return (await self.repos.users.get_by_telegram_id(telegram_id) or existing), False

        if not await self.settings.registration_enabled():
            raise ValidationError(
                "التسجيل مغلق حالياً",
                user_message="🚧 التسجيل متوقف مؤقتاً. حاول لاحقاً أو تواصل مع الدعم.",
            )

        referrer_id: int | None = None
        if referrer_telegram_id and referrer_telegram_id != telegram_id:
            referrer = await self.repos.users.get_by_telegram_id(referrer_telegram_id)
            referrer_id = referrer.id if referrer else None

        async with self.db.transaction() as tx:
            # إعادة الفحص تحت قفل الكتابة: /start متزامنة من مستخدم جديد تصل هنا معاً،
            # فيُنشئ الأولُ الحساب ويستلم الباقون الحساب نفسه بدل `IntegrityError`
            raced = await self.repos.users.get_by_telegram_id(telegram_id)
            if raced is not None:
                return raced, False
            created = await self.repos.users.create(
                tx,
                telegram_id=telegram_id,
                username=clean_username,
                first_name=first_name,
                last_name=last_name,
                referrer_id=referrer_id,
            )
            await self.audit.log(
                tx,
                action="users.register",
                admin_id=None,
                target_type="user",
                target_id=created.id,
                details={"telegram_id": telegram_id, "referrer_id": referrer_id},
                source="bot",
            )
            await self._announce_new_user(tx, created)
        logger.info("تسجيل مستخدم جديد %s (تيليجرام %s)", created.id, telegram_id)
        return created, True

    async def _announce_new_user(self, tx: Tx, user: User) -> None:
        """
        إعلان تسجيل مستخدم جديد للإدارة داخل معاملة التسجيل نفسها (مرة واحدة لكل مستخدم: `newuser:{id}`).

        الوجهة: قناة تنبيهات الإدارة إن وُجدت، وإلا إشعار خاص لمن يملك `users.view`.
        فشل الإعلان لا يُلغي التسجيل (يُسجَّل في اللوق فقط).
        """
        if self.channels is None or not await self.settings.get_bool("new_user_alert_enabled", True):
            return
        try:
            total = int(await tx.fetchval("SELECT COUNT(*) FROM users", default=0))
            title, message = new_user_post(user=user, total_users=total)
            destination, _ = await self.channels.destination(KIND_ADMIN_ALERT)
            if destination is not None:
                await self.channels.enqueue(
                    tx, kind=KIND_ADMIN_ALERT, title=title, message=message, dedupe_key=f"newuser:{user.id}"
                )
            else:
                await self.notifications.notify_admins(
                    tx, permission=Permission.USERS_VIEW, token=f"newuser:{user.id}",
                    title=title, message=message, copy_to_channel=False,
                )
        except Exception:                                  # noqa: BLE001 - لا يجوز أن يمنع الإعلانُ التسجيلَ
            logger.exception("تعذّر إعلان المستخدم الجديد %s", user.id)

    async def _refresh_profile(
        self, user: User, username: str | None, first_name: str | None, last_name: str | None
    ) -> None:
        """تحديث بيانات الملف الشخصي إذا تغيّرت في تيليجرام (بدون كتابة بلا داعٍ)."""
        if (user.username or None) == username and (user.first_name or None) == (first_name or None) \
                and (user.last_name or None) == (last_name or None):
            return
        async with self.db.transaction() as tx:
            await self.repos.users.update_profile(
                tx, user.id, username=username, first_name=first_name, last_name=last_name
            )

    async def touch_activity(self, user_id: int) -> None:
        """تحديث وقت آخر نشاط للمستخدم (يُستدعى مع كل تفاعل)."""
        async with self.db.transaction() as tx:
            await self.repos.users.touch_activity(tx, user_id)

    async def mark_bot_blocked(self, user_id: int, blocked: bool = True) -> None:
        """تسجيل أن المستخدم حظر البوت (أو ألغى الحظر) لإيقاف الإشعارات عنه."""
        async with self.db.transaction() as tx:
            await self.repos.users.set_blocked_bot(tx, user_id, blocked)

    # ------------------------------- القراءة ------------------------------ #

    async def get(self, user_id: int) -> User | None:
        """جلب مستخدم بالمعرف الداخلي."""
        return await self.repos.users.get_by_id(user_id)

    async def get_by_telegram(self, telegram_id: int) -> User | None:
        """جلب مستخدم بمعرف تيليجرام."""
        return await self.repos.users.get_by_telegram_id(telegram_id)

    async def search(self, actor: User, query: str, *, limit: int = 10, offset: int = 0) -> list[User]:
        """
        بحث الأدمن عن مستخدم بالمعرف أو الاسم.

        الاستثناءات: PermissionDeniedError إذا لم يملك صلاحية `users.view`.
        """
        await self.auth.require_permission(actor, Permission.USERS_VIEW, context="users.search")
        return await self.repos.users.search(query, limit=limit, offset=offset)

    async def summary(self, user: User) -> UserSummary:
        """ملخص حساب: عدد الطلبات والطلبات النشطة والتذاكر المفتوحة وطلبات الشحن."""
        from core.order_state import ACTIVE_STATUSES

        orders_count = await self.repos.orders.count_by_user(user.id)
        active = await self.repos.orders.count_by_user(user.id, statuses=sorted(ACTIVE_STATUSES))
        tickets = await self.repos.tickets.list_by_user(user.id, limit=50)
        payments = await self.repos.payments.list_by_user(user.id, limit=50)
        return UserSummary(
            user=user,
            orders_count=orders_count,
            active_orders=active,
            tickets_open=sum(1 for ticket in tickets if ticket.status != "closed"),
            payments_count=len(payments),
        )

    async def counters(self) -> dict[str, int]:
        """عدادات عامة عن المستخدمين (للوحة الإحصائيات السريعة)."""
        start_today, _ = day_bounds_utc(0)
        return {
            "total": await self.repos.users.count_all(),
            "new_today": await self.repos.users.count_since(start_today),
            "active_today": await self.repos.users.count_active_since(start_today),
            "banned": await self.repos.users.count_banned(),
        }

    # -------------------------- إجراءات إدارية ---------------------------- #

    async def ban(self, actor: User, target_user_id: int, reason: str) -> bool:
        """
        حظر مستخدم مع تسجيل السبب وإشعاره.

        الاستثناءات: PermissionDeniedError · ValidationError (سبب فارغ).
        """
        await self.auth.require_permission(actor, Permission.USERS_BAN, context=f"user:{target_user_id}")
        clean_reason = clean_text(reason, field="سبب الحظر", max_length=200, min_length=3)

        target = await self.repos.users.get_by_id(target_user_id)
        if target is None:
            return False
        if target.id == actor.id:
            await self.auth.audit.log_security_event(
                event="self_ban_blocked", user_id=actor.id, target_type="user", target_id=target.id
            )
            raise ValidationError(
                "محاولة حظر النفس", user_message="🚫 لا يمكنك حظر حسابك بنفسك."
            )
        if target.role == "super_admin":
            # الأدمن الأعلى لا يُحظر مباشرة: يُخفَّض دوره أولاً (بحواجز set_role) ثم يُحظر
            await self.auth.audit.log_security_event(
                event="super_admin_ban_blocked", user_id=actor.id, target_type="user", target_id=target.id
            )
            raise ValidationError(
                "محاولة حظر أدمن أعلى",
                user_message="🚫 لا يُحظر الأدمن الأعلى مباشرة — خفّض دوره أولاً.",
            )
        # التسلسل الهرمي: لا يحظر أحد حساباً بمستواه أو أعلى (يُسجَّل حدث hierarchy_denied)
        await self.auth.ensure_can_manage(actor, target, action="ban")

        async with self.db.transaction() as tx:
            changed = await self.repos.users.set_ban(tx, target_user_id, banned=True, reason=clean_reason)
            if changed:
                title, message = templates.account_banned(reason=clean_reason)
                await self.notifications.notify_user_manual(
                    tx,
                    user_id=target_user_id,
                    token=f"ban:{target_user_id}:{utc_now_iso()}",
                    title=title,
                    message=message,
                    type=NotificationType.SYSTEM,
                )
                await self.audit.log(
                    tx,
                    action="users.ban",
                    admin_id=actor.id,
                    target_type="user",
                    target_id=target_user_id,
                    before={"is_banned": target.is_banned},
                    after={"is_banned": True, "reason": clean_reason},
                )
        if changed:
            logger.warning("حظر الأدمن %s المستخدم %s: %s", actor.id, target_user_id, clean_reason)
        return changed

    async def unban(self, actor: User, target_user_id: int) -> bool:
        """رفع الحظر عن مستخدم وإشعاره."""
        await self.auth.require_permission(actor, Permission.USERS_UNBAN, context=f"user:{target_user_id}")
        target = await self.repos.users.get_by_id(target_user_id)
        if target is not None:
            await self.auth.ensure_can_manage(actor, target, action="unban")
        if target is None or not target.is_banned:
            return False

        async with self.db.transaction() as tx:
            changed = await self.repos.users.set_ban(tx, target_user_id, banned=False)
            if changed:
                title, message = templates.account_unbanned()
                await self.notifications.notify_user_manual(
                    tx,
                    user_id=target_user_id,
                    token=f"unban:{target_user_id}:{utc_now_iso()}",
                    title=title,
                    message=message,
                )
                await self.audit.log(
                    tx,
                    action="users.unban",
                    admin_id=actor.id,
                    target_type="user",
                    target_id=target_user_id,
                    before={"is_banned": True},
                    after={"is_banned": False},
                )
        return changed

    async def set_note(self, actor: User, target_user_id: int, note: str) -> bool:
        """كتابة ملاحظة إدارية على حساب مستخدم (تظهر للأدمن فقط)."""
        await self.auth.require_permission(actor, Permission.USERS_NOTE, context=f"user:{target_user_id}")
        clean_note = clean_text(note, field="الملاحظة", max_length=500, min_length=1)
        async with self.db.transaction() as tx:
            changed = await self.repos.users.update_fields(tx, target_user_id, notes=clean_note)
            if changed:
                await self.audit.log(
                    tx,
                    action="users.note",
                    admin_id=actor.id,
                    target_type="user",
                    target_id=target_user_id,
                    after={"note": clean_note},
                )
        return changed
