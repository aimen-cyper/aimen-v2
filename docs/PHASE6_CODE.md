# الكود الكامل — المرحلة 6 (المهام الدورية والمتابعة الآلية المتقدمة)

كل ما في هذا الملف منسوخ آلياً من ملفات المشروع الفعلية وقت كتابة التقرير.

> الملفات الضخمة التي تغيّر منها قسم محدود تُعرض كمقتطف موسوم بوضوح؛ وما عداها كامل.

> الملفات غير المذكورة هنا لم تتغيّر عن المراحل 1–5.

## الفهرس

**طبقة الإشراف على المهام**

- `jobs/runner.py` — 277 سطراً (جديد)
- `jobs/__init__.py` — 218 سطراً (مُحدَّث)

**المهام الجديدة**

- `jobs/provider_jobs.py` — 105 سطراً (جديد)
- `jobs/report_jobs.py` — 67 سطراً (جديد)
- `jobs/maintenance_jobs.py` — 74 سطراً (مُحدَّث)
- `jobs/order_jobs.py` — 63 سطراً (مُحدَّث)

**الفحص الجماعي لحالات الطلبات**

- `services/provider_service.py` — 525 سطراً (مُحدَّث)
- `services/order_service.py` — 1438 سطراً (مُحدَّث)
- `services/stats_service.py` — 442 سطراً (مُحدَّث)

**واجهة المراقبة في لوحة التحكم**

- `handlers/admin/system.py` — 167 سطراً (جديد)
- `handlers/admin/dashboard.py` — 133 سطراً (مُحدَّث)
- `handlers/admin/__init__.py` — 63 سطراً (مُحدَّث)
- `keyboards/admin_kb.py` — 941 سطراً (مُحدَّث)
- `texts/admin_ar.py` — 731 سطراً (مُحدَّث (مقتطف))
- `texts/templates.py` — 305 سطراً (مُحدَّث (مقتطف))

**الإعدادات والإصدار**

- `database/migrations/0005_phase6_jobs.sql` — 32 سطراً (جديد)
- `utils/datetime_utils.py` — 109 سطراً (مُحدَّث (مقتطف))
- `core/constants.py` — 44 سطراً (مُحدَّث)

**الاختبارات**

- `tests/unit/test_job_registry.py` — 58 سطراً (جديد)
- `tests/integration/test_jobs_phase6.py` — 599 سطراً (جديد)

---

## طبقة الإشراف على المهام

### `jobs/runner.py`  ·  جديد  ·  277 سطراً

الغلاف المُشرِف: منع التداخل، مهلة قصوى لكل جولة، التقاط كل استثناء إلى `error_logs` وتنبيه الأدمن عند تكرار الفشل، وسجل حالة في الذاكرة (`JobStats`/`JobRegistry`) تقرؤه شاشة المهام.

```python
"""
طبقة الإشراف على المهام الدورية (المرحلة 6).

لماذا طبقة إشراف بدل تمرير الدوال مباشرة إلى JobQueue؟
    لأن مهمة دورية بلا إشراف ثلاثة أخطار:
        1. **التداخل**: جولة لم تنتهِ وجولة جديدة تبدأ فوقها ⇒ ضغط مضاعف على
           المزود وعلى قاعدة البيانات، وفي أسوأ الحالات عمل مكرر.
        2. **التعليق**: استدعاء شبكة لا ينتهي يُجمّد المهمة إلى الأبد بصمت.
        3. **الصمت**: استثناء داخل المهمة يُطبع في اللوق فقط، فيتوقف النظام عن
           العمل أياماً دون أن يعرف أحد.

هذا الملف يعالج الثلاثة: قفل لكل مهمة يمنع التداخل، مهلة قصوى لكل جولة،
والتقاط كل استثناء وكتابته في `error_logs` مع تنبيه الأدمن بعد تكرار الفشل.
ويحتفظ بسجل حالة في الذاكرة (آخر تشغيل، المدة، النتيجة) تعرضه شاشة
«⏱ المهام الدورية» في لوحة التحكم.

لماذا السجل في الذاكرة لا في قاعدة البيانات؟
    لأنه بيانات تشغيل لحظية تُفقد عمداً عند إعادة التشغيل، وكتابتها كل بضع
    ثوانٍ تعني آلاف عمليات الكتابة يومياً بلا قيمة تاريخية. الأخطاء — وهي ما
    يستحق البقاء — تُكتب في `error_logs` فعلاً.
"""

from __future__ import annotations

import asyncio
import time
import traceback
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from telegram.ext import ContextTypes

from core.permissions import Permission
from texts import templates
from utils.datetime_utils import utc_now_iso
from utils.logging_setup import get_logger
from utils.security import sanitize

logger = get_logger(__name__)

#: نوع دالة المهمة كما تتوقعها JobQueue
JobCallback = Callable[[ContextTypes.DEFAULT_TYPE], Awaitable[None]]

#: المهلة القصوى الافتراضية لجولة واحدة (ثوانٍ) — بعدها تُلغى الجولة وتُسجَّل
DEFAULT_TIMEOUT_SECONDS = 300.0

#: عدد الإخفاقات المتتالية الافتراضي قبل تنبيه الأدمن
DEFAULT_FAILURE_ALERT_THRESHOLD = 3


@dataclass(slots=True)
class JobStats:
    """حالة مهمة دورية واحدة كما تُعرض في شاشة المهام."""

    name: str
    interval_seconds: float
    schedule_text: str = ""
    runs: int = 0
    failures: int = 0
    skipped: int = 0
    consecutive_failures: int = 0
    running: bool = False
    last_started_at: str | None = None
    last_finished_at: str | None = None
    last_success_at: str | None = None
    last_duration_ms: int | None = None
    total_duration_ms: int = 0
    last_error: str | None = None

    @property
    def average_duration_ms(self) -> int:
        """متوسط زمن الجولة بالميلي ثانية (صفر قبل أول تشغيل)."""
        completed = self.runs
        return int(self.total_duration_ms / completed) if completed else 0

    @property
    def is_healthy(self) -> bool:
        """المهمة سليمة إذا لم تفشل في آخر جولة لها."""
        return self.consecutive_failures == 0

    def as_dict(self) -> dict[str, object]:
        """تمثيل مختصر للاختبارات واللوقات."""
        return {
            "name": self.name,
            "runs": self.runs,
            "failures": self.failures,
            "skipped": self.skipped,
            "consecutive_failures": self.consecutive_failures,
            "last_duration_ms": self.last_duration_ms,
            "last_error": self.last_error,
        }


@dataclass(slots=True)
class JobRegistry:
    """
    سجل المهام المُشرَف عليها: الحالة + القفل + الدالة الملفوفة.

    يُستخدم من شاشة «⏱ المهام الدورية» للعرض ومن زر «تشغيل الآن» للتنفيذ.
    """

    stats: dict[str, JobStats] = field(default_factory=dict)
    callbacks: dict[str, JobCallback] = field(default_factory=dict)
    locks: dict[str, asyncio.Lock] = field(default_factory=dict)

    def register(
        self, name: str, *, interval_seconds: float, schedule_text: str = ""
    ) -> JobStats:
        """تسجيل مهمة جديدة (أو إعادة ضبط تسجيلها عند إعادة الجدولة)."""
        entry = JobStats(
            name=name, interval_seconds=interval_seconds, schedule_text=schedule_text
        )
        self.stats[name] = entry
        self.locks[name] = asyncio.Lock()
        return entry

    def get(self, name: str) -> JobStats | None:
        """حالة مهمة بالاسم (أو None إن لم تُجدول)."""
        return self.stats.get(name)

    def callback(self, name: str) -> JobCallback | None:
        """الدالة الملفوفة لمهمة بالاسم — يستخدمها زر «تشغيل الآن»."""
        return self.callbacks.get(name)

    def snapshot(self) -> list[JobStats]:
        """كل المهام بترتيب تسجيلها (للعرض في اللوحة)."""
        return list(self.stats.values())

    def clear(self) -> None:
        """تفريغ السجل (يُستخدم عند إعادة الجدولة وفي الاختبارات)."""
        self.stats.clear()
        self.callbacks.clear()
        self.locks.clear()


#: السجل الافتراضي الذي تستعمله الجدولة الحقيقية وشاشة اللوحة
JOB_REGISTRY = JobRegistry()


async def _record_failure(
    context: ContextTypes.DEFAULT_TYPE,
    *,
    name: str,
    stats: JobStats,
    error: BaseException,
    threshold: int,
) -> None:
    """
    تسجيل فشل جولة: سطر في `error_logs` + تنبيه الأدمن عند تكرار الفشل.

    لا يرفع هذا التسجيل أي استثناء جديد: فشلُ تسجيلِ الفشل يجب ألا يُسقط
    المهمة الدورية نفسها، فنكتفي بتسجيله في اللوق.
    """
    services = context.application.bot_data.get("services")
    if services is None:
        logger.error("المهمة %s فشلت ولا توجد خدمات في bot_data لتسجيل الخطأ", name)
        return

    message = f"فشل المهمة الدورية {name}: {error}"
    try:
        async with services.db.transaction() as tx:
            await services.repos.error_logs.log(
                tx,
                message=message,
                level="ERROR",
                source=f"job:{name}",
                error_type=type(error).__name__,
                traceback_snippet="".join(
                    traceback.format_exception(type(error), error, error.__traceback__)
                ),
            )
    except Exception as exc:                                        # noqa: BLE001
        logger.error("تعذّر كتابة خطأ المهمة %s في error_logs: %s", name, exc)

    if stats.consecutive_failures < threshold:
        return

    try:
        title, body = templates.admin_job_failing(
            job_name=name,
            failures=stats.consecutive_failures,
            error=sanitize(str(error))[:200],
        )
        async with services.db.transaction() as tx:
            await services.notifications.notify_admins(
                tx,
                permission=Permission.LOGS_VIEW,
                token=f"job:{name}:fail:{stats.consecutive_failures}",
                title=title,
                message=body,
            )
    except Exception as exc:                                        # noqa: BLE001
        logger.error("تعذّر تنبيه الأدمن بفشل المهمة %s: %s", name, exc)


def supervise(
    callback: JobCallback,
    *,
    name: str,
    registry: JobRegistry = JOB_REGISTRY,
    interval_seconds: float = 0.0,
    schedule_text: str = "",
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    failure_alert_threshold: int = DEFAULT_FAILURE_ALERT_THRESHOLD,
) -> JobCallback:
    """
    لفّ دالة مهمة دورية بحماية كاملة وتسجيلها في السجل.

    المدخلات:
        callback                : دالة المهمة الأصلية.
        name                    : اسم المهمة (يظهر في اللوحة واللوقات).
        registry                : سجل الحالة (قابل للحقن في الاختبارات).
        interval_seconds        : فترة التكرار — للعرض فقط.
        schedule_text           : وصف عربي مختصر للجدولة (مثل «كل دقيقتين»).
        timeout_seconds         : مهلة الجولة الواحدة.
        failure_alert_threshold : عدد الإخفاقات المتتالية قبل تنبيه الأدمن.

    المخرجات: دالة جاهزة لـ`JobQueue` **لا ترفع استثناءً أبداً**.
    """
    stats = registry.register(
        name, interval_seconds=interval_seconds, schedule_text=schedule_text
    )
    lock = registry.locks[name]

    async def runner(context: ContextTypes.DEFAULT_TYPE) -> None:
        """جولة واحدة محروسة: منع التداخل، مهلة قصوى، التقاط كل خطأ."""
        if lock.locked():
            stats.skipped += 1
            logger.warning(
                "تخطّي جولة %s: الجولة السابقة ما زالت تعمل (تخطّيات: %s)",
                name,
                stats.skipped,
            )
            return

        async with lock:
            stats.running = True
            stats.last_started_at = utc_now_iso()
            started = time.monotonic()
            try:
                await asyncio.wait_for(callback(context), timeout=timeout_seconds)
            except asyncio.CancelledError:
                # إيقاف البوت يُلغي المهام — ليس فشلاً، ويجب ألا يُبتلع
                stats.running = False
                logger.info("أُلغيت جولة %s أثناء الإغلاق", name)
                raise
            except Exception as exc:                                # noqa: BLE001
                stats.failures += 1
                stats.consecutive_failures += 1
                stats.last_error = sanitize(str(exc))[:300] or type(exc).__name__
                logger.exception("فشل المهمة الدورية %s", name)
                await _record_failure(
                    context,
                    name=name,
                    stats=stats,
                    error=exc,
                    threshold=failure_alert_threshold,
                )
            else:
                stats.consecutive_failures = 0
                stats.last_error = None
                stats.last_success_at = utc_now_iso()
            finally:
                duration_ms = int((time.monotonic() - started) * 1000)
                stats.runs += 1
                stats.last_duration_ms = duration_ms
                stats.total_duration_ms += duration_ms
                stats.last_finished_at = utc_now_iso()
                stats.running = False
                if duration_ms > timeout_seconds * 500:             # نصف المهلة
                    logger.warning(
                        "جولة %s استغرقت %sms — قريبة من المهلة القصوى", name, duration_ms
                    )

    runner.__name__ = f"supervised_{name}"
    registry.callbacks[name] = runner
    return runner
```

### `jobs/__init__.py`  ·  مُحدَّث  ·  218 سطراً

الجدولة الكاملة: 8 مهام متكررة + مهمتان يوميتان بتوقيت Asia/Aden، كلها ملفوفة بـ`supervise`، وفتراتها من جدول الإعدادات.

```python
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

from telegram.ext import Application

from jobs.maintenance_jobs import auto_close_tickets, database_maintenance, expire_old_payments
from jobs.notification_jobs import dispatch_notifications
from jobs.order_jobs import alert_stuck_orders, check_active_orders, submit_pending_orders
from jobs.provider_jobs import refresh_provider_balances, watch_provider_health
from jobs.report_jobs import send_admin_daily_digest
from jobs.runner import JOB_REGISTRY, JobRegistry, supervise
from services import ServiceContainer
from utils.datetime_utils import APP_TIMEZONE
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: الحد الأدنى المقبول لأي فترة تكرار (حماية من قيمة إعداد خاطئة تُغرق النظام)
MIN_INTERVAL_SECONDS = 5

#: مهلة الجولة الواحدة لكل نوع مهمة (ثوانٍ) — بعدها تُلغى الجولة وتُسجَّل كفشل
FAST_JOB_TIMEOUT = 120.0
SLOW_JOB_TIMEOUT = 600.0

__all__ = ["schedule_jobs", "run_startup_recovery", "JOB_REGISTRY", "JOB_LABELS"]

#: أسماء عربية للمهام تُعرض في لوحة التحكم (الاسم التقني يبقى للّوقات)
JOB_LABELS: dict[str, str] = {
    "notifications_dispatch": "📨 إرسال الإشعارات",
    "orders_submit": "📤 إرسال الطلبات للمزود",
    "orders_check": "🔄 متابعة حالة الطلبات",
    "payments_expire": "⌛️ إنهاء صلاحية طلبات الشحن",
    "tickets_auto_close": "🎫 إغلاق التذاكر الراكدة",
    "orders_stuck_alert": "⏰ تنبيه الطلبات المتوقفة",
    "providers_balance": "💵 فحص أرصدة المزودين",
    "providers_health": "🩺 مراقبة صحة المزودين",
    "admin_daily_digest": "📊 الملخص اليومي",
    "database_maintenance": "🗄 صيانة قاعدة البيانات",
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
    """
    queue = application.job_queue
    if queue is None:
        raise RuntimeError(
            "JobQueue غير متاح — ثبّت الحزمة بالشكل: pip install 'python-telegram-bot[job-queue]'"
        )

    registry.clear()
    alert_threshold = await services.settings.get_int("job_failure_alert_threshold", 3)

    repeating = [
        (
            "notifications_dispatch",
            dispatch_notifications,
            await _interval(services, "notification_dispatch_seconds", 10),
            5.0,
            FAST_JOB_TIMEOUT,
        ),
        (
            "orders_submit",
            submit_pending_orders,
            await _interval(services, "order_submit_interval_seconds", 30),
            12.0,
            SLOW_JOB_TIMEOUT,
        ),
        (
            "orders_check",
            check_active_orders,
            await _interval(services, "order_check_interval_seconds", 120),
            25.0,
            SLOW_JOB_TIMEOUT,
        ),
        ("payments_expire", expire_old_payments, 900.0, 60.0, FAST_JOB_TIMEOUT),
        ("tickets_auto_close", auto_close_tickets, 3600.0, 120.0, FAST_JOB_TIMEOUT),
        ("orders_stuck_alert", alert_stuck_orders, 3600.0, 300.0, FAST_JOB_TIMEOUT),
        (
            "providers_balance",
            refresh_provider_balances,
            await _interval(
                services,
                "provider_balance_check_minutes",
                30,
            )
            * 60.0,
            90.0,
            SLOW_JOB_TIMEOUT,
        ),
        (
            "providers_health",
            watch_provider_health,
            await _interval(services, "provider_health_watch_minutes", 10) * 60.0,
            150.0,
            SLOW_JOB_TIMEOUT,
        ),
    ]

    names: list[str] = []
    for name, callback, interval, first, timeout in repeating:
        supervised = supervise(
            callback,
            name=name,
            registry=registry,
            interval_seconds=interval,
            schedule_text=_every_text(interval),
            timeout_seconds=timeout,
            failure_alert_threshold=alert_threshold,
        )
        queue.run_repeating(supervised, interval=interval, first=first, name=name)
        names.append(f"{name}({int(interval)}s)")

    daily = [
        (
            "admin_daily_digest",
            send_admin_daily_digest,
            await services.settings.get_int("admin_digest_hour", 21),
        ),
        (
            "database_maintenance",
            database_maintenance,
            await services.settings.get_int("db_maintenance_hour", 4),
        ),
    ]
    for name, callback, hour in daily:
        run_at = _daily_time(hour)
        supervised = supervise(
            callback,
            name=name,
            registry=registry,
            interval_seconds=86400.0,
            schedule_text=f"يومياً {run_at.strftime('%H:%M')}",
            timeout_seconds=SLOW_JOB_TIMEOUT,
            failure_alert_threshold=alert_threshold,
        )
        queue.run_daily(supervised, time=run_at, name=name)
        names.append(f"{name}(daily {run_at.strftime('%H:%M')})")

    logger.info("تمت جدولة %s مهمة دورية: %s", len(names), ", ".join(names))
    return names


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
```

---

## المهام الجديدة

### `jobs/provider_jobs.py`  ·  جديد  ·  105 سطراً

فحص أرصدة المزودين دورياً (مع تنبيه الانخفاض) ومراقبة صحتهم وإعادة تفعيل المتعثر فور تعافيه.

```python
"""
مهام مراقبة المزودين الدورية (المرحلة 6).

لماذا؟
    المزود هو الطرف الوحيد في النظام الذي لا نتحكم به: رصيده ينفد، وواجهته
    تتعطل، ومفتاحه قد يُلغى من طرفه. بلا مراقبة دورية نكتشف ذلك من شكوى عميل.

مهمتان:
    refresh_provider_balances : تقرأ رصيدنا لدى كل مزود مفعّل وتحفظه مع لقطة
                                تاريخية، وتُطلق تنبيه «الرصيد منخفض» عند الحاجة.
    watch_provider_health     : تتابع المزودين المتعثرين — تختبرهم بلطف، وتعيد
                                تفعيل الإرسال فور تعافيهم مع إشعار الأدمن.

كلتاهما لا تُسقط بقية المزودين عند فشل واحد: الخطأ يُسجَّل ويستمر الدوران.
"""

from __future__ import annotations

from telegram.ext import ContextTypes

from core.exceptions import ProviderError
from core.permissions import Permission
from database.models import Provider
from texts import templates
from utils.datetime_utils import is_past
from utils.logging_setup import get_logger

logger = get_logger(__name__)


async def refresh_provider_balances(context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    تحديث رصيدنا لدى كل مزود مفعّل (ولقطة تاريخية + تنبيه انخفاض).

    التنبيه نفسه داخل `ProviderService.check_balance` فلا يُكرَّر منطقه هنا.

    المخرجات: عدد المزودين الذين تم تحديث رصيدهم بنجاح.
    """
    services = context.application.bot_data["services"]
    providers: list[Provider] = await services.providers.list_all(active_only=True)
    updated = 0

    for provider in providers:
        health = await services.providers.health(provider)
        if not health.is_usable:
            logger.info("تخطّي فحص رصيد %s: %s", provider.name, health.reason)
            continue
        try:
            balance = await services.providers.check_balance(provider)
        except ProviderError as exc:
            # فشل مزود واحد لا يمنع فحص البقية — والفشل مسجَّل في provider_requests
            logger.warning("تعذّر قراءة رصيد المزود %s: %s", provider.name, exc)
            continue
        updated += 1
        logger.info(
            "رصيد المزود %s: %s %s", provider.name, balance.amount_units, balance.currency
        )

    return updated


async def watch_provider_health(context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    متابعة المزودين المتعثرين وإعادة تفعيلهم عند التعافي.

    المزود يُوقَف مؤقتاً تلقائياً بعد عدد أخطاء متتالية (`_record_failure`).
    هذه المهمة تنتظر انتهاء مدة الإيقاف ثم تختبره باستدعاء خفيف (قراءة الرصيد):
        • نجح  ⇒ `record_success` يصفّر العدّاد ويمسح الإيقاف + إشعار «تعافى».
        • فشل  ⇒ يُسجَّل الفشل كالمعتاد ويبقى موقوفاً للدورة القادمة.

    المخرجات: عدد المزودين الذين تعافوا في هذه الجولة.
    """
    services = context.application.bot_data["services"]
    providers: list[Provider] = await services.providers.list_all(active_only=True)
    recovered = 0

    for provider in providers:
        failures = int(provider.consecutive_failures or 0)
        if failures == 0:
            continue
        if provider.disabled_until and not is_past(provider.disabled_until):
            logger.info("المزود %s ما زال في مدة الإيقاف المؤقت", provider.name)
            continue

        try:
            await services.providers.check_balance(provider)
        except ProviderError as exc:
            logger.warning("المزود %s ما زال متعثراً: %s", provider.name, exc)
            continue

        recovered += 1
        title, message = templates.admin_provider_recovered(
            provider_name=provider.name, failures=failures
        )
        async with services.db.transaction() as tx:
            await services.notifications.notify_admins(
                tx,
                permission=Permission.PROVIDERS_VIEW,
                token=f"provider:{provider.id}:recovered:{failures}",
                title=title,
                message=message,
            )
        logger.info("تعافى المزود %s بعد %s أخطاء متتالية", provider.name, failures)

    return recovered
```

### `jobs/report_jobs.py`  ·  جديد  ·  67 سطراً

الملخص اليومي للأدمن عبر طابور الإشعارات، مرة واحدة لكل يوم.

```python
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
```

### `jobs/maintenance_jobs.py`  ·  مُحدَّث  ·  74 سطراً

أُضيفت `database_maintenance`: حذف مفاتيح منع التكرار المنتهية + wal_checkpoint + optimize، بلا أي حذف لبيانات تاريخية.

```python
"""
مهام الصيانة الدورية.

    expire_old_payments  : إنهاء صلاحية طلبات الشحن التي تجاوزت مهلة المراجعة.
    auto_close_tickets   : إغلاق تذاكر الدعم الراكدة.
    database_maintenance : صيانة تقنية يومية لقاعدة البيانات (المرحلة 6).

الثلاثة تمنع تراكم ما لا قيمة له، واثنتان منها تُشعران صاحب الشأن بما حدث
بدل أن «يختفي» طلبه بصمت.

ملاحظة مهمة: صيانة قاعدة البيانات **لا تحذف أي بيانات تاريخية** — لا طلبات
ولا حركات مالية ولا تذاكر ولا سجلات تدقيق. تحذف فقط مفاتيح منع التكرار
(`idempotency_keys`) بعد انتهاء صلاحيتها، وهي مفاتيح تقنية مؤقتة بطبيعتها.
"""

from __future__ import annotations

from telegram.ext import ContextTypes

from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: عدد طلبات الشحن التي تُفحص صلاحيتها في الجولة الواحدة
EXPIRE_BATCH = 50


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
        2. `PRAGMA wal_checkpoint(TRUNCATE)` لتقليص ملف الـWAL المتضخم.
        3. `PRAGMA optimize` لتحديث إحصاءات المخطط فتبقى الاستعلامات سريعة.

    ما **لا** تفعله: أي حذف لبيانات تاريخية، وأي `VACUUM` تلقائي (يقفل القاعدة
    مدة طويلة؛ يبقى قراراً يدوياً في أدوات الصيانة).

    المخرجات: عدّادات ما جرى (لتسجيلها في اللوق والاختبارات).
    """
    services = context.application.bot_data["services"]
    async with services.db.transaction() as tx:
        removed_keys = await services.repos.idempotency.cleanup_expired(tx)

    checkpointed = 0
    try:
        await services.db.execute_raw("PRAGMA wal_checkpoint(TRUNCATE)")
        await services.db.execute_raw("PRAGMA optimize")
        checkpointed = 1
    except Exception as exc:                                        # noqa: BLE001
        # الصيانة التقنية ليست حرجة: نسجّلها ولا نُسقط المهمة على بقية خطواتها
        logger.warning("تعذّرت صيانة ملف قاعدة البيانات: %s", exc)

    result = {"idempotency_keys_removed": removed_keys, "checkpoint": checkpointed}
    if removed_keys:
        logger.info("صيانة القاعدة: %s", result)
    return result
```

