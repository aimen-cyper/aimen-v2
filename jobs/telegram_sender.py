"""
جسر الإرسال بين طابور الإشعارات وتيليجرام.

خدمة الإشعارات لا تعرف تيليجرام إطلاقاً — تطلب فقط دالة إرسال بالشكل:
    ``async sender(telegram_id, title, message) -> message_id | None``

هذا الملف يوفّر تلك الدالة ويُترجم أخطاء تيليجرام إلى استثناءات الطابور
حتى يقرر الطابور بنفسه: يُعيد المحاولة (مؤقت) أم يتوقف (محظور/نهائي).
"""

from __future__ import annotations

import html
import re

from core.exceptions import (
    NotificationBlockedError,
    NotificationPermanentError,
    NotificationTemporaryError,
)
from telegram import Bot, LinkPreviewOptions
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TimedOut

#: أقصى طول نص رسالة في تيليجرام (نقتطع قبله بهامش أمان)
MAX_MESSAGE_LEN = 3900

#: حد تيليجرام الفعلي للرسالة؛ إن تجاوزته الصياغة المزخرفة نرجع للنص البسيط المقتطع
TELEGRAM_HARD_LIMIT = 4096

#: خط الفصل بين العنوان والمحتوى
DIVIDER = "━━━━━━━━━━━━━━━━━━━━"

#: سطر «🛒 الخدمة: قيمة»: رمز تعبيري في أوله ثم عنوان قصير ثم قيمة قصيرة ⇒ القيمة تُبرَز بالخط العريض.
#: النص الحر الطويل (رد دعم، سبب مفصّل) لا يطابق النمط عمداً فيبقى كما هو.
_FIELD_LINE = re.compile(r"^(?P<lead>[^\w\s<&#]{1,4}\s)(?P<label>[^:\n<]{1,30}):\s(?P<value>[^\n]{1,80})$")

#: عناوين قيمها معرّفات تُنسخ بلمسة (خط ثابت)
_COPYABLE_LABELS = frozenset({"Telegram ID", "رقم الحساب"})


class TelegramNotificationSender:
    """مُرسل إشعارات عبر تيليجرام مع تصنيف دقيق للأخطاء."""

    #: يقبل `order_id` اختيارياً لإرفاق زر «📦 عرض الطلب» بإشعارات الطلبات
    supports_order_button = True

    def __init__(self, bot: Bot) -> None:
        """تهيئة المرسل ببوت تيليجرام الجاهز."""
        self.bot = bot

    async def __call__(
        self, telegram_id: int, title: str, message: str, *, order_id: int | None = None
    ) -> int | None:
        """
        إرسال إشعار واحد.

        المخرجات: رقم الرسالة في تيليجرام عند النجاح.

        الاستثناءات:
            NotificationBlockedError   : المستخدم حظر البوت (لا تُعاد المحاولة).
            NotificationTemporaryError : شبكة/مهلة/حد معدل (تُعاد المحاولة).
            NotificationPermanentError : رسالة غير صالحة أو محادثة غير موجودة.
        """
        text = self._format(title, message)
        markup = None
        if order_id is not None:
            from keyboards.user_kb import order_view_kb      # استيراد متأخر: طبقة العرض لا تُحمَّل مع الخدمات

            markup = order_view_kb(order_id)
        try:
            sent = await self.bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        except Forbidden as exc:
            raise NotificationBlockedError(f"المستخدم {telegram_id} حظر البوت: {exc}") from exc
        except RetryAfter as exc:
            raise NotificationTemporaryError(
                f"تجاوز حد الإرسال، إعادة المحاولة بعد {exc.retry_after}ث"
            ) from exc
        except BadRequest as exc:            # يسبق NetworkError: BadRequest فرع منه في PTB فلا يصل إليه بعده
            text_error = str(exc).lower()
            if "chat not found" in text_error or "user is deactivated" in text_error:
                raise NotificationBlockedError(f"محادثة غير متاحة: {exc}") from exc
            raise NotificationPermanentError(f"رسالة مرفوضة من تيليجرام: {exc}") from exc
        except (TimedOut, NetworkError) as exc:
            raise NotificationTemporaryError(f"خطأ شبكة أثناء الإرسال: {exc}") from exc
        return sent.message_id

    @staticmethod
    def _format(title: str, message: str) -> str:
        """
        تنسيق الإشعار: عنوان عريض ← خط فصل ← المحتوى بقيم بارزة، مع تهريب HTML كاملاً.

        • كل نص يمرّ عبر `html.escape` أولاً ثم نضيف وسومنا نحن فقط (لا حقن ممكن من نص المستخدم).
        • الرسالة الأطول من الحد تُقتطع بالأسلوب البسيط القديم (لا نخاطر بقطع وسم في المنتصف).
        """
        safe_title = html.escape(title or "")
        safe_message = html.escape(message or "")
        plain = f"<b>{safe_title}</b>\n\n{safe_message}" if safe_title else safe_message
        if len(plain) > MAX_MESSAGE_LEN:
            return plain[: MAX_MESSAGE_LEN - 1] + "…"

        body = "\n".join(TelegramNotificationSender._decorate_line(line) for line in safe_message.split("\n"))
        pretty = f"<b>{safe_title}</b>\n{DIVIDER}\n{body}" if safe_title else body
        return pretty if len(pretty) <= TELEGRAM_HARD_LIMIT else plain

    @staticmethod
    def _decorate_line(line: str) -> str:
        """إبراز قيمة سطر «🛒 الخدمة: قيمة» (عريض، أو خط ثابت للمعرّفات القابلة للنسخ)؛ غيره يبقى كما هو."""
        match = _FIELD_LINE.match(line)
        if match is None:
            return line
        label = match.group("label").strip()
        tag = "code" if label in _COPYABLE_LABELS else "b"
        return f"{match.group('lead')}{match.group('label')}: <{tag}>{match.group('value')}</{tag}>"


