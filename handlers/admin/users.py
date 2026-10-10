"""
قسم «👥 المستخدمون» في لوحة التحكم.

ما ينفّذه هذا الملف:
    • البحث عن مستخدم (معرف رقمي / @username / جزء من الاسم).
    • بطاقة المستخدم الكاملة (رصيد، إنفاق، طلبات، تذاكر، حظر، ملاحظة).
    • إضافة رصيد وخصمه بمحادثة من ثلاث خطوات تنتهي بشاشة تأكيد.
    • الحظر وفك الحظر والملاحظة الإدارية وتغيير الدور.
    • استعراض طلبات المستخدم وحركاته المالية.

قواعد مطبّقة هنا حرفياً:
    • كل معالج يفحص صلاحيته بنفسه عبر `@admin_required` (لا نكتفي بإخفاء الزر).
    • كل عملية مالية تمر بشاشة تأكيد ثانية، وتحمل `token` ثابتاً طوال المحادثة
      فلا تُنفَّذ مرتين عند الضغط المزدوج (`DuplicateOperationError`).
    • تغيير الرصيد يتم حصراً عبر `WalletService.adjust_balance` — لا SQL هنا.
    • سجل التدقيق تكتبه الخدمات نفسها؛ المعالج لا يزوّر سجلاً ولا يتجاوزه.
    • المستخدم المتأثر يُشعَر عبر صندوق الإشعارات (Outbox) لا برسالة مباشرة.
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

from core.enums import NotificationType
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
    load_user_or_fail,
    paginate,
    permissions_of,
    start_flow,
    symbol_of,
    update_flow,
)
from handlers.common.fallbacks import exit_conversation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    cancel_only_kb,
    confirm_cancel_kb,
    user_card_kb,
    user_list_nav_kb,
    user_results_kb,
    user_role_confirm_kb,
    user_role_kb,
    users_home_kb,
)
from keyboards.callback_data import NS_ADM_USERS, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from texts import templates
from utils.formatters import (
    datetime_text,
    money_text,
    order_status_text,
    safe,
    transaction_line,
)
from utils.logging_setup import get_logger
from utils.validators import clean_text, parse_amount_units, validate_amount_range

logger = get_logger(__name__)

#: حالات محادثة البحث
ASK_QUERY = 0

#: حالات محادثة تعديل الرصيد
ASK_AMOUNT, ASK_REASON, CONFIRM_BALANCE = range(10, 13)

#: حالات محادثة الحظر
ASK_BAN_REASON, CONFIRM_BAN = range(20, 22)

#: حالة محادثة الملاحظة الإدارية
ASK_NOTE = 30

#: الحد الأقصى لنتائج البحث المعروضة دفعة واحدة
SEARCH_LIMIT = 8


# ============================ أدوات العرض ============================== #


async def _render_card(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, *, as_new: bool = False
) -> None:
    """
    عرض بطاقة مستخدم كاملة (تُستخدم بعد كل إجراء حتى يرى الأدمن النتيجة فوراً).

    المدخلات:
        user_id : المعرف الداخلي للمستخدم.
        as_new  : إرسال رسالة جديدة بدل تحرير الحالية (بعد انتهاء محادثة نصية).
    """
    services = services_of(context)
    target = await load_user_or_fail(context, user_id)
    summary = await services.users.summary(target)
    symbol = await symbol_of(context)
    perms = await permissions_of(context)

    text = t.USER_CARD.format(
        name=safe(target.display_name, limit=40),
        telegram_id=target.telegram_id,
        username=f"@{safe(target.username)}" if target.username else "—",
        role=t.ROLE_NAMES.get(target.role, safe(target.role)),
        ban_line=t.USER_BANNED_LINE.format(reason=safe(target.ban_reason or "—", limit=120))
        if target.is_banned
        else "",
        balance=money_text(target.balance_units, symbol),
        deposited=money_text(target.total_deposited_units, symbol),
        spent=money_text(target.total_spent_units, symbol),
        orders_count=summary.orders_count,
        active_orders=summary.active_orders,
        payments_count=summary.payments_count,
        tickets_open=summary.tickets_open,
        joined=datetime_text(target.created_at),
        last_activity=datetime_text(target.last_activity or target.created_at),
        note_line=t.USER_NOTE_LINE.format(note=safe(target.notes, limit=300))
        if target.notes
        else "",
    )
    markup = user_card_kb(target, perms)
    if as_new:
        await send(update, context, text, markup)
    else:
        await render(update, context, text, markup)


# ============================ شاشات القراءة ============================ #


@guarded
@admin_required(Permission.USERS_VIEW)
async def users_home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الشاشة الرئيسية لقسم المستخدمين: عدادات + زر البحث."""
    await answer_callback(update)
    services = services_of(context)
    counters = await services.users.counters()
    perms = await permissions_of(context)
    await render(
        update,
        context,
        t.USERS_HOME.format(
            total=counters["total"],
            new_today=counters["new_today"],
            active_today=counters["active_today"],
            banned=counters["banned"],
        ),
        users_home_kb(perms),
    )


