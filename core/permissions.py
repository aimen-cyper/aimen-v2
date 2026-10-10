"""
كتالوج الصلاحيات والأدوار.

هذا الملف هو «المرجع» لأسماء الصلاحيات المستخدمة في الكود،
بينما القيم الفعلية تُخزَّن في قاعدة البيانات (جداول permissions / role_permissions)
لتبقى قابلة للتعديل من لوحة الأدمن دون تعديل الكود.

يوجد اختبار آلي (tests/test_permissions_seed.py) يتأكد أن ما في هذا الملف
مطابق تماماً لما تزرعه ملفات الترحيل في قاعدة البيانات.
"""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple

from core.enums import Role


class Permission(StrEnum):
    """
    رموز الصلاحيات كثوابت مكتوبة (لتفادي الأخطاء الإملائية في الكود).

    القيم هنا مطابقة حرفياً لكتالوج `PERMISSIONS` أدناه، ويحرس التطابق
    اختبار آلي في `tests/unit/test_permission_catalog.py`.
    """

    ADMIN_ACCESS = "admin.access"
    USERS_VIEW = "users.view"
    USERS_BALANCE_CREDIT = "users.balance.credit"
    USERS_BALANCE_DEBIT = "users.balance.debit"
    USERS_BAN = "users.ban"
    USERS_UNBAN = "users.unban"
    USERS_NOTE = "users.note"
    USERS_ROLE_CHANGE = "users.role.change"
    SERVICES_VIEW = "services.view"
    SERVICES_CREATE = "services.create"
    SERVICES_UPDATE = "services.update"
    SERVICES_PRICE = "services.price"
    SERVICES_ARCHIVE = "services.archive"
    SERVICES_SYNC = "services.sync"
    PROVIDERS_VIEW = "providers.view"
    PROVIDERS_CREATE = "providers.create"
    PROVIDERS_UPDATE = "providers.update"
    PROVIDERS_KEY_UPDATE = "providers.key.update"
    PROVIDERS_TEST = "providers.test"
    ORDERS_VIEW = "orders.view"
    ORDERS_RECHECK = "orders.recheck"
    ORDERS_CANCEL = "orders.cancel"
    ORDERS_REFUND = "orders.refund"
    ORDERS_LINK_PROVIDER_ID = "orders.link_provider_id"
    ORDERS_STATUS_OVERRIDE = "orders.status.override"
    PAYMENTS_VIEW = "payments.view"
    PAYMENTS_APPROVE = "payments.approve"
    PAYMENTS_REJECT = "payments.reject"
    PAYMENTS_METHODS = "payments.methods"
    TICKETS_VIEW = "tickets.view"
    TICKETS_REPLY = "tickets.reply"
    TICKETS_ASSIGN = "tickets.assign"
    TICKETS_CLOSE = "tickets.close"
    BROADCAST_SEND = "broadcast.send"
    NOTIFICATIONS_TEMPLATES = "notifications.templates"
    STATS_VIEW = "stats.view"
    STATS_PROFIT = "stats.profit"
    STATS_EXPORT = "stats.export"
    SETTINGS_VIEW = "settings.view"
    SETTINGS_UPDATE = "settings.update"
    SETTINGS_MAINTENANCE = "settings.maintenance"
    LOGS_VIEW = "logs.view"
    BACKUP_CREATE = "backup.create"
    BACKUP_DOWNLOAD = "backup.download"
    ADMINS_MANAGE = "admins.manage"
    SECURITY_VIEW = "security.view"
    SECURITY_MANAGE = "security.manage"


class PermissionDef(NamedTuple):
    """تعريف صلاحية واحدة."""

    code: str
    name_ar: str
    group_code: str
    is_dangerous: bool = False


# --------------------------- كتالوج الصلاحيات --------------------------- #

