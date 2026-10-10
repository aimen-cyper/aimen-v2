"""
اختبارات قسم الطلبات في لوحة التحكم.

تشمل: التصفية والبطاقة، إعادة الفحص الفوري، الإلغاء مع الاسترجاع، وضع الطلب
فاشلاً مع الاسترجاع، ربط رقم المزود يدوياً، وتغيير الحالة قسرياً بسبب مكتوب.
القاعدة المحروسة هنا: **لا استرجاع بلا حركة مالية، ولا تغيير حالة بلا تحقق**.
"""

from __future__ import annotations

import pytest
from telegram.ext import ConversationHandler

from core.enums import OrderStatus, TransactionType
from core.permissions import Permission
from database.models import Service, User
from database.repositories import Repositories
from handlers.admin import orders as admin_orders
from integrations.providers.mock import MockProviderClient
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

ORDER_COST = 10_000  # تكلفة طلب 1000 وحدة بسعر 10000 لكل ألف


async def _funded_order(
    services: ServiceContainer, user: User, admin: User, service: Service, *, quantity: int = 1000
):
    """شحن رصيد المستخدم ثم إنشاء طلب جاهز للاختبار."""
    await services.wallet.adjust_balance(
        target=user, amount_units=ORDER_COST * 2, admin=admin, reason="رصيد اختبار", credit=True
    )
    return await services.orders.create_order(
        user, service_id=service.id, link="https://instagram.com/test", quantity=quantity
    )


# ======================================================================== #
#                             القوائم والبطاقة                             #
# ======================================================================== #


async def test_orders_list_and_filters(
    bot: FakeBot, context: FakeContext, admin: User, user: User, mock_service: Service, services: ServiceContainer
) -> None:
    """قائمة الطلبات تعرض الطلب الحقيقي وأزرار التصفية."""
    order = await _funded_order(services, user, admin, mock_service)
    await load_user(bot, context, admin)
    await press(
        bot, context, admin_orders.orders_list_screen, pack("ao", "list", "all", 1), admin.telegram_id
    )

    assert f"ao:view:{order.id}:all:1:v1" in bot.last.buttons
    assert "ao:list:act:1:v1" in bot.last.buttons, "أزرار التصفية غير معروضة"


async def test_order_card_shows_actions(
    bot: FakeBot, context: FakeContext, super_admin: User, user: User, mock_service: Service, services: ServiceContainer
) -> None:
    """بطاقة الطلب تعرض كوده وحالته وأزرار الإجراءات المسموح بها."""
    order = await _funded_order(services, user, super_admin, mock_service)
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        admin_orders.order_card_screen,
        pack("ao", "view", order.id, "all", 1),
        super_admin.telegram_id,
    )

    assert order.public_code in bot.last.text
    assert f"ao:cancel:{order.id}:v1" in bot.last.buttons
    assert f"ao:fail:{order.id}:v1" in bot.last.buttons


# ======================================================================== #
#                          الإلغاء والفشل والاسترجاع                       #
# ======================================================================== #


