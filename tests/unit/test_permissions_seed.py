"""
اختبار تطابق مصدر الصلاحيات.

قاعدة ذهبية: `core/permissions.py` و `0002_seed_rbac.sql` يجب أن يظلا متطابقين تماماً.
أي صلاحية تُضاف في أحدهما وتُنسى في الآخر يكشفها هذا الاختبار فوراً.
"""

from __future__ import annotations

from core.permissions import (
    PERMISSION_MAP,
    PERMISSIONS,
    ROLE_DEFAULTS,
    ROLES,
    all_permission_codes,
    role_has_default,
)
from database.database import Database
from database.repositories import Repositories


async def test_permission_codes_match_seed(db: Database) -> None:
    """كل صلاحية في الكود موجودة في قاعدة البيانات والعكس."""
    rows = await db.fetchall("SELECT code FROM permissions")
    db_codes = {row["code"] for row in rows}
    code_codes = set(all_permission_codes())

    missing_in_db = code_codes - db_codes
    extra_in_db = db_codes - code_codes
    assert not missing_in_db, f"صلاحيات في الكود وغير مزروعة: {sorted(missing_in_db)}"
    assert not extra_in_db, f"صلاحيات مزروعة وغير معرَّفة في الكود: {sorted(extra_in_db)}"


async def test_permission_metadata_matches_seed(db: Database) -> None:
    """الاسم العربي والمجموعة وعلامة الخطورة متطابقة بين الكود والزرع."""
    rows = await db.fetchall("SELECT code, name_ar, group_code, is_dangerous FROM permissions")
    for row in rows:
        definition = PERMISSION_MAP[row["code"]]
        assert row["name_ar"] == definition.name_ar, f"اسم مختلف: {row['code']}"
        assert row["group_code"] == definition.group_code, f"مجموعة مختلفة: {row['code']}"
        assert bool(row["is_dangerous"]) is definition.is_dangerous, f"خطورة مختلفة: {row['code']}"


async def test_role_defaults_match_seed(repos: Repositories) -> None:
    """توزيع الصلاحيات على الأدوار في الكود = التوزيع المزروع في قاعدة البيانات."""
    for role, expected in ROLE_DEFAULTS.items():
        actual = await repos.rbac.role_permissions(role)
        assert actual == set(expected), (
            f"اختلاف في الدور {role}: "
            f"ناقص={sorted(set(expected) - actual)} زائد={sorted(actual - set(expected))}"
        )


async def test_roles_seeded_with_levels(db: Database) -> None:
    """الأدوار الأربعة مزروعة بمستوياتها وأسمائها الصحيحة."""
    rows = await db.fetchall("SELECT code, name_ar, level FROM roles ORDER BY level")
    seeded = [(row["code"], row["name_ar"], row["level"]) for row in rows]
    expected = [(r.code, r.name_ar, r.level) for r in sorted(ROLES, key=lambda r: r.level)]
    assert seeded == expected


async def test_every_permission_belongs_to_a_known_group(db: Database) -> None:
    """لا صلاحية يتيمة بلا مجموعة عرض في لوحة الأدمن."""
    groups = {p.group_code for p in PERMISSIONS}
    assert "" not in groups
    rows = await db.fetchall("SELECT DISTINCT group_code FROM permissions")
    assert {row["group_code"] for row in rows} == groups


async def test_permission_names_are_arabic(db: Database) -> None:
    """كل صلاحية لها اسم عربي غير فارغ لعرضه في الواجهة."""
    rows = await db.fetchall("SELECT code, name_ar FROM permissions")
    for row in rows:
        name = (row["name_ar"] or "").strip()
        assert name, f"اسم فارغ للصلاحية {row['code']}"
        assert any("\u0600" <= ch <= "\u06ff" for ch in name), f"اسم غير عربي للصلاحية {row['code']}"


async def test_super_admin_has_all_permissions(repos: Repositories) -> None:
    """الدور الأعلى يملك كل الصلاحيات دون استثناء."""
    perms = await repos.rbac.role_permissions("super_admin")
    assert perms == set(all_permission_codes())


async def test_user_role_has_no_admin_permissions(repos: Repositories) -> None:
    """المستخدم العادي لا يملك أي صلاحية إدارية."""
    assert await repos.rbac.role_permissions("user") == set()
    assert role_has_default("user", "admin.access") is False


async def test_permission_codes_unique() -> None:
    """لا تكرار في رموز الصلاحيات داخل الكتالوج."""
    codes = [p.code for p in PERMISSIONS]
    assert len(codes) == len(set(codes))
    assert len(codes) == len(PERMISSION_MAP)


async def test_dangerous_permissions_flagged(db: Database) -> None:
    """الصلاحيات الحساسة (المال، المفاتيح، الحظر) موسومة كخطِرة لتأكيدها في الواجهة."""
    critical = [
        "users.balance.credit",
        "users.balance.debit",
        "users.ban",
        "users.role.change",
        "providers.key.update",
        "orders.refund",
        "payments.approve",
    ]
    rows = await db.fetchall(
        f"SELECT code, is_dangerous FROM permissions WHERE code IN ({','.join('?' * len(critical))})",
        critical,
    )
    assert len(rows) == len(critical)
    for row in rows:
        assert row["is_dangerous"] == 1, f"صلاحية حساسة غير موسومة: {row['code']}"
