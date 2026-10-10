"""مستودع المفضلة: خدمات يحفظها المستخدم لوصول أسرع (مفتاح مركّب ⇒ لا تكرار بنيوياً)."""

from __future__ import annotations

from database.database import Tx
from database.models import Service
from database.repositories.base import BaseRepository


class FavoritesRepository(BaseRepository):
    """إضافة/حذف/عرض مفضلة المستخدم."""

    async def add(self, tx: Tx, user_id: int, service_id: int) -> bool:
        """إضافة خدمة؛ المخرجات: True إن أُضيفت الآن، False إن كانت موجودة (لا تكرار)."""
        result = await tx.execute(
            "INSERT INTO favorites (user_id, service_id, created_at) VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
            (user_id, service_id, self.now()),
        )
        return result.rowcount == 1

    async def remove(self, tx: Tx, user_id: int, service_id: int) -> bool:
        """إزالة خدمة؛ المخرجات: True إن كانت موجودة وأُزيلت."""
        result = await tx.execute(
            "DELETE FROM favorites WHERE user_id = ? AND service_id = ?", (user_id, service_id)
        )
        return result.rowcount == 1

    async def exists(self, user_id: int, service_id: int) -> bool:
        """هل الخدمة في مفضلة المستخدم؟"""
        row = await self.db.fetchone(
            "SELECT 1 FROM favorites WHERE user_id = ? AND service_id = ?", (user_id, service_id)
        )
        return row is not None

    async def count_for_user(self, user_id: int) -> int:
        """عدد مفضلات المستخدم (كل الخدمات، متاحة أو لا)."""
        return await self.count("favorites", "user_id = ?", (user_id,))

    async def list_available(self, user_id: int, *, limit: int, offset: int) -> list[Service]:
        """مفضلة المستخدم من الخدمات المتاحة للطلب حالياً، الأحدث إضافةً أولاً."""
        rows = await self.db.fetchall(
            """
            SELECT s.* FROM favorites f
              JOIN services s ON s.id = f.service_id
             WHERE f.user_id = ? AND s.is_active = 1 AND s.is_archived = 0
             ORDER BY f.created_at DESC, s.id DESC LIMIT ? OFFSET ?
            """,
            (user_id, limit, offset),
        )
        return Service.from_rows(rows)

    async def count_available(self, user_id: int) -> int:
        """عدد المفضلة المتاحة للطلب (لترقيم الصفحات)."""
        return int(
            await self.db.fetchval(
                """
                SELECT COUNT(*) FROM favorites f JOIN services s ON s.id = f.service_id
                 WHERE f.user_id = ? AND s.is_active = 1 AND s.is_archived = 0
                """,
                [user_id],
                default=0,
            )
        )
