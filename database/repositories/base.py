"""
الأساس المشترك لكل المستودعات (Repositories).

القاعدة المتبعة في المشروع:
    • كل دوال القراءة تعمل مباشرة عبر db (وتستخدم المعاملة الحالية تلقائياً إن وُجدت).
    • كل دوال الكتابة تستقبل tx كأول مُعامل، لإجبار المنادي على فتح معاملة صريحة.
      هذا يضمن أن العمليات المترابطة (مال + طلب + سجل + إشعار) تتم كوحدة واحدة.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from database.database import Database, ExecResult, Tx
from utils.datetime_utils import utc_now_iso


class BaseRepository:
    """أساس المستودعات: يحمل مرجع قاعدة البيانات وأدوات مساعدة مشتركة."""

    def __init__(self, db: Database) -> None:
        """تهيئة المستودع بمرجع قاعدة البيانات."""
        self.db = db

    @staticmethod
    def now() -> str:
        """الوقت الحالي بصيغة التخزين المعتمدة (ISO/UTC)."""
        return utc_now_iso()

    @staticmethod
    def _build_update(
        fields: Mapping[str, Any],
        allowed: Iterable[str],
    ) -> tuple[str, list[Any]]:
        """
        بناء جملة SET آمنة من قاموس حقول، مع قبول الأعمدة المسموح بها فقط.

        المدخلات:
            fields  : الحقول المطلوب تعديلها.
            allowed : أسماء الأعمدة المسموح تعديلها (قائمة بيضاء).

        المخرجات: (نص SET، قائمة القيم) لاستخدامها في عبارة مُعلَّمة.

        ملاحظة أمنية: أسماء الأعمدة لا تأتي أبداً من إدخال المستخدم مباشرة،
        بل تُقارن بالقائمة البيضاء، والقيم تُمرَّر كمعاملات ? وليس بالدمج النصي.
        """
        allowed_set = set(allowed)
        parts: list[str] = []
        values: list[Any] = []
        for key, value in fields.items():
            if key not in allowed_set:
                raise ValueError(f"محاولة تعديل عمود غير مسموح: {key}")
            parts.append(f"{key} = ?")
            values.append(value)
        return ", ".join(parts), values

    async def _update_by_id(
        self,
        tx: Tx,
        table: str,
        row_id: int | str,
        fields: Mapping[str, Any],
        allowed: Iterable[str],
        *,
        id_column: str = "id",
        touch_updated: bool = True,
    ) -> bool:
        """
        تعديل صف واحد حسب معرفه مع تحديث عمود updated_at تلقائياً.

        المخرجات: True إذا تم تعديل صف فعلاً.
        """
        data = dict(fields)
        if not data:
            return False
        set_sql, values = self._build_update(data, allowed)
        if touch_updated:
            set_sql += ", updated_at = ?"
            values.append(self.now())
        values.append(row_id)
        result: ExecResult = await tx.execute(
            f"UPDATE {table} SET {set_sql} WHERE {id_column} = ?", values
        )
        return result.rowcount > 0

    async def count(self, table: str, where: str = "", params: Iterable[Any] = ()) -> int:
        """عدّ الصفوف في جدول مع شرط اختياري (يُستخدم في الإحصائيات)."""
        sql = f"SELECT COUNT(*) FROM {table}"
        if where:
            sql += f" WHERE {where}"
        return int(await self.db.fetchval(sql, list(params), default=0))
