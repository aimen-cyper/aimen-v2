"""اختبارات المحدِّد والحارس ضد الإساءة بساعة حقنية (المرحلة 9)."""

from __future__ import annotations

from middlewares.rate_limit import (
    BUCKET_GENERAL,
    BUCKET_SENSITIVE,
    STRIKE_WINDOW_SECONDS,
    WARNING_COOLDOWN_SECONDS,
    AbuseGuard,
    RateLimiter,
)


class Clock:
    """ساعة يدوية: نتحكم بالزمن دون انتظار."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_limiter_blocks_after_limit_and_recovers_after_window() -> None:
    """الحد يُطبَّق داخل النافذة وينفرج بعد انقضائها."""
    clock = Clock()
    limiter = RateLimiter(window_seconds=60, clock=clock)
    assert all(limiter.hit(1, 3) for _ in range(3))
    assert limiter.hit(1, 3) is False
    clock.advance(61)
    assert limiter.hit(1, 3) is True


def test_limiter_is_per_user_and_per_bucket() -> None:
    """مستخدم آخر أو سلة أخرى لا يتأثر بحد غيره."""
    limiter = RateLimiter(clock=Clock())
    assert all(limiter.hit(1, 2) for _ in range(2))
    assert limiter.hit(1, 2) is False
    assert limiter.hit(2, 2) is True
    assert limiter.hit(1, 2, bucket=BUCKET_SENSITIVE) is True
    assert limiter.hit(1, 2, bucket=BUCKET_GENERAL) is False


def test_limiter_zero_limit_means_unlimited() -> None:
    """حد صفر = بلا حد (يُستخدم للمراقبة فقط؛ الإعدادات تمنعه عملياً)."""
    limiter = RateLimiter(clock=Clock())
    assert all(limiter.hit(1, 0) for _ in range(500))


def test_limiter_remaining_and_reset() -> None:
    """العدّاد المتبقي يتناقص والتصفير يعيده كاملاً."""
    limiter = RateLimiter(clock=Clock())
    limiter.hit(1, 5)
    limiter.hit(1, 5)
    assert limiter.remaining(1, 5) == 3
    limiter.reset(1)
    assert limiter.remaining(1, 5) == 5


def test_guard_blocks_after_strikes_and_expires() -> None:
    """بلوغ عدد المخالفات يوقف المستخدم، ويزول الإيقاف بانتهاء مدته."""
    clock = Clock()
    guard = AbuseGuard(clock=clock)
    for _ in range(2):
        result = guard.record_violation(7, strikes_limit=3, block_seconds=300)
        assert result.blocked is False
        clock.advance(1)
    final = guard.record_violation(7, strikes_limit=3, block_seconds=300)
    assert final.blocked is True and final.strikes == 3
    assert guard.is_blocked(7)
    assert 290 < guard.seconds_blocked(7) <= 300
    assert guard.total_blocks == 1 and guard.total_violations == 3

    clock.advance(301)
    assert guard.is_blocked(7) is False
    assert guard.blocked_snapshot() == []


def test_guard_old_strikes_expire() -> None:
    """مخالفات أقدم من نافذة الاحتساب لا تجمع مع الجديدة."""
    clock = Clock()
    guard = AbuseGuard(clock=clock)
    guard.record_violation(7, strikes_limit=3, block_seconds=60)
    guard.record_violation(7, strikes_limit=3, block_seconds=60)
    clock.advance(STRIKE_WINDOW_SECONDS + 1)
    result = guard.record_violation(7, strikes_limit=3, block_seconds=60)
    assert result.blocked is False and result.strikes == 1


def test_guard_warning_is_throttled() -> None:
    """التحذير مُهدَّأ: أول مخالفة تحذّر، والتالية السريعة لا تحذّر، وبعد التهدئة تحذّر."""
    clock = Clock()
    guard = AbuseGuard(clock=clock)
    assert guard.record_violation(7, strikes_limit=50, block_seconds=60).warn is True
    clock.advance(1)
    assert guard.record_violation(7, strikes_limit=50, block_seconds=60).warn is False
    clock.advance(WARNING_COOLDOWN_SECONDS)
    assert guard.record_violation(7, strikes_limit=50, block_seconds=60).warn is True


def test_guard_first_warning_works_even_with_tiny_clock() -> None:
    """أول تحذير يصدر حتى لو بدأت الساعة من صفر (لا اعتماد على قيمة افتراضية خاطئة)."""
    guard = AbuseGuard(clock=lambda: 0.0)
    assert guard.record_violation(1, strikes_limit=9, block_seconds=60).warn is True


def test_guard_clear_and_snapshot_ordering() -> None:
    """رفع الإيقاف يزيل المستخدم، والقائمة مرتبة بالأطول إيقافاً."""
    clock = Clock()
    guard = AbuseGuard(clock=clock)
    guard.record_violation(1, strikes_limit=1, block_seconds=100)
    guard.record_violation(2, strikes_limit=1, block_seconds=500)
    snapshot = guard.blocked_snapshot()
    assert [info.telegram_id for info in snapshot] == [2, 1]
    assert guard.clear(2) is True
    assert guard.clear(2) is False
    assert [info.telegram_id for info in guard.blocked_snapshot()] == [1]
