"""
تغطية بقية شاشات العميل: القوائم، السجلات، الحالات الفارغة، والأوامر.

الهدف من هذا الملف: ألا يبقى أي معالج في الواجهة بلا استدعاء واحد على الأقل
في الاختبارات — فالمعالج غير المُستدعى هو مكمن أخطاء `AttributeError` الصامتة.
"""

from __future__ import annotations

import pytest

from core.enums import PaymentStatus
from database.models import Service, User
from handlers.common import errors, fallbacks, navigation
from handlers.user import catalog, deposit, orders, support, wallet
from keyboards.callback_data import pack
from services import ServiceContainer
from tests.integration.test_user_interface import load_user, press, write
from tests.telegram_fakes import FakeBot, FakeContext, make_message_update

pytestmark = pytest.mark.asyncio


@pytest.fixture
def bot() -> FakeBot:
    """بوت مزيّف لكل اختبار."""
    return FakeBot()


@pytest.fixture
def context(bot: FakeBot, services: ServiceContainer) -> FakeContext:
    """سياق مزيّف بالخدمات الحقيقية."""
    return FakeContext(bot, services)


# ============================ الأوامر النصية ============================= #


async def test_help_and_id_commands(bot: FakeBot, context: FakeContext, user: User) -> None:
    """/help يشرح الاستخدام، و/id يعرض معرف المستخدم الحقيقي."""
    await load_user(bot, context, user)

    update = make_message_update(bot, text="/help", user_id=user.telegram_id)
    await navigation.help_command(update, context)
    assert len(bot.last.text) > 40

    update = make_message_update(bot, text="/id", user_id=user.telegram_id)
    await navigation.id_command(update, context)
    assert str(user.telegram_id) in bot.last.text


async def test_cancel_command_outside_conversation(
    bot: FakeBot, context: FakeContext, user: User
) -> None:
    """/cancel خارج أي محادثة يطمئن المستخدم ويعيده للقائمة بدل الصمت."""
    await load_user(bot, context, user)
    update = make_message_update(bot, text="/cancel", user_id=user.telegram_id)
    await fallbacks.cancel_command(update, context)
    assert bot.last.buttons


async def test_unknown_command_and_free_text(
    bot: FakeBot, context: FakeContext, user: User
) -> None:
    """الأمر المجهول والنص الحر يُقابلان برد واضح وأزرار تنقل."""
    await load_user(bot, context, user)

    await fallbacks.unknown_command(
        make_message_update(bot, text="/nothing", user_id=user.telegram_id), context
    )
    assert bot.last.buttons

    await fallbacks.free_text(
        make_message_update(bot, text="السلام عليكم", user_id=user.telegram_id), context
    )
    assert bot.last.buttons


async def test_exit_conversation_fallback_clears_flow(
    bot: FakeBot, context: FakeContext, user: User
) -> None:
    """/start أثناء محادثة يُنهيها وينظّف بياناتها ويعرض القائمة."""
    from telegram.ext import ConversationHandler

    await load_user(bot, context, user)
    context.user_data["order_flow"] = {"service_id": 1}
    handler = fallbacks.exit_conversation("order_flow")

    result = await handler(
        make_message_update(bot, text="/start", user_id=user.telegram_id), context
    )
    assert result == ConversationHandler.END
    assert "order_flow" not in context.user_data


async def test_page_indicator_is_not_a_dead_button(
    bot: FakeBot, context: FakeContext, user: User
) -> None:
    """زر رقم الصفحة يرد بتلميح بدل أن يبدو معطلاً."""
    await load_user(bot, context, user)
    await press(
        bot, context, navigation.page_indicator_callback, pack("nav", "page", 2, 5), user.telegram_id
    )
    assert bot.answers, "زر الصفحة لم يرد على المستخدم"
    assert "2" in (bot.answers[-1]["text"] or "")


# =========================== الحالات الفارغة ============================= #


