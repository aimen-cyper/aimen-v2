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
