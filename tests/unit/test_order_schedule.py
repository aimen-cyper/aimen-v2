"""سياسة جدولة فحص الطلب (v1.3.1): النجاح بفاصل صغير محدود، والفشل بتباطؤ أسّي محدود."""

from __future__ import annotations

import pytest

from core.order_schedule import failure_delay_seconds, success_delay_seconds


@pytest.mark.parametrize(
    ("age", "expected"),
    [(0, 120), (1799, 120), (1800, 240), (3600, 300), (86_400, 300), (10**7, 300)],
)
def test_success_delay_grows_slowly_and_is_capped(age: int, expected: int) -> None:
    """120 ثم 240 ثم 300 كحد أقصى — لا ساعة أبداً (v1.3.0 كان 3600)."""
    assert success_delay_seconds(base=120, active_max=300, age_seconds=age) == expected


def test_success_delay_never_below_admin_base() -> None:
    """إن ضبط الأدمن فاصلاً أساسياً أكبر من السقف احتُرم الأساسي."""
    assert success_delay_seconds(base=600, active_max=300, age_seconds=10**6) == 600


@pytest.mark.parametrize(("streak", "expected"), [(1, 60), (2, 120), (3, 240), (4, 480), (5, 600), (50, 600)])
def test_failure_delay_is_exponential_and_capped(streak: int, expected: int) -> None:
    """أول إخفاق دقيقة، ثم يتضاعف بسقف الإعداد."""
    assert failure_delay_seconds(streak=streak, error_max=600) == expected
