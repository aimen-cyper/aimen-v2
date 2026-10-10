"""
قسم «💰 المدفوعات» في لوحة التحكم: مراجعة طلبات الشحن واعتمادها أو رفضها.

المسار المعتمد (مطابق للبند 4.3 من تصميم المرحلة 0):
    قائمة المعلّق ← بطاقة الطلب ← عرض الإثبات ← (اعتماد بمبلغ قابل للتعديل
    + شاشة تأكيد) أو (رفض بسبب إجباري يصل للمستخدم).

قواعد مطبّقة:
    • إضافة الرصيد تتم داخل `PaymentService.approve` وحدها (معاملة واحدة
      تشمل: تغيير الحالة + الحركة المالية + التدقيق + إشعار المستخدم).
    • الضغط المزدوج على «اعتماد» لا يضيف الرصيد مرتين: تغيير الحالة مشروط
      بالحالة السابقة، والثانية ترفع `DuplicateOperationError` برسالة عربية.
    • المبلغ المضاف قد يختلف عن المبلغ المطلوب (حوالة ناقصة مثلاً) — ولذلك
      تُعرض شاشة تأكيد تبيّن بالضبط ما سيُضاف.
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

from core.enums import PaymentStatus
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
    ADMIN_PAYMENT_FILTERS,
    cancel_only_kb,
    payment_approve_kb,
    payment_card_kb,
    payments_list_kb,
    payments_search_kb,
)
from keyboards.callback_data import NS_ADM_PAY, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from utils.formatters import datetime_text, money_text, payment_status_text, safe
from utils.logging_setup import get_logger
from utils.validators import clean_text, parse_amount_units, validate_amount_range

logger = get_logger(__name__)

#: حالات محادثة الاعتماد
CONFIRM_APPROVE, ASK_CREDITED = range(2)

#: حالة محادثة الرفض
ASK_REJECT_REASON = 10

#: حالة محادثة البحث عن حوالة
ASK_SEARCH_TERM = 20

#: التصفية الافتراضية لقائمة طلبات الشحن
DEFAULT_FILTER = "pend"


async def _payment_card_text(context: ContextTypes.DEFAULT_TYPE, payment) -> str:
    """بناء نص بطاقة طلب الشحن (بيانات الطلب + صاحبه + حالة المراجعة)."""
    services = services_of(context)
    symbol = await symbol_of(context)
    owner = await services.users.get(payment.user_id)
    method = await services.payments.get_method(payment.method_id, require_active=False)

    proof = t.PAYMENT_PROOF_NONE
    if payment.proof_file_id:
        proof = (
            t.PAYMENT_PROOF_PHOTO if payment.proof_file_type == "photo" else t.PAYMENT_PROOF_DOC
        )

    review_line = ""
    if payment.admin_id:
        reviewer = await services.users.get(payment.admin_id)
        detail = payment.reject_reason or payment.admin_note or "—"
        review_line = t.PAYMENT_REVIEW_LINE.format(
            admin=safe(reviewer.display_name if reviewer else str(payment.admin_id), limit=30),
            detail=safe(detail, limit=200),
        )

    # سطر الرسوم يظهر فقط للطلبات التي اقتُطعت منها رسوم طريقة الشحن
    fee_line = ""
    if payment.fee_units:
        fee_line = t.PAYMENT_FEE_LINE.format(
            fee=money_text(payment.fee_units, symbol),
            net=money_text(payment.net_units, symbol),
        )

    return t.PAYMENT_CARD.format(
        payment_id=payment.id,
        name=safe(owner.display_name if owner else "—", limit=30),
        telegram_id=owner.telegram_id if owner else "—",
        amount=money_text(payment.amount_units, symbol),
        method=safe(method.name_ar if method else "—", limit=30),
        reference=safe(payment.transaction_reference or "—", limit=40),
        proof=proof,
        created=datetime_text(payment.created_at),
        expires=datetime_text(payment.expires_at) if payment.expires_at else "—",
        status=payment_status_text(payment.status),
        fee_line=fee_line,
        note_line=t.PAYMENT_NOTE_LINE.format(note=safe(payment.user_note, limit=200))
        if payment.user_note
        else "",
        review_line=review_line,
    )


async def _render_payment(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    payment_id: int,
    *,
    as_new: bool = False,
    filter_code: str = DEFAULT_FILTER,
    page: int = 1,
) -> None:
    """عرض بطاقة طلب شحن بعد أي إجراء عليه (مع حفظ موضع القائمة للرجوع)."""
    services = services_of(context)
    admin = require_user(context)
    payment = await services.payments.admin_get(admin, payment_id)
    perms = await permissions_of(context)
    text = await _payment_card_text(context, payment)
    markup = payment_card_kb(
        payment,
        perms,
        is_pending=payment.status == PaymentStatus.PENDING,
        filter_code=filter_code,
        page=page,
    )
    if as_new:
        await send(update, context, text, markup)
    else:
        await render(update, context, text, markup)


# ============================= شاشات القراءة =========================== #


def _payment_lines(payments, symbol: str) -> str:
    """أسطر عرض طلبات الشحن في القوائم ونتائج البحث (سطر مختصر لكل طلب)."""
    return "\n\n".join(
        f"💳 <b>#{payment.id}</b> · {money_text(payment.amount_units, symbol)}"
        f" · {payment_status_text(payment.status)}\n"
        f"   🔢 {safe(payment.transaction_reference or '—', limit=30)}\n"
        f"   🕒 {datetime_text(payment.created_at)}"
        for payment in payments
    )


@guarded
@admin_required(Permission.PAYMENTS_VIEW)
async def payments_list_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    قائمة طلبات الشحن مُصفّاة (معلّقة / معتمدة / مرفوضة / الكل).

    المعلّقة تظهر الأقدم أولاً (طابور مراجعة عادل)، وبقية الحالات الأحدث أولاً.
    """
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    symbol = await symbol_of(context)
    perms = await permissions_of(context)

    data = args(update)
    filter_code = data.arg(0) or DEFAULT_FILTER
    if filter_code not in ADMIN_PAYMENT_FILTERS:
        filter_code = DEFAULT_FILTER
    filter_name, statuses = ADMIN_PAYMENT_FILTERS[filter_code]

    total = await services.payments.admin_count(admin, statuses=statuses)
    page, total_pages, offset = paginate(total, data.int_arg(1, 1))
    payments = await services.payments.admin_list(
        admin, statuses=statuses, limit=PAGE_SIZE, offset=offset
    )

    if not payments:
        empty_text = (
            t.PAYMENTS_EMPTY
            if filter_code == DEFAULT_FILTER
            else t.PAYMENTS_FILTER_EMPTY.format(filter_name=filter_name)
        )
        await render(
            update,
            context,
            empty_text,
            payments_list_kb(
                [], page=1, total_pages=1, symbol=symbol, filter_code=filter_code, perms=perms
            ),
        )
        return

    title = t.PAYMENTS_FILTER_TITLE.format(
        filter_name=filter_name, count=total, page=page, pages=total_pages
    )
    await render(
        update,
        context,
        f"{title}\n\n{_payment_lines(payments, symbol)}",
        payments_list_kb(
            payments,
            page=page,
            total_pages=total_pages,
            symbol=symbol,
            filter_code=filter_code,
            perms=perms,
        ),
    )


