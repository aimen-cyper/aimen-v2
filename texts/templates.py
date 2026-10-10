"""
قوالب نصوص الإشعارات العربية.

كل نص يصل إلى المستخدم أو الأدمن مكتوب هنا في مكان واحد — لا نصوص متناثرة داخل الخدمات.
كل دالة تُرجع زوجاً: (العنوان، النص) جاهزاً للإرسال عبر تيليجرام.

المرحلة 8 — القوالب القابلة للتحرير:
    رسائل العملاء (الطلبات/المدفوعات/الرصيد/الدعم/الحساب) صارت تمرّ عبر `render`،
    فتُستبدل صياغتها بما حفظه الأدمن في جدول `notification_templates` إن وُجد،
    وإلا يُستعمل النص الافتراضي المكتوب هنا حرفياً.

    • الافتراضي يبقى في الكود دائماً ⇒ زر «استعادة الافتراضي» يعمل بلا نسخة احتياطية.
    • القيم تُمرَّر جاهزة للعرض (مبالغ منسّقة، أعداد بفواصل) حتى يبقى القالب نصاً بحتاً
      بلا أي صياغة برمجية داخله (`{amount}` لا `{amount:,.2f}`).
    • تنبيهات الأدمن الداخلية (أخطاء المزودين، المهام المتعثرة…) غير قابلة للتحرير
      عمداً: هي أدوات تشخيص لا رسائل تسويقية، وتغيير صياغتها يُربك التشخيص.
"""

from __future__ import annotations

from dataclasses import dataclass
from string import Formatter

from core.money import format_units
from core.order_state import label_ar as order_label
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: الرمز الافتراضي للعملة عند عدم تمريره (تُقرأ القيمة الحقيقية من الإعدادات)
DEFAULT_SYMBOL = ""

#: أقصى طول مسموح لعنوان القالب ونصه (حماية من رسائل تتجاوز حد تيليجرام)
MAX_TEMPLATE_TITLE = 120
MAX_TEMPLATE_BODY = 1500


def money(units: int, symbol: str = DEFAULT_SYMBOL, decimals: int = 2) -> str:
    """تنسيق مبلغ للعرض داخل نصوص الإشعارات."""
    return format_units(units, symbol=symbol, decimals=decimals)


def _count(value: int) -> str:
    """تنسيق عدد صحيح بفواصل الآلاف (يُحسب هنا لا داخل القالب)."""
    return f"{value:,}"


# ======================================================================= #
#                     كتالوج القوالب القابلة للتحرير                      #
# ======================================================================= #


@dataclass(frozen=True, slots=True)
class TemplateDef:
    """
    تعريف قالب واحد: رمزه، مجموعته، نصه الافتراضي، ومتغيراته المسموحة.

    الحقول:
        code      : رمز الحدث (مفتاح الصف في جدول notification_templates).
        name_ar   : الاسم كما يظهر في لوحة التحكم.
        group     : مجموعة العرض (orders / payments / wallet / tickets / account).
        title     : العنوان الافتراضي.
        body      : النص الافتراضي بمتغيراته.
        variables : أسماء المتغيرات المسموح استخدامها في هذا القالب فقط.
        sample    : قيم تجريبية تُستخدم في زر «👁 معاينة» (لا تُرسل لأحد).
    """

    code: str
    name_ar: str
    group: str
    title: str
    body: str
    variables: tuple[str, ...]
    sample: dict[str, str]


#: أسماء عربية لمجموعات القوالب في شاشة الأدمن
TEMPLATE_GROUPS: dict[str, str] = {
    "orders": "📦 الطلبات",
    "payments": "💳 الشحن",
    "wallet": "👛 الرصيد",
    "tickets": "🎫 الدعم",
    "account": "👤 الحساب",
}

