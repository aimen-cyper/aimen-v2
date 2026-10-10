"""اختبارات حواجز الأدوار والصلاحيات وحظر التنفيذ الذاتي (المرحلة 9)."""

from __future__ import annotations

import pytest

from core.exceptions import PermissionDeniedError, ValidationError
from core.permissions import Permission
from database.models import User
from services import ServiceContainer

pytestmark = pytest.mark.asyncio


async def _make(db, repos, telegram_id: int, role: str, name: str) -> User:
    """إنشاء مستخدم بدور محدد."""
    async with db.transaction() as tx:
        return await repos.users.create(tx, telegram_id=telegram_id, username=name, first_name=name, role=role)


async def _grant_role_perm(db, repos, role: str, permission: str) -> None:
    """منح صلاحية لدور (لتمكين سيناريو أدمن يملك صلاحية عالية)."""
    async with db.transaction() as tx:
        await repos.rbac.grant_to_role(tx, role, permission)


async def _events(repos, event: str) -> int:
    """عدد مرات حدث أمني في سجل التدقيق."""
    return await repos.audit.count_by_action_prefix(f"security.{event}")


# ============================== تغيير الدور ============================== #


async def test_super_admin_can_promote_and_demote(db, repos, services: ServiceContainer, super_admin, user) -> None:
    """الأدمن الأعلى يرقّي المستخدم ثم يعيده (المسار الطبيعي يعمل)."""
    assert await services.auth.set_role(super_admin, user.id, "support") is True
    assert (await repos.users.get_by_id(user.id)).role == "support"
    assert await services.auth.set_role(super_admin, user.id, "user") is True


async def test_normal_admin_without_permission_cannot_change_roles(services, super_admin, admin, user, repos) -> None:
    """الأدمن العادي لا يملك `users.role.change` افتراضياً."""
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_role(admin, user.id, "support")
    assert (await repos.users.get_by_id(user.id)).role == "user"


async def test_self_role_change_blocked_and_audited(db, repos, services, super_admin) -> None:
    """لا يغيّر أحد دور حسابه بنفسه (حتى الأدمن الأعلى) ويُسجَّل الحدث."""
    other = await _make(db, repos, 5001, "super_admin", "second_root")
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_role(super_admin, super_admin.id, "user")
    assert (await repos.users.get_by_id(super_admin.id)).role == "super_admin"
    assert await _events(repos, "self_role_change_blocked") == 1
    assert other.id != super_admin.id


async def test_admin_with_role_permission_cannot_escalate_to_own_level(db, repos, services, admin, user) -> None:
    """أدمن مُنح تغيير الأدوار لا يستطيع منح دور بمستواه أو أعلى (منع التصعيد)."""
    await _grant_role_perm(db, repos, "admin", Permission.USERS_ROLE_CHANGE)
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_role(admin, user.id, "admin")
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_role(admin, user.id, "super_admin")
    assert (await repos.users.get_by_id(user.id)).role == "user"
    assert await _events(repos, "role_escalation_blocked") == 2
    # ما دون مستواه مسموح
    assert await services.auth.set_role(admin, user.id, "support") is True


async def test_admin_cannot_modify_peer_or_superior(db, repos, services, admin, super_admin) -> None:
    """الأدمن العادي لا يعدّل زميلاً بنفس المستوى ولا أدمن أعلى."""
    await _grant_role_perm(db, repos, "admin", Permission.USERS_ROLE_CHANGE)
    peer = await _make(db, repos, 5002, "admin", "peer")
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_role(admin, peer.id, "user")
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_role(admin, super_admin.id, "user")
    assert await _events(repos, "hierarchy_denied") == 2


async def test_last_super_admin_cannot_be_demoted(db, repos, services, super_admin) -> None:
    """
    آخر أدمن أعلى فعّال محمي من التخفيض.

    الوصول لهذا الحاجز يحتاج منفِّذاً أعلى غير فعّال (محظور) لا يزال يملك الدور؛
    نتأكد أن الحاجز يعمل وأن الحدث الأمني مسجَّل تحديداً.
    """
    banned_root = await _make(db, repos, 5003, "super_admin", "banned_root")
    async with db.transaction() as tx:
        await repos.users.set_ban(tx, banned_root.id, banned=True, reason="اختبار")
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_role(banned_root, super_admin.id, "user")
    assert (await repos.users.get_by_id(super_admin.id)).role == "super_admin"
    assert await _events(repos, "last_super_admin_protected") == 1


async def test_demoting_a_banned_super_admin_is_allowed(db, repos, services, super_admin) -> None:
    """تخفيض أدمن أعلى محظور (غير فعّال) مسموح لأنه لا يُفقد النظام أدمن فعّالاً."""
    banned_root = await _make(db, repos, 5008, "super_admin", "banned_root2")
    async with db.transaction() as tx:
        await repos.users.set_ban(tx, banned_root.id, banned=True, reason="اختبار")
    assert await services.auth.set_role(super_admin, banned_root.id, "user") is True


async def test_second_super_admin_allows_demoting_the_first(db, repos, services, super_admin) -> None:
    """بوجود أدمن أعلى ثانٍ فعّال يصح تخفيض الأول."""
    second = await _make(db, repos, 5004, "super_admin", "second")
    assert await services.auth.set_role(second, super_admin.id, "admin") is True


