"""
خدمة الأمان — قراءة «وضع الأمان» وإدارة الإيقاف المؤقت (المرحلة 9).

ما تقدّمه للوحة الأدمن:
    • posture()      : قائمة فحوص (سليم/تنبيه/خطر) تلخّص حالة النظام الأمنية الآن.
    • counters()     : عدّادات آخر 24 ساعة (رفض صلاحيات، إيقافات، حواجز RBAC…).
    • events()       : صفحات الأحداث الأمنية من سجل التدقيق (`security.*`).
    • team()         : قائمة طاقم الإدارة مع أدوارهم واستثناءاتهم.
    • clear_block()  : رفع الإيقاف المؤقت عن مستخدم (يُدقَّق).

مبادئ:
    • كل دالة تتحقق من صلاحية الاستدعاء داخل الخدمة (`security.view` للقراءة،
      `security.manage` للتعديل) — فلا يُستدعى منها شيء بتجاوز المعالجات.
    • لا نعرض أي سر: الفحوص تذكر «معرّف/موجود/غير موجود» فقط، لا القيم.
    • الخدمة للقراءة في معظمها؛ وحيدة الكتابة هي رفع الإيقاف، وتسجَّل في التدقيق.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.enums import Role
from core.permissions import Permission, is_dangerous_permission
from database.database import Database
from database.models import AuditLog, User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.settings_service import SettingsService
from utils.datetime_utils import iso_minus_days, utc_now_iso
from utils.fs_security import PathCheck
from utils.logging_setup import get_logger

if TYPE_CHECKING:
    from middlewares.rate_limit import AbuseGuard
    from services.backup_service import BackupService

logger = get_logger(__name__)

#: مستويات نتيجة الفحص
LEVEL_OK = "ok"
LEVEL_WARN = "warn"
LEVEL_BAD = "bad"

#: بادئة كل الأحداث الأمنية في سجل التدقيق
SECURITY_PREFIX = "security."

#: ساعات نافذة العدّادات
COUNTER_HOURS = 24


@dataclass(frozen=True, slots=True)
class EnvPosture:
    """
    لقطة من إعدادات البيئة (بلا أي قيمة سرّية) تُمرَّر من طبقة التشغيل إلى الخدمة.

    الحقول:
        bot_token_set       : هل التوكن مضبوط؟
        encryption_key_set  : هل مفتاح التشفير مضبوط؟
        alert_chat_set      : هل مضبوط معرّف دردشة التنبيهات الخارجية؟
        path_checks         : نتائج فحص صلاحيات الملفات الحسّاسة.
    """

    bot_token_set: bool = True
    encryption_key_set: bool = True
    alert_chat_set: bool = False
    path_checks: tuple[PathCheck, ...] = ()


@dataclass(frozen=True, slots=True)
class Check:
    """نتيجة فحص أمني واحد: المستوى + العنوان + تفصيل قصير."""

    level: str
    title: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class SecurityCounters:
    """عدّادات النافذة الأخيرة (24 ساعة)."""

    permission_denied: int
    rate_limit_blocks: int
    rbac_blocks: int
    money_blocks: int
    total_events: int
    top_denied: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True, slots=True)
class BlockedUser:
    """مستخدم موقوف مؤقتاً: معرّفه واسمه والمتبقي من الإيقاف وعدد مخالفاته."""

    telegram_id: int
    seconds_left: int
    strikes: int
    name: str


@dataclass(frozen=True, slots=True)
class TeamMember:
    """عضو طاقم الإدارة كما يظهر في شاشة الفريق."""

    user: User
    overrides: int
    is_banned: bool = False


@dataclass(slots=True)
class EventsPage:
    """صفحة من الأحداث الأمنية."""

    items: list[AuditLog]
    page: int
    total_pages: int
    total: int
    names: dict[int, str] = field(default_factory=dict)


#: أحداث الحواجز التي تحمي الصلاحيات والأدوار
_RBAC_EVENTS = (
    "hierarchy_denied",
    "self_action_blocked",
    "self_role_change_blocked",
    "role_escalation_blocked",
    "last_super_admin_protected",
    "self_permission_change_blocked",
    "grant_unowned_permission_blocked",
    "grant_dangerous_permission_blocked",
    "self_ban_blocked",
    "super_admin_ban_blocked",
)

#: أحداث الحواجز المالية
_MONEY_EVENTS = ("over_credit_blocked", "adjust_cap_exceeded", "adjust_daily_cap_exceeded")


class SecurityService:
    """قراءة وضع الأمان وإدارة الإيقاف المؤقت."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        auth: AuthService,
        audit: AuditService,
        backups: BackupService | None = None,
    ) -> None:
        """تهيئة الخدمة بالاعتماديات اللازمة (`backups` اختيارية: بدونها يُهمل فحص النسخ)."""
        self.backups = backups
        self.db = db
        self.repos = repos
        self.settings = settings
        self.auth = auth
        self.audit = audit

    # ------------------------------ العدّادات ------------------------------ #

    async def counters(self, actor: User) -> SecurityCounters:
        """عدّادات الأحداث الأمنية خلال آخر 24 ساعة."""
        await self.auth.require_permission(actor, Permission.SECURITY_VIEW, context="security.counters")
        since = iso_minus_days(1)
        audit = self.repos.audit
        denied = await audit.count_action("security.permission_denied", since_iso=since)
        blocks = await audit.count_action("security.rate_limit_block", since_iso=since)
        rbac = sum([await audit.count_action(f"security.{name}", since_iso=since) for name in _RBAC_EVENTS])
        money = sum([await audit.count_action(f"security.{name}", since_iso=since) for name in _MONEY_EVENTS])
        total = await audit.count_by_action_prefix(SECURITY_PREFIX, since_iso=since)
        top = await audit.top_actors_by_action_prefix("security.permission_denied", since_iso=since, limit=3)
        return SecurityCounters(denied, blocks, rbac, money, total, tuple(top))

    # ------------------------------ الأحداث ------------------------------- #

    async def events(self, actor: User, *, page: int, page_size: int = 8) -> EventsPage:
        """صفحة من الأحداث الأمنية (الأحدث أولاً) مع أسماء المنفّذين."""
        await self.auth.require_permission(actor, Permission.SECURITY_VIEW, context="security.events")
        total = await self.repos.audit.count_by_action_prefix(SECURITY_PREFIX)
        total_pages = max(1, -(-total // page_size))
        page = min(max(1, page), total_pages)
        items = await self.repos.audit.list_by_action_prefix(
            SECURITY_PREFIX, limit=page_size, offset=(page - 1) * page_size
        )
        names: dict[int, str] = {}
        for entry in items:
            if entry.admin_id and entry.admin_id not in names:
                user = await self.repos.users.get_by_id(entry.admin_id)
                names[entry.admin_id] = user.display_name if user else str(entry.admin_id)
        return EventsPage(items=items, page=page, total_pages=total_pages, total=total, names=names)

    # ------------------------------- الفريق -------------------------------- #

    async def team(self, actor: User) -> list[TeamMember]:
        """طاقم الإدارة (دعم/أدمن/أدمن أعلى) مرتباً من الأعلى دوراً."""
        await self.auth.require_permission(actor, Permission.SECURITY_VIEW, context="security.team")
        overrides = await self.repos.rbac.count_overrides_by_user()
        members: list[TeamMember] = []
        for role in (Role.SUPER_ADMIN, Role.ADMIN, Role.SUPPORT):
            for user in await self.repos.users.list_by_role(str(role)):
                members.append(TeamMember(user, overrides.get(user.id, 0), bool(user.is_banned)))
        return members

    # ------------------------------ وضع الأمان ------------------------------ #

    async def posture(self, actor: User, env: EnvPosture) -> list[Check]:
        """
        قائمة فحوص الأمان الحالية.

        المدخلات:
            env : لقطة البيئة (التوكن/المفتاح/الملفات) من طبقة التشغيل.

        كل فحص مستقل؛ فشل قراءة أحدها لا يُسقط البقية لأنه يُحسب من قراءة مباشرة.
        """
        await self.auth.require_permission(actor, Permission.SECURITY_VIEW, context="security.posture")
        return await self.run_checks(env)

    async def run_checks(self, env: EnvPosture) -> list[Check]:
        """
        تنفيذ الفحوص بلا فحص صلاحية — **للاستخدام الداخلي وسكربت `security_check` فقط**.

        المعالجات والواجهات تستعمل `posture(actor, env)` الذي يتحقق من الصلاحية أولاً.
        """
        checks: list[Check] = []
        checks += self._secrets_checks(env)
        checks.append(await self._super_admin_check())
        checks.append(self._files_check(env))
        checks.append(await self._providers_https_check())
        checks.append(await self._privileged_overrides_check())
        checks.append(await self._self_dealing_check())
        checks.append(await self._caps_check())
        checks.append(await self._rate_limit_check())
        checks.append(await self._maintenance_check())
        checks.append(await self._errors_check())
        checks += await self._backup_checks()
        return checks

    @staticmethod
    def _secrets_checks(env: EnvPosture) -> list[Check]:
        """التوكن ومفتاح التشفير وقناة التنبيه (يُذكر الوجود فقط لا القيمة)."""
        return [
            Check(LEVEL_OK if env.bot_token_set else LEVEL_BAD, "توكن البوت",
                  "مضبوط" if env.bot_token_set else "غير مضبوط في البيئة"),
            Check(LEVEL_OK if env.encryption_key_set else LEVEL_BAD, "مفتاح تشفير مفاتيح المزودين",
                  "مضبوط" if env.encryption_key_set else "غير مضبوط — مفاتيح المزودين غير محمية"),
            Check(LEVEL_OK if env.alert_chat_set else LEVEL_WARN, "قناة التنبيهات الخارجية",
                  "مضبوطة" if env.alert_chat_set else "غير مضبوطة — التنبيهات تصل رسائل خاصة فقط"),
        ]

    async def _super_admin_check(self) -> Check:
        """عدد الأدمن الأعلى الفعّالين (واحد فقط = لا بديل عند فقدان الحساب)."""
        supers = [u for u in await self.repos.users.list_by_role(str(Role.SUPER_ADMIN)) if not u.is_banned]
        if not supers:
            return Check(LEVEL_BAD, "الأدمن الأعلى", "لا يوجد أدمن أعلى فعّال!")
        if len(supers) == 1:
            return Check(LEVEL_WARN, "الأدمن الأعلى", "حساب واحد فقط — أضف بديلاً احتياطياً")
        return Check(LEVEL_OK, "الأدمن الأعلى", f"{len(supers)} حسابات فعّالة")

    @staticmethod
    def _files_check(env: EnvPosture) -> Check:
        """صلاحيات الملفات الحسّاسة (.env/قاعدة/نسخ/لوق)."""
        if not env.path_checks:
            return Check(LEVEL_OK, "صلاحيات الملفات", "لا ينطبق على هذا النظام أو لا توجد ملفات بعد")
        bad = [item for item in env.path_checks if item.insecure]
        if not bad:
            return Check(LEVEL_OK, "صلاحيات الملفات", f"{len(env.path_checks)} مسار حسّاس مقصور على المالك")
        names = "، ".join(item.label.split(" (")[0] for item in bad[:3])
        return Check(LEVEL_WARN, "صلاحيات الملفات", f"{len(bad)} مسار مفتوح لغير المالك: {names}")

    async def _providers_https_check(self) -> Check:
        """أي مزود فعّال برابط غير https مكشوف لاعتراض المفتاح."""
        bad = [p.name for p in await self.repos.providers.list_all(active_only=True)
               if not str(p.api_url).lower().startswith("https://")]
        if bad:
            return Check(LEVEL_BAD, "اتصال المزودين", f"رابط غير مشفّر (https) للمزود: {'، '.join(bad[:3])}")
        return Check(LEVEL_OK, "اتصال المزودين", "كل المزودين الفعّالين عبر https")

    async def _privileged_overrides_check(self) -> Check:
        """منح صلاحيات خطرة فردياً لغير الأدمن الأعلى."""
        risky = 0
        for user_id, code in await self.repos.rbac.list_allow_overrides():
            user = await self.repos.users.get_by_id(user_id)
            if user and user.role != Role.SUPER_ADMIN and is_dangerous_permission(code):
                risky += 1
        if risky:
            return Check(LEVEL_WARN, "الاستثناءات الفردية", f"{risky} صلاحية خطرة ممنوحة فردياً لغير الأدمن الأعلى — راجعها")
        return Check(LEVEL_OK, "الاستثناءات الفردية", "لا صلاحيات خطرة ممنوحة فردياً")

    async def _self_dealing_check(self) -> Check:
        """حماية «أربع أعين» ضد تنفيذ الأدمن عمليات مالية على نفسه."""
        if await self.settings.get_bool("security_block_self_actions", True):
            return Check(LEVEL_OK, "منع التنفيذ الذاتي", "مفعّل")
        return Check(LEVEL_WARN, "منع التنفيذ الذاتي", "معطّل — يستطيع الأدمن اعتماد شحنته بنفسه")

    async def _caps_check(self) -> Check:
        """سقوف التسوية اليدوية للأدمن."""
        single = await self.settings.get_money_units("admin_adjust_max_units", 0)
        daily = await self.settings.get_money_units("admin_adjust_daily_max_units", 0)
        if single <= 0 and daily <= 0:
            return Check(LEVEL_WARN, "سقف التسوية اليدوية", "بلا سقف — أي أدمن يضيف أي مبلغ")
        return Check(LEVEL_OK, "سقف التسوية اليدوية",
                     "سقف للعملية الواحدة واليومي" if single > 0 and daily > 0 else "سقف جزئي (أحدهما فقط)")

    async def _rate_limit_check(self) -> Check:
        """حدود الاستخدام والإيقاف المؤقت."""
        general = await self.settings.get_int("rate_limit_actions_per_minute", 25)
        sensitive = await self.settings.get_int("rate_limit_sensitive_per_minute", 6)
        strikes = await self.settings.get_int("rate_limit_strikes_before_block", 5)
        return Check(LEVEL_OK, "حدود الاستخدام", f"عام {general}/د · حسّاس {sensitive}/د · إيقاف بعد {strikes} مخالفات")

    async def _maintenance_check(self) -> Check:
        """وضع الصيانة (معلومة تشغيلية)."""
        if await self.settings.get_bool("maintenance_mode", False):
            return Check(LEVEL_WARN, "وضع الصيانة", "مفعّل — العملاء لا يستطيعون الاستخدام")
        return Check(LEVEL_OK, "وضع الصيانة", "غير مفعّل")

    async def _errors_check(self) -> Check:
        """أخطاء النظام في آخر 24 ساعة."""
        count = await self.audit.errors_since(iso_minus_days(1))
        if count:
            return Check(LEVEL_WARN, "أخطاء النظام (24 ساعة)", f"{count} خطأ — راجع سجل الأخطاء")
        return Check(LEVEL_OK, "أخطاء النظام (24 ساعة)", "لا أخطاء")

    async def _backup_checks(self) -> list[Check]:
        """
        فحوص النسخ الاحتياطي (م10): وجود نسخة سليمة وحداثتها، ونسخة خارج السيرفر.

        بلا `backups` (خدمة غير موصولة) لا فحص — لا نختلق «سليم».
        """
        if self.backups is None:
            return []
        summary = await self.backups.build_summary()
        if summary.last_ok is None:
            main = Check(LEVEL_WARN, "النسخ الاحتياطي", "لا توجد أي نسخة سليمة بعد — خذ نسخة الآن")
        elif summary.overdue:
            main = Check(LEVEL_WARN, "النسخ الاحتياطي", "متأخر عن موعده — راجع سجل الأخطاء")
        elif not summary.auto_enabled:
            main = Check(LEVEL_WARN, "النسخ الاحتياطي", "التلقائي معطّل (آخر نسخة يدوية فقط)")
        else:
            main = Check(LEVEL_OK, "النسخ الاحتياطي", f"آخر نسخة سليمة منذ {summary.age_hours:.0f} ساعة")
        if summary.off_server_copy:
            off = Check(LEVEL_OK, "نسخة خارج السيرفر", "تُرسل لقناة النسخ")
        else:
            off = Check(LEVEL_WARN, "نسخة خارج السيرفر", "غير مفعّلة — تلف القرص يُفقد النسخ والقاعدة معاً")
        return [main, off]

    # ------------------------------ الإيقاف المؤقت ------------------------------ #

    async def blocked_users(self, actor: User, guard: AbuseGuard | None) -> list[BlockedUser]:
        """
        قائمة الموقوفين مؤقتاً الآن (الأطول إيقافاً أولاً).

        الاسم يُجلب من قاعدة البيانات إن كان المستخدم مسجَّلاً، وإلا يظهر المعرّف.
        """
        await self.auth.require_permission(actor, Permission.SECURITY_VIEW, context="security.blocks")
        if guard is None:
            return []
        result: list[BlockedUser] = []
        for info in guard.blocked_snapshot():
            user = await self.repos.users.get_by_telegram_id(info.telegram_id)
            result.append(
                BlockedUser(
                    telegram_id=info.telegram_id,
                    seconds_left=info.seconds_left,
                    strikes=info.strikes,
                    name=user.display_name if user else str(info.telegram_id),
                )
            )
        return result

    async def clear_block(self, actor: User, telegram_id: int, guard: AbuseGuard | None) -> bool:
        """
        رفع الإيقاف المؤقت عن مستخدم (يتطلب `security.manage`).

        المخرجات: True إن كان موقوفاً فعلاً وأُزيل الإيقاف، False إن لم يكن موقوفاً.
        يُسجَّل في التدقيق (`security.block_cleared`) لأن رفع الحماية يجب أن يترك أثراً.
        """
        await self.auth.require_permission(actor, Permission.SECURITY_MANAGE, context="security.clear_block")
        if guard is None or not guard.is_blocked(telegram_id):
            return False
        guard.clear(telegram_id)
        await self.audit.log_security_event(
            event="block_cleared",
            user_id=actor.id,
            target_type="telegram_user",
            target_id=telegram_id,
            details={"cleared_at": utc_now_iso(), "by_role": str(actor.role)},
        )
        return True

    @staticmethod
    def seconds_text(seconds: int) -> str:
        """تحويل ثوانٍ متبقية إلى نص قصير (مثل «3 د 20 ث»)."""
        minutes, rest = divmod(max(0, seconds), 60)
        return f"{minutes} د {rest} ث" if minutes else f"{rest} ث"


__all__ = [
    "BlockedUser",
    "Check",
    "EnvPosture",
    "EventsPage",
    "LEVEL_BAD",
    "LEVEL_OK",
    "LEVEL_WARN",
    "SecurityCounters",
    "SecurityService",
    "TeamMember",
]

