"""
حارس كتالوج الصلاحيات.

الهدف: منع أخطر خطأ صامت في نظام الصلاحيات — أن يُكتب كود يستخدم
`Permission.X` بقيمة لا توجد في كتالوج `PERMISSIONS` المزروع في قاعدة البيانات،
فتفشل عمليات التحقق دائماً (أو تنجح دائماً) دون أن ينتبه أحد.

هذا الاختبار يفشل فوراً عند إضافة صلاحية في مكان ونسيانها في الآخر.
"""

from __future__ import annotations

from core.enums import Role
from core.permissions import PERMISSIONS, ROLE_DEFAULTS, Permission


def test_enum_matches_catalog_exactly() -> None:
    """قيم الـEnum مطابقة تماماً لأكواد الكتالوج — لا زيادة ولا نقصان."""
    enum_values = {member.value for member in Permission}
    catalog_codes = {item.code for item in PERMISSIONS}
    assert enum_values == catalog_codes, (
        f"فرق بين Enum والكتالوج: "
        f"زائد في Enum={sorted(enum_values - catalog_codes)} · "
        f"ناقص من Enum={sorted(catalog_codes - enum_values)}"
    )


def test_catalog_codes_are_unique() -> None:
    """لا يوجد كود صلاحية مكرر في الكتالوج."""
    codes = [item.code for item in PERMISSIONS]
    assert len(codes) == len(set(codes))


def test_enum_member_names_follow_code() -> None:
    """اسم عضو الـEnum مشتق من الكود (نقاط وشرطات ← شرطة سفلية بحروف كبيرة)."""
    for member in Permission:
        expected = member.value.replace(".", "_").upper()
        assert member.name == expected, f"اسم غير متوافق: {member.name} ≠ {expected}"


def test_role_defaults_reference_existing_codes() -> None:
    """كل صلاحية مذكورة في خرائط الأدوار موجودة فعلاً في الكتالوج."""
    catalog_codes = {item.code for item in PERMISSIONS}
    for role, codes in ROLE_DEFAULTS.items():
        unknown = set(codes) - catalog_codes
        assert not unknown, f"الدور {role} يشير إلى صلاحيات غير معرّفة: {sorted(unknown)}"


def test_super_admin_has_all_permissions() -> None:
    """الأدمن الأعلى يملك كل الصلاحيات دون استثناء."""
    assert set(ROLE_DEFAULTS[Role.SUPER_ADMIN]) == {item.code for item in PERMISSIONS}


def test_plain_user_has_no_admin_permissions() -> None:
    """المستخدم العادي لا يملك أي صلاحية إدارية."""
    assert set(ROLE_DEFAULTS[Role.USER]) == set()


def test_admin_cannot_manage_admins_by_default() -> None:
    """الأدمن العادي لا يملك إدارة المدراء ولا تغيير الأدوار (تبقى للأدمن الأعلى)."""
    admin_permissions = set(ROLE_DEFAULTS[Role.ADMIN])
    assert Permission.ADMINS_MANAGE not in admin_permissions
    assert Permission.USERS_ROLE_CHANGE not in admin_permissions
    assert Permission.ADMIN_ACCESS in admin_permissions
