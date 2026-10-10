"""
مهمة إرسال الرسائل الجماعية على دفعات.

لماذا دفعات صغيرة متباعدة؟
    تيليجرام يحدّ الإرسال الجماعي (~30 رسالة/ثانية، وأقل لكل محادثة). إرسال
    آلاف الرسائل في حلقة واحدة يُنتج `RetryAfter` متتالياً وقد يُقيَّد البوت.
    هنا نرسل `broadcast_batch_size` رسالة كل `broadcast_interval_seconds`،
    وكلاهما قابل للضبط من «⚙️ الإعدادات ← broadcast» دون تعديل كود.

الأمان التشغيلي:
    • الجولة تعالج إذاعة واحدة فقط (الأقدم) حتى لا تتزاحم إذاعتان على الحصة.
    • نتيجة كل مستلم تُكتب فور إرسالها، فانقطاع البوت لا يُعيد إرسال ما وصل.
    • لا شيء يُرسل ما لم تكن حالة الإذاعة `running` — الإيقاف المؤقت فوري.
"""

from __future__ import annotations

from telegram.ext import ContextTypes

from jobs.telegram_sender import TelegramBroadcastSender
from utils.logging_setup import get_logger

logger = get_logger(__name__)


async def dispatch_broadcasts(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    جولة إذاعة واحدة: دفعة من مستلمي الإذاعة الجارية.

    لا تفعل شيئاً إن لم توجد إذاعة بحالة «جارية» — وهو الوضع الطبيعي معظم الوقت.
    """
    services = context.application.bot_data["services"]
    sender = TelegramBroadcastSender(context.bot)
    report = await services.broadcasts.send_batch(sender)
    if report.claimed:
        logger.info("جولة إذاعة: %s", report.as_dict())