PERMISSIONS: tuple[PermissionDef, ...] = (
    # الدخول للوحة
    PermissionDef("admin.access", "الدخول إلى لوحة التحكم", "general"),
    # المستخدمون
    PermissionDef("users.view", "عرض المستخدمين والبحث عنهم", "users"),
    PermissionDef("users.balance.credit", "إضافة رصيد لمستخدم", "users", True),
    PermissionDef("users.balance.debit", "خصم رصيد من مستخدم", "users", True),
    PermissionDef("users.ban", "حظر مستخدم", "users", True),
    PermissionDef("users.unban", "فك حظر مستخدم", "users"),
    PermissionDef("users.note", "كتابة ملاحظة إدارية على مستخدم", "users"),
    PermissionDef("users.role.change", "تغيير دور مستخدم", "users", True),
    # الخدمات
    PermissionDef("services.view", "عرض الخدمات", "services"),
    PermissionDef("services.create", "إضافة خدمة", "services"),
    PermissionDef("services.update", "تعديل بيانات خدمة", "services"),
    PermissionDef("services.price", "تغيير سعر خدمة", "services", True),
    PermissionDef("services.archive", "تعطيل أو أرشفة خدمة", "services", True),
    PermissionDef("services.sync", "استيراد ومزامنة خدمات المزود", "services"),
    # المزودون
    PermissionDef("providers.view", "عرض المزودين", "providers"),
    PermissionDef("providers.create", "إضافة مزود", "providers", True),
    PermissionDef("providers.update", "تعديل مزود", "providers", True),
    PermissionDef("providers.key.update", "تغيير مفتاح API للمزود", "providers", True),
    PermissionDef("providers.test", "اختبار اتصال المزود وفحص رصيده", "providers"),
    # الطلبات
    PermissionDef("orders.view", "عرض الطلبات", "orders"),
    PermissionDef("orders.recheck", "إعادة فحص حالة طلب", "orders"),
    PermissionDef("orders.cancel", "إلغاء طلب", "orders", True),
    PermissionDef("orders.refund", "استرجاع مبلغ طلب", "orders", True),
    PermissionDef("orders.link_provider_id", "ربط رقم الطلب عند المزود يدوياً", "orders", True),
    PermissionDef("orders.status.override", "تغيير حالة طلب يدوياً", "orders", True),
    # المدفوعات
    PermissionDef("payments.view", "عرض طلبات الشحن", "payments"),
    PermissionDef("payments.approve", "اعتماد طلب شحن", "payments", True),
    PermissionDef("payments.reject", "رفض طلب شحن", "payments", True),
    PermissionDef("payments.methods", "إدارة طرق الدفع", "payments", True),
    # الدعم
    PermissionDef("tickets.view", "عرض تذاكر الدعم", "tickets"),
    PermissionDef("tickets.reply", "الرد على التذاكر", "tickets"),
    PermissionDef("tickets.assign", "إسناد التذاكر", "tickets"),
    PermissionDef("tickets.close", "إغلاق التذاكر", "tickets"),
    # الإذاعة والإحصائيات
    PermissionDef("broadcast.send", "إرسال رسالة جماعية", "broadcast", True),
    PermissionDef("notifications.templates", "تعديل قوالب الإشعارات", "broadcast", True),
    PermissionDef("stats.view", "عرض الإحصائيات", "stats"),
    PermissionDef("stats.profit", "عرض تقارير الأرباح والتكلفة", "stats"),
    PermissionDef("stats.export", "تصدير التقارير كملفات CSV", "stats", True),
    # الإعدادات والسجلات
    PermissionDef("settings.view", "عرض الإعدادات", "settings"),
    PermissionDef("settings.update", "تعديل الإعدادات العامة", "settings", True),
    PermissionDef("settings.maintenance", "تفعيل أو إيقاف وضع الصيانة", "settings", True),
    PermissionDef("logs.view", "عرض السجلات والأخطاء", "logs"),
    # النسخ الاحتياطي وإدارة الصلاحيات
    PermissionDef("backup.create", "إنشاء نسخة احتياطية", "backup", True),
    PermissionDef("backup.download", "تنزيل نسخة احتياطية", "backup", True),
    PermissionDef("admins.manage", "إدارة الأدوار والصلاحيات", "admins", True),
    # الأمان (المرحلة 9)
    PermissionDef("security.view", "عرض شاشة الأمان", "security"),
    PermissionDef("security.manage", "إدارة الحماية (رفع الإيقاف المؤقت)", "security", True),
)

