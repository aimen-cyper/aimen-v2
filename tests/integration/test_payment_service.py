"""
اختبارات خدمة الشحن: من إرسال الإثبات حتى إضافة الرصيد.

التركيز على المال: لا إيداع مزدوج، ولا اعتماد طلب معالَج، ولا رصيد يُضاف
خارج المحفظة المركزية.
"""

from __future__ import annotations

import asyncio

import pytest

from core.enums import PaymentStatus, TransactionType
from core.exceptions import (
    DuplicateOperationError,
    InvalidAmountError,
    InvalidStateTransitionError,
    PermissionDeniedError,
    ValidationError,
)
from database.database import Database
from database.models import User
from database.repositories import Repositories
from services import ServiceContainer
from utils.datetime_utils import iso_plus_seconds


async def _submit(services: ServiceContainer, user: User, method, *, amount: str = "5", reference: str = "TRX-1001"):
    """اختصار لإرسال طلب شحن."""
    return await services.payments.create_payment(
        user,
        method_id=method.id,
        raw_amount=amount,
        transaction_reference=reference,
        proof_file_id="file-id-123",
        proof_file_type="photo",
    )


# ============================== الإنشاء ================================= #


async def test_create_payment_notifies_user_and_admins(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, payment_method
) -> None:
    """طلب الشحن يُنشأ معلّقاً مع إشعار للمستخدم وتنبيه للأدمن."""
    payment = await _submit(services, user, payment_method)

    assert payment.status == PaymentStatus.PENDING
    assert payment.amount_units == 50_000
    assert payment.expires_at is not None

    user_inbox = await repos.notifications.list_for_user(user.id)
    assert any(item.type == "payment_received" for item in user_inbox)
    assert await repos.notifications.list_for_user(admin.id)

    # لم يُضف أي رصيد قبل الاعتماد
    assert await services.wallet.balance_units(user.id) == 0


async def test_amount_below_minimum_rejected(
    services: ServiceContainer, user: User, payment_method
) -> None:
    """المبلغ الأقل من الحد الأدنى يُرفض قبل إنشاء أي صف."""
    with pytest.raises(InvalidAmountError):
        await _submit(services, user, payment_method, amount="0.5")


async def test_reference_cannot_be_reused(
    services: ServiceContainer, user: User, payment_method
) -> None:
    """رقم الحوالة الواحد لا يُستخدم في طلبين (كشف إعادة استخدام الإثبات)."""
    await _submit(services, user, payment_method, reference="TRX-SAME")
    with pytest.raises(DuplicateOperationError):
        await _submit(services, user, payment_method, reference="TRX-SAME")


async def test_pending_payments_limit(
    services: ServiceContainer, user: User, payment_method
) -> None:
    """لا يُسمح بتكديس طلبات شحن معلّقة أكثر من الحد المسموح."""
    await services.settings.set("max_pending_payments_per_user", 2)
    await _submit(services, user, payment_method, reference="TRX-A")
    await _submit(services, user, payment_method, reference="TRX-B")

    with pytest.raises(ValidationError):
        await _submit(services, user, payment_method, reference="TRX-C")


async def test_proof_required_when_method_requires_it(
    services: ServiceContainer, user: User, payment_method
) -> None:
    """طريقة تتطلب إثباتاً لا تقبل طلباً بلا رقم حوالة."""
    with pytest.raises(ValidationError):
        await services.payments.create_payment(
            user, method_id=payment_method.id, raw_amount="5", transaction_reference=None
        )


# ============================== الاعتماد ================================ #


async def test_approve_credits_balance_once(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, payment_method
) -> None:
    """الاعتماد يضيف الرصيد مرة واحدة ويكتب حركة إيداع وسجل تدقيق وإشعاراً."""
    payment = await _submit(services, user, payment_method)
    transaction = await services.payments.approve(admin, payment.id)

    assert transaction.type == TransactionType.DEPOSIT
    assert await services.wallet.balance_units(user.id) == 50_000

    updated = await repos.payments.get(payment.id)
    assert updated is not None
    assert updated.status == PaymentStatus.APPROVED
    assert updated.credited_units == 50_000
    assert updated.admin_id == admin.id
    assert updated.reviewed_at is not None

    logs = await services.audit.by_target("payment", payment.id)
    assert any(log.action == "payments.approve" for log in logs)

    inbox = await repos.notifications.list_for_user(user.id)
    assert any(item.type == "payment_approved" for item in inbox)


async def test_approve_twice_is_blocked(
    services: ServiceContainer, user: User, admin: User, payment_method
) -> None:
    """لا يُعتمد الطلب مرتين (ولا يُضاف الرصيد مرتين)."""
    payment = await _submit(services, user, payment_method)
    await services.payments.approve(admin, payment.id)

    with pytest.raises(InvalidStateTransitionError):
        await services.payments.approve(admin, payment.id)

    assert await services.wallet.balance_units(user.id) == 50_000


