"""
مستودع سجل التدقيق (Audit Log) — كل عملية إدارية حساسة تُسجَّل هنا.

القاعدة: أي تعديل على المال أو الصلاحيات أو الحالات أو الإعدادات يجب أن يترك أثراً
يحتوي: من فعل، ماذا فعل، على من، وما القيمة قبل وبعد.
"""

from __future__ import annotations

import json
from typing import Any

from database.database import Tx
from database.models import AuditLog
from database.repositories.base import BaseRepository


def _to_json(value: Any) -> str | None:
    """تحويل قيمة إلى نص JSON مختصر (أو None إذا كانت فارغة)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def _like_prefix(prefix: str) -> str:
    """تحويل بادئة نصية إلى نمط LIKE آمن (مع تعطيل الأحرف الخاصة `%` و`_` و`\\`)."""
    escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"{escaped}%"


class AuditRepository(BaseRepository):
    """كتابة وقراءة سجل العمليات الإدارية."""

    async def log(
        self,
        tx: Tx,
        *,
        action: str,
        admin_id: int | None = None,
        target_type: str | None = None,
        target_id: str | int | None = None,
        details: Any = None,
        before: Any = None,
        after: Any = None,
        source: str = "telegram",
    ) -> int | None:
        """
        تسجيل عملية إدارية.

        المدخلات:
            action      : كود العملية (مثل "user.balance.credit").
            target_type : نوع الهدف (user/order/service/provider/payment/setting/ticket).
            before/after: حالة الهدف قبل وبعد التعديل (تُخزَّن كـ JSON).

        المخرجات: معرف السجل.
        """
        result = await tx.execute(
            """
            INSERT INTO audit_logs (admin_id, action, target_type, target_id, details_json,
                                    before_json, after_json, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                admin_id, action, target_type,
                str(target_id) if target_id is not None else None,
                _to_json(details), _to_json(before), _to_json(after), source, self.now(),
            ),
        )
        return result.lastrowid

    async def list_recent(self, *, limit: int = 20, offset: int = 0) -> list[AuditLog]:
        """آخر العمليات الإدارية."""
        rows = await self.db.fetchall(
            "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        return AuditLog.from_rows(rows)

    async def list_by_admin(self, admin_id: int, *, limit: int = 20, offset: int = 0) -> list[AuditLog]:
        """عمليات أدمن معين (لمراجعة الأداء أو التحقيق)."""
        rows = await self.db.fetchall(
            "SELECT * FROM audit_logs WHERE admin_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (admin_id, limit, offset),
        )
        return AuditLog.from_rows(rows)

    async def list_by_target(
        self, target_type: str, target_id: str | int, *, limit: int = 20
    ) -> list[AuditLog]:
        """كل العمليات التي جرت على هدف معين (مثل كل ما حدث لمستخدم)."""
        rows = await self.db.fetchall(
            """
            SELECT * FROM audit_logs WHERE target_type = ? AND target_id = ?
             ORDER BY id DESC LIMIT ?
            """,
            (target_type, str(target_id), limit),
        )
        return AuditLog.from_rows(rows)

    async def count_by_action_prefix(self, prefix: str, *, since_iso: str | None = None) -> int:
        """عدد السجلات التي يبدأ إجراؤها ببادئة معينة (مثل `security.`) منذ وقت اختياري."""
        pattern = _like_prefix(prefix)
        if since_iso is None:
            row = await self.db.fetchone(
                "SELECT COUNT(*) AS n FROM audit_logs WHERE action LIKE ? ESCAPE '\\'", (pattern,)
            )
        else:
            row = await self.db.fetchone(
                "SELECT COUNT(*) AS n FROM audit_logs WHERE action LIKE ? ESCAPE '\\' AND created_at >= ?",
                (pattern, since_iso),
            )
        return int(row["n"]) if row else 0

    async def count_action(self, action: str, *, since_iso: str) -> int:
        """عدد مرات إجراء بعينه منذ وقت محدد."""
        row = await self.db.fetchone(
            "SELECT COUNT(*) AS n FROM audit_logs WHERE action = ? AND created_at >= ?",
            (action, since_iso),
        )
        return int(row["n"]) if row else 0

    async def list_by_action_prefix(
        self, prefix: str, *, limit: int = 10, offset: int = 0
    ) -> list[AuditLog]:
        """سجلات إجراءات ببادئة معينة، الأحدث أولاً (يغذّي شاشة الأحداث الأمنية)."""
        rows = await self.db.fetchall(
            "SELECT * FROM audit_logs WHERE action LIKE ? ESCAPE '\\' ORDER BY id DESC LIMIT ? OFFSET ?",
            (_like_prefix(prefix), limit, offset),
        )
        return AuditLog.from_rows(rows)

    async def top_actors_by_action_prefix(
        self, prefix: str, *, since_iso: str, limit: int = 5
    ) -> list[tuple[int, int]]:
        """أكثر المستخدمين تكراراً في أحداث ببادئة معينة: قائمة (معرّف المستخدم، العدد)."""
        rows = await self.db.fetchall(
            """
            SELECT admin_id, COUNT(*) AS n FROM audit_logs
             WHERE action LIKE ? ESCAPE '\\' AND created_at >= ? AND admin_id IS NOT NULL
             GROUP BY admin_id ORDER BY n DESC, admin_id LIMIT ?
            """,
            (_like_prefix(prefix), since_iso, limit),
        )
        return [(int(row["admin_id"]), int(row["n"])) for row in rows]

    @staticmethod
    def _prefix_clause(prefixes: tuple[str, ...]) -> tuple[str, list[str]]:
        """شرط WHERE لعدة بادئات إجراء (OR بينها)؛ قائمة فارغة = بلا شرط (كل السجلات)."""
        if not prefixes:
            return "", []
        clause = " OR ".join("action LIKE ? ESCAPE '\\'" for _ in prefixes)
        return f" WHERE {clause}", [_like_prefix(prefix) for prefix in prefixes]

    async def list_by_prefixes(
        self, prefixes: tuple[str, ...], *, limit: int = 8, offset: int = 0
    ) -> list[AuditLog]:
        """سجلات تطابق أي بادئة من القائمة، الأحدث أولاً (فلتر الفئات في شاشة السجلات)."""
        where, params = self._prefix_clause(prefixes)
        rows = await self.db.fetchall(
            f"SELECT * FROM audit_logs{where} ORDER BY id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        return AuditLog.from_rows(rows)

    async def count_by_prefixes(self, prefixes: tuple[str, ...]) -> int:
        """عدد السجلات المطابقة لأي بادئة من القائمة."""
        where, params = self._prefix_clause(prefixes)
        return int(await self.db.fetchval(f"SELECT COUNT(*) FROM audit_logs{where}", params, default=0))

    async def get(self, audit_id: int) -> AuditLog | None:
        """سجل تدقيق واحد بمعرّفه (لشاشة التفاصيل)."""
        row = await self.db.fetchone("SELECT * FROM audit_logs WHERE id = ?", (audit_id,))
        return AuditLog.from_row(row) if row else None

    async def count_all(self) -> int:
        """إجمالي عدد السجلات."""
        return await self.count("audit_logs")