TEMPLATES: tuple[TemplateDef, ...] = (
    # ------------------------------ الطلبات ------------------------------ #
    TemplateDef(
        code="order_created",
        name_ar="إنشاء الطلب",
        group="orders",
        title="🧾 تم استلام طلبك",
        body=(
            "✅ تم إنشاء الطلب {code} بنجاح.\n\n"
            "🛒 الخدمة: {service_name}\n"
            "🔢 الكمية: {quantity}\n"
            "💵 المبلغ المخصوم: {amount}\n\n"
            "⏳ سيبدأ التنفيذ خلال دقائق، وسنعلمك بكل تحديث 🔔"
        ),
        variables=("code", "service_name", "quantity", "amount"),
        sample={
            "code": "ORD-10231",
            "service_name": "متابعون انستغرام",
            "quantity": "1,000",
            "amount": "25.00",
        },
    ),
    TemplateDef(
        code="order_submitted",
        name_ar="إرسال الطلب للمزود",
        group="orders",
        title="📤 تم إرسال طلبك للتنفيذ",
        body="📤 الطلب {code} ({service_name}) أصبح لدى المزود وبدأ دوره في التنفيذ ⚡",
        variables=("code", "service_name"),
        sample={"code": "ORD-10231", "service_name": "متابعون انستغرام"},
    ),
    TemplateDef(
        code="order_in_progress",
        name_ar="بدء التنفيذ",
        group="orders",
        title="🔄 طلبك قيد التنفيذ",
        body="🔄 بدأ تنفيذ الطلب {code} الآن — نعمل على إنجازه ⚡",
        variables=("code",),
        sample={"code": "ORD-10231"},
    ),
    TemplateDef(
        code="order_completed",
        name_ar="اكتمال الطلب",
        group="orders",
        title="🎉 اكتمل طلبك",
        body=(
            "🎉 تم تنفيذ الطلب {code} بالكامل.\n\n"
            "🛒 الخدمة: {service_name}\n"
            "🔢 الكمية: {quantity}\n\n"
            "🌟 شكراً لثقتك — يسعدنا خدمتك دائماً 💙"
        ),
        variables=("code", "service_name", "quantity"),
        sample={
            "code": "ORD-10231",
            "service_name": "متابعون انستغرام",
            "quantity": "1,000",
        },
    ),
    TemplateDef(
        code="order_partial",
        name_ar="تنفيذ جزئي",
        group="orders",
        title="🟡 تم تنفيذ طلبك جزئياً",
        body=(
            "⚠️ الطلب {code} نُفِّذ جزئياً.\n\n"
            "✅ المنفَّذ: {delivered} من {quantity}\n"
            "💰 أُعيد إلى رصيدك: {refund}\n\n"
            "👛 المبلغ المسترجع متاح في محفظتك الآن."
        ),
        variables=("code", "delivered", "quantity", "refund"),
        sample={
            "code": "ORD-10231",
            "delivered": "600",
            "quantity": "1,000",
            "refund": "10.00",
        },
    ),
    TemplateDef(
        code="order_failed",
        name_ar="فشل الطلب",
        group="orders",
        title="❌ تعذّر تنفيذ طلبك",
        body=(
            "😔 الطلب {code} لم يُنفَّذ.\n\n"
            "📝 السبب: {reason}\n"
            "💰 أُعيد كامل المبلغ إلى رصيدك: {refund}\n\n"
            "🔄 يمكنك المحاولة مرة أخرى، أو تواصل مع 🎫 الدعم."
        ),
        variables=("code", "reason", "refund"),
        sample={"code": "ORD-10231", "reason": "الرابط غير صحيح", "refund": "25.00"},
    ),
    TemplateDef(
        code="order_canceled",
        name_ar="إلغاء الطلب",
        group="orders",
        title="🚫 تم إلغاء طلبك",
        body="🛑 أُلغي الطلب {code}.\n💰 أُعيد المبلغ إلى رصيدك: {refund}",
        variables=("code", "refund"),
        sample={"code": "ORD-10231", "refund": "25.00"},
    ),
    TemplateDef(
        code="order_refunded",
        name_ar="استرجاع مبلغ طلب",
        group="orders",
        title="💰 تم استرجاع مبلغ طلبك",
        body="↩️ أُضيف مبلغ {refund} إلى رصيدك بخصوص الطلب {code} 💰",
        variables=("code", "refund"),
        sample={"code": "ORD-10231", "refund": "25.00"},
    ),
    TemplateDef(
        code="order_status_changed",
        name_ar="تغيّر حالة الطلب",
        group="orders",
        title="ℹ️ تحديث على طلبك",
        body="📦 الطلب {code}\n📊 الحالة: {status}",
        variables=("code", "status"),
        sample={"code": "ORD-10231", "status": "قيد التنفيذ"},
    ),
    # ----------------------------- المدفوعات ----------------------------- #
    TemplateDef(
        code="payment_received",
        name_ar="استلام طلب الشحن",
        group="payments",
        title="📥 تم استلام طلب الشحن",
        body="📥 طلب الشحن #{payment_id} بمبلغ {amount} قيد المراجعة ⏳\n{fee_block}🔔 سنعلمك فور اعتماده.",
        variables=("payment_id", "amount", "fee_block"),
        sample={
            "payment_id": "42",
            "amount": "200.00",
            "fee_block": "🧾 رسوم الطريقة: 6.00\n💵 المتوقع إضافته: 194.00\n",
        },
    ),
    TemplateDef(
        code="payment_approved",
        name_ar="اعتماد الشحن",
        group="payments",
        title="✅ تم اعتماد شحن رصيدك",
        body=(
            "✅ اعتُمد طلب الشحن #{payment_id}.\n\n"
            "💵 المبلغ المضاف: {amount}\n"
            "👛 رصيدك الآن: {balance}\n\n"
            "🚀 يمكنك الآن الطلب من «🛍 الخدمات»!"
        ),
        variables=("payment_id", "amount", "balance"),
        sample={"payment_id": "42", "amount": "194.00", "balance": "219.00"},
    ),
    TemplateDef(
        code="payment_rejected",
        name_ar="رفض الشحن",
        group="payments",
        title="❌ تم رفض طلب الشحن",
        body=(
            "❌ رُفض طلب الشحن #{payment_id}.\n📝 السبب: {reason}\n\n"
            "🎫 إن كنت ترى أن هذا خطأ، تواصل مع الدعم."
        ),
        variables=("payment_id", "reason"),
        sample={"payment_id": "42", "reason": "رقم العملية غير صحيح"},
    ),
    TemplateDef(
        code="payment_expired",
        name_ar="انتهاء صلاحية الشحن",
        group="payments",
        title="⌛ انتهت صلاحية طلب الشحن",
        body="⌛ انتهت مهلة طلب الشحن #{payment_id} دون مراجعة.\n➕ يمكنك إنشاء طلب جديد.",
        variables=("payment_id",),
        sample={"payment_id": "42"},
    ),
    # ------------------------------- الرصيد ------------------------------ #
    TemplateDef(
        code="balance_credited",
        name_ar="إضافة رصيد يدوية",
        group="wallet",
        title="💰 تمت إضافة رصيد",
        body=(
            "🎁 أضافت الإدارة {amount} إلى رصيدك.\n"
            "📝 السبب: {reason}\n👛 رصيدك الآن: {balance}"
        ),
        variables=("amount", "reason", "balance"),
        sample={"amount": "50.00", "reason": "تعويض", "balance": "75.00"},
    ),
    TemplateDef(
        code="balance_debited",
        name_ar="خصم رصيد يدوي",
        group="wallet",
        title="➖ تم خصم رصيد",
        body=(
            "➖ خصمت الإدارة {amount} من رصيدك.\n"
            "📝 السبب: {reason}\n👛 رصيدك الآن: {balance}"
        ),
        variables=("amount", "reason", "balance"),
        sample={"amount": "50.00", "reason": "تصحيح شحن مكرر", "balance": "25.00"},
    ),
    # -------------------------------- الدعم ------------------------------ #
    TemplateDef(
        code="ticket_replied",
        name_ar="رد الدعم على التذكرة",
        group="tickets",
        title="💬 رد جديد من الدعم",
        body="💬 لديك رد على التذكرة #{ticket_id}:\n\n«{preview}»\n\n📂 افتح «🎫 الدعم ← تذاكري» لعرض المحادثة.",
        variables=("ticket_id", "preview"),
        sample={"ticket_id": "7", "preview": "تم تنفيذ طلبك، يرجى المراجعة"},
    ),
    TemplateDef(
        code="ticket_closed",
        name_ar="إغلاق التذكرة",
        group="tickets",
        title="✅ تم إغلاق تذكرتك",
        body="🔒 تم إغلاق التذكرة #{ticket_id}.{reason_block}\n\n🌹 شكراً لتواصلك معنا.",
        variables=("ticket_id", "reason_block"),
        sample={"ticket_id": "7", "reason_block": "\n📝 تمت معالجة الطلب"},
    ),
    # ------------------------------- الحساب ------------------------------ #
    TemplateDef(
        code="account_banned",
        name_ar="حظر الحساب",
        group="account",
        title="🚫 تم حظر حسابك",
        body="⛔ تم إيقاف حسابك عن استخدام البوت.\n📝 السبب: {reason}\n\n🎫 للاعتراض تواصل مع الإدارة.",
        variables=("reason",),
        sample={"reason": "مخالفة الشروط"},
    ),
    TemplateDef(
        code="account_unbanned",
        name_ar="رفع الحظر",
        group="account",
        title="✅ تم رفع الحظر",
        body="🎉 أصبح بإمكانك استخدام البوت مجدداً. نتمنى لك تجربة طيبة 🌹",
        variables=(),
        sample={},
    ),
)

