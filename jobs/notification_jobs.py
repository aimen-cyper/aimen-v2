"""
مهمة إرسال الإشعارات من الطابور إلى تيليجرام.

لماذا طابور بدل الإرسال المباشر؟
    لأن الإرسال المباشر داخل المعاملة يربط نجاح العملية المالية بنجاح الشبكة.
    هنا: العملية تُسجَّل في قاعدة البيانات وتُدرج رسالتها في `notifications`،
    ثم تأتي هذه المهمة كل بضع ثوانٍ وتُرسل ما تراكم. انقطاع الشبكة يؤخر
    الإشعار فقط ولا يُفسد أي عملية.
"""

from __future__ import annotations

import time

from telegram.ext import ContextTypes

from jobs.telegram_sender import TelegramNotificationSender
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: أقصى عدد إشعارات تُرسل في الجولة الواحدة (حماية من حدود تيليجرام)
BATCH_LIMIT = 20

#: سقف زمن الجولة الواحدة (ثوانٍ): الإشعارات والقنوات معاً. تيليجرام البطيء (20 رسالة × مهلة شبكة)
#: كان يُبقي الجولة جارية أضعاف فترتها فتظهر تحذيرات «الحد الأقصى للنسخ الجارية» (بند 9).
ROUND_BUDGET_SECONDS = 25.0


async def dispatch_notifications(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    جولة إرسال واحدة: تحجز دفعة من الطابور وترسلها ثم تسجّل الحصيلة.

    الأخطاء هنا لا تُسقط المهمة الدورية: خدمة الإشعارات تُصنّف كل فشل
    (محظور / مؤقت / نهائي) وتتعامل معه، وما يصل إلى هنا يُسجَّل في اللوق.
    """
    services = context.application.bot_data["services"]
    sender = TelegramNotificationSender(context.bot)
    started = time.monotonic()
    report = await services.notifications.dispatch_pending(
        sender, limit=BATCH_LIMIT, budget_seconds=ROUND_BUDGET_SECONDS
    )
    if report.claimed:
        logger.info("جولة إشعارات: %s", report.as_dict())

    # صندوق القنوات الدائم: تنبيهات الإدارة/المستخدمون الجدد (admin_alert) + توثيق الطلبات (orders_log).
    # قناة النسخ الاحتياطي ليست طرفاً هنا إطلاقاً (مخصصة للنسخ فقط).
    remaining = max(1.0, ROUND_BUDGET_SECONDS - (time.monotonic() - started))
    channel_report = await services.channels.flush(
        sender, limit=BATCH_LIMIT, on_sent=services.order_messages.on_channel_post_sent, budget_seconds=remaining
    )
    if channel_report.claimed:
        logger.info("جولة قنوات: %s", channel_report)