async def test_empty_screens_render_safely(
    bot: FakeBot, context: FakeContext, user: User
) -> None:
    """قوائم فارغة (خدمات/طلبات/سجل/إيداعات/تذاكر) تعرض رسالة وأزرار رجوع."""
    await load_user(bot, context, user)

    screens = [
        (catalog.categories_screen, pack("cat", "list", 1)),
        (orders.orders_list_screen, pack("ord", "list", "all", 1)),
        (wallet.history_screen, pack("wal", "history", 1)),
        (deposit.deposits_list_screen, pack("dep", "list", 1)),
        (support.tickets_list_screen, pack("sup", "list", 1)),
        (support.support_home, pack("sup", "home")),
    ]
    for handler, data in screens:
        bot.clear()
        await press(bot, context, handler, data, user.telegram_id)
        assert bot.last.text, f"{handler.__name__} عرض شاشة فارغة بلا نص"
        assert bot.last.buttons, f"{handler.__name__} شاشة بلا أي زر — طريق مسدود"


# ======================= قوائم فيها بيانات حقيقية ======================== #


async def test_orders_list_filters_and_card(
    bot: FakeBot,
    context: FakeContext,
    services: ServiceContainer,
    user: User,
    admin: User,
    mock_service: Service,
) -> None:
    """قائمة الطلبات تعرض الطلب، والتصفية تعمل، وبطاقة الطلب تفتح بتفاصيله."""
    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/list", quantity=1000
    )
    await load_user(bot, context, user)

    await press(bot, context, orders.orders_list_screen, pack("ord", "list", "all", 1), user.telegram_id)
    assert any(b.startswith("ord:view") for b in bot.last.buttons)

    await press(
        bot, context, orders.orders_list_screen, pack("ord", "list", "active", 1), user.telegram_id
    )
    assert any(b.startswith("ord:view") for b in bot.last.buttons)

    await press(
        bot, context, orders.orders_list_screen, pack("ord", "list", "done", 1), user.telegram_id
    )
    assert not any(b.startswith("ord:view") for b in bot.last.buttons)

    await press(
        bot, context, orders.order_card_screen, pack("ord", "view", order.id, "all", 1), user.telegram_id
    )
    assert order.public_code in bot.last.text
    assert any(b.startswith("sup:neworder") for b in bot.last.buttons), "بطاقة الطلب بلا زر دعم"


async def test_wallet_history_shows_transactions(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User
) -> None:
    """سجل العمليات يعرض الحركة المالية الحقيقية بعلامتها."""
    await services.wallet.adjust_balance(
        target=user, amount_units=30_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    await load_user(bot, context, user)
    await press(bot, context, wallet.history_screen, pack("wal", "history", 1), user.telegram_id)
    assert "3.00" in bot.last.text


async def test_deposits_list_and_cancel(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, payment_method
) -> None:
    """قائمة طلبات الشحن تعرض المعلّق مع زر إلغائه، والإلغاء يُنفَّذ فعلاً."""
    payment = await services.payments.create_payment(
        user, method_id=payment_method.id, raw_amount="20", transaction_reference="TRX-LIST-1"
    )
    await load_user(bot, context, user)

    await press(bot, context, deposit.deposits_list_screen, pack("dep", "list", 1), user.telegram_id)
    assert any(b.startswith("dep:cancel") for b in bot.last.buttons)

    await press(
        bot, context, deposit.cancel_payment, pack("dep", "cancel", payment.id), user.telegram_id
    )
    refreshed = await services.payments.get_for_user(user, payment.id)
    assert refreshed.status == PaymentStatus.CANCELLED


async def test_ticket_from_order_prefills_subject(
    bot: FakeBot,
    context: FakeContext,
    services: ServiceContainer,
    user: User,
    admin: User,
    mock_service: Service,
) -> None:
    """فتح تذكرة من بطاقة الطلب يتخطى السؤال عن التصنيف ويربطها بالطلب."""
    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/tkt", quantity=1000
    )
    await load_user(bot, context, user)

    state = await press(
        bot, context, support.start_ticket_for_order, pack("sup", "neworder", order.id), user.telegram_id
    )
    assert state == support.ASK_MESSAGE
    assert order.public_code in bot.last.text

    await write(bot, context, support.receive_ticket_message, "الطلب متوقف", user.telegram_id)
    tickets = await services.tickets.list_for_user(user, limit=5)
    assert len(tickets) == 1
    assert tickets[0].related_order_id == order.id


