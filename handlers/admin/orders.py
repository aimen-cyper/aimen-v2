"""
قسم «📦 الطلبات» في لوحة التحكم.

ما ينفّذه هذا الملف:
    • قوائم الطلبات مصنّفة: «تحتاج تدخلاً» (غير مؤكدة/فاشلة) · «نشطة» · «الكل».
    • بطاقة الطلب بكل تفاصيله التشغيلية (المزود، رقمه، المحاولات، آخر خطأ).
    • إعادة الفحص الفوري، الإلغاء مع استرجاع، تأكيد الفشل مع استرجاع،
      ربط رقم المزود يدوياً، وتجاوز الحالة يدوياً بسبب مكتوب.

قواعد مطبّقة:
    • لا حركة مالية في هذا الملف: الاسترجاع يتم داخل `OrderService` عبر
      `WalletService` فقط، ونحن نعرض النتيجة.
    • لا تغيير حالة بلا تحقق: كل الأزرار تمر بدوال الخدمة التي تفحص الحالة
      السابقة (`expected_statuses`) وجدول الانتقالات.
    • أزرار الإجراءات تظهر فقط حين تكون ممكنة فعلاً (حسب الحالة والصلاحية).
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

from core.enums import OrderStatus
from core.exceptions import OrderError
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
    symbol_of,
    update_flow,
)
from handlers.common.fallbacks import exit_conversation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    ADMIN_ORDER_FILTERS,
    admin_order_card_kb,
    admin_orders_kb,
    cancel_only_kb,
    confirm_cancel_kb,
    order_override_kb,
)
from keyboards.callback_data import NS_ADM_ORD, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from utils.formatters import (
    build_order_view,
    datetime_text,
    money_text,
    order_status_text,
    safe,
    short_link,
)
from utils.logging_setup import get_logger
from utils.validators import clean_text

logger = get_logger(__name__)

#: حالات محادثة الإلغاء / تأكيد الفشل (نفس التسلسل، تختلف العملية فقط)
ASK_REASON, CONFIRM_ACTION = range(2)

#: حالة محادثة ربط رقم المزود
ASK_PROVIDER_ID = 10

#: حالة محادثة تجاوز الحالة يدوياً
ASK_OVERRIDE_REASON = 20


def _filter_of(code: str) -> tuple[str, tuple[str, ...]]:
    """اسم التصفية وحالاتها (مع العودة للافتراضي عند رمز غير معروف)."""
    return ADMIN_ORDER_FILTERS.get(code, ADMIN_ORDER_FILTERS["att"])


async def _order_card_text(context: ContextTypes.DEFAULT_TYPE, order) -> str:
    """بناء نص بطاقة الطلب الإدارية."""
    services = services_of(context)
    symbol = await symbol_of(context)
    owner = await services.users.get(order.user_id)
    provider = await services.providers.get(order.provider_id)

    provider_line = ""
    if order.provider_order_id:
        provider_line = t.ORDER_PROVIDER_LINE.format(
            provider=safe(provider.name if provider else "—", limit=25),
            provider_order_id=safe(order.provider_order_id, limit=30),
        )
    view = build_order_view(order, symbol)
    progress_line = ""
    if view.delivered is not None and view.remains is not None:
        progress_line = t.ORDER_PROGRESS_LINE.format(delivered=view.delivered, remains=view.remains)
    # أخطاء الفحص (انقطاع/مهلة) في سطر مستقل عن `last_error` (خطأ الإرسال/الفشل النهائي)
    error_line = (
        t.ORDER_ERROR_LINE.format(error=safe(order.last_error, limit=140)) if order.last_error else ""
    )
    sync_lines = ""
    if view.provider_status_label:
        sync_lines += t.ORDER_PROVIDER_STATUS_LINE.format(status=safe(view.provider_status_label, limit=40))
    if view.last_check_ok_at:
        sync_lines += t.ORDER_LAST_OK_LINE.format(when=datetime_text(view.last_check_ok_at))
    if view.last_check_error:
        sync_lines += t.ORDER_CHECK_ERROR_LINE.format(
            error=safe(view.last_check_error, limit=140), streak=view.check_fail_streak
        )
    if view.next_check_at and order.status in (OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS):
        sync_lines += t.ORDER_NEXT_CHECK_LINE.format(when=datetime_text(view.next_check_at))
    refund_line = t.ORDER_REFUND_LINE.format(amount=view.refund_text) if view.refund_text else ""

    return t.ORDER_CARD.format(
        code=safe(order.public_code or f"#{order.id}", limit=20),
        name=safe(owner.display_name if owner else "—", limit=30),
        telegram_id=owner.telegram_id if owner else "—",
        service=safe(order.service_name_snapshot, limit=45),
        link=short_link(order.link),
        quantity=order.quantity,
        cost=view.cost_text,
        status=view.status_label,
        progress_line=progress_line,
        provider_line=provider_line,
        error_line=error_line + sync_lines,
        refund_line=refund_line,
        created=datetime_text(order.created_at),
        attempts=order.submit_attempts,
        checks=order.checks_count,
    )


async def _render_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    order_id: int,
    *,
    filter_code: str = "all",
    page: int = 1,
    as_new: bool = False,
) -> None:
    """عرض بطاقة طلب بعد أي إجراء (تحرير الرسالة أو إرسال رسالة جديدة)."""
    services = services_of(context)
    admin = require_user(context)
    order = await services.orders.admin_get(admin, order_id)
    perms = await permissions_of(context)
    text = await _order_card_text(context, order)
    markup = admin_order_card_kb(order, perms, filter_code=filter_code, page=page)
    if as_new:
        await send(update, context, text, markup)
    else:
        await render(update, context, text, markup)


# ============================= شاشات القراءة =========================== #


@guarded
@admin_required(Permission.ORDERS_VIEW)
async def orders_list_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة الطلبات حسب التصفية المختارة."""
    await answer_callback(update)
    data = args(update)
    filter_code = data.arg(0, "att")
    if filter_code not in ADMIN_ORDER_FILTERS:
        filter_code = "att"
    name, statuses = _filter_of(filter_code)

    services = services_of(context)
    admin = require_user(context)
    symbol = await symbol_of(context)

    total = await services.orders.admin_count(admin, statuses=list(statuses) or None)
    page, total_pages, offset = paginate(total, data.int_arg(1, 1))
    orders = await services.orders.admin_list(
        admin, statuses=list(statuses) or None, limit=PAGE_SIZE, offset=offset
    )

    if not orders:
        await render(
            update,
            context,
            t.ORDERS_EMPTY,
            admin_orders_kb([], filter_code=filter_code, page=1, total_pages=1, symbol=symbol),
        )
        return

    lines = "\n\n".join(
        f"{order_status_text(order.status)}\n"
        f"   📦 {safe(order.public_code or f'#{order.id}', limit=20)} · "
        f"{money_text(order.cost_units, symbol)}\n"
        f"   🛍 {safe(order.service_name_snapshot, limit=36)}\n"
        f"   🕒 {datetime_text(order.created_at)}"
        for order in orders
    )
    await render(
        update,
        context,
        f"{t.ORDERS_TITLE.format(filter_name=name, count=total, page=page, pages=total_pages)}"
        f"\n\n{lines}",
        admin_orders_kb(
            orders, filter_code=filter_code, page=page, total_pages=total_pages, symbol=symbol
        ),
    )


