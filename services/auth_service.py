"""
خدمة الصلاحيات والحماية.

كل إجراء حسّاس يمر من هنا مرتين:
    1. في طبقة الواجهة قبل عرض الزر أو تنفيذه.
    2. داخل الخدمة نفسها قبل تنفيذ العملية (دفاع في العمق).

لا يوجد أي أدمن مكتوب في الكود: الأدوار والصلاحيات كلها في قاعدة البيانات،
و`SUPER_ADMIN_IDS` في ملف البيئة تُستخدم للزرع الأولي والطوارئ فقط.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

from core.enums import Role
from core.exceptions import (
    MaintenanceModeError,
    PermissionDeniedError,
    UserBannedError,
    ValidationError,
)
from core.permissions import PERMISSION_MAP, Permission, is_dangerous_permission, role_level
from database.database import Database
from database.models import User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.settings_service import SettingsService
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: الأدوار التي يُسمح لها بالعمل أثناء وضع الصيانة
MAINTENANCE_BYPASS_ROLES: frozenset[str] = frozenset({Role.ADMIN, Role.SUPER_ADMIN})


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    """نتيجة تثبيت أدمن أعلى من البيئة: created / promoted / unbanned / promoted_unbanned / unchanged."""

    telegram_id: int
    action: str

    @property
    def changed(self) -> bool:
        """هل كُتب شيء في قاعدة البيانات؟"""
        return self.action != "unchanged"


class AuthService:
    """التحقق من الصلاحيات والحظر ووضع الصيانة."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        audit: AuditService,
        *,
        super_admin_ids: tuple[int, ...] = (),
    ) -> None:
        """تهيئة الخدمة مع قائمة الأدمن الأعلى القادمة من ملف البيئة (للطوارئ فقط)."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.audit = audit
        self.super_admin_ids = tuple(super_admin_ids)

    # ------------------------------ الصلاحيات ----------------------------- #

    async def permissions_of(self, user: User) -> set[str]:
        """كل الصلاحيات الفعلية للمستخدم (صلاحيات دوره + استثناءاته الفردية)."""
        return await self.repos.rbac.effective_permissions(user.id, user.role)

    async def has_permission(self, user: User, permission: str) -> bool:
        """هل يملك المستخدم هذه الصلاحية؟"""
        return await self.repos.rbac.has_permission(user.id, user.role, permission)

    async def require_permission(self, user: User, permission: str, *, context: str = "") -> None:
        """
        التأكد من امتلاك الصلاحية وإلا رفع استثناء وتسجيل المحاولة.

        الاستثناءات:
            PermissionDeniedError : المستخدم لا يملك الصلاحية (تُسجَّل المحاولة في سجل التدقيق).
        """
        if await self.has_permission(user, permission):
            return
        await self.audit.log_permission_denied(
            user_id=user.id, permission=permission, context=context
        )
        raise PermissionDeniedError(
            f"المستخدم {user.id} لا يملك الصلاحية {permission}"
        )

    async def is_admin(self, user: User) -> bool:
        """هل يملك المستخدم حق دخول لوحة التحكم أصلاً؟"""
        return await self.has_permission(user, Permission.ADMIN_ACCESS)

    def is_emergency_super_admin(self, telegram_id: int) -> bool:
        """
        هل هذا المعرف ضمن قائمة الطوارئ في ملف البيئة؟

        تُستخدم فقط عند تعذّر الوصول لقاعدة البيانات أو لإصلاح دور مفقود،
        ولا تمنح أي صلاحية بمفردها داخل المسارات العادية.
        """
        return telegram_id in self.super_admin_ids

    # --------------------------- الأدمن الأعلى من البيئة ------------------ #

    async def bootstrap_super_admins(self, telegram_ids: tuple[int, ...] | None = None) -> list[BootstrapResult]:
        """
        ضمان أن كل معرف في `SUPER_ADMIN_IDS` (من متغيرات البيئة) يملك حساب أدمن أعلى فعّالاً.

        يُستدعى عند كل إقلاع (`main.post_init`) وعند `init_db` — فيعمل على Render بلا Shell ولا تعديل قاعدة
        بيانات يدوي، ويُصلح تلقائياً دوراً مفقوداً أو حظراً حدث بالخطأ. **idempotent**: لا يكتب شيئاً لحساب سليم.
        كل تغيير يُدقَّق (`system.bootstrap_super_admin`) بالحالة قبل/بعد.

        ملاحظة تشغيلية: المعرف المذكور في البيئة مرجع الحقيقة؛ تخفيض دوره من البوت يُعاد عند الإقلاع التالي
        (لإزالة أدمن أعلى احذف معرّفه من `SUPER_ADMIN_IDS` ثم غيّر دوره).
        """
        ids = tuple(dict.fromkeys(self.super_admin_ids if telegram_ids is None else telegram_ids))
        return [await self._bootstrap_one(telegram_id) for telegram_id in ids]

    async def bootstrap_user(self, user: User) -> User:
        """تصحيح لحظي لمستخدم من قائمة البيئة (دوره ليس super_admin أو محظور) ثم إعادته محدَّثاً."""
        if not self.is_emergency_super_admin(user.telegram_id):
            return user
        if user.role == Role.SUPER_ADMIN and not user.is_banned:
            return user
        await self._bootstrap_one(user.telegram_id)
        return await self.repos.users.get_by_telegram_id(user.telegram_id) or user

    async def _bootstrap_one(self, telegram_id: int) -> BootstrapResult:
        """إنشاء/ترقية/رفع حظر حساب واحد في معاملة واحدة مع التدقيق."""
        async with self.db.transaction() as tx:
            existing = await tx.fetchone("SELECT id, role, is_banned FROM users WHERE telegram_id = ?", (telegram_id,))
            if existing is None:
                created = await self.repos.users.create(
                    tx, telegram_id=telegram_id, first_name="Super Admin", role=Role.SUPER_ADMIN
                )
                await self.audit.log(
                    tx, action="system.bootstrap_super_admin", target_type="user", target_id=created.id,
                    after={"role": str(Role.SUPER_ADMIN)}, details={"source": "SUPER_ADMIN_IDS", "result": "created"},
                    source="system",
                )
                return BootstrapResult(telegram_id=telegram_id, action="created")

            user_id, role, banned = int(existing["id"]), str(existing["role"]), bool(existing["is_banned"])
            if role == Role.SUPER_ADMIN and not banned:
                return BootstrapResult(telegram_id=telegram_id, action="unchanged")
            if role != Role.SUPER_ADMIN:
                await self.repos.users.set_role(tx, user_id, str(Role.SUPER_ADMIN))
            if banned:
                await self.repos.users.set_ban(tx, user_id, banned=False)
            action = "promoted" if role != Role.SUPER_ADMIN and not banned else (
                "unbanned" if role == Role.SUPER_ADMIN else "promoted_unbanned"
            )
            await self.audit.log(
                tx, action="system.bootstrap_super_admin", target_type="user", target_id=user_id,
                before={"role": role, "is_banned": banned},
                after={"role": str(Role.SUPER_ADMIN), "is_banned": False},
                details={"source": "SUPER_ADMIN_IDS", "result": action}, source="system",
            )
            return BootstrapResult(telegram_id=telegram_id, action=action)

    # -------------------------------- الحظر ------------------------------- #

    async def ensure_not_banned(self, user: User) -> None:
        """
        رفض تنفيذ أي إجراء لمستخدم محظور.

        الاستثناءات:
            UserBannedError : الحساب محظور، مع ذكر السبب إن وُجد.
        """
        if not user.is_banned:
            return
        reason = f" السبب: {user.ban_reason}" if user.ban_reason else ""
        raise UserBannedError(
            f"المستخدم {user.id} محظور", user_message=f"🚫 حسابك محظور من استخدام البوت.{reason}"
        )

    # ------------------------------- الصيانة ------------------------------ #

    async def ensure_available(self, user: User) -> None:
        """
        التأكد أن النظام يعمل (ليس في صيانة) — مع استثناء الأدمن.

        الاستثناءات:
            MaintenanceModeError : النظام في وضع الصيانة والمستخدم ليس أدمن.
        """
        if user.role in MAINTENANCE_BYPASS_ROLES:
            return
        if await self.settings.is_maintenance():
            raise MaintenanceModeError(
                "النظام في وضع الصيانة", user_message=await self.settings.maintenance_message()
            )

    async def guard(self, user: User, *, permission: str | None = None, context: str = "") -> None:
        """
        فحص شامل يُستدعى في بداية أي إجراء: الحظر ثم الصيانة ثم الصلاحية.

        الاستثناءات: UserBannedError · MaintenanceModeError · PermissionDeniedError
        """
        await self.ensure_not_banned(user)
        await self.ensure_available(user)
        if permission:
            await self.require_permission(user, permission, context=context)

    # ------------------------- حواجز التسلسل والإجراء الذاتي ------------------- #

    async def _deny(
        self,
        actor: User,
        *,
        event: str,
        user_message: str,
        target_id: int | None = None,
        details: dict | None = None,
    ) -> NoReturn:
        """تسجيل محاولة محجوبة كحدث أمني ثم رفع PermissionDeniedError برسالة عربية."""
        await self.audit.log_security_event(
            event=event,
            user_id=actor.id,
            target_type="user" if target_id is not None else None,
            target_id=target_id,
            details=details,
        )
        raise PermissionDeniedError(f"{event}: actor={actor.id} target={target_id}", user_message=user_message)

    async def ensure_can_manage(self, actor: User, target: User, *, action: str) -> None:
        """
        «التسلسل الهرمي»: لا يتصرف أحد في حساب مستواه مساوٍ لمستواه أو أعلى، إلا الأدمن الأعلى.

        الغاية: أدمن عادي يملك صلاحية ممنوحة استثناءً لا يستطيع تعديل زميله
        ولا رفع نفسه فوق مستواه عبر حساب آخر.

        الاستثناءات: PermissionDeniedError (مع تسجيل حدث أمني).
        """
        if actor.role == Role.SUPER_ADMIN:
            return
        if role_level(target.role) >= role_level(actor.role):
            await self._deny(
                actor,
                event="hierarchy_denied",
                user_message="🚫 لا يمكنك التصرف في حساب بمستوى مساوٍ لمستواك أو أعلى.",
                target_id=target.id,
                details={"action": action, "actor_role": actor.role, "target_role": target.role},
            )

    async def ensure_not_self_dealing(
        self, actor: User, owner_user_id: int, *, what: str, context: str = ""
    ) -> None:
        """
        مبدأ «عينان على كل عملية مالية»: لا ينفّذ الأدمن عملية مالية تعود لحسابه هو.

        المدخلات:
            owner_user_id : صاحب المال/الطلب المعني بالعملية.
            what          : وصف عربي مختصر يظهر في رسالة الرفض (مثل «اعتماد شحنتك»).

        يُعطَّل بالإعداد `security_block_self_actions` (للاختبار بحساب المالك)،
        وتبقى المحاولة مسجَّلة عند الرفض.

        الاستثناءات: PermissionDeniedError.
        """
        if actor.id != owner_user_id:
            return
        if not await self.settings.get_bool("security_block_self_actions", True):
            return
        await self._deny(
            actor,
            event="self_action_blocked",
            user_message=f"🚫 لا يمكنك {what} بنفسك — يجب أن ينفّذها أدمن آخر.",
            target_id=owner_user_id,
            details={"what": what, "context": context},
        )

    # ------------------------- إدارة أدوار المستخدمين --------------------- #

    async def set_role(self, actor: User, target_user_id: int, new_role: str) -> bool:
        """
        تغيير دور مستخدم (صلاحية `users.role.change` — للأدمن الأعلى فقط افتراضياً).

        حواجز المرحلة 9 (كلها تُسجَّل كأحداث أمنية عند الرفض):
            1. لا تغيير لدور الحساب نفسه.
            2. غير الأدمن الأعلى لا يمنح دوراً مساوياً لمستواه أو أعلى.
            3. غير الأدمن الأعلى لا يعدّل حساباً مستواه مساوٍ لمستواه أو أعلى.
            4. لا يُخفَّض آخر أدمن أعلى فعّال (حتى لا تُقفل اللوحة على الجميع).

        المخرجات: True عند التغيير الفعلي.

        الاستثناءات:
            PermissionDeniedError : المنفّذ لا يملك الصلاحية أو خالف أحد الحواجز.
            ValueError            : دور غير معروف.
        """
        await self.require_permission(actor, Permission.USERS_ROLE_CHANGE, context=f"user:{target_user_id}")
        valid_roles = {row["code"] for row in await self.repos.rbac.list_roles()}
        if new_role not in valid_roles:
            raise ValueError(f"دور غير معروف: {new_role}")

        target = await self.repos.users.get_by_id(target_user_id)
        if target is None:
            return False

        if target.id == actor.id:
            await self._deny(
                actor,
                event="self_role_change_blocked",
                user_message="🚫 لا يمكنك تغيير دور حسابك بنفسك.",
                target_id=target.id,
                details={"new_role": new_role},
            )
        if actor.role != Role.SUPER_ADMIN and role_level(new_role) >= role_level(actor.role):
            await self._deny(
                actor,
                event="role_escalation_blocked",
                user_message="🚫 لا يمكنك منح دور بمستوى مساوٍ لمستواك أو أعلى.",
                target_id=target.id,
                details={"new_role": new_role, "actor_role": actor.role},
            )
        await self.ensure_can_manage(actor, target, action="role_change")

        protected = False
        async with self.db.transaction() as tx:
            # حماية «آخر أدمن أعلى» داخل المعاملة نفسها (BEGIN IMMEDIATE): تخفيضان متزامنان لأدمنين اثنين
            # كان كلٌّ منهما يرى الآخر فعّالاً فيمرّان معاً ثم تُقفل اللوحة على الجميع
            current = await tx.fetchone("SELECT role, is_banned FROM users WHERE id = ?", (target_user_id,))
            if current is None:
                return False
            if current["role"] == Role.SUPER_ADMIN and new_role != Role.SUPER_ADMIN and not current["is_banned"]:
                other_active = await tx.fetchval(
                    "SELECT COUNT(*) FROM users WHERE role = ? AND is_banned = 0 AND id != ?",
                    (Role.SUPER_ADMIN, target_user_id),
                    default=0,
                )
                protected = other_active == 0
            changed = False
            if not protected:
                changed = await self.repos.users.set_role(tx, target_user_id, new_role)
            if changed:
                await self.audit.log(
                    tx,
                    action="users.role.change",
                    admin_id=actor.id,
                    target_type="user",
                    target_id=target_user_id,
                    before={"role": target.role},
                    after={"role": new_role},
                )
        if protected:
            # خارج المعاملة: تسجيل الحدث الأمني لا يُتراجع عنه مع الرفض
            await self._deny(
                actor,
                event="last_super_admin_protected",
                user_message="🚫 هذا آخر أدمن أعلى فعّال — عيّن غيره أولاً قبل تخفيض دوره.",
                target_id=target.id,
                details={"new_role": new_role},
            )
        if changed:
            logger.info("غيّر الأدمن %s دور المستخدم %s إلى %s", actor.id, target_user_id, new_role)
        return changed

    async def _check_override_request(
        self, actor: User, target_user_id: int, permission: str, *, granting: bool
    ) -> None:
        """
        حواجز تعديل الاستثناءات الفردية للصلاحيات (منع تصعيد الصلاحيات).

        القواعد: الصلاحية معرّفة في الكتالوج · لا تعديل لصلاحيات الحساب نفسه ·
        التسلسل الهرمي · لا يمنح أحد ما لا يملكه · الصلاحية الخطِرة تمنحها
        الأدمن الأعلى فقط.
        """
        if permission not in PERMISSION_MAP:
            raise ValidationError(
                f"صلاحية غير معرّفة: {permission}", user_message="❌ صلاحية غير معروفة."
            )
        target = await self.repos.users.get_by_id(target_user_id)
        if target is None:
            raise ValidationError(
                f"مستخدم غير موجود: {target_user_id}", user_message="❌ المستخدم غير موجود."
            )
        if target.id == actor.id:
            await self._deny(
                actor,
                event="self_permission_change_blocked",
                user_message="🚫 لا يمكنك تعديل صلاحيات حسابك بنفسك.",
                target_id=target.id,
                details={"permission": permission},
            )
        await self.ensure_can_manage(actor, target, action="permission_override")
        if not granting or actor.role == Role.SUPER_ADMIN:
            return
        if not await self.has_permission(actor, permission):
            await self._deny(
                actor,
                event="grant_unowned_permission_blocked",
                user_message="🚫 لا يمكنك منح صلاحية لا تملكها أنت.",
                target_id=target.id,
                details={"permission": permission},
            )
        if is_dangerous_permission(permission):
            await self._deny(
                actor,
                event="grant_dangerous_permission_blocked",
                user_message="🚫 منح الصلاحيات الخطِرة للأدمن الأعلى فقط.",
                target_id=target.id,
                details={"permission": permission},
            )

    async def set_user_permission(
        self, actor: User, target_user_id: int, permission: str, *, allow: bool
    ) -> None:
        """
        منح أو منع صلاحية لمستخدم بعينه (استثناء فردي يتقدم على دوره).

        الاستثناءات:
            PermissionDeniedError : المنفّذ لا يملك صلاحية إدارة الأدمن أو خالف حاجزاً.
            ValidationError       : صلاحية أو مستخدم غير موجود.
        """
        await self.require_permission(actor, Permission.ADMINS_MANAGE, context=f"user:{target_user_id}")
        await self._check_override_request(actor, target_user_id, permission, granting=allow)
        async with self.db.transaction() as tx:
            await self.repos.rbac.set_user_override(
                tx, target_user_id, permission, allow=allow, granted_by=actor.id
            )
            await self.audit.log(
                tx,
                action="admins.permission.override",
                admin_id=actor.id,
                target_type="user",
                target_id=target_user_id,
                after={"permission": permission, "allow": allow},
            )

    async def clear_user_permission(self, actor: User, target_user_id: int, permission: str) -> bool:
        """إزالة استثناء فردي وإعادة المستخدم إلى صلاحيات دوره."""
        await self.require_permission(actor, Permission.ADMINS_MANAGE, context=f"user:{target_user_id}")
        await self._check_override_request(actor, target_user_id, permission, granting=False)
        async with self.db.transaction() as tx:
            removed = await self.repos.rbac.clear_user_override(tx, target_user_id, permission)
            if removed:
                await self.audit.log(
                    tx,
                    action="admins.permission.clear",
                    admin_id=actor.id,
                    target_type="user",
                    target_id=target_user_id,
                    after={"permission": permission},
                )
        return removed