async def test_two_admins_approving_together_credit_once(
    services: ServiceContainer, user: User, admin: User, super_admin: User, payment_method
) -> None:
    """اعتمادان متزامنان من أدمنين مختلفين ⇒ إيداع واحد فقط."""
    payment = await _submit(services, user, payment_method)

    results = await asyncio.gather(
        services.payments.approve(admin, payment.id),
        services.payments.approve(super_admin, payment.id),
        return_exceptions=True,
    )
    successes = [item for item in results if not isinstance(item, Exception)]
    failures = [item for item in results if isinstance(item, Exception)]

    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], (DuplicateOperationError, InvalidStateTransitionError))
    assert await services.wallet.balance_units(user.id) == 50_000


async def test_approve_with_different_amount(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, payment_method
) -> None:
    """يمكن اعتماد مبلغ مختلف عن المطلوب (تحويل ناقص) مع توثيق الفرق."""
    payment = await _submit(services, user, payment_method, amount="10")
    await services.payments.approve(admin, payment.id, credited_units=70_000, admin_note="وصل ناقصاً")

    assert await services.wallet.balance_units(user.id) == 70_000
    updated = await repos.payments.get(payment.id)
    assert updated is not None
    assert updated.credited_units == 70_000
    assert updated.admin_note and "70000" in updated.admin_note.replace(" ", "")


# =============================== الرفض ================================== #


async def test_reject_requires_reason_and_notifies(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, payment_method
) -> None:
    """الرفض يحتاج سبباً يصل للمستخدم، ولا يضيف أي رصيد."""
    payment = await _submit(services, user, payment_method)

    with pytest.raises(ValidationError):
        await services.payments.reject(admin, payment.id, "")

    assert await services.payments.reject(admin, payment.id, "الإيصال غير واضح")
    updated = await repos.payments.get(payment.id)
    assert updated is not None
    assert updated.status == PaymentStatus.REJECTED
    assert updated.reject_reason == "الإيصال غير واضح"
    assert await services.wallet.balance_units(user.id) == 0

    inbox = await repos.notifications.list_for_user(user.id)
    assert any(item.type == "payment_rejected" for item in inbox)


async def test_rejected_payment_cannot_be_approved(
    services: ServiceContainer, user: User, admin: User, payment_method
) -> None:
    """الطلب المرفوض مغلق نهائياً."""
    payment = await _submit(services, user, payment_method)
    await services.payments.reject(admin, payment.id, "مكرر")

    with pytest.raises(InvalidStateTransitionError):
        await services.payments.approve(admin, payment.id)


# ======================= الإلغاء وانتهاء الصلاحية ======================== #


async def test_user_can_cancel_pending_payment(
    services: ServiceContainer, repos: Repositories, user: User, payment_method
) -> None:
    """المستخدم يلغي طلب شحن أرسله بالخطأ."""
    payment = await _submit(services, user, payment_method)
    assert await services.payments.cancel_by_user(user, payment.id)

    updated = await repos.payments.get(payment.id)
    assert updated is not None and updated.status == PaymentStatus.CANCELLED


async def test_expired_payments_are_closed_and_user_notified(
    services: ServiceContainer, db: Database, repos: Repositories, user: User, payment_method
) -> None:
    """الطلبات منتهية الصلاحية تُغلق تلقائياً ويُشعَر أصحابها."""
    payment = await _submit(services, user, payment_method)
    async with db.transaction() as tx:
        await repos.payments.update_fields(tx, payment.id, expires_at=iso_plus_seconds(-60))

    assert await services.payments.expire_due() == 1
    updated = await repos.payments.get(payment.id)
    assert updated is not None and updated.status == PaymentStatus.EXPIRED
    assert await services.wallet.balance_units(user.id) == 0


# ============================ الصلاحيات والإدارة ========================= #


async def test_plain_user_cannot_approve_or_list(
    services: ServiceContainer, user: User, payment_method
) -> None:
    """المستخدم العادي لا يرى طابور المراجعة ولا يعتمد الطلبات."""
    payment = await _submit(services, user, payment_method)

    with pytest.raises(PermissionDeniedError):
        await services.payments.approve(user, payment.id)
    with pytest.raises(PermissionDeniedError):
        await services.payments.pending(user)


async def test_method_management_requires_permission(
    services: ServiceContainer, user: User, super_admin: User
) -> None:
    """إدارة طرق الدفع محصورة بمن يملك صلاحية `payments.methods`."""
    with pytest.raises(PermissionDeniedError):
        await services.payments.create_method(user, code="x", name_ar="طريقة")

    method = await services.payments.create_method(
        super_admin, code="Kuraimi Bank", name_ar="بنك الكريمي", min_amount_units=20_000
    )
    assert method.code == "kuraimi_bank"

    assert await services.payments.set_method_active(super_admin, method.id, False)
    methods = await services.payments.active_methods()
    assert method.id not in {item.id for item in methods}


async def test_method_limits_override_global_settings(
    services: ServiceContainer, super_admin: User, user: User
) -> None:
    """حد الطريقة يتقدّم على الحد العام في الإعدادات."""
    method = await services.payments.create_method(
        super_admin, code="big_only", name_ar="تحويلات كبيرة", min_amount_units=100_000,
        requires_proof=False,
    )
    min_units, _ = await services.payments.method_limits(method)
    assert min_units == 100_000

    with pytest.raises(InvalidAmountError):
        await services.payments.create_payment(
            user, method_id=method.id, raw_amount="5", transaction_reference=None
        )