@guarded
@admin_required(Permission.USERS_VIEW)
async def user_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة مستخدم بالمعرف الداخلي القادم من الزر."""
    await answer_callback(update)
    await _render_card(update, context, args(update).int_arg(0))


@guarded
@admin_required(Permission.ORDERS_VIEW)
async def user_orders_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة طلبات مستخدم بعينه (مرقَّمة)."""
    await answer_callback(update)
    data = args(update)
    user_id = data.int_arg(0)
    services = services_of(context)
    admin = require_user(context)
    target = await load_user_or_fail(context, user_id)
    symbol = await symbol_of(context)

    total = await services.orders.admin_count(admin, user_id=user_id)
    page, total_pages, offset = paginate(total, data.int_arg(1, 1))
    orders = await services.orders.admin_list(
        admin, user_id=user_id, limit=PAGE_SIZE, offset=offset
    )

    if not orders:
        await render(
            update,
            context,
            t.USER_ORDERS_EMPTY,
            user_list_nav_kb("orders", user_id, page=1, total_pages=1),
        )
        return

    lines = "\n\n".join(
        f"{order_status_text(order.status)}\n"
        f"   {order.public_code or order.id} · {money_text(order.cost_units, symbol)}\n"
        f"   🛍 {safe(order.service_name_snapshot, limit=38)}\n"
        f"   🕒 {datetime_text(order.created_at)}"
        for order in orders
    )
    await render(
        update,
        context,
        t.USER_ORDERS_TITLE.format(
            name=safe(target.display_name, limit=30), page=page, pages=total_pages, lines=lines
        ),
        user_list_nav_kb("orders", user_id, page=page, total_pages=total_pages),
    )


@guarded
@admin_required(Permission.USERS_VIEW)
async def user_transactions_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """كشف الحركات المالية لمستخدم بعينه (مرقَّم)."""
    await answer_callback(update)
    data = args(update)
    user_id = data.int_arg(0)
    services = services_of(context)
    target = await load_user_or_fail(context, user_id)
    symbol = await symbol_of(context)

    total = await services.wallet.history_count(user_id)
    page, total_pages, offset = paginate(total, data.int_arg(1, 1))
    transactions = await services.wallet.history(user_id, limit=PAGE_SIZE, offset=offset)

    if not transactions:
        await render(
            update,
            context,
            t.USER_TX_EMPTY,
            user_list_nav_kb("tx", user_id, page=1, total_pages=1),
        )
        return

    lines = "\n\n".join(
        transaction_line(transaction, symbol=symbol) for transaction in transactions
    )
    await render(
        update,
        context,
        t.USER_TX_TITLE.format(
            name=safe(target.display_name, limit=30), page=page, pages=total_pages, lines=lines
        ),
        user_list_nav_kb("tx", user_id, page=page, total_pages=total_pages),
    )


# ============================= محادثة البحث ============================ #


@guarded
@admin_required(Permission.USERS_VIEW)
async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء محادثة البحث عن مستخدم."""
    await answer_callback(update)
    start_flow(context)
    await render(update, context, t.USERS_ASK_QUERY, cancel_only_kb())
    return ASK_QUERY


@guarded
@admin_required(Permission.USERS_VIEW)
async def receive_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ البحث وعرض النتائج كأزرار."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_QUERY

    query = clean_text(message.text, field="نص البحث", max_length=64, min_length=1)
    services = services_of(context)
    admin = require_user(context)
    found = await services.users.search(admin, query, limit=SEARCH_LIMIT)
    clear_flow(context)

    if not found:
        await send(update, context, t.USERS_NO_RESULTS.format(query=safe(query)), cancel_only_kb())
        return ASK_QUERY

    await send(
        update,
        context,
        t.USERS_RESULTS.format(query=safe(query), count=len(found)),
        user_results_kb(found),
    )
    return ConversationHandler.END


# ========================== محادثة تعديل الرصيد ========================= #


async def _start_balance(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, credit: bool
) -> int:
    """الخطوة الأولى المشتركة بين الإضافة والخصم: سؤال المبلغ."""
    await answer_callback(update)
    user_id = args(update).int_arg(0)
    target = await load_user_or_fail(context, user_id)
    symbol = await symbol_of(context)
    start_flow(context, user_id=user_id, credit=credit)

    template = t.USER_ASK_CREDIT if credit else t.USER_ASK_DEBIT
    await render(
        update,
        context,
        template.format(
            name=safe(target.display_name, limit=30),
            balance=money_text(target.balance_units, symbol),
        ),
        cancel_only_kb(),
    )
    return ASK_AMOUNT


@guarded
@admin_required(Permission.USERS_BALANCE_CREDIT)
async def start_credit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء محادثة إضافة رصيد."""
    return await _start_balance(update, context, credit=True)