class TelegramMessageEditor:
    """
    مُحرِّر رسائل حالة الطلب (يطبّق `services.order_message_service.MessageEditor`).

    «message is not modified» نجاح (الرسالة تعرض الحالة أصلاً). رسالة محذوفة/غير قابلة للتعديل/محادثة غائبة ⇒
    فشل دائم لهذا المرجع فقط. الشبكة/المهلة/حد المعدل ⇒ مؤقت يُعاد لاحقاً. لا شيء من هذا يمس حالة الطلب.
    """

    def __init__(self, bot: Bot) -> None:
        """تهيئة المُحرِّر ببوت تيليجرام الجاهز."""
        self.bot = bot

    async def edit_card(self, chat_id: str, message_id: int, html: str, order_id: int) -> None:
        """تعديل بطاقة حالة المستخدم مع زر «📦 عرض الطلب»."""
        from keyboards.user_kb import order_view_kb          # استيراد متأخر: طبقة العرض لا تُحمَّل مع الخدمات

        await self._edit(chat_id, message_id, html[:TELEGRAM_HARD_LIMIT], order_view_kb(order_id))

    async def edit_post(self, chat_id: str, message_id: int, title: str, message: str) -> None:
        """تعديل منشور قناة التوثيق بنفس تنسيق المنشور الأول."""
        await self._edit(chat_id, message_id, TelegramNotificationSender._format(title, message), None)

    async def _edit(self, chat_id: str, message_id: int, text: str, markup) -> None:
        """تعديل رسالة مع تصنيف أخطاء تيليجرام."""
        target: int | str = int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id
        try:
            await self.bot.edit_message_text(
                chat_id=target, message_id=message_id, text=text, parse_mode=ParseMode.HTML,
                reply_markup=markup, link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        except Forbidden as exc:
            raise NotificationBlockedError(f"لا يمكن تعديل الرسالة (محظور/مطرود): {exc}") from exc
        except RetryAfter as exc:
            raise NotificationTemporaryError(f"تجاوز حد التعديل، بعد {exc.retry_after}ث") from exc
        except BadRequest as exc:            # يسبق NetworkError: BadRequest فرع منه في PTB
            if "message is not modified" in str(exc).lower():
                return
            raise NotificationPermanentError(f"تعذّر تعديل الرسالة: {exc}") from exc
        except (TimedOut, NetworkError) as exc:
            raise NotificationTemporaryError(f"خطأ شبكة أثناء التعديل: {exc}") from exc


class TelegramBroadcastSender:
    """
    مُرسل الرسائل الجماعية (نص أو صورة بتعليق) بنفس تصنيف أخطاء الإشعارات.

    لماذا مُرسل مستقل عن `TelegramNotificationSender`؟
        إشعار النظام له عنوان ونص ويُنسَّق بـHTML، أما الإذاعة فنص يكتبه الأدمن
        بحروفه وقد يرافقه ملف. خلطهما في دالة واحدة كان سيجبرنا على معاملات
        اختيارية تُربك الطرفين. التصنيف الدقيق للأخطاء مشترك عبر `_classify`.
    """

    def __init__(self, bot: Bot) -> None:
        """تهيئة المرسل ببوت تيليجرام الجاهز."""
        self.bot = bot

    async def __call__(
        self,
        telegram_id: int,
        text: str,
        media_file_id: str | None = None,
        media_type: str | None = None,
    ) -> int | None:
        """
        إرسال رسالة إذاعة واحدة.

        المخرجات: رقم الرسالة في تيليجرام عند النجاح.

        الاستثناءات: نفس استثناءات الإشعارات (محظور / مؤقت / نهائي) ليتعامل
        معها طابور الإذاعة بنفس المنطق المختبر.
        """
        body = html.escape(text or "")[:MAX_MESSAGE_LEN]
        try:
            if media_file_id and media_type == "photo":
                sent = await self.bot.send_photo(
                    chat_id=telegram_id,
                    photo=media_file_id,
                    caption=body[:1024] or None,
                    parse_mode=ParseMode.HTML,
                )
            elif media_file_id and media_type == "document":
                sent = await self.bot.send_document(
                    chat_id=telegram_id,
                    document=media_file_id,
                    caption=body[:1024] or None,
                    parse_mode=ParseMode.HTML,
                )
            else:
                sent = await self.bot.send_message(
                    chat_id=telegram_id,
                    text=body,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
        except Forbidden as exc:
            raise NotificationBlockedError(f"المستخدم {telegram_id} حظر البوت: {exc}") from exc
        except RetryAfter as exc:
            raise NotificationTemporaryError(
                f"تجاوز حد الإرسال، إعادة المحاولة بعد {exc.retry_after}ث"
            ) from exc
        except BadRequest as exc:            # يسبق NetworkError: BadRequest فرع منه في PTB فلا يصل إليه بعده
            text_error = str(exc).lower()
            if "chat not found" in text_error or "user is deactivated" in text_error:
                raise NotificationBlockedError(f"محادثة غير متاحة: {exc}") from exc
            raise NotificationPermanentError(f"رسالة مرفوضة من تيليجرام: {exc}") from exc
        except (TimedOut, NetworkError) as exc:
            raise NotificationTemporaryError(f"خطأ شبكة أثناء الإرسال: {exc}") from exc
        return sent.message_id
