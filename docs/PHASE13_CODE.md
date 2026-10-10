# الكود الكامل — المرحلة الأولى من ملاحظات v1.0.1 (الإصدار 1.1.0)

كل ما هنا منسوخ آلياً من ملفات المشروع الفعلية. الملفات الأطول من 760 سطراً غير مُكرَّرة هنا؛ تجد مسارها في الفهرس وهي مسلَّمة كاملة في المشروع.

## الفهرس

- `database/migrations/0011_phase13_launch_readiness.sql` — 64 سطراً
- `core/constants.py` — 45 سطراً
- `core/money.py` — 248 سطراً
- `core/setting_rules.py` — 307 سطراً
- `config.py` — 242 سطراً
- `main.py` — 265 سطراً
- `utils/channel_ref.py` — 139 سطراً
- `utils/privacy.py` — 46 سطراً
- `utils/conflict_guard.py` — 108 سطراً
- `utils/health_server.py` — 91 سطراً
- `utils/link_rules.py` — 377 سطراً
- `utils/validators.py` — 352 سطراً
- `utils/formatters.py` — 206 سطراً
- `database/repositories/channel_outbox.py` — 117 سطراً
- `database/repositories/favorites.py` — 64 سطراً
- `database/repositories/services.py` — 249 سطراً
- `database/repositories/__init__.py` — 90 سطراً
- `database/models.py` — 498 سطراً
- `services/channel_service.py` — 262 سطراً
- `services/subscription_service.py` — 225 سطراً
- `services/auth_service.py` — 451 سطراً
- `services/catalog_service.py` — 858 سطراً (غير مُكرَّر: كبير)
- `services/provider_service.py` — 729 سطراً
- `services/notification_service.py` — 329 سطراً
- `services/user_service.py` — 325 سطراً
- `services/order_service.py` — 1682 سطراً (غير مُكرَّر: كبير)
- `services/backup_service.py` — 961 سطراً (غير مُكرَّر: كبير)
- `services/__init__.py` — 212 سطراً
- `jobs/notification_jobs.py` — 42 سطراً
- `jobs/maintenance_jobs.py` — 90 سطراً
- `jobs/telegram_sender.py` — 146 سطراً
- `middlewares/context.py` — 373 سطراً
- `handlers/common/navigation.py` — 153 سطراً
- `handlers/user/catalog.py` — 126 سطراً
- `handlers/user/favorites.py` — 78 سطراً
- `handlers/user/order_flow.py` — 241 سطراً
- `handlers/admin/channels.py` — 175 سطراً
- `handlers/admin/catalog.py` — 928 سطراً (غير مُكرَّر: كبير)
- `handlers/admin/providers.py` — 1252 سطراً (غير مُكرَّر: كبير)
- `handlers/admin/__init__.py` — 88 سطراً
- `handlers/registry.py` — 305 سطراً
- `keyboards/user_kb.py` — 462 سطراً
- `keyboards/admin_kb.py` — 1757 سطراً (غير مُكرَّر: كبير)
- `keyboards/callback_data.py` — 170 سطراً
- `texts/channel_posts.py` — 54 سطراً
- `texts/ar.py` — 404 سطراً
- `texts/admin_ar.py` — 1584 سطراً (غير مُكرَّر: كبير)
- `scripts/init_db.py` — 190 سطراً
- `tests/integration/test_phase13_channels.py` — 443 سطراً
- `tests/integration/test_phase13_ops.py` — 310 سطراً
- `tests/integration/test_phase13_service_card.py` — 139 سطراً
- `tests/integration/test_phase13_admin_catalog.py` — 280 سطراً
- `tests/unit/test_link_rules.py` — 139 سطراً

---

## `database/migrations/0011_phase13_launch_readiness.sql`

```sql
-- =====================================================================
-- الترحيل 0011 — المرحلة 13.1 (الجاهزية للاستخدام الفعلي، ملاحظات التطوير v1.0.1)
--
-- ما يضيفه:
--   1) خدمات: link_rule (قاعدة التحقق من الرابط حسب المنصة/النوع مثل instagram:profile)،
--      speed_text / quality_text / guarantee_text (معلومات عرض اختيارية؛ NULL ⇒ «غير محددة»).
--   2) favorites: مفضلة المستخدم (مفتاح مركّب user_id+service_id ⇒ لا تكرار بنيوياً).
--   3) channel_outbox: صندوق إرسال دائم لقنوات الإدارة (تنبيهات الإدارة + توثيق الطلبات)،
--      بنفس نمط notifications: يُكتب مع الحدث في المعاملة نفسها، ويرسله job لاحقاً بمحاولات مجدولة،
--      فلا يضيع سجل عند إعادة التشغيل ولا يُكتب سجل لحدث لم يُثبَّت.
--   4) إعدادات: usd_rate، قنوات الاشتراك الإجباري الأربع، orders_log_chat_id، إشعار المستخدم الجديد.
--
-- لا حذف ولا إعادة بناء لأي جدول (ALTER ADD COLUMN وجداول جديدة وإعدادات فقط).
-- =====================================================================

ALTER TABLE services ADD COLUMN link_rule TEXT;
ALTER TABLE services ADD COLUMN speed_text TEXT;
ALTER TABLE services ADD COLUMN quality_text TEXT;
ALTER TABLE services ADD COLUMN guarantee_text TEXT;

CREATE TABLE favorites (
    user_id     INTEGER NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
    service_id  INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL,
    PRIMARY KEY (user_id, service_id)
) WITHOUT ROWID;

CREATE INDEX idx_favorites_user ON favorites(user_id, created_at);

CREATE TABLE channel_outbox (
    id              INTEGER PRIMARY KEY,
    kind            TEXT    NOT NULL CHECK (kind IN ('admin_alert', 'orders_log')),
    title           TEXT    NOT NULL DEFAULT '',
    message         TEXT    NOT NULL,
    dedupe_key      TEXT    NOT NULL UNIQUE,
    status          TEXT    NOT NULL DEFAULT 'queued'
                     CHECK (status IN ('queued', 'sent', 'failed', 'skipped')),
    attempts        INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at TEXT,
    last_error      TEXT,
    created_at      TEXT    NOT NULL,
    sent_at         TEXT
);

CREATE INDEX idx_channel_outbox_queue ON channel_outbox(status, next_attempt_at);

INSERT OR IGNORE INTO settings (key, value, value_type, group_code, name_ar, description_ar, is_editable, updated_at) VALUES
    ('usd_rate', '530', 'str', 'general', 'سعر صرف الدولار للعرض',
     'كم وحدة من عملة النظام تساوي 1$ (مثال 530). للعرض فقط: يُحسب منه السعر بالدولار في بطاقة الخدمة والطلب', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('subscription_required', 'true', 'bool', 'channels', 'الاشتراك الإجباري في القنوات',
     'عند التفعيل لا يستخدم المستخدم العادي البوت قبل الاشتراك في كل القنوات المضبوطة أدناه (الفريق الإداري معفى)', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('channel_official', '', 'str', 'channels', '📢 القناة الرسمية',
     'معرّف القناة: @username أو -100xxxxxxxxxx، ويمكن إضافة رابط الدعوة بعد مسافة (للقنوات الخاصة). فارغ = غير مطلوبة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('channel_proofs', '', 'str', 'channels', '📚 قناة توثيق/متابعة الطلبات',
     'نفس صيغة القناة الرسمية. فارغ = غير مطلوبة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('channel_updates', '', 'str', 'channels', '🔔 قناة التحديثات',
     'نفس صيغة القناة الرسمية. فارغ = غير مطلوبة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('channel_offers', '', 'str', 'channels', '🎁 قناة العروض',
     'نفس صيغة القناة الرسمية. فارغ = غير مطلوبة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('orders_log_chat_id', '', 'str', 'channels', 'قناة توثيق الطلبات الجديدة (للنشر)',
     'قناة يُنشر فيها سجل منظم لكل طلب جديد (بيانات مقنّعة). @username أو -100xxxxxxxxxx. فارغ = لا نشر', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('new_user_alert_enabled', 'true', 'bool', 'channels', 'إشعار الإدارة بالمستخدم الجديد',
     'يُنشر في قناة تنبيهات الإدارة (admin_alert_chat_id) عند تسجيل مستخدم جديد', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
```

---

## `core/constants.py`

```python
"""ثوابت عامة للنظام (قيم لا تتغير أثناء التشغيل)."""

from __future__ import annotations

#: اسم المشروع وإصداره
APP_NAME: str = "SMM Telegram Bot"
APP_VERSION = "1.1.0"

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

---

## `core/money.py`

```python
"""
التعامل مع المال — أعداد صحيحة فقط، بلا أي استخدام لـ float.

المبدأ:
    كل مبلغ في النظام يُخزَّن كعدد صحيح بوحدة «نقطة» = 1/10000 من وحدة العملة.
    مثال: 5.25 ريال  →  52500 نقطة.
    وسعر الألف 1.2345 →  12345 نقطة.

السبب: الحسابات العائمة (float) تُنتج فروقاً صغيرة تتراكم في الأرصدة،
وهو أخطر خطأ ممكن في نظام مالي.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from core.exceptions import InvalidAmountError

#: عدد النقاط في وحدة العملة الواحدة (4 خانات عشرية)
MONEY_SCALE: int = 10_000

#: أقصى مبلغ مسموح في عملية واحدة (حماية من الأخطاء الكارثية عند إدخال رقم ضخم)
MAX_AMOUNT_UNITS: int = 10_000_000 * MONEY_SCALE

#: مقياس نقاط الأساس للرسوم: 10000 نقطة أساس = 100%
FEE_SCALE: int = 10_000

#: أقصى نسبة رسوم مسموح ضبطها لطريقة شحن (100%)
MAX_FEE_PERCENT_BP: int = FEE_SCALE


def to_units(value: str | int | Decimal) -> int:
    """
    تحويل مبلغ مكتوب (نص/عدد صحيح/Decimal) إلى نقاط صحيحة.

    المدخلات: value مثل "12.5" أو Decimal("12.5") أو 12.
    المخرجات: عدد صحيح من النقاط (12.5 → 125000).

    الاستثناءات:
        InvalidAmountError : القيمة غير رقمية أو سالبة أو تتجاوز الحد الأقصى.
    """
    if isinstance(value, float):  # منع الاستخدام الخاطئ صراحةً
        raise InvalidAmountError("ممنوع تمرير float إلى to_units — استخدم نصاً أو Decimal.")
    try:
        dec = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, AttributeError) as exc:
        raise InvalidAmountError(f"قيمة مالية غير صالحة: {value!r}") from exc

    if dec.is_nan() or dec.is_infinite():
        raise InvalidAmountError("قيمة مالية غير صالحة.")
    if dec < 0:
        raise InvalidAmountError("المبلغ لا يمكن أن يكون سالباً.")

    units = int((dec * MONEY_SCALE).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if units > MAX_AMOUNT_UNITS:
        raise InvalidAmountError("المبلغ يتجاوز الحد الأقصى المسموح.")
    return units


def from_units(units: int) -> Decimal:
    """تحويل النقاط الصحيحة إلى Decimal بعملة العرض (125000 → 12.5)."""
    return (Decimal(int(units)) / Decimal(MONEY_SCALE)).quantize(Decimal("0.0001"))


def format_units(units: int, symbol: str = "", decimals: int = 2) -> str:
    """
    تنسيق مبلغ للعرض على المستخدم.

    المدخلات:
        units    : المبلغ بالنقاط.
        symbol   : رمز العملة (مثل "﷼" أو "$").
        decimals : عدد الخانات المعروضة (لا يؤثر على التخزين).

    المخرجات: نص منسّق مثل "12.50 ﷼".
    """
    quant = Decimal(1).scaleb(-decimals)  # 0.01 مثلاً
    amount = from_units(units).quantize(quant, rounding=ROUND_HALF_UP)
    text = f"{amount:,.{decimals}f}"
    return f"{text} {symbol}".strip()


def order_cost_units(price_per_1000_units: int, quantity: int) -> int:
    """
    حساب تكلفة الطلب بدقة كاملة بأعداد صحيحة.

    المعادلة: التكلفة = (سعر الألف × الكمية) ÷ 1000 مع تقريب نصفي لأعلى.

    المدخلات:
        price_per_1000_units : سعر الألف بالنقاط.
        quantity             : الكمية المطلوبة.

    المخرجات: تكلفة الطلب بالنقاط.

    الاستثناءات:
        InvalidAmountError : كمية أو سعر غير صالح.
    """
    if price_per_1000_units <= 0:
        raise InvalidAmountError("سعر الخدمة يجب أن يكون أكبر من صفر.")
    if quantity <= 0:
        raise InvalidAmountError("الكمية يجب أن تكون أكبر من صفر.")
    total = price_per_1000_units * quantity
    cost = (total + 500) // 1000  # تقريب نصفي لأعلى بأعداد صحيحة
    if cost > MAX_AMOUNT_UNITS:
        raise InvalidAmountError("تكلفة الطلب تتجاوز الحد الأقصى المسموح.")
    return cost


def unit_price_units(price_per_1000_units: int) -> Decimal:
    """سعر الوحدة الواحدة (بالنقاط، كـ Decimal لتفادي فقدان الدقة في الحسابات الوسيطة)."""
    return Decimal(price_per_1000_units) / Decimal(1000)


def partial_refund_units(
    *,
    cost_units: int,
    quantity: int,
    remains: int,
    already_refunded_units: int = 0,
) -> int:
    """
    حساب مبلغ الاسترجاع الجزئي لطلب نُفِّذ جزئياً.

    السياسة المعتمدة: يُسترجع ما يقابل الكمية غير المنفَّذة من التكلفة الأصلية.
        الاسترجاع = التكلفة × (المتبقي ÷ الكمية) − ما سبق استرجاعه

    المدخلات:
        cost_units             : تكلفة الطلب الأصلية بالنقاط.
        quantity               : الكمية الأصلية.
        remains                : الكمية غير المنفَّذة كما أبلغ عنها المزود.
        already_refunded_units : ما سبق استرجاعه لهذا الطلب (لمنع الاسترجاع المزدوج).

    المخرجات: مبلغ الاسترجاع بالنقاط (قد يكون 0 إن لم يستحق شيء).
    """
    if quantity <= 0 or cost_units <= 0:
        return 0
    remains = max(0, min(int(remains), int(quantity)))  # ضبط ضمن الحدود المنطقية
    if remains == 0:
        return 0
    refund = (cost_units * remains) // quantity  # تقريب لأسفل لصالح النظام (لا يتجاوز التكلفة)
    refund = min(refund, cost_units)
    remaining_allowed = cost_units - max(0, already_refunded_units)
    return max(0, min(refund, remaining_allowed))


def deposit_fee_units(amount_units: int, *, percent_bp: int = 0, fixed_units: int = 0) -> int:
    """
    حساب رسوم طريقة الشحن على مبلغ حوالة واحدة (أعداد صحيحة فقط).

    لماذا نقاط الأساس (bp)؟
        1 bp = 1/100 من 1%، فـ250 تعني 2.5%. هذا يسمح بكسور النِسب
        (مثل 1.75%) بلا أي استخدام لـfloat.

    المعادلة: الرسوم = (المبلغ × bp + 5000) ÷ 10000  +  الرسوم الثابتة
              (تقريب نصفي لأعلى بأعداد صحيحة)

    المدخلات:
        amount_units : مبلغ الحوالة بالنقاط.
        percent_bp   : النسبة بنقاط الأساس (0..10000).
        fixed_units  : رسوم ثابتة بالنقاط.

    المخرجات: الرسوم بالنقاط (لا تتجاوز أبداً مبلغ الحوالة نفسه).

    الاستثناءات:
        InvalidAmountError : مبلغ سالب أو نسبة/رسوم خارج المدى المسموح.
    """
    amount = int(amount_units)
    percent = int(percent_bp)
    fixed = int(fixed_units)
    if amount < 0:
        raise InvalidAmountError("مبلغ الحوالة لا يمكن أن يكون سالباً.")
    if not 0 <= percent <= MAX_FEE_PERCENT_BP:
        raise InvalidAmountError("نسبة الرسوم يجب أن تكون بين 0% و100%.")
    if fixed < 0:
        raise InvalidAmountError("الرسوم الثابتة لا يمكن أن تكون سالبة.")

    percent_part = (amount * percent + FEE_SCALE // 2) // FEE_SCALE  # تقريب نصفي لأعلى
    fee = percent_part + fixed
    return min(fee, amount)  # الرسوم لا تتجاوز الحوالة مهما كانت الإعدادات


def net_after_fee(amount_units: int, *, percent_bp: int = 0, fixed_units: int = 0) -> tuple[int, int]:
    """
    حساب (الرسوم، الصافي) لمبلغ حوالة بطريقة شحن محددة.

    المخرجات: tuple من (الرسوم بالنقاط، المبلغ الصافي الذي يستحقه المستخدم).

    ملاحظة: الصافي قد يكون صفراً إذا ابتلعت الرسوم المبلغ كله —
            وهي حالة يرفضها `PaymentService` قبل إنشاء الطلب.
    """
    fee = deposit_fee_units(amount_units, percent_bp=percent_bp, fixed_units=fixed_units)
    return fee, max(0, int(amount_units) - fee)


def apply_markup(provider_price_units: int, markup_percent: int) -> int:
    """
    حساب سعر البيع من سعر التكلفة بإضافة نسبة ربح.

    المدخلات:
        provider_price_units : سعر الألف عند المزود بالنقاط.
        markup_percent       : نسبة الربح (مثال 30 تعني +30%).

    المخرجات: سعر البيع بالنقاط (مقرّب نصفياً لأعلى).
    """
    if provider_price_units < 0:
        raise InvalidAmountError("سعر التكلفة غير صالح.")
    if markup_percent < 0:
        raise InvalidAmountError("نسبة الربح لا يمكن أن تكون سالبة.")
    total = provider_price_units * (100 + markup_percent)
    return (total + 50) // 100


#: سعر الصرف الافتراضي للعرض (ريال لكل 1 دولار) عند غياب/فساد الإعداد
DEFAULT_USD_RATE: Decimal = Decimal("530")


def parse_usd_rate(raw: str | None) -> Decimal:
    """
    تحويل نص إعداد `usd_rate` إلى Decimal موجب؛ القيمة الفاسدة أو غير الموجبة ⇒ الافتراضي (للعرض فقط).
    """
    try:
        value = Decimal(str(raw or "").strip().replace(",", ""))
    except InvalidOperation:
        return DEFAULT_USD_RATE
    if not value.is_finite() or value <= 0:
        return DEFAULT_USD_RATE
    return value


def usd_amount(units: int, usd_rate: Decimal) -> Decimal:
    """
    المقابل بالدولار لمبلغ بعملة النظام (للعرض فقط، لا يدخل في أي حساب مالي).

    المخرجات: Decimal بدقة 4 خانات (يُقرَّب عند العرض).
    """
    return (from_units(units) / usd_rate).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def format_usd(units: int, usd_rate: Decimal) -> str:
    """
    تنسيق المقابل بالدولار: خانتان عادةً، وأربع للمبالغ الصغيرة جداً حتى لا يظهر السعر الحقيقي صفراً.

    أمثلة (سعر 530): 530 ريال ⇒ `$1.00` · 10 ريال ⇒ `$0.0189`.
    """
    amount = usd_amount(units, usd_rate)
    if amount != 0 and abs(amount) < Decimal("0.01"):
        return f"${amount:,.4f}"
    return f"${amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"
```

---

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
```

---

## `config.py`

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

from utils.channel_ref import ChannelRefError, normalize_chat_ref
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


def _get_chat_ref(key: str) -> int | str | None:
    """
    قراءة معرّف قناة/محادثة اختياري من البيئة (`-100…` أو `@username` أو `t.me/name`).

    يُصحَّح الخطأ الشائع (رقم قناة بلا `-100`) ويُرفض ما لا يُصلَح برسالة تشرح السبب — بدل أن يظهر
    لاحقاً كـ«Chat not found» عند أول إرسال.
    """
    raw = _get_str(key)
    if raw is None:
        return None
    try:
        return normalize_chat_ref(raw, allow_user_ids=True)
    except ChannelRefError as exc:
        raise ConfigError(f"القيمة في المتغير {key} غير صالحة: {exc}") from exc


def _get_port(key: str) -> int | None:
    """قراءة منفذ اختياري (1..65535)؛ الفراغ ⇒ None."""
    value = _get_int(key)
    if value is None:
        return None
    if not 1 <= value <= 65535:
        raise ConfigError(f"القيمة في المتغير {key} يجب أن تكون منفذاً بين 1 و65535.")
    return value


def _get_ids(key: str) -> tuple[int, ...]:
    """قراءة قائمة معرفات تيليجرام مفصولة بفواصل (مثال: 111,222)."""
    raw = _get_str(key)
    if not raw:
        return ()
    ids: list[int] = []
    # تسامح مع أخطاء اللصق الشائعة في لوحات الاستضافة: أقواس، علامات اقتباس، مسافات، فاصلة عربية
    cleaned = raw.translate(str.maketrans({"[": " ", "]": " ", "'": " ", '"': " ", "،": ","}))
    for part in cleaned.replace(";", ",").replace(" ", ",").split(","):
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
    admin_alert_chat_id: int | str | None
    backup_channel_id: int | str | None
    health_port: int | None = None             # PORT من الاستضافة (Render): يفعّل خادم الصحة الاختياري

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
            admin_alert_chat_id=_get_chat_ref("ADMIN_ALERT_CHAT_ID"),
            backup_channel_id=_get_chat_ref("BACKUP_CHANNEL_ID"),
            health_port=_get_port("PORT"),
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

---

## `main.py`

```python
"""
نقطة تشغيل البوت.

التسلسل الكامل عند الإقلاع:
    1. تحميل الإعدادات من ‎.env‎ والتحقق من وجود التوكن.
    2. تهيئة اللوق (ملف متدحرج + شاشة).
    3. حجز قفل «نسخة واحدة» حتى لا يعمل بوتان على نفس القاعدة.
    4. فتح قاعدة البيانات، وأخذ نسخة أمان قبل أي ترحيل ناقص على قاعدة قائمة، ثم تطبيقه.
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

from telegram import BotCommand, LinkPreviewOptions                  # noqa: E402
from telegram.error import InvalidToken, NetworkError, TimedOut    # noqa: E402
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
from core.enums import BackupType                                   # noqa: E402
from core.exceptions import BackupError                             # noqa: E402
from services.backup_service import create_backup_file              # noqa: E402
from utils.conflict_guard import EXIT_CODE_CONFLICT, ConflictGuard  # noqa: E402
from utils.fs_security import check_paths                            # noqa: E402
from utils.health_server import HealthServer                         # noqa: E402
from utils.logging_setup import get_logger, setup_logging           # noqa: E402
from utils.security import SecretBox, sanitize                      # noqa: E402
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
        if await migrator.applied():
            # قاعدة قائمة ستُرقّى: نسخة أمان أولاً (A13). فشلها يوقف الإقلاع — لا ترقية بلا شبكة أمان.
            try:
                artifact = await create_backup_file(
                    db, config.backup_dir, backup_type=str(BackupType.PRE_OPERATION), app_version=APP_VERSION
                )
            except BackupError as exc:
                await db.close()
                raise SystemExit(
                    f"❌ تعذّر أخذ نسخة أمان قبل ترقية قاعدة البيانات: {exc}\n"
                    "   حرّر مساحة على القرص أو افحص صلاحيات مجلد النسخ ثم أعد التشغيل."
                ) from exc
            logger.info("نسخة أمان قبل الترحيل: %s", artifact.filename)
        applied = await migrator.apply_all()
        logger.info("تم تطبيق الترحيلات: %s", ", ".join(applied))
    logger.info("إصدار مخطط قاعدة البيانات: %s", await migrator.current_version())
    return db


def _health_status(application: Application) -> dict:
    """حالة عامة لخادم الصحة: بلا أي بيانات حسّاسة (إصدار + هل أُوقف الحارس بسبب تعارض)."""
    guard = application.bot_data.get("conflict_guard")
    return {
        "status": "conflict" if guard is not None and guard.tripped else "ok",
        "version": APP_VERSION,
        "recent_conflicts": guard.recent_conflicts if guard is not None else 0,
    }


def build_application(config: Config) -> Application:
    """
    بناء تطبيق تيليجرام وربط كل مكوناته.

    المخرجات: تطبيق جاهز للتشغيل عبر `run_polling`.
    """
    # block=True (الافتراضي): معالجة متسلسلة للتحديث الواحد — لا سباق على الرصيد
    defaults = Defaults(parse_mode=ParseMode.HTML, link_preview_options=LinkPreviewOptions(is_disabled=True))

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
            backup_dir=config.backup_dir,
            backup_channel_id=config.backup_channel_id,
            admin_alert_chat_id=config.admin_alert_chat_id,
            app_version=APP_VERSION,
        )
        application.bot_data["services"] = services
        application.bot_data["config"] = config

        # الأدمن الأعلى من متغيرات البيئة: إنشاء/ترقية/رفع حظر تلقائي عند كل إقلاع (بلا Shell ولا تعديل DB)
        if config.super_admin_ids:
            for outcome in await services.auth.bootstrap_super_admins():
                if outcome.changed:
                    logger.warning("تثبيت الأدمن الأعلى %s من SUPER_ADMIN_IDS: %s", outcome.telegram_id, outcome.action)
            logger.info("الأدمن الأعلى المعتمدون من البيئة: %s", len(config.super_admin_ids))
        else:
            logger.warning("SUPER_ADMIN_IDS غير مضبوط — لن يوجد أدمن أعلى جديد إلا إن كان في قاعدة البيانات أصلاً")

        # خادم الصحة (اختياري): يعمل فقط إن وُفّر PORT (Render Web Service)
        if config.health_port:
            health = HealthServer(config.health_port, lambda: _health_status(application))
            await health.start()
            application.bot_data["health_server"] = health

        await services.backups.sync_catalog()           # يسجّل نسخاً وُجدت على القرص بلا سجل
        await run_startup_recovery(services)
        await schedule_jobs(application, services)
        await application.bot.set_my_commands(BOT_COMMANDS)

        me = await application.bot.get_me()
        logger.info("البوت جاهز: @%s (الإصدار %s)", me.username, APP_VERSION)
        if await services.settings.is_maintenance():
            logger.warning("النظام في وضع الصيانة — المستخدمون سيرون رسالة الصيانة")

    async def post_shutdown(application: Application) -> None:
        """إغلاق الموارد بنظافة بعد توقف التطبيق."""
        health = application.bot_data.get("health_server")
        if health is not None:
            await health.stop()
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

    المخرجات: رمز خروج للنظام (0 إيقاف سليم، 1 خطأ إعداد أو فشل إقلاع/انهيار، 2 نسخة تعمل بالفعل محلياً،
    3 تعارض getUpdates مستمر مع نسخة أخرى بنفس التوكن).

    أخطاء الإقلاع (توكن مرفوض، شبكة، انهيار) تُلتقط وتُطبع منقّاة من الأسرار: رسالة استثناء
    تيليجرام تحمل التوكن كاملاً، وتتبّع الاستثناء الخام كان سيُكتب في journald/الطرفية.
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

    exit_code = 0
    try:
        application = build_application(config)
        guard = ConflictGuard(application.stop_running)
        application.bot_data["conflict_guard"] = guard
        # drop_pending_updates: تجاهل ما تراكم أثناء التوقف حتى لا تُنفَّذ ضغطات
        # أزرار قديمة على حالة تغيّرت — الطلبات نفسها تُستأنف من قاعدة البيانات.
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "my_chat_member"],
            error_callback=guard.on_polling_error,
        )
        if guard.tripped:
            exit_code = EXIT_CODE_CONFLICT
            print(
                "❌ تعارض مستمر: نسخة أخرى تستخدم نفس التوكن (Conflict getUpdates). أُوقفت هذه النسخة بأمان.\n"
                "   أوقف النسخة الزائدة (محلية/Render قديمة/خدمة ثانية) أو استعمل توكناً منفصلاً للتطوير.",
                file=sys.stderr,
            )
    except (KeyboardInterrupt, SystemExit):
        logger.info("إيقاف البوت بطلب من المشغّل")
    except InvalidToken:
        exit_code = 1
        logger.critical("رفض تيليجرام التوكن (BOT_TOKEN) — انسخه من @BotFather من جديد")
        print("❌ رفض تيليجرام التوكن — راجع BOT_TOKEN في ملف .env (انسخه كاملاً من @BotFather).", file=sys.stderr)
    except (NetworkError, TimedOut) as exc:
        exit_code = 1
        logger.critical("تعذّر الاتصال بتيليجرام عند الإقلاع: %s", sanitize(str(exc)))
        print("❌ تعذّر الاتصال بتيليجرام — تحقق من الشبكة/الجدار الناري ثم أعد التشغيل.", file=sys.stderr)
    except Exception:  # noqa: BLE001 - آخر حاجز: نسجّل التتبّع منقّىً ونخرج برمز فشل بدل traceback خام
        exit_code = 1
        logger.critical("انهيار غير متوقع أثناء التشغيل", exc_info=True)
        print("❌ انهيار غير متوقع — التفاصيل في ملف اللوق (الأسرار مُنقّاة).", file=sys.stderr)
    finally:
        lock.release()
        logger.info("انتهى التشغيل")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
```

---

## `utils/channel_ref.py`

```python
"""
قراءة وتطبيع معرّفات القنوات/المحادثات التي يكتبها المالك في الإعدادات أو متغيرات البيئة.

لماذا ملف مستقل؟
    «Chat not found» من أكثر أخطاء تيليجرام شيوعاً عند ضبط القنوات، وسببها شبه دائم صيغة المعرّف:
        • رقم قناة بلا `-100` في أوله (يعيد تيليجرام «chat not found»)؛
        • رابط دعوة `t.me/+xxxx` وُضع مكان المعرّف (لا يصلح للإرسال ولا للتحقق من العضوية)؛
        • @username بإملاء خاطئ.
    هنا نُطبّع ما يمكن تطبيعه بأمان، ونرفض الباقي برسالة عربية تقول ما الخطأ بالضبط وكيف يُصلَح.

الصيغة المقبولة في إعداد قناة: `المعرّف` أو `المعرّف رابط_دعوة` (الرابط اختياري ويلزم للقنوات الخاصة
حتى يظهر زر «انضمام» للمستخدم).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from utils.validators import normalize_digits

#: اسم مستخدم تيليجرام الصالح (5–32 حرفاً، يبدأ بحرف)
_USERNAME_RE: Final = re.compile(r"[A-Za-z][A-Za-z0-9_]{4,31}")
#: روابط تيليجرام المقبولة كرابط دعوة/انضمام
_LINK_RE: Final = re.compile(r"https://(?:t\.me|telegram\.me)/[A-Za-z0-9_+/\-]{3,100}", re.IGNORECASE)
#: رابط عام لقناة بمعرّفها: t.me/name (ليس +invite ولا joinchat ولا c/)
_PUBLIC_LINK_RE: Final = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/(?P<name>[A-Za-z][A-Za-z0-9_]{4,31})/?", re.IGNORECASE
)


class ChannelRefError(ValueError):
    """معرّف قناة غير صالح؛ نص الاستثناء رسالة عربية جاهزة للعرض."""


@dataclass(frozen=True, slots=True)
class ChannelRef:
    """قناة بعد التطبيع: المعرّف (رقم أو @username) ورابط انضمام اختياري."""

    chat_id: int | str
    link: str | None = None

    @property
    def canonical(self) -> str:
        """الصيغة القياسية للتخزين: `المعرّف` أو `المعرّف الرابط`."""
        return f"{self.chat_id} {self.link}" if self.link else str(self.chat_id)

    @property
    def join_url(self) -> str | None:
        """رابط يفتحه المستخدم للانضمام: الرابط المُدخل، وإلا رابط @username العام، وإلا None."""
        if self.link:
            return self.link
        if isinstance(self.chat_id, str) and self.chat_id.startswith("@"):
            return f"https://t.me/{self.chat_id[1:]}"
        return None


def normalize_chat_ref(raw: object, *, allow_user_ids: bool = False) -> int | str:
    """
    تطبيع معرّف محادثة إلى رقم (`-100…`) أو `@username`.

    المدخلات:
        allow_user_ids : السماح بمعرّف موجب (محادثة خاصة مع شخص) — لقناة تنبيهات الإدارة فقط؛ القنوات
                         والمجموعات دائماً سالبة.

    الاستثناءات:
        ChannelRefError : صيغة غير صالحة (الرسالة تشرح السبب والحل).
    """
    text = normalize_digits(str(raw if raw is not None else "")).strip()
    if not text:
        raise ChannelRefError("المعرّف فارغ.")

    if "+" in text and ("t.me" in text.lower() or "telegram.me" in text.lower()):
        raise ChannelRefError(
            "هذا رابط دعوة وليس معرّف قناة. اكتب معرّف القناة (-100xxxxxxxxxx أو @username) "
            "ثم ضع رابط الدعوة بعده بمسافة."
        )
    if "joinchat" in text.lower():
        raise ChannelRefError("رابط joinchat لا يصلح معرّفاً. اكتب -100xxxxxxxxxx أو @username.")

    public = _PUBLIC_LINK_RE.fullmatch(text)
    if public:
        return f"@{public.group('name')}"

    if text.startswith("@"):
        if not _USERNAME_RE.fullmatch(text[1:]):
            raise ChannelRefError("اسم المستخدم غير صالح: 5–32 حرفاً إنجليزياً/أرقاماً/شرطة سفلية ويبدأ بحرف.")
        return text

    if re.fullmatch(r"-?\d{5,20}", text):
        number = int(text)
        if number > 0 and text.startswith("100") and len(text) >= 12:
            return -number                  # -100 ناقصة: خطأ شائع، والتصحيح آمن (لا معرّف مستخدم بهذا الطول)
        if number > 0 and not allow_user_ids:
            raise ChannelRefError(
                "معرّف القناة أو المجموعة يكون سالباً ويبدأ بـ -100 (مثال -1001234567890). "
                "انسخه من بوت مثل @userinfobot أو @getidsbot بتحويل رسالة من القناة إليه."
            )
        return number

    if _USERNAME_RE.fullmatch(text):
        return f"@{text}"                   # اسم بلا @ — نصحّحه
    raise ChannelRefError("صيغة غير مفهومة. استخدم -100xxxxxxxxxx أو @username.")


def parse_channel_value(raw: object, *, allow_user_ids: bool = False) -> ChannelRef:
    """
    قراءة قيمة إعداد قناة: `المعرّف [رابط الدعوة]`.

    الاستثناءات: ChannelRefError عند أي صيغة غير صالحة.
    """
    text = normalize_digits(str(raw if raw is not None else "")).strip()
    if not text:
        raise ChannelRefError("القيمة فارغة.")
    parts = text.split()
    if len(parts) > 2:
        raise ChannelRefError("الصيغة: المعرّف ثم (اختيارياً) رابط الدعوة، بمسافة واحدة بينهما.")

    # رابط عام وحده (t.me/name) يُقرأ معرّفاً؛ أما رابط الدعوة +xxx فيُرفض في normalize_chat_ref
    chat_id = normalize_chat_ref(parts[0], allow_user_ids=allow_user_ids)
    link: str | None = None
    if len(parts) == 2:
        if not _LINK_RE.fullmatch(parts[1]):
            raise ChannelRefError("رابط الدعوة يجب أن يكون https://t.me/... كاملاً.")
        link = parts[1]
    return ChannelRef(chat_id=chat_id, link=link)


def try_parse_chat_id(raw: object, *, allow_user_ids: bool = True) -> int | str | None:
    """معرّف المحادثة من نص إعداد، أو None إن كان فارغاً/غير صالح (للاستخدام في مسارات لا ترفع)."""
    text = str(raw if raw is not None else "").strip()
    if not text:
        return None
    try:
        return parse_channel_value(text, allow_user_ids=allow_user_ids).chat_id
    except ChannelRefError:
        return None
```

---

## `utils/privacy.py`

```python
"""
إخفاء البيانات الحساسة قبل نشرها في القنوات (توثيق الطلبات، إشعارات الإدارة).

القناة قد يراها عدد كبير من الناس، لذلك: المعرّف الرقمي يُقنَّع، والرابط يُظهر المنصة فقط بلا الحساب/المنشور.
"""

from __future__ import annotations

from urllib.parse import urlparse

#: الرمز الذي يحل محل الأجزاء المخفية
MASK_CHAR = "•"


def mask_telegram_id(telegram_id: int | str) -> str:
    """إظهار أول رقمين فقط من معرّف تيليجرام: `1712345678` ⇒ `17••••••••`."""
    text = str(telegram_id).strip().lstrip("-")
    if len(text) <= 2:
        return MASK_CHAR * 4
    return text[:2] + MASK_CHAR * (len(text) - 2)


def mask_link(link: str | None) -> str:
    """
    إخفاء مسار الرابط وإبقاء النطاق: `https://instagram.com/user/p/xyz` ⇒ `https://instagram.com/••••`.

    الرابط الذي يتعذر تحليله يُعاد مقنّعاً كلياً (لا نكشف نصاً لا نفهمه).
    """
    text = (link or "").strip()
    if not text:
        return MASK_CHAR * 4
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        return f"https://{MASK_CHAR * 4}"
    has_path = bool((parsed.path or "").strip("/")) or bool(parsed.query)
    return f"https://{host}/{MASK_CHAR * 4}" if has_path else f"https://{host}"


def mask_username(username: str | None) -> str:
    """اسم المستخدم كما هو (معلومة عامة في تيليجرام) أو «—» إن لم يوجد."""
    clean = (username or "").strip().lstrip("@")
    return f"@{clean}" if clean else "—"
```

---

## `utils/conflict_guard.py`

```python
"""
حارس «Conflict» في getUpdates: يُميّز التعارض العابر عن تشغيل نسختين دائماً بنفس التوكن.

الخلفية:
    تيليجرام يسمح لعملية **واحدة** فقط بـ`getUpdates` لكل توكن؛ الثانية تتلقى `Conflict: terminated by other
    getUpdates request`. هذا **ليس خطأ كود** بل بيئة تشغيل: نسخة محلية ما زالت تعمل، أو نشر Render يتداخل فيه
    القديم مع الجديد دقائق، أو خدمتان بنفس التوكن، أو Webhook مفعّل.

السياسة:
    • أول تعارض ⇒ تحذير يشرح الأسباب وطريقة الحل (لا traceback مزعج).
    • تعارض **عابر** (نشر متداخل) يزول وحده ⇒ نتابع بلا تدخل.
    • تعارض **مستمر** (≥ `MIN_EVENTS` أحداث على امتداد ≥ `PERSIST_SECONDS`) ⇒ إيقاف آمن للنسخة الخاسرة
      (إغلاق نظيف + رمز خروج مميّز) بدل حلقة أبدية تتنازع فيها النسختان على الرسائل وتُضاعف الإشعارات.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

