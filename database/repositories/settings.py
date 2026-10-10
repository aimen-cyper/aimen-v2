"""
مستودع الإعدادات العامة — كل قيمة قابلة للتعديل من لوحة الأدمن تُقرأ من هنا.

التخزين نصي دائماً، والتحويل إلى النوع الصحيح يتم عند القراءة حسب value_type.
"""

from __future__ import annotations

import json
from typing import Any

from database.database import Tx
from database.models import Setting
from database.repositories.base import BaseRepository


class SettingsRepository(BaseRepository):
    """قراءة وكتابة إعدادات النظام."""

    # ------------------------------ القراءة ------------------------------ #

    async def get_raw(self, key: str) -> str | None:
        """القيمة النصية الخام لإعداد، أو None إذا لم يوجد."""
        return await self.db.fetchval("SELECT value FROM settings WHERE key = ?", (key,))

    async def get(self, key: str) -> Setting | None:
        """جلب الإعداد كاملاً بكل بياناته الوصفية."""
        row = await self.db.fetchone("SELECT * FROM settings WHERE key = ?", (key,))
        return Setting.from_row(row)

    async def get_str(self, key: str, default: str = "") -> str:
        """قراءة إعداد نصي."""
        value = await self.get_raw(key)
        return default if value is None else value

    async def get_int(self, key: str, default: int = 0) -> int:
        """قراءة إعداد رقمي (يُرجع القيمة الافتراضية إذا كانت القيمة تالفة)."""
        value = await self.get_raw(key)
        if value is None or value == "":
            return default
        try:
            return int(value)
        except ValueError:
            return default

    async def get_bool(self, key: str, default: bool = False) -> bool:
        """قراءة إعداد منطقي (يقبل 1/0 و true/false و yes/no)."""
        value = await self.get_raw(key)
        if value is None or value == "":
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    async def get_json(self, key: str, default: Any = None) -> Any:
        """قراءة إعداد مخزَّن كـ JSON."""
        value = await self.get_raw(key)
        if not value:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default

    async def get_money_units(self, key: str, default: int = 0) -> int:
        """قراءة إعداد مالي مخزَّن بالنقاط."""
        return await self.get_int(key, default)

    async def all(self) -> list[Setting]:
        """كل الإعدادات مرتبة حسب المجموعة."""
        rows = await self.db.fetchall("SELECT * FROM settings ORDER BY group_code, key")
        return Setting.from_rows(rows)

    async def by_group(self, group_code: str) -> list[Setting]:
        """إعدادات مجموعة واحدة (لعرضها في شاشة واحدة داخل اللوحة)."""
        rows = await self.db.fetchall(
            "SELECT * FROM settings WHERE group_code = ? ORDER BY key", (group_code,)
        )
        return Setting.from_rows(rows)

    async def groups(self) -> list[str]:
        """أسماء مجموعات الإعدادات الموجودة."""
        rows = await self.db.fetchall("SELECT DISTINCT group_code FROM settings ORDER BY group_code")
        return [row["group_code"] for row in rows]

    async def as_dict(self) -> dict[str, str]:
        """كل الإعدادات كقاموس (يُستخدم لبناء الذاكرة المؤقتة في SettingsService)."""
        rows = await self.db.fetchall("SELECT key, value FROM settings")
        return {row["key"]: row["value"] for row in rows}

    # ------------------------------ الكتابة ------------------------------ #

    async def set(self, tx: Tx, key: str, value: Any, *, updated_by: int | None = None) -> bool:
        """
        تعديل قيمة إعداد موجود.

        المخرجات: True إذا تم التعديل، False إذا كان المفتاح غير موجود أو غير قابل للتعديل.
        """
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        result = await tx.execute(
            "UPDATE settings SET value = ?, updated_by = ?, updated_at = ? WHERE key = ? AND is_editable = 1",
            (text, updated_by, self.now(), key),
        )
        return result.rowcount > 0

    async def upsert(
        self,
        tx: Tx,
        key: str,
        value: Any,
        *,
        value_type: str = "str",
        group_code: str = "general",
        name_ar: str = "",
        description_ar: str | None = None,
        is_editable: bool = True,
    ) -> None:
        """إضافة إعداد جديد أو تحديثه (تُستخدم عند إضافة ميزات جديدة تحتاج إعدادات)."""
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        await tx.execute(
            """
            INSERT INTO settings (key, value, value_type, group_code, name_ar, description_ar,
                                  is_editable, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                value_type = excluded.value_type,
                group_code = excluded.group_code,
                name_ar = excluded.name_ar,
                description_ar = excluded.description_ar,
                updated_at = excluded.updated_at
            """,
            (key, text, value_type, group_code, name_ar, description_ar, 1 if is_editable else 0, self.now()),
        )
