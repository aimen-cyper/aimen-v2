"""
اختبارات المحفظة — الخدمة المالية المركزية.

هذه أهم اختبارات المشروع: أي خلل هنا يعني مالاً ضائعاً أو رصيداً سالباً.
تشمل: الخصم، الاسترجاع (الكامل والجزئي)، منع التكرار، التسويات اليدوية،
تدقيق الدفتر، واختبار السباق (50 خصماً متزامناً على رصيد يكفي 10 فقط).
"""

from __future__ import annotations

import asyncio

import pytest

from core.enums import TransactionType
from core.exceptions import (
    DuplicateOperationError,
    InsufficientBalanceError,
    InvalidAmountError,
    WalletError,
)
from database.database import Database
from database.models import Service, User
from database.repositories import Repositories
from services import ServiceContainer

ORDER_COST = 10_000  # 1.0000 من وحدة العملة


async def _make_order(db: Database, repos: Repositories, user: User, service: Service, index: int):
    """إنشاء صف طلب خام للاختبار (بلا خصم) — الخصم يتم عبر المحفظة في الاختبار نفسه."""
    async with db.transaction() as tx:
        return await repos.orders.create(
            tx,
            user_id=user.id,
            service_id=service.id,
            provider_id=service.provider_id,
            service_name_snapshot=service.name,
            price_per_1000_snapshot_units=service.price_per_1000_units,
            link=f"https://instagram.com/u{index}",
            quantity=1000,
            cost_units=ORDER_COST,
            client_request_id=f"test-{index}",
        )


async def _credit(services: ServiceContainer, user: User, amount_units: int, admin: User) -> None:
    """شحن رصيد اختباري عبر المسار الرسمي (تسوية يدوية من الأدمن)."""
    await services.wallet.adjust_balance(
        target=user, amount_units=amount_units, admin=admin, reason="رصيد اختباري", credit=True
    )


# ------------------------------- الخصم ---------------------------------- #


async def test_charge_debits_and_records_transaction(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, admin: User, service: Service
) -> None:
    """الخصم ينقص الرصيد ويكتب حركة مالية بنفس المعاملة."""
    await _credit(services, user, 50_000, admin)
    order = await _make_order(db, repos, user, service, 1)

    async with db.transaction() as tx:
        transaction = await services.wallet.charge_for_order(
            tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
        )

    assert transaction.type == TransactionType.ORDER
    assert transaction.balance_before_units == 50_000
    assert transaction.balance_after_units == 40_000
    assert await services.wallet.balance_units(user.id) == 40_000

    refreshed = await repos.users.get_by_id(user.id)
    assert refreshed is not None and refreshed.total_spent_units == ORDER_COST


async def test_charge_without_balance_raises_and_changes_nothing(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, service: Service
) -> None:
    """الخصم بلا رصيد كافٍ يرفع استثناءً ولا يغيّر شيئاً."""
    order = await _make_order(db, repos, user, service, 2)

    with pytest.raises(InsufficientBalanceError):
        async with db.transaction() as tx:
            await services.wallet.charge_for_order(
                tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
            )

    assert await services.wallet.balance_units(user.id) == 0
    assert await repos.transactions.count_by_user(user.id) == 0


async def test_double_charge_for_same_order_rejected(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, admin: User, service: Service
) -> None:
    """لا يُخصم الطلب الواحد مرتين (مرجع العملية فريد)."""
    await _credit(services, user, 50_000, admin)
    order = await _make_order(db, repos, user, service, 3)

    async with db.transaction() as tx:
        await services.wallet.charge_for_order(
            tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
        )

    with pytest.raises(DuplicateOperationError):
        async with db.transaction() as tx:
            await services.wallet.charge_for_order(
                tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
            )

    assert await services.wallet.balance_units(user.id) == 40_000


