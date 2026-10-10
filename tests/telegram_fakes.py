"""
بدائل اختبارية لواجهة تيليجرام (بلا أي اتصال بالشبكة).

الفكرة: نستخدم كائنات `telegram.Update` **حقيقية** (مبنية عبر `de_json`) حتى
نختبر نفس المسارات التي تعمل في الإنتاج، لكن مع بوت مزيّف يسجّل ما كان
سيُرسَل بدل إرساله. هكذا يفحص الاختبار النص النهائي والأزرار الفعلية.
"""

from __future__ import annotations

from types import SimpleNamespace

import itertools
import time
from dataclasses import dataclass, field
from typing import Any

from telegram import InlineKeyboardMarkup, Update

#: عدّاد معرفات التحديثات حتى لا يتكرر رقم داخل اختبار واحد
_update_ids = itertools.count(1000)

#: معرف البوت المزيّف
BOT_ID = 999_000_111


@dataclass
class SentMessage:
    """رسالة مسجّلة (أُرسلت أو عُدِّلت) مع نصها وأزرارها."""

    kind: str                       # "send" أو "edit"
    chat_id: int | None
    text: str
    markup: InlineKeyboardMarkup | None
    kwargs: dict[str, Any] = field(default_factory=dict)

    @property
    def buttons(self) -> list[str]:
        """كل `callback_data` الموجودة في اللوحة المرافقة."""
        if self.markup is None:
            return []
        return [
            button.callback_data
            for row in self.markup.inline_keyboard
            for button in row
            if button.callback_data
        ]

    @property
    def labels(self) -> list[str]:
        """نصوص الأزرار كما يراها المستخدم."""
        if self.markup is None:
            return []
        return [button.text for row in self.markup.inline_keyboard for button in row]


class FakeMessage:
    """ردّ مبسّط يحاكي `Message` المُعاد من تيليجرام بعد الإرسال."""

    def __init__(self, message_id: int, chat_id: int, text: str) -> None:
        """تهيئة الرسالة المزيّفة بالحد الأدنى من الحقول المستخدمة."""
        self.message_id = message_id
        self.chat_id = chat_id
        self.text = text


