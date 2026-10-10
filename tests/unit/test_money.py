"""اختبارات حساب المال — أخطر جزء في النظام، لذا يُختبر بدقة."""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.exceptions import InvalidAmountError
from core.money import (
    MONEY_SCALE,
    apply_markup,
    format_units,
    from_units,
    order_cost_units,
    partial_refund_units,
    to_units,
)


def test_scale_is_four_decimals() -> None:
    """المقياس المعتمد أربع خانات عشرية."""
    assert MONEY_SCALE == 10_000


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1", 10_000), ("0.5", 5_000), ("12.3456", 123_456), ("0.0001", 1), (7, 70_000)],
)
def test_to_units_conversion(value, expected) -> None:
    """التحويل من نص/عدد إلى نقاط صحيحة."""
    assert to_units(value) == expected


def test_to_units_rejects_float() -> None:
    """ممنوع تمرير float لتفادي أخطاء الفاصلة العائمة."""
    with pytest.raises(InvalidAmountError):
        to_units(1.5)  # type: ignore[arg-type]


def test_to_units_rejects_negative_and_garbage() -> None:
    """رفض القيم السالبة وغير الرقمية."""
    with pytest.raises(InvalidAmountError):
        to_units("-5")
    with pytest.raises(InvalidAmountError):
        to_units("abc")


def test_round_trip_precision() -> None:
    """التحويل ذهاباً وإياباً لا يفقد الدقة."""
    assert from_units(to_units("99.9999")) == Decimal("99.9999")


def test_order_cost_basic() -> None:
    """تكلفة 1000 وحدة بسعر ألف = نفس سعر الألف."""
    assert order_cost_units(10_000, 1000) == 10_000


def test_order_cost_half_quantity() -> None:
    """نصف الكمية = نصف السعر بالضبط."""
    assert order_cost_units(10_000, 500) == 5_000


def test_order_cost_rounding_half_up() -> None:
    """التقريب نصفي لأعلى بأعداد صحيحة (لا أخطاء عائمة)."""
    # 3 نقاط لكل ألف × 500 وحدة = 1.5 نقطة ⇒ تقرّب إلى 2
    assert order_cost_units(3, 500) == 2


def test_order_cost_no_float_drift() -> None:
    """مجموع 1000 عملية صغيرة يبقى دقيقاً تماماً (اختبار انحراف الفاصلة العائمة)."""
    total = sum(order_cost_units(1_234, 7) for _ in range(1000))
    assert total == 1000 * ((1_234 * 7 + 500) // 1000)


def test_order_cost_rejects_invalid() -> None:
    """رفض الكمية أو السعر غير الصالح."""
    with pytest.raises(InvalidAmountError):
        order_cost_units(0, 100)
    with pytest.raises(InvalidAmountError):
        order_cost_units(10_000, 0)


def test_partial_refund_half() -> None:
    """تنفيذ نصف الكمية يسترجع نصف التكلفة."""
    assert partial_refund_units(cost_units=10_000, quantity=1000, remains=500) == 5_000


def test_partial_refund_never_exceeds_cost() -> None:
    """الاسترجاع لا يتجاوز التكلفة مهما كانت قيمة remains الواردة من المزود."""
    assert partial_refund_units(cost_units=10_000, quantity=1000, remains=99_999) == 10_000


def test_partial_refund_accounts_previous_refunds() -> None:
    """ما سبق استرجاعه يُخصم فلا يحدث استرجاع مزدوج."""
    assert (
        partial_refund_units(cost_units=10_000, quantity=1000, remains=1000, already_refunded_units=6_000)
        == 4_000
    )


def test_partial_refund_zero_when_completed() -> None:
    """لا استرجاع إذا لم يتبقَّ شيء."""
    assert partial_refund_units(cost_units=10_000, quantity=1000, remains=0) == 0


def test_apply_markup() -> None:
    """حساب سعر البيع من التكلفة بنسبة ربح."""
    assert apply_markup(10_000, 30) == 13_000
    assert apply_markup(3_333, 50) == 5_000  # تقريب نصفي لأعلى


def test_format_units_display() -> None:
    """تنسيق العرض يحترم عدد الخانات المطلوب."""
    assert format_units(123_456, "ريال", 2) == "12.35 ريال"
    assert format_units(10_000, "$", 0) == "1 $"
