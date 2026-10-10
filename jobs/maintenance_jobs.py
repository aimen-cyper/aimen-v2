"""
مهام الصيانة الدورية.

    expire_old_payments  : إنهاء صلاحية طلبات الشحن التي تجاوزت مهلة المراجعة.
    auto_close_tickets   : إغلاق تذاكر الدعم الراكدة.
    database_maintenance : صيانة تقنية يومية لقاعدة البيانات (المرحلة 6).

الثلاثة تمنع تراكم ما لا قيمة له، واثنتان منها تُشعران صاحب الشأن بما حدث
بدل أن «يختفي» طلبه بصمت.

ملاحظة مهمة: صيانة قاعدة البيانات **لا تحذف أي بيانات تاريخية** — لا طلبات
ولا حركات مالية ولا تذاكر ولا سجلات تدقيق. تحذف فقط مفاتيح منع التكرار
(`idempotency_keys`) بعد انتهاء صلاحيتها، وطابور منشورات القنوات المنتهي (`channel_outbox`)
بعد 30 يوماً؛ وكلاهما تقني مؤقت بطبيعته.
"""

from __future__ import annotations

from telegram.ext import ContextTypes

from utils.datetime_utils import iso_minus_days
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: عدد طلبات الشحن التي تُفحص صلاحيتها في الجولة الواحدة
EXPIRE_BATCH = 50

#: مدة الاحتفاظ بمنشورات القنوات المنتهية في الطابور قبل تنظيفها
CHANNEL_OUTBOX_RETENTION_DAYS = 30


async def expire_old_payments(context: ContextTypes.DEFAULT_TYPE) -> None:
    """تعليم طلبات الشحن التي تجاوزت مهلة المراجعة كمنتهية + إشعار أصحابها."""
    services = context.application.bot_data["services"]
    count = await services.payments.expire_due(limit=EXPIRE_BATCH)
    if count:
        logger.info("طلبات شحن انتهت صلاحيتها: %s", count)


async def auto_close_tickets(context: ContextTypes.DEFAULT_TYPE) -> None:
    """إغلاق تذاكر الدعم التي لم يرد عليها أصحابها خلال المدة المحددة في الإعدادات."""
    services = context.application.bot_data["services"]
    count = await services.tickets.auto_close_idle()
    if count:
        logger.info("تذاكر أُغلقت تلقائياً لركودها: %s", count)


async def database_maintenance(context: ContextTypes.DEFAULT_TYPE) -> dict[str, int]:
    """
    صيانة تقنية يومية لقاعدة البيانات.

    ما تفعله:
        1. حذف مفاتيح منع التكرار المنتهية (`idempotency_keys`) — مؤقتة بطبيعتها.
        2. حذف منشورات القنوات المنتهية (`channel_outbox`: مرسلة/متجاوزة/فاشلة) الأقدم من
           `CHANNEL_OUTBOX_RETENTION_DAYS` يوماً — طابور تشغيلي لا سجل محاسبي (السجل الأصلي
           في `orders`/`audit_logs`).
        3. `PRAGMA wal_checkpoint(TRUNCATE)` لتقليص ملف الـWAL المتضخم.
        4. `PRAGMA optimize` لتحديث إحصاءات المخطط فتبقى الاستعلامات سريعة.

    ما **لا** تفعله: أي حذف لبيانات تاريخية، وأي `VACUUM` تلقائي (يقفل القاعدة
    مدة طويلة؛ يبقى قراراً يدوياً في أدوات الصيانة).

    المخرجات: عدّادات ما جرى (لتسجيلها في اللوق والاختبارات).
    """
    services = context.application.bot_data["services"]
    async with services.db.transaction() as tx:
        removed_keys = await services.repos.idempotency.cleanup_expired(tx)
        removed_posts = await services.repos.channel_outbox.delete_old(
            tx, iso_minus_days(CHANNEL_OUTBOX_RETENTION_DAYS)
        )

    checkpointed = 0
    try:
        await services.db.execute_raw("PRAGMA wal_checkpoint(TRUNCATE)")
        await services.db.execute_raw("PRAGMA optimize")
        checkpointed = 1
    except Exception as exc:                                        # noqa: BLE001
        # الصيانة التقنية ليست حرجة: نسجّلها ولا نُسقط المهمة على بقية خطواتها
        logger.warning("تعذّرت صيانة ملف قاعدة البيانات: %s", exc)

    result = {
        "idempotency_keys_removed": removed_keys,
        "channel_posts_removed": removed_posts,
        "checkpoint": checkpointed,
    }
    if removed_keys or removed_posts:
        logger.info("صيانة القاعدة: %s", result)
    return result