### `jobs/order_jobs.py`  ·  مُحدَّث  ·  63 سطراً

حجم دفعتَي الإرسال والفحص صار من الإعدادات ضمن حدود آمنة.

```python
"""
مهام دورة حياة الطلب: الإرسال للمزود، فحص الحالة، تنبيه الطلبات العالقة.

منطق العمل كله داخل `OrderService` (المرحلة 2) — هذه الملفات مجرد جدولة
زمنية تستدعيه. الفائدة: يبقى المنطق قابلاً للاختبار بلا تيليجرام ولا مؤقتات.
"""

from __future__ import annotations

from telegram.ext import ContextTypes

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
```

---

## الفحص الجماعي لحالات الطلبات

### `services/provider_service.py`  ·  مُحدَّث  ·  525 سطراً

`fetch_multi_status(provider, orders)`: استعلام واحد عن حالات عدة طلبات مع تسجيله في `provider_requests` وتصنيف أخطائه كبقية الاستدعاءات.

```python
"""
خدمة المزودين: إدارة بياناتهم، وتشفير مفاتيحهم، والاتصال بهم بأمان.

قواعد صارمة:
    • مفتاح API يُخزَّن مشفّراً، ولا يُفك إلا لحظة الاستدعاء داخل هذه الخدمة.
    • لا يظهر المفتاح في أي سجل أو رسالة خطأ (كل النصوص تمر على `sanitize`).
    • كل استدعاء خارجي يُسجَّل في `provider_requests` بنجاحه أو فشله ومدته.
    • قاطع دائرة: بعد عدد أخطاء متتالية يُعطَّل المزود مؤقتاً ويُنبَّه الأدمن.
    • لا تُفتح معاملة قاعدة بيانات أثناء انتظار الشبكة.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Sequence

from core.enums import ProviderAction
from core.exceptions import (
    ProviderError,
    ProviderPermanentError,
    ProviderTemporaryError,
    ProviderUncertainError,
)
from core.permissions import Permission
from database.database import Database
from database.models import Order, Provider, Service, User
from database.repositories import Repositories
from integrations.providers.base import (
    ProviderBalance,
    ProviderClient,
    ProviderOrderResult,
    ProviderServiceItem,
    ProviderStatusResult,
)
from integrations.providers.registry import create_client, is_supported
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.notification_service import NotificationService
from services.settings_service import SettingsService
from texts import templates
from utils.datetime_utils import is_past, iso_plus_seconds
from utils.logging_setup import get_logger
from utils.security import SecretBox, secret_hint
from utils.validators import clean_text, validate_url

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    """حالة صحة مزود كما تُعرض في لوحة الأدمن."""

    provider: Provider
    is_usable: bool
    reason: str


class ProviderService:
    """كل تعامل مع مزودي الخدمات يمر من هنا."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        audit: AuditService,
        auth: AuthService,
        notifications: NotificationService,
        secret_box: SecretBox,
    ) -> None:
        """تهيئة الخدمة مع صندوق التشفير المسؤول عن مفاتيح المزودين."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.audit = audit
        self.auth = auth
        self.notifications = notifications
        self.secret_box = secret_box

    # ------------------------------- القراءة ------------------------------ #

    async def get(self, provider_id: int) -> Provider | None:
        """جلب مزود بالمعرف."""
        return await self.repos.providers.get(provider_id)

    async def list_all(self, *, active_only: bool = False) -> list[Provider]:
        """قائمة المزودين (كلهم أو المفعّلون فقط)."""
        return await self.repos.providers.list_all(active_only=active_only)

    async def health(self, provider: Provider) -> ProviderHealth:
        """
        تقييم جاهزية المزود للاستخدام الآن.

        المخرجات: كائن يوضح هل يمكن الإرسال إليه ولماذا لا، بصيغة عربية للعرض.
        """
        if not provider.is_active:
            return ProviderHealth(provider, False, "المزود معطّل يدوياً")
        if provider.disabled_until and not is_past(provider.disabled_until):
            return ProviderHealth(provider, False, "المزود موقوف مؤقتاً بعد أخطاء متتالية")
        if not is_supported(provider.api_type):
            return ProviderHealth(provider, False, f"نوع API غير مدعوم: {provider.api_type}")
        return ProviderHealth(provider, True, "جاهز")

    async def is_usable(self, provider: Provider) -> bool:
        """هل يمكن إرسال طلبات لهذا المزود الآن؟"""
        return (await self.health(provider)).is_usable

    # ------------------------------ الإدارة ------------------------------- #

    async def create_provider(
        self,
        actor: User,
        *,
        name: str,
        api_url: str,
        api_key: str,
        api_type: str = "perfect_panel",
        currency: str = "USD",
        timeout_seconds: int = 30,
    ) -> Provider:
        """
        إضافة مزود جديد مع تشفير مفتاحه قبل التخزين.

        الاستثناءات: PermissionDeniedError · ValidationError · EncryptionError
        """
        await self.auth.require_permission(actor, Permission.PROVIDERS_CREATE, context="provider.create")
        clean_name = clean_text(name, field="اسم المزود", max_length=60, min_length=2)
        clean_gateway = validate_url(api_url)
        key = (api_key or "").strip()
        if len(key) < 8:
            raise ProviderError(
                "مفتاح API قصير جداً", user_message="❌ مفتاح API غير صالح."
            )

        async with self.db.transaction() as tx:
            provider = await self.repos.providers.create(
                tx,
                name=clean_name,
                api_url=clean_gateway,
                api_key_enc=self.secret_box.encrypt(key),
                api_key_hint=secret_hint(key),
                api_type=api_type,
                currency=currency,
                timeout_seconds=timeout_seconds,
            )
            await self.audit.log(
                tx,
                action="providers.create",
                admin_id=actor.id,
                target_type="provider",
                target_id=provider.id,
                after={"name": clean_name, "api_url": clean_gateway, "api_type": api_type},
            )
        logger.info("أضاف الأدمن %s المزود %s (%s)", actor.id, provider.id, clean_name)
        return provider

    async def update_api_key(self, actor: User, provider_id: int, new_key: str) -> bool:
        """
        تحديث مفتاح API لمزود (يُخزَّن مشفّراً، ولا يُسجَّل في أي مكان).

        الاستثناءات: PermissionDeniedError · ProviderError
        """
        await self.auth.require_permission(
            actor, Permission.PROVIDERS_KEY_UPDATE, context=f"provider:{provider_id}"
        )
        key = (new_key or "").strip()
        if len(key) < 8:
            raise ProviderError("مفتاح API قصير جداً", user_message="❌ مفتاح API غير صالح.")

        async with self.db.transaction() as tx:
            changed = await self.repos.providers.update_fields(
                tx,
                provider_id,
                api_key_enc=self.secret_box.encrypt(key),
                api_key_hint=secret_hint(key),
            )
            if changed:
                # لا نُسجّل المفتاح نفسه — فقط أن التغيير حدث ومن نفّذه
                await self.audit.log(
                    tx,
                    action="providers.key.update",
                    admin_id=actor.id,
                    target_type="provider",
                    target_id=provider_id,
                    after={"api_key_hint": secret_hint(key)},
                )
        return changed

    async def set_active(self, actor: User, provider_id: int, active: bool) -> bool:
        """تفعيل أو تعطيل مزود يدوياً."""
        await self.auth.require_permission(
            actor, Permission.PROVIDERS_UPDATE, context=f"provider:{provider_id}"
        )
        async with self.db.transaction() as tx:
            changed = await self.repos.providers.set_active(tx, provider_id, active)
            if changed:
                await self.audit.log(
                    tx,
                    action="providers.update",
                    admin_id=actor.id,
                    target_type="provider",
                    target_id=provider_id,
                    after={"is_active": active},
                )
        return changed

    # ------------------------------ الاتصال ------------------------------- #

    def client_for(self, provider: Provider) -> ProviderClient:
        """
        بناء عميل اتصال للمزود بعد فك تشفير مفتاحه.

        الاستثناءات:
            EncryptionError : المفتاح المخزَّن لا يُفك بمفتاح التشفير الحالي.
            ProviderError   : نوع API غير مدعوم.
        """
        api_key = self.secret_box.decrypt(provider.api_key_enc)
        return create_client(
            api_type=provider.api_type,
            api_url=provider.api_url,
            api_key=api_key,
            timeout_seconds=provider.timeout_seconds,
        )

    async def _log_request(
        self,
        *,
        provider: Provider,
        action: str,
        is_success: bool,
        started: float,
        request_summary: str,
        response_snippet: str,
        error_type: str | None = None,
        order_id: int | None = None,
        secrets: tuple[str, ...] = (),
    ) -> None:
        """تسجيل استدعاء المزود في قاعدة البيانات بعد تنقيته من الأسرار."""
        duration_ms = int((time.monotonic() - started) * 1000)
        async with self.db.transaction() as tx:
            await self.repos.provider_requests.log(
                tx,
                provider_id=provider.id,
                action=action,
                is_success=is_success,
                order_id=order_id,
                request_summary=request_summary,
                response_snippet=response_snippet,
                duration_ms=duration_ms,
                error_type=error_type,
                secrets=secrets,
            )

    async def _record_success(self, provider: Provider) -> None:
        """تصفير عدّاد الأخطاء بعد نجاح الاتصال."""
        async with self.db.transaction() as tx:
            await self.repos.providers.record_success(tx, provider.id)

    async def _record_failure(self, provider: Provider, error: str) -> int:
        """
        تسجيل خطأ متتالٍ، وتعطيل المزود مؤقتاً عند بلوغ الحد، مع تنبيه الأدمن.

        المخرجات: عدد الأخطاء المتتالية بعد هذا الخطأ.
        """
        threshold = await self.settings.get_int("provider_failure_threshold", 5)
        disable_minutes = await self.settings.get_int("provider_disable_minutes", 15)

        async with self.db.transaction() as tx:
            current = await self.repos.providers.record_failure(tx, provider.id, error)
            if current >= threshold:
                await self.repos.providers.update_fields(
                    tx, provider.id, disabled_until=iso_plus_seconds(disable_minutes * 60)
                )
                title, message = templates.admin_provider_disabled(
                    provider_name=provider.name, failures=current, minutes=disable_minutes
                )
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.PROVIDERS_VIEW,
                    token=f"provider:{provider.id}:disabled:{current}",
                    title=title,
                    message=message,
                )
                logger.error(
                    "تعطيل مؤقت للمزود %s بعد %s أخطاء متتالية", provider.name, current
                )
        return current

    # ------------------------------ العمليات ------------------------------ #

    async def submit_order(self, provider: Provider, service: Service, order: Order) -> ProviderOrderResult:
        """
        إرسال طلب إلى المزود.

        المخرجات: نتيجة فيها رقم الطلب عند المزود.

        الاستثناءات:
            ProviderTemporaryError  : فشل مؤقت — يُعاد المحاولة لاحقاً.
            ProviderUncertainError  : نتيجة غير مؤكدة — ممنوع إعادة الإرسال آلياً.
            ProviderPermanentError  : رفض نهائي — فشل الطلب واسترجاع المبلغ.
        """
        client = self.client_for(provider)
        summary = f"add service={service.provider_service_id} quantity={order.quantity} link={order.link}"
        started = time.monotonic()
        try:
            result = await client.add_order(
                provider_service_id=service.provider_service_id,
                link=order.link,
                quantity=order.quantity,
            )
        except ProviderUncertainError as exc:
            await self._log_request(
                provider=provider, action=ProviderAction.ADD, is_success=False, started=started,
                request_summary=summary, response_snippet=str(exc),
                error_type=type(exc).__name__, order_id=order.id, secrets=client.secrets(),
            )
            await self._record_failure(provider, str(exc))
            raise
        except ProviderError as exc:
            await self._log_request(
                provider=provider, action=ProviderAction.ADD, is_success=False, started=started,
                request_summary=summary, response_snippet=str(exc),
                error_type=type(exc).__name__, order_id=order.id, secrets=client.secrets(),
            )
            await self._record_failure(provider, str(exc))
            raise
        finally:
            await client.close()

        if not result.provider_order_id:
            raise ProviderPermanentError("المزود لم يُرجع رقم طلب صالحاً")

        await self._log_request(
            provider=provider, action=ProviderAction.ADD, is_success=True, started=started,
            request_summary=summary, response_snippet=str(result.raw)[:500],
            order_id=order.id, secrets=client.secrets(),
        )
        await self._record_success(provider)
        return result

    async def fetch_status(self, provider: Provider, order: Order) -> ProviderStatusResult:
        """
        الاستعلام عن حالة طلب لدى المزود.

        الاستثناءات: ProviderTemporaryError · ProviderPermanentError
        """
        if not order.provider_order_id:
            raise ProviderPermanentError(f"الطلب #{order.id} بلا رقم عند المزود")

        client = self.client_for(provider)
        started = time.monotonic()
        try:
            result = await client.get_order_status(order.provider_order_id)
        except ProviderError as exc:
            await self._log_request(
                provider=provider, action=ProviderAction.STATUS, is_success=False, started=started,
                request_summary=f"status order={order.provider_order_id}", response_snippet=str(exc),
                error_type=type(exc).__name__, order_id=order.id, secrets=client.secrets(),
            )
            await self._record_failure(provider, str(exc))
            raise
        finally:
            await client.close()

        await self._log_request(
            provider=provider, action=ProviderAction.STATUS, is_success=True, started=started,
            request_summary=f"status order={order.provider_order_id}",
            response_snippet=str(result.raw)[:500], order_id=order.id, secrets=client.secrets(),
        )
        await self._record_success(provider)
        return result

    async def fetch_multi_status(
        self, provider: Provider, orders: Sequence[Order]
    ) -> dict[str, ProviderStatusResult]:
        """
        الاستعلام عن حالة عدة طلبات لدى مزود واحد في **استدعاء واحد**.

        لماذا؟ فحص 20 طلباً فردياً = 20 طلب HTTP كل دقيقتين، وهو ما يستنزف حدود
        المزود ويبطئ الجولة. معيار Perfect Panel يدعم `orders=1,2,3` فنستفيد منه،
        والمزود الذي لا يدعمه يرجع تلقائياً للفحص الفردي (التطبيق الافتراضي في
        `ProviderClient.get_multi_status`).

        المخرجات: قاموس {رقم الطلب لدى المزود: نتيجة الحالة} — قد ينقص منه ما لم
                  يُجب عنه المزود، والمستدعي يتولى فحص الناقص فردياً.

        الاستثناءات: ProviderTemporaryError · ProviderPermanentError
        """
        provider_order_ids = [
            order.provider_order_id for order in orders if order.provider_order_id
        ]
        if not provider_order_ids:
            return {}

        client = self.client_for(provider)
        started = time.monotonic()
        try:
            results = await client.get_multi_status(provider_order_ids)
        except ProviderError as exc:
            await self._log_request(
                provider=provider, action=ProviderAction.STATUS, is_success=False, started=started,
                request_summary=f"multi-status count={len(provider_order_ids)}",
                response_snippet=str(exc), error_type=type(exc).__name__,
                secrets=client.secrets(),
            )
            await self._record_failure(provider, str(exc))
            raise
        finally:
            await client.close()

        await self._log_request(
            provider=provider, action=ProviderAction.STATUS, is_success=True, started=started,
            request_summary=f"multi-status count={len(provider_order_ids)}",
            response_snippet=f"answered={len(results)}/{len(provider_order_ids)}",
            secrets=client.secrets(),
        )
        await self._record_success(provider)
        return results

    async def check_balance(self, provider: Provider) -> ProviderBalance:
        """
        قراءة رصيدنا لدى المزود وتحديثه في قاعدة البيانات مع لقطة تاريخية.

        يُرسل تنبيهاً للأدمن إذا نزل الرصيد تحت الحد المحدد.
        """
        client = self.client_for(provider)
        started = time.monotonic()
        try:
            balance = await client.get_balance()
        except ProviderError as exc:
            await self._log_request(
                provider=provider, action=ProviderAction.BALANCE, is_success=False, started=started,
                request_summary="balance", response_snippet=str(exc),
                error_type=type(exc).__name__, secrets=client.secrets(),
            )
            await self._record_failure(provider, str(exc))
            raise
        finally:
            await client.close()

        async with self.db.transaction() as tx:
            await self.repos.providers.update_balance(
                tx, provider.id, balance.amount_units, currency=balance.currency
            )
            await self.repos.providers.add_balance_snapshot(
                tx, provider.id, balance.amount_units, currency=balance.currency
            )

        threshold = provider.low_balance_threshold_units or await self.settings.get_int(
            "provider_low_balance_alert_units", 0
        )
        if threshold and balance.amount_units < threshold:
            symbol = await self.settings.money_symbol()
            title, message = templates.admin_provider_low_balance(
                provider_name=provider.name, balance_units=balance.amount_units, symbol=symbol
            )
            async with self.db.transaction() as tx:
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.PROVIDERS_VIEW,
                    token=f"provider:{provider.id}:low:{balance.amount_units}",
                    title=title,
                    message=message,
                )

        await self._log_request(
            provider=provider, action=ProviderAction.BALANCE, is_success=True, started=started,
            request_summary="balance", response_snippet=f"amount_units={balance.amount_units}",
            secrets=client.secrets(),
        )
        await self._record_success(provider)
        return balance

    async def fetch_services(self, actor: User, provider: Provider) -> list[ProviderServiceItem]:
        """
        جلب قائمة خدمات المزود (تمهيداً للاستيراد في المرحلة 5).

        الاستثناءات: PermissionDeniedError · ProviderError
        """
        await self.auth.require_permission(
            actor, Permission.SERVICES_SYNC, context=f"provider:{provider.id}"
        )
        client = self.client_for(provider)
        started = time.monotonic()
        try:
            items = await client.get_services()
        except ProviderError as exc:
            await self._log_request(
                provider=provider, action=ProviderAction.SERVICES, is_success=False, started=started,
                request_summary="services", response_snippet=str(exc),
                error_type=type(exc).__name__, secrets=client.secrets(),
            )
            await self._record_failure(provider, str(exc))
            raise
        finally:
            await client.close()

        await self._log_request(
            provider=provider, action=ProviderAction.SERVICES, is_success=True, started=started,
            request_summary="services", response_snippet=f"count={len(items)}", secrets=client.secrets(),
        )
        await self._record_success(provider)
        return items

    async def test_connection(self, actor: User, provider_id: int) -> tuple[bool, str]:
        """
        اختبار اتصال المزود من لوحة الأدمن.

        المخرجات: (نجح؟، رسالة عربية للعرض) — لا تحتوي الرسالة أي سر.
        """
        await self.auth.require_permission(
            actor, Permission.PROVIDERS_TEST, context=f"provider:{provider_id}"
        )
        provider = await self.repos.providers.get(provider_id)
        if provider is None:
            return False, "المزود غير موجود."
        try:
            balance = await self.check_balance(provider)
        except ProviderTemporaryError as exc:
            return False, f"فشل مؤقت في الاتصال: {exc.user_message}"
        except ProviderError as exc:
            return False, f"فشل الاتصال: {exc.user_message}"
        symbol = provider.currency or "USD"
        return True, f"الاتصال ناجح ✅ — الرصيد: {balance.amount_units / 10_000:.4f} {symbol}"
```

### `services/order_service.py`  ·  مُحدَّث  ·  1438 سطراً

`process_due_orders` تُجمّع الطلبات حسب المزود وتستعلم دفعة واحدة، مع `_sync_provider_group` و`_apply_status` ومسار احتياطي فردي لما لم يُجب عنه المزود.

