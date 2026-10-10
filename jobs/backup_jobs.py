"""
مهمة النسخ الاحتياطي الدورية (المرحلة 10).

مهمة واحدة تعمل كل بضع دقائق وتقرّر بنفسها ما يلزم:
    1. هل حان موعد نسخة جديدة؟ (من عمر آخر نسخة سليمة وإعداد `backup_interval_hours`).
    2. هل أُرسلت أحدث نسخة للقناة الخارجية؟
    3. هل في القرص نسخ أقدم من مدة الاحتفاظ تُحذف ملفاتها؟
    4. هل النسخ فاشل أو متأخر ⇒ تنبيه الأدمن (مرة يومياً).

لماذا فحص دوري بدل «كل N ساعة» ثابتة؟
    جدولة ثابتة تُنتج نسخة عند كل إعادة تشغيل، ولا تلتقط تغيير الفاصل إلا بعد
    إعادة جدولة. أما الفحص الدوري فيحسب الموعد من آخر نسخة فعلية: تشغيل البوت
    مراراً لا يُنتج نسخاً زائدة، وانقطاعه ساعات ينتج نسخة فور عودته.
"""

from __future__ import annotations

from telegram.ext import ContextTypes

from utils.logging_setup import get_logger

logger = get_logger(__name__)


async def run_backups(context: ContextTypes.DEFAULT_TYPE) -> dict[str, int]:
    """جولة النسخ الاحتياطي: إنشاء إن حان الموعد + إرسال + احتفاظ + تنبيه."""
    services = context.application.bot_data["services"]
    report = await services.backups.run_scheduled(context.bot)
    if any(report.values()):
        logger.info("جولة النسخ الاحتياطي: %s", report)
    return report
