"""
مستودع الإشعارات — يعمل بنمط صندوق الإرسال (Outbox).

الفكرة:
    الإشعار يُكتب في نفس معاملة الحدث (تغيّر حالة طلب مثلاً)، ثم يرسله job منفصل.
    النتيجة:
        • لا يضيع إشعار عند إعادة تشغيل البوت (محفوظ في قاعدة البيانات).
        • لا يُرسل إشعار عن حدث لم يُثبَّت (نفس المعاملة).
        • لا يتكرر الإشعار (dedupe_key فريد).
"""

from __future__ import annotations

from core.constants import MAX_NOTIFICATION_ATTEMPTS, NOTIFICATION_BACKOFF
from database.database import Tx
from database.models import Notification
from database.repositories.base import BaseRepository
from utils.datetime_utils import iso_plus_seconds, utc_now_iso


class NotificationsRepository(BaseRepository):
    """إدراج الإشعارات في الصندوق وإدارة محاولات إرسالها."""

    # ------------------------------ الكتابة ------------------------------ #

    async def enqueue(
        self,
        tx: Tx,
        *,
        user_id: int,
        type: str,
        message: str,
        dedupe_key: str,
        title: str = "",
        payload_json: str | None = None,
    ) -> int | None:
        """
        إضافة إشعار إلى صندوق الإرسال.

        المدخلات:
            dedupe_key : مفتاح فريد يمنع تكرار نفس الإشعار (مثل "order:12:completed").

        المخرجات: معرف الإشعار الجديد، أو None إذا كان الإشعار موجوداً مسبقاً
                  (وهذا سلوك صحيح وليس خطأ).
        """
        result = await tx.execute(
            """
            INSERT INTO notifications (user_id, type, title, message, payload_json, dedupe_key,
                                       status, next_attempt_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?)
            ON CONFLICT(dedupe_key) DO NOTHING
            """,
            (user_id, type, title, message, payload_json, dedupe_key, utc_now_iso(), self.now()),
        )
        if result.rowcount == 0:
            return None
        return result.lastrowid

    async def claim_batch(self, tx: Tx, *, limit: int = 25, lease_seconds: int = 60) -> list[Notification]:
        """
        حجز دفعة من الإشعارات الجاهزة للإرسال.

        الآلية: تأجيل موعد المحاولة التالية فوراً (lease) حتى لا تلتقطها دورة أخرى
        قبل أن تنتهي الدورة الحالية من الإرسال.
        """
        now = utc_now_iso()
        rows = await tx.fetchall(
            """
            SELECT * FROM notifications
             WHERE status = 'queued' AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
             ORDER BY id LIMIT ?
            """,
            (now, limit),
        )
        claimed: list[Notification] = []
        for row in rows:
            ok = await tx.execute(
                """
                UPDATE notifications SET next_attempt_at = ?
                 WHERE id = ? AND status = 'queued'
                   AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                """,
                (iso_plus_seconds(lease_seconds), row["id"], now),
            )
            if ok.rowcount == 1:
                notification = Notification.from_row(row)
                if notification is not None:
                    claimed.append(notification)
        return claimed

    async def release_claims(self, tx: Tx, ids: list[int]) -> int:
        """فكّ حجز إشعارات لم يتسع لها وقت الجولة لتُلتقط في التي تليها فوراً (لا تنتظر انتهاء الـlease)."""
        released = 0
        for notification_id in ids:
            result = await tx.execute(
                "UPDATE notifications SET next_attempt_at = ? WHERE id = ? AND status = 'queued'",
                (self.now(), notification_id),
            )
            released += result.rowcount
        return released

    async def mark_sent(self, tx: Tx, notification_id: int, telegram_message_id: int | None = None) -> bool:
        """تعليم الإشعار كمُرسل (مشروط بأن يكون ما زال في حالة queued)."""
        result = await tx.execute(
            """
            UPDATE notifications
               SET status = 'sent', sent_at = ?, telegram_message_id = ?, last_error = NULL
             WHERE id = ? AND status = 'queued'
            """,
            (self.now(), telegram_message_id, notification_id),
        )
        return result.rowcount == 1

    async def mark_failed(
        self, tx: Tx, notification_id: int, *, error: str, permanent: bool = False
    ) -> None:
        """
        تسجيل فشل محاولة إرسال.

        المدخلات:
            permanent : True يعني لا فائدة من إعادة المحاولة (مثل: الدردشة غير موجودة).

        المنطق: مع كل فشل يزيد العداد ويُؤجَّل الموعد بتدرج، وعند تجاوز الحد
                يُعلَّم الإشعار كفاشل نهائياً ويُسجَّل السبب.
        """
        row = await tx.fetchone("SELECT attempts FROM notifications WHERE id = ?", (notification_id,))
        attempts = int(row["attempts"]) + 1 if row else 1
        clean_error = error[:300]

        if permanent or attempts >= MAX_NOTIFICATION_ATTEMPTS:
            await tx.execute(
                "UPDATE notifications SET status = 'failed', attempts = ?, last_error = ? WHERE id = ?",
                (attempts, clean_error, notification_id),
            )
            return

        delay = NOTIFICATION_BACKOFF[min(attempts - 1, len(NOTIFICATION_BACKOFF) - 1)]
        await tx.execute(
            """
            UPDATE notifications
               SET attempts = ?, last_error = ?, next_attempt_at = ?, status = 'queued'
             WHERE id = ?
            """,
            (attempts, clean_error, iso_plus_seconds(delay), notification_id),
        )

    async def mark_skipped(self, tx: Tx, notification_id: int, reason: str) -> None:
        """تخطي الإشعار نهائياً (مثلاً لأن المستخدم حظر البوت)."""
        await tx.execute(
            "UPDATE notifications SET status = 'skipped', last_error = ? WHERE id = ?",
            (reason[:300], notification_id),
        )

    async def mark_read_for_user(self, tx: Tx, user_id: int) -> int:
        """تعليم كل إشعارات المستخدم كمقروءة عند فتحه شاشة الإشعارات."""
        result = await tx.execute(
            "UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0", (user_id,)
        )
        return result.rowcount

    async def delete_old(self, tx: Tx, before_iso: str) -> int:
        """حذف الإشعارات القديمة المرسلة (مهمة التنظيف الدورية)."""
        result = await tx.execute(
            "DELETE FROM notifications WHERE created_at < ? AND status IN ('sent', 'skipped', 'failed')",
            (before_iso,),
        )
        return result.rowcount

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, notification_id: int) -> Notification | None:
        """جلب إشعار بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM notifications WHERE id = ?", (notification_id,))
        return Notification.from_row(row)

    async def exists(self, dedupe_key: str) -> bool:
        """هل سبق إنشاء إشعار بهذا المفتاح؟"""
        row = await self.db.fetchone("SELECT 1 FROM notifications WHERE dedupe_key = ?", (dedupe_key,))
        return row is not None

    async def list_for_user(self, user_id: int, *, limit: int = 10, offset: int = 0) -> list[Notification]:
        """آخر إشعارات المستخدم لعرضها داخل «حسابي»."""
        rows = await self.db.fetchall(
            "SELECT * FROM notifications WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
        return Notification.from_rows(rows)

    async def count_unread(self, user_id: int) -> int:
        """عدد الإشعارات غير المقروءة للمستخدم."""
        return await self.count("notifications", "user_id = ? AND is_read = 0", (user_id,))

    async def count_queued(self) -> int:
        """عدد الإشعارات المنتظرة في الصندوق (مؤشر صحة النظام)."""
        return await self.count("notifications", "status = 'queued'")
