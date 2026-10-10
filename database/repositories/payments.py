"""
مستودع المدفوعات — طلبات شحن الرصيد وطرق الدفع.

الحماية الأساسية هنا: تغيير حالة الدفعة مشروط بحالتها السابقة،
فلا يمكن اعتماد نفس الدفعة مرتين حتى لو ضغط الأدمن الزر مرتين.
"""

from __future__ import annotations

from typing import Any, Sequence

from database.database import Tx
from database.models import Payment, PaymentMethod
from database.repositories.base import BaseRepository
from utils.datetime_utils import utc_now_iso

_METHOD_FIELDS = {
    "code",
    "name_ar",
    "type",
    "instructions_ar",
    "account_details",
    "min_amount_units",
    "max_amount_units",
    "requires_proof",
    "is_active",
    "sort_order",
    "fee_percent_bp",
    "fee_fixed_units",
}

_PAYMENT_FIELDS = {
    "amount_units",
    "credited_units",
    "status",
    "transaction_reference",
    "proof_file_id",
    "proof_file_type",
    "user_note",
    "admin_id",
    "admin_note",
    "reject_reason",
    "reviewed_at",
    "expires_at",
}


class PaymentMethodsRepository(BaseRepository):
    """إدارة طرق الشحن القابلة للتهيئة من لوحة الأدمن."""

    async def get(self, method_id: int) -> PaymentMethod | None:
        """جلب طريقة دفع بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM payment_methods WHERE id = ?", (method_id,))
        return PaymentMethod.from_row(row)

    async def get_by_code(self, code: str) -> PaymentMethod | None:
        """جلب طريقة دفع بالكود الفريد."""
        row = await self.db.fetchone("SELECT * FROM payment_methods WHERE code = ?", (code,))
        return PaymentMethod.from_row(row)

    async def list_all(self, *, active_only: bool = False) -> list[PaymentMethod]:
        """قائمة طرق الدفع مرتبة للعرض."""
        sql = "SELECT * FROM payment_methods"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY sort_order, id"
        rows = await self.db.fetchall(sql)
        return PaymentMethod.from_rows(rows)

    async def create(
        self,
        tx: Tx,
        *,
        code: str,
        name_ar: str,
        instructions_ar: str = "",
        account_details: str = "",
        type: str = "manual",
        min_amount_units: int = 0,
        max_amount_units: int | None = None,
        requires_proof: bool = True,
        sort_order: int = 100,
        fee_percent_bp: int = 0,
        fee_fixed_units: int = 0,
    ) -> PaymentMethod:
        """إضافة طريقة دفع جديدة (مع رسومها إن وُجدت)."""
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO payment_methods (code, name_ar, type, instructions_ar, account_details,
                                         min_amount_units, max_amount_units, requires_proof,
                                         sort_order, fee_percent_bp, fee_fixed_units,
                                         created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code, name_ar, type, instructions_ar, account_details, min_amount_units,
                max_amount_units, 1 if requires_proof else 0, sort_order,
                fee_percent_bp, fee_fixed_units, now, now,
            ),
        )
        row = await tx.fetchone("SELECT * FROM payment_methods WHERE id = ?", (result.lastrowid,))
        method = PaymentMethod.from_row(row)
        assert method is not None
        return method

    async def update_fields(self, tx: Tx, method_id: int, **fields: Any) -> bool:
        """تعديل بيانات طريقة دفع."""
        return await self._update_by_id(tx, "payment_methods", method_id, fields, _METHOD_FIELDS)

    async def next_sort_order(self) -> int:
        """ترتيب العرض التالي (تُضاف الطريقة الجديدة في آخر القائمة)."""
        value = await self.db.fetchval(
            "SELECT COALESCE(MAX(sort_order), 0) FROM payment_methods", default=0
        )
        return int(value) + 10

    async def neighbour(self, method: PaymentMethod, *, up: bool) -> PaymentMethod | None:
        """
        الطريقة المجاورة في ترتيب العرض (الأعلى أو الأدنى مباشرة).

        تُستخدم لتبديل الترتيب من اللوحة بزرَّي ▲/▼ بلا إدخال أرقام يدوية.
        """
        if up:
            sql = """
                SELECT * FROM payment_methods
                 WHERE (sort_order < ?) OR (sort_order = ? AND id < ?)
                 ORDER BY sort_order DESC, id DESC LIMIT 1
            """
        else:
            sql = """
                SELECT * FROM payment_methods
                 WHERE (sort_order > ?) OR (sort_order = ? AND id > ?)
                 ORDER BY sort_order, id LIMIT 1
            """
        row = await self.db.fetchone(sql, (method.sort_order, method.sort_order, method.id))
        return PaymentMethod.from_row(row)


class PaymentsRepository(BaseRepository):
    """إدارة طلبات الشحن."""

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, payment_id: int) -> Payment | None:
        """جلب طلب شحن بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM payments WHERE id = ?", (payment_id,))
        return Payment.from_row(row)

    async def list_by_user(self, user_id: int, *, limit: int = 10, offset: int = 0) -> list[Payment]:
        """طلبات شحن مستخدم معين."""
        rows = await self.db.fetchall(
            "SELECT * FROM payments WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
        return Payment.from_rows(rows)

    async def list_pending(self, *, limit: int = 10, offset: int = 0) -> list[Payment]:
        """طلبات الشحن المعلّقة بانتظار مراجعة الأدمن (الأقدم أولاً)."""
        rows = await self.db.fetchall(
            "SELECT * FROM payments WHERE status = 'pending' ORDER BY id LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return Payment.from_rows(rows)

    async def count_pending(self) -> int:
        """عدد طلبات الشحن المعلّقة (يظهر في لوحة المعلومات)."""
        return await self.count("payments", "status = 'pending'")

    async def count_pending_by_user(self, user_id: int) -> int:
        """عدد طلبات الشحن المعلّقة لمستخدم واحد (لمنع تكديس الطلبات)."""
        return await self.count("payments", "user_id = ? AND status = 'pending'", (user_id,))

    async def usage_by_method(self) -> list[Any]:
        """
        إحصاء استخدام طرق الشحن لكل طريقة على حدة.

        المخرجات: صفوف فيها method_id و name_ar و is_active و approved_count و
                  pending_count و total_units (المضاف فعلاً) و fee_units (الرسوم المحصّلة).

        ملاحظة: `LEFT JOIN` مقصود — الطريقة التي لم تُستخدم بعد تظهر بأصفار
        لا أن تختفي، وإلا ظن الأدمن أنها غير موجودة.
        """
        return await self.db.fetchall(
            """
            SELECT m.id        AS method_id,
                   m.name_ar   AS name_ar,
                   m.is_active AS is_active,
                   COUNT(ap.id) AS approved_count,
                   COALESCE(SUM(COALESCE(ap.credited_units, ap.amount_units)), 0) AS total_units,
                   COALESCE(SUM(ap.fee_units), 0) AS fee_units,
                   (SELECT COUNT(*) FROM payments pp
                     WHERE pp.method_id = m.id AND pp.status = 'pending') AS pending_count
              FROM payment_methods m
              LEFT JOIN payments ap ON ap.method_id = m.id AND ap.status = 'approved'
             GROUP BY m.id
             ORDER BY total_units DESC, m.sort_order
            """
        )

    async def list_filtered(
        self, *, statuses: Sequence[str] | None = None, limit: int = 10, offset: int = 0
    ) -> list[Payment]:
        """
        قائمة طلبات الشحن حسب الحالة (أو كلها عند عدم تمرير حالات).

        الترتيب: المعلّق الأقدم أولاً (طابور مراجعة عادل)، وبقية الحالات
        الأحدث أولاً (آخر ما عولج يهم أكثر).
        """
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            order = "id" if list(statuses) == ["pending"] else "id DESC"
            rows = await self.db.fetchall(
                f"SELECT * FROM payments WHERE status IN ({placeholders}) "
                f"ORDER BY {order} LIMIT ? OFFSET ?",
                (*statuses, limit, offset),
            )
        else:
            rows = await self.db.fetchall(
                "SELECT * FROM payments ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
            )
        return Payment.from_rows(rows)

    async def count_filtered(self, *, statuses: Sequence[str] | None = None) -> int:
        """عدد طلبات الشحن ضمن حالات محددة (لحساب صفحات القائمة)."""
        if not statuses:
            return await self.count("payments")
        placeholders = ", ".join("?" for _ in statuses)
        return await self.count("payments", f"status IN ({placeholders})", tuple(statuses))

    async def search(self, term: str, *, limit: int = 10) -> list[Payment]:
        """
        بحث الأدمن عن طلب شحن برقم العملية (كلياً أو جزئياً) أو برقم الطلب.

        المدخلات: term نص البحث كما كتبه الأدمن (نُظّف قبل الوصول هنا).
        المخرجات: أحدث الطلبات المطابقة (محدودة بـlimit).
        """
        like = f"%{term}%"
        payment_id = int(term) if term.isdigit() else -1
        rows = await self.db.fetchall(
            """
            SELECT * FROM payments
             WHERE (transaction_reference IS NOT NULL AND transaction_reference LIKE ?)
                OR id = ?
             ORDER BY id DESC LIMIT ?
            """,
            (like, payment_id, limit),
        )
        return Payment.from_rows(rows)

    async def list_expired_pending(self, *, limit: int = 50) -> list[Payment]:
        """طلبات الشحن المعلّقة التي انتهت صلاحيتها (لمهمة الإغلاق التلقائي)."""
        rows = await self.db.fetchall(
            """
            SELECT * FROM payments
             WHERE status = 'pending' AND expires_at IS NOT NULL AND expires_at <= ?
             ORDER BY id LIMIT ?
            """,
            (utc_now_iso(), limit),
        )
        return Payment.from_rows(rows)

    async def sum_approved_between(self, start_iso: str, end_iso: str) -> int:
        """إجمالي المبالغ المعتمدة خلال فترة (بالنقاط)."""
        return int(
            await self.db.fetchval(
                """
                SELECT COALESCE(SUM(COALESCE(credited_units, amount_units)), 0) FROM payments
                 WHERE status = 'approved' AND reviewed_at >= ? AND reviewed_at < ?
                """,
                (start_iso, end_iso),
                default=0,
            )
        )

    async def find_duplicate_reference(self, reference: str) -> Payment | None:
        """
        البحث عن طلب شحن سابق بنفس رقم الحوالة.

        الفائدة: كشف محاولة استخدام نفس إثبات الدفع مرتين.
        """
        row = await self.db.fetchone(
            """
            SELECT * FROM payments
             WHERE transaction_reference IS NOT NULL AND transaction_reference = ?
               AND status IN ('pending', 'approved')
             ORDER BY id DESC LIMIT 1
            """,
            (reference,),
        )
        return Payment.from_row(row)

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        user_id: int,
        method_id: int,
        amount_units: int,
        transaction_reference: str | None = None,
        proof_file_id: str | None = None,
        proof_file_type: str | None = None,
        user_note: str | None = None,
        expires_at: str | None = None,
        fee_units: int = 0,
    ) -> Payment:
        """إنشاء طلب شحن جديد بحالة pending (مع لقطة الرسوم وقت الإرسال)."""
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO payments (user_id, method_id, amount_units, transaction_reference,
                                  proof_file_id, proof_file_type, user_note, expires_at,
                                  fee_units, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, method_id, amount_units, transaction_reference, proof_file_id,
                proof_file_type, user_note, expires_at, max(0, int(fee_units)), now, now,
            ),
        )
        row = await tx.fetchone("SELECT * FROM payments WHERE id = ?", (result.lastrowid,))
        payment = Payment.from_row(row)
        assert payment is not None
        return payment

    async def update_fields(self, tx: Tx, payment_id: int, **fields: Any) -> bool:
        """تعديل حقول طلب شحن (قبل المراجعة عادةً)."""
        return await self._update_by_id(tx, "payments", payment_id, fields, _PAYMENT_FIELDS)

    async def set_status(
        self,
        tx: Tx,
        payment_id: int,
        *,
        new_status: str,
        expected_status: str = "pending",
        admin_id: int | None = None,
        credited_units: int | None = None,
        admin_note: str | None = None,
        reject_reason: str | None = None,
    ) -> bool:
        """
        تغيير حالة طلب الشحن بشكل مشروط بالحالة السابقة.

        المخرجات: True إذا تم التغيير، False إذا كانت الحالة قد تغيّرت مسبقاً
                  (أي أن أدمن آخر عالجها، أو أن الزر ضُغط مرتين).
        """
        result = await tx.execute(
            """
            UPDATE payments
               SET status = ?, admin_id = COALESCE(?, admin_id),
                   credited_units = COALESCE(?, credited_units),
                   admin_note = COALESCE(?, admin_note),
                   reject_reason = COALESCE(?, reject_reason),
                   reviewed_at = ?, updated_at = ?
             WHERE id = ? AND status = ?
            """,
            (
                new_status, admin_id, credited_units, admin_note, reject_reason,
                self.now(), self.now(), payment_id, expected_status,
            ),
        )
        return result.rowcount == 1