async def test_ticket_card_shows_conversation(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User
) -> None:
    """بطاقة التذكرة تعرض الرسائل وأزرار الرد والإغلاق."""
    ticket = await services.tickets.create_ticket(
        user, subject="استفسار", message="هل يمكن تعديل الرابط؟", category="other"
    )
    await load_user(bot, context, user)

    await press(bot, context, support.ticket_card_screen, pack("sup", "view", ticket.id), user.telegram_id)
    assert "استفسار" in bot.last.text
    assert any(b.startswith("sup:reply") for b in bot.last.buttons)
    assert any(b.startswith("sup:close") for b in bot.last.buttons)


# ============================ معالج الأخطاء ============================== #


async def test_error_handler_logs_and_informs_user(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, repos, user: User
) -> None:
    """خطأ غير متوقع: يُسجَّل في قاعدة البيانات ويُبلَّغ المستخدم برسالة مهذبة."""
    await load_user(bot, context, user)
    update = make_message_update(bot, text="أي نص", user_id=user.telegram_id)
    context.error = RuntimeError("انفجار اختباري")

    await errors.error_handler(update, context)

    stored = await repos.error_logs.list_recent(limit=5)
    assert stored, "الخطأ لم يُسجَّل في جدول error_logs"
    assert "انفجار اختباري" in stored[0]["message"]
    assert bot.sent, "المستخدم لم يُبلَّغ بأي شيء بعد الخطأ"


async def test_error_handler_treats_network_noise_as_external_warning(
    bot: FakeBot, context: FakeContext, repos, user: User
) -> None:
    """
    أعطال الشبكة المؤقتة (المرحلة 14): ليست «خطأ كود» ⇒ لا ERROR ولا تنبيه أدمن ولا إغراق للجدول
    (سجل WARNING واحد لكل فترة تهدئة)، والمستخدم يُبلَّغ بأن الحالة محفوظة وعليه إعادة المحاولة.
    """
    from telegram.error import TimedOut

    await load_user(bot, context, user)
    update = make_message_update(bot, text="أي نص", user_id=user.telegram_id)
    context.error = TimedOut()
    for _ in range(25):
        await errors.error_handler(update, context)

    stored = await repos.error_logs.list_recent(limit=50)
    assert len(stored) == 1 and stored[0]["level"] == "WARNING" and stored[0]["source"] == "telegram_network"
    assert "محفوظة" in bot.sent[0].text


async def test_error_handler_marks_blocked_user(
    bot: FakeBot, context: FakeContext, repos, user: User
) -> None:
    """حظر المستخدم للبوت يُعلَّم في قاعدة البيانات بدل تكرار محاولات الإرسال."""
    from telegram.error import Forbidden

    await load_user(bot, context, user)
    update = make_message_update(bot, text="أي نص", user_id=user.telegram_id)
    context.error = Forbidden("bot was blocked by the user")

    await errors.error_handler(update, context)

    refreshed = await repos.users.get_by_id(user.id)
    assert refreshed.blocked_bot == 1


# ========================= مسارات الإلغاء والتخطي ======================== #


async def test_cancel_order_flow_leaves_no_trace(
    bot: FakeBot,
    context: FakeContext,
    services: ServiceContainer,
    user: User,
    admin: User,
    mock_service: Service,
) -> None:
    """إلغاء مسار الطلب في منتصفه: لا طلب ولا خصم ولا بيانات محادثة متبقية."""
    from telegram.ext import ConversationHandler

    from handlers.user import order_flow

    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    await load_user(bot, context, user)

    await press(
        bot, context, order_flow.start_order, pack("new", "start", mock_service.id), user.telegram_id
    )
    await write(bot, context, order_flow.receive_link, "https://instagram.com/p/c", user.telegram_id)

    state = await press(
        bot, context, order_flow.cancel_order_flow, pack("flow", "cancel"), user.telegram_id
    )
    assert state == ConversationHandler.END
    assert order_flow.FLOW_KEY not in context.user_data
    assert await services.orders.count_for_user(user, statuses=()) == 0
    assert await services.wallet.balance_units(user.id) == 50_000
    assert bot.last.buttons, "شاشة الإلغاء بلا أزرار"