@guarded
@admin_required(Permission.PAYMENTS_VIEW)
async def payment_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة طلب شحن واحد (مع تذكّر التصفية والصفحة التي جاء منها)."""
    await answer_callback(update)
    data = args(update)
    await _render_payment(
        update,
        context,
        data.int_arg(0),
        filter_code=data.arg(1) or DEFAULT_FILTER,
        page=max(1, data.int_arg(2, 1)),
    )


@guarded
@admin_required(Permission.PAYMENTS_VIEW)
async def payment_proof_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إرسال ملف إثبات الدفع كما رفعه المستخدم (صورة أو مستند)."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    payment = await services.payments.admin_get(admin, args(update).int_arg(0))
    chat = update.effective_chat

    if not payment.proof_file_id or chat is None:
        await answer_callback(update, t.PAYMENT_PROOF_NONE, alert=True)
        return

    caption = t.PAYMENT_PROOF_CAPTION.format(payment_id=payment.id)
    if payment.proof_file_type == "photo":
        await context.bot.send_photo(chat_id=chat.id, photo=payment.proof_file_id, caption=caption)
    else:
        await context.bot.send_document(
            chat_id=chat.id, document=payment.proof_file_id, caption=caption
        )


# ============================ محادثة الاعتماد ========================== #


async def _approve_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, *, as_new: bool = False) -> int:
    """عرض شاشة تأكيد الاعتماد بالمبلغ الحالي (المطلوب أو المعدَّل)."""
    data = flow(context)
    services = services_of(context)
    admin = require_user(context)
    payment = await services.payments.admin_get(admin, int(data["payment_id"]))
    owner = await services.users.get(payment.user_id)
    symbol = await symbol_of(context)
    # الافتراضي هو الصافي بعد رسوم الطريقة (كما ستحسبه الخدمة عند الاعتماد)
    credited = int(data.get("credited_units") or payment.net_units)

    text = t.PAYMENT_APPROVE_CONFIRM.format(
        payment_id=payment.id,
        name=safe(owner.display_name if owner else "—", limit=30),
        amount=money_text(payment.amount_units, symbol),
        fee_line=t.PAYMENT_APPROVE_FEE_LINE.format(fee=money_text(payment.fee_units, symbol))
        if payment.fee_units
        else "",
        credited=money_text(credited, symbol),
        balance_after=money_text((owner.balance_units if owner else 0) + credited, symbol),
    )
    if as_new:
        await send(update, context, text, payment_approve_kb())
    else:
        await render(update, context, text, payment_approve_kb())
    return CONFIRM_APPROVE


@guarded
@admin_required(Permission.PAYMENTS_APPROVE)
async def start_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء اعتماد طلب شحن: شاشة التأكيد مع المبلغ المطلوب."""
    await answer_callback(update)
    payment_id = args(update).int_arg(0)
    start_flow(context, payment_id=payment_id)
    return await _approve_confirm(update, context)


