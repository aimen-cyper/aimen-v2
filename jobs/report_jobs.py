"""
مهام التقارير الدورية (المرحلة 6).

حالياً مهمة واحدة: **الملخص اليومي للأدمن**.

لماذا؟
    لوحة التحكم تعرض الأرقام لمن يدخلها، لكن النظام الذي يعمل وحده يحتاج أن
    يتكلم: رسالة واحدة في وقت محدد يومياً تختصر حركة اليوم وما ينتظر تدخلاً.
    وهي كذلك نبضة حياة: غيابها مؤشر على أن شيئاً ما توقف.

الملخص يمر عبر طابور الإشعارات كغيره (`notify_admins`) فلا يرتبط نجاحه
باتصال الشبكة لحظة التوليد، ولا يُرسل مرتين لنفس اليوم (رمز منع التكرار).
"""

from __future__ import annotations

from telegram.ext import ContextTypes

from core.enums import OrderStatus
from core.permissions import Permission
from texts import templates
from utils.datetime_utils import day_bounds_utc
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: الحالات التي تعني «طلب يحتاج تدخل الأدمن الآن»
ATTENTION_STATUSES = (OrderStatus.SUBMIT_UNCERTAIN, OrderStatus.FAILED)


async def send_admin_daily_digest(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    إرسال الملخص اليومي لكل من يملك `stats.view`.

    المخرجات: True إذا أُدرج الملخص في الطابور (False إذا كان قد أُرسل اليوم).
    """
    services = context.application.bot_data["services"]
    digest = await services.stats.system_digest()
    symbol = await services.settings.money_symbol()
    today = day_bounds_utc(0)[0][:10]

    title, message = templates.admin_daily_digest(
        orders_today=digest["orders_today"],
        revenue_today_units=digest["revenue_today_units"],
        deposits_today_units=digest["deposits_today_units"],
        pending_payments=digest["pending_payments"],
        attention_orders=digest["attention_orders"],
        open_tickets=digest["open_tickets"],
        new_users=digest["new_users_today"],
        errors_24h=digest["errors_24h"],
        refunds_today_units=digest["refunds_today_units"],
        completed_today=digest["completed_today"],
        failed_today=digest["failed_today"],
        symbol=symbol,
    )

    async with services.db.transaction() as tx:
        inserted = await services.notifications.notify_admins(
            tx,
            permission=Permission.STATS_VIEW,
            token=f"digest:{today}",
            title=title,
            message=message,
        )

    if inserted:
        logger.info("أُدرج الملخص اليومي لـ%s أدمن", inserted)
    else:
        logger.info("الملخص اليومي لـ%s أُرسل سابقاً — تم تخطّيه", today)
    return bool(inserted)