from telegram.error import Conflict, TelegramError

from utils.logging_setup import get_logger
from utils.security import sanitize

logger = get_logger(__name__)

#: رمز الخروج عند الإيقاف بسبب تعارض مستمر (يميّزه المشغّل ومراقب الخدمة عن الانهيار=1)
EXIT_CODE_CONFLICT = 3

#: أقل عدد تعارضات لاعتباره مستمراً
MIN_EVENTS = 5
#: أقل امتداد زمني (ثانية) بين أول تعارض وآخره لاعتباره مستمراً لا عابراً
PERSIST_SECONDS = 60.0
#: نافذة الاحتفاظ بالأحداث (ثانية): ما أقدم منها يُنسى فيُعدّ التعارض قد زال
WINDOW_SECONDS = 180.0

GUIDANCE = (
    "تعارض getUpdates: نسخة أخرى من البوت تستخدم نفس التوكن الآن. الأسباب المعتادة: "
    "(1) نسخة محلية/جهاز آخر ما زال يعمل، (2) نشر Render قديم لم يُوقَف بعد أو خدمتان بنفس التوكن، "
    "(3) عملية بوت أخرى على نفس السيرفر. الحل: أوقف النسخة الزائدة (أو أنشئ توكناً منفصلاً للتطوير)."
)


