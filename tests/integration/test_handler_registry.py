"""
اختبارات تسجيل المعالجات على تطبيق PTB حقيقي (بلا اتصال بالشبكة).

ما الذي يُثبته هذا الملف؟
    • كل المعالجات تُسجَّل في المجموعات الصحيحة وبالترتيب الصحيح.
    • التحديث يصل للمعالج المقصود لا لغيره (نختبر `check_update` مباشرة).
    • الطبقة الوسيطة تسبق الجميع، والمسار الاحتياطي يأتي أخيراً فلا يبتلع
      زراً صحيحاً.
"""

from __future__ import annotations

import pytest
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    TypeHandler,
)

from handlers.registry import MAIN_GROUP, MIDDLEWARE_GROUP, build_handlers, register_handlers
from keyboards.callback_data import pack
from tests.telegram_fakes import FakeBot, make_callback_update, make_message_update

#: توكن شكلي صالح البنية — لا يُستخدم في أي اتصال فعلي
DUMMY_TOKEN = "123456789:AAEssentialDummyTokenForLocalTestsOnly"


@pytest.fixture
def bot() -> FakeBot:
    """بوت مزيّف لبناء التحديثات."""
    return FakeBot()


def test_middleware_is_registered_first() -> None:
    """الطبقة الوسيطة وحدها في المجموعة -10 قبل كل المعالجات."""
    handlers = build_handlers()
    group, handler = handlers[0]
    assert group == MIDDLEWARE_GROUP
    assert isinstance(handler, TypeHandler)
    assert all(group == MAIN_GROUP for group, _ in handlers[1:])


def test_conversations_registered_before_global_commands() -> None:
    """المحادثات تسبق /start العام حتى تلتقط أوامر الخروج أثناء المحادثة."""
    handlers = [handler for _group, handler in build_handlers()]
    first_command = next(
        index for index, handler in enumerate(handlers) if isinstance(handler, CommandHandler)
    )
    last_conversation = max(
        index for index, handler in enumerate(handlers) if isinstance(handler, ConversationHandler)
    )
    assert last_conversation < first_command


def test_catch_all_handlers_are_last() -> None:
    """المعالج الشامل للأزرار والنصوص في آخر القائمة (شبكة أمان لا حاجز)."""
    handlers = [handler for _group, handler in build_handlers()]
    catch_all_callback = next(
        index
        for index, handler in enumerate(handlers)
        if isinstance(handler, CallbackQueryHandler) and handler.pattern is None
    )
    specific_callbacks = [
        index
        for index, handler in enumerate(handlers)
        if isinstance(handler, CallbackQueryHandler) and handler.pattern is not None
    ]
    assert catch_all_callback > max(specific_callbacks)
    assert isinstance(handlers[-1], MessageHandler)


def test_register_handlers_on_real_application() -> None:
    """التسجيل على تطبيق PTB حقيقي ينجح ويضع كل معالج في مجموعته."""
    application = ApplicationBuilder().token(DUMMY_TOKEN).build()
    count = register_handlers(application)

    assert count == len(build_handlers())
    assert len(application.handlers[MIDDLEWARE_GROUP]) == 1
    assert len(application.handlers[MAIN_GROUP]) == count - 1
    assert application.error_handlers, "لم يُسجَّل معالج الأخطاء العام"


@pytest.mark.parametrize(
    ("callback_data", "expected_module"),
    [
        (pack("nav", "home"), "handlers.common.navigation"),
        (pack("cat", "list", 1), "handlers.user.catalog"),
        (pack("cat", "svc", 3, 1, 1), "handlers.user.catalog"),
        (pack("ord", "list", "all", 1), "handlers.user.orders"),
        (pack("ord", "cancel", 5), "handlers.user.orders"),
        (pack("ord", "cancelyes", 5), "handlers.user.orders"),
        (pack("wal", "history", 2), "handlers.user.wallet"),
        (pack("dep", "list", 1), "handlers.user.deposit"),
        (pack("sup", "view", 4), "handlers.user.support"),
        (pack("acc", "notif", 1), "handlers.user.account"),
    ],
)
def test_button_reaches_expected_handler(
    bot: FakeBot, callback_data: str, expected_module: str
) -> None:
    """كل زر يلتقطه المعالج المقصود لا معالجاً آخر سبقه في الترتيب."""
    update = make_callback_update(bot, data=callback_data, user_id=4242)
    claimed: list[str] = []

    for _group, handler in build_handlers():
        if isinstance(handler, TypeHandler):
            continue                                   # الطبقة الوسيطة تلتقط كل شيء بطبيعتها
        if handler.check_update(update) is not False and handler.check_update(update) is not None:
            callback = getattr(handler, "callback", None)
            if callback is not None:
                claimed.append(callback.__module__)
                break

    assert claimed and claimed[0] == expected_module, (
        f"الزر {callback_data} التقطه {claimed or 'لا أحد'} بدل {expected_module}"
    )


def test_order_cancel_and_cancelyes_are_distinct(bot: FakeBot) -> None:
    """تأكيد الإلغاء وتنفيذه زران مختلفان ولا يتداخل نمطاهما."""
    from handlers.registry import screen_handlers

    confirm_update = make_callback_update(bot, data=pack("ord", "cancel", 9), user_id=1)
    execute_update = make_callback_update(bot, data=pack("ord", "cancelyes", 9), user_id=1)

    matched_confirm = [
        handler.callback.__name__
        for handler in screen_handlers()
        if handler.check_update(confirm_update)
    ]
    matched_execute = [
        handler.callback.__name__
        for handler in screen_handlers()
        if handler.check_update(execute_update)
    ]
    assert matched_confirm == ["order_cancel_confirm"]
    assert matched_execute == ["order_cancel_execute"]


def test_free_text_outside_conversation_hits_fallback(bot: FakeBot) -> None:
    """نص حر خارج المحادثات يصل لمعالج الرسائل الاحتياطي لا لشيء آخر."""
    update = make_message_update(bot, text="مرحبا كيف أطلب؟", user_id=777)
    matched = [
        handler.callback.__name__
        for _group, handler in build_handlers()
        if isinstance(handler, MessageHandler) and handler.check_update(update)
    ]
    assert matched == ["free_text"]


def test_unknown_command_hits_its_handler(bot: FakeBot) -> None:
    """أمر غير معروف يصل لمعالج الأوامر المجهولة لا لمعالج النصوص."""
    update = make_message_update(bot, text="/whatever", user_id=777)
    matched = [
        handler.callback.__name__
        for _group, handler in build_handlers()
        if isinstance(handler, MessageHandler) and handler.check_update(update)
    ]
    assert matched[0] == "unknown_command"


def test_known_commands_are_registered(bot: FakeBot) -> None:
    """الأوامر المعلنة للمستخدم (/start /help /id /cancel) كلها مسجَّلة فعلاً."""
    from main import BOT_COMMANDS

    registered = {
        tuple(handler.commands)[0]
        for _group, handler in build_handlers()
        if isinstance(handler, CommandHandler) and handler.commands
    }
    for command in BOT_COMMANDS:
        assert command.command in registered, f"الأمر /{command.command} معلن بلا معالج"
