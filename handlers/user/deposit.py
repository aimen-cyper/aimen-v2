"""
محادثة شحن الرصيد (ConversationHandler) + شاشة طلبات الشحن السابقة.

المسار: 🏦 اختيار الطريقة ← 💵 المبلغ ← 🧾 رقم العملية ← 📸 الإيصال (اختياري)
        ← 🧾 مراجعة ← ✅ إرسال للمراجعة.

قواعد:
    • لا يُضاف أي رصيد هنا إطلاقاً — الطلب يُسجَّل بحالة «قيد المراجعة» فقط،
      والرصيد يُضاف من لوحة الأدمن عبر `PaymentService.approve` (المرحلة 4).
    • حدود المبلغ تأتي من طريقة الدفع وإلا من الإعدادات العامة.
    • رقم العملية يُفحص فوراً ضد التكرار (منع إعادة استخدام نفس الإيصال).
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.callback_data import unpack
from keyboards.common_kb import cancel_markup, confirm_cancel_markup, skip_cancel_markup
from keyboards.user_kb import deposit_methods_kb, deposits_kb, main_menu_kb, wallet_kb
from middlewares.context import require_user, services_of
from texts import ar
from utils.formatters import money_text, payment_line, safe
from core.money import from_units
from utils.validators import (
    parse_amount_units,
    validate_amount_range,
    validate_transaction_reference,
)

#: حالات المحادثة
CHOOSE_METHOD, ASK_AMOUNT, ASK_REFERENCE, ASK_PROOF, CONFIRM = range(5)

#: مفتاح بيانات المحادثة
FLOW_KEY = "deposit_flow"

#: عدد طلبات الشحن المعروضة في الصفحة
PAGE_SIZE = 5


def _flow(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """قراءة بيانات محادثة الشحن الحالية."""
    if context.user_data is None:
        return {}
    return context.user_data.get(FLOW_KEY) or {}


def _clear(context: ContextTypes.DEFAULT_TYPE) -> None:
    """مسح بيانات المحادثة بعد الانتهاء أو الإلغاء."""
    if context.user_data is not None:
        context.user_data.pop(FLOW_KEY, None)


async def _fee_lines(context: ContextTypes.DEFAULT_TYPE, method, amount_units: int) -> str:
    """
    سطرا «الرسوم» و«سيُضاف لرصيدك» للطريقة ذات الرسوم (أو نص فارغ).

    تُحترم إعداد `deposit_fee_visible`: بعض المالكين يفضّلون إخفاء تفصيل
    الرسوم وعرض المبلغ كما هو — والافتراضي هو الإظهار (الشفافية أولاً).
    """
    services = services_of(context)
    if not method.has_fees or not await services.payments.fee_visible_to_user():
        return ""
    symbol = await services.settings.money_symbol()
    fee_units, net_units = services.payments.fee_for(method, amount_units)
    return ar.DEPOSIT_FEE_LINES.format(
        fee=money_text(fee_units, symbol), net=money_text(net_units, symbol)
    )


async def _summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """عرض مراجعة نهائية لطلب الشحن قبل إرساله."""
    flow = _flow(context)
    services = services_of(context)
    symbol = await services.settings.money_symbol()
    amount_units = flow.get("amount_units", 0)
    method = await services.payments.get_method(flow["method_id"])
    text = ar.DEPOSIT_SUMMARY.format(
        method=safe(flow.get("method_name", "")),
        amount=money_text(amount_units, symbol),
        fee_lines=await _fee_lines(context, method, amount_units),
        reference=safe(flow.get("reference") or "—"),
        proof=ar.DEPOSIT_PROOF_ATTACHED if flow.get("proof_file_id") else ar.DEPOSIT_PROOF_NONE,
    )
    await send(update, context, text, confirm_cancel_markup())
    return CONFIRM


@guarded
async def start_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء محادثة الشحن بعرض طرق الدفع المفعّلة."""
    await answer_callback(update)
    services = services_of(context)
    methods = await services.payments.active_methods()
    if not methods:
        await render(update, context, ar.DEPOSIT_METHODS_EMPTY, wallet_kb())
        return ConversationHandler.END

    if context.user_data is not None:
        context.user_data[FLOW_KEY] = {}
    await render(update, context, ar.DEPOSIT_METHODS_TITLE, deposit_methods_kb(methods))
    return CHOOSE_METHOD


@guarded
async def choose_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ الطريقة المختارة وعرض تعليماتها وحدودها وسؤال المستخدم عن المبلغ."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    method_id = data.int_arg(0)

    services = services_of(context)
    method = await services.payments.get_method(method_id)
    limits = await services.payments.limits_text(method)

    if context.user_data is not None:
        context.user_data[FLOW_KEY] = {
            "method_id": method.id,
            "method_name": method.name_ar,
            "requires_proof": bool(method.requires_proof),
        }

    fee_line = ""
    if method.has_fees and await services.payments.fee_visible_to_user():
        fee_line = ar.DEPOSIT_FEE_NOTICE.format(fee=await services.payments.fee_text(method))

    text = ar.DEPOSIT_ASK_AMOUNT.format(
        method=safe(method.name_ar),
        instructions=safe(method.instructions_ar or ""),
        account=safe(method.account_details or ""),
        limits=limits,
        fee_line=fee_line,
    )
    await render(update, context, text, cancel_markup())
    return ASK_AMOUNT