#: فهرس سريع بالرمز
TEMPLATE_BY_CODE: dict[str, TemplateDef] = {item.code: item for item in TEMPLATES}


# ======================================================================= #
#                    طبقة التخصيص (ذاكرة + تحقق + عرض)                    #
# ======================================================================= #

#: القوالب المخصّصة المحمّلة من قاعدة البيانات: code -> (title, body)
#: تُملأ من `TemplateService.refresh_cache()` عند الإقلاع وبعد كل تعديل.
_overrides: dict[str, tuple[str, str]] = {}


def set_overrides(mapping: dict[str, tuple[str, str]]) -> None:
    """استبدال ذاكرة القوالب المخصّصة بالكامل (تُستدعى بعد أي تعديل أو عند الإقلاع)."""
    _overrides.clear()
    _overrides.update(mapping)


def clear_overrides() -> None:
    """إفراغ القوالب المخصّصة والعودة للنصوص الافتراضية (تُستخدم في الاختبارات أيضاً)."""
    _overrides.clear()


def active_overrides() -> dict[str, tuple[str, str]]:
    """نسخة من القوالب المخصّصة الفعّالة حالياً (للعرض والتشخيص)."""
    return dict(_overrides)


def placeholders_in(text: str) -> list[str]:
    """
    استخراج أسماء المتغيرات المكتوبة داخل نص قالب.

    الاسم الفارغ `{}` أو الرقمي `{0}` يُرجَع كما هو ليُرفض لاحقاً في التحقق،
    وأي محاولة وصول لخاصية أو فهرس (`{a.b}` / `{a[0]}`) تُرجَع كاملة لترفض كذلك.
    """
    found: list[str] = []
    for _literal, field_name, _spec, _conv in Formatter().parse(text):
        if field_name is None:
            continue
        found.append(field_name)
    return found