class ConflictGuard:
    """يُمرَّر `on_polling_error` إلى `run_polling(error_callback=...)`."""

    def __init__(
        self,
        stop: Callable[[], None],
        *,
        min_events: int = MIN_EVENTS,
        persist_seconds: float = PERSIST_SECONDS,
        window_seconds: float = WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """
        تهيئة الحارس.

        المدخلات:
            stop : دالة الإيقاف الآمن (`application.stop_running`) — تُستدعى مرة واحدة عند التعارض المستمر.
        """
        self._stop = stop
        self._min_events = min_events
        self._persist_seconds = persist_seconds
        self._window_seconds = window_seconds
        self._clock = clock
        self._events: deque[float] = deque()
        self._warned = False
        self.tripped = False

    def on_polling_error(self, error: TelegramError) -> None:
        """
        معالجة خطأ من حلقة الاستقبال (دالة متزامنة كما يشترط PTB).

        غير التعارض: يُسجَّل تحذيراً منقّىً (رسالة تيليجرام قد تحمل التوكن) والمكتبة تعيد المحاولة وحدها.
        """
        if not isinstance(error, Conflict):
            logger.warning("خطأ مؤقت في استقبال التحديثات: %s: %s", type(error).__name__, sanitize(str(error))[:200])
            return

        now = self._clock()
        self._events.append(now)
        while self._events and now - self._events[0] > self._window_seconds:
            self._events.popleft()

        if not self._warned:
            self._warned = True
            logger.warning("%s", GUIDANCE)
        if self.tripped:
            return

        persistent = len(self._events) >= self._min_events and now - self._events[0] >= self._persist_seconds
        if persistent:
            self.tripped = True
            logger.critical(
                "تعارض مستمر منذ %.0f ثانية (%s حدثاً) — إيقاف هذه النسخة بأمان. %s",
                now - self._events[0], len(self._events), GUIDANCE,
            )
            self._stop()

    @property
    def recent_conflicts(self) -> int:
        """عدد التعارضات ضمن النافذة الحالية (للتشخيص)."""
        now = self._clock()
        return sum(1 for moment in self._events if now - moment <= self._window_seconds)
```

---

## `utils/health_server.py`

```python
"""
خادم فحص صحة اختياري (HTTP خفيف) لاستضافات تشترط منفذاً مفتوحاً مثل Render Web Service.

يعمل **فقط** إن وُجد المتغير `PORT`. لا يكشف أي بيانات حسّاسة: الاستجابة حالة عامة + رقم الإصدار.
المسارات: `GET /` و`GET /health` و`GET /healthz` ⇒ 200 JSON؛ غيرها ⇒ 404؛ غير GET ⇒ 405.
الحماية: حجم الطلب ≤ 4KB ومهلة قراءة 5ث وإغلاق الاتصال بعد كل رد (لا اتصالات معلّقة).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: أقصى حجم لرأس الطلب المقبول (بايت)
MAX_REQUEST_BYTES = 4096
#: مهلة قراءة الطلب (ثانية)
READ_TIMEOUT_SECONDS = 5.0
HEALTH_PATHS = frozenset({"/", "/health", "/healthz"})


class HealthServer:
    """خادم صحة ينتج حالة من دالة يمررها المشغّل (بلا أسرار)."""

    def __init__(self, port: int, status: Callable[[], dict], *, host: str = "0.0.0.0") -> None:  # noqa: S104
        """
        تهيئة الخادم (لا يبدأ قبل `start`).

        المدخلات:
            status : دالة تُرجع قاموساً قابلاً لـJSON يصف الحالة العامة.
        """
        self.port = port
        self.host = host
        self._status = status
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> int:
        """بدء الاستماع وإرجاع المنفذ الفعلي (مفيد حين يكون `port=0` في الاختبارات)."""
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        sockets = self._server.sockets or []
        actual = sockets[0].getsockname()[1] if sockets else self.port
        logger.info("خادم الصحة يعمل على %s:%s", self.host, actual)
        return int(actual)

    async def stop(self) -> None:
        """إيقاف الخادم وانتظار إغلاق اتصالاته."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """قراءة سطر الطلب والرد عليه ثم إغلاق الاتصال."""
        try:
            try:
                raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), READ_TIMEOUT_SECONDS)
            except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
                return
            if len(raw) > MAX_REQUEST_BYTES:
                return
            line = raw.split(b"\r\n", 1)[0].decode("latin-1", errors="replace").split()
            method, path = (line[0], line[1].split("?", 1)[0]) if len(line) >= 2 else ("", "")
            if not method:
                code, body = 400, {"error": "bad request"}
            elif method not in {"GET", "HEAD"}:
                code, body = 405, {"error": "method not allowed"}
            elif path not in HEALTH_PATHS:
                code, body = 404, {"error": "not found"}
            else:
                code, body = 200, self._status()
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            reasons = {200: "OK", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed"}
            head = (
                f"HTTP/1.1 {code} {reasons[code]}\r\nContent-Type: application/json; charset=utf-8\r\n"
                f"Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n"
            ).encode("latin-1")
            writer.write(head + (b"" if method == "HEAD" else payload))
            await writer.drain()
        except (ConnectionError, OSError):
            logger.debug("انقطع اتصال فحص الصحة قبل اكتمال الرد")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                logger.debug("تعذّر إغلاق اتصال فحص الصحة بنظافة")
```

---

## `utils/link_rules.py`

```python
"""
قواعد التحقق من رابط الطلب حسب المنصة ونوع الهدف (حساب مقابل منشور...).

لماذا؟ رابط خاطئ يعني طلباً مدفوعاً يُرسَل للمزود ثم يفشل أو يُنفَّذ على هدف غير مقصود. لذلك
يُرفض الرابط **قبل** إنشاء الطلب وقبل أي خصم، مع رسالة عربية تقول ما المطلوب بالضبط ومثال صحيح.

المبدأ: كل خدمة تحمل `link_rule` اختيارياً (مفتاح من `LINK_RULES`)؛ بلا قاعدة ⇒ يبقى التحقق
العام فقط (بروتوكول/نطاق/طول) كما كان. تُحدَّد القاعدة تلقائياً عند الاستيراد (`infer_rule`)
ويمكن للأدمن تعديلها من بطاقة الخدمة.

الملف نقيّ: لا قاعدة بيانات ولا شبكة؛ كل الدوال حتمية وقابلة للاختبار.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from core.exceptions import InvalidLinkError

# ========================================================================= #
#                               تعريف القواعد                               #
# ========================================================================= #

#: أنواع الأهداف
KIND_PROFILE = "profile"
KIND_POST = "post"


@dataclass(frozen=True)
class Platform:
    """منصة: نطاقاتها المقبولة واسمها العربي."""

    key: str
    label: str
    hosts: frozenset[str]


@dataclass(frozen=True)
class LinkRule:
    """قاعدة رابط: منصة + نوع هدف + مثال صحيح يُعرض للمستخدم."""

    key: str
    platform: str
    kind: str
    label: str
    example: str


PLATFORMS: dict[str, Platform] = {
    "instagram": Platform("instagram", "انستغرام", frozenset({"instagram.com", "instagr.am"})),
    "tiktok": Platform("tiktok", "تيك توك", frozenset({"tiktok.com", "vm.tiktok.com", "vt.tiktok.com"})),
    "youtube": Platform("youtube", "يوتيوب", frozenset({"youtube.com", "youtu.be"})),
    "telegram": Platform("telegram", "تيليجرام", frozenset({"t.me", "telegram.me"})),
    "facebook": Platform("facebook", "فيسبوك", frozenset({"facebook.com", "fb.com", "fb.watch"})),
    "x": Platform("x", "إكس (تويتر)", frozenset({"x.com", "twitter.com"})),
}

_RULES = (
    LinkRule("instagram_profile", "instagram", KIND_PROFILE, "حساب انستغرام", "https://instagram.com/username"),
    LinkRule("instagram_post", "instagram", KIND_POST, "منشور/ريلز انستغرام", "https://instagram.com/p/AbCdEf123/"),
    LinkRule("tiktok_profile", "tiktok", KIND_PROFILE, "حساب تيك توك", "https://tiktok.com/@username"),
    LinkRule("tiktok_video", "tiktok", KIND_POST, "فيديو تيك توك", "https://tiktok.com/@username/video/1234567890"),
    LinkRule("youtube_channel", "youtube", KIND_PROFILE, "قناة يوتيوب", "https://youtube.com/@channel"),
    LinkRule("youtube_video", "youtube", KIND_POST, "فيديو يوتيوب", "https://youtube.com/watch?v=AbCdEfGhIjK"),
    LinkRule("telegram_channel", "telegram", KIND_PROFILE, "قناة/مجموعة تيليجرام", "https://t.me/channelname"),
    LinkRule("telegram_post", "telegram", KIND_POST, "منشور تيليجرام", "https://t.me/channelname/123"),
    LinkRule("facebook_page", "facebook", KIND_PROFILE, "صفحة/حساب فيسبوك", "https://facebook.com/pagename"),
    LinkRule("facebook_post", "facebook", KIND_POST, "منشور فيسبوك", "https://facebook.com/pagename/posts/1234567890"),
    LinkRule("x_profile", "x", KIND_PROFILE, "حساب إكس", "https://x.com/username"),
    LinkRule("x_post", "x", KIND_POST, "تغريدة إكس", "https://x.com/username/status/1234567890"),
)

#: القواعد بحسب مفتاحها (الترتيب هو ترتيب العرض للأدمن)
LINK_RULES: dict[str, LinkRule] = {rule.key: rule for rule in _RULES}

#: الأجزاء الأولى المحجوزة في روابط انستغرام (ليست أسماء مستخدمين)
_IG_RESERVED = frozenset(
    {"p", "reel", "reels", "tv", "stories", "explore", "accounts", "direct", "about", "legal", "web", "developer", "challenge"}
)
_USER = r"[A-Za-z0-9._]{1,30}"
_FB_RESERVED = frozenset(
    {"watch", "groups", "events", "marketplace", "gaming", "login", "help", "policies", "privacy", "reel", "share", "story.php", "permalink.php", "photo", "photo.php", "video.php", "sharer", "sharer.php", "dialog", "plugins", "tr"}
)


# ========================================================================= #
#                               تحليل الرابط                                #
# ========================================================================= #


@dataclass(frozen=True)
class _Parsed:
    """الرابط بعد التفكيك: نطاق مبسّط (بلا www/m)، المسار، الاستعلام."""

    host: str
    path: str
    query: dict[str, list[str]]


def _parse(link: str) -> _Parsed | None:
    """تفكيك الرابط إلى (نطاق، مسار، استعلام)؛ None إن تعذّر."""
    text = (link or "").strip()
    try:
        parsed = urlparse(text if "://" in text else f"https://{text}")
        host = (parsed.hostname or "").lower()
    except ValueError:
        return None
    for prefix in ("www.", "m.", "mobile.", "web."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    if not host:
        return None
    path = parsed.path or "/"
    return _Parsed(host=host, path=path, query=parse_qs(parsed.query))


def detect_platform(link: str) -> str | None:
    """المنصة التي ينتمي إليها الرابط (من نطاقه) أو None إن لم تكن منصة معروفة."""
    parsed = _parse(link)
    if parsed is None:
        return None
    for key, platform in PLATFORMS.items():
        if parsed.host in platform.hosts or any(parsed.host.endswith("." + h) for h in platform.hosts):
            return key
    return None


def _segments(path: str) -> list[str]:
    """أجزاء المسار غير الفارغة."""
    return [part for part in path.split("/") if part]


# ------------------------------ مطابقات الأنواع ------------------------------ #


def _instagram_kind(p: _Parsed) -> str | None:
    """نوع رابط انستغرام: post (p/reel/tv) أو profile أو None."""
    seg = _segments(p.path)
    if not seg:
        return None
    if seg[0].lower() in {"p", "reel", "reels", "tv"} and len(seg) >= 2:
        return KIND_POST
    if len(seg) >= 3 and seg[1].lower() in {"p", "reel", "tv"} and re.fullmatch(_USER, seg[0]):
        return KIND_POST
    if seg[0].lower() in _IG_RESERVED:
        return None
    if len(seg) == 1 and re.fullmatch(_USER, seg[0]):
        return KIND_PROFILE
    return None


def _tiktok_kind(p: _Parsed) -> str | None:
    """نوع رابط تيك توك: الفيديو `/@user/video/ID` أو الرابط المختصر، والحساب `/@user`."""
    seg = _segments(p.path)
    if p.host in {"vm.tiktok.com", "vt.tiktok.com"}:
        return KIND_POST if len(seg) == 1 else None
    if not seg or not seg[0].startswith("@") or not re.fullmatch(r"@[A-Za-z0-9._]{2,30}", seg[0]):
        if len(seg) == 2 and seg[0] == "t":  # tiktok.com/t/CODE (مختصر)
            return KIND_POST
        return None
    if len(seg) == 1:
        return KIND_PROFILE
    if len(seg) >= 3 and seg[1] in {"video", "photo"} and seg[2].isdigit():
        return KIND_POST
    return None


def _youtube_kind(p: _Parsed) -> str | None:
    """نوع رابط يوتيوب: فيديو (watch/shorts/live/youtu.be) أو قناة (@/channel/c/user)."""
    seg = _segments(p.path)
    if p.host == "youtu.be":
        return KIND_POST if len(seg) == 1 else None
    if not seg:
        return None
    if seg[0] == "watch":
        return KIND_POST if p.query.get("v") and re.fullmatch(r"[\w-]{6,20}", p.query["v"][0]) else None
    if seg[0] in {"shorts", "live", "embed"} and len(seg) == 2:
        return KIND_POST
    if seg[0].startswith("@") and len(seg[0]) > 1 and len(seg) <= 2:
        return KIND_PROFILE
    if seg[0] in {"channel", "c", "user"} and len(seg) >= 2:
        return KIND_PROFILE
    return None


def _telegram_kind(p: _Parsed) -> str | None:
    """نوع رابط تيليجرام: قناة/مجموعة (اسم أو دعوة) أو منشور (اسم/رقم، c/ID/رقم)."""
    seg = _segments(p.path)
    if not seg:
        return None
    first = seg[0]
    if first.startswith("+") and len(first) > 4 and len(seg) == 1:
        return KIND_PROFILE
    if first == "joinchat" and len(seg) == 2:
        return KIND_PROFILE
    if first == "c" and len(seg) == 3 and seg[1].isdigit() and seg[2].isdigit():
        return KIND_POST
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", first):
        return None
    if len(seg) == 1:
        return KIND_PROFILE
    if len(seg) == 2 and seg[1].isdigit():
        return KIND_POST
    return None


def _facebook_kind(p: _Parsed) -> str | None:
    """نوع رابط فيسبوك: منشور/فيديو/مشاركة أو صفحة/حساب (تساهل مقصود لتنوع الروابط)."""
    seg = _segments(p.path)
    if p.host == "fb.watch":
        return KIND_POST if seg else None
    if not seg:
        return None
    first = seg[0].lower()
    if first in {"permalink.php", "story.php", "photo.php", "photo", "video.php", "watch", "reel"}:
        return KIND_POST
    if first == "share" and len(seg) >= 2:
        return KIND_POST
    if first == "profile.php":
        return KIND_PROFILE if p.query.get("id") else None
    if first == "pages" and len(seg) >= 2:
        return KIND_PROFILE
    if first in _FB_RESERVED or first == "groups":
        return None
    if not re.fullmatch(r"[A-Za-z0-9.\-]{3,60}", seg[0]):
        return None
    if len(seg) == 1:
        return KIND_PROFILE
    if len(seg) >= 3 and seg[1].lower() in {"posts", "videos", "photos", "reel"}:
        return KIND_POST
    return None


def _x_kind(p: _Parsed) -> str | None:
    """نوع رابط إكس: تغريدة `/user/status/ID` أو حساب `/user`."""
    seg = _segments(p.path)
    if not seg:
        return None
    if len(seg) >= 3 and seg[1] == "status" and seg[2].isdigit() and re.fullmatch(r"[A-Za-z0-9_]{1,15}", seg[0]):
        return KIND_POST
    if len(seg) == 1 and re.fullmatch(r"[A-Za-z0-9_]{1,15}", seg[0]) and seg[0].lower() not in {"home", "explore", "i", "search", "settings", "login", "share", "intent", "hashtag", "messages", "notifications"}:
        return KIND_PROFILE
    return None


_KIND_DETECTORS = {
    "instagram": _instagram_kind,
    "tiktok": _tiktok_kind,
    "youtube": _youtube_kind,
    "telegram": _telegram_kind,
    "facebook": _facebook_kind,
    "x": _x_kind,
}

_KIND_LABELS = {KIND_PROFILE: "حساب/قناة", KIND_POST: "منشور/فيديو"}


def detect(link: str) -> tuple[str, str | None] | None:
    """
    تصنيف رابط: (المنصة، نوع الهدف أو None إن لم يُعرف النوع)، أو None إن لم تُعرف المنصة.
    """
    platform = detect_platform(link)
    if platform is None:
        return None
    parsed = _parse(link)
    assert parsed is not None
    return platform, _KIND_DETECTORS[platform](parsed)


# ========================================================================= #
#                                 التحقق                                    #
# ========================================================================= #


def rule_of(key: str | None) -> LinkRule | None:
    """القاعدة من مفتاحها؛ None للمفتاح الفارغ أو غير المعروف."""
    return LINK_RULES.get(key or "")


def check_link_rule(link: str, rule_key: str | None) -> None:
    """
    التحقق من أن الرابط يطابق قاعدة الخدمة، وإلا `InvalidLinkError` برسالة عربية دقيقة.

    ثلاث حالات رفض بثلاث رسائل مختلفة كي يعرف العميل ما الخطأ:
        1. منصة مختلفة (رابط تيك توك لخدمة انستغرام).
        2. المنصة صحيحة لكن النوع خاطئ (رابط منشور لخدمة تتطلب حساباً، والعكس).
        3. رابط مشوّه/غير مدعوم (لا يشبه أي رابط للمنصة).

    مفتاح فارغ ⇒ لا قيد إضافي. مفتاح غير معروف (قاعدة تالفة في القاعدة) ⇒ نتجاهله ونسمح بالطلب
    بدل إسقاطه بخطأ إعدادي غامض — التحقق العام قد جرى مسبقاً.
    """
    rule = rule_of(rule_key)
    if rule is None:
        return
    platform = PLATFORMS[rule.platform]
    example = f"\nمثال صحيح: {rule.example}"
    expected = f"{_KIND_LABELS[rule.kind]} {platform.label}"

    found = detect(link)
    if found is None or found[0] != rule.platform:
        other = PLATFORMS[found[0]].label if found else None
        reason = (
            f"❌ هذا رابط {other} والخدمة خاصة بـ{platform.label}."
            if other
            else f"❌ الرابط لا يبدو رابط {platform.label}."
        )
        raise InvalidLinkError(
            f"رابط من منصة مختلفة: المطلوب {rule.platform} والمُدخل {found[0] if found else 'غير معروف'}",
            user_message=f"{reason}\nهذه الخدمة تتطلب رابط {expected}.{example}",
        )

    kind = found[1]
    if kind == rule.kind:
        return
    if kind is None:
        raise InvalidLinkError(
            f"رابط {rule.platform} غير مفهوم (المطلوب {rule.kind})",
            user_message=f"❌ الرابط غير صحيح. هذه الخدمة تتطلب رابط {expected}.{example}",
        )
    given = _KIND_LABELS[kind]
    raise InvalidLinkError(
        f"نوع رابط خاطئ: المطلوب {rule.kind} والمُدخل {kind}",
        user_message=f"❌ هذا رابط {given} والخدمة تتطلب رابط {expected}.{example}",
    )


# ========================================================================= #
#                          استنتاج القاعدة عند الاستيراد                     #
# ========================================================================= #

_PLATFORM_WORDS = {
    "instagram": ("instagram", "insta", "انستغرام", "انستجرام", "انستا", "إنستغرام", "إنستجرام"),
    "tiktok": ("tiktok", "tik tok", "تيك توك", "تيكتوك"),
    "youtube": ("youtube", "يوتيوب"),
    "telegram": ("telegram", "تيليجرام", "تلغرام", "تليجرام", "تلجرام"),
    "facebook": ("facebook", "فيسبوك", "فيس بوك"),
    "x": ("twitter", "تويتر", "إكس", " x "),
}
_PROFILE_WORDS = ("follower", "subscriber", "member", "متابع", "مشترك", "اعضاء", "أعضاء", "عضو", "page like", "لايكات صفحة")
_POST_WORDS = (
    "like", "view", "comment", "share", "save", "impression", "reach", "repost", "retweet", "watch",
    "لايك", "اعجاب", "إعجاب", "مشاهد", "تعليق", "مشاركة", "حفظ", "ريتويت", "وصول", "ظهور",
)


def infer_rule(*texts: str | None) -> str | None:
    """
    استنتاج `link_rule` من اسم الخدمة (وتصنيفها) عند الاستيراد؛ None إن لم يتضح.

    متحفظ عمداً: لا نُرجع قاعدة إلا إذا ظهرت **منصة واحدة فقط** و**نوع واحد واضح** (حساب أو منشور)
    كي لا نمنع طلبات صحيحة بسبب تخمين. وفي الحالة الملتبسة يبقى بلا قاعدة ويضبطها الأدمن يدوياً.
    """
    haystack = " " + " ".join((t or "") for t in texts).lower() + " "
    platforms = [k for k, words in _PLATFORM_WORDS.items() if any(w in haystack for w in words)]
    if len(platforms) != 1:
        return None
    # الأسماء تُفحص أولاً: «likes» منشور حتى لو ورد «followers» في وصف التصنيف
    name = " " + (texts[0] or "").lower() + " "
    is_profile = any(w in name for w in _PROFILE_WORDS)
    is_post = any(w in name for w in _POST_WORDS)
    if is_profile == is_post:
        return None
    platform = platforms[0]
    kind = KIND_PROFILE if is_profile else KIND_POST
    for rule in _RULES:
        if rule.platform == platform and rule.kind == kind:
            return rule.key
    return None


def rule_label(key: str | None) -> str:
    """وصف عربي للقاعدة لبطاقة الأدمن: «حساب انستغرام» أو «بلا قيد»."""
    rule = rule_of(key)
    return rule.label if rule else "بلا قيد (تحقق عام فقط)"
```

---

## `utils/validators.py`

```python
"""
التحقق من مدخلات المستخدم.

كل مُدخل قادم من تيليجرام يمر من هنا قبل أن يصل إلى طبقة الخدمات:
لا رابط بلا فحص، ولا كمية بلا حدود، ولا مبلغ بلا تحقق.
كل دالة إما تُرجع قيمة نظيفة جاهزة للتخزين أو ترفع استثناءً برسالة عربية واضحة.
"""

from __future__ import annotations

import re
from decimal import Decimal
from urllib.parse import urlparse

from core.exceptions import (
    InvalidAmountError,
    InvalidLinkError,
    QuantityOutOfRangeError,
    ValidationError,
)
from core.money import to_units
from utils.link_rules import check_link_rule

#: أقصى طول مقبول للرابط (حماية من إغراق قاعدة البيانات)
MAX_LINK_LENGTH: int = 500

#: أقصى طول لنص رسالة الدعم
MAX_MESSAGE_LENGTH: int = 2000

#: أقصى طول لعنوان التذكرة
MAX_SUBJECT_LENGTH: int = 100

#: أقصى طول لرقم الحوالة/المرجع
MAX_REFERENCE_LENGTH: int = 64

#: الأرقام العربية-الهندية وما يقابلها
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

#: صيغة مرجع الحوالة المسموحة (أرقام وحروف وشرطات فقط)
_REFERENCE_RE = re.compile(r"^[A-Za-z0-9\-_/.]{3,64}$")

#: صيغة اسم المستخدم في تيليجرام
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")


def normalize_digits(text: str) -> str:
    """تحويل الأرقام العربية-الهندية (٠١٢…) إلى أرقام لاتينية ليقبلها النظام."""
    return text.translate(_ARABIC_DIGITS)


def clean_text(value: str | None, *, field: str, max_length: int, min_length: int = 1) -> str:
    """
    تنظيف نص عام: إزالة الفراغات الزائدة والتحقق من الطول.

    الاستثناءات:
        ValidationError : النص فارغ أو أطول من المسموح.
    """
    text = " ".join((value or "").split())
    if len(text) < min_length:
        raise ValidationError(
            f"حقل {field} فارغ", user_message=f"❌ الرجاء إدخال {field}."
        )
    if len(text) > max_length:
        raise ValidationError(
            f"حقل {field} أطول من {max_length}",
            user_message=f"❌ {field} طويل جداً (الحد الأقصى {max_length} حرفاً).",
        )
    return text


def clean_multiline(
    value: str | None, *, field: str, max_length: int, min_length: int = 1
) -> str:
    """
    تنظيف نص متعدد الأسطر **مع الحفاظ على الأسطر**.

    لماذا لا نستخدم `clean_text`؟ لأنها تدمج كل شيء في سطر واحد، وبعض النصوص
    (تعليمات التحويل، نص قالب إشعار) تفقد معناها بلا أسطر.

    القواعد: تُشذَّب الفراغات داخل كل سطر، ويُمنع تكرار الأسطر الفارغة.

    الاستثناءات:
        ValidationError : النص فارغ أو أطول من المسموح.
    """
    kept: list[str] = []
    for raw_line in (value or "").splitlines():
        line = " ".join(raw_line.split())
        if not line and (not kept or not kept[-1]):
            continue  # لا نسمح بأكثر من سطر فارغ متتالٍ
        kept.append(line)
    text = "\n".join(kept).strip()
    if len(text) < min_length:
        raise ValidationError(f"حقل {field} فارغ", user_message=f"❌ الرجاء إدخال {field}.")
    if len(text) > max_length:
        raise ValidationError(
            f"حقل {field} أطول من {max_length}",
            user_message=f"❌ {field} طويل جداً (الحد الأقصى {max_length} حرفاً).",
        )
    return text


def validate_link(link: str | None, *, pattern: str | None = None, rule: str | None = None) -> str:
    """
    التحقق من رابط الطلب.

    المدخلات:
        link    : الرابط كما أدخله المستخدم.
        pattern : تعبير نمطي اختياري مرتبط بالخدمة (مثلاً روابط انستغرام فقط).
        rule    : مفتاح قاعدة منصة/نوع (`utils.link_rules.LINK_RULES`) مثل `instagram_profile`.

    المخرجات: الرابط بعد التنظيف.

    الاستثناءات:
        InvalidLinkError : رابط فارغ أو بلا بروتوكول صحيح أو لا يطابق نمط الخدمة.
    """
    text = (link or "").strip()
    if not text:
        raise InvalidLinkError("رابط فارغ", user_message="❌ الرجاء إرسال الرابط.")
    if len(text) > MAX_LINK_LENGTH:
        raise InvalidLinkError(
            "رابط طويل جداً", user_message="❌ الرابط طويل جداً، تأكد من نسخه بشكل صحيح."
        )
    if any(ch.isspace() for ch in text):
        raise InvalidLinkError(
            "الرابط يحتوي فراغات", user_message="❌ الرابط يحتوي مسافات — أرسل الرابط وحده."
        )

    parsed = urlparse(text if "://" in text else f"https://{text}")
    if parsed.scheme not in {"http", "https"}:
        raise InvalidLinkError(
            f"بروتوكول غير مدعوم: {parsed.scheme}",
            user_message="❌ الرابط يجب أن يبدأ بـ http أو https.",
        )
    host = (parsed.hostname or "").strip()
    if "." not in host or host.startswith(".") or host.endswith("."):
        raise InvalidLinkError(
            f"نطاق غير صالح: {host}", user_message="❌ الرابط غير صالح. تأكد منه وأعد الإرسال."
        )

    normalized = text if "://" in text else f"https://{text}"
    if pattern:
        try:
            matcher = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            # نمط الخدمة نفسه خاطئ: لا نُسقط طلب المستخدم بسببه، بل نُبلغ كخطأ إعداد
            raise ValidationError(
                f"نمط رابط غير صالح في إعداد الخدمة: {pattern} ({exc})",
                user_message="⚠️ إعداد هذه الخدمة غير مكتمل. أبلغ الدعم من فضلك.",
            ) from exc
        if not matcher.search(normalized):
            raise InvalidLinkError(
                "الرابط لا يطابق نمط الخدمة",
                user_message="❌ هذا الرابط لا يناسب هذه الخدمة. تأكد من المنصة المطلوبة.",
            )
    if rule:
        check_link_rule(normalized, rule)
    return normalized


def parse_margin_percent(raw: str | None, *, minimum: int = 0, maximum: int = 1000) -> int:
    """
    تحليل هامش الربح المُدخَل: **رقم صحيح فقط** (`40` تعني ربح 40%)، بلا علامة `%`.

    الرفض برسالة عربية محددة لكل حالة: فارغ، فيه %، عشري، حروف، سالب، خارج الحدود.
    الأرقام العربية/الهندية مقبولة.

    الاستثناءات: ValidationError.
    """
    text = normalize_digits((raw or "").strip())
    example = "مثال: <code>40</code> تعني ربح 40%"
    if not text:
        raise ValidationError("هامش فارغ", user_message=f"❌ أرسل نسبة الهامش كرقم. {example}")
    if "%" in text:
        raise ValidationError(
            f"هامش فيه علامة %: {raw!r}", user_message=f"❌ اكتب الرقم فقط بلا علامة %. {example}"
        )
    if text.startswith("-"):
        raise ValidationError(
            f"هامش سالب: {raw!r}", user_message=f"❌ الهامش لا يكون سالباً (من {minimum} إلى {maximum}). {example}"
        )
    if "." in text or "," in text:
        raise ValidationError(
            f"هامش عشري: {raw!r}", user_message=f"❌ الهامش رقم صحيح بلا كسور. {example}"
        )
    if not text.isdigit():
        raise ValidationError(
            f"هامش غير رقمي: {raw!r}", user_message=f"❌ أرسل رقماً فقط بلا حروف أو رموز. {example}"
        )
    value = int(text)
    if value < minimum or value > maximum:
        raise ValidationError(
            f"هامش خارج الحدود: {value}",
            user_message=f"❌ الهامش يجب أن يكون بين {minimum} و{maximum}. {example}",
        )
    return value


def validate_quantity(raw_quantity: str | int, *, min_quantity: int, max_quantity: int) -> int:
    """
    التحقق من الكمية المطلوبة ضمن حدود الخدمة.

    الاستثناءات:
        QuantityOutOfRangeError : الكمية ليست رقماً صحيحاً أو خارج الحدود.
    """
    if isinstance(raw_quantity, bool):  # bool نوع فرعي من int — نمنعه صراحة
        raise QuantityOutOfRangeError("قيمة كمية غير صالحة")
    if isinstance(raw_quantity, int):
        quantity = raw_quantity
    else:
        text = normalize_digits(str(raw_quantity)).strip().replace(",", "")
        if not text.isdigit():
            raise QuantityOutOfRangeError(
                f"كمية غير رقمية: {raw_quantity}", user_message="❌ أرسل الكمية كرقم صحيح فقط."
            )
        quantity = int(text)

    if quantity < min_quantity or quantity > max_quantity:
        raise QuantityOutOfRangeError(
            f"الكمية {quantity} خارج [{min_quantity}, {max_quantity}]",
            user_message=(
                f"❌ الكمية يجب أن تكون بين {min_quantity:,} و {max_quantity:,}."
            ),
        )
    return quantity


def parse_amount_units(raw_amount: str | int | Decimal) -> int:
    """
    تحويل مبلغ مُدخل من المستخدم إلى وحدات صحيحة للتخزين.

    يقبل: "1500" · "1,500.50" · "١٥٠٠" · Decimal.

    الاستثناءات:
        InvalidAmountError : نص غير رقمي أو مبلغ صفر/سالب.
    """
    if isinstance(raw_amount, str):
        cleaned = normalize_digits(raw_amount).replace(",", "").replace("٫", ".").strip()
    else:
        cleaned = raw_amount
    try:
        units = to_units(cleaned)
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise InvalidAmountError(
            f"مبلغ غير صالح: {raw_amount!r}", user_message="❌ أرسل المبلغ كرقم صحيح."
        ) from exc
    if units <= 0:
        raise InvalidAmountError(
            f"مبلغ غير موجب: {raw_amount!r}", user_message="❌ المبلغ يجب أن يكون أكبر من صفر."
        )
    return units


def validate_amount_range(
    amount_units: int, *, min_units: int = 0, max_units: int | None = None, label: str = "المبلغ"
) -> int:
    """
    التحقق من أن المبلغ ضمن الحد الأدنى والأقصى المسموحين.

    الاستثناءات:
        InvalidAmountError : خارج الحدود، مع رسالة توضّح الحدود للمستخدم.
    """
    from core.money import format_units  # استيراد داخلي لتفادي الاعتماد الدائري عند الإقلاع

    if min_units and amount_units < min_units:
        raise InvalidAmountError(
            f"{label} أقل من الحد الأدنى",
            user_message=f"❌ الحد الأدنى {format_units(min_units)}.",
        )
    if max_units is not None and max_units > 0 and amount_units > max_units:
        raise InvalidAmountError(
            f"{label} أكبر من الحد الأقصى",
            user_message=f"❌ الحد الأقصى {format_units(max_units)}.",
        )
    return amount_units


def validate_transaction_reference(reference: str | None, *, required: bool = True) -> str | None:
    """
    التحقق من رقم الحوالة الذي يكتبه المستخدم عند الشحن.

    الاستثناءات:
        ValidationError : مرجع مطلوب وغير موجود، أو يحتوي رموزاً غير مسموحة.
    """
    text = normalize_digits((reference or "").strip())
    if not text:
        if required:
            raise ValidationError(
                "رقم الحوالة مطلوب", user_message="❌ الرجاء إرسال رقم عملية التحويل."
            )
        return None
    if not _REFERENCE_RE.match(text):
        raise ValidationError(
            f"مرجع غير صالح: {text!r}",
            user_message="❌ رقم العملية غير صالح (أرقام وحروف إنجليزية فقط، 3 محارف على الأقل).",
        )
    return text[:MAX_REFERENCE_LENGTH]


def validate_telegram_id(raw_id: str | int) -> int:
    """
    التحقق من معرف تيليجرام رقمي.

    الاستثناءات:
        ValidationError : قيمة غير رقمية أو خارج المدى المنطقي.
    """
    text = normalize_digits(str(raw_id)).strip()
    if not text.lstrip("-").isdigit():
        raise ValidationError(
            f"معرف تيليجرام غير رقمي: {raw_id!r}", user_message="❌ أرسل معرف تيليجرام كرقم."
        )
    value = int(text)
    if value <= 0 or value > 10**13:
        raise ValidationError(
            f"معرف تيليجرام خارج المدى: {value}", user_message="❌ معرف تيليجرام غير صالح."
        )
    return value


def normalize_username(username: str | None) -> str | None:
    """تنظيف اسم المستخدم (إزالة @) وإرجاع None إن كان غير صالح."""
    if not username:
        return None
    text = username.strip().lstrip("@")
    return text if _USERNAME_RE.match(text) else None


def validate_subject(subject: str | None) -> str:
    """التحقق من عنوان تذكرة الدعم."""
    return clean_text(subject, field="عنوان التذكرة", max_length=MAX_SUBJECT_LENGTH, min_length=3)


def validate_message(message: str | None) -> str:
    """التحقق من نص رسالة الدعم."""
    return clean_text(message, field="نص الرسالة", max_length=MAX_MESSAGE_LENGTH, min_length=2)


def validate_url(url: str | None, *, field: str = "رابط API") -> str:
    """
    التحقق من رابط إداري (مثل رابط API للمزود).

    الاستثناءات:
        ValidationError : الرابط فارغ أو بلا بروتوكول http/https.
    """
    text = (url or "").strip()
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValidationError(
            f"{field} غير صالح: {text!r}",
            user_message=f"❌ {field} يجب أن يبدأ بـ https:// ويحتوي نطاقاً صحيحاً.",
        )
    return text
```

---

## `utils/formatters.py`

```python
"""
أدوات تنسيق العرض: تحويل بيانات قاعدة البيانات إلى نصوص عربية جاهزة للشاشة.

قاعدة: لا منطق أعمال هنا — تنسيق فقط. وأي رقم مالي يُنسَّق من النقاط الصحيحة
عبر `core.money` ولا يُحسب هنا إطلاقاً.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from html import escape

from core.enums import (
    NotificationType,
    OrderStatus,
    PaymentStatus,
    TicketStatus,
    TransactionType,
)
from core.money import format_units, format_usd, from_units
from utils.datetime_utils import to_local_text

#: أيقونة ووصف عربي لكل حالة طلب
ORDER_STATUS_LABELS: dict[str, str] = {
    OrderStatus.PENDING: "⏳ بانتظار الإرسال",
    OrderStatus.SUBMITTING: "📤 جاري الإرسال",
    OrderStatus.SUBMIT_UNCERTAIN: "❓ قيد المراجعة اليدوية",
    OrderStatus.SUBMITTED: "📨 أُرسل للمزود",
    OrderStatus.IN_PROGRESS: "🔄 قيد التنفيذ",
    OrderStatus.PARTIAL: "⚠️ نُفِّذ جزئياً",
    OrderStatus.COMPLETED: "✅ مكتمل",
    OrderStatus.CANCELED: "🛑 ملغي",
    OrderStatus.FAILED: "❌ فشل",
    OrderStatus.REFUNDED: "↩️ مسترجع",
}

#: وصف عربي لحالات طلب الشحن
PAYMENT_STATUS_LABELS: dict[str, str] = {
    PaymentStatus.PENDING: "⏳ قيد المراجعة",
    PaymentStatus.APPROVED: "✅ معتمد",
    PaymentStatus.REJECTED: "❌ مرفوض",
    PaymentStatus.CANCELLED: "🛑 ملغي",
    PaymentStatus.EXPIRED: "⌛ منتهي",
}

#: وصف عربي لحالات التذكرة
TICKET_STATUS_LABELS: dict[str, str] = {
    TicketStatus.OPEN: "🟢 مفتوحة",
    TicketStatus.PENDING_ADMIN: "⏳ بانتظار الدعم",
    TicketStatus.PENDING_USER: "💬 بانتظار ردك",
    TicketStatus.CLOSED: "🔒 مغلقة",
}

#: وصف عربي لأنواع الحركات المالية
TRANSACTION_LABELS: dict[str, str] = {
    TransactionType.DEPOSIT: "📥 شحن رصيد",
    TransactionType.ORDER: "🛒 دفع طلب",
    TransactionType.REFUND: "↩️ استرجاع",
    TransactionType.PARTIAL_REFUND: "↩️ استرجاع جزئي",
    TransactionType.MANUAL_CREDIT: "➕ إضافة إدارية",
    TransactionType.MANUAL_DEBIT: "➖ خصم إداري",
    TransactionType.WITHDRAW: "📤 سحب",
    TransactionType.ADJUSTMENT: "🔧 تسوية",
}

#: أيقونة لكل نوع إشعار (للعرض في صندوق إشعارات المستخدم)
NOTIFICATION_ICONS: dict[str, str] = {
    NotificationType.ORDER_CREATED: "🛒",
    NotificationType.ORDER_SUBMITTED: "📨",
    NotificationType.ORDER_IN_PROGRESS: "🔄",
    NotificationType.ORDER_COMPLETED: "✅",
    NotificationType.ORDER_PARTIAL: "⚠️",
    NotificationType.ORDER_FAILED: "❌",
    NotificationType.ORDER_CANCELED: "🛑",
    NotificationType.ORDER_REFUNDED: "↩️",
    NotificationType.PAYMENT_RECEIVED: "📥",
    NotificationType.PAYMENT_APPROVED: "✅",
    NotificationType.PAYMENT_REJECTED: "❌",
    NotificationType.BALANCE_CREDITED: "➕",
    NotificationType.BALANCE_DEBITED: "➖",
    NotificationType.TICKET_REPLIED: "💬",
    NotificationType.TICKET_CLOSED: "🔒",
    NotificationType.BROADCAST: "📣",
    NotificationType.SYSTEM: "ℹ️",
}


def order_status_text(status: str) -> str:
    """وصف عربي لحالة الطلب (مع إيموجي)."""
    return ORDER_STATUS_LABELS.get(status, f"❔ {status}")


def payment_status_text(status: str) -> str:
    """وصف عربي لحالة طلب الشحن."""
    return PAYMENT_STATUS_LABELS.get(status, f"❔ {status}")


def ticket_status_text(status: str) -> str:
    """وصف عربي لحالة التذكرة."""
    return TICKET_STATUS_LABELS.get(status, f"❔ {status}")


def transaction_type_text(tx_type: str) -> str:
    """وصف عربي لنوع الحركة المالية."""
    return TRANSACTION_LABELS.get(tx_type, f"❔ {tx_type}")


def notification_icon(notification_type: str) -> str:
    """أيقونة نوع الإشعار."""
    return NOTIFICATION_ICONS.get(notification_type, "🔔")


def money_text(units: int, symbol: str = "", decimals: int = 2) -> str:
    """عرض مبلغ من النقاط الصحيحة بصيغة قابلة للقراءة مع رمز العملة."""
    return format_units(units, symbol, decimals)


def local_amount(units: int, symbol: str = "") -> str:
    """مبلغ بعملة النظام بلا أصفار زائدة بعد الفاصلة (`530.00 ريال` ⇒ `530 ريال`، و`530.50` تبقى)."""
    amount = from_units(units).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    text = f"{amount:,.2f}"
    if text.endswith(".00"):
        text = text[:-3]
    return f"{text} {symbol}".strip()


def price_pair(units: int, symbol: str, usd_rate: Decimal) -> tuple[str, str]:
    """
    السعر بالدولار (الأساس في العرض) ومقابله الفعلي بعملة النظام.

    المخرجات: (`$1.00`، `530 ريال`). المقابل هو **المبلغ الحقيقي المخصوم** لا ناتج تقريب، فلا يظهر
    فرق بين ما يراه العميل وما يُخصم منه؛ أما الدولار فمشتق منه بسعر الصرف المعروض (للعرض فقط).
    """
    return format_usd(units, usd_rate), local_amount(units, symbol)


def price_line(units: int, symbol: str, usd_rate: Decimal) -> str:
    """سطر سعر مختصر للأزرار والملخصات: `$1.00 • 530 ريال`."""
    usd, local = price_pair(units, symbol, usd_rate)
    return f"{usd} • {local}"


def safe(text: str | None, *, limit: int = 0) -> str:
    """
    تهريب نص المستخدم قبل عرضه بتنسيق HTML (حماية من كسر التنسيق أو الحقن).

    المدخلات:
        text  : النص الخام (قد يكون None).
        limit : قص النص عند هذا الطول مع إضافة «…» (صفر = بلا قص).
    """
    value = (text or "").strip()
    if limit and len(value) > limit:
        value = value[: limit - 1].rstrip() + "…"
    return escape(value, quote=False)


def datetime_text(iso_value: str | None, timezone: str = "Asia/Aden") -> str:
    """عرض تاريخ ISO بتوقيت المستخدم المحلي."""
    return to_local_text(iso_value, timezone)


def short_link(link: str, *, limit: int = 45) -> str:
    """اختصار رابط طويل للعرض داخل البطاقات."""
    return safe(link, limit=limit)


def transaction_line(transaction, *, symbol: str = "", timezone: str = "Asia/Aden") -> str:
    """سطر واحد يمثل حركة مالية في سجل العمليات."""
    sign = "+" if transaction.direction == "credit" else "−"
    amount = money_text(transaction.amount_units, symbol)
    label = transaction_type_text(transaction.type)
    when = datetime_text(transaction.created_at, timezone)
    return f"{label}\n   {sign}{amount} • الرصيد بعدها {money_text(transaction.balance_after_units, symbol)}\n   🕒 {when}"


def payment_line(payment, *, symbol: str = "", timezone: str = "Asia/Aden") -> str:
    """سطر واحد يمثل طلب شحن في قائمة طلبات الشحن."""
    status = payment_status_text(payment.status)
    amount = money_text(payment.amount_units, symbol)
    when = datetime_text(payment.created_at, timezone)
    return f"#{payment.id} • {amount} • {status}\n   🕒 {when}"


def notification_line(notification, *, timezone: str = "Asia/Aden") -> str:
    """سطر واحد يمثل إشعاراً في صندوق الإشعارات."""
    icon = notification_icon(notification.type)
    unread = "" if notification.is_read else " 🆕"
    when = datetime_text(notification.created_at, timezone)
    title = safe(notification.title or "", limit=60)
    body = safe(notification.message or "", limit=120)
    return f"{icon} <b>{title}</b>{unread}\n   {body}\n   🕒 {when}"


def order_list_line(order, *, symbol: str = "") -> str:
    """نص زر الطلب في قائمة الطلبات (سطر واحد قصير)."""
    code = order.public_code or f"#{order.id}"
    status = order_status_text(order.status).split(" ", 1)[0]
    return f"{status} {code} • {money_text(order.cost_units, symbol)}"


def ticket_list_line(ticket) -> str:
    """نص زر التذكرة في قائمة التذاكر."""
    status = ticket_status_text(ticket.status).split(" ", 1)[0]
    subject = safe(ticket.subject, limit=30)
    return f"{status} #{ticket.id} • {subject}"
```

---

## `database/repositories/channel_outbox.py`

```python
"""
مستودع صندوق إرسال القنوات الإدارية (تنبيهات الإدارة + توثيق الطلبات).

نفس فكرة صندوق الإشعارات: يُكتب السجل في معاملة الحدث نفسه (طلب جديد مثلاً)، ثم يرسله job لاحقاً.
    • لا يضيع سجل عند إعادة التشغيل؛  • لا يُنشر سجل لحدث لم يُثبَّت؛  • `dedupe_key` يمنع النشر المزدوج.
"""

from __future__ import annotations

from core.constants import MAX_NOTIFICATION_ATTEMPTS, NOTIFICATION_BACKOFF
from database.database import Tx
from database.models import ChannelPost
from database.repositories.base import BaseRepository
from utils.datetime_utils import iso_plus_seconds, utc_now_iso


class ChannelOutboxRepository(BaseRepository):
    """إدراج منشورات القنوات وإدارة محاولات إرسالها."""

    async def enqueue(self, tx: Tx, *, kind: str, title: str, message: str, dedupe_key: str) -> int | None:
        """إضافة منشور؛ المخرجات: معرّفه، أو None إن كان `dedupe_key` موجوداً (لا تكرار)."""
        result = await tx.execute(
            """
            INSERT INTO channel_outbox (kind, title, message, dedupe_key, status, next_attempt_at, created_at)
            VALUES (?, ?, ?, ?, 'queued', ?, ?)
            ON CONFLICT(dedupe_key) DO NOTHING
            """,
            (kind, title, message, dedupe_key, utc_now_iso(), self.now()),
        )
        return None if result.rowcount == 0 else result.lastrowid

    async def claim_batch(self, tx: Tx, *, limit: int = 20, lease_seconds: int = 60) -> list[ChannelPost]:
        """حجز دفعة جاهزة بتأجيل موعدها فوراً (lease) حتى لا تلتقطها دورة أخرى."""
        now = utc_now_iso()
        rows = await tx.fetchall(
            """
            SELECT * FROM channel_outbox
             WHERE status = 'queued' AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
             ORDER BY id LIMIT ?
            """,
            (now, limit),
        )
        claimed: list[ChannelPost] = []
        for row in rows:
            ok = await tx.execute(
                """
                UPDATE channel_outbox SET next_attempt_at = ?
                 WHERE id = ? AND status = 'queued' AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                """,
                (iso_plus_seconds(lease_seconds), row["id"], now),
            )
            post = ChannelPost.from_row(row) if ok.rowcount == 1 else None
            if post is not None:
                claimed.append(post)
        return claimed

    async def mark_sent(self, tx: Tx, post_id: int) -> bool:
        """تعليم المنشور كمُرسَل (مشروط بأنه ما زال queued)."""
        result = await tx.execute(
            "UPDATE channel_outbox SET status = 'sent', sent_at = ?, last_error = NULL WHERE id = ? AND status = 'queued'",
            (self.now(), post_id),
        )
        return result.rowcount == 1

    async def mark_failed(self, tx: Tx, post_id: int, *, error: str, permanent: bool = False) -> None:
        """تسجيل فشل محاولة: تأجيل متدرج، وفشل نهائي عند تجاوز الحد أو عند `permanent`."""
        row = await tx.fetchone("SELECT attempts FROM channel_outbox WHERE id = ?", (post_id,))
        attempts = int(row["attempts"]) + 1 if row else 1
        clean = error[:300]
        if permanent or attempts >= MAX_NOTIFICATION_ATTEMPTS:
            await tx.execute(
                "UPDATE channel_outbox SET status = 'failed', attempts = ?, last_error = ? WHERE id = ?",
                (attempts, clean, post_id),
            )
            return
        delay = NOTIFICATION_BACKOFF[min(attempts - 1, len(NOTIFICATION_BACKOFF) - 1)]
        await tx.execute(
            "UPDATE channel_outbox SET attempts = ?, last_error = ?, next_attempt_at = ?, status = 'queued' WHERE id = ?",
            (attempts, clean, iso_plus_seconds(delay), post_id),
        )

    async def mark_skipped(self, tx: Tx, post_id: int, reason: str) -> None:
        """تخطي نهائي (لا قناة مضبوطة لهذا النوع)."""
        await tx.execute(
            "UPDATE channel_outbox SET status = 'skipped', last_error = ? WHERE id = ?", (reason[:300], post_id)
        )

    async def reschedule(self, tx: Tx, post_id: int) -> None:
        """إعادة المنشور للطابور فوراً بلا احتساب محاولة (مثل: حد معدل مؤقت من تيليجرام)."""
        await tx.execute(
            "UPDATE channel_outbox SET next_attempt_at = ? WHERE id = ? AND status = 'queued'",
            (iso_plus_seconds(5), post_id),
        )

    async def get_by_dedupe(self, dedupe_key: str) -> ChannelPost | None:
        """جلب منشور بمفتاح التفرد (للاختبار والتشخيص)."""
        row = await self.db.fetchone("SELECT * FROM channel_outbox WHERE dedupe_key = ?", (dedupe_key,))
        return ChannelPost.from_row(row)

    async def list_recent(self, *, limit: int = 10) -> list[ChannelPost]:
        """آخر المنشورات (شاشة تشخيص القنوات)."""
        rows = await self.db.fetchall("SELECT * FROM channel_outbox ORDER BY id DESC LIMIT ?", (limit,))
        return ChannelPost.from_rows(rows)

    async def count_by_status(self) -> dict[str, int]:
        """عدد المنشورات لكل حالة."""
        rows = await self.db.fetchall("SELECT status, COUNT(*) AS n FROM channel_outbox GROUP BY status")
        return {row["status"]: int(row["n"]) for row in rows}

    async def delete_old(self, tx: Tx, before_iso: str) -> int:
        """حذف المنشورات القديمة المنتهية (التنظيف الدوري)."""
        result = await tx.execute(
            "DELETE FROM channel_outbox WHERE created_at < ? AND status IN ('sent', 'skipped', 'failed')",
            (before_iso,),
        )
        return result.rowcount
```

---

## `database/repositories/favorites.py`

```python
"""مستودع المفضلة: خدمات يحفظها المستخدم لوصول أسرع (مفتاح مركّب ⇒ لا تكرار بنيوياً)."""

from __future__ import annotations

from database.database import Tx
from database.models import Service
from database.repositories.base import BaseRepository


class FavoritesRepository(BaseRepository):
    """إضافة/حذف/عرض مفضلة المستخدم."""

    async def add(self, tx: Tx, user_id: int, service_id: int) -> bool:
        """إضافة خدمة؛ المخرجات: True إن أُضيفت الآن، False إن كانت موجودة (لا تكرار)."""
        result = await tx.execute(
            "INSERT INTO favorites (user_id, service_id, created_at) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
            (user_id, service_id, self.now()),
        )
        return result.rowcount == 1

    async def remove(self, tx: Tx, user_id: int, service_id: int) -> bool:
        """إزالة خدمة؛ المخرجات: True إن كانت موجودة وأُزيلت."""
        result = await tx.execute(
            "DELETE FROM favorites WHERE user_id = ? AND service_id = ?", (user_id, service_id)
        )
        return result.rowcount == 1

    async def exists(self, user_id: int, service_id: int) -> bool:
        """هل الخدمة في مفضلة المستخدم؟"""
        row = await self.db.fetchone(
            "SELECT 1 FROM favorites WHERE user_id = ? AND service_id = ?", (user_id, service_id)
        )
        return row is not None

    async def count_for_user(self, user_id: int) -> int:
        """عدد مفضلات المستخدم (كل الخدمات، متاحة أو لا)."""
        return await self.count("favorites", "user_id = ?", (user_id,))

    async def list_available(self, user_id: int, *, limit: int, offset: int) -> list[Service]:
        """مفضلة المستخدم من الخدمات المتاحة للطلب حالياً، الأحدث إضافةً أولاً."""
        rows = await self.db.fetchall(
            """
            SELECT s.* FROM favorites f
              JOIN services s ON s.id = f.service_id
             WHERE f.user_id = ? AND s.is_active = 1 AND s.is_archived = 0
             ORDER BY f.created_at DESC, s.id DESC LIMIT ? OFFSET ?
            """,
            (user_id, limit, offset),
        )
        return Service.from_rows(rows)

    async def count_available(self, user_id: int) -> int:
        """عدد المفضلة المتاحة للطلب (لترقيم الصفحات)."""
        return int(
            await self.db.fetchval(
                """
                SELECT COUNT(*) FROM favorites f JOIN services s ON s.id = f.service_id
                 WHERE f.user_id = ? AND s.is_active = 1 AND s.is_archived = 0
                """,
                [user_id],
                default=0,
            )
        )
```

---

## `database/repositories/services.py`

```python
"""
مستودع الخدمات — الخدمات المعروضة للبيع وارتباطها بالمزودين.

قاعدة مهمة: الخدمة التي لها طلبات سابقة لا تُحذف نهائياً، بل تُعطَّل أو تُؤرشف،
حتى لا تُكسر المراجع التاريخية في جدول الطلبات.
"""

from __future__ import annotations

from typing import Any

from database.database import Tx
from database.models import Service
from database.repositories.base import BaseRepository

_ALLOWED_FIELDS = {
    "category_id",
    "provider_id",
    "provider_service_id",
    "name",
    "description",
    "service_type",
    "price_per_1000_units",
    "provider_price_per_1000_units",
    "min_quantity",
    "max_quantity",
    "dripfeed_enabled",
    "refill_enabled",
    "cancel_enabled",
    "link_pattern",
    "avg_time_text",
    "is_active",
    "is_archived",
    "sort_order",
    "link_rule",
    "speed_text",
    "quality_text",
    "guarantee_text",
}


class ServicesRepository(BaseRepository):
    """عمليات قراءة وكتابة الخدمات."""

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, service_id: int) -> Service | None:
        """جلب خدمة بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM services WHERE id = ?", (service_id,))
        return Service.from_row(row)

    async def get_available(self, service_id: int) -> Service | None:
        """جلب خدمة متاحة للطلب فقط (مفعّلة وغير مؤرشفة)."""
        row = await self.db.fetchone(
            "SELECT * FROM services WHERE id = ? AND is_active = 1 AND is_archived = 0", (service_id,)
        )
        return Service.from_row(row)

    async def list_by_category(
        self, category_id: int, *, only_available: bool = True, limit: int = 8, offset: int = 0
    ) -> list[Service]:
        """قائمة خدمات تصنيف معين مع ترقيم صفحات."""
        sql = "SELECT * FROM services WHERE category_id = ?"
        params: list[Any] = [category_id]
        if only_available:
            sql += " AND is_active = 1 AND is_archived = 0"
        sql += " ORDER BY sort_order, id LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = await self.db.fetchall(sql, params)
        return Service.from_rows(rows)

    async def count_by_category(self, category_id: int, *, only_available: bool = True) -> int:
        """عدد خدمات تصنيف (لحساب عدد الصفحات)."""
        where = "category_id = ?"
        if only_available:
            where += " AND is_active = 1 AND is_archived = 0"
        return await self.count("services", where, (category_id,))

    async def find_by_provider_service(self, provider_id: int, provider_service_id: str) -> Service | None:
        """البحث عن خدمة مرتبطة بمعرف خدمة معين عند المزود (يُستخدم في المزامنة)."""
        row = await self.db.fetchone(
            "SELECT * FROM services WHERE provider_id = ? AND provider_service_id = ?",
            (provider_id, str(provider_service_id)),
        )
        return Service.from_row(row)

    async def list_by_provider(self, provider_id: int, *, limit: int = 50, offset: int = 0) -> list[Service]:
        """خدمات مزود معين."""
        rows = await self.db.fetchall(
            "SELECT * FROM services WHERE provider_id = ? ORDER BY id LIMIT ? OFFSET ?",
            (provider_id, limit, offset),
        )
        return Service.from_rows(rows)

    async def search(self, text: str, *, limit: int = 10) -> list[Service]:
        """بحث نصي في أسماء الخدمات (للوحة الأدمن)."""
        pattern = f"%{text.strip()}%"
        rows = await self.db.fetchall(
            "SELECT * FROM services WHERE name LIKE ? ORDER BY id LIMIT ?", (pattern, limit)
        )
        return Service.from_rows(rows)

    async def count_active(self) -> int:
        """عدد الخدمات المتاحة حالياً."""
        return await self.count("services", "is_active = 1 AND is_archived = 0")

    async def has_orders(self, service_id: int) -> bool:
        """هل توجد طلبات مرتبطة بهذه الخدمة؟ (يمنع الحذف الفعلي)."""
        row = await self.db.fetchone("SELECT 1 FROM orders WHERE service_id = ? LIMIT 1", (service_id,))
        return row is not None

    async def negative_margin_services(self) -> list[Service]:
        """الخدمات التي أصبح سعر بيعها أقل من تكلفتها (تحذير بعد مزامنة الأسعار)."""
        rows = await self.db.fetchall(
            """
            SELECT * FROM services
             WHERE provider_price_per_1000_units IS NOT NULL
               AND price_per_1000_units < provider_price_per_1000_units
               AND is_archived = 0
             ORDER BY id
            """
        )
        return Service.from_rows(rows)

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        category_id: int,
        provider_id: int,
        provider_service_id: str,
        name: str,
        price_per_1000_units: int,
        min_quantity: int,
        max_quantity: int,
        description: str | None = None,
        provider_price_per_1000_units: int | None = None,
        service_type: str = "default",
        link_pattern: str | None = None,
        avg_time_text: str | None = None,
        sort_order: int = 100,
        link_rule: str | None = None,
        speed_text: str | None = None,
        quality_text: str | None = None,
        guarantee_text: str | None = None,
    ) -> Service:
        """إضافة خدمة جديدة (مع حقول العرض: قاعدة الرابط والسرعة والجودة والضمان)."""
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO services (category_id, provider_id, provider_service_id, name, description,
                                  service_type, price_per_1000_units, provider_price_per_1000_units,
                                  min_quantity, max_quantity, link_pattern, avg_time_text,
                                  sort_order, created_at, updated_at,
                                  link_rule, speed_text, quality_text, guarantee_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                category_id, provider_id, str(provider_service_id), name, description,
                service_type, price_per_1000_units, provider_price_per_1000_units,
                min_quantity, max_quantity, link_pattern, avg_time_text, sort_order, now, now,
                link_rule, speed_text, quality_text, guarantee_text,
            ),
        )
        row = await tx.fetchone("SELECT * FROM services WHERE id = ?", (result.lastrowid,))
        service = Service.from_row(row)
        assert service is not None
        return service

    async def update_fields(self, tx: Tx, service_id: int, **fields: Any) -> bool:
        """تعديل حقول مسموح بها للخدمة."""
        return await self._update_by_id(tx, "services", service_id, fields, _ALLOWED_FIELDS)

    async def change_price(
        self,
        tx: Tx,
        service_id: int,
        *,
        new_price_units: int,
        new_min: int | None = None,
        new_max: int | None = None,
        changed_by: int | None = None,
        source: str = "admin",
    ) -> bool:
        """
        تغيير سعر أو حدود خدمة مع تسجيل التغيير في سجل الأسعار.

        السبب: الحاجة لتفسير محاسبي لأي فرق سعر بين الطلبات القديمة والجديدة.
        """
        current = await tx.fetchone(
            "SELECT price_per_1000_units, min_quantity, max_quantity FROM services WHERE id = ?",
            (service_id,),
        )
        if current is None:
            return False

        fields: dict[str, Any] = {"price_per_1000_units": new_price_units}
        if new_min is not None:
            fields["min_quantity"] = new_min
        if new_max is not None:
            fields["max_quantity"] = new_max
        updated = await self._update_by_id(tx, "services", service_id, fields, _ALLOWED_FIELDS)
        if not updated:
            return False

        await tx.execute(
            """
            INSERT INTO service_price_history (service_id, old_price_units, new_price_units,
                                               old_min, new_min, old_max, new_max,
                                               changed_by, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                service_id,
                current["price_per_1000_units"],
                new_price_units,
                current["min_quantity"],
                new_min if new_min is not None else current["min_quantity"],
                current["max_quantity"],
                new_max if new_max is not None else current["max_quantity"],
                changed_by,
                source,
                self.now(),
            ),
        )
        return True

    async def set_active(self, tx: Tx, service_id: int, active: bool) -> bool:
        """تفعيل أو تعطيل خدمة."""
        return await self._update_by_id(
            tx, "services", service_id, {"is_active": 1 if active else 0}, _ALLOWED_FIELDS
        )

    async def archive(self, tx: Tx, service_id: int) -> bool:
        """أرشفة خدمة (حذف ناعم): تُخفى عن المستخدمين ويبقى تاريخها سليماً."""
        return await self._update_by_id(
            tx, "services", service_id, {"is_archived": 1, "is_active": 0}, _ALLOWED_FIELDS
        )

    async def price_history(self, service_id: int, limit: int = 10) -> list[dict]:
        """آخر تغييرات السعر لخدمة."""
        rows = await self.db.fetchall(
            "SELECT * FROM service_price_history WHERE service_id = ? ORDER BY id DESC LIMIT ?",
            (service_id, limit),
        )
        return [dict(row) for row in rows]
```

---

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
from database.repositories.channel_outbox import ChannelOutboxRepository
from database.repositories.favorites import FavoritesRepository
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
    "ChannelOutboxRepository",
    "FavoritesRepository",
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
        self.channel_outbox = ChannelOutboxRepository(db)
        self.favorites = FavoritesRepository(db)
```

---

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
    link_rule: str | None = None
    speed_text: str | None = None
    quality_text: str | None = None
    guarantee_text: str | None = None

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


@dataclass(slots=True)
class ChannelPost(BaseModel):
    """منشور في صندوق إرسال القنوات الإدارية (تنبيهات الإدارة / توثيق الطلبات)."""

    id: int
    kind: str
    message: str
    dedupe_key: str
    created_at: str
    title: str = ""
    status: str = "queued"
    attempts: int = 0
    next_attempt_at: str | None = None
    last_error: str | None = None
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

---

## `services/channel_service.py`

```python
"""
خدمة القنوات الإدارية: النشر الدائم (تنبيهات الإدارة + توثيق الطلبات) وتشخيص وجهات الإرسال.

المبادئ:
    • **النشر عبر صندوق دائم** (`channel_outbox`): يُكتب المنشور في معاملة الحدث، ويرسله job بمحاولات
      متدرجة. فشل تيليجرام المؤقت لا يُسقط طلباً ولا يضيّع سجلاً.
    • **قناة النسخ الاحتياطي للنسخ فقط**: لا يُنشر فيها شيء آخر؛ وإن تطابقت وجهة تنبيه/توثيق معها
      تُرفض الوجهة وتُسجَّل المشكلة (ولا يُرسل إليها).
    • فشل **دائم** (قناة غير موجودة / البوت ليس مشرفاً) يُنبِّه الأدمن مرة يومياً بسبب واضح، بلا
      تكرار للمنشور الفاشل وبلا حلقة تنبيهات (تنبيه الفشل نفسه لا يُنسخ للقناة).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from core.exceptions import (
    NotificationBlockedError,
    NotificationPermanentError,
    NotificationTemporaryError,
)
from core.permissions import Permission
from database.database import Database, Tx
from database.repositories import Repositories
from services.notification_service import NotificationSender, NotificationService
from services.settings_service import SettingsService
from telegram.error import BadRequest, Forbidden, NetworkError, TelegramError, TimedOut
from utils.channel_ref import try_parse_chat_id
from utils.datetime_utils import utc_now
from utils.logging_setup import get_logger
from utils.security import sanitize

logger = get_logger(__name__)

#: أنواع المنشورات
KIND_ADMIN_ALERT = "admin_alert"
KIND_ORDERS_LOG = "orders_log"

#: مفتاح الإعداد لوجهة كل نوع
_SETTING_FOR_KIND = {KIND_ADMIN_ALERT: "admin_alert_chat_id", KIND_ORDERS_LOG: "orders_log_chat_id"}

#: فاصل بين منشورين متتاليين (حد تيليجرام ~20 رسالة/دقيقة للقناة الواحدة)
POST_GAP_SECONDS = 0.4


@dataclass(slots=True)
class FlushReport:
    """حصيلة جولة نشر."""

    claimed: int = 0
    sent: int = 0
    retried: int = 0
    failed: int = 0
    skipped: int = 0


@dataclass(slots=True)
class ChannelCheck:
    """نتيجة فحص وجهة: ok=True سليمة، False مشكلة مؤكدة، None تعذّر الجزم (شبكة)."""

    label: str
    ref: int | str | None
    ok: bool | None
    title: str = ""
    problem: str = ""
    hints: list[str] = field(default_factory=list)


class ChannelService:
    """نشر منشورات القنوات وفحص صحة الوجهات."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        notifications: NotificationService,
        *,
        alert_chat_fallback: int | str | None = None,
        backup_channel_id: int | str | None = None,
    ) -> None:
        """
        تهيئة الخدمة.

        المدخلات:
            alert_chat_fallback : `ADMIN_ALERT_CHAT_ID` من البيئة (يُستعمل إن لم يُضبط الإعداد).
            backup_channel_id   : قناة النسخ (محجوزة للنسخ؛ ممنوع استعمالها كوجهة تنبيه/توثيق).
        """
        self.db = db
        self.repos = repos
        self.settings = settings
        self.notifications = notifications
        self.alert_chat_fallback = alert_chat_fallback
        self.backup_channel_id = backup_channel_id

    # ------------------------------- الإدراج ------------------------------ #

    async def enqueue(self, tx: Tx, *, kind: str, title: str, message: str, dedupe_key: str) -> int | None:
        """وضع منشور في الصندوق داخل معاملة قائمة (None ⇒ موجود مسبقاً بنفس المفتاح)."""
        return await self.repos.channel_outbox.enqueue(
            tx, kind=kind, title=title, message=message, dedupe_key=dedupe_key
        )

    # ------------------------------- الوجهات ------------------------------ #

    async def destination(self, kind: str) -> tuple[int | str | None, str]:
        """
        وجهة منشورات نوع معيّن.

        المخرجات: (المعرّف أو None، سبب عدم وجود وجهة إن وُجد). التعارض مع قناة النسخ ⇒ لا وجهة.
        """
        key = _SETTING_FOR_KIND[kind]
        chat = try_parse_chat_id(await self.settings.get_str(key, ""), allow_user_ids=True)
        if chat is None and kind == KIND_ADMIN_ALERT:
            chat = try_parse_chat_id(self.alert_chat_fallback, allow_user_ids=True)
        if chat is None:
            return None, "لا وجهة مضبوطة"
        if self.backup_channel_id is not None and str(chat) == str(self.backup_channel_id):
            return None, "الوجهة هي قناة النسخ الاحتياطي (مخصصة للنسخ فقط)"
        return chat, ""

    # -------------------------------- النشر ------------------------------- #

    async def flush(self, sender: NotificationSender, *, limit: int = 20) -> FlushReport:
        """
        نشر دفعة من الصندوق.

        المدخلات:
            sender : نفس مُرسل الإشعارات `(chat_id, title, message)`، يرفع استثناءات الإشعارات المصنّفة.
        """
        report = FlushReport()
        async with self.db.transaction() as tx:
            posts = await self.repos.channel_outbox.claim_batch(tx, limit=limit)
        report.claimed = len(posts)

        alerted: set[str] = set()
        for index, post in enumerate(posts):
            chat, why = await self.destination(post.kind)
            if chat is None:
                async with self.db.transaction() as tx:
                    await self.repos.channel_outbox.mark_skipped(tx, post.id, why)
                report.skipped += 1
                if "النسخ" in why and post.kind not in alerted:
                    alerted.add(post.kind)
                    await self._alert_problem(post.kind, why)
                continue

            if index:
                await asyncio.sleep(POST_GAP_SECONDS)
            try:
                await sender(chat, post.title, post.message)
            except NotificationTemporaryError as exc:
                async with self.db.transaction() as tx:
                    await self.repos.channel_outbox.mark_failed(tx, post.id, error=str(exc))
                report.retried += 1
            except (NotificationBlockedError, NotificationPermanentError) as exc:
                reason = sanitize(str(exc))[:200]
                async with self.db.transaction() as tx:
                    await self.repos.channel_outbox.mark_failed(tx, post.id, error=reason, permanent=True)
                report.failed += 1
                logger.error("تعذّر النشر في القناة (%s): %s", post.kind, reason)
                if post.kind not in alerted:
                    alerted.add(post.kind)
                    await self._alert_problem(post.kind, reason)
            else:
                async with self.db.transaction() as tx:
                    await self.repos.channel_outbox.mark_sent(tx, post.id)
                report.sent += 1
        return report

    async def _alert_problem(self, kind: str, reason: str) -> None:
        """تنبيه الأدمن (مرة يومياً لكل نوع) بأن وجهة النشر معطّلة — بلا نسخ للقناة (تفادياً للحلقة)."""
        label = "تنبيهات الإدارة" if kind == KIND_ADMIN_ALERT else "توثيق الطلبات"
        async with self.db.transaction() as tx:
            await self.notifications.notify_admins(
                tx,
                permission=Permission.SETTINGS_UPDATE,
                token=f"channel-dest:{kind}:{utc_now().strftime('%Y%m%d')}",
                title=f"⚠️ تعذّر النشر في قناة {label}",
                message=(
                    f"السبب: {reason}\n"
                    "افتح: لوحة التحكم ← 📢 القنوات للتشخيص، وتأكد أن البوت مشرف في القناة "
                    "وأن المعرّف بصيغة -100xxxxxxxxxx أو @username."
                ),
                copy_to_channel=False,
            )

    # -------------------------------- التشخيص ----------------------------- #

    async def diagnose(self, bot: Any, label: str, ref: int | str | None, *, needs_post: bool = True) -> ChannelCheck:
        """
        فحص وجهة فعلياً عبر تيليجرام: هل تُرى؟ وهل البوت قادر على النشر فيها؟

        المدخلات:
            needs_post : True للوجهات التي ينشر فيها البوت (تنبيهات/توثيق/نسخ)، False لقنوات الاشتراك
                         (يكفي أن يرى البوت العضوية، وهذا يتطلب أن يكون مشرفاً في القناة).
        """
        if ref is None:
            return ChannelCheck(label=label, ref=None, ok=None, problem="غير مضبوطة")
        try:
            chat = await bot.get_chat(ref)
        except BadRequest as exc:
            return self._bad(label, ref, exc)
        except Forbidden:
            return ChannelCheck(
                label=label, ref=ref, ok=False,
                problem="البوت محظور/مطرود من هذه المحادثة",
                hints=["أعد إضافة البوت مشرفاً في القناة."],
            )
        except (TimedOut, NetworkError) as exc:
            return ChannelCheck(label=label, ref=ref, ok=None, problem=f"تعذّر الاتصال بتيليجرام ({type(exc).__name__})")
        except TelegramError as exc:
            return ChannelCheck(label=label, ref=ref, ok=False, problem=sanitize(str(exc))[:150])

        title = str(getattr(chat, "title", None) or getattr(chat, "full_name", None) or "")
        chat_type = str(getattr(chat, "type", ""))
        if chat_type == "private":
            return ChannelCheck(label=label, ref=ref, ok=True, title=title)

        try:
            me = await bot.get_me()
            member = await bot.get_chat_member(chat.id, me.id)
        except (BadRequest, Forbidden) as exc:             # يسبق NetworkError: BadRequest فرع منه في PTB
            return ChannelCheck(label=label, ref=ref, ok=False, title=title, problem=sanitize(str(exc))[:150])
        except (TimedOut, NetworkError) as exc:
            return ChannelCheck(label=label, ref=ref, ok=None, title=title, problem=f"تعذّر الاتصال ({type(exc).__name__})")
        except TelegramError as exc:
            return ChannelCheck(label=label, ref=ref, ok=False, title=title, problem=sanitize(str(exc))[:150])

        status = str(getattr(member, "status", ""))
        if chat_type == "channel" and status != "administrator" and status != "creator":
            return ChannelCheck(
                label=label, ref=ref, ok=False, title=title,
                problem="البوت ليس مشرفاً في القناة",
                hints=["أضِف البوت مشرفاً (Administrator) في القناة."],
            )
        if needs_post and chat_type == "channel" and getattr(member, "can_post_messages", True) is False:
            return ChannelCheck(
                label=label, ref=ref, ok=False, title=title,
                problem="البوت مشرف لكن بلا صلاحية «نشر الرسائل»",
                hints=["فعّل صلاحية Post Messages للبوت في إعدادات المشرف."],
            )
        if status in {"left", "kicked"}:
            return ChannelCheck(label=label, ref=ref, ok=False, title=title, problem="البوت ليس عضواً في المحادثة")
        return ChannelCheck(label=label, ref=ref, ok=True, title=title)

    @staticmethod
    def _bad(label: str, ref: int | str, exc: BadRequest) -> ChannelCheck:
        """تفسير BadRequest (غالباً chat not found) بسبب وحل واضحين."""
        text = str(exc).lower()
        if "chat not found" in text or "channel_invalid" in text:
            hints = [
                "المعرّف خاطئ، أو البوت ليس عضواً/مشرفاً في هذه القناة (القناة الخاصة لا تُرى بلا عضوية).",
                "للقناة الخاصة استعمل -100xxxxxxxxxx (وليس رابط الدعوة)، وأضِف البوت مشرفاً أولاً.",
            ]
            if isinstance(ref, int) and ref > 0:
                hints.insert(0, "معرّف القنوات سالب ويبدأ بـ -100.")
            return ChannelCheck(label=label, ref=ref, ok=False, problem="Chat not found", hints=hints)
        return ChannelCheck(label=label, ref=ref, ok=False, problem=sanitize(str(exc))[:150])
```

---

## `services/subscription_service.py`

```python
"""
خدمة الاشتراك الإجباري: التحقق **الفعلي** من عضوية المستخدم في القنوات المطلوبة.

القواعد:
    • القنوات الأربع (الرسمية، توثيق الطلبات، التحديثات، العروض) تُدار من الإعدادات؛ القناة الفارغة غير مطلوبة،
      وإذا كانت كلها فارغة أو `subscription_required=false` فلا بوابة.
    • العضوية تُقرأ من تيليجرام (`getChatMember`) — لا نفترضها: الحالات المعتمدة فقط `creator/administrator/member`
      أو `restricted` مع `is_member`. ما عداها (`left/kicked`) غير مشترك.
    • **الفشل مغلق**: تعذّر التحقق (قناة غير مضبوطة صحيحاً، البوت ليس مشرفاً، انقطاع) لا يُعدّ اشتراكاً.
      الاستثناء الوحيد: مستخدم تأكّد اشتراكه خلال الساعة الأخيرة وتعذّر التحقق مؤقتاً بسبب **شبكة** (لا إعداد).
    • نتيجة «مشترك» تُخزَّن في الذاكرة 5 دقائق لتخفيف النداءات (4 نداءات لكل تحقق)؛ ضغط «تحقق» يتجاوز الكاش.
    • الفريق الإداري معفى (يقرّر ذلك الطبقة الوسيطة)، حتى لا يُقفل الأدمن عن لوحة تصحيح القنوات نفسها.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from database.database import Database
from database.repositories import Repositories
from services.notification_service import NotificationService
from services.settings_service import SettingsService
from telegram.error import BadRequest, Forbidden, NetworkError, TelegramError, TimedOut
from utils.channel_ref import ChannelRef, ChannelRefError, parse_channel_value
from utils.datetime_utils import utc_now
from utils.logging_setup import get_logger
from utils.security import sanitize

logger = get_logger(__name__)

#: القنوات المطلوبة: (مفتاح الإعداد، أيقونة، اسم العرض)
REQUIRED_CHANNEL_SPECS: tuple[tuple[str, str, str], ...] = (
    ("channel_official", "📢", "القناة الرسمية"),
    ("channel_proofs", "📚", "قناة توثيق/متابعة الطلبات"),
    ("channel_updates", "🔔", "قناة التحديثات"),
    ("channel_offers", "🎁", "قناة العروض"),
)

#: حالات العضوية المعتمدة
MEMBER_STATUSES = frozenset({"creator", "administrator", "member"})

#: مدة اعتماد نتيجة «مشترك» من الكاش (ثانية)
CACHE_TTL_SECONDS = 300.0
#: مدة سماح عند تعذّر التحقق بسبب الشبكة لمن تأكّد اشتراكه سابقاً
NETWORK_GRACE_SECONDS = 3600.0
#: سقف ذاكرة الكاش (مدخلات)
MAX_CACHE_ENTRIES = 20_000


@dataclass(frozen=True, slots=True)
class RequiredChannel:
    """قناة مطلوبة بعد القراءة من الإعدادات."""

    key: str
    emoji: str
    label: str
    ref: ChannelRef

    @property
    def title(self) -> str:
        """اسم العرض مع الأيقونة."""
        return f"{self.emoji} {self.label}"


@dataclass(slots=True)
class SubscriptionStatus:
    """حصيلة التحقق: المطلوبة، غير المشترك فيها، وما تعذّر التحقق منه (مع السبب)."""

    channels: list[RequiredChannel] = field(default_factory=list)
    missing: list[RequiredChannel] = field(default_factory=list)
    unverifiable: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """مشترك في الكل فعلاً؟ (تعذّر التحقق ≠ اشتراك)."""
        return not self.missing and not self.unverifiable


class SubscriptionService:
    """قراءة القنوات المطلوبة والتحقق من اشتراك المستخدم."""

    def __init__(
        self, db: Database, repos: Repositories, settings: SettingsService, notifications: NotificationService
    ) -> None:
        """تهيئة الخدمة (الكاش في الذاكرة فقط)."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.notifications = notifications
        self._verified_at: dict[tuple[int, str], float] = {}
        self._alerted: set[str] = set()                    # تنبيهات الإعداد المُدرجة اليوم (حماية من قاعدة البيانات)

    # ----------------------------- الإعدادات ------------------------------ #

    async def required_channels(self) -> list[RequiredChannel]:
        """القنوات المطلوبة حالياً (فارغ إن عُطِّلت البوابة أو لم تُضبط قناة). الصيغة الخاطئة تُتجاهل مع تحذير."""
        if not await self.settings.get_bool("subscription_required", True):
            return []
        channels: list[RequiredChannel] = []
        for key, emoji, label in REQUIRED_CHANNEL_SPECS:
            raw = (await self.settings.get_str(key, "")).strip()
            if not raw:
                continue
            try:
                ref = parse_channel_value(raw)
            except ChannelRefError as exc:
                logger.warning("إعداد القناة %s غير صالح (%s) — تُتجاهل في البوابة", key, exc)
                continue
            channels.append(RequiredChannel(key=key, emoji=emoji, label=label, ref=ref))
        return channels

    # ------------------------------- التحقق ------------------------------- #

    async def check(self, bot: Any, telegram_id: int, *, force: bool = False) -> SubscriptionStatus:
        """
        التحقق من اشتراك المستخدم في كل القنوات المطلوبة (بالتوازي).

        المدخلات:
            force : تجاوز كاش «مشترك» (يُستعمل عند ضغط زر «تحقق»).
        """
        channels = await self.required_channels()
        status = SubscriptionStatus(channels=channels)
        if not channels:
            return status
        results = await asyncio.gather(
            *(self._check_one(bot, telegram_id, channel, force=force) for channel in channels)
        )
        for channel, (state, reason) in zip(channels, results):
            if state == "member":
                continue
            if state == "missing":
                status.missing.append(channel)
            else:
                status.unverifiable[channel.key] = reason
        if status.unverifiable:
            await self._alert_config_problem(channels, status.unverifiable)
        return status

    async def _check_one(
        self, bot: Any, telegram_id: int, channel: RequiredChannel, *, force: bool
    ) -> tuple[str, str]:
        """فحص قناة واحدة؛ المخرجات: ("member"|"missing"|"error", سبب)."""
        cache_key = (telegram_id, channel.key + str(channel.ref.chat_id))
        now = time.monotonic()
        verified = self._verified_at.get(cache_key)
        if not force and verified is not None and now - verified < CACHE_TTL_SECONDS:
            return "member", ""
        try:
            member = await bot.get_chat_member(channel.ref.chat_id, telegram_id)
        except BadRequest as exc:                          # يسبق NetworkError: BadRequest فرع منه في PTB
            text = str(exc).lower()
            if "user not found" in text or "participant_id_invalid" in text or "user_not_participant" in text:
                self._verified_at.pop(cache_key, None)
                return "missing", ""
            return "error", sanitize(str(exc))[:150]       # chat not found وغيره: إعداد القناة/البوت
        except Forbidden as exc:
            return "error", sanitize(str(exc))[:150] or "البوت ليس مشرفاً في القناة"
        except (TimedOut, NetworkError) as exc:
            if verified is not None and now - verified < NETWORK_GRACE_SECONDS:
                return "member", ""              # شبكة فقط + اشتراك مؤكَّد حديثاً
            return "error", f"تعذّر الاتصال بتيليجرام ({type(exc).__name__})"
        except TelegramError as exc:
            return "error", sanitize(str(exc))[:150]

        status = str(getattr(member, "status", ""))
        is_member = status in MEMBER_STATUSES or (status == "restricted" and bool(getattr(member, "is_member", False)))
        if is_member:
            self._remember(cache_key, now)
            return "member", ""
        self._verified_at.pop(cache_key, None)
        return "missing", ""

    def _remember(self, key: tuple[int, str], now: float) -> None:
        """حفظ نتيجة «مشترك» مع سقف لحجم الذاكرة (تُحذف المنتهية ثم الأقدم)."""
        if len(self._verified_at) >= MAX_CACHE_ENTRIES:
            expired = [k for k, ts in self._verified_at.items() if now - ts >= NETWORK_GRACE_SECONDS]
            for old in expired:
                self._verified_at.pop(old, None)
            while len(self._verified_at) >= MAX_CACHE_ENTRIES:
                self._verified_at.pop(next(iter(self._verified_at)))
        self._verified_at[key] = now

    def forget(self, telegram_id: int) -> None:
        """نسيان كاش مستخدم (بعد تغيير إعداد القنوات مثلاً)."""
        for key in [k for k in self._verified_at if k[0] == telegram_id]:
            self._verified_at.pop(key, None)

    def clear_cache(self) -> None:
        """تفريغ الكاش كله (عند تعديل القنوات من الإعدادات)."""
        self._verified_at.clear()

    async def _alert_config_problem(self, channels: list[RequiredChannel], problems: dict[str, str]) -> None:
        """تنبيه الأدمن (مرة يومياً لكل قناة) بأن القناة لا يمكن التحقق منها (إعداد/صلاحية البوت)."""
        from core.permissions import Permission

        by_key = {channel.key: channel for channel in channels}
        for key, reason in problems.items():
            channel = by_key.get(key)
            if channel is None or reason.startswith("تعذّر الاتصال"):
                continue                                   # الشبكة المؤقتة ليست مشكلة إعداد
            day_key = f"{key}:{utc_now().strftime('%Y%m%d')}"
            if day_key in self._alerted:
                continue
            if len(self._alerted) > 200:
                self._alerted.clear()
            self._alerted.add(day_key)
            try:
                async with self.db.transaction() as tx:
                    await self.notifications.notify_admins(
                        tx,
                        permission=Permission.SETTINGS_UPDATE,
                        token=f"sub-config:{key}:{utc_now().strftime('%Y%m%d')}",
                        title=f"⚠️ تعذّر التحقق من {channel.label}",
                        message=(
                            f"السبب: {reason}\n"
                            "المستخدمون الجدد لن يتجاوزوا بوابة الاشتراك حتى يُصلَح. تأكد أن البوت مشرف في "
                            "القناة وأن المعرّف صحيح (لوحة التحكم ← 📢 القنوات)."
                        ),
                    )
            except Exception:                              # noqa: BLE001 - التنبيه لا يجوز أن يكسر بوابة المستخدم
                logger.exception("تعذّر إدراج تنبيه مشكلة القناة %s", key)
```

---

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
```

---

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
from utils.validators import clean_text, normalize_digits

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
        if len(parts) == 1 and normalize_digits(code).replace(".", "", 1).isdigit():
            raise ValidationError(
                f"سعر صرف بلا رمز عملة: {text!r}",
                user_message="❌ أرسل رمز العملة قبل سعر الصرف. مثال: <code>USD 530</code>",
            )
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

---

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

---

## `services/user_service.py`

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
```

---

## `services/__init__.py`

```python
"""
حزمة الخدمات — طبقة منطق العمل بين الواجهة (المرحلة 3+) وقاعدة البيانات.

لماذا حاوية خدمات؟
    الخدمات مترابطة (الطلبات تحتاج المحفظة والمزودين والإشعارات...). بدل أن تبني كل
    نقطة دخول اعتمادياتها بنفسها — فتتسرب الأخطاء وتتكرر الكائنات — تُبنى هنا مرة
    واحدة بترتيب صحيح، ويُمرَّر كائن `ServiceContainer` واحد إلى بقية النظام.

ترتيب البناء (من الأدنى اعتماداً إلى الأعلى):
    settings → audit → notifications → auth → wallet → users → catalog
    → providers → orders → payments → tickets → stats → templates → broadcasts → security → backups
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from database.database import Database
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.backup_service import BackupService
from services.broadcast_service import BroadcastService
from services.catalog_service import CatalogService
from services.channel_service import ChannelService
from services.notification_service import NotificationService
from services.order_service import OrderService
from services.payment_service import PaymentService
from services.provider_service import ProviderService
from services.security_service import SecurityService
from services.settings_service import SettingsService
from services.stats_service import StatsService
from services.subscription_service import SubscriptionService
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
    "BackupService",
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
    backups: BackupService
    channels: ChannelService
    subscriptions: SubscriptionService

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
    backup_dir: Path | None = None,
    backup_channel_id: int | str | None = None,
    admin_alert_chat_id: int | str | None = None,
    app_version: str = "",
) -> ServiceContainer:
    """
    بناء كل الخدمات وربط اعتمادياتها بالترتيب الصحيح.

    المدخلات:
        db                   : اتصال قاعدة البيانات (مفتوح مسبقاً).
        repos                : المستودعات (تُبنى تلقائياً إن لم تُمرَّر).
        secret_box           : صندوق التشفير لمفاتيح المزودين (إجباري — لا مفاتيح واضحة).
        super_admin_ids      : معرفات الأدمن الأعلى من ملف البيئة (مسار طوارئ فقط).
        settings_ttl_seconds : مدة صلاحية كاش الإعدادات (يُستخدم 0 في الاختبارات لإلغاء الكاش).
        backup_dir           : مجلد النسخ الاحتياطية (الافتراضي: `backups` بجوار ملف القاعدة).
        backup_channel_id    : قناة النسخ الخارجية (None ⇒ غير مضبوطة)؛ مخصصة للنسخ فقط.
        admin_alert_chat_id  : `ADMIN_ALERT_CHAT_ID` من البيئة (بديل الإعداد إن لم يُضبط).
        app_version          : إصدار التطبيق (يُدوَّن في الملف الجانبي لكل نسخة).

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
    channels = ChannelService(
        db, repositories, settings, notifications,
        alert_chat_fallback=admin_alert_chat_id, backup_channel_id=backup_channel_id,
    )
    users = UserService(db, repositories, settings, audit, auth, notifications, channels)
    catalog = CatalogService(db, repositories, settings, audit, auth)
    providers = ProviderService(
        db, repositories, settings, audit, auth, notifications, secret_box
    )
    orders = OrderService(
        db, repositories, settings, wallet, catalog, providers, notifications, audit, auth, channels
    )
    payments = PaymentService(db, repositories, settings, wallet, notifications, audit, auth)
    tickets = TicketService(db, repositories, settings, notifications, audit, auth)
    stats = StatsService(db, repositories, settings, auth, providers, audit)
    template_service = TemplateService(db, repositories, auth, audit)
    broadcasts = BroadcastService(db, repositories, auth, audit, notifications, settings)

    backups = BackupService(
        db, repositories, settings, audit, auth, notifications,
        backup_dir=backup_dir if backup_dir is not None else db.path.parent / "backups",
        channel_id=backup_channel_id,
        app_version=app_version,
    )
    security = SecurityService(db, repositories, settings, auth, audit, backups)
    subscriptions = SubscriptionService(db, repositories, settings, notifications)

    logger.info("تم بناء طبقة الخدمات (%s خدمة)", 18)
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
        backups=backups,
        channels=channels,
        subscriptions=subscriptions,
    )
```

---

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

    # صندوق القنوات الدائم: تنبيهات الإدارة/المستخدمون الجدد (admin_alert) + توثيق الطلبات (orders_log).
    # قناة النسخ الاحتياطي ليست طرفاً هنا إطلاقاً (مخصصة للنسخ فقط).
    channel_report = await services.channels.flush(sender, limit=BATCH_LIMIT)
    if channel_report.claimed:
        logger.info("جولة قنوات: %s", channel_report)
```

---

## `jobs/maintenance_jobs.py`

```python
"""
مهام الصيانة الدورية.

    expire_old_payments  : إنهاء صلاحية طلبات الشحن التي تجاوزت مهلة المراجعة.
    auto_close_tickets   : إغلاق تذاكر الدعم الراكدة.
    database_maintenance : صيانة تقنية يومية لقاعدة البيانات (المرحلة 6).

