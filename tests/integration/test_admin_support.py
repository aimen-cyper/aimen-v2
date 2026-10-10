"""
اختبارات قسم التذاكر في لوحة التحكم.

المطلوب إثباته: الأدمن يرى المحادثة كاملة، ردّه يصل للمستخدم فعلاً (إشعار
+ رسالة محفوظة)، الإسناد يمنع ازدواج العمل، والإغلاق لا يحذف التاريخ.
"""

from __future__ import annotations

import pytest
from telegram.ext import ConversationHandler

from core.enums import TicketStatus
from core.permissions import Permission
from database.models import SupportTicket, User
from database.repositories import Repositories
from handlers.admin import tickets as admin_tickets
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


@pytest.fixture
async def ticket(services: ServiceContainer, user: User) -> SupportTicket:
    """تذكرة دعم مفتوحة أنشأها المستخدم."""
    return await services.tickets.create_ticket(
        user, subject="لم يصل طلبي", category="order", message="مرّ يومان ولم يصل شيء"
    )


async def test_tickets_list_shows_open_ticket(
    bot: FakeBot, context: FakeContext, admin: User, ticket: SupportTicket
) -> None:
    """قائمة التذاكر المفتوحة تعرض التذكرة وأزرار التصفية."""
    await load_user(bot, context, admin)
    await press(
        bot, context, admin_tickets.tickets_list_screen, pack("at", "list", "open", 1), admin.telegram_id
    )
    assert f"at:view:{ticket.id}:v1" in bot.last.buttons
    assert "at:list:mine:1:v1" in bot.last.buttons


async def test_ticket_card_shows_conversation(
    bot: FakeBot, context: FakeContext, admin: User, ticket: SupportTicket
) -> None:
    """بطاقة التذكرة تعرض نص رسالة المستخدم وأزرار الرد والإغلاق."""
    await load_user(bot, context, admin)
    await press(
        bot, context, admin_tickets.ticket_card_screen, pack("at", "view", ticket.id), admin.telegram_id
    )

    assert "مرّ يومان" in bot.last.text
    assert f"at:reply:{ticket.id}:v1" in bot.last.buttons
    assert f"at:close:{ticket.id}:v1" in bot.last.buttons


async def test_reply_reaches_user(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    ticket: SupportTicket,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """رد الأدمن يُحفظ في المحادثة ويصل المستخدم كإشعار."""
    await load_user(bot, context, admin)
    state = await press(
        bot, context, admin_tickets.start_reply, pack("at", "reply", ticket.id), admin.telegram_id
    )
    assert state == admin_tickets.ASK_REPLY

    state = await write(
        bot, context, admin_tickets.receive_reply, "تم تسريع طلبك، شكراً لصبرك", admin.telegram_id
    )
    assert state == ConversationHandler.END

    messages = await repos.tickets.messages(ticket.id, limit=10)
    assert any(item.sender_type == "admin" for item in messages), "لم يُحفظ رد الأدمن"

    queued = await repos.notifications.list_for_user(user.id, limit=5)
    assert queued, "لم يصل المستخدم إشعار برد الدعم"


async def test_assign_ticket_to_self(
    bot: FakeBot, context: FakeContext, admin: User, ticket: SupportTicket, repos: Repositories
) -> None:
    """الإسناد يربط التذكرة بالأدمن الحالي (منع ازدواج الردود)."""
    await load_user(bot, context, admin)
    await press(
        bot, context, admin_tickets.assign_ticket, pack("at", "assign", ticket.id), admin.telegram_id
    )

    stored = await repos.tickets.get(ticket.id)
    assert stored.assigned_admin == admin.id


async def test_close_ticket_keeps_history(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    ticket: SupportTicket,
    repos: Repositories,
) -> None:
    """الإغلاق يغيّر الحالة فقط — الرسائل تبقى محفوظة (لا حذف تاريخي)."""
    await load_user(bot, context, admin)
    state = await press(
        bot, context, admin_tickets.start_close, pack("at", "close", ticket.id), admin.telegram_id
    )
    assert state == admin_tickets.ASK_CLOSE_REASON

    state = await write(
        bot, context, admin_tickets.receive_close_reason, "تم حل المشكلة", admin.telegram_id
    )
    assert state == ConversationHandler.END

    stored = await repos.tickets.get(ticket.id)
    assert stored.status == TicketStatus.CLOSED

    messages = await repos.tickets.messages(ticket.id, limit=10)
    assert messages, "اختفت رسائل التذكرة بعد الإغلاق"


async def test_reply_requires_permission(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    super_admin: User,
    ticket: SupportTicket,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """بلا صلاحية `tickets.reply` لا يمكن الرد."""
    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.TICKETS_REPLY, allow=False
    )
    await load_user(bot, context, admin)
    await press(
        bot, context, admin_tickets.start_reply, pack("at", "reply", ticket.id), admin.telegram_id
    )

    assert bot.answers[-1]["alert"] is True
    messages = await repos.tickets.messages(ticket.id, limit=10)
    assert all(item.sender_type != "admin" for item in messages)
