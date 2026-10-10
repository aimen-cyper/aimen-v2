"""
اختبارات واجهة العميل: من ضغطة الزر إلى أثرها في قاعدة البيانات.

لا شبكة ولا `Application` حقيقي: نبني تحديثات `telegram.Update` حقيقية،
ونمرّرها للمعالجات مباشرة مع بوت مزيّف يسجّل النصوص والأزرار، وقاعدة بيانات
مؤقتة حقيقية. أي خلل في النص أو الأزرار أو الأثر المالي يظهر هنا.
"""

from __future__ import annotations

import pytest
from telegram.ext import ApplicationHandlerStop, ConversationHandler

from core.enums import OrderStatus, PaymentStatus
from database.models import Service, User
from database.repositories import Repositories
from handlers.common import fallbacks, navigation
from handlers.user import account, catalog, deposit, order_flow, orders, support, wallet
from keyboards.callback_data import pack
from middlewares.context import USER_KEY, UserContextMiddleware
from middlewares.rate_limit import RateLimiter
from services import ServiceContainer
from tests.telegram_fakes import (
    FakeBot,
    FakeContext,
    make_callback_update,
    make_message_update,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def bot() -> FakeBot:
    """بوت مزيّف جديد لكل اختبار."""
    return FakeBot()


@pytest.fixture
def context(bot: FakeBot, services: ServiceContainer) -> FakeContext:
    """سياق مزيّف محقون بالخدمات الحقيقية على قاعدة بيانات مؤقتة."""
    return FakeContext(bot, services)


async def run_middleware(bot: FakeBot, context: FakeContext, update) -> bool:
    """
    تمرير التحديث عبر الطبقة الوسيطة كما يحدث في التشغيل الحقيقي.

    المخرجات: True إذا سُمح بمتابعة المعالجة، False إذا أوقفتها الطبقة.
    """
    middleware = UserContextMiddleware(RateLimiter())
    try:
        await middleware(update, context)
    except ApplicationHandlerStop:
        return False
    return True


async def press(bot: FakeBot, context: FakeContext, handler, data: str, user_id: int):
    """محاكاة ضغطة زر: بناء التحديث ثم استدعاء المعالج مباشرة."""
    update = make_callback_update(bot, data=data, user_id=user_id)
    context.user_data.setdefault("db_user", context.user_data.get(USER_KEY))
    return await handler(update, context)


async def write(bot: FakeBot, context: FakeContext, handler, text: str, user_id: int, *, photo: bool = False):
    """محاكاة إرسال المستخدم رسالة نصية (أو صورة)."""
    update = make_message_update(bot, text=text, user_id=user_id, photo=photo)
    return await handler(update, context)


async def load_user(bot: FakeBot, context: FakeContext, user: User) -> None:
    """تحميل المستخدم في السياق عبر الطبقة الوسيطة (كما في التشغيل الفعلي)."""
    update = make_message_update(bot, text="/start", user_id=user.telegram_id)
    allowed = await run_middleware(bot, context, update)
    assert allowed, "الطبقة الوسيطة رفضت مستخدماً عادياً"
    bot.clear()


# ======================================================================== #
#                            الشاشة الأولى والتنقل                          #
# ======================================================================== #


async def test_start_registers_user_and_shows_menu(
    bot: FakeBot, context: FakeContext, services: ServiceContainer
) -> None:
    """أول /start ينشئ المستخدم ويعرض القائمة الرئيسية بأزرارها السبعة."""
    update = make_message_update(bot, text="/start", user_id=55_001)
    assert await run_middleware(bot, context, update)
    await navigation.start_command(update, context)

    created = await services.users.get_by_telegram(55_001)
    assert created is not None
    assert bot.last.kind == "send"
    assert len(bot.last.buttons) == 8            # + «📖 التعليمات»
    assert "cat:list:1:v1" in bot.last.buttons
    assert "wal:home::v1" in bot.last.buttons or "wal:home:v1" in bot.last.buttons


async def test_home_button_edits_same_message(
    bot: FakeBot, context: FakeContext, user: User
) -> None:
    """زر «الرئيسية» يحرّر نفس الرسالة بدل إرسال رسالة جديدة."""
    await load_user(bot, context, user)
    await press(bot, context, navigation.home_callback, pack("nav", "home"), user.telegram_id)
    assert bot.last.kind == "edit"
    assert bot.answers, "لم يُرد البوت على ضغطة الزر — سيبقى المؤشر يدور عند المستخدم"


async def test_unknown_button_does_not_fail_silently(
    bot: FakeBot, context: FakeContext, user: User
) -> None:
    """زر قديم/غير معروف يُقابَل برسالة واضحة وبالقائمة الرئيسية."""
    await load_user(bot, context, user)
    await press(bot, context, fallbacks.unknown_callback, "zz:gone:1:v9", user.telegram_id)
    assert bot.answers[-1]["alert"] is True
    assert bot.last.buttons, "رسالة الزر المجهول بلا أزرار — المستخدم يصل لطريق مسدود"


# ======================================================================== #
#                          تصفح الخدمات وبطاقة الخدمة                       #
# ======================================================================== #


async def test_catalog_screens(
    bot: FakeBot, context: FakeContext, user: User, mock_service: Service
) -> None:
    """التصنيفات ← الخدمات ← بطاقة الخدمة: كل شاشة تعرض أزرار الانتقال التالية."""
    await load_user(bot, context, user)

    await press(bot, context, catalog.categories_screen, pack("cat", "list", 1), user.telegram_id)
    category_buttons = [b for b in bot.last.buttons if b.startswith("cat:open")]
    assert category_buttons, "لا تصنيفات معروضة رغم وجود خدمة متاحة"

    await press(bot, context, catalog.services_screen, category_buttons[0], user.telegram_id)
    service_buttons = [b for b in bot.last.buttons if b.startswith("cat:svc")]
    assert service_buttons

    await press(bot, context, catalog.service_card_screen, service_buttons[0], user.telegram_id)
    assert mock_service.name in bot.last.text
    assert any(b.startswith("new:start") for b in bot.last.buttons), "بطاقة الخدمة بلا زر طلب"


# ======================================================================== #
#                              مسار الطلب الكامل                            #
# ======================================================================== #


async def test_order_flow_happy_path(
    bot: FakeBot,
    context: FakeContext,
    services: ServiceContainer,
    user: User,
    admin: User,
    mock_service: Service,
) -> None:
    """طلب كامل: رابط ← كمية ← ملخص ← تأكيد ⇒ طلب في القاعدة ورصيد مخصوم."""
    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    await load_user(bot, context, user)

    state = await press(
        bot, context, order_flow.start_order, pack("new", "start", mock_service.id), user.telegram_id
    )
    assert state == order_flow.ASK_LINK
    assert any(b.startswith("flow:cancel") for b in bot.last.buttons), "خطوة بلا زر إلغاء"

    state = await write(
        bot, context, order_flow.receive_link, "https://instagram.com/p/abc", user.telegram_id
    )
    assert state == order_flow.ASK_QUANTITY

    state = await write(bot, context, order_flow.receive_quantity, "1000", user.telegram_id)
    assert state == order_flow.CONFIRM
    summary = bot.last.text
    assert "1000" in summary
    assert any(b.startswith("flow:confirm") for b in bot.last.buttons)

    state = await press(
        bot, context, order_flow.confirm_order, pack("flow", "confirm"), user.telegram_id
    )
    assert state == ConversationHandler.END

    created = await services.orders.list_for_user(user, statuses=())
    assert len(created) == 1
    assert created[0].quantity == 1000
    assert created[0].status == OrderStatus.PENDING
    assert await services.wallet.balance_units(user.id) == 40_000
    assert order_flow.FLOW_KEY not in context.user_data, "بيانات المحادثة لم تُنظَّف"


async def test_order_flow_double_confirm_creates_one_order(
    bot: FakeBot,
    context: FakeContext,
    services: ServiceContainer,
    user: User,
    admin: User,
    mock_service: Service,
) -> None:
    """الضغط المزدوج على «تأكيد» لا ينشئ طلبين (client_request_id ثابت للمحادثة)."""
    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    await load_user(bot, context, user)

    await press(
        bot, context, order_flow.start_order, pack("new", "start", mock_service.id), user.telegram_id
    )
    await write(bot, context, order_flow.receive_link, "https://instagram.com/p/abc", user.telegram_id)
    await write(bot, context, order_flow.receive_quantity, "1000", user.telegram_id)

    flow = dict(context.user_data[order_flow.FLOW_KEY])
    await press(bot, context, order_flow.confirm_order, pack("flow", "confirm"), user.telegram_id)
    context.user_data[order_flow.FLOW_KEY] = flow        # محاكاة ضغطة ثانية على نفس الرسالة
    await press(bot, context, order_flow.confirm_order, pack("flow", "confirm"), user.telegram_id)

    created = await services.orders.list_for_user(user, statuses=())
    assert len(created) == 1, "تكرّر الطلب عند الضغط المزدوج"
    assert await services.wallet.balance_units(user.id) == 40_000


async def test_order_flow_insufficient_balance_offers_topup(
    bot: FakeBot,
    context: FakeContext,
    services: ServiceContainer,
    user: User,
    mock_service: Service,
) -> None:
    """رصيد غير كافٍ ⇒ عرض المبلغ الناقص وزر شحن مباشر، بلا إنشاء طلب."""
    await load_user(bot, context, user)

    await press(
        bot, context, order_flow.start_order, pack("new", "start", mock_service.id), user.telegram_id
    )
    await write(bot, context, order_flow.receive_link, "https://instagram.com/p/abc", user.telegram_id)
    state = await write(bot, context, order_flow.receive_quantity, "1000", user.telegram_id)

    assert state == ConversationHandler.END
    assert "الناقص" in bot.last.text
    assert any(b.startswith("dep:start") for b in bot.last.buttons), "لا زر شحن عند نقص الرصيد"
    assert await services.orders.count_for_user(user, statuses=()) == 0


async def test_order_flow_rejects_bad_quantity_and_keeps_step(
    bot: FakeBot,
    context: FakeContext,
    services: ServiceContainer,
    user: User,
    admin: User,
    mock_service: Service,
) -> None:
    """كمية خارج الحدود: رسالة خطأ والبقاء في نفس الخطوة (لا إسقاط للمحادثة)."""
    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    await load_user(bot, context, user)
    await press(
        bot, context, order_flow.start_order, pack("new", "start", mock_service.id), user.telegram_id
    )
    await write(bot, context, order_flow.receive_link, "https://instagram.com/p/abc", user.telegram_id)

    state = await write(bot, context, order_flow.receive_quantity, "5", user.telegram_id)
    assert state is None, "الحارس يُبقي المستخدم في نفس خطوة المحادثة"
    assert "❌" in bot.last.text
    assert await services.orders.count_for_user(user, statuses=()) == 0


async def test_order_cancel_by_user_refunds(
    bot: FakeBot,
    context: FakeContext,
    services: ServiceContainer,
    user: User,
    admin: User,
    mock_service: Service,
) -> None:
    """إلغاء المستخدم لطلب لم يُرسل بعد ⇒ استرجاع كامل موثّق في المحفظة."""
    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/x", quantity=1000
    )
    await load_user(bot, context, user)

    await press(
        bot, context, orders.order_cancel_confirm, pack("ord", "cancel", order.id), user.telegram_id
    )
    assert any(b.startswith("ord:cancelyes") for b in bot.last.buttons)

    await press(
        bot, context, orders.order_cancel_execute, pack("ord", "cancelyes", order.id), user.telegram_id
    )
    refreshed = await services.orders.get_for_user(user, order.id)
    assert refreshed.status in {OrderStatus.CANCELED, OrderStatus.REFUNDED}
    assert await services.wallet.balance_units(user.id) == 50_000


