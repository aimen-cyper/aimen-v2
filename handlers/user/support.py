"""
شاشات ومحادثات «🎫 الدعم الفني».

يشمل:
    • الشاشة الرئيسية وقائمة التذاكر وبطاقة التذكرة مع كامل المحادثة.
    • محادثة فتح تذكرة جديدة: 🗂 التصنيف ← ✏️ العنوان ← 📝 الشرح.
    • محادثة إضافة رد على تذكرة قائمة.
    • فتح تذكرة مرتبطة بطلب مباشرة من بطاقة الطلب.
    • إغلاق التذكرة من المستخدم نفسه.

قاعدة من طبقة الخدمات تُحترم هنا: تذكرة مفتوحة واحدة لكل مستخدم — ومحاولة
فتح ثانية تُرفض برسالة توجّهه إلى تذكرته الحالية.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.callback_data import unpack
from keyboards.common_kb import cancel_markup
from keyboards.user_kb import (
    main_menu_kb,
    support_kb,
    ticket_card_kb,
    ticket_categories_kb,
    tickets_kb,
)
from middlewares.context import require_user, services_of
from texts import ar
from utils.formatters import datetime_text, safe, ticket_status_text

#: حالات محادثة التذكرة الجديدة
ASK_CATEGORY, ASK_SUBJECT, ASK_MESSAGE = range(3)

#: حالة محادثة الرد على تذكرة
ASK_REPLY = 10

#: مفاتيح بيانات المحادثات
NEW_FLOW_KEY = "ticket_flow"
REPLY_FLOW_KEY = "ticket_reply_flow"

#: عدد التذاكر في الصفحة
PAGE_SIZE = 6

#: أقصى عدد رسائل تُعرض داخل بطاقة التذكرة
MESSAGES_LIMIT = 10


def _flow(context: ContextTypes.DEFAULT_TYPE, key: str) -> dict:
    """قراءة بيانات محادثة الدعم المطلوبة."""
    if context.user_data is None:
        return {}
    return context.user_data.get(key) or {}


def _clear(context: ContextTypes.DEFAULT_TYPE, key: str) -> None:
    """مسح بيانات محادثة الدعم."""
    if context.user_data is not None:
        context.user_data.pop(key, None)


# =============================== الشاشات ================================ #


@guarded
async def support_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الشاشة الرئيسية للدعم مع عدد التذاكر المفتوحة."""
    await answer_callback(update)
    services = services_of(context)
    user = require_user(context)
    summary = await services.users.summary(user)
    await render(
        update, context, ar.SUPPORT_TITLE.format(open_count=summary.tickets_open), support_kb()
    )


@guarded
async def tickets_list_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة تذاكر المستخدم بصفحات."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    page = max(1, data.int_arg(0, 1))

    services = services_of(context)
    user = require_user(context)
    tickets = await services.tickets.list_for_user(
        user, limit=PAGE_SIZE + 1, offset=(page - 1) * PAGE_SIZE
    )
    has_next = len(tickets) > PAGE_SIZE
    tickets = tickets[:PAGE_SIZE]
    total_pages = page + 1 if has_next else page

    if not tickets:
        await render(update, context, ar.TICKETS_EMPTY, tickets_kb([], page=1, total_pages=1))
        return

    await render(
        update,
        context,
        ar.TICKETS_TITLE.format(page=page, pages=total_pages),
        tickets_kb(tickets, page=page, total_pages=total_pages),
    )


@guarded
async def ticket_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة التذكرة مع آخر رسائل المحادثة (وتُعلَّم كمقروءة من طرف المستخدم)."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    ticket_id = data.int_arg(0)

    services = services_of(context)
    user = require_user(context)
    ticket = await services.tickets.get_for_user(user, ticket_id)
    messages = await services.tickets.conversation_for_user(user, ticket_id, limit=MESSAGES_LIMIT)

    lines = []
    for item in messages:
        is_user = item.sender_type == "user"
        lines.append(
            ar.TICKET_MESSAGE_LINE.format(
                icon="👤" if is_user else "🛠",
                sender="أنت" if is_user else "الدعم",
                time=datetime_text(item.created_at),
                text=safe(item.message, limit=400),
            )
        )

    text = ar.TICKET_CARD.format(
        ticket_id=ticket.id,
        subject=safe(ticket.subject),
        category=ar.TICKET_CATEGORIES.get(ticket.category, ticket.category),
        status=ticket_status_text(ticket.status),
        updated=datetime_text(ticket.last_message_at or ticket.updated_at),
        messages="\n".join(lines),
    )
    await render(update, context, text, ticket_card_kb(ticket))


@guarded
async def close_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إغلاق التذكرة بطلب من صاحبها."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    ticket_id = data.int_arg(0)

    services = services_of(context)
    user = require_user(context)
    await services.tickets.close_by_user(user, ticket_id)
    await render(update, context, ar.TICKET_CLOSED_BY_USER.format(ticket_id=ticket_id), support_kb())


# ======================= محادثة تذكرة جديدة ============================= #


