# الكود الكامل — مراجعة Hardening (الإصدار 1.0.1)

كل ما هنا منسوخ آلياً من ملفات المشروع الفعلية. الملفات الكبيرة جداً (أكثر من 760 سطراً) غير مُكرَّرة هنا؛ تجد مسارها ووصف ما تغيّر فيها في الفهرس، وهي مسلَّمة كاملة في المشروع.

## الفهرس

- `database/migrations/0010_phase12_1_hardening.sql` — 29 سطراً
- `core/order_state.py` — 233 سطراً
- `core/setting_rules.py` — 269 سطراً
- `core/constants.py` — 44 سطراً
- `database/database.py` — 337 سطراً
- `database/models.py` — 476 سطراً
- `database/repositories/orders.py` — 728 سطراً
- `database/repositories/providers.py` — 167 سطراً
- `database/repositories/broadcasts.py` — 187 سطراً
- `database/repositories/misc.py` — 307 سطراً
- `database/repositories/__init__.py` — 83 سطراً
- `services/provider_service.py` — 723 سطراً
- `services/settings_service.py` — 199 سطراً
- `services/broadcast_service.py` — 523 سطراً
- `services/auth_service.py` — 378 سطراً
- `services/notification_service.py` — 354 سطراً
- `jobs/order_jobs.py` — 65 سطراً
- `jobs/notification_jobs.py` — 41 سطراً
- `integrations/providers/base.py` — 169 سطراً
- `integrations/providers/perfect_panel.py` — 489 سطراً
- `integrations/providers/registry.py` — 78 سطراً
- `integrations/providers/__init__.py` — 33 سطراً
- `middlewares/context.py` — 303 سطراً
- `middlewares/rate_limit.py` — 250 سطراً
- `scripts/demo_cycle.py` — 344 سطراً
- `tests/conftest.py` — 228 سطراً
- `tests/integration/test_submission_safety_phase12_1.py` — 349 سطراً
- `tests/integration/test_db_commit_failure_phase12_1.py` — 45 سطراً
- `tests/integration/test_currency_types_phase12_1.py` — 342 سطراً
- `tests/integration/test_races_phase12_1.py` — 253 سطراً
- `tests/unit/test_perfect_panel_hardening_phase12_1.py` — 61 سطراً
- `tests/unit/test_registry_dev_types_phase12_1.py` — 25 سطراً
- `services/order_service.py` — 1643 سطراً (ملف كبير؛ في المشروع كاملاً) — التغيير: طبقة الإرسال/الاستعادة/التجاوز اليدوي: `process_pending_orders`، `_submit_one`، `recover_stale_submissions`، `recover_after_restart`، `_mark_uncertain`، `admin_cancel`، `admin_mark_failed`، `admin_override_status`، `_apply_partial`، تحويل التكلفة بسعر الصرف
- `services/payment_service.py` — 1074 سطراً (ملف كبير؛ في المشروع كاملاً) — التغيير: `_check_limit_pair` و`create_method`/`update_method` (فحص min/max)
- `services/catalog_service.py` — 624 سطراً (ملف كبير؛ في المشروع كاملاً) — التغيير: رفض/تعطيل الأنواع غير `default` في الاستيراد والمزامنة، وتسعير بسعر الصرف
- `handlers/admin/providers.py` — 1105 سطراً (ملف كبير؛ في المشروع كاملاً) — التغيير: خطوة العملة/سعر الصرف عند إضافة المزود وعرضها
- `keyboards/admin_kb.py` — 1671 سطراً (ملف كبير؛ في المشروع كاملاً) — التغيير: أزرار الأدمن (مزودون/عملة/استيراد)
- `texts/admin_ar.py` — 1496 سطراً (ملف كبير؛ في المشروع كاملاً) — التغيير: نصوص العملة وسعر الصرف والأنواع
- `texts/templates.py` — 720 سطراً (ملف كبير؛ في المشروع كاملاً) — التغيير: قوالب الإشعارات (غير مؤكد/ربط)

---

## `database/migrations/0010_phase12_1_hardening.sql`

```sql
-- =====================================================================
-- الترحيل 0010 — المرحلة 12.1 (التقوية بعد المراجعة الخارجية)
--
-- لماذا هذا الترحيل؟
--   1) سعر صرف لكل مزود (providers.exchange_rate):
--        • كان النظام يفترض أن عملة المزود = عملة النظام (provider_price/charge بلا تحويل)،
--          والإعداد العام `provider_exchange_rate` ميت (لا كود يقرأه) فكان تغييره وهماً.
--        • الآن لكل مزود عملته (`currency`) وسعر صرفه إلى عملة النظام (`exchange_rate`، نص Decimal
--          يعني: 1 وحدة من عملة المزود = X من عملة النظام). NULL ⇒ لا سعر: مقبول فقط إن تطابقت
--          عملة المزود مع `currency_code`، وإلا يُرفض الاستيراد والإرسال برسالة واضحة.
--        • المزودون الموجودون بعملة تختلف عن عملة النظام يصيرون «غير جاهزين» حتى يُحدَّد سعرهم
--          (عمداً: لا افتراض صامت 1:1).
--   2) حذف الإعداد الميت `provider_exchange_rate` (لا حذف لأي بيانات تاريخية: الإعداد لم يُستعمل).
--   3) فهرس فريد (provider_id, provider_service_id) يمنع استيراد نفس خدمة المزود مرتين تحت سباق
--      ضغطتين متزامنتين (الفحص في التطبيق وحده لا يكفي).
--      تنبيه: إن وُجدت تكرارات قديمة فسيفشل إنشاء الفهرس — عالجها يدوياً (أرشف المكرر) ثم أعد التشغيل.
--
-- ملاحظات:
--   • لا حذف ولا إعادة بناء لأي جدول؛ ALTER ADD COLUMN وفهرس وحذف إعداد ميت فقط.
--   • جدول user_states يبقى في المخطط (غير مستخدم: حالة المحادثة في الذاكرة) — لا حذف بيانات.
-- =====================================================================

ALTER TABLE providers ADD COLUMN exchange_rate TEXT;

DELETE FROM settings WHERE key = 'provider_exchange_rate';

CREATE UNIQUE INDEX IF NOT EXISTS uq_services_provider_service
    ON services(provider_id, provider_service_id)
    WHERE provider_service_id IS NOT NULL;
```

## `core/order_state.py`

```python
"""
آلة حالات الطلب (Order State Machine).

هذا الملف هو **المرجع الوحيد** لما هو مسموح وما هو ممنوع في انتقالات حالة الطلب.
لا يعتمد على قاعدة البيانات ولا على تيليجرام، لذلك يمكن اختباره مباشرة.

القاعدة الصارمة: أي انتقال غير مذكور في `ALLOWED_TRANSITIONS` يُرفض باستثناء
`InvalidStateTransitionError` — ولا يوجد أي مسار في النظام يغيّر حالة طلب دون المرور من هنا.
"""

from __future__ import annotations

from core.enums import OrderStatus
from core.exceptions import InvalidStateTransitionError

#: الحالات النهائية التي لا يجوز الانتقال منها إلى أي حالة أخرى
FINAL_STATUSES: frozenset[str] = frozenset(
    {
        OrderStatus.COMPLETED,
        OrderStatus.PARTIAL,
        OrderStatus.CANCELED,
        OrderStatus.REFUNDED,
    }
)

#: الحالات التي ما زال الطلب فيها حياً (تحتاج متابعة من النظام)
ACTIVE_STATUSES: frozenset[str] = frozenset(
    {
        OrderStatus.PENDING,
        OrderStatus.SUBMITTING,
        OrderStatus.SUBMIT_UNCERTAIN,
        OrderStatus.SUBMITTED,
        OrderStatus.IN_PROGRESS,
    }
)

#: الحالات التي تحتاج تدخلاً بشرياً (تُعرض للأدمن كتنبيه)
NEEDS_ATTENTION_STATUSES: frozenset[str] = frozenset({OrderStatus.SUBMIT_UNCERTAIN})

#: جدول الانتقالات المسموحة: من حالة → الحالات التي يجوز الانتقال إليها
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    OrderStatus.PENDING: frozenset(
        {OrderStatus.SUBMITTING, OrderStatus.CANCELED, OrderStatus.FAILED}
    ),
    OrderStatus.SUBMITTING: frozenset(
        {
            OrderStatus.SUBMITTED,
            OrderStatus.PENDING,           # فشل شبكي قبل الإرسال مع بقاء محاولات
            OrderStatus.SUBMIT_UNCERTAIN,  # مهلة/انقطاع بعد الإرسال
            OrderStatus.FAILED,
        }
    ),
    OrderStatus.SUBMIT_UNCERTAIN: frozenset({OrderStatus.SUBMITTED, OrderStatus.FAILED}),
    OrderStatus.SUBMITTED: frozenset(
        {
            OrderStatus.IN_PROGRESS,
            OrderStatus.COMPLETED,
            OrderStatus.PARTIAL,
            OrderStatus.CANCELED,
            OrderStatus.FAILED,
        }
    ),
    OrderStatus.IN_PROGRESS: frozenset(
        {OrderStatus.COMPLETED, OrderStatus.PARTIAL, OrderStatus.CANCELED, OrderStatus.FAILED}
    ),
    OrderStatus.FAILED: frozenset({OrderStatus.REFUNDED}),
    OrderStatus.CANCELED: frozenset({OrderStatus.REFUNDED}),
    OrderStatus.PARTIAL: frozenset(),
    OrderStatus.COMPLETED: frozenset(),
    OrderStatus.REFUNDED: frozenset(),
}

#: الحالات التي توجب استرجاعاً كاملاً للمبلغ فور الدخول إليها
REQUIRE_FULL_REFUND: frozenset[str] = frozenset({OrderStatus.FAILED, OrderStatus.CANCELED})

#: الحالة التي توجب استرجاعاً جزئياً بحسب المتبقي
REQUIRE_PARTIAL_REFUND: frozenset[str] = frozenset({OrderStatus.PARTIAL})

#: خريطة نصوص حالات المزود الشائعة → حالات النظام (تُقارن بحروف صغيرة بعد التنظيف)
PROVIDER_STATUS_MAP: dict[str, str] = {
    "pending": OrderStatus.SUBMITTED,
    "awaiting": OrderStatus.SUBMITTED,
    "queue": OrderStatus.SUBMITTED,
    "in queue": OrderStatus.SUBMITTED,
    "processing": OrderStatus.IN_PROGRESS,
    "in progress": OrderStatus.IN_PROGRESS,
    "inprogress": OrderStatus.IN_PROGRESS,
    "active": OrderStatus.IN_PROGRESS,
    "running": OrderStatus.IN_PROGRESS,
    "completed": OrderStatus.COMPLETED,
    "complete": OrderStatus.COMPLETED,
    "success": OrderStatus.COMPLETED,
    "partial": OrderStatus.PARTIAL,
    "canceled": OrderStatus.CANCELED,
    "cancelled": OrderStatus.CANCELED,
    "refunded": OrderStatus.CANCELED,  # المزود ردّ المبلغ ⇒ نعامله كإلغاء ثم نسترجع للمستخدم
    "error": OrderStatus.FAILED,
    "fail": OrderStatus.FAILED,
    "failed": OrderStatus.FAILED,
    "rejected": OrderStatus.FAILED,
}

#: الحالات العربية للعرض في الواجهة
STATUS_LABELS_AR: dict[str, str] = {
    OrderStatus.PENDING: "⏳ بانتظار الإرسال",
    OrderStatus.SUBMITTING: "📤 جاري الإرسال",
    OrderStatus.SUBMIT_UNCERTAIN: "❓ غير مؤكد (قيد المراجعة)",
    OrderStatus.SUBMITTED: "✅ أُرسل للمزود",
    OrderStatus.IN_PROGRESS: "🔄 قيد التنفيذ",
    OrderStatus.PARTIAL: "🟡 مكتمل جزئياً",
    OrderStatus.COMPLETED: "🎉 مكتمل",
    OrderStatus.CANCELED: "🚫 ملغي",
    OrderStatus.FAILED: "❌ فاشل",
    OrderStatus.REFUNDED: "💰 مسترجع",
}


def can_transition(from_status: str, to_status: str) -> bool:
    """
    هل يجوز الانتقال من حالة إلى أخرى؟

    ملاحظة: الانتقال إلى نفس الحالة مسموح دائماً ويُعامل كـ«لا تغيير» (no-op)
    لأن فحص الحالة الدوري قد يعيد نفس النتيجة.
    """
    if from_status == to_status:
        return True
    return to_status in ALLOWED_TRANSITIONS.get(from_status, frozenset())


def assert_transition(from_status: str, to_status: str, *, order_id: int | None = None) -> None:
    """
    التحقق من الانتقال ورفع استثناء واضح عند المخالفة.

    الاستثناءات:
        InvalidStateTransitionError : الانتقال غير مسموح في جدول الحالات.
    """
    if can_transition(from_status, to_status):
        return
    where = f" للطلب #{order_id}" if order_id else ""
    raise InvalidStateTransitionError(
        f"انتقال غير مسموح{where}: {from_status} ← {to_status}",
        user_message="⚠️ لا يمكن تنفيذ هذا الإجراء على الطلب في حالته الحالية.",
    )


def is_final(status: str) -> bool:
    """هل الطلب في حالة نهائية لا تقبل أي تغيير لاحق؟"""
    return status in FINAL_STATUSES


def is_active(status: str) -> bool:
    """هل الطلب ما زال يحتاج متابعة من النظام؟"""
    return status in ACTIVE_STATUSES


def allowed_next(status: str) -> frozenset[str]:
    """الحالات التي يمكن الانتقال إليها من الحالة الحالية."""
    return ALLOWED_TRANSITIONS.get(status, frozenset())


def sources_for(to_status: str) -> tuple[str, ...]:
    """
    الحالات التي يجوز أن يأتي منها هذا الانتقال.

    تُستخدم مباشرة كـ`expected_statuses` في تحديث الحالة المشروط داخل قاعدة البيانات،
    فيصبح منع السباق مضموناً من مصدر واحد بدل تكرار القوائم يدوياً في كل مكان.
    """
    return tuple(
        source for source, targets in ALLOWED_TRANSITIONS.items() if to_status in targets
    )


def requires_full_refund(to_status: str) -> bool:
    """هل الدخول إلى هذه الحالة يوجب استرجاع كامل المبلغ؟"""
    return to_status in REQUIRE_FULL_REFUND


def requires_partial_refund(to_status: str) -> bool:
    """هل الدخول إلى هذه الحالة يوجب استرجاعاً جزئياً؟"""
    return to_status in REQUIRE_PARTIAL_REFUND


def map_provider_status(raw_status: str | None) -> str | None:
    """
    تحويل نص حالة المزود إلى حالة النظام.

    المخرجات: حالة معروفة، أو None إذا كان النص غير معروف
              (المتصل مسؤول عن تسجيل تحذير وعدم تغيير الحالة).
    """
    if not raw_status:
        return None
    key = " ".join(str(raw_status).strip().lower().split())
    return PROVIDER_STATUS_MAP.get(key)


def label_ar(status: str) -> str:
    """الاسم العربي للحالة كما يُعرض للمستخدم."""
    return STATUS_LABELS_AR.get(status, status)


#: حالات ممنوع الوصول إليها بالتجاوز الإداري اليدوي (إرسال/مال): إعادة الطلب لحالات الإرسال قد تُرسله مرتين،
#: و«ملغى/مسترجع» حالتان ماليتان لهما أداتان مخصصتان (حركة مالية + استرجاع)
OVERRIDE_FORBIDDEN_TARGETS: frozenset[str] = frozenset(
    {
        OrderStatus.PENDING,
        OrderStatus.SUBMITTING,
        OrderStatus.SUBMIT_UNCERTAIN,
        OrderStatus.CANCELED,
        OrderStatus.REFUNDED,
    }
)

#: حالات تفترض أن للطلب رقماً عند المزود (لا معنى لها بدونه)
OVERRIDE_NEEDS_PROVIDER_ID: frozenset[str] = frozenset(
    {OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS, OrderStatus.COMPLETED, OrderStatus.PARTIAL}
)


def override_targets(status: str, *, has_provider_id: bool) -> list[str]:
    """
    الحالات التي يجوز التجاوز اليدوي إليها من حالة معينة (للأزرار والتحقق): آلة الحالات ∩ سياسة التجاوز.

    فارغة تعني أن التجاوز غير متاح (قيد الإرسال/غير مؤكد/نهائي). `submitting` و`submit_uncertain` لهما
    مساراتهما الخاصة («🔗 ربط رقم المزود» و«⛔ تعليم كفاشل + استرجاع»).
    """
    if status in (OrderStatus.SUBMITTING, OrderStatus.SUBMIT_UNCERTAIN):
        return []
    return sorted(
        target
        for target in allowed_next(status)
        if target not in OVERRIDE_FORBIDDEN_TARGETS
        and (target not in OVERRIDE_NEEDS_PROVIDER_ID or has_provider_id)
    )
```

## `core/setting_rules.py`

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
    """

    minimum: int | None = None
    maximum: int | None = None
    max_length: int | None = None
    pattern: str | None = None
    allow_empty: bool = False
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
    "provider_failure_threshold": _int(1, 100),
    "provider_disable_minutes": _int(1, 10_080),
    "provider_insufficient_wait_hours": _int(1, 168),
    "provider_balance_check_minutes": _int(1, 1440),
    "provider_health_watch_minutes": _int(1, 1440),
    # النسخ الاحتياطي
    "backup_interval_hours": _int(0, 720),             # صفر = تعطيل النسخ التلقائي
    "backup_retention_days": _int(1, 3650),
    "backup_min_keep": _int(1, 100),
    "export_max_rows": _int(100, 100_000),
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


def normalize_decimal_text(text: str) -> str:
    """
    فحص وتطبيع عدد عشري موجب (مثل سعر الصرف) إلى نص قياسي بلا أصفار زائدة.

    القواعد: أرقام عربية/هندية مقبولة، فاصلة عشرية `.` أو `,`، أكبر من صفر وأقل/يساوي مليار،
    وحتى 8 خانات عشرية. الاستثناءات: ValidationError برسالة عربية.
    """
    try:
        value = Decimal(normalize_digits(str(text).strip()).replace(",", "."))
    except InvalidOperation as exc:
        raise _bad(f"عدد عشري غير صالح: {text!r}", "❌ أرسل رقماً (مثل 1 أو 530.5).") from exc
    if not value.is_finite() or value <= 0 or value > Decimal("1000000000"):
        raise _bad(f"عدد خارج النطاق: {text!r}", "❌ يجب أن يكون الرقم أكبر من صفر وأقل من مليار.")
    if value.as_tuple().exponent < -8:                            # type: ignore[operator]
        raise _bad(f"خانات عشرية كثيرة: {text!r}", "❌ الحد الأقصى 8 خانات عشرية.")
    return format(value.normalize(), "f")


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

## `core/constants.py`

```python
"""ثوابت عامة للنظام (قيم لا تتغير أثناء التشغيل)."""

from __future__ import annotations

#: اسم المشروع وإصداره
APP_NAME: str = "SMM Telegram Bot"
APP_VERSION = "1.0.1"

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

## `database/database.py`

```python
"""
طبقة الوصول إلى قاعدة البيانات (SQLite عبر aiosqlite).

التصميم:
    • اتصال كتابة واحد محمي بقفل asyncio  ← لأن SQLite يسمح بكاتب واحد فقط،
      والتسلسل الصريح يمنع أخطاء "database is locked" العشوائية.
    • مجموعة اتصالات للقراءة (WAL يسمح بقراءات متوازية أثناء الكتابة).
    • كل كتابة تتم داخل معاملة BEGIN IMMEDIATE ... COMMIT، مع دعم المعاملات المتداخلة
      (إذا فتحت خدمة معاملة ثم نادت خدمة أخرى، تُستخدم نفس المعاملة ولا تُفتح ثانية).
    • إعادة محاولة تلقائية محدودة عند قفل قاعدة البيانات.

كل عبارات SQL هنا وفي المستودعات (repositories) مُعلَّمة بـ ? — لا بناء نصوص SQL يدوياً.
"""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Sequence

import aiosqlite

from core.exceptions import DatabaseError, DatabaseLockedError
from utils.logging_setup import get_logger

logger = get_logger(__name__)

SQLParams = Sequence[Any] | dict[str, Any]


@dataclass(frozen=True)
class ExecResult:
    """نتيجة تنفيذ عبارة كتابة: عدد الصفوف المتأثرة ومعرف آخر صف مُدرج."""

    rowcount: int
    lastrowid: int | None


def _is_locked_error(exc: BaseException) -> bool:
    """هل هذا الخطأ ناتج عن قفل مؤقت لقاعدة البيانات (قابل لإعادة المحاولة)؟"""
    return isinstance(exc, sqlite3.OperationalError) and (
        "locked" in str(exc).lower() or "busy" in str(exc).lower()
    )


class Tx:
    """
    مقبض معاملة مفتوحة على اتصال الكتابة.

    يُمرَّر إلى دوال المستودعات التي تُعدِّل البيانات، لضمان أن كل التعديلات
    المترابطة (خصم رصيد + إنشاء طلب + تسجيل حركة + إشعار) تتم كوحدة واحدة.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        """ربط المعاملة باتصال aiosqlite المفتوح."""
        self._conn = conn

    async def execute(self, sql: str, params: SQLParams = ()) -> ExecResult:
        """تنفيذ عبارة كتابة (INSERT/UPDATE/DELETE) وإرجاع عدد الصفوف والمعرف الجديد."""
        async with self._conn.execute(sql, params) as cursor:
            return ExecResult(rowcount=cursor.rowcount, lastrowid=cursor.lastrowid)

    async def executemany(self, sql: str, seq: Iterable[SQLParams]) -> ExecResult:
        """تنفيذ نفس العبارة على مجموعة قيم (إدراج جماعي)."""
        async with self._conn.executemany(sql, seq) as cursor:
            return ExecResult(rowcount=cursor.rowcount, lastrowid=cursor.lastrowid)

    async def fetchone(self, sql: str, params: SQLParams = ()) -> aiosqlite.Row | None:
        """قراءة صف واحد داخل المعاملة (يرى التعديلات غير المثبتة بعد)."""
        async with self._conn.execute(sql, params) as cursor:
            return await cursor.fetchone()

    async def fetchall(self, sql: str, params: SQLParams = ()) -> list[aiosqlite.Row]:
        """قراءة كل الصفوف داخل المعاملة."""
        async with self._conn.execute(sql, params) as cursor:
            return list(await cursor.fetchall())

    async def fetchval(self, sql: str, params: SQLParams = (), default: Any = None) -> Any:
        """قراءة قيمة واحدة (أول عمود من أول صف) داخل المعاملة."""
        row = await self.fetchone(sql, params)
        if row is None:
            return default
        value = row[0]
        return default if value is None else value


#: المعاملة النشطة في السياق الحالي (لدعم المعاملات المتداخلة بأمان)
_current_tx: ContextVar[Tx | None] = ContextVar("smm_current_tx", default=None)


