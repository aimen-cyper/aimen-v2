"""
اختبارات طبقة الاتصال والمعاملات.

أهم اختبار هنا: سباق الخصم المتزامن — إثبات أن الرصيد لا يمكن أن يصبح سالباً
مهما تزاحمت العمليات.
"""

from __future__ import annotations

import asyncio

import pytest

from core.exceptions import DatabaseError
from database.database import Database
from database.repositories import Repositories


async def test_commit_persists_changes(db: Database, repos: Repositories, user) -> None:
    """التعديل داخل معاملة ناجحة يُحفظ فعلاً."""
    async with db.transaction() as tx:
        await repos.users.update_fields(tx, user.id, first_name="مُعدَّل")
    refreshed = await repos.users.get_by_id(user.id)
    assert refreshed is not None and refreshed.first_name == "مُعدَّل"


async def test_rollback_on_exception(db: Database, repos: Repositories, user) -> None:
    """أي استثناء داخل المعاملة يتراجع عن كل التعديلات."""
    with pytest.raises(RuntimeError):
        async with db.transaction() as tx:
            await repos.users.update_fields(tx, user.id, first_name="لن يُحفظ")
            await repos.users.credit(tx, user.id, 50_000)
            raise RuntimeError("فشل مُتعمَّد")

    refreshed = await repos.users.get_by_id(user.id)
    assert refreshed is not None
    assert refreshed.first_name == "Tester"
    assert refreshed.balance_units == 0


async def test_nested_transaction_shares_outer(db: Database, repos: Repositories, user) -> None:
    """المعاملة المتداخلة تستخدم نفس المعاملة الخارجية ولا تُثبِّت مبكراً."""
    with pytest.raises(RuntimeError):
        async with db.transaction() as outer:
            await repos.users.credit(outer, user.id, 10_000)
            async with db.transaction() as inner:
                await repos.users.credit(inner, user.id, 10_000)
            raise RuntimeError("تراجع كامل")

    refreshed = await repos.users.get_by_id(user.id)
    assert refreshed is not None and refreshed.balance_units == 0


async def test_concurrent_debits_never_go_negative(db: Database, repos: Repositories, user) -> None:
    """
    سيناريو السباق: رصيد يكفي 10 عمليات فقط، و50 محاولة خصم متزامنة.

    المتوقع: تنجح 10 بالضبط، ويبقى الرصيد صفراً — لا سالب ولا خصم مزدوج.
    """
    async with db.transaction() as tx:
        await repos.users.credit(tx, user.id, 10)

    async def attempt(index: int) -> bool:
        """محاولة خصم نقطة واحدة مع تسجيل حركة مالية."""
        async with db.transaction() as tx:
            ok = await repos.users.try_debit(tx, user.id, 1)
            if ok:
                balance = await repos.users.get_balance_units(user.id)
                await repos.transactions.insert(
                    tx, user_id=user.id, type="order", amount_units=1,
                    balance_before_units=balance + 1, balance_after_units=balance,
                    reference=f"race:{index}",
                )
            return ok

    results = await asyncio.gather(*(attempt(i) for i in range(50)))
    refreshed = await repos.users.get_by_id(user.id)

    assert sum(results) == 10
    assert refreshed is not None and refreshed.balance_units == 0
    assert await repos.transactions.count_by_user(user.id) == 10


async def test_ledger_matches_balance(db: Database, repos: Repositories, user) -> None:
    """مجموع دفتر الحركات يطابق الرصيد المخزَّن (تدقيق محاسبي)."""
    async with db.transaction() as tx:
        await repos.users.credit(tx, user.id, 100_000, count_as_deposit=True)
        await repos.transactions.insert(
            tx, user_id=user.id, type="deposit", amount_units=100_000,
            balance_before_units=0, balance_after_units=100_000, reference="p:1",
        )
    async with db.transaction() as tx:
        await repos.users.try_debit(tx, user.id, 30_000)
        await repos.transactions.insert(
            tx, user_id=user.id, type="order", amount_units=30_000,
            balance_before_units=100_000, balance_after_units=70_000, reference="o:1",
        )

    user_row = await repos.users.get_by_id(user.id)
    assert user_row is not None
    assert user_row.balance_units == 70_000
    assert await repos.transactions.user_balance_from_ledger(user.id) == 70_000


async def test_try_debit_insufficient_returns_false(db: Database, repos: Repositories, user) -> None:
    """محاولة خصم أكبر من الرصيد تُرجع False ولا تغيّر شيئاً."""
    async with db.transaction() as tx:
        await repos.users.credit(tx, user.id, 5_000)
    async with db.transaction() as tx:
        assert await repos.users.try_debit(tx, user.id, 5_001) is False
    assert await repos.users.get_balance_units(user.id) == 5_000


async def test_operations_require_connection(tmp_path) -> None:
    """استخدام قاعدة بيانات غير متصلة يعطي خطأ واضحاً لا انهياراً غامضاً."""
    database = Database(tmp_path / "x.db")
    with pytest.raises(DatabaseError):
        await database.fetchone("SELECT 1")


async def test_reads_work_during_open_transaction(db: Database, repos: Repositories, user) -> None:
    """القراءة داخل معاملة ترى التعديلات غير المثبتة (نفس الاتصال)."""
    async with db.transaction() as tx:
        await repos.users.credit(tx, user.id, 7_000)
        inside = await repos.users.get_balance_units(user.id)
        assert inside == 7_000
    assert await repos.users.get_balance_units(user.id) == 7_000


async def test_integrity_and_foreign_key_check(db: Database) -> None:
    """أدوات الفحص الإداري تعمل وتُرجع نتيجة سليمة."""
    assert await db.integrity_check() is True
    assert await db.foreign_key_check() == []
