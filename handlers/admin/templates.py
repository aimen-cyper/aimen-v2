"""
قسم «✉️ قوالب الإشعارات» في لوحة التحكم (المرحلة 8).

ما يُنفَّذ هنا:
    • قائمة قوالب رسائل العملاء مجمّعة (طلبات/شحن/رصيد/دعم/حساب) مع علامة المعدَّل.
    • بطاقة القالب: النص الفعّال، المتغيرات المسموحة، وحالته (افتراضي/مخصّص/موقوف).
    • تعديل العنوان أو النص بمحادثة تعرض القيمة الحالية والمتغيرات المتاحة.
    • معاينة بقيم تجريبية عبر نفس مسار الإرسال الحقيقي (لا تُرسل لأحد).
    • إيقاف/تفعيل التخصيص، واستعادة النص الافتراضي بضغطة واحدة.

قواعد ملزمة مطبّقة هنا:
    • صلاحية `notifications.templates` تُفحص على كل callback.
    • التحقق من المتغيرات يتم في `TemplateService` قبل الحفظ، فلا يوجد
      مسار يحفظ قالباً قد يفشل عند الإرسال.
    • كل تعديل يُسجَّل في التدقيق بنصه قبل/بعد.
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

from core.permissions import Permission
from handlers.common.conversation import conversation
from handlers.admin.common import (
    ADMIN_FLOW_KEY,
    admin_required,
    args,
    cancel_admin_flow,
    clear_flow,
    flow,
    start_flow,
)
from handlers.common.fallbacks import exit_conversation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    cancel_only_kb,
    template_card_kb,
    template_preview_kb,
    templates_home_kb,
)
from keyboards.callback_data import NS_ADM_TPL, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: حالة محادثة «تعديل عنوان/نص قالب»
ASK_VALUE = 0

#: الحقول القابلة للتعديل: رمز الزر ⇐ اسم المعامل في الخدمة
EDIT_FIELDS = {"title": "title", "body": "body"}


# ======================================================================== #
#                              أدوات داخلية                                #
# ======================================================================== #


def _variables_text(variables: tuple[str, ...]) -> str:
    """عرض المتغيرات المتاحة بالشكل الذي يكتبه الأدمن حرفياً: {code} {amount}."""
    if not variables:
        return t.TEMPLATE_NO_VARIABLES
    return " ".join(f"<code>{{{name}}}</code>" for name in variables)


def _escape(value: str) -> str:
    """تهريب نص القالب قبل عرضه داخل رسالة HTML (حتى لا تُفسد الأقواس المعقوفة العرض)."""
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def _render_card(
    update: Update, context: ContextTypes.DEFAULT_TYPE, code: str, *, as_new: bool = False
) -> None:
    """عرض بطاقة القالب بنصه الفعّال وحالته (تحديث الرسالة أو إرسال جديدة)."""
    services = services_of(context)
    admin = require_user(context)
    state = await services.templates.get_state(admin, code)
    definition = state["definition"]

    if not state["is_customized"]:
        state_text = t.TEMPLATE_STATE_TEXT_DEFAULT
    elif state["is_active"]:
        state_text = t.TEMPLATE_STATE_TEXT_CUSTOM
    else:
        state_text = t.TEMPLATE_STATE_TEXT_PAUSED

    text = t.TEMPLATE_CARD.format(
        name=definition.name_ar,
        state=state_text,
        variables=_variables_text(definition.variables),
        title=_escape(state["title"]),
        body=_escape(state["body"]),
    )
    markup = template_card_kb(
        code, is_customized=state["is_customized"], is_active=state["is_active"]
    )
    if as_new:
        await send(update, context, text, markup)
    else:
        await render(update, context, text, markup)


# ======================================================================== #
#                             شاشات القراءة                                #
# ======================================================================== #


@guarded
@admin_required(Permission.NOTIFICATIONS_TEMPLATES)
async def templates_home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة القوالب مجمّعة حسب المجموعة، وعدّاد المعدَّل منها."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    items = await services.templates.overview(admin)

    lines: list[str] = []
    current_group = None
    for item in items:
        if item["group"] != current_group:
            current_group = item["group"]
            lines.append(t.TEMPLATES_GROUP_LINE.format(group=item["group_name"]))
        if not item["is_customized"]:
            state = t.TEMPLATE_STATE_DEFAULT
        elif item["is_active"]:
            state = t.TEMPLATE_STATE_CUSTOM
        else:
            state = t.TEMPLATE_STATE_OFF
        lines.append(t.TEMPLATE_LINE.format(state=state, name=item["name_ar"]))

    await render(
        update,
        context,
        t.TEMPLATES_HOME.format(
            customized=sum(1 for item in items if item["is_customized"]),
            total=len(items),
            lines="".join(lines),
        ),
        templates_home_kb(items),
    )


@guarded
@admin_required(Permission.NOTIFICATIONS_TEMPLATES)
async def template_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة قالب واحد."""
    await answer_callback(update)
    await _render_card(update, context, args(update).arg(0))


@guarded
@admin_required(Permission.NOTIFICATIONS_TEMPLATES)
async def template_preview_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معاينة القالب الفعّال بقيم تجريبية — لا تُرسل لأي مستخدم."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    code = args(update).arg(0)
    title, body = await services.templates.preview(admin, code)
    await render(
        update,
        context,
        t.TEMPLATE_PREVIEW.format(title=_escape(title), body=_escape(body)),
        template_preview_kb(code),
    )