@guarded
@admin_required(Permission.PAYMENTS_APPROVE)
async def ask_credited_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """طلب مبلغ مختلف عن المبلغ المذكور في الطلب (حوالة ناقصة أو زائدة)."""
    await answer_callback(update)
    data = flow(context)
    if not data.get("payment_id"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    payment = await services.payments.admin_get(admin, int(data["payment_id"]))
    symbol = await symbol_of(context)
    await render(
        update,
        context,
        t.PAYMENT_ASK_AMOUNT.format(
            amount=money_text(payment.amount_units, symbol),
            net=money_text(payment.net_units, symbol),
        ),
        cancel_only_kb(),
    )
    return ASK_CREDITED


@guarded
@admin_required(Permission.PAYMENTS_APPROVE)
async def receive_credited_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال المبلغ المعدَّل والعودة إلى شاشة التأكيد."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_CREDITED

    units = validate_amount_range(parse_amount_units(message.text), min_units=1, label="المبلغ")
    update_flow(context, credited_units=units)
    return await _approve_confirm(update, context, as_new=True)


@guarded
@admin_required(Permission.PAYMENTS_APPROVE)
async def confirm_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """اعتماد الطلب فعلياً: إضافة الرصيد + الحركة المالية + الإشعار (داخل الخدمة)."""
    await answer_callback(update)
    data = flow(context)
    if not data.get("payment_id"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    payment_id = int(data["payment_id"])
    credited = data.get("credited_units")
    symbol = await symbol_of(context)

    transaction = await services.payments.approve(
        admin,
        payment_id,
        credited_units=int(credited) if credited else None,
        admin_note=None,
    )
    owner = await services.users.get(transaction.user_id)
    clear_flow(context)
    logger.info("اعتمد الأدمن %s طلب الشحن #%s", admin.telegram_id, payment_id)

    await render(
        update,
        context,
        t.PAYMENT_APPROVED.format(
            payment_id=payment_id,
            name=safe(owner.display_name if owner else "—", limit=30),
            credited=money_text(transaction.amount_units, symbol),
            balance=money_text(transaction.balance_after_units, symbol),
        ),
    )
    await _render_payment(update, context, payment_id, as_new=True)
    return ConversationHandler.END


# ============================= محادثة الرفض ============================ #


@guarded
@admin_required(Permission.PAYMENTS_REJECT)
async def start_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء رفض طلب شحن: السبب إجباري ويصل للمستخدم كما كُتب."""
    await answer_callback(update)
    payment_id = args(update).int_arg(0)
    start_flow(context, payment_id=payment_id)
    await render(
        update, context, t.PAYMENT_ASK_REJECT_REASON.format(payment_id=payment_id), cancel_only_kb()
    )
    return ASK_REJECT_REASON


@guarded
@admin_required(Permission.PAYMENTS_REJECT)
async def receive_reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ الرفض بعد استلام السبب (الخدمة تُشعر المستخدم وتسجّل التدقيق)."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_REJECT_REASON

    data = flow(context)
    if not data.get("payment_id"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    reason = clean_text(message.text, field="سبب الرفض", max_length=300, min_length=3)
    services = services_of(context)
    admin = require_user(context)
    payment_id = int(data["payment_id"])
    await services.payments.reject(admin, payment_id, reason)
    clear_flow(context)
    logger.info("رفض الأدمن %s طلب الشحن #%s", admin.telegram_id, payment_id)

    await send(
        update,
        context,
        t.PAYMENT_REJECTED.format(payment_id=payment_id, reason=safe(reason, limit=300)),
    )
    await _render_payment(update, context, payment_id, as_new=True)
    return ConversationHandler.END


# ============================= محادثة البحث ============================ #


@guarded
@admin_required(Permission.PAYMENTS_VIEW)
async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء البحث عن طلب شحن برقم العملية أو برقم الطلب."""
    await answer_callback(update)
    start_flow(context)
    await render(update, context, t.PAYMENT_SEARCH_ASK, cancel_only_kb())
    return ASK_SEARCH_TERM


@guarded
@admin_required(Permission.PAYMENTS_VIEW)
async def receive_search_term(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    تنفيذ البحث وعرض النتائج كأزرار تفتح بطاقة الطلب مباشرة.

    يشمل البحث كل الحالات (حتى الملغاة والمنتهية) لأن سؤال العميل عادةً
    عن حوالة لم تصل، وقد تكون رُفضت أو انتهت صلاحيتها.
    """
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_SEARCH_TERM

    services = services_of(context)
    admin = require_user(context)
    symbol = await symbol_of(context)
    term = message.text.strip()

    results = await services.payments.admin_search(admin, term)
    clear_flow(context)
    if not results:
        await send(
            update,
            context,
            t.PAYMENT_SEARCH_EMPTY.format(term=safe(term, limit=40)),
            payments_search_kb([], symbol=symbol),
        )
        return ConversationHandler.END

    await send(
        update,
        context,
        t.PAYMENT_SEARCH_TITLE.format(
            term=safe(term, limit=40),
            count=len(results),
            lines=_payment_lines(results, symbol),
        ),
        payments_search_kb(results, symbol=symbol),
    )
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
    """محادثات القسم: الاعتماد، الرفض، والبحث عن حوالة."""
    approve = conversation(
        entry_points=[CallbackQueryHandler(start_approve, pattern=pattern(NS_ADM_PAY, "ok"))],
        states={
            CONFIRM_APPROVE: [
                CallbackQueryHandler(confirm_approve, pattern=pattern(NS_FLOW, "confirm")),
                CallbackQueryHandler(
                    ask_credited_amount, pattern=pattern(NS_ADM_PAY, "amount")
                ),
            ],
            ASK_CREDITED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_credited_amount)
            ],
        },
        fallbacks=_fallbacks(),
        name="admin_payment_approve",
        per_chat=True,
        per_user=True,
    )

    reject = conversation(
        entry_points=[CallbackQueryHandler(start_reject, pattern=pattern(NS_ADM_PAY, "no"))],
        states={
            ASK_REJECT_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reject_reason)
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_payment_reject",
        per_chat=True,
        per_user=True,
    )

    search = conversation(
        entry_points=[CallbackQueryHandler(start_search, pattern=pattern(NS_ADM_PAY, "find"))],
        states={
            ASK_SEARCH_TERM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_search_term)
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_payment_search",
        per_chat=True,
        per_user=True,
    )
    return [approve, reject, search]


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم المدفوعات خارج المحادثات."""
    return [
        CallbackQueryHandler(payments_list_screen, pattern=pattern(NS_ADM_PAY, "list")),
        CallbackQueryHandler(payment_card_screen, pattern=pattern(NS_ADM_PAY, "view")),
        CallbackQueryHandler(payment_proof_screen, pattern=pattern(NS_ADM_PAY, "proof")),
    ]
