"""مستودع الدعم الفني — التذاكر ورسائلها."""

from __future__ import annotations

from typing import Any, Sequence

from database.database import Tx
from database.models import SupportMessage, SupportTicket
from database.repositories.base import BaseRepository

_TICKET_FIELDS = {
    "subject",
    "category",
    "related_order_id",
    "status",
    "priority",
    "assigned_admin",
    "last_message_at",
    "closed_by",
    "close_reason",
    "closed_at",
}


class TicketsRepository(BaseRepository):
    """عمليات التذاكر ورسائل الدعم."""

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, ticket_id: int) -> SupportTicket | None:
        """جلب تذكرة بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM support_tickets WHERE id = ?", (ticket_id,))
        return SupportTicket.from_row(row)

    async def list_by_user(self, user_id: int, *, limit: int = 10, offset: int = 0) -> list[SupportTicket]:
        """تذاكر مستخدم معين."""
        rows = await self.db.fetchall(
            "SELECT * FROM support_tickets WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
        return SupportTicket.from_rows(rows)

    async def list_by_status(
        self,
        statuses: Sequence[str],
        *,
        assigned_admin: int | None = None,
        priority: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[SupportTicket]:
        """
        التذاكر حسب الحالة (للوحة الدعم).

        المدخلات:
            statuses       : الحالات المطلوبة.
            assigned_admin : حصر النتائج بالتذاكر المسندة لأدمن بعينه (تبويب «المسندة لي»).
            priority       : حصر النتائج بأولوية بعينها (تبويب «العاجلة»).
        """
        where, params = self._status_filter(statuses, assigned_admin, priority)
        rows = await self.db.fetchall(
            f"""
            SELECT * FROM support_tickets WHERE {where}
             ORDER BY COALESCE(last_message_at, created_at) DESC LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        )
        return SupportTicket.from_rows(rows)

    async def count_by_status(
        self,
        statuses: Sequence[str],
        *,
        assigned_admin: int | None = None,
        priority: str | None = None,
    ) -> int:
        """عدد التذاكر المطابقة لنفس مرشّحات `list_by_status` (لحساب عدد الصفحات)."""
        where, params = self._status_filter(statuses, assigned_admin, priority)
        return await self.count("support_tickets", where, tuple(params))

    @staticmethod
    def _status_filter(
        statuses: Sequence[str], assigned_admin: int | None, priority: str | None = None
    ) -> tuple[str, list[Any]]:
        """بناء شرط WHERE المشترك بين قائمة التذاكر وعدّادها."""
        clauses: list[str] = []
        params: list[Any] = []
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(statuses)
        else:
            clauses.append("1 = 1")
        if assigned_admin is not None:
            clauses.append("assigned_admin = ?")
            params.append(assigned_admin)
        if priority is not None:
            clauses.append("priority = ?")
            params.append(priority)
        return " AND ".join(clauses), params

    async def list_idle(
        self, *, statuses: Sequence[str], before_iso: str, limit: int = 50
    ) -> list[SupportTicket]:
        """
        التذاكر الراكدة: لم تصلها رسالة منذ تاريخ معيّن (للإغلاق التلقائي).

        المدخلات:
            statuses   : الحالات المستهدفة (عادةً pending_user).
            before_iso : أقدم وقت مقبول لآخر رسالة.
        """
        placeholders = ", ".join("?" for _ in statuses)
        rows = await self.db.fetchall(
            f"""
            SELECT * FROM support_tickets
             WHERE status IN ({placeholders})
               AND COALESCE(last_message_at, created_at) <= ?
             ORDER BY id LIMIT ?
            """,
            [*statuses, before_iso, limit],
        )
        return SupportTicket.from_rows(rows)

    async def count_open(self) -> int:
        """عدد التذاكر غير المغلقة."""
        return await self.count("support_tickets", "status != 'closed'")

    async def count_today_by_user(self, user_id: int, since_iso: str) -> int:
        """عدد تذاكر المستخدم اليوم (لتطبيق الحد اليومي ومنع الإزعاج)."""
        return await self.count(
            "support_tickets", "user_id = ? AND created_at >= ?", (user_id, since_iso)
        )

    async def messages(self, ticket_id: int, *, limit: int = 50) -> list[SupportMessage]:
        """رسائل تذكرة مرتبة زمنياً."""
        rows = await self.db.fetchall(
            "SELECT * FROM support_messages WHERE ticket_id = ? ORDER BY id LIMIT ?",
            (ticket_id, limit),
        )
        return SupportMessage.from_rows(rows)

    async def has_open_ticket(self, user_id: int) -> bool:
        """هل لدى المستخدم تذكرة مفتوحة حالياً؟ (لتوجيهه إليها بدل فتح تذكرة جديدة)."""
        row = await self.db.fetchone(
            "SELECT 1 FROM support_tickets WHERE user_id = ? AND status != 'closed' LIMIT 1",
            (user_id,),
        )
        return row is not None

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        user_id: int,
        subject: str,
        category: str = "other",
        related_order_id: int | None = None,
        priority: str = "normal",
    ) -> SupportTicket:
        """إنشاء تذكرة جديدة بحالة open."""
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO support_tickets (user_id, subject, category, related_order_id, priority,
                                         status, last_message_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?)
            """,
            (user_id, subject, category, related_order_id, priority, now, now, now),
        )
        row = await tx.fetchone("SELECT * FROM support_tickets WHERE id = ?", (result.lastrowid,))
        ticket = SupportTicket.from_row(row)
        assert ticket is not None
        return ticket

    async def add_message(
        self,
        tx: Tx,
        *,
        ticket_id: int,
        sender_type: str,
        message: str,
        sender_id: int | None = None,
        attachment_file_id: str | None = None,
        attachment_type: str | None = None,
        telegram_message_id: int | None = None,
    ) -> SupportMessage:
        """
        إضافة رسالة إلى تذكرة وتحديث وقت آخر رسالة وحالة التذكرة.

        المنطق: رسالة المستخدم تجعل التذكرة بانتظار رد الأدمن، والعكس صحيح.
        """
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO support_messages (ticket_id, sender_id, sender_type, message,
                                          attachment_file_id, attachment_type, telegram_message_id,
                                          is_read_by_user, is_read_by_admin, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket_id, sender_id, sender_type, message, attachment_file_id, attachment_type,
                telegram_message_id,
                1 if sender_type == "user" else 0,
                1 if sender_type in {"admin", "system"} else 0,
                now,
            ),
        )
        new_status = "pending_admin" if sender_type == "user" else "pending_user"
        await tx.execute(
            """
            UPDATE support_tickets
               SET last_message_at = ?, updated_at = ?,
                   status = CASE WHEN status = 'closed' THEN status ELSE ? END
             WHERE id = ?
            """,
            (now, now, new_status, ticket_id),
        )
        row = await tx.fetchone("SELECT * FROM support_messages WHERE id = ?", (result.lastrowid,))
        support_message = SupportMessage.from_row(row)
        assert support_message is not None
        return support_message

    async def update_fields(self, tx: Tx, ticket_id: int, **fields: Any) -> bool:
        """تعديل حقول التذكرة (الأولوية، الإسناد ...)."""
        return await self._update_by_id(tx, "support_tickets", ticket_id, fields, _TICKET_FIELDS)

    async def assign(self, tx: Tx, ticket_id: int, admin_id: int) -> bool:
        """إسناد التذكرة إلى أدمن معين."""
        return await self._update_by_id(
            tx, "support_tickets", ticket_id, {"assigned_admin": admin_id}, _TICKET_FIELDS
        )

    async def close(self, tx: Tx, ticket_id: int, *, closed_by: int | None, reason: str | None = None) -> bool:
        """
        إغلاق التذكرة (مشروط بأن تكون مفتوحة) — لمنع الإغلاق المزدوج.
        """
        result = await tx.execute(
            """
            UPDATE support_tickets
               SET status = 'closed', closed_by = ?, close_reason = ?, closed_at = ?, updated_at = ?
             WHERE id = ? AND status != 'closed'
            """,
            (closed_by, reason, self.now(), self.now(), ticket_id),
        )
        return result.rowcount == 1

    async def reopen(self, tx: Tx, ticket_id: int) -> bool:
        """إعادة فتح تذكرة مغلقة."""
        result = await tx.execute(
            """
            UPDATE support_tickets
               SET status = 'pending_admin', closed_by = NULL, closed_at = NULL, updated_at = ?
             WHERE id = ? AND status = 'closed'
            """,
            (self.now(), ticket_id),
        )
        return result.rowcount == 1

    async def mark_read(self, tx: Tx, ticket_id: int, *, by_admin: bool) -> None:
        """تعليم رسائل التذكرة كمقروءة من طرف الأدمن أو المستخدم."""
        column = "is_read_by_admin" if by_admin else "is_read_by_user"
        await tx.execute(
            f"UPDATE support_messages SET {column} = 1 WHERE ticket_id = ?", (ticket_id,)
        )
