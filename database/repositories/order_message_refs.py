"""
مستودع مراجع رسائل الطلبات (`order_message_refs`): أي رسالة تيليجرام تعرض حالة طلب وقابلة للتعديل لاحقاً.

المبدأ: **حالة الطلب في `orders` هي المصدر**؛ هذا الجدول مجرد «أين عرضنا الحالة وبأي نسخة». فشل تعديل رسالة
يزيد `fail_count` هنا فقط ولا يلمس `orders`.
"""

from __future__ import annotations

from database.database import Tx
from database.models import Order, OrderMessageRef
from database.repositories.base import BaseRepository
from utils.datetime_utils import iso_plus_seconds, utc_now_iso

#: أنواع المراجع (تطابق CHECK في الترحيل 0013)
KIND_USER_CONFIRM = "user_confirm"
KIND_USER_NOTICE = "user_notice"
KIND_CHANNEL_POST = "channel_post"

#: بعد هذا العدد من الإخفاقات المتتالية يتوقف تعديل المرجع (يحتاج تدخلاً/تغيير وجهة)
MAX_REFRESH_FAILS = 5


def order_state_key(order: Order) -> str:
    """
    مفتاح «حالة الطلب كما تُعرض»: الحالة + المتبقي + المسترجع.

    يُطابَق حرفياً مع تعبير SQL في `list_stale` — أي تعديل هنا يلزمه تعديل هناك.
    """
    remains = order.remains if order.remains is not None else -1
    return f"{order.status}|{remains}|{int(order.refund_amount_units or 0)}"


class OrderMessageRefsRepository(BaseRepository):
    """تسجيل المراجع واختيار المتأخر منها عن حالة الطلب."""

    async def upsert(self, tx: Tx, *, order: Order, kind: str, chat_id: int | str, message_id: int) -> None:
        """تسجيل (أو استبدال) مرجع النوع للطلب؛ المفتاح المعروض = حالة الطلب الآن."""
        now = self.now()
        await tx.execute(
            """
            INSERT INTO order_message_refs
                (order_id, kind, chat_id, message_id, rendered_status, rendered_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(order_id, kind) DO UPDATE SET
                chat_id = excluded.chat_id, message_id = excluded.message_id,
                rendered_status = excluded.rendered_status, rendered_hash = excluded.rendered_hash,
                fail_count = 0, next_try_at = NULL, is_dead = 0, last_error = NULL, updated_at = excluded.updated_at
            """,
            (order.id, kind, str(chat_id), int(message_id), order.status, order_state_key(order), now, now),
        )

    async def list_stale(self, *, limit: int = 15) -> list[OrderMessageRef]:
        """مراجع حية موعدها حلّ ومفتاحها المعروض ≠ حالة الطلب الحالية."""
        rows = await self.db.fetchall(
            """
            SELECT r.* FROM order_message_refs r
              JOIN orders o ON o.id = r.order_id
             WHERE r.is_dead = 0
               AND (r.next_try_at IS NULL OR r.next_try_at <= ?)
               AND COALESCE(r.rendered_hash, '') <>
                   (o.status || '|' || COALESCE(o.remains, -1) || '|' || o.refund_amount_units)
             ORDER BY r.updated_at, r.id
             LIMIT ?
            """,
            (utc_now_iso(), limit),
        )
        return OrderMessageRef.from_rows(rows)

    async def get(self, order_id: int, kind: str) -> OrderMessageRef | None:
        """جلب مرجع بنوعه (للاختبار والتشخيص)."""
        row = await self.db.fetchone(
            "SELECT * FROM order_message_refs WHERE order_id = ? AND kind = ?", (order_id, kind)
        )
        return OrderMessageRef.from_row(row)

    async def mark_rendered(self, tx: Tx, ref_id: int, *, order: Order) -> None:
        """نجح التعديل (أو لم يكن به جديد): المفتاح المعروض = حالة الطلب الآن، وتُصفَّر الإخفاقات."""
        await tx.execute(
            """
            UPDATE order_message_refs
               SET rendered_status = ?, rendered_hash = ?, fail_count = 0, next_try_at = NULL,
                   last_error = NULL, updated_at = ?
             WHERE id = ?
            """,
            (order.status, order_state_key(order), self.now(), ref_id),
        )

    async def mark_failed(self, tx: Tx, ref_id: int, *, error: str, retry_seconds: int, dead: bool = False) -> None:
        """فشل تعديل: عدّاد + تأجيل متدرج؛ `dead` (أو تجاوز الحد) يوقف المرجع."""
        row = await tx.fetchone("SELECT fail_count FROM order_message_refs WHERE id = ?", (ref_id,))
        fails = (int(row["fail_count"]) if row else 0) + 1
        is_dead = 1 if (dead or fails >= MAX_REFRESH_FAILS) else 0
        await tx.execute(
            """
            UPDATE order_message_refs
               SET fail_count = ?, last_error = ?, next_try_at = ?, is_dead = ?, updated_at = ?
             WHERE id = ?
            """,
            (fails, error[:300], iso_plus_seconds(retry_seconds * fails), is_dead, self.now(), ref_id),
        )

    async def list_live_user_keys(self) -> set[tuple[str, int]]:
        """مفاتيح (chat_id, message_id) لمراجع المستخدم الحية — لتحرير رسالة صارت تعرض شاشة أخرى."""
        rows = await self.db.fetchall(
            "SELECT chat_id, message_id FROM order_message_refs WHERE is_dead = 0 AND kind IN (?, ?)",
            (KIND_USER_CONFIRM, KIND_USER_NOTICE),
        )
        return {(row["chat_id"], int(row["message_id"])) for row in rows}

    async def kill_message(self, tx: Tx, chat_id: int | str, message_id: int) -> int:
        """إيقاف مراجع رسالة لم تعد تعرض بطاقة الطلب (المستخدم تنقّل فيها إلى شاشة أخرى)."""
        result = await tx.execute(
            """
            UPDATE order_message_refs SET is_dead = 1, last_error = 'user navigated', updated_at = ?
             WHERE chat_id = ? AND message_id = ? AND is_dead = 0 AND kind IN (?, ?)
            """,
            (self.now(), str(chat_id), int(message_id), KIND_USER_CONFIRM, KIND_USER_NOTICE),
        )
        return result.rowcount

    async def count_by_state(self) -> dict[str, int]:
        """عدد المراجع الحية/الميتة (صحة النظام)."""
        rows = await self.db.fetchall(
            "SELECT is_dead, COUNT(*) AS n FROM order_message_refs GROUP BY is_dead"
        )
        return {("dead" if row["is_dead"] else "live"): int(row["n"]) for row in rows}
