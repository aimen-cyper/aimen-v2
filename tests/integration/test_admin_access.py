"""
اختبارات بوابة لوحة التحكم: من يدخل؟ وماذا يرى؟ وماذا يُسجَّل عند الرفض؟

هذه الاختبارات هي الدليل العملي على أن قاعدة «الصلاحية تُفحص على الـcallback
نفسه» مطبَّقة فعلاً، لا على مستوى إخفاء الأزرار فقط.
"""

from __future__ import annotations

import pytest

from core.permissions import Permission
from database.models import User
from database.repositories import Repositories
from handlers.admin import dashboard, logs, settings, users
from handlers.common import navigation
from keyboards.callback_data import pack
from services import ServiceContainer
from tests.integration.test_user_interface import (  # إعادة استخدام أدوات الواجهة نفسها
    bot,  # noqa: F401
    context,  # noqa: F401
    load_user,
    press,
)
from tests.telegram_fakes import FakeBot, FakeContext

pytestmark = pytest.mark.asyncio


async def test_normal_user_cannot_open_panel(
    bot: FakeBot, context: FakeContext, user: User, repos: Repositories
) -> None:
    """مستخدم عادي يضغط زر لوحة التحكم ⇐ رفض واضح + تسجيل أمني."""
    await load_user(bot, context, user)
    await press(bot, context, dashboard.panel_screen, pack("adm", "home"), user.telegram_id)

    assert bot.answers[-1]["alert"] is True
    assert "صلاحية" in (bot.answers[-1]["text"] or "")
    denied = await repos.audit.list_recent(limit=5)
    assert any(entry.action == "security.permission_denied" for entry in denied), (
        "محاولة الوصول المرفوضة لم تُسجَّل في سجل التدقيق"
    )


async def test_admin_sees_panel_with_sections(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """الأدمن يرى لوحة التحكم بأقسامها وبأرقام حقيقية."""
    await load_user(bot, context, admin)
    await press(bot, context, dashboard.panel_screen, pack("adm", "home"), admin.telegram_id)

    assert bot.last.kind == "edit"
    assert "لوحة التحكم" in bot.last.text
    assert "au:home:v1" in bot.last.buttons
    assert "ap:list:pend:1:v1" in bot.last.buttons
    assert "ao:list:att:1:v1" in bot.last.buttons


async def test_panel_hides_sections_without_permission(
    bot: FakeBot, context: FakeContext, db, repos: Repositories, services: ServiceContainer
) -> None:
    """أدمن دعم فني يرى ما يخصّه فقط — لا إعدادات ولا سجلات."""
    async with db.transaction() as tx:
        support_admin = await repos.users.create(
            tx, telegram_id=555_111, username="supporter", first_name="Supp", role="support"
        )
    await load_user(bot, context, support_admin)
    await press(
        bot, context, dashboard.panel_screen, pack("adm", "home"), support_admin.telegram_id
    )

    buttons = bot.last.buttons
    assert "at:list:open:1:v1" in buttons, "أدمن الدعم لا يرى قسم التذاكر"
    assert "as:home:v1" not in buttons, "ظهر قسم الإعدادات لمن لا يملك صلاحيته"
    assert "al:home:v1" not in buttons, "ظهر قسم السجلات لمن لا يملك صلاحيته"


async def test_section_blocked_even_if_button_pressed_directly(
    bot: FakeBot, context: FakeContext, db, repos: Repositories
) -> None:
    """الضغط المباشر على زر قسم محجوب يُرفض — إخفاء الزر ليس هو الحماية."""
    async with db.transaction() as tx:
        support_admin = await repos.users.create(
            tx, telegram_id=555_112, username="supporter2", first_name="Supp", role="support"
        )
    await load_user(bot, context, support_admin)
    await press(
        bot,
        context,
        settings.settings_home_screen,
        pack("as", "home"),
        support_admin.telegram_id,
    )
    assert bot.answers[-1]["alert"] is True
    assert not bot.sent, "عُرضت شاشة الإعدادات لمن لا يملك صلاحيتها"


async def test_permission_revoked_mid_session_blocks_action(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    super_admin: User,
    services: ServiceContainer,
) -> None:
    """سحب الصلاحية أثناء الجلسة يُغلق الزر فوراً حتى لو كان معروضاً."""
    await load_user(bot, context, admin)
    await press(bot, context, logs.audit_screen, pack("al", "audit", 1), admin.telegram_id)
    assert bot.last.kind == "edit"

    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.LOGS_VIEW, allow=False
    )
    bot.clear()
    await press(bot, context, logs.audit_screen, pack("al", "audit", 1), admin.telegram_id)
    assert bot.answers[-1]["alert"] is True
    assert not bot.sent, "شاشة السجلات ظهرت بعد سحب الصلاحية"


async def test_main_menu_shows_panel_button_for_admin_only(
    bot: FakeBot, context: FakeContext, admin: User, user: User
) -> None:
    """زر «🛠 لوحة التحكم» يظهر في القائمة الرئيسية للأدمن فقط."""
    await load_user(bot, context, admin)
    await press(bot, context, navigation.home_callback, pack("nav", "home"), admin.telegram_id)
    assert "adm:home:v1" in bot.last.buttons

    other = FakeContext(bot, context.bot_data["services"])
    bot.clear()
    await load_user(bot, other, user)
    await press(bot, other, navigation.home_callback, pack("nav", "home"), user.telegram_id)
    assert "adm:home:v1" not in bot.last.buttons


async def test_admin_command_opens_panel(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """الأمر /admin يفتح اللوحة لمن يملك صلاحية الدخول."""
    await load_user(bot, context, admin)
    from tests.integration.test_user_interface import write

    await write(bot, context, dashboard.admin_command, "/admin", admin.telegram_id)
    assert "لوحة التحكم" in bot.last.text
    assert bot.last.buttons


async def test_health_screen_requires_stats_permission(
    bot: FakeBot, context: FakeContext, admin: User, super_admin: User, services: ServiceContainer
) -> None:
    """شاشة صحة النظام تحتاج `stats.view` تحديداً."""
    await load_user(bot, context, admin)
    await press(bot, context, dashboard.health_screen, pack("adm", "health"), admin.telegram_id)
    assert "صحة النظام" in bot.last.text

    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.STATS_VIEW, allow=False
    )
    bot.clear()
    await press(bot, context, dashboard.health_screen, pack("adm", "health"), admin.telegram_id)
    assert bot.answers[-1]["alert"] is True
    assert not bot.sent


async def test_panel_without_stats_still_opens(
    bot: FakeBot, context: FakeContext, admin: User, super_admin: User, services: ServiceContainer
) -> None:
    """من لا يملك `stats.view` يدخل اللوحة بلا أرقام بدل أن يُمنع منها."""
    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.STATS_VIEW, allow=False
    )
    await load_user(bot, context, admin)
    await press(bot, context, dashboard.panel_screen, pack("adm", "home"), admin.telegram_id)

    assert "لوحة التحكم" in bot.last.text
    assert "المستخدمون:" not in bot.last.text
    assert bot.last.buttons, "اللوحة بلا أزرار"


async def test_users_screen_shows_real_counters(
    bot: FakeBot, context: FakeContext, admin: User, user: User
) -> None:
    """شاشة المستخدمين تعرض عدّادات حقيقية من قاعدة البيانات."""
    await load_user(bot, context, admin)
    await press(bot, context, users.users_home_screen, pack("au", "home"), admin.telegram_id)
    assert "الإجمالي: 2" in bot.last.text
    assert "au:search:v1" in bot.last.buttons