#: خريطة سريعة: كود الصلاحية → تعريفها
PERMISSION_MAP: dict[str, PermissionDef] = {p.code: p for p in PERMISSIONS}


# ------------------------------ الأدوار ------------------------------ #


class RoleDef(NamedTuple):
    """تعريف دور واحد."""

    code: str
    name_ar: str
    level: int


ROLES: tuple[RoleDef, ...] = (
    RoleDef(Role.USER, "مستخدم", 10),
    RoleDef(Role.SUPPORT, "دعم فني", 40),
    RoleDef(Role.ADMIN, "أدمن", 70),
    RoleDef(Role.SUPER_ADMIN, "أدمن أعلى", 100),
)


#: صلاحيات الدعم الفني (عرض + تذاكر فقط)
_SUPPORT_PERMISSIONS: tuple[str, ...] = (
    "admin.access",
    "users.view",
    "orders.view",
    "orders.recheck",
    "payments.view",
    "tickets.view",
    "tickets.reply",
    "tickets.assign",
    "tickets.close",
    "services.view",
)

#: الصلاحيات الممنوعة على الأدمن العادي (حصرية للأدمن الأعلى)
_SUPER_ONLY: frozenset[str] = frozenset(
    {
        "users.role.change",
        "providers.key.update",
        "orders.link_provider_id",
        "orders.status.override",
        "stats.profit",
        "backup.create",
        "backup.download",
        "admins.manage",
        "security.manage",
    }
)

#: الصلاحيات الافتراضية لكل دور (تُزرع في جدول role_permissions)
ROLE_DEFAULTS: dict[str, tuple[str, ...]] = {
    Role.USER: (),
    Role.SUPPORT: _SUPPORT_PERMISSIONS,
    Role.ADMIN: tuple(p.code for p in PERMISSIONS if p.code not in _SUPER_ONLY),
    Role.SUPER_ADMIN: tuple(p.code for p in PERMISSIONS),
}


def all_permission_codes() -> tuple[str, ...]:
    """إرجاع كل أكواد الصلاحيات المعرَّفة في الكتالوج."""
    return tuple(p.code for p in PERMISSIONS)


def role_has_default(role: str, permission: str) -> bool:
    """هل يملك الدور هذه الصلاحية افتراضياً؟ (للاختبارات والزرع الأولي فقط)."""
    return permission in ROLE_DEFAULTS.get(role, ())


# ------------------------- تسلسل الأدوار (المرحلة 9) ------------------------- #

#: خريطة: رمز الدور ← مستواه الرقمي (الأعلى أقوى). أي دور مجهول يُعامَل كأدنى مستوى.
ROLE_LEVELS: dict[str, int] = {str(role.code): role.level for role in ROLES}


def role_level(role: str | None) -> int:
    """
    المستوى الرقمي لدور (user=10 · support=40 · admin=70 · super_admin=100).

    يُستخدم في فحص «التسلسل الهرمي»: لا يتصرف أحد في حساب مستواه مساوٍ لمستواه
    أو أعلى منه، إلا الأدمن الأعلى. الدور المجهول يرجع 0 فيكون أضعف الجميع.
    """
    return ROLE_LEVELS.get(str(role), 0) if role else 0


def is_dangerous_permission(code: str) -> bool:
    """هل الصلاحية معلَّمة «خطِرة» في الكتالوج؟ (المجهولة تُعدّ خطِرة احتياطاً)."""
    definition = PERMISSION_MAP.get(code)
    return True if definition is None else definition.is_dangerous
