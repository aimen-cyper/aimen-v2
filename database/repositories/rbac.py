"""
مستودع الأدوار والصلاحيات (RBAC) — المصدر الفعلي للصلاحيات هو قاعدة البيانات.

منطق التحقق:
    1. إن وُجد استثناء فردي للمستخدم في user_permissions فهو الحاسم (منح أو منع).
    2. وإلا تُستخدم صلاحيات دوره من role_permissions.
"""

from __future__ import annotations

from database.database import Tx
from database.repositories.base import BaseRepository


class RbacRepository(BaseRepository):
    """قراءة وتعديل الأدوار والصلاحيات."""

    # ------------------------------ القراءة ------------------------------ #

    async def list_roles(self) -> list[dict]:
        """كل الأدوار مرتبة حسب مستوى الصلاحية."""
        rows = await self.db.fetchall("SELECT * FROM roles ORDER BY level DESC")
        return [dict(row) for row in rows]

    async def list_permissions(self) -> list[dict]:
        """كل الصلاحيات المعرَّفة في النظام."""
        rows = await self.db.fetchall("SELECT * FROM permissions ORDER BY group_code, code")
        return [dict(row) for row in rows]

    async def role_permissions(self, role_code: str) -> set[str]:
        """أكواد الصلاحيات الممنوحة لدور معين."""
        rows = await self.db.fetchall(
            "SELECT permission_code FROM role_permissions WHERE role_code = ?", (role_code,)
        )
        return {row["permission_code"] for row in rows}

    async def user_overrides(self, user_id: int) -> dict[str, bool]:
        """الاستثناءات الفردية لمستخدم: كود الصلاحية → مسموح/ممنوع."""
        rows = await self.db.fetchall(
            "SELECT permission_code, allow FROM user_permissions WHERE user_id = ?", (user_id,)
        )
        return {row["permission_code"]: bool(row["allow"]) for row in rows}

    async def list_allow_overrides(self) -> list[tuple[int, str]]:
        """كل الاستثناءات الفردية «الممنوحة» (user_id، permission_code) — لمراجعة الأمان."""
        rows = await self.db.fetchall(
            "SELECT user_id, permission_code FROM user_permissions WHERE allow = 1 ORDER BY user_id"
        )
        return [(int(row["user_id"]), row["permission_code"]) for row in rows]

    async def count_overrides_by_user(self) -> dict[int, int]:
        """عدد الاستثناءات الفردية لكل مستخدم (للمستخدمين الذين لديهم استثناء فقط)."""
        rows = await self.db.fetchall(
            "SELECT user_id, COUNT(*) AS n FROM user_permissions GROUP BY user_id"
        )
        return {int(row["user_id"]): int(row["n"]) for row in rows}

    async def has_permission(self, user_id: int, role_code: str, permission: str) -> bool:
        """
        هل يملك المستخدم هذه الصلاحية؟

        الترتيب: الاستثناء الفردي أولاً، ثم صلاحيات الدور.
        """
        override = await self.db.fetchone(
            "SELECT allow FROM user_permissions WHERE user_id = ? AND permission_code = ?",
            (user_id, permission),
        )
        if override is not None:
            return bool(override["allow"])
        found = await self.db.fetchone(
            "SELECT 1 FROM role_permissions WHERE role_code = ? AND permission_code = ?",
            (role_code, permission),
        )
        return found is not None

    async def effective_permissions(self, user_id: int, role_code: str) -> set[str]:
        """الصلاحيات الفعلية للمستخدم بعد تطبيق الاستثناءات الفردية."""
        permissions = await self.role_permissions(role_code)
        for code, allowed in (await self.user_overrides(user_id)).items():
            if allowed:
                permissions.add(code)
            else:
                permissions.discard(code)
        return permissions

    # ------------------------------ الكتابة ------------------------------ #

    async def grant_to_role(self, tx: Tx, role_code: str, permission: str) -> None:
        """منح صلاحية لدور (يتجاهل التكرار)."""
        await tx.execute(
            "INSERT OR IGNORE INTO role_permissions (role_code, permission_code) VALUES (?, ?)",
            (role_code, permission),
        )

    async def revoke_from_role(self, tx: Tx, role_code: str, permission: str) -> bool:
        """سحب صلاحية من دور."""
        result = await tx.execute(
            "DELETE FROM role_permissions WHERE role_code = ? AND permission_code = ?",
            (role_code, permission),
        )
        return result.rowcount > 0

    async def set_user_override(
        self, tx: Tx, user_id: int, permission: str, *, allow: bool, granted_by: int | None = None
    ) -> None:
        """تعيين استثناء فردي لمستخدم (منح صلاحية أو منعها بغض النظر عن دوره)."""
        await tx.execute(
            """
            INSERT INTO user_permissions (user_id, permission_code, allow, granted_by, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, permission_code)
            DO UPDATE SET allow = excluded.allow, granted_by = excluded.granted_by
            """,
            (user_id, permission, 1 if allow else 0, granted_by, self.now()),
        )

    async def clear_user_override(self, tx: Tx, user_id: int, permission: str) -> bool:
        """حذف استثناء فردي والعودة إلى صلاحيات الدور."""
        result = await tx.execute(
            "DELETE FROM user_permissions WHERE user_id = ? AND permission_code = ?",
            (user_id, permission),
        )
        return result.rowcount > 0
