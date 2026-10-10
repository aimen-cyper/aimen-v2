"""
اختبارات أقسام: الكتالوج، الإعدادات، السجلات في لوحة التحكم.

النقاط المحروسة:
    • تغيير السعر يُحفظ، والبيع بخسارة يحتاج تأكيداً ثانياً.
    • إيقاف/أرشفة خدمة لا يحذفها ولا يكسر طلبات قائمة.
    • قيمة الإعداد تُطبَّع حسب نوعها (لا نص في حقل رقمي).
    • وضع الصيانة يمنع المستخدمين فعلاً ولا يمنع الأدمن.
    • السجلات للقراءة فقط وتعرض أحداثاً حقيقية.
"""

from __future__ import annotations

import pytest
from telegram.ext import ConversationHandler

from core.permissions import Permission
from database.models import Service, User
from database.repositories import Repositories
from handlers.admin import catalog, logs, settings as admin_settings
from keyboards.callback_data import pack
from services import ServiceContainer
from tests.integration.test_user_interface import (
    bot,  # noqa: F401
    context,  # noqa: F401
    load_user,
    press,
    write,
)
from tests.telegram_fakes import FakeBot, FakeContext

pytestmark = pytest.mark.asyncio


# ======================================================================== #
#                                الكتالوج                                  #
# ======================================================================== #


async def test_catalog_home_lists_categories(
    bot: FakeBot, context: FakeContext, admin: User, service: Service
) -> None:
    """شاشة الكتالوج تعرض التصنيفات وعدد الخدمات الفعّالة."""
    await load_user(bot, context, admin)
    await press(bot, context, catalog.catalog_home_screen, pack("ac", "home"), admin.telegram_id)

    assert any(button.startswith("ac:cat:") for button in bot.last.buttons)
    assert "الخدمات" in bot.last.text or "التصنيفات" in bot.last.text


