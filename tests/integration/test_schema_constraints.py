"""
اختبارات قيود قاعدة البيانات.

الهدف: التأكد أن قاعدة البيانات نفسها ترفض البيانات الخاطئة،
حتى لو حدث خطأ برمجي في الطبقات الأعلى (دفاع أخير).
"""

from __future__ import annotations

import sqlite3

import pytest

from core.enums import OrderStatus, PaymentStatus, TransactionType, values
from database.database import Database
from database.repositories import Repositories


async def _make_order(db: Database, repos: Repositories, user, service, *, crid: str = "req-1"):
    """إنشاء طلب اختباري بسيط."""
    async with db.transaction() as tx:
        return await repos.orders.create(
            tx,
            user_id=user.id,
            service_id=service.id,
            provider_id=service.provider_id,
            service_name_snapshot=service.name,
            price_per_1000_snapshot_units=service.price_per_1000_units,
            link="https://example.com/p/1",
            quantity=1000,
            cost_units=10_000,
            client_request_id=crid,
        )


async def test_balance_cannot_go_negative(db: Database, user) -> None:
    """قيد CHECK يمنع الرصيد السالب حتى عند محاولة تحديث مباشر."""
    with pytest.raises(sqlite3.IntegrityError):
        async with db.transaction() as tx:
            await tx.execute("UPDATE users SET balance_units = -1 WHERE id = ?", (user.id,))


async def test_foreign_key_enforced_on_orders(db: Database, service) -> None:
    """لا يمكن إنشاء طلب لمستخدم غير موجود."""
    with pytest.raises(sqlite3.IntegrityError):
        async with db.transaction() as tx:
            await tx.execute(
                """
                INSERT INTO orders (user_id, service_id, provider_id, service_name_snapshot,
                                    price_per_1000_snapshot_units, link, quantity, cost_units,
                                    client_request_id, created_at, updated_at)
                VALUES (999999, ?, ?, 'x', 1, 'l', 1, 1, 'crid-x', '2026-01-01T00:00:00.000Z',
                        '2026-01-01T00:00:00.000Z')
                """,
                (service.id, service.provider_id),
            )


async def test_user_with_orders_cannot_be_deleted(db: Database, repos: Repositories, user, service) -> None:
    """لا يجوز حذف مستخدم له طلبات (حماية التاريخ المالي)."""
    await _make_order(db, repos, user, service)
    with pytest.raises(sqlite3.IntegrityError):
        async with db.transaction() as tx:
            await tx.execute("DELETE FROM users WHERE id = ?", (user.id,))


async def test_service_with_orders_cannot_be_deleted(db: Database, repos: Repositories, user, service) -> None:
    """لا يجوز حذف خدمة لها طلبات — تُؤرشف بدلاً من ذلك."""
    await _make_order(db, repos, user, service, crid="req-svc")
    with pytest.raises(sqlite3.IntegrityError):
        async with db.transaction() as tx:
            await tx.execute("DELETE FROM services WHERE id = ?", (service.id,))


async def test_duplicate_client_request_id_rejected(db: Database, repos: Repositories, user, service) -> None:
    """نفس مفتاح الطلب لا ينشئ طلبين (حماية الضغط المزدوج)."""
    await _make_order(db, repos, user, service, crid="same-key")
    with pytest.raises(sqlite3.IntegrityError):
        await _make_order(db, repos, user, service, crid="same-key")


async def test_duplicate_transaction_reference_rejected(db: Database, repos: Repositories, user) -> None:
    """نفس المرجع المالي لا يُسجَّل مرتين (حماية الاسترجاع المزدوج)."""
    async with db.transaction() as tx:
        await repos.transactions.insert(
            tx, user_id=user.id, type=TransactionType.DEPOSIT, amount_units=1000,
            balance_before_units=0, balance_after_units=1000, reference="payment:1",
        )
    from core.exceptions import DuplicateOperationError

    with pytest.raises(DuplicateOperationError):
        async with db.transaction() as tx:
            await repos.transactions.insert(
                tx, user_id=user.id, type=TransactionType.DEPOSIT, amount_units=1000,
                balance_before_units=1000, balance_after_units=2000, reference="payment:1",
            )


async def test_duplicate_provider_order_id_rejected(db: Database, repos: Repositories, user, service) -> None:
    """لا يمكن ربط رقم طلب المزود نفسه بطلبين (كشف الازدواج)."""
    first = await _make_order(db, repos, user, service, crid="a")
    second = await _make_order(db, repos, user, service, crid="b")
    async with db.transaction() as tx:
        await repos.orders.update_fields(tx, first.id, provider_order_id="P-100")
    with pytest.raises(sqlite3.IntegrityError):
        async with db.transaction() as tx:
            await repos.orders.update_fields(tx, second.id, provider_order_id="P-100")


