"""
اختبارات آلة حالات الطلب — بلا قاعدة بيانات.

أهميتها: هذه الجداول هي الحارس الذي يمنع «تغيير حالة الطلب من أي مكان».
أي تعديل يفتح انتقالاً خطيراً (مثل completed ← pending) يجب أن يُسقط هذه الاختبارات.
"""

from __future__ import annotations

import pytest

from core.enums import OrderStatus
from core.exceptions import InvalidStateTransitionError
from core.order_state import (
    ACTIVE_STATUSES,
    ALLOWED_TRANSITIONS,
    FINAL_STATUSES,
    allowed_next,
    assert_transition,
    can_transition,
    is_active,
    is_final,
    label_ar,
    map_provider_status,
    requires_full_refund,
    requires_partial_refund,
    sources_for,
)


def test_every_status_has_an_entry() -> None:
    """كل حالة معرّفة في الـEnum لها صف في جدول الانتقالات (ولو فارغاً)."""
    assert set(ALLOWED_TRANSITIONS) == set(OrderStatus)


def test_final_statuses_have_no_exit_except_refund() -> None:
    """الحالات النهائية لا تخرج إلا إلى refunded (لتسجيل إعادة المال بعد الإلغاء)."""
    for status in FINAL_STATUSES:
        assert allowed_next(status) <= {OrderStatus.REFUNDED}


def test_completed_is_terminal() -> None:
    """الطلب المكتمل لا يُعاد فتحه بأي شكل."""
    assert is_final(OrderStatus.COMPLETED)
    assert allowed_next(OrderStatus.COMPLETED) == frozenset()
    assert not can_transition(OrderStatus.COMPLETED, OrderStatus.PENDING)
    assert not can_transition(OrderStatus.COMPLETED, OrderStatus.IN_PROGRESS)


def test_happy_path_transitions_allowed() -> None:
    """المسار الطبيعي للطلب مسموح خطوة بخطوة."""
    path = [
        OrderStatus.PENDING,
        OrderStatus.SUBMITTING,
        OrderStatus.SUBMITTED,
        OrderStatus.IN_PROGRESS,
        OrderStatus.COMPLETED,
    ]
    for current, nxt in zip(path, path[1:]):
        assert can_transition(current, nxt), f"ممنوع خطأً: {current} ← {nxt}"


def test_failure_path_transitions_allowed() -> None:
    """مسار الفشل: submitting ← failed ← refunded."""
    assert can_transition(OrderStatus.SUBMITTING, OrderStatus.FAILED)
    assert can_transition(OrderStatus.FAILED, OrderStatus.REFUNDED)
    assert can_transition(OrderStatus.CANCELED, OrderStatus.REFUNDED)


def test_same_status_is_treated_as_no_op() -> None:
    """
    الانتقال إلى نفس الحالة مسموح بوصفه «لا تغيير».

    السبب: فحص الحالة الدوري قد يعيد نفس النتيجة مرات كثيرة، ولا يصح أن يُعتبر خطأً.
    منع التكرار الفعلي يتم في `OrderService._transition` الذي يتوقف قبل أي كتابة
    أو إشعار عندما تكون الحالة الجديدة مطابقة للحالية.
    """
    for status in OrderStatus:
        assert can_transition(status, status)
        assert status not in allowed_next(status)


def test_skipping_submission_is_rejected() -> None:
    """ممنوع القفز من pending إلى completed دون المرور بالمزود."""
    assert not can_transition(OrderStatus.PENDING, OrderStatus.COMPLETED)
    assert not can_transition(OrderStatus.PENDING, OrderStatus.IN_PROGRESS)


def test_assert_transition_raises_with_order_id() -> None:
    """رسالة الخطأ تذكر رقم الطلب لتسهيل التتبع."""
    with pytest.raises(InvalidStateTransitionError) as error:
        assert_transition(OrderStatus.COMPLETED, OrderStatus.PENDING, order_id=77)
    assert "77" in str(error.value)


def test_uncertain_cannot_be_resubmitted_automatically() -> None:
    """الحالة غير المؤكدة لا تعود إلى pending — فإعادة الإرسال تعني طلباً مكرراً."""
    assert OrderStatus.PENDING not in allowed_next(OrderStatus.SUBMIT_UNCERTAIN)
    assert allowed_next(OrderStatus.SUBMIT_UNCERTAIN) == frozenset(
        {OrderStatus.SUBMITTED, OrderStatus.FAILED}
    )


def test_active_statuses_are_not_final() -> None:
    """لا تتداخل مجموعة الحالات النشطة مع النهائية."""
    assert ACTIVE_STATUSES.isdisjoint(FINAL_STATUSES)
    assert is_active(OrderStatus.IN_PROGRESS)
    assert not is_active(OrderStatus.COMPLETED)


def test_sources_for_is_inverse_of_allowed_next() -> None:
    """دالة المصادر تعطي عكس جدول الانتقالات بدقة."""
    for status in OrderStatus:
        for source in sources_for(status):
            assert status in allowed_next(source)


def test_refund_requirements() -> None:
    """الفشل والإلغاء يوجبان استرجاعاً كاملاً، والتنفيذ الجزئي استرجاعاً جزئياً."""
    assert requires_full_refund(OrderStatus.FAILED)
    assert requires_full_refund(OrderStatus.CANCELED)
    assert requires_partial_refund(OrderStatus.PARTIAL)
    assert not requires_full_refund(OrderStatus.COMPLETED)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Pending", OrderStatus.SUBMITTED),
        ("In progress", OrderStatus.IN_PROGRESS),
        ("Processing", OrderStatus.IN_PROGRESS),
        ("Completed", OrderStatus.COMPLETED),
        ("completed", OrderStatus.COMPLETED),
        ("  COMPLETED  ", OrderStatus.COMPLETED),
        ("Partial", OrderStatus.PARTIAL),
        ("Canceled", OrderStatus.CANCELED),
        ("Cancelled", OrderStatus.CANCELED),
        ("Fail", OrderStatus.FAILED),
    ],
)
def test_provider_status_mapping(raw: str, expected: str) -> None:
    """نصوص المزودين الشائعة تُترجم إلى حالات النظام بشكل صحيح."""
    assert map_provider_status(raw) == expected


def test_unknown_provider_status_returns_none() -> None:
    """الحالة المجهولة تُعاد None — فلا نغيّر حالة الطلب بالتخمين."""
    assert map_provider_status("Something New") is None
    assert map_provider_status("") is None
    assert map_provider_status(None) is None


def test_labels_are_arabic_for_all_statuses() -> None:
    """لكل حالة تسمية عربية للعرض."""
    for status in OrderStatus:
        label = label_ar(status)
        assert label and label != status
