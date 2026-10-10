"""اختبارات مهلة المحادثات، والتحقق المركزي من الإعدادات، وترحيل الأمان 0008 (المرحلة 9)."""

from __future__ import annotations

import pytest
from telegram.ext import ConversationHandler

from core.exceptions import ValidationError
from core.permissions import Permission
from handlers.common.conversation import (
    CONVERSATION_TIMEOUT_SECONDS,
    FLOW_DATA_KEYS,
    conversation,
    on_conversation_timeout,
)
from handlers.registry import build_handlers
from tests.telegram_fakes import FakeBot, FakeContext, make_message_update

pytestmark = pytest.mark.asyncio


# ============================== مهلة المحادثات ============================== #


def _all_conversations() -> list[ConversationHandler]:
    """كل المحادثات المسجَّلة فعلاً في التطبيق."""
    return [h for _group, h in build_handlers() if isinstance(h, ConversationHandler)]


async def test_every_conversation_has_uniform_timeout_and_timeout_state() -> None:
    """لا محادثة تشذّ عن السياسة: مهلة 15 دقيقة وحالة TIMEOUT مسجَّلة."""
    conversations = _all_conversations()
    assert len(conversations) == 32
    for handler in conversations:
        assert handler.conversation_timeout == CONVERSATION_TIMEOUT_SECONDS == 900, handler.name
        assert ConversationHandler.TIMEOUT in handler.states, f"{handler.name} بلا حالة TIMEOUT"
        assert handler.states[ConversationHandler.TIMEOUT], handler.name


async def test_conversation_factory_rejects_manual_timeout() -> None:
    """تمرير مهلة يدوية ممنوع حتى لا تتفاوت السياسة بين المحادثات."""
    with pytest.raises(ValueError):
        conversation(states={}, entry_points=[], fallbacks=[], conversation_timeout=5)


async def test_timeout_callback_clears_all_flow_data_and_notifies(services) -> None:
    """انتهاء المهلة يمسح بيانات كل المسارات ويُعلم المستخدم، ولا يمسّ بقية user_data."""
    bot = FakeBot()
    context = FakeContext(bot, services)
    for key in FLOW_DATA_KEYS:
        context.user_data[key] = {"pending": True}
    context.user_data["db_user"] = "keep-me"

    update = make_message_update(bot, text="متابعة", user_id=777)
    result = await on_conversation_timeout(update, context)

    assert result == ConversationHandler.END
    assert all(key not in context.user_data for key in FLOW_DATA_KEYS)
    assert context.user_data["db_user"] == "keep-me"
    assert "انتهت" in bot.last.text


# ============================== التحقق من الإعدادات ============================== #


async def test_settings_set_rejects_out_of_range_and_keeps_old_value(services, super_admin) -> None:
    """قيمة خارج النطاق ترفض وتبقى القيمة القديمة (لا تعطيل للحماية بصفر)."""
    before = await services.settings.get_int("rate_limit_actions_per_minute", 0)
    with pytest.raises(ValidationError):
        await services.settings.set("rate_limit_actions_per_minute", "0", admin_id=super_admin.id)
    with pytest.raises(ValidationError):
        await services.settings.set("rate_limit_actions_per_minute", "abc", admin_id=super_admin.id)
    assert await services.settings.get_int("rate_limit_actions_per_minute", 0) == before


async def test_settings_set_normalizes_hindi_digits_and_audits(services, repos, super_admin) -> None:
    """الأرقام الهندية تُطبَّع وتُدقَّق العملية بالقيمة قبل وبعد."""
    assert await services.settings.set("rate_limit_actions_per_minute", "٤٠", admin_id=super_admin.id)
    assert await services.settings.get_int("rate_limit_actions_per_minute", 0) == 40
    logs = await repos.audit.list_by_target("setting", "rate_limit_actions_per_minute")
    assert logs and "40" in (logs[0].after_json or "")


async def test_settings_min_max_deposit_order_is_enforced(services, super_admin) -> None:
    """الحد الأدنى للشحن لا يتجاوز الأعلى حتى لو كل قيمة صالحة وحدها."""
    await services.settings.set("max_deposit_units", "1000000", admin_id=super_admin.id)
    with pytest.raises(ValidationError):
        await services.settings.set("min_deposit_units", "2000000", admin_id=super_admin.id)


async def test_settings_listener_called_and_its_failure_does_not_break_save(services, super_admin) -> None:
    """المراقب يُستدعى بعد الحفظ، وفشله لا يُبطل التعديل ولا يخفي الخطأ (يُسجَّل)."""
    seen: list[tuple[str, str]] = []

    async def good(key: str, value: str) -> None:
        seen.append((key, value))

    async def bad(key: str, value: str) -> None:
        raise RuntimeError("مراقب معطوب")

    services.settings.add_listener(bad)
    services.settings.add_listener(good)
    assert await services.settings.set("bot_name", "متجري", admin_id=super_admin.id)
    assert seen == [("bot_name", "متجري")]
    assert await services.settings.get_str("bot_name", "") == "متجري"


async def test_settings_listener_not_called_on_rejected_value(services, super_admin) -> None:
    """القيمة المرفوضة لا تُبلَّغ للمراقبين."""
    calls: list[str] = []

    async def listener(key: str, value: str) -> None:
        calls.append(key)

    services.settings.add_listener(listener)
    with pytest.raises(ValidationError):
        await services.settings.set("admin_digest_hour", "99", admin_id=super_admin.id)
    assert calls == []


# ============================== ترحيل 0008 ============================== #


async def test_migration_0008_seeds_security_permissions_and_settings(db, repos) -> None:
    """الترحيل يزرع صلاحيتي الأمان وإعداداتها بالقيم الافتراضية الآمنة."""
    codes = {row["code"] for row in await repos.rbac.list_permissions()}
    assert {Permission.SECURITY_VIEW, Permission.SECURITY_MANAGE} <= codes

    admin_perms = await repos.rbac.role_permissions("admin")
    super_perms = await repos.rbac.role_permissions("super_admin")
    support_perms = await repos.rbac.role_permissions("support")
    assert Permission.SECURITY_VIEW in admin_perms and Permission.SECURITY_MANAGE not in admin_perms
    assert {Permission.SECURITY_VIEW, Permission.SECURITY_MANAGE} <= super_perms
    assert not ({Permission.SECURITY_VIEW, Permission.SECURITY_MANAGE} & support_perms)

    settings = await repos.settings.as_dict()
    assert settings["security_block_self_actions"] in {"true", "1"}
    assert settings["rate_limit_strikes_before_block"] == "5"
    assert int(settings["admin_adjust_max_units"]) > 0 and int(settings["admin_adjust_daily_max_units"]) > 0
    assert settings["error_alert_enabled"] in {"true", "1"}