def invalid_placeholders(text: str, allowed: tuple[str, ...]) -> list[str]:
    """
    قائمة المتغيرات غير المسموحة في نص قالب (فارغة تعني أن النص صالح).

    لماذا التشدد؟ لأن `str.format` على نص يكتبه الأدمن سلاح ذو حدين:
    `{x.__class__}` يسرّب تفاصيل داخلية، و`{a:>999999}` يصنع رسالة ضخمة.
    لذلك نقبل أسماء المتغيرات المعلنة فقط، بلا نقطة ولا قوس ولا تنسيق.
    """
    bad: list[str] = []
    for _literal, field_name, spec, conv in Formatter().parse(text):
        if field_name is None:
            continue
        if field_name not in allowed or spec or conv:
            bad.append(field_name or "{}")
    return bad


def missing_placeholders(text: str, provided: dict[str, str]) -> list[str]:
    """المتغيرات المذكورة في النص ولا توجد لها قيمة (تمنع KeyError وقت الإرسال)."""
    return [name for name in placeholders_in(text) if name not in provided]


def render(template_code: str, /, **variables: object) -> tuple[str, str]:
    """
    بناء (العنوان، النص) لحدث قابل للتحرير.

    الترتيب: القالب المخصّص الفعّال ← ثم الافتراضي المدمج.
    أي خطأ في القالب المخصّص (متغير ناقص مثلاً) يُسجَّل في اللوق ويُستعمل
    الافتراضي بدلاً منه — رسالة العميل لا تضيع بسبب خطأ صياغة.

    اسم المعامل الأول موضعي فقط (`/`) لأن «code» نفسه أحد متغيرات القوالب.
    """
    definition = TEMPLATE_BY_CODE.get(template_code)
    if definition is None:  # رمز غير معروف = خطأ برمجي، نكشفه فوراً
        raise KeyError(f"قالب غير معرّف: {template_code}")

    values = {key: str(value) for key, value in variables.items()}
    custom = _overrides.get(template_code)
    if custom is not None:
        try:
            return (custom[0].format_map(values), custom[1].format_map(values))
        except (KeyError, IndexError, ValueError, AttributeError) as exc:
            logger.error(
                "فشل تطبيق القالب المخصّص «%s» (%s) — استُعمل النص الافتراضي",
                template_code, exc,
            )

    return (definition.title.format_map(values), definition.body.format_map(values))


