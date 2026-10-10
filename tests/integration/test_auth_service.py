"""
اختبارات الصلاحيات والحماية.

القاعدة المعتمدة: لا أدمن ثابت في الكود — كل شيء من قاعدة البيانات،
ويمكن منح أو منع أي صلاحية لمستخدم بعينه دون تغيير دوره.
"""

from __future__ import annotations

import pytest

from core.enums import Role
from core.exceptions import (
    MaintenanceModeError,
    PermissionDeniedError,
    UserBannedError,
)
from core.permissions import Permission
from database.database import Database
from database.models import User
from database.repositories import Repositories
from services import ServiceContainer


async def test_role_permissions_come_from_database(
    services: ServiceContainer, user: User, admin: User, super_admin: User
) -> None:
    """الصلاحيات تُقرأ من جدول الأدوار لا من ثوابت في الكود."""
    assert await services.auth.permissions_of(user) == set()
    assert await services.auth.has_permission(admin, Permission.ORDERS_VIEW)
    assert not await services.auth.has_permission(admin, Permission.ADMINS_MANAGE)
    assert await services.auth.has_permission(super_admin, Permission.ADMINS_MANAGE)


async def test_require_permission_records_denied_attempt(
    services: ServiceContainer, repos: Repositories, user: User
) -> None:
    """محاولة الوصول غير المصرّح بها تُرفض وتُسجَّل في سجل التدقيق."""
    with pytest.raises(PermissionDeniedError):
        await services.auth.require_permission(user, Permission.STATS_VIEW, context="dashboard")

    logs = await repos.audit.list_recent(limit=5)
    assert any(log.action == "security.permission_denied" for log in logs)


async def test_banned_user_is_blocked_everywhere(
    services: ServiceContainer, user: User, admin: User
) -> None:
    """المستخدم المحظور يُمنع من أي إجراء."""
    await services.users.ban(admin, user.id, reason="سلوك مسيء")
    banned = await services.users.get(user.id)
    assert banned is not None

    with pytest.raises(UserBannedError):
        await services.auth.guard(banned)

    await services.users.unban(admin, user.id)
    restored = await services.users.get(user.id)
    assert restored is not None
    await services.auth.guard(restored)  # لا يرفع استثناءً بعد رفع الحظر


async def test_maintenance_mode_blocks_users_not_admins(
    services: ServiceContainer, user: User, admin: User, super_admin: User
) -> None:
    """وضع الصيانة يوقف المستخدمين ويُبقي الأدمن قادراً على العمل."""
    await services.settings.set("maintenance_mode", True)

    with pytest.raises(MaintenanceModeError):
        await services.auth.guard(user)

    await services.auth.guard(admin)
    await services.auth.guard(super_admin)

    await services.settings.set("maintenance_mode", False)
    await services.auth.guard(user)


async def test_individual_permission_override(
    services: ServiceContainer, db: Database, repos: Repositories, super_admin: User
) -> None:
    """يمكن منح صلاحية واحدة لمستخدم عادي دون ترقيته إلى أدمن."""
    async with db.transaction() as tx:
        helper = await repos.users.create(tx, telegram_id=321321321, first_name="Helper")

    assert not await services.auth.has_permission(helper, Permission.TICKETS_REPLY)

    await services.auth.set_user_permission(
        super_admin, helper.id, Permission.TICKETS_REPLY, allow=True
    )
    assert await services.auth.has_permission(helper, Permission.TICKETS_REPLY)
    assert helper.role == Role.USER  # الدور لم يتغير

    await services.auth.clear_user_permission(super_admin, helper.id, Permission.TICKETS_REPLY)
    assert not await services.auth.has_permission(helper, Permission.TICKETS_REPLY)


async def test_deny_override_beats_role_permission(
    services: ServiceContainer, repos: Repositories, admin: User, super_admin: User
) -> None:
    """المنع الفردي يتقدّم على صلاحية الدور."""
    assert await services.auth.has_permission(admin, Permission.ORDERS_CANCEL)

    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.ORDERS_CANCEL, allow=False
    )
    refreshed = await repos.users.get_by_id(admin.id)
    assert refreshed is not None
    assert not await services.auth.has_permission(refreshed, Permission.ORDERS_CANCEL)


async def test_role_change_requires_super_admin(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, super_admin: User
) -> None:
    """ترقية المستخدمين صلاحية حصرية للأدمن الأعلى."""
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_role(admin, user.id, Role.ADMIN)

    assert await services.auth.set_role(super_admin, user.id, Role.SUPPORT)
    promoted = await repos.users.get_by_id(user.id)
    assert promoted is not None and promoted.role == Role.SUPPORT
    assert await services.auth.has_permission(promoted, Permission.TICKETS_REPLY)
    assert not await services.auth.has_permission(promoted, Permission.ORDERS_CANCEL)


async def test_support_role_scope(
    services: ServiceContainer, repos: Repositories, user: User, super_admin: User
) -> None:
    """دور الدعم يرى ولا يغيّر: لا اعتماد مدفوعات ولا تعديل أسعار."""
    await services.auth.set_role(super_admin, user.id, Role.SUPPORT)
    support = await repos.users.get_by_id(user.id)
    assert support is not None

    assert await services.auth.has_permission(support, Permission.TICKETS_VIEW)
    assert await services.auth.has_permission(support, Permission.PAYMENTS_VIEW)
    assert not await services.auth.has_permission(support, Permission.PAYMENTS_APPROVE)
    assert not await services.auth.has_permission(support, Permission.SERVICES_PRICE)


async def test_emergency_super_admin_list_is_isolated(
    db: Database, repos: Repositories, secret_box, user: User
) -> None:
    """قائمة الطوارئ في ملف البيئة لا تمنح صلاحيات بذاتها داخل المسارات العادية."""
    from services import build_services

    container = build_services(
        db, repos, secret_box=secret_box, super_admin_ids=(user.telegram_id,), settings_ttl_seconds=0
    )
    assert container.auth.is_emergency_super_admin(user.telegram_id)
    assert not await container.auth.has_permission(user, Permission.ADMIN_ACCESS)