async def test_service_card_and_toggle(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    service: Service,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """بطاقة الخدمة تعرض السعر والهامش، وزر الإيقاف يعمل فوراً ويُسجَّل."""
    await load_user(bot, context, admin)
    await press(
        bot, context, catalog.service_card_screen, pack("ac", "svc", service.id), admin.telegram_id
    )
    assert service.name in bot.last.text
    assert f"ac:toggle:{service.id}:v1" in bot.last.buttons

    await press(
        bot, context, catalog.toggle_service, pack("ac", "toggle", service.id), admin.telegram_id
    )
    stored = await repos.services.get(service.id)
    assert not stored.is_active, "لم تتوقف الخدمة بعد الضغط على زر التبديل"

    await press(
        bot, context, catalog.toggle_service, pack("ac", "toggle", service.id), admin.telegram_id
    )
    restored = await repos.services.get(service.id)
    assert restored.is_active, "لم تُعَد الخدمة للعمل"


async def test_price_change_is_saved_with_history(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    service: Service,
    repos: Repositories,
) -> None:
    """تغيير السعر يُحفظ ويُسجَّل في تاريخ الأسعار."""
    await load_user(bot, context, admin)
    state = await press(
        bot, context, catalog.start_price, pack("ac", "price", service.id), admin.telegram_id
    )
    assert state == catalog.ASK_PRICE

    state = await write(bot, context, catalog.receive_price, "2", admin.telegram_id)
    assert state == ConversationHandler.END

    stored = await repos.services.get(service.id)
    assert stored.price_per_1000_units == 20_000

    history = await repos.services.price_history(service.id, limit=5)
    assert history, "تغيير السعر بلا سجل تاريخي"


async def test_price_below_cost_needs_confirmation(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    service: Service,
    repos: Repositories,
) -> None:
    """سعر أقل من تكلفة المزود = بيع بخسارة ⇒ تأكيد ثانٍ إجباري."""
    await load_user(bot, context, admin)
    await press(bot, context, catalog.start_price, pack("ac", "price", service.id), admin.telegram_id)

    state = await write(bot, context, catalog.receive_price, "0.3", admin.telegram_id)
    assert state == catalog.CONFIRM_PRICE
    assert "flow:confirm:v1" in bot.last.buttons

    not_yet = await repos.services.get(service.id)
    assert not_yet.price_per_1000_units == 10_000, "طُبِّق السعر الخاسر قبل التأكيد"

    state = await press(bot, context, catalog.confirm_price, pack("flow", "confirm"), admin.telegram_id)
    assert state == ConversationHandler.END

    stored = await repos.services.get(service.id)
    assert stored.price_per_1000_units == 3_000


async def test_archive_service_requires_confirmation(
    bot: FakeBot,
    context: FakeContext,
    super_admin: User,
    service: Service,
    repos: Repositories,
) -> None:
    """الأرشفة إجراء خطير: تأكيد ثانٍ، ثم إخفاء الخدمة دون حذفها."""
    await load_user(bot, context, super_admin)
    state = await press(
        bot, context, catalog.start_archive, pack("ac", "archive", service.id), super_admin.telegram_id
    )
    assert state == catalog.CONFIRM_ARCHIVE
    assert "flow:confirm:v1" in bot.last.buttons

    state = await press(
        bot, context, catalog.confirm_archive, pack("flow", "confirm"), super_admin.telegram_id
    )
    assert state == ConversationHandler.END

    stored = await repos.services.get(service.id)
    assert stored is not None, "حُذفت الخدمة بدل أرشفتها"
    assert stored.is_archived


async def test_new_category_flow_with_skipped_emoji(
    bot: FakeBot,
    context: FakeContext,
    super_admin: User,
    repos: Repositories,
) -> None:
    """إنشاء تصنيف جديد مع تخطي الأيقونة ⇒ أيقونة افتراضية لا قيمة فارغة."""
    await load_user(bot, context, super_admin)
    state = await press(
        bot, context, catalog.start_new_category, pack("ac", "newcat"), super_admin.telegram_id
    )
    assert state == catalog.ASK_CATEGORY_NAME

    state = await write(bot, context, catalog.receive_category_name, "تيك توك", super_admin.telegram_id)
    assert state == catalog.ASK_CATEGORY_EMOJI
    assert "flow:skip:v1" in bot.last.buttons

    state = await press(
        bot, context, catalog.skip_category_emoji, pack("flow", "skip"), super_admin.telegram_id
    )
    assert state == ConversationHandler.END

    created = [item for item in await repos.categories.list_all(active_only=False) if item.name_ar == "تيك توك"]
    assert created, "لم يُنشأ التصنيف"
    assert created[0].emoji, "التصنيف بلا أيقونة"


async def test_catalog_write_actions_need_permission(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    super_admin: User,
    service: Service,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """سحب صلاحية تعديل السعر يمنع المحادثة من البدء."""
    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.SERVICES_PRICE, allow=False
    )
    await load_user(bot, context, admin)
    await press(bot, context, catalog.start_price, pack("ac", "price", service.id), admin.telegram_id)

    assert bot.answers[-1]["alert"] is True
    stored = await repos.services.get(service.id)
    assert stored.price_per_1000_units == 10_000


# ======================================================================== #
#                                الإعدادات                                 #
# ======================================================================== #


async def test_settings_home_and_group(
    bot: FakeBot, context: FakeContext, super_admin: User
) -> None:
    """شاشة الإعدادات تعرض المجموعات، وشاشة المجموعة تعرض مفاتيحها."""
    await load_user(bot, context, super_admin)
    await press(
        bot, context, admin_settings.settings_home_screen, pack("as", "home"), super_admin.telegram_id
    )
    group_buttons = [button for button in bot.last.buttons if button.startswith("as:group:")]
    assert group_buttons, "لا مجموعات إعدادات معروضة"

    await press(bot, context, admin_settings.settings_group_screen, group_buttons[0], super_admin.telegram_id)
    assert any(button.startswith("as:edit:") for button in bot.last.buttons), "لا مفاتيح للتعديل"


async def test_edit_integer_setting(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer
) -> None:
    """تعديل مفتاح رقمي يُحفظ ويُقرأ فوراً بالقيمة الجديدة."""
    await load_user(bot, context, super_admin)
    state = await press(
        bot,
        context,
        admin_settings.start_edit,
        pack("as", "edit", "order_check_interval_seconds"),
        super_admin.telegram_id,
    )
    assert state == admin_settings.ASK_VALUE

    state = await write(bot, context, admin_settings.receive_value, "300", super_admin.telegram_id)
    assert state == ConversationHandler.END
    assert await services.settings.get_int("order_check_interval_seconds") == 300


async def test_invalid_setting_value_is_refused(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer
) -> None:
    """نص غير رقمي في مفتاح من نوع int يُرفض ولا يفسد الإعداد."""
    before = await services.settings.get_int("order_check_interval_seconds")
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        admin_settings.start_edit,
        pack("as", "edit", "order_check_interval_seconds"),
        super_admin.telegram_id,
    )
    await write(bot, context, admin_settings.receive_value, "ليست رقماً", super_admin.telegram_id)

    assert await services.settings.get_int("order_check_interval_seconds") == before


