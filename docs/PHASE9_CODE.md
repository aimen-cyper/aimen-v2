# الكود الكامل — المرحلة 9 (الأمان والموثوقية)

كل ما في هذا الملف منسوخ آلياً من ملفات المشروع الفعلية وقت كتابة التقرير.

> الملفات الكبيرة التي تغيّر منها جزء محدود تُعرض كمقتطف موسوم بوضوح («مُحدَّث (مقتطف)») وفيه الدوال المتغيرة كاملة؛ وما عداها كامل.

> الملفات غير المذكورة هنا لم تتغيّر عن المراحل 1–8، باستثناء استبدال `ConversationHandler(...)` بـ`conversation(...)` في 10 ملفات معالجات أدمن (`broadcast, catalog, orders, payment_methods, payments, providers, settings, templates, tickets, users`) وفي `handlers/registry.py` (4 محادثات مستخدم) — أي 29 محادثة كلها، والتغيير ميكانيكي (اسم المصنع فقط).

## الفهرس


**قاعدة البيانات والإعدادات والتهيئة**

- `database/migrations/0008_phase9_security.sql` — 61 سطراً (جديد)
- `core/permissions.py` — 237 سطراً (مُحدَّث)
- `core/setting_rules.py` — 264 سطراً (جديد)
- `core/constants.py` — 44 سطراً (مُحدَّث)
- `config.py` — 210 سطراً (مُحدَّث)
- `main.py` — 185 سطراً (مُحدَّث)
- `.env.example` — 37 سطراً (مُحدَّث)

**طبقة الأمان المشتركة (utils / middlewares)**

- `utils/net_security.py` — 188 سطراً (جديد)
- `utils/fs_security.py` — 123 سطراً (جديد)
- `utils/throttle.py` — 83 سطراً (جديد)
- `utils/security.py` — 153 سطراً (مُحدَّث)
- `middlewares/rate_limit.py` — 206 سطراً (مُحدَّث)
- `middlewares/context.py` — 262 سطراً (مُحدَّث)
- `handlers/common/conversation.py` — 82 سطراً (جديد)
- `handlers/common/errors.py` — 194 سطراً (مُحدَّث)

**الخدمات**

- `services/security_service.py` — 383 سطراً (جديد)
- `services/auth_service.py` — 368 سطراً (مُحدَّث)
- `services/user_service.py` — 289 سطراً (مُحدَّث)
- `services/settings_service.py` — 195 سطراً (مُحدَّث)
- `services/__init__.py` — 181 سطراً (مُحدَّث)
- `services/wallet_service.py` — 443 سطراً (مُحدَّث (مقتطف))
- `services/payment_service.py` — 1043 سطراً (مُحدَّث (مقتطف))
- `services/order_service.py` — 1447 سطراً (مُحدَّث (مقتطف))
- `services/provider_service.py` — 526 سطراً (مُحدَّث (مقتطف))
- `integrations/providers/perfect_panel.py` — 453 سطراً (مُحدَّث (مقتطف))

**المهام الدورية والواجهة**

- `jobs/runner.py` — 298 سطراً (مُحدَّث)
- `handlers/admin/security.py` — 257 سطراً (جديد)
- `handlers/admin/providers.py` — 977 سطراً (مُحدَّث (مقتطف))
- `keyboards/admin_kb.py` — 1432 سطراً (مُحدَّث (مقتطف))

**السكربتات**

- `scripts/security_check.py` — 102 سطراً (جديد)
- `scripts/create_admin.py` — 110 سطراً (مُحدَّث)
- `scripts/init_db.py` — 186 سطراً (مُحدَّث)

**الاختبارات**

- `tests/unit/test_net_security_phase9.py` — 131 سطراً (جديد)
- `tests/unit/test_sanitize_phase9.py` — 97 سطراً (جديد)
- `tests/unit/test_setting_rules_phase9.py` — 86 سطراً (جديد)
- `tests/unit/test_rate_limit_phase9.py` — 121 سطراً (جديد)
- `tests/unit/test_hardening_phase9.py` — 163 سطراً (جديد)
- `tests/integration/test_rbac_phase9.py` — 210 سطراً (جديد)
- `tests/integration/test_money_guards_phase9.py` — 192 سطراً (جديد)
- `tests/integration/test_security_phase9.py` — 443 سطراً (جديد)
- `tests/integration/test_ssrf_scripts_phase9.py` — 155 سطراً (جديد)
- `tests/integration/test_conversation_settings_phase9.py` — 140 سطراً (جديد)
- `tests/integration/test_no_dead_buttons.py` — 611 سطراً (مُحدَّث (مقتطف))

---


## قاعدة البيانات والإعدادات والتهيئة

### `database/migrations/0008_phase9_security.sql`  ·  جديد  ·  61 سطراً

صلاحيتا الأمان + 8 إعدادات حماية (حدود الاستخدام، السقوف، منع الإجراء الذاتي، تنبيه الأخطاء).

```sql
-- =====================================================================
-- الترحيل 0008 — المرحلة 9 (الأمان والموثوقية)
--
-- لماذا هذا الترحيل؟
--   1) شاشة «🛡️ الأمان» تحتاج صلاحية مستقلة للعرض (security.view) وأخرى
--      للإجراءات (security.manage: رفع الإيقاف المؤقت عن مستخدم). الثانية
--      حصرية للأدمن الأعلى لأنها تتجاوز حماية الاستخدام.
--   2) حدود الاستخدام صارت متدرجة (أدمن/إجراء حسّاس/إيقاف مؤقت عند التكرار)
--      وكلها قيم قابلة للضبط من داخل البوت لا من الكود.
--   3) سقوف التسويات اليدوية للرصيد (للعملية الواحدة ولليوم) بحيث لا يستطيع
--      حساب إداري مخترق أو مخطئ إضافة رصيد بلا حد. الأدمن الأعلى مستثنى منها
--      لكن عملياته مُدقَّقة دائماً.
--   4) منع «الإجراء الذاتي»: لا يعتمد الأدمن شحنته ولا يعدّل رصيده بنفسه
--      (مبدأ «عينان على كل عملية مالية»).
--   5) تنبيه الأدمن عند تكرار الأخطاء غير المتوقعة، بتهدئة حتى لا يغرق.
--
-- ملاحظات تقنية:
--   • إضافة صفوف بذور فقط — لا تعديل على بنية أي جدول ولا حذف بيانات.
--   • القيم المالية بوحدات صحيحة (MONEY_SCALE = 10000):
--       500,000.00 ⇒ 5000000000   ·   2,000,000.00 ⇒ 20000000000
-- =====================================================================

-- ----------------------------- صلاحيات جديدة --------------------------- --
INSERT OR IGNORE INTO permissions (code, name_ar, group_code, is_dangerous) VALUES
    ('security.view',   'عرض شاشة الأمان',                    'security', 0),
    ('security.manage', 'إدارة الحماية (رفع الإيقاف المؤقت)', 'security', 1);

-- العرض للأدمن والأدمن الأعلى؛ الإدارة للأدمن الأعلى فقط.
INSERT OR IGNORE INTO role_permissions (role_code, permission_code) VALUES
    ('super_admin', 'security.view'),
    ('super_admin', 'security.manage'),
    ('admin',       'security.view');

-- ----------------------------- إعدادات جديدة --------------------------- --
INSERT OR IGNORE INTO settings (key, value, value_type, group_code, name_ar, description_ar, is_editable, updated_at) VALUES
    ('rate_limit_admin_actions_per_minute', '120', 'int', 'security', 'حد إجراءات الأدمن بالدقيقة',
     'الأدمن يتنقل بين صفحات كثيرة فيحتاج حداً أعلى من العميل. القيمة بين 10 و1000', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('rate_limit_sensitive_per_minute', '8', 'int', 'security', 'حد الإجراءات الحسّاسة بالدقيقة',
     'التأكيدات المالية وإنشاء الطلبات والشحن والتذاكر لها حد أضيق من التصفح. القيمة بين 1 و100', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('rate_limit_strikes_before_block', '5', 'int', 'security', 'عدد المخالفات قبل الإيقاف المؤقت',
     'تكرار تجاوز الحد هذا العدد من المرات خلال 10 دقائق يوقف المستخدم مؤقتاً. القيمة بين 1 و50', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('rate_limit_block_minutes', '5', 'int', 'security', 'مدة الإيقاف المؤقت (دقائق)',
     'يُتجاهل المستخدم الموقوف بصمت (بلا ردود تضخّم الضغط). القيمة بين 1 و1440', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('security_block_self_actions', 'true', 'bool', 'security', 'منع الإجراء الذاتي على العمليات المالية',
     'يمنع الأدمن من اعتماد/رفض شحنته أو تعديل رصيده أو استرجاع طلباته بنفسه. أوقفه فقط عند اختبار النظام بحسابك', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('admin_adjust_max_units', '5000000000', 'money', 'security', 'سقف التسوية اليدوية للعملية الواحدة',
     'أقصى مبلغ يضيفه أو يخصمه أدمن (غير الأعلى) في عملية واحدة. صفر = بلا سقف', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('admin_adjust_daily_max_units', '20000000000', 'money', 'security', 'سقف التسويات اليدوية اليومي لكل أدمن',
     'مجموع ما يضيفه ويخصمه الأدمن (غير الأعلى) خلال اليوم. صفر = بلا سقف', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('error_alert_enabled', 'true', 'bool', 'security', 'تنبيه الأدمن عند الأخطاء غير المتوقعة',
     'يصل تنبيه لمن يملك صلاحية السجلات عند أول خطأ من كل نوع ثم يهدأ لفترة التهدئة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('error_alert_cooldown_minutes', '15', 'int', 'security', 'تهدئة تنبيه الأخطاء (دقائق)',
     'لا يتكرر تنبيه الخطأ نفسه قبل مرور هذه المدة. القيمة بين 1 و1440', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
```

### `core/permissions.py`  ·  مُحدَّث  ·  237 سطراً

كتالوج الصلاحيات (46) مع `security.*` وقائمة 24 صلاحية خطِرة + قواعد الهرمية.

```python
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
```

### `core/setting_rules.py`  ·  جديد  ·  264 سطراً

قواعد التحقق المركزية لـ50 إعداداً (نوع/نطاق/علاقات بين الإعدادات).

```python
"""
قواعد التحقق من قيم الإعدادات (المرحلة 9).

المشكلة التي يحلّها هذا الملف:
    جدول `settings` يخزّن نصاً خاماً. قبل هذه المرحلة كان الفحص النوعي يقع في
    معالج واجهة واحد فقط، فأي مسار آخر (خدمة، سكربت، اختبار) يستطيع حفظ قيمة
    تُسقط النظام لاحقاً في مكان بعيد، أو تفتح ثغرة:
        • `rate_limit_actions_per_minute = 0` ⇒ إلغاء حد الاستخدام كلياً.
        • `broadcast_batch_size = 100000` ⇒ تجاوز حدود تيليجرام وحظر البوت.
        • `max_deposit_units < min_deposit_units` ⇒ لا يستطيع أحد الشحن.
        • `provider_exchange_rate = "abc"` ⇒ انفجار عند أول حساب تكلفة.
    الآن تمر كل قيمة من هنا داخل `SettingsService.set` نفسها (مصدر الحقيقة الوحيد).

المبدأ: القاعدة تُرفض برسالة عربية تذكر النطاق المسموح، ولا يُعدَّل شيء بصمت.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final

from core.exceptions import ValidationError
from utils.validators import normalize_digits

#: القيم المقبولة للإعدادات المنطقية (تُطبَّع إلى true/false قبل الحفظ)
TRUE_WORDS: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on", "نعم", "تفعيل", "مفعل"})
FALSE_WORDS: Final[frozenset[str]] = frozenset({"0", "false", "no", "off", "لا", "تعطيل", "معطل"})

#: حدود عامة للمفاتيح غير المذكورة صراحةً (حماية من أرقام خرافية تكسر الحسابات)
GENERIC_INT_MIN: Final[int] = -1_000_000_000_000
GENERIC_INT_MAX: Final[int] = 1_000_000_000_000
GENERIC_MONEY_MAX: Final[int] = 10**15
GENERIC_TEXT_MAX: Final[int] = 1000


@dataclass(frozen=True, slots=True)
class SettingRule:
    """
    قاعدة مفتاح واحد.

    الحقول:
        minimum / maximum : حدّا الأرقام (شاملان) للأنواع int/money.
        max_length        : أقصى طول للنصوص.
        pattern           : تعبير نمطي يجب أن يطابقه النص كاملاً (عند عدم الفراغ).
        allow_empty       : هل تُقبل القيمة الفارغة (تعني «غير مضبوط»)؟
        decimal           : النص يمثّل رقماً عشرياً موجباً (مثل سعر الصرف).
    """

    minimum: int | None = None
    maximum: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    allow_empty: bool = False
    decimal: bool = False
    hint: str = ""


def _int(minimum: int, maximum: int) -> SettingRule:
    """اختصار لقاعدة رقم صحيح ضمن نطاق."""
    return SettingRule(minimum=minimum, maximum=maximum)


#: القواعد الخاصة بكل مفتاح (المفاتيح الأخرى تأخذ الحدود العامة حسب نوعها)
SETTING_RULES: Final[dict[str, SettingRule]] = {
    # عامة
    "display_decimals": _int(0, 6),
    "bot_name": SettingRule(max_length=60),
    "currency_code": SettingRule(pattern=r"[A-Za-z]{2,6}", hint="رمز من 2 إلى 6 حروف إنجليزية مثل YER"),
    "currency_symbol": SettingRule(max_length=10),
    "welcome_message": SettingRule(max_length=1500),
    "rules_text": SettingRule(max_length=3000),
    "maintenance_message": SettingRule(max_length=500),
    "support_username": SettingRule(
        pattern=r"@?[A-Za-z][A-Za-z0-9_]{4,31}", allow_empty=True,
        hint="معرّف تيليجرام من 5 إلى 32 محرفاً (حروف وأرقام وشرطة سفلية)",
    ),
    # الطلبات
    "min_order_amount_units": SettingRule(minimum=0, maximum=GENERIC_MONEY_MAX),
    "duplicate_order_window_minutes": _int(0, 1440),
    "order_submit_interval_seconds": _int(5, 3600),
    "order_check_interval_seconds": _int(5, 86_400),
    "order_stuck_alert_hours": _int(1, 720),
    "max_orders_per_day": _int(0, 100_000),
    "order_submit_batch_size": _int(1, 50),
    "order_check_batch_size": _int(1, 200),
    # الشحن
    "min_deposit_units": SettingRule(minimum=1, maximum=GENERIC_MONEY_MAX),
    "max_deposit_units": SettingRule(minimum=1, maximum=GENERIC_MONEY_MAX),
    "payment_expiry_hours": _int(1, 720),
    "max_pending_payments_per_user": _int(1, 50),
    "payment_search_limit": _int(1, 50),
    # الإشعارات والإذاعة
    "notification_dispatch_seconds": _int(5, 3600),
    "admin_alert_chat_id": SettingRule(
        pattern=r"-?\d{5,20}", allow_empty=True, hint="معرّف محادثة رقمي (قد يبدأ بـ -100 للقنوات)"
    ),
    "broadcast_rate_per_second": _int(1, 30),
    "broadcast_batch_size": _int(1, 100),
    "broadcast_interval_seconds": _int(5, 3600),
    "broadcast_active_days": _int(1, 3650),
    # المزودون
    "provider_low_balance_alert_units": SettingRule(minimum=0, maximum=GENERIC_MONEY_MAX),
    "provider_exchange_rate": SettingRule(decimal=True, max_length=24),
    "provider_failure_threshold": _int(1, 100),
    "provider_disable_minutes": _int(1, 10_080),
    "provider_insufficient_wait_hours": _int(1, 168),
    "provider_balance_check_minutes": _int(1, 1440),
    "provider_health_watch_minutes": _int(1, 1440),
    # النسخ الاحتياطي
    "backup_interval_hours": _int(1, 720),
    "backup_retention_days": _int(1, 3650),
    # الحدود والدعم
    "max_tickets_per_day": _int(1, 1000),
    "ticket_auto_close_days": _int(1, 365),
    "ticket_reopen_hours": _int(0, 8760),
    # المهام
    "job_failure_alert_threshold": _int(1, 100),
    "admin_digest_hour": _int(0, 23),
    "db_maintenance_hour": _int(0, 23),
    # الأمان (المرحلة 9) — الحد الأدنى للحدود يمنع إلغاء الحماية بوضع صفر
    "rate_limit_actions_per_minute": _int(3, 600),
    "rate_limit_admin_actions_per_minute": _int(10, 1000),
    "rate_limit_sensitive_per_minute": _int(1, 100),
    "rate_limit_strikes_before_block": _int(1, 50),
    "rate_limit_block_minutes": _int(1, 1440),
    "admin_adjust_max_units": SettingRule(minimum=0, maximum=GENERIC_MONEY_MAX),
    "admin_adjust_daily_max_units": SettingRule(minimum=0, maximum=GENERIC_MONEY_MAX),
    "error_alert_cooldown_minutes": _int(1, 1440),
}

#: مفاتيح مرتبطة ببعضها: (الأدنى، الأعلى) — يجب أن يبقى الأول ≤ الثاني
ORDERED_PAIRS: Final[tuple[tuple[str, str], ...]] = (("min_deposit_units", "max_deposit_units"),)


def _bad(message: str, user_message: str) -> ValidationError:
    """بناء خطأ تحقق (رسالة تقنية + رسالة عربية للمستخدم)."""
    return ValidationError(message, user_message=user_message)


def _normalize_bool(text: str) -> str:
    """تطبيع قيمة منطقية إلى true/false أو رفضها."""
    lowered = text.lower()
    if lowered in TRUE_WORDS:
        return "true"
    if lowered in FALSE_WORDS:
        return "false"
    raise _bad(f"قيمة منطقية غير صالحة: {text!r}", "❌ أرسل true أو false (أو 1 / 0).")


def _normalize_number(text: str, key: str, value_type: str) -> str:
    """تطبيع رقم صحيح (يقبل الأرقام الهندية والفواصل) ثم فرض حدوده."""
    cleaned = normalize_digits(text).replace(",", "").replace("٬", "").strip()
    if not re.fullmatch(r"-?\d{1,18}", cleaned):
        raise _bad(f"قيمة رقمية غير صالحة: {text!r}", "❌ أرسل رقماً صحيحاً.")
    number = int(cleaned)

    rule = SETTING_RULES.get(key)
    if rule is not None and (rule.minimum is not None or rule.maximum is not None):
        low, high = rule.minimum, rule.maximum
    elif value_type == "money":
        low, high = 0, GENERIC_MONEY_MAX
    else:
        low, high = GENERIC_INT_MIN, GENERIC_INT_MAX
    if low is not None and number < low or high is not None and number > high:
        raise _bad(
            f"القيمة {number} خارج النطاق المسموح للمفتاح {key} ({low}..{high})",
            f"❌ القيمة يجب أن تكون بين {low:,} و{high:,}.",
        )
    return str(number)


def _normalize_text(text: str, key: str) -> str:
    """فحص نص: الطول، الفراغ، النمط، أو العدد العشري."""
    rule = SETTING_RULES.get(key, SettingRule())
    limit = rule.max_length or GENERIC_TEXT_MAX
    if not text:
        if rule.allow_empty:
            return ""
        raise _bad(f"قيمة فارغة للمفتاح {key}", "❌ القيمة لا يمكن أن تكون فارغة.")
    if len(text) > limit:
        raise _bad(f"نص طويل للمفتاح {key}: {len(text)} > {limit}", f"❌ النص طويل (الحد {limit} حرفاً).")

    if rule.decimal:
        try:
            value = Decimal(normalize_digits(text).replace(",", "."))
        except InvalidOperation as exc:
            raise _bad(f"عدد عشري غير صالح: {text!r}", "❌ أرسل رقماً (مثل 1 أو 530.5).") from exc
        if not value.is_finite() or value <= 0 or value > Decimal("1000000000"):
            raise _bad(f"عدد خارج النطاق: {text!r}", "❌ يجب أن يكون الرقم أكبر من صفر وأقل من مليار.")
        if value.as_tuple().exponent < -8:                            # type: ignore[operator]
            raise _bad(f"خانات عشرية كثيرة: {text!r}", "❌ الحد الأقصى 8 خانات عشرية.")
        return format(value.normalize(), "f")

    if rule.pattern and not re.fullmatch(rule.pattern, text):
        hint = f" ({rule.hint})" if rule.hint else ""
        raise _bad(f"قيمة لا تطابق النمط للمفتاح {key}: {text!r}", f"❌ صيغة غير صالحة{hint}.")
    return text


def normalize_setting_value(key: str, raw: object, value_type: str) -> str:
    """
    التحقق من موافقة قيمة لنوع مفتاحها ولقاعدته ثم تطبيعها لنصٍّ يُخزَّن.

    المدخلات:
        key        : اسم المفتاح (لجلب قاعدته الخاصة إن وُجدت).
        raw        : القيمة كما وصلت (نص من الواجهة أو رقم/منطقي من الكود).
        value_type : نوع المفتاح في قاعدة البيانات (str/int/bool/json/money).

    المخرجات: النص الجاهز للتخزين (bool ← true/false، أرقام ← صيغة قياسية).

    الاستثناءات:
        ValidationError : القيمة لا تناسب النوع أو خارج النطاق المسموح.
    """
    if isinstance(raw, bool):                       # قبل int: bool فرع من int في بايثون
        text = "true" if raw else "false"
    elif isinstance(raw, (dict, list)):
        text = json.dumps(raw, ensure_ascii=False)
    else:
        text = str(raw).strip()

    if value_type == "bool":
        return _normalize_bool(text)
    if value_type in {"int", "money"}:
        return _normalize_number(text, key, value_type)
    if value_type == "json":
        try:
            json.loads(text)
        except ValueError as exc:
            raise _bad(f"JSON غير صالح: {exc}", "❌ النص ليس JSON صالحاً.") from exc
        if len(text) > 5000:
            raise _bad("JSON طويل جداً", "❌ النص طويل جداً (الحد 5000 حرف).")
        return text
    return _normalize_text(text, key)


def check_ordered_pairs(key: str, value: str, current: dict[str, str]) -> None:
    """
    التأكد أن تعديل مفتاح لا يكسر ترتيبه مع مفتاحه المرتبط (الأدنى ≤ الأعلى).

    المدخلات:
        key     : المفتاح المراد تعديله.
        value   : قيمته الجديدة بعد التطبيع.
        current : القيم الحالية لكل الإعدادات (نصية).

    الاستثناءات:
        ValidationError : التعديل يجعل الحد الأدنى أكبر من الأعلى.
    """
    for low_key, high_key in ORDERED_PAIRS:
        if key not in (low_key, high_key):
            continue
        other_key = high_key if key == low_key else low_key
        other_raw = current.get(other_key, "")
        if not str(other_raw).strip().lstrip("-").isdigit():
            continue                                              # المقابل غير مضبوط: لا مقارنة
        low = int(value) if key == low_key else int(other_raw)
        high = int(other_raw) if key == low_key else int(value)
        if low > high:
            raise _bad(
                f"{low_key}={low} أكبر من {high_key}={high}",
                "❌ الحد الأدنى للشحن لا يمكن أن يتجاوز الحد الأقصى.",
            )
```

### `core/constants.py`  ·  مُحدَّث  ·  44 سطراً

`APP_VERSION = 0.10.0-phase9`.

```python
"""ثوابت عامة للنظام (قيم لا تتغير أثناء التشغيل)."""

from __future__ import annotations

#: اسم المشروع وإصداره
APP_NAME: str = "SMM Telegram Bot"
APP_VERSION: str = "0.10.0-phase9"

#: مدة قفل الطلب أثناء معالجته بواسطة job (بالثواني)
ORDER_LOCK_SECONDS: int = 120

#: أقصى عدد محاولات لإرسال الطلب إلى المزود عند الفشل الآمن (قبل اعتباره فاشلاً)
MAX_SUBMIT_ATTEMPTS: int = 3

#: أقصى عدد محاولات إرسال إشعار قبل اعتباره فاشلاً
MAX_NOTIFICATION_ATTEMPTS: int = 5

#: تدرج فترات إعادة فحص حالة الطلب (بالثواني)
ORDER_CHECK_BACKOFF: tuple[int, ...] = (60, 300, 900, 1800, 3600)

#: تدرج فترات إعادة إرسال الإشعار الفاشل (بالثواني)
NOTIFICATION_BACKOFF: tuple[int, ...] = (10, 60, 300, 1800, 3600)

#: مدة صلاحية مفاتيح منع التكرار الافتراضية (بالثواني)
IDEMPOTENCY_TTL_SECONDS: int = 24 * 3600

#: طول أقصى للنصوص المُخزَّنة من استجابات المزود (منعاً لتضخم قاعدة البيانات)
PROVIDER_RESPONSE_SNIPPET_LEN: int = 500

#: عدد العناصر في صفحة القوائم داخل تيليجرام
PAGE_SIZE: int = 8

#: صيغة مراجع الحركات المالية (تُستخدم لمنع التكرار)
REF_ORDER_DEBIT: str = "order:{order_id}"
REF_ORDER_REFUND: str = "refund:order:{order_id}"
REF_ORDER_PARTIAL_REFUND: str = "partial_refund:order:{order_id}"
REF_PAYMENT_DEPOSIT: str = "payment:{payment_id}"
REF_MANUAL: str = "manual:{kind}:{admin_id}:{token}"

#: صيغة مفاتيح منع تكرار الإشعارات
NOTIF_KEY_ORDER: str = "order:{order_id}:{event}"
NOTIF_KEY_PAYMENT: str = "payment:{payment_id}:{event}"
NOTIF_KEY_TICKET: str = "ticket:{ticket_id}:{event}"
NOTIF_KEY_MANUAL: str = "manual:{token}"
```

### `config.py`  ·  مُحدَّث  ·  210 سطراً

التحقق من صيغة التوكن/Fernet/SUPER_ADMIN_IDS + تسجيل الأسرار + `sensitive_paths`.

```python
"""
إعدادات التشغيل — تُقرأ من ملف .env ولا تُكتب أبداً داخل الكود.

هذا الملف مسؤول عن:
    • تحميل متغيرات البيئة من ملف .env.
    • التحقق من وجود القيم الإلزامية وإعطاء رسالة خطأ واضحة عند نقصها.
    • تجهيز المسارات (قاعدة البيانات، اللوقات، النسخ الاحتياطية) وإنشاء مجلداتها.

ملاحظة أمنية: لا تُطبع أي قيمة سرية (التوكن/مفتاح التشفير) في اللوقات أو عند الطباعة.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv

from utils.fs_security import sensitive_paths as _sensitive_paths
from utils.security import register_secret

# المجلد الجذر للمشروع (حيث يوجد هذا الملف)
BASE_DIR: Path = Path(__file__).resolve().parent


class ConfigError(Exception):
    """خطأ في ملف الإعدادات أو في متغيرات البيئة."""


def _get_str(key: str, default: str | None = None) -> str | None:
    """قراءة متغير نصي من البيئة مع تجاهل الفراغات والقيم الفارغة."""
    value = os.getenv(key, default)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _get_int(key: str) -> int | None:
    """قراءة متغير رقمي اختياري من البيئة، وإرجاع None إن لم يكن موجوداً أو صالحاً."""
    raw = _get_str(key)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"القيمة في المتغير {key} يجب أن تكون رقماً صحيحاً.") from exc


def _get_ids(key: str) -> tuple[int, ...]:
    """قراءة قائمة معرفات تيليجرام مفصولة بفواصل (مثال: 111,222)."""
    raw = _get_str(key)
    if not raw:
        return ()
    ids: list[int] = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError as exc:
            raise ConfigError(
                f"المتغير {key} يجب أن يحتوي معرفات رقمية مفصولة بفواصل، والقيمة «{part}» غير صالحة."
            ) from exc
    return tuple(ids)


#: صيغة توكن بوت تيليجرام: معرّف رقمي ثم نقطتان ثم نص طويل
_BOT_TOKEN_RE = re.compile(r"\d{6,12}:[A-Za-z0-9_\-]{30,}")


def _validate_secrets(bot_token: str | None, encryption_key: str | None) -> None:
    """
    فحص صيغة الأسرار عند التحميل لاكتشاف الخطأ قبل أول استخدام.

    الاستثناءات:
        ConfigError : توكن بصيغة خاطئة، أو مفتاح تشفير ليس مفتاح Fernet صالحاً.
                      (الرسالة لا تحتوي القيمة نفسها أبداً.)
    """
    if bot_token and not _BOT_TOKEN_RE.fullmatch(bot_token):
        raise ConfigError(
            "قيمة BOT_TOKEN بصيغة غير صحيحة — انسخها كاملة من @BotFather "
            "(مثال الشكل: 123456789:AA... بلا مسافات أو علامات اقتباس)."
        )
    if encryption_key:
        try:
            Fernet(encryption_key.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise ConfigError(
                "قيمة ENCRYPTION_KEY ليست مفتاح Fernet صالحاً — ولّد واحداً بالأمر: "
                "python -m scripts.init_db --gen-key"
            ) from exc


def _validate_admin_ids(ids: tuple[int, ...]) -> None:
    """معرفات تيليجرام للأشخاص أعداد موجبة؛ السالب/الصفر خطأ إدخال (المجموعات والقنوات سالبة)."""
    bad = [value for value in ids if value <= 0]
    if bad:
        raise ConfigError("SUPER_ADMIN_IDS يجب أن تكون معرفات مستخدمين موجبة (ليس معرف مجموعة أو قناة).")


def _resolve(path_value: str, default_relative: str) -> Path:
    """تحويل مسار نصي إلى مسار مطلق نسبةً لجذر المشروع."""
    raw = path_value or default_relative
    path = Path(raw)
    return path if path.is_absolute() else (BASE_DIR / path)


@dataclass(frozen=True)
class Config:
    """حاوية إعدادات التشغيل (غير قابلة للتعديل بعد التحميل)."""

    bot_token: str | None
    super_admin_ids: tuple[int, ...]
    encryption_key: str | None
    database_path: Path
    log_level: str
    log_file: Path
    backup_dir: Path
    data_dir: Path
    timezone: str
    admin_alert_chat_id: int | None
    backup_channel_id: int | None

    # ------------------------------------------------------------------ #

    @classmethod
    def load(cls, *, require_bot_token: bool = False, env_file: str | Path | None = None) -> "Config":
        """
        تحميل الإعدادات من ملف .env ومن متغيرات البيئة.

        المدخلات:
            require_bot_token : اجعلها True عند تشغيل البوت نفسه (main.py)،
                                واتركها False لأدوات قاعدة البيانات والاختبارات.
            env_file          : مسار ملف بيئة بديل (يُستخدم في الاختبارات).

        المخرجات: كائن Config جاهز.

        الاستثناءات:
            ConfigError : عند نقص قيمة إلزامية أو وجود قيمة غير صالحة.
        """
        load_dotenv(env_file or (BASE_DIR / ".env"), override=False)

        bot_token = _get_str("BOT_TOKEN")
        if require_bot_token and not bot_token:
            raise ConfigError(
                "المتغير BOT_TOKEN غير موجود. انسخ ملف .env.example إلى .env ثم ضع توكن البوت."
            )

        database_path = _resolve(_get_str("DATABASE_PATH") or "", "data/smm_bot.db")
        log_file = _resolve(_get_str("LOG_FILE") or "", "logs/bot.log")
        backup_dir = _resolve(_get_str("BACKUP_DIR") or "", "backups")

        log_level = (_get_str("LOG_LEVEL") or "INFO").upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigError("قيمة LOG_LEVEL يجب أن تكون إحدى: DEBUG/INFO/WARNING/ERROR/CRITICAL")

        encryption_key = _get_str("ENCRYPTION_KEY")
        super_admin_ids = _get_ids("SUPER_ADMIN_IDS")
        _validate_secrets(bot_token, encryption_key)
        _validate_admin_ids(super_admin_ids)
        # تسجيل الأسرار ليُحذف أي ظهور حرفي لها من اللوقات وحقول الأخطاء المخزَّنة
        register_secret(bot_token)
        register_secret(encryption_key)

        return cls(
            bot_token=bot_token,
            super_admin_ids=super_admin_ids,
            encryption_key=encryption_key,
            database_path=database_path,
            log_level=log_level,
            log_file=log_file,
            backup_dir=backup_dir,
            data_dir=database_path.parent,
            timezone=_get_str("TIMEZONE") or "Asia/Aden",
            admin_alert_chat_id=_get_int("ADMIN_ALERT_CHAT_ID"),
            backup_channel_id=_get_int("BACKUP_CHANNEL_ID"),
        )

    def ensure_directories(self) -> None:
        """إنشاء المجلدات المطلوبة (البيانات/اللوقات/النسخ الاحتياطية) إن لم تكن موجودة."""
        for directory in (self.data_dir, self.log_file.parent, self.backup_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def sensitive_paths(self, env_file: Path | None = None) -> list[tuple[Path, str, int]]:
        """المسارات الحسّاسة (بيئة/قاعدة/نسخ/لوق) مع الصلاحية المطلوبة لكل منها."""
        return _sensitive_paths(
            env_file=env_file or (BASE_DIR / ".env"),
            database_path=self.database_path,
            data_dir=self.data_dir,
            backup_dir=self.backup_dir,
            log_dir=self.log_file.parent,
        )

    def safe_summary(self) -> dict[str, str]:
        """ملخص آمن للطباعة — بدون أي قيمة سرية."""
        return {
            "database_path": str(self.database_path),
            "log_file": str(self.log_file),
            "backup_dir": str(self.backup_dir),
            "timezone": self.timezone,
            "log_level": self.log_level,
            "bot_token": "✓ موجود" if self.bot_token else "✗ غير موجود",
            "encryption_key": "✓ موجود" if self.encryption_key else "✗ غير موجود",
            "super_admins": str(len(self.super_admin_ids)),
        }
```