الثلاثة تمنع تراكم ما لا قيمة له، واثنتان منها تُشعران صاحب الشأن بما حدث
بدل أن «يختفي» طلبه بصمت.

ملاحظة مهمة: صيانة قاعدة البيانات **لا تحذف أي بيانات تاريخية** — لا طلبات
ولا حركات مالية ولا تذاكر ولا سجلات تدقيق. تحذف فقط مفاتيح منع التكرار
(`idempotency_keys`) بعد انتهاء صلاحيتها، وطابور منشورات القنوات المنتهي (`channel_outbox`)
بعد 30 يوماً؛ وكلاهما تقني مؤقت بطبيعته.
"""

from __future__ import annotations

from telegram.ext import ContextTypes

from utils.datetime_utils import iso_minus_days
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: عدد طلبات الشحن التي تُفحص صلاحيتها في الجولة الواحدة
EXPIRE_BATCH = 50

#: مدة الاحتفاظ بمنشورات القنوات المنتهية في الطابور قبل تنظيفها
CHANNEL_OUTBOX_RETENTION_DAYS = 30


async def expire_old_payments(context: ContextTypes.DEFAULT_TYPE) -> None:
    """تعليم طلبات الشحن التي تجاوزت مهلة المراجعة كمنتهية + إشعار أصحابها."""
    services = context.application.bot_data["services"]
    count = await services.payments.expire_due(limit=EXPIRE_BATCH)
    if count:
        logger.info("طلبات شحن انتهت صلاحيتها: %s", count)


async def auto_close_tickets(context: ContextTypes.DEFAULT_TYPE) -> None:
    """إغلاق تذاكر الدعم التي لم يرد عليها أصحابها خلال المدة المحددة في الإعدادات."""
    services = context.application.bot_data["services"]
    count = await services.tickets.auto_close_idle()
    if count:
        logger.info("تذاكر أُغلقت تلقائياً لركودها: %s", count)


async def database_maintenance(context: ContextTypes.DEFAULT_TYPE) -> dict[str, int]:
    """
    صيانة تقنية يومية لقاعدة البيانات.

    ما تفعله:
        1. حذف مفاتيح منع التكرار المنتهية (`idempotency_keys`) — مؤقتة بطبيعتها.
        2. حذف منشورات القنوات المنتهية (`channel_outbox`: مرسلة/متجاوزة/فاشلة) الأقدم من
           `CHANNEL_OUTBOX_RETENTION_DAYS` يوماً — طابور تشغيلي لا سجل محاسبي (السجل الأصلي
           في `orders`/`audit_logs`).
        3. `PRAGMA wal_checkpoint(TRUNCATE)` لتقليص ملف الـWAL المتضخم.
        4. `PRAGMA optimize` لتحديث إحصاءات المخطط فتبقى الاستعلامات سريعة.

    ما **لا** تفعله: أي حذف لبيانات تاريخية، وأي `VACUUM` تلقائي (يقفل القاعدة
    مدة طويلة؛ يبقى قراراً يدوياً في أدوات الصيانة).

    المخرجات: عدّادات ما جرى (لتسجيلها في اللوق والاختبارات).
    """
    services = context.application.bot_data["services"]
    async with services.db.transaction() as tx:
        removed_keys = await services.repos.idempotency.cleanup_expired(tx)
        removed_posts = await services.repos.channel_outbox.delete_old(
            tx, iso_minus_days(CHANNEL_OUTBOX_RETENTION_DAYS)
        )

    checkpointed = 0
    try:
        await services.db.execute_raw("PRAGMA wal_checkpoint(TRUNCATE)")
        await services.db.execute_raw("PRAGMA optimize")
        checkpointed = 1
    except Exception as exc:                                        # noqa: BLE001
        # الصيانة التقنية ليست حرجة: نسجّلها ولا نُسقط المهمة على بقية خطواتها
        logger.warning("تعذّرت صيانة ملف قاعدة البيانات: %s", exc)

    result = {
        "idempotency_keys_removed": removed_keys,
        "channel_posts_removed": removed_posts,
        "checkpoint": checkpointed,
    }
    if removed_keys or removed_posts:
        logger.info("صيانة القاعدة: %s", result)
    return result
```

---

## `jobs/telegram_sender.py`

```python
"""
جسر الإرسال بين طابور الإشعارات وتيليجرام.

خدمة الإشعارات لا تعرف تيليجرام إطلاقاً — تطلب فقط دالة إرسال بالشكل:
    ``async sender(telegram_id, title, message) -> message_id | None``

هذا الملف يوفّر تلك الدالة ويُترجم أخطاء تيليجرام إلى استثناءات الطابور
حتى يقرر الطابور بنفسه: يُعيد المحاولة (مؤقت) أم يتوقف (محظور/نهائي).
"""

from __future__ import annotations

import html

from core.exceptions import (
    NotificationBlockedError,
    NotificationPermanentError,
    NotificationTemporaryError,
)
from telegram import Bot, LinkPreviewOptions
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TimedOut

#: أقصى طول نص رسالة في تيليجرام (نقتطع قبله بهامش أمان)
MAX_MESSAGE_LEN = 3900


class TelegramNotificationSender:
    """مُرسل إشعارات عبر تيليجرام مع تصنيف دقيق للأخطاء."""

    def __init__(self, bot: Bot) -> None:
        """تهيئة المرسل ببوت تيليجرام الجاهز."""
        self.bot = bot

    async def __call__(self, telegram_id: int, title: str, message: str) -> int | None:
        """
        إرسال إشعار واحد.

        المخرجات: رقم الرسالة في تيليجرام عند النجاح.

        الاستثناءات:
            NotificationBlockedError   : المستخدم حظر البوت (لا تُعاد المحاولة).
            NotificationTemporaryError : شبكة/مهلة/حد معدل (تُعاد المحاولة).
            NotificationPermanentError : رسالة غير صالحة أو محادثة غير موجودة.
        """
        text = self._format(title, message)
        try:
            sent = await self.bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        except Forbidden as exc:
            raise NotificationBlockedError(f"المستخدم {telegram_id} حظر البوت: {exc}") from exc
        except RetryAfter as exc:
            raise NotificationTemporaryError(
                f"تجاوز حد الإرسال، إعادة المحاولة بعد {exc.retry_after}ث"
            ) from exc
        except BadRequest as exc:            # يسبق NetworkError: BadRequest فرع منه في PTB فلا يصل إليه بعده
            text_error = str(exc).lower()
            if "chat not found" in text_error or "user is deactivated" in text_error:
                raise NotificationBlockedError(f"محادثة غير متاحة: {exc}") from exc
            raise NotificationPermanentError(f"رسالة مرفوضة من تيليجرام: {exc}") from exc
        except (TimedOut, NetworkError) as exc:
            raise NotificationTemporaryError(f"خطأ شبكة أثناء الإرسال: {exc}") from exc
        return sent.message_id

    @staticmethod
    def _format(title: str, message: str) -> str:
        """تنسيق الإشعار: عنوان عريض ثم النص، مع تهريب HTML واقتطاع الطويل."""
        safe_title = html.escape(title or "")
        safe_message = html.escape(message or "")
        body = f"<b>{safe_title}</b>\n\n{safe_message}" if safe_title else safe_message
        if len(body) > MAX_MESSAGE_LEN:
            body = body[: MAX_MESSAGE_LEN - 1] + "…"
        return body


class TelegramBroadcastSender:
    """
    مُرسل الرسائل الجماعية (نص أو صورة بتعليق) بنفس تصنيف أخطاء الإشعارات.

    لماذا مُرسل مستقل عن `TelegramNotificationSender`؟
        إشعار النظام له عنوان ونص ويُنسَّق بـHTML، أما الإذاعة فنص يكتبه الأدمن
        بحروفه وقد يرافقه ملف. خلطهما في دالة واحدة كان سيجبرنا على معاملات
        اختيارية تُربك الطرفين. التصنيف الدقيق للأخطاء مشترك عبر `_classify`.
    """

    def __init__(self, bot: Bot) -> None:
        """تهيئة المرسل ببوت تيليجرام الجاهز."""
        self.bot = bot

    async def __call__(
        self,
        telegram_id: int,
        text: str,
        media_file_id: str | None = None,
        media_type: str | None = None,
    ) -> int | None:
        """
        إرسال رسالة إذاعة واحدة.

        المخرجات: رقم الرسالة في تيليجرام عند النجاح.

        الاستثناءات: نفس استثناءات الإشعارات (محظور / مؤقت / نهائي) ليتعامل
        معها طابور الإذاعة بنفس المنطق المختبر.
        """
        body = html.escape(text or "")[:MAX_MESSAGE_LEN]
        try:
            if media_file_id and media_type == "photo":
                sent = await self.bot.send_photo(
                    chat_id=telegram_id,
                    photo=media_file_id,
                    caption=body[:1024] or None,
                    parse_mode=ParseMode.HTML,
                )
            elif media_file_id and media_type == "document":
                sent = await self.bot.send_document(
                    chat_id=telegram_id,
                    document=media_file_id,
                    caption=body[:1024] or None,
                    parse_mode=ParseMode.HTML,
                )
            else:
                sent = await self.bot.send_message(
                    chat_id=telegram_id,
                    text=body,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
        except Forbidden as exc:
            raise NotificationBlockedError(f"المستخدم {telegram_id} حظر البوت: {exc}") from exc
        except RetryAfter as exc:
            raise NotificationTemporaryError(
                f"تجاوز حد الإرسال، إعادة المحاولة بعد {exc.retry_after}ث"
            ) from exc
        except BadRequest as exc:            # يسبق NetworkError: BadRequest فرع منه في PTB فلا يصل إليه بعده
            text_error = str(exc).lower()
            if "chat not found" in text_error or "user is deactivated" in text_error:
                raise NotificationBlockedError(f"محادثة غير متاحة: {exc}") from exc
            raise NotificationPermanentError(f"رسالة مرفوضة من تيليجرام: {exc}") from exc
        except (TimedOut, NetworkError) as exc:
            raise NotificationTemporaryError(f"خطأ شبكة أثناء الإرسال: {exc}") from exc
        return sent.message_id
```

---

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
    6. بوابة الاشتراك الإجباري (القنوات الأربع) لغير الفريق الإداري — بعد حد المعدل حتى لا يُغرق
       أحدٌ تيليجرام بنداءات `getChatMember`.
    7. تحديث آخر نشاط (مرة كل دقيقة على الأكثر لتفادي كتابة عند كل ضغطة).

أي رفض يوقف سلسلة المعالجات عبر `ApplicationHandlerStop` فلا يصل التحديث
إلى بقية المعالجات إطلاقاً — وهذا ما يمنع تكرار فحوص الأمان داخل كل معالج.
"""

from __future__ import annotations

import time

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from core.exceptions import MaintenanceModeError, UserBannedError, ValidationError
from database.models import User
from handlers.common.ui import answer_callback, render, send
from keyboards.callback_data import NS_FLOW, NS_SUB, CallbackError, unpack
from keyboards.user_kb import subscription_kb
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
            # التسجيل مغلق من الإعدادات ومحاولة إنشاء حساب جديد — إلا الأدمن الأعلى المعتمد من البيئة:
            # لا يجوز أن يُقفل المالك خارج بوته بسبب إغلاق التسجيل
            if not services.auth.is_emergency_super_admin(telegram_user.id):
                await answer_callback(update)
                await send(update, context, exc.user_message)
                raise ApplicationHandlerStop from None
            await services.auth.bootstrap_super_admins((telegram_user.id,))
            user = await services.users.get_by_telegram(telegram_user.id)
            if user is None:
                raise ApplicationHandlerStop from None
            created = False

        # الأدمن الأعلى المعتمد من SUPER_ADMIN_IDS: تصحيح لحظي لدور مفقود أو حظر خاطئ (يُدقَّق)
        user = await services.auth.bootstrap_user(user)

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

        # 4) الاشتراك الإجباري (الفريق الإداري معفى)
        if not is_staff:
            await self._enforce_subscription(update, context, services, telegram_user.id)

        # 5) تحديث آخر نشاط بتهدئة
        await self._touch_activity(context, services, user)

    async def _enforce_subscription(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, services: ServiceContainer, telegram_id: int
    ) -> None:
        """
        بوابة الاشتراك: غير المشترك فعلياً في كل القنوات المطلوبة يرى شاشة الاشتراك فقط.

        • ضغط «✅ تحقق» يتجاوز الكاش ويعيد الفحص من تيليجرام؛ نجاحه يمرّر التحديث لمعالجه (القائمة الرئيسية).
        • الفشل مغلق: تعذّر التحقق لا يُعدّ اشتراكاً (يُبلَّغ المستخدم بوضوح ويُنبَّه الأدمن مرة يومياً).

        الاستثناءات:
            ApplicationHandlerStop : المستخدم غير مكتمل الاشتراك.
        """
        is_check = False
        if update.callback_query is not None and update.callback_query.data:
            try:
                callback = unpack(update.callback_query.data)
                is_check = callback.namespace == NS_SUB and callback.action == "check"
            except CallbackError:
                is_check = False

        status = await services.subscriptions.check(context.bot, telegram_id, force=is_check)
        if status.ok:
            return

        lines: list[str] = []
        missing_keys = {channel.key for channel in status.missing}
        buttons: list[tuple[str, str | None]] = []
        for channel in status.channels:
            if channel.key in missing_keys:
                lines.append(ar.SUB_LINE_MISSING.format(title=channel.title))
                buttons.append((channel.title, channel.ref.join_url))
            elif channel.key in status.unverifiable:
                lines.append(ar.SUB_LINE_UNKNOWN.format(title=channel.title))
                if channel.ref.join_url:
                    buttons.append((channel.title, channel.ref.join_url))
            else:
                lines.append(ar.SUB_LINE_OK.format(title=channel.title))
        text = ar.SUB_GATE_TITLE + "\n".join(lines)
        if status.unverifiable:
            text += ar.SUB_GATE_UNVERIFIABLE_NOTE

        if is_check:
            if status.missing:
                names = "، ".join(channel.label for channel in status.missing)
                await answer_callback(update, ar.SUB_CHECK_FAILED.format(names=names), alert=True)
            else:
                await answer_callback(update, ar.SUB_CHECK_UNVERIFIED, alert=True)
        else:
            await answer_callback(update)
        await render(update, context, text, subscription_kb(buttons))
        raise ApplicationHandlerStop

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

---

## `handlers/common/navigation.py`

```python
"""
شاشة البداية والقائمة الرئيسية والأوامر العامة.

يشمل:
    /start  : تسجيل/ترحيب ثم القائمة الرئيسية.
    /help   : شرح مختصر لطريقة الاستخدام.
    /id     : عرض معرف تيليجرام (يطلبه الدعم أحياناً).
    nav:home: العودة للقائمة الرئيسية من أي شاشة.
    nav:page: زر عدّاد الصفحات — يعرض موضع المستخدم بدل أن يكون زراً صامتاً.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, delete_quietly, render, send
from keyboards.callback_data import unpack
from keyboards.user_kb import main_menu_kb
from middlewares.context import require_user, services_of
from texts import ar
from utils.formatters import money_text, safe

#: مفتاح user_data لرقم رسالة القائمة الرئيسية الأخيرة (في الذاكرة؛ يضيع عند إعادة التشغيل وهذا مقبول)
MENU_MESSAGE_KEY = "menu_msg_id"


async def is_admin_user(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    هل يملك صاحب هذا التحديث حق دخول لوحة التحكم؟

    تُستدعى قبل بناء القائمة الرئيسية حتى يظهر زر «🛠 لوحة التحكم» لمن يستحقه
    فقط، وتختفي فوراً عمن سُحبت صلاحيته (تُقرأ من قاعدة البيانات كل مرة).
    """
    services = services_of(context)
    return await services.auth.is_admin(require_user(context))


async def main_menu_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    بناء نص القائمة الرئيسية بأرقام حقيقية (رصيد، طلبات نشطة، تذاكر مفتوحة).

    المخرجات: نص HTML جاهز للعرض.
    """
    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    summary = await services.users.summary(user)
    return ar.MAIN_MENU_BODY.format(
        balance=money_text(user.balance_units, symbol),
        active_orders=summary.active_orders,
        open_tickets=summary.tickets_open,
    )


@guarded
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الأمر /start: رسالة ترحيب (مختلفة للجديد) ثم القائمة الرئيسية."""
    services = services_of(context)
    user = require_user(context)
    is_new = bool(context.user_data and context.user_data.get("is_new_user"))

    if is_new:
        welcome = await services.settings.get_str(
            "welcome_message", "أهلاً بك في بوت خدمات التواصل الاجتماعي."
        )
        greeting = ar.START_NEW.format(name=safe(user.first_name or "", limit=30), welcome=safe(welcome))
    else:
        greeting = ar.START_BACK.format(name=safe(user.first_name or "", limit=30))

    # رسالة واحدة (ترحيب + قائمة) بدل رسالتين، وتنظيف المحادثة: حذف أمر /start نفسه والقائمة السابقة
    chat_id = update.effective_chat.id if update.effective_chat else None
    previous_menu = context.user_data.get(MENU_MESSAGE_KEY) if context.user_data is not None else None
    sent = await send(
        update,
        context,
        greeting + await main_menu_text(context),
        main_menu_kb(is_admin=await is_admin_user(context)),
    )
    if chat_id is not None:
        if update.message is not None:
            await delete_quietly(context, chat_id, update.message.message_id)
        if previous_menu and (sent is None or previous_menu != sent.message_id):
            await delete_quietly(context, chat_id, previous_menu)
    if sent is not None and context.user_data is not None:
        context.user_data[MENU_MESSAGE_KEY] = sent.message_id


@guarded
async def home_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """زر «القائمة الرئيسية» من أي شاشة."""
    await answer_callback(update)
    await render(
        update,
        context,
        await main_menu_text(context),
        main_menu_kb(is_admin=await is_admin_user(context)),
    )
    _remember_menu_message(update, context)


def _remember_menu_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """حفظ رقم رسالة القائمة الحالية ليُحذف عند /start التالي بدل تراكم القوائم في المحادثة."""
    query = update.callback_query
    if query is not None and query.message is not None and context.user_data is not None:
        context.user_data[MENU_MESSAGE_KEY] = query.message.message_id


@guarded
async def subscription_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    زر «✅ تحقق من الاشتراك»: يصل هنا فقط بعد أن أكّدت الطبقة الوسيطة الاشتراك الفعلي.

    (غير المشترك لا يصل لهذا المعالج؛ تُعيد الطبقة الوسيطة عرض شاشة البوابة وتوقف التحديث.)
    """
    await answer_callback(update, ar.SUB_CHECK_OK)
    await render(
        update,
        context,
        await main_menu_text(context),
        main_menu_kb(is_admin=await is_admin_user(context)),
    )
    _remember_menu_message(update, context)


@guarded
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الأمر /help: شرح خطوات الاستخدام والأوامر المتاحة."""
    await send(
        update, context, ar.HELP_TEXT, main_menu_kb(is_admin=await is_admin_user(context))
    )


@guarded
async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الأمر /id: عرض معرف المستخدم في تيليجرام."""
    user = require_user(context)
    await send(update, context, ar.ID_TEXT.format(telegram_id=user.telegram_id))


@guarded
async def page_indicator_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    زر عدّاد الصفحات: يعرض موضع المستخدم الحالي كتنبيه منبثق.

    سبب وجوده: القاعدة تمنع الأزرار بلا وظيفة — فحتى زر العرض يفعل شيئاً مفيداً.
    """
    data = unpack(update.callback_query.data if update.callback_query else None)
    await answer_callback(
        update, ar.PAGE_INFO.format(page=data.int_arg(0, 1), pages=data.int_arg(1, 1))
    )
```

---

## `handlers/user/catalog.py`

```python
"""
شاشات تصفح الخدمات: التصنيفات ← خدمات التصنيف (بصفحات) ← بطاقة الخدمة.

كل البيانات تأتي من `CatalogService`، ولا تُعرض خدمة غير متاحة للطلب
(معطّلة أو مؤرشفة أو مزودها متوقف) — القائمة نفسها مفلترة من طبقة الخدمات.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render
from keyboards.callback_data import unpack
from keyboards.user_kb import categories_kb, service_card_kb, services_kb
from middlewares.context import require_user, services_of
from texts import ar
from utils.formatters import local_amount, price_pair, safe

#: عدد الخدمات المعروضة في كل صفحة
PAGE_SIZE = 6


@guarded
async def categories_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض التصنيفات التي تحتوي خدمات متاحة فعلاً."""
    await answer_callback(update)
    services = services_of(context)
    categories = await services.catalog.categories()
    if not categories:
        await render(update, context, ar.CATEGORIES_EMPTY, categories_kb([]))
        return
    await render(update, context, ar.CATEGORIES_TITLE, categories_kb(categories))


@guarded
async def services_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض صفحة من خدمات تصنيف معيّن."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    category_id = data.int_arg(0)
    page_number = max(1, data.int_arg(1, 1))

    services = services_of(context)
    symbol = await services.settings.money_symbol()
    usd_rate = await services.settings.usd_rate()
    page = await services.catalog.services_page(category_id, page=page_number, page_size=PAGE_SIZE)

    categories = {category.id: category for category in await services.catalog.categories()}
    category = categories.get(category_id)
    if category is None or not page.items:
        await render(
            update,
            context,
            ar.SERVICES_EMPTY,
            services_kb([], category_id=category_id, page=1, total_pages=1, symbol=symbol),
        )
        return

    text = ar.SERVICES_TITLE.format(
        emoji=category.emoji,
        category=safe(category.name_ar),
        page=page.page,
        pages=page.total_pages,
    )
    await render(
        update,
        context,
        text,
        services_kb(
            page.items,
            category_id=category_id,
            page=page.page,
            total_pages=page.total_pages,
            symbol=symbol,
            usd_rate=usd_rate,
        ),
    )


@guarded
async def service_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة خدمة واحدة: الرقم، السعر بالدولار ومقابله، السرعة/الجودة/الضمان، الحدّان، ورصيد المستخدم."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    await show_service_card(update, context, data.int_arg(0), data.int_arg(1), max(1, data.int_arg(2, 1)))


async def show_service_card(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int, category_id: int, page: int
) -> None:
    """
    عرض بطاقة خدمة (تُستعمل من التصفح ومن المفضلة ومن تبديل ⭐ دون تكرار الكود).

    الحقول الناقصة تُعرض «غير محددة» لا فراغاً؛ والسرعة تسقط إلى `avg_time_text` القديم إن لم تُضبط.
    """
    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    usd_rate = await services.settings.usd_rate()
    service = await services.catalog.get_available_service(service_id)
    balance_units = (await services.users.get(user.id) or user).balance_units

    usd, local = price_pair(service.price_per_1000_units, symbol, usd_rate)
    description = f"📝 {safe(service.description, limit=300)}\n" if service.description else ""
    text = ar.SERVICE_CARD.format(
        name=safe(service.name),
        service_id=service.id,
        usd=usd,
        local=local,
        rate=f"{usd_rate.normalize():f}",
        symbol=safe(symbol),
        speed=safe(service.speed_text or service.avg_time_text) or ar.FIELD_UNSET,
        quality=safe(service.quality_text) or ar.FIELD_UNSET,
        guarantee=safe(service.guarantee_text) or ar.FIELD_UNSET,
        min_quantity=f"{service.min_quantity:,}",
        max_quantity=f"{service.max_quantity:,}",
        description=description,
        balance=local_amount(balance_units, symbol),
    )
    favorite = await services.catalog.is_favorite(user, service.id)
    await render(
        update, context, text, service_card_kb(service, category_id=category_id, page=page, is_favorite=favorite)
    )
```

---

## `handlers/user/favorites.py`

