"""
محادثة إنشاء طلب جديد (ConversationHandler).

المسار: بطاقة الخدمة ← 🔗 الرابط ← 🔢 الكمية ← 🧾 المراجعة ← ✅ تأكيد.

ضمانات مهمة:
    • `client_request_id` يُولَّد **مرة واحدة عند بدء المحادثة**، فالضغط المزدوج
      على «تأكيد» يُعيد نفس الطلب ولا ينشئ طلبين (منع تكرار من طبقة الخدمات).
    • التحقق من الرابط والكمية يتم عند الإدخال، وتتكرر الخطوة عند الخطأ بدل
      إسقاط المحادثة.
    • عدم كفاية الرصيد لا يُنهي المسار بصمت: تُعرض قيمة النقص مع زر شحن مباشر.
    • الإلغاء متاح في كل خطوة (زر ❌ أو الأمر /cancel) ولا يُخصم شيء قبل التأكيد.
"""

from __future__ import annotations

import uuid

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from core.exceptions import InsufficientBalanceError
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.callback_data import unpack
from keyboards.common_kb import cancel_markup, confirm_cancel_markup
from keyboards.user_kb import insufficient_balance_kb, main_menu_kb
from middlewares.context import reload_user, require_user, services_of
from texts import ar
from utils.formatters import money_text, price_line, safe, short_link
from utils.link_rules import rule_of

#: حالات المحادثة
ASK_LINK, ASK_QUANTITY, CONFIRM = range(3)

#: مفتاح بيانات المحادثة داخل `user_data`
FLOW_KEY = "order_flow"


