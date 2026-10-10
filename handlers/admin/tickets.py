"""
قسم «🎫 الدعم» في لوحة التحكم: قوائم التذاكر، المحادثة الكاملة، الرد، الإسناد، الإغلاق.

ما ينفّذه هذا الملف:
    • أربع قوائم: المفتوحة · بانتظار الدعم · المسندة لي · المغلقة.
    • شاشة التذكرة تعرض **كل** الرسائل بالترتيب مع تمييز المرسل.
    • الرد يصل المستخدم كإشعار، والإغلاق يحتاج سبباً مكتوباً.

قواعد مطبّقة:
    • فتح التذكرة يعلّمها «مقروءة من الأدمن» تلقائياً (داخل الخدمة).
    • لا حذف لأي رسالة أو تذكرة — الإغلاق فقط.
    • كل إجراء يسجّله `TicketService` في سجل التدقيق.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from core.enums import SenderType, TicketStatus
from core.permissions import Permission
from handlers.common.conversation import conversation
from handlers.admin.common import (
    ADMIN_FLOW_KEY,
    PAGE_SIZE,
    admin_required,
    args,
    cancel_admin_flow,
    clear_flow,
    flow,
    paginate,
    permissions_of,
    start_flow,
)
from handlers.common.fallbacks import exit_conversation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    ADMIN_TICKET_FILTERS,
    TICKET_PRIORITIES,
    admin_ticket_card_kb,
    admin_tickets_kb,
    cancel_only_kb,
)
from keyboards.callback_data import NS_ADM_TKT, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from services.ticket_service import OPEN_STATUSES, TICKET_CATEGORIES
from texts import admin_ar as t
from utils.formatters import datetime_text, safe, ticket_status_text
from utils.logging_setup import get_logger
from utils.validators import clean_text, validate_message

logger = get_logger(__name__)

#: حالة محادثة الرد على تذكرة
ASK_REPLY = 0

#: حالة محادثة إغلاق تذكرة
ASK_CLOSE_REASON = 10

#: عدد الرسائل المعروضة من محادثة التذكرة
CONVERSATION_LIMIT = 12

#: أيقونة كل نوع مرسل في عرض المحادثة
SENDER_ICONS: dict[str, str] = {
    SenderType.USER: "👤",
    SenderType.ADMIN: "👮",
    SenderType.SYSTEM: "🤖",
}

#: اسم كل مرسل كما يُعرض فوق رسالته
SENDER_NAMES: dict[str, str] = {
    SenderType.USER: t.SENDER_USER,
    SenderType.ADMIN: t.SENDER_ADMIN,
    SenderType.SYSTEM: t.SENDER_SYSTEM,
}


def _statuses_for(filter_code: str) -> tuple[tuple[str, ...], bool]:
    """
    الحالات المطلوبة لكل تبويب + هل يُقيَّد بالتذاكر المسندة للأدمن الحالي.

    المخرجات: (الحالات، هل التقييد بالإسناد مطلوب).
    """
    if filter_code == "wait":
        return (TicketStatus.OPEN, TicketStatus.PENDING_ADMIN), False
    if filter_code == "mine":
        return OPEN_STATUSES, True
    if filter_code == "high":
        return OPEN_STATUSES, False
    if filter_code == "closed":
        return (TicketStatus.CLOSED,), False
    return OPEN_STATUSES, False


async def _render_ticket(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    ticket_id: int,
    *,
    filter_code: str = "open",
    as_new: bool = False,
) -> None:
    """عرض بطاقة التذكرة مع محادثتها كاملة."""
    services = services_of(context)
    admin = require_user(context)
    ticket, messages = await services.tickets.admin_conversation(
        admin, ticket_id, limit=CONVERSATION_LIMIT
    )
    owner = await services.users.get(ticket.user_id)
    perms = await permissions_of(context)

    assigned_line = ""
    if ticket.assigned_admin:
        assignee = await services.users.get(ticket.assigned_admin)
        assigned_line = t.TICKET_ASSIGNED_LINE.format(
            admin=safe(assignee.display_name if assignee else str(ticket.assigned_admin), limit=30)
        )
    order_line = ""
    if ticket.related_order_id:
        # رمز الطلب العلني يُقرأ فقط لمن يملك صلاحية عرض الطلبات، وإلا يُعرض رقمه
        code = f"#{ticket.related_order_id}"
        if Permission.ORDERS_VIEW in perms:
            related = await services.orders.admin_get(admin, ticket.related_order_id)
            code = related.public_code or code
        order_line = t.TICKET_ORDER_LINE.format(code=safe(code, limit=20))

    conversation = "\n\n".join(
        t.TICKET_MESSAGE_LINE.format(
            icon=SENDER_ICONS.get(message.sender_type, "💬"),
            sender=SENDER_NAMES.get(message.sender_type, message.sender_type),
            when=datetime_text(message.created_at),
            message=safe(message.message, limit=600),
        )
        for message in messages
    )

    text = t.TICKET_CARD.format(
        ticket_id=ticket.id,
        name=safe(owner.display_name if owner else "—", limit=30),
        telegram_id=owner.telegram_id if owner else "—",
        subject=safe(ticket.subject, limit=80),
        category=TICKET_CATEGORIES.get(ticket.category, safe(ticket.category)),
        status=ticket_status_text(ticket.status),
        priority_line=t.TICKET_PRIORITY_LINE.format(
            priority=TICKET_PRIORITIES.get(ticket.priority, safe(ticket.priority))
        ),
        order_line=order_line,
        assigned_line=assigned_line,
        last_message=datetime_text(ticket.last_message_at or ticket.created_at),
        conversation=conversation or "—",
    )
    markup = admin_ticket_card_kb(ticket, perms, filter_code=filter_code)
    if as_new:
        await send(update, context, text, markup)
    else:
        await render(update, context, text, markup)


# ============================= شاشات القراءة =========================== #


@guarded
@admin_required(Permission.TICKETS_VIEW)
async def tickets_list_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة التذاكر حسب التبويب المختار."""
    await answer_callback(update)
    data = args(update)
    filter_code = data.arg(0, "open")
    if filter_code not in ADMIN_TICKET_FILTERS:
        filter_code = "open"

    services = services_of(context)
    admin = require_user(context)
    statuses, mine_only = _statuses_for(filter_code)
    assigned = admin.id if mine_only else None
    priority = "high" if filter_code == "high" else None

    total = await services.tickets.admin_count(
        admin, statuses=statuses, assigned_admin=assigned, priority=priority
    )
    page, total_pages, offset = paginate(total, data.int_arg(1, 1))
    tickets = await services.tickets.admin_list(
        admin,
        statuses=statuses,
        assigned_admin=assigned,
        priority=priority,
        limit=PAGE_SIZE,
        offset=offset,
    )
    open_count = await services.tickets.open_count()

    if not tickets:
        await render(
            update,
            context,
            t.TICKETS_EMPTY,
            admin_tickets_kb([], filter_code=filter_code, page=1, total_pages=1),
        )
        return

    lines = "\n\n".join(
        f"{ticket_status_text(ticket.status)} · <b>#{ticket.id}</b>\n"
        f"   📌 {safe(ticket.subject, limit=45)}\n"
        f"   🕒 {datetime_text(ticket.last_message_at or ticket.created_at)}"
        for ticket in tickets
    )
    await render(
        update,
        context,
        f"{t.TICKETS_TITLE.format(filter_name=ADMIN_TICKET_FILTERS[filter_code], open_count=open_count, page=page, pages=total_pages)}"
        f"\n\n{lines}",
        admin_tickets_kb(tickets, filter_code=filter_code, page=page, total_pages=total_pages),
    )