# ======================================================================== #
#                         إجراءات بضغطة واحدة                              #
# ======================================================================== #


@guarded
@admin_required(Permission.NOTIFICATIONS_TEMPLATES)
async def toggle_template(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إيقاف أو تفعيل النص المخصّص (الإيقاف يُرجع الافتراضي دون فقد التعديل)."""
    # ملاحظة: يُجاب على الـcallback مرة واحدة فقط (برسالة النتيجة) — الرد الثاني يتجاهله تيليجرام
    services = services_of(context)
    admin = require_user(context)
    code = args(update).arg(0)

    state = await services.templates.get_state(admin, code)
    target_active = not state["is_active"]
    await services.templates.set_active(admin, code, active=target_active)
    name = state["definition"].name_ar
    await answer_callback(
        update,
        (t.TEMPLATE_ENABLED if target_active else t.TEMPLATE_DISABLED).format(name=name),
    )
    await _render_card(update, context, code)


@guarded
@admin_required(Permission.NOTIFICATIONS_TEMPLATES)
async def reset_template(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """استعادة النص الافتراضي (حذف التخصيص فقط، والنص الأصلي في الكود)."""
    # ملاحظة: يُجاب على الـcallback مرة واحدة فقط (برسالة النتيجة) — الرد الثاني يتجاهله تيليجرام
    services = services_of(context)
    admin = require_user(context)
    code = args(update).arg(0)

    name = services.templates.definition(code).name_ar
    deleted = await services.templates.reset(admin, code)
    await answer_callback(
        update,
        (t.TEMPLATE_RESET_DONE if deleted else t.TEMPLATE_RESET_NOTHING).format(name=name),
        alert=not deleted,
    )
    await _render_card(update, context, code)


# ======================================================================== #
#                     محادثة «تعديل عنوان/نص قالب»                         #
# ======================================================================== #


@guarded
@admin_required(Permission.NOTIFICATIONS_TEMPLATES)
async def start_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء التعديل: السؤال يعرض القيمة الحالية والمتغيرات المتاحة."""
    services = services_of(context)
    admin = require_user(context)
    data = args(update)
    code, field = data.arg(0), data.arg(1)

    if field not in EDIT_FIELDS:
        await answer_callback(update, t.TEMPLATE_NOT_FOUND, alert=True)
        return ConversationHandler.END
    await answer_callback(update)

    state = await services.templates.get_state(admin, code)
    definition = state["definition"]
    start_flow(context, code=code, field=field)

    prompt = t.TEMPLATE_ASK_TITLE if field == "title" else t.TEMPLATE_ASK_BODY
    await render(
        update,
        context,
        prompt.format(
            name=definition.name_ar,
            current=_escape(state[field]),
            variables=_variables_text(definition.variables),
        ),
        cancel_only_kb(),
    )
    return ASK_VALUE


@guarded
@admin_required(Permission.NOTIFICATIONS_TEMPLATES)
async def receive_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    استقبال النص الجديد وحفظه.

    إن رُفض النص (متغير غير مسموح مثلاً) تبقى المحادثة مفتوحة لإعادة المحاولة
    ولا يضيع ما كتبه الأدمن من سياق — الحارس `@guarded` يعرض سبب الرفض.
    """
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_VALUE

    data = flow(context)
    code, field = data.get("code"), data.get("field")
    if not code or field not in EDIT_FIELDS:
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    definition = services.templates.definition(str(code))

    await services.templates.set_text(admin, str(code), **{EDIT_FIELDS[field]: message.text})
    clear_flow(context)
    logger.info("حفظ الأدمن %s القالب %s (الحقل %s)", admin.telegram_id, code, field)

    await send(update, context, t.TEMPLATE_SAVED.format(name=definition.name_ar))
    await _render_card(update, context, str(code), as_new=True)
    return ConversationHandler.END


# ============================== التسجيل ================================ #


def _fallbacks() -> list:
    """المسارات الاحتياطية الموحّدة لمحادثة هذا القسم."""
    return [
        CallbackQueryHandler(cancel_admin_flow, pattern=pattern(NS_FLOW, "cancel")),
        CommandHandler("cancel", cancel_admin_flow),
        CommandHandler("start", exit_conversation(ADMIN_FLOW_KEY)),
    ]


def conversations() -> list[ConversationHandler]:
    """محادثة تعديل العنوان أو النص."""
    edit = conversation(
        entry_points=[CallbackQueryHandler(start_edit, pattern=pattern(NS_ADM_TPL, "edit"))],
        states={ASK_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_value)]},
        fallbacks=_fallbacks(),
        name="admin_template_edit",
        per_chat=True,
        per_user=True,
    )
    return [edit]


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم القوالب خارج المحادثة."""
    return [
        CallbackQueryHandler(templates_home_screen, pattern=pattern(NS_ADM_TPL, "home")),
        CallbackQueryHandler(template_card_screen, pattern=pattern(NS_ADM_TPL, "view")),
        CallbackQueryHandler(template_preview_screen, pattern=pattern(NS_ADM_TPL, "prev")),
        CallbackQueryHandler(toggle_template, pattern=pattern(NS_ADM_TPL, "toggle")),
        CallbackQueryHandler(reset_template, pattern=pattern(NS_ADM_TPL, "reset")),
    ]