def _flow(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """قراءة بيانات المحادثة الحالية (قاموس فارغ إن ضاعت الجلسة)."""
    if context.user_data is None:
        return {}
    return context.user_data.get(FLOW_KEY) or {}


def _clear(context: ContextTypes.DEFAULT_TYPE) -> None:
    """مسح بيانات المحادثة بعد انتهائها أو إلغائها."""
    if context.user_data is not None:
        context.user_data.pop(FLOW_KEY, None)


def _link_hint(service) -> str:
    """تلميح طلب الرابط: مثال خاص بقاعدة الخدمة إن وُجدت، وإلا المثال العام."""
    rule = rule_of(service.link_rule)
    if rule is None:
        return ar.ORDER_LINK_HINT_GENERIC
    return ar.ORDER_LINK_HINT_RULE.format(label=rule.label, example=safe(rule.example))


@guarded
async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء المحادثة من زر «🛒 اطلب الآن» وسؤال المستخدم عن الرابط."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    service_id = data.int_arg(0)

    services = services_of(context)
    service = await services.catalog.get_available_service(service_id)

    if context.user_data is not None:
        context.user_data[FLOW_KEY] = {
            "service_id": service.id,
            "service_name": service.name,
            # معرف فريد للطلب يُولَّد الآن: الضغط المزدوج على تأكيد لن يُنشئ طلبين
            "client_request_id": uuid.uuid4().hex,
        }

    await render(
        update,
        context,
        ar.ORDER_ASK_LINK.format(service=safe(service.name), hint=_link_hint(service)),
        cancel_markup(),
    )
    return ASK_LINK


@guarded
async def receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال الرابط والتحقق منه ثم سؤال المستخدم عن الكمية."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, ar.ERR_NOT_TEXT, cancel_markup())
        return ASK_LINK

    flow = _flow(context)
    if not flow:
        await send(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    services = services_of(context)
    service = await services.catalog.get_available_service(flow["service_id"])

    from utils.validators import validate_link      # تحقق فوري قبل إزعاج المستخدم بخطوة أخرى

    link = validate_link(message.text, pattern=service.link_pattern, rule=service.link_rule)
    flow["link"] = link

    await send(
        update,
        context,
        ar.ORDER_ASK_QUANTITY.format(
            service=safe(service.name),
            link=short_link(link),
            min_quantity=service.min_quantity,
            max_quantity=service.max_quantity,
        ),
        cancel_markup(),
    )
    return ASK_QUANTITY


@guarded
async def receive_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال الكمية وحساب التكلفة وعرض ملخص الطلب قبل التأكيد."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, ar.ERR_NOT_TEXT, cancel_markup())
        return ASK_QUANTITY

    flow = _flow(context)
    if not flow or "link" not in flow:
        await send(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    usd_rate = await services.settings.usd_rate()
    service = await services.catalog.get_available_service(flow["service_id"])

    quote = await services.catalog.quote(service, message.text)
    flow["quantity"] = quote.quantity
    flow["cost_units"] = quote.cost_units

    balance = user.balance_units
    if balance < quote.cost_units:
        text = ar.ORDER_SUMMARY_NO_BALANCE.format(
            service=safe(service.name),
            link=short_link(flow["link"]),
            quantity=quote.quantity,
            cost=price_line(quote.cost_units, symbol, usd_rate),
            balance=money_text(balance, symbol),
            missing=money_text(quote.cost_units - balance, symbol),
        )
        await send(update, context, text, insufficient_balance_kb(service.category_id, 1))
        _clear(context)
        return ConversationHandler.END

    text = ar.ORDER_SUMMARY.format(
        service=safe(service.name),
        link=short_link(flow["link"]),
        quantity=quote.quantity,
        cost=price_line(quote.cost_units, symbol, usd_rate),
        balance=money_text(balance, symbol),
        balance_after=money_text(balance - quote.cost_units, symbol),
    )
    await send(update, context, text, confirm_cancel_markup())
    return CONFIRM


@guarded
async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تأكيد الطلب: إنشاؤه عبر `OrderService` (خصم + سجل + إشعار في معاملة واحدة)."""
    await answer_callback(update)
    flow = _flow(context)
    if not flow or "quantity" not in flow:
        await render(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    usd_rate = await services.settings.usd_rate()

    try:
        order = await services.orders.create_order(
            user,
            service_id=flow["service_id"],
            link=flow["link"],
            quantity=flow["quantity"],
            client_request_id=flow["client_request_id"],
        )
    except InsufficientBalanceError:
        # قد يكون الرصيد أُنفق في محادثة أخرى بين المراجعة والتأكيد
        service = await services.catalog.get_available_service(flow["service_id"])
        fresh = await reload_user(context)
        await render(
            update,
            context,
            ar.ORDER_SUMMARY_NO_BALANCE.format(
                service=safe(service.name),
                link=short_link(flow["link"]),
                quantity=flow["quantity"],
                cost=price_line(flow["cost_units"], symbol, usd_rate),
                balance=money_text(fresh.balance_units, symbol),
                missing=money_text(max(0, flow["cost_units"] - fresh.balance_units), symbol),
            ),
            insufficient_balance_kb(service.category_id, 1),
        )
        _clear(context)
        return ConversationHandler.END

    fresh = await reload_user(context)
    await render(
        update,
        context,
        ar.ORDER_CREATED.format(
            code=order.public_code or f"#{order.id}",
            service=safe(order.service_name_snapshot),
            quantity=order.quantity,
            cost=price_line(order.cost_units, symbol, usd_rate),
            balance=money_text(fresh.balance_units, symbol),
        ),
        main_menu_kb(),
    )
    # الشاشة تتجدد تلقائياً عند تغيّر حالة الطلب ما لم ينتقل المستخدم منها إلى شاشة أخرى
    query = update.callback_query
    if query is not None and query.message is not None:
        await services.order_messages.register(
            order_id=order.id, kind="user_confirm", chat_id=query.message.chat_id, message_id=query.message.message_id
        )
    _clear(context)
    return ConversationHandler.END


@guarded
async def cancel_order_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء المحادثة في أي خطوة (زر ❌ أو الأمر /cancel) — لا خصم ولا طلب."""
    await answer_callback(update)
    _clear(context)
    if update.callback_query is not None:
        await render(update, context, ar.ORDER_CANCELLED_FLOW, main_menu_kb())
    else:
        await send(update, context, ar.ORDER_CANCELLED_FLOW, main_menu_kb())
    return ConversationHandler.END