@pytest.mark.parametrize("amount", [0, -1])
async def test_invalid_amounts_rejected(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, service: Service, amount: int
) -> None:
    """المبالغ غير الموجبة مرفوضة في كل العمليات المالية."""
    order = await _make_order(db, repos, user, service, 4)
    with pytest.raises(InvalidAmountError):
        async with db.transaction() as tx:
            await services.wallet.charge_for_order(
                tx, user_id=user.id, order_id=order.id, amount_units=amount
            )


# ------------------------------ الاسترجاع -------------------------------- #


async def test_full_refund_returns_money_once(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, admin: User, service: Service
) -> None:
    """الاسترجاع الكامل يعيد المبلغ مرة واحدة فقط، وإعادة المحاولة لا تضاعفه."""
    await _credit(services, user, 50_000, admin)
    order = await _make_order(db, repos, user, service, 5)

    async with db.transaction() as tx:
        await services.wallet.charge_for_order(
            tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
        )
    async with db.transaction() as tx:
        first = await services.wallet.refund_order(
            tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
        )
    async with db.transaction() as tx:
        second = await services.wallet.refund_order(
            tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
        )

    assert first is not None and first.type == TransactionType.REFUND
    assert second is None, "الاسترجاع المكرر يجب أن يُتجاهل بهدوء لا أن يضاعف المال"
    assert await services.wallet.balance_units(user.id) == 50_000

    refreshed_order = await repos.orders.get(order.id)
    assert refreshed_order is not None
    assert refreshed_order.refund_amount_units == ORDER_COST
    assert refreshed_order.refunded_at is not None


async def test_partial_refund_cannot_exceed_order_cost(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, admin: User, service: Service
) -> None:
    """مجموع الاسترجاعات لا يتجاوز تكلفة الطلب أبداً."""
    await _credit(services, user, 50_000, admin)
    order = await _make_order(db, repos, user, service, 6)
    async with db.transaction() as tx:
        await services.wallet.charge_for_order(
            tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
        )

    async with db.transaction() as tx:
        await services.wallet.refund_order(
            tx, user_id=user.id, order_id=order.id, amount_units=4_000, partial=True
        )

    with pytest.raises(WalletError):
        async with db.transaction() as tx:
            await services.wallet.refund_order(
                tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
            )

    assert await services.wallet.balance_units(user.id) == 44_000
    refreshed = await repos.orders.get(order.id)
    assert refreshed is not None and refreshed.refund_amount_units == 4_000


# ---------------------------- الإيداع والتسوية ---------------------------- #


async def test_credit_from_payment_counts_as_deposit(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, payment_method
) -> None:
    """الإيداع المعتمد يزيد الرصيد ويزيد إجمالي الإيداعات."""
    async with db.transaction() as tx:
        payment = await repos.payments.create(
            tx, user_id=user.id, method_id=payment_method.id, amount_units=30_000
        )
    async with db.transaction() as tx:
        transaction = await services.wallet.credit_from_payment(
            tx, user_id=user.id, payment_id=payment.id, amount_units=30_000
        )

    assert transaction.type == TransactionType.DEPOSIT
    refreshed = await repos.users.get_by_id(user.id)
    assert refreshed is not None
    assert refreshed.balance_units == 30_000
    assert refreshed.total_deposited_units == 30_000

    with pytest.raises(DuplicateOperationError):
        async with db.transaction() as tx:
            await services.wallet.credit_from_payment(
                tx, user_id=user.id, payment_id=payment.id, amount_units=30_000
            )


async def test_manual_adjustments_write_audit_log(
    services: ServiceContainer, repos: Repositories, user: User, admin: User
) -> None:
    """التسوية اليدوية تُسجَّل في سجل التدقيق باسم الأدمن المنفّذ."""
    await services.wallet.adjust_balance(
        target=user, amount_units=20_000, admin=admin, reason="تعويض", credit=True
    )
    await services.wallet.adjust_balance(
        target=user, amount_units=5_000, admin=admin, reason="تصحيح خطأ", credit=False
    )

    assert await services.wallet.balance_units(user.id) == 15_000
    logs = await repos.audit.list_by_admin(admin.id, limit=10)
    actions = {log.action for log in logs}
    assert "users.balance.credit" in actions
    assert "users.balance.debit" in actions