async def test_maintenance_toggle_blocks_users_not_admins(
    bot: FakeBot,
    context: FakeContext,
    super_admin: User,
    user: User,
    services: ServiceContainer,
) -> None:
    """وضع الصيانة: تأكيد ⇒ تفعيل ⇒ المستخدم ممنوع والأدمن يعمل ⇒ إيقافه يعيد الوضع."""
    await load_user(bot, context, super_admin)
    state = await press(
        bot, context, admin_settings.start_maintenance, pack("as", "maint"), super_admin.telegram_id
    )
    assert state == admin_settings.CONFIRM_MAINTENANCE
    assert "flow:confirm:v1" in bot.last.buttons
    assert await services.settings.is_maintenance() is False, "فُعِّلت الصيانة قبل التأكيد"

    await press(
        bot, context, admin_settings.confirm_maintenance, pack("flow", "confirm"), super_admin.telegram_id
    )
    assert await services.settings.is_maintenance() is True

    from core.exceptions import MaintenanceModeError

    with pytest.raises(MaintenanceModeError):
        await services.auth.guard(user)
    await services.auth.guard(super_admin)  # الأدمن يستثنى من المنع

    await press(
        bot, context, admin_settings.start_maintenance, pack("as", "maint"), super_admin.telegram_id
    )
    await press(
        bot, context, admin_settings.confirm_maintenance, pack("flow", "confirm"), super_admin.telegram_id
    )
    assert await services.settings.is_maintenance() is False


async def test_maintenance_needs_dedicated_permission(
    bot: FakeBot, context: FakeContext, admin: User, super_admin: User, services: ServiceContainer
) -> None:
    """بلا صلاحية `settings.maintenance` لا يمكن تبديل وضع الصيانة."""
    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.SETTINGS_MAINTENANCE, allow=False
    )
    await load_user(bot, context, admin)
    await press(bot, context, admin_settings.start_maintenance, pack("as", "maint"), admin.telegram_id)

    assert bot.answers[-1]["alert"] is True
    assert await services.settings.is_maintenance() is False


# ======================================================================== #
#                                 السجلات                                  #
# ======================================================================== #


async def test_audit_screen_shows_real_actions(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    services: ServiceContainer,
) -> None:
    """سجل التدقيق يعرض عملية حقيقية جرت للتو (لا بيانات تجريبية)."""
    await services.users.set_note(admin, user.id, "ملاحظة لأجل السجل")
    await load_user(bot, context, admin)
    await press(bot, context, logs.audit_screen, pack("al", "audit", 1), admin.telegram_id)

    assert "note" in bot.last.text or "ملاحظة" in bot.last.text
    assert bot.last.buttons, "شاشة السجل بلا أزرار تنقل"


async def test_errors_screen_lists_logged_error(
    bot: FakeBot, context: FakeContext, admin: User, repos: Repositories
) -> None:
    """شاشة الأخطاء تعرض الأخطاء المسجَّلة فعلاً في قاعدة البيانات."""
    async with repos.db.transaction() as tx:
        await repos.error_logs.log(
            tx,
            error_type="ValueError",
            message="خطأ اختباري للعرض",
            traceback_snippet="line 1",
            source="tests",
        )
    await load_user(bot, context, admin)
    await press(bot, context, logs.errors_screen, pack("al", "errors", 1), admin.telegram_id)

    assert "خطأ اختباري للعرض" in bot.last.text or "ValueError" in bot.last.text


async def test_logs_are_read_only(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """شاشات السجلات لا تحتوي أي زر تعديل أو حذف — قراءة فقط."""
    await load_user(bot, context, admin)
    await press(bot, context, logs.logs_home_screen, pack("al", "home"), admin.telegram_id)

    for button in bot.last.buttons:
        assert not any(word in button for word in ("del", "edit", "clear")), (
            f"زر تعديل/حذف في شاشة سجلات للقراءة فقط: {button}"
        )