### `main.py`  ·  مُحدَّث  ·  185 سطراً

umask 077 + `harden_filesystem` + ربط المراقبين وإعادة الجدولة الحيّة.

```python
"""
نقطة تشغيل البوت.

التسلسل الكامل عند الإقلاع:
    1. تحميل الإعدادات من ‎.env‎ والتحقق من وجود التوكن.
    2. تهيئة اللوق (ملف متدحرج + شاشة).
    3. حجز قفل «نسخة واحدة» حتى لا يعمل بوتان على نفس القاعدة.
    4. فتح قاعدة البيانات وتطبيق أي ترحيلات ناقصة.
    5. بناء حاوية الخدمات (المنطق كله) وحقنها في `bot_data`.
    6. تسجيل المعالجات (`handlers/registry.py`) والمعالج العام للأخطاء.
    7. استرداد ما علق من تشغيل سابق، ثم جدولة المهام الدورية.
    8. بدء الاستقبال (polling) حتى إشارة إيقاف، ثم إغلاق نظيف.

التشغيل:
    python -m main            # من داخل مجلد المشروع
    python main.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:                       # تشغيل مباشر بلا تثبيت الحزمة
    sys.path.insert(0, str(ROOT))

from telegram import BotCommand                                     # noqa: E402
from telegram.ext import Application, ApplicationBuilder, Defaults  # noqa: E402
from telegram.constants import ParseMode                            # noqa: E402

from config import Config, ConfigError                              # noqa: E402
from core.constants import APP_VERSION                              # noqa: E402
from database.database import Database                              # noqa: E402
from database.migrator import Migrator                              # noqa: E402
from database.repositories import Repositories                      # noqa: E402
from handlers.registry import register_handlers                     # noqa: E402
from jobs import run_startup_recovery, schedule_jobs                # noqa: E402
from services import build_services                                 # noqa: E402
from utils.fs_security import check_paths                            # noqa: E402
from utils.logging_setup import get_logger, setup_logging           # noqa: E402
from utils.security import SecretBox                                # noqa: E402
from utils.single_instance import AlreadyRunningError, SingleInstance  # noqa: E402

logger = get_logger(__name__)

#: أوامر البوت التي تظهر في قائمة تيليجرام
BOT_COMMANDS = [
    BotCommand("start", "القائمة الرئيسية"),
    BotCommand("help", "شرح استخدام البوت"),
    BotCommand("cancel", "إلغاء العملية الحالية"),
    BotCommand("id", "عرض معرفي في تيليجرام"),
]


def harden_filesystem(config: Config) -> int:
    """
    ضبط صلاحيات الملفات الحسّاسة (.env، القاعدة، النسخ، اللوقات) وإرجاع عدد المخالفات المتبقية.

    تُستدعى مرتين: عند الإقلاع (للملفات الموجودة)، وبعد فتح القاعدة (لملفات WAL/SHM
    التي تُنشأ عند أول اتصال). ما تعذّر ضبطه يُسجَّل كتحذير ولا يوقف البوت.
    """
    results = check_paths(config.sensitive_paths(), fix=True)
    remaining = [item for item in results if item.insecure]
    for item in remaining:
        logger.warning(
            "⚠️ %s ما زال مفتوحاً لغير المالك (صلاحية %s) %s", item.label, item.mode_text, item.note
        )
    return len(remaining)


async def _open_database(config: Config) -> Database:
    """فتح قاعدة البيانات وتطبيق الترحيلات الناقصة قبل بدء الخدمة."""
    db = Database(config.database_path)
    await db.connect()
    migrator = Migrator(db)
    pending = await migrator.pending()
    if pending:
        logger.info("تطبيق %s ترحيل ناقص: %s", len(pending), ", ".join(pending))
        applied = await migrator.apply_all()
        logger.info("تم تطبيق الترحيلات: %s", ", ".join(applied))
    logger.info("إصدار مخطط قاعدة البيانات: %s", await migrator.current_version())
    return db


def build_application(config: Config) -> Application:
    """
    بناء تطبيق تيليجرام وربط كل مكوناته.

    المخرجات: تطبيق جاهز للتشغيل عبر `run_polling`.
    """
    # block=True (الافتراضي): معالجة متسلسلة للتحديث الواحد — لا سباق على الرصيد
    defaults = Defaults(parse_mode=ParseMode.HTML, disable_web_page_preview=True)

    async def post_init(application: Application) -> None:
        """ما يُنفَّذ بعد تهيئة التطبيق وقبل استقبال أول تحديث."""
        db = await _open_database(config)
        harden_filesystem(config)               # ملفات WAL/SHM وُلدت الآن
        repos = Repositories(db)
        services = build_services(
            db,
            repos,
            secret_box=SecretBox(config.encryption_key),
            super_admin_ids=config.super_admin_ids,
        )
        application.bot_data["services"] = services
        application.bot_data["config"] = config

        await run_startup_recovery(services)
        await schedule_jobs(application, services)
        await application.bot.set_my_commands(BOT_COMMANDS)

        me = await application.bot.get_me()
        logger.info("البوت جاهز: @%s (الإصدار %s)", me.username, APP_VERSION)
        if await services.settings.is_maintenance():
            logger.warning("النظام في وضع الصيانة — المستخدمون سيرون رسالة الصيانة")

    async def post_shutdown(application: Application) -> None:
        """إغلاق الموارد بنظافة بعد توقف التطبيق."""
        services = application.bot_data.get("services")
        if services is not None:
            await services.db.close()
            logger.info("تم إغلاق قاعدة البيانات")

    application = (
        ApplicationBuilder()
        .token(config.bot_token)
        .defaults(defaults)
        .concurrent_updates(False)       # معالجة متسلسلة: أأمن مع SQLite والعمليات المالية
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    count = register_handlers(application)
    logger.info("تم تسجيل %s معالجاً", count)
    return application


def main() -> int:
    """
    تشغيل البوت حتى إشارة الإيقاف.

    المخرجات: رمز خروج للنظام (0 نجاح، 1 خطأ إعداد، 2 نسخة تعمل بالفعل).
    """
    try:
        config = Config.load(require_bot_token=True)
    except ConfigError as exc:
        print(f"❌ خطأ في الإعدادات: {exc}", file=sys.stderr)
        return 1

    if os.name == "posix":
        os.umask(0o077)                         # كل ملف/مجلد جديد خاص بالمالك من لحظة إنشائه
    config.ensure_directories()
    setup_logging(config.log_file, config.log_level)
    harden_filesystem(config)
    logger.info("بدء تشغيل البوت — الإصدار %s", APP_VERSION)

    lock = SingleInstance(config.data_dir / "bot.lock")
    try:
        lock.acquire()
    except AlreadyRunningError as exc:
        logger.error("%s", exc)
        print(f"❌ {exc}", file=sys.stderr)
        return 2

    try:
        application = build_application(config)
        # drop_pending_updates: تجاهل ما تراكم أثناء التوقف حتى لا تُنفَّذ ضغطات
        # أزرار قديمة على حالة تغيّرت — الطلبات نفسها تُستأنف من قاعدة البيانات.
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "my_chat_member"],
        )
    except (KeyboardInterrupt, SystemExit):
        logger.info("إيقاف البوت بطلب من المشغّل")
    finally:
        lock.release()
        logger.info("انتهى التشغيل")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### `.env.example`  ·  مُحدَّث  ·  37 سطراً

تنبيهات الصلاحية وصيغ القيم.

```bash
# ==========================================================
#  ملف إعدادات البيئة — انسخه إلى .env ثم املأ القيم
#  ⚠️ لا ترفع ملف .env إلى Git أبداً
#  🔒 اضبط صلاحيته: chmod 600 .env   (يفحصه البوت ويضبطه عند الإقلاع، ويفحصه
#     الأمر: python -m scripts.security_check)
# ==========================================================

# توكن البوت من BotFather (مطلوب لتشغيل البوت، غير مطلوب لتهيئة قاعدة البيانات)
# الصيغة: 123456789:AA... بلا مسافات أو علامات اقتباس (تُفحص عند التحميل)
BOT_TOKEN=

# معرفات تيليجرام لأصحاب صلاحية الأدمن الأعلى، مفصولة بفواصل
# تُستخدم لزرع أول حساب إداري وللطوارئ فقط — معرّفات أشخاص موجبة (ليست مجموعات)
SUPER_ADMIN_IDS=

# مفتاح تشفير مفاتيح المزودين (Fernet)
# ولّده بالأمر: python -m scripts.init_db --gen-key
ENCRYPTION_KEY=

# مسار ملف قاعدة البيانات
DATABASE_PATH=data/smm_bot.db

# إعدادات السجلات: DEBUG / INFO / WARNING / ERROR / CRITICAL
LOG_LEVEL=INFO
LOG_FILE=logs/bot.log

# مجلد النسخ الاحتياطية
BACKUP_DIR=backups

# المنطقة الزمنية المستخدمة في العرض (التخزين دائماً UTC)
TIMEZONE=Asia/Aden

# قناة أو مجموعة خاصة لاستقبال تنبيهات النظام (اختياري)
ADMIN_ALERT_CHAT_ID=

# قناة خاصة لحفظ النسخ الاحتياطية خارج السيرفر (اختياري)
BACKUP_CHANNEL_ID=
```


## طبقة الأمان المشتركة (utils / middlewares)

### `utils/net_security.py`  ·  جديد  ·  188 سطراً

منع SSRF: فحص نصي عند الحفظ + فحص DNS عند الإرسال.

```python
"""
حماية الاتصالات الخارجية: منع SSRF وتسريب مفاتيح المزودين (المرحلة 9).

المشكلة:
    رابط API للمزود يُدخله أدمن، والبوت يرسل إليه مفتاح المزود مع كل طلب.
    رابط خبيث أو خاطئ يعني أحد ثلاثة أخطار:
        1. **SSRF**: توجيه البوت إلى عنوان داخلي (127.0.0.1، 169.254.169.254،
           شبكة الخادم الخاصة) لقراءة خدمات لا يجوز الوصول إليها.
        2. **تسريب المفتاح**: رابط `http://` يرسل المفتاح نصاً صريحاً عبر الشبكة.
        3. **بيانات اعتماد داخل الرابط** (`https://user:pass@host`) تظهر في اللوقات.

الحل (طبقتان):
    • عند الحفظ: `validate_public_https_url` — فحص نصي سريع (بروتوكول، منفذ،
      اسم المضيف، عنوان IP حرفي).
    • عند الإرسال: `ensure_public_host` — يحلّ اسم النطاق ويرفض إن أشار إلى أي
      عنوان غير عام (يسدّ حيلة نطاق عام يشير إلى عنوان داخلي).

قيد معروف (موثَّق في تقرير المرحلة): بين فحص DNS وفتح الاتصال فجوة زمنية صغيرة
(DNS rebinding)؛ الحد منها كاملاً يتطلب تثبيت العنوان داخل الناقل، وهو خارج
نطاق هذه المرحلة. الفحص الحالي يسدّ الأخطاء الشائعة والهجمات المباشرة.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from core.exceptions import ProviderPermanentError, ValidationError

#: لواحق أسماء المضيفين المحلية/الداخلية المرفوضة دائماً
BLOCKED_HOST_SUFFIXES: tuple[str, ...] = (
    ".local", ".localhost", ".internal", ".lan", ".home", ".corp", ".intranet", ".private",
)

#: أسماء مضيفين محجوزة مرفوضة بالنص
BLOCKED_HOSTNAMES: frozenset[str] = frozenset({"localhost", "ip6-localhost", "metadata.google.internal"})

#: المنافذ المسموحة لواجهات المزودين (غير ذلك يُرفض: لا فحص منافذ داخلية)
ALLOWED_PORTS: frozenset[int] = frozenset({443, 8443})

#: مدة بقاء نتيجة فحص DNS الناجحة (ثانية) — لتفادي حلّ الاسم عند كل طلب
DNS_CACHE_TTL_SECONDS: float = 300.0

#: نوع دالة حلّ الأسماء (قابلة للحقن في الاختبارات): اسم المضيف ← قائمة عناوين IP
Resolver = Callable[[str], Awaitable[list[str]]]

_dns_cache: dict[str, float] = {}


def is_public_ip(value: str) -> bool:
    """
    هل العنوان عام قابل للوصول من الإنترنت؟

    يرفض: الحلقة المحلية، الخاص (RFC1918/ULA)، link-local (169.254.x.x)،
    المحجوز، البث المتعدد، وغير المحدد (0.0.0.0). العناوين IPv4 المضمَّنة في
    IPv6 (`::ffff:127.0.0.1`) تُفحص بعد فك التضمين حتى لا تلتف على القاعدة.
    """
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


def _reject(reason: str, *, field: str) -> ValidationError:
    """بناء خطأ تحقق موحّد برسالة عربية تذكر سبب الرفض."""
    return ValidationError(
        f"{field} مرفوض: {reason}",
        user_message=f"❌ {field} غير آمن: {reason}",
    )


def validate_public_https_url(url: str | None, *, field: str = "رابط API") -> str:
    """
    فحص نصي لرابط مزود: https فقط، منفذ مسموح، مضيف عام، بلا بيانات اعتماد.

    المخرجات: الرابط بعد إزالة الفراغات.

    الاستثناءات:
        ValidationError : أي مخالفة مع ذكر سببها بالعربية.
    """
    text = (url or "").strip()
    if not text:
        raise _reject("الرابط فارغ", field=field)
    if len(text) > 300:
        raise _reject("الرابط طويل جداً", field=field)
    if any(ch.isspace() or ord(ch) < 32 for ch in text):
        raise _reject("الرابط يحتوي مسافات أو محارف تحكم", field=field)

    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError as exc:
        raise _reject("صيغة الرابط غير صحيحة", field=field) from exc

    if parts.scheme.lower() != "https":
        raise _reject("يجب أن يبدأ بـ https:// (مفتاح المزود لا يُرسل بلا تشفير)", field=field)
    if parts.username or parts.password:
        raise _reject("لا يجوز وضع اسم مستخدم أو كلمة مرور داخل الرابط", field=field)

    host = (parts.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise _reject("لا يوجد اسم نطاق", field=field)
    if host in BLOCKED_HOSTNAMES or host.endswith(BLOCKED_HOST_SUFFIXES):
        raise _reject("النطاق محلي/داخلي", field=field)

    is_literal_ip = _looks_like_ip(host)
    if is_literal_ip:
        if not is_public_ip(host):
            raise _reject("عنوان IP غير عام (داخلي أو محجوز)", field=field)
    elif "." not in host:
        raise _reject("اسم النطاق غير مكتمل", field=field)

    if port is not None and port not in ALLOWED_PORTS:
        raise _reject(f"المنفذ {port} غير مسموح (المسموح: 443 أو 8443)", field=field)
    return text


def _looks_like_ip(host: str) -> bool:
    """هل النص عنوان IP حرفي (v4 أو v6)؟ — الأرقام المجرّدة (مثل 2130706433) تُعدّ IP أيضاً."""
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    # صيغ قديمة يقبلها بعض المحللات: 2130706433 أو 0x7f000001 أو 017700000001
    try:
        int(host, 0)
        return True
    except ValueError:
        return False


async def _system_resolver(host: str) -> list[str]:
    """حلّ اسم المضيف عبر نظام التشغيل دون حجب حلقة الأحداث."""
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return sorted({str(info[4][0]) for info in infos})


async def ensure_public_host(url: str, *, resolver: Resolver | None = None) -> None:
    """
    التأكد وقت الإرسال أن اسم مضيف الرابط يشير إلى عناوين عامة فقط.

    المدخلات:
        url      : رابط المزود (سبق تحقق صيغته عند الحفظ).
        resolver : دالة حلّ بديلة (للاختبارات).

    الاستثناءات:
        ProviderPermanentError : النطاق لا يُحلّ، أو أحد عناوينه غير عام.
                                 (دائم لأن إعادة المحاولة لن تغيّر الحكم الأمني.)
    """
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    if not host:
        raise ProviderPermanentError("رابط المزود بلا اسم مضيف")

    now = time.monotonic()
    cached_until = _dns_cache.get(host, 0.0)
    if cached_until > now:
        return

    if _looks_like_ip(host):
        addresses = [host]
    else:
        try:
            addresses = await (resolver or _system_resolver)(host)
        except OSError as exc:
            raise ProviderPermanentError(f"تعذّر حلّ نطاق المزود {host}: {type(exc).__name__}") from exc

    if not addresses:
        raise ProviderPermanentError(f"النطاق {host} لا يشير إلى أي عنوان")
    for address in addresses:
        if not is_public_ip(address):
            raise ProviderPermanentError(
                f"النطاق {host} يشير إلى عنوان غير عام ({address}) — تم رفض الاتصال حمايةً من SSRF"
            )
    _dns_cache[host] = now + DNS_CACHE_TTL_SECONDS


def clear_dns_cache() -> None:
    """تفريغ ذاكرة نتائج DNS (للاختبارات وعند تغيير رابط مزود)."""
    _dns_cache.clear()
```

### `utils/fs_security.py`  ·  جديد  ·  123 سطراً

فحص/ضبط صلاحيات الملفات الحسّاسة (0600/0700).

```python
"""
تصلّب صلاحيات الملفات والمجلدات الحسّاسة (المرحلة 9).

لماذا؟
    ملف `.env` فيه التوكن ومفتاح التشفير، وقاعدة البيانات فيها أرصدة العملاء
    ومفاتيح المزودين (مشفّرة)، والنسخ الاحتياطية نسخة كاملة منها. على خادم
    مشترك أو بعد نسخ ملفات بأمر `cp` يصبح الملف بصلاحية `644` فيقرؤه أي
    مستخدم آخر على الجهاز. نضبط الصلاحيات تلقائياً عند الإقلاع ونبلّغ بما
    تعذّر ضبطه بدل السكوت.

الاستثناء: على ويندوز لا يوجد مكافئ مباشر لـchmod، فنعيد قائمة فارغة.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: الصلاحية المطلوبة للملفات الحسّاسة: قراءة/كتابة للمالك فقط
FILE_MODE = 0o600

#: الصلاحية المطلوبة للمجلدات الحسّاسة: دخول المالك فقط
DIR_MODE = 0o700

#: أي بت ضمن هذه القناع يعني أن المجموعة أو الآخرين يملكون وصولاً
GROUP_OTHER_MASK = 0o077


@dataclass(frozen=True, slots=True)
class PathCheck:
    """
    نتيجة فحص مسار واحد.

    الحقول:
        path     : المسار.
        label    : وصف عربي مختصر (مثل «ملف البيئة .env»).
        mode     : الصلاحية الحالية بعد المعالجة (None إن لم يوجد المسار).
        insecure : هل بقي مفتوحاً للمجموعة/الآخرين؟
        fixed    : هل ضُبطت الصلاحية في هذا الاستدعاء؟
        note     : سبب إن تعذّر الضبط.
    """

    path: Path
    label: str
    mode: int | None
    insecure: bool
    fixed: bool = False
    note: str = ""

    @property
    def mode_text(self) -> str:
        """الصلاحية بصيغة ثمانية مثل 600 (أو «غير موجود»)."""
        return "غير موجود" if self.mode is None else format(self.mode, "03o")


def _check_one(path: Path, label: str, expected: int, *, fix: bool) -> PathCheck | None:
    """فحص مسار واحد وضبطه عند الطلب؛ يُرجع None إن لم يكن موجوداً."""
    try:
        current = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        return None
    except OSError as exc:
        return PathCheck(path, label, None, True, note=f"تعذّر الفحص: {type(exc).__name__}")

    if current & GROUP_OTHER_MASK == 0:
        return PathCheck(path, label, current, False)
    if not fix:
        return PathCheck(path, label, current, True)
    try:
        os.chmod(path, expected)
    except OSError as exc:
        logger.warning("تعذّر ضبط صلاحية %s إلى %o: %s", path, expected, exc)
        return PathCheck(path, label, current, True, note=f"تعذّر الضبط: {type(exc).__name__}")
    logger.info("ضُبطت صلاحية %s من %o إلى %o", path, current, expected)
    return PathCheck(path, label, expected, False, fixed=True)


def sensitive_paths(
    *, env_file: Path, database_path: Path, data_dir: Path, backup_dir: Path, log_dir: Path
) -> list[tuple[Path, str, int]]:
    """
    قائمة المسارات الحسّاسة مع الصلاحية المطلوبة لكل منها.

    تشمل ملفات SQLite الجانبية (`-wal`/`-shm`) لأنها تحوي بيانات حديثة غير مدمجة.
    """
    return [
        (env_file, "ملف البيئة .env (التوكن ومفتاح التشفير)", FILE_MODE),
        (database_path, "قاعدة البيانات", FILE_MODE),
        (Path(f"{database_path}-wal"), "سجل WAL لقاعدة البيانات", FILE_MODE),
        (Path(f"{database_path}-shm"), "ذاكرة SHM لقاعدة البيانات", FILE_MODE),
        (data_dir / "bot.lock", "ملف قفل النسخة الواحدة", FILE_MODE),
        (data_dir, "مجلد البيانات", DIR_MODE),
        (backup_dir, "مجلد النسخ الاحتياطية", DIR_MODE),
        (log_dir, "مجلد اللوقات", DIR_MODE),
    ]


def check_paths(
    entries: list[tuple[Path, str, int]], *, fix: bool = False
) -> list[PathCheck]:
    """
    فحص (وضبط اختيارياً) صلاحيات مجموعة مسارات.

    المدخلات:
        entries : قائمة (المسار، الوصف، الصلاحية المطلوبة).
        fix     : True لضبط المخالف تلقائياً (يُستخدم عند الإقلاع)، False للفحص فقط.

    المخرجات: نتائج المسارات الموجودة فقط. فارغة على ويندوز.
    """
    if os.name != "posix":
        return []
    results = []
    for path, label, expected in entries:
        outcome = _check_one(path, label, expected, fix=fix)
        if outcome is not None:
            results.append(outcome)
    return results
```

### `utils/throttle.py`  ·  جديد  ·  83 سطراً

`AlertThrottle` لتهدئة التنبيهات المتكررة.

```python
"""
مُهدِّئ التنبيهات المتكررة (المرحلة 9).

المشكلة: عطل واحد (مثل انقطاع قاعدة البيانات) قد يولّد مئات الأخطاء في الدقيقة؛
لو أرسلنا تنبيهاً لكل خطأ لأغرقنا الأدمن وأخفينا التنبيه المهم وسط الضجيج.

الحل: تنبيه واحد لكل «بصمة خطأ» خلال فترة تهدئة، مع عدّ ما كُبت ليُذكر في التنبيه
التالي («تكرر 37 مرة»)، وسقف إجمالي للتنبيهات في النافذة نفسها حتى لو تنوّعت الأخطاء.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

#: أقصى عدد بصمات تُحفظ في الذاكرة (حماية من نموّ غير محدود)
MAX_TRACKED_KEYS = 500


@dataclass(frozen=True, slots=True)
class ThrottleDecision:
    """
    قرار المُهدِّئ.

    الحقول:
        allow      : هل يُرسل التنبيه الآن؟
        suppressed : عدد مرات الكبت السابقة لهذه البصمة (يُذكر عند السماح).
    """

    allow: bool
    suppressed: int = 0


class AlertThrottle:
    """تهدئة بحسب البصمة + سقف إجمالي لكل نافذة تهدئة."""

    def __init__(
        self, *, max_per_window: int = 5, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """
        المدخلات:
            max_per_window : أقصى تنبيهات مسموحة في نافذة التهدئة عبر كل البصمات.
            clock          : ساعة قابلة للحقن (الاختبارات تتحكم بالزمن بلا انتظار).
        """
        self._max_per_window = max_per_window
        self._clock = clock
        self._last_sent: dict[str, float] = {}
        self._suppressed: dict[str, int] = {}
        self._window_sent: list[float] = []

    def check(self, key: str, *, cooldown_seconds: float) -> ThrottleDecision:
        """
        تقرير إرسال تنبيه لهذه البصمة الآن.

        القواعد:
            1. إن أُرسل تنبيه للبصمة خلال فترة التهدئة ⇒ كبت (وعدّ).
            2. إن بلغ إجمالي التنبيهات في النافذة السقف ⇒ كبت (وعدّ).
            3. غير ذلك ⇒ سماح وتصفير عدّاد الكبت للبصمة.
        """
        now = self._clock()
        self._window_sent = [stamp for stamp in self._window_sent if now - stamp < cooldown_seconds]

        last = self._last_sent.get(key)
        if last is not None and now - last < cooldown_seconds:
            self._suppressed[key] = self._suppressed.get(key, 0) + 1
            return ThrottleDecision(False)
        if len(self._window_sent) >= self._max_per_window:
            self._suppressed[key] = self._suppressed.get(key, 0) + 1
            return ThrottleDecision(False)

        if len(self._last_sent) >= MAX_TRACKED_KEYS:
            self._evict_oldest()
        suppressed = self._suppressed.pop(key, 0)
        self._last_sent[key] = now
        self._window_sent.append(now)
        return ThrottleDecision(True, suppressed)

    def _evict_oldest(self) -> None:
        """حذف أقدم بصمة عند امتلاء الذاكرة."""
        oldest = min(self._last_sent, key=self._last_sent.__getitem__)
        self._last_sent.pop(oldest, None)
        self._suppressed.pop(oldest, None)
```

### `utils/security.py`  ·  مُحدَّث  ·  153 سطراً

تنقية الأسرار (`sanitize`) وتسجيلها (`register_secret`) والتشفير.

```python
"""
أدوات الأمان: تشفير أسرار المزودين، وإخفاء الأسرار عند العرض والتسجيل.

قواعد صارمة:
    • مفاتيح API للمزودين تُخزَّن مشفّرة (Fernet) ولا تُعرض كاملة أبداً.
    • لا يُكتب أي سر في ملفات اللوق.
"""

from __future__ import annotations

import hashlib
import re
import secrets

from cryptography.fernet import Fernet, InvalidToken

from core.exceptions import EncryptionError


def generate_encryption_key() -> str:
    """توليد مفتاح تشفير جديد (يوضع في متغير البيئة ENCRYPTION_KEY)."""
    return Fernet.generate_key().decode("utf-8")


class SecretBox:
    """
    صندوق تشفير متماثل للأسرار المخزَّنة في قاعدة البيانات.

    الاستخدام: تشفير api_key للمزود قبل الحفظ، وفك التشفير عند الاستدعاء فقط.
    """

    def __init__(self, key: str | None) -> None:
        """تهيئة الصندوق بمفتاح Fernet؛ يُرفع خطأ واضح إذا كان المفتاح ناقصاً أو تالفاً."""
        if not key:
            raise EncryptionError(
                "متغير البيئة ENCRYPTION_KEY غير موجود. "
                "ولّد مفتاحاً عبر: python -m scripts.init_db --gen-key"
            )
        try:
            self._fernet = Fernet(key.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise EncryptionError("قيمة ENCRYPTION_KEY غير صالحة (يجب أن تكون مفتاح Fernet).") from exc

    def encrypt(self, plaintext: str) -> str:
        """تشفير نص سري وإرجاعه كنص قابل للتخزين."""
        if not plaintext:
            raise EncryptionError("لا يمكن تشفير قيمة فارغة.")
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """فك تشفير نص مخزَّن؛ يُرفع خطأ إذا كان المفتاح خاطئاً أو البيانات تالفة."""
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError, TypeError) as exc:
            raise EncryptionError(
                "تعذر فك تشفير المفتاح المخزَّن — تأكد أن ENCRYPTION_KEY هو نفسه المستخدم عند الحفظ."
            ) from exc


def mask_secret(value: str | None, visible: int = 4) -> str:
    """
    إخفاء سر للعرض في الواجهة (يُظهر آخر أربعة محارف فقط).

    مثال: "abcd1234efgh" → "••••efgh"
    """
    if not value:
        return "غير محدد"
    tail = value[-visible:] if len(value) > visible else value
    return f"••••{tail}"


def secret_hint(value: str) -> str:
    """تلميح قصير يُخزَّن في قاعدة البيانات بجانب المفتاح المشفّر (آخر 4 محارف)."""
    return value[-4:] if len(value) >= 4 else "****"


def fingerprint(value: str) -> str:
    """بصمة SHA-256 مختصرة لقيمة سرية (للمقارنة دون كشف القيمة)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def new_token(length: int = 16) -> str:
    """توليد رمز عشوائي آمن (يُستخدم كمرجع فريد أو مفتاح منع تكرار)."""
    return secrets.token_urlsafe(length)