# ============================ الاستثناءات الفردية ============================ #


async def test_cannot_change_own_permissions(db, repos, services, super_admin) -> None:
    """لا أحد يعدّل استثناءات صلاحيات حسابه."""
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_user_permission(super_admin, super_admin.id, Permission.ORDERS_VIEW, allow=False)
    assert await _events(repos, "self_permission_change_blocked") == 1


async def test_admin_cannot_grant_permission_he_lacks(db, repos, services, admin, user) -> None:
    """لا يمنح الأدمن صلاحية لا يملكها (`backup.create` حصرية للأعلى)."""
    await _grant_role_perm(db, repos, "admin", Permission.ADMINS_MANAGE)
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_user_permission(admin, user.id, Permission.BACKUP_CREATE, allow=True)
    assert await _events(repos, "grant_unowned_permission_blocked") == 1


async def test_admin_cannot_grant_dangerous_permission_even_if_owned(db, repos, services, admin, user) -> None:
    """الصلاحية الخطِرة (اعتماد الشحن) يمنحها الأدمن الأعلى فقط ولو كان المانح يملكها."""
    await _grant_role_perm(db, repos, "admin", Permission.ADMINS_MANAGE)
    assert await services.auth.has_permission(admin, Permission.PAYMENTS_APPROVE)
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_user_permission(admin, user.id, Permission.PAYMENTS_APPROVE, allow=True)
    assert await _events(repos, "grant_dangerous_permission_blocked") == 1


async def test_admin_can_grant_safe_owned_permission(db, repos, services, admin, user) -> None:
    """منح صلاحية عادية يملكها المانح مسموح ويُدقَّق."""
    await _grant_role_perm(db, repos, "admin", Permission.ADMINS_MANAGE)
    await services.auth.set_user_permission(admin, user.id, Permission.ORDERS_VIEW, allow=True)
    assert await services.auth.has_permission(user, Permission.ORDERS_VIEW)
    assert await repos.audit.count_by_action_prefix("admins.permission.override") == 1


async def test_super_admin_can_grant_dangerous_permission(services, super_admin, user) -> None:
    """الأدمن الأعلى يمنح الخطِرة عند الحاجة."""
    await services.auth.set_user_permission(super_admin, user.id, Permission.PAYMENTS_APPROVE, allow=True)
    assert await services.auth.has_permission(user, Permission.PAYMENTS_APPROVE)


async def test_unknown_permission_code_rejected(services, super_admin, user) -> None:
    """كود صلاحية غير معرَّف يُرفض بدل أن يُخزَّن بصمت."""
    with pytest.raises(ValidationError):
        await services.auth.set_user_permission(super_admin, user.id, "made.up.permission", allow=True)


# ================================== الحظر ================================== #


async def test_cannot_ban_self(db, repos, services, admin) -> None:
    """لا يحظر الأدمن نفسه."""
    with pytest.raises(ValidationError):
        await services.users.ban(admin, admin.id, "تجربة")
    assert await _events(repos, "self_ban_blocked") == 1
    assert not (await repos.users.get_by_id(admin.id)).is_banned


async def test_cannot_ban_super_admin(db, repos, services, admin, super_admin) -> None:
    """لا يُحظر الأدمن الأعلى مباشرة (حتى بمن يملك الصلاحية)."""
    with pytest.raises(ValidationError):
        await services.users.ban(admin, super_admin.id, "تجربة")
    assert not (await repos.users.get_by_id(super_admin.id)).is_banned
    assert await _events(repos, "super_admin_ban_blocked") == 1


async def test_admin_cannot_ban_peer_admin(db, repos, services, admin) -> None:
    """التسلسل الهرمي: لا يحظر الأدمن زميله."""
    peer = await _make(db, repos, 5005, "admin", "peer2")
    with pytest.raises(PermissionDeniedError):
        await services.users.ban(admin, peer.id, "تجربة")
    assert await _events(repos, "hierarchy_denied") == 1
    assert not (await repos.users.get_by_id(peer.id)).is_banned


async def test_admin_cannot_unban_peer_banned_by_super(db, repos, services, admin, super_admin) -> None:
    """أدمن عادي لا يلغي حظراً أوقعه الأدمن الأعلى على زميله."""
    peer = await _make(db, repos, 5007, "admin", "peer3")
    async with db.transaction() as tx:
        await repos.users.set_ban(tx, peer.id, banned=True, reason="تحقيق")
    with pytest.raises(PermissionDeniedError):
        await services.users.unban(admin, peer.id)
    assert (await repos.users.get_by_id(peer.id)).is_banned


async def test_admin_can_ban_regular_user(db, repos, services, admin, user) -> None:
    """المسار الطبيعي: أدمن يحظر مستخدماً عادياً."""
    await services.users.ban(admin, user.id, "مخالفة")
    assert (await repos.users.get_by_id(user.id)).is_banned


async def test_support_role_has_no_security_access(services, db, repos) -> None:
    """الدعم الفني لا يرى ولا يدير الأمان."""
    support = await _make(db, repos, 5006, "support", "agent")
    with pytest.raises(PermissionDeniedError):
        await services.security.counters(support)
    with pytest.raises(PermissionDeniedError):
        await services.security.clear_block(support, 123, None)