@guarded
@admin_required(Permission.ORDERS_VIEW)
async def order_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة طلب واحد."""
    await answer_callback(update)
    data = args(update)
    await _render_order(
        update,
        context,
        data.int_arg(0),
        filter_code=data.arg(1, "all"),
        page=data.int_arg(2, 1),
    )


@guarded
@admin_required(Permission.ORDERS_RECHECK)
async def recheck_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """طلب فحص فوري لحالة الطلب لدى المزود."""
    services = services_of(context)
    admin = require_user(context)
    order_id = args(update).int_arg(0)
    result = await services.orders.recheck_now(admin, order_id)
    await answer_callback(update, t.ORDER_RECHECK_RESULT.format(result=result), alert=True)
    await _render_order(update, context, order_id)


# ===================== محادثة الإلغاء / تأكيد الفشل ==================== #


async def _start_reason_flow(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, operation: str
) -> int:
    """
    الخطوة الأولى المشتركة بين «الإلغاء» و«تعليم كفاشل»: سؤال السبب.

    المدخلات:
        operation : "cancel" أو "fail" — يحدد نص السؤال والعملية المنفَّذة لاحقاً.
    """
    await answer_callback(update)
    order_id = args(update).int_arg(0)
    services = services_of(context)
    admin = require_user(context)
    order = await services.orders.admin_get(admin, order_id)
    start_flow(context, order_id=order_id, operation=operation)

    template = {
        "cancel": t.ORDER_ASK_CANCEL_REASON,
        "force_refund": t.ORDER_ASK_FORCE_REFUND_REASON,
    }.get(operation, t.ORDER_ASK_FAIL_REASON)
    await render(
        update,
        context,
        template.format(code=safe(order.public_code or f"#{order.id}", limit=20)),
        cancel_only_kb(),
    )
    return ASK_REASON


@guarded
@admin_required(Permission.ORDERS_CANCEL)
async def start_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء إلغاء طلب مع استرجاع كامل."""
    return await _start_reason_flow(update, context, operation="cancel")