class Database:
    """مدير الاتصال بقاعدة البيانات: اتصال كتابة واحد + مجموعة اتصالات قراءة."""

    def __init__(
        self,
        path: str | Path,
        *,
        read_pool_size: int = 3,
        busy_timeout_ms: int = 5_000,
        max_retries: int = 5,
    ) -> None:
        """تهيئة المدير دون فتح الاتصال (الفتح يتم في connect)."""
        self.path = Path(path)
        self._read_pool_size = max(1, read_pool_size)
        self._busy_timeout_ms = busy_timeout_ms
        self._max_retries = max_retries
        self._write_conn: aiosqlite.Connection | None = None
        self._read_pool: asyncio.Queue[aiosqlite.Connection] | None = None
        self._read_conns: list[aiosqlite.Connection] = []
        self._write_lock = asyncio.Lock()
        self._connected = False

    # ------------------------------ الاتصال ------------------------------ #

    async def connect(self) -> None:
        """فتح الاتصالات وتطبيق إعدادات SQLite المطلوبة (WAL، المفاتيح الأجنبية...)."""
        if self._connected:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self._write_conn = await self._open_connection()
        self._read_pool = asyncio.Queue(maxsize=self._read_pool_size)
        for _ in range(self._read_pool_size):
            conn = await self._open_connection()
            self._read_conns.append(conn)
            self._read_pool.put_nowait(conn)

        self._connected = True
        logger.info("تم الاتصال بقاعدة البيانات: %s", self.path)

    async def _open_connection(self) -> aiosqlite.Connection:
        """فتح اتصال واحد وضبط إعداداته (isolation_level=None للتحكم اليدوي بالمعاملات)."""
        conn = await aiosqlite.connect(self.path, isolation_level=None)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode = WAL")
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute(f"PRAGMA busy_timeout = {int(self._busy_timeout_ms)}")
        await conn.execute("PRAGMA synchronous = NORMAL")
        await conn.execute("PRAGMA temp_store = MEMORY")
        return conn

    async def close(self) -> None:
        """إغلاق كل الاتصالات بأمان."""
        if not self._connected:
            return
        for conn in self._read_conns:
            await conn.close()
        self._read_conns.clear()
        if self._write_conn is not None:
            await self._write_conn.close()
            self._write_conn = None
        self._read_pool = None
        self._connected = False
        logger.info("تم إغلاق الاتصال بقاعدة البيانات.")

    def _require_connected(self) -> None:
        """التأكد من أن الاتصال مفتوح قبل أي عملية."""
        if not self._connected or self._write_conn is None or self._read_pool is None:
            raise DatabaseError("قاعدة البيانات غير متصلة — نادِ connect() أولاً.")

    # ------------------------------ المعاملات ----------------------------- #

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Tx]:
        """
        فتح معاملة كتابة ذرّية (BEGIN IMMEDIATE ... COMMIT).

        الاستخدام:
            async with db.transaction() as tx:
                await repo.do_something(tx, ...)

        الضمانات:
            • أي استثناء داخل الكتلة يؤدي إلى ROLLBACK كامل.
            • المعاملات المتداخلة تُعيد استخدام نفس المعاملة (لا commit مبكر).
            • إعادة محاولة محدودة إذا كانت قاعدة البيانات مقفولة مؤقتاً.
        """
        self._require_connected()
        existing = _current_tx.get()
        if existing is not None:
            # معاملة متداخلة: نكمل ضمن نفس المعاملة الخارجية
            yield existing
            return

        async with self._write_lock:
            conn = self._write_conn
            assert conn is not None
            await self._begin_with_retry(conn)
            tx = Tx(conn)
            token = _current_tx.set(tx)
            try:
                yield tx
                await conn.execute("COMMIT")
            except BaseException:
                # يشمل فشل COMMIT نفسه: بدون ROLLBACK يبقى اتصال الكتابة داخل معاملة مفتوحة
                # فيفشل كل `BEGIN IMMEDIATE` التالي حتى إعادة تشغيل البوت.
                await self._rollback_quietly(conn)
                raise
            finally:
                _current_tx.reset(token)

    async def _begin_with_retry(self, conn: aiosqlite.Connection) -> None:
        """بدء معاملة فورية مع إعادة محاولة عند القفل المؤقت."""
        delay = 0.05
        for attempt in range(1, self._max_retries + 1):
            try:
                await conn.execute("BEGIN IMMEDIATE")
                return
            except sqlite3.OperationalError as exc:
                if not _is_locked_error(exc) or attempt == self._max_retries:
                    if _is_locked_error(exc):
                        raise DatabaseLockedError(
                            "تعذر بدء المعاملة: قاعدة البيانات مقفولة."
                        ) from exc
                    raise DatabaseError(f"خطأ في بدء المعاملة: {exc}") from exc
                logger.warning("قاعدة البيانات مقفولة، إعادة المحاولة %s/%s", attempt, self._max_retries)
                await asyncio.sleep(delay)
                delay *= 2

    async def _rollback_quietly(self, conn: aiosqlite.Connection) -> None:
        """تنفيذ ROLLBACK مع تسجيل أي مشكلة (دون إخفاء الخطأ الأصلي)."""
        try:
            await conn.execute("ROLLBACK")
        except sqlite3.Error as exc:  # نسجل ولا نبتلع: الخطأ الأصلي هو الأهم
            if "no transaction is active" in str(exc):
                logger.debug("لا معاملة نشطة للتراجع عنها (SQLite أنهتها بنفسها): %s", exc)
            else:
                logger.error("فشل التراجع عن المعاملة: %s", exc)

    # ------------------------------- القراءة ------------------------------ #

    @asynccontextmanager
    async def _reader(self) -> AsyncIterator[aiosqlite.Connection]:
        """حجز اتصال قراءة من المجموعة وإعادته بعد الانتهاء."""
        self._require_connected()
        assert self._read_pool is not None
        conn = await self._read_pool.get()
        try:
            yield conn
        finally:
            self._read_pool.put_nowait(conn)

    async def fetchone(self, sql: str, params: SQLParams = ()) -> aiosqlite.Row | None:
        """قراءة صف واحد (تستخدم المعاملة الحالية إن وُجدت، وإلا اتصال قراءة)."""
        tx = _current_tx.get()
        if tx is not None:
            return await tx.fetchone(sql, params)
        async with self._reader() as conn, conn.execute(sql, params) as cursor:
            return await cursor.fetchone()

    async def fetchall(self, sql: str, params: SQLParams = ()) -> list[aiosqlite.Row]:
        """قراءة كل الصفوف المطابقة."""
        tx = _current_tx.get()
        if tx is not None:
            return await tx.fetchall(sql, params)
        async with self._reader() as conn, conn.execute(sql, params) as cursor:
            return list(await cursor.fetchall())

    async def fetchval(self, sql: str, params: SQLParams = (), default: Any = None) -> Any:
        """قراءة قيمة مفردة (مثل COUNT أو SUM)."""
        row = await self.fetchone(sql, params)
        if row is None:
            return default
        value = row[0]
        return default if value is None else value

    # ------------------------------ أدوات إدارية --------------------------- #

    async def executescript(self, script: str) -> None:
        """
        تنفيذ سكربت SQL كامل على اتصال الكتابة (يُستخدم للترحيلات فقط).

        تحذير: هذه الدالة تتحكم بالمعاملات بنفسها، لذا لا تُستدعى داخل transaction().
        """
        self._require_connected()
        assert self._write_conn is not None
        async with self._write_lock:
            await self._write_conn.executescript(script)

    async def execute_raw(self, sql: str, params: SQLParams = ()) -> ExecResult:
        """
        تنفيذ عبارة كتابة مفردة خارج معاملة صريحة (للأدوات الإدارية فقط).

        ⚠️ ممنوع استخدامها في أي عملية مالية — تلك تمر عبر transaction() دائماً.
        """
        self._require_connected()
        assert self._write_conn is not None
        async with self._write_lock:
            async with self._write_conn.execute(sql, params) as cursor:
                return ExecResult(rowcount=cursor.rowcount, lastrowid=cursor.lastrowid)

    async def table_names(self) -> list[str]:
        """قائمة بأسماء جداول قاعدة البيانات (للتحقق والاختبارات)."""
        rows = await self.fetchall(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return [row["name"] for row in rows]

    async def integrity_check(self) -> bool:
        """فحص سلامة ملف قاعدة البيانات (يُستخدم قبل/بعد النسخ الاحتياطي)."""
        result = await self.fetchval("PRAGMA integrity_check")
        return str(result).lower() == "ok"

    async def foreign_key_check(self) -> list[aiosqlite.Row]:
        """فحص وجود أي انتهاك للمفاتيح الأجنبية (يجب أن تكون النتيجة فارغة)."""
        return await self.fetchall("PRAGMA foreign_key_check")

    async def vacuum(self) -> None:
        """ضغط ملف قاعدة البيانات بعد عمليات الحذف الكبيرة."""
        self._require_connected()
        assert self._write_conn is not None
        async with self._write_lock:
            await self._write_conn.execute("VACUUM")

    async def snapshot_to(self, destination: str | Path) -> None:
        """
        نسخة متّسقة من القاعدة الحيّة إلى ملف جديد (`VACUUM INTO`) دون إيقاف البوت.

        لماذا `VACUUM INTO` وليس نسخ الملف؟ ملف WAL قد يحوي معاملات مثبّتة لم تُدمج
        بعد في الملف الرئيسي، فنسخ الملف وحده قد يعطي نسخة ناقصة أو تالفة. هذا الأمر
        يقرأ لقطة واحدة متّسقة عبر اتصال قراءة (لا يحجب الكتابة) ويكتب ملفاً مدمجاً.

        المدخلات: مسار ملف غير موجود (يُرفض الاستبدال حتى لا نكتب فوق نسخة قائمة).
        الاستثناءات: DatabaseError عند وجود الملف أو فشل الأمر.
        """
        target = Path(destination)
        if target.exists():
            raise DatabaseError(f"ملف النسخة موجود مسبقاً: {target.name}")
        async with self._reader() as conn:
            try:
                await conn.execute("VACUUM INTO ?", (str(target),))
            except sqlite3.Error as exc:
                target.unlink(missing_ok=True)
                raise DatabaseError(f"فشل أخذ لقطة من القاعدة: {exc}") from exc
```

## `database/models.py`

```python
"""
نماذج البيانات (Data Models) — تمثيل صفوف الجداول ككائنات Python.

لماذا dataclasses بدل ORM كامل؟
    • خفيفة وسريعة ولا تُخفي ما يحدث في SQL.
    • تُبقي كل عبارات SQL ظاهرة في المستودعات (repositories) مما يسهّل
      مراجعتها أمنياً ونقلها لاحقاً إلى PostgreSQL.

كل نموذج يوفّر from_row لتحويل صف قاعدة البيانات إلى كائن، مع تجاهل أي أعمدة إضافية.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Iterable, Mapping, TypeVar

from core.money import from_units

_T = TypeVar("_T", bound="BaseModel")


@dataclass(slots=True)
class BaseModel:
    """أساس كل النماذج: يوفّر التحويل من صف قاعدة بيانات إلى كائن."""

    @classmethod
    def from_row(cls: type[_T], row: Mapping[str, Any] | None) -> _T | None:
        """تحويل صف واحد إلى كائن النموذج، أو None إذا لم يوجد صف."""
        if row is None:
            return None
        allowed = {f.name for f in fields(cls)}
        data = {key: row[key] for key in row.keys() if key in allowed}
        return cls(**data)  # type: ignore[arg-type]

    @classmethod
    def from_rows(cls: type[_T], rows: Iterable[Mapping[str, Any]]) -> list[_T]:
        """تحويل مجموعة صفوف إلى قائمة كائنات."""
        result: list[_T] = []
        for row in rows:
            item = cls.from_row(row)
            if item is not None:
                result.append(item)
        return result


# ------------------------------- المستخدمون ------------------------------- #


@dataclass(slots=True)
class User(BaseModel):
    """مستخدم البوت (عميل أو أدمن)."""

    id: int
    telegram_id: int
    created_at: str
    updated_at: str
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    balance_units: int = 0
    total_spent_units: int = 0
    total_deposited_units: int = 0
    role: str = "user"
    is_banned: int = 0
    ban_reason: str | None = None
    banned_at: str | None = None
    blocked_bot: int = 0
    language: str = "ar"
    referrer_id: int | None = None
    notes: str | None = None
    last_activity: str | None = None

    @property
    def balance(self):
        """الرصيد كقيمة عشرية للعرض فقط (التخزين والحساب يبقى بالنقاط)."""
        return from_units(self.balance_units)

    @property
    def display_name(self) -> str:
        """اسم مناسب للعرض في لوحة الأدمن."""
        if self.username:
            return f"@{self.username}"
        return self.first_name or f"ID:{self.telegram_id}"

    @property
    def banned(self) -> bool:
        """هل المستخدم محظور؟"""
        return bool(self.is_banned)


# -------------------------------- المزودون -------------------------------- #


@dataclass(slots=True)
class Provider(BaseModel):
    """مزود خدمات SMM خارجي."""

    id: int
    name: str
    api_url: str
    api_key_enc: str
    created_at: str
    updated_at: str
    api_key_hint: str | None = None
    api_type: str = "perfect_panel"
    balance_units: int = 0
    currency: str = "USD"
    #: سعر الصرف: 1 وحدة من `currency` = X من عملة النظام (نص Decimal)؛ None ⇒ لا سعر (يُقبل فقط عند تطابق العملتين)
    exchange_rate: str | None = None
    balance_checked_at: str | None = None
    low_balance_threshold_units: int | None = None
    is_active: int = 1
    priority: int = 100
    timeout_seconds: int = 30
    consecutive_failures: int = 0
    disabled_until: str | None = None
    last_error: str | None = None
    last_success_at: str | None = None

    @property
    def active(self) -> bool:
        """هل المزود مفعّل؟ (التعطيل المؤقت يُفحص في ProviderService)."""
        return bool(self.is_active)


# --------------------------- التصنيفات والخدمات ---------------------------- #


@dataclass(slots=True)
class ServiceCategory(BaseModel):
    """تصنيف خدمات (منصة مثل انستغرام أو تيك توك)."""

    id: int
    name_ar: str
    created_at: str
    updated_at: str
    name_en: str | None = None
    emoji: str = "📦"
    sort_order: int = 100
    is_active: int = 1

    @property
    def title(self) -> str:
        """العنوان المعروض على الزر."""
        return f"{self.emoji} {self.name_ar}"


@dataclass(slots=True)
class Service(BaseModel):
    """خدمة معروضة للبيع."""

    id: int
    category_id: int
    provider_id: int
    provider_service_id: str
    name: str
    price_per_1000_units: int
    min_quantity: int
    max_quantity: int
    created_at: str
    updated_at: str
    description: str | None = None
    service_type: str = "default"
    provider_price_per_1000_units: int | None = None
    dripfeed_enabled: int = 0
    refill_enabled: int = 0
    cancel_enabled: int = 0
    link_pattern: str | None = None
    avg_time_text: str | None = None
    is_active: int = 1
    is_archived: int = 0
    sort_order: int = 100

    @property
    def available(self) -> bool:
        """هل الخدمة متاحة للطلب الآن؟"""
        return bool(self.is_active) and not bool(self.is_archived)

    @property
    def margin_units(self) -> int | None:
        """هامش الربح لكل ألف (None إذا لم تُسجَّل تكلفة المزود)."""
        if self.provider_price_per_1000_units is None:
            return None
        return self.price_per_1000_units - self.provider_price_per_1000_units


# --------------------------------- الطلبات -------------------------------- #


@dataclass(slots=True)
class Order(BaseModel):
    """طلب عميل على خدمة."""

    id: int
    user_id: int
    service_id: int
    provider_id: int
    service_name_snapshot: str
    price_per_1000_snapshot_units: int
    link: str
    quantity: int
    cost_units: int
    client_request_id: str
    created_at: str
    updated_at: str
    public_code: str | None = None
    provider_cost_units: int | None = None
    status: str = "pending"
    provider_status: str | None = None
    provider_order_id: str | None = None
    start_count: int | None = None
    remains: int | None = None
    delivered_quantity: int | None = None
    refund_amount_units: int = 0
    refunded_at: str | None = None
    submit_attempts: int = 0
    checks_count: int = 0
    last_error: str | None = None
    locked_by: str | None = None
    locked_until: str | None = None
    next_check_at: str | None = None
    submitted_at: str | None = None
    completed_at: str | None = None
    cancelled_at: str | None = None

    @property
    def refundable_units(self) -> int:
        """المبلغ المتبقي القابل للاسترجاع (التكلفة ناقص ما استُرجع)."""
        return max(0, self.cost_units - self.refund_amount_units)


@dataclass(slots=True)
class OrderStatusHistory(BaseModel):
    """سجل انتقال حالة طلب."""

    id: int
    order_id: int
    to_status: str
    created_at: str
    from_status: str | None = None
    actor_type: str = "system"
    actor_id: int | None = None
    reason: str | None = None
    provider_status_raw: str | None = None


# ----------------------------- الحركات المالية ----------------------------- #


@dataclass(slots=True)
class Transaction(BaseModel):
    """حركة مالية في دفتر الأستاذ (إضافة فقط — لا تُعدَّل ولا تُحذف)."""

    id: int
    user_id: int
    type: str
    direction: str
    amount_units: int
    balance_before_units: int
    balance_after_units: int
    created_at: str
    order_id: int | None = None
    payment_id: int | None = None
    description: str | None = None
    reference: str | None = None
    actor_id: int | None = None

    @property
    def signed_amount_units(self) -> int:
        """المبلغ بإشارته (موجب للإضافة وسالب للخصم) لعرضه في السجل."""
        return self.amount_units if self.direction == "credit" else -self.amount_units


# -------------------------------- المدفوعات -------------------------------- #


@dataclass(slots=True)
class PaymentMethod(BaseModel):
    """طريقة شحن رصيد قابلة للتهيئة من لوحة الأدمن."""

    id: int
    code: str
    name_ar: str
    created_at: str
    updated_at: str
    type: str = "manual"
    instructions_ar: str = ""
    account_details: str = ""
    min_amount_units: int = 0
    max_amount_units: int | None = None
    requires_proof: int = 1
    is_active: int = 1
    sort_order: int = 100
    fee_percent_bp: int = 0      # رسوم نسبية بنقاط الأساس (250 = 2.5%)
    fee_fixed_units: int = 0     # رسوم ثابتة بالنقاط تُخصم من كل حوالة

    @property
    def has_fees(self) -> bool:
        """هل لهذه الطريقة رسوم تُخصم من مبلغ الحوالة؟"""
        return self.fee_percent_bp > 0 or self.fee_fixed_units > 0


@dataclass(slots=True)
class Payment(BaseModel):
    """طلب شحن رصيد."""

    id: int
    user_id: int
    method_id: int
    amount_units: int
    created_at: str
    updated_at: str
    credited_units: int | None = None
    status: str = "pending"
    transaction_reference: str | None = None
    proof_file_id: str | None = None
    proof_file_type: str | None = None
    user_note: str | None = None
    admin_id: int | None = None
    admin_note: str | None = None
    reject_reason: str | None = None
    reviewed_at: str | None = None
    expires_at: str | None = None
    fee_units: int = 0           # لقطة رسوم الطريقة وقت الإرسال (لا تتغير لاحقاً)

    @property
    def net_units(self) -> int:
        """
        المبلغ الصافي المتوقع إضافته للرصيد = المبلغ المحوَّل − الرسوم.

        يُستخدم كقيمة افتراضية في شاشة الاعتماد، ويبقى للأدمن حق تعديله.
        """
        return max(0, int(self.amount_units) - int(self.fee_units or 0))


# ---------------------------------- الدعم ---------------------------------- #


@dataclass(slots=True)
class SupportTicket(BaseModel):
    """تذكرة دعم فني."""

    id: int
    user_id: int
    subject: str
    created_at: str
    updated_at: str
    category: str = "other"
    related_order_id: int | None = None
    status: str = "open"
    priority: str = "normal"
    assigned_admin: int | None = None
    last_message_at: str | None = None
    closed_by: int | None = None
    close_reason: str | None = None
    closed_at: str | None = None

    @property
    def is_open(self) -> bool:
        """هل التذكرة ما زالت مفتوحة؟"""
        return self.status != "closed"


@dataclass(slots=True)
class SupportMessage(BaseModel):
    """رسالة داخل تذكرة دعم."""

    id: int
    ticket_id: int
    sender_type: str
    message: str
    created_at: str
    sender_id: int | None = None
    attachment_file_id: str | None = None
    attachment_type: str | None = None
    telegram_message_id: int | None = None
    is_read_by_user: int = 0
    is_read_by_admin: int = 0


# -------------------------------- الإشعارات -------------------------------- #


@dataclass(slots=True)
class Notification(BaseModel):
    """إشعار في صندوق الإرسال (Outbox)."""

    id: int
    user_id: int
    type: str
    message: str
    dedupe_key: str
    created_at: str
    title: str = ""
    payload_json: str | None = None
    status: str = "queued"
    attempts: int = 0
    next_attempt_at: str | None = None
    last_error: str | None = None
    telegram_message_id: int | None = None
    is_read: int = 0
    sent_at: str | None = None


# ------------------------------ الإعدادات والسجل ---------------------------- #


@dataclass(slots=True)
class Setting(BaseModel):
    """إعداد عام من جدول settings."""

    key: str
    value: str
    updated_at: str
    value_type: str = "str"
    group_code: str = "general"
    name_ar: str = ""
    description_ar: str | None = None
    is_editable: int = 1
    updated_by: int | None = None


@dataclass(slots=True)
class AuditLog(BaseModel):
    """سجل عملية إدارية حساسة."""

    id: int
    action: str
    created_at: str
    admin_id: int | None = None
    target_type: str | None = None
    target_id: str | None = None
    details_json: str | None = None
    before_json: str | None = None
    after_json: str | None = None
    source: str = "telegram"


@dataclass(slots=True)
class Broadcast(BaseModel):
    """رسالة جماعية."""

    id: int
    created_at: str
    admin_id: int | None = None
    message_text: str = ""
    parse_mode: str | None = None
    media_file_id: str | None = None
    media_type: str | None = None
    buttons_json: str | None = None
    target: str = "all"
    target_filter_json: str | None = None
    total_count: int = 0
    sent_count: int = 0
    failed_count: int = 0
    blocked_count: int = 0
    status: str = "draft"
    started_at: str | None = None
    finished_at: str | None = None


@dataclass(slots=True)
class NotificationTemplate(BaseModel):
    """قالب إشعار مخصّص من لوحة التحكم (المرحلة 8) — غيابه يعني استعمال النص الافتراضي."""

    code: str
    title: str
    body: str
    updated_at: str
    is_active: int = 1
    updated_by: int | None = None

    @property
    def enabled(self) -> bool:
        """هل القالب المخصّص مفعّل فعلاً (وإلا يعود النظام للنص المدمج)؟"""
        return bool(self.is_active)
```

## `database/repositories/orders.py`

```python
"""
مستودع الطلبات — أهم مستودع في النظام.

يوفّر العمليات الذرّية التي تمنع أخطر مشكلتين:
    1. تغيير حالة الطلب من مكانين في نفس اللحظة  → update_status المشروط بالحالة السابقة.
    2. معالجة نفس الطلب بواسطة أكثر من job       → claim_* مع قفل زمني (lease).
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from core.constants import ORDER_LOCK_SECONDS
from database.database import Tx
from database.models import Order, OrderStatusHistory
from database.repositories.base import BaseRepository
from utils.datetime_utils import iso_plus_seconds, utc_now_iso

_ALLOWED_FIELDS = {
    "status",
    "provider_status",
    "provider_order_id",
    "provider_cost_units",
    "start_count",
    "remains",
    "delivered_quantity",
    "refund_amount_units",
    "refunded_at",
    "submit_attempts",
    "checks_count",
    "last_error",
    "locked_by",
    "locked_until",
    "next_check_at",
    "submitted_at",
    "completed_at",
    "cancelled_at",
    "public_code",
}


class OrdersRepository(BaseRepository):
    """عمليات قراءة وكتابة الطلبات."""

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, order_id: int) -> Order | None:
        """جلب طلب بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM orders WHERE id = ?", (order_id,))
        return Order.from_row(row)

    async def get_by_client_request_id(self, client_request_id: str) -> Order | None:
        """
        جلب طلب بمفتاح الطلب الفريد القادم من واجهة المستخدم.

        الفائدة: إذا ضغط المستخدم «تأكيد» مرتين، نُرجع نفس الطلب بدل إنشاء طلب جديد.
        """
        row = await self.db.fetchone(
            "SELECT * FROM orders WHERE client_request_id = ?", (client_request_id,)
        )
        return Order.from_row(row)

    async def get_by_provider_order_id(self, provider_id: int, provider_order_id: str) -> Order | None:
        """جلب طلب برقمه عند المزود (للتسوية اليدوية)."""
        row = await self.db.fetchone(
            "SELECT * FROM orders WHERE provider_id = ? AND provider_order_id = ?",
            (provider_id, str(provider_order_id)),
        )
        return Order.from_row(row)

    async def list_by_user(
        self, user_id: int, *, statuses: Sequence[str] | None = None, limit: int = 8, offset: int = 0
    ) -> list[Order]:
        """قائمة طلبات مستخدم مع إمكانية الفلترة بالحالة."""
        sql = "SELECT * FROM orders WHERE user_id = ?"
        params: list[Any] = [user_id]
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            sql += f" AND status IN ({placeholders})"
            params.extend(statuses)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = await self.db.fetchall(sql, params)
        return Order.from_rows(rows)

    async def count_by_user(self, user_id: int, *, statuses: Sequence[str] | None = None) -> int:
        """عدد طلبات مستخدم (لحساب الصفحات والحدود اليومية)."""
        where = "user_id = ?"
        params: list[Any] = [user_id]
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            where += f" AND status IN ({placeholders})"
            params.extend(statuses)
        return await self.count("orders", where, params)

    async def count_today_by_user(self, user_id: int, since_iso: str) -> int:
        """عدد طلبات المستخدم منذ بداية اليوم (لتطبيق الحد اليومي)."""
        return await self.count("orders", "user_id = ? AND created_at >= ?", (user_id, since_iso))

    async def list_by_status(self, status: str, *, limit: int = 20, offset: int = 0) -> list[Order]:
        """قائمة الطلبات حسب الحالة (للوحة الأدمن)."""
        rows = await self.db.fetchall(
            "SELECT * FROM orders WHERE status = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (status, limit, offset),
        )
        return Order.from_rows(rows)

    async def list_by_statuses(
        self,
        statuses: Sequence[str] | None = None,
        *,
        user_id: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Order]:
        """
        قائمة الطلبات لعدة حالات دفعة واحدة (قوائم لوحة الأدمن).

        المدخلات:
            statuses : الحالات المطلوبة، و`None` أو قائمة فارغة تعني كل الحالات.
            user_id  : حصر النتائج بمستخدم واحد (تبويب «طلباته» في بطاقة المستخدم).
            limit/offset : الترقيم.

        المخرجات: قائمة طلبات مرتبة من الأحدث إلى الأقدم.
        """
        where, params = self._admin_filter(statuses, user_id)
        rows = await self.db.fetchall(
            f"SELECT * FROM orders WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        return Order.from_rows(rows)

    async def count_by_statuses(
        self, statuses: Sequence[str] | None = None, *, user_id: int | None = None
    ) -> int:
        """عدد الطلبات المطابقة لنفس مرشّحات `list_by_statuses` (لحساب عدد الصفحات)."""
        where, params = self._admin_filter(statuses, user_id)
        return await self.count("orders", where, tuple(params))

    @staticmethod
    def _admin_filter(
        statuses: Sequence[str] | None, user_id: int | None
    ) -> tuple[str, list[Any]]:
        """بناء شرط WHERE المشترك بين قائمة الأدمن وعدّادها (مصدر واحد للمنطق)."""
        clauses: list[str] = ["1 = 1"]
        params: list[Any] = []
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(statuses)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        return " AND ".join(clauses), params

    async def status_counts(self) -> dict[str, int]:
        """عدد الطلبات في كل حالة (لوحة الإحصائيات)."""
        rows = await self.db.fetchall("SELECT status, COUNT(*) AS c FROM orders GROUP BY status")
        return {row["status"]: int(row["c"]) for row in rows}

    async def find_recent_duplicate(
        self, *, user_id: int, service_id: int, link: str, quantity: int, since_iso: str
    ) -> Order | None:
        """
        كشف طلب مشابه خلال نافذة زمنية (نفس المستخدم والخدمة والرابط والكمية).

        الفائدة: تحذير المستخدم قبل تكرار الدفع بالخطأ.
        """
        row = await self.db.fetchone(
            """
            SELECT * FROM orders
             WHERE user_id = ? AND service_id = ? AND link = ? AND quantity = ?
               AND created_at >= ?
               AND status NOT IN ('failed', 'canceled', 'refunded')
             ORDER BY id DESC LIMIT 1
            """,
            (user_id, service_id, link, quantity, since_iso),
        )
        return Order.from_row(row)

    async def history(self, order_id: int) -> list[OrderStatusHistory]:
        """سجل انتقالات حالة الطلب."""
        rows = await self.db.fetchall(
            "SELECT * FROM order_status_history WHERE order_id = ? ORDER BY id", (order_id,)
        )
        return OrderStatusHistory.from_rows(rows)

    async def stuck_orders(self, *, before_iso: str, limit: int = 20) -> list[Order]:
        """الطلبات النشطة التي تجاوزت المدة المتوقعة (لتنبيه الأدمن)."""
        rows = await self.db.fetchall(
            """
            SELECT * FROM orders
             WHERE status IN ('pending', 'submitting', 'submit_uncertain', 'submitted', 'in_progress')
               AND created_at <= ?
             ORDER BY id LIMIT ?
            """,
            (before_iso, limit),
        )
        return Order.from_rows(rows)

    # ------------------------- الإحصائيات المالية (م10) ------------------------- #
    #
    # دلالة الأرقام (موحَّدة في كل التقارير):
    #   • الفترة تُحسب بوقت إنشاء الطلب (created_at) لأن الخصم يقع وقتها.
    #   • الإجمالي (gross) = Σ cost_units · المسترجع = Σ refund_amount_units.
    #   • الإيراد الصافي = الإجمالي − المسترجع. الطلب الملغى/الفاشل المسترجع كاملاً يُنتج صفراً،
    #     والجزئي يُحتسب بما بقي مخصوماً فعلاً. (المجموع الخام القديم كان يُضخّم الإيراد.)

    async def period_totals(self, start_iso: str, end_iso: str) -> dict[str, int]:
        """
        مجاميع فترة: عدد الطلبات، الإجمالي، المسترجع، الصافي، وعدد المشترين المختلفين.

        المخرجات: orders_count, gross_units, refund_units, net_units, buyers.
        """
        row = await self.db.fetchone(
            """
            SELECT COUNT(*)                                   AS orders_count,
                   COALESCE(SUM(cost_units), 0)               AS gross_units,
                   COALESCE(SUM(refund_amount_units), 0)      AS refund_units,
                   COUNT(DISTINCT user_id)                    AS buyers
              FROM orders
             WHERE created_at >= ? AND created_at < ?
            """,
            (start_iso, end_iso),
        )
        gross = int(row["gross_units"]) if row else 0
        refund = int(row["refund_units"]) if row else 0
        return {
            "orders_count": int(row["orders_count"]) if row else 0,
            "gross_units": gross,
            "refund_units": refund,
            "net_units": gross - refund,
            "buyers": int(row["buyers"]) if row else 0,
        }

    async def sum_net_between(self, start_iso: str, end_iso: str) -> int:
        """الإيراد الصافي لفترة (الإجمالي − المسترجع) بوحدات المال الصحيحة."""
        return (await self.period_totals(start_iso, end_iso))["net_units"]

    async def status_counts_between(self, start_iso: str, end_iso: str) -> dict[str, int]:
        """عدد طلبات الفترة في كل حالة."""
        rows = await self.db.fetchall(
            """
            SELECT status, COUNT(*) AS c FROM orders
             WHERE created_at >= ? AND created_at < ? GROUP BY status
            """,
            (start_iso, end_iso),
        )
        return {row["status"]: int(row["c"]) for row in rows}

    async def profit_inputs(self, start_iso: str, end_iso: str) -> dict[str, int]:
        """
        مدخلات الربح التقديري لفترة — **للطلبات المنتهية فقط** (مكتمل/جزئي).

        لماذا المنتهية فقط؟ إيراد الطلب الجاري غير مُحقَّق وقد يُسترجع، فخلطه بتكلفة مزود
        لم تُحسم يعطي ربحاً وهمياً. ولماذا «المغطّاة» فقط؟ تكلفة المزود تُسجَّل حين يردّ
        المزود بها؛ الطلب بلا تكلفة مسجّلة لا يدخل الحساب ويُعلن نسبة التغطية بدل التخمين.

        التكلفة الفعلية للطلب الجزئي تُقسَّم بنسبة ما بقي مخصوماً: `تكلفة × (cost−refund)/cost`
        (المزود لم يُسلّم الباقي). تُحسب بحساب صحيح في بايثون للصفوف ذات الاسترجاع (قليلة)،
        وفي SQL لغيرها (لا مضروبات ضخمة تتحول إلى أعداد عشرية).

        المخرجات:
            eligible_orders / eligible_net_units : كل الطلبات المنتهية وصافيها.
            covered_orders  / covered_net_units  : المغطّاة بتكلفة مزود وصافيها.
            covered_cost_units                   : تكلفة المزود الفعلية لها.
        """
        eligible = await self.db.fetchone(
            """
            SELECT COUNT(*) AS n, COALESCE(SUM(cost_units - refund_amount_units), 0) AS net
              FROM orders
             WHERE created_at >= ? AND created_at < ? AND status IN ('completed', 'partial')
            """,
            (start_iso, end_iso),
        )
        full = await self.db.fetchone(
            """
            SELECT COUNT(*) AS n,
                   COALESCE(SUM(cost_units), 0) AS net,
                   COALESCE(SUM(provider_cost_units), 0) AS cost
              FROM orders
             WHERE created_at >= ? AND created_at < ? AND status IN ('completed', 'partial')
               AND provider_cost_units IS NOT NULL AND refund_amount_units = 0
            """,
            (start_iso, end_iso),
        )
        prorated = await self.db.fetchall(
            """
            SELECT cost_units, refund_amount_units, provider_cost_units FROM orders
             WHERE created_at >= ? AND created_at < ? AND status IN ('completed', 'partial')
               AND provider_cost_units IS NOT NULL AND refund_amount_units > 0
            """,
            (start_iso, end_iso),
        )
        covered_orders = int(full["n"]) if full else 0
        covered_net = int(full["net"]) if full else 0
        covered_cost = int(full["cost"]) if full else 0
        for row in prorated:
            cost, refund, provider_cost = (int(row[k]) for k in ("cost_units", "refund_amount_units", "provider_cost_units"))
            net = cost - refund
            covered_orders += 1
            covered_net += net
            covered_cost += (provider_cost * net) // cost if cost > 0 else provider_cost
        return {
            "eligible_orders": int(eligible["n"]) if eligible else 0,
            "eligible_net_units": int(eligible["net"]) if eligible else 0,
            "covered_orders": covered_orders,
            "covered_net_units": covered_net,
            "covered_cost_units": covered_cost,
        }

    async def count_between(self, start_iso: str, end_iso: str) -> int:
        """عدد الطلبات المنشأة بين تاريخين (للإحصائيات)."""
        return await self.count("orders", "created_at >= ? AND created_at < ?", (start_iso, end_iso))

    async def count_between_by_status(
        self, start_iso: str, end_iso: str, statuses: Sequence[str]
    ) -> int:
        """عدد الطلبات بين تاريخين ضمن حالات محددة (نسبة النجاح/الفشل)."""
        placeholders = ", ".join("?" for _ in statuses)
        return await self.count(
            "orders",
            f"created_at >= ? AND created_at < ? AND status IN ({placeholders})",
            [start_iso, end_iso, *statuses],
        )

    async def top_services(
        self, *, start_iso: str, end_iso: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """
        أكثر الخدمات طلباً خلال فترة (مرتبة بعدد الطلبات ثم بالصافي).

        المخرجات: صفوف فيها service_name و orders_count و total_units (الصافي) و gross_units.
        """
        rows = await self.db.fetchall(
            """
            SELECT service_name_snapshot                         AS service_name,
                   COUNT(*)                                       AS orders_count,
                   COALESCE(SUM(cost_units), 0)                   AS gross_units,
                   COALESCE(SUM(cost_units - refund_amount_units), 0) AS total_units
              FROM orders
             WHERE created_at >= ? AND created_at < ?
             GROUP BY service_id
             ORDER BY orders_count DESC, total_units DESC, service_id
             LIMIT ?
            """,
            (start_iso, end_iso, limit),
        )
        return [dict(row) for row in rows]

    async def top_buyers(self, *, start_iso: str, end_iso: str, limit: int = 5) -> list[dict[str, Any]]:
        """
        أكثر العملاء إنفاقاً **صافياً** خلال فترة (من الطلبات لا من عدّاد المستخدم المتراكم).

        المخرجات: صفوف فيها user_id و orders_count و net_units (الأعلى أولاً، بلا أصفار).
        """
        rows = await self.db.fetchall(
            """
            SELECT user_id,
                   COUNT(*) AS orders_count,
                   COALESCE(SUM(cost_units - refund_amount_units), 0) AS net_units
              FROM orders
             WHERE created_at >= ? AND created_at < ?
             GROUP BY user_id
            HAVING net_units > 0
             ORDER BY net_units DESC, user_id
             LIMIT ?
            """,
            (start_iso, end_iso, limit),
        )
        return [dict(row) for row in rows]

    async def minute_buckets(self, start_iso: str, end_iso: str) -> list[dict[str, Any]]:
        """
        تجميع الطلبات بالدقيقة (UTC) بدل اليوم: يترك للخدمة تجميعها بأيام **محلية**.

        لماذا؟ `substr(created_at,1,10)` يقسّم اليوم عند منتصف الليل UTC لا المحلي، فتظهر
        طلبات ما بعد الثالثة فجراً (توقيت عدن) في اليوم الخطأ. التجميع بالدقيقة صحيح
        لأي إزاحة (حتى نصف الساعة) وعدد الصفوف لا يتجاوز عدد الطلبات.
        """
        rows = await self.db.fetchall(
            """
            SELECT substr(created_at, 1, 16)                    AS minute,
                   COUNT(*)                                      AS orders_count,
                   COALESCE(SUM(cost_units), 0)                  AS gross_units,
                   COALESCE(SUM(refund_amount_units), 0)         AS refund_units
              FROM orders
             WHERE created_at >= ? AND created_at < ?
             GROUP BY minute
             ORDER BY minute
            """,
            (start_iso, end_iso),
        )
        return [dict(row) for row in rows]

    async def export_rows(self, start_iso: str, end_iso: str, *, limit: int) -> list[dict[str, Any]]:
        """
        صفوف طلبات الفترة للتصدير (الأقدم أولاً). لا رابط العميل ولا معرّف تيليجرام عمداً.

        المخرجات: حتى `limit` صفاً (اطلب سقفاً+1 لمعرفة هل قُطعت النتيجة).
        """
        rows = await self.db.fetchall(
            """
            SELECT id, public_code, created_at, user_id, service_name_snapshot AS service_name,
                   quantity, status, cost_units, refund_amount_units, provider_cost_units,
                   delivered_quantity
              FROM orders
             WHERE created_at >= ? AND created_at < ?
             ORDER BY id
             LIMIT ?
            """,
            (start_iso, end_iso, limit),
        )
        return [dict(row) for row in rows]

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        user_id: int,
        service_id: int,
        provider_id: int,
        service_name_snapshot: str,
        price_per_1000_snapshot_units: int,
        link: str,
        quantity: int,
        cost_units: int,
        client_request_id: str,
        provider_cost_units: int | None = None,
        status: str = "pending",
    ) -> Order:
        """
        إنشاء طلب جديد بحالة pending.

        ملاحظة: خصم الرصيد وتسجيل الحركة المالية يتمان في نفس المعاملة
        داخل OrderService، وليس هنا.
        """
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO orders (user_id, service_id, provider_id, service_name_snapshot,
                                price_per_1000_snapshot_units, link, quantity, cost_units,
                                provider_cost_units, status, client_request_id,
                                created_at, updated_at, next_check_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, service_id, provider_id, service_name_snapshot,
                price_per_1000_snapshot_units, link, quantity, cost_units,
                provider_cost_units, status, client_request_id, now, now, now,
            ),
        )
        row = await tx.fetchone("SELECT * FROM orders WHERE id = ?", (result.lastrowid,))
        order = Order.from_row(row)
        assert order is not None
        return order

    async def add_history(
        self,
        tx: Tx,
        *,
        order_id: int,
        from_status: str | None,
        to_status: str,
        actor_type: str = "system",
        actor_id: int | None = None,
        reason: str | None = None,
        provider_status_raw: str | None = None,
    ) -> None:
        """تسجيل انتقال حالة في سجل الطلب (يُستدعى مع كل تغيير حالة)."""
        await tx.execute(
            """
            INSERT INTO order_status_history (order_id, from_status, to_status, actor_type,
                                              actor_id, reason, provider_status_raw, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (order_id, from_status, to_status, actor_type, actor_id, reason, provider_status_raw, self.now()),
        )

    async def update_status(
        self,
        tx: Tx,
        order_id: int,
        *,
        new_status: str,
        expected_statuses: Iterable[str],
        extra_fields: dict[str, Any] | None = None,
    ) -> bool:
        """
        تغيير حالة الطلب بشكل مشروط بالحالة الحالية (العمود الفقري لمنع التغيير العشوائي).

        المدخلات:
            new_status        : الحالة الجديدة.
            expected_statuses : الحالات المسموح الانتقال منها.
            extra_fields      : حقول إضافية تُحدَّث في نفس العبارة (رقم المزود، أوقات ...).

        المخرجات: True إذا تم التغيير فعلاً، False إذا كانت حالة الطلب مختلفة
                  (يعني أن جهة أخرى غيّرتها قبلنا — وهذا ليس خطأً بل حماية).
        """
        statuses = list(expected_statuses)
        if not statuses:
            raise ValueError("يجب تحديد الحالات المتوقعة قبل تغيير حالة الطلب.")

        fields: dict[str, Any] = {"status": new_status}
        if extra_fields:
            fields.update(extra_fields)
        set_sql, values = self._build_update(fields, _ALLOWED_FIELDS)
        set_sql += ", updated_at = ?"
        values.append(self.now())
        placeholders = ", ".join("?" for _ in statuses)
        values.append(order_id)
        values.extend(statuses)

        result = await tx.execute(
            f"UPDATE orders SET {set_sql} WHERE id = ? AND status IN ({placeholders})", values
        )
        return result.rowcount == 1

    async def update_fields(self, tx: Tx, order_id: int, **fields: Any) -> bool:
        """تعديل حقول غير حالة الطلب (تقدم التنفيذ، مواعيد الفحص ...)."""
        return await self._update_by_id(tx, "orders", order_id, fields, _ALLOWED_FIELDS)

    async def add_refund_amount(self, tx: Tx, order_id: int, amount_units: int) -> bool:
        """
        زيادة مبلغ الاسترجاع المسجَّل على الطلب دون تجاوز التكلفة.

        المخرجات: True عند النجاح، False إذا كان المبلغ سيتجاوز تكلفة الطلب
                  (حماية إضافية فوق قيد CHECK في قاعدة البيانات).
        """
        result = await tx.execute(
            """
            UPDATE orders
               SET refund_amount_units = refund_amount_units + ?,
                   refunded_at = ?, updated_at = ?
             WHERE id = ? AND refund_amount_units + ? <= cost_units
            """,
            (amount_units, self.now(), self.now(), order_id, amount_units),
        )
        return result.rowcount == 1

    # --------------------------- الأقفال والمهام --------------------------- #

    async def claim_pending_for_submit(
        self, tx: Tx, *, worker: str, limit: int = 5, lock_seconds: int = ORDER_LOCK_SECONDS
    ) -> list[Order]:
        """
        حجز دفعة من الطلبات المعلّقة لإرسالها للمزود.

        الآلية: لكل طلب مرشّح يُنفَّذ UPDATE مشروط (status='pending' وغير مقفول)؛
        من ينجح UPDATE الخاص به هو من يملك الطلب — فلا يعالجه worker آخر.

        ملاحظة: يُحترم `next_check_at` هنا أيضاً، لأن الطلب الذي فشل إرساله مؤقتاً
        يعود إلى pending بموعد محاولة مؤجَّل؛ وتجاهل الموعد يعني إغراق المزود
        بمحاولات متتالية بلا تهدئة.
        """
        now = utc_now_iso()
        candidates = await tx.fetchall(
            """
            SELECT id FROM orders
             WHERE status = 'pending'
               AND (next_check_at IS NULL OR next_check_at <= ?)
               AND (locked_until IS NULL OR locked_until < ?)
             ORDER BY id LIMIT ?
            """,
            (now, now, limit),
        )
        claimed: list[Order] = []
        for row in candidates:
            ok = await tx.execute(
                """
                UPDATE orders
                   SET status = 'submitting', locked_by = ?, locked_until = ?,
                       submit_attempts = submit_attempts + 1, updated_at = ?
                 WHERE id = ? AND status = 'pending'
                   AND (locked_until IS NULL OR locked_until < ?)
                """,
                (worker, iso_plus_seconds(lock_seconds), now, row["id"], now),
            )
            if ok.rowcount == 1:
                order_row = await tx.fetchone("SELECT * FROM orders WHERE id = ?", (row["id"],))
                order = Order.from_row(order_row)
                if order is not None:
                    claimed.append(order)
                    await self.add_history(
                        tx,
                        order_id=order.id,
                        from_status="pending",
                        to_status="submitting",
                        actor_type="job",
                        reason=f"حجز للإرسال بواسطة {worker}",
                    )
        return claimed

    async def claim_due_for_check(
        self, tx: Tx, *, worker: str, limit: int = 20, lock_seconds: int = ORDER_LOCK_SECONDS
    ) -> list[Order]:
        """
        حجز دفعة من الطلبات النشطة التي حان موعد فحص حالتها عند المزود.

        لا تُغيَّر حالة الطلب هنا — فقط يوضع قفل زمني لتفادي الفحص المزدوج.
        """
        now = utc_now_iso()
        candidates = await tx.fetchall(
            """
            SELECT id FROM orders
             WHERE status IN ('submitted', 'in_progress')
               AND provider_order_id IS NOT NULL
               AND (next_check_at IS NULL OR next_check_at <= ?)
               AND (locked_until IS NULL OR locked_until < ?)
             ORDER BY next_check_at LIMIT ?
            """,
            (now, now, limit),
        )
        claimed: list[Order] = []
        for row in candidates:
            ok = await tx.execute(
                """
                UPDATE orders
                   SET locked_by = ?, locked_until = ?, checks_count = checks_count + 1, updated_at = ?
                 WHERE id = ? AND (locked_until IS NULL OR locked_until < ?)
                """,
                (worker, iso_plus_seconds(lock_seconds), now, row["id"], now),
            )
            if ok.rowcount == 1:
                order_row = await tx.fetchone("SELECT * FROM orders WHERE id = ?", (row["id"],))
                order = Order.from_row(order_row)
                if order is not None:
                    claimed.append(order)
        return claimed

    async def release_lock(self, tx: Tx, order_id: int, *, next_check_at: str | None = None) -> None:
        """تحرير قفل الطلب بعد انتهاء المعالجة، مع تحديد موعد الفحص القادم اختيارياً."""
        if next_check_at is None:
            await tx.execute(
                "UPDATE orders SET locked_by = NULL, locked_until = NULL, updated_at = ? WHERE id = ?",
                (self.now(), order_id),
            )
        else:
            await tx.execute(
                """
                UPDATE orders SET locked_by = NULL, locked_until = NULL,
                       next_check_at = ?, updated_at = ? WHERE id = ?
                """,
                (next_check_at, self.now(), order_id),
            )

    async def renew_submit_lock(self, tx: Tx, order_id: int, *, worker: str, lock_seconds: int = ORDER_LOCK_SECONDS) -> bool:
        """
        تمديد قفل طلب في `submitting` قبل إرساله فعلاً.

        الفائدة: دفعة من عدة طلبات تُحجز بقفل واحد، وقد يبدأ إرسال آخرها بعد انتهاء قفله
        فيحسبه الاسترداد الدوري عالقاً. التمديد مشروط بأن يظل الطلب لهذا العامل.
        """
        result = await tx.execute(
            """
            UPDATE orders SET locked_until = ?, updated_at = ?
             WHERE id = ? AND status = 'submitting' AND locked_by = ?
            """,
            (iso_plus_seconds(lock_seconds), self.now(), order_id, worker),
        )
        return result.rowcount == 1

    async def release_expired_locks(self, tx: Tx) -> int:
        """
        تحرير كل الأقفال المنتهية (يُستدعى عند إقلاع البوت ضمن عملية الاسترداد).

        المخرجات: عدد الطلبات التي حُرِّرت.
        """
        result = await tx.execute(
            """
            UPDATE orders SET locked_by = NULL, locked_until = NULL, updated_at = ?
             WHERE locked_until IS NOT NULL AND locked_until < ?
            """,
            (self.now(), utc_now_iso()),
        )
        return result.rowcount

    async def recover_submitting_orders(self, tx: Tx, *, only_expired: bool = False) -> list[int]:
        """
        معالجة الطلبات العالقة في حالة submitting (بعد إعادة تشغيل مفاجئ أو انتهاء مهلة جولة الإرسال).

        القاعدة: إذا لم يُسجَّل رقم الطلب عند المزود فالنتيجة غير مؤكدة
        (ربما وصل الطلب وربما لا) ⇒ تُنقل إلى submit_uncertain لمراجعة الأدمن،
        وممنوع إعادة إرسالها تلقائياً.

        المدخلات:
            only_expired : False عند الإقلاع (لا عامل حيّ بعد، فكل `submitting` عالق).
                           True أثناء التشغيل: لا يُمسّ إلا ما انتهى قفله (لا ينتزع طلباً
                           ما زال عامل حيّ يرسله).

        المخرجات: قائمة معرفات الطلبات التي نُقلت إلى submit_uncertain.
        """
        if only_expired:
            rows = await tx.fetchall(
                """
                SELECT id FROM orders
                 WHERE status = 'submitting' AND provider_order_id IS NULL
                   AND (locked_until IS NULL OR locked_until < ?)
                """,
                (utc_now_iso(),),
            )
        else:
            rows = await tx.fetchall(
                "SELECT id FROM orders WHERE status = 'submitting' AND provider_order_id IS NULL"
            )
        ids: list[int] = []
        for row in rows:
            ok = await tx.execute(
                """
                UPDATE orders SET status = 'submit_uncertain', locked_by = NULL, locked_until = NULL,
                       last_error = 'انقطاع أثناء الإرسال - تحتاج مراجعة يدوية', updated_at = ?
                 WHERE id = ? AND status = 'submitting'
                """,
                (self.now(), row["id"]),
            )
            if ok.rowcount == 1:
                ids.append(int(row["id"]))
                await self.add_history(
                    tx,
                    order_id=int(row["id"]),
                    from_status="submitting",
                    to_status="submit_uncertain",
                    actor_type="system",
                    reason="استرداد بعد انقطاع الإرسال" if only_expired else "استرداد بعد إعادة تشغيل البوت",
                )
        return ids