```python
"""
المفضلة: إضافة/إزالة خدمة من بطاقتها، وقائمة المفضلة من القائمة الرئيسية.

الشاشات:
    fav:list:<صفحة>                   : قائمة المفضلة (المتاحة للطلب فقط).
    fav:add:<خدمة>:<تصنيف>:<صفحة>     : إضافة (بلا تكرار) ثم تحديث البطاقة نفسها.
    fav:del:<خدمة>:<تصنيف>:<صفحة>     : إزالة ثم تحديث البطاقة نفسها.
التصنيف 0 يعني أن البطاقة فُتحت من المفضلة.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from core.exceptions import ServiceNotAvailableError
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render
from handlers.user.catalog import show_service_card
from keyboards.callback_data import NS_FAV, pattern, unpack
from keyboards.user_kb import favorites_kb
from middlewares.context import require_user, services_of
from texts import ar

#: عدد الخدمات في صفحة المفضلة
PAGE_SIZE = 6


@guarded
async def favorites_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة مفضلة المستخدم (الأحدث إضافةً أولاً)."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    services = services_of(context)
    user = require_user(context)
    items, page, pages = await services.catalog.favorites_page(user, page=data.int_arg(0, 1), page_size=PAGE_SIZE)
    symbol = await services.settings.money_symbol()
    usd_rate = await services.settings.usd_rate()
    if not items:
        await render(update, context, ar.FAVORITES_EMPTY, favorites_kb([], page=1, total_pages=1, symbol=symbol, usd_rate=usd_rate))
        return
    await render(
        update,
        context,
        ar.FAVORITES_TITLE.format(page=page, pages=pages),
        favorites_kb(items, page=page, total_pages=pages, symbol=symbol, usd_rate=usd_rate),
    )


@guarded
async def favorite_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إضافة/إزالة ثم إعادة عرض بطاقة الخدمة (تحرير نفس الرسالة)."""
    data = unpack(update.callback_query.data if update.callback_query else None)
    service_id, category_id, page = data.int_arg(0), data.int_arg(1), max(1, data.int_arg(2, 1))
    services = services_of(context)
    user = require_user(context)
    try:
        if data.action == "add":
            added = await services.catalog.add_favorite(user, service_id)
            await answer_callback(update, ar.FAVORITE_ADDED if added else ar.FAVORITE_EXISTS)
        else:
            removed = await services.catalog.remove_favorite(user, service_id)
            await answer_callback(update, ar.FAVORITE_REMOVED if removed else ar.FAVORITE_NOT_FOUND)
    except ServiceNotAvailableError:
        await answer_callback(update, "❌ هذه الخدمة لم تعد متاحة", alert=True)
        await favorites_screen(update, context)
        return
    await show_service_card(update, context, service_id, category_id, page)


def handlers() -> list[CallbackQueryHandler]:
    """أزرار المفضلة."""
    return [
        CallbackQueryHandler(favorites_screen, pattern=pattern(NS_FAV, "list")),
        CallbackQueryHandler(favorite_toggle, pattern=pattern(NS_FAV, "add")),
        CallbackQueryHandler(favorite_toggle, pattern=pattern(NS_FAV, "del")),
    ]
```

---

## `handlers/user/order_flow.py`

```python
"""
محادثة إنشاء طلب جديد (ConversationHandler).

المسار: بطاقة الخدمة ← 🔗 الرابط ← 🔢 الكمية ← 🧾 المراجعة ← ✅ تأكيد.

ضمانات مهمة:
    • `client_request_id` يُولَّد **مرة واحدة عند بدء المحادثة**، فالضغط المزدوج
      على «تأكيد» يُعيد نفس الطلب ولا ينشئ طلبين (منع تكرار من طبقة الخدمات).
    • التحقق من الرابط والكمية يتم عند الإدخال، وتتكرر الخطوة عند الخطأ بدل
      إسقاط المحادثة.
    • عدم كفاية الرصيد لا يُنهي المسار بصمت: تُعرض قيمة النقص مع زر شحن مباشر.
    • الإلغاء متاح في كل خطوة (زر ❌ أو الأمر /cancel) ولا يُخصم شيء قبل التأكيد.
"""

from __future__ import annotations

import uuid

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from core.exceptions import InsufficientBalanceError
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.callback_data import unpack
from keyboards.common_kb import cancel_markup, confirm_cancel_markup
from keyboards.user_kb import insufficient_balance_kb, main_menu_kb
from middlewares.context import reload_user, require_user, services_of
from texts import ar
from utils.formatters import money_text, price_line, safe, short_link
from utils.link_rules import rule_of

#: حالات المحادثة
ASK_LINK, ASK_QUANTITY, CONFIRM = range(3)

#: مفتاح بيانات المحادثة داخل `user_data`
FLOW_KEY = "order_flow"


def _flow(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """قراءة بيانات المحادثة الحالية (قاموس فارغ إن ضاعت الجلسة)."""
    if context.user_data is None:
        return {}
    return context.user_data.get(FLOW_KEY) or {}


def _clear(context: ContextTypes.DEFAULT_TYPE) -> None:
    """مسح بيانات المحادثة بعد انتهائها أو إلغائها."""
    if context.user_data is not None:
        context.user_data.pop(FLOW_KEY, None)


def _link_hint(service) -> str:
    """تلميح طلب الرابط: مثال خاص بقاعدة الخدمة إن وُجدت، وإلا المثال العام."""
    rule = rule_of(service.link_rule)
    if rule is None:
        return ar.ORDER_LINK_HINT_GENERIC
    return ar.ORDER_LINK_HINT_RULE.format(label=rule.label, example=safe(rule.example))


@guarded
async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء المحادثة من زر «🛒 اطلب الآن» وسؤال المستخدم عن الرابط."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    service_id = data.int_arg(0)

    services = services_of(context)
    service = await services.catalog.get_available_service(service_id)

    if context.user_data is not None:
        context.user_data[FLOW_KEY] = {
            "service_id": service.id,
            "service_name": service.name,
            # معرف فريد للطلب يُولَّد الآن: الضغط المزدوج على تأكيد لن يُنشئ طلبين
            "client_request_id": uuid.uuid4().hex,
        }

    await render(
        update,
        context,
        ar.ORDER_ASK_LINK.format(service=safe(service.name), hint=_link_hint(service)),
        cancel_markup(),
    )
    return ASK_LINK


@guarded
async def receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال الرابط والتحقق منه ثم سؤال المستخدم عن الكمية."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, ar.ERR_NOT_TEXT, cancel_markup())
        return ASK_LINK

    flow = _flow(context)
    if not flow:
        await send(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    services = services_of(context)
    service = await services.catalog.get_available_service(flow["service_id"])

    from utils.validators import validate_link      # تحقق فوري قبل إزعاج المستخدم بخطوة أخرى

    link = validate_link(message.text, pattern=service.link_pattern, rule=service.link_rule)
    flow["link"] = link

    await send(
        update,
        context,
        ar.ORDER_ASK_QUANTITY.format(
            service=safe(service.name),
            link=short_link(link),
            min_quantity=service.min_quantity,
            max_quantity=service.max_quantity,
        ),
        cancel_markup(),
    )
    return ASK_QUANTITY


@guarded
async def receive_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال الكمية وحساب التكلفة وعرض ملخص الطلب قبل التأكيد."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, ar.ERR_NOT_TEXT, cancel_markup())
        return ASK_QUANTITY

    flow = _flow(context)
    if not flow or "link" not in flow:
        await send(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    usd_rate = await services.settings.usd_rate()
    service = await services.catalog.get_available_service(flow["service_id"])

    quote = await services.catalog.quote(service, message.text)
    flow["quantity"] = quote.quantity
    flow["cost_units"] = quote.cost_units

    balance = user.balance_units
    if balance < quote.cost_units:
        text = ar.ORDER_SUMMARY_NO_BALANCE.format(
            service=safe(service.name),
            link=short_link(flow["link"]),
            quantity=quote.quantity,
            cost=price_line(quote.cost_units, symbol, usd_rate),
            balance=money_text(balance, symbol),
            missing=money_text(quote.cost_units - balance, symbol),
        )
        await send(update, context, text, insufficient_balance_kb(service.category_id, 1))
        _clear(context)
        return ConversationHandler.END

    text = ar.ORDER_SUMMARY.format(
        service=safe(service.name),
        link=short_link(flow["link"]),
        quantity=quote.quantity,
        cost=price_line(quote.cost_units, symbol, usd_rate),
        balance=money_text(balance, symbol),
        balance_after=money_text(balance - quote.cost_units, symbol),
    )
    await send(update, context, text, confirm_cancel_markup())
    return CONFIRM


@guarded
async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تأكيد الطلب: إنشاؤه عبر `OrderService` (خصم + سجل + إشعار في معاملة واحدة)."""
    await answer_callback(update)
    flow = _flow(context)
    if not flow or "quantity" not in flow:
        await render(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    usd_rate = await services.settings.usd_rate()

    try:
        order = await services.orders.create_order(
            user,
            service_id=flow["service_id"],
            link=flow["link"],
            quantity=flow["quantity"],
            client_request_id=flow["client_request_id"],
        )
    except InsufficientBalanceError:
        # قد يكون الرصيد أُنفق في محادثة أخرى بين المراجعة والتأكيد
        service = await services.catalog.get_available_service(flow["service_id"])
        fresh = await reload_user(context)
        await render(
            update,
            context,
            ar.ORDER_SUMMARY_NO_BALANCE.format(
                service=safe(service.name),
                link=short_link(flow["link"]),
                quantity=flow["quantity"],
                cost=price_line(flow["cost_units"], symbol, usd_rate),
                balance=money_text(fresh.balance_units, symbol),
                missing=money_text(max(0, flow["cost_units"] - fresh.balance_units), symbol),
            ),
            insufficient_balance_kb(service.category_id, 1),
        )
        _clear(context)
        return ConversationHandler.END

    fresh = await reload_user(context)
    await render(
        update,
        context,
        ar.ORDER_CREATED.format(
            code=order.public_code or f"#{order.id}",
            service=safe(order.service_name_snapshot),
            quantity=order.quantity,
            cost=price_line(order.cost_units, symbol, usd_rate),
            balance=money_text(fresh.balance_units, symbol),
        ),
        main_menu_kb(),
    )
    _clear(context)
    return ConversationHandler.END


@guarded
async def cancel_order_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء المحادثة في أي خطوة (زر ❌ أو الأمر /cancel) — لا خصم ولا طلب."""
    await answer_callback(update)
    _clear(context)
    if update.callback_query is not None:
        await render(update, context, ar.ORDER_CANCELLED_FLOW, main_menu_kb())
    else:
        await send(update, context, ar.ORDER_CANCELLED_FLOW, main_menu_kb())
    return ConversationHandler.END
```

---

## `handlers/admin/channels.py`

```python
"""
قسم «📢 القنوات» في لوحة التحكم (المرحلة 13): رؤية وتشخيص كل القنوات في مكان واحد.

الشاشات:
    ch:home          : القنوات المطلوبة للاشتراك + وجهات النشر + حالة صندوق النشر.
    ch:check         : فحص فعلي عبر تيليجرام (وجود القناة، البوت مشرف، صلاحية النشر) مع شرح السبب والحل.
    ch:test:<نوع>    : إرسال رسالة اختبار حقيقية إلى وجهة التنبيهات أو التوثيق (alert|orders).

القواعد:
    • عرض الشاشة `settings.view`، والفحص والاختبار `settings.update` — على الـcallback نفسه (دفاع مزدوج).
    • تعديل القيم يتم من الإعدادات (مجموعة `channels`) وتُفحص قبل الحفظ؛ هنا قراءة وتشخيص فقط.
    • قناة النسخ الاحتياطي تُفحص ولا يُرسل إليها أي اختبار (مخصصة للنسخ فقط).
"""

from __future__ import annotations

import asyncio

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from core.exceptions import NotificationBlockedError, NotificationPermanentError, NotificationTemporaryError
from core.permissions import Permission
from handlers.admin.common import admin_required, args
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render
from jobs.telegram_sender import TelegramNotificationSender
from keyboards.admin_kb import channels_home_kb, channels_result_kb
from keyboards.callback_data import NS_ADM_CHN, pattern
from middlewares.context import require_user, services_of
from services.channel_service import KIND_ADMIN_ALERT, KIND_ORDERS_LOG, ChannelCheck
from services.subscription_service import REQUIRED_CHANNEL_SPECS
from texts import admin_ar as t
from utils.channel_ref import ChannelRefError, parse_channel_value
from utils.formatters import safe
from utils.logging_setup import get_logger

logger = get_logger(__name__)


def _value_text(ref: int | str | None) -> str:
    """نص عرض معرّف قناة (أو «غير مضبوطة»)."""
    return safe(str(ref), limit=40) if ref is not None else t.CHANNELS_UNSET


async def _subscription_refs(services) -> list[tuple[str, str, int | str | None]]:
    """القنوات الأربع: (مفتاح الإعداد، العنوان، المعرّف أو None) — القيمة المعطوبة تُعامل كغير مضبوطة."""
    items: list[tuple[str, str, int | str | None]] = []
    for key, emoji, label in REQUIRED_CHANNEL_SPECS:
        raw = (await services.settings.get_str(key, "")).strip()
        ref: int | str | None = None
        if raw:
            try:
                ref = parse_channel_value(raw).chat_id
            except ChannelRefError:
                ref = None
        items.append((key, f"{emoji} {label}", ref))
    return items


async def _destinations(services) -> list[tuple[str, str, int | str | None]]:
    """وجهات النشر الفعلية: (النوع، العنوان، المعرّف الفعلي أو None) + قناة النسخ من البيئة."""
    alert, _ = await services.channels.destination(KIND_ADMIN_ALERT)
    orders_log, _ = await services.channels.destination(KIND_ORDERS_LOG)
    return [
        ("alert", t.CHANNELS_ALERT_LABEL, alert),
        ("orders", t.CHANNELS_ORDERS_LABEL, orders_log),
        ("backup", t.CHANNELS_BACKUP_LABEL, services.backups.channel_id),
    ]


@guarded
@admin_required(Permission.SETTINGS_VIEW)
async def home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة القنوات: ما هو مضبوط الآن (بلا اتصال بتيليجرام) وحالة صندوق النشر."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    required = await services.settings.get_bool("subscription_required", True)
    subscription_lines = "\n".join(
        t.CHANNELS_LINE.format(icon="•", label=label, value=_value_text(ref))
        for _, label, ref in await _subscription_refs(services)
    )
    destination_lines = "\n".join(
        t.CHANNELS_LINE.format(icon="•", label=label, value=_value_text(ref))
        for _, label, ref in await _destinations(services)
    )
    counts = await services.repos.channel_outbox.count_by_status()
    outbox = t.CHANNELS_OUTBOX.format(
        queued=counts.get("queued", 0), sent=counts.get("sent", 0),
        failed=counts.get("failed", 0), skipped=counts.get("skipped", 0),
    )
    can_edit = await services.auth.has_permission(admin, Permission.SETTINGS_UPDATE)
    await render(
        update,
        context,
        t.CHANNELS_HOME.format(
            required=t.CHANNELS_REQUIRED_ON if required else t.CHANNELS_REQUIRED_OFF,
            subscription_lines=subscription_lines,
            destination_lines=destination_lines,
            outbox=outbox,
        ),
        channels_home_kb(can_edit=can_edit),
    )


def _format_check(label: str, result: ChannelCheck) -> str:
    """سطر/أسطر نتيجة فحص قناة واحدة."""
    value = _value_text(result.ref)
    if result.ref is None:
        return t.CHANNELS_CHECK_UNSET.format(label=label)
    if result.ok is True:
        title = f" ({safe(result.title, limit=30)})" if result.title else ""
        return t.CHANNELS_CHECK_OK.format(label=label, value=value, title=title)
    if result.ok is None:
        return t.CHANNELS_CHECK_UNKNOWN.format(label=label, value=value, problem=safe(result.problem, limit=80))
    hints = "".join(t.CHANNELS_HINT.format(hint=safe(hint, limit=140)) for hint in result.hints)
    return t.CHANNELS_CHECK_BAD.format(label=label, value=value, problem=safe(result.problem, limit=100), hints=hints)


@guarded
@admin_required(Permission.SETTINGS_UPDATE)
async def check_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """فحص فعلي لكل القنوات المضبوطة بالتوازي (قنوات الاشتراك + الوجهات + النسخ)."""
    await answer_callback(update, "🔍")
    services = services_of(context)
    jobs: list[tuple[str, int | str | None, bool]] = []
    for _, label, ref in await _subscription_refs(services):
        jobs.append((label, ref, False))
    for _, label, ref in await _destinations(services):
        jobs.append((label, ref, True))
    results = await asyncio.gather(
        *(services.channels.diagnose(context.bot, label, ref, needs_post=needs_post) for label, ref, needs_post in jobs)
    )
    lines = "\n".join(_format_check(label, result) for (label, _, _), result in zip(jobs, results))
    await render(update, context, t.CHANNELS_CHECK_TITLE.format(lines=lines), channels_result_kb())


@guarded
@admin_required(Permission.SETTINGS_UPDATE)
async def test_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إرسال رسالة اختبار حقيقية إلى وجهة التنبيهات أو التوثيق والإبلاغ بنتيجة واضحة."""
    await answer_callback(update)
    services = services_of(context)
    kind_code = args(update).arg(0)
    kind, label = (
        (KIND_ADMIN_ALERT, t.CHANNELS_ALERT_LABEL) if kind_code == "alert" else (KIND_ORDERS_LOG, t.CHANNELS_ORDERS_LABEL)
    )
    destination, reason = await services.channels.destination(kind)
    if destination is None:
        text = t.CHANNELS_TEST_NO_DEST.format(label=label, reason=safe(reason, limit=80))
    else:
        sender = TelegramNotificationSender(context.bot)
        try:
            await sender(destination, t.CHANNELS_TEST_TITLE, t.CHANNELS_TEST_BODY)
        except (NotificationBlockedError, NotificationPermanentError, NotificationTemporaryError) as exc:
            text = t.CHANNELS_TEST_FAIL.format(label=label, reason=safe(str(exc), limit=160))
        else:
            text = t.CHANNELS_TEST_OK.format(label=label)
    await render(update, context, text, channels_result_kb())


def conversations() -> list:
    """لا محادثات في هذا القسم (تعديل القيم عبر الإعدادات)."""
    return []


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم القنوات."""
    return [
        CallbackQueryHandler(home_screen, pattern=pattern(NS_ADM_CHN, "home")),
        CallbackQueryHandler(check_screen, pattern=pattern(NS_ADM_CHN, "check")),
        CallbackQueryHandler(test_action, pattern=pattern(NS_ADM_CHN, "test")),
    ]
```

---

## `handlers/admin/__init__.py`

```python
"""
حزمة لوحة التحكم: تجميع معالجات كل الأقسام في مكانين فقط.

تصدّر هذه الحزمة دالتين يستهلكهما `handlers/registry.py`:

    admin_conversations()   : كل محادثات الأدمن (تُسجَّل قبل أزرار الشاشات).
    admin_screen_handlers() : كل أزرار شاشات الأدمن.

كل وحدة قسم (`users`, `payments`, ...) تصدّر `conversations()` و`screens()`
فيبقى ترتيب التسجيل في مكان واحد ويظل من السهل التأكد أن كل زر له معالج.
"""

from __future__ import annotations

from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler

from handlers.admin import (
    backup,
    broadcast,
    catalog,
    channels,
    dashboard,
    logs,
    orders,
    payment_methods,
    payments,
    providers,
    security,
    settings,
    stats,
    system,
    templates,
    tickets,
    users,
)
from keyboards.callback_data import NS_ADMIN, pattern

#: وحدات الأقسام بالترتيب الذي تُسجَّل به معالجاتها
SECTIONS = (
    users,
    payments,
    payment_methods,
    orders,
    tickets,
    catalog,
    providers,
    settings,
    logs,
    broadcast,
    templates,
    security,
    channels,
    backup,
    stats,
    system,
)

__all__ = [
    "admin_conversations",
    "admin_screen_handlers",
    "admin_command_handlers",
    "SECTIONS",
]


def admin_conversations() -> list[ConversationHandler]:
    """كل محادثات لوحة التحكم مجموعة من كل الأقسام."""
    collected: list[ConversationHandler] = []
    for section in SECTIONS:
        collected.extend(section.conversations())
    return collected


def admin_screen_handlers() -> list[CallbackQueryHandler]:
    """كل أزرار شاشات لوحة التحكم (خارج المحادثات)."""
    collected: list[CallbackQueryHandler] = [
        CallbackQueryHandler(dashboard.panel_screen, pattern=pattern(NS_ADMIN, "home")),
        CallbackQueryHandler(dashboard.health_screen, pattern=pattern(NS_ADMIN, "health")),
    ]
    for section in SECTIONS:
        collected.extend(section.screens())
    return collected


def admin_command_handlers() -> list[CommandHandler]:
    """أوامر لوحة التحكم (/admin فقط حالياً)."""
    return [CommandHandler("admin", dashboard.admin_command)]
```

---

## `handlers/registry.py`

```python
"""
تسجيل كل معالجات البوت في مكان واحد.

لماذا ملف تسجيل مستقل؟
    • ترتيب المعالجات مهم جداً في python-telegram-bot: المحادثات قبل الأوامر
      العامة، والمسارات الاحتياطية في النهاية. تجميعها هنا يجعل الترتيب مرئياً
      ومراجعته سهلة بدل تناثره في `main.py`.
    • يتيح اختباراً آلياً يتحقق أن **كل زر في الواجهة له معالج فعلي**
      (`tests/integration/test_no_dead_buttons.py`) — تطبيقاً لقاعدة
      «ممنوع أزرار بلا وظيفة».

ترتيب المجموعات:
    المجموعة -10 : الطبقة الوسيطة (مستخدم/حظر/صيانة/حد استخدام) — تسبق كل شيء.
    المجموعة  0  : المحادثات ثم الأوامر ثم أزرار الشاشات ثم المسارات الاحتياطية.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import (
    Application,
    BaseHandler,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from handlers.common.conversation import conversation
from handlers.admin import (
    admin_command_handlers,
    admin_conversations,
    admin_screen_handlers,
)
from handlers.common import errors, fallbacks, navigation
from handlers.user import account, catalog, deposit, favorites, order_flow, orders, support, wallet
from keyboards.callback_data import (
    NS_ACCOUNT,
    NS_CATALOG,
    NS_DEPOSIT,
    NS_NAV,
    NS_SUB,
    NS_NEW,
    NS_ORDERS,
    NS_SUPPORT,
    NS_WALLET,
    pattern,
)
from middlewares.context import UserContextMiddleware
from middlewares.rate_limit import AbuseGuard, RateLimiter

#: مجموعة الطبقة الوسيطة (قبل كل المعالجات)
MIDDLEWARE_GROUP = -10

#: المجموعة الرئيسية لكل معالجات الواجهة
MAIN_GROUP = 0


def _order_conversation() -> ConversationHandler:
    """محادثة إنشاء طلب: رابط ← كمية ← تأكيد."""
    cancel_handlers = [
        CallbackQueryHandler(order_flow.cancel_order_flow, pattern=pattern("flow", "cancel")),
        CommandHandler("cancel", order_flow.cancel_order_flow),
        CommandHandler("start", fallbacks.exit_conversation(order_flow.FLOW_KEY)),
    ]
    return conversation(
        entry_points=[CallbackQueryHandler(order_flow.start_order, pattern=pattern(NS_NEW, "start"))],
        states={
            order_flow.ASK_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, order_flow.receive_link)
            ],
            order_flow.ASK_QUANTITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, order_flow.receive_quantity)
            ],
            order_flow.CONFIRM: [
                CallbackQueryHandler(order_flow.confirm_order, pattern=pattern("flow", "confirm"))
            ],
        },
        fallbacks=cancel_handlers,
        name="order_flow",
        per_chat=True,
        per_user=True,
    )


def _deposit_conversation() -> ConversationHandler:
    """محادثة شحن الرصيد: طريقة ← مبلغ ← مرجع ← إيصال ← تأكيد."""
    cancel_handlers = [
        CallbackQueryHandler(deposit.cancel_deposit_flow, pattern=pattern("flow", "cancel")),
        CommandHandler("cancel", deposit.cancel_deposit_flow),
        CommandHandler("start", fallbacks.exit_conversation(deposit.FLOW_KEY)),
    ]
    return conversation(
        entry_points=[CallbackQueryHandler(deposit.start_deposit, pattern=pattern(NS_DEPOSIT, "start"))],
        states={
            deposit.CHOOSE_METHOD: [
                CallbackQueryHandler(deposit.choose_method, pattern=pattern(NS_DEPOSIT, "method"))
            ],
            deposit.ASK_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, deposit.receive_amount)
            ],
            deposit.ASK_REFERENCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, deposit.receive_reference)
            ],
            deposit.ASK_PROOF: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, deposit.receive_proof),
                CallbackQueryHandler(deposit.skip_proof, pattern=pattern("flow", "skip")),
                MessageHandler(filters.TEXT & ~filters.COMMAND, deposit.receive_proof),
            ],
            deposit.CONFIRM: [
                CallbackQueryHandler(deposit.confirm_deposit, pattern=pattern("flow", "confirm"))
            ],
        },
        fallbacks=cancel_handlers,
        name="deposit_flow",
        per_chat=True,
        per_user=True,
    )


def _new_ticket_conversation() -> ConversationHandler:
    """محادثة فتح تذكرة: تصنيف ← عنوان ← شرح (أو مباشرة من بطاقة الطلب)."""
    cancel_handlers = [
        CallbackQueryHandler(support.cancel_support_flow, pattern=pattern("flow", "cancel")),
        CommandHandler("cancel", support.cancel_support_flow),
        CommandHandler("start", fallbacks.exit_conversation(support.NEW_FLOW_KEY)),
    ]
    return conversation(
        entry_points=[
            CallbackQueryHandler(support.start_new_ticket, pattern=pattern(NS_SUPPORT, "new")),
            CallbackQueryHandler(
                support.start_ticket_for_order, pattern=pattern(NS_SUPPORT, "neworder")
            ),
        ],
        states={
            support.ASK_CATEGORY: [
                CallbackQueryHandler(support.choose_ticket_category, pattern=pattern(NS_SUPPORT, "cat"))
            ],
            support.ASK_SUBJECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, support.receive_subject)
            ],
            support.ASK_MESSAGE: [
                MessageHandler(
                    (filters.TEXT | filters.PHOTO) & ~filters.COMMAND, support.receive_ticket_message
                )
            ],
        },
        fallbacks=cancel_handlers,
        name="new_ticket_flow",
        per_chat=True,
        per_user=True,
    )


def _ticket_reply_conversation() -> ConversationHandler:
    """محادثة إضافة رد على تذكرة قائمة."""
    cancel_handlers = [
        CallbackQueryHandler(support.cancel_support_flow, pattern=pattern("flow", "cancel")),
        CommandHandler("cancel", support.cancel_support_flow),
        CommandHandler("start", fallbacks.exit_conversation(support.REPLY_FLOW_KEY)),
    ]
    return conversation(
        entry_points=[
            CallbackQueryHandler(support.start_reply, pattern=pattern(NS_SUPPORT, "reply"))
        ],
        states={
            support.ASK_REPLY: [
                MessageHandler(
                    (filters.TEXT | filters.PHOTO) & ~filters.COMMAND, support.receive_reply
                )
            ],
        },
        fallbacks=cancel_handlers,
        name="ticket_reply_flow",
        per_chat=True,
        per_user=True,
    )


def screen_handlers() -> list[CallbackQueryHandler]:
    """
    معالجات أزرار الشاشات (خارج المحادثات).

    القائمة مرتبة حسب الشاشة، وكل سطر هنا يقابل زراً فعلياً في `keyboards/`.
    """
    return [
        # التنقل العام
        CallbackQueryHandler(navigation.home_callback, pattern=pattern(NS_NAV, "home")),
        CallbackQueryHandler(navigation.page_indicator_callback, pattern=pattern(NS_NAV, "page")),
        CallbackQueryHandler(navigation.subscription_check_callback, pattern=pattern(NS_SUB, "check")),
        # الخدمات
        CallbackQueryHandler(catalog.categories_screen, pattern=pattern(NS_CATALOG, "list")),
        CallbackQueryHandler(catalog.services_screen, pattern=pattern(NS_CATALOG, "open")),
        CallbackQueryHandler(catalog.service_card_screen, pattern=pattern(NS_CATALOG, "svc")),
        *favorites.handlers(),
        # الطلبات
        CallbackQueryHandler(orders.orders_list_screen, pattern=pattern(NS_ORDERS, "list")),
        CallbackQueryHandler(orders.order_card_screen, pattern=pattern(NS_ORDERS, "view")),
        CallbackQueryHandler(orders.order_cancel_confirm, pattern=pattern(NS_ORDERS, "cancel")),
        CallbackQueryHandler(orders.order_cancel_execute, pattern=pattern(NS_ORDERS, "cancelyes")),
        # المحفظة والشحن
        CallbackQueryHandler(wallet.wallet_screen, pattern=pattern(NS_WALLET, "home")),
        CallbackQueryHandler(wallet.history_screen, pattern=pattern(NS_WALLET, "history")),
        CallbackQueryHandler(deposit.deposits_list_screen, pattern=pattern(NS_DEPOSIT, "list")),
        CallbackQueryHandler(deposit.cancel_payment, pattern=pattern(NS_DEPOSIT, "cancel")),
        # الدعم
        CallbackQueryHandler(support.support_home, pattern=pattern(NS_SUPPORT, "home")),
        CallbackQueryHandler(support.tickets_list_screen, pattern=pattern(NS_SUPPORT, "list")),
        CallbackQueryHandler(support.ticket_card_screen, pattern=pattern(NS_SUPPORT, "view")),
        CallbackQueryHandler(support.close_ticket, pattern=pattern(NS_SUPPORT, "close")),
        # الحساب والمعلومات
        CallbackQueryHandler(account.account_screen, pattern=pattern(NS_ACCOUNT, "home")),
        CallbackQueryHandler(account.notifications_screen, pattern=pattern(NS_ACCOUNT, "notif")),
        CallbackQueryHandler(account.mark_all_read, pattern=pattern(NS_ACCOUNT, "readall")),
        CallbackQueryHandler(account.info_screen, pattern=pattern(NS_ACCOUNT, "info")),
        # لوحة التحكم (كل معالج يفحص صلاحيته بنفسه عبر admin_required)
        *admin_screen_handlers(),
    ]


def conversation_handlers() -> list[ConversationHandler]:
    """
    كل المحادثات بالترتيب الذي تُسجَّل به: محادثات العميل ثم محادثات لوحة الأدمن.

    محادثات الأدمن تأتي بعد محادثات العميل ولكن **قبل** أزرار الشاشات، لأن
    نقاط دخولها أزرار يجب أن تلتقطها المحادثة لا معالج الشاشة.
    """
    return [
        _order_conversation(),
        _deposit_conversation(),
        _new_ticket_conversation(),
        _ticket_reply_conversation(),
        *admin_conversations(),
    ]


def build_handlers(
    limiter: RateLimiter | None = None, guard: AbuseGuard | None = None
) -> list[tuple[int, BaseHandler]]:
    """
    بناء قائمة (المجموعة، المعالج) بالترتيب الصحيح.

    الترتيب داخل المجموعة 0:
        المحادثات ← الأوامر العامة ← أزرار الشاشات ← المسارات الاحتياطية.
    السبب: المحادثة النشطة يجب أن تلتقط /start و/cancel قبل المعالج العام،
    والمسار الاحتياطي يجب أن يكون الأخير حتى لا يبتلع أزراراً صحيحة.
    """
    handlers: list[tuple[int, BaseHandler]] = [
        (MIDDLEWARE_GROUP, TypeHandler(Update, UserContextMiddleware(limiter, guard)))
    ]

    for conversation_handler in conversation_handlers():
        handlers.append((MAIN_GROUP, conversation_handler))

    handlers.extend(
        [
            (MAIN_GROUP, CommandHandler("start", navigation.start_command)),
            (MAIN_GROUP, CommandHandler("help", navigation.help_command)),
            (MAIN_GROUP, CommandHandler("id", navigation.id_command)),
            (MAIN_GROUP, CommandHandler("cancel", fallbacks.cancel_command)),
        ]
    )

    for command in admin_command_handlers():
        handlers.append((MAIN_GROUP, command))

    for handler in screen_handlers():
        handlers.append((MAIN_GROUP, handler))

    handlers.extend(
        [
            (MAIN_GROUP, CallbackQueryHandler(fallbacks.unknown_callback)),
            (MAIN_GROUP, MessageHandler(filters.COMMAND, fallbacks.unknown_command)),
            (MAIN_GROUP, MessageHandler(filters.TEXT | filters.ATTACHMENT, fallbacks.free_text)),
        ]
    )
    return handlers


def register_handlers(
    application: Application,
    limiter: RateLimiter | None = None,
    guard: AbuseGuard | None = None,
) -> int:
    """
    تسجيل كل المعالجات على التطبيق وإرجاع عددها.

    يُنشئ عدّاد الحد وحارس الإساءة هنا (إن لم يُمرَّرا) ويحفظهما في `bot_data`
    ليراهما شاشة «🛡️ الأمان» (قائمة الموقوفين مؤقتاً وزر رفع الإيقاف).

    المخرجات: عدد المعالجات المسجَّلة (يُطبع في سجل الإقلاع للتأكيد).
    """
    limiter = limiter or RateLimiter()
    guard = guard or AbuseGuard()
    application.bot_data["rate_limiter"] = limiter
    application.bot_data["abuse_guard"] = guard

    registered = build_handlers(limiter, guard)
    for group, handler in registered:
        application.add_handler(handler, group=group)
    application.add_error_handler(errors.error_handler)
    return len(registered)
```

---

## `keyboards/user_kb.py`

```python
"""
لوحات أزرار واجهة العميل — كل شاشة لها دالة واحدة تبني أزرارها.

مبدأ ملزم: **لا زر بلا وظيفة**. كل `callback_data` هنا يقابله معالج مسجَّل في
`handlers/registry.py`، ويتحقق من ذلك اختبار `tests/integration/test_no_dead_buttons.py`.
"""

from __future__ import annotations

from decimal import Decimal

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from database.models import (
    Order,
    Payment,
    PaymentMethod,
    Service,
    ServiceCategory,
    SupportTicket,
)
from core.enums import OrderStatus, PaymentStatus
from keyboards.callback_data import (
    NS_ACCOUNT,
    NS_ADMIN,
    NS_CATALOG,
    NS_DEPOSIT,
    NS_FAV,
    NS_FLOW,
    NS_NEW,
    NS_SUB,
    NS_ORDERS,
    NS_SUPPORT,
    NS_WALLET,
    pack,
)
from keyboards.common_kb import back_home_row, home_button, pagination_row
from core.money import format_usd
from texts import admin_ar, ar
from utils.formatters import money_text, order_list_line, ticket_list_line

#: تصفية قوائم الطلبات المعروضة للمستخدم (الرمز ⇐ الحالات المشمولة)
ORDER_FILTERS: dict[str, tuple[str, tuple[str, ...]]] = {
    "all": (ar.FILTER_ALL, ()),
    "active": (
        ar.FILTER_ACTIVE,
        (
            OrderStatus.PENDING,
            OrderStatus.SUBMITTING,
            OrderStatus.SUBMIT_UNCERTAIN,
            OrderStatus.SUBMITTED,
            OrderStatus.IN_PROGRESS,
        ),
    ),
    "done": (ar.FILTER_COMPLETED, (OrderStatus.COMPLETED, OrderStatus.PARTIAL)),
    "rfnd": (
        ar.FILTER_REFUNDED,
        (OrderStatus.REFUNDED, OrderStatus.CANCELED, OrderStatus.FAILED),
    ),
}


# ============================ القائمة الرئيسية ========================== #


def main_menu_kb(*, is_admin: bool = False) -> InlineKeyboardMarkup:
    """
    القائمة الرئيسية — سبع شاشات (الخدمات، المفضلة، المحفظة، الطلبات، الدعم، الحساب، المعلومات).

    المدخلات:
        is_admin : يضيف صفاً سابعاً «🛠 لوحة التحكم» لمن يملك `admin.access` فقط.
                   القيمة الافتراضية False حتى لا يظهر الزر بالخطأ لمستخدم عادي
                   في أي مسار لم يتحقق من الصلاحية.
    """
    rows = [
        [
            InlineKeyboardButton(ar.BTN_SERVICES, callback_data=pack(NS_CATALOG, "list", 1)),
            InlineKeyboardButton(ar.BTN_FAVORITES, callback_data=pack(NS_FAV, "list", 1)),
        ],
        [
            InlineKeyboardButton(ar.BTN_WALLET, callback_data=pack(NS_WALLET, "home")),
            InlineKeyboardButton(ar.BTN_ORDERS, callback_data=pack(NS_ORDERS, "list", "all", 1)),
        ],
        [
            InlineKeyboardButton(ar.BTN_SUPPORT, callback_data=pack(NS_SUPPORT, "home")),
            InlineKeyboardButton(ar.BTN_ACCOUNT, callback_data=pack(NS_ACCOUNT, "home")),
        ],
        [InlineKeyboardButton(ar.BTN_INFO, callback_data=pack(NS_ACCOUNT, "info"))],
    ]
    if is_admin:
        rows.append(
            [InlineKeyboardButton(admin_ar.BTN_ADMIN_PANEL, callback_data=pack(NS_ADMIN, "home"))]
        )
    return InlineKeyboardMarkup(rows)


# ========================== بوابة الاشتراك ============================ #


def subscription_kb(missing: list[tuple[str, str | None]]) -> InlineKeyboardMarkup:
    """
    أزرار بوابة الاشتراك الإجباري.

    المدخلات:
        missing : قائمة (عنوان القناة، رابط الانضمام) للقنوات الناقصة؛ القناة بلا رابط (خاصة بالمعرّف الرقمي)
                  تظهر في النص فقط ولا يُرسم لها زر رابط.
    """
    rows = [
        [InlineKeyboardButton(ar.SUB_BTN_JOIN.format(title=title), url=url)]
        for title, url in missing
        if url
    ]
    rows.append([InlineKeyboardButton(ar.SUB_BTN_CHECK, callback_data=pack(NS_SUB, "check"))])
    return InlineKeyboardMarkup(rows)


# ============================== الخدمات ================================ #


def categories_kb(categories: list[ServiceCategory]) -> InlineKeyboardMarkup:
    """أزرار التصنيفات المتاحة (زرّان في كل صف)."""
    rows: list[list[InlineKeyboardButton]] = []
    for index in range(0, len(categories), 2):
        chunk = categories[index : index + 2]
        rows.append(
            [
                InlineKeyboardButton(category.title, callback_data=pack(NS_CATALOG, "open", category.id, 1))
                for category in chunk
            ]
        )
    rows.append([home_button()])
    return InlineKeyboardMarkup(rows)


def service_button_label(service: Service, *, symbol: str, usd_rate: Decimal | None) -> str:
    """
    نص زر الخدمة: `#رقم · الاسم · السعر/1000` — الدولار أساسي عند توفر سعر الصرف.

    الاسم يُقتطع ليبقى النص ضمن حد تيليجرام (64 حرفاً) فلا يُرفض الزر لطول الاسم.
    """
    if usd_rate is not None:
        price = format_usd(service.price_per_1000_units, usd_rate)
    else:
        price = money_text(service.price_per_1000_units, symbol)
    suffix = f" · {price}/1000"
    prefix = f"#{service.id} · "
    room = max(8, 62 - len(prefix) - len(suffix))
    name = service.name if len(service.name) <= room else service.name[: room - 1].rstrip() + "…"
    return f"{prefix}{name}{suffix}"


def services_kb(
    services: list[Service],
    *,
    category_id: int,
    page: int,
    total_pages: int,
    symbol: str,
    usd_rate: Decimal | None = None,
) -> InlineKeyboardMarkup:
    """أزرار خدمات تصنيف مع ترقيم صفحات وزر رجوع للتصنيفات."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                service_button_label(service, symbol=symbol, usd_rate=usd_rate),
                callback_data=pack(NS_CATALOG, "svc", service.id, category_id, page),
            )
        ]
        for service in services
    ]
    nav = pagination_row(
        NS_CATALOG, "open", page=page, total_pages=total_pages, prefix_args=(category_id,)
    )
    if nav:
        rows.append(nav)
    rows.append(back_home_row(NS_CATALOG, "list", 1))
    return InlineKeyboardMarkup(rows)