class FakeBot:
    """
    بوت مزيّف يسجّل كل نداء بدل الاتصال بتيليجرام.

    يدعم فقط ما تستخدمه الواجهة فعلاً: الإرسال، التحرير، الرد على الأزرار،
    وإرسال الصور — وأي نداء آخر يرفع `AttributeError` واضحاً بدل الصمت.
    """

    def __init__(self) -> None:
        """تهيئة البوت المزيّف بسجلات فارغة."""
        self.sent: list[SentMessage] = []
        self.answers: list[dict[str, Any]] = []
        self.id = BOT_ID
        self.username = "fake_bot"
        self._message_ids = itertools.count(1)
        self.deleted: list[tuple[int, int]] = []
        #: عضويات القنوات: (chat_id, user_id) ⇒ حالة العضوية؛ غير الموجود ⇒ «User not found» (غير مشترك)
        self.memberships: dict[tuple[Any, int], str] = {}
        #: أخطاء تُرفع عند `get_chat_member` لقناة بعينها (استثناء جاهز)
        self.member_errors: dict[Any, BaseException] = {}
        self.member_calls: list[tuple[Any, int]] = []
        #: نتائج `get_chat` لوجهات بعينها (كائن أو استثناء)
        self.chats: dict[Any, Any] = {}
        #: أعطال مبرمجة لكل عملية ("send" | "edit" | "answer" | "photo" | "document"): (استثناء، هل وصلت فعلاً؟)
        #: `delivered=True` يحاكي مهلة قراءة بعد أن نفّذ تيليجرام الطلب (الحالة الغامضة)
        self.faults: dict[str, list[tuple[BaseException, bool]]] = {}
        #: عدد محاولات كل عملية (ناجحة أو فاشلة)
        self.attempts: dict[str, int] = {}

    def fail(self, operation: str, error: BaseException, *, times: int = 1, delivered: bool = False) -> None:
        """برمجة فشل `times` محاولة قادمة للعملية (يُرفع `error` ويُسجَّل الأثر إن كان `delivered`)."""
        self.faults.setdefault(operation, []).extend([(error, delivered)] * times)

    def _fault(self, operation: str) -> tuple[BaseException, bool] | None:
        """عدّ المحاولة وإرجاع العطل المبرمج التالي (إن وُجد)."""
        self.attempts[operation] = self.attempts.get(operation, 0) + 1
        queue = self.faults.get(operation)
        return queue.pop(0) if queue else None

    # ------------------------------ الإرسال ------------------------------ #

    async def send_message(
        self, chat_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None, **kwargs: Any
    ) -> FakeMessage:
        """تسجيل رسالة جديدة وإرجاع كائن يشبه رسالة تيليجرام."""
        fault = self._fault("send")
        if fault is not None:
            if fault[1]:
                self.sent.append(SentMessage("send", chat_id, text, reply_markup, kwargs))
            raise fault[0]
        self.sent.append(SentMessage("send", chat_id, text, reply_markup, kwargs))
        return FakeMessage(next(self._message_ids), chat_id, text)

    async def edit_message_text(
        self,
        text: str,
        chat_id: int | None = None,
        message_id: int | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
        **kwargs: Any,
    ) -> FakeMessage:
        """تسجيل تحرير رسالة قائمة (هذا هو المسار الطبيعي للتنقل بين الشاشات)."""
        fault = self._fault("edit")
        if fault is not None:
            if fault[1]:
                self.sent.append(SentMessage("edit", chat_id, text, reply_markup, kwargs))
            raise fault[0]
        self.sent.append(SentMessage("edit", chat_id, text, reply_markup, kwargs))
        return FakeMessage(message_id or 0, chat_id or 0, text)

    async def send_photo(self, chat_id: int, photo: Any, caption: str = "", **kwargs: Any) -> FakeMessage:
        """تسجيل إرسال صورة (يُستخدم في إشعارات الإثباتات لاحقاً)."""
        self.sent.append(SentMessage("photo", chat_id, caption, kwargs.get("reply_markup"), kwargs))
        return FakeMessage(next(self._message_ids), chat_id, caption)

    async def send_document(
        self, chat_id: int, document: Any, caption: str = "", **kwargs: Any
    ) -> FakeMessage:
        """تسجيل إرسال مستند (إثبات دفع مرفوع كملف في لوحة الأدمن)."""
        self.sent.append(
            SentMessage("document", chat_id, caption, kwargs.get("reply_markup"), {**kwargs, "document": document})
        )
        return FakeMessage(next(self._message_ids), chat_id, caption)

    async def answer_callback_query(
        self, callback_query_id: str, text: str | None = None, show_alert: bool = False, **kwargs: Any
    ) -> bool:
        """تسجيل الرد على ضغطة زر (إزالة مؤشر الانتظار)."""
        fault = self._fault("answer")
        if fault is not None:
            raise fault[0]
        self.answers.append({"id": callback_query_id, "text": text, "alert": show_alert})
        return True

    async def delete_message(self, chat_id: int, message_id: int, **kwargs: Any) -> bool:
        """تسجيل حذف رسالة (تنظيف المحادثة عند /start)."""
        self.deleted.append((chat_id, message_id))
        return True

    async def get_chat_member(self, chat_id: Any, user_id: int, **kwargs: Any) -> Any:
        """عضوية قابلة للبرمجة: خطأ مبرمج للقناة، وإلا حالة من `memberships`، وإلا «User not found»."""
        from telegram.error import BadRequest

        self.member_calls.append((chat_id, user_id))
        if chat_id in self.member_errors:
            raise self.member_errors[chat_id]
        status = self.memberships.get((chat_id, user_id))
        if status is None:
            raise BadRequest("User not found")
        return SimpleNamespace(status=status, is_member=status == "restricted", can_post_messages=True)

    async def get_chat(self, chat_id: Any, **kwargs: Any) -> Any:
        """بيانات محادثة مبرمجة (استثناء يُرفع، أو كائن يُعاد)."""
        result = self.chats.get(chat_id)
        if isinstance(result, BaseException):
            raise result
        if result is None:
            from telegram.error import BadRequest

            raise BadRequest("Chat not found")
        return result

    async def get_me(self, **kwargs: Any) -> Any:
        """هوية البوت (للتحقق من عضويته في القنوات)."""
        return SimpleNamespace(id=self.id, username=self.username)

    # ------------------------------ مساعدات ------------------------------ #

    @property
    def last(self) -> SentMessage:
        """آخر رسالة أُرسلت أو عُدِّلت."""
        if not self.sent:
            raise AssertionError("لم تُرسل أي رسالة بعد")
        return self.sent[-1]

    @property
    def texts(self) -> list[str]:
        """نصوص كل الرسائل المسجَّلة."""
        return [message.text for message in self.sent]

    def clear(self) -> None:
        """تفريغ السجلات بين خطوات الاختبار."""
        self.sent.clear()
        self.answers.clear()


