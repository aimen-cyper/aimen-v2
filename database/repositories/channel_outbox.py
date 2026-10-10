"""
مستودع صندوق إرسال القنوات الإدارية (تنبيهات الإدارة + توثيق الطلبات).

نفس فكرة صندوق الإشعارات: يُكتب السجل في معاملة الحدث نفسه (طلب جديد مثلاً)، ثم يرسله job لاحقاً.
    • لا يضيع سجل عند إعادة التشغيل؛  • لا يُنشر سجل لحدث لم يُثبَّت؛  • `dedupe_key` يمنع النشر المزدوج.
"""

from __future__ import annotations

from core.constants import MAX_NOTIFICATION_ATTEMPTS, NOTIFICATION_BACKOFF
from database.database import Tx
from database.models import ChannelPost
from database.repositories.base import BaseRepository
from utils.datetime_utils import iso_plus_seconds, utc_now_iso


class ChannelOutboxRepository(BaseRepository):
    """إدراج منشورات القنوات وإدارة محاولات إرسالها."""

    async def enqueue(self, tx: Tx, *, kind: str, title: str, message: str, dedupe_key: str) -> int | None:
        """إضافة منشور؛ المخرجات: معرّفه، أو None إن كان `dedupe_key` موجوداً (لا تكرار)."""
        result = await tx.execute(
            """
            INSERT INTO channel_outbox (kind, title, message, dedupe_key, status, next_attempt_at, created_at)
            VALUES (?, ?, ?, ?, 'queued', ?, ?)
            ON CONFLICT(dedupe_key) DO NOTHING
            """,
            (kind, title, message, dedupe_key, utc_now_iso(), self.now()),
        )
        return None if result.rowcount == 0 else result.lastrowid

    async def claim_batch(self, tx: Tx, *, limit: int = 20, lease_seconds: int = 60) -> list[ChannelPost]:
        """حجز دفعة جاهزة بتأجيل موعدها فوراً (lease) حتى لا تلتقطها دورة أخرى."""
        now = utc_now_iso()
        rows = await tx.fetchall(
            """
            SELECT * FROM channel_outbox
             WHERE status = 'queued' AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
             ORDER BY id LIMIT ?
            """,
            (now, limit),
        )
        claimed: list[ChannelPost] = []
        for row in rows:
            ok = await tx.execute(
                """
                UPDATE channel_outbox SET next_attempt_at = ?
                 WHERE id = ? AND status = 'queued' AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                """,
                (iso_plus_seconds(lease_seconds), row["id"], now),
            )
            post = ChannelPost.from_row(row) if ok.rowcount == 1 else None
            if post is not None:
                claimed.append(post)
        return claimed

    async def release_claims(self, tx: Tx, ids: list[int]) -> int:
        """فكّ حجز منشورات لم يتسع لها وقت الجولة لتُلتقط في التي تليها فوراً."""
        released = 0
        for post_id in ids:
            result = await tx.execute(
                "UPDATE channel_outbox SET next_attempt_at = ? WHERE id = ? AND status = 'queued'",
                (self.now(), post_id),
            )
            released += result.rowcount
        return released

    async def mark_sent(self, tx: Tx, post_id: int) -> bool:
        """تعليم المنشور كمُرسَل (مشروط بأنه ما زال queued)."""
        result = await tx.execute(
            "UPDATE channel_outbox SET status = 'sent', sent_at = ?, last_error = NULL WHERE id = ? AND status = 'queued'",
            (self.now(), post_id),
        )
        return result.rowcount == 1

    async def mark_failed(self, tx: Tx, post_id: int, *, error: str, permanent: bool = False) -> None:
        """تسجيل فشل محاولة: تأجيل متدرج، وفشل نهائي عند تجاوز الحد أو عند `permanent`."""
        row = await tx.fetchone("SELECT attempts FROM channel_outbox WHERE id = ?", (post_id,))
        attempts = int(row["attempts"]) + 1 if row else 1
        clean = error[:300]
        if permanent or attempts >= MAX_NOTIFICATION_ATTEMPTS:
            await tx.execute(
                "UPDATE channel_outbox SET status = 'failed', attempts = ?, last_error = ? WHERE id = ?",
                (attempts, clean, post_id),
            )
            return
        delay = NOTIFICATION_BACKOFF[min(attempts - 1, len(NOTIFICATION_BACKOFF) - 1)]
        await tx.execute(
            "UPDATE channel_outbox SET attempts = ?, last_error = ?, next_attempt_at = ?, status = 'queued' WHERE id = ?",
            (attempts, clean, iso_plus_seconds(delay), post_id),
        )

    async def mark_skipped(self, tx: Tx, post_id: int, reason: str) -> None:
        """تخطي نهائي (لا قناة مضبوطة لهذا النوع)."""
        await tx.execute(
            "UPDATE channel_outbox SET status = 'skipped', last_error = ? WHERE id = ?", (reason[:300], post_id)
        )

    async def defer(self, tx: Tx, post_id: int, *, seconds: int, reason: str) -> None:
        """إبقاء المنشور في الطابور بتأجيل (لا وجهة الآن) بلا احتساب محاولة؛ السبب ظاهر لشاشة التشخيص."""
        await tx.execute(
            "UPDATE channel_outbox SET next_attempt_at = ?, last_error = ? WHERE id = ? AND status = 'queued'",
            (iso_plus_seconds(seconds), reason[:300], post_id),
        )

    async def requeue_failed(self, tx: Tx, *, kind: str | None, created_after_iso: str) -> int:
        """
        إعادة المنشورات الفاشلة/المتخطّاة (ضمن مدة الصلاحية) إلى الطابور، وإيقاظ المؤجَّلة «بانتظار الوجهة» فوراً.

        تقتصر على المنشورات الأحدث من `created_after_iso` حتى لا يُغرَق القناة بتاريخ قديم.
        """
        sql = (
            "UPDATE channel_outbox SET status = 'queued', attempts = 0, next_attempt_at = ?, last_error = NULL "
            "WHERE status IN ('failed', 'skipped') AND created_at >= ?"
        )
        params: list = [utc_now_iso(), created_after_iso]
        if kind is not None:
            sql += " AND kind = ?"
            params.append(kind)
        result = await tx.execute(sql, params)
        woken = await tx.execute(
            "UPDATE channel_outbox SET next_attempt_at = ?, last_error = NULL "
            "WHERE status = 'queued' AND last_error LIKE 'بانتظار الوجهة%'" + (" AND kind = ?" if kind else ""),
            [utc_now_iso()] + ([kind] if kind else []),
        )
        return result.rowcount + woken.rowcount

    async def reschedule(self, tx: Tx, post_id: int) -> None:
        """إعادة المنشور للطابور فوراً بلا احتساب محاولة (مثل: حد معدل مؤقت من تيليجرام)."""
        await tx.execute(
            "UPDATE channel_outbox SET next_attempt_at = ? WHERE id = ? AND status = 'queued'",
            (iso_plus_seconds(5), post_id),
        )

    async def get_by_dedupe(self, dedupe_key: str) -> ChannelPost | None:
        """جلب منشور بمفتاح التفرد (للاختبار والتشخيص)."""
        row = await self.db.fetchone("SELECT * FROM channel_outbox WHERE dedupe_key = ?", (dedupe_key,))
        return ChannelPost.from_row(row)

    async def list_recent(self, *, limit: int = 10) -> list[ChannelPost]:
        """آخر المنشورات (شاشة تشخيص القنوات)."""
        rows = await self.db.fetchall("SELECT * FROM channel_outbox ORDER BY id DESC LIMIT ?", (limit,))
        return ChannelPost.from_rows(rows)

    async def count_by_status(self) -> dict[str, int]:
        """عدد المنشورات لكل حالة."""
        rows = await self.db.fetchall("SELECT status, COUNT(*) AS n FROM channel_outbox GROUP BY status")
        return {row["status"]: int(row["n"]) for row in rows}

    async def delete_old(self, tx: Tx, before_iso: str) -> int:
        """حذف المنشورات القديمة المنتهية (التنظيف الدوري)."""
        result = await tx.execute(
            "DELETE FROM channel_outbox WHERE created_at < ? AND status IN ('sent', 'skipped', 'failed')",
            (before_iso,),
        )
        return result.rowcount