async def test_manual_debit_cannot_overdraw(
    services: ServiceContainer, user: User, admin: User
) -> None:
    """الخصم اليدوي لا يجعل الرصيد سالباً."""
    await _credit(services, user, 10_000, admin)
    with pytest.raises(InsufficientBalanceError):
        await services.wallet.adjust_balance(
            target=user, amount_units=99_000, admin=admin, reason="خصم كبير", credit=False
        )
    assert await services.wallet.balance_units(user.id) == 10_000


# ------------------------------ تدقيق الدفتر ------------------------------ #


async def test_ledger_matches_stored_balance(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, admin: User, service: Service
) -> None:
    """الرصيد المخزَّن يساوي مجموع دفتر الحركات بعد سلسلة عمليات."""
    await _credit(services, user, 100_000, admin)
    order = await _make_order(db, repos, user, service, 7)
    async with db.transaction() as tx:
        await services.wallet.charge_for_order(
            tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
        )
    async with db.transaction() as tx:
        await services.wallet.refund_order(
            tx, user_id=user.id, order_id=order.id, amount_units=2_000, partial=True
        )

    check = await services.wallet.verify_ledger(user.id)
    assert check.is_balanced, f"اختلال محاسبي بمقدار {check.difference_units}"
    assert check.difference_units == 0


# ------------------------------ اختبار السباق ----------------------------- #


async def test_fifty_concurrent_charges_never_overdraw(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, admin: User, service: Service
) -> None:
    """
    الاختبار الإلزامي: 50 خصماً متزامناً على رصيد يكفي 10 عمليات فقط.

    المتوقع: ينجح 10 بالضبط، ويفشل 40 بـInsufficientBalanceError،
    والرصيد النهائي صفر — لا رصيد سالب ولا خصم ضائع.
    """
    await _credit(services, user, ORDER_COST * 10, admin)
    orders = [await _make_order(db, repos, user, service, 100 + i) for i in range(50)]

    async def charge(order_id: int) -> bool:
        """محاولة خصم واحدة مستقلة بمعاملتها الخاصة."""
        try:
            async with db.transaction() as tx:
                await services.wallet.charge_for_order(
                    tx, user_id=user.id, order_id=order_id, amount_units=ORDER_COST
                )
            return True
        except InsufficientBalanceError:
            return False

    results = await asyncio.gather(*(charge(order.id) for order in orders))

    assert sum(results) == 10, f"نجح {sum(results)} خصماً بدل 10 بالضبط"
    assert await services.wallet.balance_units(user.id) == 0

    charge_transactions = [
        transaction
        for transaction in await repos.transactions.list_by_user(user.id, limit=100)
        if transaction.type == TransactionType.ORDER
    ]
    assert len(charge_transactions) == 10
    assert all(transaction.balance_after_units >= 0 for transaction in charge_transactions)

    check = await services.wallet.verify_ledger(user.id)
    assert check.is_balanced


async def test_concurrent_refunds_credit_once(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, admin: User, service: Service
) -> None:
    """عشر محاولات استرجاع متزامنة لنفس الطلب تُعيد المبلغ مرة واحدة فقط."""
    await _credit(services, user, 50_000, admin)
    order = await _make_order(db, repos, user, service, 200)
    async with db.transaction() as tx:
        await services.wallet.charge_for_order(
            tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
        )

    async def refund() -> bool:
        """محاولة استرجاع واحدة."""
        try:
            async with db.transaction() as tx:
                transaction = await services.wallet.refund_order(
                    tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
                )
            return transaction is not None
        except WalletError:
            return False

    results = await asyncio.gather(*(refund() for _ in range(10)))

    assert sum(results) == 1
    assert await services.wallet.balance_units(user.id) == 50_000
    refreshed = await repos.orders.get(order.id)
    assert refreshed is not None and refreshed.refund_amount_units == ORDER_COST
