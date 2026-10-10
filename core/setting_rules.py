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
from utils.channel_ref import ChannelRefError, parse_channel_value
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
    "order_check_active_max_seconds": _int(30, 3600),
    "order_check_error_max_seconds": _int(60, 7200),
    "order_check_round_budget_seconds": _int(10, 600),
    "order_message_refresh_seconds": _int(5, 3600),
    "channel_post_ttl_hours": _int(1, 720),
    # الشحن
    "min_deposit_units": SettingRule(minimum=1, maximum=GENERIC_MONEY_MAX),
    "max_deposit_units": SettingRule(minimum=1, maximum=GENERIC_MONEY_MAX),
    "payment_expiry_hours": _int(1, 720),
    "max_pending_payments_per_user": _int(1, 50),
    "payment_search_limit": _int(1, 50),
    # الإشعارات والإذاعة
    "notification_dispatch_seconds": _int(5, 3600),
    "admin_alert_chat_id": SettingRule(
        max_length=200, allow_empty=True, hint="معرّف محادثة: -100xxxxxxxxxx أو @username"
    ),
    "orders_log_chat_id": SettingRule(
        max_length=200, allow_empty=True, hint="معرّف القناة: -100xxxxxxxxxx أو @username"
    ),
    "usd_rate": SettingRule(max_length=20, hint="عدد وحدات العملة المحلية في 1$ مثل 530"),
    "channel_official": SettingRule(max_length=300, allow_empty=True),
    "channel_proofs": SettingRule(max_length=300, allow_empty=True),
    "channel_updates": SettingRule(max_length=300, allow_empty=True),
    "channel_offers": SettingRule(max_length=300, allow_empty=True),
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
    "provider_status_alert_threshold": _int(1, 100),
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

#: مفاتيح القنوات: تُفحص بصيغة المعرّف (قنوات الاشتراك + قناة التوثيق + قناة التنبيهات)
CHANNEL_SETTING_KEYS: Final[frozenset[str]] = frozenset(
    {"channel_official", "channel_proofs", "channel_updates", "channel_offers",
     "orders_log_chat_id", "admin_alert_chat_id"}
)
#: ما يقبل معرّف مستخدم موجباً (محادثة خاصة مع أدمن) بدل قناة
CHANNEL_KEYS_ALLOWING_USER_IDS: Final[frozenset[str]] = frozenset({"admin_alert_chat_id"})

#: مفاتيح عشرية موجبة (تُطبَّع بـ `normalize_decimal_text`)
DECIMAL_SETTING_KEYS: Final[frozenset[str]] = frozenset({"usd_rate"})

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
    cleaned = normalize_digits(str(text).strip())
    if "%" in cleaned:
        raise _bad(f"علامة % في عدد عشري: {text!r}", "❌ أرسل الرقم فقط بلا علامة % (مثال: 530).")
    if cleaned.startswith("-"):
        raise _bad(f"عدد سالب: {text!r}", "❌ يجب أن يكون الرقم أكبر من صفر (مثال: 530).")
    try:
        value = Decimal(cleaned.replace(",", "."))
    except InvalidOperation as exc:
        raise _bad(
            f"عدد عشري غير صالح: {text!r}",
            "❌ أرسل الرقم فقط بلا حروف أو رموز عملة (مثال: 530 أو 530.5).",
        ) from exc
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
    if key in DECIMAL_SETTING_KEYS:
        return normalize_decimal_text(text)
    if key in CHANNEL_SETTING_KEYS:
        try:
            return parse_channel_value(
                text, allow_user_ids=key in CHANNEL_KEYS_ALLOWING_USER_IDS
            ).canonical
        except ChannelRefError as exc:
            raise _bad(f"معرّف قناة غير صالح للمفتاح {key}: {text!r}", f"❌ {exc}") from exc
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
