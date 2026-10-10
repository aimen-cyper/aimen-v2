"""
قسم «🏦 طرق الشحن» في لوحة التحكم (المرحلة 7).

لماذا ملف مستقل عن `handlers/admin/payments.py`؟
    لأن القسمين يعالجان شيئين مختلفين تماماً: `payments.py` يراجع **حوالات
    العملاء** (اعتماد/رفض/بحث)، وهذا الملف يُدير **قنوات الاستلام نفسها**
    (أين يحوّل العميل، بأي حدود، وبأي رسوم). فصلهما يبقي كل ملف قابلاً
    للقراءة، ويطابق القاعدة المتبعة في المشروع: وحدة لكل قسم من اللوحة.

ما يُنفَّذ هنا:
    • قائمة طرق الشحن وبطاقة كل طريقة بأرقام استخدامها الحقيقية.
    • إضافة طريقة جديدة: الاسم ← التعليمات ← بيانات الحساب ← النوع ← تأكيد.
    • تعديل أي حقل لاحقاً: الاسم، التعليمات، بيانات الحساب، الحدّان، الرسوم.
    • تفعيل/إيقاف، جعل الإثبات إجبارياً أو اختيارياً، وترتيب العرض للمستخدم.
    • تقرير استخدام الطرق (معتمد/معلّق/المضاف فعلاً/الرسوم المحصّلة).

قواعد ملزمة مطبّقة في هذا الملف:
    • كل إجراء يفحص صلاحيته على الـcallback نفسه (`payments.methods`)،
      ولا يكفي إخفاء الزر في اللوحة.
    • **لا حذف لطريقة شحن** — الإيقاف فقط، حفاظاً على ارتباط الطلبات التاريخية.
    • كل تعديل يمر عبر `PaymentService` ليُسجَّل في سجل التدقيق بقيمه قبل/بعد.
    • الرسوم والحدود تُقرأ وتُكتب بأعداد صحيحة فقط (لا float).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from core.exceptions import InvalidAmountError, ValidationError
from core.money import FEE_SCALE, MAX_FEE_PERCENT_BP
from core.permissions import Permission
from database.models import PaymentMethod
from handlers.common.conversation import conversation
from handlers.admin.common import (
    ADMIN_FLOW_KEY,
    admin_required,
    args,
    cancel_admin_flow,
    clear_flow,
    flow,
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
    method_card_kb,
    method_type_kb,
    methods_report_kb,
    payment_methods_kb,
)
from keyboards.callback_data import NS_ADM_PMT, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from utils.formatters import money_text, safe
from utils.logging_setup import get_logger
from utils.validators import clean_text, normalize_digits, parse_amount_units

logger = get_logger(__name__)

#: حالات محادثة «إضافة طريقة شحن»
ASK_NAME, ASK_INSTRUCTIONS, ASK_ACCOUNT, ASK_TYPE, CONFIRM_NEW = range(5)

#: حالة محادثة «تعديل حقل في طريقة شحن»
ASK_FIELD_VALUE = 10

#: خريطة أزرار التعديل: رمز الزر ⇐ (حقل قاعدة البيانات، اسم الحقل للعرض، نوع الإدخال)
EDIT_FIELDS: dict[str, tuple[str, str, str]] = {
    "name": ("name_ar", "الاسم", "text"),
    "inst": ("instructions_ar", "التعليمات", "long_text"),
    "acct": ("account_details", "بيانات الحساب", "long_text"),
    "min": ("min_amount_units", "الحد الأدنى", "money"),
    "max": ("max_amount_units", "الحد الأقصى", "money"),
    "feep": ("fee_percent_bp", "الرسوم النسبية", "percent"),
    "feef": ("fee_fixed_units", "الرسوم الثابتة", "money"),
}


# ======================================================================== #
#                              أدوات داخلية                                #
# ======================================================================== #


async def _load_method(context: ContextTypes.DEFAULT_TYPE, method_id: int) -> PaymentMethod:
    """
    تحميل طريقة شحن (ولو كانت متوقفة) أو رفع خطأ عربي واضح.

    الاستثناءات: ValidationError إذا كان الزر يحمل معرفاً لم يعد موجوداً.
    """
    services = services_of(context)
    method = await services.payments.get_method(method_id, require_active=False)
    if method is None:  # pragma: no cover - الخدمة ترفع الاستثناء أصلاً
        raise ValidationError(f"طريقة شحن غير موجودة: {method_id}", user_message=t.METHOD_NOT_FOUND)
    return method


def _percent_text(fee_percent_bp: int) -> str:
    """عرض نسبة الرسوم المخزّنة بنقاط الأساس كنسبة مئوية مقروءة (250 ⇐ «2.5%»)."""
    if not fee_percent_bp:
        return "0%"
    value = Decimal(int(fee_percent_bp)) / Decimal(100)
    return f"{value.normalize():f}%"


def _parse_percent_to_bp(raw: str) -> int:
    """
    تحويل نسبة مكتوبة («2.5» أو «٢٫٥») إلى نقاط أساس صحيحة (250).

    الاستثناءات:
        InvalidAmountError : نص غير رقمي أو نسبة خارج المدى 0..100.
    """
    cleaned = normalize_digits(raw or "").replace("٫", ".").replace("%", "").strip()
    try:
        value = Decimal(cleaned)
    except (InvalidOperation, ValueError) as exc:
        raise InvalidAmountError(
            f"نسبة غير صالحة: {raw!r}", user_message="❌ أرسل النسبة كرقم (مثال: 2.5)."
        ) from exc
    basis_points = int(value * FEE_SCALE / 100)
    if not 0 <= basis_points <= MAX_FEE_PERCENT_BP:
        raise InvalidAmountError(
            f"نسبة خارج المدى: {value}", user_message="❌ النسبة يجب أن تكون بين 0 و100."
        )
    return basis_points


def _parse_money_or_zero(raw: str) -> int:
    """
    قراءة مبلغ من الأدمن مع السماح بالصفر (الصفر = تعطيل الحد أو الرسوم).

    الاستثناءات: InvalidAmountError عند إدخال نص غير رقمي أو مبلغ سالب.
    """
    cleaned = normalize_digits(raw or "").replace(",", "").replace("٫", ".").strip()
    if cleaned in {"0", "0.0", "0.00", ""}:
        return 0
    return parse_amount_units(cleaned)


async def _method_card_text(context: ContextTypes.DEFAULT_TYPE, method: PaymentMethod) -> str:
    """
    بناء نص بطاقة طريقة الشحن: الإعدادات كاملة + أرقام استخدامها الحقيقية.

    الأرقام تأتي من تقرير قاعدة البيانات لا من تقدير، وإن لم تُستخدم الطريقة
    بعد تظهر أصفاراً صريحة.
    """
    services = services_of(context)
    admin = require_user(context)
    symbol = await symbol_of(context)

    rows = await services.payments.methods_report(admin)
    stats = next((row for row in rows if row["method_id"] == method.id), None)

    return t.METHOD_CARD.format(
        name=safe(method.name_ar, limit=64),
        state=t.METHOD_STATE_ON if method.is_active else t.METHOD_STATE_OFF,
        code=safe(method.code, limit=32),
        type=t.METHOD_TYPE_LABELS.get(method.type, method.type),
        limits=await services.payments.limits_text(method),
        fee=await services.payments.fee_text(method),
        proof=t.METHOD_PROOF_REQUIRED if method.requires_proof else t.METHOD_PROOF_OPTIONAL,
        sort_order=method.sort_order,
        instructions=safe(method.instructions_ar, limit=600) or t.METHOD_NO_INSTRUCTIONS,
        account=safe(method.account_details, limit=300) or t.METHOD_NO_ACCOUNT,
        approved=stats["approved_count"] if stats else 0,
        pending=stats["pending_count"] if stats else 0,
        total=money_text(stats["total_units"] if stats else 0, symbol),
    )


async def _render_method(
    update: Update, context: ContextTypes.DEFAULT_TYPE, method_id: int, *, as_new: bool = False
) -> None:
    """عرض بطاقة طريقة الشحن بعد أي إجراء عليها (تحديث الرسالة أو إرسال جديدة)."""
    method = await _load_method(context, method_id)
    perms = await permissions_of(context)
    text = await _method_card_text(context, method)
    markup = method_card_kb(method, perms)
    if as_new:
        await send(update, context, text, markup)
    else:
        await render(update, context, text, markup)


# ======================================================================== #
#                             شاشات القراءة                                #
# ======================================================================== #


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def methods_home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة طرق الشحن بترتيب ظهورها للمستخدم مع حالتها ورسومها وحدودها."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    perms = await permissions_of(context)

    methods = await services.payments.all_methods(admin)
    if not methods:
        await render(update, context, t.METHODS_EMPTY, payment_methods_kb([], perms))
        return

    lines = []
    for method in methods:
        lines.append(
            t.METHOD_LINE.format(
                state=t.METHOD_STATE_ON if method.is_active else t.METHOD_STATE_OFF,
                name=safe(method.name_ar, limit=40),
                fee=await services.payments.fee_text(method),
                limits=await services.payments.limits_text(method),
                proof=(
                    t.METHOD_PROOF_REQUIRED if method.requires_proof else t.METHOD_PROOF_OPTIONAL
                ),
            )
        )

    await render(
        update,
        context,
        t.METHODS_HOME.format(
            active=sum(1 for method in methods if method.is_active),
            total=len(methods),
            lines="\n".join(lines),
        ),
        payment_methods_kb(methods, perms),
    )


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def method_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة طريقة شحن واحدة بكل إعداداتها."""
    await answer_callback(update)
    await _render_method(update, context, args(update).int_arg(0))