# --------------------------------- الطلبات --------------------------------- #


def order_created(*, code: str, service_name: str, quantity: int, cost_units: int, symbol: str = "") -> tuple[str, str]:
    """إشعار إنشاء الطلب وخصم قيمته."""
    return render(
        "order_created",
        code=code,
        service_name=service_name,
        quantity=_count(quantity),
        amount=money(cost_units, symbol),
    )


def order_submitted(*, code: str, service_name: str) -> tuple[str, str]:
    """إشعار قبول المزود للطلب."""
    return render("order_submitted", code=code, service_name=service_name)


def order_in_progress(*, code: str) -> tuple[str, str]:
    """إشعار بدء التنفيذ الفعلي."""
    return render("order_in_progress", code=code)


def order_completed(*, code: str, service_name: str, quantity: int) -> tuple[str, str]:
    """إشعار اكتمال الطلب."""
    return render(
        "order_completed", code=code, service_name=service_name, quantity=_count(quantity)
    )


def order_partial(*, code: str, delivered: int, quantity: int, refund_units: int, symbol: str = "") -> tuple[str, str]:
    """إشعار التنفيذ الجزئي مع الاسترجاع."""
    return render(
        "order_partial",
        code=code,
        delivered=_count(delivered),
        quantity=_count(quantity),
        refund=money(refund_units, symbol),
    )


def order_failed(*, code: str, reason: str, refund_units: int, symbol: str = "") -> tuple[str, str]:
    """إشعار فشل الطلب مع الاسترجاع الكامل."""
    return render("order_failed", code=code, reason=reason, refund=money(refund_units, symbol))


def order_canceled(*, code: str, refund_units: int, symbol: str = "") -> tuple[str, str]:
    """إشعار إلغاء الطلب مع الاسترجاع."""
    return render("order_canceled", code=code, refund=money(refund_units, symbol))


def order_refunded(*, code: str, refund_units: int, symbol: str = "") -> tuple[str, str]:
    """إشعار إتمام الاسترجاع."""
    return render("order_refunded", code=code, refund=money(refund_units, symbol))


def order_status_changed(*, code: str, status: str) -> tuple[str, str]:
    """إشعار عام بتغيّر حالة الطلب (يُستخدم للحالات غير المذكورة أعلاه)."""
    return render("order_status_changed", code=code, status=order_label(status))


# -------------------------------- المدفوعات -------------------------------- #