#: قيمة سرية: كل ما يلي علامة = أو : حتى أول فاصل، مع تجاهل علامات الاقتباس المحيطة
_SECRET_VALUE = r"[\"']?\s*[=:]\s*[\"']?[^\s,;&'\"}\])]+"

#: أنماط نصية يجب حذفها من أي نص يُسجَّل في اللوقات أو يُخزَّن في قاعدة البيانات
#: كل عنصر: (النمط، النص البديل)
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # توكن بوت تيليجرام 123456789:AA... وكذلك داخل روابط API: /bot123456789:AA.../getUpdates
    # (لا نشترط حدّ كلمة قبل الرقم لأن "bot" ملتصقة به في الرابط)
    (re.compile(r"(?<!\d)(?:bot)?\d{6,12}:[A-Za-z0-9_\-]{30,}(?![A-Za-z0-9_\-])"), "***"),
    # رموز Fernet المشفّرة (مفاتيح المزودين المخزَّنة) تبدأ دائماً بـ gAAAA
    (re.compile(r"\bgAAAA[A-Za-z0-9_\-=]{40,}"), "***"),
    # api_key / token / secret / password بأي صيغة (JSON أو query أو سطر إعداد)
    (
        re.compile(
            r"(?i)\b(api[_-]?key|api[_-]?token|access[_-]?token|auth[_-]?token|token|secret"
            r"|password|passwd|pwd)\b" + _SECRET_VALUE
        ),
        r"\1=***",
    ),
    # المعامل key= المستخدم في لوحات SMM (perfect panel)
    (re.compile(r"(?i)\bkey\b" + _SECRET_VALUE), "key=***"),
    # بيانات اعتماد داخل الرابط: https://user:pass@host
    (re.compile(r"(?i)\b(https?://)[^\s/@:]+:[^\s/@]+@"), r"\1***@"),
)

#: أسرار معروفة وقت التشغيل (التوكن ومفتاح التشفير …) تُحذف حرفياً من أي نص
_KNOWN_SECRETS: set[str] = set()

#: أقصر طول مقبول لسر مسجَّل (قيمة أقصر تمسح كلمات عادية من النصوص)
MIN_REGISTERED_SECRET_LENGTH = 8


def register_secret(value: str | None) -> None:
    """
    تسجيل سر معروف (مثل BOT_TOKEN أو ENCRYPTION_KEY) ليُحذف حرفياً من كل لوق وحقل مخزَّن.

    لماذا إضافة للأنماط؟ النمط يلتقط الصيغ المعروفة فقط، أما التسجيل الصريح فيلتقط
    القيمة نفسها أياً كان موضعها (داخل traceback أو رسالة خطأ مكتبة خارجية).
    """
    if value and len(value) >= MIN_REGISTERED_SECRET_LENGTH:
        _KNOWN_SECRETS.add(value)


def clear_registered_secrets() -> None:
    """مسح الأسرار المسجَّلة (للاختبارات فقط)."""
    _KNOWN_SECRETS.clear()


def sanitize(text: str | None, extra_secrets: tuple[str, ...] = ()) -> str:
    """
    تنقية نص من الأسرار قبل تسجيله في اللوق أو حفظه في قاعدة البيانات.

    المدخلات:
        text           : النص الخام (مثل استجابة المزود أو رسالة الخطأ).
        extra_secrets  : قيم سرية معروفة يجب حذفها حرفياً (مثل مفتاح المزود الحالي).

    المخرجات: نص آمن للتسجيل.
    """
    if not text:
        return ""
    clean = str(text)
    for secret in (*extra_secrets, *_KNOWN_SECRETS):
        if secret:
            clean = clean.replace(secret, "***")
    for pattern, replacement in _SECRET_PATTERNS:
        clean = pattern.sub(replacement, clean)
    return clean
```

### `middlewares/rate_limit.py`  ·  مُحدَّث  ·  206 سطراً

حدود متدرجة (عميل/أدمن/حسّاس) + `AbuseGuard` للإيقاف المؤقت.

```python
"""
حد معدل الاستخدام (Rate limit) وحارس الإساءة — حماية البوت وقاعدة البيانات.

الطبقات (المرحلة 9):
    1. `RateLimiter`: نافذة منزلقة في الذاكرة لكل (مستخدم، سلة). السلة `general`
       للتصفح، و`sensitive` للإجراءات المالية الحسّاسة (تأكيد، رفع إثبات…)
       بحدّ أضيق، حتى لا يستطيع مستخدم يضغط التأكيد عشرات المرات.
    2. `AbuseGuard`: عدّاد مخالفات. من يتجاوز الحد مراراً خلال نافذة المخالفات
       يُوقَف مؤقتاً، ويُتجاهل خلال الإيقاف **بصمت** (لا ردود ولا استعلامات
       قاعدة بيانات) — فالرد على المُغرِق يضاعف الضغط بدل أن يخففه.

لماذا في الذاكرة؟
    الحد وسيلة حماية من الضغط السريع لا سجل محاسبي؛ كتابته في قاعدة البيانات
    تعني كتابة عند كل ضغطة زر — وهو ما يُراد تجنّبه أصلاً. يُعاد ضبطه عند
    إعادة التشغيل وهذا مقبول ومقصود. أما **بدء الإيقاف** فيُكتب في سجل
    التدقيق (حدث `security.rate_limit_block`) لأنه قرار أمني يستحق الأثر.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass

#: طول النافذة الزمنية بالثواني
WINDOW_SECONDS: float = 60.0

#: أقصى عدد مفاتيح نحتفظ بسجلها قبل التنظيف الدوري
MAX_TRACKED_USERS: int = 10_000

#: السلة العامة والسلة الحسّاسة
BUCKET_GENERAL = "general"
BUCKET_SENSITIVE = "sensitive"

#: نافذة احتساب المخالفات (ثانية): المخالفات الأقدم لا تُحتسب
STRIKE_WINDOW_SECONDS: float = 600.0

#: أقل فاصل بين تحذيرين متتاليين لنفس المستخدم (ثانية) — لا نغرقه بالتحذيرات
WARNING_COOLDOWN_SECONDS: float = 10.0

#: الإجراءات الحسّاسة داخل أزرار المحادثات (تأكيدات تنفّذ عملاً مالياً أو إنشائياً)
SENSITIVE_FLOW_ACTIONS: frozenset[str] = frozenset({"confirm"})


class RateLimiter:
    """عدّاد إجراءات لكل (مستخدم، سلة) ضمن نافذة زمنية منزلقة."""

    def __init__(
        self, *, window_seconds: float = WINDOW_SECONDS, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """تهيئة العدّاد بنافذة زمنية محددة ومصدر وقت قابل للحقن في الاختبارات."""
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[tuple[int, str], deque[float]] = defaultdict(deque)

    def hit(self, user_id: int, limit: int, *, bucket: str = BUCKET_GENERAL) -> bool:
        """
        تسجيل إجراء جديد وفحص تجاوز الحد.

        المدخلات:
            user_id : معرف تيليجرام للمستخدم.
            limit   : الحد المسموح خلال النافذة (صفر أو أقل = بلا حد).
            bucket  : سلة العدّ (`general` أو `sensitive`).

        المخرجات: True إذا كان الإجراء مسموحاً، False إذا تجاوز الحد.
        """
        if limit <= 0:
            return True

        now = self._clock()
        bucket_hits = self._hits[(user_id, bucket)]
        threshold = now - self._window
        while bucket_hits and bucket_hits[0] < threshold:        # إسقاط ما خرج من النافذة
            bucket_hits.popleft()

        if len(bucket_hits) >= limit:
            return False

        bucket_hits.append(now)
        if len(self._hits) > MAX_TRACKED_USERS:                  # تنظيف وقائي للذاكرة
            self._cleanup(threshold)
        return True

    def remaining(self, user_id: int, limit: int, *, bucket: str = BUCKET_GENERAL) -> int:
        """عدد الإجراءات المتبقية للمستخدم في النافذة الحالية."""
        if limit <= 0:
            return limit
        bucket_hits = self._hits.get((user_id, bucket))
        if not bucket_hits:
            return limit
        threshold = self._clock() - self._window
        active = sum(1 for moment in bucket_hits if moment >= threshold)
        return max(0, limit - active)

    def reset(self, user_id: int) -> None:
        """تصفير سجل مستخدم في كل السلال (الاختبارات، رفع الإيقاف)."""
        for key in [key for key in self._hits if key[0] == user_id]:
            self._hits.pop(key, None)

    def _cleanup(self, threshold: float) -> None:
        """إزالة المفاتيح التي لم تُسجَّل لها أي حركة داخل النافذة."""
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] < threshold]
        for key in stale:
            self._hits.pop(key, None)


@dataclass(frozen=True, slots=True)
class BlockInfo:
    """مستخدم موقوف مؤقتاً: معرفه والثواني المتبقية وعدد مخالفاته."""

    telegram_id: int
    seconds_left: int
    strikes: int


@dataclass(frozen=True, slots=True)
class ViolationResult:
    """نتيجة تسجيل مخالفة: هل بدأ الإيقاف؟ وهل نرسل تحذيراً الآن؟"""

    strikes: int
    blocked: bool
    warn: bool


class AbuseGuard:
    """
    عدّاد المخالفات والإيقاف المؤقت للمفرطين.

    كل تجاوز للحد = «مخالفة». عند بلوغ `strikes_limit` مخالفة داخل نافذة
    `STRIKE_WINDOW_SECONDS` يُوقَف صاحبها `block_seconds`. الحالة في الذاكرة.
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        """تهيئة الحارس بمصدر وقت قابل للحقن."""
        self._clock = clock
        self._strikes: dict[int, deque[float]] = defaultdict(deque)
        self._blocked_until: dict[int, float] = {}
        self._last_warning: dict[int, float] = {}
        self.total_violations: int = 0
        self.total_blocks: int = 0

    def seconds_blocked(self, telegram_id: int) -> float:
        """الثواني المتبقية من إيقاف المستخدم (صفر = غير موقوف). ينظّف الإيقاف المنتهي."""
        until = self._blocked_until.get(telegram_id)
        if until is None:
            return 0.0
        left = until - self._clock()
        if left <= 0:
            self._blocked_until.pop(telegram_id, None)
            self._strikes.pop(telegram_id, None)
            return 0.0
        return left

    def is_blocked(self, telegram_id: int) -> bool:
        """هل المستخدم موقوف مؤقتاً الآن؟"""
        return self.seconds_blocked(telegram_id) > 0

    def record_violation(
        self, telegram_id: int, *, strikes_limit: int, block_seconds: float
    ) -> ViolationResult:
        """
        تسجيل مخالفة جديدة وتقرير الإيقاف.

        المدخلات:
            strikes_limit : عدد المخالفات التي تُوجب الإيقاف.
            block_seconds : مدة الإيقاف.

        المخرجات: عدد المخالفات الحالية + هل بدأ الإيقاف + هل يُرسَل تحذير الآن
        (التحذير مُهدَّأ كل `WARNING_COOLDOWN_SECONDS`، وإشعار الإيقاف يُرسل دائماً).
        """
        now = self._clock()
        self.total_violations += 1
        strikes = self._strikes[telegram_id]
        threshold = now - STRIKE_WINDOW_SECONDS
        while strikes and strikes[0] < threshold:
            strikes.popleft()
        strikes.append(now)

        if len(strikes) >= max(1, strikes_limit):
            self._blocked_until[telegram_id] = now + block_seconds
            self.total_blocks += 1
            return ViolationResult(strikes=len(strikes), blocked=True, warn=True)

        last = self._last_warning.get(telegram_id)
        warn = last is None or now - last >= WARNING_COOLDOWN_SECONDS
        if warn:
            self._last_warning[telegram_id] = now
        return ViolationResult(strikes=len(strikes), blocked=False, warn=warn)

    def clear(self, telegram_id: int) -> bool:
        """رفع الإيقاف وتصفير المخالفات (إجراء إداري). يُرجع True إن كان موقوفاً فعلاً."""
        was_blocked = self.is_blocked(telegram_id)
        self._blocked_until.pop(telegram_id, None)
        self._strikes.pop(telegram_id, None)
        self._last_warning.pop(telegram_id, None)
        return was_blocked

    def blocked_snapshot(self) -> list[BlockInfo]:
        """قائمة الموقوفين حالياً (الأطول إيقافاً أولاً) لشاشة الأمان."""
        result = []
        for telegram_id in list(self._blocked_until):
            left = self.seconds_blocked(telegram_id)
            if left > 0:
                result.append(BlockInfo(telegram_id, int(left) + 1, len(self._strikes.get(telegram_id, ()))))
        return sorted(result, key=lambda info: -info.seconds_left)
```

### `middlewares/context.py`  ·  مُحدَّث  ·  262 سطراً

الطبقة الوسيطة: تحذير → إيقاف → تجاهل صامت + تسجيل الأحداث الأمنية.

```python
"""
الطبقة الوسيطة (Middleware) التي تسبق كل معالج.

تُسجَّل كـ`TypeHandler` في المجموعة `-10`، أي قبل أي معالج آخر، وتؤدي بالترتيب:

    1. تجاهل التحديثات خارج المحادثة الخاصة (البوت خاص بالاستخدام الفردي).
    2. تسجيل المستخدم أو تحديث بياناته (`UserService.get_or_create`).
    3. رفض المحظورين برسالة تشرح السبب.
    4. تطبيق وضع الصيانة على غير الأدمن.
    5. تطبيق حد معدل الاستخدام (عام + حسّاس) والإيقاف المؤقت للمفرطين.
    6. تحديث آخر نشاط (مرة كل دقيقة على الأكثر لتفادي كتابة عند كل ضغطة).

أي رفض يوقف سلسلة المعالجات عبر `ApplicationHandlerStop` فلا يصل التحديث
إلى بقية المعالجات إطلاقاً — وهذا ما يمنع تكرار فحوص الأمان داخل كل معالج.
"""

from __future__ import annotations

import time

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from core.exceptions import MaintenanceModeError, UserBannedError, ValidationError
from database.models import User
from handlers.common.ui import answer_callback, send
from keyboards.callback_data import NS_FLOW, CallbackError, unpack
from middlewares.rate_limit import (
    BUCKET_SENSITIVE,
    SENSITIVE_FLOW_ACTIONS,
    AbuseGuard,
    RateLimiter,
)
from services import ServiceContainer
from texts import ar
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: مفاتيح التخزين داخل `context.user_data`
USER_KEY = "db_user"
LAST_TOUCH_KEY = "last_activity_touch"

#: لا نحدّث «آخر نشاط» أكثر من مرة خلال هذه المدة (ثانية)
ACTIVITY_THROTTLE_SECONDS: float = 60.0

#: الأدوار الإدارية: لها حد عام أعلى (تتنقل بين صفحات كثيرة) وحد حسّاس ×3
STAFF_ROLES: frozenset[str] = frozenset({"support", "admin", "super_admin"})

#: مضاعف الحد الحسّاس للفريق الإداري
STAFF_SENSITIVE_MULTIPLIER = 3


def services_of(context: ContextTypes.DEFAULT_TYPE) -> ServiceContainer:
    """
    جلب حاوية الخدمات المحقونة في التطبيق عند الإقلاع.

    الاستثناءات:
        RuntimeError : التطبيق لم يُهيَّأ بالخدمات (خطأ برمجي لا يحدث في التشغيل الصحيح).
    """
    services = context.application.bot_data.get("services")
    if services is None:
        raise RuntimeError("حاوية الخدمات غير محقونة في bot_data — راجع main.py")
    return services


def current_user(context: ContextTypes.DEFAULT_TYPE) -> User | None:
    """المستخدم المحمَّل من قاعدة البيانات لهذا التحديث (None إن لم يُحمَّل بعد)."""
    if context.user_data is None:
        return None
    return context.user_data.get(USER_KEY)


def require_user(context: ContextTypes.DEFAULT_TYPE) -> User:
    """
    المستخدم الحالي مع ضمان وجوده.

    الاستثناءات:
        RuntimeError : استُدعي معالج قبل الطبقة الوسيطة (خطأ تسجيل handlers).
    """
    user = current_user(context)
    if user is None:
        raise RuntimeError("المستخدم غير محمَّل — تأكد من تسجيل الطبقة الوسيطة في المجموعة -10")
    return user