```python
"""
خدمة الطلبات — قلب النظام.

المسؤوليات:
    • إنشاء الطلب: تحقق كامل ثم خصم الرصيد وإنشاء الطلب وإشعار المستخدم في معاملة واحدة.
    • إرسال الطلبات للمزود عبر عمّال (workers) مع حجز آمن يمنع المعالجة المزدوجة.
    • متابعة الحالة دورياً حتى الحالة النهائية.
    • الاسترجاع الآمن عند الفشل أو الإلغاء أو التنفيذ الجزئي.
    • أدوات الأدمن: إلغاء، ربط رقم مزود، تأكيد فشل، تجاوز حالة (مع تدقيق إجباري).

قواعد لا تُكسر:
    • كل تغيير حالة يمر عبر `core.order_state` (جدول انتقالات) **و** تحديث مشروط في
      قاعدة البيانات (`expected_statuses`) — فلا سباق ولا كتابة فوق عمل جهة أخرى.
    • كل استرجاع يمر عبر `WalletService` ويُسجَّل كحركة مالية بمرجع فريد.
    • لا إعادة إرسال تلقائي عند نتيجة غير مؤكدة (منعاً لطلب مزدوج عند المزود).
    • لا تُفتح معاملة قاعدة بيانات أثناء انتظار شبكة المزود.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from core.constants import MAX_SUBMIT_ATTEMPTS, ORDER_CHECK_BACKOFF, ORDER_LOCK_SECONDS
from core.enums import ActorType, NotificationType, OrderStatus
from core.exceptions import (
    DuplicateOperationError,
    InvalidStateTransitionError,
    OrderError,
    ProviderError,
    ProviderInsufficientFundsError,
    ProviderPermanentError,
    ProviderTemporaryError,
    ProviderUncertainError,
    RateLimitedError,
    ServiceNotAvailableError,
    ValidationError,
)
from core.money import format_units, partial_refund_units
from core.order_state import (
    assert_transition,
    can_transition,
    is_final,
    map_provider_status,
)
from core.permissions import Permission
from database.database import Database, Tx
from database.models import Order, Provider, Service, User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.catalog_service import CatalogService
from services.notification_service import NotificationService
from services.provider_service import ProviderService
from services.settings_service import SettingsService
from services.wallet_service import WalletService
from texts import templates
from utils.datetime_utils import day_bounds_utc, iso_minus_days, iso_plus_seconds, parse_iso, utc_now
from utils.logging_setup import get_logger
from utils.security import new_token, sanitize
from utils.validators import validate_link

logger = get_logger(__name__)


@dataclass(slots=True)
class BatchReport:
    """حصيلة جولة معالجة (إرسال أو فحص حالات)."""

    claimed: int = 0
    succeeded: int = 0
    retried: int = 0
    failed: int = 0
    uncertain: int = 0
    unchanged: int = 0
    completed: int = 0
    details: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, int]:
        """تحويل الحصيلة إلى قاموس للتسجيل."""
        return {
            "claimed": self.claimed,
            "succeeded": self.succeeded,
            "retried": self.retried,
            "failed": self.failed,
            "uncertain": self.uncertain,
            "unchanged": self.unchanged,
            "completed": self.completed,
        }


class OrderService:
    """دورة حياة الطلب كاملة من الإنشاء حتى الحالة النهائية."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        wallet: WalletService,
        catalog: CatalogService,
        providers: ProviderService,
        notifications: NotificationService,
        audit: AuditService,
        auth: AuthService,
    ) -> None:
        """تهيئة الخدمة بكل الاعتماديات التي تحتاجها."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.wallet = wallet
        self.catalog = catalog
        self.providers = providers
        self.notifications = notifications
        self.audit = audit
        self.auth = auth

    # ===================================================================== #
    #                              الإنشاء                                  #
    # ===================================================================== #

    async def create_order(
        self,
        user: User,
        *,
        service_id: int,
        link: str,
        quantity: str | int,
        client_request_id: str | None = None,
    ) -> Order:
        """
        إنشاء طلب جديد: تحقق كامل ← خصم الرصيد ← إنشاء الطلب ← إشعار — كلها معاملة واحدة.

        المدخلات:
            client_request_id : مفتاح المستخدم لمنع التكرار عند الضغط المزدوج.
                                إذا تكرر نفس المفتاح يُعاد الطلب الأول نفسه دون خصم جديد.

        المخرجات: الطلب بعد إنشائه (حالته `pending`).

        الاستثناءات:
            UserBannedError · MaintenanceModeError : الحساب محظور أو النظام في صيانة.
            ServiceNotAvailableError               : الخدمة أو مزودها غير متاح.
            QuantityOutOfRangeError · InvalidLinkError · InvalidAmountError
            RateLimitedError                       : تجاوز الحد اليومي للطلبات.
            DuplicateOperationError                : طلب مطابق خلال نافذة التكرار.
            InsufficientBalanceError               : الرصيد لا يكفي (لا يُنشأ الطلب أصلاً).
        """
        await self.auth.guard(user)

        # 1) مفتاح منع التكرار: إن تكرر نفس المفتاح نُعيد الطلب الأصلي دون أي خصم جديد
        request_id = (client_request_id or f"u{user.id}:{new_token(8)}").strip()[:64]
        existing = await self.repos.orders.get_by_client_request_id(request_id)
        if existing is not None:
            logger.info("إعادة استخدام الطلب %s لنفس مفتاح الطلب %s", existing.id, request_id)
            return existing

        # 2) الخدمة والمزود
        service = await self.catalog.get_available_service(service_id)
        provider = await self.repos.providers.get(service.provider_id)
        if provider is None:
            raise ServiceNotAvailableError(f"مزود الخدمة {service_id} غير موجود")
        health = await self.providers.health(provider)
        if not health.is_usable:
            raise ServiceNotAvailableError(
                f"المزود {provider.name} غير متاح: {health.reason}",
                user_message="❌ هذه الخدمة متوقفة مؤقتاً. جرّب لاحقاً.",
            )

        # 3) الرابط والكمية والتكلفة
        clean_link = validate_link(link, pattern=service.link_pattern)
        quote = await self.catalog.quote(service, quantity)

        symbol = await self.settings.money_symbol()
        min_order_units = await self.settings.get_money_units("min_order_amount_units", 0)
        if min_order_units and quote.cost_units < min_order_units:
            raise ValidationError(
                f"قيمة الطلب {quote.cost_units} أقل من الحد الأدنى {min_order_units}",
                user_message=(
                    "❌ الحد الأدنى لقيمة الطلب هو "
                    f"{format_units(min_order_units, symbol=symbol)}."
                ),
            )

        # 4) الحدود اليومية ومنع الطلب المكرر
        await self._check_daily_limit(user)
        await self._check_duplicate(user, service.id, clean_link, quote.quantity)

        # 5) المعاملة الذرّية: إنشاء + خصم + سجل + إشعار
        async with self.db.transaction() as tx:
            order = await self.repos.orders.create(
                tx,
                user_id=user.id,
                service_id=service.id,
                provider_id=provider.id,
                service_name_snapshot=service.name,
                price_per_1000_snapshot_units=service.price_per_1000_units,
                link=clean_link,
                quantity=quote.quantity,
                cost_units=quote.cost_units,
                client_request_id=request_id,
                provider_cost_units=self._provider_cost(service, quote.quantity),
            )
            public_code = f"ORD-{order.id:06d}"
            await self.repos.orders.update_fields(tx, order.id, public_code=public_code)

            await self.wallet.charge_for_order(
                tx,
                user_id=user.id,
                order_id=order.id,
                amount_units=quote.cost_units,
                description=f"طلب {service.name} × {quote.quantity}",
            )

            await self.repos.orders.add_history(
                tx,
                order_id=order.id,
                from_status=None,
                to_status=OrderStatus.PENDING,
                actor_type=ActorType.USER,
                actor_id=user.id,
                reason="إنشاء الطلب",
            )

            title, message = templates.order_created(
                code=public_code,
                service_name=service.name,
                quantity=quote.quantity,
                cost_units=quote.cost_units,
                symbol=symbol,
            )
            await self.notifications.notify_order(
                tx,
                user_id=user.id,
                order_id=order.id,
                event=NotificationType.ORDER_CREATED,
                title=title,
                message=message,
                payload={"order_id": order.id, "cost_units": quote.cost_units},
            )

        created = await self.repos.orders.get(order.id)
        if created is None:  # لا يحدث عملياً، لكن لا نُرجع قيمة غير مؤكدة أبداً
            raise OrderError(f"تعذر قراءة الطلب {order.id} بعد إنشائه")
        logger.info(
            "أنشأ المستخدم %s الطلب %s (%s × %s) بتكلفة %s",
            user.id, created.id, service.name, quote.quantity, quote.cost_units,
        )
        return created

    def _provider_cost(self, service: Service, quantity: int) -> int | None:
        """حساب تكلفة الطلب علينا لدى المزود (للأرباح) إن كان سعر المزود معروفاً."""
        if not service.provider_price_per_1000_units:
            return None
        return (service.provider_price_per_1000_units * quantity + 500) // 1000

    async def _check_daily_limit(self, user: User) -> None:
        """
        التأكد من عدم تجاوز الحد اليومي لعدد الطلبات.

        الاستثناءات: RateLimitedError عند التجاوز.
        """
        max_per_day = await self.settings.get_int("max_orders_per_day", 0)
        if max_per_day <= 0:
            return
        start_today, _ = day_bounds_utc(0)
        today_count = await self.repos.orders.count_today_by_user(user.id, start_today)
        if today_count >= max_per_day:
            raise RateLimitedError(
                f"المستخدم {user.id} تجاوز {max_per_day} طلباً اليوم",
                user_message=f"⏳ وصلت إلى الحد اليومي ({max_per_day} طلب). حاول غداً.",
            )

    async def _check_duplicate(self, user: User, service_id: int, link: str, quantity: int) -> None:
        """
        منع إنشاء طلب مطابق تماماً خلال نافذة زمنية قصيرة (ضغط مزدوج أو خطأ).

        الاستثناءات: DuplicateOperationError عند وجود طلب مطابق حديث.
        """
        window_minutes = await self.settings.get_int("duplicate_order_window_minutes", 0)
        if window_minutes <= 0:
            return
        since = iso_plus_seconds(-window_minutes * 60)
        duplicate = await self.repos.orders.find_recent_duplicate(
            user_id=user.id, service_id=service_id, link=link, quantity=quantity, since_iso=since
        )
        if duplicate is not None:
            raise DuplicateOperationError(
                f"طلب مكرر خلال {window_minutes} دقيقة (الطلب {duplicate.id})",
                user_message=(
                    f"⚠️ لديك طلب مطابق قبل قليل ({duplicate.public_code or duplicate.id}). "
                    f"إن كنت تريد طلباً إضافياً انتظر {window_minutes} دقيقة."
                ),
            )

    # ===================================================================== #
    #                        أدوات تغيير الحالة                             #
    # ===================================================================== #

    async def _transition(
        self,
        tx: Tx,
        order: Order,
        new_status: str,
        *,
        actor_type: str,
        actor_id: int | None = None,
        reason: str | None = None,
        extra: dict | None = None,
        provider_status_raw: str | None = None,
    ) -> bool:
        """
        تنفيذ انتقال حالة واحد: تحقق من الجدول ثم تحديث مشروط ثم تسجيل في التاريخ.

        المخرجات: True إذا تم التغيير فعلاً، False إذا سبقتنا جهة أخرى لتغيير الحالة
                  (وهذا ليس خطأً — بل الحماية من السباق تعمل).

        الاستثناءات:
            InvalidStateTransitionError : الانتقال ممنوع في جدول الحالات.
        """
        assert_transition(order.status, new_status, order_id=order.id)
        if order.status == new_status:
            return False  # لا تغيير فعلي

        changed = await self.repos.orders.update_status(
            tx,
            order.id,
            new_status=new_status,
            expected_statuses=[order.status],
            extra_fields=extra,
        )
        if not changed:
            logger.warning(
                "تجاهل انتقال الطلب %s (%s ← %s): تغيّرت حالته من جهة أخرى",
                order.id, order.status, new_status,
            )
            return False

        await self.repos.orders.add_history(
            tx,
            order_id=order.id,
            from_status=order.status,
            to_status=new_status,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            provider_status_raw=provider_status_raw,
        )
        return True

    async def _refund_full(
        self, tx: Tx, order: Order, *, reason: str, actor_type: str, actor_id: int | None = None
    ) -> int:
        """
        استرجاع كامل المبلغ المتبقي للطلب ثم نقله إلى الحالة `refunded`.

        المخرجات: المبلغ المسترجع فعلياً (قد يكون صفراً إن سبق استرجاعه بالكامل).
        """
        remaining = order.refundable_units
        if remaining <= 0:
            return 0

        transaction = await self.wallet.refund_order(
            tx,
            user_id=order.user_id,
            order_id=order.id,
            amount_units=remaining,
            partial=False,
            description=f"استرجاع كامل: {reason}",
        )
        if transaction is None:
            return 0

        fresh = await self.repos.orders.get(order.id)
        if fresh is not None and can_transition(fresh.status, OrderStatus.REFUNDED):
            await self._transition(
                tx, fresh, OrderStatus.REFUNDED,
                actor_type=actor_type, actor_id=actor_id, reason=reason,
                extra={"refunded_at": self.repos.orders.now()},
            )
        return remaining

    async def _fail_order(
        self,
        order: Order,
        *,
        reason: str,
        actor_type: str = ActorType.SYSTEM,
        actor_id: int | None = None,
        notify_admins: bool = True,
        auto_refund: bool | None = None,
    ) -> int:
        """
        المسار الكامل لفشل طلب: تغيير الحالة ← استرجاع كامل ← إشعار المستخدم والأدمن.

        المدخلات:
            auto_refund : None تعني «اتبع الإعداد `auto_refund_on_provider_fail`»،
                          وTrue تفرض الاسترجاع (إجراء أدمن صريح).
                          عند تعطيل الاسترجاع التلقائي يبقى المال محجوزاً ويُنبَّه الأدمن
                          لتنفيذ الاسترجاع يدوياً — ولا يُفقد مال المستخدم في الحالتين.

        المخرجات: المبلغ المسترجع (صفر إذا كان الاسترجاع التلقائي معطّلاً).
        """
        symbol = await self.settings.money_symbol()
        clean_reason = sanitize(reason)[:300]
        if auto_refund is None:
            auto_refund = await self.settings.get_bool("auto_refund_on_provider_fail", True)
        refunded = 0

        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None or is_final(current.status):
                return 0

            moved = await self._transition(
                tx, current, OrderStatus.FAILED,
                actor_type=actor_type, actor_id=actor_id, reason=clean_reason,
                extra={"last_error": clean_reason, "locked_by": None, "locked_until": None},
            )
            if not moved:
                return 0

            failed_order = await self.repos.orders.get(order.id)
            if failed_order is None:
                return 0
            if auto_refund:
                refunded = await self._refund_full(
                    tx, failed_order, reason=clean_reason, actor_type=actor_type, actor_id=actor_id
                )

            code = current.public_code or f"#{current.id}"
            title, message = templates.order_failed(
                code=code, reason=clean_reason, refund_units=refunded, symbol=symbol
            )
            await self.notifications.notify_order(
                tx,
                user_id=current.user_id,
                order_id=current.id,
                event=NotificationType.ORDER_FAILED,
                title=title,
                message=message,
            )
            if notify_admins or not auto_refund:
                admin_reason = clean_reason if auto_refund else (
                    f"{clean_reason} — ⚠️ الاسترجاع التلقائي معطّل، نفّذ الاسترجاع يدوياً"
                )
                admin_title, admin_message = templates.admin_order_failed(
                    code=code, order_id=current.id, reason=admin_reason,
                    refund_units=refunded, symbol=symbol,
                )
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.ORDERS_VIEW,
                    token=f"order:{current.id}:failed",
                    title=admin_title,
                    message=admin_message,
                )
            await self.repos.error_logs.log(
                tx,
                message=f"فشل الطلب #{current.id}: {clean_reason}",
                level="ERROR",
                source="order_service",
                error_type="OrderFailed",
                user_id=current.user_id,
            )
        logger.error("فشل الطلب %s: %s (استُرجع %s)", order.id, clean_reason, refunded)
        return refunded

    # ===================================================================== #
    #                        إرسال الطلبات للمزود                           #
    # ===================================================================== #

    async def process_pending_orders(self, *, worker: str = "submitter", limit: int = 5) -> BatchReport:
        """
        حجز دفعة من الطلبات المعلّقة وإرسالها إلى المزود.

        تُستدعى من job دوري. الحجز يمنع أن يعالج عاملان الطلب نفسه.
        """
        report = BatchReport()
        async with self.db.transaction() as tx:
            claimed = await self.repos.orders.claim_pending_for_submit(
                tx, worker=worker, limit=limit, lock_seconds=ORDER_LOCK_SECONDS
            )
        report.claimed = len(claimed)

        for order in claimed:
            outcome = await self._submit_one(order)
            if outcome == "submitted":
                report.succeeded += 1
            elif outcome == "retry":
                report.retried += 1
            elif outcome == "uncertain":
                report.uncertain += 1
            elif outcome == "failed":
                report.failed += 1
            else:
                report.unchanged += 1

        if report.claimed:
            logger.info("جولة إرسال الطلبات: %s", report.as_dict())
        return report

    async def _submit_one(self, order: Order) -> str:
        """
        إرسال طلب واحد إلى المزود ومعالجة كل النتائج الممكنة.

        المخرجات: وصف مختصر للنتيجة: submitted / retry / uncertain / failed / skipped.
        """
        service = await self.repos.services.get(order.service_id)
        provider = await self.repos.providers.get(order.provider_id)
        if service is None or provider is None:
            await self._fail_order(order, reason="بيانات الخدمة أو المزود غير موجودة")
            return "failed"

        health = await self.providers.health(provider)
        if not health.is_usable:
            await self._requeue(order, reason=f"المزود غير متاح: {health.reason}", delay_seconds=300)
            return "retry"

        try:
            result = await self.providers.submit_order(provider, service, order)
        except ProviderInsufficientFundsError as exc:
            await self._handle_insufficient_provider_funds(order, provider, str(exc))
            return "retry"
        except ProviderUncertainError as exc:
            await self._mark_uncertain(order, str(exc))
            return "uncertain"
        except ProviderPermanentError as exc:
            await self._fail_order(order, reason=f"رفض المزود الطلب: {exc}")
            return "failed"
        except ProviderTemporaryError as exc:
            if order.submit_attempts >= MAX_SUBMIT_ATTEMPTS:
                await self._fail_order(
                    order, reason=f"تعذر الإرسال بعد {order.submit_attempts} محاولات: {exc}"
                )
                return "failed"
            await self._requeue(order, reason=str(exc), delay_seconds=60 * order.submit_attempts)
            return "retry"
        except ProviderError as exc:
            # أي خطأ مزود غير مصنّف يُعامل معاملة الخطأ النهائي حفاظاً على مال المستخدم
            await self._fail_order(order, reason=f"خطأ غير متوقع من المزود: {exc}")
            return "failed"

        # نجاح: تسجيل رقم الطلب عند المزود والانتقال إلى submitted
        now = self.repos.orders.now()
        check_interval = await self.settings.get_int("order_check_interval_seconds", 120)
        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None:
                return "skipped"
            moved = await self._transition(
                tx, current, OrderStatus.SUBMITTED,
                actor_type=ActorType.JOB,
                reason="قبل المزود الطلب",
                extra={
                    "provider_order_id": result.provider_order_id,
                    "provider_cost_units": result.charge_units if result.charge_units else current.provider_cost_units,
                    "submitted_at": now,
                    "next_check_at": iso_plus_seconds(check_interval),
                    "locked_by": None,
                    "locked_until": None,
                    "last_error": None,
                },
            )
            if moved:
                title, message = templates.order_submitted(
                    code=current.public_code or f"#{current.id}",
                    service_name=current.service_name_snapshot,
                )
                await self.notifications.notify_order(
                    tx,
                    user_id=current.user_id,
                    order_id=current.id,
                    event=NotificationType.ORDER_SUBMITTED,
                    title=title,
                    message=message,
                )
        logger.info(
            "أُرسل الطلب %s إلى المزود %s برقم %s", order.id, provider.name, result.provider_order_id
        )
        return "submitted"

    async def _requeue(self, order: Order, *, reason: str, delay_seconds: int) -> None:
        """إعادة الطلب إلى `pending` مع تأجيل المحاولة القادمة (فشل مؤقت آمن)."""
        clean_reason = sanitize(reason)[:300]
        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None or current.status != OrderStatus.SUBMITTING:
                return
            await self._transition(
                tx, current, OrderStatus.PENDING,
                actor_type=ActorType.JOB,
                reason=f"إعادة جدولة: {clean_reason}",
                extra={
                    "last_error": clean_reason,
                    "locked_by": None,
                    "locked_until": None,
                    "next_check_at": iso_plus_seconds(max(30, delay_seconds)),
                },
            )
        logger.warning("أُعيد الطلب %s للانتظار: %s", order.id, clean_reason)

    async def _mark_uncertain(self, order: Order, error: str) -> None:
        """
        وضع الطلب في حالة «غير مؤكد» وتنبيه الأدمن فوراً.

        ⚠️ لا استرجاع ولا إعادة إرسال هنا: قد يكون الطلب أُنشئ فعلاً عند المزود،
        وإعادة الإرسال تعني دفع المبلغ مرتين.
        """
        clean_error = sanitize(error)[:300]
        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None or current.status != OrderStatus.SUBMITTING:
                return
            moved = await self._transition(
                tx, current, OrderStatus.SUBMIT_UNCERTAIN,
                actor_type=ActorType.JOB,
                reason=clean_error,
                extra={"last_error": clean_error, "locked_by": None, "locked_until": None},
            )
            if moved:
                code = current.public_code or f"#{current.id}"
                title, message = templates.admin_order_uncertain(
                    code=code, order_id=current.id, error=clean_error
                )
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.ORDERS_VIEW,
                    token=f"order:{current.id}:uncertain",
                    title=title,
                    message=message,
                )
                await self.repos.error_logs.log(
                    tx,
                    message=f"نتيجة إرسال غير مؤكدة للطلب #{current.id}: {clean_error}",
                    level="CRITICAL",
                    source="order_service",
                    error_type="ProviderUncertainError",
                    user_id=current.user_id,
                )
        logger.critical("الطلب %s بحالة غير مؤكدة: %s", order.id, clean_error)

    async def _handle_insufficient_provider_funds(
        self, order: Order, provider: Provider, error: str
    ) -> None:
        """
        معالجة «رصيد المزود غير كافٍ» حسب القرار D5:
        يبقى الطلب منتظراً حتى مهلة قصوى، وبعدها يفشل ويُسترجع المبلغ تلقائياً.
        """
        wait_hours = await self.settings.get_int("provider_insufficient_wait_hours", 6)
        created = parse_iso(order.created_at)
        age_hours = ((utc_now() - created).total_seconds() / 3600) if created else 0.0

        if age_hours >= wait_hours:
            await self._fail_order(
                order, reason=f"انتظر الطلب {wait_hours} ساعة ورصيد المزود لا يزال غير كافٍ"
            )
            return

        await self._requeue(order, reason=f"رصيد المزود غير كافٍ: {error}", delay_seconds=900)
        symbol = await self.settings.money_symbol()
        title, message = templates.admin_provider_low_balance(
            provider_name=provider.name, balance_units=provider.balance_units, symbol=symbol
        )
        async with self.db.transaction() as tx:
            await self.notifications.notify_admins(
                tx,
                permission=Permission.PROVIDERS_VIEW,
                token=f"provider:{provider.id}:insufficient:{day_bounds_utc(0)[0][:10]}",
                title=title,
                message=message,
            )

    # ===================================================================== #
    #                          متابعة حالة الطلبات                          #
    # ===================================================================== #

    async def process_due_orders(self, *, worker: str = "checker", limit: int = 20) -> BatchReport:
        """
        حجز دفعة من الطلبات المستحقة للفحص وتحديث حالاتها من المزود.

        تُستدعى من job دوري حتى تصل كل الطلبات إلى حالة نهائية دون تدخل بشري.

        **المرحلة 6:** الطلبات تُجمَّع حسب المزود ويُستعلم عنها دفعة واحدة
        (`multi-status`) بدل استدعاء لكل طلب — يقلّ عدد طلبات HTTP بمقدار حجم
        الدفعة، فيخف الضغط على المزود ويقصر زمن الجولة. الفحص الفردي يبقى
        المسار الاحتياطي لكل طلب لم يُجب عنه المزود في الدفعة.
        """
        report = BatchReport()
        async with self.db.transaction() as tx:
            claimed = await self.repos.orders.claim_due_for_check(
                tx, worker=worker, limit=limit, lock_seconds=ORDER_LOCK_SECONDS
            )
        report.claimed = len(claimed)
        if not claimed:
            return report

        use_batch = await self.settings.get_bool("order_multi_status_enabled", True)
        groups: dict[int, list[Order]] = {}
        for order in claimed:
            groups.setdefault(order.provider_id, []).append(order)

        for provider_id, orders in groups.items():
            outcomes = await self._sync_provider_group(provider_id, orders, use_batch=use_batch)
            for outcome in outcomes:
                if outcome in {OrderStatus.COMPLETED, OrderStatus.PARTIAL}:
                    report.completed += 1
                elif outcome == OrderStatus.FAILED:
                    report.failed += 1
                elif outcome == "unchanged":
                    report.unchanged += 1
                else:
                    report.succeeded += 1

        if report.claimed:
            logger.info("جولة فحص الطلبات: %s", report.as_dict())
        return report

    async def _sync_provider_group(
        self, provider_id: int | None, orders: list[Order], *, use_batch: bool
    ) -> list[str]:
        """
        فحص مجموعة طلبات تخص مزوداً واحداً.

        المدخلات:
            provider_id : معرف المزود (قد يكون None لطلب غير مرتبط بمزود).
            orders      : الطلبات المحجوزة لهذا المزود.
            use_batch   : تفعيل الاستعلام الجماعي (إعداد `order_multi_status_enabled`).

        المخرجات: قائمة نتائج بنفس ترتيب الطلبات ("unchanged" أو الحالة الجديدة).
        """
        provider = await self.repos.providers.get(provider_id) if provider_id else None
        if provider is None:
            for order in orders:
                await self._fail_order(order, reason="المزود غير موجود")
            return [OrderStatus.FAILED] * len(orders)

        statuses: dict[str, object] = {}
        batchable = [order for order in orders if order.provider_order_id]
        if use_batch and len(batchable) > 1:
            try:
                statuses = await self.providers.fetch_multi_status(provider, batchable)
            except ProviderError as exc:
                # فشل على مستوى الاتصال: لا فائدة من إعادة المحاولة فردياً الآن
                logger.warning(
                    "فشل الفحص الجماعي للمزود %s (%s طلباً): %s",
                    provider.name,
                    len(batchable),
                    exc,
                )
                for order in orders:
                    await self._release_with_backoff(order, error=str(exc))
                return ["unchanged"] * len(orders)

        outcomes: list[str] = []
        for order in orders:
            status = statuses.get(order.provider_order_id or "")
            if status is None:
                outcomes.append(await self._sync_one(order))       # المسار الاحتياطي
            else:
                outcomes.append(await self._apply_status(order, status))
        return outcomes

    async def _sync_one(self, order: Order) -> str:
        """
        فحص حالة طلب واحد لدى المزود وتطبيق النتيجة.

        المخرجات: الحالة الجديدة، أو "unchanged" إذا لم يتغير شيء.
        """
        provider = await self.repos.providers.get(order.provider_id)
        if provider is None:
            await self._fail_order(order, reason="المزود غير موجود")
            return OrderStatus.FAILED

        try:
            status = await self.providers.fetch_status(provider, order)
        except ProviderPermanentError as exc:
            await self._release_with_backoff(order, error=str(exc))
            logger.warning("فحص الطلب %s فشل نهائياً: %s", order.id, exc)
            return "unchanged"
        except ProviderError as exc:
            await self._release_with_backoff(order, error=str(exc))
            return "unchanged"

        return await self._apply_status(order, status)

    async def _apply_status(self, order: Order, status) -> str:
        """
        تطبيق نتيجة حالة قادمة من المزود على طلب واحد.

        فُصلت عن `_sync_one` في المرحلة 6 ليشاركها الفحص الجماعي: مصدر الحالة
        يختلف (استدعاء فردي أو دفعة) بينما قواعد الانتقال والاسترجاع واحدة.

        المخرجات: الحالة الجديدة، أو "unchanged" إذا لم يتغير شيء.
        """
        mapped = map_provider_status(status.raw_status)
        if mapped is None:
            await self._handle_unknown_status(order, status.raw_status)
            return "unchanged"

        if mapped == order.status:
            await self._release_with_backoff(order, progress=status)
            return "unchanged"

        if mapped == OrderStatus.IN_PROGRESS:
            await self._apply_in_progress(order, status)
            return OrderStatus.IN_PROGRESS
        if mapped == OrderStatus.COMPLETED:
            await self._apply_completed(order, status)
            return OrderStatus.COMPLETED
        if mapped == OrderStatus.PARTIAL:
            await self._apply_partial(order, status)
            return OrderStatus.PARTIAL
        if mapped == OrderStatus.CANCELED:
            await self._apply_canceled(order, reason="ألغى المزود الطلب")
            return OrderStatus.CANCELED
        if mapped == OrderStatus.FAILED:
            await self._fail_order(order, reason=f"المزود أبلغ بفشل الطلب ({status.raw_status})")
            return OrderStatus.FAILED

        # حالة معروفة لكن الانتقال إليها غير منطقي من الحالة الحالية: نسجل ونؤجل
        await self._release_with_backoff(order, error=f"انتقال غير مدعوم إلى {mapped}")
        return "unchanged"

    def _progress_fields(self, status) -> dict:
        """الحقول الرقمية المستخرجة من رد المزود (تقدّم التنفيذ)."""
        fields: dict = {"provider_status": status.raw_status}
        if status.start_count is not None:
            fields["start_count"] = status.start_count
        if status.remains is not None:
            fields["remains"] = status.remains
        if status.delivered is not None:
            fields["delivered_quantity"] = status.delivered
        return fields

    async def _apply_in_progress(self, order: Order, status) -> None:
        """نقل الطلب إلى «قيد التنفيذ» وإشعار المستخدم مرة واحدة."""
        check_interval = await self.settings.get_int("order_check_interval_seconds", 120)
        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None:
                return
            extra = self._progress_fields(status)
            extra.update({
                "locked_by": None,
                "locked_until": None,
                "next_check_at": iso_plus_seconds(check_interval),
            })
            moved = await self._transition(
                tx, current, OrderStatus.IN_PROGRESS,
                actor_type=ActorType.PROVIDER,
                reason="بدأ التنفيذ",
                extra=extra,
                provider_status_raw=status.raw_status,
            )
            if moved:
                title, message = templates.order_in_progress(
                    code=current.public_code or f"#{current.id}"
                )
                await self.notifications.notify_order(
                    tx,
                    user_id=current.user_id,
                    order_id=current.id,
                    event=NotificationType.ORDER_IN_PROGRESS,
                    title=title,
                    message=message,
                )

    async def _apply_completed(self, order: Order, status) -> None:
        """إنهاء الطلب بنجاح وإشعار المستخدم."""
        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None:
                return
            extra = self._progress_fields(status)
            extra.update({
                "completed_at": self.repos.orders.now(),
                "remains": 0,
                "delivered_quantity": status.delivered if status.delivered is not None else current.quantity,
                "locked_by": None,
                "locked_until": None,
                "next_check_at": None,
            })
            moved = await self._transition(
                tx, current, OrderStatus.COMPLETED,
                actor_type=ActorType.PROVIDER,
                reason="اكتمل التنفيذ",
                extra=extra,
                provider_status_raw=status.raw_status,
            )
            if moved:
                title, message = templates.order_completed(
                    code=current.public_code or f"#{current.id}",
                    service_name=current.service_name_snapshot,
                    quantity=current.quantity,
                )
                await self.notifications.notify_order(
                    tx,
                    user_id=current.user_id,
                    order_id=current.id,
                    event=NotificationType.ORDER_COMPLETED,
                    title=title,
                    message=message,
                )
        logger.info("اكتمل الطلب %s", order.id)

    async def _apply_partial(self, order: Order, status) -> None:
        """
        تنفيذ جزئي: حساب الاسترجاع بحسب المتبقي، تنفيذه، ثم إشعار المستخدم.

        الاسترجاع = (التكلفة × المتبقي) ÷ الكمية، مطروحاً منه ما سبق استرجاعه.
        """
        symbol = await self.settings.money_symbol()
        refund_enabled = await self.settings.get_bool("partial_refund_enabled", True)

        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None:
                return

            remains = status.remains if status.remains is not None else 0
            delivered = (
                status.delivered if status.delivered is not None else max(0, current.quantity - remains)
            )
            refund_units = 0
            if refund_enabled and remains > 0:
                refund_units = partial_refund_units(
                    cost_units=current.cost_units,
                    quantity=current.quantity,
                    remains=remains,
                    already_refunded_units=current.refund_amount_units,
                )

            extra = self._progress_fields(status)
            extra.update({
                "remains": remains,
                "delivered_quantity": delivered,
                "completed_at": self.repos.orders.now(),
                "locked_by": None,
                "locked_until": None,
                "next_check_at": None,
            })
            moved = await self._transition(
                tx, current, OrderStatus.PARTIAL,
                actor_type=ActorType.PROVIDER,
                reason=f"تنفيذ جزئي — المتبقي {remains}",
                extra=extra,
                provider_status_raw=status.raw_status,
            )
            if not moved:
                return

            refunded = 0
            if refund_units > 0:
                transaction = await self.wallet.refund_order(
                    tx,
                    user_id=current.user_id,
                    order_id=current.id,
                    amount_units=refund_units,
                    partial=True,
                    description=f"استرجاع جزئي للطلب #{current.id} (متبقي {remains})",
                )
                refunded = transaction.amount_units if transaction else 0

            title, message = templates.order_partial(
                code=current.public_code or f"#{current.id}",
                delivered=delivered,
                quantity=current.quantity,
                refund_units=refunded,
                symbol=symbol,
            )
            await self.notifications.notify_order(
                tx,
                user_id=current.user_id,
                order_id=current.id,
                event=NotificationType.ORDER_PARTIAL,
                title=title,
                message=message,
            )
        logger.info("الطلب %s نُفِّذ جزئياً (متبقي %s)", order.id, status.remains)

    async def _apply_canceled(
        self, order: Order, *, reason: str, actor_type: str = ActorType.PROVIDER, actor_id: int | None = None
    ) -> int:
        """
        إلغاء الطلب مع استرجاع كامل المبلغ وإشعار المستخدم.

        المخرجات: المبلغ المسترجع.
        """
        symbol = await self.settings.money_symbol()
        clean_reason = sanitize(reason)[:300]
        refunded = 0

        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None or is_final(current.status):
                return 0
            moved = await self._transition(
                tx, current, OrderStatus.CANCELED,
                actor_type=actor_type, actor_id=actor_id, reason=clean_reason,
                extra={
                    "cancelled_at": self.repos.orders.now(),
                    "locked_by": None,
                    "locked_until": None,
                    "next_check_at": None,
                },
            )
            if not moved:
                return 0

            canceled_order = await self.repos.orders.get(order.id)
            if canceled_order is None:
                return 0
            refunded = await self._refund_full(
                tx, canceled_order, reason=clean_reason, actor_type=actor_type, actor_id=actor_id
            )

            code = current.public_code or f"#{current.id}"
            title, message = templates.order_canceled(
                code=code, refund_units=refunded, symbol=symbol
            )
            await self.notifications.notify_order(
                tx,
                user_id=current.user_id,
                order_id=current.id,
                event=NotificationType.ORDER_CANCELED,
                title=title,
                message=message,
            )
        logger.info("أُلغي الطلب %s (%s) واسترُجع %s", order.id, clean_reason, refunded)
        return refunded

    async def _handle_unknown_status(self, order: Order, raw_status: str | None) -> None:
        """تسجيل حالة مزود غير معروفة دون تغيير حالة الطلب (سلامة أولاً)."""
        clean = sanitize(str(raw_status))[:100]
        async with self.db.transaction() as tx:
            await self.repos.error_logs.log(
                tx,
                message=f"حالة مزود غير معروفة للطلب #{order.id}: {clean}",
                level="WARNING",
                source="order_service",
                error_type="UnknownProviderStatus",
                user_id=order.user_id,
            )
        await self._release_with_backoff(order, error=f"حالة غير معروفة: {clean}")
        logger.warning("حالة مزود غير معروفة للطلب %s: %s", order.id, clean)

    async def _release_with_backoff(self, order: Order, *, progress=None, error: str | None = None) -> None:
        """
        فك حجز الطلب وتحديد موعد الفحص القادم بتدرج تصاعدي.

        كلما تكررت الفحوص دون تغيير، تباعدت المواعيد — تخفيفاً على المزود وعلى النظام.
        """
        index = min(order.checks_count, len(ORDER_CHECK_BACKOFF) - 1)
        delay = ORDER_CHECK_BACKOFF[index]
        async with self.db.transaction() as tx:
            fields: dict = {}
            if progress is not None:
                fields.update(self._progress_fields(progress))
            if error:
                fields["last_error"] = sanitize(error)[:300]
            if fields:
                await self.repos.orders.update_fields(tx, order.id, **fields)
            await self.repos.orders.release_lock(
                tx, order.id, next_check_at=iso_plus_seconds(delay)
            )

    # ===================================================================== #
    #                        إجراءات المستخدم والأدمن                       #
    # ===================================================================== #

    async def cancel_by_user(self, user: User, order_id: int) -> int:
        """
        إلغاء المستخدم لطلبه قبل إرساله للمزود (القرار D11).

        المخرجات: المبلغ المسترجع.

        الاستثناءات:
            OrderError                  : الطلب ليس للمستخدم أو غير موجود.
            InvalidStateTransitionError : الطلب غادر حالة الانتظار (لا يمكن الإلغاء).
            ValidationError             : الإلغاء الذاتي معطّل من الإعدادات.
        """
        await self.auth.guard(user)
        if not await self.settings.get_bool("user_cancel_before_submit", True):
            raise ValidationError(
                "إلغاء المستخدم معطّل", user_message="⚠️ إلغاء الطلبات غير متاح حالياً."
            )

        order = await self.repos.orders.get(order_id)
        if order is None or order.user_id != user.id:
            raise OrderError("الطلب غير موجود", user_message="❌ لم يتم العثور على هذا الطلب.")
        if order.status != OrderStatus.PENDING:
            raise InvalidStateTransitionError(
                f"لا يمكن إلغاء الطلب {order_id} في الحالة {order.status}",
                user_message="⚠️ لا يمكن الإلغاء الآن — بدأ تنفيذ الطلب بالفعل.",
            )

        return await self._apply_canceled(
            order, reason="إلغاء بطلب المستخدم", actor_type=ActorType.USER, actor_id=user.id
        )

    async def admin_cancel(self, actor: User, order_id: int, reason: str) -> int:
        """
        إلغاء طلب من الأدمن مع استرجاع كامل (صلاحية `orders.cancel`).

        المخرجات: المبلغ المسترجع.
        """
        await self.auth.require_permission(actor, Permission.ORDERS_CANCEL, context=f"order:{order_id}")
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")
        if is_final(order.status):
            raise InvalidStateTransitionError(
                f"الطلب {order_id} في حالة نهائية ({order.status})",
                user_message="⚠️ هذا الطلب مغلق ولا يقبل الإلغاء.",
            )

        refunded = await self._apply_canceled(
            order, reason=reason, actor_type=ActorType.ADMIN, actor_id=actor.id
        )
        await self.audit.log_standalone(
            action="orders.cancel",
            admin_id=actor.id,
            target_type="order",
            target_id=order_id,
            details={"reason": reason, "refunded_units": refunded},
            source="telegram",
        )
        return refunded

    async def admin_mark_failed(self, actor: User, order_id: int, reason: str) -> int:
        """
        تأكيد الأدمن أن الطلب لم يُنشأ عند المزود (للطلبات غير المؤكدة) ⇒ فشل + استرجاع.

        المخرجات: المبلغ المسترجع.
        """
        await self.auth.require_permission(actor, Permission.ORDERS_REFUND, context=f"order:{order_id}")
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")
        if is_final(order.status):
            raise InvalidStateTransitionError(
                f"الطلب {order_id} في حالة نهائية ({order.status})",
                user_message="⚠️ هذا الطلب مغلق مسبقاً.",
            )

        refunded = await self._fail_order(
            order,
            reason=reason,
            actor_type=ActorType.ADMIN,
            actor_id=actor.id,
            notify_admins=False,
            auto_refund=True,  # قرار أدمن صريح: المال يعود فوراً
        )
        await self.audit.log_standalone(
            action="orders.refund",
            admin_id=actor.id,
            target_type="order",
            target_id=order_id,
            details={"reason": reason, "refunded_units": refunded},
            source="telegram",
        )
        return refunded

    async def admin_link_provider_order(self, actor: User, order_id: int, provider_order_id: str) -> bool:
        """
        ربط رقم الطلب عند المزود يدوياً (لطلب بحالة غير مؤكدة تبيّن أنه أُنشئ فعلاً).

        الاستثناءات:
            OrderError                  : الطلب غير موجود أو الرقم مستخدم لطلب آخر.
            InvalidStateTransitionError : حالة الطلب لا تسمح بالربط.
        """
        await self.auth.require_permission(
            actor, Permission.ORDERS_LINK_PROVIDER_ID, context=f"order:{order_id}"
        )
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")

        clean_id = str(provider_order_id).strip()
        if not clean_id:
            raise ValidationError("رقم الطلب فارغ", user_message="❌ أرسل رقم الطلب عند المزود.")
        conflict = await self.repos.orders.get_by_provider_order_id(order.provider_id, clean_id)
        if conflict is not None and conflict.id != order.id:
            raise OrderError(
                f"رقم المزود {clean_id} مرتبط بالطلب {conflict.id}",
                user_message=f"❌ هذا الرقم مرتبط بالطلب {conflict.public_code or conflict.id}.",
            )

        check_interval = await self.settings.get_int("order_check_interval_seconds", 120)
        async with self.db.transaction() as tx:
            moved = await self._transition(
                tx, order, OrderStatus.SUBMITTED,
                actor_type=ActorType.ADMIN, actor_id=actor.id,
                reason=f"ربط يدوي برقم المزود {clean_id}",
                extra={
                    "provider_order_id": clean_id,
                    "submitted_at": self.repos.orders.now(),
                    "next_check_at": iso_plus_seconds(check_interval),
                    "locked_by": None,
                    "locked_until": None,
                },
            )
            if moved:
                await self.audit.log(
                    tx,
                    action="orders.link_provider_id",
                    admin_id=actor.id,
                    target_type="order",
                    target_id=order_id,
                    before={"status": order.status, "provider_order_id": order.provider_order_id},
                    after={"status": OrderStatus.SUBMITTED, "provider_order_id": clean_id},
                )
                title, message = templates.order_submitted(
                    code=order.public_code or f"#{order.id}",
                    service_name=order.service_name_snapshot,
                )
                await self.notifications.notify_order(
                    tx,
                    user_id=order.user_id,
                    order_id=order.id,
                    event=NotificationType.ORDER_SUBMITTED,
                    title=title,
                    message=message,
                )
        return moved

    async def admin_override_status(
        self, actor: User, order_id: int, new_status: str, reason: str
    ) -> bool:
        """
        تجاوز إداري لحالة الطلب (للأدمن الأعلى فقط) — مع سبب إجباري وتدقيق كامل.

        لا يُجري أي حركة مالية: الاسترجاع يتم عبر الأدوات المخصصة له،
        حتى لا يحدث تغيير رصيد خارج المسار المحاسبي.

        الاستثناءات:
            PermissionDeniedError · ValidationError · OrderError
        """
        await self.auth.require_permission(
            actor, Permission.ORDERS_STATUS_OVERRIDE, context=f"order:{order_id}"
        )
        clean_reason = (reason or "").strip()
        if len(clean_reason) < 5:
            raise ValidationError(
                "سبب التجاوز مطلوب", user_message="❌ اكتب سبباً واضحاً للتجاوز (5 أحرف على الأقل)."
            )
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")

        async with self.db.transaction() as tx:
            changed = await self.repos.orders.update_status(
                tx, order_id, new_status=new_status, expected_statuses=[order.status]
            )
            if changed:
                await self.repos.orders.add_history(
                    tx,
                    order_id=order_id,
                    from_status=order.status,
                    to_status=new_status,
                    actor_type=ActorType.ADMIN,
                    actor_id=actor.id,
                    reason=f"تجاوز إداري: {clean_reason}",
                )
                await self.audit.log(
                    tx,
                    action="orders.status.override",
                    admin_id=actor.id,
                    target_type="order",
                    target_id=order_id,
                    before={"status": order.status},
                    after={"status": new_status, "reason": clean_reason},
                )
        if changed:
            logger.warning(
                "تجاوز إداري لحالة الطلب %s: %s ← %s بواسطة %s",
                order_id, order.status, new_status, actor.id,
            )
        return changed

    async def recheck_now(self, actor: User, order_id: int) -> str:
        """
        إعادة فحص فورية لحالة طلب من لوحة الأدمن.

        المخرجات: وصف نصي للنتيجة.
        """
        await self.auth.require_permission(actor, Permission.ORDERS_RECHECK, context=f"order:{order_id}")
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")
        if not order.provider_order_id:
            return "لا يمكن الفحص: الطلب بلا رقم عند المزود."
        return await self._sync_one(order)

    # ===================================================================== #
    #                        الاسترداد بعد إعادة التشغيل                     #
    # ===================================================================== #

    async def recover_after_restart(self) -> dict[str, int]:
        """
        استرداد الحالة بعد إعادة تشغيل البوت.

        • الطلبات العالقة في `submitting` تُنقل إلى `submit_uncertain` (لا نعرف مصيرها).
        • الأقفال منتهية الصلاحية تُحرَّر ليعاد التقاط الطلبات.

        المخرجات: عدّادات ما تم استرداده.
        """
        async with self.db.transaction() as tx:
            recovered = await self.repos.orders.recover_submitting_orders(tx)
            released = await self.repos.orders.release_expired_locks(tx)

        for order_id in recovered:
            order = await self.repos.orders.get(order_id)
            if order is None:
                continue
            code = order.public_code or f"#{order.id}"
            title, message = templates.admin_order_uncertain(
                code=code, order_id=order.id, error="انقطع تشغيل البوت أثناء إرسال الطلب"
            )
            async with self.db.transaction() as tx:
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.ORDERS_VIEW,
                    token=f"order:{order.id}:uncertain",
                    title=title,
                    message=message,
                )

        if recovered or released:
            logger.warning(
                "استرداد بعد الإقلاع: %s طلب غير مؤكد، %s قفل محرَّر", len(recovered), released
            )
        return {"uncertain": len(recovered), "locks_released": released}

    async def alert_stuck_orders(self) -> int:
        """
        تنبيه الأدمن بالطلبات التي توقفت بلا تقدم لفترة طويلة.

        المخرجات: عدد الطلبات المتوقفة.
        """
        hours = await self.settings.get_int("order_stuck_alert_hours", 24)
        before = iso_plus_seconds(-hours * 3600)
        stuck = await self.repos.orders.stuck_orders(before_iso=before, limit=50)
        if not stuck:
            return 0
        title, message = templates.admin_stuck_orders(count=len(stuck), hours=hours)
        async with self.db.transaction() as tx:
            await self.notifications.notify_admins(
                tx,
                permission=Permission.ORDERS_VIEW,
                token=f"stuck:{day_bounds_utc(0)[0][:13]}",
                title=title,
                message=message,
            )
        return len(stuck)

    # ===================================================================== #
    #                                القراءة                                #
    # ===================================================================== #

    async def get_for_user(self, user: User, order_id: int) -> Order:
        """
        جلب طلب يخص المستخدم (مع منع الاطلاع على طلبات غيره).

        الاستثناءات: OrderError إذا لم يكن الطلب موجوداً أو ليس له.
        """
        order = await self.repos.orders.get(order_id)
        if order is None or order.user_id != user.id:
            raise OrderError("الطلب غير موجود", user_message="❌ لم يتم العثور على هذا الطلب.")
        return order

    async def list_for_user(
        self, user: User, *, statuses: list[str] | None = None, limit: int = 8, offset: int = 0
    ) -> list[Order]:
        """قائمة طلبات المستخدم (مع إمكانية التصفية بالحالة)."""
        return await self.repos.orders.list_by_user(
            user.id, statuses=statuses, limit=limit, offset=offset
        )

    async def count_for_user(self, user: User, *, statuses: list[str] | None = None) -> int:
        """عدد طلبات المستخدم (للتصفح بالصفحات)."""
        return await self.repos.orders.count_by_user(user.id, statuses=statuses)

    async def admin_get(self, actor: User, order_id: int) -> Order:
        """
        جلب أي طلب في النظام لعرضه في لوحة الأدمن (بعد فحص صلاحية الاطلاع).

        الاستثناءات: PermissionDeniedError · OrderError
        """
        await self.auth.require_permission(
            actor, Permission.ORDERS_VIEW, context=f"order:{order_id}"
        )
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ لم يتم العثور على هذا الطلب.")
        return order

    async def admin_list(
        self,
        actor: User,
        *,
        statuses: Sequence[str] | None = None,
        user_id: int | None = None,
        limit: int = 8,
        offset: int = 0,
    ) -> list[Order]:
        """
        قائمة طلبات لكل المستخدمين (قوائم لوحة الأدمن) — مع تصفية بالحالة أو بالمستخدم.

        الاستثناءات: PermissionDeniedError
        """
        await self.auth.require_permission(actor, Permission.ORDERS_VIEW, context="orders:list")
        return await self.repos.orders.list_by_statuses(
            statuses, user_id=user_id, limit=limit, offset=offset
        )

    async def admin_count(
        self,
        actor: User,
        *,
        statuses: Sequence[str] | None = None,
        user_id: int | None = None,
    ) -> int:
        """عدد الطلبات المطابقة للتصفية نفسها (لحساب عدد الصفحات في لوحة الأدمن)."""
        await self.auth.require_permission(actor, Permission.ORDERS_VIEW, context="orders:count")
        return await self.repos.orders.count_by_statuses(statuses, user_id=user_id)

    async def history(self, order_id: int) -> list:
        """سجل تغيّر حالات الطلب (من ماذا إلى ماذا ومتى ومن نفّذ)."""
        return await self.repos.orders.history(order_id)

    async def status_counts(self) -> dict[str, int]:
        """عدد الطلبات في كل حالة (للوحة الأدمن)."""
        return await self.repos.orders.status_counts()

    async def recent_revenue_units(self, days: int = 1) -> int:
        """إجمالي قيمة الطلبات خلال آخر عدد أيام (للإحصائيات السريعة)."""
        return await self.repos.orders.sum_cost_between(iso_minus_days(days), self.repos.orders.now())
```

