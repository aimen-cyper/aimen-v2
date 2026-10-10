"""
شاشات «📦 طلباتي»: القائمة بالتصفية والترقيم، بطاقة الطلب، وإلغاء الطلب.

قواعد:
    • المستخدم يرى طلباته فقط (الفحص داخل `OrderService.get_for_user`).
    • زر الإلغاء يظهر فقط عندما يكون الإلغاء ممكناً فعلاً حسب حالة الطلب
      وإعداد `user_cancel_before_submit` — لا أزرار كاذبة.
    • الإلغاء يمر بخطوة تأكيد، والاسترجاع يتم عبر المحفظة المركزية وحدها.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from core.enums import OrderStatus
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render
from keyboards.callback_data import unpack
from keyboards.user_kb import (
    ORDER_FILTERS,
    main_menu_kb,
    order_card_kb,
    order_cancel_confirm_kb,
    orders_kb,
)
from middlewares.context import reload_user, require_user, services_of
from texts import ar
from utils.formatters import (
    datetime_text,
    build_order_view,
    money_text,
    order_status_text,
    progress_bar,
    safe,
    short_link,
)

#: عدد الطلبات في الصفحة الواحدة
PAGE_SIZE = 6

#: الحالات التي يُسمح فيها للمستخدم بطلب الإلغاء (قبل وصول الطلب للمزود)
USER_CANCELABLE = (OrderStatus.PENDING,)


async def _can_cancel(context: ContextTypes.DEFAULT_TYPE, order) -> bool:
    """هل يُسمح للمستخدم بإلغاء هذا الطلب الآن؟ (حالة الطلب + إعداد النظام)."""
    if order.status not in USER_CANCELABLE:
        return False
    services = services_of(context)
    return await services.settings.get_bool("user_cancel_before_submit", True)


@guarded
async def orders_list_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة طلبات المستخدم حسب التصفية المختارة."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    filter_code = data.arg(0, "all")
    if filter_code not in ORDER_FILTERS:
        filter_code = "all"
    page = max(1, data.int_arg(1, 1))

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    statuses = list(ORDER_FILTERS[filter_code][1]) or None

    total = await services.orders.count_for_user(user, statuses=statuses)
    total_pages = max(1, -(-total // PAGE_SIZE))
    page = min(page, total_pages)
    orders = await services.orders.list_for_user(
        user, statuses=statuses, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE
    )

    if not orders:
        await render(
            update,
            context,
            ar.ORDERS_EMPTY,
            orders_kb([], filter_code=filter_code, page=1, total_pages=1, symbol=symbol),
        )
        return

    text = ar.ORDERS_TITLE.format(
        filter_name=ORDER_FILTERS[filter_code][0], page=page, pages=total_pages
    )
    await render(
        update,
        context,
        text,
        orders_kb(orders, filter_code=filter_code, page=page, total_pages=total_pages, symbol=symbol),
    )


@guarded
async def order_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة طلب واحد بكل تفاصيله الحقيقية."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    order_id = data.int_arg(0)
    filter_code = data.arg(1, "all")
    page = max(1, data.int_arg(2, 1))

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    order = await services.orders.get_for_user(user, order_id)

    view = build_order_view(order, symbol)

    progress = ""
    if view.delivered is not None and view.remains is not None:
        bar, percent = progress_bar(view.delivered, view.quantity)
        progress = ar.ORDER_PROGRESS_LINE.format(
            bar=bar, percent=percent, delivered=view.delivered, remains=view.remains
        )

    refund = ar.ORDER_REFUND_LINE.format(refund=view.refund_text) if view.refund_text else ""

    error = ""
    if order.last_error and order.status in {OrderStatus.FAILED, OrderStatus.REFUNDED}:
        error = ar.ORDER_ERROR_LINE.format(error=safe(order.last_error, limit=120))
    if view.last_check_ok_at and order.status in {OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS}:
        error += ar.ORDER_LAST_UPDATE_LINE.format(when=datetime_text(view.last_check_ok_at))

    text = ar.ORDER_CARD.format(
        code=view.code,
        service=safe(order.service_name_snapshot),
        link=short_link(order.link),
        quantity=order.quantity,
        progress=progress,
        cost=view.cost_text,
        refund=refund,
        status=view.status_label,
        created=datetime_text(order.created_at),
        error=error,
    )
    await render(
        update,
        context,
        text,
        order_card_kb(
            order,
            filter_code=filter_code,
            page=page,
            can_cancel=await _can_cancel(context, order),
        ),
    )


@guarded
async def order_cancel_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """خطوة التأكيد قبل إلغاء الطلب (لا حركة مالية قبل الضغط على تأكيد)."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    order_id = data.int_arg(0)

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    order = await services.orders.get_for_user(user, order_id)

    text = ar.ORDER_CANCEL_CONFIRM.format(
        code=order.public_code or f"#{order.id}",
        cost=money_text(order.cost_units, symbol),
    )
    await render(update, context, text, order_cancel_confirm_kb(order.id))


@guarded
async def order_cancel_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تنفيذ الإلغاء فعلياً عبر `OrderService` واسترجاع المبلغ كاملاً."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    order_id = data.int_arg(0)

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    order = await services.orders.get_for_user(user, order_id)

    refunded = await services.orders.cancel_by_user(user, order_id)
    await reload_user(context)

    await render(
        update,
        context,
        ar.ORDER_CANCEL_DONE.format(
            code=order.public_code or f"#{order.id}",
            refund=money_text(refunded, symbol),
        ),
        main_menu_kb(),
    )
