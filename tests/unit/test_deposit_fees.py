"""
اختبارات وحدة لحساب رسوم طرق الشحن (المرحلة 7).

لماذا اختبار مستقل بلا قاعدة بيانات؟
    لأن هذه الدوال هي المكان الوحيد الذي يقرر كم يُخصم من مال العميل،
    وأي خطأ تقريب فيها يتحول إلى فروق رصيد لا تُكتشف إلا متأخراً.
"""

from __future__ import annotations

import pytest

from core.exceptions import InvalidAmountError
from core.money import (
    FEE_SCALE,
    MAX_FEE_PERCENT_BP,
    MONEY_SCALE,
    deposit_fee_units,
    net_after_fee,
)


def test_no_fees_configured_means_zero_fee() -> None:
    """طريقة بلا رسوم: الصافي = كامل المبلغ."""
    fee, net = net_after_fee(100 * MONEY_SCALE)
    assert fee == 0
    assert net == 100 * MONEY_SCALE


def test_percent_fee_is_exact_for_round_values() -> None:
    """نسبة 2.5% على 1000 = 25 بالضبط (بلا كسور عائمة)."""
    fee = deposit_fee_units(1000 * MONEY_SCALE, percent_bp=250)
    assert fee == 25 * MONEY_SCALE


def test_fixed_and_percent_fees_add_up() -> None:
    """الرسوم النسبية والثابتة تُجمعان معاً على نفس الحوالة."""
    fee, net = net_after_fee(
        200 * MONEY_SCALE, percent_bp=100, fixed_units=5 * MONEY_SCALE  # 1% + 5
    )
    assert fee == 2 * MONEY_SCALE + 5 * MONEY_SCALE
    assert net == 200 * MONEY_SCALE - fee


def test_percent_fee_uses_half_up_rounding_on_units() -> None:
    """التقريب نصفي لأعلى على مستوى النقطة الواحدة (لا قص ولا float)."""
    # 1 نقطة × 50% = 0.5 نقطة ⇒ تُقرَّب إلى 1
    assert deposit_fee_units(1, percent_bp=FEE_SCALE // 2) == 1
    # 1 نقطة × 49.99% = 0.4999 ⇒ تُقرَّب إلى 0
    assert deposit_fee_units(1, percent_bp=FEE_SCALE // 2 - 1) == 0


def test_fee_never_exceeds_the_transfer_itself() -> None:
    """مهما كانت الإعدادات لا تتجاوز الرسوم مبلغ الحوالة (حماية من رصيد سالب)."""
    fee, net = net_after_fee(10 * MONEY_SCALE, percent_bp=MAX_FEE_PERCENT_BP, fixed_units=999999)
    assert fee == 10 * MONEY_SCALE
    assert net == 0


def test_hundred_percent_fee_is_allowed_but_zero_percent_is_default() -> None:
    """نسبة 100% مسموحة كحد أقصى، والافتراضي صفر."""
    assert deposit_fee_units(50 * MONEY_SCALE, percent_bp=MAX_FEE_PERCENT_BP) == 50 * MONEY_SCALE
    assert deposit_fee_units(50 * MONEY_SCALE) == 0


@pytest.mark.parametrize("bad_percent", [-1, MAX_FEE_PERCENT_BP + 1, 99_999])
def test_invalid_percent_is_rejected(bad_percent: int) -> None:
    """نسبة خارج المدى 0..100% ترفع خطأ مالياً واضحاً."""
    with pytest.raises(InvalidAmountError):
        deposit_fee_units(100 * MONEY_SCALE, percent_bp=bad_percent)


def test_negative_amount_or_fixed_fee_is_rejected() -> None:
    """المبالغ السالبة مرفوضة في الطرفين (المبلغ والرسوم الثابتة)."""
    with pytest.raises(InvalidAmountError):
        deposit_fee_units(-1, percent_bp=0)
    with pytest.raises(InvalidAmountError):
        deposit_fee_units(100, fixed_units=-5)


def test_fee_calculation_is_integer_only() -> None:
    """الناتج دائماً int — لا Decimal ولا float يتسرب إلى طبقة المال."""
    fee, net = net_after_fee(123_456, percent_bp=333, fixed_units=77)
    assert isinstance(fee, int) and isinstance(net, int)
    assert fee + net == 123_456  # لا تتبخّر أي نقطة في الحساب
