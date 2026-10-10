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
