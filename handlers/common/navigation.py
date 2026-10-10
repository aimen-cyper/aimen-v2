"""
شاشة البداية والقائمة الرئيسية والأوامر العامة.

يشمل:
    /start  : تسجيل/ترحيب ثم القائمة الرئيسية.
    /help   : شرح مختصر لطريقة الاستخدام.
    /id     : عرض معرف تيليجرام (يطلبه الدعم أحياناً).
    nav:home: العودة للقائمة الرئيسية من أي شاشة.
    nav:page: زر عدّاد الصفحات — يعرض موضع المستخدم بدل أن يكون زراً صامتاً.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, delete_quietly, render, send
from keyboards.callback_data import unpack
from keyboards.user_kb import help_kb, main_menu_kb
from middlewares.context import require_user, services_of
from texts import ar, help_ar
from utils.formatters import money_text, safe, time_greeting

#: مفتاح user_data لرقم رسالة القائمة الرئيسية الأخيرة (في الذاكرة؛ يضيع عند إعادة التشغيل وهذا مقبول)
MENU_MESSAGE_KEY = "menu_msg_id"


async def is_admin_user(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    هل يملك صاحب هذا التحديث حق دخول لوحة التحكم؟

    تُستدعى قبل بناء القائمة الرئيسية حتى يظهر زر «🛠 لوحة التحكم» لمن يستحقه
    فقط، وتختفي فوراً عمن سُحبت صلاحيته (تُقرأ من قاعدة البيانات كل مرة).
    """
    services = services_of(context)
    return await services.auth.is_admin(require_user(context))


async def main_menu_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    بناء نص القائمة الرئيسية بأرقام حقيقية (رصيد، طلبات نشطة، تذاكر مفتوحة).

    المخرجات: نص HTML جاهز للعرض.
    """
    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    summary = await services.users.summary(user)
    return ar.MAIN_MENU_BODY.format(
        balance=money_text(user.balance_units, symbol),
        active_orders=summary.active_orders,
        open_tickets=summary.tickets_open,
    )


@guarded
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الأمر /start: رسالة ترحيب (مختلفة للجديد) ثم القائمة الرئيسية."""
    services = services_of(context)
    user = require_user(context)
    is_new = bool(context.user_data and context.user_data.get("is_new_user"))

    if is_new:
        welcome = await services.settings.get_str(
            "welcome_message", "أهلاً بك في بوت خدمات التواصل الاجتماعي."
        )
        greeting = ar.START_NEW.format(
            greeting=time_greeting(), name=safe(user.first_name or "", limit=30), welcome=safe(welcome)
        )
    else:
        greeting = ar.START_BACK.format(greeting=time_greeting(), name=safe(user.first_name or "", limit=30))

    # رسالة واحدة (ترحيب + قائمة) بدل رسالتين، وتنظيف المحادثة: حذف أمر /start نفسه والقائمة السابقة
    chat_id = update.effective_chat.id if update.effective_chat else None
    previous_menu = context.user_data.get(MENU_MESSAGE_KEY) if context.user_data is not None else None
    sent = await send(
        update,
        context,
        greeting + await main_menu_text(context),
        main_menu_kb(is_admin=await is_admin_user(context)),
    )
    if chat_id is not None:
        if update.message is not None:
            await delete_quietly(context, chat_id, update.message.message_id)
        if previous_menu and (sent is None or previous_menu != sent.message_id):
            await delete_quietly(context, chat_id, previous_menu)
    if sent is not None and context.user_data is not None:
        context.user_data[MENU_MESSAGE_KEY] = sent.message_id


@guarded
async def home_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """زر «القائمة الرئيسية» من أي شاشة."""
    await answer_callback(update)
    await render(
        update,
        context,
        await main_menu_text(context),
        main_menu_kb(is_admin=await is_admin_user(context)),
    )
    _remember_menu_message(update, context)


def _remember_menu_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """حفظ رقم رسالة القائمة الحالية ليُحذف عند /start التالي بدل تراكم القوائم في المحادثة."""
    query = update.callback_query
    if query is not None and query.message is not None and context.user_data is not None:
        context.user_data[MENU_MESSAGE_KEY] = query.message.message_id


@guarded
async def subscription_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    زر «✅ تحقق من الاشتراك»: يصل هنا فقط بعد أن أكّدت الطبقة الوسيطة الاشتراك الفعلي.

    (غير المشترك لا يصل لهذا المعالج؛ تُعيد الطبقة الوسيطة عرض شاشة البوابة وتوقف التحديث.)
    """
    await answer_callback(update, ar.SUB_CHECK_OK)
    await render(
        update,
        context,
        await main_menu_text(context),
        main_menu_kb(is_admin=await is_admin_user(context)),
    )
    _remember_menu_message(update, context)


@guarded
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الأمر /help: يفتح «📖 التعليمات» (فهرس المواضيع) كرسالة جديدة."""
    await send(update, context, help_ar.HELP_INDEX, help_kb(None))


@guarded
async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الأمر /id: عرض معرف المستخدم في تيليجرام."""
    user = require_user(context)
    await send(update, context, ar.ID_TEXT.format(telegram_id=user.telegram_id))


@guarded
async def page_indicator_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    زر عدّاد الصفحات: يعرض موضع المستخدم الحالي كتنبيه منبثق.

    سبب وجوده: القاعدة تمنع الأزرار بلا وظيفة — فحتى زر العرض يفعل شيئاً مفيداً.
    """
    data = unpack(update.callback_query.data if update.callback_query else None)
    await answer_callback(
        update, ar.PAGE_INFO.format(page=data.int_arg(0, 1), pages=data.int_arg(1, 1))
    )