```

## `database/repositories/providers.py`

```python
"""
مستودع المزودين — بيانات الاتصال بلوحات SMM الخارجية.

ملاحظة أمنية: مفتاح API يُخزَّن مشفّراً في api_key_enc، ولا تُرجع هذه الطبقة
المفتاح الأصلي أبداً؛ فك التشفير يتم في ProviderService عند الاستدعاء فقط.
"""

from __future__ import annotations

from typing import Any

from database.database import Tx
from database.models import Provider
from database.repositories.base import BaseRepository

_ALLOWED_FIELDS = {
    "name",
    "api_url",
    "api_key_enc",
    "api_key_hint",
    "api_type",
    "balance_units",
    "currency",
    "exchange_rate",
    "balance_checked_at",
    "low_balance_threshold_units",
    "is_active",
    "priority",
    "timeout_seconds",
    "consecutive_failures",
    "disabled_until",
    "last_error",
    "last_success_at",
}


class ProvidersRepository(BaseRepository):
    """عمليات قراءة وكتابة بيانات المزودين."""

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, provider_id: int) -> Provider | None:
        """جلب مزود بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM providers WHERE id = ?", (provider_id,))
        return Provider.from_row(row)

    async def get_by_name(self, name: str) -> Provider | None:
        """جلب مزود بالاسم (الاسم فريد)."""
        row = await self.db.fetchone("SELECT * FROM providers WHERE name = ?", (name,))
        return Provider.from_row(row)

    async def list_all(self, *, active_only: bool = False) -> list[Provider]:
        """قائمة المزودين مرتبة حسب الأولوية."""
        sql = "SELECT * FROM providers"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY priority, id"
        rows = await self.db.fetchall(sql)
        return Provider.from_rows(rows)

    async def count_services(self, provider_id: int) -> int:
        """عدد الخدمات المرتبطة بمزود (للتحذير قبل تعطيله)."""
        return await self.count("services", "provider_id = ? AND is_archived = 0", (provider_id,))

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        name: str,
        api_url: str,
        api_key_enc: str,
        api_key_hint: str | None = None,
        api_type: str = "perfect_panel",
        currency: str = "USD",
        exchange_rate: str | None = None,
        timeout_seconds: int = 30,
        priority: int = 100,
    ) -> Provider:
        """إضافة مزود جديد (المفتاح يصل مشفّراً من ProviderService)."""
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO providers (name, api_url, api_key_enc, api_key_hint, api_type, currency,
                                   exchange_rate, timeout_seconds, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name, api_url, api_key_enc, api_key_hint, api_type, currency, exchange_rate,
                timeout_seconds, priority, now, now,
            ),
        )
        row = await tx.fetchone("SELECT * FROM providers WHERE id = ?", (result.lastrowid,))
        provider = Provider.from_row(row)
        assert provider is not None
        return provider

    async def update_fields(self, tx: Tx, provider_id: int, **fields: Any) -> bool:
        """تعديل حقول مسموح بها للمزود."""
        return await self._update_by_id(tx, "providers", provider_id, fields, _ALLOWED_FIELDS)

    async def update_balance(self, tx: Tx, provider_id: int, balance_units: int) -> bool:
        """
        تحديث رصيد المزود بعد فحصه، مع تسجيل وقت الفحص.

        لا يلمس `currency` عمداً: عملة المزود إعداد يحدّده الأدمن مع سعر صرفه، ولا يجوز لاستجابة API أن
        تبدّله بصمت فتُبطل سعر الصرف (التعارض يُنبَّه عليه في ProviderService).
        """
        fields: dict[str, Any] = {
            "balance_units": balance_units,
            "balance_checked_at": self.now(),
        }
        return await self._update_by_id(tx, "providers", provider_id, fields, _ALLOWED_FIELDS)

    async def record_success(self, tx: Tx, provider_id: int) -> None:
        """تصفير عداد الأخطاء المتتالية بعد استدعاء ناجح."""
        await tx.execute(
            """
            UPDATE providers
               SET consecutive_failures = 0, disabled_until = NULL,
                   last_error = NULL, last_success_at = ?, updated_at = ?
             WHERE id = ?
            """,
            (self.now(), self.now(), provider_id),
        )

    async def record_failure(
        self, tx: Tx, provider_id: int, error: str, *, disable_until: str | None = None
    ) -> int:
        """
        تسجيل فشل استدعاء وزيادة عداد الأخطاء المتتالية (قاطع الدائرة).

        المخرجات: عدد الأخطاء المتتالية بعد التحديث.
        """
        await tx.execute(
            """
            UPDATE providers
               SET consecutive_failures = consecutive_failures + 1,
                   last_error = ?, disabled_until = COALESCE(?, disabled_until), updated_at = ?
             WHERE id = ?
            """,
            (error[:500], disable_until, self.now(), provider_id),
        )
        return int(
            await self.db.fetchval(
                "SELECT consecutive_failures FROM providers WHERE id = ?", (provider_id,), default=0
            )
        )

    async def set_active(self, tx: Tx, provider_id: int, active: bool) -> bool:
        """تفعيل أو تعطيل مزود يدوياً."""
        return await self._update_by_id(
            tx, "providers", provider_id, {"is_active": 1 if active else 0}, _ALLOWED_FIELDS
        )

    async def add_balance_snapshot(
        self, tx: Tx, provider_id: int, balance_units: int, currency: str = "USD"
    ) -> None:
        """حفظ لقطة لرصيد المزود لتتبع الاتجاه والتنبيه المبكر."""
        await tx.execute(
            """
            INSERT INTO provider_balance_snapshots (provider_id, balance_units, currency, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (provider_id, balance_units, currency, self.now()),
        )
```

## `database/repositories/broadcasts.py`

```python
"""
مستودع الإذاعة — الرسائل الجماعية وقوائم المستلمين.

سبب تخزين المستلمين في جدول مستقل:
    إذا أُعيد تشغيل البوت أثناء إذاعة لآلاف المستخدمين، يجب أن تُستأنف من حيث توقفت،
    وألا يستلم أحد الرسالة مرتين.
"""

from __future__ import annotations

from typing import Any, Sequence, Iterable

from database.database import Tx
from database.models import Broadcast
from database.repositories.base import BaseRepository

_BROADCAST_FIELDS = {
    "message_text",
    "parse_mode",
    "media_file_id",
    "media_type",
    "buttons_json",
    "target",
    "target_filter_json",
    "total_count",
    "sent_count",
    "failed_count",
    "blocked_count",
    "status",
    "started_at",
    "finished_at",
}


class BroadcastsRepository(BaseRepository):
    """إنشاء الإذاعات ومتابعة تقدمها."""

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        admin_id: int | None,
        message_text: str,
        target: str = "all",
        parse_mode: str | None = None,
        media_file_id: str | None = None,
        media_type: str | None = None,
        buttons_json: str | None = None,
        target_filter_json: str | None = None,
    ) -> Broadcast:
        """إنشاء إذاعة جديدة بحالة draft."""
        result = await tx.execute(
            """
            INSERT INTO broadcasts (admin_id, message_text, parse_mode, media_file_id, media_type,
                                    buttons_json, target, target_filter_json, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?)
            """,
            (
                admin_id, message_text, parse_mode, media_file_id, media_type,
                buttons_json, target, target_filter_json, self.now(),
            ),
        )
        row = await tx.fetchone("SELECT * FROM broadcasts WHERE id = ?", (result.lastrowid,))
        broadcast = Broadcast.from_row(row)
        assert broadcast is not None
        return broadcast

    async def add_recipients(self, tx: Tx, broadcast_id: int, user_ids: Iterable[int]) -> int:
        """
        إضافة قائمة المستلمين للإذاعة (تتجاهل المكرر بفضل قيد UNIQUE).

        المخرجات: عدد المستلمين المضافين فعلاً.
        """
        ids = list(user_ids)
        if not ids:
            return 0
        await tx.executemany(
            "INSERT OR IGNORE INTO broadcast_recipients (broadcast_id, user_id) VALUES (?, ?)",
            [(broadcast_id, uid) for uid in ids],
        )
        total = await self.count("broadcast_recipients", "broadcast_id = ?", (broadcast_id,))
        await tx.execute(
            "UPDATE broadcasts SET total_count = ? WHERE id = ?", (total, broadcast_id)
        )
        return total

    async def claim_recipients(self, tx: Tx, broadcast_id: int, *, limit: int = 20) -> list[dict]:
        """
        حجز دفعة من المستلمين المنتظرين للإرسال إليهم.

        الآلية: تحديث الحالة إلى sent يتم بعد الإرسال الفعلي؛ هنا نقرأ فقط دفعة صغيرة
        مرتبة (لا حجز فعلياً في القاعدة). منع الإرسال المزدوج بين جولتين متزامنتين
        مسؤولية `BroadcastService` عبر قفل الجولة (`_round_lock`)، أما التسجيل المشروط
        بـ pending في `mark_recipient` فيمنع العدّ المزدوج فقط. الضمان: at-least-once —
        انهيار العملية بين الإرسال والتسجيل قد يعيد إرسال رسالة واحدة لمستلم واحد.
        """
        rows = await tx.fetchall(
            """
            SELECT r.id, r.user_id, u.telegram_id
              FROM broadcast_recipients r
              JOIN users u ON u.id = r.user_id
             WHERE r.broadcast_id = ? AND r.status = 'pending'
             ORDER BY r.id LIMIT ?
            """,
            (broadcast_id, limit),
        )
        return [dict(row) for row in rows]

    async def mark_recipient(
        self, tx: Tx, recipient_id: int, *, status: str, error: str | None = None
    ) -> bool:
        """
        تسجيل نتيجة الإرسال لمستلم واحد (مشروط بأن حالته ما زالت pending).

        المخرجات: True إذا سُجِّلت النتيجة الآن (يمنع العدّ المزدوج).
        """
        result = await tx.execute(
            """
            UPDATE broadcast_recipients SET status = ?, error = ?, sent_at = ?
             WHERE id = ? AND status = 'pending'
            """,
            (status, error[:200] if error else None, self.now(), recipient_id),
        )
        if result.rowcount != 1:
            return False

        column = {"sent": "sent_count", "failed": "failed_count", "blocked": "blocked_count"}.get(status)
        if column:
            broadcast_id = await tx.fetchval(
                "SELECT broadcast_id FROM broadcast_recipients WHERE id = ?", (recipient_id,)
            )
            await tx.execute(
                f"UPDATE broadcasts SET {column} = {column} + 1 WHERE id = ?", (broadcast_id,)
            )
        return True

    async def set_status(
        self,
        tx: Tx,
        broadcast_id: int,
        status: str,
        *,
        expected_statuses: Sequence[str] | None = None,
        **fields: Any,
    ) -> bool:
        """
        تغيير حالة الإذاعة (running/paused/completed/cancelled) بشرط ذرّي على الحالة السابقة.

        `expected_statuses`: الحالات التي يجوز الانتقال منها؛ يُنفَّذ الشرط داخل جملة UPDATE نفسها فلا يطغى
        قرارٌ قديم (قرأه المستدعي قبل لحظة) على قرار أحدث: إيقاف/إلغاء متزامنان مع الإكمال أو البدء.

        المخرجات: True إن تغيّرت الحالة فعلاً، False إن لم تكن الحالة الحالية ضمن المتوقعة.
        """
        data = {"status": status, **fields}
        set_sql, values = self._build_update(data, _BROADCAST_FIELDS)
        where = "id = ?"
        values.append(broadcast_id)
        if expected_statuses:
            where += f" AND status IN ({','.join('?' for _ in expected_statuses)})"
            values.extend(str(item) for item in expected_statuses)
        result = await tx.execute(f"UPDATE broadcasts SET {set_sql} WHERE {where}", values)
        return result.rowcount > 0

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, broadcast_id: int) -> Broadcast | None:
        """جلب إذاعة بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM broadcasts WHERE id = ?", (broadcast_id,))
        return Broadcast.from_row(row)

    async def list_recent(self, *, limit: int = 10) -> list[Broadcast]:
        """آخر الإذاعات."""
        rows = await self.db.fetchall("SELECT * FROM broadcasts ORDER BY id DESC LIMIT ?", (limit,))
        return Broadcast.from_rows(rows)

    async def list_running(self) -> list[Broadcast]:
        """الإذاعات الجارية (تُستأنف عند إقلاع البوت)."""
        rows = await self.db.fetchall("SELECT * FROM broadcasts WHERE status = 'running' ORDER BY id")
        return Broadcast.from_rows(rows)

    async def pending_count(self, broadcast_id: int) -> int:
        """عدد المستلمين المتبقين في إذاعة."""
        return await self.count(
            "broadcast_recipients", "broadcast_id = ? AND status = 'pending'", (broadcast_id,)
        )
```

## `database/repositories/misc.py`

```python
"""
مستودعات مساعدة صغيرة:
    • ProviderRequestsRepository: سجل استدعاءات APIs المزودين (بدون أسرار).
    • ErrorLogsRepository      : تسجيل الأخطاء المهمة في قاعدة البيانات.
    • BackupsRepository        : سجل النسخ الاحتياطية.
