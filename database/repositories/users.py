"""
مستودع المستخدمين — كل عبارات SQL الخاصة بجدول users.

مهم: هذا المستودع يوفّر العمليات الذرّية على الرصيد (try_debit / credit)،
لكن لا يجوز استدعاؤها إلا من WalletService (المرحلة 2) لضمان تسجيل كل حركة مالية.
"""

from __future__ import annotations

from typing import Any

from database.database import Tx
from database.models import User
from database.repositories.base import BaseRepository

#: الأعمدة المسموح تعديلها عبر update_fields
_ALLOWED_FIELDS = {
    "username",
    "first_name",
    "last_name",
    "role",
    "is_banned",
    "ban_reason",
    "banned_at",
    "blocked_bot",
    "language",
    "notes",
    "last_activity",
    "referrer_id",
}


class UsersRepository(BaseRepository):
    """عمليات قراءة وكتابة بيانات المستخدمين."""

    # ------------------------------ القراءة ------------------------------ #

    async def get_by_id(self, user_id: int) -> User | None:
        """جلب مستخدم بالمعرف الداخلي."""
        row = await self.db.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))
        return User.from_row(row)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        """جلب مستخدم بمعرف تيليجرام."""
        row = await self.db.fetchone("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        return User.from_row(row)

    async def get_balance_units(self, user_id: int) -> int:
        """قراءة الرصيد الحالي بالنقاط (0 إذا لم يوجد المستخدم)."""
        return int(await self.db.fetchval(
            "SELECT balance_units FROM users WHERE id = ?", (user_id,), default=0
        ))

    async def search(self, query: str, limit: int = 10, offset: int = 0) -> list[User]:
        """
        البحث عن مستخدم بالمعرف الرقمي أو باسم المستخدم أو الاسم الأول.

        المدخلات: query نص البحث (يقبل «@name» أو رقم تيليجرام أو جزء من الاسم).
        """
        text = query.strip().lstrip("@")
        if text.isdigit():
            rows = await self.db.fetchall(
                "SELECT * FROM users WHERE telegram_id = ? OR id = ? LIMIT ? OFFSET ?",
                (int(text), int(text), limit, offset),
            )
        else:
            pattern = f"%{text}%"
            rows = await self.db.fetchall(
                "SELECT * FROM users WHERE username LIKE ? OR first_name LIKE ? "
                "ORDER BY last_activity DESC LIMIT ? OFFSET ?",
                (pattern, pattern, limit, offset),
            )
        return User.from_rows(rows)

    async def list_by_role(self, role: str) -> list[User]:
        """كل المستخدمين الذين يحملون دوراً معيناً (لإشعارات الأدمن مثلاً)."""
        rows = await self.db.fetchall("SELECT * FROM users WHERE role = ? ORDER BY id", (role,))
        return User.from_rows(rows)

    async def list_recent(self, limit: int = 10, offset: int = 0) -> list[User]:
        """آخر المستخدمين المسجلين."""
        rows = await self.db.fetchall(
            "SELECT * FROM users ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        return User.from_rows(rows)

    async def count_all(self) -> int:
        """إجمالي عدد المستخدمين."""
        return await self.count("users")

    async def count_since(self, since_iso: str) -> int:
        """عدد المستخدمين الجدد منذ وقت معين."""
        return await self.count("users", "created_at >= ?", (since_iso,))

    async def count_between(self, start_iso: str, end_iso: str) -> int:
        """عدد المستخدمين المسجَّلين بين وقتين (بداية شاملة، نهاية حصرية)."""
        return await self.count("users", "created_at >= ? AND created_at < ?", (start_iso, end_iso))

    async def count_active_since(self, since_iso: str) -> int:
        """عدد المستخدمين النشطين منذ وقت معين."""
        return await self.count("users", "last_activity >= ?", (since_iso,))

    async def total_balance_units(self) -> int:
        """
        مجموع أرصدة كل المستخدمين (التزام مالي على النظام تجاه العملاء).
        """
        return int(
            await self.db.fetchval("SELECT COALESCE(SUM(balance_units), 0) FROM users", default=0)
        )

    async def top_spenders(self, *, limit: int = 5) -> list[User]:
        """أكثر المستخدمين إنفاقاً (لتقرير الأدمن)."""
        rows = await self.db.fetchall(
            "SELECT * FROM users WHERE total_spent_units > 0 ORDER BY total_spent_units DESC LIMIT ?",
            (limit,),
        )
        return User.from_rows(rows)

    async def count_banned(self) -> int:
        """عدد المستخدمين المحظورين."""
        return await self.count("users", "is_banned = 1")

    async def telegram_ids_for_broadcast(
        self, *, only_active_since: str | None = None, with_orders: bool = False
    ) -> list[int]:
        """
        قائمة معرفات تيليجرام المستهدفة بالإذاعة (تستثني المحظورين ومن حظر البوت).

        المدخلات:
            only_active_since : اقتصار على من كان نشطاً بعد هذا الوقت.
            with_orders       : اقتصار على من لديه طلب واحد على الأقل.
        """
        sql = ["SELECT DISTINCT u.telegram_id FROM users u"]
        params: list[Any] = []
        if with_orders:
            sql.append("JOIN orders o ON o.user_id = u.id")
        sql.append("WHERE u.is_banned = 0 AND u.blocked_bot = 0")
        if only_active_since:
            sql.append("AND u.last_activity >= ?")
            params.append(only_active_since)
        rows = await self.db.fetchall(" ".join(sql), params)
        return [int(row["telegram_id"]) for row in rows]

    async def ids_for_broadcast(self, *, target: str, since_iso: str | None = None) -> list[int]:
        """
        معرفات المستخدمين الداخلية لشريحة إذاعة (المرحلة 8).

        المدخلات:
            target    : all | active | buyers | no_orders.
            since_iso : بداية نافذة النشاط لشريحة «النشطون».

        المخرجات: قائمة معرفات مرتبة، بلا محظورين وبلا من حظر البوت.

        ملاحظة: نُرجع المعرف الداخلي لا معرف تيليجرام، لأن صفوف المستلمين
        ترتبط بجدول users ويجب أن تبقى صالحة حتى لو تغيّر حساب تيليجرام.
        """
        sql = ["SELECT DISTINCT u.id FROM users u"]
        params: list[Any] = []
        if target == "buyers":
            sql.append("JOIN orders o ON o.user_id = u.id")
        elif target == "no_orders":
            sql.append("LEFT JOIN orders o ON o.user_id = u.id")
        sql.append("WHERE u.is_banned = 0 AND u.blocked_bot = 0")
        if target == "no_orders":
            sql.append("AND o.id IS NULL")
        if target == "active":
            sql.append("AND u.last_activity >= ?")
            params.append(since_iso or "")
        sql.append("ORDER BY u.id")
        rows = await self.db.fetchall(" ".join(sql), params)
        return [int(row["id"]) for row in rows]

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        language: str = "ar",
        role: str = "user",
        referrer_id: int | None = None,
    ) -> User:
        """
        إنشاء مستخدم جديد برصيد صفر.

        المخرجات: كائن المستخدم بعد الإنشاء.
        """
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO users (telegram_id, username, first_name, last_name, language, role,
                               referrer_id, created_at, updated_at, last_activity)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (telegram_id, username, first_name, last_name, language, role, referrer_id, now, now, now),
        )
        row = await tx.fetchone("SELECT * FROM users WHERE id = ?", (result.lastrowid,))
        user = User.from_row(row)
        assert user is not None
        return user

    async def update_fields(self, tx: Tx, user_id: int, **fields: Any) -> bool:
        """تعديل حقول مسموح بها للمستخدم (لا تشمل الرصيد إطلاقاً)."""
        return await self._update_by_id(tx, "users", user_id, fields, _ALLOWED_FIELDS)

    async def update_profile(
        self,
        tx: Tx,
        user_id: int,
        *,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
    ) -> bool:
        """تحديث بيانات الملف الشخصي القادمة من تيليجرام عند كل تفاعل."""
        return await self._update_by_id(
            tx,
            "users",
            user_id,
            {
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "last_activity": self.now(),
            },
            _ALLOWED_FIELDS,
        )

    async def touch_activity(self, tx: Tx, user_id: int) -> None:
        """تحديث وقت آخر نشاط للمستخدم."""
        now = self.now()
        await tx.execute(
            "UPDATE users SET last_activity = ?, updated_at = ? WHERE id = ?", (now, now, user_id)
        )

    async def set_ban(self, tx: Tx, user_id: int, *, banned: bool, reason: str | None = None) -> bool:
        """حظر مستخدم أو فك حظره مع تسجيل السبب ووقت الحظر."""
        return await self._update_by_id(
            tx,
            "users",
            user_id,
            {
                "is_banned": 1 if banned else 0,
                "ban_reason": reason if banned else None,
                "banned_at": self.now() if banned else None,
            },
            _ALLOWED_FIELDS,
        )

    async def set_role(self, tx: Tx, user_id: int, role: str) -> bool:
        """تغيير دور المستخدم (عملية حساسة تتطلب تسجيلاً في Audit Log)."""
        return await self._update_by_id(tx, "users", user_id, {"role": role}, _ALLOWED_FIELDS)

    async def set_blocked_bot(self, tx: Tx, user_id: int, blocked: bool) -> bool:
        """تعليم أن المستخدم حظر البوت (يُكتشف عند فشل إرسال إشعار)."""
        return await self._update_by_id(
            tx, "users", user_id, {"blocked_bot": 1 if blocked else 0}, _ALLOWED_FIELDS
        )

    # --------------------------- عمليات الرصيد ---------------------------- #
    # ⚠️ تُستدعى حصراً من WalletService مع تسجيل حركة مالية في نفس المعاملة.

    async def try_debit(self, tx: Tx, user_id: int, amount_units: int) -> bool:
        """
        خصم مبلغ من الرصيد بشكل ذرّي دون إمكانية أن يصبح الرصيد سالباً.

        الآلية: UPDATE مشروط برصيد كافٍ؛ إذا لم يتأثر أي صف فالرصيد غير كافٍ.

        المخرجات: True إذا تم الخصم، False إذا كان الرصيد غير كافٍ أو المستخدم غير موجود.
        """
        if amount_units <= 0:
            raise ValueError("مبلغ الخصم يجب أن يكون أكبر من صفر.")
        result = await tx.execute(
            """
            UPDATE users
               SET balance_units = balance_units - ?,
                   total_spent_units = total_spent_units + ?,
                   updated_at = ?
             WHERE id = ? AND balance_units >= ?
            """,
            (amount_units, amount_units, self.now(), user_id, amount_units),
        )
        return result.rowcount == 1

    async def credit(self, tx: Tx, user_id: int, amount_units: int, *, count_as_deposit: bool = False) -> bool:
        """
        إضافة مبلغ إلى رصيد المستخدم.

        المدخلات:
            count_as_deposit : احتساب المبلغ ضمن إجمالي الإيداعات (يُستخدم عند اعتماد الشحن فقط).
        """
        if amount_units <= 0:
            raise ValueError("مبلغ الإضافة يجب أن يكون أكبر من صفر.")
        result = await tx.execute(
            """
            UPDATE users
               SET balance_units = balance_units + ?,
                   total_deposited_units = total_deposited_units + ?,
                   updated_at = ?
             WHERE id = ?
            """,
            (amount_units, amount_units if count_as_deposit else 0, self.now(), user_id),
        )
        return result.rowcount == 1

    async def refund_spent(self, tx: Tx, user_id: int, amount_units: int) -> bool:
        """
        إعادة مبلغ إلى الرصيد مع تخفيض إجمالي الإنفاق (يُستخدم عند الاسترجاع).

        ملاحظة: إجمالي الإنفاق لا يُسمح بأن يصبح سالباً.
        """
        if amount_units <= 0:
            raise ValueError("مبلغ الاسترجاع يجب أن يكون أكبر من صفر.")
        result = await tx.execute(
            """
            UPDATE users
               SET balance_units = balance_units + ?,
                   total_spent_units = MAX(0, total_spent_units - ?),
                   updated_at = ?
             WHERE id = ?
            """,
            (amount_units, amount_units, self.now(), user_id),
        )
        return result.rowcount == 1
