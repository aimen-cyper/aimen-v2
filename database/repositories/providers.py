"""
مستودع المزودين — بيانات الاتصال بلوحات SMM الخارجية.

ملاحظة أمنية: مفتاح API يُخزَّن مشفّراً في api_key_enc، ولا تُرجع هذه الطبقة
المفتاح الأصلي أبداً؛ فك التشفير يتم في ProviderService عند الاستدعاء فقط.
"""

from __future__ import annotations

from typing import Any

from database.database import Tx
from database.models import Provider
from database.repositories.base import BaseRepository

_ALLOWED_FIELDS = {
    "name",
    "api_url",
    "api_key_enc",
    "api_key_hint",
    "api_type",
    "balance_units",
    "currency",
    "exchange_rate",
    "balance_checked_at",
    "low_balance_threshold_units",
    "is_active",
    "priority",
    "timeout_seconds",
    "consecutive_failures",
    "disabled_until",
    "last_error",
    "last_success_at",
}


class ProvidersRepository(BaseRepository):
    """عمليات قراءة وكتابة بيانات المزودين."""

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, provider_id: int) -> Provider | None:
        """جلب مزود بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM providers WHERE id = ?", (provider_id,))
        return Provider.from_row(row)

    async def get_by_name(self, name: str) -> Provider | None:
        """جلب مزود بالاسم (الاسم فريد)."""
        row = await self.db.fetchone("SELECT * FROM providers WHERE name = ?", (name,))
        return Provider.from_row(row)

    async def list_all(self, *, active_only: bool = False) -> list[Provider]:
        """قائمة المزودين مرتبة حسب الأولوية."""
        sql = "SELECT * FROM providers"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY priority, id"
        rows = await self.db.fetchall(sql)
        return Provider.from_rows(rows)

    async def count_services(self, provider_id: int) -> int:
        """عدد الخدمات المرتبطة بمزود (للتحذير قبل تعطيله)."""
        return await self.count("services", "provider_id = ? AND is_archived = 0", (provider_id,))

    async def routing_counts(self) -> dict[int, dict[str, int]]:
        """
        لكل مزود: عدد خدماته المفعّلة وغير المؤرشفة، وعدد طلباته المفتوحة (لم تبلغ حالة نهائية). قراءة فقط.

        هذا ما يُبنى عليه «خريطة المزودين»: التوجيه الفعلي هو `services.provider_id` وحده.
        """
        counts: dict[int, dict[str, int]] = {}
        for row in await self.db.fetchall(
            "SELECT provider_id, COUNT(*) AS n FROM services WHERE is_active = 1 AND is_archived = 0 GROUP BY provider_id"
        ):
            counts.setdefault(row["provider_id"], {"services": 0, "open_orders": 0})["services"] = row["n"]
        for row in await self.db.fetchall(
            "SELECT provider_id, COUNT(*) AS n FROM orders "
            "WHERE status IN ('pending', 'submitting', 'submit_uncertain', 'submitted', 'in_progress') GROUP BY provider_id"
        ):
            counts.setdefault(row["provider_id"], {"services": 0, "open_orders": 0})["open_orders"] = row["n"]
        return counts

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        name: str,
        api_url: str,
        api_key_enc: str,
        api_key_hint: str | None = None,
        api_type: str = "perfect_panel",
        currency: str = "USD",
        exchange_rate: str | None = None,
        timeout_seconds: int = 30,
        priority: int = 100,
    ) -> Provider:
        """إضافة مزود جديد (المفتاح يصل مشفّراً من ProviderService)."""
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO providers (name, api_url, api_key_enc, api_key_hint, api_type, currency,
                                   exchange_rate, timeout_seconds, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name, api_url, api_key_enc, api_key_hint, api_type, currency, exchange_rate,
                timeout_seconds, priority, now, now,
            ),
        )
        row = await tx.fetchone("SELECT * FROM providers WHERE id = ?", (result.lastrowid,))
        provider = Provider.from_row(row)
        assert provider is not None
        return provider

    async def update_fields(self, tx: Tx, provider_id: int, **fields: Any) -> bool:
        """تعديل حقول مسموح بها للمزود."""
        return await self._update_by_id(tx, "providers", provider_id, fields, _ALLOWED_FIELDS)

    async def update_balance(self, tx: Tx, provider_id: int, balance_units: int) -> bool:
        """
        تحديث رصيد المزود بعد فحصه، مع تسجيل وقت الفحص.

        لا يلمس `currency` عمداً: عملة المزود إعداد يحدّده الأدمن مع سعر صرفه، ولا يجوز لاستجابة API أن
        تبدّله بصمت فتُبطل سعر الصرف (التعارض يُنبَّه عليه في ProviderService).
        """
        fields: dict[str, Any] = {
            "balance_units": balance_units,
            "balance_checked_at": self.now(),
        }
        return await self._update_by_id(tx, "providers", provider_id, fields, _ALLOWED_FIELDS)

    async def record_success(self, tx: Tx, provider_id: int) -> None:
        """تصفير عداد الأخطاء المتتالية بعد استدعاء ناجح."""
        await tx.execute(
            """
            UPDATE providers
               SET consecutive_failures = 0, disabled_until = NULL,
                   last_error = NULL, last_success_at = ?, updated_at = ?
             WHERE id = ?
            """,
            (self.now(), self.now(), provider_id),
        )

    async def record_failure(
        self, tx: Tx, provider_id: int, error: str, *, disable_until: str | None = None
    ) -> int:
        """
        تسجيل فشل استدعاء وزيادة عداد الأخطاء المتتالية (قاطع الدائرة).

        المخرجات: عدد الأخطاء المتتالية بعد التحديث.
        """
        await tx.execute(
            """
            UPDATE providers
               SET consecutive_failures = consecutive_failures + 1,
                   last_error = ?, disabled_until = COALESCE(?, disabled_until), updated_at = ?
             WHERE id = ?
            """,
            (error[:500], disable_until, self.now(), provider_id),
        )
        return int(
            await self.db.fetchval(
                "SELECT consecutive_failures FROM providers WHERE id = ?", (provider_id,), default=0
            )
        )

    async def set_active(self, tx: Tx, provider_id: int, active: bool) -> bool:
        """تفعيل أو تعطيل مزود يدوياً."""
        return await self._update_by_id(
            tx, "providers", provider_id, {"is_active": 1 if active else 0}, _ALLOWED_FIELDS
        )

    async def add_balance_snapshot(
        self, tx: Tx, provider_id: int, balance_units: int, currency: str = "USD"
    ) -> None:
        """حفظ لقطة لرصيد المزود لتتبع الاتجاه والتنبيه المبكر."""
        await tx.execute(
            """
            INSERT INTO provider_balance_snapshots (provider_id, balance_units, currency, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (provider_id, balance_units, currency, self.now()),
        )
