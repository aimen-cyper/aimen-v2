"""
اختبارات خدمة الدعم الفني: التذاكر والمحادثة والإغلاق.
"""

from __future__ import annotations

import pytest

from core.enums import TicketStatus
from core.exceptions import PermissionDeniedError, TicketError, ValidationError
from database.database import Database
from database.models import User
from database.repositories import Repositories
from services import ServiceContainer
from utils.datetime_utils import iso_plus_seconds


async def _open_ticket(services: ServiceContainer, user: User, *, subject: str = "مشكلة في طلبي"):
    """اختصار لفتح تذكرة."""
    return await services.tickets.create_ticket(
        user, subject=subject, message="لم يصلني الطلب حتى الآن", category="order"
    )


async def test_create_ticket_adds_first_message_and_alerts_admins(
    services: ServiceContainer, repos: Repositories, user: User, admin: User
) -> None:
    """فتح التذكرة يضيف الرسالة الأولى وينبّه فريق الدعم."""
    ticket = await _open_ticket(services, user)

    assert ticket.status == TicketStatus.OPEN
    messages = await repos.tickets.messages(ticket.id)
    assert len(messages) == 1
    assert messages[0].sender_type == "user"
    assert await repos.notifications.list_for_user(admin.id)


async def test_only_one_open_ticket_per_user(services: ServiceContainer, user: User) -> None:
    """لا يفتح المستخدم تذكرتين في وقت واحد — يُوجَّه إلى تذكرته القائمة."""
    await _open_ticket(services, user)
    with pytest.raises(TicketError):
        await _open_ticket(services, user, subject="مشكلة أخرى")


async def test_daily_ticket_limit(services: ServiceContainer, user: User, admin: User) -> None:
    """الحد اليومي لعدد التذاكر مطبَّق."""
    await services.settings.set("max_tickets_per_day", 1)
    ticket = await _open_ticket(services, user)
    await services.tickets.close(admin, ticket.id, "تم الحل")

    with pytest.raises(ValidationError):
        await _open_ticket(services, user, subject="تذكرة ثانية اليوم")


async def test_invalid_category_and_wrong_order_rejected(
    services: ServiceContainer, user: User
) -> None:
    """التصنيف غير المعروف أو ربط طلب ليس للمستخدم مرفوضان."""
    with pytest.raises(ValidationError):
        await services.tickets.create_ticket(
            user, subject="س", message="نص الرسالة", category="unknown"
        )
    with pytest.raises(TicketError):
        await services.tickets.create_ticket(
            user, subject="استفسار", message="نص الرسالة", related_order_id=99999
        )


async def test_conversation_flow_between_user_and_support(
    services: ServiceContainer, repos: Repositories, user: User, admin: User
) -> None:
    """تبادل الرسائل يقلب حالة التذكرة بين انتظار الدعم وانتظار المستخدم."""
    ticket = await _open_ticket(services, user)

    after_user = await repos.tickets.get(ticket.id)
    assert after_user is not None and after_user.status == TicketStatus.PENDING_ADMIN

    await services.tickets.reply_as_admin(admin, ticket.id, "أهلاً بك، نراجع طلبك الآن")
    after_admin = await repos.tickets.get(ticket.id)
    assert after_admin is not None
    assert after_admin.status == TicketStatus.PENDING_USER
    assert after_admin.assigned_admin == admin.id

    inbox = await repos.notifications.list_for_user(user.id)
    assert any(item.type == "ticket_replied" for item in inbox)

    await services.tickets.reply_as_user(user, ticket.id, "شكراً، في انتظاركم")
    after_second = await repos.tickets.get(ticket.id)
    assert after_second is not None and after_second.status == TicketStatus.PENDING_ADMIN
    assert len(await repos.tickets.messages(ticket.id)) == 3


async def test_each_admin_reply_sends_its_own_notification(
    services: ServiceContainer, repos: Repositories, user: User, admin: User
) -> None:
    """كل رد من الدعم يُنتج إشعاراً مستقلاً (منع التكرار لا يبتلع الردود)."""
    ticket = await _open_ticket(services, user)
    await services.tickets.reply_as_admin(admin, ticket.id, "الرد الأول")
    await services.tickets.reply_as_admin(admin, ticket.id, "الرد الثاني")

    inbox = await repos.notifications.list_for_user(user.id)
    replies = [item for item in inbox if item.type == "ticket_replied"]
    assert len(replies) == 2


async def test_close_notifies_user_and_blocks_further_admin_duplicates(
    services: ServiceContainer, repos: Repositories, user: User, admin: User
) -> None:
    """الإغلاق يُشعر المستخدم، وإغلاق مغلق لا يفعل شيئاً."""
    ticket = await _open_ticket(services, user)
    assert await services.tickets.close(admin, ticket.id, "تم حل المشكلة")
    assert not await services.tickets.close(admin, ticket.id, "مرة أخرى")

    closed = await repos.tickets.get(ticket.id)
    assert closed is not None
    assert closed.status == TicketStatus.CLOSED
    assert closed.closed_by == admin.id

    inbox = await repos.notifications.list_for_user(user.id)
    assert any(item.type == "ticket_closed" for item in inbox)