@guarded
async def start_new_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء محادثة فتح تذكرة: اختيار التصنيف."""
    await answer_callback(update)
    if context.user_data is not None:
        context.user_data[NEW_FLOW_KEY] = {}
    await render(update, context, ar.TICKET_ASK_CATEGORY, ticket_categories_kb())
    return ASK_CATEGORY


@guarded
async def start_ticket_for_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    فتح تذكرة مرتبطة بطلب مباشرة من بطاقة الطلب.

    يُتخطى اختيار التصنيف (تصنيفها «مشكلة في طلب») ويُربط رقم الطلب بالتذكرة.
    """
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    order_id = data.int_arg(0)

    services = services_of(context)
    user = require_user(context)
    order = await services.orders.get_for_user(user, order_id)   # تحقق من ملكية الطلب

    if context.user_data is not None:
        context.user_data[NEW_FLOW_KEY] = {
            "category": "order",
            "related_order_id": order.id,
            "subject": f"مشكلة في الطلب {order.public_code or order.id}",
        }
    await render(
        update,
        context,
        ar.TICKET_ASK_MESSAGE_ORDER.format(
            code=order.public_code or f"#{order.id}",
            service=safe(order.service_name_snapshot),
        ),
        cancel_markup(),
    )
    return ASK_MESSAGE


@guarded
async def choose_ticket_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ تصنيف التذكرة وسؤال المستخدم عن العنوان."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    category = data.arg(0, "other")
    if category not in ar.TICKET_CATEGORIES:
        category = "other"

    flow = _flow(context, NEW_FLOW_KEY)
    flow["category"] = category
    if context.user_data is not None:
        context.user_data[NEW_FLOW_KEY] = flow

    await render(update, context, ar.TICKET_ASK_SUBJECT, cancel_markup())
    return ASK_SUBJECT


@guarded
async def receive_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال عنوان التذكرة ثم طلب شرح المشكلة."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, ar.ERR_NOT_TEXT, cancel_markup())
        return ASK_SUBJECT

    from utils.validators import validate_subject       # تحقق مبكر من الطول

    flow = _flow(context, NEW_FLOW_KEY)
    flow["subject"] = validate_subject(message.text)
    if context.user_data is not None:
        context.user_data[NEW_FLOW_KEY] = flow

    await send(update, context, ar.TICKET_ASK_MESSAGE, cancel_markup())
    return ASK_MESSAGE


@guarded
async def receive_ticket_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال شرح المشكلة وإنشاء التذكرة فعلياً."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, ar.ERR_NOT_TEXT, cancel_markup())
        return ASK_MESSAGE

    flow = _flow(context, NEW_FLOW_KEY)
    if not flow:
        await send(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    services = services_of(context)
    user = require_user(context)
    ticket = await services.tickets.create_ticket(
        user,
        subject=flow.get("subject") or message.text[:60],
        message=message.text,
        category=flow.get("category", "other"),
        related_order_id=flow.get("related_order_id"),
        attachment_file_id=message.photo[-1].file_id if message.photo else None,
        attachment_type="photo" if message.photo else None,
    )

    await send(
        update,
        context,
        ar.TICKET_CREATED.format(ticket_id=ticket.id, subject=safe(ticket.subject)),
        support_kb(),
    )
    _clear(context, NEW_FLOW_KEY)
    return ConversationHandler.END


# ========================= محادثة الرد ================================== #


@guarded
async def start_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء محادثة إضافة رد على تذكرة."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    ticket_id = data.int_arg(0)

    services = services_of(context)
    user = require_user(context)
    await services.tickets.get_for_user(user, ticket_id)       # تحقق من الملكية قبل السؤال

    if context.user_data is not None:
        context.user_data[REPLY_FLOW_KEY] = {"ticket_id": ticket_id}
    await render(update, context, ar.TICKET_ASK_REPLY.format(ticket_id=ticket_id), cancel_markup())
    return ASK_REPLY


@guarded
async def receive_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إرسال رد المستخدم إلى فريق الدعم."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, ar.ERR_NOT_TEXT, cancel_markup())
        return ASK_REPLY

    flow = _flow(context, REPLY_FLOW_KEY)
    if not flow.get("ticket_id"):
        await send(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    services = services_of(context)
    user = require_user(context)
    await services.tickets.reply_as_user(
        user,
        flow["ticket_id"],
        message.text,
        attachment_file_id=message.photo[-1].file_id if message.photo else None,
        attachment_type="photo" if message.photo else None,
    )

    await send(update, context, ar.TICKET_REPLY_SENT, support_kb())
    _clear(context, REPLY_FLOW_KEY)
    return ConversationHandler.END


@guarded
async def cancel_support_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء أي محادثة دعم جارية."""
    await answer_callback(update)
    _clear(context, NEW_FLOW_KEY)
    _clear(context, REPLY_FLOW_KEY)
    if update.callback_query is not None:
        await render(update, context, ar.CANCELLED, support_kb())
    else:
        await send(update, context, ar.CANCELLED, support_kb())
    return ConversationHandler.END
