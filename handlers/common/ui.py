"""
أدوات عرض موحّدة: إرسال الشاشات وتحريرها والرد على ضغطات الأزرار.

لماذا؟
    • التنقل في البوت يكون بتحرير نفس الرسالة (`edit_message_text`) لا بإغراق
      المحادثة برسائل جديدة — هذا يحتاج تعاملاً موحّداً مع نوعي التحديث
      (ضغطة زر / رسالة نصية).
    • تيليجرام يرفض تحرير رسالة بنفس محتواها برسالة الخطأ
      «message is not modified»؛ وهي حالة طبيعية (ضغط الزر مرتين) نتعامل معها
      بوضوح بدل كتمان كل الأخطاء.
    • أعطال الاتصال (TimedOut/ConnectError/RetryAfter) خارجية: تُعاد محاولتها بحدود (`call_telegram`) ثم
      تُسجَّل كتحذير **دون أن تُسقط المعالج** — فالعملية المالية/الحالة التي سبقت العرض ثابتة في القاعدة،
      وإشعار المستخدم بها يصله من صندوق الإشعارات الدائم، فلا يبقى الطلب «معلّقاً» لأن الشاشة لم تُرسم.
"""

from __future__ import annotations

from telegram import InlineKeyboardMarkup, LinkPreviewOptions, Message, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TelegramError, TimedOut
from telegram.ext import ContextTypes

from utils.formatters import tidy_text
from utils.logging_setup import get_logger
from utils.telegram_retry import call_telegram

logger = get_logger(__name__)

#: نص خطأ تيليجرام عند تحرير رسالة بمحتوى مطابق (ليس خطأً حقيقياً)
NOT_MODIFIED = "message is not modified"


async def answer_callback(update: Update, text: str = "", *, alert: bool = False) -> None:
    """
    الرد على ضغطة الزر لإزالة مؤشر الانتظار عند المستخدم.

    يُستدعى في بداية كل معالج أزرار؛ تجاهله يُبقي الزر «يدور» عند المستخدم.
    """
    query = update.callback_query
    if query is None:
        return
    try:
        await call_telegram(
            lambda: query.answer(text=text or None, show_alert=alert), what="الرد على ضغطة زر", idempotent=True
        )
    except BadRequest as exc:
        # الاستعلام القديم (أكثر من 48 ساعة) لا يمكن الرد عليه — نسجّل ونكمل
        logger.debug("تعذر الرد على ضغطة زر قديمة: %s", exc)
    except (TimedOut, NetworkError, RetryAfter) as exc:
        # الرد على الزر تجميلي (يُزيل مؤشر الانتظار) — عطل الشبكة لا يمنع تنفيذ الوظيفة نفسها
        logger.warning("تعذر الرد على ضغطة زر بسبب اتصال تيليجرام: %s", exc)


async def render(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
    *,
    disable_preview: bool = True,
) -> None:
    """
    عرض شاشة: تحرير الرسالة الحالية إن جاء التحديث من زر، وإلا إرسال رسالة جديدة.

    المدخلات:
        text   : نص الشاشة (بتنسيق HTML).
        markup : لوحة الأزرار المرافقة.
    """
    text = tidy_text(text)
    query = update.callback_query
    if query is not None and query.message is not None:
        try:
            await call_telegram(
                lambda: query.edit_message_text(
                    text=text,
                    reply_markup=markup,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=LinkPreviewOptions(is_disabled=disable_preview),
                ),
                what="تحرير رسالة",
                idempotent=True,            # التحرير بالنص نفسه لا أثر جانبياً له
            )
            await _release_order_refs(context, query.message)
            return
        except BadRequest as exc:
            if NOT_MODIFIED in str(exc).lower():
                return                      # المستخدم ضغط نفس الزر — لا جديد يُعرض
            logger.warning("تعذر تحرير الرسالة، سيُرسل بديل: %s", exc)
        except (TimedOut, NetworkError, RetryAfter) as exc:
            # الشبكة معطّلة: الإرسال البديل سيفشل غالباً وقد يُكرّر الشاشة إن كان التحرير نجح فعلاً
            logger.warning("تعذر عرض الشاشة بسبب اتصال تيليجرام (الحالة محفوظة): %s", exc)
            return

    await send(update, context, text, markup, disable_preview=disable_preview)


async def _release_order_refs(context: ContextTypes.DEFAULT_TYPE, message: Message) -> None:
    """
    رسالة المستخدم صارت تعرض شاشة أخرى بعد هذا التحرير ⇒ نوقف تحديثها التلقائي (حالة الطلب)
    حتى لا تكتب المهمة الدورية فوق ما يقرؤه الآن. لا ترفع أبداً.
    """
    services = context.application.bot_data.get("services") if context.application else None
    order_messages = getattr(services, "order_messages", None)
    if order_messages is None:
        return
    await order_messages.release_message(message.chat_id, message.message_id)


async def send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
    *,
    disable_preview: bool = True,
) -> Message | None:
    """إرسال رسالة جديدة إلى محادثة المستخدم (تُستخدم للنتائج والتنبيهات)؛ تُرجع الرسالة المُرسلة إن نجح."""
    text = tidy_text(text)
    chat = update.effective_chat
    if chat is None:
        logger.warning("تحديث بلا محادثة — تعذر الإرسال")
        return None
    try:
        return await call_telegram(
            lambda: context.bot.send_message(
                chat_id=chat.id,
                text=text,
                reply_markup=markup,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=disable_preview),
            ),
            what="إرسال رسالة",
            idempotent=False,               # لا تُعاد إلا حين يستحيل التسليم (لا نكرّر رسالة وصلت)
        )
    except Forbidden:
        # المستخدم حظر البوت — تُعلَّم الحالة في قاعدة البيانات عبر مهمة الإشعارات
        logger.info("المستخدم %s حظر البوت", chat.id)
        return None
    except BadRequest:
        raise                               # رفض من تيليجرام لطلبنا (HTML فاسد…) = خطأ كود يجب أن يظهر
    except (TimedOut, NetworkError, RetryAfter) as exc:
        logger.warning("تعذر إرسال رسالة إلى %s بسبب اتصال تيليجرام (الحالة محفوظة): %s", chat.id, exc)
        return None


async def delete_quietly(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int | None) -> bool:
    """
    حذف رسالة بلا إزعاج إن تعذّر (قديمة >48س، محذوفة أصلاً، أو بلا صلاحية).

    هو إجراء تجميلي لتقليل الفوضى في المحادثة؛ فشله لا يؤثر على أي وظيفة، ويُسجَّل على مستوى debug.
    """
    if not message_id:
        return False
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramError as exc:
        logger.debug("تعذّر حذف الرسالة %s: %s", message_id, exc)
        return False
    return True
