"""
مستودع الإذاعة — الرسائل الجماعية وقوائم المستلمين.

سبب تخزين المستلمين في جدول مستقل:
    إذا أُعيد تشغيل البوت أثناء إذاعة لآلاف المستخدمين، يجب أن تُستأنف من حيث توقفت،
    وألا يستلم أحد الرسالة مرتين.
"""

from __future__ import annotations

from typing import Any, Sequence, Iterable

from database.database import Tx
from database.models import Broadcast
from database.repositories.base import BaseRepository

_BROADCAST_FIELDS = {
    "message_text",
    "parse_mode",
    "media_file_id",
    "media_type",
    "buttons_json",
    "target",
    "target_filter_json",
    "total_count",
    "sent_count",
    "failed_count",
    "blocked_count",
    "status",
    "started_at",
    "finished_at",
}


class BroadcastsRepository(BaseRepository):
    """إنشاء الإذاعات ومتابعة تقدمها."""

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        admin_id: int | None,
        message_text: str,
        target: str = "all",
        parse_mode: str | None = None,
        media_file_id: str | None = None,
        media_type: str | None = None,
        buttons_json: str | None = None,
        target_filter_json: str | None = None,
    ) -> Broadcast:
        """إنشاء إذاعة جديدة بحالة draft."""
        result = await tx.execute(
            """
            INSERT INTO broadcasts (admin_id, message_text, parse_mode, media_file_id, media_type,
                                    buttons_json, target, target_filter_json, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?)
            """,
            (
                admin_id, message_text, parse_mode, media_file_id, media_type,
                buttons_json, target, target_filter_json, self.now(),
            ),
        )
        row = await tx.fetchone("SELECT * FROM broadcasts WHERE id = ?", (result.lastrowid,))
        broadcast = Broadcast.from_row(row)
        assert broadcast is not None
        return broadcast

    async def add_recipients(self, tx: Tx, broadcast_id: int, user_ids: Iterable[int]) -> int:
        """
        إضافة قائمة المستلمين للإذاعة (تتجاهل المكرر بفضل قيد UNIQUE).

        المخرجات: عدد المستلمين المضافين فعلاً.
        """
        ids = list(user_ids)
        if not ids:
            return 0
        await tx.executemany(
            "INSERT OR IGNORE INTO broadcast_recipients (broadcast_id, user_id) VALUES (?, ?)",
            [(broadcast_id, uid) for uid in ids],
        )
        total = await self.count("broadcast_recipients", "broadcast_id = ?", (broadcast_id,))
        await tx.execute(
            "UPDATE broadcasts SET total_count = ? WHERE id = ?", (total, broadcast_id)
        )
        return total

    async def claim_recipients(self, tx: Tx, broadcast_id: int, *, limit: int = 20) -> list[dict]:
        """
        حجز دفعة من المستلمين المنتظرين للإرسال إليهم.

        الآلية: تحديث الحالة إلى sent يتم بعد الإرسال الفعلي؛ هنا نقرأ فقط دفعة صغيرة
        مرتبة (لا حجز فعلياً في القاعدة). منع الإرسال المزدوج بين جولتين متزامنتين
        مسؤولية `BroadcastService` عبر قفل الجولة (`_round_lock`)، أما التسجيل المشروط
        بـ pending في `mark_recipient` فيمنع العدّ المزدوج فقط. الضمان: at-least-once —
        انهيار العملية بين الإرسال والتسجيل قد يعيد إرسال رسالة واحدة لمستلم واحد.
        """
        rows = await tx.fetchall(
            """
            SELECT r.id, r.user_id, u.telegram_id
              FROM broadcast_recipients r
              JOIN users u ON u.id = r.user_id
             WHERE r.broadcast_id = ? AND r.status = 'pending'
             ORDER BY r.id LIMIT ?
            """,
            (broadcast_id, limit),
        )
        return [dict(row) for row in rows]

    async def mark_recipient(
        self, tx: Tx, recipient_id: int, *, status: str, error: str | None = None
    ) -> bool:
        """
        تسجيل نتيجة الإرسال لمستلم واحد (مشروط بأن حالته ما زالت pending).

        المخرجات: True إذا سُجِّلت النتيجة الآن (يمنع العدّ المزدوج).
        """
        result = await tx.execute(
            """
            UPDATE broadcast_recipients SET status = ?, error = ?, sent_at = ?
             WHERE id = ? AND status = 'pending'
            """,
            (status, error[:200] if error else None, self.now(), recipient_id),
        )
        if result.rowcount != 1:
            return False

        column = {"sent": "sent_count", "failed": "failed_count", "blocked": "blocked_count"}.get(status)
        if column:
            broadcast_id = await tx.fetchval(
                "SELECT broadcast_id FROM broadcast_recipients WHERE id = ?", (recipient_id,)
            )
            await tx.execute(
                f"UPDATE broadcasts SET {column} = {column} + 1 WHERE id = ?", (broadcast_id,)
            )
        return True

    async def set_status(
        self,
        tx: Tx,
        broadcast_id: int,
        status: str,
        *,
        expected_statuses: Sequence[str] | None = None,
        **fields: Any,
    ) -> bool:
        """
        تغيير حالة الإذاعة (running/paused/completed/cancelled) بشرط ذرّي على الحالة السابقة.

        `expected_statuses`: الحالات التي يجوز الانتقال منها؛ يُنفَّذ الشرط داخل جملة UPDATE نفسها فلا يطغى
        قرارٌ قديم (قرأه المستدعي قبل لحظة) على قرار أحدث: إيقاف/إلغاء متزامنان مع الإكمال أو البدء.

        المخرجات: True إن تغيّرت الحالة فعلاً، False إن لم تكن الحالة الحالية ضمن المتوقعة.
        """
        data = {"status": status, **fields}
        set_sql, values = self._build_update(data, _BROADCAST_FIELDS)
        where = "id = ?"
        values.append(broadcast_id)
        if expected_statuses:
            where += f" AND status IN ({','.join('?' for _ in expected_statuses)})"
            values.extend(str(item) for item in expected_statuses)
        result = await tx.execute(f"UPDATE broadcasts SET {set_sql} WHERE {where}", values)
        return result.rowcount > 0

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, broadcast_id: int) -> Broadcast | None:
        """جلب إذاعة بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM broadcasts WHERE id = ?", (broadcast_id,))
        return Broadcast.from_row(row)

    async def list_recent(self, *, limit: int = 10) -> list[Broadcast]:
        """آخر الإذاعات."""
        rows = await self.db.fetchall("SELECT * FROM broadcasts ORDER BY id DESC LIMIT ?", (limit,))
        return Broadcast.from_rows(rows)

    async def list_running(self) -> list[Broadcast]:
        """الإذاعات الجارية (تُستأنف عند إقلاع البوت)."""
        rows = await self.db.fetchall("SELECT * FROM broadcasts WHERE status = 'running' ORDER BY id")
        return Broadcast.from_rows(rows)

    async def pending_count(self, broadcast_id: int) -> int:
        """عدد المستلمين المتبقين في إذاعة."""
        return await self.count(
            "broadcast_recipients", "broadcast_id = ? AND status = 'pending'", (broadcast_id,)
        )