@guarded
@admin_required(Permission.PAYMENTS_VIEW)
async def methods_report_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تقرير استخدام طرق الشحن: المعتمد والمعلّق وما أُضيف فعلاً والرسوم المقتطعة."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    symbol = await symbol_of(context)

    rows = await services.payments.methods_report(admin)
    if not rows:
        await render(update, context, t.METHODS_REPORT_EMPTY, methods_report_kb())
        return

    lines = "".join(
        t.METHODS_REPORT_LINE.format(
            state=t.METHOD_STATE_ON if row["is_active"] else t.METHOD_STATE_OFF,
            name=safe(row["name_ar"], limit=40),
            approved=row["approved_count"],
            pending=row["pending_count"],
            total=money_text(row["total_units"], symbol),
            fees=money_text(row["fee_units"], symbol),
        )
        for row in rows
    )
    await render(
        update,
        context,
        t.METHODS_REPORT_TITLE.format(
            lines=lines,
            total=money_text(sum(row["total_units"] for row in rows), symbol),
            fees=money_text(sum(row["fee_units"] for row in rows), symbol),
        ),
        methods_report_kb(),
    )


# ======================================================================== #
#                         إجراءات بضغطة واحدة                              #
# ======================================================================== #


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def toggle_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تفعيل أو إيقاف طريقة الشحن (بلا حذف — الطلبات القديمة تبقى مرتبطة بها)."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    method = await _load_method(context, args(update).int_arg(0))

    new_state = not bool(method.is_active)
    await services.payments.set_method_active(admin, method.id, new_state)
    message = (t.METHOD_TOGGLED_ON if new_state else t.METHOD_TOGGLED_OFF).format(
        name=safe(method.name_ar, limit=40)
    )
    logger.info(
        "%s الأدمن %s طريقة الشحن %s",
        "فعّل" if new_state else "أوقف", admin.telegram_id, method.code,
    )
    await _render_method(update, context, method.id)
    await send(update, context, message)


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def toggle_proof(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """جعل إثبات التحويل إجبارياً أو اختيارياً لهذه الطريقة."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    method = await _load_method(context, args(update).int_arg(0))

    required = not bool(method.requires_proof)
    await services.payments.update_method(admin, method.id, requires_proof=required)
    await _render_method(update, context, method.id)
    await send(
        update,
        context,
        t.METHOD_PROOF_TOGGLED.format(
            state=t.METHOD_PROOF_REQUIRED if required else t.METHOD_PROOF_OPTIONAL,
            name=safe(method.name_ar, limit=40),
        ),
    )


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def move_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تحريك الطريقة لأعلى أو لأسفل في ترتيب عرضها للمستخدم."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    data = args(update)
    up = data.action == "up"
    method = await _load_method(context, data.int_arg(0))

    moved = await services.payments.move_method(admin, method.id, up=up)
    if not moved:
        await answer_callback(update, t.METHOD_MOVE_EDGE, alert=True)
        return
    await _render_method(update, context, method.id)
    await send(update, context, t.METHOD_MOVED.format(name=safe(method.name_ar, limit=40)))


# ======================================================================== #
#                       محادثة «إضافة طريقة شحن»                           #
# ======================================================================== #


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def start_new_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء إضافة طريقة شحن: الخطوة الأولى هي الاسم كما يراه المستخدم."""
    await answer_callback(update)
    start_flow(context)
    await render(update, context, t.METHOD_NEW_INTRO, cancel_only_kb())
    return ASK_NAME


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def receive_method_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال اسم الطريقة ثم طلب تعليمات التحويل."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_NAME

    name = clean_text(message.text, field="اسم الطريقة", max_length=64)
    update_flow(context, name=name)
    await send(update, context, t.METHOD_NEW_ASK_INSTRUCTIONS, cancel_only_kb())
    return ASK_INSTRUCTIONS


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def receive_method_instructions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال تعليمات التحويل (تظهر للمستخدم كما كُتبت) ثم طلب بيانات الحساب."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_INSTRUCTIONS

    update_flow(context, instructions=message.text)
    await send(update, context, t.METHOD_NEW_ASK_ACCOUNT, cancel_only_kb())
    return ASK_ACCOUNT


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def receive_method_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال بيانات الحساب ثم سؤال الأدمن عن نوع الطريقة."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_ACCOUNT

    update_flow(context, account=message.text)
    await send(update, context, t.METHOD_NEW_ASK_TYPE, method_type_kb())
    return ASK_TYPE


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def receive_method_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال نوع الطريقة وعرض مراجعة نهائية قبل الإنشاء."""
    await answer_callback(update)
    method_type = args(update).arg(0) or "manual"
    data = update_flow(context, type=method_type)
    if not data.get("name"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    await render(
        update,
        context,
        t.METHOD_NEW_CONFIRM.format(
            name=safe(data["name"], limit=64),
            type=t.METHOD_TYPE_LABELS.get(method_type, method_type),
            instructions=safe(data.get("instructions", ""), limit=300),
            account=safe(data.get("account", ""), limit=200),
        ),
        confirm_cancel_kb(),
    )
    return CONFIRM_NEW


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def confirm_new_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إنشاء طريقة الشحن فعلياً (الخدمة تسجّل التدقيق وتشتق الكود الداخلي)."""
    await answer_callback(update)
    data = flow(context)
    if not data.get("name"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    method = await services.payments.create_method(
        admin,
        name_ar=data["name"],
        instructions_ar=data.get("instructions", ""),
        account_details=data.get("account", ""),
        type=data.get("type", "manual"),
    )
    clear_flow(context)
    logger.info("أضاف الأدمن %s طريقة شحن %s", admin.telegram_id, method.code)

    await render(
        update,
        context,
        t.METHOD_CREATED.format(name=safe(method.name_ar, limit=64), code=safe(method.code)),
    )
    await _render_method(update, context, method.id, as_new=True)
    return ConversationHandler.END


# ======================================================================== #
#                     محادثة «تعديل حقل في طريقة شحن»                      #
# ======================================================================== #


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def start_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء تعديل حقل واحد: السؤال يعرض القيمة الحالية حتى لا يعدّل الأدمن على العمياء."""
    await answer_callback(update)
    data = args(update)
    method = await _load_method(context, data.int_arg(0))
    field_code = data.arg(1)

    if field_code not in EDIT_FIELDS:
        await answer_callback(update, t.METHOD_NOT_FOUND, alert=True)
        return ConversationHandler.END

    column, label, _kind = EDIT_FIELDS[field_code]
    symbol = await symbol_of(context)
    start_flow(context, method_id=method.id, field=field_code)

    prompts = {
        "name": lambda: t.METHOD_ASK_NAME,
        "inst": lambda: t.METHOD_ASK_INSTRUCTIONS.format(
            current=safe(method.instructions_ar, limit=300) or "—"
        ),
        "acct": lambda: t.METHOD_ASK_ACCOUNT.format(
            current=safe(method.account_details, limit=200) or "—"
        ),
        "min": lambda: t.METHOD_ASK_MIN.format(
            symbol=symbol, current=money_text(method.min_amount_units, symbol)
        ),
        "max": lambda: t.METHOD_ASK_MAX.format(
            symbol=symbol,
            current=money_text(method.max_amount_units, symbol) if method.max_amount_units else "—",
        ),
        "feep": lambda: t.METHOD_ASK_FEE_PERCENT.format(current=_percent_text(method.fee_percent_bp)),
        "feef": lambda: t.METHOD_ASK_FEE_FIXED.format(
            symbol=symbol, current=money_text(method.fee_fixed_units, symbol)
        ),
    }
    logger.info(
        "بدأ الأدمن %s تعديل الحقل %s لطريقة الشحن %s",
        require_user(context).telegram_id, column, method.code,
    )
    await render(update, context, prompts[field_code](), cancel_only_kb())
    return ASK_FIELD_VALUE


@guarded
@admin_required(Permission.PAYMENTS_METHODS)
async def receive_field_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    استقبال القيمة الجديدة وتطبيقها بعد تحويلها لنوعها الصحيح.

    التحويل هنا (نسبة ⇐ نقاط أساس، مبلغ ⇐ نقاط)، والتحقق النهائي من المدى
    داخل `PaymentService` حتى لا يوجد مسار يتجاوز الحارس.
    """
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_FIELD_VALUE

    data = flow(context)
    method_id, field_code = data.get("method_id"), data.get("field")
    if not method_id or field_code not in EDIT_FIELDS:
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    column, label, kind = EDIT_FIELDS[field_code]
    raw = message.text
    if kind == "text":
        value: object = clean_text(raw, field=label, max_length=64)
    elif kind == "long_text":
        value = raw
    elif kind == "percent":
        value = _parse_percent_to_bp(raw)
    else:  # money
        units = _parse_money_or_zero(raw)
        value = (units or None) if column == "max_amount_units" else units

    services = services_of(context)
    admin = require_user(context)
    changed = await services.payments.update_method(admin, int(method_id), **{column: value})
    clear_flow(context)

    await send(
        update,
        context,
        t.METHOD_FIELD_SAVED.format(field=label) if changed else t.METHOD_FIELD_UNCHANGED,
    )
    await _render_method(update, context, int(method_id), as_new=True)
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
    """محادثتا إضافة طريقة شحن وتعديل حقولها."""
    new_method = conversation(
        entry_points=[CallbackQueryHandler(start_new_method, pattern=pattern(NS_ADM_PMT, "new"))],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_method_name)],
            ASK_INSTRUCTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_method_instructions)
            ],
            ASK_ACCOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_method_account)
            ],
            ASK_TYPE: [
                CallbackQueryHandler(receive_method_type, pattern=pattern(NS_ADM_PMT, "type"))
            ],
            CONFIRM_NEW: [
                CallbackQueryHandler(confirm_new_method, pattern=pattern(NS_FLOW, "confirm"))
            ],
        },
        fallbacks=_fallbacks(),
        name="admin_payment_method_new",
        per_chat=True,
        per_user=True,
    )

    edit_field = conversation(
        entry_points=[CallbackQueryHandler(start_edit_field, pattern=pattern(NS_ADM_PMT, "edit"))],
        states={
            ASK_FIELD_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_field_value)
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_payment_method_edit",
        per_chat=True,
        per_user=True,
    )
    return [new_method, edit_field]


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم طرق الشحن خارج المحادثات."""
    return [
        CallbackQueryHandler(methods_home_screen, pattern=pattern(NS_ADM_PMT, "home")),
        CallbackQueryHandler(method_card_screen, pattern=pattern(NS_ADM_PMT, "view")),
        CallbackQueryHandler(methods_report_screen, pattern=pattern(NS_ADM_PMT, "rep")),
        CallbackQueryHandler(toggle_method, pattern=pattern(NS_ADM_PMT, "toggle")),
        CallbackQueryHandler(toggle_proof, pattern=pattern(NS_ADM_PMT, "proof")),
        CallbackQueryHandler(move_method, pattern=pattern(NS_ADM_PMT, "up")),
        CallbackQueryHandler(move_method, pattern=pattern(NS_ADM_PMT, "down")),
    ]
