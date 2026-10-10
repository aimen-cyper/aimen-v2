"""
مهام دورة حياة الطلب: الإرسال للمزود، فحص الحالة، تنبيه الطلبات العالقة.

منطق العمل كله داخل `OrderService` (المرحلة 2) — هذه الملفات مجرد جدولة
زمنية تستدعيه. الفائدة: يبقى المنطق قابلاً للاختبار بلا تيليجرام ولا مؤقتات.
"""

from __future__ import annotations

from telegram.ext import ContextTypes

from jobs.telegram_sender import TelegramMessageEditor
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: عدد الطلبات التي تُرسل للمزود في الجولة الواحدة (افتراضي عند غياب الإعداد)
SUBMIT_BATCH = 5

#: عدد الطلبات التي تُفحص حالتها في الجولة الواحدة (افتراضي عند غياب الإعداد)
CHECK_BATCH = 20

#: الحد الأقصى المسموح لحجم الدفعة مهما كان الإعداد (حماية من قيمة خاطئة)
MAX_BATCH = 100


async def _batch_size(services, key: str, default: int) -> int:
    """قراءة حجم الدفعة من الإعدادات ضمن حدود آمنة (1..MAX_BATCH)."""
    value = await services.settings.get_int(key, default)
    return max(1, min(MAX_BATCH, value))


async def submit_pending_orders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    إرسال الطلبات المعلّقة إلى المزودين.

    الحجز (lease) داخل الخدمة يمنع إرسال الطلب مرتين حتى لو تداخلت جولتان.
    """
    services = context.application.bot_data["services"]
    # أولاً: طلبات علقت في submitting بعد انتهاء قفلها (مهلة/انقطاع) ⇒ غير مؤكدة وتنبيه، قبل حجز جديد
    await services.orders.recover_stale_submissions()
    limit = await _batch_size(services, "order_submit_batch_size", SUBMIT_BATCH)
    report = await services.orders.process_pending_orders(worker="submitter", limit=limit)
    if report.claimed:
        logger.info("جولة إرسال الطلبات: %s", report.as_dict())


async def check_active_orders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    فحص حالة الطلبات النشطة عند المزود وتحديثها (إكمال/جزئي/فشل + استرجاع).

    هذه هي المهمة التي تجعل الطلب «يمشي لوحده» حتى حالته النهائية.
    """
    services = context.application.bot_data["services"]
    limit = await _batch_size(services, "order_check_batch_size", CHECK_BATCH)
    report = await services.orders.process_due_orders(worker="checker", limit=limit)
    if report.claimed:
        logger.info("جولة فحص الطلبات: %s", report.as_dict())


async def alert_stuck_orders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """تنبيه الأدمن بالطلبات التي لم تتقدم منذ مدة طويلة (مؤشر خلل صامت)."""
    services = context.application.bot_data["services"]
    count = await services.orders.alert_stuck_orders()
    if count:
        logger.warning("طلبات متوقفة بلا تقدم: %s", count)


#: عدد الرسائل المعدَّلة في الجولة وميزانيتها الزمنية (تحت فاصل المهمة حتى لا تتراكم الجولات)
REFRESH_BATCH = 15
REFRESH_BUDGET_SECONDS = 10.0


async def refresh_order_messages(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    تعديل رسائل تيليجرام التي تعرض حالة طلب تغيّرت (تأكيد الطلب/إشعار الإنشاء/منشور قناة التوثيق).

    الحالة في قاعدة البيانات تُكتب قبل هذه المهمة وبمعزل عنها: فشل تعديل رسالة لا يضيّع تحديث الحالة.
    """
    services = context.application.bot_data["services"]
    await services.order_messages.refresh_due(
        TelegramMessageEditor(context.bot), limit=REFRESH_BATCH, budget_seconds=REFRESH_BUDGET_SECONDS
    )