# ======================================================================== #
#                            المحفظة وطلبات الشحن                          #
# ======================================================================== #


async def test_wallet_screen_shows_balance(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User
) -> None:
    """شاشة المحفظة تعرض الرصيد الحقيقي من قاعدة البيانات."""
    await services.wallet.adjust_balance(
        target=user, amount_units=25_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    await load_user(bot, context, user)
    await press(bot, context, wallet.wallet_screen, pack("wal", "home"), user.telegram_id)
    assert "2.50" in bot.last.text
    assert any(b.startswith("dep:start") for b in bot.last.buttons)


async def test_deposit_flow_creates_pending_payment(
    bot: FakeBot,
    context: FakeContext,
    services: ServiceContainer,
    user: User,
    payment_method,
) -> None:
    """مسار الشحن ينشئ طلباً «بانتظار المراجعة» ولا يضيف رصيداً إطلاقاً."""
    await load_user(bot, context, user)
    balance_before = await services.wallet.balance_units(user.id)

    state = await press(bot, context, deposit.start_deposit, pack("dep", "start"), user.telegram_id)
    assert state == deposit.CHOOSE_METHOD
    method_buttons = [b for b in bot.last.buttons if b.startswith("dep:method")]
    assert method_buttons, "لا طرق دفع معروضة"

    state = await press(bot, context, deposit.choose_method, method_buttons[0], user.telegram_id)
    assert state == deposit.ASK_AMOUNT

    state = await write(bot, context, deposit.receive_amount, "10", user.telegram_id)
    assert state == deposit.ASK_REFERENCE

    state = await write(bot, context, deposit.receive_reference, "TRX-99887", user.telegram_id)
    assert state == deposit.ASK_PROOF

    state = await write(bot, context, deposit.receive_proof, "", user.telegram_id, photo=True)
    assert state == deposit.CONFIRM

    state = await press(
        bot, context, deposit.confirm_deposit, pack("flow", "confirm"), user.telegram_id
    )
    assert state == ConversationHandler.END

    payments = await services.payments.list_for_user(user, limit=10)
    assert len(payments) == 1
    assert payments[0].status == PaymentStatus.PENDING
    assert payments[0].amount_units == 100_000
    assert await services.wallet.balance_units(user.id) == balance_before, "الشحن غيّر الرصيد قبل الاعتماد"


async def test_deposit_cancel_keeps_nothing(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, payment_method
) -> None:
    """إلغاء مسار الشحن لا يترك أي طلب شحن ولا بيانات محادثة."""
    await load_user(bot, context, user)
    await press(bot, context, deposit.start_deposit, pack("dep", "start"), user.telegram_id)
    state = await press(
        bot, context, deposit.cancel_deposit_flow, pack("flow", "cancel"), user.telegram_id
    )
    assert state == ConversationHandler.END
    assert deposit.FLOW_KEY not in context.user_data
    assert await services.payments.list_for_user(user, limit=10) == []


# ======================================================================== #
#                                الدعم الفني                               #
# ======================================================================== #


async def test_ticket_flow_creates_ticket(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User
) -> None:
    """فتح تذكرة: تصنيف ← عنوان ← شرح ⇒ تذكرة مفتوحة برسالة واحدة."""
    await load_user(bot, context, user)

    state = await press(bot, context, support.start_new_ticket, pack("sup", "new"), user.telegram_id)
    assert state == support.ASK_CATEGORY
    category_buttons = [b for b in bot.last.buttons if b.startswith("sup:cat")]
    assert category_buttons

    state = await press(bot, context, support.choose_ticket_category, category_buttons[0], user.telegram_id)
    assert state == support.ASK_SUBJECT

    state = await write(bot, context, support.receive_subject, "طلبي متأخر", user.telegram_id)
    assert state == support.ASK_MESSAGE

    state = await write(
        bot, context, support.receive_ticket_message, "مضى يومان بلا تنفيذ", user.telegram_id
    )
    assert state == ConversationHandler.END

    tickets = await services.tickets.list_for_user(user, limit=10)
    assert len(tickets) == 1
    assert tickets[0].subject == "طلبي متأخر"


async def test_ticket_reply_and_close(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User
) -> None:
    """الرد على تذكرة ثم إغلاقها من المستخدم نفسه."""
    ticket = await services.tickets.create_ticket(
        user, subject="سؤال", message="هل الخدمة متاحة؟", category="other"
    )
    await load_user(bot, context, user)

    state = await press(
        bot, context, support.start_reply, pack("sup", "reply", ticket.id), user.telegram_id
    )
    assert state == support.ASK_REPLY

    state = await write(bot, context, support.receive_reply, "شكراً، وصلتني", user.telegram_id)
    assert state == ConversationHandler.END

    conversation = await services.tickets.conversation_for_user(user, ticket.id)
    assert len(conversation) >= 2

    await press(bot, context, support.close_ticket, pack("sup", "close", ticket.id), user.telegram_id)
    closed = await services.tickets.get_for_user(user, ticket.id)
    assert closed.status == "closed"


# ======================================================================== #
#                            الحساب والإشعارات                             #
# ======================================================================== #


async def test_account_and_notifications_screens(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User
) -> None:
    """شاشة الحساب تعرض بيانات حقيقية، وصندوق الإشعارات يُعلَّم مقروءاً."""
    await services.wallet.adjust_balance(
        target=user, amount_units=15_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    await load_user(bot, context, user)

    await press(bot, context, account.account_screen, pack("acc", "home"), user.telegram_id)
    assert str(user.telegram_id) in bot.last.text

    await press(bot, context, account.notifications_screen, pack("acc", "notif", 1), user.telegram_id)
    assert bot.last.buttons

    await press(bot, context, account.mark_all_read, pack("acc", "readall"), user.telegram_id)
    assert await services.notifications.unread_count(user.id) == 0


async def test_info_screen_has_version(bot: FakeBot, context: FakeContext, user: User) -> None:
    """شاشة المعلومات تعرض إصدار النظام وزر الرجوع."""
    from core.constants import APP_VERSION

    await load_user(bot, context, user)
    await press(bot, context, account.info_screen, pack("acc", "info"), user.telegram_id)
    assert APP_VERSION in bot.last.text
    assert bot.last.buttons


# ======================================================================== #
#                        الطبقة الوسيطة: حظر وصيانة وحد                     #
# ======================================================================== #


async def test_banned_user_is_blocked(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, db, repos: Repositories, user: User
) -> None:
    """المستخدم المحظور يُمنع من كل شيء برسالة تشرح السبب."""
    async with db.transaction() as tx:
        await repos.users.set_ban(tx, user.id, banned=True, reason="اختبار")

    update = make_message_update(bot, text="/start", user_id=user.telegram_id)
    assert await run_middleware(bot, context, update) is False
    assert bot.sent, "المحظور لم يتلقَّ أي رسالة — حظر صامت غير مقبول"


async def test_maintenance_blocks_normal_user_only(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, super_admin: User
) -> None:
    """وضع الصيانة يوقف المستخدم العادي ويسمح للأدمن."""
    await services.settings.set("maintenance_mode", "true", admin_id=super_admin.id)

    update = make_message_update(bot, text="/start", user_id=user.telegram_id)
    assert await run_middleware(bot, context, update) is False

    admin_context = FakeContext(bot, services)
    admin_update = make_message_update(bot, text="/start", user_id=super_admin.telegram_id)
    assert await run_middleware(bot, admin_context, admin_update) is True


async def test_rate_limit_stops_flood(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, super_admin: User
) -> None:
    """تجاوز حد الاستخدام يوقف المعالجة ويُعلم المستخدم."""
    await services.settings.set("rate_limit_actions_per_minute", "3", admin_id=super_admin.id)
    middleware = UserContextMiddleware(RateLimiter())

    allowed = 0
    for _ in range(5):
        update = make_message_update(bot, text="مرحبا", user_id=user.telegram_id)
        try:
            await middleware(update, context)
            allowed += 1
        except ApplicationHandlerStop:
            break
    assert allowed == 3
    assert any("كثيرة" in text or "انتظر" in text for text in bot.texts)
