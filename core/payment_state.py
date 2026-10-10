"""
آلة حالات طلب الشحن (Payment State Machine).

طلب الشحن أبسط من الطلب: يبدأ `pending` ثم ينتهي إلى حالة نهائية واحدة لا رجعة فيها.
الهدف من الملف هو منع أي «اعتماد مزدوج» أو «رفض بعد الاعتماد» على مستوى المنطق،
إضافةً إلى الحماية الموجودة أصلاً في قاعدة البيانات.
"""

from __future__ import annotations

from core.enums import PaymentStatus
from core.exceptions import InvalidStateTransitionError

#: الحالات النهائية لطلب الشحن
FINAL_STATUSES: frozenset[str] = frozenset(
    {
        PaymentStatus.APPROVED,
        PaymentStatus.REJECTED,
        PaymentStatus.CANCELLED,
        PaymentStatus.EXPIRED,
    }
)

#: جدول الانتقالات المسموحة
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    PaymentStatus.PENDING: frozenset(
        {
            PaymentStatus.APPROVED,
            PaymentStatus.REJECTED,
            PaymentStatus.CANCELLED,
            PaymentStatus.EXPIRED,
        }
    ),
    PaymentStatus.APPROVED: frozenset(),
    PaymentStatus.REJECTED: frozenset(),
    PaymentStatus.CANCELLED: frozenset(),
    PaymentStatus.EXPIRED: frozenset(),
}

#: الحالة الوحيدة التي تُضيف رصيداً للمستخدم
CREDITING_STATUS: str = PaymentStatus.APPROVED

#: تسميات عربية للعرض
STATUS_LABELS_AR: dict[str, str] = {
    PaymentStatus.PENDING: "⏳ قيد المراجعة",
    PaymentStatus.APPROVED: "✅ معتمد",
    PaymentStatus.REJECTED: "❌ مرفوض",
    PaymentStatus.CANCELLED: "🚫 ملغي",
    PaymentStatus.EXPIRED: "⌛ منتهي الصلاحية",
}


def can_transition(from_status: str, to_status: str) -> bool:
    """هل يجوز نقل طلب الشحن من حالة إلى أخرى؟"""
    if from_status == to_status:
        return False  # طلب الشحن لا يُعاد تعيينه لنفس الحالة (يعني محاولة اعتماد مزدوج)
    return to_status in ALLOWED_TRANSITIONS.get(from_status, frozenset())


def assert_transition(from_status: str, to_status: str, *, payment_id: int | None = None) -> None:
    """
    التحقق من الانتقال ورفع استثناء واضح عند المخالفة.

    الاستثناءات:
        InvalidStateTransitionError : محاولة تعديل طلب شحن محسوم مسبقاً.
    """
    if can_transition(from_status, to_status):
        return
    where = f" لطلب الشحن #{payment_id}" if payment_id else ""
    raise InvalidStateTransitionError(
        f"انتقال غير مسموح{where}: {from_status} ← {to_status}",
        user_message="⚠️ تمت معالجة طلب الشحن هذا مسبقاً.",
    )


def is_final(status: str) -> bool:
    """هل حُسم طلب الشحن نهائياً؟"""
    return status in FINAL_STATUSES


def label_ar(status: str) -> str:
    """الاسم العربي لحالة طلب الشحن."""
    return STATUS_LABELS_AR.get(status, status)
