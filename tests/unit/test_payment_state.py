"""
اختبارات آلة حالات طلب الشحن.

القاعدة الحاكمة: طلب الشحن يُعالَج مرة واحدة فقط. أي انتقال يسمح بإعادة
معالجة طلب معتمد = خطر إضافة الرصيد مرتين.
"""

from __future__ import annotations

import pytest

from core.enums import PaymentStatus
from core.exceptions import InvalidStateTransitionError
from core.payment_state import (
    ALLOWED_TRANSITIONS,
    CREDITING_STATUS,
    FINAL_STATUSES,
    assert_transition,
    can_transition,
    is_final,
    label_ar,
)


def test_every_status_has_an_entry() -> None:
    """كل حالة دفع لها صف في جدول الانتقالات."""
    assert set(ALLOWED_TRANSITIONS) == set(PaymentStatus)


def test_pending_can_go_to_all_final_states() -> None:
    """الطلب المعلّق يمكن أن ينتهي بالاعتماد أو الرفض أو الإلغاء أو انتهاء الصلاحية."""
    assert ALLOWED_TRANSITIONS[PaymentStatus.PENDING] == frozenset(
        {
            PaymentStatus.APPROVED,
            PaymentStatus.REJECTED,
            PaymentStatus.CANCELLED,
            PaymentStatus.EXPIRED,
        }
    )


def test_final_states_are_closed() -> None:
    """الحالات النهائية مغلقة تماماً — لا إعادة اعتماد ولا إعادة فتح."""
    for status in FINAL_STATUSES:
        assert is_final(status)
        assert ALLOWED_TRANSITIONS[status] == frozenset()


def test_approved_cannot_be_reprocessed() -> None:
    """ممنوع إعادة اعتماد طلب معتمد (حماية من إضافة الرصيد مرتين)."""
    assert not can_transition(PaymentStatus.APPROVED, PaymentStatus.APPROVED)
    assert not can_transition(PaymentStatus.APPROVED, PaymentStatus.PENDING)
    assert not can_transition(PaymentStatus.REJECTED, PaymentStatus.APPROVED)


def test_same_status_is_rejected_for_payments() -> None:
    """
    بخلاف الطلبات، لا يُسمح هنا بالانتقال من الحالة إلى نفسها.

    السبب: كل انتقال في الدفع يحمل أثراً مالياً، فإعادة الحالة نفسها تعني
    محاولة ثانية لتنفيذ نفس العملية.
    """
    for status in PaymentStatus:
        assert not can_transition(status, status)


def test_assert_transition_mentions_payment_id() -> None:
    """رسالة الخطأ تذكر رقم طلب الشحن."""
    with pytest.raises(InvalidStateTransitionError) as error:
        assert_transition(PaymentStatus.APPROVED, PaymentStatus.REJECTED, payment_id=42)
    assert "42" in str(error.value)


def test_crediting_status_is_approved() -> None:
    """الحالة الوحيدة التي تضيف رصيداً هي approved."""
    assert CREDITING_STATUS == PaymentStatus.APPROVED


def test_labels_are_arabic() -> None:
    """لكل حالة تسمية عربية."""
    for status in PaymentStatus:
        assert label_ar(status) not in {"", status}