def refresh_user(context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
    """تحديث نسخة المستخدم المخزَّنة بعد أي تغيير (رصيد، دور، حظر)."""
    if context.user_data is not None:
        context.user_data[USER_KEY] = user


async def reload_user(context: ContextTypes.DEFAULT_TYPE) -> User:
    """إعادة قراءة المستخدم من قاعدة البيانات (بعد عملية غيّرت رصيده مثلاً)."""
    services = services_of(context)
    user = require_user(context)
    fresh = await services.users.get(user.id)
    if fresh is not None:
        refresh_user(context, fresh)
        return fresh
    return user


def is_sensitive_update(update: Update) -> bool:
    """
    هل التحديث إجراء حسّاس يخضع للحد الأضيق؟

    الحسّاس: زر «تأكيد» داخل محادثة (إنشاء طلب، إرسال شحن، تأكيد عملية إدارية …)
    أو رسالة تحمل صورة/ملفاً (إثبات الدفع). التصفح والنصوص العادية ليست حسّاسة.
    """
    query = update.callback_query
    if query is not None:
        if not query.data:
            return False
        try:
            callback = unpack(query.data)
        except CallbackError:
            return False
        return callback.namespace == NS_FLOW and callback.action in SENSITIVE_FLOW_ACTIONS
    message = update.effective_message
    return bool(message is not None and (message.photo or message.document))


class UserContextMiddleware:
    """الطبقة الوسيطة الموحّدة لتحميل المستخدم وفرض قواعد الأمان."""

    def __init__(self, limiter: RateLimiter | None = None, guard: AbuseGuard | None = None) -> None:
        """تهيئة الطبقة مع عدّاد حد الاستخدام وحارس الإساءة (يُحقنان في الاختبارات)."""
        self.limiter = limiter or RateLimiter()
        self.guard = guard or AbuseGuard()

    async def __call__(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        تنفيذ الفحوص قبل أي معالج.

        الاستثناءات:
            ApplicationHandlerStop : التحديث مرفوض (حظر/صيانة/حد استخدام/تسجيل مغلق).
        """
        telegram_user = update.effective_user
        chat = update.effective_chat
        if telegram_user is None or telegram_user.is_bot:
            raise ApplicationHandlerStop

        # البوت مصمَّم للمحادثة الخاصة فقط — المجموعات تُرفض برسالة واضحة مرة واحدة
        if chat is not None and chat.type != "private":
            await send(update, context, ar.ERR_NO_PRIVATE)
            raise ApplicationHandlerStop

        # موقوف مؤقتاً بسبب الإفراط: تجاهل صامت قبل أي قراءة من قاعدة البيانات
        if self.guard.is_blocked(telegram_user.id):
            raise ApplicationHandlerStop

        services = services_of(context)

        try:
            user, created = await services.users.get_or_create(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
            )
        except ValidationError as exc:
            # التسجيل مغلق من الإعدادات ومحاولة إنشاء حساب جديد
            await answer_callback(update)
            await send(update, context, exc.user_message)
            raise ApplicationHandlerStop from None

        if context.user_data is not None:
            context.user_data[USER_KEY] = user
            context.user_data["is_new_user"] = created

        # 1) الحظر — يسبق كل شيء
        try:
            await services.auth.ensure_not_banned(user)
        except UserBannedError as exc:
            await answer_callback(update, "🚫")
            await send(update, context, exc.user_message)
            raise ApplicationHandlerStop from None

        # 2) الصيانة — لا تمنع الأدمن
        try:
            await services.auth.ensure_available(user)
        except MaintenanceModeError as exc:
            await answer_callback(update, "🚧")
            await send(update, context, exc.user_message)
            raise ApplicationHandlerStop from None

        # 3) حد معدل الاستخدام: عام لكل الإجراءات + أضيق للحسّاسة، والمتكرر يُوقَف مؤقتاً
        is_staff = user.role in STAFF_ROLES
        if is_staff:
            general_limit = await services.settings.get_int("rate_limit_admin_actions_per_minute", 120)
        else:
            general_limit = await services.settings.get_int("rate_limit_actions_per_minute", 30)
        allowed = self.limiter.hit(telegram_user.id, general_limit)
        if allowed and is_sensitive_update(update):
            sensitive_limit = await services.settings.get_int("rate_limit_sensitive_per_minute", 8)
            if is_staff:
                sensitive_limit *= STAFF_SENSITIVE_MULTIPLIER
            allowed = self.limiter.hit(telegram_user.id, sensitive_limit, bucket=BUCKET_SENSITIVE)
        if not allowed:
            await self._handle_violation(update, context, services, user)
            raise ApplicationHandlerStop

        # 4) تحديث آخر نشاط بتهدئة
        await self._touch_activity(context, services, user)

    async def _handle_violation(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        services: ServiceContainer,
        user: User,
    ) -> None:
        """
        معالجة تجاوز الحد: تسجيل مخالفة، وبدء الإيقاف المؤقت عند التكرار، وتحذير مُهدَّأ.

        التحذير لا يُرسل لكل تحديث (سيضاعف الضغط)، والإيقاف يُسجَّل في سجل التدقيق
        كحدث أمني `security.rate_limit_block`.
        """
        strikes_limit = await services.settings.get_int("rate_limit_strikes_before_block", 5)
        block_minutes = await services.settings.get_int("rate_limit_block_minutes", 5)
        result = self.guard.record_violation(
            user.telegram_id, strikes_limit=strikes_limit, block_seconds=block_minutes * 60.0
        )
        logger.info(
            "تجاوز المستخدم %s حد الاستخدام (مخالفات: %s/%s)", user.telegram_id, result.strikes, strikes_limit
        )

        if result.blocked:
            try:
                await services.audit.log_security_event(
                    event="rate_limit_block",
                    user_id=user.id,
                    target_type="user",
                    target_id=user.id,
                    details={"strikes": result.strikes, "minutes": block_minutes, "role": user.role},
                )
            except Exception:                                    # noqa: BLE001
                logger.exception("تعذّر تسجيل حدث الإيقاف المؤقت للمستخدم %s", user.telegram_id)
            message = ar.ERR_RATE_BLOCKED.format(minutes=block_minutes)
            await answer_callback(update, message, alert=True)
            if update.callback_query is None:
                await send(update, context, message)
            return

        if result.warn:
            await answer_callback(update, ar.ERR_RATE_LIMITED, alert=True)
            if update.callback_query is None:
                await send(update, context, ar.ERR_RATE_LIMITED)

    async def _touch_activity(
        self, context: ContextTypes.DEFAULT_TYPE, services: ServiceContainer, user: User
    ) -> None:
        """تحديث وقت آخر نشاط مرة واحدة كل دقيقة على الأكثر."""
        if context.user_data is None:
            return
        now = time.monotonic()
        last = context.user_data.get(LAST_TOUCH_KEY)
        if last is not None and now - last < ACTIVITY_THROTTLE_SECONDS:
            return
        context.user_data[LAST_TOUCH_KEY] = now
        await services.users.touch_activity(user.id)
```

### `handlers/common/conversation.py`  ·  جديد  ·  82 سطراً

مصنع المحادثات الموحّد بمهلة 15 دقيقة.

```python
"""
مصنع المحادثات الموحّد مع مهلة عدم النشاط (المرحلة 9).

المشكلة:
    محادثة تأكيد مالية (اعتماد شحن، تعديل رصيد، إرسال إذاعة…) تبقى مفتوحة
    للأبد في ذاكرة البوت. لو ترك الأدمن شاشة «تأكيد» ثم عاد بعد يومين وضغط
    الزر القديم لنُفِّذت عملية بناءً على قرار نسيه — وقد تتغير حالة الحساب
    أو صلاحياته خلال ذلك. كذلك كل محادثة معلّقة تحجز ذاكرة بلا نهاية.

الحل:
    كل محادثات المشروع تُبنى عبر `conversation(...)` فتنتهي تلقائياً بعد
    `CONVERSATION_TIMEOUT_SECONDS` من آخر تفاعل: تُمسح بيانات كل المسارات
    ويُعلَم المستخدم برسالة واضحة، فيتحول الزر القديم إلى «زر منتهٍ» عادي
    تتعامل معه المسارات الاحتياطية بدل أن ينفّذ شيئاً.
"""

from __future__ import annotations

from typing import Any

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from handlers.common.ui import send
from keyboards.user_kb import main_menu_kb
from texts import ar
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: مهلة عدم النشاط قبل إنهاء المحادثة (ثانية) — 15 دقيقة
CONVERSATION_TIMEOUT_SECONDS: int = 15 * 60

#: كل مفاتيح بيانات المسارات في `user_data` (تُمسح كلها عند انتهاء المهلة)
FLOW_DATA_KEYS: tuple[str, ...] = (
    "admin_flow",
    "order_flow",
    "deposit_flow",
    "ticket_flow",
    "ticket_reply_flow",
)


async def on_conversation_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    إنهاء محادثة منتهية المهلة: مسح بياناتها وإبلاغ المستخدم بوضوح.

    المخرجات: `ConversationHandler.END`.
    """
    if context.user_data is not None:
        for key in FLOW_DATA_KEYS:
            context.user_data.pop(key, None)
    user = update.effective_user
    logger.info("انتهت مهلة محادثة المستخدم %s بسبب عدم النشاط", user.id if user else "?")
    await send(update, context, ar.CONVERSATION_TIMED_OUT, main_menu_kb())
    return ConversationHandler.END


def conversation(*, states: dict[Any, list], **kwargs: Any) -> ConversationHandler:
    """
    بناء `ConversationHandler` بمهلة عدم نشاط موحّدة.

    يقبل نفس وسائط `ConversationHandler` (entry_points/fallbacks/name/per_chat…)،
    ويضيف حالة `TIMEOUT` تمسح البيانات وتُبلغ المستخدم. لا يُسمح بتمرير
    `conversation_timeout` يدوياً حتى لا تشذّ محادثة عن السياسة.
    """
    if "conversation_timeout" in kwargs:
        raise ValueError("المهلة موحّدة في CONVERSATION_TIMEOUT_SECONDS ولا تُمرَّر يدوياً")
    merged = dict(states)
    merged[ConversationHandler.TIMEOUT] = [
        CallbackQueryHandler(on_conversation_timeout),
        MessageHandler(filters.ALL, on_conversation_timeout),
    ]
    return ConversationHandler(
        states=merged, conversation_timeout=CONVERSATION_TIMEOUT_SECONDS, **kwargs
    )
```

### `handlers/common/errors.py`  ·  مُحدَّث  ·  194 سطراً

معالج الأخطاء العام: بصمة + تهدئة + تنبيه الأدمن بنص منقّى.

```python
"""
المعالج العام للأخطاء غير المتوقعة.

ما يفعله عند أي استثناء يصل إليه:
    1. يسجّله في اللوق مع كامل التتبع (Traceback).
    2. يحفظه في جدول `error_logs` ليراه الأدمن لاحقاً داخل البوت (المرحلة 4).
    3. يُبلغ المستخدم برسالة عربية مهذّبة بلا أي تفاصيل تقنية.

مبدأ ملزم: **لا ابتلاع أخطاء**. كل خطأ يُسجَّل ويُرى، والمستخدم لا يُترك
أمام شاشة صامتة.
"""

from __future__ import annotations

import html
import time
import traceback

from telegram import Update
from telegram.error import Forbidden, NetworkError, RetryAfter, TimedOut
from telegram.ext import ContextTypes

from core.permissions import Permission
from handlers.common.ui import answer_callback, send
from texts import ar
from utils.logging_setup import get_logger
from utils.security import sanitize
from utils.throttle import AlertThrottle

logger = get_logger(__name__)

#: أقصى طول نص خطأ يُخزَّن في قاعدة البيانات
MAX_STORED_ERROR = 4000

#: أقصى طول لمقتطف الخطأ داخل تنبيه الأدمن
MAX_ALERT_SNIPPET = 200

#: مفتاح مُهدِّئ تنبيهات الأخطاء في `bot_data`
THROTTLE_KEY = "error_alert_throttle"


def _describe_update(update: object) -> str:
    """وصف مختصر للتحديث الذي سبّب الخطأ (بلا بيانات حساسة)."""
    if not isinstance(update, Update):
        return "تحديث غير معروف"
    user = update.effective_user
    parts = [f"user={user.id}" if user else "user=?"]
    if update.callback_query is not None:
        parts.append(f"button={update.callback_query.data}")
    elif update.effective_message is not None and update.effective_message.text:
        text = update.effective_message.text
        # نصّ المستخدم العادي قد يحوي سراً (مفتاح مزود يُكتب في محادثة) فلا نسجّله؛ الأوامر فقط
        if text.startswith("/"):
            parts.append(f"command={text.split()[0][:30]!r}")
        else:
            parts.append(f"text=<{len(text)} حرف>")
    return " | ".join(parts)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    المعالج العام: يُستدعى لكل استثناء لم يُلتقط داخل المعالجات.

    أخطاء الشبكة المؤقتة تُسجَّل كتحذير فقط (ستُعاد المحاولة تلقائياً)،
    وغيرها يُسجَّل كخطأ كامل في اللوق وقاعدة البيانات.
    """
    error = context.error
    description = _describe_update(update)

    if isinstance(error, (TimedOut, NetworkError, RetryAfter)):
        logger.warning("خطأ شبكة مؤقت (%s): %s", description, error)
        return

    if isinstance(error, Forbidden):
        # المستخدم حظر البوت — نعلّمه في قاعدة البيانات ولا نزعج اللوق بخطأ كامل
        logger.info("المستخدم حظر البوت (%s)", description)
        await _mark_blocked(update, context)
        return

    trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    logger.error("خطأ غير متوقع (%s): %s\n%s", description, error, trace)

    await _store_error(context, description, error, trace)
    await _alert_admins(context, error)

    if isinstance(update, Update):
        # فشل إبلاغ المستخدم لا يجب أن يخفي الخطأ الأصلي ولا أن يولّد خطأً جديداً
        try:
            await answer_callback(update)
            await send(update, context, ar.ERR_GENERIC)
        except Exception as notify_error:          # noqa: BLE001 - المعالج العام لا يُسقَط
            logger.warning("تعذر إبلاغ المستخدم بالخطأ: %s", notify_error)


def _error_fingerprint(error: BaseException | None) -> str:
    """
    بصمة الخطأ لتجميع المتشابه: نوعه + موضع رمي الاستثناء (آخر إطار في التتبع).

    الموضع أدق من النوع وحده (`KeyError` في مكانين مختلفين خطآن مختلفان)،
    وأدق من النص (الذي يحوي أرقاماً متغيرة فيكسر التجميع).
    """
    if error is None:
        return "unknown"
    location = "?"
    tb = error.__traceback__
    while tb is not None and tb.tb_next is not None:
        tb = tb.tb_next
    if tb is not None:
        location = f"{tb.tb_frame.f_code.co_filename.rsplit('/', 1)[-1]}:{tb.tb_lineno}"
    return f"{type(error).__name__}@{location}"


async def _alert_admins(context: ContextTypes.DEFAULT_TYPE, error: BaseException | None) -> None:
    """
    تنبيه من يملك `logs.view` بخطأ غير متوقع — مرة لكل بصمة في فترة التهدئة.

    يُعطَّل بالإعداد `error_alert_enabled`. النص المرسل نوع الخطأ + مقتطف منقّى فقط
    (لا تتبّع كامل ولا بيانات مستخدم)، والتفاصيل في «السجلات ← الأخطاء».
    فشل التنبيه نفسه يُسجَّل ولا يُسقط المعالج.
    """
    services = context.application.bot_data.get("services")
    if services is None:
        return
    try:
        if not await services.settings.get_bool("error_alert_enabled", True):
            return
        cooldown_minutes = await services.settings.get_int("error_alert_cooldown_minutes", 15)
        throttle = context.application.bot_data.setdefault(THROTTLE_KEY, AlertThrottle())
        fingerprint = _error_fingerprint(error)
        decision = throttle.check(fingerprint, cooldown_seconds=cooldown_minutes * 60)
        if not decision.allow:
            return

        snippet = sanitize(f"{error}")[:MAX_ALERT_SNIPPET] if error else ""
        repeated = f"\nتكرر قبل ذلك: {decision.suppressed} مرة (كُبتت تنبيهاتها)." if decision.suppressed else ""
        message = (
            f"النوع: {type(error).__name__ if error else 'غير معروف'}\n"
            f"الموضع: {fingerprint.split('@', 1)[-1]}\n"
            f"المقتطف: {html.escape(snippet) or '—'}{repeated}\n"
            "التفاصيل في: لوحة التحكم ← السجلات ← الأخطاء."
        )
        async with services.db.transaction() as tx:
            await services.notifications.notify_admins(
                tx,
                permission=Permission.LOGS_VIEW,
                token=f"error:{fingerprint}:{_epoch_bucket(cooldown_minutes)}",
                title="🚨 خطأ غير متوقع في البوت",
                message=message,
            )
    except Exception as alert_error:               # noqa: BLE001 - تنبيه الخطأ لا يُسقط المعالج العام
        logger.error("تعذر إرسال تنبيه الخطأ للأدمن: %s", alert_error)


def _epoch_bucket(cooldown_minutes: int) -> int:
    """رقم الشريحة الزمنية الحالية (يمنع تكرار إدراج الإشعار نفسه ضمن فترة التهدئة)."""
    return int(time.time() // max(60, cooldown_minutes * 60))


async def _store_error(
    context: ContextTypes.DEFAULT_TYPE, description: str, error: BaseException | None, trace: str
) -> None:
    """حفظ الخطأ في جدول `error_logs` (مع عدم إسقاط البوت إن فشل الحفظ نفسه)."""
    services = context.application.bot_data.get("services")
    if services is None:
        return
    try:
        async with services.db.transaction() as tx:
            await services.repos.error_logs.log(
                tx,
                level="ERROR",
                source="telegram_handler",
                error_type=type(error).__name__,
                message=f"{type(error).__name__}: {error}"[:500],
                traceback_snippet=html.unescape(trace)[:MAX_STORED_ERROR],
                update_summary=description,
            )
    except Exception as storage_error:            # noqa: BLE001 - تسجيل فشل التسجيل نفسه
        logger.error("تعذر حفظ الخطأ في قاعدة البيانات: %s", storage_error)


async def _mark_blocked(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تعليم المستخدم الذي حظر البوت حتى تتوقف محاولات الإرسال إليه."""
    services = context.application.bot_data.get("services")
    if services is None or not isinstance(update, Update):
        return
    telegram_user = update.effective_user
    if telegram_user is None:
        return
    try:
        user = await services.users.get_by_telegram(telegram_user.id)
        if user is not None:
            await services.users.mark_bot_blocked(user.id, True)
    except Exception as exc:                      # noqa: BLE001 - لا نُسقط المعالج العام
        logger.error("تعذر تعليم المستخدم كحاظر للبوت: %s", exc)
```


## الخدمات

### `services/security_service.py`  ·  جديد  ·  383 سطراً

عدّادات وأحداث وطاقم وفحوص الوضع الأمني ورفع الإيقاف المؤقت.

```python
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
    ) -> None:
        """تهيئة الخدمة بالاعتماديات اللازمة."""
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
```

### `services/auth_service.py`  ·  مُحدَّث  ·  368 سطراً

هرمية الإدارة، منع التصعيد، حماية آخر أدمن أعلى، منع التعامل الذاتي.

```python
"""
خدمة الصلاحيات والحماية.

كل إجراء حسّاس يمر من هنا مرتين:
    1. في طبقة الواجهة قبل عرض الزر أو تنفيذه.
    2. داخل الخدمة نفسها قبل تنفيذ العملية (دفاع في العمق).

لا يوجد أي أدمن مكتوب في الكود: الأدوار والصلاحيات كلها في قاعدة البيانات،
و`SUPER_ADMIN_IDS` في ملف البيئة تُستخدم للزرع الأولي والطوارئ فقط.
"""

from __future__ import annotations

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

        if target.role == Role.SUPER_ADMIN and new_role != Role.SUPER_ADMIN:
            other_active = [
                u for u in await self.repos.users.list_by_role(Role.SUPER_ADMIN)
                if not u.is_banned and u.id != target.id
            ]
            if not target.is_banned and not other_active:
                await self._deny(
                    actor,
                    event="last_super_admin_protected",
                    user_message="🚫 هذا آخر أدمن أعلى فعّال — عيّن غيره أولاً قبل تخفيض دوره.",
                    target_id=target.id,
                    details={"new_role": new_role},
                )

        async with self.db.transaction() as tx:
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
```

### `services/user_service.py`  ·  مُحدَّث  ·  289 سطراً

حظر/فك حظر بهرمية وحماية ذاتية وللأعلى.

```python
"""
خدمة المستخدمين: التسجيل التلقائي عند أول استخدام، وتحديث البيانات، والحظر.

ملاحظة: هذه الخدمة لا تلمس الرصيد إطلاقاً — كل ما يتعلق بالمال في `WalletService`.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.enums import NotificationType
from core.exceptions import ValidationError
from core.permissions import Permission
from database.database import Database
from database.models import User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.notification_service import NotificationService
from services.settings_service import SettingsService
from texts import templates
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
    ) -> None:
        """تهيئة الخدمة بالاعتماديات التي تحتاجها."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.audit = audit
        self.auth = auth
        self.notifications = notifications

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
        logger.info("تسجيل مستخدم جديد %s (تيليجرام %s)", created.id, telegram_id)
        return created, True

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
```

### `services/settings_service.py`  ·  مُحدَّث  ·  195 سطراً

`set` يطبّق `SETTING_RULES` ثم يُبلغ المراقبين.

```python
"""
خدمة الإعدادات: قراءة إعدادات النظام من قاعدة البيانات مع ذاكرة مؤقتة قصيرة.

لماذا ذاكرة مؤقتة؟ لأن كل طلب مستخدم يقرأ عدة إعدادات (الصيانة، الحدود، العملة…)،
وقراءتها من القرص في كل مرة إهدار. المدة قصيرة (ثوانٍ) والتعديل من اللوحة يُبطلها فوراً،
فلا يحدث تأخير في ظهور أي تغيير.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from core.setting_rules import check_ordered_pairs, normalize_setting_value
from database.database import Database
from database.models import Setting
from database.repositories import Repositories
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: نوع مراقب الإعدادات: دالة غير متزامنة (المفتاح، القيمة الجديدة)
SettingListener = Callable[[str, str], Awaitable[None]]

#: مدة صلاحية الذاكرة المؤقتة بالثواني
CACHE_TTL_SECONDS: float = 20.0


class SettingsService:
    """واجهة واحدة لقراءة وتعديل إعدادات النظام."""

    def __init__(self, db: Database, repos: Repositories, *, ttl_seconds: float = CACHE_TTL_SECONDS) -> None:
        """تهيئة الخدمة بقاعدة البيانات ومستودعاتها ومدة صلاحية الذاكرة المؤقتة."""
        self.db = db
        self.repos = repos
        self._ttl = ttl_seconds
        self._cache: dict[str, str] = {}
        self._expires_at: float = 0.0
        self._listeners: list[SettingListener] = []

    # ------------------------------ الداخلية ------------------------------ #

    async def _values(self) -> dict[str, str]:
        """إرجاع كل الإعدادات كقاموس، مع إعادة التحميل عند انتهاء صلاحية الذاكرة."""
        now = time.monotonic()
        if now >= self._expires_at or not self._cache:
            self._cache = await self.repos.settings.as_dict()
            self._expires_at = now + self._ttl
        return self._cache

    def invalidate(self) -> None:
        """إبطال الذاكرة المؤقتة فوراً (بعد أي تعديل على الإعدادات)."""
        self._cache = {}
        self._expires_at = 0.0

    # ------------------------------- القراءة ------------------------------ #

    async def get_str(self, key: str, default: str = "") -> str:
        """قراءة إعداد نصي."""
        values = await self._values()
        raw = values.get(key)
        return raw if raw not in (None, "") else default

    async def get_int(self, key: str, default: int = 0) -> int:
        """قراءة إعداد رقمي (يُرجع الافتراضي إذا كانت القيمة تالفة، مع تسجيل تحذير)."""
        values = await self._values()
        raw = values.get(key)
        if raw is None or raw == "":
            return default
        try:
            return int(str(raw).strip())
        except ValueError:
            logger.warning("قيمة الإعداد %s ليست رقماً صحيحاً: %r — استُخدم الافتراضي", key, raw)
            return default

    async def get_bool(self, key: str, default: bool = False) -> bool:
        """قراءة إعداد منطقي (يقبل 1/true/yes/on)."""
        values = await self._values()
        raw = values.get(key)
        if raw is None or raw == "":
            return default
        return str(raw).strip().lower() in {"1", "true", "yes", "on", "نعم"}

    async def get_money_units(self, key: str, default: int = 0) -> int:
        """قراءة إعداد مالي مخزَّن بوحدات صحيحة."""
        return await self.get_int(key, default)

    async def get_json(self, key: str, default: Any = None) -> Any:
        """قراءة إعداد بصيغة JSON."""
        return await self.repos.settings.get_json(key, default)

    async def currency(self) -> tuple[str, str, int]:
        """
        بيانات العملة المعروضة.

        المخرجات: (رمز العملة النصي، الرمز المختصر للعرض، عدد الخانات العشرية).
        """
        code = await self.get_str("currency_code", "YER")
        symbol = await self.get_str("currency_symbol", code)
        decimals = await self.get_int("display_decimals", 2)
        return code, symbol, decimals

    async def money_symbol(self) -> str:
        """رمز العملة المستخدم في نصوص الإشعارات."""
        _, symbol, _ = await self.currency()
        return symbol

    async def is_maintenance(self) -> bool:
        """هل النظام في وضع الصيانة؟"""
        return await self.get_bool("maintenance_mode", False)

    async def maintenance_message(self) -> str:
        """نص رسالة الصيانة المعروضة للمستخدمين."""
        return await self.get_str(
            "maintenance_message", "🚧 النظام في صيانة مؤقتة. نعتذر عن الإزعاج."
        )

    async def registration_enabled(self) -> bool:
        """هل التسجيل مفتوح للمستخدمين الجدد؟"""
        return await self.get_bool("registration_enabled", True)

    async def all_settings(self) -> list[Setting]:
        """كل الإعدادات بتفاصيلها (لعرضها في لوحة الأدمن)."""
        return await self.repos.settings.all()

    async def group(self, group_code: str) -> list[Setting]:
        """إعدادات مجموعة واحدة (عامة، طلبات، مدفوعات…)."""
        return await self.repos.settings.by_group(group_code)

    async def groups(self) -> list[str]:
        """أسماء مجموعات الإعدادات."""
        return await self.repos.settings.groups()

    # ------------------------------- الكتابة ------------------------------ #

    # ------------------------------ المراقبون ----------------------------- #

    def add_listener(self, listener: SettingListener) -> None:
        """
        تسجيل دالة تُستدعى بعد كل تعديل ناجح (مثلاً لإعادة جدولة المهام فوراً).

        المدخلات: دالة غير متزامنة بتوقيع `async def listener(key: str, value: str)`.
        أخطاء المراقب لا تُسقط عملية الحفظ (القيمة حُفظت فعلاً) بل تُسجَّل في اللوق.
        """
        self._listeners.append(listener)

    async def _notify_listeners(self, key: str, value: str) -> None:
        """إبلاغ المراقبين بالتعديل مع عزل أخطائهم عن عملية الحفظ."""
        for listener in self._listeners:
            try:
                await listener(key, value)
            except Exception:                                    # noqa: BLE001
                logger.exception("فشل مراقب الإعدادات بعد تعديل %s", key)

    # ------------------------------- الكتابة ------------------------------ #

    async def set(self, key: str, value: Any, *, admin_id: int | None = None) -> bool:
        """
        تعديل قيمة إعداد قابل للتعديل، مع التحقق من نوعها ونطاقها وتسجيل العملية.

        الترتيب: وجود المفتاح وقابليته للتعديل ← تطبيع القيمة والتحقق ← فحص الأزواج
        المرتبطة ← حفظ + تدقيق في معاملة واحدة ← إبطال الذاكرة ← إبلاغ المراقبين.

        المخرجات: True عند التعديل، False إذا كان الإعداد غير موجود أو محمياً من التعديل.

        الاستثناءات:
            ValidationError : القيمة لا تناسب نوع المفتاح أو خارج النطاق المسموح.
        """
        setting = await self.repos.settings.get(key)
        if setting is None or not setting.is_editable:
            logger.warning("رُفض تعديل الإعداد %s (غير موجود أو غير قابل للتعديل)", key)
            return False

        clean = normalize_setting_value(key, value, setting.value_type)
        check_ordered_pairs(key, clean, await self.repos.settings.as_dict())

        before = setting.value
        async with self.db.transaction() as tx:
            changed = await self.repos.settings.set(tx, key, clean, updated_by=admin_id)
            if changed:
                await self.repos.audit.log(
                    tx,
                    action="settings.update",
                    admin_id=admin_id,
                    target_type="setting",
                    target_id=key,
                    before={"value": before},
                    after={"value": clean},
                )
        if changed:
            self.invalidate()
            logger.info("تم تعديل الإعداد %s بواسطة الأدمن %s", key, admin_id)
            await self._notify_listeners(key, clean)
        return changed
```

### `services/__init__.py`  ·  مُحدَّث  ·  181 سطراً

تجميع 15 خدمة (إضافة `security`).

```python
"""
حزمة الخدمات — طبقة منطق العمل بين الواجهة (المرحلة 3+) وقاعدة البيانات.

لماذا حاوية خدمات؟
    الخدمات مترابطة (الطلبات تحتاج المحفظة والمزودين والإشعارات...). بدل أن تبني كل
    نقطة دخول اعتمادياتها بنفسها — فتتسرب الأخطاء وتتكرر الكائنات — تُبنى هنا مرة
    واحدة بترتيب صحيح، ويُمرَّر كائن `ServiceContainer` واحد إلى بقية النظام.

ترتيب البناء (من الأدنى اعتماداً إلى الأعلى):
    settings → audit → notifications → auth → wallet → users → catalog
    → providers → orders → payments → tickets → stats → templates → broadcasts → security
"""

from __future__ import annotations

from dataclasses import dataclass

from database.database import Database
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.broadcast_service import BroadcastService
from services.catalog_service import CatalogService
from services.notification_service import NotificationService
from services.order_service import OrderService
from services.payment_service import PaymentService
from services.provider_service import ProviderService
from services.security_service import SecurityService
from services.settings_service import SettingsService
from services.stats_service import StatsService
from services.template_service import TemplateService
from services.ticket_service import TicketService
from services.user_service import UserService
from services.wallet_service import WalletService
from utils.logging_setup import get_logger
from utils.security import SecretBox

logger = get_logger(__name__)

__all__ = [
    "AuditService",
    "AuthService",
    "BroadcastService",
    "CatalogService",
    "NotificationService",
    "OrderService",
    "PaymentService",
    "ProviderService",
    "ServiceContainer",
    "SecurityService",
    "SettingsService",
    "StatsService",
    "TemplateService",
    "TicketService",
    "UserService",
    "WalletService",
    "build_services",
]


@dataclass(slots=True)
class ServiceContainer:
    """
    حاوية تضم نسخة واحدة من كل خدمة، جاهزة للتمرير إلى معالجات تيليجرام والمهام.

    الاستخدام:
        services = build_services(db, repos, secret_box=box, super_admin_ids=(123,))
        user, is_new = await services.users.get_or_create(...)
        order = await services.orders.create_order(user, service_id=1, link="...", quantity=100)
    """

    db: Database
    repos: Repositories
    settings: SettingsService
    audit: AuditService
    notifications: NotificationService
    auth: AuthService
    wallet: WalletService
    users: UserService
    catalog: CatalogService
    providers: ProviderService
    orders: OrderService
    payments: PaymentService
    tickets: TicketService
    stats: StatsService
    templates: TemplateService
    broadcasts: BroadcastService
    security: SecurityService

    def invalidate_caches(self) -> None:
        """
        إبطال الذاكرة المؤقتة للإعدادات بعد أي تعديل خارجي عليها.

        ملاحظة: عملاء المزودين تُفتح وتُغلق داخل كل عملية (`client.close()` في finally)،
        فلا توجد جلسات شبكة معلّقة تحتاج إغلاقاً عند إيقاف البوت.
        """
        self.settings.invalidate()

    async def startup_recovery(self) -> dict[str, int]:
        """
        إجراءات الاسترداد التي تُنفَّذ مرة واحدة عند إقلاع البوت.

        تشمل: تحرير الأقفال المنتهية ونقل الطلبات العالقة في الإرسال إلى «غير مؤكد».

        المخرجات: عدّادات ما تم استرداده.
        """
        report = await self.orders.recover_after_restart()
        # المرحلة 8: تحميل قوالب الإشعارات المخصّصة قبل إرسال أول رسالة،
        # وإلا خرجت أول الإشعارات بالنص الافتراضي رغم تعديل الأدمن له.
        report["templates_loaded"] = await self.templates.refresh_cache()
        logger.info("استرداد الإقلاع: %s", report)
        return report


def build_services(
    db: Database,
    repos: Repositories | None = None,
    *,
    secret_box: SecretBox,
    super_admin_ids: tuple[int, ...] = (),
    settings_ttl_seconds: float | None = None,
) -> ServiceContainer:
    """
    بناء كل الخدمات وربط اعتمادياتها بالترتيب الصحيح.

    المدخلات:
        db                   : اتصال قاعدة البيانات (مفتوح مسبقاً).
        repos                : المستودعات (تُبنى تلقائياً إن لم تُمرَّر).
        secret_box           : صندوق التشفير لمفاتيح المزودين (إجباري — لا مفاتيح واضحة).
        super_admin_ids      : معرفات الأدمن الأعلى من ملف البيئة (مسار طوارئ فقط).
        settings_ttl_seconds : مدة صلاحية كاش الإعدادات (يُستخدم 0 في الاختبارات لإلغاء الكاش).

    المخرجات: حاوية الخدمات الجاهزة للاستخدام.
    """
    repositories = repos if repos is not None else Repositories(db)

    settings = (
        SettingsService(db, repositories, ttl_seconds=settings_ttl_seconds)
        if settings_ttl_seconds is not None
        else SettingsService(db, repositories)
    )
    audit = AuditService(db, repositories)
    notifications = NotificationService(db, repositories, settings)
    auth = AuthService(db, repositories, settings, audit, super_admin_ids=super_admin_ids)
    wallet = WalletService(db, repositories, settings=settings, auth=auth)
    users = UserService(db, repositories, settings, audit, auth, notifications)
    catalog = CatalogService(db, repositories, settings, audit, auth)
    providers = ProviderService(
        db, repositories, settings, audit, auth, notifications, secret_box
    )
    orders = OrderService(
        db, repositories, settings, wallet, catalog, providers, notifications, audit, auth
    )
    payments = PaymentService(db, repositories, settings, wallet, notifications, audit, auth)
    tickets = TicketService(db, repositories, settings, notifications, audit, auth)
    stats = StatsService(db, repositories, settings, auth, providers)
    template_service = TemplateService(db, repositories, auth, audit)
    broadcasts = BroadcastService(db, repositories, auth, audit, notifications, settings)

    security = SecurityService(db, repositories, settings, auth, audit)

    logger.info("تم بناء طبقة الخدمات (%s خدمة)", 15)
    return ServiceContainer(
        db=db,
        repos=repositories,
        settings=settings,
        audit=audit,
        notifications=notifications,
        auth=auth,
        wallet=wallet,
        users=users,
        catalog=catalog,
        providers=providers,
        orders=orders,
        payments=payments,
        tickets=tickets,
        stats=stats,
        templates=template_service,
        broadcasts=broadcasts,
        security=security,
    )
```

### `services/wallet_service.py`  ·  مُحدَّث (مقتطف)  ·  443 سطراً

سقوف التسوية اليدوية ومنع التسوية الذاتية.

```python
    async def _enforce_adjust_caps(self, tx: Tx, admin: User, amount_units: int) -> None:
        """
        فرض سقف العملية الواحدة والسقف اليومي على تسويات غير الأدمن الأعلى.

        يُستدعى **داخل** معاملة الكتابة (القراءة والإدراج ذرّيان فلا يتجاوز طلبان
        متزامنان السقف). الأدمن الأعلى مستثنى لكن عملياته مُدقَّقة دائماً.
        صفر في أي سقف = بلا سقف.

        الاستثناءات: _AdjustCapExceeded (تُحوَّل لاحقاً خارج المعاملة).
        """
        if self.settings is None or admin.role == "super_admin":
            return
        per_operation = await self.settings.get_money_units("admin_adjust_max_units", 0)
        if per_operation > 0 and amount_units > per_operation:
            raise _AdjustCapExceeded(
                "adjust_cap_exceeded",
                "🚫 المبلغ يتجاوز سقف التسوية اليدوية المسموح لحسابك. اطلب من الأدمن الأعلى تنفيذها.",
                {"amount_units": amount_units, "cap_units": per_operation, "scope": "operation"},
            )
        daily = await self.settings.get_money_units("admin_adjust_daily_max_units", 0)
        if daily > 0:
            start_today, _ = day_bounds_utc(0)
            used = await self.repos.transactions.sum_manual_by_actor(tx, admin.id, start_today)
            if used + amount_units > daily:
                raise _AdjustCapExceeded(
                    "adjust_daily_cap_exceeded",
                    "🚫 تجاوزت السقف اليومي للتسويات اليدوية. اطلب من الأدمن الأعلى أو انتظر الغد.",
                    {"amount_units": amount_units, "used_today_units": used, "cap_units": daily, "scope": "daily"},
                )

    # ... (باقي الملف دون تغيير) ...

    async def adjust_balance(
        self, *, target: User, amount_units: int, admin: User, reason: str, credit: bool, token: str | None = None
    ) -> Transaction:
        """
        واجهة عالية المستوى للوحة الأدمن: تفتح معاملتها بنفسها وتُرجع الحركة.

        حواجز المرحلة 9: لا تسوية على حساب المنفِّذ نفسه، وسقف للعملية الواحدة
        ولليوم لغير الأدمن الأعلى (تُسجَّل محاولات التجاوز كأحداث أمنية).

        الاستثناءات: InvalidAmountError · InsufficientBalanceError · DuplicateOperationError
                     · PermissionDeniedError (إجراء ذاتي)
        """
        self._validate_amount(amount_units)
        if self.auth is not None:
            await self.auth.ensure_not_self_dealing(
                admin, target.id, what="تعديل رصيدك", context="wallet.adjust"
            )
        try:
            async with self.db.transaction() as tx:
                await self._enforce_adjust_caps(tx, admin, amount_units)
                if credit:
                    transaction = await self.manual_credit(
                        tx, user_id=target.id, amount_units=amount_units,
                        admin_id=admin.id, reason=reason, token=token,
                    )
                else:
                    transaction = await self.manual_debit(
                        tx, user_id=target.id, amount_units=amount_units,
                        admin_id=admin.id, reason=reason, token=token,
                    )
                await self.repos.audit.log(
                    tx,
                    action="users.balance.credit" if credit else "users.balance.debit",
                    admin_id=admin.id,
                    target_type="user",
                    target_id=target.id,
                    before={"balance_units": transaction.balance_before_units},
                    after={"balance_units": transaction.balance_after_units},
                    details={"reason": reason, "amount_units": amount_units},
                )
        except _AdjustCapExceeded as exc:
            # التسجيل خارج المعاملة الملغاة حتى لا يضيع الأثر مع التراجع
            if self.auth is not None:
                await self.auth.audit.log_security_event(
                    event=exc.event,
                    user_id=admin.id,
                    target_type="user",
                    target_id=target.id,
                    details=exc.details,
                )
            raise InvalidAmountError(
                f"{exc.event}: {exc.details}", user_message=exc.user_message
            ) from exc
        return transaction
```

### `services/payment_service.py`  ·  مُحدَّث (مقتطف)  ·  1043 سطراً

منع اعتماد الشحن الذاتي ومنع over-credit.

```python
    async def approve(
        self,
        actor: User,
        payment_id: int,
        *,
        credited_units: int | None = None,
        admin_note: str | None = None,
    ) -> Transaction:
        """
        اعتماد طلب شحن وإضافة الرصيد للمستخدم.

        المدخلات:
            credited_units : المبلغ المعتمد فعلياً إن اختلف عن الافتراضي (تحويل ناقص مثلاً).
                             الافتراضي = المبلغ المحوَّل − رسوم الطريقة المسجّلة على الطلب.

        المخرجات: الحركة المالية التي أُنشئت.

        الاستثناءات:
            PermissionDeniedError       : لا يملك صلاحية `payments.approve`.
            PaymentError                : الطلب غير موجود.
            InvalidStateTransitionError : الطلب ليس بانتظار المراجعة.
            DuplicateOperationError     : عالجه أدمن آخر قبل لحظات.
            InvalidAmountError          : مبلغ اعتماد غير صالح.
        """
        await self.auth.require_permission(
            actor, Permission.PAYMENTS_APPROVE, context=f"payment:{payment_id}"
        )
        payment = await self._load_pending(payment_id, PaymentStatus.APPROVED)
        # عينان على كل عملية مالية: لا يعتمد الأدمن شحنته هو
        await self.auth.ensure_not_self_dealing(
            actor, payment.user_id, what="اعتماد طلب شحن يخصّك", context=f"payment:{payment_id}"
        )

        # الافتراضي هو الصافي بعد رسوم الطريقة المحفوظة على الطلب نفسه
        default_units = payment.net_units
        amount_units = int(credited_units) if credited_units is not None else default_units
        if amount_units <= 0:
            raise ValidationError(
                f"مبلغ اعتماد غير صالح: {amount_units}",
                user_message="❌ المبلغ المعتمد يجب أن يكون أكبر من صفر.",
            )
        if amount_units > payment.amount_units:
            # لا يُضاف للمحفظة أكثر مما حوّله العميل فعلاً (الرسوم تُخصم ولا تُضاف)
            await self.audit.log_security_event(
                event="over_credit_blocked",
                user_id=actor.id,
                target_type="payment",
                target_id=payment_id,
                details={"requested_units": amount_units, "paid_units": payment.amount_units},
            )
            raise ValidationError(
                f"مبلغ الاعتماد {amount_units} يتجاوز المحوَّل {payment.amount_units}",
                user_message="❌ لا يمكن اعتماد مبلغ أكبر من المبلغ الذي حوّله العميل.",
            )
        note = sanitize(admin_note)[:300] if admin_note else None
        if payment.fee_units:
            fee_note = f"رسوم الطريقة {payment.fee_units} على مبلغ {payment.amount_units}"
            note = f"{note} | {fee_note}" if note else fee_note
        if amount_units != default_units:
            diff_note = f"اعتُمد {amount_units} بدل {default_units}"
            note = f"{note} | {diff_note}" if note else diff_note

        symbol = await self.settings.money_symbol()
        async with self.db.transaction() as tx:
            changed = await self.repos.payments.set_status(
                tx,
                payment_id,
                new_status=PaymentStatus.APPROVED,
                expected_status=PaymentStatus.PENDING,
                admin_id=actor.id,
                credited_units=amount_units,
                admin_note=note,
            )
            if not changed:
                raise DuplicateOperationError(
                    f"طلب الشحن {payment_id} عولج مسبقاً",
                    user_message="⚠️ هذا الطلب تمت معالجته بالفعل (ربما من أدمن آخر).",
                )

            transaction = await self.wallet.credit_from_payment(
                tx,
                user_id=payment.user_id,
                payment_id=payment.id,
                amount_units=amount_units,
                actor_id=actor.id,
            )

            await self.audit.log(
                tx,
                action="payments.approve",
                admin_id=actor.id,
                target_type="payment",
                target_id=payment_id,
                before={
                    "status": payment.status,
                    "amount_units": payment.amount_units,
                    "fee_units": payment.fee_units,
                },
                after={"status": PaymentStatus.APPROVED, "credited_units": amount_units},
                details={"note": note},
            )

            title, message = templates.payment_approved(
                payment_id=payment.id,
                credited_units=amount_units,
                new_balance_units=transaction.balance_after_units,
                symbol=symbol,
            )
            await self.notifications.notify_payment(
                tx,
                user_id=payment.user_id,
                payment_id=payment.id,
                event=NotificationType.PAYMENT_APPROVED,
                title=title,
                message=message,
            )

        logger.info(
            "اعتمد الأدمن %s طلب الشحن #%s للمستخدم %s بمبلغ %s",
            actor.id, payment_id, payment.user_id, amount_units,
        )
        return transaction
```

### `services/order_service.py`  ·  مُحدَّث (مقتطف)  ·  1447 سطراً

منع الإجراء الذاتي في الإلغاء/الفشل/تجاوز الحالة.

```python
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

        refunded = await self._apply_canceled(
            order, reason=reason, actor_type=ActorType.ADMIN, actor_id=actor.id
        )
        await self.audit.log_standalone(
            action="orders.cancel",
            admin_id=actor.id,
            target_type="order",
            target_id=order_id,
            details={"reason": reason, "refunded_units": refunded},
            source="telegram",
        )
        return refunded

    # ... (باقي الملف دون تغيير) ...

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

        refunded = await self._fail_order(
            order,
            reason=reason,
            actor_type=ActorType.ADMIN,
            actor_id=actor.id,
            notify_admins=False,
            auto_refund=True,  # قرار أدمن صريح: المال يعود فوراً
        )
        await self.audit.log_standalone(
            action="orders.refund",
            admin_id=actor.id,
            target_type="order",
            target_id=order_id,
            details={"reason": reason, "refunded_units": refunded},
            source="telegram",
        )
        return refunded
```

### `services/provider_service.py`  ·  مُحدَّث (مقتطف)  ·  526 سطراً

فحص الرابط العام عند إنشاء المزود.

```python
    async def create_provider(
        self,
        actor: User,
        *,
        name: str,
        api_url: str,
        api_key: str,
        api_type: str = "perfect_panel",
        currency: str = "USD",
        timeout_seconds: int = 30,
    ) -> Provider:
        """
        إضافة مزود جديد مع تشفير مفتاحه قبل التخزين.

        الاستثناءات: PermissionDeniedError · ValidationError · EncryptionError
        """
        await self.auth.require_permission(actor, Permission.PROVIDERS_CREATE, context="provider.create")
        clean_name = clean_text(name, field="اسم المزود", max_length=60, min_length=2)
        clean_gateway = validate_public_https_url(api_url)   # https + مضيف عام (منع SSRF)
        key = (api_key or "").strip()
        if len(key) < 8:
            raise ProviderError(
                "مفتاح API قصير جداً", user_message="❌ مفتاح API غير صالح."
            )

        async with self.db.transaction() as tx:
            provider = await self.repos.providers.create(
                tx,
                name=clean_name,
                api_url=clean_gateway,
                api_key_enc=self.secret_box.encrypt(key),
                api_key_hint=secret_hint(key),
                api_type=api_type,
                currency=currency,
                timeout_seconds=timeout_seconds,
            )
            await self.audit.log(
                tx,
                action="providers.create",
                admin_id=actor.id,
                target_type="provider",
                target_id=provider.id,
                after={"name": clean_name, "api_url": clean_gateway, "api_type": api_type},
            )
        logger.info("أضاف الأدمن %s المزود %s (%s)", actor.id, provider.id, clean_name)
        return provider
```

### `integrations/providers/perfect_panel.py`  ·  مُحدَّث (مقتطف)  ·  453 سطراً

فحص DNS وقت الإرسال ورفض التحويلات 3xx.

```python
    async def _post(self, payload: dict[str, Any], *, uncertain_on_timeout: bool = False) -> Any:
        """
        تنفيذ طلب POST واحد وإرجاع JSON المفكوك.

        المدخلات:
            payload               : حقول النموذج بلا المفتاح (يُضاف هنا).
            uncertain_on_timeout  : True عند إنشاء الطلب فقط — فالمهلة حينها تعني
                                    «لا نعرف هل وصل الطلب» لا «أعد المحاولة».

        الاستثناءات:
            ProviderUncertainError : مهلة أثناء إنشاء طلب.
            ProviderTemporaryError : مشكلة شبكة أو استجابة 429/5xx أو JSON غير صالح.
            ProviderPermanentError : استجابة 4xx صريحة (عدا 429).
        """
        data = {"key": self._api_key, **payload}
        action = str(payload.get("action", "?"))
        if self._owns_client:
            # حماية SSRF: لا نرسل المفتاح إلى نطاق يشير لعنوان داخلي (لا يُفحص عند حقن عميل اختبار)
            await ensure_public_host(self.api_url)
        try:
            response = await self._http().post(self.api_url, data=data)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            # التفريق هنا هو الفرق بين إعادة محاولة آمنة وبين طلب مكرر يكلّف مالاً
            if uncertain_on_timeout:
                raise ProviderUncertainError(
                    f"انقطع الاتصال أثناء إرسال الطلب ({type(exc).__name__})"
                ) from exc
            raise ProviderTemporaryError(
                f"تعذر الاتصال بالمزود أثناء {action} ({type(exc).__name__})"
            ) from exc
        except httpx.HTTPError as exc:                     # أي خطأ httpx آخر غير متوقع
            raise ProviderTemporaryError(
                f"خطأ اتصال غير متوقع أثناء {action}: {type(exc).__name__}"
            ) from exc

        self._raise_for_status(response, action, uncertain_on_timeout=uncertain_on_timeout)

        try:
            return response.json()
        except ValueError as exc:
            snippet = response.text[:ERROR_SNIPPET_LIMIT]
            if uncertain_on_timeout:
                raise ProviderUncertainError(
                    f"استجابة غير مفهومة بعد إرسال الطلب: {snippet}"
                ) from exc
            raise ProviderTemporaryError(
                f"استجابة المزود ليست JSON أثناء {action}: {snippet}"
            ) from exc
```


## المهام الدورية والواجهة

### `jobs/runner.py`  ·  مُحدَّث  ·  298 سطراً

`schedule_jobs` و`reschedule_for_setting` (إعادة جدولة حيّة تحفظ العدّادات).

```python
"""
طبقة الإشراف على المهام الدورية (المرحلة 6).

لماذا طبقة إشراف بدل تمرير الدوال مباشرة إلى JobQueue؟
    لأن مهمة دورية بلا إشراف ثلاثة أخطار:
        1. **التداخل**: جولة لم تنتهِ وجولة جديدة تبدأ فوقها ⇒ ضغط مضاعف على
           المزود وعلى قاعدة البيانات، وفي أسوأ الحالات عمل مكرر.
        2. **التعليق**: استدعاء شبكة لا ينتهي يُجمّد المهمة إلى الأبد بصمت.
        3. **الصمت**: استثناء داخل المهمة يُطبع في اللوق فقط، فيتوقف النظام عن
           العمل أياماً دون أن يعرف أحد.

هذا الملف يعالج الثلاثة: قفل لكل مهمة يمنع التداخل، مهلة قصوى لكل جولة،
والتقاط كل استثناء وكتابته في `error_logs` مع تنبيه الأدمن بعد تكرار الفشل.
ويحتفظ بسجل حالة في الذاكرة (آخر تشغيل، المدة، النتيجة) تعرضه شاشة
«⏱ المهام الدورية» في لوحة التحكم.

لماذا السجل في الذاكرة لا في قاعدة البيانات؟
    لأنه بيانات تشغيل لحظية تُفقد عمداً عند إعادة التشغيل، وكتابتها كل بضع
    ثوانٍ تعني آلاف عمليات الكتابة يومياً بلا قيمة تاريخية. الأخطاء — وهي ما
    يستحق البقاء — تُكتب في `error_logs` فعلاً.
"""

from __future__ import annotations

import asyncio
import time
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from telegram.ext import ContextTypes

from core.permissions import Permission
from texts import templates
from utils.datetime_utils import utc_now_iso
from utils.logging_setup import get_logger
from utils.security import sanitize

logger = get_logger(__name__)

#: نوع دالة المهمة كما تتوقعها JobQueue
JobCallback = Callable[[ContextTypes.DEFAULT_TYPE], Awaitable[None]]

#: المهلة القصوى الافتراضية لجولة واحدة (ثوانٍ) — بعدها تُلغى الجولة وتُسجَّل
DEFAULT_TIMEOUT_SECONDS = 300.0

#: عدد الإخفاقات المتتالية الافتراضي قبل تنبيه الأدمن
DEFAULT_FAILURE_ALERT_THRESHOLD = 3


@dataclass(slots=True)
class JobStats:
    """حالة مهمة دورية واحدة كما تُعرض في شاشة المهام."""

    name: str
    interval_seconds: float
    schedule_text: str = ""
    runs: int = 0
    failures: int = 0
    skipped: int = 0
    consecutive_failures: int = 0
    running: bool = False
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_success_at: str | None = None
    last_duration_ms: int | None = None
    total_duration_ms: int = 0
    last_error: str | None = None

    @property
    def average_duration_ms(self) -> int:
        """متوسط زمن الجولة بالميلي ثانية (صفر قبل أول تشغيل)."""
        completed = self.runs
        return int(self.total_duration_ms / completed) if completed else 0

    @property
    def is_healthy(self) -> bool:
        """المهمة سليمة إذا لم تفشل في آخر جولة لها."""
        return self.consecutive_failures == 0

    def as_dict(self) -> dict[str, object]:
        """تمثيل مختصر للاختبارات واللوقات."""
        return {
            "name": self.name,
            "runs": self.runs,
            "failures": self.failures,
            "skipped": self.skipped,
            "consecutive_failures": self.consecutive_failures,
            "last_duration_ms": self.last_duration_ms,
            "last_error": self.last_error,
        }


@dataclass(slots=True)
class JobRegistry:
    """
    سجل المهام المُشرَف عليها: الحالة + القفل + الدالة الملفوفة.

    يُستخدم من شاشة «⏱ المهام الدورية» للعرض ومن زر «تشغيل الآن» للتنفيذ.
    """

    stats: dict[str, JobStats] = field(default_factory=dict)
    callbacks: dict[str, JobCallback] = field(default_factory=dict)
    locks: dict[str, asyncio.Lock] = field(default_factory=dict)

    def register(
        self,
        name: str,
        *,
        interval_seconds: float,
        schedule_text: str = "",
        keep_history: bool = False,
    ) -> JobStats:
        """
        تسجيل مهمة جديدة (أو إعادة ضبط تسجيلها عند إعادة الجدولة).

        `keep_history=True` يُستخدم عند تغيير الإيقاع أثناء التشغيل: نُبقي عدّادات
        المهمة (التشغيلات/الإخفاقات) وقفلها كما هي ونحدّث الفترة والوصف فقط، فلا
        يضيع السجل ولا يتسلل تداخل جولة قديمة مع الجديدة.
        """
        existing = self.stats.get(name)
        if keep_history and existing is not None:
            existing.interval_seconds = interval_seconds
            existing.schedule_text = schedule_text
            return existing
        entry = JobStats(
            name=name, interval_seconds=interval_seconds, schedule_text=schedule_text
        )
        self.stats[name] = entry
        self.locks[name] = asyncio.Lock()
        return entry

    def get(self, name: str) -> JobStats | None:
        """حالة مهمة بالاسم (أو None إن لم تُجدول)."""
        return self.stats.get(name)

    def callback(self, name: str) -> JobCallback | None:
        """الدالة الملفوفة لمهمة بالاسم — يستخدمها زر «تشغيل الآن»."""
        return self.callbacks.get(name)

    def snapshot(self) -> list[JobStats]:
        """كل المهام بترتيب تسجيلها (للعرض في اللوحة)."""
        return list(self.stats.values())

    def clear(self) -> None:
        """تفريغ السجل (يُستخدم عند إعادة الجدولة وفي الاختبارات)."""
        self.stats.clear()
        self.callbacks.clear()
        self.locks.clear()


#: السجل الافتراضي الذي تستعمله الجدولة الحقيقية وشاشة اللوحة
JOB_REGISTRY = JobRegistry()


async def _record_failure(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    name: str,
    stats: JobStats,
    error: BaseException,
    threshold: int,
) -> None:
    """
    تسجيل فشل جولة: سطر في `error_logs` + تنبيه الأدمن عند تكرار الفشل.

    لا يرفع هذا التسجيل أي استثناء جديد: فشلُ تسجيلِ الفشل يجب ألا يُسقط
    المهمة الدورية نفسها، فنكتفي بتسجيله في اللوق.
    """
    services = context.application.bot_data.get("services")
    if services is None:
        logger.error("المهمة %s فشلت ولا توجد خدمات في bot_data لتسجيل الخطأ", name)
        return

    message = f"فشل المهمة الدورية {name}: {error}"
    try:
        async with services.db.transaction() as tx:
            await services.repos.error_logs.log(
                tx,
                message=message,
                level="ERROR",
                source=f"job:{name}",
                error_type=type(error).__name__,
                traceback_snippet="".join(
                    traceback.format_exception(type(error), error, error.__traceback__)
                ),
            )
    except Exception as exc:                                        # noqa: BLE001
        logger.error("تعذّر كتابة خطأ المهمة %s في error_logs: %s", name, exc)

    if stats.consecutive_failures < threshold:
        return

    try:
        title, body = templates.admin_job_failing(
            job_name=name,
            failures=stats.consecutive_failures,
            error=sanitize(str(error))[:200],
        )
        async with services.db.transaction() as tx:
            await services.notifications.notify_admins(
                tx,
                permission=Permission.LOGS_VIEW,
                token=f"job:{name}:fail:{stats.consecutive_failures}",
                title=title,
                message=body,
            )
    except Exception as exc:                                        # noqa: BLE001
        logger.error("تعذّر تنبيه الأدمن بفشل المهمة %s: %s", name, exc)


def supervise(
    callback: JobCallback,
    *,
    name: str,
    registry: JobRegistry = JOB_REGISTRY,
    interval_seconds: float = 0.0,
    schedule_text: str = "",
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    failure_alert_threshold: int = DEFAULT_FAILURE_ALERT_THRESHOLD,
    keep_history: bool = False,
) -> JobCallback:
    """
    لفّ دالة مهمة دورية بحماية كاملة وتسجيلها في السجل.

    المدخلات:
        callback                : دالة المهمة الأصلية.
        name                    : اسم المهمة (يظهر في اللوحة واللوقات).
        registry                : سجل الحالة (قابل للحقن في الاختبارات).
        interval_seconds        : فترة التكرار — للعرض فقط.
        schedule_text           : وصف عربي مختصر للجدولة (مثل «كل دقيقتين»).
        timeout_seconds         : مهلة الجولة الواحدة.
        failure_alert_threshold : عدد الإخفاقات المتتالية قبل تنبيه الأدمن.
        keep_history            : إبقاء عدّادات المهمة وقفلها عند إعادة الجدولة الحيّة.

    المخرجات: دالة جاهزة لـ`JobQueue` **لا ترفع استثناءً أبداً**.
    """
    stats = registry.register(
        name,
        interval_seconds=interval_seconds,
        schedule_text=schedule_text,
        keep_history=keep_history,
    )
    lock = registry.locks[name]

    async def runner(context: ContextTypes.DEFAULT_TYPE) -> None:
        """جولة واحدة محروسة: منع التداخل، مهلة قصوى، التقاط كل خطأ."""
        if lock.locked():
            stats.skipped += 1
            logger.warning(
                "تخطّي جولة %s: الجولة السابقة ما زالت تعمل (تخطّيات: %s)",
                name,
                stats.skipped,
            )
            return

        async with lock:
            stats.running = True
            stats.last_started_at = utc_now_iso()
            started = time.monotonic()
            try:
                await asyncio.wait_for(callback(context), timeout=timeout_seconds)
            except asyncio.CancelledError:
                # إيقاف البوت يُلغي المهام — ليس فشلاً، ويجب ألا يُبتلع
                stats.running = False
                logger.info("أُلغيت جولة %s أثناء الإغلاق", name)
                raise
            except Exception as exc:                                # noqa: BLE001
                stats.failures += 1
                stats.consecutive_failures += 1
                stats.last_error = sanitize(str(exc))[:300] or type(exc).__name__
                logger.exception("فشل المهمة الدورية %s", name)
                await _record_failure(
                    context,
                    name=name,
                    stats=stats,
                    error=exc,
                    threshold=failure_alert_threshold,
                )
            else:
                stats.consecutive_failures = 0
                stats.last_error = None
                stats.last_success_at = utc_now_iso()
            finally:
                duration_ms = int((time.monotonic() - started) * 1000)
                stats.runs += 1
                stats.last_duration_ms = duration_ms
                stats.total_duration_ms += duration_ms
                stats.last_finished_at = utc_now_iso()
                stats.running = False
                if duration_ms > timeout_seconds * 500:             # نصف المهلة
                    logger.warning(
                        "جولة %s استغرقت %sms — قريبة من المهلة القصوى", name, duration_ms
                    )

    runner.__name__ = f"supervised_{name}"
    registry.callbacks[name] = runner
    return runner
```

### `handlers/admin/security.py`  ·  جديد  ·  257 سطراً

شاشة «🛡️ الأمان»: ملخص، أحداث، إيقافات، طاقم (بيانات حقيقية).

```python
"""
قسم «🛡️ الأمان» في لوحة التحكم (المرحلة 9).

الشاشات:
    sc:home         : عدّادات آخر 24 ساعة + قائمة فحوص وضع الأمان.
    sc:events:<p>   : الأحداث الأمنية من سجل التدقيق (صفحات).
    sc:blocks       : الموقوفون مؤقتاً بسبب الضغط الزائد + رفع الإيقاف.
    sc:unblock:<id> : رفع إيقاف مستخدم (يتطلب `security.manage`).
    sc:team         : طاقم الإدارة وأدوارهم واستثناءاتهم.

قواعد ملزمة:
    • كل شاشة تفحص صلاحية `security.view` على الـcallback، ورفع الإيقاف يتطلب
      `security.manage` — والخدمة تعيد الفحص داخلها (دفاع مزدوج).
    • الشاشات للقراءة ما عدا رفع الإيقاف، وهو يُدقَّق كحدث أمني.
    • لا تُعرض أي أسرار: فقط «مضبوط/غير مضبوط» وحالة الصلاحيات.
"""

from __future__ import annotations

import json

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from core.permissions import Permission
from database.models import AuditLog
from handlers.admin.common import admin_required, args, permissions_of
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render
from keyboards.admin_kb import (
    security_blocks_kb,
    security_events_kb,
    security_home_kb,
    security_team_kb,
)
from keyboards.callback_data import NS_ADM_SEC, pattern
from middlewares.context import require_user, services_of
from services.security_service import (
    LEVEL_BAD,
    LEVEL_WARN,
    EnvPosture,
    SecurityService,
)
from texts import admin_ar as t
from utils.formatters import datetime_text, safe
from utils.fs_security import check_paths
from utils.logging_setup import get_logger

logger = get_logger(__name__)


def _env_posture(context: ContextTypes.DEFAULT_TYPE) -> EnvPosture:
    """
    بناء لقطة البيئة من إعدادات التشغيل المخزّنة في `bot_data` (بلا أي قيمة سرّية).

    إن لم تتوفر الإعدادات (كما في بعض الاختبارات) نُرجع لقطة افتراضية بلا فحص ملفات.
    """
    config = context.application.bot_data.get("config")
    if config is None:
        return EnvPosture()
    return EnvPosture(
        bot_token_set=bool(config.bot_token),
        encryption_key_set=bool(config.encryption_key),
        alert_chat_set=config.admin_alert_chat_id is not None,
        path_checks=tuple(check_paths(config.sensitive_paths(), fix=False)),
    )


def _event_label(action: str) -> str:
    """اسم عربي للحدث الأمني (يُزال بادئة `security.`)."""
    code = action.removeprefix("security.")
    return t.SECURITY_EVENT_LABELS.get(code, code)


def _event_target(entry: AuditLog) -> str:
    """وصف مختصر لهدف الحدث (نوع:معرّف أو ملخص التفاصيل)."""
    if entry.target_type:
        return safe(f"{entry.target_type}:{entry.target_id}", limit=28)
    if entry.details_json:
        try:
            details = json.loads(entry.details_json)
        except ValueError:
            return safe(entry.details_json, limit=28)
        if isinstance(details, dict) and details.get("permission"):
            return safe(str(details["permission"]), limit=28)
    return "—"


@guarded
@admin_required(Permission.SECURITY_VIEW)
async def home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الشاشة الرئيسية: العدّادات وفحوص وضع الأمان."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    counters = await services.security.counters(admin)
    checks = await services.security.posture(admin, _env_posture(context))

    bad = sum(1 for check in checks if check.level == LEVEL_BAD)
    warn = sum(1 for check in checks if check.level == LEVEL_WARN)
    summary = t.SECURITY_SUMMARY_ISSUES.format(bad=bad, warn=warn) if bad or warn else t.SECURITY_SUMMARY_OK

    top = ""
    if counters.top_denied:
        names: list[str] = []
        for user_id, count in counters.top_denied:
            user = await services.users.get(user_id)
            names.append(f"{safe(user.display_name if user else str(user_id), limit=20)} ({count})")
        top = t.SECURITY_TOP_DENIED.format(items="، ".join(names))

    lines = "\n".join(
        t.SECURITY_CHECK_LINE.format(
            icon=t.SECURITY_LEVEL_ICONS.get(check.level, "•"),
            title=safe(check.title),
            detail=safe(check.detail),
        )
        for check in checks
    )
    await render(
        update,
        context,
        t.SECURITY_HOME.format(
            denied=counters.permission_denied,
            blocks=counters.rate_limit_blocks,
            rbac=counters.rbac_blocks,
            money=counters.money_blocks,
            total=counters.total_events,
            top_denied=top,
            summary=summary,
            checks=lines,
        ),
        security_home_kb(),
    )


@guarded
@admin_required(Permission.SECURITY_VIEW)
async def events_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """صفحة من الأحداث الأمنية (الأحدث أولاً)."""
    await answer_callback(update)
    services = services_of(context)
    result = await services.security.events(require_user(context), page=args(update).int_arg(0, 1))
    if not result.items:
        await render(update, context, t.SECURITY_EVENTS_EMPTY, security_events_kb(page=1, total_pages=1))
        return
    lines = "\n\n".join(
        t.SECURITY_EVENT_LINE.format(
            label=safe(_event_label(entry.action), limit=45),
            who=safe(result.names.get(entry.admin_id or 0, "النظام"), limit=22),
            target=_event_target(entry),
            when=datetime_text(entry.created_at),
        )
        for entry in result.items
    )
    await render(
        update,
        context,
        t.SECURITY_EVENTS_TITLE.format(page=result.page, pages=result.total_pages, lines=lines),
        security_events_kb(page=result.page, total_pages=result.total_pages),
    )


async def _show_blocks(update: Update, context: ContextTypes.DEFAULT_TYPE, *, notice: str = "") -> None:
    """عرض شاشة الموقوفين (مشتركة بين فتحها ورفع الإيقاف)."""
    services = services_of(context)
    guard = context.application.bot_data.get("abuse_guard")
    blocked = await services.security.blocked_users(require_user(context), guard)
    perms = await permissions_of(context)
    if not blocked:
        await render(update, context, notice + t.SECURITY_BLOCKS_EMPTY, security_blocks_kb([], perms))
        return
    lines = "\n".join(
        t.SECURITY_BLOCK_LINE.format(
            name=safe(item.name, limit=25),
            telegram_id=item.telegram_id,
            left=SecurityService.seconds_text(item.seconds_left),
            strikes=item.strikes,
        )
        for item in blocked
    )
    await render(
        update,
        context,
        notice + t.SECURITY_BLOCKS_TITLE.format(lines=lines),
        security_blocks_kb([(item.telegram_id, item.name) for item in blocked], perms),
    )


@guarded
@admin_required(Permission.SECURITY_VIEW)
async def blocks_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة الموقوفين مؤقتاً الآن."""
    await answer_callback(update)
    await _show_blocks(update, context)


@guarded
@admin_required(Permission.SECURITY_MANAGE)
async def unblock_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """رفع إيقاف مؤقت عن مستخدم محدد (يُدقَّق كحدث أمني)."""
    await answer_callback(update)
    services = services_of(context)
    telegram_id = args(update).int_arg(0, 0)
    guard = context.application.bot_data.get("abuse_guard")
    user = await services.users.get_by_telegram(telegram_id) if telegram_id else None
    cleared = await services.security.clear_block(require_user(context), telegram_id, guard)
    name = safe(user.display_name if user else str(telegram_id), limit=25)
    notice = (
        t.SECURITY_UNBLOCKED.format(name=name) if cleared else t.SECURITY_UNBLOCK_NOT_BLOCKED
    ) + "\n\n"
    await _show_blocks(update, context, notice=notice)


@guarded
@admin_required(Permission.SECURITY_VIEW)
async def team_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """طاقم الإدارة مرتباً بالدور."""
    await answer_callback(update)
    services = services_of(context)
    members = await services.security.team(require_user(context))
    if not members:
        await render(update, context, t.SECURITY_TEAM_EMPTY, security_team_kb())
        return
    lines: list[str] = []
    for member in members:
        extras = []
        if member.overrides:
            extras.append(f"استثناءات: {member.overrides}")
        if member.is_banned:
            extras.append("محظور")
        lines.append(
            t.SECURITY_TEAM_LINE.format(
                icon="⛔" if member.is_banned else "👤",
                name=safe(member.user.display_name, limit=25),
                role=t.SECURITY_ROLE_LABELS.get(str(member.user.role), str(member.user.role)),
                extras=f" · {' · '.join(extras)}" if extras else "",
            )
        )
    await render(
        update, context, t.SECURITY_TEAM_TITLE.format(lines="\n".join(lines)), security_team_kb()
    )


def conversations() -> list:
    """لا محادثات في قسم الأمان (شاشات وأزرار فورية)."""
    return []


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم الأمان."""
    return [
        CallbackQueryHandler(home_screen, pattern=pattern(NS_ADM_SEC, "home")),
        CallbackQueryHandler(events_screen, pattern=pattern(NS_ADM_SEC, "events")),
        CallbackQueryHandler(blocks_screen, pattern=pattern(NS_ADM_SEC, "blocks")),
        CallbackQueryHandler(unblock_action, pattern=pattern(NS_ADM_SEC, "unblock")),
        CallbackQueryHandler(team_screen, pattern=pattern(NS_ADM_SEC, "team")),
    ]
```

### `handlers/admin/providers.py`  ·  مُحدَّث (مقتطف)  ·  977 سطراً

رفض رابط API غير آمن في خطوة الإدخال.

```python
@guarded
@admin_required(Permission.PROVIDERS_CREATE)
async def receive_provider_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال رابط الـAPI (يُتحقق منه) ثم سؤال نوع الواجهة."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_URL

    api_url = validate_public_https_url(message.text.strip())
    update_flow(context, api_url=api_url)
    await send(update, context, t.PROVIDER_ASK_TYPE, provider_type_kb())
    return ASK_TYPE
```

### `keyboards/admin_kb.py`  ·  مُحدَّث (مقتطف)  ·  1432 سطراً

لوحات الأمان.

```python
def security_home_kb() -> InlineKeyboardMarkup:
    """الشاشة الرئيسية للأمان: تحديث + الأحداث + الموقوفون + الفريق."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADM_SEC, "home"))],
            [
                InlineKeyboardButton(t.BTN_SECURITY_EVENTS, callback_data=pack(NS_ADM_SEC, "events", 1)),
                InlineKeyboardButton(t.BTN_SECURITY_BLOCKS, callback_data=pack(NS_ADM_SEC, "blocks")),
            ],
            [InlineKeyboardButton(t.BTN_SECURITY_TEAM, callback_data=pack(NS_ADM_SEC, "team"))],
            _panel_row(),
        ]
    )

    # ... (باقي الملف دون تغيير) ...