def payment_received(
    *,
    payment_id: int,
    amount_units: int,
    symbol: str = "",
    fee_units: int = 0,
    net_units: int | None = None,
) -> tuple[str, str]:
    """
    إشعار استلام طلب الشحن (قيد المراجعة).

    عند وجود رسوم للطريقة يُذكر المبلغ الصافي صراحةً، حتى لا يُفاجأ
    المستخدم بفارق بين ما حوّله وما أُضيف لرصيده. سطور الرسوم تُبنى هنا
    وتُمرَّر للقالب كمتغير واحد `{fee_block}` يكون فارغاً عند انعدام الرسوم.
    """
    fee_block = ""
    if fee_units > 0:
        expected = amount_units - fee_units if net_units is None else net_units
        fee_block = (
            f"🧾 رسوم الطريقة: {money(fee_units, symbol)}\n"
            f"💵 المتوقع إضافته: {money(expected, symbol)}\n"
        )
    return render(
        "payment_received",
        payment_id=payment_id,
        amount=money(amount_units, symbol),
        fee_block=fee_block,
    )


def payment_approved(*, payment_id: int, credited_units: int, new_balance_units: int, symbol: str = "") -> tuple[str, str]:
    """إشعار اعتماد الشحن وإضافة الرصيد."""
    return render(
        "payment_approved",
        payment_id=payment_id,
        amount=money(credited_units, symbol),
        balance=money(new_balance_units, symbol),
    )


def payment_rejected(*, payment_id: int, reason: str) -> tuple[str, str]:
    """إشعار رفض طلب الشحن."""
    return render("payment_rejected", payment_id=payment_id, reason=reason)


def payment_expired(*, payment_id: int) -> tuple[str, str]:
    """إشعار انتهاء صلاحية طلب الشحن."""
    return render("payment_expired", payment_id=payment_id)


# --------------------------------- الرصيد ---------------------------------- #


def balance_credited(*, amount_units: int, new_balance_units: int, reason: str, symbol: str = "") -> tuple[str, str]:
    """إشعار إضافة رصيد يدوية من الإدارة."""
    return render(
        "balance_credited",
        amount=money(amount_units, symbol),
        reason=reason,
        balance=money(new_balance_units, symbol),
    )


def balance_debited(*, amount_units: int, new_balance_units: int, reason: str, symbol: str = "") -> tuple[str, str]:
    """إشعار خصم رصيد يدوي من الإدارة."""
    return render(
        "balance_debited",
        amount=money(amount_units, symbol),
        reason=reason,
        balance=money(new_balance_units, symbol),
    )


# ---------------------------------- الدعم ---------------------------------- #


def ticket_replied(*, ticket_id: int, preview: str) -> tuple[str, str]:
    """إشعار وصول رد من الدعم."""
    return render("ticket_replied", ticket_id=ticket_id, preview=preview)


def ticket_closed(*, ticket_id: int, reason: str) -> tuple[str, str]:
    """إشعار إغلاق التذكرة (سبب الإغلاق اختياري فيُمرَّر كمقطع جاهز)."""
    return render(
        "ticket_closed",
        ticket_id=ticket_id,
        reason_block=f"\n📝 {reason}" if reason else "",
    )


# -------------------------------- الحسابات --------------------------------- #


def account_banned(*, reason: str) -> tuple[str, str]:
    """إشعار حظر الحساب."""
    return render("account_banned", reason=reason)


def account_unbanned() -> tuple[str, str]:
    """إشعار رفع الحظر."""
    return render("account_unbanned")


# ---------------------------- تنبيهات الإدارة ------------------------------ #
# غير قابلة للتحرير من اللوحة عمداً: رسائل تشخيص داخلية، لا رسائل عملاء.


def admin_order_uncertain(*, code: str, order_id: int, error: str) -> tuple[str, str]:
    """تنبيه أدمن: نتيجة إرسال غير مؤكدة تحتاج قراراً بشرياً."""
    return (
        "❗ طلب بحالة غير مؤكدة",
        f"الطلب {code} (#{order_id}) انقطع أثناء الإرسال ولا نعرف هل وصل للمزود.\n"
        f"📝 التفاصيل: {error}\n\n"
        f"المطلوب: تحقق من لوحة المزود ثم اربط رقم الطلب أو أكّد الفشل ليُسترجع المبلغ.",
    )