@guarded
@admin_required(Permission.ORDERS_STATUS_OVERRIDE)
async def start_force_refund(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء استرجاع إجباري (بلا تأكيد إلغاء من المزود) — للأدمن الأعلى فقط."""
    return await _start_reason_flow(update, context, operation="force_refund")


@guarded
@admin_required(Permission.ORDERS_REFUND)
async def start_fail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء تعليم طلب كفاشل مع استرجاع كامل."""
    return await _start_reason_flow(update, context, operation="fail")


@guarded
@admin_required(Permission.ORDERS_VIEW)
async def receive_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال السبب وعرض شاشة التأكيد مع المبلغ الذي سيُسترجع."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_REASON

    data = flow(context)
    if not data.get("order_id"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    reason = clean_text(message.text, field="السبب", max_length=200, min_length=5)
    update_flow(context, reason=reason)

    services = services_of(context)
    admin = require_user(context)
    order = await services.orders.admin_get(admin, int(data["order_id"]))
    owner = await services.users.get(order.user_id)
    symbol = await symbol_of(context)

    await send(
        update,
        context,
        t.ORDER_ACTION_CONFIRM.format(
            operation={"cancel": t.OP_ORDER_CANCEL, "force_refund": t.OP_ORDER_FORCE_REFUND}.get(
                data["operation"], t.OP_ORDER_FAIL
            ),
            code=safe(order.public_code or f"#{order.id}", limit=20),
            name=safe(owner.display_name if owner else "—", limit=30),
            amount=money_text(order.refundable_units, symbol),
            reason=safe(reason, limit=200),
        ) + (t.ORDER_FORCE_REFUND_WARNING if data["operation"] == "force_refund" else ""),
        confirm_cancel_kb(),
    )
    return CONFIRM_ACTION


@guarded
@admin_required(Permission.ORDERS_VIEW)
async def confirm_reason_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ الإلغاء أو تأكيد الفشل بعد التأكيد (الاسترجاع داخل الخدمة)."""
    await answer_callback(update)
    data = flow(context)
    if not data.get("order_id") or not data.get("reason"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    order_id = int(data["order_id"])
    reason = str(data["reason"])
    operation = str(data["operation"])
    symbol = await symbol_of(context)

    try:
        if operation == "cancel":
            await services.auth.require_permission(
                admin, Permission.ORDERS_CANCEL, context=f"order:{order_id}"
            )
            refunded = await services.orders.admin_cancel(admin, order_id, reason)
            template = t.ORDER_CANCEL_DONE
        elif operation == "force_refund":
            await services.auth.require_permission(
                admin, Permission.ORDERS_STATUS_OVERRIDE, context=f"order:{order_id}"
            )
            refunded = await services.orders.admin_force_refund(admin, order_id, reason)
            template = t.ORDER_FORCE_REFUND_DONE
        else:
            await services.auth.require_permission(
                admin, Permission.ORDERS_REFUND, context=f"order:{order_id}"
            )
            refunded = await services.orders.admin_mark_failed(admin, order_id, reason)
            template = t.ORDER_FAIL_DONE
    except OrderError as exc:
        # رفض آمن (مثلاً: المزود لم يؤكد الإلغاء): لا مال تحرّك — نُنهي المحادثة ونعرض السبب مع بطاقة الطلب المحدّثة
        clear_flow(context)
        await render(update, context, exc.user_message)
        await _render_order(update, context, order_id, as_new=True)
        return ConversationHandler.END

    order = await services.orders.admin_get(admin, order_id)
    clear_flow(context)
    logger.info(
        "نفّذ الأدمن %s عملية %s على الطلب %s (استرجاع %s)",
        admin.telegram_id, operation, order_id, refunded,
    )

    await render(
        update,
        context,
        template.format(
            code=safe(order.public_code or f"#{order.id}", limit=20),
            amount=money_text(refunded, symbol),
        ),
    )
    await _render_order(update, context, order_id, as_new=True)
    return ConversationHandler.END


# ========================= محادثة ربط رقم المزود ======================= #


@guarded
@admin_required(Permission.ORDERS_LINK_PROVIDER_ID)
async def start_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء ربط الطلب برقمه عند المزود."""
    await answer_callback(update)
    order_id = args(update).int_arg(0)
    services = services_of(context)
    admin = require_user(context)
    order = await services.orders.admin_get(admin, order_id)
    start_flow(context, order_id=order_id)
    await render(
        update,
        context,
        t.ORDER_ASK_PROVIDER_ID.format(code=safe(order.public_code or f"#{order.id}", limit=20)),
        cancel_only_kb(),
    )
    return ASK_PROVIDER_ID


@guarded
@admin_required(Permission.ORDERS_LINK_PROVIDER_ID)
async def receive_provider_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ الربط (الخدمة تمنع ازدواج الرقم وتنقل الحالة إلى «أُرسل»)."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_PROVIDER_ID

    data = flow(context)
    if not data.get("order_id"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    provider_order_id = clean_text(
        message.text, field="رقم الطلب عند المزود", max_length=64, min_length=1
    )
    services = services_of(context)
    admin = require_user(context)
    order_id = int(data["order_id"])
    probe = await services.orders.probe_provider_link(admin, order_id, provider_order_id)
    await services.orders.admin_link_provider_order(admin, order_id, provider_order_id)
    order = await services.orders.admin_get(admin, order_id)
    clear_flow(context)

    await send(
        update,
        context,
        t.ORDER_LINK_DONE.format(
            code=safe(order.public_code or f"#{order.id}", limit=20),
            provider_order_id=safe(provider_order_id, limit=40),
            probe=safe(probe, limit=120),
        ),
    )
    await _render_order(update, context, order_id, as_new=True)
    return ConversationHandler.END


# ======================== محادثة تجاوز الحالة ========================== #


@guarded
@admin_required(Permission.ORDERS_STATUS_OVERRIDE)
async def override_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض الحالات المسموح الانتقال إليها من حالة الطلب الحالية."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    order = await services.orders.admin_get(admin, args(update).int_arg(0))
    await render(
        update,
        context,
        t.ORDER_OVERRIDE_TITLE.format(
            code=safe(order.public_code or f"#{order.id}", limit=20),
            status=order_status_text(order.status),
        ),
        order_override_kb(order),
    )


@guarded
@admin_required(Permission.ORDERS_STATUS_OVERRIDE)
async def start_override(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بعد اختيار الحالة الجديدة: طلب سبب مكتوب (إجباري ويُسجَّل باسم الأدمن)."""
    await answer_callback(update)
    data = args(update)
    order_id = data.int_arg(0)
    new_status = data.arg(1)
    start_flow(context, order_id=order_id, new_status=new_status)
    await send(update, context, t.ORDER_ASK_OVERRIDE_REASON, cancel_only_kb())
    return ASK_OVERRIDE_REASON


@guarded
@admin_required(Permission.ORDERS_STATUS_OVERRIDE)
async def receive_override_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ تجاوز الحالة بعد استلام السبب."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_OVERRIDE_REASON

    data = flow(context)
    if not data.get("order_id") or not data.get("new_status"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    reason = clean_text(message.text, field="سبب التجاوز", max_length=200, min_length=5)
    services = services_of(context)
    admin = require_user(context)
    order_id = int(data["order_id"])
    new_status = str(data["new_status"])

    changed = await services.orders.admin_override_status(admin, order_id, new_status, reason)
    clear_flow(context)
    order = await services.orders.admin_get(admin, order_id)

    await send(
        update,
        context,
        t.ORDER_OVERRIDE_DONE.format(
            code=safe(order.public_code or f"#{order.id}", limit=20),
            status=order_status_text(order.status),
        )
        if changed
        else t.ORDER_NOT_OVERRIDABLE,
    )
    await _render_order(update, context, order_id, as_new=True)
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
    """محادثات قسم الطلبات: الإلغاء/الفشل، ربط رقم المزود، تجاوز الحالة."""
    reason_flow = conversation(
        entry_points=[
            CallbackQueryHandler(start_cancel, pattern=pattern(NS_ADM_ORD, "cancel")),
            CallbackQueryHandler(start_fail, pattern=pattern(NS_ADM_ORD, "fail")),
            CallbackQueryHandler(start_force_refund, pattern=pattern(NS_ADM_ORD, "frefund")),
        ],
        states={
            ASK_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reason)],
            CONFIRM_ACTION: [
                CallbackQueryHandler(confirm_reason_action, pattern=pattern(NS_FLOW, "confirm"))
            ],
        },
        fallbacks=_fallbacks(),
        name="admin_order_cancel",
        per_chat=True,
        per_user=True,
    )

    link_flow = conversation(
        entry_points=[CallbackQueryHandler(start_link, pattern=pattern(NS_ADM_ORD, "link"))],
        states={
            ASK_PROVIDER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_provider_id)
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_order_link",
        per_chat=True,
        per_user=True,
    )

    override_flow = conversation(
        entry_points=[CallbackQueryHandler(start_override, pattern=pattern(NS_ADM_ORD, "setst"))],
        states={
            ASK_OVERRIDE_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_override_reason)
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_order_override",
        per_chat=True,
        per_user=True,
    )
    return [reason_flow, link_flow, override_flow]


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم الطلبات خارج المحادثات."""
    return [
        CallbackQueryHandler(orders_list_screen, pattern=pattern(NS_ADM_ORD, "list")),
        CallbackQueryHandler(order_card_screen, pattern=pattern(NS_ADM_ORD, "view")),
        CallbackQueryHandler(recheck_order, pattern=pattern(NS_ADM_ORD, "recheck")),
        CallbackQueryHandler(override_screen, pattern=pattern(NS_ADM_ORD, "force")),
    ]