def service_card_kb(
    service: Service, *, category_id: int, page: int, is_favorite: bool = False
) -> InlineKeyboardMarkup:
    """
    بطاقة الخدمة: 🛒 طلب + ⭐ مفضلة (تبديل) + 🔙 رجوع.

    `category_id == 0` ⇒ فُتحت البطاقة من «المفضلة» فيرجع الزر لقائمة المفضلة لا لتصنيف.
    """
    favorite_button = (
        InlineKeyboardButton(ar.BTN_FAV_REMOVE, callback_data=pack(NS_FAV, "del", service.id, category_id, page))
        if is_favorite
        else InlineKeyboardButton(ar.BTN_FAV_ADD, callback_data=pack(NS_FAV, "add", service.id, category_id, page))
    )
    back = (
        back_home_row(NS_FAV, "list", page) if category_id == 0
        else back_home_row(NS_CATALOG, "open", category_id, page)
    )
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(ar.BTN_ORDER_NOW, callback_data=pack(NS_NEW, "start", service.id)), favorite_button],
            back,
        ]
    )


def favorites_kb(
    services: list[Service], *, page: int, total_pages: int, symbol: str, usd_rate: Decimal | None
) -> InlineKeyboardMarkup:
    """قائمة المفضلة: زر لكل خدمة (يفتح بطاقتها بـ category=0) + ترقيم + رجوع."""
    rows = [
        [
            InlineKeyboardButton(
                service_button_label(service, symbol=symbol, usd_rate=usd_rate),
                callback_data=pack(NS_CATALOG, "svc", service.id, 0, page),
            )
        ]
        for service in services
    ]
    nav = pagination_row(NS_FAV, "list", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(back_home_row())
    return InlineKeyboardMarkup(rows)


def insufficient_balance_kb(category_id: int, page: int) -> InlineKeyboardMarkup:
    """لوحة تُعرض عند عدم كفاية الرصيد: شحن مباشر أو رجوع."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(ar.BTN_DEPOSIT_NOW, callback_data=pack(NS_DEPOSIT, "start"))],
            back_home_row(NS_CATALOG, "open", category_id, page),
        ]
    )


# ============================== طلباتي ================================= #


def orders_filters_row(current: str) -> list[InlineKeyboardButton]:
    """صف أزرار تصفية الطلبات مع تمييز التصفية الحالية."""
    row: list[InlineKeyboardButton] = []
    for code, (label, _statuses) in ORDER_FILTERS.items():
        mark = "• " if code == current else ""
        row.append(InlineKeyboardButton(f"{mark}{label}", callback_data=pack(NS_ORDERS, "list", code, 1)))
    return row


def orders_kb(
    orders: list[Order], *, filter_code: str, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """قائمة طلبات المستخدم مع التصفية والترقيم."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                order_list_line(order, symbol=symbol),
                callback_data=pack(NS_ORDERS, "view", order.id, filter_code, page),
            )
        ]
        for order in orders
    ]
    rows.append(orders_filters_row(filter_code))
    nav = pagination_row(
        NS_ORDERS, "list", page=page, total_pages=total_pages, prefix_args=(filter_code,)
    )
    if nav:
        rows.append(nav)
    rows.append([home_button()])
    return InlineKeyboardMarkup(rows)


def order_card_kb(
    order: Order, *, filter_code: str, page: int, can_cancel: bool
) -> InlineKeyboardMarkup:
    """
    بطاقة الطلب.

    زر الإلغاء يظهر فقط عندما يسمح به منطق الخدمة فعلاً — لا زر معطّل ولا زر كاذب.
    """
    rows: list[list[InlineKeyboardButton]] = []
    if can_cancel:
        rows.append(
            [InlineKeyboardButton(ar.BTN_ORDER_CANCEL, callback_data=pack(NS_ORDERS, "cancel", order.id))]
        )
    rows.append(
        [InlineKeyboardButton(ar.BTN_ORDER_TICKET, callback_data=pack(NS_SUPPORT, "neworder", order.id))]
    )
    rows.append(back_home_row(NS_ORDERS, "list", filter_code, page))
    return InlineKeyboardMarkup(rows)


def order_cancel_confirm_kb(order_id: int) -> InlineKeyboardMarkup:
    """تأكيد إلغاء الطلب (خطوة إضافية قبل أي حركة مالية)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(ar.BTN_CONFIRM, callback_data=pack(NS_ORDERS, "cancelyes", order_id)),
                InlineKeyboardButton(ar.BTN_BACK, callback_data=pack(NS_ORDERS, "view", order_id, "all", 1)),
            ]
        ]
    )


# ============================== المحفظة ================================ #


def wallet_kb() -> InlineKeyboardMarkup:
    """شاشة المحفظة: شحن، سجل العمليات، طلبات الشحن."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(ar.BTN_DEPOSIT_NOW, callback_data=pack(NS_DEPOSIT, "start"))],
            [
                InlineKeyboardButton(ar.BTN_WALLET_HISTORY, callback_data=pack(NS_WALLET, "history", 1)),
                InlineKeyboardButton(ar.BTN_MY_DEPOSITS, callback_data=pack(NS_DEPOSIT, "list", 1)),
            ],
            [home_button()],
        ]
    )


def history_kb(*, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """سجل العمليات المالية مع الترقيم."""
    rows: list[list[InlineKeyboardButton]] = []
    nav = pagination_row(NS_WALLET, "history", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(back_home_row(NS_WALLET, "home"))
    return InlineKeyboardMarkup(rows)


# =============================== الشحن ================================= #


def deposit_methods_kb(methods: list[PaymentMethod]) -> InlineKeyboardMarkup:
    """أزرار طرق الشحن المفعّلة."""
    rows = [
        [InlineKeyboardButton(method.name_ar, callback_data=pack(NS_DEPOSIT, "method", method.id))]
        for method in methods
    ]
    rows.append(back_home_row(NS_WALLET, "home"))
    return InlineKeyboardMarkup(rows)


def deposits_kb(payments: list[Payment], *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """قائمة طلبات الشحن السابقة مع إمكانية إلغاء المعلّق منها."""
    rows: list[list[InlineKeyboardButton]] = []
    for payment in payments:
        if payment.status == PaymentStatus.PENDING:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"🛑 إلغاء طلب #{payment.id}",
                        callback_data=pack(NS_DEPOSIT, "cancel", payment.id),
                    )
                ]
            )
    nav = pagination_row(NS_DEPOSIT, "list", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(back_home_row(NS_WALLET, "home"))
    return InlineKeyboardMarkup(rows)


# =============================== الدعم ================================= #


def support_kb() -> InlineKeyboardMarkup:
    """شاشة الدعم الرئيسية."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(ar.BTN_TICKET_NEW, callback_data=pack(NS_SUPPORT, "new"))],
            [InlineKeyboardButton(ar.BTN_TICKETS_LIST, callback_data=pack(NS_SUPPORT, "list", 1))],
            [home_button()],
        ]
    )


def ticket_categories_kb() -> InlineKeyboardMarkup:
    """أزرار تصنيفات التذكرة الجديدة."""
    rows = [
        [InlineKeyboardButton(label, callback_data=pack(NS_SUPPORT, "cat", code))]
        for code, label in ar.TICKET_CATEGORIES.items()
    ]
    rows.append([InlineKeyboardButton(ar.BTN_CANCEL, callback_data=pack(NS_FLOW, "cancel"))])
    return InlineKeyboardMarkup(rows)


def tickets_kb(tickets: list[SupportTicket], *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """قائمة تذاكر المستخدم."""
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(ticket_list_line(ticket), callback_data=pack(NS_SUPPORT, "view", ticket.id))]
        for ticket in tickets
    ]
    nav = pagination_row(NS_SUPPORT, "list", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(back_home_row(NS_SUPPORT, "home"))
    return InlineKeyboardMarkup(rows)


def ticket_card_kb(ticket: SupportTicket) -> InlineKeyboardMarkup:
    """بطاقة التذكرة: الرد والإغلاق (تظهر فقط ما دامت مفتوحة)."""
    rows: list[list[InlineKeyboardButton]] = []
    if ticket.is_open:
        rows.append(
            [
                InlineKeyboardButton(ar.BTN_TICKET_REPLY, callback_data=pack(NS_SUPPORT, "reply", ticket.id)),
                InlineKeyboardButton(ar.BTN_TICKET_CLOSE, callback_data=pack(NS_SUPPORT, "close", ticket.id)),
            ]
        )
    else:
        rows.append(
            [InlineKeyboardButton(ar.BTN_TICKET_REPLY, callback_data=pack(NS_SUPPORT, "reply", ticket.id))]
        )
    rows.append(back_home_row(NS_SUPPORT, "list", 1))
    return InlineKeyboardMarkup(rows)


# ============================== الحساب ================================= #


def account_kb(unread: int) -> InlineKeyboardMarkup:
    """شاشة الحساب مع عدّاد الإشعارات غير المقروءة."""
    badge = f" ({unread})" if unread else ""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(ar.BTN_NOTIFICATIONS + badge, callback_data=pack(NS_ACCOUNT, "notif", 1))],
            [
                InlineKeyboardButton(ar.BTN_WALLET, callback_data=pack(NS_WALLET, "home")),
                InlineKeyboardButton(ar.BTN_ORDERS, callback_data=pack(NS_ORDERS, "list", "all", 1)),
            ],
            [home_button()],
        ]
    )


def notifications_kb(*, page: int, total_pages: int, unread: int) -> InlineKeyboardMarkup:
    """صندوق الإشعارات مع زر تعليم الكل كمقروء."""
    rows: list[list[InlineKeyboardButton]] = []
    if unread:
        rows.append(
            [InlineKeyboardButton(ar.BTN_MARK_ALL_READ, callback_data=pack(NS_ACCOUNT, "readall"))]
        )
    nav = pagination_row(NS_ACCOUNT, "notif", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(back_home_row(NS_ACCOUNT, "home"))
    return InlineKeyboardMarkup(rows)


def info_kb() -> InlineKeyboardMarkup:
    """شاشة المعلومات."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(ar.BTN_SUPPORT, callback_data=pack(NS_SUPPORT, "home"))],
            [home_button()],
        ]
    )


def notifications_only_back_kb() -> InlineKeyboardMarkup:
    """لوحة رجوع بسيطة تُستخدم بعد الإجراءات السريعة."""
    return InlineKeyboardMarkup([back_home_row(NS_ACCOUNT, "home")])
```

---

## `keyboards/callback_data.py`

```python
"""
ترميز وفك بيانات الأزرار (callback_data) بشكل مُهيكل وآمن.

لماذا ملف مستقل؟
    تيليجرام يسمح بـ64 بايت فقط لكل `callback_data`، وأي زر قديم في محادثة
    مستخدم قد يُضغط بعد تحديث البوت. لذلك نعتمد صيغة واحدة في كل المشروع:

        namespace:action:arg1:arg2...:vN

    • `namespace` يحدد الشاشة (cat / ord / wal / dep / sup / acc / nav / flow).
    • `action` يحدد الإجراء داخل الشاشة.
    • `vN` لاحقة الإصدار؛ إذا تغيّرت بنية الأزرار مستقبلاً نرفع الرقم،
      فتُرفض الأزرار القديمة برسالة واضحة بدل تنفيذ إجراء خاطئ.

قواعد ملزِمة:
    • ممنوع زر بلا معنى: كل `callback_data` يُبنى من هنا وله معالج مسجَّل
      (يتحقق من ذلك اختبار `test_no_dead_buttons`).
    • ممنوع تمرير نص حر من المستخدم داخل `callback_data` (طوله غير مضمون).
"""

from __future__ import annotations

from dataclasses import dataclass

#: إصدار بنية الأزرار الحالي — يُلحق بكل زر
CALLBACK_VERSION: int = 1

#: الحد الأقصى الذي تسمح به تيليجرام لحجم callback_data (بايت)
MAX_CALLBACK_BYTES: int = 64

#: الفاصل بين أجزاء الزر
SEPARATOR: str = ":"


class CallbackError(ValueError):
    """خطأ في بناء أو قراءة بيانات زر (بنية غير صحيحة أو طول زائد)."""


@dataclass(frozen=True, slots=True)
class Callback:
    """بيانات زر بعد فكّها: المساحة، الإجراء، الوسائط، الإصدار."""

    namespace: str
    action: str
    args: tuple[str, ...]
    version: int

    def arg(self, index: int, default: str = "") -> str:
        """قراءة وسيط نصي بموضعه مع قيمة افتراضية إن لم يوجد."""
        if index < len(self.args):
            return self.args[index]
        return default

    def int_arg(self, index: int, default: int = 0) -> int:
        """قراءة وسيط رقمي بموضعه (يُعيد الافتراضي إن كان غير رقمي)."""
        raw = self.arg(index)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    @property
    def is_current_version(self) -> bool:
        """هل هذا الزر من الإصدار الحالي لبنية الأزرار؟"""
        return self.version == CALLBACK_VERSION


def pack(namespace: str, action: str, *args: object) -> str:
    """
    بناء `callback_data` مُهيكلة والتحقق من صلاحيتها.

    المدخلات:
        namespace : مساحة الشاشة (حروف صغيرة بلا فواصل).
        action    : اسم الإجراء.
        args      : وسائط إضافية (أرقام أو كلمات قصيرة بلا الفاصل `:`).

    المخرجات: نص جاهز لوضعه في زر.

    الاستثناءات:
        CallbackError : وجود الفاصل داخل جزء، أو تجاوز حد 64 بايت.
    """
    parts = [namespace, action, *[str(arg) for arg in args]]
    for part in parts:
        if SEPARATOR in part:
            raise CallbackError(f"جزء زر يحتوي الفاصل الممنوع '{SEPARATOR}': {part!r}")
        if part == "":
            raise CallbackError("جزء زر فارغ غير مسموح")
    data = SEPARATOR.join([*parts, f"v{CALLBACK_VERSION}"])
    if len(data.encode("utf-8")) > MAX_CALLBACK_BYTES:
        raise CallbackError(f"طول callback_data تجاوز {MAX_CALLBACK_BYTES} بايت: {data!r}")
    return data


def unpack(data: str | None) -> Callback:
    """
    فكّ `callback_data` إلى أجزائها.

    المخرجات: كائن `Callback`؛ والإصدار يكون 0 إذا كان الزر قديماً بلا لاحقة إصدار.

    الاستثناءات:
        CallbackError : البيانات فارغة أو لا تحوي مساحة وإجراءً.
    """
    if not data:
        raise CallbackError("callback_data فارغة")
    parts = data.split(SEPARATOR)
    if len(parts) < 2:
        raise CallbackError(f"callback_data غير مُهيكلة: {data!r}")

    version = 0
    if parts[-1].startswith("v") and parts[-1][1:].isdigit():
        version = int(parts[-1][1:])
        parts = parts[:-1]

    namespace, action, *args = parts
    return Callback(namespace=namespace, action=action, args=tuple(args), version=version)


def pattern(namespace: str, action: str | None = None) -> str:
    """
    بناء تعبير نمطي لتسجيل المعالج على مساحة (أو مساحة+إجراء) بعينها.

    مثال: `pattern("cat")` ⇒ `^cat:` و`pattern("cat", "open")` ⇒ `^cat:open(:|$)`.
    """
    if action is None:
        return rf"^{namespace}{SEPARATOR}"
    return rf"^{namespace}{SEPARATOR}{action}({SEPARATOR}|$)"


# ----------------------- مساحات الأزرار المعتمدة ------------------------- #

NS_NAV = "nav"      # التنقل بين الشاشات الرئيسية
NS_CATALOG = "cat"  # التصنيفات والخدمات
NS_NEW = "new"      # بدء طلب جديد
NS_ORDERS = "ord"   # طلباتي
NS_WALLET = "wal"   # المحفظة
NS_DEPOSIT = "dep"  # شحن الرصيد
NS_SUPPORT = "sup"  # الدعم الفني
NS_ACCOUNT = "acc"  # الحساب والإشعارات
NS_FLOW = "flow"    # أزرار داخل المحادثات (تأكيد/إلغاء/تخطي/رجوع)
NS_SUB = "sub"      # بوابة الاشتراك الإجباري (زر «تحقق»)
NS_FAV = "fav"      # المفضلة (إضافة/إزالة/عرض)

# ----------------------- مساحات لوحة الأدمن ----------------------------- #
# مختصرة عمداً: حدّ تيليجرام 64 بايت، وبعض الأزرار تحمل معرفات طويلة.

NS_ADMIN = "adm"      # لوحة التحكم والصحة العامة
NS_ADM_USERS = "au"   # إدارة المستخدمين
NS_ADM_PAY = "ap"     # مراجعة طلبات الشحن
NS_ADM_ORD = "ao"     # إدارة الطلبات
NS_ADM_TKT = "at"     # تذاكر الدعم (جانب الأدمن)
NS_ADM_CAT = "ac"     # إدارة الكتالوج (تصنيفات/خدمات)
NS_ADM_SET = "as"     # الإعدادات
NS_ADM_LOG = "al"     # السجلات (تدقيق/أخطاء)
NS_ADM_PRV = "pv"     # المزودون وربط الـAPI (المرحلة 5)
NS_ADM_PMT = "pm"     # طرق الشحن وإدارتها (المرحلة 7)
NS_ADM_BRD = "bc"     # الرسائل الجماعية (المرحلة 8)
NS_ADM_TPL = "tp"     # قوالب الإشعارات (المرحلة 8)
NS_ADM_SEC = "sc"     # شاشة الأمان (المرحلة 9)
NS_ADM_BKP = "bk"     # النسخ الاحتياطي (المرحلة 10)
NS_ADM_STATS = "st"   # الإحصائيات والتصدير (المرحلة 10)
NS_ADM_CHN = "ch"     # القنوات: تشخيص وجهات النشر وقنوات الاشتراك (المرحلة 13)

#: كل المساحات المعروفة — تُستخدم في اختبار «لا أزرار بلا وظيفة»
ALL_NAMESPACES: tuple[str, ...] = (
    NS_NAV, NS_CATALOG, NS_NEW, NS_ORDERS, NS_WALLET, NS_DEPOSIT, NS_SUPPORT, NS_ACCOUNT, NS_FLOW,
    NS_ADMIN, NS_ADM_USERS, NS_ADM_PAY, NS_ADM_ORD, NS_ADM_TKT, NS_ADM_CAT, NS_ADM_SET, NS_ADM_LOG,
    NS_ADM_PRV, NS_ADM_PMT, NS_ADM_BRD, NS_ADM_TPL, NS_ADM_SEC, NS_ADM_BKP, NS_ADM_STATS,
    NS_SUB, NS_FAV, NS_ADM_CHN,
)
```

---

## `texts/channel_posts.py`

```python
"""
نصوص منشورات القنوات الإدارية (مستخدم جديد، توثيق طلب).

قاعدة صارمة: لا يظهر هنا أي سر — لا مفتاح مزود، لا رابط كامل، ولا Telegram ID كامل
(التقنيع في `utils.privacy`).
"""

from __future__ import annotations

from decimal import Decimal

from core.money import format_usd
from utils.formatters import datetime_text, local_amount
from utils.privacy import mask_link, mask_telegram_id, mask_username


def new_user_post(*, user, total_users: int) -> tuple[str, str]:
    """منشور «مستخدم جديد 🔥» لقناة الإدارة؛ المخرجات: (العنوان، النص)."""
    name = " ".join(part for part in (user.first_name, user.last_name) if part).strip() or "—"
    message = (
        f"رقم الحساب: {user.id}\n"
        f"الاسم: {name}\n"
        f"Username: {mask_username(user.username)}\n"
        f"Telegram ID: {mask_telegram_id(user.telegram_id)}\n"
        f"التسجيل: {datetime_text(user.created_at)}\n"
        f"إجمالي المستخدمين: {total_users:,}"
    )
    return "👤 مستخدم جديد 🔥", message


def order_post(
    *,
    category_name: str,
    service_name: str,
    order_code: str,
    quantity: int,
    cost_units: int,
    symbol: str,
    usd_rate: Decimal,
    user,
    link: str,
) -> tuple[str, str]:
    """منشور «طلب جديد 🔥» لقناة توثيق الطلبات؛ المخرجات: (العنوان، النص)."""
    message = (
        f"القسم: {category_name or '—'}\n"
        f"الخدمة: {service_name}\n"
        f"رقم الطلب: {order_code}\n"
        f"الكمية: {quantity:,}\n"
        f"السعر: {local_amount(cost_units, symbol)} ({format_usd(cost_units, usd_rate)})\n"
        f"العميل: {mask_telegram_id(user.telegram_id)}\n"
        f"الرابط: {mask_link(link)}"
    )
    return "🔥 طلب جديد", message
```

---

## `texts/ar.py`

```python
"""
نصوص الواجهة العربية — مصدر واحد لكل ما يراه المستخدم على الشاشة.

لماذا مركزية؟
    نفس العبارة تتكرر في عدة شاشات؛ وجودها في مكان واحد يمنع التناقض،
    ويجعل تعديل الصياغة (أو إضافة لغة ثانية لاحقاً) تعديلاً في ملف واحد.

تقسيم المسؤولية:
    • `texts/ar.py`        : نصوص الشاشات والأزرار والرسائل الفورية (هذا الملف).
    • `texts/templates.py` : نصوص الإشعارات المرسلة عبر صندوق الإشعارات.
"""

from __future__ import annotations

# ============================ أزرار عامة ============================== #

BTN_BACK = "🔙 رجوع"
BTN_HOME = "🏠 القائمة الرئيسية"
BTN_CANCEL = "❌ إلغاء"
BTN_CONFIRM = "✅ تأكيد"
BTN_SKIP = "⏭ تخطي"
BTN_PREV = "⬅️ السابق"
BTN_NEXT = "التالي ➡️"
BTN_REFRESH = "🔄 تحديث"

# ========================= القائمة الرئيسية =========================== #

BTN_SERVICES = "🛍 الخدمات"
BTN_WALLET = "💰 المحفظة"
BTN_ORDERS = "📦 طلباتي"
BTN_SUPPORT = "🎫 الدعم"
BTN_ACCOUNT = "👤 حسابي"
BTN_INFO = "ℹ️ معلومات"

MAIN_MENU_TITLE = "القائمة الرئيسية"

WELCOME_NEW = (
    "👋 أهلاً بك {name}!\n\n"
    "{welcome}\n\n"
    "استخدم الأزرار بالأسفل للتنقل. رصيدك الحالي: <b>{balance}</b>"
)
WELCOME_BACK = "👋 أهلاً بعودتك {name}\n\nرصيدك الحالي: <b>{balance}</b>"

START_NEW = (
    "{welcome}\n"
    "👤 <b>{name}</b>\n\n"
    "🚀 <b>ابدأ بخطوتين:</b> اشحن رصيدك من 💰 المحفظة، ثم اختر خدمتك من 🛍 الخدمات.\n\n"
)
START_BACK = "👋 أهلاً بعودتك <b>{name}</b>\n\n"

MAIN_MENU_BODY = (
    "🏠 <b>القائمة الرئيسية</b>\n\n"
    "💰 الرصيد: <b>{balance}</b>\n"
    "📦 طلبات نشطة: <b>{active_orders}</b>\n"
    "🎫 تذاكر مفتوحة: <b>{open_tickets}</b>\n\n"
    "اختر ما تريد:"
)

# ========================= الاشتراك الإجباري ========================== #

SUB_GATE_TITLE = (
    "📢 <b>الاشتراك مطلوب</b>\n\n"
    "للاستفادة من البوت اشترك في القنوات التالية ثم اضغط «✅ تحقق من الاشتراك»:\n\n"
)
SUB_LINE_OK = "✅ {title}"
SUB_LINE_MISSING = "❌ {title}"
SUB_LINE_UNKNOWN = "⚠️ {title} — تعذّر التحقق منها حالياً"
SUB_GATE_UNVERIFIABLE_NOTE = (
    "\n\n⚠️ تعذّر التحقق من بعض القنوات (مشكلة عند الإدارة أو في الاتصال). "
    "حاول بعد قليل، وإن استمر الأمر فأبلغ الدعم."
)
SUB_BTN_JOIN = "➕ {title}"
SUB_BTN_CHECK = "✅ تحقق من الاشتراك"
SUB_CHECK_FAILED = "لم يكتمل اشتراكك بعد: {names}"
SUB_CHECK_UNVERIFIED = "تعذّر التحقق الآن، حاول بعد قليل."
SUB_CHECK_OK = "✅ تم التحقق — أهلاً بك!"

# ============================== الخدمات =============================== #

CATEGORIES_TITLE = "🛍 <b>اختر التصنيف</b>\n\nاختر المنصة التي تريد خدمة لها:"
CATEGORIES_EMPTY = "📭 لا توجد خدمات متاحة حالياً.\nتابعنا لاحقاً — يجري تجهيز الخدمات."
SERVICES_TITLE = "{emoji} <b>{category}</b>\n\nالصفحة {page} من {pages} — اختر خدمة:"
SERVICES_EMPTY = "📭 لا توجد خدمات في هذا التصنيف حالياً."

SERVICE_CARD = (
    "📄 <b>{name}</b>\n"
    "🆔 رقم الخدمة: <b>#{service_id}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "💵 السعر لكل 1000: <b>{usd}</b>\n"
    "💴 ما يعادل: <b>{local}</b>\n"
    "💱 سعر الصرف: 1$ = {rate} {symbol}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🚀 السرعة: {speed}\n"
    "💎 الجودة: {quality}\n"
    "🛡 الضمان: {guarantee}\n"
    "🔢 الحد الأدنى: <b>{min_quantity}</b>\n"
    "🔢 الحد الأقصى: <b>{max_quantity}</b>\n"
    "{description}"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "💰 رصيدك: <b>{balance}</b>"
)
BTN_ORDER_NOW = "🛒 طلب"
BTN_FAV_ADD = "⭐ مفضلة"
BTN_FAV_REMOVE = "★ إزالة من المفضلة"
AVG_TIME_UNKNOWN = "غير محددة"
FIELD_UNSET = "غير محددة"

# ============================== المفضلة ============================== #

FAVORITES_TITLE = "⭐ <b>مفضلتي</b>\n\nالصفحة {page} من {pages} — اختر خدمة:"
FAVORITES_EMPTY = (
    "⭐ <b>مفضلتي</b>\n\nلا توجد خدمات في المفضلة بعد.\n"
    "افتح أي خدمة واضغط «⭐ مفضلة» لتصلها أسرع لاحقاً."
)
FAVORITE_ADDED = "⭐ أُضيفت إلى المفضلة"
FAVORITE_EXISTS = "هذه الخدمة في مفضلتك مسبقاً"
FAVORITE_REMOVED = "أُزيلت من المفضلة"
FAVORITE_NOT_FOUND = "هذه الخدمة ليست في مفضلتك"
FAVORITE_LIMIT = "وصلت للحد الأقصى للمفضلة ({limit} خدمة). أزل بعضها أولاً."
BTN_FAVORITES = "⭐ المفضلة"

# ============================ مسار الطلب ============================== #

ORDER_LINK_HINT_GENERIC = "أرسل الرابط كرسالة نصية (مثال: https://instagram.com/username)."
ORDER_LINK_HINT_RULE = "أرسل رابط <b>{label}</b> كرسالة نصية.\nمثال: <code>{example}</code>"
ORDER_ASK_LINK = (
    "🔗 <b>أرسل رابط الهدف</b>\n\n"
    "الخدمة: {service}\n\n"
    "{hint}\n"
    "يمكنك الإلغاء في أي لحظة."
)
ORDER_ASK_QUANTITY = (
    "🔢 <b>أرسل الكمية المطلوبة</b>\n\n"
    "الخدمة: {service}\n"
    "الرابط: {link}\n\n"
    "الكمية المسموحة من <b>{min_quantity}</b> إلى <b>{max_quantity}</b>."
)
ORDER_SUMMARY = (
    "🧾 <b>ملخص الطلب</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📄 الخدمة: {service}\n"
    "🔗 الرابط: {link}\n"
    "🔢 الكمية: <b>{quantity}</b>\n"
    "💵 التكلفة: <b>{cost}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "💰 رصيدك الحالي: {balance}\n"
    "💰 رصيدك بعد الطلب: <b>{balance_after}</b>\n\n"
    "اضغط تأكيد لإنشاء الطلب."
)
ORDER_SUMMARY_NO_BALANCE = (
    "🧾 <b>ملخص الطلب</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📄 الخدمة: {service}\n"
    "🔗 الرابط: {link}\n"
    "🔢 الكمية: <b>{quantity}</b>\n"
    "💵 التكلفة: <b>{cost}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "💰 رصيدك: {balance}\n"
    "❌ <b>الناقص: {missing}</b>\n\n"
    "اشحن رصيدك ثم أعد الطلب."
)
BTN_DEPOSIT_NOW = "➕ شحن الرصيد"
ORDER_CREATED = (
    "✅ <b>تم إنشاء طلبك</b>\n\n"
    "🔖 رقم الطلب: <b>{code}</b>\n"
    "📄 الخدمة: {service}\n"
    "🔢 الكمية: {quantity}\n"
    "💵 المخصوم: {cost}\n"
    "💰 رصيدك الآن: {balance}\n\n"
    "سيُرسل الطلب إلى المزود خلال لحظات، وستصلك إشعارات بتقدمه."
)
ORDER_CANCELLED_FLOW = "❌ تم إلغاء العملية. لم يُخصم أي مبلغ."

# ============================== طلباتي ================================ #

ORDERS_TITLE = "📦 <b>طلباتي</b> — {filter_name}\n\nالصفحة {page} من {pages}"
ORDERS_EMPTY = "📭 لا توجد طلبات ضمن هذا التصنيف."
FILTER_ALL = "الكل"
FILTER_ACTIVE = "نشطة"
FILTER_COMPLETED = "مكتملة"
FILTER_REFUNDED = "مسترجعة"

ORDER_CARD = (
    "📦 <b>الطلب {code}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📄 الخدمة: {service}\n"
    "🔗 الرابط: {link}\n"
    "🔢 الكمية: {quantity}\n"
    "{progress}"
    "💵 التكلفة: {cost}\n"
    "{refund}"
    "📊 الحالة: <b>{status}</b>\n"
    "🕒 التاريخ: {created}\n"
    "{error}"
)
ORDER_PROGRESS_LINE = "📈 المنفَّذ: {delivered} — المتبقي: {remains}\n"
ORDER_REFUND_LINE = "↩️ المسترجع: {refund}\n"
ORDER_ERROR_LINE = "⚠️ ملاحظة: {error}\n"
BTN_ORDER_CANCEL = "🛑 إلغاء الطلب"
BTN_ORDER_TICKET = "🎫 فتح تذكرة عن الطلب"
ORDER_CANCEL_CONFIRM = (
    "🛑 <b>تأكيد إلغاء الطلب {code}</b>\n\n"
    "سيُعاد المبلغ <b>{cost}</b> إلى رصيدك فوراً.\n"
    "هل أنت متأكد؟"
)
ORDER_CANCEL_DONE = "✅ أُلغي الطلب {code} وأُعيد إليك <b>{refund}</b>."

# ============================== المحفظة =============================== #

WALLET_TITLE = (
    "💰 <b>محفظتي</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "💵 الرصيد الحالي: <b>{balance}</b>\n"
    "📥 إجمالي الإيداع: {deposited}\n"
    "📤 إجمالي الإنفاق: {spent}\n"
    "━━━━━━━━━━━━━━━━━━━━"
)
BTN_WALLET_HISTORY = "📜 سجل العمليات"
BTN_MY_DEPOSITS = "🧾 طلبات الشحن"
HISTORY_TITLE = "📜 <b>سجل العمليات</b>\n\nالصفحة {page} من {pages}\n━━━━━━━━━━━━━━━━━━━━\n{lines}"
HISTORY_EMPTY = "📭 لا توجد عمليات بعد."

# ============================== الشحن ================================= #

DEPOSIT_METHODS_TITLE = (
    "➕ <b>شحن الرصيد</b>\n\n"
    "اختر طريقة التحويل المناسبة لك:"
)
DEPOSIT_METHODS_EMPTY = (
    "⚠️ لا توجد طرق شحن مفعّلة حالياً.\n"
    "تواصل مع الدعم الفني وسنفعّلها في أقرب وقت."
)
DEPOSIT_ASK_AMOUNT = (
    "💵 <b>{method}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{instructions}\n"
    "{account}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{limits}\n"
    "{fee_line}"
    "\nأرسل <b>المبلغ الذي حوّلته</b> كرقم."
)
#: يظهر فقط للطرق التي لها رسوم (وعندما يسمح الإعداد بإظهارها)
DEPOSIT_FEE_NOTICE = "🧾 رسوم هذه الطريقة: {fee} — تُخصم من المبلغ المحوَّل.\n"
DEPOSIT_ASK_REFERENCE = (
    "🧾 أرسل <b>رقم عملية التحويل</b> كما يظهر في إشعار الحوالة.\n\n"
    "المبلغ: {amount}"
)
DEPOSIT_ASK_PROOF = (
    "📸 أرسل <b>صورة الإيصال</b> (اختياري).\n\n"
    "يمكنك الضغط على «تخطي» إذا كان رقم العملية كافياً."
)
DEPOSIT_SUMMARY = (
    "🧾 <b>مراجعة طلب الشحن</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🏦 الطريقة: {method}\n"
    "💵 المبلغ المحوَّل: <b>{amount}</b>\n"
    "{fee_lines}"
    "🔢 رقم العملية: {reference}\n"
    "📸 الإيصال: {proof}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "سيراجع الفريق طلبك ويُضاف الرصيد بعد الاعتماد."
)
#: سطرا الرسوم والصافي داخل المراجعة وإشعار الاستلام
DEPOSIT_FEE_LINES = "🧾 رسوم الطريقة: {fee}\n💰 سيُضاف لرصيدك: <b>{net}</b>\n"
DEPOSIT_PROOF_ATTACHED = "مرفقة ✅"
DEPOSIT_PROOF_NONE = "بدون صورة"
DEPOSIT_CREATED = (
    "✅ <b>استلمنا طلب الشحن #{payment_id}</b>\n\n"
    "💵 المبلغ المحوَّل: {amount}\n"
    "{fee_lines}"
    "📊 الحالة: قيد المراجعة\n\n"
    "سيصلك إشعار فور اعتماده أو رفضه."
)
DEPOSITS_TITLE = "🧾 <b>طلبات الشحن</b>\n\n{lines}"
DEPOSITS_EMPTY = "📭 لا توجد طلبات شحن سابقة."
BTN_DEPOSIT_CANCEL = "🛑 إلغاء الطلب"
DEPOSIT_CANCELLED = "✅ أُلغي طلب الشحن #{payment_id}."

# ============================== الدعم ================================= #

SUPPORT_TITLE = (
    "🎫 <b>الدعم الفني</b>\n\n"
    "تذاكرك المفتوحة: <b>{open_count}</b>\n\n"
    "يمكنك فتح تذكرة واحدة في كل مرة، وسنرد عليك في أقرب وقت."
)
BTN_TICKET_NEW = "➕ تذكرة جديدة"
BTN_TICKETS_LIST = "📂 تذاكري"
TICKETS_TITLE = "📂 <b>تذاكري</b>\n\nالصفحة {page} من {pages}"
TICKETS_EMPTY = "📭 لا توجد تذاكر بعد."
TICKET_ASK_CATEGORY = "🗂 <b>تذكرة جديدة</b>\n\nاختر تصنيف المشكلة:"
TICKET_ASK_SUBJECT = "✏️ أرسل <b>عنواناً مختصراً</b> للمشكلة (3 أحرف على الأقل)."
TICKET_ASK_MESSAGE = "📝 اشرح مشكلتك بالتفصيل في رسالة واحدة."
TICKET_ASK_MESSAGE_ORDER = (
    "🎫 <b>تذكرة بخصوص الطلب {code}</b>\n"
    "📦 {service}\n\n"
    "📝 اشرح المشكلة بالتفصيل في رسالة واحدة."
)
TICKET_CREATED = (
    "✅ <b>تم فتح التذكرة #{ticket_id}</b>\n\n"
    "📌 الموضوع: {subject}\n\n"
    "سيصلك إشعار عند رد فريق الدعم."
)
TICKET_CARD = (
    "🎫 <b>التذكرة #{ticket_id}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📌 الموضوع: {subject}\n"
    "🗂 التصنيف: {category}\n"
    "📊 الحالة: <b>{status}</b>\n"
    "🕒 آخر تحديث: {updated}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{messages}"
)
TICKET_MESSAGE_LINE = "{icon} <b>{sender}</b> — {time}\n{text}\n"
BTN_TICKET_REPLY = "💬 إضافة رد"
BTN_TICKET_CLOSE = "✖️ إغلاق التذكرة"
TICKET_ASK_REPLY = "💬 أرسل ردك على التذكرة #{ticket_id}."
TICKET_REPLY_SENT = "✅ أُرسل ردك إلى فريق الدعم."
TICKET_CLOSED_BY_USER = "✅ أُغلقت التذكرة #{ticket_id}. شكراً لك."
TICKET_CATEGORIES: dict[str, str] = {
    "order": "📦 مشكلة في طلب",
    "payment": "💳 مشكلة في الشحن",
    "service": "🛍 استفسار عن خدمة",
    "account": "👤 مشكلة في الحساب",
    "other": "📝 موضوع آخر",
}

