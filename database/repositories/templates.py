"""
مستودع قوالب الإشعارات المخصّصة (المرحلة 8).

القاعدة هنا بسيطة ومقصودة: **لا صف = النص الافتراضي المكتوب في الكود**.
لا نزرع صفوفاً للقوالب عند التثبيت، فالصف يُنشأ فقط عندما يعدّل الأدمن نصاً،
ويُحذف عند «استعادة الافتراضي». هكذا يبقى تحديث النصوص الافتراضية مع ترقية
الإصدار نافذاً تلقائياً لكل قالب لم يلمسه أحد.
"""

from __future__ import annotations

from database.database import Tx
from database.models import NotificationTemplate
from database.repositories.base import BaseRepository


class NotificationTemplatesRepository(BaseRepository):
    """قراءة وكتابة القوالب المخصّصة لرسائل الإشعارات."""

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, code: str) -> NotificationTemplate | None:
        """جلب قالب مخصّص واحد بالرمز (None يعني أنه لم يُعدَّل قط)."""
        row = await self.db.fetchone(
            "SELECT * FROM notification_templates WHERE code = ?", (code,)
        )
        return NotificationTemplate.from_row(row)

    async def list_all(self) -> list[NotificationTemplate]:
        """كل القوالب المخصّصة (المفعّلة والموقوفة) مرتبة بالرمز."""
        rows = await self.db.fetchall("SELECT * FROM notification_templates ORDER BY code")
        return NotificationTemplate.from_rows(rows)

    async def active_map(self) -> dict[str, tuple[str, str]]:
        """
        القوالب المفعّلة فقط بشكل جاهز للذاكرة: code -> (title, body).

        هذه الدالة هي ما تُحمّله طبقة النصوص عند الإقلاع وبعد كل تعديل.
        """
        rows = await self.db.fetchall(
            "SELECT code, title, body FROM notification_templates WHERE is_active = 1"
        )
        return {row["code"]: (row["title"], row["body"]) for row in rows}

    async def count_customized(self) -> int:
        """عدد القوالب التي عُدِّلت فعلاً (يُعرض في شاشة القوالب وفحص الإقلاع)."""
        return await self.count("notification_templates", "1 = 1", ())

    # ------------------------------ الكتابة ------------------------------ #

    async def upsert(
        self,
        tx: Tx,
        *,
        code: str,
        title: str,
        body: str,
        admin_id: int | None,
        is_active: bool = True,
    ) -> NotificationTemplate:
        """
        حفظ قالب مخصّص (إنشاء أو تحديث) وإرجاع صفه بعد الحفظ.

        التحقق من صحة المتغيرات يتم في طبقة الخدمة قبل الوصول إلى هنا.
        """
        await tx.execute(
            """
            INSERT INTO notification_templates (code, title, body, is_active, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                title = excluded.title,
                body = excluded.body,
                is_active = excluded.is_active,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
            """,
            (code, title, body, 1 if is_active else 0, admin_id, self.now()),
        )
        row = await tx.fetchone("SELECT * FROM notification_templates WHERE code = ?", (code,))
        template = NotificationTemplate.from_row(row)
        assert template is not None  # الصف محفوظ للتو في نفس المعاملة
        return template

    async def set_active(self, tx: Tx, code: str, *, active: bool) -> bool:
        """تفعيل أو إيقاف قالب مخصّص دون حذف نصه (ليعود الأدمن إليه لاحقاً)."""
        result = await tx.execute(
            "UPDATE notification_templates SET is_active = ?, updated_at = ? WHERE code = ?",
            (1 if active else 0, self.now(), code),
        )
        return result.rowcount > 0

    async def delete(self, tx: Tx, code: str) -> bool:
        """
        حذف التخصيص والعودة للنص الافتراضي.

        هذا هو الحذف الوحيد المسموح في النظام لأن المحذوف ليس بيانات تاريخية
        بل «تفضيل صياغة»، والنص الأصلي موجود في الكود ولا يضيع.
        """
        result = await tx.execute("DELETE FROM notification_templates WHERE code = ?", (code,))
        return result.rowcount > 0
