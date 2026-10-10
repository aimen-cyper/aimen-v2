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


def parse_usd_rate(raw: str | None) -> Decimal | None:
    """
    تحويل نص إعداد `usd_rate` إلى Decimal موجب.

    القيمة الفارغة أو الفاسدة أو غير الموجبة ⇒ `None` (يُخفى مقابل الدولار ويُسجَّل تحذير عند القراءة).
    لا يوجد سعر صرف احتياطي في الكود: عرض سعر وهمي أسوأ من عدم عرض الدولار (بند 5).
    """
    try:
        value = Decimal(str(raw or "").strip().replace(",", ""))
    except InvalidOperation:
        return None
    if not value.is_finite() or value <= 0:
        return None
    return value


def usd_amount(units: int, usd_rate: Decimal) -> Decimal:
    """
    المقابل بالدولار لمبلغ بعملة النظام (للعرض فقط، لا يدخل في أي حساب مالي).

    المخرجات: Decimal بدقة 4 خانات (يُقرَّب عند العرض).
    """
    return (from_units(units) / usd_rate).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def format_usd(units: int, usd_rate: Decimal | None) -> str:
    """
    تنسيق المقابل بالدولار: خانتان عادةً، وأربع للمبالغ الصغيرة جداً حتى لا يظهر السعر الحقيقي صفراً.

    أمثلة (سعر 530): 530 ريال ⇒ `$1.00` · 10 ريال ⇒ `$0.0189`. بلا سعر صرف مضبوط ⇒ نص فارغ.
    """
    if usd_rate is None:
        return ""
    amount = usd_amount(units, usd_rate)
    if amount != 0 and abs(amount) < Decimal("0.01"):
        return f"${amount:,.4f}"
    return f"${amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"
