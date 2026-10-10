"""
نصوص منشورات القنوات الإدارية (مستخدم جديد، توثيق طلب).

قاعدة صارمة: لا يظهر هنا أي سر — لا مفتاح مزود ولا رابط كامل (التقنيع في `utils.privacy`).

سياسة الخصوصية (قرار المالك):
    • منشور «مستخدم جديد» يصل لفريق الإدارة فقط ⇒ **Telegram ID كاملاً** (لإدارة المستخدم والتواصل معه).
    • منشور «طلب جديد» قناة توثيق قد يراها كثيرون ⇒ المعرّف **مقنَّع** والرابط يُظهر المنصة فقط.
"""

from __future__ import annotations

from decimal import Decimal

from core.money import format_usd
from utils.formatters import datetime_text, local_amount
from utils.privacy import mask_link, mask_telegram_id, mask_username


def new_user_post(*, user, total_users: int) -> tuple[str, str]:
    """منشور «مستخدم جديد 🔥» لقناة الإدارة (Telegram ID كامل — للإدارة فقط)؛ المخرجات: (العنوان، النص)."""
    name = " ".join(part for part in (user.first_name, user.last_name) if part).strip() or "—"
    username = mask_username(user.username)
    message = (
        f"🆔 رقم الحساب: {user.id}\n"
        f"👤 الاسم: {name}\n"
        f"🔖 Username: {username}\n"
        f"📱 Telegram ID: {user.telegram_id}\n"
        f"📅 التسجيل: {datetime_text(user.created_at)}\n"
        f"👥 إجمالي المستخدمين: {total_users:,}\n\n"
        "🎉 مرحباً بالعضو الجديد في عائلتنا!"
    )
    return "🆕 مستخدم جديد انضم 🔥", message


#: سطر حالة منشور التوثيق بحسب حالة الطلب (يتجدد عند تغيّر الحالة)
_CHANNEL_STATUS_LINES: dict[str, str] = {
    "in_progress": "⏳ الطلب قيد التنفيذ",
    "completed": "✅ اكتمل التنفيذ",
    "partial": "🟡 اكتمل جزئياً وأُعيد فرق المبلغ",
    "canceled": "❌ أُلغي الطلب وأُعيد المبلغ",
    "refunded": "❌ لم يكتمل الطلب وأُعيد المبلغ",
    "failed": "❌ فشل الطلب",
    "submit_uncertain": "🔎 قيد المراجعة",
}
DEFAULT_CHANNEL_STATUS_LINE = "✅ تم تسجيل الطلب وجارٍ تنفيذه"


def channel_status_line(status: str) -> str:
    """سطر حالة منشور القناة لحالة طلب."""
    return _CHANNEL_STATUS_LINES.get(status, DEFAULT_CHANNEL_STATUS_LINE)


def order_post(
    *,
    category_name: str,
    service_name: str,
    order_code: str,
    quantity: int,
    cost_units: int,
    symbol: str,
    usd_rate: Decimal | None,
    user,
    link: str,
    status: str = "pending",
) -> tuple[str, str]:
    """منشور «طلب جديد 🔥» لقناة توثيق الطلبات؛ المخرجات: (العنوان، النص). `status` يحدد سطر الحالة الختامي."""
    usd_text = format_usd(cost_units, usd_rate)
    usd_suffix = f" ({usd_text})" if usd_text else ""
    message = (
        f"📂 القسم: {category_name or '—'}\n"
        f"💎 الخدمة: {service_name}\n"
        f"🔖 رقم الطلب: {order_code}\n"
        f"🔢 الكمية: {quantity:,}\n"
        f"💵 السعر: {local_amount(cost_units, symbol)}{usd_suffix}\n"
        f"👤 العميل: {mask_telegram_id(user.telegram_id)}\n"
        f"🔗 الرابط: {mask_link(link)}\n\n"
        f"{channel_status_line(status)}"
    )
    return "🔥 طلب جديد", message