async def test_refund_cannot_exceed_cost(db: Database, repos: Repositories, user, service) -> None:
    """قيد CHECK يمنع أن يتجاوز مجموع الاسترجاع تكلفة الطلب."""
    order = await _make_order(db, repos, user, service, crid="refund-guard")
    async with db.transaction() as tx:
        assert await repos.orders.add_refund_amount(tx, order.id, 10_000) is True
    async with db.transaction() as tx:
        assert await repos.orders.add_refund_amount(tx, order.id, 1) is False


async def test_invalid_order_status_rejected(db: Database, repos: Repositories, user, service) -> None:
    """قيد CHECK يرفض أي حالة طلب غير معرَّفة في النظام."""
    order = await _make_order(db, repos, user, service, crid="status-check")
    with pytest.raises(sqlite3.IntegrityError):
        async with db.transaction() as tx:
            await tx.execute("UPDATE orders SET status = 'hacked' WHERE id = ?", (order.id,))


async def test_all_enum_order_statuses_accepted(db: Database, repos: Repositories, user, service) -> None:
    """كل حالة معرَّفة في enums مقبولة في قاعدة البيانات (تطابق الكود مع المخطط)."""
    order = await _make_order(db, repos, user, service, crid="status-enum")
    for status in values(OrderStatus):
        async with db.transaction() as tx:
            await tx.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order.id))
    assert True


async def test_all_enum_payment_statuses_accepted(
    db: Database, repos: Repositories, user, payment_method
) -> None:
    """كل حالات الدفع المعرَّفة مقبولة في المخطط."""
    async with db.transaction() as tx:
        payment = await repos.payments.create(
            tx, user_id=user.id, method_id=payment_method.id, amount_units=50_000
        )
    for status in values(PaymentStatus):
        async with db.transaction() as tx:
            await tx.execute("UPDATE payments SET status = ? WHERE id = ?", (status, payment.id))
    assert True


async def test_all_enum_transaction_types_accepted(db: Database, repos: Repositories, user) -> None:
    """كل أنواع الحركات المالية المعرَّفة مقبولة في المخطط."""
    for index, tx_type in enumerate(values(TransactionType)):
        async with db.transaction() as tx:
            await repos.transactions.insert(
                tx, user_id=user.id, type=tx_type, amount_units=100,
                balance_before_units=0, balance_after_units=100, reference=f"enum-{index}",
            )
    assert await repos.transactions.count_by_user(user.id) == len(values(TransactionType))


async def test_notification_dedupe_key_unique(db: Database, repos: Repositories, user) -> None:
    """مفتاح منع تكرار الإشعار فريد: الإدراج الثاني لا ينشئ صفاً."""
    async with db.transaction() as tx:
        first = await repos.notifications.enqueue(
            tx, user_id=user.id, type="order_created", message="م1", dedupe_key="order:1:created"
        )
    async with db.transaction() as tx:
        second = await repos.notifications.enqueue(
            tx, user_id=user.id, type="order_created", message="م1", dedupe_key="order:1:created"
        )
    assert first is not None
    assert second is None
    assert await repos.notifications.count_queued() == 1


async def test_service_max_quantity_must_be_ge_min(db: Database, repos: Repositories, provider) -> None:
    """قيد يمنع أن يكون الحد الأقصى أقل من الحد الأدنى."""
    categories = await repos.categories.list_all()
    with pytest.raises(sqlite3.IntegrityError):
        async with db.transaction() as tx:
            await repos.services.create(
                tx, category_id=categories[0].id, provider_id=provider.id, provider_service_id="9",
                name="خدمة خاطئة", price_per_1000_units=1000, min_quantity=500, max_quantity=100,
            )


async def test_transaction_amount_must_be_positive(db: Database, user) -> None:
    """قيد يمنع تسجيل حركة مالية بمبلغ صفر أو سالب."""
    with pytest.raises(sqlite3.IntegrityError):
        async with db.transaction() as tx:
            await tx.execute(
                """
                INSERT INTO transactions (user_id, type, direction, amount_units,
                                          balance_before_units, balance_after_units, created_at)
                VALUES (?, 'deposit', 'credit', 0, 0, 0, '2026-01-01T00:00:00.000Z')
                """,
                (user.id,),
            )