### `services/stats_service.py`  ·  مُحدَّث  ·  442 سطراً

`system_digest()`: أرقام الملخص اليومي بلا فاعل بشري (الحارس عند التوزيع لا عند القراءة).

```python
"""
خدمة الإحصائيات والتقارير — أرقام حقيقية من قاعدة البيانات فقط.

المبدأ الحاكم: **لا رقم تقديري ولا بيانات وهمية**. كل قيمة هنا ناتجة عن استعلام
فعلي؛ وإن تعذّر حساب قيمة (مثل الربح بلا سعر مزود) تُعاد `None` ويُوضَّح ذلك
في العرض بدل اختراع رقم.

المحتوى:
    • لوحة المعلومات السريعة (Dashboard).
    • تقارير مالية: إيراد، ربح، التزامات المحفظة.
    • تقارير تشغيلية: نسبة النجاح، الطلبات العالقة، صحة المزودين.
    • صحة النظام: الأخطاء، صندوق الإشعارات، حجم قاعدة البيانات.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.enums import OrderStatus, TransactionType
from core.money import format_units
from core.permissions import Permission
from database.database import Database
from database.models import User
from database.repositories import Repositories
from services.auth_service import AuthService
from services.provider_service import ProviderService
from services.settings_service import SettingsService
from utils.datetime_utils import day_bounds_utc, iso_minus_days, iso_plus_seconds, utc_now_iso
from utils.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class DashboardStats:
    """أرقام لوحة المعلومات الرئيسية."""

    users_total: int
    users_new_today: int
    users_active_7d: int
    users_banned: int
    orders_today: int
    orders_by_status: dict[str, int]
    revenue_today_units: int
    revenue_7d_units: int
    deposits_today_units: int
    pending_payments: int
    open_tickets: int
    queued_notifications: int
    active_services: int
    errors_24h: int

    def as_dict(self) -> dict[str, object]:
        """تحويل الأرقام إلى قاموس (لتسجيلها أو إرسالها كتقرير)."""
        return {
            "users_total": self.users_total,
            "users_new_today": self.users_new_today,
            "users_active_7d": self.users_active_7d,
            "users_banned": self.users_banned,
            "orders_today": self.orders_today,
            "orders_by_status": self.orders_by_status,
            "revenue_today_units": self.revenue_today_units,
            "revenue_7d_units": self.revenue_7d_units,
            "deposits_today_units": self.deposits_today_units,
            "pending_payments": self.pending_payments,
            "open_tickets": self.open_tickets,
            "queued_notifications": self.queued_notifications,
            "active_services": self.active_services,
            "errors_24h": self.errors_24h,
        }


@dataclass(slots=True)
class FinancialReport:
    """تقرير مالي لفترة محددة."""

    start_iso: str
    end_iso: str
    orders_count: int
    revenue_units: int
    provider_cost_units: int
    profit_units: int | None
    deposits_units: int
    refunds_units: int
    partial_refunds_units: int
    manual_credit_units: int
    manual_debit_units: int

    @property
    def profit_known(self) -> bool:
        """هل الربح محسوب فعلياً؟ (يتطلب تسجيل أسعار المزود على الخدمات)."""
        return self.profit_units is not None


@dataclass(slots=True)
class OperationsReport:
    """تقرير تشغيلي عن جودة التنفيذ."""

    total_orders: int
    completed: int
    partial: int
    failed: int
    canceled: int
    refunded: int
    success_rate: float
    stuck_orders: int
    uncertain_orders: int


class StatsService:
    """تجميع الإحصائيات والتقارير للوحة الأدمن."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        auth: AuthService,
        providers: ProviderService,
    ) -> None:
        """تهيئة الخدمة بالاعتماديات المطلوبة."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.auth = auth
        self.providers = providers

    # ===================================================================== #
    #                           لوحة المعلومات                              #
    # ===================================================================== #

    async def dashboard(self, actor: User) -> DashboardStats:
        """
        أرقام لوحة المعلومات السريعة (صلاحية `stats.view`).

        الاستثناءات: PermissionDeniedError
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)

        start_today, end_today = day_bounds_utc(0)
        week_ago = iso_minus_days(7)
        day_ago = iso_minus_days(1)

        return DashboardStats(
            users_total=await self.repos.users.count_all(),
            users_new_today=await self.repos.users.count_since(start_today),
            users_active_7d=await self.repos.users.count_active_since(week_ago),
            users_banned=await self.repos.users.count_banned(),
            orders_today=await self.repos.orders.count_between(start_today, end_today),
            orders_by_status=await self.repos.orders.status_counts(),
            revenue_today_units=await self.repos.orders.sum_cost_between(start_today, end_today),
            revenue_7d_units=await self.repos.orders.sum_cost_between(week_ago, utc_now_iso()),
            deposits_today_units=await self.repos.payments.sum_approved_between(
                start_today, end_today
            ),
            pending_payments=await self.repos.payments.count_pending(),
            open_tickets=await self.repos.tickets.count_open(),
            queued_notifications=await self.repos.notifications.count_queued(),
            active_services=await self.repos.services.count_active(),
            errors_24h=await self.repos.error_logs.count_since(day_ago),
        )

    async def dashboard_text(self, actor: User) -> str:
        """لوحة المعلومات كنص عربي جاهز للإرسال في تيليجرام."""
        stats = await self.dashboard(actor)
        symbol = await self.settings.money_symbol()
        by_status = stats.orders_by_status
        active = (
            by_status.get(OrderStatus.PENDING, 0)
            + by_status.get(OrderStatus.SUBMITTED, 0)
            + by_status.get(OrderStatus.IN_PROGRESS, 0)
        )
        lines = [
            "📊 <b>لوحة المعلومات</b>",
            "",
            f"👥 المستخدمون: {stats.users_total} (جديد اليوم: {stats.users_new_today})",
            f"🔥 نشطون آخر 7 أيام: {stats.users_active_7d} • محظورون: {stats.users_banned}",
            "",
            f"🧾 طلبات اليوم: {stats.orders_today} • قيد التنفيذ الآن: {active}",
            f"✅ مكتملة: {by_status.get(OrderStatus.COMPLETED, 0)} • "
            f"⚠️ جزئية: {by_status.get(OrderStatus.PARTIAL, 0)} • "
            f"❌ فاشلة: {by_status.get(OrderStatus.FAILED, 0)}",
            f"❓ غير مؤكدة: {by_status.get(OrderStatus.SUBMIT_UNCERTAIN, 0)}",
            "",
            f"💰 مبيعات اليوم: {format_units(stats.revenue_today_units, symbol=symbol)}",
            f"💰 مبيعات 7 أيام: {format_units(stats.revenue_7d_units, symbol=symbol)}",
            f"💳 إيداعات اليوم: {format_units(stats.deposits_today_units, symbol=symbol)}",
            "",
            f"🧮 طلبات شحن معلّقة: {stats.pending_payments}",
            f"🎫 تذاكر مفتوحة: {stats.open_tickets}",
            f"📨 إشعارات بانتظار الإرسال: {stats.queued_notifications}",
            f"🛒 خدمات مفعّلة: {stats.active_services}",
            f"🐞 أخطاء آخر 24 ساعة: {stats.errors_24h}",
        ]
        return "\n".join(lines)

    # ===================================================================== #
    #                           التقارير المالية                            #
    # ===================================================================== #

    async def financial_report(
        self, actor: User, *, days: int = 7, include_profit: bool = True
    ) -> FinancialReport:
        """
        تقرير مالي لفترة بالأيام.

        الربح يُحسب فقط إذا كانت تكلفة المزود مسجّلة على الطلبات؛ وإلا تُعاد None
        بدل رقم مضلل. ويتطلب عرضه صلاحية `stats.profit`.
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        start_iso = iso_minus_days(days)
        end_iso = utc_now_iso()

        revenue = await self.repos.orders.sum_cost_between(start_iso, end_iso)
        provider_cost = await self.repos.orders.sum_provider_cost_between(start_iso, end_iso)
        orders_count = await self.repos.orders.count_between(start_iso, end_iso)

        profit: int | None = None
        if include_profit and await self.auth.has_permission(actor, Permission.STATS_PROFIT):
            profit = (revenue - provider_cost) if provider_cost > 0 else None

        return FinancialReport(
            start_iso=start_iso,
            end_iso=end_iso,
            orders_count=orders_count,
            revenue_units=revenue,
            provider_cost_units=provider_cost,
            profit_units=profit,
            deposits_units=await self.repos.payments.sum_approved_between(start_iso, end_iso),
            refunds_units=await self.repos.transactions.sum_by_type(
                TransactionType.REFUND, start_iso=start_iso, end_iso=end_iso
            ),
            partial_refunds_units=await self.repos.transactions.sum_by_type(
                TransactionType.PARTIAL_REFUND, start_iso=start_iso, end_iso=end_iso
            ),
            manual_credit_units=await self.repos.transactions.sum_by_type(
                TransactionType.MANUAL_CREDIT, start_iso=start_iso, end_iso=end_iso
            ),
            manual_debit_units=await self.repos.transactions.sum_by_type(
                TransactionType.MANUAL_DEBIT, start_iso=start_iso, end_iso=end_iso
            ),
        )

    async def financial_report_text(self, actor: User, *, days: int = 7) -> str:
        """التقرير المالي كنص عربي جاهز للعرض."""
        report = await self.financial_report(actor, days=days)
        symbol = await self.settings.money_symbol()
        lines = [
            f"💼 <b>التقرير المالي — آخر {days} يوم</b>",
            "",
            f"🧾 عدد الطلبات: {report.orders_count}",
            f"💰 إجمالي المبيعات: {format_units(report.revenue_units, symbol=symbol)}",
            f"💳 إجمالي الإيداعات المعتمدة: {format_units(report.deposits_units, symbol=symbol)}",
            f"↩️ استرجاع كامل: {format_units(report.refunds_units, symbol=symbol)}",
            f"↩️ استرجاع جزئي: {format_units(report.partial_refunds_units, symbol=symbol)}",
            f"➕ إضافات يدوية: {format_units(report.manual_credit_units, symbol=symbol)}",
            f"➖ خصومات يدوية: {format_units(report.manual_debit_units, symbol=symbol)}",
        ]
        if report.profit_known and report.profit_units is not None:
            lines.append(
                f"📈 الربح التقديري: {format_units(report.profit_units, symbol=symbol)} "
                f"(تكلفة المزود: {format_units(report.provider_cost_units, symbol=symbol)})"
            )
        else:
            lines.append("📈 الربح: غير محسوب — سجّل أسعار المزود على الخدمات لحسابه.")
        return "\n".join(lines)

    async def wallet_liability(self, actor: User) -> tuple[int, int, int]:
        """
        التزامات المحفظة: (مجموع أرصدة المستخدمين، إجمالي الإيداعات، إجمالي الإنفاق).

        يساعد على معرفة المبلغ المستحق للعملاء في أي لحظة.
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        total_balance = await self.repos.users.total_balance_units()
        deposits = await self.repos.transactions.sum_by_type(TransactionType.DEPOSIT)
        spent = await self.repos.transactions.sum_by_type(TransactionType.ORDER)
        return total_balance, deposits, spent

    # ===================================================================== #
    #                          التقارير التشغيلية                           #
    # ===================================================================== #

    async def operations_report(self, actor: User, *, days: int = 7) -> OperationsReport:
        """
        تقرير جودة التنفيذ: نسب الاكتمال والفشل والطلبات التي تحتاج تدخلاً.
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        start_iso = iso_minus_days(days)
        end_iso = utc_now_iso()

        total = await self.repos.orders.count_between(start_iso, end_iso)
        completed = await self.repos.orders.count_between_by_status(
            start_iso, end_iso, [OrderStatus.COMPLETED]
        )
        partial = await self.repos.orders.count_between_by_status(
            start_iso, end_iso, [OrderStatus.PARTIAL]
        )
        failed = await self.repos.orders.count_between_by_status(
            start_iso, end_iso, [OrderStatus.FAILED]
        )
        canceled = await self.repos.orders.count_between_by_status(
            start_iso, end_iso, [OrderStatus.CANCELED]
        )
        refunded = await self.repos.orders.count_between_by_status(
            start_iso, end_iso, [OrderStatus.REFUNDED]
        )

        stuck_hours = await self.settings.get_int("order_stuck_alert_hours", 24)
        stuck = len(
            await self.repos.orders.stuck_orders(
                before_iso=iso_plus_seconds(-max(1, stuck_hours) * 3600), limit=200
            )
        )
        uncertain = (await self.repos.orders.status_counts()).get(
            OrderStatus.SUBMIT_UNCERTAIN, 0
        )
        success_rate = round((completed + partial) * 100 / total, 1) if total else 0.0

        return OperationsReport(
            total_orders=total,
            completed=completed,
            partial=partial,
            failed=failed,
            canceled=canceled,
            refunded=refunded,
            success_rate=success_rate,
            stuck_orders=stuck,
            uncertain_orders=uncertain,
        )

    async def top_services(self, actor: User, *, days: int = 30, limit: int = 5) -> list[dict]:
        """أكثر الخدمات طلباً خلال فترة (اسم الخدمة، العدد، القيمة)."""
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        return await self.repos.orders.top_services(
            start_iso=iso_minus_days(days), end_iso=utc_now_iso(), limit=limit
        )

    async def top_users(self, actor: User, *, limit: int = 5) -> list[tuple[str, int]]:
        """أكثر المستخدمين إنفاقاً: (الاسم الظاهر، إجمالي الإنفاق)."""
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        users = await self.repos.users.top_spenders(limit=limit)
        return [(user.display_name, user.total_spent_units) for user in users]

    async def daily_series(self, actor: User, *, days: int = 14) -> list[dict]:
        """سلسلة يومية بعدد الطلبات وقيمتها (لرسم اتجاه بسيط نصياً)."""
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        return await self.repos.orders.daily_series(
            start_iso=iso_minus_days(days), end_iso=utc_now_iso()
        )

    # ===================================================================== #
    #                            صحة النظام                                 #
    # ===================================================================== #

    async def system_digest(self) -> dict[str, int]:
        """
        أرقام الملخص اليومي — **بلا فاعل بشري**.

        لماذا بلا `actor` ولا فحص صلاحية؟ لأن المستدعي مهمة دورية لا مستخدم،
        والنتيجة لا تُعرض لأحد مباشرة: تُحوَّل إلى إشعار يوزَّع على من يملك
        `stats.view` فعلاً عبر `notify_admins`. فالحارس في مكان التوزيع لا هنا.

        المخرجات: قاموس أرقام جاهز لقالب الإشعار.
        """
        start_today, end_today = day_bounds_utc(0)
        by_status = await self.repos.orders.status_counts()
        attention = sum(
            by_status.get(status, 0)
            for status in (OrderStatus.SUBMIT_UNCERTAIN, OrderStatus.FAILED)
        )
        return {
            "orders_today": await self.repos.orders.count_between(start_today, end_today),
            "revenue_today_units": await self.repos.orders.sum_cost_between(
                start_today, end_today
            ),
            "deposits_today_units": await self.repos.payments.sum_approved_between(
                start_today, end_today
            ),
            "pending_payments": await self.repos.payments.count_pending(),
            "attention_orders": attention,
            "open_tickets": await self.repos.tickets.count_open(),
            "new_users_today": await self.repos.users.count_since(start_today),
            "errors_24h": await self.repos.error_logs.count_since(iso_minus_days(1)),
        }

    async def system_health(self, actor: User) -> dict[str, object]:
        """
        مؤشرات صحة النظام: المزودون، صندوق الإشعارات، الأخطاء، حجم قاعدة البيانات.

        الاستثناءات: PermissionDeniedError
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)

        providers = await self.repos.providers.list_all()
        provider_rows: list[dict[str, object]] = []
        for provider in providers:
            health = await self.providers.health(provider)
            provider_rows.append(
                {
                    "name": provider.name,
                    "usable": health.is_usable,
                    "reason": health.reason,
                    "consecutive_failures": provider.consecutive_failures,
                    "balance_units": provider.balance_units,
                    "last_success_at": provider.last_success_at,
                }
            )

        db_size_bytes = self.db.path.stat().st_size if self.db.path.exists() else 0
        return {
            "providers": provider_rows,
            "queued_notifications": await self.repos.notifications.count_queued(),
            "errors_24h": await self.repos.error_logs.count_since(iso_minus_days(1)),
            "db_size_mb": round(db_size_bytes / (1024 * 1024), 2),
            "db_path": str(self.db.path),
        }

    async def health_text(self, actor: User) -> str:
        """مؤشرات صحة النظام كنص عربي."""
        health = await self.system_health(actor)
        symbol = await self.settings.money_symbol()
        lines = ["🩺 <b>صحة النظام</b>", ""]

        providers = health["providers"]
        if isinstance(providers, list) and providers:
            for row in providers:
                mark = "🟢" if row["usable"] else "🔴"
                lines.append(
                    f"{mark} {row['name']} — {row['reason']} • "
                    f"رصيد: {format_units(int(row['balance_units']), symbol=symbol)}"
                )
        else:
            lines.append("⚠️ لا يوجد مزودون مسجّلون بعد.")

        lines += [
            "",
            f"📨 إشعارات بانتظار الإرسال: {health['queued_notifications']}",
            f"🐞 أخطاء آخر 24 ساعة: {health['errors_24h']}",
            f"🗄 حجم قاعدة البيانات: {health['db_size_mb']} ميغابايت",
        ]
        return "\n".join(lines)
```