def security_events_kb(*, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """ترقيم صفحات الأحداث الأمنية + رجوع."""
    rows: list[list[InlineKeyboardButton]] = []
    nav = pagination_row(NS_ADM_SEC, "events", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_SEC, "home"))
    return InlineKeyboardMarkup(rows)

    # ... (باقي الملف دون تغيير) ...

def security_blocks_kb(telegram_ids: list[tuple[int, str]], perms: set[str]) -> InlineKeyboardMarkup:
    """
    شاشة الموقوفين: زر «رفع الإيقاف» لكل موقوف لمن يملك `security.manage` فقط.

    المدخلات:
        telegram_ids : قائمة (معرّف تيليجرام، اسم العرض).
    """
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADM_SEC, "blocks"))]
    ]
    if Permission.SECURITY_MANAGE in perms:
        for telegram_id, name in telegram_ids[:SECURITY_UNBLOCK_BUTTONS_MAX]:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"{t.BTN_SECURITY_UNBLOCK} · {safe(name, limit=20)}",
                        callback_data=pack(NS_ADM_SEC, "unblock", telegram_id),
                    )
                ]
            )
    rows.append(_back_row(NS_ADM_SEC, "home"))
    return InlineKeyboardMarkup(rows)

    # ... (باقي الملف دون تغيير) ...

def security_team_kb() -> InlineKeyboardMarkup:
    """شاشة الفريق: رجوع فقط (عرض للقراءة)."""
    return InlineKeyboardMarkup([_back_row(NS_ADM_SEC, "home")])
```


## السكربتات

### `scripts/security_check.py`  ·  جديد  ·  102 سطراً

فحص أمني من سطر الأوامر (صلاحيات ملفات، أسرار، مفاتيح).

```python
"""
فحص أمني دون اتصال (المرحلة 9) — يعمل بلا تيليجرام وبلا تعديل بيانات.

يفحص:
    1. الأسرار: وجود التوكن ومفتاح التشفير وصيغتهما (بلا طباعة قيمهما).
    2. صلاحيات الملفات الحسّاسة (.env، القاعدة، النسخ، اللوق) — مع `--fix` لضبطها.
    3. وضع النظام من قاعدة البيانات: الأدمن الأعلى، روابط المزودين، الاستثناءات
       الخطرة، منع التنفيذ الذاتي، سقوف التسوية، حدود الاستخدام، الأخطاء الأخيرة.

طريقة التشغيل (من مجلد المشروع):
    python -m scripts.security_check
    python -m scripts.security_check --fix      # ضبط صلاحيات الملفات تلقائياً

كود الخروج: 0 كل شيء سليم أو تنبيهات فقط · 1 يوجد «خطر» · 2 خطأ في الإعدادات.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:                      # تشغيل مباشر بلا تثبيت الحزمة
    sys.path.insert(0, str(ROOT))

from config import Config, ConfigError                      # noqa: E402
from database.database import Database                      # noqa: E402
from database.repositories import Repositories              # noqa: E402
from services import build_services                         # noqa: E402
from services.security_service import (                     # noqa: E402
    LEVEL_BAD,
    LEVEL_WARN,
    EnvPosture,
)
from utils.fs_security import check_paths                   # noqa: E402
from utils.security import SecretBox, generate_encryption_key  # noqa: E402

ICONS = {"ok": "✅", "warn": "⚠️ ", "bad": "⛔"}


async def run(*, fix: bool) -> int:
    """تنفيذ الفحص وطباعة التقرير وإرجاع كود الخروج."""
    try:
        config = Config.load()
    except ConfigError as exc:
        print(f"⛔ خطأ في الإعدادات: {exc}")
        return 2

    paths = check_paths(config.sensitive_paths(), fix=fix)
    env = EnvPosture(
        bot_token_set=bool(config.bot_token),
        encryption_key_set=bool(config.encryption_key),
        alert_chat_set=config.admin_alert_chat_id is not None,
        path_checks=tuple(paths),
    )

    print("🛡️  فحص الأمان — SMM Bot\n" + "─" * 40)
    for item in paths:
        mark = "✅" if not item.insecure else "⚠️ "
        suffix = " (ضُبطت الآن)" if item.fixed else ""
        print(f"  {mark} {item.label}: {item.mode_text}{suffix} {item.note}".rstrip())
    if not paths:
        print("  ℹ️  لا ملفات حسّاسة موجودة بعد (أو النظام لا يدعم صلاحيات POSIX).")

    if not config.database_path.exists():
        print("\n⚠️  قاعدة البيانات غير موجودة بعد — شغّل: python -m scripts.init_db")
        return 1 if any(item.insecure for item in paths) else 0

    db = Database(config.database_path)
    await db.connect()
    try:
        repos = Repositories(db)
        # صندوق التشفير مطلوب لبناء الخدمات فقط؛ لا يُستخدم هنا لفكّ أي مفتاح
        box = SecretBox(config.encryption_key or generate_encryption_key())
        services = build_services(db, repos, secret_box=box, super_admin_ids=config.super_admin_ids)
        checks = await services.security.run_checks(env)
    finally:
        await db.close()

    print("\n" + "─" * 40)
    for check in checks:
        print(f"  {ICONS.get(check.level, '•')} {check.title}: {check.detail}")

    bad = sum(1 for check in checks if check.level == LEVEL_BAD)
    warn = sum(1 for check in checks if check.level == LEVEL_WARN)
    print("─" * 40)
    print(f"النتيجة: {bad} خطر · {warn} تنبيه · {len(checks) - bad - warn} سليم")
    return 1 if bad else 0


def main() -> int:
    """نقطة الدخول: قراءة الوسائط وتشغيل الفحص."""
    parser = argparse.ArgumentParser(description="فحص أمني دون اتصال")
    parser.add_argument("--fix", action="store_true", help="ضبط صلاحيات الملفات الحسّاسة تلقائياً")
    args = parser.parse_args()
    return asyncio.run(run(fix=args.fix))


if __name__ == "__main__":
    sys.exit(main())
```

### `scripts/create_admin.py`  ·  مُحدَّث  ·  110 سطراً

حماية آخر أدمن أعلى (`--force`) ورفض المعرّفات غير الصالحة.

```python
"""
إنشاء أو ترقية حساب إداري من سطر الأوامر.