@guarded
@admin_required(Permission.USERS_BALANCE_DEBIT)
async def start_debit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء محادثة خصم رصيد."""
    return await _start_balance(update, context, credit=False)


@guarded
@admin_required()
async def receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال المبلغ والتحقق منه ثم سؤال السبب."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_AMOUNT

    units = validate_amount_range(parse_amount_units(message.text), min_units=1, label="المبلغ")
    update_flow(context, amount_units=units)
    await send(update, context, t.USER_ASK_BALANCE_REASON, cancel_only_kb())
    return ASK_REASON


@guarded
@admin_required()
async def receive_balance_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال سبب العملية ثم عرض شاشة التأكيد النهائية."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_REASON

    reason = clean_text(message.text, field="سبب العملية", max_length=200, min_length=3)
    data = update_flow(context, reason=reason)

    target = await load_user_or_fail(context, int(data["user_id"]))
    symbol = await symbol_of(context)
    credit = bool(data["credit"])
    amount = int(data["amount_units"])
    after = target.balance_units + amount if credit else target.balance_units - amount

    await send(
        update,
        context,
        t.USER_BALANCE_CONFIRM.format(
            name=safe(target.display_name, limit=30),
            icon="➕" if credit else "➖",
            operation=t.OP_CREDIT if credit else t.OP_DEBIT,
            amount=money_text(amount, symbol),
            balance=money_text(target.balance_units, symbol),
            balance_after=money_text(after, symbol),
            reason=safe(reason, limit=200),
        ),
        confirm_cancel_kb(),
    )
    return CONFIRM_BALANCE


@guarded
@admin_required()
async def confirm_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    تنفيذ تعديل الرصيد فعلياً بعد التأكيد.

    الصلاحية تُفحص هنا مرة أخرى حسب نوع العملية (إضافة/خصم) لأن المحادثة قد
    تكون بدأت قبل تغيّر صلاحيات هذا الأدمن.
    """
    await answer_callback(update)
    data = flow(context)
    if not data.get("user_id") or not data.get("amount_units"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    credit = bool(data["credit"])
    await services.auth.require_permission(
        admin,
        Permission.USERS_BALANCE_CREDIT if credit else Permission.USERS_BALANCE_DEBIT,
        context=f"user:{data['user_id']}",
    )

    target = await load_user_or_fail(context, int(data["user_id"]))
    amount = int(data["amount_units"])
    reason = str(data["reason"])
    symbol = await symbol_of(context)

    transaction = await services.wallet.adjust_balance(
        target=target,
        amount_units=amount,
        admin=admin,
        reason=reason,
        credit=credit,
        token=str(data["token"]),
    )

    # إشعار المستخدم المتأثر عبر صندوق الإشعارات (نفس الـtoken ⇐ لا تكرار)
    builder = templates.balance_credited if credit else templates.balance_debited
    title, body = builder(
        amount_units=amount,
        new_balance_units=transaction.balance_after_units,
        reason=reason,
        symbol=symbol,
    )
    async with services.db.transaction() as tx:
        await services.notifications.notify_user_manual(
            tx,
            user_id=target.id,
            token=str(data["token"]),
            title=title,
            message=body,
            type=NotificationType.SYSTEM,
        )

    logger.info(
        "عدّل الأدمن %s رصيد المستخدم %s بمقدار %s (%s)",
        admin.telegram_id, target.telegram_id, amount, "credit" if credit else "debit",
    )
    clear_flow(context)

    await render(
        update,
        context,
        t.USER_BALANCE_DONE.format(
            name=safe(target.display_name, limit=30),
            icon="➕" if credit else "➖",
            operation=t.OP_CREDIT if credit else t.OP_DEBIT,
            amount=money_text(amount, symbol),
            balance=money_text(transaction.balance_after_units, symbol),
        ),
    )
    await _render_card(update, context, target.id, as_new=True)
    return ConversationHandler.END


# ============================= محادثة الحظر ============================ #


@guarded
@admin_required(Permission.USERS_BAN)
async def start_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء محادثة حظر مستخدم (السبب إجباري)."""
    await answer_callback(update)
    user_id = args(update).int_arg(0)
    target = await load_user_or_fail(context, user_id)
    start_flow(context, user_id=user_id)
    await render(
        update,
        context,
        t.USER_ASK_BAN_REASON.format(name=safe(target.display_name, limit=30)),
        cancel_only_kb(),
    )
    return ASK_BAN_REASON


@guarded
@admin_required(Permission.USERS_BAN)
async def receive_ban_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال سبب الحظر وعرض شاشة التأكيد."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_BAN_REASON

    reason = clean_text(message.text, field="سبب الحظر", max_length=200, min_length=3)
    data = update_flow(context, reason=reason)
    target = await load_user_or_fail(context, int(data["user_id"]))
    await send(
        update,
        context,
        t.USER_BAN_CONFIRM.format(
            name=safe(target.display_name, limit=30), reason=safe(reason, limit=200)
        ),
        confirm_cancel_kb(),
    )
    return CONFIRM_BAN


@guarded
@admin_required(Permission.USERS_BAN)
async def confirm_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ الحظر (الخدمة تتكفّل بالتدقيق وإشعار المستخدم)."""
    await answer_callback(update)
    data = flow(context)
    if not data.get("user_id") or not data.get("reason"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    target = await load_user_or_fail(context, int(data["user_id"]))
    await services.users.ban(admin, target.id, str(data["reason"]))
    clear_flow(context)

    await render(update, context, t.USER_BAN_DONE.format(name=safe(target.display_name, limit=30)))
    await _render_card(update, context, target.id, as_new=True)
    return ConversationHandler.END


@guarded
@admin_required(Permission.USERS_UNBAN)
async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """فك الحظر مباشرة (إجراء غير خطير ⇐ بلا شاشة تأكيد)."""
    services = services_of(context)
    admin = require_user(context)
    user_id = args(update).int_arg(0)
    target = await load_user_or_fail(context, user_id)

    changed = await services.users.unban(admin, target.id)
    await answer_callback(
        update,
        t.USER_UNBAN_DONE.format(name=target.display_name) if changed else t.NOTHING_CHANGED,
        alert=True,
    )
    await _render_card(update, context, target.id)


# =========================== محادثة الملاحظة =========================== #


@guarded
@admin_required(Permission.USERS_NOTE)
async def start_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء محادثة كتابة ملاحظة إدارية عن مستخدم."""
    await answer_callback(update)
    user_id = args(update).int_arg(0)
    target = await load_user_or_fail(context, user_id)
    start_flow(context, user_id=user_id)
    await render(
        update,
        context,
        t.USER_ASK_NOTE.format(name=safe(target.display_name, limit=30)),
        cancel_only_kb(),
    )
    return ASK_NOTE


@guarded
@admin_required(Permission.USERS_NOTE)
async def receive_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ الملاحظة الإدارية وعرض البطاقة محدَّثة."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_NOTE

    data = flow(context)
    if not data.get("user_id"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    note = clean_text(message.text, field="الملاحظة", max_length=500, min_length=2)
    services = services_of(context)
    admin = require_user(context)
    user_id = int(data["user_id"])
    await services.users.set_note(admin, user_id, note)
    clear_flow(context)

    await send(update, context, t.USER_NOTE_DONE)
    await _render_card(update, context, user_id, as_new=True)
    return ConversationHandler.END


# ============================= تغيير الدور ============================= #


@guarded
@admin_required(Permission.USERS_ROLE_CHANGE)
async def role_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض الأدوار المتاحة للإسناد."""
    await answer_callback(update)
    target = await load_user_or_fail(context, args(update).int_arg(0))
    await render(
        update,
        context,
        t.USER_ROLE_TITLE.format(
            name=safe(target.display_name, limit=30),
            role=t.ROLE_NAMES.get(target.role, safe(target.role)),
        ),
        user_role_kb(target),
    )


@guarded
@admin_required(Permission.USERS_ROLE_CHANGE)
async def role_confirm_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة التأكيد الثانية قبل تغيير الدور (إجراء خطير)."""
    await answer_callback(update)
    data = args(update)
    target = await load_user_or_fail(context, data.int_arg(0))
    new_role = data.arg(1)

    if new_role not in t.ASSIGNABLE_ROLES:
        await answer_callback(update, t.ERR_NO_PERMISSION, alert=True)
        return
    if new_role == target.role:
        await answer_callback(update, t.USER_ROLE_SAME, alert=True)
        return

    await render(
        update,
        context,
        t.USER_ROLE_CONFIRM.format(
            name=safe(target.display_name, limit=30),
            old_role=t.ROLE_NAMES.get(target.role, safe(target.role)),
            new_role=t.ASSIGNABLE_ROLES[new_role],
        ),
        user_role_confirm_kb(target.id, new_role),
    )


@guarded
@admin_required(Permission.USERS_ROLE_CHANGE)
async def role_apply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تنفيذ تغيير الدور بعد التأكيد (التدقيق داخل `AuthService.set_role`)."""
    data = args(update)
    user_id = data.int_arg(0)
    new_role = data.arg(1)
    if new_role not in t.ASSIGNABLE_ROLES:
        await answer_callback(update, t.ERR_NO_PERMISSION, alert=True)
        return

    services = services_of(context)
    admin = require_user(context)
    target = await load_user_or_fail(context, user_id)
    changed = await services.auth.set_role(admin, target.id, new_role)

    await answer_callback(
        update,
        t.USER_ROLE_DONE.format(
            name=target.display_name, role=t.ASSIGNABLE_ROLES[new_role]
        )
        if changed
        else t.NOTHING_CHANGED,
        alert=True,
    )
    await _render_card(update, context, target.id)


# ============================== المحادثات ============================== #


def _fallbacks(name: str) -> list:
    """المسارات الاحتياطية الموحّدة لمحادثات هذا القسم."""
    return [
        CallbackQueryHandler(cancel_admin_flow, pattern=pattern(NS_FLOW, "cancel")),
        CommandHandler("cancel", cancel_admin_flow),
        CommandHandler("start", exit_conversation(name)),
    ]


def conversations() -> list[ConversationHandler]:
    """محادثات قسم المستخدمين: البحث، تعديل الرصيد، الحظر، الملاحظة."""
    search = conversation(
        entry_points=[
            CallbackQueryHandler(start_search, pattern=pattern(NS_ADM_USERS, "search"))
        ],
        states={ASK_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_query)]},
        fallbacks=_fallbacks(ADMIN_FLOW_KEY),
        name="admin_user_search",
        per_chat=True,
        per_user=True,
    )

    balance = conversation(
        entry_points=[
            CallbackQueryHandler(start_credit, pattern=pattern(NS_ADM_USERS, "credit")),
            CallbackQueryHandler(start_debit, pattern=pattern(NS_ADM_USERS, "debit")),
        ],
        states={
            ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_amount)],
            ASK_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_balance_reason)
            ],
            CONFIRM_BALANCE: [
                CallbackQueryHandler(confirm_balance, pattern=pattern(NS_FLOW, "confirm"))
            ],
        },
        fallbacks=_fallbacks(ADMIN_FLOW_KEY),
        name="admin_user_balance",
        per_chat=True,
        per_user=True,
    )

    ban = conversation(
        entry_points=[CallbackQueryHandler(start_ban, pattern=pattern(NS_ADM_USERS, "ban"))],
        states={
            ASK_BAN_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ban_reason)
            ],
            CONFIRM_BAN: [
                CallbackQueryHandler(confirm_ban, pattern=pattern(NS_FLOW, "confirm"))
            ],
        },
        fallbacks=_fallbacks(ADMIN_FLOW_KEY),
        name="admin_user_ban",
        per_chat=True,
        per_user=True,
    )

    note = conversation(
        entry_points=[CallbackQueryHandler(start_note, pattern=pattern(NS_ADM_USERS, "note"))],
        states={ASK_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_note)]},
        fallbacks=_fallbacks(ADMIN_FLOW_KEY),
        name="admin_user_note",
        per_chat=True,
        per_user=True,
    )

    return [search, balance, ban, note]


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم المستخدمين خارج المحادثات."""
    return [
        CallbackQueryHandler(users_home_screen, pattern=pattern(NS_ADM_USERS, "home")),
        CallbackQueryHandler(user_card_screen, pattern=pattern(NS_ADM_USERS, "view")),
        CallbackQueryHandler(unban_user, pattern=pattern(NS_ADM_USERS, "unban")),
        CallbackQueryHandler(role_screen, pattern=pattern(NS_ADM_USERS, "role")),
        CallbackQueryHandler(role_confirm_screen, pattern=pattern(NS_ADM_USERS, "setrole")),
        CallbackQueryHandler(role_apply, pattern=pattern(NS_ADM_USERS, "roleok")),
        CallbackQueryHandler(user_orders_screen, pattern=pattern(NS_ADM_USERS, "orders")),
        CallbackQueryHandler(user_transactions_screen, pattern=pattern(NS_ADM_USERS, "tx")),
    ]