---

## واجهة المراقبة في لوحة التحكم

### `handlers/admin/system.py`  ·  جديد  ·  167 سطراً

شاشة «⏱ المهام الدورية»: حالة كل مهمة + «تشغيل الآن» لمن يملك `settings.maintenance`.

```python
"""
قسم «⏱ المهام الدورية» في لوحة التحكم (المرحلة 6).

ما يعرضه:
    • حالة كل مهمة مجدولة: جدولتها، آخر تشغيل، عدد الجولات، الإخفاقات،
      التخطّيات بسبب التداخل، زمن آخر جولة ومتوسطه، وآخر خطأ إن وُجد.
    • زر «تشغيل الآن» لكل مهمة لمن يملك `settings.maintenance`.

لماذا شاشة مستقلة؟
    لأن «النظام يعمل» ليست حالة يُفترض الوثوق بها: المهمة قد تتوقف بصمت
    (استثناء متكرر، أو جولة معلّقة) ويستمر البوت يردّ على الأزرار كأن شيئاً
    لم يكن. هذه الشاشة تجعل نبض النظام مرئياً بضغطة واحدة.

المصدر: `jobs.runner.JOB_REGISTRY` — سجل في الذاكرة يُحدَّث مع كل جولة.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from core.permissions import Permission
from handlers.admin.common import admin_required, args, permissions_of
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from jobs import JOB_LABELS
from jobs.runner import JOB_REGISTRY, JobStats
from keyboards.admin_kb import jobs_home_kb
from texts import admin_ar as t
from utils.formatters import datetime_text, safe
from utils.logging_setup import get_logger

logger = get_logger(__name__)


def _duration_text(milliseconds: int | None) -> str:
    """عرض مدة بالميلي ثانية بصيغة عربية مقروءة."""
    if milliseconds is None:
        return "—"
    if milliseconds < 1000:
        return f"{milliseconds} ملّي"
    return f"{milliseconds / 1000:.1f} ثانية"


def _job_line(stats: JobStats) -> str:
    """سطر واحد يصف حالة مهمة في شاشة المهام."""
    if stats.running:
        icon = "🏃"
    elif stats.runs == 0:
        icon = "⚪️"
    elif stats.is_healthy:
        icon = "🟢"
    else:
        icon = "🔴"

    error_line = (
        t.JOB_ERROR_LINE.format(error=safe(stats.last_error, limit=120))
        if stats.last_error
        else ""
    )
    return t.JOB_LINE.format(
        icon=icon,
        label=JOB_LABELS.get(stats.name, stats.name),
        schedule=stats.schedule_text or "—",
        last_run=datetime_text(stats.last_finished_at) if stats.last_finished_at else t.JOB_NEVER_RAN,
        runs=stats.runs,
        failures=stats.failures,
        skipped=stats.skipped,
        duration=_duration_text(stats.last_duration_ms),
        average=_duration_text(stats.average_duration_ms or None),
        error_line=error_line,
    )


def jobs_overview_text() -> str:
    """
    نص شاشة المهام كاملاً (يُستخدم أيضاً في اختبارات العرض).

    المخرجات: نص HTML جاهز للإرسال، أو رسالة «لا مهام» إن كان السجل فارغاً.
    """
    jobs = JOB_REGISTRY.snapshot()
    if not jobs:
        return t.JOBS_NONE

    failing = [job for job in jobs if not job.is_healthy]
    running = [JOB_LABELS.get(job.name, job.name) for job in jobs if job.running]
    return t.JOBS_HOME.format(
        total=len(jobs),
        healthy=len(jobs) - len(failing),
        failing=len(failing),
        running_line=(
            t.JOBS_RUNNING_LINE.format(names="، ".join(running)) if running else ""
        ),
        lines="\n".join(_job_line(job) for job in jobs),
    )


@guarded
@admin_required(Permission.STATS_VIEW)
async def jobs_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة «⏱ المهام الدورية»: حالة كل مهمة مجدولة في النسخة العاملة."""
    await answer_callback(update)
    perms = await permissions_of(context)
    names = [job.name for job in JOB_REGISTRY.snapshot()]
    await render(update, context, jobs_overview_text(), jobs_home_kb(names, perms))


@guarded
@admin_required(Permission.SETTINGS_MAINTENANCE)
async def run_job_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    تشغيل مهمة دورية فوراً بدل انتظار موعدها.

    التشغيل يمر على نفس الغلاف المُشرِف (`supervise`) لا على الدالة الخام،
    فيبقى محمياً بمنع التداخل والمهلة وتسجيل الأخطاء تماماً كالجولة المجدولة.
    """
    name = args(update).arg(0) or ""
    stats = JOB_REGISTRY.get(name)
    callback = JOB_REGISTRY.callback(name)
    if stats is None or callback is None:
        await answer_callback(update, t.JOB_NOT_FOUND, alert=True)
        return

    if stats.running:
        await answer_callback(update, t.JOB_RUN_BUSY, alert=True)
        return

    label = JOB_LABELS.get(name, name)
    await answer_callback(update, t.JOB_RUN_STARTED.format(label=label))
    failures_before = stats.failures
    logger.info("شغّل الأدمن المهمة %s يدوياً", name)

    await callback(context)                      # لا يرفع استثناءً: الغلاف يبتلعه ويسجّله

    failed = stats.failures > failures_before
    await send(
        update,
        context,
        t.JOB_RUN_DONE.format(
            icon="❌" if failed else "✅",
            label=label,
            duration=_duration_text(stats.last_duration_ms),
            result_line=(
                t.JOB_RUN_FAIL_LINE.format(error=safe(stats.last_error, limit=150))
                if failed
                else t.JOB_RUN_OK_LINE
            ),
        ),
    )
    await jobs_screen(update, context)


def conversations() -> list:
    """لا محادثات في هذا القسم — شاشات وأزرار فقط."""
    return []


def screens() -> list:
    """أزرار شاشة المهام الدورية."""
    from telegram.ext import CallbackQueryHandler

    from keyboards.callback_data import NS_ADMIN, pattern

    return [
        CallbackQueryHandler(jobs_screen, pattern=pattern(NS_ADMIN, "jobs")),
        CallbackQueryHandler(run_job_now, pattern=pattern(NS_ADMIN, "jobrun")),
    ]
```

### `handlers/admin/dashboard.py`  ·  مُحدَّث  ·  133 سطراً

شاشة صحة النظام تلخّص حالة المهام وتعرض زر الدخول لشاشتها.