الاستخدام (من مجلد المشروع):
    python -m scripts.create_admin 123456789 admin
    python -m scripts.create_admin 123456789 support
    python -m scripts.create_admin 123456789 user        # تنزيل الصلاحيات
    python -m scripts.create_admin 123456789 user --force  # تنزيل آخر أدمن أعلى (خطِر)

الفائدة: التعافي عند فقدان الوصول للوحة، أو إعداد فريق العمل قبل تشغيل البوت.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from config import Config, ConfigError
from core.enums import Role
from database.database import Database
from database.repositories import Repositories
from utils.fs_security import check_paths
from utils.logging_setup import setup_logging

VALID_ROLES = {str(role) for role in Role}


async def run(telegram_id: int, role: str, *, force: bool = False) -> int:
    """
    تنفيذ إنشاء/ترقية الحساب وإرجاع كود الخروج.

    حمايتان (المرحلة 9):
        • معرّف تيليجرام للأشخاص عدد موجب (السالب/الصفر خطأ إدخال).
        • لا يُنزَّل **آخر أدمن أعلى فعّال** إلا بـ`--force`، وإلا فقد النظام كل من
          يملك صلاحية الأمان وإدارة الأدوار ولا يعود إلا بسكربت طوارئ.
    """
    if telegram_id <= 0:
        print("❌ معرّف تيليجرام يجب أن يكون عدداً موجباً.")
        return 2
    if role not in VALID_ROLES:
        print(f"❌ دور غير معروف: {role} — الأدوار المتاحة: {', '.join(sorted(VALID_ROLES))}")
        return 2

    try:
        config = Config.load()
    except ConfigError as exc:
        print(f"❌ خطأ في الإعدادات: {exc}")
        return 2

    if os.name == "posix":
        os.umask(0o077)                     # ملفات خاصة بالمالك من لحظة إنشائها
    config.ensure_directories()
    setup_logging(config.log_file, config.log_level, console=False)

    db = Database(config.database_path)
    await db.connect()
    try:
        repos = Repositories(db)
        user = await repos.users.get_by_telegram_id(telegram_id)
        if user is not None and user.role == Role.SUPER_ADMIN and role != Role.SUPER_ADMIN and not force:
            supers = [
                item for item in await repos.users.list_by_role(str(Role.SUPER_ADMIN))
                if not item.is_banned
            ]
            if len(supers) <= 1:
                print("❌ هذا آخر أدمن أعلى فعّال — تنزيله يقفل لوحة الإدارة. أضف أدمن أعلى آخر أولاً، أو استعمل --force إن كنت متأكداً.")
                return 1
        async with db.transaction() as tx:
            if user is None:
                user = await repos.users.create(tx, telegram_id=telegram_id, role=role)
                await repos.audit.log(
                    tx, action="admin.create_via_script", target_type="user", target_id=user.id,
                    after={"role": role}, source="script",
                )
                print(f"✅ تم إنشاء المستخدم {telegram_id} بالدور: {role}")
            else:
                old_role = user.role
                await repos.users.set_role(tx, user.id, role)
                await repos.audit.log(
                    tx, action="admin.role_change_via_script", target_type="user", target_id=user.id,
                    before={"role": old_role}, after={"role": role}, source="script",
                )
                print(f"✅ تم تغيير دور المستخدم {telegram_id} من {old_role} إلى {role}")

        permissions = await repos.rbac.effective_permissions(user.id, role)
        print(f"🔐 عدد الصلاحيات الفعلية: {len(permissions)}")
        for item in check_paths(config.sensitive_paths(), fix=True):
            if item.insecure:
                print(f"⚠️ {item.label}: صلاحية {item.mode_text} مفتوحة لغير المالك {item.note}")
        return 0
    finally:
        await db.close()


def main() -> int:
    """نقطة الدخول: قراءة الوسائط وتشغيل العملية."""
    parser = argparse.ArgumentParser(description="إنشاء أو ترقية حساب إداري")
    parser.add_argument("telegram_id", type=int, help="معرف تيليجرام الرقمي")
    parser.add_argument(
        "role", nargs="?", default=str(Role.ADMIN), help="الدور: user / support / admin / super_admin"
    )
    parser.add_argument("--force", action="store_true", help="السماح بتنزيل آخر أدمن أعلى")
    args = parser.parse_args()
    return asyncio.run(run(args.telegram_id, args.role, force=args.force))


if __name__ == "__main__":
    sys.exit(main())
```

### `scripts/init_db.py`  ·  مُحدَّث  ·  186 سطراً

تهيئة القاعدة بـumask 077 (ملفات خاصة بالمالك).

```python
"""
تهيئة قاعدة البيانات — أول أمر يُنفَّذ عند تثبيت المشروع.

ما تفعله هذه الأداة:
    1. قراءة الإعدادات من .env وإنشاء المجلدات المطلوبة.
    2. إنشاء ملف قاعدة البيانات وتطبيق كل الترحيلات الناقصة.
    3. التحقق من سلامة المخطط والمفاتيح الأجنبية.
    4. زرع حسابات الأدمن الأعلى المذكورة في SUPER_ADMIN_IDS.
    5. طباعة تقرير واضح بالحالة.

طريقة التشغيل (من مجلد المشروع smm_bot):
    python -m scripts.init_db
    python -m scripts.init_db --gen-key     # توليد مفتاح تشفير جديد فقط
    python -m scripts.init_db --status      # عرض الحالة دون تعديل
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from config import Config, ConfigError
from core.enums import Role
from database.database import Database
from database.migrator import Migrator
from database.repositories import Repositories
from utils.fs_security import check_paths
from utils.logging_setup import setup_logging
from utils.security import generate_encryption_key

#: الجداول التي يجب أن تكون موجودة بعد التهيئة الكاملة
EXPECTED_TABLES: tuple[str, ...] = (
    "schema_migrations", "roles", "permissions", "role_permissions", "users", "user_permissions",
    "user_states", "providers", "provider_balance_snapshots", "service_categories", "services",
    "service_price_history", "payment_methods", "payments", "orders", "order_status_history",
    "transactions", "support_tickets", "support_messages", "notifications", "audit_logs",
    "settings", "broadcasts", "broadcast_recipients", "idempotency_keys", "provider_requests",
    "error_logs", "backups",
)


async def seed_super_admins(db: Database, telegram_ids: tuple[int, ...]) -> list[str]:
    """
    إنشاء أو ترقية حسابات الأدمن الأعلى المذكورة في متغير البيئة.

    المخرجات: قائمة رسائل توضح ما تم لكل معرف.
    """
    repos = Repositories(db)
    messages: list[str] = []
    for telegram_id in telegram_ids:
        existing = await repos.users.get_by_telegram_id(telegram_id)
        async with db.transaction() as tx:
            if existing is None:
                await repos.users.create(
                    tx, telegram_id=telegram_id, first_name="Super Admin", role=Role.SUPER_ADMIN
                )
                await repos.audit.log(
                    tx, action="system.seed_super_admin", target_type="user", target_id=telegram_id,
                    details={"source": "SUPER_ADMIN_IDS"}, source="script",
                )
                messages.append(f"✅ أُنشئ حساب أدمن أعلى للمعرف {telegram_id}")
            elif existing.role != Role.SUPER_ADMIN:
                await repos.users.set_role(tx, existing.id, Role.SUPER_ADMIN)
                await repos.audit.log(
                    tx, action="system.promote_super_admin", target_type="user", target_id=existing.id,
                    before={"role": existing.role}, after={"role": str(Role.SUPER_ADMIN)}, source="script",
                )
                messages.append(f"⬆️ تمت ترقية المستخدم {telegram_id} إلى أدمن أعلى")
            else:
                messages.append(f"ℹ️ المعرف {telegram_id} أدمن أعلى بالفعل")
    return messages


async def verify_schema(db: Database) -> list[str]:
    """التحقق من وجود كل الجداول المتوقعة وسلامة قاعدة البيانات."""
    problems: list[str] = []
    tables = set(await db.table_names())
    missing = [name for name in EXPECTED_TABLES if name not in tables]
    if missing:
        problems.append("جداول ناقصة: " + ", ".join(missing))
    if not await db.integrity_check():
        problems.append("فحص سلامة قاعدة البيانات فشل (integrity_check).")
    violations = await db.foreign_key_check()
    if violations:
        problems.append(f"يوجد {len(violations)} انتهاك للمفاتيح الأجنبية.")
    return problems


async def print_status(db: Database, config: Config) -> None:
    """طباعة ملخص حالة قاعدة البيانات بعد التهيئة."""
    repos = Repositories(db)
    migrator = Migrator(db)
    tables = await db.table_names()
    print("\n📊 حالة النظام")
    print("──────────────────────────────")
    print(f"  ملف قاعدة البيانات : {config.database_path}")
    print(f"  إصدار المخطط        : {await migrator.current_version()}")
    print(f"  عدد الجداول         : {len(tables)}")
    print(f"  الأدوار             : {len(await repos.rbac.list_roles())}")
    print(f"  الصلاحيات           : {len(await repos.rbac.list_permissions())}")
    print(f"  الإعدادات           : {len(await repos.settings.all())}")
    print(f"  التصنيفات           : {len(await repos.categories.list_all())}")
    print(f"  المستخدمون          : {await repos.users.count_all()}")
    print(f"  المزودون            : {len(await repos.providers.list_all())}")
    print(f"  الخدمات             : {await repos.services.count_active()}")
    print(f"  طرق الدفع           : {len(await repos.payment_methods.list_all())}")
    print("──────────────────────────────")


async def run(args: argparse.Namespace) -> int:
    """تنفيذ عملية التهيئة الكاملة وإرجاع كود الخروج."""
    try:
        config = Config.load()
    except ConfigError as exc:
        print(f"❌ خطأ في الإعدادات: {exc}")
        return 2

    if os.name == "posix":
        os.umask(0o077)                     # ملفات خاصة بالمالك من لحظة إنشائها
    config.ensure_directories()
    setup_logging(config.log_file, config.log_level, console=False)

    print("🚀 تهيئة قاعدة بيانات SMM Bot")
    for key, value in config.safe_summary().items():
        print(f"  • {key}: {value}")

    db = Database(config.database_path)
    await db.connect()
    try:
        if args.status:
            await print_status(db, config)
            return 0

        migrator = Migrator(db)
        pending = await migrator.pending()
        if pending:
            print(f"\n⚙️ تطبيق {len(pending)} ترحيل: {', '.join(pending)}")
        applied = await migrator.apply_all()
        print("✅ تم تطبيق الترحيلات." if applied else "ℹ️ قاعدة البيانات محدّثة مسبقاً.")

        problems = await verify_schema(db)
        if problems:
            print("\n❌ مشاكل في المخطط:")
            for problem in problems:
                print(f"   - {problem}")
            return 1
        print("✅ فحص المخطط والمفاتيح الأجنبية: سليم.")

        if config.super_admin_ids:
            print("\n👤 حسابات الأدمن الأعلى:")
            for message in await seed_super_admins(db, config.super_admin_ids):
                print(f"   {message}")
        else:
            print("\n⚠️ لم يُحدَّد SUPER_ADMIN_IDS في ملف .env — لن تتمكن من دخول لوحة الأدمن.")

        if not config.encryption_key:
            print("\n⚠️ ENCRYPTION_KEY غير موجود — مطلوب لإضافة المزودين لاحقاً.")
            print(f"   مفتاح مقترح: {generate_encryption_key()}")

        await print_status(db, config)
        remaining = [item for item in check_paths(config.sensitive_paths(), fix=True) if item.insecure]
        for item in remaining:
            print(f"⚠️ {item.label}: صلاحية {item.mode_text} مفتوحة لغير المالك {item.note}")
        print("\n🎉 اكتملت التهيئة بنجاح.")
        return 0
    finally:
        await db.close()


def main() -> int:
    """نقطة الدخول: تحليل الوسائط وتشغيل العملية."""
    parser = argparse.ArgumentParser(description="تهيئة قاعدة بيانات SMM Bot")
    parser.add_argument("--gen-key", action="store_true", help="توليد مفتاح تشفير جديد فقط")
    parser.add_argument("--status", action="store_true", help="عرض حالة قاعدة البيانات دون تعديل")
    args = parser.parse_args()

    if args.gen_key:
        print(generate_encryption_key())
        return 0
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
```


## الاختبارات

### `tests/unit/test_net_security_phase9.py`  ·  جديد  ·  131 سطراً

SSRF: صيغ الروابط والعناوين المحجوبة والـDNS.

```python
"""اختبارات حماية SSRF لروابط المزودين (المرحلة 9)."""

from __future__ import annotations

import pytest

from core.exceptions import ProviderPermanentError, ValidationError
from utils import net_security
from utils.net_security import ensure_public_host, is_public_ip, validate_public_https_url


@pytest.mark.parametrize(
    "url",
    [
        "https://api.provider.com/api/v2",
        "https://provider.example.org:8443/api",
        "https://8.8.8.8/api",
        "  https://api.provider.com/api/v2  ",
    ],
)
def test_valid_public_https_urls_are_accepted(url: str) -> None:
    """الروابط العامة عبر https وعلى المنافذ المسموحة تُقبل (مع قصّ الفراغات)."""
    assert validate_public_https_url(url) == url.strip()


@pytest.mark.parametrize(
    "url",
    [
        "",
        None,
        "http://api.provider.com/api",                 # بلا تشفير
        "ftp://api.provider.com/api",
        "https://localhost/api",
        "https://service.localhost/api",
        "https://127.0.0.1/api",
        "https://10.0.0.5/api",
        "https://192.168.1.10/api",
        "https://169.254.169.254/latest/meta-data",   # بيانات السحابة
        "https://[::1]/api",
        "https://[::ffff:127.0.0.1]/api",             # IPv4 مضمَّن في IPv6
        "https://0.0.0.0/api",
        "https://metadata.google.internal/x",
        "https://intranet/api",                       # اسم بلا نقطة
        "https://user:pass@api.provider.com/api",     # بيانات اعتماد في الرابط
        "https://api.provider.com:8080/api",          # منفذ غير مسموح
        "https://api.provider.com:22/api",
        "https://api.provider.com/a b",
        "https://" + "a" * 320 + ".com",
    ],
)
def test_unsafe_urls_are_rejected(url: str | None) -> None:
    """أي رابط داخلي/غير مشفّر/بمنفذ غريب يُرفض برسالة عربية."""
    with pytest.raises(ValidationError):
        validate_public_https_url(url)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("8.8.8.8", True),
        ("1.1.1.1", True),
        ("127.0.0.1", False),
        ("10.1.2.3", False),
        ("172.16.0.1", False),
        ("192.168.0.1", False),
        ("169.254.1.1", False),
        ("224.0.0.1", False),
        ("::1", False),
        ("fe80::1", False),
        ("fc00::1", False),
        ("::ffff:10.0.0.1", False),
        ("not-an-ip", False),
    ],
)
def test_is_public_ip(value: str, expected: bool) -> None:
    """التصنيف الصحيح للعناوين العامة والخاصة بما فيها IPv6 المضمَّن."""
    assert is_public_ip(value) is expected


@pytest.mark.asyncio
async def test_ensure_public_host_accepts_public_resolution() -> None:
    """مضيف يُحلّ لعنوان عام يمر ويُخزَّن في ذاكرة DNS (حلّ واحد فقط)."""
    calls: list[str] = []

    async def resolver(host: str) -> list[str]:
        calls.append(host)
        return ["93.184.216.34"]

    await ensure_public_host("https://api.provider.com/x", resolver=resolver)
    await ensure_public_host("https://api.provider.com/y", resolver=resolver)
    assert calls == ["api.provider.com"], "لم تُستخدم ذاكرة DNS"


@pytest.mark.asyncio
async def test_ensure_public_host_rejects_private_resolution() -> None:
    """نطاق عام الاسم يشير لعنوان داخلي (هجوم SSRF بالنطاق) يُرفض كخطأ دائم."""

    async def resolver(host: str) -> list[str]:
        return ["93.184.216.34", "10.0.0.7"]        # عنوان واحد خاص يكفي للرفض

    with pytest.raises(ProviderPermanentError):
        await ensure_public_host("https://evil.example.com/x", resolver=resolver)


@pytest.mark.asyncio
async def test_ensure_public_host_failed_resolution_is_permanent_and_not_cached() -> None:
    """فشل الحلّ خطأ دائم، ولا يُخزَّن نجاحاً كاذباً."""

    async def broken(host: str) -> list[str]:
        raise OSError("dns down")

    with pytest.raises(ProviderPermanentError):
        await ensure_public_host("https://api.provider.com/x", resolver=broken)

    async def good(host: str) -> list[str]:
        return ["93.184.216.34"]

    await ensure_public_host("https://api.provider.com/x", resolver=good)   # لا يزال قابلاً للنجاح


@pytest.mark.asyncio
async def test_literal_private_ip_rejected_at_send_time() -> None:
    """عنوان IP حرفي داخلي يُرفض وقت الإرسال أيضاً (دفاع ثانٍ لما خُزّن قبل التحقق)."""
    with pytest.raises(ProviderPermanentError):
        await ensure_public_host("https://192.168.0.9/x")


def test_clear_dns_cache_is_idempotent() -> None:
    """تفريغ الذاكرة آمن بلا استدعاء سابق."""
    net_security.clear_dns_cache()
    net_security.clear_dns_cache()
```

### `tests/unit/test_sanitize_phase9.py`  ·  جديد  ·  97 سطراً

تنقية الأسرار من النصوص واللوقات.

```python
"""اختبارات تنقية الأسرار من النصوص واللوقات (المرحلة 9)."""

from __future__ import annotations

import logging

import pytest

from utils.logging_setup import RedactingFormatter, SecretRedactionFilter
from utils.security import register_secret, sanitize

TOKEN = "123456789:AAFakeTokenValue1234567890abcdefghi"


@pytest.mark.parametrize(
    "text",
    [
        f"https://api.telegram.org/bot{TOKEN}/getUpdates",
        f"token={TOKEN}",
        "api_key=abcdef123456",
        '{"api_key": "abcdef123456"}',
        "key=SECRETVALUE99",
        "password: hunter2hunter2",
        "https://user:pass1234@host.com/x",
        "Authorization failed secret='my-long-secret'",
    ],
)
def test_known_secret_shapes_are_removed(text: str) -> None:
    """الصيغ الشائعة للأسرار تُحذف قيمها."""
    clean = sanitize(text)
    for leaked in ("AAFakeTokenValue", "abcdef123456", "SECRETVALUE99", "hunter2hunter2", "pass1234", "my-long-secret"):
        assert leaked not in clean, clean


def test_fernet_ciphertext_is_removed() -> None:
    """نص Fernet المشفّر (مفتاح مزود مخزَّن) لا يظهر في أي نص."""
    cipher = "gAAAAAB" + "x" * 80
    assert cipher not in sanitize(f"stored value {cipher} end")


def test_registered_secret_is_removed_anywhere() -> None:
    """السر المسجَّل يُحذف حرفياً حتى لو لم يطابق أي نمط."""
    register_secret("plain-looking-secret-value")
    assert "plain-looking-secret-value" not in sanitize("خطأ: plain-looking-secret-value في الاتصال")


def test_short_registered_secret_is_ignored() -> None:
    """سر أقصر من الحد لا يُسجَّل (حتى لا يمسح كلمات عادية)."""
    register_secret("abc")
    assert sanitize("abc def") == "abc def"


def test_extra_secrets_are_removed() -> None:
    """الأسرار الإضافية الممرَّرة وقت الاستدعاء تُحذف أيضاً."""
    assert "provider-key-77" not in sanitize("bad provider-key-77 here", ("provider-key-77",))


def test_sanitize_handles_empty() -> None:
    """None والنص الفارغ ينتجان نصاً فارغاً."""
    assert sanitize(None) == ""
    assert sanitize("") == ""


def test_ordinary_text_is_untouched() -> None:
    """نص عادي بلا أسرار لا يتغير (لا إيجابيات كاذبة)."""
    text = "تم إنشاء الطلب ORD-123 بنجاح لعدد 1000"
    assert sanitize(text) == text


def test_log_file_never_contains_secrets(tmp_path) -> None:
    """
    ما يُكتب في ملف اللوق ينقّى حتى من استثناءات تحمل السر.

    نركّب المعالج بنفس فلتر ومنسّق الإنتاج على مسجّل خاص بالاختبار، فلا نعتمد
    على الحالة العامة لـ`setup_logging` (تُهيَّأ مرة واحدة في العملية).
    """
    log_file = tmp_path / "bot.log"
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.addFilter(SecretRedactionFilter())
    handler.setFormatter(RedactingFormatter("%(levelname)s %(message)s"))
    logger = logging.getLogger("phase9.test.isolated")
    logger.propagate = False
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        try:
            raise RuntimeError(f"فشل الاتصال token={TOKEN}")
        except RuntimeError:
            logger.exception("خطأ مع %s", "api_key=abcdef123456")
        handler.flush()
    finally:
        logger.removeHandler(handler)
        handler.close()
    content = log_file.read_text(encoding="utf-8")
    assert "AAFakeTokenValue" not in content
    assert "abcdef123456" not in content
    assert "فشل الاتصال" in content
```

### `tests/unit/test_setting_rules_phase9.py`  ·  جديد  ·  86 سطراً

قواعد نطاق الإعدادات.

```python
"""اختبارات قواعد التحقق من الإعدادات (المرحلة 9)."""

from __future__ import annotations

import pytest

from core.exceptions import ValidationError
from core.setting_rules import check_ordered_pairs, normalize_setting_value


@pytest.mark.parametrize(
    ("key", "value", "value_type", "expected"),
    [
        ("rate_limit_actions_per_minute", "30", "int", "30"),
        ("rate_limit_actions_per_minute", "٣٠", "int", "30"),         # أرقام هندية
        ("admin_digest_hour", "0", "int", "0"),
        ("admin_digest_hour", "23", "int", "23"),
        ("maintenance_mode", "نعم", "bool", "true"),
        ("maintenance_mode", "off", "bool", "false"),
        ("maintenance_mode", True, "bool", "true"),
        ("provider_exchange_rate", "530.50", "str", "530.5"),
        ("support_username", "", "str", ""),
        ("support_username", "@my_support", "str", "@my_support"),
        ("currency_code", "YER", "str", "YER"),
        ("admin_adjust_max_units", "0", "money", "0"),
        ("admin_alert_chat_id", "-1001234567890", "str", "-1001234567890"),
    ],
)
def test_valid_values_are_normalized(key: str, value: object, value_type: str, expected: str) -> None:
    """القيم الصحيحة تُقبل وتُطبَّع."""
    assert normalize_setting_value(key, value, value_type) == expected


@pytest.mark.parametrize(
    ("key", "value", "value_type"),
    [
        ("rate_limit_actions_per_minute", "0", "int"),         # تعطيل الحماية بصفر
        ("rate_limit_actions_per_minute", "2", "int"),
        ("rate_limit_actions_per_minute", "100000", "int"),
        ("rate_limit_actions_per_minute", "abc", "int"),
        ("rate_limit_block_minutes", "0", "int"),
        ("admin_digest_hour", "24", "int"),
        ("admin_digest_hour", "-1", "int"),
        ("order_submit_interval_seconds", "1", "int"),         # أقل من حد الجدولة
        ("maintenance_mode", "ربما", "bool"),
        ("provider_exchange_rate", "0", "str"),
        ("provider_exchange_rate", "-5", "str"),
        ("provider_exchange_rate", "NaN", "str"),
        ("provider_exchange_rate", "1.123456789", "str"),
        ("currency_code", "ريال", "str"),
        ("currency_code", "TOOLONGCODE", "str"),
        ("support_username", "ab", "str"),
        ("bot_name", "x" * 200, "str"),
        ("bot_name", "", "str"),
        ("admin_adjust_max_units", "-1", "money"),
        ("min_deposit_units", "0", "money"),
        ("some_json", "{broken", "json"),
        ("admin_alert_chat_id", "abc", "str"),
    ],
)
def test_invalid_values_are_rejected(key: str, value: object, value_type: str) -> None:
    """القيم الخارجة عن النطاق أو الصيغة تُرفض برسالة تحقق."""
    with pytest.raises(ValidationError):
        normalize_setting_value(key, value, value_type)


def test_unknown_key_gets_generic_limits() -> None:
    """مفتاح بلا قاعدة خاصة يخضع للحدود العامة بحسب نوعه."""
    assert normalize_setting_value("brand_new_key", "5", "int") == "5"
    with pytest.raises(ValidationError):
        normalize_setting_value("brand_new_key", "9" * 18, "int")


def test_ordered_pairs_min_must_not_exceed_max() -> None:
    """الحد الأدنى للشحن لا يتجاوز الأعلى وبالعكس."""
    current = {"min_deposit_units": "10000", "max_deposit_units": "500000"}
    check_ordered_pairs("min_deposit_units", "20000", current)
    with pytest.raises(ValidationError):
        check_ordered_pairs("min_deposit_units", "600000", current)
    with pytest.raises(ValidationError):
        check_ordered_pairs("max_deposit_units", "5000", current)


def test_ordered_pairs_ignores_unrelated_keys() -> None:
    """مفتاح خارج الأزواج لا يُفحص."""
    check_ordered_pairs("bot_name", "x", {"min_deposit_units": "1", "max_deposit_units": "0"})
```

### `tests/unit/test_rate_limit_phase9.py`  ·  جديد  ·  121 سطراً

`AbuseGuard` والحدود المتدرجة.

```python
"""اختبارات المحدِّد والحارس ضد الإساءة بساعة حقنية (المرحلة 9)."""

from __future__ import annotations

from middlewares.rate_limit import (
    BUCKET_GENERAL,
    BUCKET_SENSITIVE,
    STRIKE_WINDOW_SECONDS,
    WARNING_COOLDOWN_SECONDS,
    AbuseGuard,
    RateLimiter,
)


class Clock:
    """ساعة يدوية: نتحكم بالزمن دون انتظار."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_limiter_blocks_after_limit_and_recovers_after_window() -> None:
    """الحد يُطبَّق داخل النافذة وينفرج بعد انقضائها."""
    clock = Clock()
    limiter = RateLimiter(window_seconds=60, clock=clock)
    assert all(limiter.hit(1, 3) for _ in range(3))
    assert limiter.hit(1, 3) is False
    clock.advance(61)
    assert limiter.hit(1, 3) is True


def test_limiter_is_per_user_and_per_bucket() -> None:
    """مستخدم آخر أو سلة أخرى لا يتأثر بحد غيره."""
    limiter = RateLimiter(clock=Clock())
    assert all(limiter.hit(1, 2) for _ in range(2))
    assert limiter.hit(1, 2) is False
    assert limiter.hit(2, 2) is True
    assert limiter.hit(1, 2, bucket=BUCKET_SENSITIVE) is True
    assert limiter.hit(1, 2, bucket=BUCKET_GENERAL) is False


def test_limiter_zero_limit_means_unlimited() -> None:
    """حد صفر = بلا حد (يُستخدم للمراقبة فقط؛ الإعدادات تمنعه عملياً)."""
    limiter = RateLimiter(clock=Clock())
    assert all(limiter.hit(1, 0) for _ in range(500))


def test_limiter_remaining_and_reset() -> None:
    """العدّاد المتبقي يتناقص والتصفير يعيده كاملاً."""
    limiter = RateLimiter(clock=Clock())
    limiter.hit(1, 5)
    limiter.hit(1, 5)
    assert limiter.remaining(1, 5) == 3
    limiter.reset(1)
    assert limiter.remaining(1, 5) == 5


def test_guard_blocks_after_strikes_and_expires() -> None:
    """بلوغ عدد المخالفات يوقف المستخدم، ويزول الإيقاف بانتهاء مدته."""
    clock = Clock()
    guard = AbuseGuard(clock=clock)
    for _ in range(2):
        result = guard.record_violation(7, strikes_limit=3, block_seconds=300)
        assert result.blocked is False
        clock.advance(1)
    final = guard.record_violation(7, strikes_limit=3, block_seconds=300)
    assert final.blocked is True and final.strikes == 3
    assert guard.is_blocked(7)
    assert 290 < guard.seconds_blocked(7) <= 300
    assert guard.total_blocks == 1 and guard.total_violations == 3

    clock.advance(301)
    assert guard.is_blocked(7) is False
    assert guard.blocked_snapshot() == []


def test_guard_old_strikes_expire() -> None:
    """مخالفات أقدم من نافذة الاحتساب لا تجمع مع الجديدة."""
    clock = Clock()
    guard = AbuseGuard(clock=clock)
    guard.record_violation(7, strikes_limit=3, block_seconds=60)
    guard.record_violation(7, strikes_limit=3, block_seconds=60)
    clock.advance(STRIKE_WINDOW_SECONDS + 1)
    result = guard.record_violation(7, strikes_limit=3, block_seconds=60)
    assert result.blocked is False and result.strikes == 1


def test_guard_warning_is_throttled() -> None:
    """التحذير مُهدَّأ: أول مخالفة تحذّر، والتالية السريعة لا تحذّر، وبعد التهدئة تحذّر."""
    clock = Clock()
    guard = AbuseGuard(clock=clock)
    assert guard.record_violation(7, strikes_limit=50, block_seconds=60).warn is True
    clock.advance(1)
    assert guard.record_violation(7, strikes_limit=50, block_seconds=60).warn is False
    clock.advance(WARNING_COOLDOWN_SECONDS)
    assert guard.record_violation(7, strikes_limit=50, block_seconds=60).warn is True


def test_guard_first_warning_works_even_with_tiny_clock() -> None:
    """أول تحذير يصدر حتى لو بدأت الساعة من صفر (لا اعتماد على قيمة افتراضية خاطئة)."""
    guard = AbuseGuard(clock=lambda: 0.0)
    assert guard.record_violation(1, strikes_limit=9, block_seconds=60).warn is True


def test_guard_clear_and_snapshot_ordering() -> None:
    """رفع الإيقاف يزيل المستخدم، والقائمة مرتبة بالأطول إيقافاً."""
    clock = Clock()
    guard = AbuseGuard(clock=clock)
    guard.record_violation(1, strikes_limit=1, block_seconds=100)
    guard.record_violation(2, strikes_limit=1, block_seconds=500)
    snapshot = guard.blocked_snapshot()
    assert [info.telegram_id for info in snapshot] == [2, 1]
    assert guard.clear(2) is True
    assert guard.clear(2) is False
    assert [info.telegram_id for info in guard.blocked_snapshot()] == [1]