@guarded
async def receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال المبلغ والتحقق من الحدود قبل الانتقال لرقم العملية."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, ar.ERR_NOT_TEXT, cancel_markup())
        return ASK_AMOUNT

    flow = _flow(context)
    if not flow.get("method_id"):
        await send(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    services = services_of(context)
    symbol = await services.settings.money_symbol()
    method = await services.payments.get_method(flow["method_id"])
    minimum, maximum = await services.payments.method_limits(method)

    amount_units = parse_amount_units(message.text)
    validate_amount_range(
        amount_units, min_units=minimum, max_units=maximum, label="مبلغ الشحن"
    )
    flow["amount_units"] = amount_units
    # نحتفظ بالمبلغ نصاً عشرياً دقيقاً (لا float) لأن خدمة الدفع تُعيد تحليله بنفسها
    flow["raw_amount"] = str(from_units(amount_units))

    if flow.get("requires_proof"):
        await send(
            update,
            context,
            ar.DEPOSIT_ASK_REFERENCE.format(amount=money_text(amount_units, symbol)),
            cancel_markup(),
        )
        return ASK_REFERENCE

    return await _summary(update, context)


@guarded
async def receive_reference(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال رقم عملية التحويل ثم طلب صورة الإيصال (اختيارية)."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, ar.ERR_NOT_TEXT, cancel_markup())
        return ASK_REFERENCE

    flow = _flow(context)
    if not flow.get("amount_units"):
        await send(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    flow["reference"] = validate_transaction_reference(message.text, required=True)
    await send(update, context, ar.DEPOSIT_ASK_PROOF, skip_cancel_markup())
    return ASK_PROOF


@guarded
async def receive_proof(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال صورة الإيصال وحفظ معرف الملف لعرضه لاحقاً للأدمن."""
    message = update.effective_message
    flow = _flow(context)
    if not flow:
        await send(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    if message is not None and message.photo:
        flow["proof_file_id"] = message.photo[-1].file_id      # أعلى دقة متاحة
        flow["proof_file_type"] = "photo"
    elif message is not None and message.document:
        flow["proof_file_id"] = message.document.file_id
        flow["proof_file_type"] = "document"
    else:
        await send(update, context, ar.DEPOSIT_ASK_PROOF, skip_cancel_markup())
        return ASK_PROOF

    return await _summary(update, context)


@guarded
async def skip_proof(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تخطي إرفاق الإيصال والانتقال إلى المراجعة."""
    await answer_callback(update)
    return await _summary(update, context)


@guarded
async def confirm_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إرسال طلب الشحن للمراجعة (بلا أي إضافة رصيد)."""
    await answer_callback(update)
    flow = _flow(context)
    if not flow.get("amount_units"):
        await render(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()

    payment = await services.payments.create_payment(
        user,
        method_id=flow["method_id"],
        raw_amount=flow["raw_amount"],
        transaction_reference=flow.get("reference"),
        proof_file_id=flow.get("proof_file_id"),
        proof_file_type=flow.get("proof_file_type"),
    )

    # لقطة الرسوم محفوظة على الطلب نفسه، فنعرضها من الطلب لا من الطريقة
    fee_lines = ""
    if payment.fee_units and await services.payments.fee_visible_to_user():
        fee_lines = ar.DEPOSIT_FEE_LINES.format(
            fee=money_text(payment.fee_units, symbol),
            net=money_text(payment.net_units, symbol),
        )

    await render(
        update,
        context,
        ar.DEPOSIT_CREATED.format(
            payment_id=payment.id,
            amount=money_text(payment.amount_units, symbol),
            fee_lines=fee_lines,
        ),
        main_menu_kb(),
    )
    _clear(context)
    return ConversationHandler.END


@guarded
async def cancel_deposit_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء محادثة الشحن في أي خطوة."""
    await answer_callback(update)
    _clear(context)
    if update.callback_query is not None:
        await render(update, context, ar.CANCELLED, wallet_kb())
    else:
        await send(update, context, ar.CANCELLED, wallet_kb())
    return ConversationHandler.END


# ---------------------- شاشات خارج المحادثة ---------------------------- #


@guarded
async def deposits_list_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة طلبات الشحن السابقة مع إمكانية إلغاء المعلّق منها."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    page = max(1, data.int_arg(0, 1))

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()

    payments = await services.payments.list_for_user(
        user, limit=PAGE_SIZE + 1, offset=(page - 1) * PAGE_SIZE
    )
    has_next = len(payments) > PAGE_SIZE
    payments = payments[:PAGE_SIZE]
    total_pages = page + 1 if has_next else page

    if not payments:
        await render(update, context, ar.DEPOSITS_EMPTY, deposits_kb([], page=1, total_pages=1))
        return

    lines = "\n\n".join(payment_line(item, symbol=symbol) for item in payments)
    await render(
        update,
        context,
        ar.DEPOSITS_TITLE.format(lines=lines),
        deposits_kb(payments, page=page, total_pages=total_pages),
    )


@guarded
async def cancel_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إلغاء طلب شحن معلّق أرسله المستخدم بالخطأ."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    payment_id = data.int_arg(0)

    services = services_of(context)
    user = require_user(context)
    await services.payments.cancel_by_user(user, payment_id)
    await render(update, context, ar.DEPOSIT_CANCELLED.format(payment_id=payment_id), wallet_kb())
