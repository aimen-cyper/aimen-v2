"""
جدولة المهام الدورية على JobQueue الخاص بـpython-telegram-bot.

لماذا JobQueue بدل asyncio.create_task يدوياً؟
    لأنه يعمل داخل حلقة التطبيق نفسها، ويتوقف معه بنظافة عند الإغلاق،
    ويمنحنا `first`/`interval`/`run_daily` ومعالج أخطاء موحّداً. لا حاجة
    لعفريت خارجي ولا cron.

كل الفترات الزمنية تُقرأ من جدول الإعدادات (`settings`) لا من ثوابت في الكود،
فيستطيع الأدمن ضبط إيقاع النظام من داخل البوت دون إعادة نشر.

**المرحلة 6:** كل مهمة تُسجَّل الآن عبر `jobs.runner.supervise` فتكتسب:
منع التداخل، مهلة قصوى للجولة، التقاط كل استثناء إلى `error_logs`، تنبيه
الأدمن عند تكرار الفشل، وسجل حالة تعرضه شاشة «⏱ المهام الدورية».
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from telegram.ext import Application, JobQueue

from jobs.backup_jobs import run_backups
from jobs.broadcast_jobs import dispatch_broadcasts
from jobs.maintenance_jobs import auto_close_tickets, database_maintenance, expire_old_payments
from jobs.notification_jobs import dispatch_notifications
from jobs.order_jobs import alert_stuck_orders, check_active_orders, refresh_order_messages, submit_pending_orders
from jobs.provider_jobs import refresh_provider_balances, watch_provider_health
from jobs.report_jobs import send_admin_daily_digest
from jobs.runner import JOB_REGISTRY, JobCallback, JobRegistry, supervise
from services import ServiceContainer
from utils.datetime_utils import APP_TIMEZONE
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: الحد الأدنى المقبول لأي فترة تكرار (حماية من قيمة إعداد خاطئة تُغرق النظام)
MIN_INTERVAL_SECONDS = 5

#: مهلة الجولة الواحدة لكل نوع مهمة (ثوانٍ) — بعدها تُلغى الجولة وتُسجَّل كفشل
FAST_JOB_TIMEOUT = 120.0
SLOW_JOB_TIMEOUT = 600.0

#: فاصل فحص «هل حان موعد النسخة؟» (ثانية) — الفاصل الفعلي للنسخ من الإعدادات
BACKUP_CHECK_SECONDS = 600.0

__all__ = [
    "schedule_jobs",
    "reschedule_for_setting",
    "run_startup_recovery",
    "JOB_REGISTRY",
    "JOB_LABELS",
]

#: أسماء عربية للمهام تُعرض في لوحة التحكم (الاسم التقني يبقى للّوقات)
JOB_LABELS: dict[str, str] = {
    "notifications_dispatch": "📨 إرسال الإشعارات",
    "broadcast_dispatch": "📣 إرسال الرسائل الجماعية",
    "orders_submit": "📤 إرسال الطلبات للمزود",
    "orders_check": "🔄 متابعة حالة الطلبات",
    "orders_refresh_messages": "📝 تحديث رسائل الطلبات",
    "payments_expire": "⌛️ إنهاء صلاحية طلبات الشحن",
    "tickets_auto_close": "🎫 إغلاق التذاكر الراكدة",
    "orders_stuck_alert": "⏰ تنبيه الطلبات المتوقفة",
    "providers_balance": "💵 فحص أرصدة المزودين",
    "providers_health": "🩺 مراقبة صحة المزودين",
    "admin_daily_digest": "📊 الملخص اليومي",
    "database_maintenance": "🗄 صيانة قاعدة البيانات",
    "backups_auto": "💾 النسخ الاحتياطي",
}


async def _interval(services: ServiceContainer, key: str, default: int) -> float:
    """قراءة فترة تكرار من الإعدادات مع فرض حد أدنى آمن."""
    value = await services.settings.get_int(key, default)
    return float(max(MIN_INTERVAL_SECONDS, value))


def _every_text(seconds: float) -> str:
    """وصف عربي مختصر لفترة التكرار (يُعرض في شاشة المهام)."""
    seconds = int(seconds)
    if seconds < 60:
        return f"كل {seconds} ثانية"
    if seconds < 3600:
        return f"كل {seconds // 60} دقيقة"
    if seconds < 86400:
        return f"كل {seconds // 3600} ساعة"
    return f"كل {seconds // 86400} يوم"


def _daily_time(hour: int) -> dt.time:
    """ساعة تشغيل يومية بتوقيت التطبيق (Asia/Aden افتراضياً) مع حصر 0..23."""
    return dt.time(hour=max(0, min(23, hour)), minute=0, tzinfo=APP_TIMEZONE)


@dataclass(frozen=True, slots=True)
class JobSpec:
    """
    وصف مهمة دورية واحدة كما تُحسب من الإعدادات الحالية.

    الحقول:
        name        : اسم المهمة (مفتاح السجل واللوحة).
        callback    : دالة المهمة الأصلية.
        interval    : فترة التكرار بالثواني (None للمهام اليومية).
        daily_hour  : ساعة التشغيل اليومية (None للمتكررة).
        first       : تأخير أول تشغيل (للمتكررة).
        timeout     : مهلة الجولة الواحدة.
    """

    name: str
    callback: JobCallback
    interval: float | None
    daily_hour: int | None
    first: float
    timeout: float


#: ربط مفتاح إعداد بالمهمة التي يتحكم بإيقاعها (يُستخدم في إعادة الجدولة الحيّة)
JOB_SETTING_KEYS: dict[str, str] = {
    "notification_dispatch_seconds": "notifications_dispatch",
    "broadcast_interval_seconds": "broadcast_dispatch",
    "order_submit_interval_seconds": "orders_submit",
    "order_check_interval_seconds": "orders_check",
    "order_message_refresh_seconds": "orders_refresh_messages",
    "provider_balance_check_minutes": "providers_balance",
    "provider_health_watch_minutes": "providers_health",
    "admin_digest_hour": "admin_daily_digest",
    "db_maintenance_hour": "database_maintenance",
}

#: إعدادات وجهات القنوات ⇒ نوع المنشور (لإعادة جدولة الفاشل عند التصحيح)
CHANNEL_DESTINATION_KEYS: dict[str, str] = {
    "orders_log_chat_id": "orders_log",
    "admin_alert_chat_id": "admin_alert",
}

#: مفتاح يؤثر على كل المهام (عتبة تنبيه الفشل مغلَّفة داخل كل مهمة)
ALL_JOBS_SETTING_KEY = "job_failure_alert_threshold"


async def build_job_specs(services: ServiceContainer) -> list[JobSpec]:
    """
    حساب جدول المهام من قيم الإعدادات **الحالية** (يُستدعى عند الإقلاع وعند أي تعديل).

    فصل الحساب عن التركيب هو ما يتيح تغيير الإيقاع دون إعادة تشغيل: نعيد حساب
    الجدول ثم نستبدل المهمة المتأثرة فقط.
    """
    return [
        JobSpec("notifications_dispatch", dispatch_notifications,
                await _interval(services, "notification_dispatch_seconds", 10), None, 5.0, FAST_JOB_TIMEOUT),
        JobSpec("broadcast_dispatch", dispatch_broadcasts,
                await _interval(services, "broadcast_interval_seconds", 5), None, 8.0, FAST_JOB_TIMEOUT),
        JobSpec("orders_submit", submit_pending_orders,
                await _interval(services, "order_submit_interval_seconds", 30), None, 12.0, SLOW_JOB_TIMEOUT),
        JobSpec("orders_check", check_active_orders,
                await _interval(services, "order_check_interval_seconds", 120), None, 25.0, SLOW_JOB_TIMEOUT),
        JobSpec("orders_refresh_messages", refresh_order_messages,
                await _interval(services, "order_message_refresh_seconds", 15), None, 20.0, FAST_JOB_TIMEOUT),
        JobSpec("payments_expire", expire_old_payments, 900.0, None, 60.0, FAST_JOB_TIMEOUT),
        JobSpec("tickets_auto_close", auto_close_tickets, 3600.0, None, 120.0, FAST_JOB_TIMEOUT),
        JobSpec("orders_stuck_alert", alert_stuck_orders, 3600.0, None, 300.0, FAST_JOB_TIMEOUT),
        JobSpec("providers_balance", refresh_provider_balances,
                await _interval(services, "provider_balance_check_minutes", 30) * 60.0,
                None, 90.0, SLOW_JOB_TIMEOUT),
        JobSpec("providers_health", watch_provider_health,
                await _interval(services, "provider_health_watch_minutes", 10) * 60.0,
                None, 150.0, SLOW_JOB_TIMEOUT),
        JobSpec("admin_daily_digest", send_admin_daily_digest, None,
                await services.settings.get_int("admin_digest_hour", 21), 0.0, SLOW_JOB_TIMEOUT),
        JobSpec("database_maintenance", database_maintenance, None,
                await services.settings.get_int("db_maintenance_hour", 4), 0.0, SLOW_JOB_TIMEOUT),
        # فحص دوري ثابت: الموعد الفعلي يُحسب من آخر نسخة سليمة وإعداد backup_interval_hours
        JobSpec("backups_auto", run_backups, BACKUP_CHECK_SECONDS, None, 180.0, SLOW_JOB_TIMEOUT),
    ]


def _job_kwargs(interval: float) -> dict:
    """
    خيارات APScheduler الصريحة لكل مهمة: نسخة واحدة جارية، دمج الجولات الفائتة، ومهلة سماح محدودة.

    بدونها كانت جولة بطيئة (إشعارات/استعلامات) تُراكم جولات متأخرة وتظهر تحذيرات
    «maximum number of running instances reached». العلاج الفعلي لبطء الجولة في المهمة نفسها؛ هذه فقط تمنع التراكم.
    """
    return {"max_instances": 1, "coalesce": True, "misfire_grace_time": int(max(5.0, min(interval, 60.0)))}


def _install_job(
    queue: JobQueue,
    spec: JobSpec,
    *,
    registry: JobRegistry,
    alert_threshold: int,
    keep_history: bool,
) -> str:
    """
    تركيب مهمة واحدة على JobQueue (واستبدال نسختها القديمة إن وُجدت).

    المخرجات: وصف نصي قصير للسجل (مثل `orders_check(120s)`).
    """
    for old in queue.get_jobs_by_name(spec.name):          # إزالة الجدولة القديمة أولاً
        old.schedule_removal()

    if spec.daily_hour is not None:
        run_at = _daily_time(spec.daily_hour)
        supervised = supervise(
            spec.callback, name=spec.name, registry=registry, interval_seconds=86400.0,
            schedule_text=f"يومياً {run_at.strftime('%H:%M')}", timeout_seconds=spec.timeout,
            failure_alert_threshold=alert_threshold, keep_history=keep_history,
        )
        queue.run_daily(supervised, time=run_at, name=spec.name, job_kwargs=_job_kwargs(86400.0))
        return f"{spec.name}(daily {run_at.strftime('%H:%M')})"

    interval = float(spec.interval or MIN_INTERVAL_SECONDS)
    supervised = supervise(
        spec.callback, name=spec.name, registry=registry, interval_seconds=interval,
        schedule_text=_every_text(interval), timeout_seconds=spec.timeout,
        failure_alert_threshold=alert_threshold, keep_history=keep_history,
    )
    queue.run_repeating(
        supervised, interval=interval, first=spec.first, name=spec.name, job_kwargs=_job_kwargs(interval)
    )
    return f"{spec.name}({int(interval)}s)"


async def schedule_jobs(
    application: Application,
    services: ServiceContainer,
    *,
    registry: JobRegistry = JOB_REGISTRY,
) -> list[str]:
    """
    جدولة كل المهام الدورية وإرجاع أسمائها (تُطبع في سجل الإقلاع).

    المهام المتكررة:
        notifications_dispatch : إرسال الإشعارات المتراكمة.
        broadcast_dispatch     : إرسال دفعة من مستلمي الرسالة الجماعية الجارية.
        orders_submit          : إرسال الطلبات المعلّقة للمزود.
        orders_check           : متابعة الطلبات النشطة حتى حالتها النهائية.
        payments_expire        : إنهاء صلاحية طلبات الشحن القديمة.
        tickets_auto_close     : إغلاق التذاكر الراكدة.
        orders_stuck_alert     : تنبيه الأدمن بالطلبات المتوقفة.
        providers_balance      : قراءة أرصدتنا لدى المزودين + تنبيه الانخفاض.
        providers_health       : إعادة تفعيل المزود المتعثر فور تعافيه.

    المهام اليومية (بتوقيت التطبيق):
        admin_daily_digest     : الملخص اليومي للأدمن.
        database_maintenance   : صيانة تقنية لقاعدة البيانات.

    مهمة النسخ الاحتياطي `backups_auto` تفحص كل 10 دقائق هل حان موعد نسخة (المرحلة 10).

    **المرحلة 9:** تُسجَّل أيضاً دالة مراقبة على الإعدادات: أي تعديل لمفتاح إيقاع
    (فترة/ساعة) يعيد جدولة مهمته فوراً بلا إعادة تشغيل (`reschedule_for_setting`).
    """
    queue = application.job_queue
    if queue is None:
        raise RuntimeError(
            "JobQueue غير متاح — ثبّت الحزمة بالشكل: pip install 'python-telegram-bot[job-queue]'"
        )

    registry.clear()
    alert_threshold = await services.settings.get_int("job_failure_alert_threshold", 3)

    names = [
        _install_job(queue, spec, registry=registry, alert_threshold=alert_threshold, keep_history=False)
        for spec in await build_job_specs(services)
    ]
    _attach_setting_listener(application, services, registry)
    logger.info("تمت جدولة %s مهمة دورية: %s", len(names), ", ".join(names))
    return names


async def reschedule_for_setting(
    application: Application,
    services: ServiceContainer,
    key: str,
    *,
    registry: JobRegistry = JOB_REGISTRY,
) -> list[str]:
    """
    إعادة جدولة المهمة (أو المهام) التي يتحكم بها مفتاح إعداد تغيّر للتو.

    المدخلات:
        key : المفتاح الذي تغيّر (غير المرتبط بأي مهمة لا يُحدث شيئاً).

    المخرجات: أوصاف المهام التي أُعيدت جدولتها (قائمة فارغة إن لم يتأثر شيء).

    تُحفظ عدّادات المهمة وقفلها: جولة جارية لا تتداخل مع الجديدة ولا يضيع سجلها.
    """
    queue = application.job_queue
    if queue is None:
        return []
    if key == ALL_JOBS_SETTING_KEY:
        affected = None                                      # كل المهام
    elif key in JOB_SETTING_KEYS:
        affected = {JOB_SETTING_KEYS[key]}
    else:
        return []

    alert_threshold = await services.settings.get_int(ALL_JOBS_SETTING_KEY, 3)
    done: list[str] = []
    for spec in await build_job_specs(services):
        if affected is not None and spec.name not in affected:
            continue
        done.append(
            _install_job(queue, spec, registry=registry, alert_threshold=alert_threshold, keep_history=True)
        )
    logger.info("إعادة جدولة حيّة بعد تعديل %s: %s", key, ", ".join(done))
    return done


def _attach_setting_listener(
    application: Application, services: ServiceContainer, registry: JobRegistry
) -> None:
    """ربط مراقب الإعدادات بإعادة الجدولة (مرة واحدة لكل تطبيق)."""
    if application.bot_data.get("_jobs_listener_attached"):
        return
    application.bot_data["_jobs_listener_attached"] = True

    async def on_change(key: str, value: str) -> None:
        """يُستدعى بعد كل تعديل إعداد ناجح."""
        await reschedule_for_setting(application, services, key, registry=registry)
        # وجهة قناة عُدّلت ⇒ المنشورات الفاشلة/المتخطّاة بسببها (ضمن مدة الصلاحية) تعود للطابور فلا تضيع
        kind = CHANNEL_DESTINATION_KEYS.get(key)
        if kind is not None:
            await services.channels.requeue_failed(kind)

    services.settings.add_listener(on_change)


async def run_startup_recovery(services: ServiceContainer) -> dict[str, int]:
    """
    استرداد الحالة بعد إعادة التشغيل — يُستدعى مرة واحدة قبل بدء الاستقبال.

    يعالج الطلبات التي كانت «قيد الإرسال» لحظة الإغلاق (تُنقل إلى
    `submit_uncertain` لتُراجَع بدل أن تُرسل مرتين)، ويحرّر الأقفال المنتهية.

    المخرجات: عدّادات ما تم استرداده.
    """
    result = await services.orders.recover_after_restart()
    if any(result.values()):
        logger.warning("استرداد بعد إعادة التشغيل: %s", result)
    else:
        logger.info("لا توجد طلبات عالقة من تشغيل سابق")
    return result