```python
"""
شاشة لوحة التحكم الرئيسية + شاشة صحة النظام + الأمر /admin.

مبدأ الشاشة: القائمة تُبنى من صلاحيات هذا الأدمن تحديداً، فأدمن الدعم يرى
«🎫 الدعم» فقط، ومراجع المدفوعات يرى «💰 المدفوعات» فقط. والأرقام الظاهرة
في الرأس تُعرض لمن يملك `stats.view` فقط.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from core.enums import OrderStatus
from core.permissions import Permission
from handlers.admin.common import admin_required, permissions_of, symbol_of
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render
from jobs import JOB_LABELS
from jobs.runner import JOB_REGISTRY
from keyboards.admin_kb import admin_menu_kb, health_kb
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from utils.datetime_utils import utc_now_iso
from utils.formatters import datetime_text, money_text

#: الحالات التي تُحتسب «طلبات نشطة» في رأس اللوحة
ACTIVE_FOR_DASHBOARD = (
    OrderStatus.PENDING,
    OrderStatus.SUBMITTING,
    OrderStatus.SUBMITTED,
    OrderStatus.IN_PROGRESS,
)

#: الحالات التي تعني «يحتاج تدخل أدمن الآن»
ATTENTION_FOR_DASHBOARD = (OrderStatus.SUBMIT_UNCERTAIN, OrderStatus.FAILED)


async def _panel_text(update: Update, context: ContextTypes.DEFAULT_TYPE, perms: set[str]) -> str:
    """
    بناء نص رأس اللوحة: الأرقام الكاملة لمن يملك `stats.view`، وعنوان مختصر لغيره.

    لا نستدعي خدمة الإحصائيات أصلاً لمن لا يملك الصلاحية، حتى لا يمتلئ سجل
    التدقيق بمحاولات رفض لا ذنب للأدمن فيها (زيارته للوحة ليست محاولة اختراق).
    """
    if Permission.STATS_VIEW not in perms:
        return t.PANEL_SIMPLE

    services = services_of(context)
    admin = require_user(context)
    stats = await services.stats.dashboard(admin)
    symbol = await symbol_of(context)
    by_status = stats.orders_by_status
    return t.DASHBOARD.format(
        users_total=stats.users_total,
        users_new_today=stats.users_new_today,
        users_active_7d=stats.users_active_7d,
        users_banned=stats.users_banned,
        orders_today=stats.orders_today,
        active_orders=sum(by_status.get(status, 0) for status in ACTIVE_FOR_DASHBOARD),
        attention_orders=sum(by_status.get(status, 0) for status in ATTENTION_FOR_DASHBOARD),
        revenue_today=money_text(stats.revenue_today_units, symbol),
        revenue_7d=money_text(stats.revenue_7d_units, symbol),
        deposits_today=money_text(stats.deposits_today_units, symbol),
        pending_payments=stats.pending_payments,
        open_tickets=stats.open_tickets,
        queued=stats.queued_notifications,
        active_services=stats.active_services,
        errors_24h=stats.errors_24h,
        now=datetime_text(utc_now_iso()),
    )


@guarded
@admin_required()
async def panel_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الشاشة الرئيسية للوحة التحكم (زر «🛠 لوحة التحكم» و«🔄 تحديث»)."""
    await answer_callback(update)
    services = services_of(context)
    perms = await permissions_of(context)

    pending = (
        await services.payments.pending_count() if Permission.PAYMENTS_VIEW in perms else 0
    )
    tickets = await services.tickets.open_count() if Permission.TICKETS_VIEW in perms else 0

    await render(
        update,
        context,
        await _panel_text(update, context, perms),
        admin_menu_kb(perms, pending_payments=pending, open_tickets=tickets),
    )


@guarded
@admin_required()
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الأمر /admin — مدخل اللوحة لمن يملك `admin.access` فقط."""
    await panel_screen(update, context)


def _jobs_health_line() -> str:
    """
    سطر حالة المهام الدورية داخل شاشة صحة النظام (المرحلة 6).

    مصدره سجل التشغيل في الذاكرة؛ إن كانت الجدولة لم تتم بعد (كما في بعض
    الاختبارات) يُرجع نصاً فارغاً بدل ادّعاء حالة لا نعرفها.
    """
    jobs = JOB_REGISTRY.snapshot()
    if not jobs:
        return ""
    failing = [job for job in jobs if not job.is_healthy]
    failing_text = (
        t.HEALTH_JOBS_FAILING.format(
            names="، ".join(JOB_LABELS.get(job.name, job.name) for job in failing)
        )
        if failing
        else ""
    )
    return t.HEALTH_JOBS_SECTION.format(
        healthy=len(jobs) - len(failing), total=len(jobs), failing_text=failing_text
    )


@guarded
@admin_required(Permission.STATS_VIEW)
async def health_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة صحة النظام: المزودون، المهام الدورية، الإشعارات، الأخطاء، حجم القاعدة."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    text = await services.stats.health_text(admin) + _jobs_health_line()
    await render(update, context, text, health_kb())
```

### `handlers/admin/__init__.py`  ·  مُحدَّث  ·  63 سطراً

تسجيل وحدة `system` ضمن أقسام اللوحة.

```python
"""
حزمة لوحة التحكم: تجميع معالجات كل الأقسام في مكانين فقط.

تصدّر هذه الحزمة دالتين يستهلكهما `handlers/registry.py`:

    admin_conversations()   : كل محادثات الأدمن (تُسجَّل قبل أزرار الشاشات).
    admin_screen_handlers() : كل أزرار شاشات الأدمن.

كل وحدة قسم (`users`, `payments`, ...) تصدّر `conversations()` و`screens()`
فيبقى ترتيب التسجيل في مكان واحد ويظل من السهل التأكد أن كل زر له معالج.
"""

from __future__ import annotations

from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler

from handlers.admin import (
    catalog,
    dashboard,
    logs,
    orders,
    payments,
    providers,
    settings,
    system,
    tickets,
    users,
)
from keyboards.callback_data import NS_ADMIN, pattern

#: وحدات الأقسام بالترتيب الذي تُسجَّل به معالجاتها
SECTIONS = (users, payments, orders, tickets, catalog, providers, settings, logs, system)

__all__ = [
    "admin_conversations",
    "admin_screen_handlers",
    "admin_command_handlers",
    "SECTIONS",
]


def admin_conversations() -> list[ConversationHandler]:
    """كل محادثات لوحة التحكم مجموعة من كل الأقسام."""
    collected: list[ConversationHandler] = []
    for section in SECTIONS:
        collected.extend(section.conversations())
    return collected


def admin_screen_handlers() -> list[CallbackQueryHandler]:
    """كل أزرار شاشات لوحة التحكم (خارج المحادثات)."""
    collected: list[CallbackQueryHandler] = [
        CallbackQueryHandler(dashboard.panel_screen, pattern=pattern(NS_ADMIN, "home")),
        CallbackQueryHandler(dashboard.health_screen, pattern=pattern(NS_ADMIN, "health")),
    ]
    for section in SECTIONS:
        collected.extend(section.screens())
    return collected


def admin_command_handlers() -> list[CommandHandler]:
    """أوامر لوحة التحكم (/admin فقط حالياً)."""
    return [CommandHandler("admin", dashboard.admin_command)]
```

### `keyboards/admin_kb.py`  ·  مُحدَّث  ·  941 سطراً

`jobs_home_kb` + زر «⏱ المهام الدورية» في `health_kb` + تسميات الأزرار القصيرة.

```python
"""
لوحات أزرار لوحة التحكم.

قاعدتان ملزمتان في هذا الملف:

1. **لا يظهر زر لا يملك الأدمن صلاحيته.** كل باني لوحة يستقبل مجموعة صلاحيات
   المستخدم (`perms`) ويبني الأزرار على أساسها. هذا لا يُغني عن فحص الصلاحية
   داخل المعالج نفسه (الزر قد يُضغط من رسالة قديمة بعد سحب الصلاحية) — الفحصان
   مطلوبان معاً.
2. **لا زر بلا معالج.** كل `callback_data` هنا يقابله معالج مسجَّل في
   `handlers/registry.py`، ويتحقق من ذلك اختبار `test_no_dead_buttons`.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from core.enums import OrderStatus
from core.order_state import allowed_next
from core.permissions import Permission
from database.models import (
    Order,
    Payment,
    Provider,
    Service,
    ServiceCategory,
    Setting,
    SupportTicket,
    User,
)
from integrations.providers.base import ProviderServiceItem
from keyboards.callback_data import (
    NS_ADM_CAT,
    NS_ADM_LOG,
    NS_ADM_ORD,
    NS_ADM_PAY,
    NS_ADM_PRV,
    NS_ADM_SET,
    NS_ADM_TKT,
    NS_ADM_USERS,
    NS_ADMIN,
    NS_FLOW,
    pack,
)
from keyboards.common_kb import home_button, pagination_row
from texts import admin_ar as t
from utils.formatters import money_text, order_status_text, safe, ticket_status_text

#: تصفية قوائم الطلبات في لوحة الأدمن (الرمز ⇐ الاسم والحالات المشمولة)
ADMIN_ORDER_FILTERS: dict[str, tuple[str, tuple[str, ...]]] = {
    "att": (
        t.ORDER_FILTER_ATTENTION,
        (OrderStatus.SUBMIT_UNCERTAIN, OrderStatus.FAILED),
    ),
    "act": (
        t.ORDER_FILTER_ACTIVE,
        (
            OrderStatus.PENDING,
            OrderStatus.SUBMITTING,
            OrderStatus.SUBMITTED,
            OrderStatus.IN_PROGRESS,
        ),
    ),
    "all": (t.ORDER_FILTER_ALL, ()),
}

#: تصفية قوائم التذاكر في لوحة الأدمن
ADMIN_TICKET_FILTERS: dict[str, str] = {
    "open": t.TICKET_FILTER_OPEN,
    "wait": t.TICKET_FILTER_WAITING,
    "mine": t.TICKET_FILTER_MINE,
    "closed": t.TICKET_FILTER_CLOSED,
}


# ============================= أدوات داخلية ============================= #


def _panel_row(*, with_home: bool = True) -> list[InlineKeyboardButton]:
    """صف سفلي موحّد: رجوع إلى لوحة التحكم (+ القائمة الرئيسية للمستخدم)."""
    row = [InlineKeyboardButton(t.BTN_BACK_PANEL, callback_data=pack(NS_ADMIN, "home"))]
    if with_home:
        row.append(home_button())
    return row


def _back_row(namespace: str, action: str, *args: object) -> list[InlineKeyboardButton]:
    """صف رجوع إلى شاشة أدمن محددة + لوحة التحكم."""
    return [
        InlineKeyboardButton("🔙 رجوع", callback_data=pack(namespace, action, *args)),
        InlineKeyboardButton(t.BTN_BACK_PANEL, callback_data=pack(NS_ADMIN, "home")),
    ]


def _cancel_row() -> list[InlineKeyboardButton]:
    """صف إلغاء داخل محادثات الأدمن."""
    return [InlineKeyboardButton("❌ إلغاء", callback_data=pack(NS_FLOW, "cancel"))]


def back_panel_kb() -> InlineKeyboardMarkup:
    """لوحة فيها الرجوع إلى لوحة التحكم فقط (تُرفق برسائل النتائج)."""
    return InlineKeyboardMarkup([_panel_row()])


def cancel_only_kb() -> InlineKeyboardMarkup:
    """لوحة فيها زر إلغاء فقط (تُرفق بأسئلة محادثات الأدمن)."""
    return InlineKeyboardMarkup([_cancel_row()])


def confirm_cancel_kb(label: str = t.BTN_CONFIRM_DANGER) -> InlineKeyboardMarkup:
    """لوحة تأكيد عملية خطيرة (تأكيد صريح + إلغاء)."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=pack(NS_FLOW, "confirm"))], _cancel_row()]
    )


def skip_cancel_kb() -> InlineKeyboardMarkup:
    """لوحة تخطي خطوة اختيارية داخل محادثات الأدمن."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⏭ تخطي", callback_data=pack(NS_FLOW, "skip"))], _cancel_row()]
    )


# ============================ القائمة الرئيسية ========================== #


def admin_menu_kb(perms: set[str], *, pending_payments: int = 0, open_tickets: int = 0) -> InlineKeyboardMarkup:
    """
    قائمة لوحة التحكم — تُبنى حسب صلاحيات هذا الأدمن تحديداً.

    المدخلات:
        perms            : مجموعة صلاحيات المستخدم الحالية.
        pending_payments : عدد طلبات الشحن المعلّقة (يظهر كعدّاد على الزر).
        open_tickets     : عدد التذاكر المفتوحة (عدّاد على الزر).
    """
    rows: list[list[InlineKeyboardButton]] = []
    current: list[InlineKeyboardButton] = []

    def add(button: InlineKeyboardButton) -> None:
        """إضافة زر مع ترتيب الأزرار في صفوف من اثنين."""
        current.append(button)
        if len(current) == 2:
            rows.append(list(current))
            current.clear()

    if Permission.USERS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_USERS, callback_data=pack(NS_ADM_USERS, "home")))
    if Permission.PAYMENTS_VIEW in perms:
        label = t.MENU_PAYMENTS + (f" ({pending_payments})" if pending_payments else "")
        add(InlineKeyboardButton(label, callback_data=pack(NS_ADM_PAY, "list", 1)))
    if Permission.ORDERS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_ORDERS, callback_data=pack(NS_ADM_ORD, "list", "att", 1)))
    if Permission.TICKETS_VIEW in perms:
        label = t.MENU_TICKETS + (f" ({open_tickets})" if open_tickets else "")
        add(InlineKeyboardButton(label, callback_data=pack(NS_ADM_TKT, "list", "open", 1)))
    if Permission.SERVICES_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_CATALOG, callback_data=pack(NS_ADM_CAT, "home")))
    if Permission.PROVIDERS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_PROVIDERS, callback_data=pack(NS_ADM_PRV, "home")))
    if Permission.SETTINGS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_SETTINGS, callback_data=pack(NS_ADM_SET, "home")))
    if Permission.LOGS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_LOGS, callback_data=pack(NS_ADM_LOG, "home")))
    if Permission.STATS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_HEALTH, callback_data=pack(NS_ADMIN, "health")))

    if current:
        rows.append(list(current))

    rows.append(
        [
            InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADMIN, "home")),
            home_button(),
        ]
    )
    return InlineKeyboardMarkup(rows)


#: تسميات قصيرة لأزرار «تشغيل الآن» في شاشة المهام (الوصف الكامل في نص الشاشة)
JOB_SHORT_LABELS: dict[str, str] = {
    "notifications_dispatch": "الإشعارات",
    "orders_submit": "إرسال الطلبات",
    "orders_check": "متابعة الطلبات",
    "payments_expire": "صلاحية الشحن",
    "tickets_auto_close": "إغلاق التذاكر",
    "orders_stuck_alert": "الطلبات المتوقفة",
    "providers_balance": "أرصدة المزودين",
    "providers_health": "صحة المزودين",
    "admin_daily_digest": "الملخص اليومي",
    "database_maintenance": "صيانة القاعدة",
}


def health_kb() -> InlineKeyboardMarkup:
    """أزرار شاشة صحة النظام (تحديث + دخول شاشة المهام الدورية)."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADMIN, "health"))],
            [InlineKeyboardButton(t.BTN_JOBS, callback_data=pack(NS_ADMIN, "jobs"))],
            _panel_row(),
        ]
    )


def jobs_home_kb(job_names: list[str], perms: set[str]) -> InlineKeyboardMarkup:
    """
    شاشة المهام الدورية: تحديث + «تشغيل الآن» لكل مهمة لمن يملك الصلاحية.

    التشغيل اليدوي مشروط بـ`settings.maintenance` لأنه تدخل تشغيلي في إيقاع
    النظام (قد يستدعي المزود أو يرسل إشعارات) لا مجرد قراءة.
    """
    rows = [[InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADMIN, "jobs"))]]
    if Permission.SETTINGS_MAINTENANCE in perms:
        rows += [
            [
                InlineKeyboardButton(
                    f"{t.BTN_JOB_RUN} · {JOB_SHORT_LABELS.get(name, name)}",
                    callback_data=pack(NS_ADMIN, "jobrun", name),
                )
            ]
            for name in job_names
        ]
    rows.append(_back_row(NS_ADMIN, "health"))
    return InlineKeyboardMarkup(rows)


# ============================= المستخدمون =============================== #


def users_home_kb(perms: set[str]) -> InlineKeyboardMarkup:
    """شاشة المستخدمين: بحث + رجوع."""
    rows = [[InlineKeyboardButton(t.BTN_USER_SEARCH, callback_data=pack(NS_ADM_USERS, "search"))]]
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def user_results_kb(users: list[User]) -> InlineKeyboardMarkup:
    """نتائج البحث: زر لكل مستخدم."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'🚫 ' if user.is_banned else ''}{user.display_name} · {user.telegram_id}",
                callback_data=pack(NS_ADM_USERS, "view", user.id),
            )
        ]
        for user in users
    ]
    rows.append(
        [InlineKeyboardButton(t.BTN_USER_SEARCH, callback_data=pack(NS_ADM_USERS, "search"))]
    )
    rows.append(_back_row(NS_ADM_USERS, "home"))
    return InlineKeyboardMarkup(rows)


def user_card_kb(user: User, perms: set[str]) -> InlineKeyboardMarkup:
    """أزرار بطاقة المستخدم حسب الصلاحيات المتاحة."""
    rows: list[list[InlineKeyboardButton]] = []

    money_row: list[InlineKeyboardButton] = []
    if Permission.USERS_BALANCE_CREDIT in perms:
        money_row.append(
            InlineKeyboardButton(
                t.BTN_USER_CREDIT, callback_data=pack(NS_ADM_USERS, "credit", user.id)
            )
        )
    if Permission.USERS_BALANCE_DEBIT in perms:
        money_row.append(
            InlineKeyboardButton(
                t.BTN_USER_DEBIT, callback_data=pack(NS_ADM_USERS, "debit", user.id)
            )
        )
    if money_row:
        rows.append(money_row)

    state_row: list[InlineKeyboardButton] = []
    if user.is_banned and Permission.USERS_UNBAN in perms:
        state_row.append(
            InlineKeyboardButton(
                t.BTN_USER_UNBAN, callback_data=pack(NS_ADM_USERS, "unban", user.id)
            )
        )
    elif not user.is_banned and Permission.USERS_BAN in perms:
        state_row.append(
            InlineKeyboardButton(t.BTN_USER_BAN, callback_data=pack(NS_ADM_USERS, "ban", user.id))
        )
    if Permission.USERS_NOTE in perms:
        state_row.append(
            InlineKeyboardButton(t.BTN_USER_NOTE, callback_data=pack(NS_ADM_USERS, "note", user.id))
        )
    if state_row:
        rows.append(state_row)

    if Permission.USERS_ROLE_CHANGE in perms:
        rows.append(
            [InlineKeyboardButton(t.BTN_USER_ROLE, callback_data=pack(NS_ADM_USERS, "role", user.id))]
        )

    history_row: list[InlineKeyboardButton] = []
    if Permission.ORDERS_VIEW in perms:
        history_row.append(
            InlineKeyboardButton(
                t.BTN_USER_ORDERS, callback_data=pack(NS_ADM_USERS, "orders", user.id, 1)
            )
        )
    history_row.append(
        InlineKeyboardButton(t.BTN_USER_TX, callback_data=pack(NS_ADM_USERS, "tx", user.id, 1))
    )
    rows.append(history_row)

    rows.append(_back_row(NS_ADM_USERS, "home"))
    return InlineKeyboardMarkup(rows)


def user_role_kb(user: User) -> InlineKeyboardMarkup:
    """أزرار اختيار الدور الجديد للمستخدم."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'• ' if user.role == code else ''}{label}",
                callback_data=pack(NS_ADM_USERS, "setrole", user.id, code),
            )
        ]
        for code, label in t.ASSIGNABLE_ROLES.items()
    ]
    rows.append(_back_row(NS_ADM_USERS, "view", user.id))
    return InlineKeyboardMarkup(rows)


def user_role_confirm_kb(user_id: int, role_code: str) -> InlineKeyboardMarkup:
    """تأكيد ثانٍ قبل تغيير الدور (إجراء خطير يغيّر الصلاحيات فوراً)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t.BTN_CONFIRM_DANGER,
                    callback_data=pack(NS_ADM_USERS, "roleok", user_id, role_code),
                )
            ],
            [InlineKeyboardButton("🔙 رجوع", callback_data=pack(NS_ADM_USERS, "role", user_id))],
        ]
    )


def user_list_nav_kb(
    action: str, user_id: int, *, page: int, total_pages: int
) -> InlineKeyboardMarkup:
    """ترقيم قوائم طلبات/معاملات مستخدم بعينه."""
    rows: list[list[InlineKeyboardButton]] = []
    nav = pagination_row(
        NS_ADM_USERS, action, page=page, total_pages=total_pages, prefix_args=(user_id,)
    )
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_USERS, "view", user_id))
    return InlineKeyboardMarkup(rows)


# ============================= المدفوعات ================================ #


def payments_list_kb(
    payments: list[Payment], *, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """قائمة طلبات الشحن المعلّقة."""
    rows = [
        [
            InlineKeyboardButton(
                f"#{payment.id} · {money_text(payment.amount_units, symbol)}",
                callback_data=pack(NS_ADM_PAY, "view", payment.id),
            )
        ]
        for payment in payments
    ]
    nav = pagination_row(NS_ADM_PAY, "list", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def payment_card_kb(payment: Payment, perms: set[str], *, is_pending: bool) -> InlineKeyboardMarkup:
    """أزرار بطاقة طلب الشحن (الاعتماد/الرفض تظهر للمعلّق فقط)."""
    rows: list[list[InlineKeyboardButton]] = []
    if payment.proof_file_id:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_PAYMENT_PROOF, callback_data=pack(NS_ADM_PAY, "proof", payment.id)
                )
            ]
        )
    if is_pending:
        action_row: list[InlineKeyboardButton] = []
        if Permission.PAYMENTS_APPROVE in perms:
            action_row.append(
                InlineKeyboardButton(
                    t.BTN_PAYMENT_APPROVE, callback_data=pack(NS_ADM_PAY, "ok", payment.id)
                )
            )
        if Permission.PAYMENTS_REJECT in perms:
            action_row.append(
                InlineKeyboardButton(
                    t.BTN_PAYMENT_REJECT, callback_data=pack(NS_ADM_PAY, "no", payment.id)
                )
            )
        if action_row:
            rows.append(action_row)
    if Permission.USERS_VIEW in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    "👤 صاحب الطلب", callback_data=pack(NS_ADM_USERS, "view", payment.user_id)
                )
            ]
        )
    rows.append(_back_row(NS_ADM_PAY, "list", 1))
    return InlineKeyboardMarkup(rows)


def payment_approve_kb() -> InlineKeyboardMarkup:
    """تأكيد الاعتماد مع إمكانية تعديل المبلغ المضاف."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_CONFIRM_DANGER, callback_data=pack(NS_FLOW, "confirm"))],
            [InlineKeyboardButton(t.BTN_EDIT_AMOUNT, callback_data=pack(NS_ADM_PAY, "amount"))],
            _cancel_row(),
        ]
    )


# ============================== الطلبات ================================= #


def admin_orders_filters_row(current: str) -> list[InlineKeyboardButton]:
    """صف تصفية قوائم الطلبات."""
    return [
        InlineKeyboardButton(
            f"{'• ' if code == current else ''}{label}",
            callback_data=pack(NS_ADM_ORD, "list", code, 1),
        )
        for code, (label, _statuses) in ADMIN_ORDER_FILTERS.items()
    ]


def admin_orders_kb(
    orders: list[Order], *, filter_code: str, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """قائمة الطلبات في لوحة الأدمن."""
    rows = [
        [
            InlineKeyboardButton(
                f"{order_status_text(order.status).split(' ', 1)[0]} "
                f"{order.public_code or order.id} · {money_text(order.cost_units, symbol)}",
                callback_data=pack(NS_ADM_ORD, "view", order.id, filter_code, page),
            )
        ]
        for order in orders
    ]
    rows.append(admin_orders_filters_row(filter_code))
    nav = pagination_row(
        NS_ADM_ORD, "list", page=page, total_pages=total_pages, prefix_args=(filter_code,)
    )
    if nav:
        rows.append(nav)
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def admin_order_card_kb(
    order: Order, perms: set[str], *, filter_code: str, page: int
) -> InlineKeyboardMarkup:
    """أزرار بطاقة الطلب الإدارية (كل زر مشروط بصلاحيته وبحالة الطلب)."""
    rows: list[list[InlineKeyboardButton]] = []
    is_final = not allowed_next(order.status)

    first_row: list[InlineKeyboardButton] = []
    if Permission.ORDERS_RECHECK in perms and order.provider_order_id and not is_final:
        first_row.append(
            InlineKeyboardButton(
                t.BTN_ORDER_RECHECK, callback_data=pack(NS_ADM_ORD, "recheck", order.id)
            )
        )
    if Permission.ORDERS_LINK_PROVIDER_ID in perms and order.status == OrderStatus.SUBMIT_UNCERTAIN:
        first_row.append(
            InlineKeyboardButton(
                t.BTN_ORDER_LINK, callback_data=pack(NS_ADM_ORD, "link", order.id)
            )
        )
    if first_row:
        rows.append(first_row)

    danger_row: list[InlineKeyboardButton] = []
    if Permission.ORDERS_CANCEL in perms and not is_final:
        danger_row.append(
            InlineKeyboardButton(
                t.BTN_ORDER_CANCEL, callback_data=pack(NS_ADM_ORD, "cancel", order.id)
            )
        )
    if Permission.ORDERS_REFUND in perms and not is_final:
        danger_row.append(
            InlineKeyboardButton(t.BTN_ORDER_FAIL, callback_data=pack(NS_ADM_ORD, "fail", order.id))
        )
    if danger_row:
        rows.append(danger_row)

    if Permission.ORDERS_STATUS_OVERRIDE in perms and allowed_next(order.status):
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_ORDER_OVERRIDE, callback_data=pack(NS_ADM_ORD, "force", order.id)
                )
            ]
        )

    if Permission.USERS_VIEW in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_ORDER_USER, callback_data=pack(NS_ADM_USERS, "view", order.user_id)
                )
            ]
        )

    rows.append(_back_row(NS_ADM_ORD, "list", filter_code, page))
    return InlineKeyboardMarkup(rows)


def order_override_kb(order: Order) -> InlineKeyboardMarkup:
    """أزرار الحالات المسموح الانتقال إليها من الحالة الحالية فقط."""
    rows = [
        [
            InlineKeyboardButton(
                order_status_text(status),
                callback_data=pack(NS_ADM_ORD, "setst", order.id, status),
            )
        ]
        for status in sorted(allowed_next(order.status))
    ]
    rows.append(_back_row(NS_ADM_ORD, "view", order.id, "all", 1))
    return InlineKeyboardMarkup(rows)


# =============================== الدعم ================================== #


def admin_tickets_filters_row(current: str) -> list[InlineKeyboardButton]:
    """صف تصفية قوائم التذاكر."""
    return [
        InlineKeyboardButton(
            f"{'• ' if code == current else ''}{label}",
            callback_data=pack(NS_ADM_TKT, "list", code, 1),
        )
        for code, label in ADMIN_TICKET_FILTERS.items()
    ]


def admin_tickets_kb(
    tickets: list[SupportTicket], *, filter_code: str, page: int, total_pages: int
) -> InlineKeyboardMarkup:
    """قائمة التذاكر في لوحة الأدمن."""
    rows = [
        [
            InlineKeyboardButton(
                f"{ticket_status_text(ticket.status).split(' ', 1)[0]} #{ticket.id} · "
                f"{safe(ticket.subject, limit=28)}",
                callback_data=pack(NS_ADM_TKT, "view", ticket.id),
            )
        ]
        for ticket in tickets
    ]
    rows.append(admin_tickets_filters_row(filter_code))
    nav = pagination_row(
        NS_ADM_TKT, "list", page=page, total_pages=total_pages, prefix_args=(filter_code,)
    )
    if nav:
        rows.append(nav)
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def admin_ticket_card_kb(
    ticket: SupportTicket, perms: set[str], *, filter_code: str = "open"
) -> InlineKeyboardMarkup:
    """أزرار بطاقة التذكرة الإدارية."""
    rows: list[list[InlineKeyboardButton]] = []
    action_row: list[InlineKeyboardButton] = []
    if ticket.is_open and Permission.TICKETS_REPLY in perms:
        action_row.append(
            InlineKeyboardButton(
                t.BTN_TICKET_REPLY, callback_data=pack(NS_ADM_TKT, "reply", ticket.id)
            )
        )
    if ticket.is_open and Permission.TICKETS_CLOSE in perms:
        action_row.append(
            InlineKeyboardButton(
                t.BTN_TICKET_CLOSE, callback_data=pack(NS_ADM_TKT, "close", ticket.id)
            )
        )
    if action_row:
        rows.append(action_row)

    if ticket.is_open and Permission.TICKETS_ASSIGN in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_TICKET_ASSIGN, callback_data=pack(NS_ADM_TKT, "assign", ticket.id)
                )
            ]
        )
    if Permission.USERS_VIEW in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_TICKET_USER, callback_data=pack(NS_ADM_USERS, "view", ticket.user_id)
                )
            ]
        )
    rows.append(_back_row(NS_ADM_TKT, "list", filter_code, 1))
    return InlineKeyboardMarkup(rows)


# ============================== الكتالوج ================================ #


def catalog_home_kb(categories: list[ServiceCategory], perms: set[str]) -> InlineKeyboardMarkup:
    """شاشة الكتالوج: التصنيفات + إضافة تصنيف."""
    rows = [
        [
            InlineKeyboardButton(
                category.title, callback_data=pack(NS_ADM_CAT, "cat", category.id, 1)
            )
        ]
        for category in categories
    ]
    if Permission.SERVICES_CREATE in perms:
        rows.append(
            [
                InlineKeyboardButton(t.BTN_SERVICE_NEW, callback_data=pack(NS_ADM_CAT, "newsvc")),
                InlineKeyboardButton(t.BTN_CATEGORY_NEW, callback_data=pack(NS_ADM_CAT, "newcat")),
            ]
        )
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def catalog_services_kb(
    services: list[Service], *, category_id: int, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """قائمة خدمات تصنيف في لوحة الأدمن (مع مؤشر التفعيل)."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'🟢' if service.is_active else '⚪️'} {safe(service.name, limit=26)} · "
                f"{money_text(service.price_per_1000_units, symbol)}",
                callback_data=pack(NS_ADM_CAT, "svc", service.id),
            )
        ]
        for service in services
    ]
    nav = pagination_row(
        NS_ADM_CAT, "cat", page=page, total_pages=total_pages, prefix_args=(category_id,)
    )
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_CAT, "home"))
    return InlineKeyboardMarkup(rows)


def service_card_kb(service: Service, perms: set[str]) -> InlineKeyboardMarkup:
    """أزرار بطاقة الخدمة الإدارية."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    if Permission.SERVICES_UPDATE in perms and not service.is_archived:
        label = t.BTN_SERVICE_TOGGLE_OFF if service.is_active else t.BTN_SERVICE_TOGGLE_ON
        row.append(InlineKeyboardButton(label, callback_data=pack(NS_ADM_CAT, "toggle", service.id)))
    if Permission.SERVICES_PRICE in perms and not service.is_archived:
        row.append(
            InlineKeyboardButton(
                t.BTN_SERVICE_PRICE, callback_data=pack(NS_ADM_CAT, "price", service.id)
            )
        )
    if row:
        rows.append(row)
    if Permission.SERVICES_ARCHIVE in perms and not service.is_archived:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_SERVICE_ARCHIVE, callback_data=pack(NS_ADM_CAT, "archive", service.id)
                )
            ]
        )
    rows.append(_back_row(NS_ADM_CAT, "cat", service.category_id, 1))
    return InlineKeyboardMarkup(rows)


# ============================= الإعدادات ================================ #


def settings_home_kb(
    groups: list[str], perms: set[str], *, maintenance_on: bool
) -> InlineKeyboardMarkup:
    """مجموعات الإعدادات + مفتاح وضع الصيانة."""
    rows = [
        [InlineKeyboardButton(f"⚙️ {group}", callback_data=pack(NS_ADM_SET, "group", group, 1))]
        for group in groups
    ]
    if Permission.SETTINGS_MAINTENANCE in perms:
        label = t.BTN_MAINTENANCE_OFF if maintenance_on else t.BTN_MAINTENANCE_ON
        rows.append([InlineKeyboardButton(label, callback_data=pack(NS_ADM_SET, "maint"))])
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def settings_group_kb(
    settings: list[Setting], *, group: str, page: int, total_pages: int, perms: set[str]
) -> InlineKeyboardMarkup:
    """مفاتيح مجموعة إعدادات (القابل للتعديل فقط يصبح زراً)."""
    rows: list[list[InlineKeyboardButton]] = []
    if Permission.SETTINGS_UPDATE in perms:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        f"✏️ {safe(setting.name_ar or setting.key, limit=32)}",
                        callback_data=pack(NS_ADM_SET, "edit", setting.key),
                    )
                ]
                for setting in settings
                if setting.is_editable
            ]
        )
    nav = pagination_row(
        NS_ADM_SET, "group", page=page, total_pages=total_pages, prefix_args=(group,)
    )
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_SET, "home"))
    return InlineKeyboardMarkup(rows)


# ============================== السجلات ================================= #


def logs_home_kb() -> InlineKeyboardMarkup:
    """اختيار نوع السجل."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_LOG_AUDIT, callback_data=pack(NS_ADM_LOG, "audit", 1))],
            [InlineKeyboardButton(t.BTN_LOG_ERRORS, callback_data=pack(NS_ADM_LOG, "errors", 1))],
            _panel_row(),
        ]
    )


def logs_page_kb(action: str, *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """ترقيم صفحات السجلات."""
    rows: list[list[InlineKeyboardButton]] = []
    nav = pagination_row(NS_ADM_LOG, action, page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_LOG, "home"))
    return InlineKeyboardMarkup(rows)


# ============================== المزودون ================================ #


def providers_home_kb(providers: list[Provider], perms: set[str]) -> InlineKeyboardMarkup:
    """
    قائمة المزودين.

    كل زر يحمل مؤشر حالة (🟢 مفعّل · ⚪️ متوقف) وتلميح المفتاح لا المفتاح نفسه.
    """
    rows = [
        [
            InlineKeyboardButton(
                f"{'🟢' if provider.is_active else '⚪️'} {safe(provider.name, limit=28)}",
                callback_data=pack(NS_ADM_PRV, "view", provider.id),
            )
        ]
        for provider in providers
    ]
    if Permission.PROVIDERS_CREATE in perms:
        rows.append(
            [InlineKeyboardButton(t.BTN_PROVIDER_NEW, callback_data=pack(NS_ADM_PRV, "new"))]
        )
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def provider_card_kb(provider: Provider, perms: set[str]) -> InlineKeyboardMarkup:
    """أزرار بطاقة المزود — كل زر مشروط بصلاحيته."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    if Permission.PROVIDERS_TEST in perms:
        row.append(
            InlineKeyboardButton(
                t.BTN_PROVIDER_TEST, callback_data=pack(NS_ADM_PRV, "test", provider.id)
            )
        )
        row.append(
            InlineKeyboardButton(
                t.BTN_PROVIDER_BALANCE, callback_data=pack(NS_ADM_PRV, "bal", provider.id)
            )
        )
    if row:
        rows.append(row)
        row = []

    if Permission.SERVICES_SYNC in perms:
        row.append(
            InlineKeyboardButton(
                t.BTN_PROVIDER_SYNC, callback_data=pack(NS_ADM_PRV, "sync", provider.id)
            )
        )
    if Permission.SERVICES_CREATE in perms:
        row.append(
            InlineKeyboardButton(
                t.BTN_PROVIDER_IMPORT, callback_data=pack(NS_ADM_PRV, "imp", provider.id)
            )
        )
    if row:
        rows.append(row)
        row = []

    if Permission.PROVIDERS_UPDATE in perms:
        label = t.BTN_PROVIDER_OFF if provider.is_active else t.BTN_PROVIDER_ON
        row.append(
            InlineKeyboardButton(label, callback_data=pack(NS_ADM_PRV, "toggle", provider.id))
        )
    if Permission.PROVIDERS_KEY_UPDATE in perms:
        row.append(
            InlineKeyboardButton(
                t.BTN_PROVIDER_KEY, callback_data=pack(NS_ADM_PRV, "key", provider.id)
            )
        )
    if row:
        rows.append(row)

    if Permission.SERVICES_VIEW in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_PROVIDER_SERVICES, callback_data=pack(NS_ADM_PRV, "svcs", provider.id, 1)
                )
            ]
        )
    rows.append(_back_row(NS_ADM_PRV, "home"))
    return InlineKeyboardMarkup(rows)


def provider_type_kb() -> InlineKeyboardMarkup:
    """اختيار نوع واجهة المزود عند إضافته (من الأنواع المدعومة فعلياً فقط)."""
    from integrations.providers.registry import available_types

    rows = [
        [
            InlineKeyboardButton(
                t.PROVIDER_TYPE_LABELS.get(api_type, api_type),
                callback_data=pack(NS_ADM_PRV, "type", api_type),
            )
        ]
        for api_type in available_types()
    ]
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


def provider_services_kb(
    services: list[Service], *, provider_id: int, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """قائمة خدماتنا المرتبطة بمزود (تفتح بطاقة الخدمة في قسم الكتالوج)."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'🟢' if service.is_active else '⚪️'} {safe(service.name, limit=24)} · "
                f"{money_text(service.price_per_1000_units, symbol)}",
                callback_data=pack(NS_ADM_CAT, "svc", service.id),
            )
        ]
        for service in services
    ]
    nav = pagination_row(
        NS_ADM_PRV, "svcs", page=page, total_pages=total_pages, prefix_args=(provider_id,)
    )
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_PRV, "view", provider_id))
    return InlineKeyboardMarkup(rows)


def provider_import_results_kb(
    items: list[ProviderServiceItem], *, provider_id: int, symbol: str
) -> InlineKeyboardMarkup:
    """
    نتائج البحث في قائمة خدمات المزود.

    الزر يحمل **فهرس العنصر** في النتائج المحفوظة مؤقتاً لا رقم الخدمة، لأن
    أرقام بعض المزودين طويلة وقد تتجاوز حد 64 بايت مع بقية الوسائط.
    """
    rows = [
        [
            InlineKeyboardButton(
                f"{safe(item.name, limit=28)} · {money_text(item.rate_per_1000_units, symbol)}",
                callback_data=pack(NS_ADM_PRV, "pick", index),
            )
        ]
        for index, item in enumerate(items)
    ]
    rows.append(_back_row(NS_ADM_PRV, "view", provider_id))
    return InlineKeyboardMarkup(rows)


def category_picker_kb(
    categories: list[ServiceCategory], namespace: str, action: str
) -> InlineKeyboardMarkup:
    """اختيار تصنيف داخل محادثة (يُستخدم في الاستيراد وفي إنشاء خدمة يدوياً)."""
    rows = [
        [InlineKeyboardButton(category.title, callback_data=pack(namespace, action, category.id))]
        for category in categories
    ]
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


def provider_picker_kb(
    providers: list[Provider], namespace: str, action: str
) -> InlineKeyboardMarkup:
    """اختيار مزود داخل محادثة إنشاء خدمة."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'🟢' if provider.is_active else '⚪️'} {safe(provider.name, limit=28)}",
                callback_data=pack(namespace, action, provider.id),
            )
        ]
        for provider in providers
    ]
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)
```

