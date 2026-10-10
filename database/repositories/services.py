"""
مستودع الخدمات — الخدمات المعروضة للبيع وارتباطها بالمزودين.

قاعدة مهمة: الخدمة التي لها طلبات سابقة لا تُحذف نهائياً، بل تُعطَّل أو تُؤرشف،
حتى لا تُكسر المراجع التاريخية في جدول الطلبات.
"""

from __future__ import annotations

from typing import Any

from database.database import Tx
from database.models import Service
from database.repositories.base import BaseRepository

_ALLOWED_FIELDS = {
    "category_id",
    "provider_id",
    "provider_service_id",
    "name",
    "description",
    "service_type",
    "price_per_1000_units",
    "provider_price_per_1000_units",
    "min_quantity",
    "max_quantity",
    "dripfeed_enabled",
    "refill_enabled",
    "cancel_enabled",
    "link_pattern",
    "avg_time_text",
    "is_active",
    "is_archived",
    "sort_order",
    "link_rule",
    "speed_text",
    "quality_text",
    "guarantee_text",
    "provider_missing_at",
    "disabled_by_sync",
}


def _like_escape(text: str) -> str:
    """تعطيل أحرف LIKE الخاصة (`%` و`_` و`\\`) حتى يُبحث عنها كنص عادي مع `ESCAPE '\\'`."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ServicesRepository(BaseRepository):
    """عمليات قراءة وكتابة الخدمات."""

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, service_id: int) -> Service | None:
        """جلب خدمة بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM services WHERE id = ?", (service_id,))
        return Service.from_row(row)

    async def get_available(self, service_id: int) -> Service | None:
        """جلب خدمة متاحة للطلب فقط (مفعّلة وغير مؤرشفة)."""
        row = await self.db.fetchone(
            "SELECT * FROM services WHERE id = ? AND is_active = 1 AND is_archived = 0", (service_id,)
        )
        return Service.from_row(row)

    async def list_by_category(
        self, category_id: int, *, only_available: bool = True, limit: int = 8, offset: int = 0
    ) -> list[Service]:
        """قائمة خدمات تصنيف معين مع ترقيم صفحات."""
        sql = "SELECT * FROM services WHERE category_id = ?"
        params: list[Any] = [category_id]
        if only_available:
            sql += " AND is_active = 1 AND is_archived = 0"
        sql += " ORDER BY sort_order, id LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = await self.db.fetchall(sql, params)
        return Service.from_rows(rows)

    async def count_by_category(self, category_id: int, *, only_available: bool = True) -> int:
        """عدد خدمات تصنيف (لحساب عدد الصفحات)."""
        where = "category_id = ?"
        if only_available:
            where += " AND is_active = 1 AND is_archived = 0"
        return await self.count("services", where, (category_id,))

    async def find_by_provider_service(self, provider_id: int, provider_service_id: str) -> Service | None:
        """البحث عن خدمة مرتبطة بمعرف خدمة معين عند المزود (يُستخدم في المزامنة)."""
        row = await self.db.fetchone(
            "SELECT * FROM services WHERE provider_id = ? AND provider_service_id = ?",
            (provider_id, str(provider_service_id)),
        )
        return Service.from_row(row)

    async def list_by_provider(self, provider_id: int, *, limit: int = 50, offset: int = 0) -> list[Service]:
        """خدمات مزود معين."""
        rows = await self.db.fetchall(
            "SELECT * FROM services WHERE provider_id = ? ORDER BY id LIMIT ? OFFSET ?",
            (provider_id, limit, offset),
        )
        return Service.from_rows(rows)

    async def list_all_by_provider(self, provider_id: int) -> list[Service]:
        """كل خدمات مزود بلا سقف (المزامنة يجب أن ترى الكتالوج كاملاً مهما كبر)، مرتّبة بالمعرّف."""
        rows = await self.db.fetchall(
            "SELECT * FROM services WHERE provider_id = ? ORDER BY id", (provider_id,)
        )
        return Service.from_rows(rows)

    async def count_by_provider(self, provider_id: int) -> int:
        """عدد خدمات مزود (لترقيم الصفحات في بطاقة المزود)."""
        return await self.count("services", "provider_id = ?", (provider_id,))

    async def search(self, text: str, *, limit: int = 10) -> list[Service]:
        """بحث نصي في أسماء الخدمات (الأحرف الخاصة `%` و`_` تُعامل كنص عادي)."""
        pattern = f"%{_like_escape(text.strip())}%"
        rows = await self.db.fetchall(
            "SELECT * FROM services WHERE name LIKE ? ESCAPE '\\' ORDER BY id LIMIT ?", (pattern, limit)
        )
        return Service.from_rows(rows)

    @staticmethod
    def _admin_search_clause(tokens: list[str], numeric: int | None, exact: bool) -> tuple[str, list[Any]]:
        """
        شرط بحث الأدمن: كل كلمة يجب أن تطابق (اسم الخدمة أو القسم أو المزود أو معرّف المزود للخدمة).

        إن كان الاستعلام رقماً صرفاً ووُجدت مطابقة تامة لمعرّف الخدمة عندنا أو لمعرّف المزود (`exact`)
        فالبحث يقتصر على المطابقة التامة؛ فلا يغرق «#12» بكل خدمة يحوي معرّفها أو اسمها «12».
        """
        conditions: list[str] = []
        params: list[Any] = []
        for token in tokens:
            pattern = f"%{_like_escape(token)}%"
            conditions.append(
                "(s.name LIKE ? ESCAPE '\\' OR c.name_ar LIKE ? ESCAPE '\\' OR c.name_en LIKE ? ESCAPE '\\' "
                "OR p.name LIKE ? ESCAPE '\\' OR s.provider_service_id LIKE ? ESCAPE '\\')"
            )
            params.extend([pattern] * 5)
        clause = " AND ".join(conditions) if conditions else "0"
        if numeric is not None and exact:
            return "(s.id = ? OR s.provider_service_id = ?)", [numeric, str(numeric)]
        return clause, params

    async def has_exact_id(self, number: int) -> bool:
        """هل يطابق الرقم معرّف خدمة عندنا أو معرّف خدمة لدى مزود بالضبط؟"""
        row = await self.db.fetchone(
            "SELECT 1 FROM services WHERE id = ? OR provider_service_id = ? LIMIT 1", (number, str(number))
        )
        return row is not None

    async def admin_search(
        self, tokens: list[str], *, numeric: int | None = None, exact: bool = False, limit: int = 8, offset: int = 0
    ) -> list[Service]:
        """
        بحث الأدمن (كل الخدمات بما فيها المعطّلة والمؤرشفة): اسم/قسم/مزود/معرّف المزود/معرّف الخدمة.

        الترتيب: المطابقة التامة لمعرّف الخدمة أولاً ثم لمعرّف المزود ثم بحسب المعرّف.
        """
        clause, params = self._admin_search_clause(tokens, numeric, exact)
        order = "ORDER BY s.id"
        order_params: list[Any] = []
        if numeric is not None:
            order = "ORDER BY (s.id = ?) DESC, (s.provider_service_id = ?) DESC, s.id"
            order_params = [numeric, str(numeric)]
        rows = await self.db.fetchall(
            f"""
            SELECT s.* FROM services s
              JOIN service_categories c ON c.id = s.category_id
              JOIN providers p ON p.id = s.provider_id
             WHERE {clause}
             {order} LIMIT ? OFFSET ?
            """,
            (*params, *order_params, limit, offset),
        )
        return Service.from_rows(rows)

    async def admin_search_count(self, tokens: list[str], *, numeric: int | None = None, exact: bool = False) -> int:
        """عدد نتائج بحث الأدمن (لترقيم الصفحات)."""
        clause, params = self._admin_search_clause(tokens, numeric, exact)
        row = await self.db.fetchone(
            f"""
            SELECT COUNT(*) AS n FROM services s
              JOIN service_categories c ON c.id = s.category_id
              JOIN providers p ON p.id = s.provider_id
             WHERE {clause}
            """,
            params,
        )
        return int(row["n"]) if row else 0

    async def count_active(self) -> int:
        """عدد الخدمات المتاحة حالياً."""
        return await self.count("services", "is_active = 1 AND is_archived = 0")

    async def has_orders(self, service_id: int) -> bool:
        """هل توجد طلبات مرتبطة بهذه الخدمة؟ (يمنع الحذف الفعلي)."""
        row = await self.db.fetchone("SELECT 1 FROM orders WHERE service_id = ? LIMIT 1", (service_id,))
        return row is not None

    async def negative_margin_services(self, provider_id: int | None = None) -> list[Service]:
        """الخدمات التي أصبح سعر بيعها أقل من تكلفتها (تحذير بعد مزامنة الأسعار)، ولمزود بعينه إن حُدّد."""
        provider_clause = "" if provider_id is None else "AND provider_id = ?"
        rows = await self.db.fetchall(
            f"""
            SELECT * FROM services
             WHERE provider_price_per_1000_units IS NOT NULL
               AND price_per_1000_units < provider_price_per_1000_units
               AND is_archived = 0 {provider_clause}
             ORDER BY id
            """,
            () if provider_id is None else (provider_id,),
        )
        return Service.from_rows(rows)

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        category_id: int,
        provider_id: int,
        provider_service_id: str,
        name: str,
        price_per_1000_units: int,
        min_quantity: int,
        max_quantity: int,
        description: str | None = None,
        provider_price_per_1000_units: int | None = None,
        service_type: str = "default",
        link_pattern: str | None = None,
        avg_time_text: str | None = None,
        sort_order: int = 100,
        link_rule: str | None = None,
        speed_text: str | None = None,
        quality_text: str | None = None,
        guarantee_text: str | None = None,
    ) -> Service:
        """إضافة خدمة جديدة (مع حقول العرض: قاعدة الرابط والسرعة والجودة والضمان)."""
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO services (category_id, provider_id, provider_service_id, name, description,
                                  service_type, price_per_1000_units, provider_price_per_1000_units,
                                  min_quantity, max_quantity, link_pattern, avg_time_text,
                                  sort_order, created_at, updated_at,
                                  link_rule, speed_text, quality_text, guarantee_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                category_id, provider_id, str(provider_service_id), name, description,
                service_type, price_per_1000_units, provider_price_per_1000_units,
                min_quantity, max_quantity, link_pattern, avg_time_text, sort_order, now, now,
                link_rule, speed_text, quality_text, guarantee_text,
            ),
        )
        row = await tx.fetchone("SELECT * FROM services WHERE id = ?", (result.lastrowid,))
        service = Service.from_row(row)
        assert service is not None
        return service

    async def update_fields(self, tx: Tx, service_id: int, **fields: Any) -> bool:
        """تعديل حقول مسموح بها للخدمة."""
        return await self._update_by_id(tx, "services", service_id, fields, _ALLOWED_FIELDS)

    async def change_price(
        self,
        tx: Tx,
        service_id: int,
        *,
        new_price_units: int,
        new_min: int | None = None,
        new_max: int | None = None,
        changed_by: int | None = None,
        source: str = "admin",
    ) -> bool:
        """
        تغيير سعر أو حدود خدمة مع تسجيل التغيير في سجل الأسعار.

        السبب: الحاجة لتفسير محاسبي لأي فرق سعر بين الطلبات القديمة والجديدة.
        """
        current = await tx.fetchone(
            "SELECT price_per_1000_units, min_quantity, max_quantity FROM services WHERE id = ?",
            (service_id,),
        )
        if current is None:
            return False

        fields: dict[str, Any] = {"price_per_1000_units": new_price_units}
        if new_min is not None:
            fields["min_quantity"] = new_min
        if new_max is not None:
            fields["max_quantity"] = new_max
        updated = await self._update_by_id(tx, "services", service_id, fields, _ALLOWED_FIELDS)
        if not updated:
            return False

        await tx.execute(
            """
            INSERT INTO service_price_history (service_id, old_price_units, new_price_units,
                                               old_min, new_min, old_max, new_max,
                                               changed_by, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                service_id,
                current["price_per_1000_units"],
                new_price_units,
                current["min_quantity"],
                new_min if new_min is not None else current["min_quantity"],
                current["max_quantity"],
                new_max if new_max is not None else current["max_quantity"],
                changed_by,
                source,
                self.now(),
            ),
        )
        return True

    async def set_active(self, tx: Tx, service_id: int, active: bool) -> bool:
        """
        تفعيل أو تعطيل خدمة بقرار بشري/إداري؛ يمسح علامة «عطّلتها المزامنة» لتصبح القرار النهائي للأدمن
        (فلا تعيد المزامنة تفعيل ما عطّله يدوياً، ولا تعطّل ما فعّله يدوياً بلا سبب جديد).
        """
        return await self._update_by_id(
            tx, "services", service_id,
            {"is_active": 1 if active else 0, "disabled_by_sync": 0},
            _ALLOWED_FIELDS,
        )

    async def disable_by_sync(self, tx: Tx, service_id: int) -> bool:
        """تعطيل خدمة اختفت من قائمة المزود (تُميَّز بعلامة لتعود تلقائياً إن عادت)."""
        return await self._update_by_id(
            tx, "services", service_id,
            {"is_active": 0, "disabled_by_sync": 1, "provider_missing_at": self.now()},
            _ALLOWED_FIELDS,
        )

    async def archive(self, tx: Tx, service_id: int) -> bool:
        """أرشفة خدمة (حذف ناعم): تُخفى عن المستخدمين ويبقى تاريخها سليماً."""
        return await self._update_by_id(
            tx, "services", service_id, {"is_archived": 1, "is_active": 0}, _ALLOWED_FIELDS
        )

    async def price_history(self, service_id: int, limit: int = 10) -> list[dict]:
        """آخر تغييرات السعر لخدمة."""
        rows = await self.db.fetchall(
            "SELECT * FROM service_price_history WHERE service_id = ? ORDER BY id DESC LIMIT ?",
            (service_id, limit),
        )
        return [dict(row) for row in rows]