# ============================== الحساب ================================ #

ACCOUNT_CARD = (
    "👤 <b>حسابي</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🆔 المعرف: <code>{telegram_id}</code>\n"
    "👤 الاسم: {name}\n"
    "🏷 النوع: {role}\n"
    "💰 الرصيد: <b>{balance}</b>\n"
    "📦 الطلبات: {orders_count} (نشطة: {active_orders})\n"
    "🧾 طلبات الشحن: {payments_count}\n"
    "🎫 تذاكر مفتوحة: {tickets_open}\n"
    "📅 تاريخ الانضمام: {joined}\n"
    "━━━━━━━━━━━━━━━━━━━━"
)
BTN_NOTIFICATIONS = "🔔 إشعاراتي"
NOTIFICATIONS_TITLE = "🔔 <b>إشعاراتي</b>\n\nغير مقروء: <b>{unread}</b>\nالصفحة {page} من {pages}\n━━━━━━━━━━━━━━━━━━━━\n{lines}"
NOTIFICATIONS_EMPTY = "📭 لا توجد إشعارات."
BTN_MARK_ALL_READ = "✅ تعليم الكل كمقروء"
MARKED_READ = "✅ عُلّمت {count} إشعاراً كمقروء."

ROLE_LABELS: dict[str, str] = {
    "user": "عميل",
    "support": "دعم فني",
    "admin": "مشرف",
    "super_admin": "مشرف أعلى",
}

# ============================== معلومات =============================== #

INFO_TITLE = (
    "ℹ️ <b>{bot_name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{rules}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📞 للتواصل مع الدعم: {support}\n"
    "🔖 الإصدار: {version}"
)
INFO_NO_RULES = "لم تُضف شروط استخدام بعد."
INFO_NO_SUPPORT = "استخدم زر 🎫 الدعم داخل البوت."

# ======================== رسائل فورية وأخطاء ========================== #

ERR_GENERIC = "⚠️ حدث خطأ غير متوقع. تم تسجيل المشكلة وسنعالجها."
ERR_OLD_BUTTON = "⚠️ هذا الزر من نسخة قديمة. اضغط /start لفتح القائمة المحدثة."
ERR_UNKNOWN_BUTTON = "⚠️ زر غير معروف. اضغط /start للعودة إلى القائمة."
ERR_SESSION_LOST = "⚠️ انتهت الجلسة. ابدأ من جديد عبر /start."
ERR_NOT_TEXT = "⚠️ أرسل رسالة نصية من فضلك."
ERR_RATE_LIMITED = "⏳ أبطئ قليلاً — أرسلت طلبات كثيرة خلال وقت قصير."
ERR_RATE_BLOCKED = (
    "🚫 تم إيقاف استخدامك للبوت مؤقتاً لمدة {minutes} دقيقة بسبب كثرة الطلبات المتكررة.\n"
    "ستعود الخدمة تلقائياً بعد انتهاء المدة."
)
CONVERSATION_TIMED_OUT = (
    "⌛ انتهت الجلسة بسبب عدم النشاط وأُلغيت العملية الجارية حفاظاً على أمان حسابك.\n"
    "ابدأ من جديد من القائمة."
)
ERR_NO_PRIVATE = "ℹ️ هذا البوت يعمل في المحادثة الخاصة فقط."
UNKNOWN_COMMAND = "❓ أمر غير معروف. اضغط /start لعرض القائمة."
UNKNOWN_TEXT = "💡 استخدم الأزرار للتنقل، أو اضغط /start لعرض القائمة."
CANCELLED = "❌ أُلغيت العملية."
LOADING = "⏳ لحظة من فضلك..."
PAGE_INFO = "📄 الصفحة {page} من {pages}"
HELP_TEXT = (
    "🤖 <b>كيف أستخدم البوت؟</b>\n\n"
    "1️⃣ اشحن رصيدك من 💰 المحفظة ← ➕ شحن الرصيد\n"
    "2️⃣ اختر خدمة من 🛍 الخدمات\n"
    "3️⃣ أرسل الرابط والكمية ثم أكّد\n"
    "4️⃣ تابع التنفيذ من 📦 طلباتي\n\n"
    "الأوامر المتاحة:\n"
    "/start — القائمة الرئيسية\n"
    "/help — هذه الرسالة\n"
    "/cancel — إلغاء العملية الحالية\n"
    "/id — عرض معرفك في تيليجرام"
)
ID_TEXT = "🆔 معرفك في تيليجرام: <code>{telegram_id}</code>"
```

---

## `scripts/init_db.py`

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
from core.constants import APP_VERSION
from core.exceptions import BackupError
from database.database import Database
from database.migrator import Migrator
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.backup_service import create_backup_file
from services.settings_service import SettingsService
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
    "error_logs", "backups", "favorites", "channel_outbox",
)


async def seed_super_admins(db: Database, telegram_ids: tuple[int, ...]) -> list[str]:
    """
    إنشاء أو ترقية حسابات الأدمن الأعلى المذكورة في متغير البيئة.

    المخرجات: قائمة رسائل توضح ما تم لكل معرف.
    """
    # المصدر الوحيد: AuthService.bootstrap_super_admins (نفسه الذي يعمل عند إقلاع البوت)
    repos = Repositories(db)
    settings = SettingsService(db, repos)
    auth = AuthService(db, repos, settings, AuditService(db, repos), super_admin_ids=telegram_ids)
    labels = {
        "created": "✅ أُنشئ حساب أدمن أعلى للمعرف {id}",
        "promoted": "⬆️ تمت ترقية المستخدم {id} إلى أدمن أعلى",
        "unbanned": "🔓 رُفع الحظر عن الأدمن الأعلى {id}",
        "promoted_unbanned": "⬆️🔓 تمت ترقية {id} إلى أدمن أعلى ورُفع حظره",
        "unchanged": "ℹ️ المعرف {id} أدمن أعلى بالفعل",
    }
    return [labels[item.action].format(id=item.telegram_id) for item in await auth.bootstrap_super_admins()]


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
        if pending and await migrator.applied():
            # ترقية قاعدة قائمة: نسخة أمان أولاً، وفشلها يوقف الترقية
            try:
                artifact = await create_backup_file(
                    db, config.backup_dir, backup_type="pre_operation", app_version=APP_VERSION
                )
            except BackupError as exc:
                print(f"❌ تعذّر أخذ نسخة أمان قبل الترقية: {exc}")
                return 1
            print(f"🛟 نسخة أمان قبل الترقية: {artifact.filename}")
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

---

## `tests/integration/test_phase13_channels.py`

```python
"""
المرحلة 13 — البنود 1–4: الاشتراك الإجباري، إشعار المستخدم الجديد، توثيق الطلبات، قناة النسخ.

لا اختبار على تيليجرام حقيقي هنا: `FakeBot` يحاكي `getChatMember/getChat` بأخطاء تيليجرام الحقيقية
(`BadRequest("User not found")`, `Chat not found`, `TimedOut`) فنختبر منطقنا لا الشبكة.
"""

from __future__ import annotations

import time

import pytest
from telegram.error import BadRequest, Forbidden, TimedOut

from core.exceptions import NotificationBlockedError, NotificationTemporaryError, ValidationError
from handlers.common import navigation
from keyboards.callback_data import pack
from services import ServiceContainer
from services.subscription_service import CACHE_TTL_SECONDS
from tests.integration.test_user_interface import bot, context, load_user, press, run_middleware  # noqa: F401
from tests.telegram_fakes import make_callback_update, make_message_update

pytestmark = pytest.mark.asyncio

CHANNELS = {
    "channel_official": ("@smm_official", -1001000000001),
    "channel_proofs": ("@smm_proofs", -1001000000002),
    "channel_updates": ("@smm_updates", -1001000000003),
    "channel_offers": ("@smm_offers", -1001000000004),
}
UID = 100200300


async def _configure_channels(services: ServiceContainer, super_admin) -> None:
    """ضبط القنوات الأربع كما يفعل الأدمن من الإعدادات."""
    for key, (ref, _) in CHANNELS.items():
        await services.settings.set(key, ref, admin_id=super_admin.id)


def _join_all(bot, user_id: int = UID, status: str = "member") -> None:
    """جعل المستخدم عضواً في القنوات الأربع في بوت الاختبار."""
    for ref, _ in CHANNELS.values():
        bot.memberships[(ref, user_id)] = status


# --------------------------------- البند 1: الاشتراك الإجباري --------------------------------- #


async def test_gate_is_off_when_no_channels_configured(bot, context, user) -> None:  # noqa: F811
    """بلا قنوات مضبوطة لا بوابة ولا نداءات لتيليجرام."""
    update = make_message_update(bot, text="/start", user_id=user.telegram_id)
    assert await run_middleware(bot, context, update)
    assert not bot.member_calls


async def test_non_member_is_blocked_with_join_buttons(bot, context, services, user, super_admin) -> None:  # noqa: F811
    """غير المشترك لا يمرّ؛ يرى القنوات الأربع ❌ مع زر انضمام لكل واحدة وزر «تحقق»."""
    await _configure_channels(services, super_admin)
    update = make_message_update(bot, text="/start", user_id=user.telegram_id)
    assert await run_middleware(bot, context, update) is False
    text = bot.last.text
    assert text.count("\n❌ ") == 4 and "\n✅ " not in text
    urls = [button.url for row in bot.last.markup.inline_keyboard for button in row if button.url]
    assert sorted(urls) == sorted(f"https://t.me/{ref[1:]}" for ref, _ in CHANNELS.values())
    assert any(pack("sub", "check") == data for data in [b.callback_data for r in bot.last.markup.inline_keyboard for b in r])


async def test_partial_membership_still_blocked_and_marks_each_channel(bot, context, services, user, super_admin) -> None:  # noqa: F811
    """الاشتراك في ثلاث من أربع لا يكفي، والقناة الناقصة وحدها ❌."""
    await _configure_channels(services, super_admin)
    _join_all(bot)
    del bot.memberships[("@smm_offers", UID)]
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID)) is False
    assert bot.last.text.count("\n✅ ") == 3 and bot.last.text.count("\n❌ ") == 1


@pytest.mark.parametrize("status", ["left", "kicked"])
async def test_left_or_kicked_is_not_a_member(bot, context, services, user, super_admin, status) -> None:  # noqa: F811
    """حالات `left/kicked` ليست عضوية فعلية حتى لو وُجد سجل للمستخدم في القناة."""
    await _configure_channels(services, super_admin)
    _join_all(bot, status=status)
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID)) is False


async def test_full_member_passes_and_result_is_cached(bot, context, services, user, super_admin) -> None:  # noqa: F811
    """العضو في الأربع يمرّ؛ التحديث التالي يُخدم من الكاش (لا 4 نداءات جديدة)."""
    await _configure_channels(services, super_admin)
    _join_all(bot)
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID))
    assert len(bot.member_calls) == 4
    assert await run_middleware(bot, context, make_message_update(bot, text="/help", user_id=UID))
    assert len(bot.member_calls) == 4, "نتيجة «مشترك» تُعاد من الكاش خلال 5 دقائق"


async def test_check_button_bypasses_cache_and_lets_user_in(bot, context, services, user, super_admin) -> None:  # noqa: F811
    """بعد الاشتراك يضغط «تحقق»: تُعاد قراءة العضوية فوراً ويصل المستخدم للقائمة الرئيسية."""
    await _configure_channels(services, super_admin)
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID)) is False
    bot.clear()

    update = make_callback_update(bot, data=pack("sub", "check"), user_id=UID)
    assert await run_middleware(bot, context, update) is False, "لم يشترك بعد ⇒ يبقى على البوابة"
    assert bot.answers[-1]["alert"] and "قناة" in bot.answers[-1]["text"]

    _join_all(bot)
    update = make_callback_update(bot, data=pack("sub", "check"), user_id=UID)
    assert await run_middleware(bot, context, update), "اشترك فعلاً ⇒ يمرّ"
    await navigation.subscription_check_callback(update, context)
    assert "القائمة الرئيسية" in bot.last.text and bot.last.kind == "edit"


async def test_leaving_a_channel_blocks_again_after_check(bot, context, services, user, super_admin) -> None:  # noqa: F811
    """مشترك ثم غادر قناة: «تحقق» (يتجاوز الكاش) يُسقط الوصول."""
    await _configure_channels(services, super_admin)
    _join_all(bot)
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID))
    bot.memberships[("@smm_proofs", UID)] = "left"
    update = make_callback_update(bot, data=pack("sub", "check"), user_id=UID)
    assert await run_middleware(bot, context, update) is False


async def test_chat_not_found_is_fail_closed_and_alerts_admin_once(bot, context, services, user, admin, super_admin) -> None:  # noqa: F811
    """قناة مضبوطة خطأً (Chat not found): لا يُعدّ المستخدم مشتركاً، يُشرح له السبب، وينبَّه الأدمن مرة يومياً."""
    await _configure_channels(services, super_admin)
    _join_all(bot)
    bot.member_errors["@smm_updates"] = BadRequest("Chat not found")
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID)) is False
    assert "⚠️" in bot.last.text and "تعذّر التحقق" in bot.last.text
    rows = await services.repos.db.fetchall("SELECT dedupe_key FROM notifications WHERE dedupe_key LIKE 'manual:sub-config:%'")
    assert len(rows) >= 1
    first = len(rows)
    await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID))
    rows = await services.repos.db.fetchall("SELECT dedupe_key FROM notifications WHERE dedupe_key LIKE 'manual:sub-config:%'")
    assert len(rows) == first, "التنبيه مرة واحدة يومياً لكل قناة"


async def test_bot_not_admin_in_channel_is_fail_closed(bot, context, services, user, super_admin) -> None:  # noqa: F811
    """البوت ليس مشرفاً (Forbidden) ⇒ تعذّر التحقق ⇒ لا مرور."""
    await _configure_channels(services, super_admin)
    _join_all(bot)
    bot.member_errors["@smm_offers"] = Forbidden("Forbidden: bot is not a member of the channel chat")
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID)) is False


async def test_network_error_blocks_unknown_user_but_grace_keeps_recently_verified(bot, context, services, user, super_admin) -> None:  # noqa: F811
    """انقطاع الشبكة: المجهول يُمنع (فشل مغلق)، ومن تأكّد اشتراكه خلال الساعة الأخيرة لا يُطرد بسبب عطل مؤقت."""
    await _configure_channels(services, super_admin)
    for ref, _ in CHANNELS.values():
        bot.member_errors[ref] = TimedOut("timed out")
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID)) is False
    assert "تعذّر" in bot.last.text

    # نفس المستخدم بعد أن تأكّد اشتراكه قبل أكثر من 5 دقائق (انتهى الكاش) وأقل من ساعة
    sub = services.subscriptions
    for ref, _ in CHANNELS.values():
        bot.member_errors.pop(ref)
    _join_all(bot)
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID))
    for key in list(sub._verified_at):
        sub._verified_at[key] = time.monotonic() - (CACHE_TTL_SECONDS + 60)
    for ref, _ in CHANNELS.values():
        bot.member_errors[ref] = TimedOut("timed out")
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID))


async def test_staff_is_exempt_from_gate(bot, context, services, admin, super_admin) -> None:  # noqa: F811
    """الفريق الإداري لا تحجبه البوابة (حتى يصلح القنوات نفسها)."""
    await _configure_channels(services, super_admin)
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=admin.telegram_id))
    assert not bot.member_calls


async def test_disabling_requirement_removes_gate(bot, context, services, user, super_admin) -> None:  # noqa: F811
    """`subscription_required=false` يعطّل البوابة رغم ضبط القنوات."""
    await _configure_channels(services, super_admin)
    await services.settings.set("subscription_required", "false", admin_id=super_admin.id)
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID))


async def test_channel_settings_are_validated_and_normalized(services, super_admin) -> None:
    """قيم القنوات تُطبَّع (رابط ⇒ @name) وتُرفض الصيغ المعطوبة وروابط الدعوة برسالة مفهومة."""
    await services.settings.set("channel_official", "https://t.me/MyChannel", admin_id=super_admin.id)
    assert (await services.repos.settings.get("channel_official")).value == "@MyChannel"
    await services.settings.set("channel_offers", "1001234567890", admin_id=super_admin.id)
    assert (await services.repos.settings.get("channel_offers")).value == "-1001234567890"
    for bad in ("https://t.me/+AbCdEf", "قناة", "123", "@a"):
        with pytest.raises(ValidationError):
            await services.settings.set("channel_updates", bad, admin_id=super_admin.id)


# ------------------------------- البند 2: إشعار المستخدم الجديد ------------------------------- #


async def test_new_user_alert_goes_to_channel_with_masked_id(services, super_admin) -> None:
    """مستخدم جديد ⇒ منشور في صندوق قناة التنبيهات بالقالب المطلوب وبمعرّف مقنَّع، مرة واحدة."""
    await services.settings.set("admin_alert_chat_id", "-1002000000001", admin_id=super_admin.id)
    user, created = await services.users.get_or_create(telegram_id=1712345678, username="newbie", first_name="Ali", last_name="Saleh")
    assert created
    post = await services.repos.channel_outbox.get_by_dedupe(f"newuser:{user.id}")
    assert post is not None and post.kind == "admin_alert"
    assert post.title == "👤 مستخدم جديد 🔥"
    for needle in (f"رقم الحساب: {user.id}", "الاسم: Ali Saleh", "Username: @newbie", "Telegram ID: 17••••••••", "التسجيل:", "إجمالي المستخدمين:"):
        assert needle in post.message, needle
    assert "1712345678" not in post.message
    again, created_again = await services.users.get_or_create(telegram_id=1712345678)
    assert not created_again and again.id == user.id
    assert (await services.repos.channel_outbox.count_by_status()).get("queued") == 1


async def test_new_user_alert_falls_back_to_admin_dm_without_channel(services, admin) -> None:
    """بلا قناة تنبيهات: يصل لمن يملك `users.view` كإشعار خاص (لا يضيع الحدث)."""
    user, _ = await services.users.get_or_create(telegram_id=555000111, first_name="Sara")
    rows = await services.repos.db.fetchall("SELECT message FROM notifications WHERE dedupe_key LIKE ?", (f"manual:newuser:{user.id}:%",))
    assert rows and "Telegram ID: 55•••••••" in rows[0]["message"]


async def test_new_user_alert_can_be_disabled(services, super_admin) -> None:
    """`new_user_alert_enabled=false` ⇒ لا منشور ولا إشعار."""
    await services.settings.set("admin_alert_chat_id", "-1002000000001", admin_id=super_admin.id)
    await services.settings.set("new_user_alert_enabled", "false", admin_id=super_admin.id)
    user, _ = await services.users.get_or_create(telegram_id=555000222)
    assert await services.repos.channel_outbox.get_by_dedupe(f"newuser:{user.id}") is None


async def test_alert_failure_never_blocks_registration(services, super_admin, monkeypatch) -> None:
    """عطل في إعلان المستخدم الجديد لا يمنع تسجيله."""
    await services.settings.set("admin_alert_chat_id", "-1002000000001", admin_id=super_admin.id)

    async def boom(*args, **kwargs):
        raise RuntimeError("outbox down")

    monkeypatch.setattr(services.channels, "enqueue", boom)
    user, created = await services.users.get_or_create(telegram_id=555000333)
    assert created and await services.users.get(user.id) is not None


# --------------------------------- البند 3: توثيق الطلبات --------------------------------- #


async def test_order_is_documented_in_orders_log_channel_without_secrets(services, super_admin, admin, user, mock_service) -> None:
    """طلب جديد ⇒ منشور توثيق بالقالب المطلوب: القسم/الخدمة/الرقم/الكمية/السعر ريال+$/عميل مقنّع/رابط مقنّع."""
    await services.settings.set("orders_log_chat_id", "-1003000000001", admin_id=super_admin.id)
    await services.wallet.adjust_balance(target=user, amount_units=5_300_000, admin=admin, reason="رصيد", credit=True)
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/private_account_name", quantity=1000
    )
    post = await services.repos.channel_outbox.get_by_dedupe(f"order:{order.id}")
    assert post is not None and post.kind == "orders_log" and post.title == "🔥 طلب جديد"
    body = post.message
    for needle in ("القسم:", "الخدمة: متابعين انستغرام (Mock)", f"رقم الطلب: {order.public_code}", "الكمية: 1,000",
                   "السعر:", "ريال" if False else "$", "العميل: 10•••••••", "الرابط: https://instagram.com/••••"):
        assert needle in body, needle
    assert "private_account_name" not in body and "100200300" not in body
    assert "api" not in body.lower().replace("instagram", "")


async def test_order_not_documented_without_destination_and_failure_does_not_break_order(services, super_admin, admin, user, mock_service, monkeypatch) -> None:
    """بلا وجهة لا منشور؛ وعطل التوثيق لا يُسقط الطلب ولا الخصم."""
    await services.wallet.adjust_balance(target=user, amount_units=5_300_000, admin=admin, reason="رصيد", credit=True)
    first = await services.orders.create_order(user, service_id=mock_service.id, link="https://instagram.com/a", quantity=1000)
    assert await services.repos.channel_outbox.get_by_dedupe(f"order:{first.id}") is None

    await services.settings.set("orders_log_chat_id", "-1003000000001", admin_id=super_admin.id)

    async def boom(*args, **kwargs):
        raise RuntimeError("outbox down")

    monkeypatch.setattr(services.channels, "enqueue", boom)
    second = await services.orders.create_order(user, service_id=mock_service.id, link="https://instagram.com/b", quantity=1000)
    assert second.id != first.id and (await services.repos.orders.get(second.id)) is not None


async def test_flush_delivers_each_kind_to_its_own_destination(services, super_admin) -> None:
    """التنبيهات وتوثيق الطلبات يذهبان لوجهتين مختلفتين، ولا شيء لقناة النسخ."""
    await services.settings.set("admin_alert_chat_id", "-1002000000001", admin_id=super_admin.id)
    await services.settings.set("orders_log_chat_id", "-1003000000001", admin_id=super_admin.id)
    services.channels.backup_channel_id = -1004000000001
    sent: list[int] = []

    async def sender(chat_id, title, message):
        sent.append(chat_id)
        return 1

    async with services.db.transaction() as tx:
        await services.channels.enqueue(tx, kind="admin_alert", title="a", message="m", dedupe_key="t:1")
        await services.channels.enqueue(tx, kind="orders_log", title="o", message="m", dedupe_key="t:2")
    report = await services.channels.flush(sender)
    assert report.sent == 2 and sorted(sent) == [-1003000000001, -1002000000001]
    assert -1004000000001 not in sent


async def test_destination_equal_to_backup_channel_is_refused(services, super_admin, admin) -> None:
    """وجهة تنبيه/توثيق مطابقة لقناة النسخ تُرفض (القناة للنسخ فقط): لا إرسال، وتنبيه للأدمن."""
    services.channels.backup_channel_id = -1004000000001
    await services.settings.set("orders_log_chat_id", "-1004000000001", admin_id=super_admin.id)
    called: list[int] = []

    async def sender(chat_id, title, message):
        called.append(chat_id)
        return 1

    async with services.db.transaction() as tx:
        await services.channels.enqueue(tx, kind="orders_log", title="o", message="m", dedupe_key="t:9")
    report = await services.channels.flush(sender)
    assert report.skipped == 1 and not called
    alerts = await services.repos.db.fetchall("SELECT 1 FROM notifications WHERE dedupe_key LIKE 'manual:channel-dest:%'")
    assert alerts


async def test_permanent_channel_failure_marks_failed_and_alerts_without_loop(services, super_admin, admin) -> None:
    """فشل دائم (البوت ليس في القناة) ⇒ failed بلا إعادة، تنبيه أدمن واحد، ولا منشور جديد في القناة نفسها."""
    await services.settings.set("admin_alert_chat_id", "-1002000000001", admin_id=super_admin.id)

    async def sender(chat_id, title, message):
        raise NotificationBlockedError("محادثة غير متاحة: Chat not found")

    async with services.db.transaction() as tx:
        await services.channels.enqueue(tx, kind="admin_alert", title="a", message="m", dedupe_key="t:7")
    report = await services.channels.flush(sender)
    assert report.failed == 1
    counts = await services.repos.channel_outbox.count_by_status()
    assert counts.get("failed") == 1 and not counts.get("queued")
    assert (await services.channels.flush(sender)).claimed == 0, "الفاشل نهائياً لا يُعاد"
    assert not await services.repos.db.fetchall("SELECT 1 FROM channel_outbox WHERE dedupe_key LIKE 'alert:channel-dest%'"), "تنبيه الفشل لا يُنسخ للقناة"
    assert await services.repos.db.fetchall("SELECT 1 FROM notifications WHERE dedupe_key LIKE 'manual:channel-dest:admin_alert:%'")


async def test_temporary_failure_is_retried_later(services, super_admin) -> None:
    """فشل مؤقت ⇒ يبقى في الصندوق ويُرسل لاحقاً عند نجاح الشبكة."""
    await services.settings.set("admin_alert_chat_id", "-1002000000001", admin_id=super_admin.id)

    async def failing(chat_id, title, message):
        raise NotificationTemporaryError("شبكة")

    async with services.db.transaction() as tx:
        await services.channels.enqueue(tx, kind="admin_alert", title="a", message="m", dedupe_key="t:8")
    assert (await services.channels.flush(failing)).retried == 1
    await services.repos.db.fetchone("SELECT 1")
    async with services.db.transaction() as tx:
        await tx.execute("UPDATE channel_outbox SET next_attempt_at = '2000-01-01T00:00:00Z'")

    async def ok(chat_id, title, message):
        return 1

    assert (await services.channels.flush(ok)).sent == 1


# --------------------------------- البند 4: قناة النسخ + التشخيص --------------------------------- #


async def test_diagnose_explains_chat_not_found_and_missing_post_permission(bot, services) -> None:  # noqa: F811
    """التشخيص يفرّق: غير موجودة / البوت ليس مشرفاً / بلا صلاحية نشر / سليمة."""
    from types import SimpleNamespace

    result = await services.channels.diagnose(bot, "قناة النسخ", -1001111111111)
    assert result.ok is False and result.problem == "Chat not found" and any("-100" in hint for hint in result.hints)

    bot.chats[-1001111111111] = SimpleNamespace(id=-1001111111111, type="channel", title="Backups")
    bot.memberships[(-1001111111111, bot.id)] = "member"
    assert (await services.channels.diagnose(bot, "x", -1001111111111)).problem == "البوت ليس مشرفاً في القناة"

    bot.memberships[(-1001111111111, bot.id)] = "administrator"
    assert (await services.channels.diagnose(bot, "x", -1001111111111)).ok is True

    bot.chats[-1001111111111] = BadRequest("Chat not found")
    assert (await services.channels.diagnose(bot, "x", -1001111111111)).ok is False
    bot.chats[-1001111111111] = TimedOut("t")
    assert (await services.channels.diagnose(bot, "x", -1001111111111)).ok is None


async def test_backup_delivery_error_explains_chat_not_found(services, super_admin, bot, tmp_path) -> None:  # noqa: F811
    """رسالة فشل رفع النسخة تشرح «Chat not found» وتدلّ على شاشة القنوات."""
    services.backups.channel_id = -1005000000001

    async def failing_send(**kwargs):
        raise BadRequest("Chat not found")

    bot.send_document = failing_send
    info = await services.backups.create(super_admin)
    from core.exceptions import BackupError

    with pytest.raises(BackupError) as caught:
        await services.backups.send_to_channel(super_admin, bot, info.id)
    assert "-100" in caught.value.user_message and "القنوات" in caught.value.user_message


def test_config_normalizes_channel_env_vars(monkeypatch, tmp_path) -> None:
    """BACKUP_CHANNEL_ID/ADMIN_ALERT_CHAT_ID: يُصحَّح الرقم بلا -100، ويُقبل @name/الرابط، ويُرفض رابط الدعوة بوضوح."""
    from config import Config, ConfigError

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "d" / "t.db"))
    monkeypatch.setenv("BACKUP_CHANNEL_ID", "1001234567890")
    monkeypatch.setenv("ADMIN_ALERT_CHAT_ID", "https://t.me/mychan")
    cfg = Config.load(env_file=tmp_path / "none.env")
    assert cfg.backup_channel_id == -1001234567890 and cfg.admin_alert_chat_id == "@mychan"
    monkeypatch.setenv("BACKUP_CHANNEL_ID", "https://t.me/+AbCdEf")
    with pytest.raises(ConfigError) as caught:
        Config.load(env_file=tmp_path / "none.env")
    assert "BACKUP_CHANNEL_ID" in str(caught.value)


# ------------------------------------ شاشة الأدمن «📢 القنوات» ------------------------------------ #


async def test_admin_channels_screens_show_check_and_test(bot, context, services, super_admin) -> None:  # noqa: F811
    """الشاشة تعرض القيم، الفحص يشرح «Chat not found» بالحل، واختبار الإرسال يعمل ويبلّغ بالنتيجة."""
    from types import SimpleNamespace

    from handlers.admin import channels as admin_channels

    await services.settings.set("channel_official", "@smm_official", admin_id=super_admin.id)
    await services.settings.set("admin_alert_chat_id", "-1002000000001", admin_id=super_admin.id)
    services.backups.channel_id = -1005000000001
    await load_user(bot, context, super_admin)

    await press(bot, context, admin_channels.home_screen, pack("ch", "home"), super_admin.telegram_id)
    text = bot.last.text
    assert "@smm_official" in text and "-1002000000001" in text and "-1005000000001" in text and "النسخ" in text
    callbacks = [b.callback_data for row in bot.last.markup.inline_keyboard for b in row]
    assert pack("ch", "check") in callbacks and pack("ch", "test", "alert") in callbacks

    bot.chats["@smm_official"] = SimpleNamespace(id=-1001, type="channel", title="Official")
    bot.memberships[(-1001, bot.id)] = "administrator"
    await press(bot, context, admin_channels.check_screen, pack("ch", "check"), super_admin.telegram_id)
    text = bot.last.text
    assert "✅ 📢 القناة الرسمية" in text
    assert "Chat not found" in text and "-100" in text, "قناة النسخ غير الموجودة تُشرح بسببها وحلها"

    await press(bot, context, admin_channels.test_action, pack("ch", "test", "alert"), super_admin.telegram_id)
    assert any(item.chat_id == -1002000000001 and "اختبار" in item.text for item in bot.sent)
    assert "أُرسلت" in bot.last.text
    await press(bot, context, admin_channels.test_action, pack("ch", "test", "orders"), super_admin.telegram_id)
    assert "غير مضبوطة" in bot.last.text, "بلا وجهة توثيق: يُقال ذلك بوضوح بدل نجاح كاذب"


async def test_admin_channels_screen_requires_permission(bot, context, services, user) -> None:  # noqa: F811
    """مستخدم عادي لا يفتح الشاشة ولا يفحص (الصلاحية على الـcallback نفسه)."""
    from handlers.admin import channels as admin_channels

    await load_user(bot, context, user)
    await press(bot, context, admin_channels.check_screen, pack("ch", "check"), user.telegram_id)
    assert not bot.sent and bot.answers[-1]["alert"]
```

---

## `tests/integration/test_phase13_ops.py`

```python
"""
المرحلة 13 — البنود 12 و13 و7(جزء /start): الأدمن الأعلى من البيئة، تعارض getUpdates، خادم الصحة، رسالة /start.
"""

from __future__ import annotations

import asyncio

import pytest
from telegram.error import Conflict, NetworkError

import main as app_main
from config import Config
from handlers.common import navigation
from services import ServiceContainer
from tests.integration.test_user_interface import bot, context, load_user, run_middleware  # noqa: F401
from tests.telegram_fakes import make_message_update
from utils.conflict_guard import ConflictGuard
from utils.health_server import HealthServer

pytestmark = pytest.mark.asyncio


# --------------------------------- البند 12: الأدمن الأعلى من البيئة --------------------------------- #


async def test_bootstrap_creates_promotes_and_unbans_then_is_idempotent(services: ServiceContainer, repos, user) -> None:
    """إنشاء حساب جديد، ترقية مستخدم قائم، رفع حظر — ومرة ثانية لا يكتب شيئاً."""
    async with repos.db.transaction() as tx:
        await repos.users.set_ban(tx, user.id, banned=True, reason="خطأ")
    outcomes = await services.auth.bootstrap_super_admins((user.telegram_id, 4_040_404_040))
    assert {item.telegram_id: item.action for item in outcomes} == {
        user.telegram_id: "promoted_unbanned",
        4_040_404_040: "created",
    }
    promoted = await services.users.get(user.id)
    assert promoted.role == "super_admin" and not promoted.is_banned
    created = await services.users.get_by_telegram(4_040_404_040)
    assert created.role == "super_admin"

    audits_before = await repos.db.fetchval("SELECT COUNT(*) FROM audit_logs WHERE action = 'system.bootstrap_super_admin'")
    assert audits_before == 2
    again = await services.auth.bootstrap_super_admins((user.telegram_id, 4_040_404_040))
    assert [item.action for item in again] == ["unchanged", "unchanged"]
    assert await repos.db.fetchval("SELECT COUNT(*) FROM audit_logs WHERE action = 'system.bootstrap_super_admin'") == audits_before


async def test_bootstrap_uses_env_ids_by_default(services: ServiceContainer, repos) -> None:
    """بلا وسيط: يستعمل `SUPER_ADMIN_IDS` المحقونة في الخدمة (كما يفعل main.post_init)."""
    services.auth.super_admin_ids = (6_060_606_060,)
    outcomes = await services.auth.bootstrap_super_admins()
    assert [item.action for item in outcomes] == ["created"]
    assert (await services.users.get_by_telegram(6_060_606_060)).role == "super_admin"


async def test_middleware_heals_demoted_env_super_admin_instantly(bot, context, services, repos, super_admin) -> None:  # noqa: F811
    """أدمن أعلى من البيئة فقد دوره أو حُظر خطأً: أول تحديث منه يُصلح الحساب ويدخل اللوحة."""
    services.auth.super_admin_ids = (super_admin.telegram_id,)
    async with repos.db.transaction() as tx:
        await repos.users.set_role(tx, super_admin.id, "user")
        await repos.users.set_ban(tx, super_admin.id, banned=True, reason="خطأ")
    update = make_message_update(bot, text="/start", user_id=super_admin.telegram_id)
    assert await run_middleware(bot, context, update)
    healed = await services.users.get(super_admin.id)
    assert healed.role == "super_admin" and not healed.is_banned
    assert await services.auth.is_admin(healed)


async def test_env_super_admin_enters_even_when_registration_is_closed(bot, context, services) -> None:  # noqa: F811
    """إغلاق التسجيل لا يقفل المالك خارج بوته (أول دخول له يُنشئ حسابه)، ويبقى المستخدم العادي مرفوضاً."""
    services.auth.super_admin_ids = (7_070_707_070,)
    await services.settings.set("registration_enabled", "false", admin_id=None)
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=7_070_707_070))
    assert (await services.users.get_by_telegram(7_070_707_070)).role == "super_admin"
    bot.clear()
    assert not await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=8_080_808_080))


async def test_non_env_user_never_becomes_super_admin(bot, context, services, user) -> None:  # noqa: F811
    """من ليس في البيئة لا يترقّى بأي مسار."""
    services.auth.super_admin_ids = (1,)
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=user.telegram_id))
    assert (await services.users.get(user.id)).role == "user"


def test_super_admin_ids_parsing_is_forgiving(monkeypatch, tmp_path) -> None:
    """الصيغ الشائعة عند اللصق في Render: أقواس، علامات اقتباس، مسافات، فاصلة عربية."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "d" / "t.db"))
    for raw in ('123456789,987654321', '[123456789, 987654321]', '"123456789" ، "987654321"', "123456789 987654321", "123456789;987654321"):
        monkeypatch.setenv("SUPER_ADMIN_IDS", raw)
        assert Config.load(env_file=tmp_path / "none.env").super_admin_ids == (123456789, 987654321), raw
    monkeypatch.setenv("SUPER_ADMIN_IDS", "123,abc")
    from config import ConfigError

    with pytest.raises(ConfigError):
        Config.load(env_file=tmp_path / "none.env")


async def test_init_db_seed_uses_same_service(db, repos) -> None:
    """`scripts.init_db.seed_super_admins` يمر من نفس الخدمة (مصدر واحد) وidempotent."""
    from scripts.init_db import seed_super_admins

    first = await seed_super_admins(db, (9_090_909_090,))
    second = await seed_super_admins(db, (9_090_909_090,))
    assert "أُنشئ" in first[0] and "بالفعل" in second[0]


# ------------------------------------ البند 13: Conflict ------------------------------------ #


class _Clock:
    """ساعة يدوية لاختبار نوافذ الزمن."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _guard(stops: list[int]) -> tuple[ConflictGuard, _Clock]:
    clock = _Clock()
    return ConflictGuard(lambda: stops.append(1), clock=clock), clock


def test_transient_conflict_does_not_stop_the_bot() -> None:
    """تعارض عابر (نشر Render متداخل) يزول خلال أقل من دقيقة ⇒ لا إيقاف."""
    stops: list[int] = []
    guard, clock = _guard(stops)
    for _ in range(8):
        guard.on_polling_error(Conflict("terminated by other getUpdates request"))
        clock.now += 4
    assert not stops and not guard.tripped


def test_persistent_conflict_stops_once_with_clear_reason(caplog) -> None:
    """تعارض مستمر ≥ 60ث و≥ 5 أحداث ⇒ إيقاف آمن مرة واحدة فقط وسجل CRITICAL يشرح الحل."""
    stops: list[int] = []
    guard, clock = _guard(stops)
    with caplog.at_level("WARNING"):
        for _ in range(20):
            guard.on_polling_error(Conflict("terminated by other getUpdates request"))
            clock.now += 10
    assert guard.tripped and stops == [1]
    assert any("نفس التوكن" in record.getMessage() and record.levelname == "CRITICAL" for record in caplog.records)


def test_conflict_that_stops_for_a_while_is_forgotten() -> None:
    """تعارضات متباعدة جداً (أقدم من النافذة) لا تتجمع لتصبح «مستمرة»."""
    stops: list[int] = []
    guard, clock = _guard(stops)
    for _ in range(4):
        guard.on_polling_error(Conflict("x"))
        clock.now += 1
    clock.now += 600
    for _ in range(4):
        guard.on_polling_error(Conflict("x"))
        clock.now += 1
    assert not stops and guard.recent_conflicts == 4