```

### `tests/unit/test_hardening_phase9.py`  ·  جديد  ·  163 سطراً

صلاحيات الملفات وتحميل الإعدادات الصارم.

```python
"""اختبارات المُهدِّئ وصلاحيات الملفات وتشديد الإعدادات (المرحلة 9)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from config import Config, ConfigError
from utils.fs_security import DIR_MODE, FILE_MODE, check_paths
from utils.security import generate_encryption_key, sanitize
from utils.throttle import AlertThrottle

posix_only = pytest.mark.skipif(os.name != "posix", reason="صلاحيات POSIX فقط")


# ------------------------------ المُهدِّئ ------------------------------ #


class Clock:
    """ساعة يدوية."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_throttle_allows_first_then_suppresses_then_reports_count() -> None:
    """أول تنبيه يمر، والمتكرر يُكبت، ثم يذكر التنبيه التالي عدد المكبوت."""
    clock = Clock()
    throttle = AlertThrottle(clock=clock)
    assert throttle.check("a", cooldown_seconds=60).allow is True
    clock.now = 10
    assert throttle.check("a", cooldown_seconds=60).allow is False
    assert throttle.check("a", cooldown_seconds=60).allow is False
    clock.now = 61
    decision = throttle.check("a", cooldown_seconds=60)
    assert decision.allow is True and decision.suppressed == 2


def test_throttle_distinct_keys_independent_but_capped_per_window() -> None:
    """بصمات مختلفة مستقلة، لكن سقف النافذة يمنع الإغراق عند تنوّع الأخطاء."""
    throttle = AlertThrottle(max_per_window=3, clock=Clock())
    results = [throttle.check(f"k{i}", cooldown_seconds=60).allow for i in range(5)]
    assert results == [True, True, True, False, False]


def test_throttle_window_resets() -> None:
    """بعد مرور النافذة يعود السماح."""
    clock = Clock()
    throttle = AlertThrottle(max_per_window=1, clock=clock)
    assert throttle.check("a", cooldown_seconds=60).allow
    assert not throttle.check("b", cooldown_seconds=60).allow
    clock.now = 61
    assert throttle.check("b", cooldown_seconds=60).allow


# --------------------------- صلاحيات الملفات --------------------------- #


@posix_only
def test_check_paths_detects_and_fixes_insecure_files(tmp_path: Path) -> None:
    """ملف مفتوح للجميع يُكتشف بلا إصلاح، ثم يُضبط 600 مع الإصلاح."""
    secret = tmp_path / "secret.env"
    secret.write_text("X=1", encoding="utf-8")
    secret.chmod(0o644)
    entries = [(secret, "ملف سرّي", FILE_MODE)]

    [report] = check_paths(entries, fix=False)
    assert report.insecure and not report.fixed
    assert stat.S_IMODE(secret.stat().st_mode) == 0o644, "الفحص وحده لا يجب أن يعدّل"

    [fixed] = check_paths(entries, fix=True)
    assert fixed.fixed and not fixed.insecure
    assert stat.S_IMODE(secret.stat().st_mode) == 0o600


@posix_only
def test_check_paths_fixes_directories_and_skips_missing(tmp_path: Path) -> None:
    """المجلد يُضبط 700، والمسار غير الموجود يُتجاهل بلا خطأ."""
    folder = tmp_path / "backups"
    folder.mkdir()
    folder.chmod(0o755)
    entries = [(folder, "نسخ", DIR_MODE), (tmp_path / "missing.db", "قاعدة", FILE_MODE)]
    results = check_paths(entries, fix=True)
    assert len(results) == 1 and results[0].fixed
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700


@posix_only
def test_check_paths_secure_file_untouched(tmp_path: Path) -> None:
    """ملف سليم الصلاحية لا يُعدَّل ولا يُعلَّم كمخالف."""
    ok = tmp_path / "ok.db"
    ok.write_text("x", encoding="utf-8")
    ok.chmod(0o600)
    [report] = check_paths([(ok, "قاعدة", FILE_MODE)], fix=True)
    assert not report.insecure and not report.fixed


# ----------------------------- تشديد الإعدادات ----------------------------- #


def _env(tmp_path: Path, content: str) -> Path:
    """كتابة ملف بيئة مؤقت."""
    path = tmp_path / ".env"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    """عزل متغيرات البيئة."""
    for key in ("BOT_TOKEN", "ENCRYPTION_KEY", "SUPER_ADMIN_IDS"):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize("token", ["abc", "123:short", "notanumber:AAFakeTokenValue1234567890abcdefghi", "12345:AA bad token with spaces 1234567890"])
def test_malformed_bot_token_rejected_without_echoing_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, token: str) -> None:
    """توكن بصيغة خاطئة يُرفض عند التحميل، والرسالة لا تحتوي قيمته."""
    monkeypatch.setenv("BOT_TOKEN", token)
    with pytest.raises(ConfigError) as info:
        Config.load(env_file=_env(tmp_path, ""))
    assert token not in str(info.value)


def test_invalid_encryption_key_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """مفتاح تشفير ليس Fernet يُرفض مبكراً."""
    monkeypatch.setenv("ENCRYPTION_KEY", "not-a-fernet-key")
    with pytest.raises(ConfigError, match="ENCRYPTION_KEY"):
        Config.load(env_file=_env(tmp_path, ""))


@pytest.mark.parametrize("ids", ["-100123", "0", "5,-7"])
def test_non_positive_super_admin_ids_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ids: str) -> None:
    """معرّفات الأدمن الأعلى يجب أن تكون موجبة."""
    monkeypatch.setenv("SUPER_ADMIN_IDS", ids)
    with pytest.raises(ConfigError, match="SUPER_ADMIN_IDS"):
        Config.load(env_file=_env(tmp_path, ""))


def test_valid_secrets_are_registered_for_sanitizing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """بعد التحميل يُحذف التوكن والمفتاح حرفياً من أي نص حتى بلا صيغة معروفة."""
    key = generate_encryption_key()
    monkeypatch.setenv("BOT_TOKEN", "123456789:AAFakeTokenValue1234567890abcdefghi")
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    Config.load(env_file=_env(tmp_path, ""))
    assert key not in sanitize(f"فشل بسبب المفتاح {key} أثناء الفك")
    token = "123456789:AAFakeTokenValue1234567890abcdefghi"
    assert "AAFakeTokenValue" not in sanitize(f"استجابة غريبة [{token}] انتهت")


def test_sensitive_paths_cover_db_sidecars_and_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """قائمة المسارات الحسّاسة تشمل .env وملفات WAL/SHM والمجلدات."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "d" / "x.db"))
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "l" / "bot.log"))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "b"))
    config = Config.load(env_file=_env(tmp_path, ""))
    names = {path.name for path, _label, _mode in config.sensitive_paths(tmp_path / ".env")}
    assert {".env", "x.db", "x.db-wal", "x.db-shm", "b", "l", "d"} <= names
```

### `tests/integration/test_rbac_phase9.py`  ·  جديد  ·  210 سطراً

هرمية الصلاحيات ومنع التصعيد وحماية آخر أدمن أعلى.

```python
"""اختبارات حواجز الأدوار والصلاحيات وحظر التنفيذ الذاتي (المرحلة 9)."""

from __future__ import annotations

import pytest

from core.exceptions import PermissionDeniedError, ValidationError
from core.permissions import Permission
from database.models import User
from services import ServiceContainer

pytestmark = pytest.mark.asyncio


async def _make(db, repos, telegram_id: int, role: str, name: str) -> User:
    """إنشاء مستخدم بدور محدد."""
    async with db.transaction() as tx:
        return await repos.users.create(tx, telegram_id=telegram_id, username=name, first_name=name, role=role)


async def _grant_role_perm(db, repos, role: str, permission: str) -> None:
    """منح صلاحية لدور (لتمكين سيناريو أدمن يملك صلاحية عالية)."""
    async with db.transaction() as tx:
        await repos.rbac.grant_to_role(tx, role, permission)


async def _events(repos, event: str) -> int:
    """عدد مرات حدث أمني في سجل التدقيق."""
    return await repos.audit.count_by_action_prefix(f"security.{event}")


# ============================== تغيير الدور ============================== #


async def test_super_admin_can_promote_and_demote(db, repos, services: ServiceContainer, super_admin, user) -> None:
    """الأدمن الأعلى يرقّي المستخدم ثم يعيده (المسار الطبيعي يعمل)."""
    assert await services.auth.set_role(super_admin, user.id, "support") is True
    assert (await repos.users.get_by_id(user.id)).role == "support"
    assert await services.auth.set_role(super_admin, user.id, "user") is True


async def test_normal_admin_without_permission_cannot_change_roles(services, super_admin, admin, user, repos) -> None:
    """الأدمن العادي لا يملك `users.role.change` افتراضياً."""
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_role(admin, user.id, "support")
    assert (await repos.users.get_by_id(user.id)).role == "user"


async def test_self_role_change_blocked_and_audited(db, repos, services, super_admin) -> None:
    """لا يغيّر أحد دور حسابه بنفسه (حتى الأدمن الأعلى) ويُسجَّل الحدث."""
    other = await _make(db, repos, 5001, "super_admin", "second_root")
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_role(super_admin, super_admin.id, "user")
    assert (await repos.users.get_by_id(super_admin.id)).role == "super_admin"
    assert await _events(repos, "self_role_change_blocked") == 1
    assert other.id != super_admin.id


async def test_admin_with_role_permission_cannot_escalate_to_own_level(db, repos, services, admin, user) -> None:
    """أدمن مُنح تغيير الأدوار لا يستطيع منح دور بمستواه أو أعلى (منع التصعيد)."""
    await _grant_role_perm(db, repos, "admin", Permission.USERS_ROLE_CHANGE)
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_role(admin, user.id, "admin")
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_role(admin, user.id, "super_admin")
    assert (await repos.users.get_by_id(user.id)).role == "user"
    assert await _events(repos, "role_escalation_blocked") == 2
    # ما دون مستواه مسموح
    assert await services.auth.set_role(admin, user.id, "support") is True


async def test_admin_cannot_modify_peer_or_superior(db, repos, services, admin, super_admin) -> None:
    """الأدمن العادي لا يعدّل زميلاً بنفس المستوى ولا أدمن أعلى."""
    await _grant_role_perm(db, repos, "admin", Permission.USERS_ROLE_CHANGE)
    peer = await _make(db, repos, 5002, "admin", "peer")
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_role(admin, peer.id, "user")
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_role(admin, super_admin.id, "user")
    assert await _events(repos, "hierarchy_denied") == 2


async def test_last_super_admin_cannot_be_demoted(db, repos, services, super_admin) -> None:
    """
    آخر أدمن أعلى فعّال محمي من التخفيض.

    الوصول لهذا الحاجز يحتاج منفِّذاً أعلى غير فعّال (محظور) لا يزال يملك الدور؛
    نتأكد أن الحاجز يعمل وأن الحدث الأمني مسجَّل تحديداً.
    """
    banned_root = await _make(db, repos, 5003, "super_admin", "banned_root")
    async with db.transaction() as tx:
        await repos.users.set_ban(tx, banned_root.id, banned=True, reason="اختبار")
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_role(banned_root, super_admin.id, "user")
    assert (await repos.users.get_by_id(super_admin.id)).role == "super_admin"
    assert await _events(repos, "last_super_admin_protected") == 1


async def test_demoting_a_banned_super_admin_is_allowed(db, repos, services, super_admin) -> None:
    """تخفيض أدمن أعلى محظور (غير فعّال) مسموح لأنه لا يُفقد النظام أدمن فعّالاً."""
    banned_root = await _make(db, repos, 5008, "super_admin", "banned_root2")
    async with db.transaction() as tx:
        await repos.users.set_ban(tx, banned_root.id, banned=True, reason="اختبار")
    assert await services.auth.set_role(super_admin, banned_root.id, "user") is True


async def test_second_super_admin_allows_demoting_the_first(db, repos, services, super_admin) -> None:
    """بوجود أدمن أعلى ثانٍ فعّال يصح تخفيض الأول."""
    second = await _make(db, repos, 5004, "super_admin", "second")
    assert await services.auth.set_role(second, super_admin.id, "admin") is True


# ============================ الاستثناءات الفردية ============================ #


async def test_cannot_change_own_permissions(db, repos, services, super_admin) -> None:
    """لا أحد يعدّل استثناءات صلاحيات حسابه."""
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_user_permission(super_admin, super_admin.id, Permission.ORDERS_VIEW, allow=False)
    assert await _events(repos, "self_permission_change_blocked") == 1


async def test_admin_cannot_grant_permission_he_lacks(db, repos, services, admin, user) -> None:
    """لا يمنح الأدمن صلاحية لا يملكها (`backup.create` حصرية للأعلى)."""
    await _grant_role_perm(db, repos, "admin", Permission.ADMINS_MANAGE)
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_user_permission(admin, user.id, Permission.BACKUP_CREATE, allow=True)
    assert await _events(repos, "grant_unowned_permission_blocked") == 1


async def test_admin_cannot_grant_dangerous_permission_even_if_owned(db, repos, services, admin, user) -> None:
    """الصلاحية الخطِرة (اعتماد الشحن) يمنحها الأدمن الأعلى فقط ولو كان المانح يملكها."""
    await _grant_role_perm(db, repos, "admin", Permission.ADMINS_MANAGE)
    assert await services.auth.has_permission(admin, Permission.PAYMENTS_APPROVE)
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_user_permission(admin, user.id, Permission.PAYMENTS_APPROVE, allow=True)
    assert await _events(repos, "grant_dangerous_permission_blocked") == 1


async def test_admin_can_grant_safe_owned_permission(db, repos, services, admin, user) -> None:
    """منح صلاحية عادية يملكها المانح مسموح ويُدقَّق."""
    await _grant_role_perm(db, repos, "admin", Permission.ADMINS_MANAGE)
    await services.auth.set_user_permission(admin, user.id, Permission.ORDERS_VIEW, allow=True)
    assert await services.auth.has_permission(user, Permission.ORDERS_VIEW)
    assert await repos.audit.count_by_action_prefix("admins.permission.override") == 1


async def test_super_admin_can_grant_dangerous_permission(services, super_admin, user) -> None:
    """الأدمن الأعلى يمنح الخطِرة عند الحاجة."""
    await services.auth.set_user_permission(super_admin, user.id, Permission.PAYMENTS_APPROVE, allow=True)
    assert await services.auth.has_permission(user, Permission.PAYMENTS_APPROVE)


async def test_unknown_permission_code_rejected(services, super_admin, user) -> None:
    """كود صلاحية غير معرَّف يُرفض بدل أن يُخزَّن بصمت."""
    with pytest.raises(ValidationError):
        await services.auth.set_user_permission(super_admin, user.id, "made.up.permission", allow=True)


# ================================== الحظر ================================== #


async def test_cannot_ban_self(db, repos, services, admin) -> None:
    """لا يحظر الأدمن نفسه."""
    with pytest.raises(ValidationError):
        await services.users.ban(admin, admin.id, "تجربة")
    assert await _events(repos, "self_ban_blocked") == 1
    assert not (await repos.users.get_by_id(admin.id)).is_banned


async def test_cannot_ban_super_admin(db, repos, services, admin, super_admin) -> None:
    """لا يُحظر الأدمن الأعلى مباشرة (حتى بمن يملك الصلاحية)."""
    with pytest.raises(ValidationError):
        await services.users.ban(admin, super_admin.id, "تجربة")
    assert not (await repos.users.get_by_id(super_admin.id)).is_banned
    assert await _events(repos, "super_admin_ban_blocked") == 1


async def test_admin_cannot_ban_peer_admin(db, repos, services, admin) -> None:
    """التسلسل الهرمي: لا يحظر الأدمن زميله."""
    peer = await _make(db, repos, 5005, "admin", "peer2")
    with pytest.raises(PermissionDeniedError):
        await services.users.ban(admin, peer.id, "تجربة")
    assert await _events(repos, "hierarchy_denied") == 1
    assert not (await repos.users.get_by_id(peer.id)).is_banned


async def test_admin_cannot_unban_peer_banned_by_super(db, repos, services, admin, super_admin) -> None:
    """أدمن عادي لا يلغي حظراً أوقعه الأدمن الأعلى على زميله."""
    peer = await _make(db, repos, 5007, "admin", "peer3")
    async with db.transaction() as tx:
        await repos.users.set_ban(tx, peer.id, banned=True, reason="تحقيق")
    with pytest.raises(PermissionDeniedError):
        await services.users.unban(admin, peer.id)
    assert (await repos.users.get_by_id(peer.id)).is_banned


async def test_admin_can_ban_regular_user(db, repos, services, admin, user) -> None:
    """المسار الطبيعي: أدمن يحظر مستخدماً عادياً."""
    await services.users.ban(admin, user.id, "مخالفة")
    assert (await repos.users.get_by_id(user.id)).is_banned


async def test_support_role_has_no_security_access(services, db, repos) -> None:
    """الدعم الفني لا يرى ولا يدير الأمان."""
    support = await _make(db, repos, 5006, "support", "agent")
    with pytest.raises(PermissionDeniedError):
        await services.security.counters(support)
    with pytest.raises(PermissionDeniedError):
        await services.security.clear_block(support, 123, None)
```

### `tests/integration/test_money_guards_phase9.py`  ·  جديد  ·  192 سطراً

الإجراء الذاتي وover-credit وسقوف التسوية.

```python
"""اختبارات الحواجز المالية: التنفيذ الذاتي، الاعتماد الزائد، سقوف التسوية (المرحلة 9)."""

from __future__ import annotations

import pytest

from core.enums import OrderStatus, PaymentStatus
from core.exceptions import InvalidAmountError, PermissionDeniedError, ValidationError
from database.models import User
from services import ServiceContainer

pytestmark = pytest.mark.asyncio


async def _event_count(repos, event: str) -> int:
    """عدد مرات حدث أمني."""
    return await repos.audit.count_by_action_prefix(f"security.{event}")


async def _balance(services: ServiceContainer, user: User) -> int:
    """رصيد المستخدم بالنقاط."""
    return await services.wallet.balance_units(user.id)


async def _fund(services: ServiceContainer, target: User, by: User, units: int, token: str) -> None:
    """شحن رصيد يدوي بيد أدمن أعلى (لا يخضع للسقوف)."""
    await services.wallet.adjust_balance(
        target=target, amount_units=units, admin=by, reason="تمويل اختبار", credit=True, token=token
    )


# ============================ اعتماد الشحن ============================ #


async def test_admin_cannot_approve_own_payment(services, repos, admin, payment_method) -> None:
    """الأدمن لا يعتمد شحنته هو (عينان على كل عملية) ولا يتغير رصيده."""
    payment = await services.payments.create_payment(
        admin, method_id=payment_method.id, raw_amount="5", transaction_reference="SELF-1",
        proof_file_id="f", proof_file_type="photo",
    )
    with pytest.raises(PermissionDeniedError):
        await services.payments.approve(admin, payment.id)
    assert await _balance(services, admin) == 0
    assert (await repos.payments.get(payment.id)).status == PaymentStatus.PENDING
    assert await _event_count(repos, "self_action_blocked") == 1


async def test_other_admin_can_approve_that_payment(services, admin, super_admin, payment_method) -> None:
    """أدمن آخر يعتمدها بلا مشكلة."""
    payment = await services.payments.create_payment(
        admin, method_id=payment_method.id, raw_amount="5", transaction_reference="SELF-2",
        proof_file_id="f", proof_file_type="photo",
    )
    await services.payments.approve(super_admin, payment.id)
    assert await _balance(services, admin) == 50_000


async def test_self_dealing_can_be_disabled_by_setting(services, admin, super_admin, payment_method) -> None:
    """التعطيل الصريح بالإعداد (لبيئات الاختبار) يسمح، والإعداد نفسه مدقَّق."""
    await services.settings.set("security_block_self_actions", "false", admin_id=super_admin.id)
    payment = await services.payments.create_payment(
        admin, method_id=payment_method.id, raw_amount="5", transaction_reference="SELF-3",
        proof_file_id="f", proof_file_type="photo",
    )
    await services.payments.approve(admin, payment.id)
    assert await _balance(services, admin) == 50_000


async def test_over_credit_is_rejected_and_logged(services, repos, user, admin, payment_method) -> None:
    """لا يُعتمد مبلغ أكبر مما حوّله العميل، ويبقى الطلب معلّقاً."""
    payment = await services.payments.create_payment(
        user, method_id=payment_method.id, raw_amount="5", transaction_reference="OVER-1",
        proof_file_id="f", proof_file_type="photo",
    )
    with pytest.raises(ValidationError):
        await services.payments.approve(admin, payment.id, credited_units=payment.amount_units + 1)
    assert await _balance(services, user) == 0
    assert (await repos.payments.get(payment.id)).status == PaymentStatus.PENDING
    assert await _event_count(repos, "over_credit_blocked") == 1


async def test_partial_credit_below_amount_is_allowed(services, user, admin, payment_method) -> None:
    """اعتماد مبلغ أقل (خصم رسوم/فرق حوالة) مسموح."""
    payment = await services.payments.create_payment(
        user, method_id=payment_method.id, raw_amount="5", transaction_reference="PART-1",
        proof_file_id="f", proof_file_type="photo",
    )
    await services.payments.approve(admin, payment.id, credited_units=30_000)
    assert await _balance(services, user) == 30_000


# ============================== التسوية اليدوية ============================== #


async def test_admin_cannot_adjust_own_balance(services, repos, admin) -> None:
    """لا تسوية يدوية على حساب المنفِّذ نفسه."""
    with pytest.raises(PermissionDeniedError):
        await services.wallet.adjust_balance(
            target=admin, amount_units=10_000, admin=admin, reason="تجربة", credit=True, token="s1"
        )
    assert await _balance(services, admin) == 0
    assert await _event_count(repos, "self_action_blocked") == 1


async def test_single_adjust_cap_for_admin(services, repos, user, admin, super_admin) -> None:
    """يتجاوز الأدمن سقف العملية الواحدة ⇒ رفض + حدث أمني + رصيد ثابت."""
    await services.settings.set("admin_adjust_max_units", "100000", admin_id=super_admin.id)
    await services.wallet.adjust_balance(
        target=user, amount_units=100_000, admin=admin, reason="ضمن السقف", credit=True, token="c1"
    )
    with pytest.raises(InvalidAmountError):
        await services.wallet.adjust_balance(
            target=user, amount_units=100_001, admin=admin, reason="فوق السقف", credit=True, token="c2"
        )
    assert await _balance(services, user) == 100_000
    assert await _event_count(repos, "adjust_cap_exceeded") == 1


async def test_daily_adjust_cap_counts_credits_and_debits(services, repos, user, admin, super_admin) -> None:
    """السقف اليومي يجمع الإضافة والخصم معاً."""
    await services.settings.set("admin_adjust_max_units", "100000", admin_id=super_admin.id)
    await services.settings.set("admin_adjust_daily_max_units", "150000", admin_id=super_admin.id)
    await services.wallet.adjust_balance(
        target=user, amount_units=100_000, admin=admin, reason="أولى", credit=True, token="d1"
    )
    with pytest.raises(InvalidAmountError):
        await services.wallet.adjust_balance(
            target=user, amount_units=60_000, admin=admin, reason="تتجاوز اليومي", credit=False, token="d2"
        )
    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="تكمل اليومي", credit=False, token="d3"
    )
    assert await _balance(services, user) == 50_000
    assert await _event_count(repos, "adjust_daily_cap_exceeded") == 1


async def test_super_admin_not_subject_to_caps(services, user, super_admin) -> None:
    """الأدمن الأعلى معفى من السقوف."""
    await services.settings.set("admin_adjust_max_units", "1000", admin_id=super_admin.id)
    await _fund(services, user, super_admin, 5_000_000, "sa1")
    assert await _balance(services, user) == 5_000_000


async def test_zero_cap_means_unlimited(services, user, admin, super_admin) -> None:
    """السقف صفر = بلا سقف (مسموح صراحةً بقرار الأدمن الأعلى، وتنبّه شاشة الأمان)."""
    await services.settings.set("admin_adjust_max_units", "0", admin_id=super_admin.id)
    await services.settings.set("admin_adjust_daily_max_units", "0", admin_id=super_admin.id)
    await services.wallet.adjust_balance(
        target=user, amount_units=9_000_000_000, admin=admin, reason="كبير", credit=True, token="z1"
    )
    assert await _balance(services, user) == 9_000_000_000


# ============================ عمليات الطلبات ============================ #


async def _order_for(services: ServiceContainer, owner: User, funder: User, mock_service):
    """إنشاء طلب لمالك محدد بعد تمويله."""
    await _fund(services, owner, funder, 100_000, f"fund-{owner.id}")
    return await services.orders.create_order(
        owner, service_id=mock_service.id, link="https://instagram.com/self_test", quantity=1000
    )


async def test_admin_cannot_cancel_or_fail_or_override_own_order(
    services, repos, admin, super_admin, mock_service
) -> None:
    """الأدمن لا يلغي/يفشّل/يغيّر حالة طلب يخصّه (لا استرجاع لنفسه)."""
    order = await _order_for(services, admin, super_admin, mock_service)
    balance_after_order = await _balance(services, admin)

    with pytest.raises(PermissionDeniedError):
        await services.orders.admin_cancel(admin, order.id, "إلغاء ذاتي")
    with pytest.raises(PermissionDeniedError):
        await services.orders.admin_mark_failed(admin, order.id, "فشل ذاتي")
    await services.auth.set_user_permission(super_admin, admin.id, "orders.status.override", allow=True)
    with pytest.raises(PermissionDeniedError):
        await services.orders.admin_override_status(admin, order.id, OrderStatus.FAILED, "تجاوز ذاتي")

    assert await _balance(services, admin) == balance_after_order
    assert (await repos.orders.get(order.id)).status == OrderStatus.PENDING
    assert await _event_count(repos, "self_action_blocked") == 3


async def test_other_admin_can_cancel_that_order_with_refund(
    services, admin, super_admin, mock_service
) -> None:
    """أدمن آخر يلغي الطلب فيُرجَع المبلغ لصاحبه (المسار الطبيعي لم يتأثر)."""
    order = await _order_for(services, admin, super_admin, mock_service)
    before = await _balance(services, admin)
    await services.orders.admin_cancel(super_admin, order.id, "إلغاء من أدمن آخر")
    assert await _balance(services, admin) == before + order.cost_units
```

### `tests/integration/test_security_phase9.py`  ·  جديد  ·  443 سطراً

خدمة الأمان والشاشة والطبقة الوسيطة وتنبيه الأخطاء وإعادة الجدولة.

```python
"""
اختبارات المرحلة 9 — شاشة الأمان، الحدّ من الإساءة، تنبيه الأخطاء، إعادة الجدولة الحيّة.

ما تغطيه:
    1. خدمة الأمان: العدّادات، الأحداث، الفريق، فحوص الوضع، رفع الإيقاف + الصلاحيات.
    2. شاشات اللوحة: كل زر يعمل، وزر رفع الإيقاف لا يظهر ولا يُنفَّذ بلا `security.manage`.
    3. الطبقة الوسيطة: الإيقاف المؤقت الصامت، السلة الحسّاسة، تمييز الأدمن.
    4. تنبيه الأخطاء: تهدئة، تنقية، تعطيل، وعدم تسريب نص المستخدم.
    5. إعادة جدولة المهام فور تعديل الإعداد بلا إعادة تشغيل وبلا فقدان العدّادات.
