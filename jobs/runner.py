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
        self,
        name: str,
        *,
        interval_seconds: float,
        schedule_text: str = "",
        keep_history: bool = False,
    ) -> JobStats:
        """
        تسجيل مهمة جديدة (أو إعادة ضبط تسجيلها عند إعادة الجدولة).

        `keep_history=True` يُستخدم عند تغيير الإيقاع أثناء التشغيل: نُبقي عدّادات
        المهمة (التشغيلات/الإخفاقات) وقفلها كما هي ونحدّث الفترة والوصف فقط، فلا
        يضيع السجل ولا يتسلل تداخل جولة قديمة مع الجديدة.
        """
        existing = self.stats.get(name)
        if keep_history and existing is not None:
            existing.interval_seconds = interval_seconds
            existing.schedule_text = schedule_text
            return existing
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
    keep_history: bool = False,
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
        keep_history            : إبقاء عدّادات المهمة وقفلها عند إعادة الجدولة الحيّة.

    المخرجات: دالة جاهزة لـ`JobQueue` **لا ترفع استثناءً أبداً**.
    """
    stats = registry.register(
        name,
        interval_seconds=interval_seconds,
        schedule_text=schedule_text,
        keep_history=keep_history,
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