### `texts/admin_ar.py`  ·  مُحدَّث (مقتطف)  ·  731 سطراً (المعروض: 44 سطراً من قسم المرحلة 6)

قسم نصوص المهام الدورية في آخر الملف.

```python
# ======================================================================== #
#                   المهام الدورية ومراقبتها (المرحلة 6)                   #
# ======================================================================== #

BTN_JOBS = "⏱ المهام الدورية"
BTN_JOB_RUN = "▶️ تشغيل الآن"

JOBS_HOME = (
    "⏱ <b>المهام الدورية</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "المهام: {total} · سليمة: {healthy} · متعثرة: {failing}\n"
    "{running_line}"
    "\n{lines}"
    "\nℹ️ هذه إحصاءات التشغيل الحالي فقط — تُصفَّر عند إعادة تشغيل البوت.\n"
    "الأخطاء نفسها محفوظة في «📋 السجلات ← الأخطاء»."
)
JOBS_RUNNING_LINE = "🏃 تعمل الآن: {names}\n"
JOBS_NONE = (
    "⏱ <b>المهام الدورية</b>\n\n"
    "لا توجد مهام مجدولة في هذه النسخة قيد التشغيل.\n"
    "إن كنت ترى هذه الرسالة والبوت يعمل فهذا خلل — راجع سجل الإقلاع."
)
JOB_LINE = (
    "{icon} <b>{label}</b>\n"
    "   ⏲ {schedule} · آخر تشغيل: {last_run}\n"
    "   🔁 جولات: {runs} · ⚠️ إخفاقات: {failures} · ⏭ تخطٍّ: {skipped}\n"
    "   ⌛️ آخر مدة: {duration} · متوسط: {average}\n"
    "{error_line}"
)
JOB_ERROR_LINE = "   🐞 آخر خطأ: <code>{error}</code>\n"
JOB_NEVER_RAN = "لم تعمل بعد"
JOB_RUN_STARTED = "▶️ شُغّلت المهمة «{label}» الآن…"
JOB_RUN_DONE = (
    "{icon} <b>انتهت المهمة «{label}»</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "⌛️ المدة: {duration}\n"
    "{result_line}"
)
JOB_RUN_OK_LINE = "✅ اكتملت بلا أخطاء."
JOB_RUN_FAIL_LINE = "❌ انتهت بخطأ: <code>{error}</code>\nالتفاصيل في «📋 السجلات ← الأخطاء»."
JOB_RUN_BUSY = "⏳ المهمة تعمل الآن بالفعل — انتظر انتهاء الجولة الحالية."
JOB_NOT_FOUND = "❌ هذه المهمة غير مجدولة في النسخة العاملة."
HEALTH_JOBS_SECTION = "\n⏱ المهام: {healthy}/{total} سليمة{failing_text}"
HEALTH_JOBS_FAILING = " · ⚠️ متعثرة: {names}"
```

### `texts/templates.py`  ·  مُحدَّث (مقتطف)  ·  305 سطراً (المعروض: 46 سطراً من قسم المرحلة 6)

قوالب الإشعارات الجديدة: مهمة متعثرة، تعافي مزود، الملخص اليومي.

```python
# ----------------------- المرحلة 6: المهام الدورية ---------------------- #


def admin_job_failing(*, job_name: str, failures: int, error: str) -> tuple[str, str]:
    """تنبيه أدمن: مهمة دورية تفشل بشكل متكرر (مؤشر عطل صامت في النظام)."""
    return (
        "🛠 مهمة دورية متعثرة",
        f"المهمة «{job_name}» فشلت {failures} مرات متتالية.\n"
        f"آخر خطأ: {error}\n"
        "راجع «📋 السجلات ← الأخطاء» في لوحة التحكم.",
    )


def admin_provider_recovered(*, provider_name: str, failures: int) -> tuple[str, str]:
    """تنبيه أدمن: مزود كان متعثراً وعاد يستجيب."""
    return (
        "✅ تعافى مزود",
        f"المزود «{provider_name}» عاد يستجيب بعد {failures} أخطاء متتالية، "
        "وأُعيد تفعيل الإرسال إليه.",
    )


def admin_daily_digest(
    *,
    orders_today: int,
    revenue_today_units: int,
    deposits_today_units: int,
    pending_payments: int,
    attention_orders: int,
    open_tickets: int,
    new_users: int,
    errors_24h: int,
    symbol: str = "",
) -> tuple[str, str]:
    """الملخص اليومي للأدمن: أرقام أمس/اليوم في رسالة واحدة."""
    return (
        "📊 الملخص اليومي",
        f"📦 طلبات اليوم: {orders_today}\n"
        f"💰 مبيعات اليوم: {money(revenue_today_units, symbol)}\n"
        f"💳 إيداعات معتمدة اليوم: {money(deposits_today_units, symbol)}\n"
        f"👥 مستخدمون جدد: {new_users}\n"
        f"⏳ طلبات شحن تنتظر المراجعة: {pending_payments}\n"
        f"⚠️ طلبات تحتاج انتباهك: {attention_orders}\n"
        f"🎫 تذاكر مفتوحة: {open_tickets}\n"
        f"🐞 أخطاء آخر 24 ساعة: {errors_24h}",
    )
```

---

## الإعدادات والإصدار

### `database/migrations/0005_phase6_jobs.sql`  ·  جديد  ·  32 سطراً

8 إعدادات جديدة تضبط إيقاع المهام (بلا أي تغيير في المخطط).

```sql
-- =====================================================================
-- الترحيل 0005 — إعدادات المرحلة 6 (المهام الدورية والمتابعة الآلية)
-- السبب: إيقاع النظام (كل كم دقيقة نفحص الأرصدة، متى يصل الملخص اليومي،
--        متى نُنبّه على مهمة متعثرة) قرار تشغيلي يتغيّر بحجم العمل،
--        فيجب أن يُضبط من لوحة التحكم لا من ثوابت في الكود.
-- ملاحظة: لا تغيير في المخطط — إضافة صفوف إعدادات فقط.
-- =====================================================================

INSERT OR IGNORE INTO settings (key, value, value_type, group_code, name_ar, description_ar, is_editable, updated_at) VALUES
    ('provider_balance_check_minutes', '30', 'int', 'providers', 'فحص أرصدة المزودين كل (دقيقة)',
     'كل كم دقيقة يُقرأ رصيدنا لدى كل مزود مفعّل مع تنبيه الانخفاض', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('provider_health_watch_minutes', '10', 'int', 'providers', 'مراقبة صحة المزودين كل (دقيقة)',
     'كل كم دقيقة يُختبر المزود المتعثر لإعادة تفعيله فور تعافيه', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('order_multi_status_enabled', '1', 'bool', 'orders', 'فحص حالة الطلبات دفعة واحدة',
     'استعلام جماعي واحد لكل مزود بدل استدعاء لكل طلب - أطفئه فقط إن كان مزودك لا يدعمه', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('job_failure_alert_threshold', '3', 'int', 'general', 'تنبيه الأدمن بعد كم فشل متتالٍ لمهمة',
     'عدد إخفاقات المهمة الدورية المتتالية قبل إرسال تنبيه للأدمن', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('admin_digest_hour', '21', 'int', 'general', 'ساعة إرسال الملخص اليومي (0-23)',
     'بتوقيت Asia/Aden - ملخص يومي واحد لكل من يملك صلاحية الإحصائيات', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('db_maintenance_hour', '4', 'int', 'general', 'ساعة صيانة قاعدة البيانات (0-23)',
     'صيانة تقنية يومية لا تحذف أي بيانات تاريخية - يُفضّل وقت الذروة المنخفضة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('order_submit_batch_size', '5', 'int', 'orders', 'عدد الطلبات المُرسلة للمزود في الجولة',
     'كلما زاد العدد أسرع الإرسال وزاد الضغط على المزود - ابدأ صغيراً', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('order_check_batch_size', '20', 'int', 'orders', 'عدد الطلبات المفحوصة في الجولة',
     'تُفحص دفعة واحدة لكل مزود عند تفعيل الاستعلام الجماعي', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
```

### `utils/datetime_utils.py`  ·  مُحدَّث (مقتطف)  ·  109 سطراً (المعروض: 5 سطراً من قسم المرحلة 6)

`DEFAULT_TIMEZONE` و`APP_TIMEZONE` لجدولة المهام اليومية.

```python
#: المنطقة الزمنية المعتمدة للعرض وللمهام اليومية (تُستخدم عند عدم تمرير غيرها)
DEFAULT_TIMEZONE: str = "Asia/Aden"

#: كائن المنطقة الزمنية الجاهز (يحتاجه `run_daily` في JobQueue)
APP_TIMEZONE: ZoneInfo = ZoneInfo(DEFAULT_TIMEZONE)
```

### `core/constants.py`  ·  مُحدَّث  ·  44 سطراً

`APP_VERSION = "0.7.0-phase6"`.

```python
"""ثوابت عامة للنظام (قيم لا تتغير أثناء التشغيل)."""

from __future__ import annotations

#: اسم المشروع وإصداره
APP_NAME: str = "SMM Telegram Bot"
APP_VERSION: str = "0.7.0-phase6"

#: مدة قفل الطلب أثناء معالجته بواسطة job (بالثواني)
ORDER_LOCK_SECONDS: int = 120

#: أقصى عدد محاولات لإرسال الطلب إلى المزود عند الفشل الآمن (قبل اعتباره فاشلاً)
MAX_SUBMIT_ATTEMPTS: int = 3

#: أقصى عدد محاولات إرسال إشعار قبل اعتباره فاشلاً
MAX_NOTIFICATION_ATTEMPTS: int = 5

#: تدرج فترات إعادة فحص حالة الطلب (بالثواني)
ORDER_CHECK_BACKOFF: tuple[int, ...] = (60, 300, 900, 1800, 3600)

#: تدرج فترات إعادة إرسال الإشعار الفاشل (بالثواني)
NOTIFICATION_BACKOFF: tuple[int, ...] = (10, 60, 300, 1800, 3600)

#: مدة صلاحية مفاتيح منع التكرار الافتراضية (بالثواني)
IDEMPOTENCY_TTL_SECONDS: int = 24 * 3600

#: طول أقصى للنصوص المُخزَّنة من استجابات المزود (منعاً لتضخم قاعدة البيانات)
PROVIDER_RESPONSE_SNIPPET_LEN: int = 500

#: عدد العناصر في صفحة القوائم داخل تيليجرام
PAGE_SIZE: int = 8

#: صيغة مراجع الحركات المالية (تُستخدم لمنع التكرار)
REF_ORDER_DEBIT: str = "order:{order_id}"
REF_ORDER_REFUND: str = "refund:order:{order_id}"
REF_ORDER_PARTIAL_REFUND: str = "partial_refund:order:{order_id}"
REF_PAYMENT_DEPOSIT: str = "payment:{payment_id}"
REF_MANUAL: str = "manual:{kind}:{admin_id}:{token}"

#: صيغة مفاتيح منع تكرار الإشعارات
NOTIF_KEY_ORDER: str = "order:{order_id}:{event}"
NOTIF_KEY_PAYMENT: str = "payment:{payment_id}:{event}"
NOTIF_KEY_TICKET: str = "ticket:{ticket_id}:{event}"
NOTIF_KEY_MANUAL: str = "manual:{token}"
```