@guarded
@admin_required(Permission.TICKETS_VIEW)
async def ticket_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة التذكرة الكاملة."""
    await answer_callback(update)
    await _render_ticket(update, context, args(update).int_arg(0))


@guarded
@admin_required(Permission.TICKETS_ASSIGN)
async def assign_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إسناد التذكرة إلى الأدمن الذي ضغط الزر."""
    services = services_of(context)
    admin = require_user(context)
    ticket_id = args(update).int_arg(0)
    changed = await services.tickets.assign(admin, ticket_id, admin.id)
    await answer_callback(
        update,
        t.TICKET_ASSIGNED.format(ticket_id=ticket_id) if changed else t.NOTHING_CHANGED,
        alert=True,
    )
    await _render_ticket(update, context, ticket_id)


@guarded
@admin_required(Permission.TICKETS_ASSIGN)
async def set_ticket_priority(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تغيير أولوية التذكرة (منخفضة/عادية/عالية) مع تسجيل التدقيق في الخدمة."""
    services = services_of(context)
    admin = require_user(context)
    data = args(update)
    ticket_id, priority = data.int_arg(0), data.arg(1)
    changed = await services.tickets.set_priority(admin, ticket_id, priority)
    label = TICKET_PRIORITIES.get(priority, priority)
    await answer_callback(
        update,
        t.TICKET_PRIORITY_SET.format(ticket_id=ticket_id, priority=label)
        if changed
        else t.TICKET_PRIORITY_SAME,
    )
    await _render_ticket(update, context, ticket_id)


# ============================= محادثة الرد ============================= #


@guarded
@admin_required(Permission.TICKETS_REPLY)
async def start_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء كتابة رد على تذكرة."""
    await answer_callback(update)
    ticket_id = args(update).int_arg(0)
    start_flow(context, ticket_id=ticket_id)
    await render(update, context, t.TICKET_ASK_REPLY.format(ticket_id=ticket_id), cancel_only_kb())
    return ASK_REPLY


@guarded
@admin_required(Permission.TICKETS_REPLY)
async def receive_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إرسال الرد للمستخدم (الخدمة تُنشئ الرسالة والإشعار والتدقيق)."""
    message = update.effective_message
    if message is None or not (message.text or message.caption):
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_REPLY

    data = flow(context)
    if not data.get("ticket_id"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    body = validate_message(message.text or message.caption or "")
    attachment_id = message.photo[-1].file_id if message.photo else None
    services = services_of(context)
    admin = require_user(context)
    ticket_id = int(data["ticket_id"])

    await services.tickets.reply_as_admin(
        admin,
        ticket_id,
        body,
        attachment_file_id=attachment_id,
        attachment_type="photo" if attachment_id else None,
    )
    clear_flow(context)
    logger.info("ردّ الأدمن %s على التذكرة #%s", admin.telegram_id, ticket_id)

    await send(update, context, t.TICKET_REPLY_DONE.format(ticket_id=ticket_id))
    await _render_ticket(update, context, ticket_id, as_new=True)
    return ConversationHandler.END


# =========================== محادثة الإغلاق ============================ #


@guarded
@admin_required(Permission.TICKETS_CLOSE)
async def start_close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء إغلاق تذكرة (سبب الإغلاق يصل المستخدم)."""
    await answer_callback(update)
    ticket_id = args(update).int_arg(0)
    start_flow(context, ticket_id=ticket_id)
    await render(
        update,
        context,
        t.TICKET_ASK_CLOSE_REASON.format(ticket_id=ticket_id),
        cancel_only_kb(),
    )
    return ASK_CLOSE_REASON


@guarded
@admin_required(Permission.TICKETS_CLOSE)
async def receive_close_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ الإغلاق بعد استلام السبب."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_CLOSE_REASON

    data = flow(context)
    if not data.get("ticket_id"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    reason = clean_text(message.text, field="سبب الإغلاق", max_length=200, min_length=3)
    services = services_of(context)
    admin = require_user(context)
    ticket_id = int(data["ticket_id"])
    await services.tickets.close(admin, ticket_id, reason)
    clear_flow(context)

    await send(update, context, t.TICKET_CLOSED.format(ticket_id=ticket_id))
    await _render_ticket(update, context, ticket_id, as_new=True)
    return ConversationHandler.END


# ============================== التسجيل ================================ #


def _fallbacks() -> list:
    """المسارات الاحتياطية الموحّدة لمحادثات هذا القسم."""
    return [
        CallbackQueryHandler(cancel_admin_flow, pattern=pattern(NS_FLOW, "cancel")),
        CommandHandler("cancel", cancel_admin_flow),
        CommandHandler("start", exit_conversation(ADMIN_FLOW_KEY)),
    ]


def conversations() -> list[ConversationHandler]:
    """محادثتا الرد والإغلاق."""
    reply = conversation(
        entry_points=[CallbackQueryHandler(start_reply, pattern=pattern(NS_ADM_TKT, "reply"))],
        states={
            ASK_REPLY: [
                MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, receive_reply)
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_ticket_reply",
        per_chat=True,
        per_user=True,
    )

    close = conversation(
        entry_points=[CallbackQueryHandler(start_close, pattern=pattern(NS_ADM_TKT, "close"))],
        states={
            ASK_CLOSE_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_close_reason)
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_ticket_close",
        per_chat=True,
        per_user=True,
    )
    return [reply, close]


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم الدعم خارج المحادثات."""
    return [
        CallbackQueryHandler(tickets_list_screen, pattern=pattern(NS_ADM_TKT, "list")),
        CallbackQueryHandler(ticket_card_screen, pattern=pattern(NS_ADM_TKT, "view")),
        CallbackQueryHandler(assign_ticket, pattern=pattern(NS_ADM_TKT, "assign")),
        CallbackQueryHandler(set_ticket_priority, pattern=pattern(NS_ADM_TKT, "prio")),
    ]
