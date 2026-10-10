"""
نصوص الرسائل «الحيّة» التي تُعدَّل عند تغيّر حالة الطلب (بطاقة حالة للمستخدم).

تنسيق فقط: القيم كلها من `OrderView` (مصدر العرض الموحّد) فلا اختلاف بين هذه الرسالة وبطاقة «📦 طلباتي».
"""

from __future__ import annotations

from utils.formatters import OrderView, datetime_text, progress_bar, safe, short_link


def user_status_card(view: OrderView, *, service_name: str, link: str, updated_at: str | None) -> str:
    """بطاقة حالة قصيرة للمستخدم (HTML). تحلّ محل رسالة «تم إنشاء طلبك» عندما تتغير الحالة."""
    lines = [
        f"📦 <b>الطلب {safe(view.code)}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💎 الخدمة: {safe(service_name)}",
        f"🔗 الرابط: {short_link(link)}",
        f"🔢 الكمية: {view.quantity}",
    ]
    if view.delivered is not None and view.remains is not None:
        bar, percent = progress_bar(view.delivered, view.quantity)
        lines.append(f"📈 التقدّم: {bar} <b>{percent}%</b>")
        lines.append(f"✅ المنفَّذ: {view.delivered} · ⏳ المتبقي: {view.remains}")
    lines.append(f"💵 التكلفة: {view.cost_text}")
    if view.refund_text:
        lines.append(f"↩️ المسترجع: <b>{view.refund_text}</b>")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"📊 الحالة: <b>{view.status_label}</b>")
    if updated_at:
        lines.append(f"🕒 آخر تحديث: {datetime_text(updated_at)}")
    return "\n".join(lines)
