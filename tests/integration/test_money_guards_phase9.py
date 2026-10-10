"""اختبارات الحواجز المالية: التنفيذ الذاتي، الاعتماد الزائد، سقوف التسوية (المرحلة 9)."""

from __future__ import annotations

import pytest

from core.enums import OrderStatus, PaymentStatus
from core.exceptions import InvalidAmountError, PermissionDeniedError, ValidationError
from database.models import User
from services import ServiceContainer

pytestmark = pytest.mark.asyncio


async def _event_count(repos, event: str) -> int:
    """عدد مرات حدث أمني."""
    return await repos.audit.count_by_action_prefix(f"security.{event}")


async def _balance(services: ServiceContainer, user: User) -> int:
    """رصيد المستخدم بالنقاط."""
    return await services.wallet.balance_units(user.id)


async def _fund(services: ServiceContainer, target: User, by: User, units: int, token: str) -> None:
    """شحن رصيد يدوي بيد أدمن أعلى (لا يخضع للسقوف)."""
    await services.wallet.adjust_balance(
        target=target, amount_units=units, admin=by, reason="تمويل اختبار", credit=True, token=token
    )


# ============================ اعتماد الشحن ============================ #


async def test_admin_cannot_approve_own_payment(services, repos, admin, payment_method) -> None:
    """الأدمن لا يعتمد شحنته هو (عينان على كل عملية) ولا يتغير رصيده."""
    payment = await services.payments.create_payment(
        admin, method_id=payment_method.id, raw_amount="5", transaction_reference="SELF-1",
        proof_file_id="f", proof_file_type="photo",
    )
    with pytest.raises(PermissionDeniedError):
        await services.payments.approve(admin, payment.id)
    assert await _balance(services, admin) == 0
    assert (await repos.payments.get(payment.id)).status == PaymentStatus.PENDING
    assert await _event_count(repos, "self_action_blocked") == 1


async def test_other_admin_can_approve_that_payment(services, admin, super_admin, payment_method) -> None:
    """أدمن آخر يعتمدها بلا مشكلة."""
    payment = await services.payments.create_payment(
        admin, method_id=payment_method.id, raw_amount="5", transaction_reference="SELF-2",
        proof_file_id="f", proof_file_type="photo",
    )
    await services.payments.approve(super_admin, payment.id)
    assert await _balance(services, admin) == 50_000


async def test_self_dealing_can_be_disabled_by_setting(services, admin, super_admin, payment_method) -> None:
    """التعطيل الصريح بالإعداد (لبيئات الاختبار) يسمح، والإعداد نفسه مدقَّق."""
    await services.settings.set("security_block_self_actions", "false", admin_id=super_admin.id)
    payment = await services.payments.create_payment(
        admin, method_id=payment_method.id, raw_amount="5", transaction_reference="SELF-3",
        proof_file_id="f", proof_file_type="photo",
    )
    await services.payments.approve(admin, payment.id)
    assert await _balance(services, admin) == 50_000


async def test_over_credit_is_rejected_and_logged(services, repos, user, admin, payment_method) -> None:
    """لا يُعتمد مبلغ أكبر مما حوّله العميل، ويبقى الطلب معلّقاً."""
    payment = await services.payments.create_payment(
        user, method_id=payment_method.id, raw_amount="5", transaction_reference="OVER-1",
        proof_file_id="f", proof_file_type="photo",
    )
    with pytest.raises(ValidationError):
        await services.payments.approve(admin, payment.id, credited_units=payment.amount_units + 1)
    assert await _balance(services, user) == 0
    assert (await repos.payments.get(payment.id)).status == PaymentStatus.PENDING
    assert await _event_count(repos, "over_credit_blocked") == 1


async def test_partial_credit_below_amount_is_allowed(services, user, admin, payment_method) -> None:
    """اعتماد مبلغ أقل (خصم رسوم/فرق حوالة) مسموح."""
    payment = await services.payments.create_payment(
        user, method_id=payment_method.id, raw_amount="5", transaction_reference="PART-1",
        proof_file_id="f", proof_file_type="photo",
    )
    await services.payments.approve(admin, payment.id, credited_units=30_000)
    assert await _balance(services, user) == 30_000


# ============================== التسوية اليدوية ============================== #


async def test_admin_cannot_adjust_own_balance(services, repos, admin) -> None:
    """لا تسوية يدوية على حساب المنفِّذ نفسه."""
    with pytest.raises(PermissionDeniedError):
        await services.wallet.adjust_balance(
            target=admin, amount_units=10_000, admin=admin, reason="تجربة", credit=True, token="s1"
        )
    assert await _balance(services, admin) == 0
    assert await _event_count(repos, "self_action_blocked") == 1