---

## الاختبارات

### `tests/unit/test_job_registry.py`  ·  جديد  ·  58 سطراً

اختبارات وحدة لسجل المهام وحساباته.

```python
"""
اختبارات وحدة لسجل المهام الدورية (`jobs.runner`) بلا قاعدة بيانات ولا تيليجرام.

ما تحرسه:
    • حساب المتوسط وحالة «سليمة/متعثرة» في `JobStats`.
    • تسجيل المهام واسترجاعها وتفريغ السجل.
"""

from __future__ import annotations

from jobs.runner import JobRegistry, JobStats


def test_job_stats_average_is_zero_before_any_run() -> None:
    """لا متوسط زمن قبل أول جولة — لا قسمة على صفر."""
    stats = JobStats(name="demo", interval_seconds=60)
    assert stats.average_duration_ms == 0
    assert stats.is_healthy is True


def test_job_stats_average_uses_completed_runs() -> None:
    """المتوسط = إجمالي المدد ÷ عدد الجولات."""
    stats = JobStats(name="demo", interval_seconds=60)
    stats.runs = 4
    stats.total_duration_ms = 1_000
    assert stats.average_duration_ms == 250


def test_job_stats_unhealthy_after_consecutive_failure() -> None:
    """أي فشل متتالٍ يجعل المهمة غير سليمة حتى تنجح جولة."""
    stats = JobStats(name="demo", interval_seconds=60)
    stats.consecutive_failures = 1
    assert stats.is_healthy is False
    assert "demo" in str(stats.as_dict())


def test_registry_register_and_lookup() -> None:
    """التسجيل ينشئ حالة وقفلاً، والاسترجاع يعمل بالاسم."""
    registry = JobRegistry()
    entry = registry.register("alpha", interval_seconds=30, schedule_text="كل 30 ثانية")

    assert registry.get("alpha") is entry
    assert registry.get("missing") is None
    assert "alpha" in registry.locks
    assert [job.name for job in registry.snapshot()] == ["alpha"]


def test_registry_clear_empties_everything() -> None:
    """التفريغ يزيل الحالات والأقفال والدوال (يُستخدم عند إعادة الجدولة)."""
    registry = JobRegistry()
    registry.register("alpha", interval_seconds=10)
    registry.callbacks["alpha"] = lambda context: None       # type: ignore[assignment]

    registry.clear()

    assert registry.snapshot() == []
    assert registry.callback("alpha") is None
    assert registry.locks == {}
```

### `tests/integration/test_jobs_phase6.py`  ·  جديد  ·  599 سطراً

21 اختباراً: الإشراف، الفحص الجماعي، مهام المزودين، الملخص، الصيانة، وشاشة المهام.

```python
"""
اختبارات المرحلة 6: الإشراف على المهام، الفحص الجماعي، مراقبة المزودين،
الملخص اليومي، صيانة القاعدة، وشاشة «⏱ المهام الدورية».

كل الاختبارات تستدعي المهام مباشرة بسياق مزيّف — بلا مؤقتات حقيقية وبلا شبكة.
"""

from __future__ import annotations

import asyncio

import pytest

from core.enums import OrderStatus
from database.models import Service, User
from database.repositories import Repositories
from handlers.admin import dashboard, system as admin_system
from jobs.maintenance_jobs import database_maintenance
from jobs.order_jobs import check_active_orders
from jobs.provider_jobs import refresh_provider_balances, watch_provider_health
from jobs.report_jobs import send_admin_daily_digest
from jobs.runner import JOB_REGISTRY, JobRegistry, supervise
from keyboards.callback_data import pack
from services import ServiceContainer
from tests.integration.test_user_interface import (
    bot,  # noqa: F401
    context,  # noqa: F401
    load_user,
    press,
)
from tests.telegram_fakes import FakeBot, FakeContext
from utils.datetime_utils import iso_plus_seconds, utc_now_iso

pytestmark = pytest.mark.asyncio


@pytest.fixture
def job_context(bot: FakeBot, services: ServiceContainer) -> FakeContext:
    """سياق مزيّف يحمل الخدمات كما تفعل JobQueue في التشغيل الحقيقي."""
    return FakeContext(bot, services)


@pytest.fixture
def clean_registry():
    """سجل المهام العام يُفرَّغ قبل كل اختبار يعتمد عليه وبعده."""
    JOB_REGISTRY.clear()
    yield JOB_REGISTRY
    JOB_REGISTRY.clear()


async def _credit(services: ServiceContainer, user: User, admin: User, units: int = 100_000) -> None:
    """شحن رصيد اختباري عبر الخدمة المركزية الوحيدة المسؤولة عن المال."""
    await services.wallet.adjust_balance(
        target=user, amount_units=units, admin=admin, reason="رصيد اختبار", credit=True
    )


async def _place_order(services: ServiceContainer, user: User, service: Service, link_suffix: str):
    """إنشاء طلب جاهز للإرسال (أداة مشتركة بين الاختبارات)."""
    return await services.orders.create_order(
        user,
        service_id=service.id,
        link=f"https://instagram.com/{link_suffix}",
        quantity=1_000,
    )


# ======================================================================== #
#                        1) الإشراف على المهام                             #
# ======================================================================== #


async def test_supervisor_records_successful_run(job_context: FakeContext) -> None:
    """الجولة الناجحة تُحدِّث العدّادات وتترك المهمة سليمة."""
    registry = JobRegistry()
    calls = []

    async def job(_context) -> None:
        """مهمة اختبارية ناجحة."""
        calls.append(1)

    runner = supervise(job, name="demo_ok", registry=registry, interval_seconds=30)
    await runner(job_context)

    stats = registry.get("demo_ok")
    assert calls == [1]
    assert stats.runs == 1
    assert stats.failures == 0
    assert stats.is_healthy
    assert stats.last_success_at is not None
    assert stats.last_duration_ms is not None


async def test_supervisor_swallows_error_and_logs_it(
    job_context: FakeContext, services: ServiceContainer, repos: Repositories
) -> None:
    """استثناء داخل المهمة لا يُسقط المهمة الدورية ويُكتب في `error_logs`."""
    registry = JobRegistry()
    before = await repos.error_logs.count_since(utc_now_iso()[:10])

    async def failing(_context) -> None:
        """مهمة اختبارية تفشل دائماً."""
        raise RuntimeError("انفجار اختباري")

    runner = supervise(failing, name="demo_fail", registry=registry, interval_seconds=30)
    await runner(job_context)                       # لا يرفع استثناءً

    stats = registry.get("demo_fail")
    assert stats.failures == 1
    assert stats.consecutive_failures == 1
    assert not stats.is_healthy
    assert "انفجار اختباري" in stats.last_error

    errors = await services.audit.recent_errors(limit=10)
    assert any("demo_fail" in str(row.get("source")) for row in errors)
    assert await repos.error_logs.count_since(utc_now_iso()[:10]) > before


async def test_supervisor_alerts_admin_after_threshold(
    job_context: FakeContext, services: ServiceContainer, admin: User
) -> None:
    """بعد بلوغ حد الإخفاقات المتتالية يصل تنبيه للأدمن (مرة واحدة لكل عدد)."""

    async def failing(_context) -> None:
        """مهمة تفشل دائماً لاختبار التنبيه."""
        raise RuntimeError("فشل متكرر")

    registry = JobRegistry()
    runner = supervise(
        failing,
        name="demo_alert",
        registry=registry,
        interval_seconds=30,
        failure_alert_threshold=2,
    )

    await runner(job_context)
    assert await services.notifications.queued_count() == 0      # أول فشل: لا تنبيه

    await runner(job_context)
    assert await services.notifications.queued_count() >= 1      # بلغ الحد ⇒ تنبيه

    notifications = await services.repos.notifications.list_for_user(admin.id, limit=5)
    assert any("مهمة دورية" in (item.title or "") for item in notifications)


async def test_supervisor_skips_overlapping_round(job_context: FakeContext) -> None:
    """جولة جديدة لا تبدأ فوق جولة لم تنتهِ — تُحتسب «تخطّياً» لا فشلاً."""
    registry = JobRegistry()
    release = asyncio.Event()
    entered = asyncio.Event()

    async def slow(_context) -> None:
        """مهمة بطيئة تبقى عاملة حتى نحرّرها."""
        entered.set()
        await release.wait()

    runner = supervise(slow, name="demo_slow", registry=registry, interval_seconds=5)
    first = asyncio.create_task(runner(job_context))
    await entered.wait()

    await runner(job_context)                        # الجولة الثانية أثناء الأولى
    stats = registry.get("demo_slow")
    assert stats.skipped == 1
    assert stats.runs == 0                           # الأولى لم تنتهِ بعد

    release.set()
    await first
    assert registry.get("demo_slow").runs == 1


async def test_supervisor_timeout_counts_as_failure(job_context: FakeContext) -> None:
    """الجولة التي تتجاوز المهلة تُلغى وتُسجَّل كفشل بدل أن تُعلَّق للأبد."""
    registry = JobRegistry()

    async def hanging(_context) -> None:
        """مهمة لا تنتهي أبداً."""
        await asyncio.sleep(30)

    runner = supervise(
        hanging, name="demo_timeout", registry=registry, interval_seconds=5, timeout_seconds=0.05
    )
    await runner(job_context)

    stats = registry.get("demo_timeout")
    assert stats.failures == 1
    assert not stats.is_healthy


# ======================================================================== #
#                   2) الفحص الجماعي لحالات الطلبات                        #
# ======================================================================== #


async def test_check_round_uses_single_multi_status_call(
    job_context: FakeContext,
    services: ServiceContainer,
    repos: Repositories,
    user: User,
    admin: User,
    mock_service: Service,
    mock_client,
    db,
) -> None:
    """ثلاثة طلبات لمزود واحد ⇒ استعلام جماعي واحد لا ثلاثة استعلامات."""
    await _credit(services, user, admin)
    user = await repos.users.get_by_id(user.id)

    for index in range(3):
        await _place_order(services, user, mock_service, f"user{index}")
    await services.orders.process_pending_orders(limit=5)

    async with db.transaction() as tx:
        await tx.execute(
            "UPDATE orders SET next_check_at = ? WHERE status IN ('submitted','in_progress')",
            (iso_plus_seconds(-60),),
        )

    await check_active_orders(job_context)

    rows = await db.fetchall(
        "SELECT request_summary FROM provider_requests WHERE request_summary LIKE 'multi-status%'"
    )
    assert len(rows) == 1, "كان يجب استعلام جماعي واحد لكل مزود في الجولة"
    assert "count=3" in rows[0]["request_summary"]


async def test_check_round_falls_back_for_unanswered_order(
    job_context: FakeContext,
    services: ServiceContainer,
    repos: Repositories,
    user: User,
    admin: User,
    mock_service: Service,
    mock_client,
    db,
) -> None:
    """الطلب الذي لم يُجب عنه الاستعلام الجماعي يُفحص فردياً ولا يُهمَل."""
    await _credit(services, user, admin)
    user = await repos.users.get_by_id(user.id)

    for index in range(2):
        await _place_order(services, user, mock_service, f"partial{index}")
    await services.orders.process_pending_orders(limit=5)

    original_multi = mock_client.get_multi_status

    async def partial_multi(provider_order_ids):
        """ردّ ناقص: يُجيب عن أول طلب فقط كما تفعل بعض اللوحات."""
        answers = await original_multi(provider_order_ids[:1])
        return answers

    mock_client.get_multi_status = partial_multi            # type: ignore[method-assign]
    mock_client.calls.clear()

    async with db.transaction() as tx:
        await tx.execute(
            "UPDATE orders SET next_check_at = ? WHERE status IN ('submitted','in_progress')",
            (iso_plus_seconds(-60),),
        )
    report = await services.orders.process_due_orders(limit=10)

    assert report.claimed == 2
    single_calls = [call for call in mock_client.calls if call[0] == "status"]
    assert single_calls, "لم يُفحص الطلب الناقص فردياً"


async def test_batch_failure_releases_orders_without_losing_them(
    job_context: FakeContext,
    services: ServiceContainer,
    repos: Repositories,
    user: User,
    admin: User,
    mock_service: Service,
    mock_client,
    db,
) -> None:
    """فشل الاستعلام الجماعي يؤجل الطلبات بتدرج ولا يغيّر حالتها ولا يفقدها."""
    from core.exceptions import ProviderTemporaryError

    await _credit(services, user, admin)
    user = await repos.users.get_by_id(user.id)

    for index in range(2):
        await _place_order(services, user, mock_service, f"down{index}")
    await services.orders.process_pending_orders(limit=5)

    async def broken_multi(_ids):
        """محاكاة انقطاع المزود أثناء الاستعلام الجماعي."""
        raise ProviderTemporaryError("انقطاع مؤقت")

    mock_client.get_multi_status = broken_multi             # type: ignore[method-assign]

    async with db.transaction() as tx:
        await tx.execute(
            "UPDATE orders SET next_check_at = ? WHERE status IN ('submitted','in_progress')",
            (iso_plus_seconds(-60),),
        )
    report = await services.orders.process_due_orders(limit=10)

    assert report.claimed == 2
    assert report.unchanged == 2
    orders = await repos.orders.list_by_statuses(
        [OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS]
    )
    assert len(orders) == 2
    assert all(order.locked_by is None for order in orders), "بقيت الطلبات محجوزة بعد الفشل"


# ======================================================================== #
#                      3) مهام مراقبة المزودين                             #
# ======================================================================== #


async def test_balance_job_updates_provider_and_snapshot(
    job_context: FakeContext, repos: Repositories, mock_provider, mock_client, db
) -> None:
    """مهمة الأرصدة تحفظ الرصيد في صف المزود وتضيف لقطة تاريخية."""
    updated = await refresh_provider_balances(job_context)

    assert updated == 1
    provider = await repos.providers.get(mock_provider.id)
    assert provider.balance_units == mock_client.balance_units
    assert provider.balance_checked_at is not None

    snapshots = await db.fetchall(
        "SELECT * FROM provider_balance_snapshots WHERE provider_id = ?", (mock_provider.id,)
    )
    assert len(snapshots) == 1


async def test_balance_job_alerts_admin_on_low_balance(
    job_context: FakeContext,
    services: ServiceContainer,
    repos: Repositories,
    mock_provider,
    mock_client,
    admin: User,
    db,
) -> None:
    """الرصيد تحت الحد ⇒ تنبيه للأدمن (ولا يتكرر لنفس القيمة)."""
    async with db.transaction() as tx:
        await repos.providers.update_fields(
            tx, mock_provider.id, low_balance_threshold_units=mock_client.balance_units + 1
        )

    await refresh_provider_balances(job_context)
    first = await services.notifications.queued_count()
    await refresh_provider_balances(job_context)
    second = await services.notifications.queued_count()

    assert first >= 1, "لم يصل تنبيه انخفاض الرصيد"
    assert second == first, "تكرر التنبيه نفسه في الجولة الثانية"


async def test_health_watch_recovers_provider(
    job_context: FakeContext,
    services: ServiceContainer,
    repos: Repositories,
    mock_provider,
    mock_client,
    admin: User,
    db,
) -> None:
    """مزود متعثر انتهت مدة إيقافه وعاد يستجيب ⇒ تصفير العداد + إشعار تعافٍ."""
    async with db.transaction() as tx:
        for _ in range(3):
            await repos.providers.record_failure(tx, mock_provider.id, "مهلة")
        await repos.providers.update_fields(
            tx, mock_provider.id, disabled_until=iso_plus_seconds(-60)
        )

    recovered = await watch_provider_health(job_context)

    assert recovered == 1
    provider = await repos.providers.get(mock_provider.id)
    assert provider.consecutive_failures == 0
    assert provider.disabled_until is None

    notifications = await services.repos.notifications.list_for_user(admin.id, limit=5)
    assert any("تعافى" in (item.title or "") for item in notifications)


async def test_health_watch_skips_provider_still_disabled(
    job_context: FakeContext, repos: Repositories, mock_provider, mock_client, db
) -> None:
    """المزود الموقوف مؤقتاً لا يُختبر قبل انتهاء مدته — نحترم فترة التهدئة."""
    async with db.transaction() as tx:
        await repos.providers.record_failure(tx, mock_provider.id, "مهلة")
        await repos.providers.update_fields(
            tx, mock_provider.id, disabled_until=iso_plus_seconds(600)
        )

    recovered = await watch_provider_health(job_context)

    assert recovered == 0
    provider = await repos.providers.get(mock_provider.id)
    assert provider.consecutive_failures == 1


# ======================================================================== #
#                   4) الملخص اليومي وصيانة القاعدة                        #
# ======================================================================== #


async def test_daily_digest_is_queued_once_per_day(
    job_context: FakeContext, services: ServiceContainer, admin: User
) -> None:
    """الملخص اليومي يُدرج مرة واحدة لليوم نفسه مهما تكرر استدعاء المهمة."""
    assert await send_admin_daily_digest(job_context) is True
    assert await send_admin_daily_digest(job_context) is False

    notifications = await services.repos.notifications.list_for_user(admin.id, limit=5)
    assert any("الملخص اليومي" in (item.title or "") for item in notifications)


async def test_database_maintenance_removes_only_expired_keys(
    job_context: FakeContext, services: ServiceContainer, repos: Repositories, user: User, db
) -> None:
    """الصيانة تحذف مفاتيح منع التكرار المنتهية فقط — ولا تمسّ البيانات التاريخية."""
    async with db.transaction() as tx:
        await repos.idempotency.try_acquire(tx, "fresh-key", scope="test", ttl_seconds=3600)
        await repos.idempotency.try_acquire(tx, "old-key", scope="test", ttl_seconds=3600)
        await tx.execute(
            "UPDATE idempotency_keys SET expires_at = ? WHERE key = 'old-key'",
            (iso_plus_seconds(-60),),
        )

    users_before = await repos.users.count_all()
    result = await database_maintenance(job_context)

    assert result["idempotency_keys_removed"] == 1
    assert await repos.idempotency.exists("fresh-key") is True
    assert await repos.idempotency.exists("old-key") is False
    assert await repos.users.count_all() == users_before


# ======================================================================== #
#                      5) شاشة «⏱ المهام الدورية»                          #
# ======================================================================== #


def _register_demo_jobs(registry) -> None:
    """تسجيل مهمتين في السجل العام: واحدة سليمة وواحدة متعثرة (للعرض)."""
    healthy = registry.register(
        "orders_check", interval_seconds=120, schedule_text="كل 2 دقيقة"
    )
    healthy.runs = 5
    healthy.last_finished_at = utc_now_iso()
    healthy.last_duration_ms = 320
    healthy.total_duration_ms = 1_600
    healthy.last_success_at = utc_now_iso()

    failing = registry.register(
        "providers_balance", interval_seconds=1800, schedule_text="كل 30 دقيقة"
    )
    failing.runs = 2
    failing.failures = 2
    failing.consecutive_failures = 2
    failing.last_error = "انقطاع الاتصال بالمزود"
    failing.last_finished_at = utc_now_iso()
    failing.last_duration_ms = 980
    failing.total_duration_ms = 1_900


async def test_jobs_screen_shows_state_of_each_job(
    bot: FakeBot, context: FakeContext, admin: User, clean_registry
) -> None:
    """شاشة المهام تعرض كل مهمة بحالتها وآخر خطأ للمتعثرة."""
    _register_demo_jobs(clean_registry)
    await load_user(bot, context, admin)
    await press(bot, context, admin_system.jobs_screen, pack("adm", "jobs"), admin.telegram_id)

    text = bot.last.text
    assert "متابعة حالة الطلبات" in text
    assert "أرصدة المزودين" in text
    assert "انقطاع الاتصال بالمزود" in text
    assert "🔴" in text and "🟢" in text
    assert any(data.startswith("adm:jobrun:") for data in bot.last.buttons)


async def test_jobs_screen_without_maintenance_has_no_run_buttons(
    bot: FakeBot, context: FakeContext, user: User, super_admin: User, clean_registry, services
) -> None:
    """من يرى الإحصائيات بلا صلاحية الصيانة يقرأ الحالة ولا يملك «تشغيل الآن»."""
    _register_demo_jobs(clean_registry)
    for permission in ("admin.access", "stats.view"):
        await services.auth.set_user_permission(super_admin, user.id, permission, allow=True)
    await load_user(bot, context, user)
    await press(bot, context, admin_system.jobs_screen, pack("adm", "jobs"), user.telegram_id)

    assert "المهام الدورية" in bot.last.text
    assert not any(data.startswith("adm:jobrun:") for data in bot.last.buttons)


async def test_run_job_now_executes_and_reports(
    bot: FakeBot, context: FakeContext, super_admin: User, clean_registry, services
) -> None:
    """زر «تشغيل الآن» ينفّذ المهمة فوراً ويعرض نتيجتها."""
    calls: list[int] = []

    async def job(_context) -> None:
        """مهمة اختبارية تُسجّل استدعاءها."""
        calls.append(1)

    supervise(job, name="orders_check", registry=clean_registry, interval_seconds=120)
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        admin_system.run_job_now,
        pack("adm", "jobrun", "orders_check"),
        super_admin.telegram_id,
    )

    assert calls == [1]
    texts = " ".join(message.text or "" for message in bot.sent)
    assert "✅" in texts
    assert clean_registry.get("orders_check").runs == 1


async def test_run_job_now_reports_failure_without_crashing(
    bot: FakeBot, context: FakeContext, super_admin: User, clean_registry
) -> None:
    """فشل المهمة المُشغَّلة يدوياً يُعرض للأدمن ولا يُسقط المعالج."""

    async def failing(_context) -> None:
        """مهمة اختبارية تفشل."""
        raise RuntimeError("خطأ يدوي")

    supervise(failing, name="orders_check", registry=clean_registry, interval_seconds=120)
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        admin_system.run_job_now,
        pack("adm", "jobrun", "orders_check"),
        super_admin.telegram_id,
    )

    texts = " ".join(message.text or "" for message in bot.sent)
    assert "❌" in texts
    assert "خطأ يدوي" in texts


async def test_run_job_now_blocked_for_plain_admin(
    bot: FakeBot, context: FakeContext, admin: User, clean_registry
) -> None:
    """دور `admin` بلا `settings.maintenance`؟ يُحجب التشغيل اليدوي."""
    calls: list[int] = []

    async def job(_context) -> None:
        """مهمة لا يجب أن تعمل في هذا الاختبار."""
        calls.append(1)

    supervise(job, name="orders_check", registry=clean_registry, interval_seconds=120)
    await load_user(bot, context, admin)
    has_maintenance = await context.application.bot_data["services"].auth.has_permission(
        admin, "settings.maintenance"
    )

    await press(
        bot,
        context,
        admin_system.run_job_now,
        pack("adm", "jobrun", "orders_check"),
        admin.telegram_id,
    )

    assert calls == ([1] if has_maintenance else [])


async def test_run_unknown_job_is_rejected(
    bot: FakeBot, context: FakeContext, super_admin: User, clean_registry
) -> None:
    """طلب تشغيل مهمة غير مجدولة يُرفض برسالة واضحة بلا انهيار."""
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        admin_system.run_job_now,
        pack("adm", "jobrun", "no_such_job"),
        super_admin.telegram_id,
    )

    assert bot.answers, "لم يصل أي ردّ على الزر"
    assert "غير مجدولة" in bot.answers[-1]["text"]


async def test_health_screen_includes_jobs_summary(
    bot: FakeBot, context: FakeContext, admin: User, clean_registry
) -> None:
    """شاشة صحة النظام تلخّص حالة المهام وتعرض زر الدخول لشاشتها."""
    _register_demo_jobs(clean_registry)
    await load_user(bot, context, admin)
    await press(bot, context, dashboard.health_screen, pack("adm", "health"), admin.telegram_id)

    assert "المهام:" in bot.last.text
    assert "adm:jobs:v1" in bot.last.buttons
```