def admin_order_failed(*, code: str, order_id: int, reason: str, refund_units: int, symbol: str = "") -> tuple[str, str]:
    """تنبيه أدمن: فشل طلب واسترجاع مبلغه."""
    return (
        "❌ فشل طلب واسترجاع تلقائي",
        f"الطلب {code} (#{order_id}) فشل.\n📝 السبب: {reason}\n"
        f"💰 المبلغ المسترجع: {money(refund_units, symbol)}",
    )


def admin_provider_disabled(*, provider_name: str, failures: int, minutes: int) -> tuple[str, str]:
    """تنبيه أدمن: تعطيل مؤقت لمزود بعد أخطاء متتالية."""
    return (
        "🔌 تعطيل مؤقت لمزود",
        f"المزود «{provider_name}» توقف مؤقتاً بعد {failures} أخطاء متتالية.\n"
        f"⏱ سيُعاد تفعيله تلقائياً بعد {minutes} دقيقة.",
    )


def admin_rate_change_margin(*, provider_name: str, count: int, sample: list[int]) -> tuple[str, str]:
    """تنبيه أدمن: تغيير سعر صرف مزود سيجعل خدمات بهامش سالب عند المزامنة التالية (تنبيه فقط، لا تغيير أسعار)."""
    ids = "، ".join(f"#{i}" for i in sample)
    return (
        "⚠️ هامش سالب متوقع بعد تغيير الصرف",
        f"بعد تغيير سعر صرف «{provider_name}» ستصير تكلفة {count} خدمة أعلى من سعر بيعها عند «🔄 مزامنة» التالية.\n"
        f"🔢 أمثلة: {ids}\n"
        "ℹ️ لم يتغير أي سعر تلقائياً، والطلبات القائمة محفوظة بسعرها وقت الإنشاء. راجع أسعار البيع أو الهامش.",
    )


def admin_provider_status_failing(*, provider_name: str, failures: int) -> tuple[str, str]:
    """تنبيه أدمن: استعلام حالة الطلبات لدى مزود يفشل بتكرار (لا يوقف الطلبات الجديدة ولا يغيّر حالة أي طلب)."""
    return (
        "🔌 تعذّر متابعة الطلبات عند مزود",
        f"استعلام حالة الطلبات لدى «{provider_name}» فشل {failures} مرات متتالية.\n"
        "ℹ️ هذا لا يعني فشل الطلبات ولا يوقف إنشاء الجديدة؛ تُعاد المحاولة تلقائياً بفاصل متدرج.\n"
        "🔎 افحص اتصال المزود من «🔌 المزودون».",
    )


def admin_provider_low_balance(*, provider_name: str, balance_units: int, symbol: str = "") -> tuple[str, str]:
    """تنبيه أدمن: رصيد المزود قارب على النفاد."""
    return (
        "⚠️ رصيد مزود منخفض",
        f"رصيد حسابنا لدى «{provider_name}» أصبح {money(balance_units, symbol)}.\n"
        f"اشحن الحساب قبل توقف الطلبات.",
    )


def admin_provider_currency_mismatch(*, provider_name: str, configured: str, reported: str) -> tuple[str, str]:
    """تنبيه أدمن: المزود يُبلِّغ برصيد بعملة تختلف عن المسجّلة (سعر الصرف قد يكون خاطئاً)."""
    return (
        "⚠️ عملة مزود مختلفة",
        f"المزود «{provider_name}» يُبلِّغ برصيده بعملة {reported} بينما المسجّل لدينا {configured}.\n"
        f"راجع «💱 العملة وسعر الصرف» في بطاقة المزود قبل أن تُحسب التكاليف بسعر خاطئ.",
    )