"""

from __future__ import annotations

import pytest
from telegram.ext import ApplicationBuilder, ApplicationHandlerStop

from core.exceptions import PermissionDeniedError
from handlers.admin import security as security_screens
from handlers.common.errors import _describe_update, _error_fingerprint, error_handler
from jobs import reschedule_for_setting, schedule_jobs
from jobs.runner import JobRegistry
from keyboards.callback_data import NS_ADM_SEC, NS_FLOW, pack
from middlewares.context import UserContextMiddleware
from middlewares.rate_limit import AbuseGuard, RateLimiter
from services.security_service import LEVEL_BAD, LEVEL_OK, LEVEL_WARN, EnvPosture
from tests.integration.test_user_interface import bot, context, load_user, press  # noqa: F401
from tests.telegram_fakes import FakeBot, FakeContext, make_callback_update, make_message_update
from utils.fs_security import PathCheck

pytestmark = pytest.mark.asyncio


class Clock:
    """ساعة يدوية للتحكم بالزمن دون انتظار."""

    def __init__(self) -> None:
        self.now = 5000.0

    def __call__(self) -> float:
        return self.now


async def _log_event(services, event: str, user_id: int | None, **details) -> None:
    """تسجيل حدث أمني تجريبي."""
    await services.audit.log_security_event(event=event, user_id=user_id, target_type="user", target_id=user_id, details=details)


# ============================== خدمة الأمان ============================== #


async def test_counters_reflect_recent_events(services, user, admin, super_admin) -> None:
    """العدّادات تحسب كل فئة بحسب أحداثها."""
    await services.audit.log_permission_denied(user_id=user.id, permission="orders.cancel", context="t")
    await services.audit.log_permission_denied(user_id=user.id, permission="users.ban", context="t")
    await _log_event(services, "rate_limit_block", user.id)
    await _log_event(services, "hierarchy_denied", admin.id)
    await _log_event(services, "over_credit_blocked", admin.id)
    await _log_event(services, "adjust_cap_exceeded", admin.id)

    counters = await services.security.counters(super_admin)
    assert counters.permission_denied == 2
    assert counters.rate_limit_blocks == 1
    assert counters.rbac_blocks == 1
    assert counters.money_blocks == 2
    assert counters.total_events == 6
    assert counters.top_denied == ((user.id, 2),)


async def test_events_are_paginated_newest_first(services, user, super_admin) -> None:
    """صفحات الأحداث: الأحدث أولاً وعدد الصفحات صحيح، والصفحة الخارجة عن النطاق تُقصّ."""
    for index in range(11):
        await _log_event(services, "hierarchy_denied", user.id, n=index)
    first = await services.security.events(super_admin, page=1, page_size=5)
    assert first.total == 11 and first.total_pages == 3 and len(first.items) == 5
    assert first.items[0].id > first.items[-1].id
    last = await services.security.events(super_admin, page=99, page_size=5)
    assert last.page == 3 and len(last.items) == 1
    assert first.names[user.id]


async def test_events_only_include_security_prefix(services, user, super_admin, admin) -> None:
    """الأحداث الأمنية لا تخلط معها سجلات التدقيق العادية."""
    await services.users.ban(admin, user.id, "سبب كافٍ")           # سجل users.ban عادي
    result = await services.security.events(super_admin, page=1)
    assert all(item.action.startswith("security.") for item in result.items)


async def test_team_lists_staff_with_overrides(services, super_admin, admin, user) -> None:
    """الفريق يعرض غير العملاء مرتباً بالدور مع عدد الاستثناءات."""
    await services.auth.set_user_permission(super_admin, admin.id, "backup.create", allow=True)
    team = await services.security.team(super_admin)
    names = [(member.user.id, member.overrides) for member in team]
    assert names[0][0] == super_admin.id
    assert (admin.id, 1) in names
    assert user.id not in [member.user.id for member in team]


async def test_posture_healthy_defaults_have_no_bad_items(services, super_admin) -> None:
    """الوضع الافتراضي: لا «خطر»، وبه تنبيه الأدمن الأعلى الوحيد."""
    checks = await services.security.posture(super_admin, EnvPosture(alert_chat_set=True))
    assert not [c for c in checks if c.level == LEVEL_BAD]
    titles = {c.title: c for c in checks}
    assert titles["الأدمن الأعلى"].level == LEVEL_WARN          # حساب واحد فقط
    assert titles["منع التنفيذ الذاتي"].level == LEVEL_OK


async def test_posture_flags_weak_configuration(services, repos, db, super_admin, admin) -> None:
    """الإعدادات الضعيفة تظهر: تعطيل four-eyes، بلا سقوف، مزود http، استثناء خطر، ملف مفتوح."""
    await services.settings.set("security_block_self_actions", "false", admin_id=super_admin.id)
    await services.settings.set("admin_adjust_max_units", "0", admin_id=super_admin.id)
    await services.settings.set("admin_adjust_daily_max_units", "0", admin_id=super_admin.id)
    await services.settings.set("maintenance_mode", "true", admin_id=super_admin.id)
    await services.auth.set_user_permission(super_admin, admin.id, "backup.create", allow=True)
    async with db.transaction() as tx:
        await repos.providers.create(
            tx, name="Insecure", api_url="http://plain.example.com/api", api_key_enc="x", api_key_hint="1234"
        )
    insecure_file = PathCheck(path=__import__("pathlib").Path("/x/.env"), label="ملف البيئة .env (سر)", mode=0o644, insecure=True)

    checks = {c.title: c for c in await services.security.posture(
        super_admin, EnvPosture(bot_token_set=True, encryption_key_set=False, path_checks=(insecure_file,))
    )}
    assert checks["منع التنفيذ الذاتي"].level == LEVEL_WARN
    assert checks["سقف التسوية اليدوية"].level == LEVEL_WARN
    assert checks["اتصال المزودين"].level == LEVEL_BAD
    assert checks["الاستثناءات الفردية"].level == LEVEL_WARN
    assert checks["وضع الصيانة"].level == LEVEL_WARN
    assert checks["صلاحيات الملفات"].level == LEVEL_WARN
    assert checks["مفتاح تشفير مفاتيح المزودين"].level == LEVEL_BAD


async def test_clear_block_requires_manage_and_is_audited(services, repos, user, admin, super_admin) -> None:
    """رفع الإيقاف يحتاج `security.manage` (الأدمن العادي مرفوض) ويُدقَّق."""
    guard = AbuseGuard(clock=Clock())
    guard.record_violation(user.telegram_id, strikes_limit=1, block_seconds=300)

    with pytest.raises(PermissionDeniedError):
        await services.security.clear_block(admin, user.telegram_id, guard)
    assert guard.is_blocked(user.telegram_id)

    assert await services.security.clear_block(super_admin, user.telegram_id, guard) is True
    assert not guard.is_blocked(user.telegram_id)
    assert await repos.audit.count_by_action_prefix("security.block_cleared") == 1
    assert await services.security.clear_block(super_admin, user.telegram_id, guard) is False


async def test_blocked_users_listing(services, user, admin) -> None:
    """قائمة الموقوفين تعرض الاسم والمتبقي وعدد المخالفات."""
    guard = AbuseGuard(clock=Clock())
    guard.record_violation(user.telegram_id, strikes_limit=1, block_seconds=120)
    [item] = await services.security.blocked_users(admin, guard)
    assert item.telegram_id == user.telegram_id and item.name == "@tester"
    assert 100 < item.seconds_left <= 121 and item.strikes == 1
    assert await services.security.blocked_users(admin, None) == []


# ============================== شاشات اللوحة ============================== #


async def test_security_home_screen_renders_for_admin(bot, context, services, admin) -> None:  # noqa: F811
    """الأدمن يفتح الشاشة الرئيسية فيرى العدّادات والفحوص وأزرار التنقل."""
    await load_user(bot, context, admin)
    await _log_event(services, "hierarchy_denied", admin.id)
    await press(bot, context, security_screens.home_screen, "sc:home", admin.telegram_id)
    text = bot.last.text
    assert "الأمان" in text and "آخر 24 ساعة" in text and "وضع الأمان" in text
    expected = {pack(NS_ADM_SEC, "events", 1), pack(NS_ADM_SEC, "blocks"), pack(NS_ADM_SEC, "team"), pack(NS_ADM_SEC, "home")}
    assert expected <= set(bot.last.buttons)


async def test_security_screens_denied_without_permission(bot, context, services, user) -> None:  # noqa: F811
    """العميل العادي لا يفتح أي شاشة أمان."""
    await load_user(bot, context, user)
    for action, handler in (
        ("home", security_screens.home_screen),
        ("events:1", security_screens.events_screen),
        ("blocks", security_screens.blocks_screen),
        ("team", security_screens.team_screen),
        ("unblock:5", security_screens.unblock_action),
    ):
        bot.clear()
        await press(bot, context, handler, f"sc:{action}", user.telegram_id)
        assert not bot.sent, f"عُرضت شاشة {action} لعميل عادي"


async def test_security_events_and_team_screens(bot, context, services, admin, super_admin) -> None:  # noqa: F811
    """شاشتا الأحداث والفريق تعرضان محتواهما العربي وزر الرجوع."""
    await load_user(bot, context, admin)
    await press(bot, context, security_screens.events_screen, "sc:events:1", admin.telegram_id)
    assert "لا توجد أحداث" in bot.last.text

    await _log_event(services, "self_ban_blocked", admin.id)
    bot.clear()
    await press(bot, context, security_screens.events_screen, "sc:events:1", admin.telegram_id)
    assert "منع حظر النفس" in bot.last.text
    assert pack(NS_ADM_SEC, "home") in bot.last.buttons

    bot.clear()
    await press(bot, context, security_screens.team_screen, "sc:team", admin.telegram_id)
    assert "أدمن أعلى" in bot.last.text and "أدمن" in bot.last.text


async def test_blocks_screen_unblock_button_only_for_manager(bot, context, services, user, admin, super_admin) -> None:  # noqa: F811
    """زر رفع الإيقاف يظهر للأدمن الأعلى فقط، وضغطه من الأدمن العادي لا يرفع شيئاً."""
    guard = AbuseGuard(clock=Clock())
    guard.record_violation(user.telegram_id, strikes_limit=1, block_seconds=300)
    context.bot_data["abuse_guard"] = guard
    unblock_data = f"sc:unblock:{user.telegram_id}"
    unblock_button = pack(NS_ADM_SEC, "unblock", user.telegram_id)

    await load_user(bot, context, admin)
    await press(bot, context, security_screens.blocks_screen, "sc:blocks", admin.telegram_id)
    assert "@tester" in bot.last.text
    assert unblock_button not in bot.last.buttons

    bot.clear()
    await press(bot, context, security_screens.unblock_action, unblock_data, admin.telegram_id)
    assert guard.is_blocked(user.telegram_id), "رُفع الإيقاف بلا صلاحية"

    context.user_data.clear()
    await load_user(bot, context, super_admin)
    await press(bot, context, security_screens.blocks_screen, "sc:blocks", super_admin.telegram_id)
    assert unblock_button in bot.last.buttons

    bot.clear()
    await press(bot, context, security_screens.unblock_action, unblock_data, super_admin.telegram_id)
    assert not guard.is_blocked(user.telegram_id)
    assert "رُفع الإيقاف" in bot.last.text and "لا أحد موقوف" in bot.last.text


# ============================== الطبقة الوسيطة ============================== #


async def _tap(middleware, bot, context, *, user_id: int, text: str = "مرحبا", data: str | None = None) -> bool:
    """تمرير تحديث عبر الطبقة الوسيطة؛ True = مرّ، False = أُوقف."""
    update = (
        make_callback_update(bot, data=data, user_id=user_id)
        if data
        else make_message_update(bot, text=text, user_id=user_id)
    )
    try:
        await middleware(update, context)
    except ApplicationHandlerStop:
        return False
    return True


async def test_middleware_warns_then_blocks_then_ignores_silently(bot, context, services, repos, super_admin) -> None:  # noqa: F811
    """حد → تحذير → إيقاف مؤقت مُدقَّق → تجاهل صامت → عودة بعد رفع الإيقاف/انتهاء المدة."""
    await services.settings.set("rate_limit_actions_per_minute", "3", admin_id=super_admin.id)
    await services.settings.set("rate_limit_strikes_before_block", "2", admin_id=super_admin.id)
    await services.settings.set("rate_limit_block_minutes", "1", admin_id=super_admin.id)
    clock = Clock()
    guard = AbuseGuard(clock=clock)
    middleware = UserContextMiddleware(RateLimiter(clock=clock), guard)
    uid = 424_242

    assert all([await _tap(middleware, bot, context, user_id=uid) for _ in range(3)])
    bot.clear()
    assert await _tap(middleware, bot, context, user_id=uid) is False         # مخالفة 1 ⇒ تحذير
    assert "أبطئ" in bot.last.text

    bot.clear()
    clock.now += 11                                                           # بعد تهدئة التحذير لكن داخل النافذة
    assert await _tap(middleware, bot, context, user_id=uid) is False         # مخالفة 2 ⇒ إيقاف
    assert "إيقاف استخدامك" in bot.last.text
    assert guard.is_blocked(uid)
    assert await repos.audit.count_by_action_prefix("security.rate_limit_block") == 1

    bot.clear()
    assert await _tap(middleware, bot, context, user_id=uid) is False         # تجاهل صامت
    assert not bot.sent and not bot.answers

    clock.now += 61                                                           # انتهت مدة الإيقاف والنافذة
    assert await _tap(middleware, bot, context, user_id=uid) is True


async def test_middleware_sensitive_bucket_is_tighter(bot, context, services, super_admin) -> None:  # noqa: F811
    """زر التأكيد يخضع لحد أضيق من التصفح، ولا يستهلك التصفح العادي حصته."""
    await services.settings.set("rate_limit_sensitive_per_minute", "1", admin_id=super_admin.id)
    clock = Clock()
    middleware = UserContextMiddleware(RateLimiter(clock=clock), AbuseGuard(clock=clock))
    confirm = pack(NS_FLOW, "confirm")
    uid = 535_353

    assert await _tap(middleware, bot, context, user_id=uid, data=confirm) is True
    assert await _tap(middleware, bot, context, user_id=uid, data=confirm) is False
    assert await _tap(middleware, bot, context, user_id=uid, text="تصفح عادي") is True


async def test_middleware_staff_gets_higher_limits(bot, context, services, admin, super_admin) -> None:  # noqa: F811
    """الفريق الإداري له حد عام أعلى، فلا يُخنق أثناء التنقل بين الشاشات."""
    await services.settings.set("rate_limit_actions_per_minute", "3", admin_id=super_admin.id)
    clock = Clock()
    middleware = UserContextMiddleware(RateLimiter(clock=clock), AbuseGuard(clock=clock))
    results = [await _tap(middleware, bot, context, user_id=admin.telegram_id) for _ in range(12)]
    assert all(results)
    regular = [await _tap(middleware, bot, context, user_id=616_161) for _ in range(5)]
    assert regular == [True, True, True, False, False]


# ============================== تنبيه الأخطاء ============================== #


def _raise_here(message: str) -> BaseException:
    """رفع واستلام استثناء حقيقي ليحمل traceback (مطلوب للبصمة)."""
    try:
        raise RuntimeError(message)
    except RuntimeError as exc:
        return exc


def _raise_there(message: str) -> BaseException:
    """نفس النوع من موضع مختلف ⇒ بصمة مختلفة."""
    try:
        raise RuntimeError(message)
    except RuntimeError as exc:
        return exc


async def _alerts_for(services, user) -> list:
    """إشعارات «خطأ غير متوقع» التي وصلت مستخدماً."""
    items = await services.repos.notifications.list_for_user(user.id)
    return [item for item in items if "خطأ غير متوقع" in item.title]


async def test_error_alert_goes_to_log_viewers_with_sanitized_snippet(services, admin, super_admin, user) -> None:
    """التنبيه يصل من يملك `logs.view` فقط، منقّى، بلا traceback."""
    fake_bot = FakeBot()
    ctx = FakeContext(fake_bot, services)
    ctx.error = _raise_here("فشل api_key=SUPERSECRET12345 أثناء الإرسال")
    await error_handler(None, ctx)

    admin_alerts = await _alerts_for(services, admin)
    assert len(admin_alerts) == 1 and len(await _alerts_for(services, super_admin)) == 1
    assert not await _alerts_for(services, user)
    body = admin_alerts[0].message
    assert "RuntimeError" in body and "SUPERSECRET12345" not in body and "Traceback" not in body


async def test_error_alert_is_throttled_per_fingerprint(services, admin) -> None:
    """الخطأ نفسه لا يُنبَّه به ثانية في فترة التهدئة، والخطأ من موضع آخر يُنبَّه."""
    ctx = FakeContext(FakeBot(), services)
    for _ in range(3):
        ctx.error = _raise_here("نفس الخطأ")
        await error_handler(None, ctx)
    assert len(await _alerts_for(services, admin)) == 1

    ctx.error = _raise_there("خطأ من مكان آخر")
    await error_handler(None, ctx)
    assert len(await _alerts_for(services, admin)) == 2
    assert _error_fingerprint(_raise_here("a")) != _error_fingerprint(_raise_there("a"))


async def test_error_alert_can_be_disabled(services, admin, super_admin) -> None:
    """الإعداد يعطّل التنبيه، لكن الخطأ يبقى مخزَّناً في السجل."""
    await services.settings.set("error_alert_enabled", "false", admin_id=super_admin.id)
    ctx = FakeContext(FakeBot(), services)
    ctx.error = _raise_here("خطأ صامت")
    await error_handler(None, ctx)
    assert not await _alerts_for(services, admin)
    assert await services.repos.error_logs.count_since("2000-01-01T00:00:00Z") == 1


async def test_error_handler_does_not_log_plain_user_text(bot) -> None:  # noqa: F811
    """وصف التحديث لا يحمل نص المستخدم العادي (قد يكون مفتاح API) لكنه يحمل اسم الأمر."""
    secret_text = make_message_update(bot, text="my-provider-key-ABCDEF123456", user_id=5)
    command = make_message_update(bot, text="/admin now", user_id=5)
    assert "ABCDEF123456" not in _describe_update(secret_text)
    assert "/admin" in _describe_update(command)


# ====================== إعادة الجدولة الحيّة للمهام ====================== #


def _interval_of(application, name: str) -> float:
    """فترة تكرار مهمة مجدولة فعلاً على JobQueue."""
    [job] = application.job_queue.get_jobs_by_name(name)
    return job.job.trigger.interval.total_seconds()


@pytest.fixture
def app_with_jobs(services):
    """تطبيق حقيقي (غير مشغَّل) للتحقق من الجدولة الفعلية."""
    return ApplicationBuilder().token("123456789:AAJobsTestDummyTokenNotUsedAtAll").build()


async def test_changing_interval_setting_reschedules_job_live(app_with_jobs, services, super_admin) -> None:
    """تعديل فترة المتابعة من الإعدادات يغيّر جدول المهمة فوراً مع إبقاء عدّاداتها."""
    registry = JobRegistry()
    try:
        await schedule_jobs(app_with_jobs, services, registry=registry)
        assert _interval_of(app_with_jobs, "orders_check") == 120
        registry.stats["orders_check"].runs = 7
        submit_before = _interval_of(app_with_jobs, "orders_submit")

        await services.settings.set("order_check_interval_seconds", "300", admin_id=super_admin.id)

        assert _interval_of(app_with_jobs, "orders_check") == 300
        assert len(app_with_jobs.job_queue.get_jobs_by_name("orders_check")) == 1, "تكرر تسجيل المهمة"
        assert registry.stats["orders_check"].interval_seconds == 300
        assert registry.stats["orders_check"].runs == 7, "ضاعت عدّادات المهمة"
        assert _interval_of(app_with_jobs, "orders_submit") == submit_before, "تأثرت مهمة غير معنية"
    finally:
        await app_with_jobs.shutdown()


async def test_unrelated_setting_does_not_touch_jobs(app_with_jobs, services, super_admin) -> None:
    """مفتاح لا يخص المهام لا يعيد جدولة شيء."""
    registry = JobRegistry()
    try:
        await schedule_jobs(app_with_jobs, services, registry=registry)
        assert await reschedule_for_setting(app_with_jobs, services, "bot_name", registry=registry) == []
        await services.settings.set("bot_name", "متجري", admin_id=super_admin.id)
        assert len(app_with_jobs.job_queue.jobs()) == 11
    finally:
        await app_with_jobs.shutdown()


async def test_daily_job_hour_change_reschedules(app_with_jobs, services, super_admin) -> None:
    """تغيير ساعة الملخص اليومي يعيد جدولة المهمة اليومية."""
    registry = JobRegistry()
    try:
        await schedule_jobs(app_with_jobs, services, registry=registry)
        await services.settings.set("admin_digest_hour", "7", admin_id=super_admin.id)
        [job] = app_with_jobs.job_queue.get_jobs_by_name("admin_daily_digest")
        assert "07:00" in registry.stats["admin_daily_digest"].schedule_text
        assert job is not None
    finally:
        await app_with_jobs.shutdown()


async def test_failure_threshold_change_reinstalls_all_jobs_once_each(app_with_jobs, services, super_admin) -> None:
    """تغيير عتبة التنبيه يعيد تركيب كل المهام بلا تكرار أو فقدان."""
    registry = JobRegistry()
    try:
        await schedule_jobs(app_with_jobs, services, registry=registry)
        await services.settings.set("job_failure_alert_threshold", "5", admin_id=super_admin.id)
        assert len(app_with_jobs.job_queue.jobs()) == 11
        names = [job.name for job in app_with_jobs.job_queue.jobs()]
        assert len(names) == len(set(names))
    finally:
        await app_with_jobs.shutdown()
```

### `tests/integration/test_ssrf_scripts_phase9.py`  ·  جديد  ·  155 سطراً

SSRF في العميل والخدمة + سكربتات `create_admin`/`security_check`.

```python
"""اختبارات حماية SSRF عبر مسار المزودين، وحمايات سكربتات التشغيل (المرحلة 9)."""

from __future__ import annotations

import stat
from pathlib import Path

import httpx
import pytest

from core.exceptions import ProviderPermanentError, ValidationError
from database.database import Database
from database.migrator import Migrator
from database.repositories import Repositories
from integrations.providers.perfect_panel import PerfectPanelClient
from utils import net_security

pytestmark = pytest.mark.asyncio


# ================================ SSRF ================================ #


@pytest.mark.parametrize(
    "url",
    [
        "http://panel.example.com/api/v2",
        "https://127.0.0.1/api/v2",
        "https://169.254.169.254/latest",
        "https://panel.example.com:8080/api/v2",
        "https://localhost/api",
    ],
)
async def test_create_provider_rejects_unsafe_urls(services, super_admin, url: str) -> None:
    """إنشاء مزود برابط غير آمن يُرفض قبل حفظ أي شيء."""
    with pytest.raises(ValidationError):
        await services.providers.create_provider(
            super_admin, name="Bad", api_url=url, api_key="key-1234567890"
        )
    assert await services.repos.providers.list_all() == []


async def test_create_provider_accepts_public_https(services, super_admin) -> None:
    """رابط https عام صحيح يُقبل (المسار الطبيعي لم يتأثر)."""
    provider = await services.providers.create_provider(
        super_admin, name="Good", api_url="https://panel.example.com/api/v2", api_key="key-1234567890"
    )
    assert provider.api_url == "https://panel.example.com/api/v2"


async def test_real_client_refuses_private_literal_ip_before_any_network() -> None:
    """العميل الحقيقي (بلا حقن) يرفض عنواناً داخلياً قبل أي اتصال أو إرسال للمفتاح."""
    client = PerfectPanelClient(api_url="https://10.0.0.5/api/v2", api_key="key-1234567890")
    with pytest.raises(ProviderPermanentError):
        await client.get_balance()


async def test_real_client_refuses_domain_resolving_to_private(monkeypatch: pytest.MonkeyPatch) -> None:
    """نطاق يبدو عاماً لكنه يُحلّ لعنوان داخلي (DNS rebinding الساذج) يُرفض."""

    async def private_resolver(host: str) -> list[str]:
        return ["192.168.1.20"]

    monkeypatch.setattr(net_security, "_system_resolver", private_resolver)
    client = PerfectPanelClient(api_url="https://evil.example.com/api/v2", api_key="key-1234567890")
    with pytest.raises(ProviderPermanentError):
        await client.get_balance()


async def test_injected_test_client_skips_dns_check() -> None:
    """عميل الاختبار المحقون لا يُفحص DNS له (قرار موثّق) فيعمل بلا شبكة."""
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"balance": "5.0", "currency": "USD"}))
    client = PerfectPanelClient(
        api_url="https://panel.invalid/api/v2", api_key="key-1234567890", client=httpx.AsyncClient(transport=transport)
    )
    balance = await client.get_balance()
    assert balance.amount_units == 50_000 and balance.currency == "USD"


# ============================== سكربت create_admin ============================== #


@pytest.fixture
async def script_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """بيئة معزولة لسكربتات CLI: قاعدة مؤقتة جاهزة المخطط ومتغيرات بيئة موجَّهة لها."""
    db_path = tmp_path / "data" / "smm.db"
    db_path.parent.mkdir()
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "logs" / "bot.log"))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    for key in ("BOT_TOKEN", "ENCRYPTION_KEY", "SUPER_ADMIN_IDS"):
        monkeypatch.delenv(key, raising=False)
    database = Database(db_path)
    await database.connect()
    await Migrator(database).apply_all()
    repos = Repositories(database)
    async with database.transaction() as tx:
        await repos.users.create(tx, telegram_id=111, first_name="Root", role="super_admin")
    await database.close()
    return db_path


async def _role_of(db_path: Path, telegram_id: int) -> str | None:
    """قراءة دور مستخدم من ملف القاعدة مباشرة."""
    database = Database(db_path)
    await database.connect()
    try:
        user = await Repositories(database).users.get_by_telegram_id(telegram_id)
        return user.role if user else None
    finally:
        await database.close()


async def test_create_admin_refuses_to_demote_last_super_admin(script_env, capsys) -> None:
    """تنزيل آخر أدمن أعلى مرفوض بلا --force ويبقى دوره."""
    from scripts.create_admin import run

    assert await run(111, "user") == 1
    assert await _role_of(script_env, 111) == "super_admin"
    assert "آخر أدمن أعلى" in capsys.readouterr().out


async def test_create_admin_force_allows_demotion(script_env) -> None:
    """--force يسمح بالتنزيل عند الضرورة."""
    from scripts.create_admin import run

    assert await run(111, "user", force=True) == 0
    assert await _role_of(script_env, 111) == "user"


async def test_create_admin_allows_demotion_when_another_super_exists(script_env) -> None:
    """بوجود أدمن أعلى آخر فعّال يجوز تنزيل الأول بلا --force."""
    from scripts.create_admin import run

    assert await run(222, "super_admin") == 0
    assert await run(111, "admin") == 0
    assert await _role_of(script_env, 111) == "admin"


@pytest.mark.parametrize("telegram_id", [0, -5])
async def test_create_admin_rejects_non_positive_ids(script_env, telegram_id: int) -> None:
    """معرّف غير موجب خطأ إدخال لا ينشئ مستخدماً."""
    from scripts.create_admin import run

    assert await run(telegram_id, "admin") == 2
    assert await _role_of(script_env, telegram_id) is None


async def test_create_admin_leaves_database_private(script_env) -> None:
    """بعد تشغيل السكربت يبقى ملف القاعدة مقصوراً على المالك."""
    from scripts.create_admin import run

    script_env.chmod(0o644)
    assert await run(333, "admin") == 0
    assert stat.S_IMODE(script_env.stat().st_mode) == 0o600
```

### `tests/integration/test_conversation_settings_phase9.py`  ·  جديد  ·  140 سطراً

مهلة المحادثات، `SettingsService.set`، ترحيل 0008.

```python
"""اختبارات مهلة المحادثات، والتحقق المركزي من الإعدادات، وترحيل الأمان 0008 (المرحلة 9)."""

from __future__ import annotations

import pytest
from telegram.ext import ConversationHandler

from core.exceptions import ValidationError
from core.permissions import Permission
from handlers.common.conversation import (
    CONVERSATION_TIMEOUT_SECONDS,
    FLOW_DATA_KEYS,
    conversation,
    on_conversation_timeout,
)
from handlers.registry import build_handlers
from tests.telegram_fakes import FakeBot, FakeContext, make_message_update

pytestmark = pytest.mark.asyncio


# ============================== مهلة المحادثات ============================== #


def _all_conversations() -> list[ConversationHandler]:
    """كل المحادثات المسجَّلة فعلاً في التطبيق."""
    return [h for _group, h in build_handlers() if isinstance(h, ConversationHandler)]


async def test_every_conversation_has_uniform_timeout_and_timeout_state() -> None:
    """لا محادثة تشذّ عن السياسة: مهلة 15 دقيقة وحالة TIMEOUT مسجَّلة."""
    conversations = _all_conversations()
    assert len(conversations) == 29
    for handler in conversations:
        assert handler.conversation_timeout == CONVERSATION_TIMEOUT_SECONDS == 900, handler.name
        assert ConversationHandler.TIMEOUT in handler.states, f"{handler.name} بلا حالة TIMEOUT"
        assert handler.states[ConversationHandler.TIMEOUT], handler.name


async def test_conversation_factory_rejects_manual_timeout() -> None:
    """تمرير مهلة يدوية ممنوع حتى لا تتفاوت السياسة بين المحادثات."""
    with pytest.raises(ValueError):
        conversation(states={}, entry_points=[], fallbacks=[], conversation_timeout=5)


async def test_timeout_callback_clears_all_flow_data_and_notifies(services) -> None:
    """انتهاء المهلة يمسح بيانات كل المسارات ويُعلم المستخدم، ولا يمسّ بقية user_data."""
    bot = FakeBot()
    context = FakeContext(bot, services)
    for key in FLOW_DATA_KEYS:
        context.user_data[key] = {"pending": True}
    context.user_data["db_user"] = "keep-me"

    update = make_message_update(bot, text="متابعة", user_id=777)
    result = await on_conversation_timeout(update, context)

    assert result == ConversationHandler.END
    assert all(key not in context.user_data for key in FLOW_DATA_KEYS)
    assert context.user_data["db_user"] == "keep-me"
    assert "انتهت" in bot.last.text


# ============================== التحقق من الإعدادات ============================== #


async def test_settings_set_rejects_out_of_range_and_keeps_old_value(services, super_admin) -> None:
    """قيمة خارج النطاق ترفض وتبقى القيمة القديمة (لا تعطيل للحماية بصفر)."""
    before = await services.settings.get_int("rate_limit_actions_per_minute", 0)
    with pytest.raises(ValidationError):
        await services.settings.set("rate_limit_actions_per_minute", "0", admin_id=super_admin.id)
    with pytest.raises(ValidationError):
        await services.settings.set("rate_limit_actions_per_minute", "abc", admin_id=super_admin.id)
    assert await services.settings.get_int("rate_limit_actions_per_minute", 0) == before


async def test_settings_set_normalizes_hindi_digits_and_audits(services, repos, super_admin) -> None:
    """الأرقام الهندية تُطبَّع وتُدقَّق العملية بالقيمة قبل وبعد."""
    assert await services.settings.set("rate_limit_actions_per_minute", "٤٠", admin_id=super_admin.id)
    assert await services.settings.get_int("rate_limit_actions_per_minute", 0) == 40
    logs = await repos.audit.list_by_target("setting", "rate_limit_actions_per_minute")
    assert logs and "40" in (logs[0].after_json or "")


async def test_settings_min_max_deposit_order_is_enforced(services, super_admin) -> None:
    """الحد الأدنى للشحن لا يتجاوز الأعلى حتى لو كل قيمة صالحة وحدها."""
    await services.settings.set("max_deposit_units", "1000000", admin_id=super_admin.id)
    with pytest.raises(ValidationError):
        await services.settings.set("min_deposit_units", "2000000", admin_id=super_admin.id)


async def test_settings_listener_called_and_its_failure_does_not_break_save(services, super_admin) -> None:
    """المراقب يُستدعى بعد الحفظ، وفشله لا يُبطل التعديل ولا يخفي الخطأ (يُسجَّل)."""
    seen: list[tuple[str, str]] = []

    async def good(key: str, value: str) -> None:
        seen.append((key, value))

    async def bad(key: str, value: str) -> None:
        raise RuntimeError("مراقب معطوب")

    services.settings.add_listener(bad)
    services.settings.add_listener(good)
    assert await services.settings.set("bot_name", "متجري", admin_id=super_admin.id)
    assert seen == [("bot_name", "متجري")]
    assert await services.settings.get_str("bot_name", "") == "متجري"


async def test_settings_listener_not_called_on_rejected_value(services, super_admin) -> None:
    """القيمة المرفوضة لا تُبلَّغ للمراقبين."""
    calls: list[str] = []

    async def listener(key: str, value: str) -> None:
        calls.append(key)

    services.settings.add_listener(listener)
    with pytest.raises(ValidationError):
        await services.settings.set("admin_digest_hour", "99", admin_id=super_admin.id)
    assert calls == []


# ============================== ترحيل 0008 ============================== #


async def test_migration_0008_seeds_security_permissions_and_settings(db, repos) -> None:
    """الترحيل يزرع صلاحيتي الأمان وإعداداتها بالقيم الافتراضية الآمنة."""
    codes = {row["code"] for row in await repos.rbac.list_permissions()}
    assert {Permission.SECURITY_VIEW, Permission.SECURITY_MANAGE} <= codes

    admin_perms = await repos.rbac.role_permissions("admin")
    super_perms = await repos.rbac.role_permissions("super_admin")
    support_perms = await repos.rbac.role_permissions("support")
    assert Permission.SECURITY_VIEW in admin_perms and Permission.SECURITY_MANAGE not in admin_perms
    assert {Permission.SECURITY_VIEW, Permission.SECURITY_MANAGE} <= super_perms
    assert not ({Permission.SECURITY_VIEW, Permission.SECURITY_MANAGE} & support_perms)

    settings = await repos.settings.as_dict()
    assert settings["security_block_self_actions"] in {"true", "1"}
    assert settings["rate_limit_strikes_before_block"] == "5"
    assert int(settings["admin_adjust_max_units"]) > 0 and int(settings["admin_adjust_daily_max_units"]) > 0
    assert settings["error_alert_enabled"] in {"true", "1"}
```

### `tests/integration/test_no_dead_buttons.py`  ·  مُحدَّث (مقتطف)  ·  611 سطراً

إضافة لوحات الأمان إلى فحص الأزرار.

```python
        # ------------------------- المرحلة 9 ------------------------- #
        ("security_home_kb", admin_kb.security_home_kb()),
        ("security_events_kb", admin_kb.security_events_kb(page=2, total_pages=4)),
        ("security_events_kb_single", admin_kb.security_events_kb(page=1, total_pages=1)),
        ("security_blocks_kb_manager", admin_kb.security_blocks_kb(
            [(111, "@a"), (222, "@b")], {Permission.SECURITY_VIEW, Permission.SECURITY_MANAGE}
        )),
        ("security_blocks_kb_viewer", admin_kb.security_blocks_kb([(111, "@a")], {Permission.SECURITY_VIEW})),
        ("security_blocks_kb_empty", admin_kb.security_blocks_kb([], set())),
        ("security_team_kb", admin_kb.security_team_kb()),
    ]
```