class FakeApplication:
    """تطبيق مزيّف يحمل `bot_data` فقط (ما تحتاجه المعالجات)."""

    def __init__(self, bot: FakeBot, services: Any) -> None:
        """تهيئة التطبيق المزيّف بحاوية الخدمات."""
        self.bot = bot
        self.bot_data: dict[str, Any] = {"services": services}


class FakeContext:
    """سياق مزيّف يحاكي `ContextTypes.DEFAULT_TYPE` بالقدر الذي تستخدمه الواجهة."""

    def __init__(self, bot: FakeBot, services: Any) -> None:
        """تهيئة السياق ببوت وخدمات وذاكرة مستخدم فارغة."""
        self.bot = bot
        self.application = FakeApplication(bot, services)
        self.bot_data = self.application.bot_data
        self.user_data: dict[str, Any] = {}
        self.chat_data: dict[str, Any] = {}
        self.error: BaseException | None = None


def make_message_update(
    bot: FakeBot, *, text: str, user_id: int, chat_id: int | None = None, photo: bool = False
) -> Update:
    """
    بناء تحديث رسالة نصية حقيقي (أو صورة عند `photo=True`).

    المدخلات:
        text    : نص الرسالة (أو التعليق مع الصورة).
        user_id : معرف المستخدم في تيليجرام.
    """
    chat = chat_id if chat_id is not None else user_id
    message: dict[str, Any] = {
        "message_id": next(bot._message_ids),
        "date": int(time.time()),
        "chat": {"id": chat, "type": "private"},
        "from": {"id": user_id, "is_bot": False, "first_name": "Tester"},
    }
    if photo:
        message["photo"] = [
            {"file_id": "photo-file-id", "file_unique_id": "uniq", "width": 90, "height": 90}
        ]
        if text:
            message["caption"] = text
    else:
        message["text"] = text
        if text.startswith("/"):
            # تيليجرام يرفق كيان bot_command مع الأوامر — بدونه لا يلتقطها CommandHandler
            command = text.split()[0]
            message["entities"] = [
                {"type": "bot_command", "offset": 0, "length": len(command)}
            ]
    payload = {"update_id": next(_update_ids), "message": message}
    return Update.de_json(payload, bot)


def make_callback_update(
    bot: FakeBot, *, data: str, user_id: int, chat_id: int | None = None, message_id: int = 555
) -> Update:
    """بناء تحديث ضغطة زر حقيقي يحمل `callback_data` المطلوب."""
    chat = chat_id if chat_id is not None else user_id
    payload = {
        "update_id": next(_update_ids),
        "callback_query": {
            "id": f"cb-{next(_update_ids)}",
            "chat_instance": "test-instance",
            "data": data,
            "from": {"id": user_id, "is_bot": False, "first_name": "Tester"},
            "message": {
                "message_id": message_id,
                "date": int(time.time()),
                "chat": {"id": chat, "type": "private"},
                "from": {"id": BOT_ID, "is_bot": True, "first_name": "Bot", "username": "fake_bot"},
                "text": "شاشة سابقة",
            },
        },
    }
    return Update.de_json(payload, bot)