def admin_new_payment(*, payment_id: int, amount_units: int, user_label: str, symbol: str = "") -> tuple[str, str]:
    """تنبيه أدمن: طلب شحن جديد بانتظار المراجعة."""
    return (
        "📥 طلب شحن جديد",
        f"طلب شحن #{payment_id} من {user_label} بمبلغ {money(amount_units, symbol)} ينتظر المراجعة.",
    )


def admin_new_ticket(*, ticket_id: int, subject: str, user_label: str) -> tuple[str, str]:
    """تنبيه أدمن: تذكرة دعم جديدة."""
    return (
        "🎫 تذكرة دعم جديدة",
        f"التذكرة #{ticket_id} من {user_label}\n📌 الموضوع: {subject}",
    )


def admin_stuck_orders(*, count: int, hours: int) -> tuple[str, str]:
    """تنبيه أدمن: طلبات متوقفة بلا تقدم."""
    return (
        "⏰ طلبات متوقفة",
        f"يوجد {count} طلب لم يتقدم منذ أكثر من {hours} ساعة. راجعها في لوحة الطلبات.",
    )


# ----------------------- المرحلة 6: المهام الدورية ---------------------- #


def admin_job_failing(*, job_name: str, failures: int, error: str) -> tuple[str, str]:
    """تنبيه أدمن: مهمة دورية تفشل بشكل متكرر (مؤشر عطل صامت في النظام)."""
    return (
        "🛠 مهمة دورية متعثرة",
        f"المهمة «{job_name}» فشلت {failures} مرات متتالية.\n"
        f"آخر خطأ: {error}\n"
        "راجع «📋 السجلات ← الأخطاء» في لوحة التحكم.",
    )


def admin_provider_recovered(*, provider_name: str, failures: int) -> tuple[str, str]:
    """تنبيه أدمن: مزود كان متعثراً وعاد يستجيب."""
    return (
        "✅ تعافى مزود",
        f"المزود «{provider_name}» عاد يستجيب بعد {failures} أخطاء متتالية، "
        "وأُعيد تفعيل الإرسال إليه.",
    )


def admin_daily_digest(
    *,
    orders_today: int,
    revenue_today_units: int,
    deposits_today_units: int,
    pending_payments: int,
    attention_orders: int,
    open_tickets: int,
    new_users: int,
    errors_24h: int,
    symbol: str = "",
    refunds_today_units: int = 0,
    completed_today: int = 0,
    failed_today: int = 0,
) -> tuple[str, str]:
    """
    الملخص اليومي للأدمن: أرقام اليوم في رسالة واحدة.

    المبيعات **صافية** (بعد الاسترجاع). لا ربح هنا عمداً: الرسالة تصل كل من يملك `stats.view`.
    """
    return (
        "📊 الملخص اليومي",
        f"📦 طلبات اليوم: {orders_today} (✅ منتهية: {completed_today} · ❌ فاشلة: {failed_today})\n"
        f"💰 صافي مبيعات اليوم: {money(revenue_today_units, symbol)}\n"
        f"↩️ مسترجع من طلبات اليوم: {money(refunds_today_units, symbol)}\n"
        f"💳 إيداعات معتمدة اليوم: {money(deposits_today_units, symbol)}\n"
        f"👥 مستخدمون جدد: {new_users}\n"
        f"⏳ طلبات شحن تنتظر المراجعة: {pending_payments}\n"
        f"⚠️ طلبات تحتاج انتباهك: {attention_orders}\n"
        f"🎫 تذاكر مفتوحة: {open_tickets}\n"
        f"🐞 أخطاء آخر 24 ساعة: {errors_24h}",
    )


# ------------------------- المرحلة 8: الإذاعة ---------------------------- #


def broadcast_finished(*, broadcast_id: int, sent: int, failed: int, blocked: int) -> tuple[str, str]:
    """تنبيه أدمن: انتهت الإذاعة مع حصيلتها النهائية."""
    return (
        "📣 انتهت الرسالة الجماعية",
        f"الإذاعة #{broadcast_id} اكتملت.\n"
        f"✅ وصلت: {sent}\n"
        f"🚫 حظروا البوت: {blocked}\n"
        f"⚠️ فشلت: {failed}",
    )