"""

from __future__ import annotations

from core.constants import PROVIDER_RESPONSE_SNIPPET_LEN
from database.database import Tx
from database.repositories.base import BaseRepository
from utils.security import sanitize


class ProviderRequestsRepository(BaseRepository):
    """سجل استدعاءات المزودين لأغراض التشخيص (منقّى من الأسرار)."""

    async def log(
        self,
        tx: Tx,
        *,
        provider_id: int,
        action: str,
        is_success: bool,
        order_id: int | None = None,
        request_summary: str | None = None,
        http_status: int | None = None,
        response_snippet: str | None = None,
        duration_ms: int | None = None,
        error_type: str | None = None,
        secrets: tuple[str, ...] = (),
    ) -> None:
        """
        تسجيل استدعاء واحد لمزود.

        ملاحظة أمنية: يمر النص على دالة التنقية لحذف أي مفتاح قبل التخزين،
        ويُقتطع الرد حتى لا تتضخم قاعدة البيانات.
        """
        await tx.execute(
            """
            INSERT INTO provider_requests (provider_id, order_id, action, request_summary, http_status,
                                           response_snippet, duration_ms, is_success, error_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provider_id,
                order_id,
                action,
                sanitize(request_summary, secrets)[:PROVIDER_RESPONSE_SNIPPET_LEN],
                http_status,
                sanitize(response_snippet, secrets)[:PROVIDER_RESPONSE_SNIPPET_LEN],
                duration_ms,
                1 if is_success else 0,
                error_type,
                self.now(),
            ),
        )

    async def list_by_provider(self, provider_id: int, *, limit: int = 20) -> list[dict]:
        """آخر استدعاءات مزود معين."""
        rows = await self.db.fetchall(
            "SELECT * FROM provider_requests WHERE provider_id = ? ORDER BY id DESC LIMIT ?",
            (provider_id, limit),
        )
        return [dict(row) for row in rows]

    _CALL_SELECT = (
        "SELECT r.*, p.name AS provider_name FROM provider_requests r "
        "LEFT JOIN providers p ON p.id = r.provider_id"
    )

    async def list_page(self, *, only_failed: bool = False, limit: int = 8, offset: int = 0) -> list[dict]:
        """صفحة من سجل استدعاءات كل المزودين (الأحدث أولاً) مع اسم المزود؛ اختيارياً الفاشلة فقط."""
        where = " WHERE r.is_success = 0" if only_failed else ""
        rows = await self.db.fetchall(
            f"{self._CALL_SELECT}{where} ORDER BY r.id DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        return [dict(row) for row in rows]

    async def count_calls(self, *, only_failed: bool = False) -> int:
        """عدد الاستدعاءات المسجلة (أو الفاشلة فقط)."""
        return await self.count("provider_requests", "is_success = 0" if only_failed else "")

    async def get_call(self, request_id: int) -> dict | None:
        """استدعاء واحد بمعرّفه مع اسم المزود (لشاشة التفاصيل)."""
        row = await self.db.fetchone(f"{self._CALL_SELECT} WHERE r.id = ?", (request_id,))
        return dict(row) if row else None

    async def delete_old(self, tx: Tx, before_iso: str) -> int:
        """حذف السجلات الأقدم من تاريخ معين."""
        result = await tx.execute("DELETE FROM provider_requests WHERE created_at < ?", (before_iso,))
        return result.rowcount


class ErrorLogsRepository(BaseRepository):
    """تسجيل الأخطاء المهمة في قاعدة البيانات لعرضها في لوحة الأدمن."""

    async def log(
        self,
        tx: Tx,
        *,
        message: str,
        level: str = "ERROR",
        source: str = "app",
        error_type: str | None = None,
        traceback_snippet: str | None = None,
        user_id: int | None = None,
        update_summary: str | None = None,
    ) -> int | None:
        """تسجيل خطأ (بعد تنقيته من أي أسرار)."""
        result = await tx.execute(
            """
            INSERT INTO error_logs (level, source, error_type, message, traceback_snippet,
                                    user_id, update_summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                level, source, error_type, sanitize(message)[:1000],
                sanitize(traceback_snippet)[:2000] if traceback_snippet else None,
                user_id, sanitize(update_summary)[:500] if update_summary else None, self.now(),
            ),
        )
        return result.lastrowid

    async def mark_notified(self, tx: Tx, error_id: int) -> None:
        """تعليم أنه تم إشعار الأدمن بهذا الخطأ (منعاً لتكرار التنبيه)."""
        await tx.execute("UPDATE error_logs SET notified_admin = 1 WHERE id = ?", (error_id,))

    async def list_recent(self, *, limit: int = 20, offset: int = 0) -> list[dict]:
        """آخر الأخطاء المسجلة."""
        rows = await self.db.fetchall(
            "SELECT * FROM error_logs ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        return [dict(row) for row in rows]

    async def get(self, error_id: int) -> dict | None:
        """خطأ واحد بمعرّفه (لشاشة التفاصيل)."""
        row = await self.db.fetchone("SELECT * FROM error_logs WHERE id = ?", (error_id,))
        return dict(row) if row else None

    async def count_all(self) -> int:
        """إجمالي الأخطاء المسجلة."""
        return await self.count("error_logs")

    async def count_since(self, since_iso: str) -> int:
        """عدد الأخطاء منذ وقت معين (مؤشر صحة النظام)."""
        return await self.count("error_logs", "created_at >= ?", (since_iso,))

    async def delete_old(self, tx: Tx, before_iso: str) -> int:
        """حذف الأخطاء القديمة."""
        result = await tx.execute("DELETE FROM error_logs WHERE created_at < ?", (before_iso,))
        return result.rowcount


class BackupsRepository(BaseRepository):
    """
    سجل النسخ الاحتياطية (المرحلة 10: مكتمل).

    الحالات (`status`):
        ok       : نسخة سليمة (آخر فحص نجح).
        failed   : فشل إنشاؤها (لا ملف لها؛ السبب في `error_text`).
        corrupt  : فشل فحصها لاحقاً (بصمة مختلفة أو قاعدة تالفة) — لا تُستعمل للاستعادة.
        missing  : سجلها موجود وملفها غائب عن القرص.
        purged   : حُذف ملفها بسياسة الاحتفاظ (يبقى السجل أثراً تاريخياً).
    """

    async def add(
        self,
        tx: Tx,
        *,
        filename: str,
        path: str,
        size_bytes: int,
        sha256: str | None = None,
        type: str = "manual",
        created_by: int | None = None,
        status: str = "ok",
        schema_version: str | None = None,
        error_text: str | None = None,
        created_at: str | None = None,
    ) -> int | None:
        """تسجيل نسخة احتياطية جديدة (`created_at` يُمرَّر عند استيراد نسخة من القرص)."""
        result = await tx.execute(
            """
            INSERT INTO backups (filename, path, size_bytes, sha256, type, created_by, status,
                                 schema_version, error_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (filename, path, size_bytes, sha256, type, created_by, status,
             schema_version, error_text, created_at or self.now()),
        )
        return result.lastrowid

    async def get(self, backup_id: int) -> dict | None:
        """نسخة بمعرّفها (None إن لم توجد)."""
        row = await self.db.fetchone("SELECT * FROM backups WHERE id = ?", (backup_id,))
        return dict(row) if row else None

    async def get_by_filename(self, filename: str) -> dict | None:
        """نسخة باسم ملفها (للاستيراد من القرص ومنع التكرار)."""
        row = await self.db.fetchone(
            "SELECT * FROM backups WHERE filename = ? ORDER BY id DESC LIMIT 1", (filename,)
        )
        return dict(row) if row else None

    async def list_recent(self, *, limit: int = 10) -> list[dict]:
        """آخر النسخ الاحتياطية."""
        rows = await self.db.fetchall(
            "SELECT * FROM backups ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in rows]

    async def list_page(
        self, *, limit: int, offset: int = 0, include_purged: bool = False
    ) -> list[dict]:
        """صفحة من النسخ (الأحدث أولاً). المحذوفة بالاحتفاظ مخفية افتراضياً."""
        where = "" if include_purged else "WHERE status <> 'purged'"
        rows = await self.db.fetchall(
            f"SELECT * FROM backups {where} ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        return [dict(row) for row in rows]

    async def count_visible(self, *, include_purged: bool = False) -> int:
        """عدد النسخ المعروضة."""
        where = "" if include_purged else "status <> 'purged'"
        return await self.count("backups", where) if where else await self.count("backups")

    async def latest(self, *, status: str = "ok", backup_type: str | None = None) -> dict | None:
        """أحدث نسخة بحالة معينة (ونوع اختياري)."""
        if backup_type is None:
            row = await self.db.fetchone(
                "SELECT * FROM backups WHERE status = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                (status,),
            )
        else:
            row = await self.db.fetchone(
                """
                SELECT * FROM backups WHERE status = ? AND type = ?
                 ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (status, backup_type),
            )
        return dict(row) if row else None

    async def latest_failure_after(self, since_iso: str) -> dict | None:
        """أحدث نسخة فاشلة بعد وقت معين (لتنبيه الأدمن)."""
        row = await self.db.fetchone(
            "SELECT * FROM backups WHERE status = 'failed' AND created_at > ? ORDER BY id DESC LIMIT 1",
            (since_iso,),
        )
        return dict(row) if row else None

    async def list_ok_newest_first(self) -> list[dict]:
        """كل النسخ السليمة الأحدث أولاً (أساس سياسة الاحتفاظ)."""
        rows = await self.db.fetchall(
            "SELECT * FROM backups WHERE status = 'ok' ORDER BY created_at DESC, id DESC"
        )
        return [dict(row) for row in rows]

    async def list_older_than(self, before_iso: str) -> list[dict]:
        """النسخ الأقدم من تاريخ معين (لحذف ملفاتها ضمن سياسة الاحتفاظ)."""
        rows = await self.db.fetchall(
            "SELECT * FROM backups WHERE created_at < ? AND status <> 'purged' ORDER BY id",
            (before_iso,),
        )
        return [dict(row) for row in rows]

    async def totals(self) -> dict[str, int]:
        """عدّادات للشاشة: عدد النسخ السليمة وحجمها الكلي وعدد الفاشلة/التالفة."""
        row = await self.db.fetchone(
            """
            SELECT COALESCE(SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END), 0)              AS ok_count,
                   COALESCE(SUM(CASE WHEN status = 'ok' THEN size_bytes ELSE 0 END), 0)     AS ok_bytes,
                   COALESCE(SUM(CASE WHEN status IN ('failed','corrupt','missing') THEN 1 ELSE 0 END), 0)
                                                                                            AS bad_count
              FROM backups
            """
        )
        return {
            "ok_count": int(row["ok_count"]) if row else 0,
            "ok_bytes": int(row["ok_bytes"]) if row else 0,
            "bad_count": int(row["bad_count"]) if row else 0,
        }

    async def set_verification(self, tx: Tx, backup_id: int, *, status: str, error_text: str | None) -> bool:
        """تسجيل نتيجة فحص: الحالة الجديدة ووقت الفحص وسبب الفشل (إن وُجد)."""
        result = await tx.execute(
            "UPDATE backups SET status = ?, verified_at = ?, error_text = ? WHERE id = ? AND status <> 'purged'",
            (status, self.now(), error_text, backup_id),
        )
        return result.rowcount > 0

    async def mark_purged(self, tx: Tx, backup_id: int) -> bool:
        """تعليم نسخة كمحذوفة الملف (يبقى السجل)."""
        result = await tx.execute(
            "UPDATE backups SET status = 'purged' WHERE id = ? AND status <> 'purged'", (backup_id,)
        )
        return result.rowcount > 0

    async def mark_channel_sent(self, tx: Tx, backup_id: int, *, message_id: int | None) -> bool:
        """تسجيل إرسال النسخة لقناة النسخ الخارجية."""
        result = await tx.execute(
            "UPDATE backups SET channel_message_id = ?, channel_sent_at = ? WHERE id = ?",
            (message_id, self.now(), backup_id),
        )
        return result.rowcount > 0
```

## `database/repositories/__init__.py`

```python
"""
حزمة المستودعات + حاوية موحدة للوصول إليها.

الاستخدام في الطبقات الأعلى:
    repos = Repositories(db)
    user = await repos.users.get_by_telegram_id(123)
"""

from __future__ import annotations

from database.database import Database
from database.repositories.audit import AuditRepository
from database.repositories.base import BaseRepository
from database.repositories.broadcasts import BroadcastsRepository
from database.repositories.categories import CategoriesRepository
from database.repositories.idempotency import IdempotencyRepository
from database.repositories.misc import (
    BackupsRepository,
    ErrorLogsRepository,
    ProviderRequestsRepository,
)
from database.repositories.notifications import NotificationsRepository
from database.repositories.orders import OrdersRepository
from database.repositories.payments import PaymentMethodsRepository, PaymentsRepository
from database.repositories.providers import ProvidersRepository
from database.repositories.rbac import RbacRepository
from database.repositories.services import ServicesRepository
from database.repositories.settings import SettingsRepository
from database.repositories.templates import NotificationTemplatesRepository
from database.repositories.tickets import TicketsRepository
from database.repositories.transactions import TransactionsRepository
from database.repositories.users import UsersRepository

__all__ = [
    "Repositories",
    "BaseRepository",
    "UsersRepository",
    "RbacRepository",
    "SettingsRepository",
    "ProvidersRepository",
    "CategoriesRepository",
    "ServicesRepository",
    "OrdersRepository",
    "TransactionsRepository",
    "PaymentsRepository",
    "PaymentMethodsRepository",
    "TicketsRepository",
    "NotificationsRepository",
    "NotificationTemplatesRepository",
    "AuditRepository",
    "BroadcastsRepository",
    "IdempotencyRepository",
    "ProviderRequestsRepository",
    "ErrorLogsRepository",
    "BackupsRepository",
]


class Repositories:
    """حاوية تجمع كل المستودعات على نفس اتصال قاعدة البيانات."""

    def __init__(self, db: Database) -> None:
        """إنشاء نسخة واحدة من كل مستودع ومشاركتها مع بقية النظام."""
        self.db = db
        self.users = UsersRepository(db)
        self.rbac = RbacRepository(db)
        self.settings = SettingsRepository(db)
        self.templates = NotificationTemplatesRepository(db)
        self.providers = ProvidersRepository(db)
        self.categories = CategoriesRepository(db)
        self.services = ServicesRepository(db)
        self.orders = OrdersRepository(db)
        self.transactions = TransactionsRepository(db)
        self.payments = PaymentsRepository(db)
        self.payment_methods = PaymentMethodsRepository(db)
        self.tickets = TicketsRepository(db)
        self.notifications = NotificationsRepository(db)
        self.audit = AuditRepository(db)
        self.broadcasts = BroadcastsRepository(db)
        self.idempotency = IdempotencyRepository(db)
        self.provider_requests = ProviderRequestsRepository(db)
        self.error_logs = ErrorLogsRepository(db)
        self.backups = BackupsRepository(db)
```

## `services/provider_service.py`

```python
"""
خدمة المزودين: إدارة بياناتهم، وتشفير مفاتيحهم، والاتصال بهم بأمان.

قواعد صارمة:
    • مفتاح API يُخزَّن مشفّراً، ولا يُفك إلا لحظة الاستدعاء داخل هذه الخدمة.
    • لا يظهر المفتاح في أي سجل أو رسالة خطأ (كل النصوص تمر على `sanitize`).
    • كل استدعاء خارجي يُسجَّل في `provider_requests` بنجاحه أو فشله ومدته.
    • قاطع دائرة: بعد عدد أخطاء متتالية يُعطَّل المزود مؤقتاً ويُنبَّه الأدمن.
    • لا تُفتح معاملة قاعدة بيانات أثناء انتظار الشبكة.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence

from core.enums import ProviderAction
from core.exceptions import (
    ProviderError,
    ProviderPermanentError,
    ProviderTemporaryError,
    ProviderUncertainError,
    ValidationError,
)
from core.permissions import Permission
from core.setting_rules import normalize_decimal_text
from database.database import Database
from database.models import Order, Provider, Service, User
from database.repositories import Repositories
from integrations.providers.base import (
    ProviderBalance,
    ProviderClient,
    ProviderOrderResult,
    ProviderServiceItem,
    ProviderStatusResult,
)
from integrations.providers.registry import create_client, is_supported
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.notification_service import NotificationService
from services.settings_service import SettingsService
from texts import templates
from utils.datetime_utils import is_past, iso_plus_seconds
from utils.logging_setup import get_logger
from utils.security import SecretBox, secret_hint
from utils.net_security import validate_public_https_url
from utils.validators import clean_text

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    """حالة صحة مزود كما تُعرض في لوحة الأدمن."""

    provider: Provider
    is_usable: bool
    reason: str


class ProviderService:
    """كل تعامل مع مزودي الخدمات يمر من هنا."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        audit: AuditService,
        auth: AuthService,
        notifications: NotificationService,
        secret_box: SecretBox,
    ) -> None:
        """تهيئة الخدمة مع صندوق التشفير المسؤول عن مفاتيح المزودين."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.audit = audit
        self.auth = auth
        self.notifications = notifications
        self.secret_box = secret_box

    # ------------------------------- القراءة ------------------------------ #

    async def get(self, provider_id: int) -> Provider | None:
        """جلب مزود بالمعرف."""
        return await self.repos.providers.get(provider_id)

    async def list_all(self, *, active_only: bool = False) -> list[Provider]:
        """قائمة المزودين (كلهم أو المفعّلون فقط)."""
        return await self.repos.providers.list_all(active_only=active_only)

    async def health(self, provider: Provider) -> ProviderHealth:
        """
        تقييم جاهزية المزود للاستخدام الآن.

        المخرجات: كائن يوضح هل يمكن الإرسال إليه ولماذا لا، بصيغة عربية للعرض.
        """
        if not provider.is_active:
            return ProviderHealth(provider, False, "المزود معطّل يدوياً")
        if provider.disabled_until and not is_past(provider.disabled_until):
            return ProviderHealth(provider, False, "المزود موقوف مؤقتاً بعد أخطاء متتالية")
        if not is_supported(provider.api_type):
            return ProviderHealth(provider, False, f"نوع API غير مدعوم: {provider.api_type}")
        _, problem = await self.rate_state(provider)
        if problem:
            return ProviderHealth(provider, False, problem)
        return ProviderHealth(provider, True, "جاهز")

    # ------------------------------ العملة ------------------------------- #

    async def rate_state(self, provider: Provider) -> tuple[Decimal | None, str | None]:
        """
        سعر تحويل عملة المزود إلى عملة النظام، أو سبب تعذّره.

        القاعدة: سعر مضبوط ⇒ يُستعمل. بلا سعر ⇒ مقبول فقط إن كانت عملة المزود هي عملة النظام (السعر 1)،
        وإلا (None، رسالة عربية) — فلا يُفترض 1:1 بصمت أبداً (كان ذلك يُسعِّر بالدولار كأنه ريال).
        """
        system_code, _, _ = await self.settings.currency()
        if provider.exchange_rate:
            return Decimal(provider.exchange_rate), None
        provider_code = (provider.currency or "").strip().upper()
        if provider_code and provider_code == system_code.strip().upper():
            return Decimal(1), None
        return None, (
            f"عملة المزود ({provider_code or '؟'}) تختلف عن عملة النظام ({system_code}) ولم يُحدَّد سعر الصرف"
        )

    async def system_rate(self, provider: Provider) -> Decimal:
        """
        سعر التحويل إلى عملة النظام لهذا المزود.

        الاستثناءات: ProviderError برسالة عربية تدلّ الأدمن على مكان الإصلاح.
        """
        rate, problem = await self.rate_state(provider)
        if rate is None:
            raise ProviderError(
                problem or "سعر الصرف غير محدد",
                user_message=f"⚠️ {problem}. حدّده من بطاقة المزود («💱 العملة وسعر الصرف»).",
            )
        return rate

    @staticmethod
    def to_system_units(units: int, rate: Decimal) -> int:
        """تحويل مبلغ بوحدات المال من عملة المزود إلى عملة النظام (تقريب نصف لأعلى، Decimal فقط)."""
        return int((Decimal(units) * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP))

    async def _convert_known(self, provider: Provider, units: int | None) -> int | None:
        """
        تحويل مبلغ وارد من المزود إلى عملة النظام إن أمكن، وإلا None (لا قيمة خاطئة تُخزَّن).

        يُستعمل لمسارات المتابعة (الحالة) حيث لا يجوز أن يعطّل غياب سعر الصرف تتبّع طلب أُرسل فعلاً.
        """
        if units is None:
            return None
        rate, problem = await self.rate_state(provider)
        if rate is None:
            logger.warning("مبلغ من المزود %s لم يُحوَّل: %s", provider.id, problem)
            return None
        return self.to_system_units(units, rate)

    @staticmethod
    def parse_currency_spec(text: str) -> tuple[str, str | None]:
        """
        تحليل إدخال الأدمن «العملة [سعر الصرف]» مثل `USD 530` أو `YER`.

        المخرجات: (رمز العملة بأحرف كبيرة، سعر الصرف المطبَّع أو None).
        الاستثناءات: ValidationError برسالة عربية.
        """
        parts = (text or "").replace("،", " ").split()
        if not 1 <= len(parts) <= 2:
            raise ValidationError(
                f"إدخال عملة غير صالح: {text!r}",
                user_message="❌ أرسل رمز العملة ثم سعر الصرف (اختياري إن كانت عملة النظام). مثال: <code>USD 530</code>",
            )
        code = parts[0].strip().upper()
        if not (2 <= len(code) <= 6 and code.isascii() and code.isalpha()):
            raise ValidationError(
                f"رمز عملة غير صالح: {code!r}", user_message="❌ رمز العملة أحرف لاتينية (مثل USD أو SAR)."
            )
        rate = normalize_decimal_text(parts[1]) if len(parts) == 2 else None
        return code, rate

    async def validate_currency(self, currency: str, exchange_rate: str | None) -> tuple[str, str | None]:
        """اتساق العملة وسعرها: عملة مختلفة عن النظام تتطلب سعراً (ولا يُقبل رفض ضمني لاحقاً)."""
        system_code, _, _ = await self.settings.currency()
        code = currency.strip().upper()
        rate = normalize_decimal_text(exchange_rate) if exchange_rate not in (None, "") else None
        if rate is None and code != system_code.strip().upper():
            raise ValidationError(
                f"عملة {code} تختلف عن عملة النظام {system_code} بلا سعر صرف",
                user_message=f"❌ عملة المزود ({code}) تختلف عن عملة النظام ({system_code}) — أرسل سعر الصرف أيضاً. مثال: <code>{code} 530</code>",
            )
        return code, rate

    async def set_currency(
        self, actor: User, provider_id: int, *, currency: str, exchange_rate: str | None
    ) -> Provider:
        """
        ضبط عملة المزود وسعر صرفها إلى عملة النظام.

        لا يغيّر أسعار خدمات مستوردة سابقاً: التكلفة المخزّنة تُحدَّث عند المزامنة التالية، لذلك تنبّه الواجهة
        الأدمن لتشغيل «🔄 مزامنة» بعد التغيير.

        الاستثناءات: PermissionDeniedError · ValidationError · ProviderError (مزود غير موجود)
        """
        await self.auth.require_permission(
            actor, Permission.PROVIDERS_UPDATE, context=f"provider:{provider_id}"
        )
        code, rate = await self.validate_currency(currency, exchange_rate)
        async with self.db.transaction() as tx:
            before = await self.repos.providers.get(provider_id)
            if before is None:
                raise ProviderError(f"مزود غير موجود: {provider_id}", user_message="❌ المزود غير موجود.")
            await self.repos.providers.update_fields(tx, provider_id, currency=code, exchange_rate=rate)
            await self.audit.log(
                tx,
                action="providers.set_currency",
                admin_id=actor.id,
                target_type="provider",
                target_id=provider_id,
                before={"currency": before.currency, "exchange_rate": before.exchange_rate},
                after={"currency": code, "exchange_rate": rate},
            )
        provider = await self.repos.providers.get(provider_id)
        assert provider is not None
        logger.info("ضبط الأدمن %s عملة المزود %s: %s × %s", actor.id, provider_id, code, rate)
        return provider

    async def is_usable(self, provider: Provider) -> bool:
        """هل يمكن إرسال طلبات لهذا المزود الآن؟"""
        return (await self.health(provider)).is_usable

    # ------------------------------ الإدارة ------------------------------- #

    async def create_provider(
        self,
        actor: User,
        *,
        name: str,
        api_url: str,
        api_key: str,
        api_type: str = "perfect_panel",
        currency: str | None = None,
        exchange_rate: str | None = None,
        timeout_seconds: int = 30,
    ) -> Provider:
        """
        إضافة مزود جديد مع تشفير مفتاحه قبل التخزين.

        `currency=None` ⇒ عملة النظام (سعر الصرف غير لازم). عملة مختلفة تتطلب `exchange_rate`.

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
        system_code, _, _ = await self.settings.currency()
        clean_currency, clean_rate = await self.validate_currency(currency or system_code, exchange_rate)

        async with self.db.transaction() as tx:
            # الفحص داخل المعاملة نفسها (BEGIN IMMEDIATE) فلا يتسلل مكرر عند إنشاءين متزامنين
            if await tx.fetchval("SELECT 1 FROM providers WHERE name = ?", (clean_name,)):
                raise ProviderError(
                    f"اسم المزود {clean_name} مستخدم", user_message="❌ يوجد مزود بنفس الاسم."
                )
            provider = await self.repos.providers.create(
                tx,
                name=clean_name,
                api_url=clean_gateway,
                api_key_enc=self.secret_box.encrypt(key),
                api_key_hint=secret_hint(key),
                api_type=api_type,
                currency=clean_currency,
                exchange_rate=clean_rate,
                timeout_seconds=timeout_seconds,
            )
            await self.audit.log(
                tx,
                action="providers.create",
                admin_id=actor.id,
                target_type="provider",
                target_id=provider.id,
                after={
                    "name": clean_name, "api_url": clean_gateway, "api_type": api_type,
                    "currency": clean_currency, "exchange_rate": clean_rate,
                },
            )
        logger.info("أضاف الأدمن %s المزود %s (%s)", actor.id, provider.id, clean_name)
        return provider

    async def update_api_key(self, actor: User, provider_id: int, new_key: str) -> bool:
        """
        تحديث مفتاح API لمزود (يُخزَّن مشفّراً، ولا يُسجَّل في أي مكان).

        الاستثناءات: PermissionDeniedError · ProviderError
        """
        await self.auth.require_permission(
            actor, Permission.PROVIDERS_KEY_UPDATE, context=f"provider:{provider_id}"
        )
        key = (new_key or "").strip()
        if len(key) < 8:
            raise ProviderError("مفتاح API قصير جداً", user_message="❌ مفتاح API غير صالح.")

        async with self.db.transaction() as tx:
            changed = await self.repos.providers.update_fields(
                tx,
                provider_id,
                api_key_enc=self.secret_box.encrypt(key),
                api_key_hint=secret_hint(key),
            )
            if changed:
                # لا نُسجّل المفتاح نفسه — فقط أن التغيير حدث ومن نفّذه
                await self.audit.log(
                    tx,
                    action="providers.key.update",
                    admin_id=actor.id,
                    target_type="provider",
                    target_id=provider_id,
                    after={"api_key_hint": secret_hint(key)},
                )
        return changed

    async def set_active(self, actor: User, provider_id: int, active: bool) -> bool:
        """تفعيل أو تعطيل مزود يدوياً."""
        await self.auth.require_permission(
            actor, Permission.PROVIDERS_UPDATE, context=f"provider:{provider_id}"
        )
        async with self.db.transaction() as tx:
            changed = await self.repos.providers.set_active(tx, provider_id, active)
            if changed:
                await self.audit.log(
                    tx,
                    action="providers.update",
                    admin_id=actor.id,
                    target_type="provider",
                    target_id=provider_id,
                    after={"is_active": active},
                )
        return changed

    # ------------------------------ الاتصال ------------------------------- #

    def client_for(self, provider: Provider) -> ProviderClient:
        """
        بناء عميل اتصال للمزود بعد فك تشفير مفتاحه.

        الاستثناءات:
            EncryptionError : المفتاح المخزَّن لا يُفك بمفتاح التشفير الحالي.
            ProviderError   : نوع API غير مدعوم.
        """
        api_key = self.secret_box.decrypt(provider.api_key_enc)
        return create_client(
            api_type=provider.api_type,
            api_url=provider.api_url,
            api_key=api_key,
            timeout_seconds=provider.timeout_seconds,
        )

    async def _log_request(
        self,
        *,
        provider: Provider,
        action: str,
        is_success: bool,
        started: float,
        request_summary: str,
        response_snippet: str,
        error_type: str | None = None,
        order_id: int | None = None,
        secrets: tuple[str, ...] = (),
    ) -> None:
        """تسجيل استدعاء المزود في قاعدة البيانات بعد تنقيته من الأسرار."""
        duration_ms = int((time.monotonic() - started) * 1000)
        async with self.db.transaction() as tx:
            await self.repos.provider_requests.log(
                tx,
                provider_id=provider.id,
                action=action,
                is_success=is_success,
                order_id=order_id,
                request_summary=request_summary,
                response_snippet=response_snippet,
                duration_ms=duration_ms,
                error_type=error_type,
                secrets=secrets,
            )

    async def _record_success(self, provider: Provider) -> None:
        """تصفير عدّاد الأخطاء بعد نجاح الاتصال."""
        async with self.db.transaction() as tx:
            await self.repos.providers.record_success(tx, provider.id)

    async def _record_failure(self, provider: Provider, error: str) -> int:
        """
        تسجيل خطأ متتالٍ، وتعطيل المزود مؤقتاً عند بلوغ الحد، مع تنبيه الأدمن.

        المخرجات: عدد الأخطاء المتتالية بعد هذا الخطأ.
        """
        threshold = await self.settings.get_int("provider_failure_threshold", 5)
        disable_minutes = await self.settings.get_int("provider_disable_minutes", 15)

        async with self.db.transaction() as tx:
            current = await self.repos.providers.record_failure(tx, provider.id, error)
            if current >= threshold:
                await self.repos.providers.update_fields(
                    tx, provider.id, disabled_until=iso_plus_seconds(disable_minutes * 60)
                )
                title, message = templates.admin_provider_disabled(
                    provider_name=provider.name, failures=current, minutes=disable_minutes
                )
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.PROVIDERS_VIEW,
                    token=f"provider:{provider.id}:disabled:{current}",
                    title=title,
                    message=message,
                )
                logger.error(
                    "تعطيل مؤقت للمزود %s بعد %s أخطاء متتالية", provider.name, current
                )
        return current

    # ------------------------------ العمليات ------------------------------ #

    async def submit_order(self, provider: Provider, service: Service, order: Order) -> ProviderOrderResult:
        """
        إرسال طلب إلى المزود.

        المخرجات: نتيجة فيها رقم الطلب عند المزود.

        الاستثناءات:
            ProviderTemporaryError  : فشل مؤقت — يُعاد المحاولة لاحقاً.
            ProviderUncertainError  : نتيجة غير مؤكدة — ممنوع إعادة الإرسال آلياً.
            ProviderPermanentError  : رفض نهائي — فشل الطلب واسترجاع المبلغ.
        """
        # قبل الاتصال بالمزود وليس بعده: لو رُفض بسبب العملة بعد قبول المزود للطلب لضاعت النتيجة
        try:
            rate = await self.system_rate(provider)
        except ProviderError as exc:
            raise ProviderTemporaryError(str(exc), user_message=exc.user_message) from exc
        system_code, _, _ = await self.settings.currency()

        client = self.client_for(provider)
        summary = f"add service={service.provider_service_id} quantity={order.quantity} link={order.link}"
        started = time.monotonic()
        try:
            result = await client.add_order(
                provider_service_id=service.provider_service_id,
                link=order.link,
                quantity=order.quantity,
            )
        except ProviderUncertainError as exc:
            await self._log_request(
                provider=provider, action=ProviderAction.ADD, is_success=False, started=started,
                request_summary=summary, response_snippet=str(exc),
                error_type=type(exc).__name__, order_id=order.id, secrets=client.secrets(),
            )
            await self._record_failure(provider, str(exc))
            raise
        except ProviderError as exc:
            await self._log_request(
                provider=provider, action=ProviderAction.ADD, is_success=False, started=started,
                request_summary=summary, response_snippet=str(exc),
                error_type=type(exc).__name__, order_id=order.id, secrets=client.secrets(),
            )
            await self._record_failure(provider, str(exc))
            raise
        finally:
            await client.close()

        if not result.provider_order_id:
            raise ProviderPermanentError("المزود لم يُرجع رقم طلب صالحاً")

        await self._log_request(
            provider=provider, action=ProviderAction.ADD, is_success=True, started=started,
            request_summary=summary, response_snippet=str(result.raw)[:500],
            order_id=order.id, secrets=client.secrets(),
        )
        await self._record_success(provider)
        if result.charge_units is not None:
            result = replace(
                result, charge_units=self.to_system_units(result.charge_units, rate), currency=system_code
            )
        return result

    async def fetch_status(self, provider: Provider, order: Order) -> ProviderStatusResult:
        """
        الاستعلام عن حالة طلب لدى المزود.

        الاستثناءات: ProviderTemporaryError · ProviderPermanentError
        """
        if not order.provider_order_id:
            raise ProviderPermanentError(f"الطلب #{order.id} بلا رقم عند المزود")

        client = self.client_for(provider)
        started = time.monotonic()
        try:
            result = await client.get_order_status(order.provider_order_id)
        except ProviderError as exc:
            await self._log_request(
                provider=provider, action=ProviderAction.STATUS, is_success=False, started=started,
                request_summary=f"status order={order.provider_order_id}", response_snippet=str(exc),
                error_type=type(exc).__name__, order_id=order.id, secrets=client.secrets(),
            )
            await self._record_failure(provider, str(exc))
            raise
        finally:
            await client.close()

        await self._log_request(
            provider=provider, action=ProviderAction.STATUS, is_success=True, started=started,
            request_summary=f"status order={order.provider_order_id}",
            response_snippet=str(result.raw)[:500], order_id=order.id, secrets=client.secrets(),
        )
        await self._record_success(provider)
        return await self._to_system_status(provider, result)

    async def _to_system_status(
        self, provider: Provider, result: ProviderStatusResult
    ) -> ProviderStatusResult:
        """تحويل مبلغ حالة الطلب (إن وُجد) إلى عملة النظام، أو إسقاطه إن تعذّر السعر."""
        if result.charge_units is None:
            return result
        system_code, _, _ = await self.settings.currency()
        return replace(
            result, charge_units=await self._convert_known(provider, result.charge_units), currency=system_code
        )

    async def fetch_multi_status(
        self, provider: Provider, orders: Sequence[Order]
    ) -> dict[str, ProviderStatusResult]:
        """
        الاستعلام عن حالة عدة طلبات لدى مزود واحد في **استدعاء واحد**.

        لماذا؟ فحص 20 طلباً فردياً = 20 طلب HTTP كل دقيقتين، وهو ما يستنزف حدود
        المزود ويبطئ الجولة. معيار Perfect Panel يدعم `orders=1,2,3` فنستفيد منه،
        والمزود الذي لا يدعمه يرجع تلقائياً للفحص الفردي (التطبيق الافتراضي في
        `ProviderClient.get_multi_status`).

        المخرجات: قاموس {رقم الطلب لدى المزود: نتيجة الحالة} — قد ينقص منه ما لم
                  يُجب عنه المزود، والمستدعي يتولى فحص الناقص فردياً.

        الاستثناءات: ProviderTemporaryError · ProviderPermanentError
        """
        provider_order_ids = [
            order.provider_order_id for order in orders if order.provider_order_id
        ]
        if not provider_order_ids:
            return {}

        client = self.client_for(provider)
        started = time.monotonic()
        try:
            results = await client.get_multi_status(provider_order_ids)
        except ProviderError as exc:
            await self._log_request(
                provider=provider, action=ProviderAction.STATUS, is_success=False, started=started,
                request_summary=f"multi-status count={len(provider_order_ids)}",
                response_snippet=str(exc), error_type=type(exc).__name__,
                secrets=client.secrets(),
            )
            await self._record_failure(provider, str(exc))
            raise
        finally:
            await client.close()

        await self._log_request(
            provider=provider, action=ProviderAction.STATUS, is_success=True, started=started,
            request_summary=f"multi-status count={len(provider_order_ids)}",
            response_snippet=f"answered={len(results)}/{len(provider_order_ids)}",
            secrets=client.secrets(),
        )
        await self._record_success(provider)
        return {key: await self._to_system_status(provider, value) for key, value in results.items()}

    async def check_balance(self, provider: Provider) -> ProviderBalance:
        """
        قراءة رصيدنا لدى المزود وتحديثه في قاعدة البيانات مع لقطة تاريخية.

        يُرسل تنبيهاً للأدمن إذا نزل الرصيد تحت الحد المحدد.
        """
        client = self.client_for(provider)
        started = time.monotonic()
        try:
            balance = await client.get_balance()
        except ProviderError as exc:
            await self._log_request(
                provider=provider, action=ProviderAction.BALANCE, is_success=False, started=started,
                request_summary="balance", response_snippet=str(exc),
                error_type=type(exc).__name__, secrets=client.secrets(),
            )
            await self._record_failure(provider, str(exc))
            raise
        finally:
            await client.close()

        reported_currency = (balance.currency or "").strip().upper()
        async with self.db.transaction() as tx:
            await self.repos.providers.update_balance(tx, provider.id, balance.amount_units)
            await self.repos.providers.add_balance_snapshot(
                tx, provider.id, balance.amount_units, currency=reported_currency or provider.currency
            )

        if reported_currency and reported_currency != (provider.currency or "").strip().upper():
            logger.warning(
                "المزود %s يُبلِّغ بعملة %s بينما المسجَّل %s", provider.id, reported_currency, provider.currency
            )
            title, message = templates.admin_provider_currency_mismatch(
                provider_name=provider.name, configured=provider.currency, reported=reported_currency
            )
            async with self.db.transaction() as tx:
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.PROVIDERS_UPDATE,
                    token=f"provider:{provider.id}:currency:{reported_currency}",
                    title=title,
                    message=message,
                )

        # عتبة التنبيه بعملة النظام ⇒ نقارن بمكافئ الرصيد وليس بالرقم الخام بعملة المزود
        threshold = provider.low_balance_threshold_units or await self.settings.get_int(
            "provider_low_balance_alert_units", 0
        )
        equivalent, problem = await self.rate_state(provider)
        if threshold and equivalent is not None:
            equivalent_units = self.to_system_units(balance.amount_units, equivalent)
            if equivalent_units < threshold:
                symbol = await self.settings.money_symbol()
                title, message = templates.admin_provider_low_balance(
                    provider_name=provider.name, balance_units=equivalent_units, symbol=symbol
                )
                async with self.db.transaction() as tx:
                    await self.notifications.notify_admins(
                        tx,
                        permission=Permission.PROVIDERS_VIEW,
                        token=f"provider:{provider.id}:low:{equivalent_units}",
                        title=title,
                        message=message,
                    )
        elif threshold:
            logger.warning("تعذّرت مقارنة رصيد المزود %s بالعتبة: %s", provider.id, problem)

        await self._log_request(
            provider=provider, action=ProviderAction.BALANCE, is_success=True, started=started,
            request_summary="balance", response_snippet=f"amount_units={balance.amount_units}",
            secrets=client.secrets(),
        )
        await self._record_success(provider)
        return balance

    async def fetch_services(self, actor: User, provider: Provider) -> list[ProviderServiceItem]:
        """
        جلب قائمة خدمات المزود (تمهيداً للاستيراد في المرحلة 5).

        الاستثناءات: PermissionDeniedError · ProviderError
        """
        await self.auth.require_permission(
            actor, Permission.SERVICES_SYNC, context=f"provider:{provider.id}"
        )
        rate = await self.system_rate(provider)      # قبل الاتصال: لا جلب بلا إمكانية تحويل
        client = self.client_for(provider)
        started = time.monotonic()
        try:
            items = await client.get_services()
        except ProviderError as exc:
            await self._log_request(
                provider=provider, action=ProviderAction.SERVICES, is_success=False, started=started,
                request_summary="services", response_snippet=str(exc),
                error_type=type(exc).__name__, secrets=client.secrets(),
            )
            await self._record_failure(provider, str(exc))
            raise
        finally:
            await client.close()

        await self._log_request(
            provider=provider, action=ProviderAction.SERVICES, is_success=True, started=started,
            request_summary="services", response_snippet=f"count={len(items)}", secrets=client.secrets(),
        )
        await self._record_success(provider)

        # أسعار المزود بعملته ⇒ عملة النظام (مرة واحدة هنا، فيبقى الكتالوج كله بعملة واحدة)
        system_code, _, _ = await self.settings.currency()
        return [
            replace(item, rate_per_1000_units=self.to_system_units(item.rate_per_1000_units, rate), currency=system_code)
            for item in items
        ]

    async def test_connection(self, actor: User, provider_id: int) -> tuple[bool, str]:
        """
        اختبار اتصال المزود من لوحة الأدمن.

        المخرجات: (نجح؟، رسالة عربية للعرض) — لا تحتوي الرسالة أي سر.
        """
        await self.auth.require_permission(
            actor, Permission.PROVIDERS_TEST, context=f"provider:{provider_id}"
        )
        provider = await self.repos.providers.get(provider_id)
        if provider is None:
            return False, "المزود غير موجود."
        try:
            balance = await self.check_balance(provider)
        except ProviderTemporaryError as exc:
            return False, f"فشل مؤقت في الاتصال: {exc.user_message}"
        except ProviderError as exc:
            return False, f"فشل الاتصال: {exc.user_message}"
        symbol = provider.currency or "USD"
        text = f"الاتصال ناجح ✅ — الرصيد: {balance.amount_units / 10_000:.4f} {symbol}"
        rate, problem = await self.rate_state(provider)
        if rate is None:
            return True, f"{text}\n⚠️ {problem}"
        if rate != 1:
            system_code, _, _ = await self.settings.currency()
            text += f" (≈ {self.to_system_units(balance.amount_units, rate) / 10_000:.2f} {system_code})"
        return True, text
```

## `services/settings_service.py`

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

        before = setting.value
        async with self.db.transaction() as tx:
            # فحص الأزواج (أدنى ≤ أعلى) داخل المعاملة نفسها بقيم محقونة منها: تعديلان متزامنان لمفتاحين
            # مرتبطين كانا يمرّان كلٌّ على حدة ثم يتركان أدنى > أعلى
            current = {row["key"]: row["value"] for row in await tx.fetchall("SELECT key, value FROM settings")}
            check_ordered_pairs(key, clean, current)
            before = current.get(key, before)
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

## `services/broadcast_service.py`

```python
"""
خدمة الرسائل الجماعية (الإذاعة) — المرحلة 8.

لماذا طابور مستلمين بدل حلقة إرسال واحدة؟
    إرسال رسالة لعشرة آلاف مستخدم داخل معالج زر مستحيل عملياً: تيليجرام يحدّ
    السرعة (~30 رسالة/ثانية)، وأي انقطاع يفقد أثر من وصلته الرسالة ومن لم تصله.
    لذلك: تُسجَّل قائمة المستلمين كاملة في `broadcast_recipients` أولاً، ثم تأتي
    مهمة دورية وترسل دفعة صغيرة كل بضع ثوانٍ وتسجّل نتيجة كل مستلم على حدة.

النتائج المضمونة:
    • لا تكرار: صف المستلم ينتقل من pending إلى نتيجة نهائية بشرط `status='pending'`،
      فحتى لو تداخلت جولتان لا يُرسل لأحد مرتين.
    • استئناف تلقائي: إعادة تشغيل البوت لا تفقد شيئاً — الإذاعة تبقى `running`
      والجولة التالية تكمل من حيث توقفت.
    • إيقاف فوري: زر «⏸ إيقاف مؤقت» يوقف الجولات، والملغاة لا تُستأنف أبداً.
    • من حظر البوت يُسجَّل فوراً (`blocked_bot=1`) فلا نزعج طابور الإشعارات به لاحقاً.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from core.enums import BroadcastStatus, RecipientStatus
from core.exceptions import (
    NotificationBlockedError,
    NotificationPermanentError,
    NotificationTemporaryError,
    ValidationError,
)
from core.permissions import Permission
from database.database import Database
from database.models import Broadcast, User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.notification_service import NotificationService
from services.settings_service import SettingsService
from texts import templates
from utils.datetime_utils import iso_minus_days, utc_now_iso
from utils.logging_setup import get_logger
from utils.security import sanitize
from utils.validators import clean_multiline

logger = get_logger(__name__)

#: توقيع دالة إرسال رسالة إذاعة واحدة (تُمرَّر من طبقة تيليجرام)
#: (telegram_id, text, media_file_id, media_type) -> message_id | None
BroadcastSender = Callable[[int, str, str | None, str | None], Awaitable[int | None]]

#: أقصى طول لنص الإذاعة بلا وسائط (حد تيليجرام 4096 ونترك هامشاً)
MAX_BROADCAST_TEXT = 3500

#: أقصى طول للنص المرافق لصورة (حد التعليق في تيليجرام 1024)
MAX_BROADCAST_CAPTION = 1000

#: شرائح الاستهداف المدعومة ووصفها العربي
TARGETS: dict[str, str] = {
    "all": "👥 كل المستخدمين",
    "active": "🔥 النشطون مؤخراً",
    "buyers": "🛒 من لديه طلب سابق",
    "no_orders": "🌱 مسجّلون بلا طلبات",
}

#: الحالات التي يمكن الإرسال منها
RESUMABLE_STATUSES = (BroadcastStatus.DRAFT, BroadcastStatus.PAUSED)


@dataclass(slots=True)
class BroadcastRound:
    """حصيلة جولة إرسال واحدة (تُسجَّل في اللوق وتظهر في شاشة المهام)."""

    broadcast_id: int = 0
    claimed: int = 0
    sent: int = 0
    failed: int = 0
    blocked: int = 0
    completed: bool = False

    def as_dict(self) -> dict[str, int | bool]:
        """تحويل الحصيلة إلى قاموس للتسجيل."""
        return {
            "broadcast_id": self.broadcast_id,
            "claimed": self.claimed,
            "sent": self.sent,
            "failed": self.failed,
            "blocked": self.blocked,
            "completed": self.completed,
        }


class BroadcastService:
    """إنشاء الرسائل الجماعية وإدارتها وإرسالها على دفعات آمنة."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        auth: AuthService,
        audit: AuditService,
        notifications: NotificationService,
        settings: SettingsService,
    ) -> None:
        """تهيئة الخدمة باعتمادياتها."""
        self.db = db
        self.repos = repos
        self.auth = auth
        self.audit = audit
        self.notifications = notifications
        self.settings = settings
        #: قفل جولة الإرسال: يمنع عاملين متزامنين من حجز المستلمين أنفسهم وإرسال الرسالة مرتين
        #: (التسجيل يتم بعد الإرسال الفعلي، فلا يكفي شرط `status = 'pending'` وحده). صحيح لأن
        #: البوت عملية واحدة بقفل `bot.lock`؛ ولو انقطع التشغيل بين الإرسال والتسجيل يُعاد إرسال رسالة واحدة فقط.
        self._round_lock = asyncio.Lock()

    # ----------------------------- الاستهداف ----------------------------- #

    async def target_label(self, target: str) -> str:
        """وصف عربي للشريحة المستهدفة (يتضمن عدد أيام النشاط عند الحاجة)."""
        if target == "active":
            days = await self.settings.get_int("broadcast_active_days", 30)
            return f"🔥 النشطون آخر {days} يوماً"
        return TARGETS.get(target, target)

    async def audience_ids(self, target: str) -> list[int]:
        """
        معرفات المستخدمين الداخلية للشريحة المطلوبة.

        المستبعدون دائماً: المحظورون ومن حظر البوت — إرسال رسالة لهم مضيعة
        للحصة اليومية ويشوّه إحصائية «وصلت».

        الاستثناءات: ValidationError للشريحة غير المعروفة.
        """
        if target not in TARGETS:
            raise ValidationError(
                f"شريحة إذاعة غير معروفة: {target}",
                user_message="❌ شريحة الاستهداف غير معروفة.",
            )
        since = None
        if target == "active":
            days = await self.settings.get_int("broadcast_active_days", 30)
            since = iso_minus_days(max(1, days))
        return await self.repos.users.ids_for_broadcast(target=target, since_iso=since)

    async def audience_count(self, actor: User, target: str) -> int:
        """عدد من ستصلهم الرسالة فعلاً لو أُرسلت الآن (يُعرض قبل التأكيد)."""
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        return len(await self.audience_ids(target))

    async def audience_summary(self, actor: User) -> list[tuple[str, str, int]]:
        """
        جدول الشرائح: (الرمز، الوصف، العدد الحالي) لشاشة اختيار الشريحة.

        الأرقام محسوبة من قاعدة البيانات لحظة العرض — لا تقديرات.
        """
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        rows: list[tuple[str, str, int]] = []
        for code in TARGETS:
            rows.append((code, await self.target_label(code), len(await self.audience_ids(code))))
        return rows

    # ------------------------------ الإنشاء ------------------------------ #

    def validate_text(self, text: str, *, has_media: bool) -> str:
        """
        تنظيف نص الإذاعة والتحقق من طوله.

        مع صورة يصبح النص تعليقاً، وحد تيليجرام للتعليق أقصر بكثير من الرسالة.

        الاستثناءات: ValidationError عند الفراغ أو تجاوز الحد.
        """
        limit = MAX_BROADCAST_CAPTION if has_media else MAX_BROADCAST_TEXT
        return clean_multiline(text, field="نص الرسالة", max_length=limit, min_length=2)

    async def create(
        self,
        actor: User,
        *,
        text: str,
        target: str,
        media_file_id: str | None = None,
        media_type: str | None = None,
    ) -> Broadcast:
        """
        إنشاء إذاعة بحالة «مسودة» مع تثبيت قائمة مستلميها.

        تثبيت القائمة لحظة الإنشاء مقصود: من يسجّل بعد الضغط على «إرسال»
        لا تصله رسالة قديمة، ومن حُظر بعدها لا يُحذف من السجل بل تُسجَّل محاولته.

        الاستثناءات:
            PermissionDeniedError : بلا صلاحية `broadcast.send`.
            ValidationError       : نص فارغ/طويل، شريحة مجهولة، أو شريحة بلا مستلمين.
        """
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        clean = self.validate_text(text, has_media=bool(media_file_id))
        recipients = await self.audience_ids(target)
        if not recipients:
            raise ValidationError(
                f"لا مستلمين في الشريحة {target}",
                user_message="❌ لا يوجد مستخدمون في هذه الشريحة الآن.",
            )

        async with self.db.transaction() as tx:
            broadcast = await self.repos.broadcasts.create(
                tx,
                admin_id=actor.id,
                message_text=clean,
                target=target,
                media_file_id=media_file_id,
                media_type=media_type,
            )
            total = await self.repos.broadcasts.add_recipients(tx, broadcast.id, recipients)
            await self.audit.log(
                tx,
                action="broadcast.send",
                admin_id=actor.id,
                target_type="broadcast",
                target_id=broadcast.id,
                before=None,
                after={"target": target, "recipients": total, "has_media": bool(media_file_id)},
                details=clean[:200],
            )
        logger.info(
            "أنشأ الأدمن %s إذاعة #%s للشريحة %s بعدد %s مستلم",
            actor.id, broadcast.id, target, total,
        )
        refreshed = await self.repos.broadcasts.get(broadcast.id)
        return refreshed or broadcast

    # ------------------------------ التحكم ------------------------------- #

    async def _require(self, broadcast_id: int) -> Broadcast:
        """
        جلب إذاعة أو رفع خطأ واضح.

        الاستثناءات: ValidationError إذا لم توجد.
        """
        broadcast = await self.repos.broadcasts.get(broadcast_id)
        if broadcast is None:
            raise ValidationError(
                f"إذاعة غير موجودة: {broadcast_id}", user_message="❌ هذه الرسالة غير موجودة."
            )
        return broadcast

    async def start(self, actor: User, broadcast_id: int) -> Broadcast:
        """
        بدء (أو استئناف) الإرسال.

        التحقق من الحالة السابقة إلزامي: لا نعيد تشغيل إذاعة مكتملة أو ملغاة
        حتى لا يُرسل النص مرتين لمن استلمه.

        الاستثناءات: PermissionDeniedError · ValidationError على الحالة غير المسموحة.
        """
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        broadcast = await self._require(broadcast_id)
        if broadcast.status not in RESUMABLE_STATUSES:
            raise ValidationError(
                f"حالة غير قابلة للبدء: {broadcast.status}",
                user_message="⚠️ لا يمكن بدء هذه الرسالة في حالتها الحالية.",
            )
        remaining = await self.repos.broadcasts.pending_count(broadcast_id)
        if remaining == 0:
            raise ValidationError(
                "لا مستلمين متبقين", user_message="⚠️ لا يوجد مستلمون متبقون في هذه الرسالة."
            )

        async with self.db.transaction() as tx:
            started = await self.repos.broadcasts.set_status(
                tx,
                broadcast_id,
                BroadcastStatus.RUNNING,
                expected_statuses=RESUMABLE_STATUSES,       # شرط ذرّي: لا نُحيي إذاعة أُلغيت/اكتملت للتو
                started_at=broadcast.started_at or utc_now_iso(),
            )
            if not started:
                raise ValidationError(
                    f"تغيّرت حالة الإذاعة {broadcast_id} أثناء البدء",
                    user_message="⚠️ تغيّرت حالة هذه الرسالة للتو (أُلغيت أو اكتملت) — حدّث الشاشة.",
                )
            await self.audit.log(
                tx,
                action="broadcast.send",
                admin_id=actor.id,
                target_type="broadcast",
                target_id=broadcast_id,
                before={"status": broadcast.status},
                after={"status": BroadcastStatus.RUNNING.value, "remaining": remaining},
            )
        logger.info("بدأ الأدمن %s إرسال الإذاعة #%s (%s متبقٍ)", actor.id, broadcast_id, remaining)
        return await self._require(broadcast_id)

    async def pause(self, actor: User, broadcast_id: int) -> bool:
        """
        إيقاف مؤقت للإرسال (يمكن استئنافه لاحقاً من نفس النقطة).

        المخرجات: True إن تغيّرت الحالة فعلاً.
        """
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        broadcast = await self._require(broadcast_id)
        if broadcast.status != BroadcastStatus.RUNNING:
            return False
        async with self.db.transaction() as tx:
            changed = await self.repos.broadcasts.set_status(
                tx, broadcast_id, BroadcastStatus.PAUSED, expected_statuses=(BroadcastStatus.RUNNING,)
            )
            if changed:
                await self.audit.log(
                    tx,
                    action="broadcast.send",
                    admin_id=actor.id,
                    target_type="broadcast",
                    target_id=broadcast_id,
                    before={"status": broadcast.status},
                    after={"status": BroadcastStatus.PAUSED.value},
                )
        logger.info("أوقف الأدمن %s الإذاعة #%s مؤقتاً", actor.id, broadcast_id)
        return changed

    async def cancel(self, actor: User, broadcast_id: int) -> bool:
        """
        إلغاء نهائي: لا تُستأنف بعده، ومن وصلته الرسالة تبقى عنده.

        لا نحذف صفوف المستلمين — السجل التاريخي لمن وصلته الرسالة يبقى كاملاً.
        """
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        broadcast = await self._require(broadcast_id)
        if broadcast.status in (BroadcastStatus.COMPLETED, BroadcastStatus.CANCELLED):
            return False
        async with self.db.transaction() as tx:
            changed = await self.repos.broadcasts.set_status(
                tx,
                broadcast_id,
                BroadcastStatus.CANCELLED,
                expected_statuses=(BroadcastStatus.DRAFT, BroadcastStatus.RUNNING, BroadcastStatus.PAUSED),
                finished_at=utc_now_iso(),
            )
            if changed:
                await self.audit.log(
                    tx,
                    action="broadcast.send",
                    admin_id=actor.id,
                    target_type="broadcast",
                    target_id=broadcast_id,
                    before={"status": broadcast.status, "sent": broadcast.sent_count},
                    after={"status": BroadcastStatus.CANCELLED.value},
                )
        logger.warning("ألغى الأدمن %s الإذاعة #%s", actor.id, broadcast_id)
        return changed

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, actor: User, broadcast_id: int) -> Broadcast:
        """جلب إذاعة واحدة للعرض في اللوحة."""
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        return await self._require(broadcast_id)

    async def recent(self, actor: User, *, limit: int = 8) -> list[Broadcast]:
        """آخر الإذاعات (الأحدث أولاً) لشاشة «📣 الرسائل الجماعية»."""
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        return await self.repos.broadcasts.list_recent(limit=limit)

    async def progress(self, actor: User, broadcast_id: int) -> dict[str, Any]:
        """
        تقدم إذاعة بالأرقام الحقيقية: المرسل والفاشل والمحظور والمتبقي.

        كل رقم من قاعدة البيانات مباشرة، لا عدّادات في الذاكرة.
        """
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        broadcast = await self._require(broadcast_id)
        pending = await self.repos.broadcasts.pending_count(broadcast_id)
        done = broadcast.sent_count + broadcast.failed_count + broadcast.blocked_count
        percent = int(done * 100 / broadcast.total_count) if broadcast.total_count else 0
        return {
            "broadcast": broadcast,
            "pending": pending,
            "done": done,
            "percent": min(100, percent),
            "target_label": await self.target_label(broadcast.target),
        }

    # ------------------------------ الإرسال ------------------------------ #

    async def next_running(self) -> Broadcast | None:
        """أقدم إذاعة جارية (نُرسل واحدة في كل جولة حتى لا نتجاوز حدود تيليجرام)."""
        running = await self.repos.broadcasts.list_running()
        return running[0] if running else None

    async def send_batch(self, sender: BroadcastSender, *, limit: int | None = None) -> BroadcastRound:
        """
        جولة إرسال واحدة للإذاعة الجارية الحالية.

        المدخلات:
            sender : دالة إرسال من طبقة تيليجرام ترفع استثناءات الإشعارات المعروفة.
            limit  : حجم الدفعة (الافتراضي من الإعدادات `broadcast_batch_size`).

        المخرجات: حصيلة الجولة. إذاعة بلا متبقٍ تُغلق تلقائياً ويُشعَر منشئها.

        ملاحظة: كل مستلم يُسجَّل في معاملة قصيرة مستقلة، فلا تبقى قاعدة البيانات
        مقفلة أثناء انتظار الشبكة، ولا نفقد نتيجة من أُرسل له عند أي انقطاع.
        """
        if self._round_lock.locked():
            return BroadcastRound()          # جولة أخرى جارية الآن: لا ننتظرها ولا نزاحمها
        async with self._round_lock:
            return await self._send_batch_locked(sender, limit=limit)

    async def _send_batch_locked(self, sender: BroadcastSender, *, limit: int | None) -> BroadcastRound:
        """جسم جولة الإرسال (يُستدعى حصراً تحت `_round_lock`)."""
        broadcast = await self.next_running()
        if broadcast is None:
            return BroadcastRound()

        batch_size = limit or await self.settings.get_int("broadcast_batch_size", 20)
        batch_size = max(1, min(50, batch_size))

        async with self.db.transaction() as tx:
            claimed = await self.repos.broadcasts.claim_recipients(
                tx, broadcast.id, limit=batch_size
            )

        # وتيرة الإرسال من الإعداد `broadcast_rate_per_second` (كان مجرد رقم لا أثر له): فاصل أدنى بين رسالتين
        rate = max(1, await self.settings.get_int("broadcast_rate_per_second", 20))
        gap = 1.0 / rate
        loop = asyncio.get_running_loop()
        last_started: float | None = None

        round_report = BroadcastRound(broadcast_id=broadcast.id, claimed=len(claimed))
        for row in claimed:
            if last_started is not None:
                wait = last_started + gap - loop.time()
                if wait > 0:
                    await asyncio.sleep(wait)
            last_started = loop.time()
            status, error = await self._send_one(sender, broadcast, int(row["telegram_id"]))
            async with self.db.transaction() as tx:
                recorded = await self.repos.broadcasts.mark_recipient(
                    tx, int(row["id"]), status=status, error=error
                )
                if recorded and status == RecipientStatus.BLOCKED:
                    await self.repos.users.set_blocked_bot(tx, int(row["user_id"]), True)
            if not recorded:
                continue  # سُجِّلت نتيجته في جولة أخرى — لا نعدّه مرتين
            if status == RecipientStatus.SENT:
                round_report.sent += 1
            elif status == RecipientStatus.BLOCKED:
                round_report.blocked += 1
            else:
                round_report.failed += 1

        remaining = await self.repos.broadcasts.pending_count(broadcast.id)
        if remaining == 0:
            await self._complete(broadcast.id)
            round_report.completed = True

        if round_report.claimed:
            logger.info("جولة إذاعة: %s", round_report.as_dict())
        return round_report

    async def _send_one(
        self, sender: BroadcastSender, broadcast: Broadcast, telegram_id: int
    ) -> tuple[str, str | None]:
        """
        إرسال رسالة واحدة وتصنيف نتيجتها.

        الأخطاء المؤقتة (شبكة/حد معدل) تُعاد محاولتها **مرة واحدة** بعد ثانية،
        فإن تكررت سُجِّلت كفشل مع نص الخطأ بدل تعليق الطابور إلى الأبد.

        المخرجات: (حالة المستلم، نص الخطأ المختصر أو None).
        """
        for attempt in (1, 2):
            try:
                await sender(
                    telegram_id,
                    broadcast.message_text,
                    broadcast.media_file_id,
                    broadcast.media_type,
                )
            except NotificationBlockedError as exc:
                return RecipientStatus.BLOCKED, sanitize(str(exc))[:200]
            except NotificationTemporaryError as exc:
                if attempt == 1:
                    await asyncio.sleep(1)
                    continue
                return RecipientStatus.FAILED, sanitize(str(exc))[:200]
            except NotificationPermanentError as exc:
                return RecipientStatus.FAILED, sanitize(str(exc))[:200]
            else:
                return RecipientStatus.SENT, None
        return RecipientStatus.FAILED, "تعذر الإرسال بعد محاولتين"

    async def _complete(self, broadcast_id: int) -> None:
        """إغلاق الإذاعة بعد انتهاء مستلميها وإشعار الأدمن الذي أنشأها بالحصيلة."""
        broadcast = await self.repos.broadcasts.get(broadcast_id)
        if broadcast is None or broadcast.status != BroadcastStatus.RUNNING:
            return
        async with self.db.transaction() as tx:
            completed = await self.repos.broadcasts.set_status(
                tx,
                broadcast_id,
                BroadcastStatus.COMPLETED,
                expected_statuses=(BroadcastStatus.RUNNING,),   # إلغاء/إيقاف متزامن لا يُمحى بالإكمال
                finished_at=utc_now_iso(),
            )
            if not completed:
                return
            if broadcast.admin_id:
                title, message = templates.broadcast_finished(
                    broadcast_id=broadcast_id,
                    sent=broadcast.sent_count,
                    failed=broadcast.failed_count,
                    blocked=broadcast.blocked_count,
                )
                await self.notifications.notify_user_manual(
                    tx,
                    user_id=broadcast.admin_id,
                    token=f"broadcast:{broadcast_id}:done",
                    title=title,
                    message=message,
                )
        logger.info(
            "اكتملت الإذاعة #%s: وصلت %s · حظر %s · فشل %s",
            broadcast_id, broadcast.sent_count, broadcast.blocked_count, broadcast.failed_count,
        )
```

## `services/auth_service.py`

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
```

## `services/notification_service.py`

```python
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

from collections import deque
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


@dataclass(slots=True)
class DispatchReport:
    """حصيلة جولة إرسال واحدة من الطابور."""

    claimed: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0

    def as_dict(self) -> dict[str, int]:
        """تحويل الحصيلة إلى قاموس للتسجيل في اللوق."""
        return {
            "claimed": self.claimed,
            "sent": self.sent,
            "failed": self.failed,
            "skipped": self.skipped,
        }


class NotificationService:
    """إدراج الإشعارات في الطابور وإرسالها لاحقاً بأمان."""

    def __init__(self, db: Database, repos: Repositories, settings: SettingsService) -> None:
        """تهيئة الخدمة."""
        self.db = db
        self.repos = repos
        self.settings = settings
        #: نسخ تنبيهات الأدمن المنتظرة للإرسال إلى قناة التنبيهات (في الذاكرة، محدودة، best-effort):
        #: الإرسال الدائم يبقى للأدمن أنفسهم عبر الطابور؛ القناة نسخة إضافية لا يتوقف عليها شيء
        self._alert_outbox: deque[tuple[str, str]] = deque(maxlen=100)

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
    ) -> int:
        """
        إرسال تنبيه لكل من يملك صلاحية معينة (مثل `orders.view` أو `payments.approve`).

        المخرجات: عدد الإشعارات التي أُدرجت فعلاً (المكررة لا تُحتسب).

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
        if inserted:
            self._alert_outbox.append((title, message))      # نسخة واحدة للقناة لا لكل أدمن
        return inserted

    async def flush_alert_channel(self, sender: NotificationSender, *, fallback_chat_id: int | None = None) -> int:
        """
        إرسال نسخ تنبيهات الأدمن المتراكمة إلى قناة/مجموعة التنبيهات (إن عُيّنت).

        القناة المستهدفة: الإعداد `admin_alert_chat_id` (يُعدَّل من البوت) وإلا متغير البيئة
        `ADMIN_ALERT_CHAT_ID` (`fallback_chat_id`). بلا قناة تُفرَّغ النسخ (لا تتراكم بلا نهاية).
        فشل الإرسال يُسجَّل ولا يُعاد (لا يتوقف عليه شيء: الأدمن استلموا تنبيههم عبر الطابور).

        المخرجات: عدد النسخ المرسلة فعلاً.
        """
        if not self._alert_outbox:
            return 0
        raw = (await self.settings.get_str("admin_alert_chat_id", "")).strip()
        chat_id = int(raw) if raw.lstrip("-").isdigit() else fallback_chat_id
        pending = list(self._alert_outbox)
        self._alert_outbox.clear()
        if chat_id is None:
            return 0

        sent = 0
        for title, message in pending:
            try:
                await sender(chat_id, title, message)
            except (NotificationBlockedError, NotificationPermanentError, NotificationTemporaryError) as exc:
                logger.warning("تعذّر إرسال نسخة التنبيه لقناة التنبيهات: %s", sanitize(str(exc))[:200])
                continue
            sent += 1
        return sent

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
        self, sender: NotificationSender, *, limit: int = 25, lease_seconds: int = 60
    ) -> DispatchReport:
        """
        إرسال دفعة من الإشعارات المنتظرة.

        المدخلات:
            sender : دالة غير متزامنة (telegram_id, title, message) → معرف الرسالة.
                     يجب أن ترفع NotificationBlockedError إذا حظر المستخدم البوت،
                     وNotificationTemporaryError عند فشل قابل لإعادة المحاولة.

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

        for notification in batch:
            telegram_id = await self._telegram_id_for(notification.user_id)
            if telegram_id is None:
                async with self.db.transaction() as tx:
                    await self.repos.notifications.mark_skipped(
                        tx, notification.id, "المستخدم غير موجود"
                    )
                report.skipped += 1
                continue

            try:
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
```

## `jobs/order_jobs.py`

```python
"""
مهام دورة حياة الطلب: الإرسال للمزود، فحص الحالة، تنبيه الطلبات العالقة.

منطق العمل كله داخل `OrderService` (المرحلة 2) — هذه الملفات مجرد جدولة
زمنية تستدعيه. الفائدة: يبقى المنطق قابلاً للاختبار بلا تيليجرام ولا مؤقتات.
"""

from __future__ import annotations

from telegram.ext import ContextTypes

from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: عدد الطلبات التي تُرسل للمزود في الجولة الواحدة (افتراضي عند غياب الإعداد)
SUBMIT_BATCH = 5

#: عدد الطلبات التي تُفحص حالتها في الجولة الواحدة (افتراضي عند غياب الإعداد)
CHECK_BATCH = 20

#: الحد الأقصى المسموح لحجم الدفعة مهما كان الإعداد (حماية من قيمة خاطئة)
MAX_BATCH = 100


async def _batch_size(services, key: str, default: int) -> int:
    """قراءة حجم الدفعة من الإعدادات ضمن حدود آمنة (1..MAX_BATCH)."""
    value = await services.settings.get_int(key, default)
    return max(1, min(MAX_BATCH, value))


async def submit_pending_orders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    إرسال الطلبات المعلّقة إلى المزودين.

    الحجز (lease) داخل الخدمة يمنع إرسال الطلب مرتين حتى لو تداخلت جولتان.
    """
    services = context.application.bot_data["services"]
    # أولاً: طلبات علقت في submitting بعد انتهاء قفلها (مهلة/انقطاع) ⇒ غير مؤكدة وتنبيه، قبل حجز جديد
    await services.orders.recover_stale_submissions()
    limit = await _batch_size(services, "order_submit_batch_size", SUBMIT_BATCH)
    report = await services.orders.process_pending_orders(worker="submitter", limit=limit)
    if report.claimed:
        logger.info("جولة إرسال الطلبات: %s", report.as_dict())


async def check_active_orders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    فحص حالة الطلبات النشطة عند المزود وتحديثها (إكمال/جزئي/فشل + استرجاع).

    هذه هي المهمة التي تجعل الطلب «يمشي لوحده» حتى حالته النهائية.
    """
    services = context.application.bot_data["services"]
    limit = await _batch_size(services, "order_check_batch_size", CHECK_BATCH)
    report = await services.orders.process_due_orders(worker="checker", limit=limit)
    if report.claimed:
        logger.info("جولة فحص الطلبات: %s", report.as_dict())


async def alert_stuck_orders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """تنبيه الأدمن بالطلبات التي لم تتقدم منذ مدة طويلة (مؤشر خلل صامت)."""
    services = context.application.bot_data["services"]
    count = await services.orders.alert_stuck_orders()
    if count:
        logger.warning("طلبات متوقفة بلا تقدم: %s", count)
```

## `jobs/notification_jobs.py`

```python
"""
مهمة إرسال الإشعارات من الطابور إلى تيليجرام.

لماذا طابور بدل الإرسال المباشر؟
    لأن الإرسال المباشر داخل المعاملة يربط نجاح العملية المالية بنجاح الشبكة.
    هنا: العملية تُسجَّل في قاعدة البيانات وتُدرج رسالتها في `notifications`،
    ثم تأتي هذه المهمة كل بضع ثوانٍ وتُرسل ما تراكم. انقطاع الشبكة يؤخر
    الإشعار فقط ولا يُفسد أي عملية.
"""

from __future__ import annotations

from telegram.ext import ContextTypes

from jobs.telegram_sender import TelegramNotificationSender
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: أقصى عدد إشعارات تُرسل في الجولة الواحدة (حماية من حدود تيليجرام)
BATCH_LIMIT = 20


async def dispatch_notifications(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    جولة إرسال واحدة: تحجز دفعة من الطابور وترسلها ثم تسجّل الحصيلة.

    الأخطاء هنا لا تُسقط المهمة الدورية: خدمة الإشعارات تُصنّف كل فشل
    (محظور / مؤقت / نهائي) وتتعامل معه، وما يصل إلى هنا يُسجَّل في اللوق.
    """
    services = context.application.bot_data["services"]
    sender = TelegramNotificationSender(context.bot)
    report = await services.notifications.dispatch_pending(sender, limit=BATCH_LIMIT)
    if report.claimed:
        logger.info("جولة إشعارات: %s", report.as_dict())

    # نسخة تنبيهات الأدمن إلى قناة التنبيهات (إن عُيّنت في الإعدادات أو `ADMIN_ALERT_CHAT_ID`)
    config = context.application.bot_data.get("config")
    await services.notifications.flush_alert_channel(
        sender, fallback_chat_id=getattr(config, "admin_alert_chat_id", None)
    )
```

## `integrations/providers/base.py`

```python
"""
الواجهة المجردة لمزودي الخدمات (Provider Client).

الفكرة: بقية النظام لا يعرف شيئاً عن شكل API أي مزود — يتعامل فقط مع هذه الواجهة
وأنواع البيانات المعرَّفة هنا. إضافة مزود بمعيار مختلف = ملف جديد يطبّق `ProviderClient`
دون لمس أي سطر في الخدمات أو الواجهة.

تصنيف الأخطاء (مهم جداً لسلامة المال):
    • ProviderTemporaryError        → آمن لإعادة المحاولة (شبكة/حد معدل).
    • ProviderInsufficientFundsError → مؤقت كذلك، لكن سببه رصيدنا لدى المزود.
    • ProviderPermanentError        → لا فائدة من إعادة المحاولة (رفض صريح) ⇒ فشل + استرجاع.
    • ProviderUncertainError        → لا نعرف هل وصل الطلب ⇒ ممنوع إعادة الإرسال آلياً.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.money import MONEY_SCALE


#: أنواع الخدمات التي يدعمها النظام فعلاً: الطلب العادي (رابط + كمية) فقط. الأنواع الأخرى
#: (Package/Custom Comments/Subscriptions/…) تحتاج حقولاً إضافية (تعليقات، اسم مستخدم، مدة…) لا يجمعها مسار الطلب.
SUPPORTED_SERVICE_TYPES: frozenset[str] = frozenset({"default"})


def normalize_service_type(raw: Any) -> str:
    """توحيد نوع الخدمة القادم من المزود: أحرف صغيرة وشرطة سفلية بدل المسافات («Custom Comments» ⇒ custom_comments)."""
    text = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    return text or "default"


@dataclass(frozen=True, slots=True)
class ProviderOrderResult:
    """نتيجة إنشاء طلب عند المزود."""

    provider_order_id: str          # رقم الطلب عند المزود (لا يكون فارغاً أبداً)
    charge_units: int | None = None  # ما خصمه المزود منا (بوحدات المال) إن أرسله
    currency: str = "USD"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderStatusResult:
    """نتيجة الاستعلام عن حالة طلب لدى المزود."""

    raw_status: str                  # نص الحالة كما ورد من المزود
    start_count: int | None = None   # العدد قبل البدء
    remains: int | None = None       # المتبقي
    delivered: int | None = None     # المنفَّذ فعلياً (إن أرسله المزود)
    charge_units: int | None = None
    currency: str = "USD"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderBalance:
    """رصيد حسابنا لدى المزود."""

    amount_units: int
    currency: str = "USD"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderServiceItem:
    """خدمة واحدة كما يعرضها المزود (تُستخدم في الاستيراد والمزامنة)."""

    provider_service_id: str
    name: str
    rate_per_1000_units: int          # سعر المزود بوحدات المال
    min_quantity: int
    max_quantity: int
    category: str = ""
    service_type: str = "default"
    dripfeed: bool = False
    refill: bool = False
    cancel: bool = False
    currency: str = "USD"
    raw: dict[str, Any] = field(default_factory=dict)


class ProviderClient(ABC):
    """
    الواجهة التي يجب أن يطبّقها كل عميل مزود.

    ملاحظات للمطوّر:
        • كل الدوال غير متزامنة ولا تفتح أي معاملة قاعدة بيانات.
        • ممنوع أن يُرجع أي عميل مفتاح API أو يضعه في نص خطأ — استخدم `secrets()`
          لتمرير القيم الحساسة إلى أداة التنقية قبل أي تسجيل.
    """

    #: المعرّف النصي لنوع المزود (يطابق عمود providers.api_type)
    api_type: str = "base"

    def __init__(self, *, api_url: str, api_key: str, timeout_seconds: int = 30) -> None:
        """تهيئة العميل ببيانات الاتصال (المفتاح يبقى داخل الكائن ولا يُسجَّل)."""
        self.api_url = api_url
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds

    def secrets(self) -> tuple[str, ...]:
        """القيم السرية التي يجب حذفها من أي نص قبل تسجيله (تُمرَّر إلى sanitize)."""
        return (self._api_key,) if self._api_key else ()

    @abstractmethod
    async def add_order(
        self, *, provider_service_id: str, link: str, quantity: int, extras: dict[str, Any] | None = None
    ) -> ProviderOrderResult:
        """إنشاء طلب جديد عند المزود وإرجاع رقمه."""

    @abstractmethod
    async def get_order_status(self, provider_order_id: str) -> ProviderStatusResult:
        """الاستعلام عن حالة طلب واحد."""

    @abstractmethod
    async def get_balance(self) -> ProviderBalance:
        """قراءة رصيد حسابنا لدى المزود."""

    @abstractmethod
    async def get_services(self) -> list[ProviderServiceItem]:
        """جلب قائمة خدمات المزود (للاستيراد والمزامنة)."""

    async def get_multi_status(self, provider_order_ids: list[str]) -> dict[str, ProviderStatusResult]:
        """
        الاستعلام عن عدة طلبات دفعة واحدة.

        التطبيق الافتراضي يستدعي `get_order_status` لكل طلب؛ المزود الذي يدعم
        الاستعلام الجماعي يعيد تعريف هذه الدالة لتوفير الاستدعاءات.
        """
        results: dict[str, ProviderStatusResult] = {}
        for provider_order_id in provider_order_ids:
            results[provider_order_id] = await self.get_order_status(provider_order_id)
        return results

    async def cancel_order(self, provider_order_id: str) -> bool:
        """
        طلب إلغاء لدى المزود.

        المخرجات: False افتراضياً لأن أغلب اللوحات لا تدعم الإلغاء —
                  المزود الذي يدعمه يعيد تعريف الدالة.
        """
        return False

    async def refill_order(self, provider_order_id: str) -> bool:
        """طلب إعادة تعبئة (refill) — غير مدعوم افتراضياً."""
        return False

    async def close(self) -> None:
        """إغلاق أي موارد شبكة مفتوحة (اتصالات/جلسات). افتراضياً لا شيء."""
        return None

    def money_from_decimal_text(self, text: str | float | int | None) -> int | None:
        """
        تحويل مبلغ نصي من المزود (مثل "1.2345") إلى وحدات صحيحة.

        المخرجات: عدد الوحدات، أو None إذا كانت القيمة غير قابلة للتحويل
                  (لا نُسقط العملية بسبب حقل تكلفة غير مفهوم).
        """
        if text is None or text == "":
            return None
        try:
            from decimal import Decimal

            return int((Decimal(str(text)) * MONEY_SCALE).to_integral_value())
        except (ArithmeticError, ValueError, TypeError):
            return None
```

## `integrations/providers/perfect_panel.py`

```python
"""
عميل المزودين بمعيار Perfect Panel — وهو المعيار الذي تستخدمه أغلب لوحات SMM.

شكل الواجهة لدى هذه اللوحات موحّد تقريباً:

    POST {api_url}
    key=<api_key>&action=add&service=<id>&link=<url>&quantity=<n>   ⇐ إنشاء طلب
    key=<api_key>&action=status&order=<id>                          ⇐ حالة طلب
    key=<api_key>&action=status&orders=1,2,3                        ⇐ حالات متعددة
    key=<api_key>&action=services                                   ⇐ قائمة الخدمات
    key=<api_key>&action=balance                                    ⇐ رصيدنا لديهم

والاستجابة JSON دائماً، والخطأ يأتي داخل الحقل `error` بحالة 200 غالباً.

مبدأ السلامة المالية في هذا الملف (الأهم فيه):
    • كل خطأ شبكة/مهلة **قبل** تأكيد الإرسال  → ProviderTemporaryError (إعادة محاولة آمنة).
    • كل مهلة أو انقطاع **أثناء** إنشاء الطلب → ProviderUncertainError (ممنوع إعادة الإرسال
      تلقائياً، لأن الطلب قد يكون وصل بالفعل وخُصم منا).
    • الرفض الصريح (خدمة غير موجودة، رابط غير صالح، كمية خاطئة) → ProviderPermanentError.
    • نقص الرصيد لدى المزود → ProviderInsufficientFundsError (مؤقت: يُحل بالشحن).

ولا يخرج مفتاح API من هذا الملف أبداً: لا في رسالة خطأ ولا في لوق — تُمرَّر القيم
السرية عبر `secrets()` لأداة التنقية `sanitize` قبل أي تسجيل.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from core.exceptions import (
    ProviderError,
    ProviderInsufficientFundsError,
    ProviderPermanentError,
    ProviderServiceMismatchError,
    ProviderTemporaryError,
    ProviderUncertainError,
)
from integrations.providers.base import (
    ProviderBalance,
    ProviderClient,
    ProviderOrderResult,
    ProviderServiceItem,
    ProviderStatusResult,
    normalize_service_type,
)
from utils.net_security import ensure_public_host

logger = logging.getLogger(__name__)

#: أقصى عدد محارف نحتفظ به من نص الاستجابة عند بناء رسالة خطأ (منعاً لتضخم اللوق)
ERROR_SNIPPET_LIMIT = 200

#: أقصى حجم لجسم استجابة المزود (بالبايت). قائمة خدمات كبيرة بضعة ميغابايت؛ ما فوق ذلك استجابة شاذة
#: أو خبيثة تستهلك الذاكرة، فنقطعها أثناء القراءة (التدفق) لا بعد تحميلها كاملة
MAX_RESPONSE_BYTES = 10 * 1024 * 1024

#: كلمات ترد في نص خطأ المزود وتعني «رصيدك لدينا لا يكفي»
INSUFFICIENT_FUNDS_WORDS = (
    "not enough funds",
    "insufficient funds",
    "insufficient balance",
    "not enough balance",
    "no funds",
    "low balance",
)

#: كلمات تعني أن رقم الخدمة أو معاملاتها خاطئة عندنا (إعداد خاطئ لا عطل مؤقت)
SERVICE_MISMATCH_WORDS = (
    "incorrect service",
    "invalid service",
    "service not found",
    "service is not active",
    "incorrect service id",
)

#: كلمات تعني ضغطاً مؤقتاً أو صيانة ⇒ إعادة المحاولة آمنة
TEMPORARY_WORDS = (
    "try again",
    "too many requests",
    "rate limit",
    "temporarily",
    "maintenance",
    "server busy",
    "timeout",
)


class _ResponseTooLarge(Exception):
    """داخلي: جسم استجابة المزود تجاوز الحد المسموح (يُحوَّل إلى خطأ مزود مصنَّف في `_post`)."""


class PerfectPanelClient(ProviderClient):
    """
    عميل HTTP حقيقي للوحات المتوافقة مع Perfect Panel API v2.

    الاستخدام:
        client = PerfectPanelClient(api_url=..., api_key=..., timeout_seconds=30)
        try:
            result = await client.add_order(provider_service_id="55", link=..., quantity=1000)
        finally:
            await client.close()
    """

    api_type = "perfect_panel"

    def __init__(
        self,
        *,
        api_url: str,
        api_key: str,
        timeout_seconds: int = 30,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """
        تهيئة العميل.

        المدخلات:
            client : عميل httpx جاهز — يُمرَّر في الاختبارات لحقن نقل وهمي
                     (MockTransport)، وفي التشغيل يُبنى تلقائياً عند أول طلب.
        """
        super().__init__(api_url=api_url, api_key=api_key, timeout_seconds=timeout_seconds)
        self._client = client
        self._owns_client = client is None

    # ======================================================================= #
    #                           طبقة الاتصال الدنيا                            #
    # ======================================================================= #

    def _http(self) -> httpx.AsyncClient:
        """إرجاع عميل HTTP (يُنشأ عند أول استخدام ويُعاد استخدامه بعدها)."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds),
                headers={"User-Agent": "smm-bot/1.0"},
                # ممنوع تتبّع التحويلات: الطلب يحمل مفتاح المزود، وتحويل 307/308
                # يعيد إرسال الجسم نفسه إلى مضيف آخر فيُسرَّب المفتاح.
                follow_redirects=False,
            )
            self._owns_client = True
        return self._client

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
            response = await self._read_limited(data)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            # التفريق هنا هو الفرق بين إعادة محاولة آمنة وبين طلب مكرر يكلّف مالاً
            if uncertain_on_timeout:
                raise ProviderUncertainError(
                    f"انقطع الاتصال أثناء إرسال الطلب ({type(exc).__name__})"
                ) from exc
            raise ProviderTemporaryError(
                f"تعذر الاتصال بالمزود أثناء {action} ({type(exc).__name__})"
            ) from exc
        except _ResponseTooLarge as exc:
            if uncertain_on_timeout:                       # الطلب قد يكون سُجّل لدى المزود: لا نعيد الإرسال
                raise ProviderUncertainError(f"استجابة المزود أكبر من الحد المسموح بعد الإرسال ({exc})") from exc
            raise ProviderTemporaryError(f"استجابة المزود أكبر من الحد المسموح أثناء {action} ({exc})") from exc
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

    async def _read_limited(self, data: dict[str, Any]) -> httpx.Response:
        """
        POST مع قراءة الجسم بالتدفق وقطعها عند `MAX_RESPONSE_BYTES`.

        المخرجات: استجابة كاملة الجسم (مفكوكة الضغط) صالحة لـ`.json()`/`.text`.
        الاستثناءات: `_ResponseTooLarge` (داخلي) يحوّله `_post` إلى مؤقت/غير مؤكد حسب السياق.
        """
        async with self._http().stream("POST", self.api_url, data=data) as streamed:
            declared = streamed.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > MAX_RESPONSE_BYTES:
                raise _ResponseTooLarge(f"حجم الاستجابة المعلن {declared} بايت")
            body = bytearray()
            async for chunk in streamed.aiter_bytes():
                body += chunk
                if len(body) > MAX_RESPONSE_BYTES:
                    raise _ResponseTooLarge(f"تجاوزت الاستجابة {MAX_RESPONSE_BYTES} بايت")
            return httpx.Response(streamed.status_code, content=bytes(body), request=streamed.request)

    def _raise_for_status(
        self, response: httpx.Response, action: str, *, uncertain_on_timeout: bool
    ) -> None:
        """تحويل رمز حالة HTTP إلى الاستثناء الصحيح (مؤقت/نهائي/غير مؤكد)."""
        status = response.status_code
        if 300 <= status < 400:
            # لا نتبع التحويلات (انظر _http) — نعدّه خطأ إعداد دائماً لا مؤقتاً
            raise ProviderPermanentError(
                f"المزود يعيد توجيه الطلب (HTTP {status}) — صحّح رابط API ليشير للعنوان النهائي مباشرة"
            )
        if status < 400:
            return
        snippet = response.text[:ERROR_SNIPPET_LIMIT]
        if status == 429 or status >= 500:
            if uncertain_on_timeout and status >= 500:
                # 5xx بعد إرسال الطلب: قد يكون المزود سجّله ثم فشل في الرد
                raise ProviderUncertainError(f"المزود رد بخطأ {status} بعد الإرسال: {snippet}")
            raise ProviderTemporaryError(f"المزود رد بالحالة {status} أثناء {action}: {snippet}")
        raise ProviderPermanentError(f"المزود رفض الطلب بالحالة {status}: {snippet}")

    def _check_error_field(self, payload: Any, *, uncertain_on_timeout: bool = False) -> dict:
        """
        فحص حقل `error` في استجابة JSON وتحويله إلى الاستثناء المناسب.

        المخرجات: القاموس نفسه إن لم يكن فيه خطأ.
        """
        if not isinstance(payload, dict):
            raise ProviderTemporaryError("استجابة المزود ليست كائن JSON متوقعاً")

        error = payload.get("error")
        if not error:
            return payload

        text = str(error)
        lowered = text.lower()
        if any(word in lowered for word in INSUFFICIENT_FUNDS_WORDS):
            raise ProviderInsufficientFundsError(f"رصيدنا لدى المزود غير كافٍ: {text}")
        if any(word in lowered for word in SERVICE_MISMATCH_WORDS):
            raise ProviderServiceMismatchError(f"المزود رفض رقم الخدمة: {text}")
        if any(word in lowered for word in TEMPORARY_WORDS):
            raise ProviderTemporaryError(f"خطأ مؤقت من المزود: {text}")
        if uncertain_on_timeout and "duplicate" in lowered:
            # المزود يقول «طلب مكرر» ⇒ غالباً الطلب الأول وصل: لا نُعيد الإرسال
            raise ProviderUncertainError(f"المزود أبلغ بتكرار الطلب: {text}")
        raise ProviderPermanentError(f"المزود رفض الطلب: {text}")

    # ======================================================================= #
    #                               الطلبات                                   #
    # ======================================================================= #

    async def add_order(
        self,
        *,
        provider_service_id: str,
        link: str,
        quantity: int,
        extras: dict[str, Any] | None = None,
    ) -> ProviderOrderResult:
        """
        إنشاء طلب جديد عند المزود.

        المخرجات: رقم الطلب عند المزود (وما خصمه منا إن أرسله).

        الاستثناءات:
            ProviderUncertainError : انقطاع/مهلة أثناء الإرسال ⇒ يتولاها مسار
                                     «النتيجة غير المؤكدة» ولا يُعاد الإرسال آلياً.
        """
        payload: dict[str, Any] = {
            "action": "add",
            "service": str(provider_service_id),
            "link": link,
            "quantity": int(quantity),
        }
        for key, value in (extras or {}).items():
            if value is not None and key not in payload:
                payload[key] = value

        raw = await self._post(payload, uncertain_on_timeout=True)
        data = self._check_error_field(raw, uncertain_on_timeout=True)

        order_id = data.get("order")
        if order_id in (None, "", 0):
            # لا رقم طلب ولا رسالة خطأ: لا نعرف ماذا حدث ⇒ غير مؤكد لا فاشل
            raise ProviderUncertainError(
                f"المزود لم يُرجع رقم طلب: {str(data)[:ERROR_SNIPPET_LIMIT]}"
            )

        return ProviderOrderResult(
            provider_order_id=str(order_id),
            charge_units=self.money_from_decimal_text(data.get("charge")),
            currency=str(data.get("currency") or "USD"),
            raw=data,
        )

    async def get_order_status(self, provider_order_id: str) -> ProviderStatusResult:
        """الاستعلام عن حالة طلب واحد لدى المزود."""
        raw = await self._post({"action": "status", "order": str(provider_order_id)})
        data = self._check_error_field(raw)
        return self._status_from_dict(data)

    async def get_multi_status(
        self, provider_order_ids: list[str]
    ) -> dict[str, ProviderStatusResult]:
        """
        الاستعلام عن عدة طلبات باستدعاء واحد (`orders=1,2,3`).

        المخرجات: قاموس {رقم الطلب عند المزود: نتيجة الحالة} — الطلبات التي ردّ
                  عليها المزود بخطأ فردي تُستثنى بدل إسقاط الدفعة كلها.
        """
        ids = [str(item) for item in provider_order_ids if str(item)]
        if not ids:
            return {}

        raw = await self._post({"action": "status", "orders": ",".join(ids)})
        if isinstance(raw, dict) and raw.get("error") and len(ids) > 1:
            # خطأ عام على الدفعة كلها: نتعامل معه كخطأ عادي
            self._check_error_field(raw)

        results: dict[str, ProviderStatusResult] = {}
        if isinstance(raw, dict):
            for order_id, value in raw.items():
                if not isinstance(value, dict) or value.get("error"):
                    logger.debug("تخطّي حالة الطلب %s: استجابة غير صالحة", order_id)
                    continue
                results[str(order_id)] = self._status_from_dict(value)
        elif isinstance(raw, list):
            # بعض اللوحات تُرجع قائمة بنفس ترتيب المعرفات المرسلة
            for index, value in enumerate(raw):
                if index < len(ids) and isinstance(value, dict) and not value.get("error"):
                    results[ids[index]] = self._status_from_dict(value)
        return results

    def _status_from_dict(self, data: dict[str, Any]) -> ProviderStatusResult:
        """تحويل قاموس حالة من المزود إلى `ProviderStatusResult` بأعداد صحيحة."""
        remains = self._as_int(data.get("remains"))
        start_count = self._as_int(data.get("start_count"))
        delivered = self._as_int(data.get("delivered"))
        quantity = self._as_int(data.get("quantity"))
        if delivered is None and quantity is not None and remains is not None:
            delivered = max(quantity - remains, 0)

        return ProviderStatusResult(
            raw_status=str(data.get("status") or "").strip() or "Unknown",
            start_count=start_count,
            remains=remains,
            delivered=delivered,
            charge_units=self.money_from_decimal_text(data.get("charge")),
            currency=str(data.get("currency") or "USD"),
            raw=data,
        )

    @staticmethod
    def _as_int(value: Any) -> int | None:
        """تحويل قيمة قد تأتي نصاً أو عشرية إلى عدد صحيح، أو None إن تعذّر."""
        if value is None or value == "":
            return None
        try:
            number = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            return None
        # لا NaN/Infinity، ولا أسس هائلة، ولا كسور (1.5 ليست «1»): القيمة المبهمة تُعامَل كغير معروفة
        if not number.is_finite() or number.adjusted() > 18 or number != number.to_integral_value():
            return None
        return int(number)

    async def cancel_order(self, provider_order_id: str) -> bool:
        """
        طلب إلغاء لدى المزود.

        المخرجات: True إذا قَبِل المزود الإلغاء. المزودون الذين لا يدعمون الإلغاء
                  يردّون بخطأ ⇒ نُرجع False بدل إسقاط العملية (الإلغاء محاولة لا وعد).
        """
        try:
            raw = await self._post({"action": "cancel", "order": str(provider_order_id)})
        except ProviderError as exc:
            logger.info("المزود لم يقبل إلغاء الطلب %s: %s", provider_order_id, exc)
            return False

        if isinstance(raw, dict):
            if raw.get("error"):
                return False
            return bool(raw.get("cancel") or raw.get("status") or raw.get("order"))
        if isinstance(raw, list) and raw:
            first = raw[0]
            return isinstance(first, dict) and not first.get("error")
        return False

    # ======================================================================= #
    #                           الرصيد وقائمة الخدمات                          #
    # ======================================================================= #

    async def get_balance(self) -> ProviderBalance:
        """قراءة رصيد حسابنا لدى المزود."""
        raw = await self._post({"action": "balance"})
        data = self._check_error_field(raw)
        amount_units = self.money_from_decimal_text(data.get("balance"))
        if amount_units is None:
            raise ProviderTemporaryError(
                f"المزود لم يُرجع رصيداً مفهوماً: {str(data)[:ERROR_SNIPPET_LIMIT]}"
            )
        return ProviderBalance(
            amount_units=amount_units,
            currency=str(data.get("currency") or "USD"),
            raw=data,
        )

    async def get_services(self) -> list[ProviderServiceItem]:
        """
        جلب قائمة خدمات المزود.

        المخرجات: قائمة الخدمات الصالحة فقط — أي عنصر ناقص الحقول الأساسية
                  (رقم/اسم/سعر) يُتخطّى مع تسجيله، لأن استيراد خدمة ناقصة
                  يعني طلباً سيفشل لاحقاً عند أول مستخدم.
        """
        raw = await self._post({"action": "services"})
        if isinstance(raw, dict):
            self._check_error_field(raw)                 # يرفع الاستثناء المناسب
            raise ProviderTemporaryError("استجابة قائمة الخدمات ليست قائمة")
        if not isinstance(raw, list):
            raise ProviderTemporaryError("استجابة قائمة الخدمات ليست قائمة")

        items: list[ProviderServiceItem] = []
        skipped = 0
        for entry in raw:
            item = self._service_from_dict(entry)
            if item is None:
                skipped += 1
                continue
            items.append(item)

        if skipped:
            logger.warning("تخطّي %s خدمة ناقصة الحقول من قائمة المزود", skipped)
        return items

    def _service_from_dict(self, entry: Any) -> ProviderServiceItem | None:
        """تحويل عنصر خدمة من المزود إلى `ProviderServiceItem`، أو None إن كان ناقصاً."""
        if not isinstance(entry, dict):
            return None

        service_id = entry.get("service") or entry.get("id")
        name = entry.get("name")
        rate_units = self.money_from_decimal_text(entry.get("rate"))
        minimum = self._as_int(entry.get("min"))
        maximum = self._as_int(entry.get("max"))
        if not service_id or not name or rate_units is None or minimum is None or maximum is None:
            return None
        if minimum <= 0 or maximum < minimum:
            return None

        return ProviderServiceItem(
            provider_service_id=str(service_id),
            name=str(name).strip(),
            rate_per_1000_units=rate_units,
            min_quantity=minimum,
            max_quantity=maximum,
            category=str(entry.get("category") or "").strip(),
            service_type=normalize_service_type(entry.get("type")),
            dripfeed=bool(entry.get("dripfeed")),
            refill=bool(entry.get("refill")),
            cancel=bool(entry.get("cancel")),
            currency=str(entry.get("currency") or "USD"),
            raw=entry,
        )

    # ======================================================================= #
    #                                الإغلاق                                  #
    # ======================================================================= #

    async def close(self) -> None:
        """إغلاق اتصال HTTP إن كان هذا العميل هو من أنشأه."""
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None
```

## `integrations/providers/registry.py`

```python
"""
سجل عملاء المزودين: تحويل `api_type` المخزَّن في قاعدة البيانات إلى عميل فعلي.

الفائدة: إضافة معيار API جديد = تسجيل صنف جديد هنا فقط، دون تعديل أي خدمة.
"""

from __future__ import annotations

from typing import Callable

from core.exceptions import ProviderError
from integrations.providers.base import ProviderClient
from integrations.providers.mock import MockProviderClient
from integrations.providers.perfect_panel import PerfectPanelClient

#: نوع الدالة المُنشئة لعميل مزود
ClientFactory = Callable[..., ProviderClient]

#: الأنواع المسجَّلة فعلياً والجاهزة للاستخدام
_REGISTRY: dict[str, ClientFactory] = {
    PerfectPanelClient.api_type: PerfectPanelClient,   # المعيار الحقيقي (المرحلة 5)
    MockProviderClient.api_type: MockProviderClient,   # للاختبار والتطوير فقط
}

#: أنواع للتطوير والاختبار فقط: معطَّلة افتراضياً فلا تظهر في الواجهة ولا يُنشأ لها عميل في الإنتاج
#: (مزود وهمي «ينجح» دائماً؛ وجوده بجانب مزودين حقيقيين خطر مالي). تُفعَّل صراحةً من الاختبارات/`demo_cycle`
DEV_ONLY_TYPES: frozenset[str] = frozenset({MockProviderClient.api_type})
_dev_types_enabled = False

#: أنواع مخطط لها لكنها لم تُنفَّذ بعد — نرفضها برسالة صريحة بدل تنفيذ صوري فارغ
_PLANNED: dict[str, str] = {}


def register_client(api_type: str, factory: ClientFactory) -> None:
    """تسجيل عميل مزود جديد تحت نوع محدد (يُستدعى عند إضافة معيار API جديد)."""
    _REGISTRY[api_type] = factory


def enable_dev_types(enabled: bool = True) -> None:
    """تفعيل/تعطيل أنواع التطوير (Mock). لا تُستدعَ في مسار الإنتاج؛ للاختبارات والعرض التجريبي فقط."""
    global _dev_types_enabled
    _dev_types_enabled = bool(enabled)


def dev_types_enabled() -> bool:
    """هل أنواع التطوير مفعّلة الآن؟"""
    return _dev_types_enabled


def available_types() -> tuple[str, ...]:
    """أنواع المزودين الجاهزة للاستخدام الآن (بلا أنواع التطوير ما لم تُفعَّل)."""
    return tuple(sorted(name for name in _REGISTRY if _dev_types_enabled or name not in DEV_ONLY_TYPES))


def is_supported(api_type: str) -> bool:
    """هل هذا النوع مدعوم فعلياً الآن (مسجَّل، وليس من أنواع التطوير المعطّلة)؟"""
    return api_type in available_types()


def create_client(
    *, api_type: str, api_url: str, api_key: str, timeout_seconds: int = 30
) -> ProviderClient:
    """
    إنشاء عميل مزود من نوعه المخزَّن في قاعدة البيانات.

    الاستثناءات:
        ProviderError : نوع غير معروف، أو نوع مخطط له ولم يُنفَّذ بعد.
    """
    factory = _REGISTRY.get(api_type) if is_supported(api_type) else None
    if factory is None:
        planned = _PLANNED.get(api_type)
        if planned:
            raise ProviderError(planned, user_message="⚠️ هذا المزود غير مفعّل بعد.")
        raise ProviderError(
            f"نوع مزود غير معروف: {api_type}. الأنواع المتاحة: {', '.join(available_types())}",
            user_message="⚠️ إعداد المزود غير صحيح. راجع لوحة التحكم.",
        )
    return factory(api_url=api_url, api_key=api_key, timeout_seconds=timeout_seconds)
```

## `integrations/providers/__init__.py`

```python
"""عملاء مزودي خدمات SMM."""

from integrations.providers.base import (
    ProviderBalance,
    ProviderClient,
    ProviderOrderResult,
    ProviderServiceItem,
    ProviderStatusResult,
)
from integrations.providers.mock import MockProviderClient
from integrations.providers.registry import (
    available_types,
    dev_types_enabled,
    enable_dev_types,
    create_client,
    is_supported,
    register_client,
)

__all__ = [
    "ProviderBalance",
    "ProviderClient",
    "ProviderOrderResult",
    "ProviderServiceItem",
    "ProviderStatusResult",
    "MockProviderClient",
    "available_types",
    "dev_types_enabled",
    "enable_dev_types",
    "create_client",
    "is_supported",
    "register_client",
]
```

## `middlewares/context.py`

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
    BUCKET_PRE,
    BUCKET_SENSITIVE,
    SENSITIVE_ADMIN_ACTIONS,
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
        if callback.namespace == NS_FLOW and callback.action in SENSITIVE_FLOW_ACTIONS:
            return True
        return callback.action in SENSITIVE_ADMIN_ACTIONS.get(callback.namespace, frozenset())
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

        # فحص معدل مسبق في الذاكرة **قبل** أي قراءة/كتابة في قاعدة البيانات: من يُغرق البوت بتحديثات
        # لا يستطيع إجبار `get_or_create` على الجري لكل تحديث (الدور غير معروف بعد ⇒ الحدّ الأعلى)
        if not await self._pre_check(update, context, services, telegram_user.id):
            raise ApplicationHandlerStop

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

    async def _pre_check(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, services: ServiceContainer, telegram_id: int
    ) -> bool:
        """
        فحص حد المعدل قبل قاعدة البيانات بالحد الأعلى بين حدّي العادي والأدمن.

        الدور الحقيقي يُطبَّق بدقة بعد تحميل المستخدم؛ هذا الفحص يقطع السيل فقط. المخالفة هنا تُسجَّل في
        `AbuseGuard` (فيُوقَف المُغرِق بصمت بلا قاعدة بيانات) مع تحذير مُهدَّأ بلا أي قراءة من القاعدة.

        المخرجات: True إن سُمح بالمتابعة.
        """
        user_limit = await services.settings.get_int("rate_limit_actions_per_minute", 30)
        staff_limit = await services.settings.get_int("rate_limit_admin_actions_per_minute", 120)
        if self.limiter.hit(telegram_id, max(user_limit, staff_limit), bucket=BUCKET_PRE):
            return True
        strikes_limit = await services.settings.get_int("rate_limit_strikes_before_block", 5)
        block_minutes = await services.settings.get_int("rate_limit_block_minutes", 5)
        result = self.guard.record_violation(
            telegram_id, strikes_limit=strikes_limit, block_seconds=block_minutes * 60.0
        )
        logger.info("تجاوز المستخدم %s الحد المسبق (مخالفات: %s/%s)", telegram_id, result.strikes, strikes_limit)
        if result.blocked:
            message = ar.ERR_RATE_BLOCKED.format(minutes=block_minutes)
        elif result.warn:
            message = ar.ERR_RATE_LIMITED
        else:
            return False
        await answer_callback(update, message, alert=True)
        if update.callback_query is None:
            await send(update, context, message)
        return False

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

## `middlewares/rate_limit.py`

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

from keyboards.callback_data import NS_ADM_BKP, NS_ADM_STATS

#: طول النافذة الزمنية بالثواني
WINDOW_SECONDS: float = 60.0

#: أقصى عدد مفاتيح نحتفظ بسجلها قبل التنظيف الدوري
MAX_TRACKED_USERS: int = 10_000

#: السلة العامة والسلة الحسّاسة
BUCKET_GENERAL = "general"
BUCKET_SENSITIVE = "sensitive"

#: سلة الفحص المسبق (قبل قراءة المستخدم من القاعدة): حدّها الأعلى بين حدّي العادي والأدمن
BUCKET_PRE = "pre"

#: سقف إدخالات `AbuseGuard` في الذاكرة (يمنع تضخمها بسيل معرّفات مختلفة)
MAX_GUARD_ENTRIES: int = 10_000

#: نافذة احتساب المخالفات (ثانية): المخالفات الأقدم لا تُحتسب
STRIKE_WINDOW_SECONDS: float = 600.0

#: أقل فاصل بين تحذيرين متتاليين لنفس المستخدم (ثانية) — لا نغرقه بالتحذيرات
WARNING_COOLDOWN_SECONDS: float = 10.0

#: الإجراءات الحسّاسة داخل أزرار المحادثات (تأكيدات تنفّذ عملاً مالياً أو إنشائياً)
SENSITIVE_FLOW_ACTIONS: frozenset[str] = frozenset({"confirm"})

#: أزرار لوحة الأدمن الحسّاسة خارج المحادثات: (المساحة ← الإجراءات) — ثقيلة أو تخرج بيانات (م10)
SENSITIVE_ADMIN_ACTIONS: dict[str, frozenset[str]] = {
    NS_ADM_BKP: frozenset({"new", "chan", "dl", "vac"}),
    NS_ADM_STATS: frozenset({"exp"}),
}


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
        if len(self._strikes) >= MAX_GUARD_ENTRIES:
            self._prune(now)
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

    def _prune(self, now: float) -> None:
        """
        تقليص ذاكرة الحارس: إسقاط المخالفات المنتهية والإيقافات المنقضية والتحذيرات القديمة.

        إن بقي العدد فوق السقف بعد ذلك (سيل معرّفات نشطة) أُسقطت أقدم السجلات غير الموقوفة؛ **الموقوفون لا
        يُسقَطون أبداً** حتى لا يُرفع إيقاف مُغرِق بإغراقه بمعرّفات أخرى.
        """
        window = now - STRIKE_WINDOW_SECONDS
        for telegram_id in [tid for tid, until in self._blocked_until.items() if until <= now]:
            self._blocked_until.pop(telegram_id, None)
        for telegram_id in [
            tid for tid, strikes in self._strikes.items()
            if tid not in self._blocked_until and (not strikes or strikes[-1] < window)
        ]:
            self._strikes.pop(telegram_id, None)
        for telegram_id in [tid for tid, last in self._last_warning.items() if now - last >= WARNING_COOLDOWN_SECONDS]:
            self._last_warning.pop(telegram_id, None)

        overflow = len(self._strikes) - MAX_GUARD_ENTRIES + 1
        if overflow > 0:
            removable = sorted(
                (tid for tid in self._strikes if tid not in self._blocked_until),
                key=lambda tid: self._strikes[tid][-1] if self._strikes[tid] else 0.0,
            )
            for telegram_id in removable[:overflow]:
                self._strikes.pop(telegram_id, None)
                self._last_warning.pop(telegram_id, None)

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

## `scripts/demo_cycle.py`

```python
"""
عرض حيّ للدورة الكاملة — المرحلة 2 (قبل بناء واجهة تيليجرام في المرحلة 3).

الغرض: أن ترى بعينك أن منطق العمل يعمل فعلاً من البداية للنهاية:
    تسجيل → تصفح → طلب → شحن → اعتماد → خصم → إرسال للمزود → متابعة آلية
    → إكمال → إشعار → سجل → إحصائيات
ثم المسار البديل: فشل المزود → استرجاع آمن → حركة مالية → إشعار المستخدم والأدمن.

⚠️ تنبيهات مهمة حتى لا يُفهم هذا العرض خطأً:
    • يعمل على قاعدة بيانات **مؤقتة منفصلة** (افتراضياً `data/demo_cycle.db`)
      تُحذف وتُعاد بناؤها عند كل تشغيل — لا يمس بيانات التشغيل إطلاقاً.
    • المزود هنا هو `MockProviderClient` (مزود وهمي محلي): **لا اتصال بأي شبكة
      ولا إنفاق أي مال حقيقي**. الأرقام أدناه حقيقية داخل قاعدة البيانات المؤقتة فقط.
    • الرسائل التي تُطبع بوصفها «إشعارات» هي ما كان البوت سيرسله لتيليجرام فعلاً،
      وهي مقروءة من جدول `notifications` لا مكتوبة يدوياً.

طريقة التشغيل (من داخل مجلد المشروع smm_bot):
    python -m scripts.demo_cycle
    python -m scripts.demo_cycle --keep     # إبقاء قاعدة البيانات المؤقتة بعد الانتهاء
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:                      # تشغيل مباشر بلا تثبيت الحزمة
    sys.path.insert(0, str(ROOT))

from core.enums import OrderStatus                                  # noqa: E402
from core.exceptions import InsufficientBalanceError                # noqa: E402
from core.exceptions import ProviderPermanentError                  # noqa: E402
from core.money import format_units                                 # noqa: E402
from database.database import Database                              # noqa: E402
from database.migrator import Migrator                              # noqa: E402
from database.repositories import Repositories                      # noqa: E402
from integrations.providers import registry                         # noqa: E402
from integrations.providers.mock import MockProviderClient          # noqa: E402
from services import ServiceContainer, build_services               # noqa: E402
from utils.datetime_utils import iso_plus_seconds                   # noqa: E402
from utils.logging_setup import setup_logging                       # noqa: E402
from utils.security import SecretBox, generate_encryption_key       # noqa: E402

LINE = "─" * 62


def step(number: str, title: str) -> None:
    """طباعة عنوان خطوة من الدورة."""
    print(f"\n{LINE}\n▶ {number}  {title}\n{LINE}")


def info(label: str, value: object) -> None:
    """طباعة سطر معلومة بمحاذاة ثابتة."""
    print(f"   • {label:<28} {value}")


def money(units: int) -> str:
    """عرض مبلغ بالنقاط الصحيحة بصيغة قابلة للقراءة."""
    return format_units(units, decimals=2)


class ConsoleSender:
    """بديل واجهة تيليجرام: يطبع الرسائل بدل إرسالها (لا شبكة في هذا العرض)."""

    def __init__(self, names: dict[int, str]) -> None:
        """تهيئة المرسل بخريطة معرفات تيليجرام إلى أسماء للعرض."""
        self.names = names
        self.count = 0

    async def __call__(self, telegram_id: int, title: str, message: str) -> int:
        """طباعة الرسالة كما كانت ستصل للمستخدم في تيليجرام."""
        self.count += 1
        who = self.names.get(telegram_id, str(telegram_id))
        first_line = message.strip().splitlines()[0] if message.strip() else ""
        print(f"   📨 إلى {who}: {title} — {first_line}")
        return self.count


async def build_environment(db_path: Path) -> tuple[Database, Repositories, ServiceContainer, dict]:
    """
    تجهيز قاعدة بيانات مؤقتة كاملة: ترحيلات + أدمن + مزود وهمي + خدمة + طريقة دفع.

    المخرجات: (قاعدة البيانات، المستودعات، حاوية الخدمات، قاموس الكائنات المُنشأة).
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    db = Database(db_path, read_pool_size=2)
    await db.connect()
    applied = await Migrator(db).apply_all()
    repos = Repositories(db)
    secret_box = SecretBox(generate_encryption_key())          # مفتاح مؤقت لهذا التشغيل فقط
    services = build_services(db, repos, secret_box=secret_box, settings_ttl_seconds=0)

    async with db.transaction() as tx:
        admin = await repos.users.create(
            tx, telegram_id=900900900, username="demo_admin", first_name="أدمن العرض",
            role="super_admin",
        )
        provider = await repos.providers.create(
            tx,
            currency="YER",   # عملة النظام الافتراضية: لا تحويل مطلوب
            name="MockPanel",
            api_url="https://mock.invalid/api/v2",
            api_key_enc=secret_box.encrypt("demo-key-1234567890"),
            api_key_hint="7890",
            api_type="mock",
        )
        categories = await repos.categories.list_all()
        service = await repos.services.create(
            tx,
            category_id=categories[0].id,
            provider_id=provider.id,
            provider_service_id="555",
            name="متابعين انستغرام (عرض تجريبي)",
            price_per_1000_units=10_000,          # 1.00 لكل ألف
            provider_price_per_1000_units=6_000,  # تكلفتنا من المزود
            min_quantity=100,
            max_quantity=100_000,
        )
        method = await repos.payment_methods.create(
            tx, code="demo_transfer", name_ar="حوالة بنكية (عرض)",
            instructions_ar="حوّل ثم أرسل رقم العملية",
        )

    info("ملف قاعدة البيانات", db_path)
    info("ترحيلات مطبَّقة", len(applied))
    info("أدمن العرض", f"{admin.display_name} (tg={admin.telegram_id})")
    info("المزود", f"{provider.name} — نوع {provider.api_type} — مفتاح ****{provider.api_key_hint}")
    info("الخدمة", f"{service.name} بسعر {money(service.price_per_1000_units)} لكل 1000")
    info("طريقة الدفع", method.name_ar)
    return db, repos, services, {"admin": admin, "provider": provider, "service": service, "method": method}


async def follow_until_final(services: ServiceContainer, repos: Repositories, order_id: int) -> None:
    """تشغيل حلقة المتابعة الآلية (كما يفعل JobQueue) حتى تستقر حالة الطلب."""
    for round_number in range(1, 9):
        order = await repos.orders.get(order_id)
        if order is None or order.status in {
            OrderStatus.COMPLETED, OrderStatus.PARTIAL, OrderStatus.REFUNDED, OrderStatus.CANCELED
        }:
            return
        async with repos.db.transaction() as tx:      # تقديم موعد الفحص بدل الانتظار الحقيقي
            await repos.orders.update_fields(tx, order_id, next_check_at=iso_plus_seconds(-5))
        report = await services.orders.process_due_orders()
        current = await repos.orders.get(order_id)
        assert current is not None
        info(
            f"دورة متابعة {round_number}",
            f"الحالة: {current.status} | منفَّذ: {current.delivered_quantity or 0}"
            f" | متبقٍ: {current.remains if current.remains is not None else '—'}"
            f" | فحوصات: {report.claimed}",
        )


async def happy_path(services: ServiceContainer, repos: Repositories, env: dict) -> None:
    """تنفيذ الدورة الكاملة الناجحة وطباعة كل خطوة."""
    admin, service, method = env["admin"], env["service"], env["method"]
    sender = ConsoleSender({admin.telegram_id: "الأدمن"})

    step("1/11", "التسجيل — أول تفاعل مع البوت")
    customer, created = await services.users.get_or_create(
        telegram_id=111222333, username="demo_client", first_name="عميل العرض"
    )
    sender.names[customer.telegram_id] = "العميل"
    info("الحساب", f"{customer.display_name} (tg={customer.telegram_id})")
    info("أُنشئ الآن؟", "نعم" if created else "كان موجوداً")
    info("الرصيد الابتدائي", money(customer.balance_units))

    step("2/11", "التصفح — التصنيفات والخدمات والتسعيرة")
    categories = await services.catalog.categories()
    info("تصنيفات بها خدمات", ", ".join(category.name_ar for category in categories))
    page = await services.catalog.services_page(categories[0].id)
    info("خدمات الصفحة الأولى", f"{page.total_items} خدمة")
    chosen = await services.catalog.get_available_service(service.id)
    quote = await services.catalog.quote(chosen, 1000)
    info("التسعيرة لـ1000 وحدة", quote.cost_text)

    step("3/11", "محاولة الطلب بلا رصيد — يجب أن تُرفض بلا أي أثر")
    try:
        await services.orders.create_order(
            customer, service_id=chosen.id, link="https://instagram.com/p/demo", quantity=1000
        )
    except InsufficientBalanceError as exc:
        info("الرفض المتوقع", exc.user_message)
    info("عدد طلبات العميل", await repos.orders.count_by_user(customer.id))

    step("4/11", "الشحن — العميل يرسل إثبات التحويل")
    payment = await services.payments.create_payment(
        customer, method_id=method.id, raw_amount="5",
        transaction_reference="DEMO-TRX-001", proof_file_id="demo-photo", proof_file_type="photo",
    )
    info("رقم طلب الشحن", payment.id)
    info("المبلغ المطلوب", money(payment.amount_units))
    info("الحالة", payment.status)
    info("الرصيد الآن", money(await services.wallet.balance_units(customer.id)))

    step("5/11", "الاعتماد — الأدمن يراجع ويعتمد")
    pending = await services.payments.pending(admin)
    info("طلبات بانتظار المراجعة", len(pending))
    transaction = await services.payments.approve(admin, payment.id)
    info("نوع الحركة المالية", transaction.type)
    info("مرجع الحركة", transaction.reference)
    info("الرصيد بعد الاعتماد", money(await services.wallet.balance_units(customer.id)))

    step("6/11", "الطلب — الخصم يتم داخل نفس معاملة الإنشاء")
    order = await services.orders.create_order(
        customer, service_id=chosen.id, link="https://instagram.com/p/demo", quantity=1000
    )
    info("رقم الطلب", order.public_code)
    info("التكلفة المخصومة", money(order.cost_units))
    info("الحالة", order.status)
    info("الرصيد بعد الخصم", money(await services.wallet.balance_units(customer.id)))

    step("7/11", "الإرسال للمزود — مهمة الخلفية تلتقط الطلب")
    batch = await services.orders.process_pending_orders()
    info("طلبات التُقطت", batch.claimed)
    info("أُرسلت بنجاح", batch.succeeded)
    submitted = await repos.orders.get(order.id)
    assert submitted is not None
    info("رقم الطلب لدى المزود", submitted.provider_order_id)
    info("تكلفتنا من المزود", money(submitted.provider_cost_units or 0))

    step("8/11", "المتابعة الآلية حتى الإكمال")
    await follow_until_final(services, repos, order.id)
    final = await repos.orders.get(order.id)
    assert final is not None
    info("الحالة النهائية", final.status)
    info("الكمية المنفَّذة", final.delivered_quantity)

    step("9/11", "الإشعارات — ما كان سيصل إلى تيليجرام")
    report = await services.notifications.dispatch_pending(sender, limit=50)
    info("أُرسل", report.sent)
    info("تخطّي (حظر البوت)", report.skipped)
    info("المتبقي في الطابور", await services.notifications.queued_count())

    step("10/11", "السجلات — حركات مالية وتدقيق وتاريخ حالات")
    for movement in await repos.transactions.list_by_user(customer.id, limit=5):
        info(movement.type, f"{money(movement.amount_units)} | الرصيد بعدها {money(movement.balance_after_units)}")
    ledger = await services.wallet.verify_ledger(customer.id)
    info("مطابقة الرصيد مع الدفتر", "متوازن ✅" if ledger.is_balanced else "اختلال ❌")
    history = await repos.orders.history(order.id)
    info("مسار حالات الطلب", " ← ".join(row.to_status for row in history))
    logs = await services.audit.by_target("payment", payment.id)
    info("سجل التدقيق للاعتماد", ", ".join(f"{log.action} بواسطة {log.admin_id}" for log in logs))

    step("11/11", "الإحصائيات — أرقام مقروءة من قاعدة البيانات")
    dashboard = await services.stats.dashboard(admin)
    info("طلبات اليوم", dashboard.orders_today)
    info("مبيعات اليوم", money(dashboard.revenue_today_units))
    financial = await services.stats.financial_report(admin, days=1)
    info("إيداعات", money(financial.deposits_units))
    info("مبيعات", money(financial.revenue_units))
    info("تكلفة المزود", money(financial.provider_cost_units))
    info("الربح", money(financial.profit_units) if financial.profit_known else "غير محسوب")
    operations = await services.stats.operations_report(admin, days=1)
    info("نسبة النجاح", f"{operations.success_rate}%")

    env["customer"] = customer
    env["sender"] = sender


async def failure_path(services: ServiceContainer, repos: Repositories, env: dict, client: MockProviderClient) -> None:
    """تنفيذ المسار البديل: رفض المزود للطلب ثم الاسترجاع الآمن."""
    customer, sender = env["customer"], env["sender"]
    service = env["service"]

    step("بديل 1/4", "طلب جديد — لكن المزود سيرفضه هذه المرة")
    await services.settings.set("duplicate_order_window_minutes", 0)
    client.always_fail_add = ProviderPermanentError("الخدمة غير متاحة لدى المزود")
    before = await services.wallet.balance_units(customer.id)
    order = await services.orders.create_order(
        customer, service_id=service.id, link="https://instagram.com/p/fail-demo", quantity=1000
    )
    info("رقم الطلب", order.public_code)
    info("الرصيد قبل", money(before))
    info("الرصيد بعد الخصم", money(await services.wallet.balance_units(customer.id)))

    step("بديل 2/4", "المزود يرفض — فشل + استرجاع كامل في معاملة واحدة")
    batch = await services.orders.process_pending_orders()
    info("فشل", batch.failed)
    failed = await repos.orders.get(order.id)
    assert failed is not None
    info("الحالة النهائية", failed.status)
    info("المبلغ المسترجَع", money(failed.refund_amount_units))
    info("سبب الفشل", failed.last_error)

    step("بديل 3/4", "الحركة المالية والرصيد")
    movements = await repos.transactions.list_by_user(customer.id, limit=2)
    for movement in movements:
        info(movement.type, f"{money(movement.amount_units)} | مرجع {movement.reference}")
    info("الرصيد بعد الاسترجاع", money(await services.wallet.balance_units(customer.id)))
    info("المال المفقود", money(before - await services.wallet.balance_units(customer.id)))
    ledger = await services.wallet.verify_ledger(customer.id)
    info("مطابقة الدفتر", "متوازن ✅" if ledger.is_balanced else "اختلال ❌")

    step("بديل 4/4", "إشعار العميل والأدمن + منع إعادة الإرسال")
    await services.notifications.dispatch_pending(sender, limit=50)
    again = await services.orders.process_pending_orders()
    info("محاولات إرسال جديدة للطلب الفاشل", again.claimed)
    errors = await repos.error_logs.list_recent(limit=3)
    info("أحدث خطأ مسجَّل", errors[0]["message"] if errors else "—")


async def run(keep: bool) -> int:
    """تشغيل العرض كاملاً وإرجاع كود الخروج."""
    db_path = ROOT / "data" / "demo_cycle.db"
    # السجلات إلى الملف فقط حتى لا تتداخل أسطر اللوق مع خطوات العرض
    setup_logging(ROOT / "logs" / "demo_cycle.log", "INFO", console=False)
    print("\n🧪 عرض الدورة الكاملة — المرحلة 2 (مزود وهمي، قاعدة بيانات مؤقتة، بلا شبكة)")
    shared_client = MockProviderClient()
    registry.enable_dev_types(True)                                    # العرض التجريبي وحده يسمح بالمزود الوهمي
    registry.register_client("mock", lambda **_kwargs: shared_client)   # عميل واحد يحتفظ بحالته

    db, repos, services, env = await build_environment(db_path)
    try:
        await happy_path(services, repos, env)
        await failure_path(services, repos, env, shared_client)
        print(f"\n{LINE}\n✅ انتهى العرض: الدورة الكاملة والمسار البديل نُفِّذا دون فقدان أي مبلغ.\n{LINE}")
    finally:
        await db.close()
        registry.register_client("mock", MockProviderClient)
        if not keep and db_path.exists():
            db_path.unlink()
            print(f"🧹 حُذفت قاعدة البيانات المؤقتة: {db_path}")
        elif keep:
            print(f"💾 أُبقيت قاعدة البيانات المؤقتة: {db_path}")
    return 0


def main() -> int:
    """نقطة الدخول: قراءة الخيارات ثم تشغيل العرض."""
    parser = argparse.ArgumentParser(description="عرض حيّ للدورة الكاملة (المرحلة 2)")
    parser.add_argument("--keep", action="store_true", help="إبقاء قاعدة البيانات المؤقتة بعد الانتهاء")
    args = parser.parse_args()
    return asyncio.run(run(args.keep))


if __name__ == "__main__":
    raise SystemExit(main())
```

## `tests/conftest.py`

```python
"""
تهيئة بيئة الاختبارات.

كل اختبار يحصل على قاعدة بيانات مؤقتة جديدة مع تطبيق كامل الترحيلات،
حتى تكون الاختبارات مستقلة تماماً عن بعضها وعن بيانات التشغيل الحقيقية.

تنظيم الاختبارات:
    tests/unit/        : منطق خالص بلا قاعدة بيانات (مال، حالات، تحقق، صلاحيات).
    tests/integration/ : خدمة واحدة مع قاعدة بيانات حقيقية (مؤقتة).
    tests/e2e/         : الدورة الكاملة عبر كل الخدمات معاً.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio

# إضافة جذر المشروع إلى مسار الاستيراد حتى تعمل الاستيرادات المطلقة
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.database import Database  # noqa: E402
from database.migrator import Migrator  # noqa: E402
from database.repositories import Repositories  # noqa: E402
from integrations.providers import registry  # noqa: E402
from integrations.providers.mock import MockProviderClient  # noqa: E402
from services import ServiceContainer, build_services  # noqa: E402
from texts import templates as templates_module  # noqa: E402
from utils import net_security  # noqa: E402
from utils.security import SecretBox, clear_registered_secrets, generate_encryption_key  # noqa: E402


@pytest.fixture(autouse=True)
def _enable_dev_provider_types():
    """الاختبارات تستعمل المزود الوهمي: نفعّل أنواع التطوير ونعيد الحالة بعد كل اختبار (الإنتاج: معطّلة)."""
    previous = registry.dev_types_enabled()
    registry.enable_dev_types(True)
    yield
    registry.enable_dev_types(previous)


@pytest.fixture(autouse=True)
def _reset_template_overrides():
    """
    تصفير قوالب الإشعارات المخصّصة قبل وبعد كل اختبار (المرحلة 8).

    ذاكرة القوالب عامة على مستوى الوحدة، فبدون هذا التصفير يتسرّب قالب
    عدّله اختبارٌ ما إلى اختبار آخر فيفشل لسبب لا علاقة له به.
    """
    templates_module.clear_overrides()
    yield
    templates_module.clear_overrides()


@pytest.fixture(autouse=True)
def _reset_security_globals():
    """
    تصفير الحالة الأمنية العامة قبل وبعد كل اختبار (المرحلة 9).

    الأسرار المسجَّلة وذاكرة نتائج DNS عامتان على مستوى الوحدة؛ تركهما يتسرّب
    بين الاختبارات يخفي أخطاء (قيمة تُحذف من نص اختبار آخر دون سبب ظاهر).
    """
    clear_registered_secrets()
    net_security.clear_dns_cache()
    yield
    clear_registered_secrets()
    net_security.clear_dns_cache()


@pytest_asyncio.fixture
async def db(tmp_path: Path):
    """قاعدة بيانات مؤقتة مع تطبيق كل الترحيلات."""
    database = Database(tmp_path / "test.db", read_pool_size=2)
    await database.connect()
    await Migrator(database).apply_all()
    try:
        yield database
    finally:
        await database.close()


@pytest_asyncio.fixture
async def repos(db: Database) -> Repositories:
    """حاوية المستودعات على قاعدة بيانات الاختبار."""
    return Repositories(db)


@pytest.fixture
def secret_box() -> SecretBox:
    """صندوق تشفير بمفتاح مؤقت يُولَّد لكل اختبار (لا مفاتيح ثابتة في الكود)."""
    return SecretBox(generate_encryption_key())


@pytest_asyncio.fixture
async def services(db: Database, repos: Repositories, secret_box: SecretBox) -> ServiceContainer:
    """
    حاوية الخدمات كاملة الربط.

    `settings_ttl_seconds=0` يلغي كاش الإعدادات حتى يرى الاختبار أي تعديل فوراً.
    """
    return build_services(db, repos, secret_box=secret_box, settings_ttl_seconds=0)


@pytest_asyncio.fixture
async def user(db: Database, repos: Repositories):
    """مستخدم اختباري جاهز برصيد صفر."""
    async with db.transaction() as tx:
        return await repos.users.create(
            tx, telegram_id=100200300, username="tester", first_name="Tester"
        )


@pytest_asyncio.fixture
async def admin(db: Database, repos: Repositories):
    """مستخدم بدور admin (الصلاحيات تأتي من جدول الأدوار المزروع في الترحيل 0002)."""
    async with db.transaction() as tx:
        return await repos.users.create(
            tx, telegram_id=900900900, username="bossadmin", first_name="Admin", role="admin"
        )


@pytest_asyncio.fixture
async def super_admin(db: Database, repos: Repositories):
    """مستخدم بدور super_admin (يملك كل الصلاحيات)."""
    async with db.transaction() as tx:
        return await repos.users.create(
            tx, telegram_id=777777777, username="root", first_name="Root", role="super_admin"
        )


@pytest_asyncio.fixture
async def provider(db: Database, repos: Repositories):
    """مزود اختباري (المفتاح هنا نص وهمي مشفَّر شكلياً — لا يُستخدم للاتصال)."""
    async with db.transaction() as tx:
        return await repos.providers.create(
            tx,
            currency="YER",   # عملة النظام الافتراضية: لا تحويل مطلوب
            name="TestProvider",
            api_url="https://example.invalid/api/v2",
            api_key_enc="ENC::dummy-not-a-real-key",
            api_key_hint="1234",
        )


@pytest.fixture
def mock_client() -> MockProviderClient:
    """
    عميل مزود وهمي **مشترك**: يُعاد نفس الكائن لكل استدعاء داخل الاختبار.

    السبب: `ProviderService.client_for` يبني عميلاً جديداً في كل عملية، بينما يحتاج
    المزود الوهمي الاحتفاظ بحالة الطلبات بين الإرسال وفحص الحالة.
    """
    shared = MockProviderClient()
    registry.register_client("mock", lambda **_kwargs: shared)
    try:
        yield shared
    finally:
        registry.register_client("mock", MockProviderClient)  # إعادة السجل كما كان


@pytest_asyncio.fixture
async def mock_provider(db: Database, repos: Repositories, secret_box: SecretBox):
    """مزود من نوع mock بمفتاح مشفَّر فعلياً (يُفك عند الاتصال)."""
    async with db.transaction() as tx:
        return await repos.providers.create(
            tx,
            currency="YER",   # عملة النظام الافتراضية: لا تحويل مطلوب
            name="MockProvider",
            api_url="https://mock.invalid/api/v2",
            api_key_enc=secret_box.encrypt("mock-key-123456"),
            api_key_hint="3456",
            api_type="mock",
        )


@pytest_asyncio.fixture
async def service(db: Database, repos: Repositories, provider):
    """خدمة اختبارية بسعر 1.0000 لكل ألف (10000 نقطة)."""
    categories = await repos.categories.list_all()
    async with db.transaction() as tx:
        return await repos.services.create(
            tx,
            category_id=categories[0].id,
            provider_id=provider.id,
            provider_service_id="555",
            name="متابعين انستغرام اختبار",
            price_per_1000_units=10_000,
            provider_price_per_1000_units=6_000,
            min_quantity=100,
            max_quantity=10_000,
        )


@pytest_asyncio.fixture
async def mock_service(db: Database, repos: Repositories, mock_provider):
    """خدمة مرتبطة بالمزود الوهمي (تُستخدم في اختبارات الدورة الكاملة)."""
    categories = await repos.categories.list_all()
    async with db.transaction() as tx:
        return await repos.services.create(
            tx,
            category_id=categories[0].id,
            provider_id=mock_provider.id,
            provider_service_id="555",
            name="متابعين انستغرام (Mock)",
            price_per_1000_units=10_000,     # 1.0000 لكل ألف ⇒ طلب 1000 يكلف 10000 نقطة
            provider_price_per_1000_units=6_000,
            min_quantity=100,
            max_quantity=100_000,
        )


@pytest_asyncio.fixture
async def payment_method(db: Database, repos: Repositories):
    """طريقة دفع يدوية للاختبار."""
    async with db.transaction() as tx:
        return await repos.payment_methods.create(
            tx, code="test_wallet", name_ar="محفظة اختبار", instructions_ar="حوّل ثم أرسل الإثبات"
        )


@pytest.fixture
def anyio_backend() -> str:
    """تثبيت backend الخاص بالاختبارات غير المتزامنة."""
    return "asyncio"
```

## `tests/integration/test_submission_safety_phase12_1.py`

```python
"""
المرحلة 12.1 (تقوية) — سلامة إرسال الطلبات للمزود وسياسات الأدمن:

    P0-1  `submitting` لا يعلق للأبد: إلغاء الجولة/انهيار/انتهاء القفل ⇒ `submit_uncertain` + تنبيه، بلا إعادة إرسال.
    P0-2  نجاح المزود ثم فشل القاعدة لا يُنتج طلباً مزدوجاً: إعادة محاولة الحفظ ثم «غير مؤكد» مع رقم المزود.
    P0-3/4 الأدمن لا يسترجع/يُغلق/يتجاوز طلباً قيد الإرسال، و«تعليم كفاشل» لا يشمل الطلبات المُرسلة.
    + ثغرة وجدناها: طلب فاشل بلا استرجاع (تعطيل التلقائي) لم يكن له أي مسار استرجاع.
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

from core.enums import OrderStatus, TransactionType
from core.exceptions import InvalidStateTransitionError, ProviderPermanentError
from core.order_state import override_targets
from database.models import Service, User
from services import ServiceContainer
from services.order_service import OrderService
from utils.datetime_utils import iso_plus_seconds

pytestmark = pytest.mark.asyncio

COST = 10_000


async def _fund(services, user, admin, amount=100_000) -> None:
    """شحن رصيد اختباري عبر المسار الرسمي."""
    await services.wallet.adjust_balance(target=user, amount_units=amount, admin=admin, reason="رصيد اختبار", credit=True)


async def _order(services, user, service, n: int = 1):
    """إنشاء طلب بروابط مختلفة (لتفادي فحص التكرار)."""
    return await services.orders.create_order(
        user, service_id=service.id, link=f"https://instagram.com/safety{n}", quantity=1000
    )


async def _status(repos, order_id: int):
    """قراءة الطلب الحالي."""
    order = await repos.orders.get(order_id)
    assert order is not None
    return order


def _hang_after_accept(mock_client, seconds: float = 30.0) -> None:
    """مزود يقبل الطلب فعلاً ثم «يضيع الرد» (يتأخر طويلاً) — أخطر سيناريو مهلة."""
    original = mock_client.add_order

    async def slow(**kwargs):
        result = await original(**kwargs)
        await asyncio.sleep(seconds)
        return result

    mock_client.add_order = slow


# ----------------------------- P0-1: submitting لا يعلق ----------------------------- #


async def test_job_timeout_marks_in_flight_order_uncertain_and_requeues_the_rest(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service, mock_client
) -> None:
    """إلغاء جولة الإرسال (مهلة المهمة) أثناء انتظار المزود: الطلب الجاري «غير مؤكد»، وغير المبدوء يعود pending."""
    await _fund(services, user, admin)
    first = await _order(services, user, mock_service, 1)
    second = await _order(services, user, mock_service, 2)
    _hang_after_accept(mock_client)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(services.orders.process_pending_orders(limit=5), timeout=0.3)

    assert (await _status(repos, first.id)).status == OrderStatus.SUBMIT_UNCERTAIN
    assert (await _status(repos, second.id)).status == OrderStatus.PENDING, "طلب لم يُرسل شيء منه يجب أن يعود للانتظار"
    assert len(mock_client.orders) == 1, "المزود استلم الطلب الأول فقط"

    # لا إعادة إرسال تلقائية للطلب غير المؤكد، والثاني يُرسل لاحقاً مرة واحدة
    mock_client.add_order = type(mock_client).add_order.__get__(mock_client)
    async with repos.db.transaction() as tx:
        await repos.orders.update_fields(tx, second.id, next_check_at=iso_plus_seconds(-5))
    await services.orders.process_pending_orders(limit=5)
    assert (await _status(repos, first.id)).status == OrderStatus.SUBMIT_UNCERTAIN
    assert len(mock_client.orders) == 2
    assert (await services.wallet.balance_units(user.id)) == 100_000 - 2 * COST, "لا استرجاع تلقائي لغير المؤكد"


async def test_unexpected_exception_during_submit_becomes_uncertain(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service, mock_client
) -> None:
    """استثناء غير متوقع (ليس من المزود) أثناء الإرسال ⇒ غير مؤكد بدل البقاء submitting."""
    await _fund(services, user, admin)
    order = await _order(services, user, mock_service)
    mock_client.always_fail_add = RuntimeError("انهيار غير متوقع")
    report = await services.orders.process_pending_orders()
    assert report.uncertain == 1
    assert (await _status(repos, order.id)).status == OrderStatus.SUBMIT_UNCERTAIN
    logged = await repos.db.fetchall("SELECT message FROM error_logs WHERE error_type = 'ProviderUncertainError'")
    assert len(logged) == 1 and "RuntimeError" in str(logged[0]["message"])


async def test_periodic_recovery_moves_expired_submitting_to_uncertain(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service, mock_client
) -> None:
    """طلب علق في submitting وانتهى قفله ⇒ الاسترداد الدوري يجعله غير مؤكد وينبّه، ولا يمسّ ما قفله ساري."""
    await _fund(services, user, admin)
    stale = await _order(services, user, mock_service, 1)
    live = await _order(services, user, mock_service, 2)
    async with repos.db.transaction() as tx:
        claimed = await repos.orders.claim_pending_for_submit(tx, worker="w", limit=5, lock_seconds=120)
        assert {o.id for o in claimed} == {stale.id, live.id}
        await repos.orders.update_fields(tx, stale.id, locked_until=iso_plus_seconds(-10))

    assert await services.orders.recover_stale_submissions() == 1
    assert (await _status(repos, stale.id)).status == OrderStatus.SUBMIT_UNCERTAIN
    assert (await _status(repos, live.id)).status == OrderStatus.SUBMITTING, "قفل ساري ⇒ عامل حيّ يرسله"
    assert await services.orders.recover_stale_submissions() == 0, "الاسترداد idempotent"

    history = await repos.orders.history(stale.id)
    assert history[-1].to_status == OrderStatus.SUBMIT_UNCERTAIN
    errors = await repos.db.fetchall("SELECT error_type FROM error_logs WHERE error_type = 'SubmitStalled'")
    assert len(errors) == 1
    # لا يُعاد التقاطه للإرسال
    assert (await services.orders.process_pending_orders()).claimed == 0
    assert len(mock_client.orders) == 0


async def test_submit_job_runs_recovery_first(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service
) -> None:
    """مهمة `orders_submit` الدورية تستدعي الاسترداد قبل الحجز."""
    from jobs.order_jobs import submit_pending_orders

    await _fund(services, user, admin)
    order = await _order(services, user, mock_service)
    async with repos.db.transaction() as tx:
        await repos.orders.claim_pending_for_submit(tx, worker="w", limit=5, lock_seconds=120)
        await repos.orders.update_fields(tx, order.id, locked_until=iso_plus_seconds(-1))

    class _App:
        bot_data = {"services": services}

    class _Ctx:
        application = _App()

    await submit_pending_orders(_Ctx())
    assert (await _status(repos, order.id)).status == OrderStatus.SUBMIT_UNCERTAIN


async def test_lock_is_renewed_before_each_submit(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service
) -> None:
    """الطلب الأخير في دفعة طويلة لا يُعدّ عالقاً: القفل يُمدَّد قبل إرساله."""
    await _fund(services, user, admin)
    order = await _order(services, user, mock_service)
    async with repos.db.transaction() as tx:
        claimed = await repos.orders.claim_pending_for_submit(tx, worker="w1", limit=1, lock_seconds=1)
        await repos.orders.update_fields(tx, order.id, locked_until=iso_plus_seconds(-1))
    async with repos.db.transaction() as tx:
        assert await repos.orders.renew_submit_lock(tx, order.id, worker="w1", lock_seconds=100)
        assert not await repos.orders.renew_submit_lock(tx, order.id, worker="other", lock_seconds=100)
    assert (await _status(repos, order.id)).locked_until > iso_plus_seconds(50)
    assert claimed


# ------------------- P0-2: نجاح المزود ثم فشل القاعدة (لا طلب مزدوج) ------------------- #


def _fail_submitted_update(monkeypatch, repos, *, times: int) -> dict[str, int]:
    """يجعل تحديث الطلب إلى submitted يفشل `times` مرة (خطأ SQLite) ثم يعمل."""
    original = repos.orders.update_status
    state = {"calls": 0}

    async def flaky(tx, order_id, *, new_status, expected_statuses, extra_fields=None):
        if new_status == OrderStatus.SUBMITTED and state["calls"] < times:
            state["calls"] += 1
            raise sqlite3.OperationalError("database is locked")
        return await original(tx, order_id, new_status=new_status, expected_statuses=expected_statuses, extra_fields=extra_fields)

    monkeypatch.setattr(repos.orders, "update_status", flaky)
    return state


async def test_db_failure_after_provider_success_never_resubmits(
    services: ServiceContainer, repos, user: User, admin: User, super_admin: User, mock_service: Service, mock_client,
    monkeypatch, caplog,
) -> None:
    """المزود قبل الطلب ثم فشل الحفظ دائماً ⇒ غير مؤكد + رقم المزود في التنبيه واللوق، وطلب واحد فقط عند المزود."""
    monkeypatch.setattr(OrderService, "PERSIST_RETRY_DELAYS", (0.0, 0.0, 0.0))
    await _fund(services, user, admin)
    order = await _order(services, user, mock_service)
    state = _fail_submitted_update(monkeypatch, repos, times=99)

    with caplog.at_level("CRITICAL"):
        report = await services.orders.process_pending_orders()
    assert report.uncertain == 1 and state["calls"] == 3
    current = await _status(repos, order.id)
    assert current.status == OrderStatus.SUBMIT_UNCERTAIN and current.provider_order_id is None
    provider_id = next(iter(mock_client.orders))
    assert provider_id in (current.last_error or ""), "رقم المزود يجب أن يظهر ليُربط يدوياً"
    assert provider_id in caplog.text

    # لا إعادة إرسال مهما تكررت الجولات
    for _ in range(3):
        await services.orders.recover_stale_submissions()
        await services.orders.process_pending_orders()
    assert len(mock_client.orders) == 1

    # الأدمن الأعلى يربط الرقم ⇒ الدورة تكتمل
    monkeypatch.undo()
    assert await services.orders.admin_link_provider_order(super_admin, order.id, provider_id)
    assert (await _status(repos, order.id)).status == OrderStatus.SUBMITTED


async def test_transient_db_failure_is_retried_and_order_is_submitted(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service, mock_client, monkeypatch
) -> None:
    """فشل حفظ مؤقت (محاولتان) ثم نجاح ⇒ submitted بلا تدخل بشري وبطلب واحد عند المزود."""
    monkeypatch.setattr(OrderService, "PERSIST_RETRY_DELAYS", (0.0, 0.0, 0.0))
    await _fund(services, user, admin)
    order = await _order(services, user, mock_service)
    state = _fail_submitted_update(monkeypatch, repos, times=2)

    report = await services.orders.process_pending_orders()
    assert report.succeeded == 1 and state["calls"] == 2
    current = await _status(repos, order.id)
    assert current.status == OrderStatus.SUBMITTED and current.provider_order_id in mock_client.orders
    assert len(mock_client.orders) == 1


# ---------------------- P0-3/4: سياسات الأدمن أثناء الإرسال ---------------------- #


async def _claim(repos, order_id: int) -> None:
    """وضع الطلب في submitting كأن عاملاً حجزه الآن (قفل ساري)."""
    async with repos.db.transaction() as tx:
        claimed = await repos.orders.claim_pending_for_submit(tx, worker="w", limit=10, lock_seconds=120)
    assert order_id in {o.id for o in claimed}


async def test_admin_cannot_cancel_or_fail_or_override_in_flight_order(
    services: ServiceContainer, repos, user: User, admin: User, super_admin: User, mock_service: Service
) -> None:
    """طلب قيد الإرسال الآن: لا إلغاء ولا تعليم كفاشل ولا تجاوز، ولا يتحرك أي مبلغ."""
    await _fund(services, user, admin)
    order = await _order(services, user, mock_service)
    await _claim(repos, order.id)
    balance = await services.wallet.balance_units(user.id)

    with pytest.raises(InvalidStateTransitionError):
        await services.orders.admin_cancel(admin, order.id, "إلغاء أثناء الإرسال")
    with pytest.raises(InvalidStateTransitionError):
        await services.orders.admin_mark_failed(admin, order.id, "فشل أثناء الإرسال")
    with pytest.raises(InvalidStateTransitionError):
        await services.orders.admin_override_status(super_admin, order.id, OrderStatus.FAILED, "تجاوز أثناء الإرسال")

    assert (await _status(repos, order.id)).status == OrderStatus.SUBMITTING
    assert await services.wallet.balance_units(user.id) == balance


async def test_mark_failed_only_for_orders_that_did_not_reach_provider(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service, mock_client
) -> None:
    """«تعليم كفاشل + استرجاع» مرفوض لطلب عند المزود (submitted)، ومسموح لـpending."""
    await _fund(services, user, admin)
    sent = await _order(services, user, mock_service, 1)
    await services.orders.process_pending_orders()
    assert (await _status(repos, sent.id)).status == OrderStatus.SUBMITTED
    balance = await services.wallet.balance_units(user.id)
    with pytest.raises(InvalidStateTransitionError):
        await services.orders.admin_mark_failed(admin, sent.id, "محاولة تعليم طلب مُرسَل")
    assert await services.wallet.balance_units(user.id) == balance

    waiting = await _order(services, user, mock_service, 2)
    assert await services.orders.admin_mark_failed(admin, waiting.id, "الرابط خاطئ والطلب لم يُرسل") == COST


async def test_override_follows_state_machine_and_money_policy(
    services: ServiceContainer, repos, user: User, admin: User, super_admin: User, mock_service: Service, mock_client
) -> None:
    """التجاوز: لا قفز في آلة الحالات، لا حالات إرسال/مال، ولا حالة تتطلب رقم مزود بلا رقم."""
    await _fund(services, user, admin)
    pending = await _order(services, user, mock_service, 1)
    for target in (OrderStatus.COMPLETED, OrderStatus.PENDING, OrderStatus.CANCELED, OrderStatus.REFUNDED, OrderStatus.SUBMITTING):
        with pytest.raises(InvalidStateTransitionError):
            await services.orders.admin_override_status(super_admin, pending.id, target, "محاولة تجاوز ممنوعة")
    assert (await _status(repos, pending.id)).status == OrderStatus.PENDING

    mock_client.always_fail_add = None
    await services.orders.process_pending_orders()
    sent = await _status(repos, pending.id)
    assert sent.status == OrderStatus.SUBMITTED
    for target in (OrderStatus.CANCELED, OrderStatus.REFUNDED, OrderStatus.PENDING):
        with pytest.raises(InvalidStateTransitionError):
            await services.orders.admin_override_status(super_admin, sent.id, target, "محاولة تجاوز ممنوعة")
    assert await services.orders.admin_override_status(super_admin, sent.id, OrderStatus.COMPLETED, "أكّد المزود الاكتمال يدوياً")
    assert (await _status(repos, sent.id)).status == OrderStatus.COMPLETED


async def test_override_blocked_from_uncertain_state(
    services: ServiceContainer, repos, user: User, admin: User, super_admin: User, mock_service: Service, mock_client
) -> None:
    """غير مؤكد: مساره «ربط الرقم» أو «تعليم كفاشل» فقط."""
    await _fund(services, user, admin)
    order = await _order(services, user, mock_service)
    mock_client.always_fail_add = RuntimeError("x")
    await services.orders.process_pending_orders()
    assert (await _status(repos, order.id)).status == OrderStatus.SUBMIT_UNCERTAIN
    for target in (OrderStatus.SUBMITTED, OrderStatus.FAILED):
        with pytest.raises(InvalidStateTransitionError):
            await services.orders.admin_override_status(super_admin, order.id, target, "تجاوز غير مسموح هنا")


def test_override_targets_pure_function() -> None:
    """منطق الأزرار: ما يُعرض للأدمن = آلة الحالات ∩ السياسة."""
    assert override_targets(OrderStatus.SUBMITTING, has_provider_id=False) == []
    assert override_targets(OrderStatus.SUBMIT_UNCERTAIN, has_provider_id=False) == []
    assert override_targets(OrderStatus.PENDING, has_provider_id=False) == [OrderStatus.FAILED]
    assert OrderStatus.COMPLETED in override_targets(OrderStatus.SUBMITTED, has_provider_id=True)
    assert OrderStatus.CANCELED not in override_targets(OrderStatus.SUBMITTED, has_provider_id=True)
    assert override_targets(OrderStatus.COMPLETED, has_provider_id=True) == []


# ------------- ثغرة مكتشفة: طلب فاشل بلا استرجاع لا مسار لاسترجاعه ------------- #


async def test_failed_order_without_auto_refund_can_be_refunded_once_manually(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service, mock_client
) -> None:
    """الاسترجاع التلقائي معطّل ⇒ الطلب failed والمال محجوز ⇒ «تعليم كفاشل» يسترجعه مرة واحدة فقط."""
    await services.settings.set("auto_refund_on_provider_fail", False)
    await _fund(services, user, admin)
    order = await _order(services, user, mock_service)
    mock_client.always_fail_add = ProviderPermanentError("رفض المزود")
    await services.orders.process_pending_orders()
    assert (await _status(repos, order.id)).status == OrderStatus.FAILED
    assert await services.wallet.balance_units(user.id) == 100_000 - COST

    assert await services.orders.admin_mark_failed(admin, order.id, "استرجاع يدوي بعد مراجعة") == COST
    final = await _status(repos, order.id)
    assert final.status == OrderStatus.REFUNDED and final.refund_amount_units == COST
    assert await services.wallet.balance_units(user.id) == 100_000

    with pytest.raises(InvalidStateTransitionError):                     # مغلق الآن
        await services.orders.admin_mark_failed(admin, order.id, "استرجاع ثانٍ")
    txs = await services.wallet.order_transactions(order.id)
    assert [t.type for t in txs].count(TransactionType.REFUND) == 1
```

## `tests/integration/test_db_commit_failure_phase12_1.py`

```python
"""المرحلة 12.1 — فشل COMMIT نفسه لا يترك اتصال الكتابة داخل معاملة مفتوحة."""

from __future__ import annotations

import sqlite3

import pytest

from database.database import Database

pytestmark = pytest.mark.asyncio


async def test_commit_failure_rolls_back_and_database_stays_usable(db: Database, monkeypatch) -> None:
    """COMMIT يفشل مرة: التغيير لا يُحفظ، والاستثناء يصل للمستدعي، والمعاملة التالية تعمل."""
    async with db.transaction() as tx:
        await tx.execute("CREATE TABLE probe (k TEXT)")
        await tx.execute("INSERT INTO probe (k) VALUES ('probe_a')")

    conn = db._write_conn
    real_execute = conn.execute
    state = {"failed": False}

    async def boom():
        """COMMIT فاشل مع بقاء المعاملة مفتوحة (كما في SQLITE_BUSY/IOERR): يجب أن يتراجع عنها الكود."""
        raise sqlite3.OperationalError("disk I/O error")

    def flaky_execute(sql, *args, **kwargs):
        if sql == "COMMIT" and not state["failed"]:
            state["failed"] = True
            return boom()
        return real_execute(sql, *args, **kwargs)

    monkeypatch.setattr(conn, "execute", flaky_execute)

    with pytest.raises(sqlite3.OperationalError):
        async with db.transaction() as tx:
            await tx.execute("INSERT INTO probe (k) VALUES ('probe_b')")

    assert state["failed"]
    assert await db.fetchval("SELECT COUNT(*) FROM probe WHERE k = 'probe_b'") == 0, "تغيير معاملة فاشلة حُفظ"

    async with db.transaction() as tx:                 # يجب ألا يفشل بـ«within a transaction»
        await tx.execute("INSERT INTO probe (k) VALUES ('probe_c')")
    assert await db.fetchval("SELECT COUNT(*) FROM probe WHERE k IN ('probe_a', 'probe_c')") == 2
```

## `tests/integration/test_currency_types_phase12_1.py`

```python
"""
المرحلة 12.1 — العملة وأنواع الخدمات وتكرار الاستيراد:

    P0-5  سعر صرف لكل مزود: التحويل مرة واحدة عند حدود المزود، ورفض واضح عند اختلاف العملة بلا سعر.
    P0-6  الأنواع غير default مرفوضة في الاستيراد وتُعطَّل عند المزامنة.
    #7    استيراد نفس خدمة المزود مرتين (سباق) ينتج واحدة فقط.
"""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import replace

import pytest

from core.enums import OrderStatus
from core.exceptions import DuplicateOperationError, ProviderError, ServiceNotAvailableError, ValidationError
from database.models import Provider, Service, User
from integrations.providers.base import ProviderServiceItem, normalize_service_type
from services import ServiceContainer

pytestmark = pytest.mark.asyncio

RATE = "530"


async def _set_currency(repos, provider: Provider, currency: str, rate: str | None) -> Provider:
    """ضبط عملة مزود مباشرة في القاعدة (يتجاوز الخدمة لتجهيز الحالة)."""
    async with repos.db.transaction() as tx:
        await repos.providers.update_fields(tx, provider.id, currency=currency, exchange_rate=rate)
    refreshed = await repos.providers.get(provider.id)
    assert refreshed is not None
    return refreshed


async def _row(repos, service_id: int):
    """قراءة صف خدمة خاماً (بما فيها المعطَّلة)."""
    return await repos.db.fetchone("SELECT * FROM services WHERE id = ?", (service_id,))


def _item(pid: str, *, rate: int = 5_000, service_type: str = "default") -> ProviderServiceItem:
    """عنصر خدمة مزود للاختبار."""
    return ProviderServiceItem(
        provider_service_id=pid, name=f"خدمة اختبار {pid}", rate_per_1000_units=rate,
        min_quantity=10, max_quantity=1000, category="Test", service_type=service_type,
    )


# --------------------------------- العملة --------------------------------- #


async def test_currency_mismatch_without_rate_blocks_provider(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service, mock_provider: Provider, mock_client
) -> None:
    """مزود بـUSD والنظام YER بلا سعر: غير جاهز، لا طلبات جديدة، ولا جلب خدمات، ولا إرسال."""
    await services.wallet.adjust_balance(target=user, amount_units=100_000, admin=admin, reason="رصيد", credit=True)
    provider = await _set_currency(repos, mock_provider, "USD", None)

    health = await services.providers.health(provider)
    assert not health.is_usable and "USD" in health.reason and "YER" in health.reason

    with pytest.raises(ServiceNotAvailableError):
        await services.orders.create_order(user, service_id=mock_service.id, link="https://instagram.com/x", quantity=1000)
    with pytest.raises(ProviderError) as info:
        await services.providers.fetch_services(admin, provider)
    assert "سعر الصرف" in info.value.user_message
    assert not mock_client.calls, "لا اتصال بالمزود قبل التحقق من العملة"


async def test_order_placed_before_misconfiguration_is_never_sent_with_wrong_currency(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service, mock_provider: Provider, mock_client
) -> None:
    """طلب أُنشئ ثم تغيّرت عملة المزود بلا سعر: يبقى منتظراً ولا يُرسل ولا يُعاد إرساله بقيمة خاطئة."""
    await services.wallet.adjust_balance(target=user, amount_units=100_000, admin=admin, reason="رصيد", credit=True)
    order = await services.orders.create_order(user, service_id=mock_service.id, link="https://instagram.com/x", quantity=1000)
    await _set_currency(repos, mock_provider, "USD", None)

    await services.orders.process_pending_orders()
    current = await repos.orders.get(order.id)
    assert current.status == OrderStatus.PENDING
    assert not [call for call in mock_client.calls if call[0] == "add"], "أُرسل الطلب رغم غياب سعر الصرف"


async def test_exchange_rate_converts_service_prices_and_provider_cost(
    services: ServiceContainer, repos, user: User, admin: User, super_admin: User, mock_provider: Provider, mock_client
) -> None:
    """سعر صرف 530: أسعار الاستيراد وتكلفة المزود الفعلية تُحوَّل مرة واحدة إلى عملة النظام."""
    mock_client.rate_per_1000_units = 6_000                     # 0.6 USD لكل ألف عند المزود
    mock_client.currency = "USD"
    provider = await services.providers.set_currency(super_admin, mock_provider.id, currency="usd", exchange_rate=RATE)
    assert provider.currency == "USD" and provider.exchange_rate == RATE

    items = await services.providers.fetch_services(super_admin, provider)
    assert items[0].rate_per_1000_units == 6_000 * 530 and items[0].currency == "YER"

    category = (await repos.categories.list_all())[0]
    service = await services.catalog.import_provider_service(
        super_admin, provider_id=provider.id, item=items[0], category_id=category.id, margin_percent=20
    )
    assert service.provider_price_per_1000_units == 3_180_000
    assert service.price_per_1000_units == 3_816_000            # +20% على التكلفة بعملة النظام

    await services.wallet.adjust_balance(target=user, amount_units=50_000_000, admin=admin, reason="رصيد", credit=True)
    order = await services.orders.create_order(user, service_id=service.id, link="https://instagram.com/x", quantity=1000)
    await services.orders.process_pending_orders()
    sent = await repos.orders.get(order.id)
    assert sent.status == OrderStatus.SUBMITTED
    assert sent.provider_cost_units == 6_000 * 530, "charge المزود (USD) يجب أن يُحوَّل إلى YER"


async def test_same_currency_needs_no_rate_and_balance_alert_uses_equivalent(
    services: ServiceContainer, repos, admin: User, super_admin: User, mock_provider: Provider, mock_client
) -> None:
    """تنبيه الرصيد المنخفض يقارن مكافئ الرصيد بعملة النظام لا الرقم الخام."""
    await services.settings.set("provider_low_balance_alert_units", 1_000_000, admin_id=super_admin.id)   # 100 YER
    mock_client.currency = "USD"
    provider = await services.providers.set_currency(super_admin, mock_provider.id, currency="USD", exchange_rate=RATE)

    mock_client.balance_units = 1_000 * 10_000                  # 1000 USD ≈ 530,000 YER ⇒ لا تنبيه
    await services.providers.check_balance(provider)
    low = await repos.db.fetchall("SELECT 1 FROM notifications WHERE dedupe_key LIKE 'manual:provider:%:low:%'")
    assert not low

    mock_client.balance_units = 1_000                           # 0.1 USD ≈ 53 YER ⇒ تنبيه
    await services.providers.check_balance(provider)
    low = await repos.db.fetchall("SELECT 1 FROM notifications WHERE dedupe_key LIKE 'manual:provider:%:low:%'")
    assert low
    stored = await repos.providers.get(provider.id)
    assert stored.balance_units == 1_000 and stored.currency == "USD", "العملة المسجّلة لا تتغير من استجابة API"


async def test_api_reported_currency_mismatch_is_flagged_not_overwritten(
    services: ServiceContainer, repos, admin: User, super_admin: User, mock_provider: Provider, mock_client
) -> None:
    """المزود يُبلّغ بعملة غير المسجّلة: تنبيه للأدمن وتبقى العملة المسجّلة كما هي."""
    mock_client.currency = "EUR"
    await services.providers.check_balance(mock_provider)
    stored = await repos.providers.get(mock_provider.id)
    assert stored.currency == "YER"
    rows = await repos.db.fetchall("SELECT 1 FROM notifications WHERE dedupe_key LIKE 'manual:provider:%:currency:EUR:%'")
    assert rows


async def test_set_currency_validation_and_audit(
    services: ServiceContainer, repos, admin: User, super_admin: User, mock_provider: Provider
) -> None:
    """عملة مختلفة بلا سعر مرفوضة، السعر يُطبَّع، والتغيير يُدقَّق."""
    with pytest.raises(ValidationError):
        await services.providers.set_currency(super_admin, mock_provider.id, currency="USD", exchange_rate=None)
    for bad in ("0", "-1", "abc", "NaN"):
        with pytest.raises(ValidationError):
            await services.providers.set_currency(super_admin, mock_provider.id, currency="USD", exchange_rate=bad)
    updated = await services.providers.set_currency(super_admin, mock_provider.id, currency="USD", exchange_rate="530.50")
    assert updated.exchange_rate == "530.5"
    back = await services.providers.set_currency(super_admin, mock_provider.id, currency="YER", exchange_rate=None)
    assert back.exchange_rate is None
    audit = await repos.audit.list_recent(limit=10)
    assert sum(1 for entry in audit if entry.action == "providers.set_currency") == 2


async def test_create_provider_defaults_to_system_currency_and_requires_rate_otherwise(
    services: ServiceContainer, super_admin: User
) -> None:
    """إنشاء مزود: بلا عملة ⇒ عملة النظام؛ عملة مختلفة بلا سعر ⇒ رفض."""
    created = await services.providers.create_provider(
        super_admin, name="P1", api_url="https://panel.example.com/api/v2", api_key="abcdefgh12345", api_type="mock"
    )
    assert created.currency == "YER" and created.exchange_rate is None
    with pytest.raises(ValidationError):
        await services.providers.create_provider(
            super_admin, name="P2", api_url="https://panel2.example.com/api/v2", api_key="abcdefgh12345",
            api_type="mock", currency="USD",
        )
    with_rate = await services.providers.create_provider(
        super_admin, name="P3", api_url="https://panel3.example.com/api/v2", api_key="abcdefgh12345",
        api_type="mock", currency="usd", exchange_rate="530",
    )
    assert (with_rate.currency, with_rate.exchange_rate) == ("USD", "530")


def test_parse_currency_spec() -> None:
    """تحليل «العملة [السعر]»."""
    from services.provider_service import ProviderService

    parse = ProviderService.parse_currency_spec
    assert parse("usd 530") == ("USD", "530")
    assert parse("YER") == ("YER", None)
    assert parse("SAR ٣٫٧٥".replace("٫", ".")) == ("SAR", "3.75")
    for bad in ("", "USD 1 2", "ريال 5", "U 5", "USD abc"):
        with pytest.raises(ValidationError):
            parse(bad)


def test_to_system_units_rounds_half_up_with_decimal() -> None:
    """التحويل Decimal بتقريب نصف لأعلى (لا float)."""
    from decimal import Decimal

    from services.provider_service import ProviderService

    assert ProviderService.to_system_units(1, Decimal("0.5")) == 1          # 0.5 ⇒ 1
    assert ProviderService.to_system_units(3, Decimal("0.5")) == 2          # 1.5 ⇒ 2
    assert ProviderService.to_system_units(10_000, Decimal("530.5")) == 5_305_000
    assert ProviderService.to_system_units(0, Decimal("530")) == 0


# ------------------------------- أنواع الخدمات ------------------------------- #


def test_service_type_is_normalized() -> None:
    """«Custom Comments» ⇒ custom_comments و«Default» ⇒ default."""
    assert normalize_service_type("Custom Comments") == "custom_comments"
    assert normalize_service_type("Default") == "default"
    assert normalize_service_type("") == "default" and normalize_service_type(None) == "default"
    assert normalize_service_type("Mentions-Hashtag") == "mentions_hashtag"


async def test_unsupported_types_are_rejected_on_import(
    services: ServiceContainer, repos, super_admin: User, mock_provider: Provider
) -> None:
    """الاستيراد يرفض الأنواع غير default برسالة واضحة، ويقبل default."""
    category = (await repos.categories.list_all())[0]
    for service_type in ("package", "custom_comments", "subscriptions"):
        with pytest.raises(ValidationError) as info:
            await services.catalog.import_provider_service(
                super_admin, provider_id=mock_provider.id, item=_item("900", service_type=service_type),
                category_id=category.id, margin_percent=10,
            )
        assert "غير مدعوم" in info.value.user_message
    assert await repos.services.find_by_provider_service(mock_provider.id, "900") is None

    ok = await services.catalog.import_provider_service(
        super_admin, provider_id=mock_provider.id, item=_item("901"), category_id=category.id, margin_percent=10
    )
    assert ok.service_type == "default"


async def test_sync_disables_service_whose_type_became_unsupported(
    services: ServiceContainer, repos, super_admin: User, mock_provider: Provider
) -> None:
    """المزامنة: خدمة مستوردة صار نوعها package ⇒ تُعطَّل وتُذكر في التقرير، وسعرها لا يتغير."""
    category = (await repos.categories.list_all())[0]
    keep = await services.catalog.import_provider_service(
        super_admin, provider_id=mock_provider.id, item=_item("1"), category_id=category.id, margin_percent=10
    )
    drift = await services.catalog.import_provider_service(
        super_admin, provider_id=mock_provider.id, item=_item("2"), category_id=category.id, margin_percent=10
    )
    report = await services.catalog.sync_provider_services(
        super_admin, provider_id=mock_provider.id,
        items=[_item("1"), replace(_item("2", rate=9_000), service_type="package")],
    )
    assert [service.id for service in report.unsupported] == [drift.id]
    assert (await _row(repos, drift.id))["is_active"] == 0
    assert (await _row(repos, keep.id))["is_active"] == 1
    assert (await _row(repos, drift.id))["provider_price_per_1000_units"] == 5_000

    again = await services.catalog.sync_provider_services(
        super_admin, provider_id=mock_provider.id, items=[_item("1"), _item("2", service_type="package")]
    )
    assert again.unsupported == [], "المعطَّلة مسبقاً لا تُكرَّر في كل مزامنة"


# --------------------------- تكرار الاستيراد (سباق) --------------------------- #


async def test_concurrent_import_creates_one_service_only(
    services: ServiceContainer, repos, super_admin: User, mock_provider: Provider
) -> None:
    """ضغطتا استيراد متزامنتان لنفس الخدمة: واحدة تنجح والأخرى DuplicateOperationError."""
    category = (await repos.categories.list_all())[0]

    async def attempt():
        return await services.catalog.import_provider_service(
            super_admin, provider_id=mock_provider.id, item=_item("777"), category_id=category.id, margin_percent=10
        )

    results = await asyncio.gather(*(attempt() for _ in range(4)), return_exceptions=True)
    assert sum(isinstance(r, Service) for r in results) == 1
    assert sum(isinstance(r, DuplicateOperationError) for r in results) == 3
    count = await repos.db.fetchval(
        "SELECT COUNT(*) FROM services WHERE provider_id = ? AND provider_service_id = '777'", (mock_provider.id,)
    )
    assert count == 1


async def test_unique_index_blocks_duplicates_at_database_level(
    repos, mock_provider: Provider, mock_service: Service
) -> None:
    """حتى لو تجاوز الكود الفحص، القيد الفريد يمنع تكرار (المزود، خدمة المزود)."""
    with pytest.raises(sqlite3.IntegrityError):
        async with repos.db.transaction() as tx:
            await repos.services.create(
                tx, category_id=mock_service.category_id, provider_id=mock_provider.id,
                provider_service_id=mock_service.provider_service_id, name="نسخة مكررة",
                price_per_1000_units=1, min_quantity=1, max_quantity=10,
            )


async def test_migration_0010_schema(repos) -> None:
    """الترحيل 0010: عمود exchange_rate موجود والإعداد الميت محذوف."""
    columns = {row["name"] for row in await repos.db.fetchall("PRAGMA table_info(providers)")}
    assert "exchange_rate" in columns
    keys = {row["key"] for row in await repos.db.fetchall("SELECT key FROM settings")}
    assert "provider_exchange_rate" not in keys


# ------------------------------ سباق الإعدادات (#8) ------------------------------ #


async def test_concurrent_min_max_deposit_updates_cannot_cross(
    services: ServiceContainer, repos, super_admin: User
) -> None:
    """رفع الأدنى وخفض الأعلى متزامنين: لا يُسمح بالنتيجة أدنى > أعلى."""
    await services.settings.set("min_deposit_units", 100_000, admin_id=super_admin.id)
    await services.settings.set("max_deposit_units", 1_000_000, admin_id=super_admin.id)

    results = await asyncio.gather(
        services.settings.set("min_deposit_units", 900_000, admin_id=super_admin.id),
        services.settings.set("max_deposit_units", 500_000, admin_id=super_admin.id),
        return_exceptions=True,
    )
    assert sum(isinstance(r, ValidationError) for r in results) == 1, "أحد التعديلين يجب أن يُرفض"
    low = int((await repos.settings.get("min_deposit_units")).value)
    high = int((await repos.settings.get("max_deposit_units")).value)
    assert low <= high


# --------------------------- حدود طريقة الدفع عند الإنشاء (#9) --------------------------- #


async def test_create_payment_method_rejects_inverted_limits(services: ServiceContainer, repos, super_admin: User) -> None:
    """إنشاء طريقة بأدنى > أقصى مرفوض ولا تُنشأ أي صف."""
    with pytest.raises(ValidationError):
        await services.payments.create_method(
            super_admin, name_ar="طريقة معكوسة", min_amount_units=900_000, max_amount_units=100_000
        )
    assert await repos.db.fetchval("SELECT COUNT(*) FROM payment_methods WHERE name_ar = 'طريقة معكوسة'") == 0
    ok = await services.payments.create_method(
        super_admin, name_ar="طريقة سليمة", min_amount_units=100_000, max_amount_units=900_000
    )
    assert ok.min_amount_units == 100_000
```

## `tests/integration/test_races_phase12_1.py`

```python
"""المرحلة 12.1 — سباقات الحالة: الإذاعة وآخر super admin وحدود المحادثة."""

from __future__ import annotations

import asyncio

import pytest

from core.enums import BroadcastStatus
from database.models import User
from services import ServiceContainer
from tests.integration.test_user_interface import bot, context  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _audience(services: ServiceContainer, count: int = 3) -> None:
    """مستخدمون عاديون كجمهور للإذاعة."""
    async with services.db.transaction() as tx:
        for index in range(count):
            await services.repos.users.create(
                tx, telegram_id=8100 + index, username=f"r{index}", first_name="مستخدم", role="user"
            )


class _Sender:
    """مرسل يسجّل المستلمين."""

    def __init__(self) -> None:
        self.ids: list[int] = []

    async def __call__(self, telegram_id: int, text: str, media_file_id, media_type) -> int:
        self.ids.append(telegram_id)
        return len(self.ids)


# --------------------------------- الإذاعة --------------------------------- #


async def test_set_status_is_conditional_on_previous_state(services: ServiceContainer, super_admin: User) -> None:
    """`set_status(expected_statuses=…)` لا يغيّر شيئاً إن كانت الحالة الحالية غير متوقعة."""
    await _audience(services)
    broadcast = await services.broadcasts.create(super_admin, text="نص", target="all")
    await services.broadcasts.cancel(super_admin, broadcast.id)

    async with services.db.transaction() as tx:
        changed = await services.repos.broadcasts.set_status(
            tx, broadcast.id, BroadcastStatus.RUNNING,
            expected_statuses=(BroadcastStatus.DRAFT, BroadcastStatus.PAUSED),
        )
    assert changed is False
    assert (await services.repos.broadcasts.get(broadcast.id)).status == BroadcastStatus.CANCELLED


async def test_complete_never_overwrites_a_concurrent_cancel(services: ServiceContainer, super_admin: User) -> None:
    """إلغاء حدث بين قراءة الإكمال وكتابته: يبقى الإلغاء ولا إشعار «اكتملت»."""
    await _audience(services, 1)
    broadcast = await services.broadcasts.create(super_admin, text="نص", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)

    original_get = services.repos.broadcasts.get
    stale = await original_get(broadcast.id)                         # لقطة «تعمل» قديمة

    calls = {"n": 0}

    async def stale_get(broadcast_id: int):
        calls["n"] += 1
        if calls["n"] == 1:
            await services.broadcasts.cancel(super_admin, broadcast_id)   # الإلغاء يقع بعد القراءة
            return stale
        return await original_get(broadcast_id)

    services.repos.broadcasts.get = stale_get                        # type: ignore[method-assign]
    try:
        await services.broadcasts._complete(broadcast.id)
    finally:
        services.repos.broadcasts.get = original_get                 # type: ignore[method-assign]

    assert (await original_get(broadcast.id)).status == BroadcastStatus.CANCELLED
    done = await services.db.fetchall("SELECT 1 FROM notifications WHERE dedupe_key LIKE ?", (f"%broadcast:{broadcast.id}:done%",))
    assert not done


async def test_concurrent_start_and_cancel_end_consistent(services: ServiceContainer, super_admin: User) -> None:
    """بدء وإلغاء متزامنان: إن نجح الإلغاء فالحالة النهائية cancelled دائماً (لا تعود running)."""
    await _audience(services)
    broadcast = await services.broadcasts.create(super_admin, text="نص", target="all")
    results = await asyncio.gather(
        services.broadcasts.start(super_admin, broadcast.id),
        services.broadcasts.cancel(super_admin, broadcast.id),
        return_exceptions=True,
    )
    final = (await services.repos.broadcasts.get(broadcast.id)).status
    if results[1] is True:
        assert final == BroadcastStatus.CANCELLED
    else:
        assert final == BroadcastStatus.RUNNING
    sender = _Sender()
    if final == BroadcastStatus.CANCELLED:
        assert (await services.broadcasts.send_batch(sender)).claimed == 0 and not sender.ids


# ------------------------------- آخر super admin ------------------------------- #


async def test_two_super_admins_cannot_demote_each_other_concurrently(services: ServiceContainer) -> None:
    """أدمنان أعلى يخفّض كلٌّ منهما الآخر معاً: ينجح واحد فقط ويبقى أدمن أعلى فعّال واحد على الأقل."""
    from core.exceptions import PermissionDeniedError

    async with services.db.transaction() as tx:
        first = await services.repos.users.create(tx, telegram_id=9101, username="s1", first_name="أ", role="super_admin")
        second = await services.repos.users.create(tx, telegram_id=9102, username="s2", first_name="ب", role="super_admin")

    results = await asyncio.gather(
        services.auth.set_role(first, second.id, "user"),
        services.auth.set_role(second, first.id, "user"),
        return_exceptions=True,
    )
    assert sum(r is True for r in results) == 1, results
    assert sum(isinstance(r, PermissionDeniedError) for r in results) == 1, results
    remaining = await services.db.fetchval("SELECT COUNT(*) FROM users WHERE role = 'super_admin' AND is_banned = 0")
    assert remaining == 1
    events = await services.repos.audit.count_by_action_prefix("security.last_super_admin_protected")
    assert events == 1, "الحدث الأمني يُسجَّل رغم رفض العملية"


# ------------------------ حد المعدل قبل القاعدة + ذاكرة الحارس ------------------------ #


async def test_flood_is_cut_before_any_database_read(bot, context, services, super_admin) -> None:  # noqa: F811
    """سيل تحديثات من معرّف واحد: `get_or_create` لا يجري أكثر من الحد المسبق، والباقي يُقطع في الذاكرة."""
    from middlewares.context import UserContextMiddleware
    from middlewares.rate_limit import AbuseGuard, RateLimiter
    from tests.integration.test_security_phase9 import Clock, _tap

    await services.settings.set("rate_limit_actions_per_minute", "3", admin_id=super_admin.id)
    await services.settings.set("rate_limit_admin_actions_per_minute", "10", admin_id=super_admin.id)
    clock = Clock()
    middleware = UserContextMiddleware(RateLimiter(clock=clock), AbuseGuard(clock=clock))

    calls = {"n": 0}
    original = services.users.get_or_create

    async def counting(**kwargs):
        calls["n"] += 1
        return await original(**kwargs)

    services.users.get_or_create = counting                         # type: ignore[method-assign]
    try:
        results = [await _tap(middleware, bot, context, user_id=616_161) for _ in range(40)]
    finally:
        services.users.get_or_create = original                     # type: ignore[method-assign]

    assert results[:3] == [True, True, True] and not any(results[3:])
    assert calls["n"] <= 10, f"قراءات القاعدة تجاوزت الحد المسبق: {calls['n']}"


def test_abuse_guard_memory_is_bounded_and_keeps_blocked(monkeypatch) -> None:
    """سيل معرّفات مختلفة لا يضخّم ذاكرة الحارس، والموقوف لا يُسقَط من السجل."""
    import middlewares.rate_limit as rl

    monkeypatch.setattr(rl, "MAX_GUARD_ENTRIES", 50)

    class _Clock:
        now = 1000.0

        def __call__(self) -> float:
            return self.now

    clock = _Clock()
    guard = rl.AbuseGuard(clock=clock)
    assert guard.record_violation(1, strikes_limit=1, block_seconds=10_000).blocked
    for telegram_id in range(100, 2_000):
        clock.now += 0.01
        guard.record_violation(telegram_id, strikes_limit=5, block_seconds=60)

    assert len(guard._strikes) <= 51
    assert guard.is_blocked(1), "المُوقَف أُسقط من الذاكرة بسبب السيل"


async def test_broadcast_rate_setting_paces_sending(services: ServiceContainer, super_admin: User) -> None:
    """`broadcast_rate_per_second` يضبط الفاصل بين الرسائل فعلاً (5/ث ⇒ ≥ 0.2ث بين رسالتين)."""
    import time

    await services.settings.set("broadcast_rate_per_second", "5", admin_id=super_admin.id)
    await _audience(services, 4)
    broadcast = await services.broadcasts.create(super_admin, text="نص", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)

    stamps: list[float] = []

    async def sender(telegram_id: int, text: str, media_file_id, media_type) -> int:
        stamps.append(time.monotonic())
        return 1

    report = await services.broadcasts.send_batch(sender, limit=10)
    assert report.sent == len(stamps) >= 4
    gaps = [later - earlier for earlier, later in zip(stamps, stamps[1:])]
    assert all(gap >= 0.18 for gap in gaps), gaps


# ------------------------------- قناة تنبيهات الأدمن (#17) ------------------------------- #


async def _notify(services: ServiceContainer, token: str) -> int:
    """إدراج تنبيه أدمن عبر الخدمة (كما تفعل الخدمات الأخرى)."""
    from core.permissions import Permission

    async with services.db.transaction() as tx:
        return await services.notifications.notify_admins(
            tx, permission=Permission.ORDERS_VIEW, token=token, title="تنبيه تجريبي", message="نص التنبيه"
        )


async def test_alert_channel_receives_copy_from_env_or_setting(services: ServiceContainer, admin: User, super_admin: User) -> None:
    """نسخة التنبيه تصل لقناة التنبيهات: الإعداد أولاً وإلا متغير البيئة، ولا تُكرَّر لكل أدمن."""
    sent: list[tuple[int, str, str]] = []

    async def sender(chat_id: int, title: str, message: str) -> int:
        sent.append((chat_id, title, message))
        return 1

    assert await _notify(services, "alert:1") >= 2                 # أدمنان على الأقل
    assert await services.notifications.flush_alert_channel(sender, fallback_chat_id=-100111) == 1
    assert sent == [(-100111, "تنبيه تجريبي", "نص التنبيه")]

    await services.settings.set("admin_alert_chat_id", "-100222333", admin_id=super_admin.id)
    await _notify(services, "alert:2")
    await services.notifications.flush_alert_channel(sender, fallback_chat_id=-100111)
    assert sent[-1][0] == -100222333, "الإعداد يتقدم على متغير البيئة"

    # تنبيه مكرر (نفس token) لا يُنسخ مرة ثانية
    assert await _notify(services, "alert:2") == 0
    assert await services.notifications.flush_alert_channel(sender, fallback_chat_id=-100111) == 0


async def test_alert_channel_unset_drains_outbox_and_failures_do_not_raise(services: ServiceContainer, admin: User) -> None:
    """بلا قناة: لا تراكم. وفشل الإرسال للقناة يُسجَّل ولا يُسقط المهمة."""
    from core.exceptions import NotificationTemporaryError

    await _notify(services, "alert:3")
    assert await services.notifications.flush_alert_channel(_never_called) == 0
    assert not services.notifications._alert_outbox

    async def failing(chat_id: int, title: str, message: str) -> int:
        raise NotificationTemporaryError("شبكة")

    await _notify(services, "alert:4")
    assert await services.notifications.flush_alert_channel(failing, fallback_chat_id=-100999) == 0


async def _never_called(chat_id: int, title: str, message: str) -> int:
    raise AssertionError("لا قناة مضبوطة ⇒ لا إرسال")
```

## `tests/unit/test_perfect_panel_hardening_phase12_1.py`

```python
"""اختبارات تقوية عميل Perfect Panel (المراجعة 12.1): حد حجم الاستجابة وتحويل الأعداد الصحيحة."""

from __future__ import annotations

import httpx
import pytest

import integrations.providers.perfect_panel as pp
from core.exceptions import ProviderTemporaryError, ProviderUncertainError
from integrations.providers.perfect_panel import PerfectPanelClient

pytestmark = pytest.mark.asyncio

API_URL = "https://panel.invalid/api/v2"


def _client(handler) -> PerfectPanelClient:
    """عميل بنقل وهمي."""
    return PerfectPanelClient(api_url=API_URL, api_key="k" * 12, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_oversized_response_on_read_is_temporary(monkeypatch) -> None:
    """استجابة أكبر من الحد أثناء قراءة عادية ⇒ خطأ مؤقت (لا تحميل كامل للذاكرة)."""
    monkeypatch.setattr(pp, "MAX_RESPONSE_BYTES", 1_000)
    client = _client(lambda request: httpx.Response(200, content=b"[" + b"1," * 5_000 + b"1]"))
    with pytest.raises(ProviderTemporaryError):
        await client.get_services()


async def test_oversized_response_after_add_is_uncertain(monkeypatch) -> None:
    """بعد إرسال طلب شراء: الاستجابة الضخمة ⇒ غير مؤكد (لا إعادة إرسال تلقائية)."""
    monkeypatch.setattr(pp, "MAX_RESPONSE_BYTES", 1_000)
    client = _client(lambda request: httpx.Response(200, content=b"x" * 5_000))
    with pytest.raises(ProviderUncertainError):
        await client.add_order(provider_service_id="1", link="https://a.test/u", quantity=100)


async def test_declared_content_length_over_limit_is_rejected(monkeypatch) -> None:
    """الطول المعلن في الترويسة يكفي للرفض قبل قراءة الجسم."""
    monkeypatch.setattr(pp, "MAX_RESPONSE_BYTES", 1_000)
    client = _client(lambda request: httpx.Response(200, content=b"{}", headers={"content-length": "999999"}))
    with pytest.raises(ProviderTemporaryError):
        await client.get_services()


async def test_normal_response_still_parses() -> None:
    """استجابة عادية تحت الحد تُقرأ كما كانت."""
    client = _client(lambda request: httpx.Response(200, json={"order": 7, "charge": "1.5", "currency": "USD"}))
    result = await client.add_order(provider_service_id="1", link="https://a.test/u", quantity=100)
    assert result.provider_order_id == "7"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("100", 100), (100, 100), ("100.0", 100), (" 7 ", 7), ("1e3", 1000), (0, 0),
     ("100.5", None), (1.5, None), ("nan", None), ("inf", None), ("1e400", None), ("1e30", None),
     ("abc", None), ("", None), (None, None)],
)
def test_as_int_rejects_fractions_and_non_finite(raw, expected) -> None:
    """الكسور والقيم غير المنتهية لا تُقرَّب بصمت (كان 1e400 يرفع OverflowError)."""
    assert PerfectPanelClient._as_int(raw) == expected
```

## `tests/unit/test_registry_dev_types_phase12_1.py`

```python
"""المزود الوهمي مخفي ومرفوض في الإنتاج ما لم تُفعَّل أنواع التطوير صراحةً (المراجعة 12.1، البند 18)."""

from __future__ import annotations

import pytest

from core.exceptions import ProviderError
from integrations.providers import registry


def test_mock_hidden_and_unsupported_by_default() -> None:
    """افتراضياً (حالة الإنتاج): لا يظهر في القائمة، ولا يُعدّ مدعوماً، ولا يُنشأ له عميل."""
    registry.enable_dev_types(False)
    assert "mock" not in registry.available_types()
    assert not registry.is_supported("mock")
    assert registry.is_supported("perfect_panel")
    with pytest.raises(ProviderError):
        registry.create_client(api_type="mock", api_url="https://x.test", api_key="k" * 10)


def test_mock_available_once_enabled() -> None:
    """بعد التفعيل الصريح يعمل كما كان (الاختبارات و`demo_cycle`)."""
    registry.enable_dev_types(True)
    assert "mock" in registry.available_types()
    assert registry.create_client(api_type="mock", api_url="https://x.test", api_key="k" * 10) is not None
```