async def test_cancel_order_flow_by_command(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, mock_service: Service
) -> None:
    """الأمر /cancel داخل المحادثة يُنهيها كما يفعل الزر تماماً."""
    from telegram.ext import ConversationHandler

    from handlers.user import order_flow

    await load_user(bot, context, user)
    await press(
        bot, context, order_flow.start_order, pack("new", "start", mock_service.id), user.telegram_id
    )

    update = make_message_update(bot, text="/cancel", user_id=user.telegram_id)
    state = await order_flow.cancel_order_flow(update, context)
    assert state == ConversationHandler.END
    assert order_flow.FLOW_KEY not in context.user_data


async def test_skip_proof_when_optional(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, db, repos, user: User
) -> None:
    """طريقة دفع لا تطلب إثباتاً: زر «تخطي» ينقل المستخدم للملخص مباشرة."""
    async with db.transaction() as tx:
        method = await repos.payment_methods.create(
            tx,
            code="no_proof_wallet",
            name_ar="محفظة بلا إثبات",
            instructions_ar="حوّل فقط",
            requires_proof=0,
        )
    await load_user(bot, context, user)

    await press(bot, context, deposit.start_deposit, pack("dep", "start"), user.telegram_id)
    await press(bot, context, deposit.choose_method, pack("dep", "method", method.id), user.telegram_id)
    state = await write(bot, context, deposit.receive_amount, "15", user.telegram_id)

    assert state == deposit.CONFIRM, "طريقة بلا إثبات يجب أن تقفز للملخص مباشرة"
    assert any(b.startswith("flow:confirm") for b in bot.last.buttons)

    state = await press(
        bot, context, deposit.confirm_deposit, pack("flow", "confirm"), user.telegram_id
    )
    payments = await services.payments.list_for_user(user, limit=5)
    assert len(payments) == 1
    assert payments[0].amount_units == 150_000


async def test_cancel_support_flow(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User
) -> None:
    """إلغاء مسار التذكرة لا يترك تذكرة ولا بيانات محادثة."""
    from telegram.ext import ConversationHandler

    await load_user(bot, context, user)
    await press(bot, context, support.start_new_ticket, pack("sup", "new"), user.telegram_id)

    state = await press(
        bot, context, support.cancel_support_flow, pack("flow", "cancel"), user.telegram_id
    )
    assert state == ConversationHandler.END
    assert support.NEW_FLOW_KEY not in context.user_data
    assert await services.tickets.list_for_user(user, limit=5) == []


async def test_skip_proof_button_goes_to_summary(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, payment_method
) -> None:
    """زر «تخطي» في خطوة الإيصال ينتقل للملخص مع بقاء رقم العملية محفوظاً."""
    await load_user(bot, context, user)
    await press(bot, context, deposit.start_deposit, pack("dep", "start"), user.telegram_id)
    await press(
        bot, context, deposit.choose_method, pack("dep", "method", payment_method.id), user.telegram_id
    )
    await write(bot, context, deposit.receive_amount, "12", user.telegram_id)
    await write(bot, context, deposit.receive_reference, "TRX-SKIP-1", user.telegram_id)

    state = await press(bot, context, deposit.skip_proof, pack("flow", "skip"), user.telegram_id)
    assert state == deposit.CONFIRM
    assert any(b.startswith("flow:confirm") for b in bot.last.buttons)

    await press(bot, context, deposit.confirm_deposit, pack("flow", "confirm"), user.telegram_id)
    payments = await services.payments.list_for_user(user, limit=5)
    assert payments[0].transaction_reference == "TRX-SKIP-1"
    assert payments[0].proof_file_id is None
