"""
مستودع الحركات المالية (دفتر الأستاذ).

قواعد صارمة:
    • الجدول «إضافة فقط»: لا يوجد UPDATE ولا DELETE هنا، وأي تصحيح يكون بحركة adjustment جديدة.
    • عمود reference فريد، وهو خط الدفاع الأخير ضد تكرار أي عملية مالية.
"""

from __future__ import annotations

import sqlite3

from core.enums import TRANSACTION_DIRECTIONS, TransactionDirection
from core.exceptions import DuplicateOperationError
from database.database import Tx
from database.models import Transaction
from database.repositories.base import BaseRepository


class TransactionsRepository(BaseRepository):
    """تسجيل وقراءة الحركات المالية."""

    # ------------------------------ الكتابة ------------------------------ #

    async def insert(
        self,
        tx: Tx,
        *,
        user_id: int,
        type: str,
        amount_units: int,
        balance_before_units: int,
        balance_after_units: int,
        direction: str | None = None,
        order_id: int | None = None,
        payment_id: int | None = None,
        description: str | None = None,
        reference: str | None = None,
        actor_id: int | None = None,
    ) -> Transaction:
        """
        تسجيل حركة مالية جديدة.

        المدخلات:
            type      : نوع الحركة (deposit/order/refund/...).
            direction : اتجاه الحركة، ويُستنتج تلقائياً من النوع إن لم يُحدَّد.
            reference : مرجع فريد لمنع التكرار (مثل "refund:order:12").

        الاستثناءات:
            DuplicateOperationError : المرجع مستخدم سابقاً ⇒ العملية نُفِّذت من قبل.
        """
        if amount_units <= 0:
            raise ValueError("مبلغ الحركة يجب أن يكون أكبر من صفر.")
        resolved_direction = direction or TRANSACTION_DIRECTIONS.get(type, TransactionDirection.CREDIT)

        try:
            result = await tx.execute(
                """
                INSERT INTO transactions (user_id, order_id, payment_id, type, direction, amount_units,
                                          balance_before_units, balance_after_units, description,
                                          reference, actor_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id, order_id, payment_id, type, str(resolved_direction), amount_units,
                    balance_before_units, balance_after_units, description, reference, actor_id, self.now(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            if "transactions.reference" in str(exc) or "UNIQUE" in str(exc).upper():
                raise DuplicateOperationError(
                    f"حركة مالية بنفس المرجع موجودة مسبقاً: {reference}"
                ) from exc
            raise

        row = await tx.fetchone("SELECT * FROM transactions WHERE id = ?", (result.lastrowid,))
        transaction = Transaction.from_row(row)
        assert transaction is not None
        return transaction

    # ------------------------------ القراءة ------------------------------ #

    async def exists_reference(self, reference: str) -> bool:
        """هل سبق تنفيذ عملية بهذا المرجع؟ (فحص استباقي قبل محاولة الإدراج)."""
        row = await self.db.fetchone("SELECT 1 FROM transactions WHERE reference = ?", (reference,))
        return row is not None

    async def get_by_reference(self, reference: str) -> Transaction | None:
        """جلب حركة بمرجعها الفريد."""
        row = await self.db.fetchone("SELECT * FROM transactions WHERE reference = ?", (reference,))
        return Transaction.from_row(row)

    async def get(self, transaction_id: int) -> Transaction | None:
        """جلب حركة بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM transactions WHERE id = ?", (transaction_id,))
        return Transaction.from_row(row)

    async def list_by_user(self, user_id: int, *, limit: int = 10, offset: int = 0) -> list[Transaction]:
        """سجل العمليات المالية للمستخدم (الأحدث أولاً)."""
        rows = await self.db.fetchall(
            "SELECT * FROM transactions WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
        return Transaction.from_rows(rows)

    async def count_by_user(self, user_id: int) -> int:
        """عدد الحركات المالية للمستخدم."""
        return await self.count("transactions", "user_id = ?", (user_id,))

    async def list_by_order(self, order_id: int) -> list[Transaction]:
        """كل الحركات المرتبطة بطلب (خصم + استرجاعات)."""
        rows = await self.db.fetchall(
            "SELECT * FROM transactions WHERE order_id = ? ORDER BY id", (order_id,)
        )
        return Transaction.from_rows(rows)

    async def sum_by_type(self, tx_type: str, *, start_iso: str | None = None, end_iso: str | None = None) -> int:
        """إجمالي المبالغ لنوع حركة خلال فترة اختيارية (بالنقاط)."""
        sql = "SELECT COALESCE(SUM(amount_units), 0) FROM transactions WHERE type = ?"
        params: list[object] = [tx_type]
        if start_iso:
            sql += " AND created_at >= ?"
            params.append(start_iso)
        if end_iso:
            sql += " AND created_at < ?"
            params.append(end_iso)
        return int(await self.db.fetchval(sql, params, default=0))

    async def sum_manual_by_actor(self, executor: Tx, actor_id: int, since_iso: str) -> int:
        """
        مجموع التسويات اليدوية (إضافة + خصم) التي نفّذها أدمن منذ وقت محدد.

        يُستدعى **داخل** معاملة الكتابة نفسها (`executor` هو الـTx) فتكون القراءة
        والإدراج ذرّيين: لا يستطيع طلبان متزامنان تجاوز السقف اليومي معاً.
        """
        value = await executor.fetchval(
            """
            SELECT COALESCE(SUM(amount_units), 0) FROM transactions
            WHERE actor_id = ? AND type IN ('manual_credit', 'manual_debit') AND created_at >= ?
            """,
            (actor_id, since_iso),
            default=0,
        )
        return int(value)

    async def user_balance_from_ledger(self, user_id: int) -> int:
        """
        احتساب الرصيد من دفتر الحركات (للمطابقة والتدقيق).

        الفائدة: مقارنة الناتج مع users.balance_units يكشف أي خلل محاسبي.
        """
        return int(
            await self.db.fetchval(
                """
                SELECT COALESCE(SUM(CASE WHEN direction = 'credit' THEN amount_units ELSE -amount_units END), 0)
                  FROM transactions WHERE user_id = ?
                """,
                (user_id,),
                default=0,
            )
        )