async def test_admin_cancel_refunds_user(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    mock_service: Service,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """إلغاء الأدمن لطلب معلّق: سبب ⇒ تأكيد ⇒ استرجاع بحركة مالية وإشعار."""
    order = await _funded_order(services, user, admin, mock_service)
    before = await services.users.get(user.id)

    await load_user(bot, context, admin)
    state = await press(
        bot, context, admin_orders.start_cancel, pack("ao", "cancel", order.id), admin.telegram_id
    )
    assert state == admin_orders.ASK_REASON

    state = await write(
        bot, context, admin_orders.receive_reason, "طلب العميل الإلغاء", admin.telegram_id
    )
    assert state == admin_orders.CONFIRM_ACTION
    assert "flow:confirm:v1" in bot.last.buttons, "لا تأكيد ثانٍ قبل إلغاء الطلب"

    still = await repos.orders.get(order.id)
    assert still.status == OrderStatus.PENDING, "أُلغي الطلب قبل التأكيد"

    state = await press(
        bot, context, admin_orders.confirm_reason_action, pack("flow", "confirm"), admin.telegram_id
    )
    assert state == ConversationHandler.END

    canceled = await repos.orders.get(order.id)
    assert canceled.status in {OrderStatus.CANCELED, OrderStatus.REFUNDED}

    after = await services.users.get(user.id)
    assert after.balance_units == before.balance_units + ORDER_COST, "لم يُسترجع المبلغ"

    transactions = await repos.transactions.list_by_user(user.id, limit=5)
    assert any(item.type == TransactionType.REFUND for item in transactions), (
        "استرجاع بلا حركة مالية"
    )


async def test_admin_mark_failed_refunds_once(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    mock_service: Service,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """وضع الطلب فاشلاً يسترجع المبلغ مرة واحدة فقط مهما تكرر الضغط."""
    order = await _funded_order(services, user, admin, mock_service)
    before = await services.users.get(user.id)

    await load_user(bot, context, admin)
    await press(bot, context, admin_orders.start_fail, pack("ao", "fail", order.id), admin.telegram_id)
    await write(bot, context, admin_orders.receive_reason, "المزود لا يدعم الرابط", admin.telegram_id)
    await press(
        bot, context, admin_orders.confirm_reason_action, pack("flow", "confirm"), admin.telegram_id
    )

    after = await services.users.get(user.id)
    assert after.balance_units == before.balance_units + ORDER_COST

    # تكرار العملية على طلب نهائي: لا استرجاع ثانٍ
    await press(bot, context, admin_orders.start_fail, pack("ao", "fail", order.id), admin.telegram_id)
    await write(bot, context, admin_orders.receive_reason, "محاولة ثانية", admin.telegram_id)
    await press(
        bot, context, admin_orders.confirm_reason_action, pack("flow", "confirm"), admin.telegram_id
    )

    final = await services.users.get(user.id)
    assert final.balance_units == after.balance_units, "تكرّر الاسترجاع على نفس الطلب"


async def test_cancel_without_permission_is_blocked(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    super_admin: User,
    user: User,
    mock_service: Service,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """بلا صلاحية `orders.cancel` لا يبدأ الإلغاء أصلاً."""
    order = await _funded_order(services, user, super_admin, mock_service)
    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.ORDERS_CANCEL, allow=False
    )
    await load_user(bot, context, admin)
    await press(bot, context, admin_orders.start_cancel, pack("ao", "cancel", order.id), admin.telegram_id)

    assert bot.answers[-1]["alert"] is True
    unchanged = await repos.orders.get(order.id)
    assert unchanged.status == OrderStatus.PENDING


# ======================================================================== #
#                       المزود: فحص فوري وربط رقم الطلب                     #
# ======================================================================== #


async def test_recheck_now_updates_status(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    mock_service: Service,
    mock_client: MockProviderClient,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """إعادة الفحص الفوري تستجلب حالة المزود وتحدّث الطلب."""
    order = await _funded_order(services, user, admin, mock_service)
    await services.orders.process_pending_orders()
    submitted = await repos.orders.get(order.id)
    assert submitted.provider_order_id, "لم يُرسل الطلب للمزود"

    mock_client.advance(submitted.provider_order_id, to="Completed", delivered=submitted.quantity)
    await load_user(bot, context, admin)
    await press(
        bot, context, admin_orders.recheck_order, pack("ao", "recheck", order.id), admin.telegram_id
    )

    rechecked = await repos.orders.get(order.id)
    assert rechecked.status == OrderStatus.COMPLETED
    assert bot.answers, "لم يُرد البوت على زر إعادة الفحص"


async def test_recheck_without_provider_order_id_explains(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    mock_service: Service,
    services: ServiceContainer,
) -> None:
    """طلب بلا رقم عند المزود: رسالة واضحة بدل عطل صامت."""
    order = await _funded_order(services, user, admin, mock_service)
    await load_user(bot, context, admin)
    await press(
        bot, context, admin_orders.recheck_order, pack("ao", "recheck", order.id), admin.telegram_id
    )
    assert bot.answers[-1]["text"], "لا رسالة توضح تعذّر الفحص"


async def test_link_provider_order_id(
    bot: FakeBot,
    context: FakeContext,
    super_admin: User,
    user: User,
    mock_service: Service,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """ربط رقم طلب المزود يدوياً لطلب نتيجته غير مؤكدة."""
    order = await _funded_order(services, user, super_admin, mock_service)
    async with repos.db.transaction() as tx:
        await repos.orders.update_fields(tx, order.id, status=OrderStatus.SUBMIT_UNCERTAIN)

    await load_user(bot, context, super_admin)
    state = await press(
        bot, context, admin_orders.start_link, pack("ao", "link", order.id), super_admin.telegram_id
    )
    assert state == admin_orders.ASK_PROVIDER_ID

    state = await write(bot, context, admin_orders.receive_provider_id, "PRV-55512", super_admin.telegram_id)
    assert state == ConversationHandler.END

    linked = await repos.orders.get(order.id)
    assert linked.provider_order_id == "PRV-55512"
    assert linked.status == OrderStatus.SUBMITTED


# ======================================================================== #
#                            تغيير الحالة قسرياً                           #
# ======================================================================== #


async def test_override_status_requires_reason(
    bot: FakeBot,
    context: FakeContext,
    super_admin: User,
    user: User,
    mock_service: Service,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """التغيير القسري للحالة يحتاج سبباً مكتوباً ويُسجَّل في التدقيق."""
    order = await _funded_order(services, user, super_admin, mock_service)
    await load_user(bot, context, super_admin)

    await press(
        bot, context, admin_orders.override_screen, pack("ao", "force", order.id), super_admin.telegram_id
    )
    assert any(button.startswith(f"ao:setst:{order.id}") for button in bot.last.buttons), (
        "شاشة التغيير القسري لا تعرض الحالات المسموح بها"
    )

    state = await press(
        bot,
        context,
        admin_orders.start_override,
        pack("ao", "setst", order.id, OrderStatus.FAILED),
        super_admin.telegram_id,
    )
    assert state == admin_orders.ASK_OVERRIDE_REASON

    state = await write(
        bot, context, admin_orders.receive_override_reason, "تسوية يدوية بعد اتفاق مع العميل", super_admin.telegram_id
    )
    assert state == ConversationHandler.END

    changed = await repos.orders.get(order.id)
    assert changed.status == OrderStatus.FAILED

    audit = await repos.audit.list_recent(limit=10)
    assert any("status" in entry.action or "override" in entry.action for entry in audit), (
        "التغيير القسري بلا سجل تدقيق"
    )


async def test_override_rejects_short_reason(
    bot: FakeBot,
    context: FakeContext,
    super_admin: User,
    user: User,
    mock_service: Service,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """سبب قصير لا يكفي لتغيير حالة طلب قسرياً."""
    order = await _funded_order(services, user, super_admin, mock_service)
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        admin_orders.start_override,
        pack("ao", "setst", order.id, OrderStatus.FAILED),
        super_admin.telegram_id,
    )
    await write(bot, context, admin_orders.receive_override_reason, "خطأ", super_admin.telegram_id)

    unchanged = await repos.orders.get(order.id)
    assert unchanged.status == OrderStatus.PENDING, "تغيّرت الحالة رغم السبب الناقص"


async def test_override_blocked_for_plain_admin(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    mock_service: Service,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """التغيير القسري حكر على من يملك `orders.status.override` (ليس الأدمن العادي)."""
    order = await _funded_order(services, user, admin, mock_service)
    await load_user(bot, context, admin)
    await press(
        bot,
        context,
        admin_orders.start_override,
        pack("ao", "setst", order.id, OrderStatus.COMPLETED),
        admin.telegram_id,
    )
    assert bot.answers[-1]["alert"] is True
    unchanged = await repos.orders.get(order.id)
    assert unchanged.status == OrderStatus.PENDING
