"""
مستودع مفاتيح منع التكرار (Idempotency).

الاستخدام النموذجي:
    قبل تنفيذ عملية حساسة (اعتماد دفعة، استرجاع، إضافة رصيد يدوي) يُحاول النظام
    حجز مفتاح فريد؛ إذا كان محجوزاً مسبقاً فهذا يعني أن العملية نُفِّذت بالفعل
    (ضغط مزدوج على الزر مثلاً) فتُعاد النتيجة السابقة بدل التنفيذ مرتين.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from core.constants import IDEMPOTENCY_TTL_SECONDS
from database.database import Tx
from database.repositories.base import BaseRepository
from utils.datetime_utils import iso_plus_seconds, utc_now_iso


class IdempotencyRepository(BaseRepository):
    """حجز مفاتيح العمليات وتخزين نتائجها."""

    async def try_acquire(
        self,
        tx: Tx,
        key: str,
        *,
        scope: str,
        user_id: int | None = None,
        ttl_seconds: int = IDEMPOTENCY_TTL_SECONDS,
    ) -> bool:
        """
        محاولة حجز مفتاح عملية.

        المخرجات:
            True  : المفتاح جديد ⇒ تابع تنفيذ العملية.
            False : المفتاح محجوز مسبقاً ⇒ العملية نُفِّذت من قبل، لا تعدها.
        """
        try:
            result = await tx.execute(
                """
                INSERT INTO idempotency_keys (key, scope, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO NOTHING
                """,
                (key, scope, user_id, self.now(), iso_plus_seconds(ttl_seconds)),
            )
        except sqlite3.IntegrityError:
            return False
        return result.rowcount == 1

    async def save_result(self, tx: Tx, key: str, result: Any) -> None:
        """حفظ نتيجة العملية ليُعاد عرضها عند تكرار الطلب."""
        await tx.execute(
            "UPDATE idempotency_keys SET result_json = ? WHERE key = ?",
            (json.dumps(result, ensure_ascii=False, default=str), key),
        )

    async def get_result(self, key: str) -> Any | None:
        """قراءة نتيجة عملية سبق تنفيذها بنفس المفتاح."""
        value = await self.db.fetchval(
            "SELECT result_json FROM idempotency_keys WHERE key = ?", (key,)
        )
        if not value:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None

    async def exists(self, key: str) -> bool:
        """هل المفتاح محجوز؟"""
        row = await self.db.fetchone("SELECT 1 FROM idempotency_keys WHERE key = ?", (key,))
        return row is not None

    async def release(self, tx: Tx, key: str) -> bool:
        """
        تحرير مفتاح (يُستخدم فقط عندما تفشل العملية قبل أن تُحدث أي أثر).

        تحذير: لا تحرر المفتاح إذا نُفِّذ جزء من العملية — الأصل هو الاحتفاظ به.
        """
        result = await tx.execute("DELETE FROM idempotency_keys WHERE key = ?", (key,))
        return result.rowcount > 0

    async def cleanup_expired(self, tx: Tx) -> int:
        """حذف المفاتيح المنتهية (مهمة التنظيف الدورية)."""
        result = await tx.execute(
            "DELETE FROM idempotency_keys WHERE expires_at < ?", (utc_now_iso(),)
        )
        return result.rowcount
