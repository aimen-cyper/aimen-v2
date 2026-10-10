"""
أدوات تنسيق العرض: تحويل بيانات قاعدة البيانات إلى نصوص عربية جاهزة للشاشة.

قاعدة: لا منطق أعمال هنا — تنسيق فقط. وأي رقم مالي يُنسَّق من النقاط الصحيحة
عبر `core.money` ولا يُحسب هنا إطلاقاً.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from html import escape
from zoneinfo import ZoneInfo

from core.enums import (
    NotificationType,
    OrderStatus,
    PaymentStatus,
    TicketStatus,
    TransactionType,
)
from core.money import format_units, format_usd, from_units
from core.order_state import map_provider_status
from utils.datetime_utils import DEFAULT_TIMEZONE, parse_iso, to_local_text, utc_now

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


def format_money(units: int, symbol: str = "", *, compact: bool = False) -> str:
    """
    **الدالة الوحيدة** لتنسيق مبلغ بعملة النظام (التقريب HALF_UP إلى خانتين مرة واحدة).

    `compact=False` (الافتراضي): خانتان دائماً `530.00 ريال` — لكل السجلات المالية وبطاقات الطلب.
    `compact=True`: يحذف `.00` للأسطر الموجزة (أزرار/منشورات) `530 ريال`، وتبقى `530.50` كما هي.
    القيمة العددية واحدة في الحالتين؛ لا يختلف إلا حذف الأصفار الزائدة.
    """
    amount = from_units(units).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    text = f"{amount:,.2f}"
    if compact and text.endswith(".00"):
        text = text[:-3]
    return f"{text} {symbol}".strip()


def money_text(units: int, symbol: str = "", decimals: int = 2) -> str:
    """عرض مبلغ من النقاط الصحيحة بصيغة قابلة للقراءة مع رمز العملة (خانتان دائماً عبر `format_money`)."""
    if decimals == 2:
        return format_money(units, symbol)
    return format_units(units, symbol, decimals)


def local_amount(units: int, symbol: str = "") -> str:
    """مبلغ بعملة النظام بلا أصفار زائدة بعد الفاصلة (`530.00 ريال` ⇒ `530 ريال`، و`530.50` تبقى)."""
    return format_money(units, symbol, compact=True)


def price_pair(units: int, symbol: str, usd_rate: Decimal | None) -> tuple[str, str]:
    """
    السعر بالدولار (الأساس في العرض) ومقابله الفعلي بعملة النظام.

    المخرجات: (`$1.00`، `530 ريال`). المقابل هو **المبلغ الحقيقي المخصوم** لا ناتج تقريب، فلا يظهر
    فرق بين ما يراه العميل وما يُخصم منه؛ أما الدولار فمشتق منه بسعر الصرف المعروض (للعرض فقط).
    """
    return format_usd(units, usd_rate), local_amount(units, symbol)


def price_line(units: int, symbol: str, usd_rate: Decimal | None) -> str:
    """سطر سعر مختصر للأزرار والملخصات: `$1.00 • 530 ريال` (بلا سعر صرف: المبلغ المحلي وحده)."""
    usd, local = price_pair(units, symbol, usd_rate)
    return f"{usd} • {local}" if usd else local


def tidy_text(text: str) -> str:
    """
    تنسيق مركزي للرسائل العربية: لا مسافات بادئة (WP0).

    المسافات البادئة تنهار أو تنزاح في الاتجاه من اليمين إلى اليسار ويظهر النص «غير مرتب». كل سطر يبدأ بمسافتين فأكثر
    يُجرَّد منها، ويُسبَق بنقطة «•» إن كان أول حرف فيه حرفاً/رقماً (السطر الذي يبدأ برمز أو إيموجي يبقى كما هو).
    النص داخل `<pre>` لا يُمسّ لأن مسافاته مقصودة.
    """
    if "<pre" in text or "\n " not in text and not text.startswith("  "):
        return text
    lines = []
    for line in text.split("\n"):
        stripped = line.lstrip(" ")
        if len(line) - len(stripped) >= 2 and stripped:
            first = stripped[0]
            lines.append(f"• {stripped}" if (first.isalnum() or first in "<#") else stripped)
        else:
            lines.append(line)
    return "\n".join(lines)


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


# ======================= لمسات العرض (تحية · تقدّم · عضوية) ======================= #

#: خطّ الفصل الموحّد بين أقسام البطاقات
DIVIDER = "━━━━━━━━━━━━━━━━━━━━"


def time_greeting(now: datetime | None = None, timezone: str = DEFAULT_TIMEZONE) -> str:
    """
    تحية بحسب وقت اليوم المحلي (Asia/Aden افتراضياً): «🌅 صباح الخير» · «☀️ طاب يومك» · «🌆 مساء الخير» · «🌙 أهلاً بك».

    المدخلات: `now` لحقن الوقت في الاختبار (UTC أو بمنطقة)، وإلا اللحظة الحالية.
    """
    moment = now or utc_now()
    try:
        hour = moment.astimezone(ZoneInfo(timezone)).hour
    except (KeyError, ValueError, OSError):
        hour = moment.hour
    if 5 <= hour < 12:
        return "🌅 صباح الخير"
    if 12 <= hour < 18:
        return "☀️ طاب يومك"
    if 18 <= hour < 23:
        return "🌆 مساء الخير"
    return "🌙 أهلاً بك"


def progress_bar(done: int, total: int, *, width: int = 10) -> tuple[str, int]:
    """
    شريط تقدّم نصي مثل `▰▰▰▰▱▱▱▱▱▱` مع النسبة المئوية الصحيحة (0..100).

    المدخلات: المنفَّذ والإجمالي؛ الإجمالي غير الموجب أو القيم السالبة تُعامَل كصفر تقدّم.
    """
    if total <= 0 or done <= 0:
        return "▱" * width, 0
    ratio = min(1.0, done / total)
    filled = min(width, int(ratio * width + 0.5)) if ratio < 1 else width
    percent = min(100, int(ratio * 100))
    return "▰" * filled + "▱" * (width - filled), percent


def member_days(created_iso: str | None, now: datetime | None = None) -> int:
    """عدد الأيام الكاملة منذ الانضمام (0 إن تعذّر قراءة التاريخ أو كان في المستقبل)."""
    joined = parse_iso(created_iso)
    if joined is None:
        return 0
    return max(0, ((now or utc_now()) - joined).days)



# ======================================================================= #
#                  OrderView — مصدر واحد لعرض الطلب في كل الشاشات           #
# ======================================================================= #


def order_progress(order) -> tuple[int, int] | None:
    """
    (المنفَّذ، المتبقي) بحدود صحيحة، أو None إن لم يصل أي تقدّم من المزود.

    بعض اللوحات (JAP/Perfect Panel) تُرجع `remains` فقط بلا `quantity`: كان المنفَّذ يظهر 0 مع متبقٍّ 700.
    القاعدة: المنفَّذ = الكمية − المتبقي عند غياب المنفَّذ، والمتبقي = الكمية − المنفَّذ عند غيابه، وكلاهما ضمن [0، الكمية].
    """
    delivered, remains = order.delivered_quantity, order.remains
    if delivered is None and remains is None:
        return None
    quantity = max(0, int(order.quantity))
    if delivered is None:
        delivered = quantity - int(remains)
    if remains is None:
        remains = quantity - int(delivered)
    delivered = min(max(0, int(delivered)), quantity)
    remains = min(max(0, int(remains)), quantity)
    return delivered, remains


@dataclass(frozen=True, slots=True)
class OrderView:
    """قيم عرض الطلب المحسوبة مرة واحدة؛ كل شاشة (مستخدم/أدمن/قوائم/إشعارات/قناة) تقرأ منها لا من الصف مباشرة."""

    code: str
    status: str
    status_label: str
    quantity: int
    delivered: int | None
    remains: int | None
    percent: int
    cost_text: str
    refund_text: str | None
    net_text: str
    provider_status_label: str | None
    last_checked_at: str | None
    last_check_ok_at: str | None
    last_check_error: str | None
    check_fail_streak: int
    next_check_at: str | None


def build_order_view(order, symbol: str = "") -> OrderView:
    """بناء `OrderView` من صف الطلب (تنسيق فقط، بلا منطق أعمال)."""
    progress = order_progress(order)
    delivered, remains = progress if progress else (None, None)
    percent = 0
    if delivered is not None and order.quantity > 0:
        percent = min(100, delivered * 100 // order.quantity)
    provider_label = None
    if order.provider_status:
        mapped = map_provider_status(order.provider_status)
        provider_label = order_status_text(mapped) if mapped else str(order.provider_status)
    refunded = int(order.refund_amount_units or 0)
    return OrderView(
        code=order.public_code or f"#{order.id}",
        status=order.status,
        status_label=order_status_text(order.status),
        quantity=order.quantity,
        delivered=delivered,
        remains=remains,
        percent=percent,
        cost_text=format_money(order.cost_units, symbol),
        refund_text=format_money(refunded, symbol) if refunded else None,
        net_text=format_money(max(0, order.cost_units - refunded), symbol),
        provider_status_label=provider_label,
        last_checked_at=order.last_checked_at,
        last_check_ok_at=order.last_check_ok_at,
        last_check_error=order.last_check_error,
        check_fail_streak=int(order.check_fail_streak or 0),
        next_check_at=order.next_check_at,
    )