async def test_single_adjust_cap_for_admin(services, repos, user, admin, super_admin) -> None:
    """يتجاوز الأدمن سقف العملية الواحدة ⇒ رفض + حدث أمني + رصيد ثابت."""
    await services.settings.set("admin_adjust_max_units", "100000", admin_id=super_admin.id)
    await services.wallet.adjust_balance(
        target=user, amount_units=100_000, admin=admin, reason="ضمن السقف", credit=True, token="c1"
    )
    with pytest.raises(InvalidAmountError):
        await services.wallet.adjust_balance(
            target=user, amount_units=100_001, admin=admin, reason="فوق السقف", credit=True, token="c2"
        )
    assert await _balance(services, user) == 100_000
    assert await _event_count(repos, "adjust_cap_exceeded") == 1


async def test_daily_adjust_cap_counts_credits_and_debits(services, repos, user, admin, super_admin) -> None:
    """السقف اليومي يجمع الإضافة والخصم معاً."""
    await services.settings.set("admin_adjust_max_units", "100000", admin_id=super_admin.id)
    await services.settings.set("admin_adjust_daily_max_units", "150000", admin_id=super_admin.id)
    await services.wallet.adjust_balance(
        target=user, amount_units=100_000, admin=admin, reason="أولى", credit=True, token="d1"
    )
    with pytest.raises(InvalidAmountError):
        await services.wallet.adjust_balance(
            target=user, amount_units=60_000, admin=admin, reason="تتجاوز اليومي", credit=False, token="d2"
        )
    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="تكمل اليومي", credit=False, token="d3"
    )
    assert await _balance(services, user) == 50_000
    assert await _event_count(repos, "adjust_daily_cap_exceeded") == 1


async def test_super_admin_not_subject_to_caps(services, user, super_admin) -> None:
    """الأدمن الأعلى معفى من السقوف."""
    await services.settings.set("admin_adjust_max_units", "1000", admin_id=super_admin.id)
    await _fund(services, user, super_admin, 5_000_000, "sa1")
    assert await _balance(services, user) == 5_000_000


async def test_zero_cap_means_unlimited(services, user, admin, super_admin) -> None:
    """السقف صفر = بلا سقف (مسموح صراحةً بقرار الأدمن الأعلى، وتنبّه شاشة الأمان)."""
    await services.settings.set("admin_adjust_max_units", "0", admin_id=super_admin.id)
    await services.settings.set("admin_adjust_daily_max_units", "0", admin_id=super_admin.id)
    await services.wallet.adjust_balance(
        target=user, amount_units=9_000_000_000, admin=admin, reason="كبير", credit=True, token="z1"
    )
    assert await _balance(services, user) == 9_000_000_000


# ============================ عمليات الطلبات ============================ #


async def _order_for(services: ServiceContainer, owner: User, funder: User, mock_service):
    """إنشاء طلب لمالك محدد بعد تمويله."""
    await _fund(services, owner, funder, 100_000, f"fund-{owner.id}")
    return await services.orders.create_order(
        owner, service_id=mock_service.id, link="https://instagram.com/self_test", quantity=1000
    )


async def test_admin_cannot_cancel_or_fail_or_override_own_order(
    services, repos, admin, super_admin, mock_service
) -> None:
    """الأدمن لا يلغي/يفشّل/يغيّر حالة طلب يخصّه (لا استرجاع لنفسه)."""
    order = await _order_for(services, admin, super_admin, mock_service)
    balance_after_order = await _balance(services, admin)

    with pytest.raises(PermissionDeniedError):
        await services.orders.admin_cancel(admin, order.id, "إلغاء ذاتي")
    with pytest.raises(PermissionDeniedError):
        await services.orders.admin_mark_failed(admin, order.id, "فشل ذاتي")
    await services.auth.set_user_permission(super_admin, admin.id, "orders.status.override", allow=True)
    with pytest.raises(PermissionDeniedError):
        await services.orders.admin_override_status(admin, order.id, OrderStatus.FAILED, "تجاوز ذاتي")

    assert await _balance(services, admin) == balance_after_order
    assert (await repos.orders.get(order.id)).status == OrderStatus.PENDING
    assert await _event_count(repos, "self_action_blocked") == 3


async def test_other_admin_can_cancel_that_order_with_refund(
    services, admin, super_admin, mock_service
) -> None:
    """أدمن آخر يلغي الطلب فيُرجَع المبلغ لصاحبه (المسار الطبيعي لم يتأثر)."""
    order = await _order_for(services, admin, super_admin, mock_service)
    before = await _balance(services, admin)
    await services.orders.admin_cancel(super_admin, order.id, "إلغاء من أدمن آخر")
    assert await _balance(services, admin) == before + order.cost_units
