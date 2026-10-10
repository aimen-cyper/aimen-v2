"""مستودع تصنيفات الخدمات (المنصات: انستغرام، تيك توك ...)."""

from __future__ import annotations

from typing import Any

from database.database import Tx
from database.models import ServiceCategory
from database.repositories.base import BaseRepository

_ALLOWED_FIELDS = {"name_ar", "name_en", "emoji", "sort_order", "is_active"}


class CategoriesRepository(BaseRepository):
    """عمليات التصنيفات."""

    async def get(self, category_id: int) -> ServiceCategory | None:
        """جلب تصنيف بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM service_categories WHERE id = ?", (category_id,))
        return ServiceCategory.from_row(row)

    async def list_all(self, *, active_only: bool = False) -> list[ServiceCategory]:
        """قائمة التصنيفات مرتبة حسب ترتيب العرض."""
        sql = "SELECT * FROM service_categories"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY sort_order, id"
        rows = await self.db.fetchall(sql)
        return ServiceCategory.from_rows(rows)

    async def list_with_available_services(self) -> list[ServiceCategory]:
        """
        التصنيفات التي تحتوي فعلياً على خدمة واحدة متاحة على الأقل.

        الفائدة: عدم عرض تصنيف فارغ للمستخدم (زر بلا محتوى).
        """
        rows = await self.db.fetchall(
            """
            SELECT c.* FROM service_categories c
             WHERE c.is_active = 1
               AND EXISTS (
                   SELECT 1 FROM services s
                    WHERE s.category_id = c.id AND s.is_active = 1 AND s.is_archived = 0
               )
             ORDER BY c.sort_order, c.id
            """
        )
        return ServiceCategory.from_rows(rows)

    async def create(
        self, tx: Tx, *, name_ar: str, name_en: str | None = None, emoji: str = "📦", sort_order: int = 100
    ) -> ServiceCategory:
        """إضافة تصنيف جديد."""
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO service_categories (name_ar, name_en, emoji, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name_ar, name_en, emoji, sort_order, now, now),
        )
        row = await tx.fetchone("SELECT * FROM service_categories WHERE id = ?", (result.lastrowid,))
        category = ServiceCategory.from_row(row)
        assert category is not None
        return category

    async def update_fields(self, tx: Tx, category_id: int, **fields: Any) -> bool:
        """تعديل بيانات تصنيف."""
        return await self._update_by_id(tx, "service_categories", category_id, fields, _ALLOWED_FIELDS)

    async def set_active(self, tx: Tx, category_id: int, active: bool) -> bool:
        """تفعيل أو إخفاء تصنيف."""
        return await self._update_by_id(
            tx, "service_categories", category_id, {"is_active": 1 if active else 0}, _ALLOWED_FIELDS
        )