async def test_user_reply_reopens_recently_closed_ticket(
    services: ServiceContainer, repos: Repositories, user: User, admin: User
) -> None:
    """الرد على تذكرة أُغلقت حديثاً يعيد فتحها بدل إجبار المستخدم على تذكرة جديدة."""
    ticket = await _open_ticket(services, user)
    await services.tickets.close(admin, ticket.id, "تم الحل")

    await services.tickets.reply_as_user(user, ticket.id, "المشكلة عادت")
    reopened = await repos.tickets.get(ticket.id)
    assert reopened is not None
    assert reopened.status == TicketStatus.PENDING_ADMIN
    assert reopened.closed_at is None


async def test_reply_blocked_when_reopen_disabled(
    services: ServiceContainer, user: User, admin: User
) -> None:
    """عند تعطيل إعادة الفتح، التذكرة المغلقة تبقى مغلقة."""
    await services.settings.set("ticket_reopen_hours", 0)
    ticket = await _open_ticket(services, user)
    await services.tickets.close(admin, ticket.id, "تم الحل")

    with pytest.raises(TicketError):
        await services.tickets.reply_as_user(user, ticket.id, "محاولة متأخرة")


async def test_user_cannot_read_or_reply_to_others_tickets(
    services: ServiceContainer, db: Database, repos: Repositories, user: User
) -> None:
    """تذاكر المستخدمين معزولة تماماً."""
    ticket = await _open_ticket(services, user)
    async with db.transaction() as tx:
        other = await repos.users.create(tx, telegram_id=444333222, first_name="Other")

    with pytest.raises(TicketError):
        await services.tickets.get_for_user(other, ticket.id)
    with pytest.raises(TicketError):
        await services.tickets.reply_as_user(other, ticket.id, "تطفل")


async def test_support_actions_require_permissions(
    services: ServiceContainer, user: User, admin: User
) -> None:
    """إجراءات فريق الدعم محمية بالصلاحيات."""
    ticket = await _open_ticket(services, user)

    with pytest.raises(PermissionDeniedError):
        await services.tickets.reply_as_admin(user, ticket.id, "رد غير مصرح")
    with pytest.raises(PermissionDeniedError):
        await services.tickets.admin_list(user)
    with pytest.raises(PermissionDeniedError):
        await services.tickets.close(user, ticket.id, "إغلاق غير مصرح")

    assert await services.tickets.admin_list(admin)


async def test_assign_only_to_admins_and_priority_validated(
    services: ServiceContainer, db: Database, repos: Repositories, user: User, admin: User
) -> None:
    """الإسناد لا يكون إلا لأدمن، والأولوية من القيم المعروفة فقط."""
    ticket = await _open_ticket(services, user)
    async with db.transaction() as tx:
        plain = await repos.users.create(tx, telegram_id=222111000, first_name="Plain")

    with pytest.raises(PermissionDeniedError):
        await services.tickets.assign(admin, ticket.id, plain.id)
    assert await services.tickets.assign(admin, ticket.id, admin.id)

    with pytest.raises(ValidationError):
        await services.tickets.set_priority(admin, ticket.id, "urgent")
    assert await services.tickets.set_priority(admin, ticket.id, "high")


async def test_auto_close_idle_tickets(
    services: ServiceContainer, db: Database, repos: Repositories, user: User, admin: User
) -> None:
    """التذاكر الراكدة بانتظار رد المستخدم تُغلق تلقائياً بعد المدة المحددة."""
    await services.settings.set("ticket_auto_close_days", 3)
    ticket = await _open_ticket(services, user)
    await services.tickets.reply_as_admin(admin, ticket.id, "بانتظار ردك")

    async with db.transaction() as tx:   # محاكاة مرور 10 أيام بلا رد
        await repos.tickets.update_fields(
            tx, ticket.id, last_message_at=iso_plus_seconds(-10 * 86400)
        )

    assert await services.tickets.auto_close_idle() == 1
    closed = await repos.tickets.get(ticket.id)
    assert closed is not None and closed.status == TicketStatus.CLOSED


async def test_reading_conversation_marks_messages_read(
    services: ServiceContainer, repos: Repositories, user: User, admin: User
) -> None:
    """فتح المحادثة من الطرفين يعلّم الرسائل كمقروءة."""
    ticket = await _open_ticket(services, user)
    await services.tickets.reply_as_admin(admin, ticket.id, "رد الدعم")

    messages = await services.tickets.conversation_for_user(user, ticket.id)
    assert messages and all(message.is_read_by_user == 1 for message in await repos.tickets.messages(ticket.id))

    _, admin_messages = await services.tickets.admin_conversation(admin, ticket.id)
    assert admin_messages
    assert all(message.is_read_by_admin == 1 for message in await repos.tickets.messages(ticket.id))