def test_other_errors_are_logged_without_token_and_never_stop(caplog) -> None:
    """أخطاء الشبكة العادية لا توقف شيئاً، ونص الخطأ يُنقّى من التوكن."""
    from utils.security import register_secret

    token = "123456789:AAConflictGuardSecretToken0123456789"
    register_secret(token)
    stops: list[int] = []
    guard, _ = _guard(stops)
    with caplog.at_level("WARNING"):
        for _ in range(50):
            guard.on_polling_error(NetworkError(f"boom https://api.telegram.org/bot{token}/getUpdates"))
    assert not stops and not guard.tripped
    assert token not in " ".join(record.getMessage() for record in caplog.records)


def test_main_returns_distinct_exit_code_on_persistent_conflict(monkeypatch, tmp_path, capsys) -> None:
    """main(): تعارض مستمر ⇒ رمز خروج 3 ورسالة عربية واضحة (لا 0 ولا 1)."""
    token = "123456789:AAConflictExitCodeToken0123456789012"
    monkeypatch.setenv("BOT_TOKEN", token)
    monkeypatch.setenv("SUPER_ADMIN_IDS", "111222333")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "t.db"))
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "logs" / "bot.log"))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(app_main, "setup_logging", lambda *a, **k: None)

    class _App:
        def __init__(self) -> None:
            self.bot_data: dict = {}
            self.stopped = False

        def stop_running(self) -> None:
            self.stopped = True

        def run_polling(self, **kwargs) -> None:
            callback = kwargs["error_callback"]
            clock_value = [0.0]
            guard = self.bot_data["conflict_guard"]
            guard._clock = lambda: clock_value[0]
            for _ in range(10):
                callback(Conflict("terminated by other getUpdates request"))
                clock_value[0] += 10

    app = _App()
    monkeypatch.setattr(app_main, "build_application", lambda config: app)
    assert app_main.main() == 3
    assert app.stopped
    assert "نفس التوكن" in capsys.readouterr().err


async def test_health_server_responds_and_hides_secrets() -> None:
    """GET /health ⇒ 200 JSON بلا أسرار؛ مسار آخر 404؛ POST 405؛ والاتصال يُغلق."""
    server = HealthServer(0, lambda: {"status": "ok", "version": "x"}, host="127.0.0.1")
    port = await server.start()
    try:
        async def request(raw: bytes) -> bytes:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(raw)
            await writer.drain()
            data = await asyncio.wait_for(reader.read(), 5)
            writer.close()
            return data

        ok = await request(b"GET /health HTTP/1.1\r\nHost: x\r\n\r\n")
        assert ok.startswith(b"HTTP/1.1 200") and b'"status": "ok"' in ok
        assert (await request(b"GET /healthz HTTP/1.1\r\n\r\n")).startswith(b"HTTP/1.1 200")
        assert (await request(b"GET /admin HTTP/1.1\r\n\r\n")).startswith(b"HTTP/1.1 404")
        assert (await request(b"POST / HTTP/1.1\r\n\r\n")).startswith(b"HTTP/1.1 405")
        assert (await request(b"garbage\r\n\r\n")).startswith(b"HTTP/1.1 400")
    finally:
        await server.stop()


def test_config_reads_port_for_health_and_rejects_bad_port(monkeypatch, tmp_path) -> None:
    """PORT اختياري: غائب ⇒ لا خادم صحة، صحيح ⇒ يُقرأ، خارج المدى ⇒ خطأ إعداد واضح."""
    from config import ConfigError

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "d" / "t.db"))
    monkeypatch.delenv("PORT", raising=False)
    assert Config.load(env_file=tmp_path / "none.env").health_port is None
    monkeypatch.setenv("PORT", "10000")
    assert Config.load(env_file=tmp_path / "none.env").health_port == 10000
    monkeypatch.setenv("PORT", "70000")
    with pytest.raises(ConfigError):
        Config.load(env_file=tmp_path / "none.env")


# ------------------------------------ البند 7: /start ------------------------------------ #


async def test_start_sends_one_message_and_cleans_previous_menu(bot, context, services, user) -> None:  # noqa: F811
    """/start: رسالة واحدة (ترحيب + قائمة)، تُحذف رسالة الأمر نفسها والقائمة السابقة بدل تراكم الرسائل."""
    first = make_message_update(bot, text="/start", user_id=50_010)
    assert await run_middleware(bot, context, first)
    await navigation.start_command(first, context)
    assert len(bot.sent) == 1 and "الرصيد" in bot.sent[0].text and "أهلاً" in bot.sent[0].text
    assert "ابدأ بخطوتين" in bot.sent[0].text, "الجديد يرى توجيهاً واضحاً"
    assert (50_010, first.message.message_id) in bot.deleted
    menu_id = context.user_data["menu_msg_id"]

    second = make_message_update(bot, text="/start", user_id=50_010)
    assert await run_middleware(bot, context, second)
    await navigation.start_command(second, context)
    assert len(bot.sent) == 2, "رسالة واحدة جديدة فقط لكل /start"
    assert (50_010, menu_id) in bot.deleted, "القائمة السابقة حُذفت"
    assert "ابدأ بخطوتين" not in bot.sent[1].text, "العائد لا يكرَّر عليه الإرشاد"


# ======================= تنظيف الطابور وترتيب except ======================= #


async def test_maintenance_cleans_only_old_final_channel_posts(bot, services, repos, db) -> None:  # noqa: F811
    """الصيانة تحذف منشورات القنوات المنتهية القديمة فقط؛ المعلّق والحديث يبقيان."""
    from jobs.maintenance_jobs import database_maintenance
    from tests.telegram_fakes import FakeContext
    from utils.datetime_utils import iso_minus_days

    async with db.transaction() as tx:
        ids = {}
        for key, status, age in (("old-sent", "sent", 45), ("old-queued", "queued", 45), ("new-sent", "sent", 1)):
            ids[key] = await repos.channel_outbox.enqueue(tx, kind="orders_log", title="t", message="m", dedupe_key=key)
            await tx.execute(
                "UPDATE channel_outbox SET status=?, created_at=? WHERE id=?", (status, iso_minus_days(age), ids[key])
            )

    result = await database_maintenance(FakeContext(bot, services))
    assert result["channel_posts_removed"] == 1
    remaining = {r["dedupe_key"] for r in await db.fetchall("SELECT dedupe_key FROM channel_outbox")}
    assert remaining == {"old-queued", "new-sent"}


async def test_sender_classifies_badrequest_as_permanent_and_timeout_as_temporary() -> None:
    """BadRequest فرع من NetworkError في PTB: يجب أن يبقى دائماً لا مؤقتاً (ترتيب except)."""
    from telegram.error import BadRequest, TimedOut

    from core.exceptions import NotificationPermanentError, NotificationTemporaryError
    from jobs.telegram_sender import TelegramNotificationSender

    class _Bot:
        def __init__(self, error: Exception) -> None:
            self.error = error

        async def send_message(self, **_kwargs):
            raise self.error

    with pytest.raises(NotificationPermanentError):
        await TelegramNotificationSender(_Bot(BadRequest("Can't parse entities")))(1, "t", "m")
    with pytest.raises(NotificationTemporaryError):
        await TelegramNotificationSender(_Bot(TimedOut("timeout")))(1, "t", "m")
```

---

## `tests/integration/test_phase13_service_card.py`

```python
"""
بطاقة الخدمة والدولار ورقم الخدمة والمفضلة (المرحلة 13 — بنود 5 و6 و8 و19).

كلها عبر FakeBot ومعالجات حقيقية وقاعدة SQLite مؤقتة؛ لا Telegram حقيقي.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.money import to_units
from handlers.user import catalog as catalog_handlers
from handlers.user import favorites as favorites_handlers
from keyboards.callback_data import NS_CATALOG, NS_FAV, NS_NEW, pack
from keyboards.user_kb import service_button_label
from services.catalog_service import MAX_FAVORITES
from tests.integration.test_user_interface import bot, context, load_user, press, write  # noqa: F401,F811
from utils.formatters import local_amount, price_pair

pytestmark = pytest.mark.asyncio


async def _open_card(bot, context, user, service_id, category_id=1, page=1):  # noqa: F811
    await load_user(bot, context, user)
    await press(bot, context, catalog_handlers.service_card_screen,
                pack(NS_CATALOG, "svc", service_id, category_id, page), user.telegram_id)
    return bot.last


async def test_local_amount_drops_trailing_zeros() -> None:
    """530.00 ⇒ «530 ريال»، و530.50 تبقى، والآلاف بفاصلة."""
    assert local_amount(to_units(Decimal("530")), "ريال") == "530 ريال"
    assert local_amount(to_units(Decimal("530.5")), "ريال") == "530.50 ريال"
    assert local_amount(to_units(Decimal("12345")), "ريال") == "12,345 ريال"


async def test_price_pair_is_dollar_first_and_consistent() -> None:
    """$1.00 مقابل 530 ريال عند الصرف 530 — والمقابل هو المبلغ الحقيقي."""
    usd, local = price_pair(to_units(Decimal("530")), "ريال", Decimal("530"))
    assert usd == "$1.00"
    assert local == "530 ريال"


async def test_card_shows_id_dollar_rate_and_unset_fields(bot, context, user, mock_service, services) -> None:  # noqa: F811
    """البطاقة: الرقم، الدولار، المقابل، الصرف، «غير محددة» للناقص، حدّان، زرا طلب ومفضلة."""
    await services.settings.set("usd_rate", "530", admin_id=None)
    await services.repos.settings.get("usd_rate")
    msg = await _open_card(bot, context, user, mock_service.id)
    text = msg.text
    assert f"#{mock_service.id}" in text
    assert "💵 السعر لكل 1000: <b>$" in text
    assert "💴 ما يعادل:" in text and "ريال" in text
    assert "1$ = 530" in text
    assert text.count("غير محددة") >= 2  # الجودة والضمان لم تُضبطا
    assert "الحد الأدنى" in text and "الحد الأقصى" in text
    buttons = msg.buttons
    assert pack(NS_NEW, "start", mock_service.id) in buttons
    assert pack(NS_FAV, "add", mock_service.id, 1, 1) in buttons


async def test_card_uses_provided_speed_quality_guarantee(bot, context, user, mock_service, services) -> None:  # noqa: F811
    """الحقول المضبوطة تظهر كما هي لا «غير محددة»."""
    async with services.db.transaction() as tx:
        await tx.execute(
            "UPDATE services SET speed_text=?, quality_text=?, guarantee_text=? WHERE id=?",
            ("1000/ساعة", "عالية", "30 يوماً", mock_service.id),
        )
    text = (await _open_card(bot, context, user, mock_service.id)).text
    assert "1000/ساعة" in text and "عالية" in text and "30 يوماً" in text
    assert "غير محددة" not in text


async def test_service_button_label_has_id_and_fits_telegram_limit(mock_service) -> None:
    """زر الخدمة يحمل الرقم والسعر ولا يتجاوز 64 حرفاً مهما طال الاسم."""
    from dataclasses import replace

    long = replace(mock_service, name="اسم خدمة طويل جداً " * 10)
    label = service_button_label(long, symbol="ريال", usd_rate=Decimal("530"))
    assert label.startswith(f"#{long.id} · ")
    assert "$" in label and len(label) <= 64


async def test_favorite_add_toggle_no_duplicates_and_remove(bot, context, user, mock_service, services) -> None:  # noqa: F811
    """إضافة ⇒ البطاقة تعرض «إزالة»؛ إضافة ثانية لا تكرر؛ إزالة ⇒ تعود «مفضلة»."""
    await load_user(bot, context, user)
    for _ in range(2):
        await press(bot, context, favorites_handlers.favorite_toggle,
                    pack(NS_FAV, "add", mock_service.id, 1, 1), user.telegram_id)
    assert await services.repos.favorites.count_for_user(user.id) == 1
    assert pack(NS_FAV, "del", mock_service.id, 1, 1) in bot.last.buttons

    await press(bot, context, favorites_handlers.favorite_toggle,
                pack(NS_FAV, "del", mock_service.id, 1, 1), user.telegram_id)
    assert await services.repos.favorites.count_for_user(user.id) == 0
    assert pack(NS_FAV, "add", mock_service.id, 1, 1) in bot.last.buttons


async def test_favorites_list_empty_and_filled_and_back_from_card(bot, context, user, mock_service, services) -> None:  # noqa: F811
    """قائمة فارغة ⇒ رسالة إرشاد؛ بعد الإضافة تظهر الخدمة؛ البطاقة منها ترجع للمفضلة لا للتصنيف."""
    await load_user(bot, context, user)
    await press(bot, context, favorites_handlers.favorites_screen, pack(NS_FAV, "list", 1), user.telegram_id)
    assert "لا توجد خدمات" in (bot.last.text or "")

    await services.catalog.add_favorite(user, mock_service.id)
    await press(bot, context, favorites_handlers.favorites_screen, pack(NS_FAV, "list", 1), user.telegram_id)
    assert f"#{mock_service.id}" in str(bot.last.markup)
    card = await _open_card(bot, context, user, mock_service.id, category_id=0)
    assert pack(NS_FAV, "list", 1) in card.buttons
    assert pack(NS_CATALOG, "open", 0, 1) not in card.buttons


async def test_favorites_are_per_user_and_hide_unavailable(user, admin, mock_service, services) -> None:  # noqa: F811
    """مفضلة كل مستخدم منفصلة، والخدمة المعطّلة تختفي من القائمة دون حذفها."""
    await services.catalog.add_favorite(user, mock_service.id)
    items, _, _ = await services.catalog.favorites_page(admin, page=1, page_size=6)
    assert items == []
    items, _, _ = await services.catalog.favorites_page(user, page=1, page_size=6)
    assert [s.id for s in items] == [mock_service.id]
    async with services.db.transaction() as tx:
        await tx.execute("UPDATE services SET is_active=0 WHERE id=?", (mock_service.id,))
    items, _, _ = await services.catalog.favorites_page(user, page=1, page_size=6)
    assert items == []
    assert await services.repos.favorites.count_for_user(user.id) == 1


async def test_favorite_limit_is_enforced(user, mock_service, services, monkeypatch) -> None:  # noqa: F811
    """تجاوز الحد يُرفض برسالة عربية واضحة ولا يُكتب شيء؛ والحد الافتراضي 100."""
    from core.exceptions import ValidationError
    from services import catalog_service

    assert MAX_FAVORITES == 100
    monkeypatch.setattr(catalog_service, "MAX_FAVORITES", 0)
    with pytest.raises(ValidationError) as exc:
        await services.catalog.add_favorite(user, mock_service.id)
    assert "للحد الأقصى" in exc.value.user_message
    assert await services.repos.favorites.count_for_user(user.id) == 0
```

---

## `tests/integration/test_phase13_admin_catalog.py`

```python
"""
استيراد دفعة، بطاقة الأدمن (الربط داخلي↔مزود↔Provider ID)، تعديل حقول العرض، قواعد الروابط في الطلب،
وإدخال الهامش/الصرف (المرحلة 13 — بنود 8 و9 و10 و11).
"""

from __future__ import annotations

import pytest

from core.exceptions import InvalidLinkError, ValidationError
from handlers.admin import catalog as admin_catalog
from handlers.admin import providers as admin_providers
from keyboards.callback_data import NS_ADM_CAT, pack
from tests.integration.test_user_interface import bot, context, load_user, press, write  # noqa: F401,F811
from utils.validators import parse_margin_percent

pytestmark = pytest.mark.asyncio


async def _start_import(bot, context, admin, provider, query):  # noqa: F811
    await press(bot, context, admin_providers.start_import, pack("pv", "imp", provider.id), admin.telegram_id)
    return await write(bot, context, admin_providers.receive_import_query, query, admin.telegram_id)


async def _finish_import(bot, context, admin, margin="40"):  # noqa: F811
    await press(bot, context, admin_providers.import_continue, pack("pv", "go"), admin.telegram_id)
    category_button = next(b for b in bot.last.buttons if b.startswith("pv:cat:"))
    await press(bot, context, admin_providers.pick_import_category, category_button, admin.telegram_id)
    await write(bot, context, admin_providers.receive_margin, margin, admin.telegram_id)
    return await press(bot, context, admin_providers.confirm_import, pack("flow", "confirm"), admin.telegram_id)


# ============================ استيراد دفعة (9) ============================ #


async def test_batch_import_by_ids_creates_all_with_correct_mapping(bot, context, admin, mock_provider, mock_client, repos) -> None:  # noqa: F811
    """عدة أرقام مزود ⇒ تُحدَّد تلقائياً وتُستورد معاً، وكل خدمة تحمل رقمها لدى المزود الصحيح."""
    await load_user(bot, context, admin)
    state = await _start_import(bot, context, admin, mock_provider, "555 556")
    assert state == admin_providers.PICK_ITEM
    assert "المحدد: <b>2</b>" in bot.last.text

    await _finish_import(bot, context, admin, margin="40")
    report = " ".join(m.text or "" for m in bot.sent)
    assert "أُنشئت: <b>2</b>" in report

    by_psid = {s.provider_service_id: s for s in await repos.services.list_by_provider(mock_provider.id, limit=50, offset=0)}
    assert set(by_psid) == {"555", "556"}
    followers, likes = by_psid["555"], by_psid["556"]
    assert "Followers" in followers.name and "Likes" in likes.name
    assert followers.provider_id == likes.provider_id == mock_provider.id
    assert followers.price_per_1000_units == (followers.provider_price_per_1000_units * 140 + 50) // 100
    # التقرير يربط الرقم الداخلي برقم المزود
    assert f"<code>{followers.id}</code> ⇐ مزود <code>555</code>" in report
    assert f"<code>{likes.id}</code> ⇐ مزود <code>556</code>" in report
    # قاعدة الرابط استُنتجت للحساب والمنشور
    assert followers.link_rule == "instagram_profile" and likes.link_rule == "instagram_post"


async def test_batch_import_multi_select_with_toggle_and_skips_duplicates(bot, context, admin, mock_provider, mock_service, mock_client, repos) -> None:  # noqa: F811
    """اختيار متعدد بالأزرار: المكررة (555 موجودة) تُبلَّغ ولا تُنشأ، والجديدة تُنشأ."""
    await load_user(bot, context, admin)
    await _start_import(bot, context, admin, mock_provider, "*")
    assert "المحدد: <b>0</b>" in bot.last.text
    for index in (0, 1):
        await press(bot, context, admin_providers.pick_import_item, pack("pv", "pick", index), admin.telegram_id)
    assert "المحدد: <b>2</b>" in bot.last.text
    await press(bot, context, admin_providers.pick_import_item, pack("pv", "pick", 1), admin.telegram_id)  # إلغاء الثانية
    await press(bot, context, admin_providers.pick_import_item, pack("pv", "pick", 1), admin.telegram_id)  # وإعادتها
    await _finish_import(bot, context, admin)
    report = " ".join(m.text or "" for m in bot.sent)
    assert "أُنشئت: <b>1</b>" in report and "مكررة: <b>1</b>" in report
    assert len(await repos.services.list_by_provider(mock_provider.id, limit=50, offset=0)) == 2


async def test_batch_import_requires_selection_and_reports_missing_ids(bot, context, admin, mock_provider, mock_client) -> None:  # noqa: F811
    """«التالي» بلا تحديد يُرفض بتنبيه؛ وأرقام غير موجودة تُعرض بوضوح."""
    await load_user(bot, context, admin)
    await _start_import(bot, context, admin, mock_provider, "*")
    state = await press(bot, context, admin_providers.import_continue, pack("pv", "go"), admin.telegram_id)
    assert state == admin_providers.PICK_ITEM
    assert "حدّد خدمة واحدة" in bot.answers[-1]["text"]

    await _start_import(bot, context, admin, mock_provider, "555 99999")
    assert "99999" in bot.last.text and "غير موجودة" in bot.last.text
    assert "المحدد: <b>1</b>" in bot.last.text


async def test_batch_import_select_all_and_clear(bot, context, admin, mock_provider, mock_client) -> None:  # noqa: F811
    """تحديد الكل ثم مسح التحديد."""
    await load_user(bot, context, admin)
    await _start_import(bot, context, admin, mock_provider, "Instagram")
    await press(bot, context, admin_providers.import_results_nav, pack("pv", "all"), admin.telegram_id)
    assert "المحدد: <b>2</b>" in bot.last.text
    await press(bot, context, admin_providers.import_results_nav, pack("pv", "none"), admin.telegram_id)
    assert "المحدد: <b>0</b>" in bot.last.text


async def test_batch_import_service_layer_isolates_failures(admin, mock_provider, mock_client, services, repos) -> None:  # noqa: F811
    """عنصر معيب لا يُسقط الباقي؛ وتكرار الرقم داخل الدفعة يُتجاهل."""
    from dataclasses import replace

    items = await mock_client.get_services()
    bad = replace(items[1], provider_service_id="777", service_type="package")
    category = (await repos.categories.list_all())[0]
    report = await services.catalog.import_provider_services(
        admin, provider_id=mock_provider.id, items=[items[0], items[0], bad], category_id=category.id, margin_percent=10
    )
    assert [o.status for o in report.outcomes] == ["created", "failed"]
    assert report.failed[0].item.provider_service_id == "777"
    with pytest.raises(ValidationError):
        await services.catalog.import_provider_services(
            admin, provider_id=mock_provider.id, items=[], category_id=category.id, margin_percent=10
        )


async def test_parse_provider_ids() -> None:
    """أرقام بفواصل/مسافات/سطور/أرقام عربية؛ نص مختلط ⇒ ليس وضع أرقام."""
    assert admin_providers.parse_provider_ids("101 205,330\n١٠١") == ["101", "205", "330"]
    assert admin_providers.parse_provider_ids("instagram 101") == []
    assert admin_providers.parse_provider_ids("") == []


# ========================= الهامش وسعر الصرف (11) ========================= #


@pytest.mark.parametrize(("text", "expected"), [("40", 40), ("٤٠", 40), (" 0 ", 0), ("1000", 1000)])
async def test_margin_accepts_plain_numbers(text: str, expected: int) -> None:
    """الرقم وحده (40) مقبول، بما فيه الأرقام العربية."""
    assert parse_margin_percent(text) == expected


@pytest.mark.parametrize(
    ("text", "fragment"),
    [("40%", "بلا علامة %"), ("-5", "سالباً"), ("12.5", "بلا كسور"), ("abc", "بلا حروف"), ("1001", "بين 0 و1000"), ("", "رقم")],
)
async def test_margin_rejections_are_explicit(text: str, fragment: str) -> None:
    """كل حالة رفض لها رسالة واضحة فيها مثال."""
    with pytest.raises(ValidationError) as exc:
        parse_margin_percent(text)
    assert fragment in exc.value.user_message
    assert "40" in exc.value.user_message


async def test_margin_message_in_flow_has_example(bot, context, admin, mock_provider, mock_client) -> None:  # noqa: F811
    """داخل المحادثة: «40%» تُرفض وتبقى المحادثة بانتظار رقم صحيح."""
    await load_user(bot, context, admin)
    await _start_import(bot, context, admin, mock_provider, "555")
    await press(bot, context, admin_providers.import_continue, pack("pv", "go"), admin.telegram_id)
    category_button = next(b for b in bot.last.buttons if b.startswith("pv:cat:"))
    await press(bot, context, admin_providers.pick_import_category, category_button, admin.telegram_id)
    assert "بلا علامة %" in bot.last.text and "<code>40</code>" in bot.last.text
    await write(bot, context, admin_providers.receive_margin, "40%", admin.telegram_id)
    assert "بلا علامة %" in bot.last.text and bot.last.text.startswith("❌")


async def test_exchange_rate_input_messages(services) -> None:
    """سعر الصرف: 530 مقبول مع الرمز؛ بدون رمز/بحروف/بـ% يُرفض برسالة واضحة."""
    assert services.providers.parse_currency_spec("USD 530") == ("USD", "530")
    assert services.providers.parse_currency_spec("USD ٥٣٠") == ("USD", "530")
    for text, fragment in (("530", "رمز العملة قبل"), ("USD 530%", "بلا علامة %"), ("USD abc", "بلا حروف"), ("USD -5", "أكبر من صفر")):
        with pytest.raises(ValidationError) as exc:
            services.providers.parse_currency_spec(text)
        assert fragment in exc.value.user_message, text


async def test_usd_rate_setting_accepts_530_and_rejects_percent(services) -> None:
    """إعداد usd_rate: «530» يُقبل، و«530%» و«530$» يُرفضان."""
    await services.settings.set("usd_rate", "530", admin_id=None)
    assert str(await services.settings.usd_rate()) == "530"
    for bad in ("530%", "530$", "-1", "0"):
        with pytest.raises(ValidationError):
            await services.settings.set("usd_rate", bad, admin_id=None)


# ===================== بطاقة الأدمن وتعديل العرض (5/8) ===================== #


async def test_admin_card_shows_three_way_link_and_unset_fields(bot, context, admin, mock_service) -> None:  # noqa: F811
    """البطاقة: رقم الخدمة الداخلي ثم المزود ثم رقمها لديه، والدولار، و«غير محددة»."""
    await load_user(bot, context, admin)
    await press(bot, context, admin_catalog.service_card_screen, pack(NS_ADM_CAT, "svc", mock_service.id), admin.telegram_id)
    text = bot.last.text
    assert f"#{mock_service.id}" in text
    assert "MockProvider" in text and f"<code>#{mock_service.provider_id}</code>" in text
    assert "رقمها لدى المزود: <code>555</code>" in text
    assert "$" in text and text.count("غير محددة") == 3
    assert "بلا قيد" in text
    assert pack(NS_ADM_CAT, "edit", mock_service.id) in bot.last.buttons


async def test_admin_service_list_buttons_show_internal_id(bot, context, admin, mock_service) -> None:  # noqa: F811
    """قائمة خدمات التصنيف للأدمن تُظهر الرقم الداخلي."""
    await load_user(bot, context, admin)
    await press(bot, context, admin_catalog.category_services_screen, pack(NS_ADM_CAT, "cat", mock_service.category_id, 1), admin.telegram_id)
    assert any(f"#{mock_service.id} " in label for label in bot.last.labels)


async def test_edit_display_fields_and_rule_via_conversation(bot, context, admin, mock_service, repos) -> None:  # noqa: F811
    """تعديل السرعة نصاً، ثم مسحها بـ«-»، ثم ضبط قاعدة الرابط من القائمة."""
    await load_user(bot, context, admin)
    sid = mock_service.id
    await press(bot, context, admin_catalog.start_edit_display, pack(NS_ADM_CAT, "edit", sid), admin.telegram_id)
    state = await press(bot, context, admin_catalog.pick_edit_field, pack(NS_ADM_CAT, "fld", "speed"), admin.telegram_id)
    assert state == admin_catalog.EDIT_ASK_VALUE
    await write(bot, context, admin_catalog.receive_edit_value, "1000 في الساعة", admin.telegram_id)
    assert (await repos.services.get(sid)).speed_text == "1000 في الساعة"
    assert "1000 في الساعة" in bot.last.text

    await press(bot, context, admin_catalog.start_edit_display, pack(NS_ADM_CAT, "edit", sid), admin.telegram_id)
    await press(bot, context, admin_catalog.pick_edit_field, pack(NS_ADM_CAT, "fld", "speed"), admin.telegram_id)
    await write(bot, context, admin_catalog.receive_edit_value, "-", admin.telegram_id)
    assert (await repos.services.get(sid)).speed_text is None

    await press(bot, context, admin_catalog.start_edit_display, pack(NS_ADM_CAT, "edit", sid), admin.telegram_id)
    state = await press(bot, context, admin_catalog.pick_edit_field, pack(NS_ADM_CAT, "fld", "rule"), admin.telegram_id)
    assert state == admin_catalog.EDIT_PICK_RULE
    await press(bot, context, admin_catalog.pick_edit_rule, pack(NS_ADM_CAT, "rul", 1), admin.telegram_id)  # أول قاعدة
    assert (await repos.services.get(sid)).link_rule == "instagram_profile"
    assert "حساب انستغرام" in bot.last.text


async def test_edit_display_is_audited_and_permission_checked(admin, user, mock_service, services, repos) -> None:  # noqa: F811
    """كل تعديل يُسجَّل بقيمتي قبل/بعد؛ ومستخدم عادي مرفوض؛ وحقل غير مسموح مرفوض."""
    from core.exceptions import PermissionDeniedError

    await services.catalog.admin_set_display_field(admin, mock_service.id, "quality_text", "عالية")
    count = await services.db.fetchval(
        "SELECT COUNT(*) FROM audit_logs WHERE action='services.update' AND target_id=?", (str(mock_service.id),)
    )
    assert count == 1
    with pytest.raises(PermissionDeniedError):
        await services.catalog.admin_set_display_field(user, mock_service.id, "quality_text", "x")
    with pytest.raises(ValidationError):
        await services.catalog.admin_set_display_field(admin, mock_service.id, "price_per_1000_units", "1")
    with pytest.raises(ValidationError):
        await services.catalog.admin_set_display_field(admin, mock_service.id, "link_rule", "no_such_rule")


# ===================== الرابط في مسار الطلب (10) ===================== #


async def test_order_rejects_wrong_link_before_any_charge(user, mock_service, services, repos) -> None:  # noqa: F811
    """رابط منشور لخدمة «حساب» يُرفض قبل إنشاء الطلب والخصم؛ والصحيح يمر."""
    from core.money import to_units
    from decimal import Decimal

    async with services.db.transaction() as tx:
        await tx.execute("UPDATE services SET link_rule='instagram_profile' WHERE id=?", (mock_service.id,))
        await tx.execute("UPDATE users SET balance_units=? WHERE id=?", (to_units(Decimal("1000")), user.id))
    fresh = await services.users.get(user.id)
    before = fresh.balance_units

    for bad in ("https://instagram.com/p/AbCdEf123/", "https://tiktok.com/@someone", "https://example.com/x"):
        with pytest.raises(InvalidLinkError):
            await services.orders.create_order(fresh, service_id=mock_service.id, link=bad, quantity=1000)
    assert (await services.users.get(user.id)).balance_units == before
    assert await services.db.fetchval("SELECT COUNT(*) FROM orders") == 0

    order = await services.orders.create_order(
        fresh, service_id=mock_service.id, link="https://instagram.com/some.user", quantity=1000
    )
    assert order.id and (await services.users.get(user.id)).balance_units < before


async def test_order_flow_prompt_and_rejection_show_example(bot, context, user, mock_service, services) -> None:  # noqa: F811
    """رسالة طلب الرابط تعرض مثال القاعدة، وإدخال رابط خاطئ يعيد السؤال بمثال صحيح."""
    from handlers.user import order_flow

    async with services.db.transaction() as tx:
        await tx.execute("UPDATE services SET link_rule='instagram_post' WHERE id=?", (mock_service.id,))
    await load_user(bot, context, user)
    await press(bot, context, order_flow.start_order, pack("new", "start", mock_service.id), user.telegram_id)
    assert "https://instagram.com/p/AbCdEf123/" in bot.last.text and "منشور/ريلز انستغرام" in bot.last.text
    state = await write(bot, context, order_flow.receive_link, "https://instagram.com/username", user.telegram_id)
    assert state is None  # @guarded يعرض الخطأ ويُبقي المحادثة في حالتها (الانتظار لرابط)
    assert "❌" in bot.last.text and "https://instagram.com/p/AbCdEf123/" in bot.last.text
    state = await write(bot, context, order_flow.receive_link, "https://instagram.com/p/AbCdEf123/", user.telegram_id)
    assert state == order_flow.ASK_QUANTITY
```

---

## `tests/unit/test_link_rules.py`

```python
"""قواعد الروابط حسب المنصة والنوع (المرحلة 13 — بند 10): روابط صحيحة وخاطئة لكل منصة."""

from __future__ import annotations

import pytest

from core.exceptions import InvalidLinkError
from utils.link_rules import LINK_RULES, check_link_rule, detect, detect_platform, infer_rule, rule_label
from utils.validators import validate_link

VALID = [
    ("instagram_profile", "https://instagram.com/username"),
    ("instagram_profile", "https://www.instagram.com/user.name_1/"),
    ("instagram_profile", "instagram.com/username?igsh=abc"),
    ("instagram_post", "https://www.instagram.com/p/AbCdEf123/"),
    ("instagram_post", "https://instagram.com/reel/AbCdEf123/?igsh=x"),
    ("instagram_post", "https://instagram.com/username/p/AbCdEf123/"),
    ("tiktok_profile", "https://www.tiktok.com/@some.user"),
    ("tiktok_video", "https://www.tiktok.com/@some.user/video/7234567890123456789"),
    ("tiktok_video", "https://vm.tiktok.com/ZMabc123/"),
    ("youtube_channel", "https://youtube.com/@channel"),
    ("youtube_channel", "https://www.youtube.com/channel/UCabcdefghijklmnop"),
    ("youtube_video", "https://www.youtube.com/watch?v=AbCdEfGhIjK&t=5"),
    ("youtube_video", "https://youtu.be/AbCdEfGhIjK"),
    ("youtube_video", "https://youtube.com/shorts/AbCdEfGhIjK"),
    ("telegram_channel", "https://t.me/channelname"),
    ("telegram_channel", "https://t.me/+AbCdEfGh123"),
    ("telegram_post", "https://t.me/channelname/123"),
    ("telegram_post", "https://t.me/c/1234567890/55"),
    ("facebook_page", "https://www.facebook.com/pagename"),
    ("facebook_page", "https://facebook.com/profile.php?id=1000123"),
    ("facebook_post", "https://facebook.com/pagename/posts/123456789"),
    ("facebook_post", "https://fb.watch/abcDEF/"),
    ("x_profile", "https://x.com/username"),
    ("x_profile", "https://twitter.com/user_1"),
    ("x_post", "https://x.com/username/status/1234567890"),
]

INVALID = [
    # منصة مختلفة
    ("instagram_profile", "https://tiktok.com/@username"),
    ("instagram_post", "https://youtube.com/watch?v=AbCdEfGhIjK"),
    ("tiktok_video", "https://instagram.com/p/AbCdEf123/"),
    ("youtube_video", "https://t.me/channelname/12"),
    ("x_post", "https://facebook.com/pagename/posts/123456789"),
    # رابط عام لا يخص منصة
    ("instagram_profile", "https://example.com/username"),
    ("telegram_channel", "https://google.com"),
    # منصة صحيحة ونوع خاطئ
    ("instagram_profile", "https://instagram.com/p/AbCdEf123/"),
    ("instagram_post", "https://instagram.com/username"),
    ("tiktok_profile", "https://tiktok.com/@user/video/123"),
    ("tiktok_video", "https://tiktok.com/@user"),
    ("youtube_channel", "https://youtube.com/watch?v=AbCdEfGhIjK"),
    ("youtube_video", "https://youtube.com/@channel"),
    ("telegram_channel", "https://t.me/channelname/123"),
    ("telegram_post", "https://t.me/channelname"),
    ("x_profile", "https://x.com/user/status/123"),
    ("x_post", "https://x.com/user"),
    # مشوّه
    ("instagram_profile", "https://instagram.com/"),
    ("instagram_profile", "https://instagram.com/explore/"),
    ("instagram_post", "https://instagram.com/p/"),
    ("youtube_video", "https://youtube.com/watch"),
    ("telegram_channel", "https://t.me/"),
    ("x_post", "https://x.com/user/status/notanumber"),
]


@pytest.mark.parametrize(("rule", "link"), VALID)
def test_valid_links_pass(rule: str, link: str) -> None:
    """الروابط الصحيحة تُقبل لقاعدتها."""
    check_link_rule(link, rule)
    assert validate_link(link, rule=rule)


@pytest.mark.parametrize(("rule", "link"), INVALID)
def test_invalid_links_are_rejected_with_example(rule: str, link: str) -> None:
    """الخاطئة تُرفض برسالة عربية فيها المثال الصحيح."""
    with pytest.raises(InvalidLinkError) as exc:
        validate_link(link, rule=rule)
    message = exc.value.user_message
    assert message.startswith("❌")
    assert LINK_RULES[rule].example in message


def test_messages_distinguish_platform_from_kind() -> None:
    """رسالة المنصة المختلفة غير رسالة النوع الخاطئ."""
    with pytest.raises(InvalidLinkError) as other:
        check_link_rule("https://tiktok.com/@a", "instagram_profile")
    assert "تيك توك" in other.value.user_message and "والخدمة خاصة بـانستغرام" in other.value.user_message
    with pytest.raises(InvalidLinkError) as kind:
        check_link_rule("https://instagram.com/p/AbC123/", "instagram_profile")
    assert "منشور/فيديو" in kind.value.user_message and "حساب/قناة" in kind.value.user_message


def test_no_rule_or_unknown_rule_changes_nothing() -> None:
    """بلا قاعدة (أو مفتاح غير معروف) يبقى التحقق العام فقط."""
    assert validate_link("https://example.com/x") == "https://example.com/x"
    assert validate_link("https://example.com/x", rule="nope") == "https://example.com/x"
    assert rule_label(None).startswith("بلا قيد")
    assert rule_label("instagram_profile") == "حساب انستغرام"


def test_general_validation_still_runs_before_rule() -> None:
    """الفراغات/البروتوكول يُرفضان قبل القاعدة كما كان."""
    with pytest.raises(InvalidLinkError):
        validate_link("https://instagram.com/user name", rule="instagram_profile")
    with pytest.raises(InvalidLinkError):
        validate_link("ftp://instagram.com/user", rule="instagram_profile")


def test_detect() -> None:
    """تصنيف الرابط (منصة، نوع)."""
    assert detect("https://instagram.com/p/x1/") == ("instagram", "post")
    assert detect("https://m.facebook.com/pagename") == ("facebook", "profile")
    assert detect("https://example.com") is None
    assert detect_platform("https://evil-instagram.com/user") is None
    assert detect_platform("https://notinstagram.com/user") is None


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("متابعين انستغرام عرب", "instagram_profile"),
        ("Instagram Followers [Real]", "instagram_profile"),
        ("لايكات انستغرام", "instagram_post"),
        ("TikTok Views Fast", "tiktok_video"),
        ("مشاهدات يوتيوب", "youtube_video"),
        ("أعضاء قناة تيليجرام", "telegram_channel"),
        ("خدمة عامة", None),
        ("متابعين انستغرام وتيك توك", None),
        ("Instagram Followers + Likes", None),
    ],
)
def test_infer_rule_is_conservative(name: str, expected: str | None) -> None:
    """الاستنتاج يحدد القاعدة فقط عند وضوح المنصة والنوع."""
    assert infer_rule(name) == expected
```
