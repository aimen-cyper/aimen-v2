"""
قراءة وتطبيع معرّفات القنوات/المحادثات التي يكتبها المالك في الإعدادات أو متغيرات البيئة.

لماذا ملف مستقل؟
    «Chat not found» من أكثر أخطاء تيليجرام شيوعاً عند ضبط القنوات، وسببها شبه دائم صيغة المعرّف:
        • رقم قناة بلا `-100` في أوله (يعيد تيليجرام «chat not found»)؛
        • رابط دعوة `t.me/+xxxx` وُضع مكان المعرّف (لا يصلح للإرسال ولا للتحقق من العضوية)؛
        • @username بإملاء خاطئ.
    هنا نُطبّع ما يمكن تطبيعه بأمان، ونرفض الباقي برسالة عربية تقول ما الخطأ بالضبط وكيف يُصلَح.

الصيغة المقبولة في إعداد قناة: `المعرّف` أو `المعرّف رابط_دعوة` (الرابط اختياري ويلزم للقنوات الخاصة
حتى يظهر زر «انضمام» للمستخدم).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from utils.validators import normalize_digits

#: اسم مستخدم تيليجرام الصالح (5–32 حرفاً، يبدأ بحرف)
_USERNAME_RE: Final = re.compile(r"[A-Za-z][A-Za-z0-9_]{4,31}")
#: روابط تيليجرام المقبولة كرابط دعوة/انضمام
_LINK_RE: Final = re.compile(r"https://(?:t\.me|telegram\.me)/[A-Za-z0-9_+/\-]{3,100}", re.IGNORECASE)
#: رابط عام لقناة بمعرّفها: t.me/name (ليس +invite ولا joinchat ولا c/)
_PUBLIC_LINK_RE: Final = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/(?P<name>[A-Za-z][A-Za-z0-9_]{4,31})/?", re.IGNORECASE
)


class ChannelRefError(ValueError):
    """معرّف قناة غير صالح؛ نص الاستثناء رسالة عربية جاهزة للعرض."""


@dataclass(frozen=True, slots=True)
class ChannelRef:
    """قناة بعد التطبيع: المعرّف (رقم أو @username) ورابط انضمام اختياري."""

    chat_id: int | str
    link: str | None = None

    @property
    def canonical(self) -> str:
        """الصيغة القياسية للتخزين: `المعرّف` أو `المعرّف الرابط`."""
        return f"{self.chat_id} {self.link}" if self.link else str(self.chat_id)

    @property
    def join_url(self) -> str | None:
        """رابط يفتحه المستخدم للانضمام: الرابط المُدخل، وإلا رابط @username العام، وإلا None."""
        if self.link:
            return self.link
        if isinstance(self.chat_id, str) and self.chat_id.startswith("@"):
            return f"https://t.me/{self.chat_id[1:]}"
        return None


def normalize_chat_ref(raw: object, *, allow_user_ids: bool = False) -> int | str:
    """
    تطبيع معرّف محادثة إلى رقم (`-100…`) أو `@username`.

    المدخلات:
        allow_user_ids : السماح بمعرّف موجب (محادثة خاصة مع شخص) — لقناة تنبيهات الإدارة فقط؛ القنوات
                         والمجموعات دائماً سالبة.

    الاستثناءات:
        ChannelRefError : صيغة غير صالحة (الرسالة تشرح السبب والحل).
    """
    text = normalize_digits(str(raw if raw is not None else "")).strip()
    if not text:
        raise ChannelRefError("المعرّف فارغ.")

    if "+" in text and ("t.me" in text.lower() or "telegram.me" in text.lower()):
        raise ChannelRefError(
            "هذا رابط دعوة وليس معرّف قناة. اكتب معرّف القناة (-100xxxxxxxxxx أو @username) "
            "ثم ضع رابط الدعوة بعده بمسافة."
        )
    if "joinchat" in text.lower():
        raise ChannelRefError("رابط joinchat لا يصلح معرّفاً. اكتب -100xxxxxxxxxx أو @username.")

    public = _PUBLIC_LINK_RE.fullmatch(text)
    if public:
        return f"@{public.group('name')}"

    if text.startswith("@"):
        if not _USERNAME_RE.fullmatch(text[1:]):
            raise ChannelRefError("اسم المستخدم غير صالح: 5–32 حرفاً إنجليزياً/أرقاماً/شرطة سفلية ويبدأ بحرف.")
        return text

    if re.fullmatch(r"-?\d{5,20}", text):
        number = int(text)
        if number > 0 and text.startswith("100") and len(text) >= 12:
            return -number                  # -100 ناقصة: خطأ شائع، والتصحيح آمن (لا معرّف مستخدم بهذا الطول)
        if number > 0 and not allow_user_ids:
            raise ChannelRefError(
                "معرّف القناة أو المجموعة يكون سالباً ويبدأ بـ -100 (مثال -1001234567890). "
                "انسخه من بوت مثل @userinfobot أو @getidsbot بتحويل رسالة من القناة إليه."
            )
        return number

    if _USERNAME_RE.fullmatch(text):
        return f"@{text}"                   # اسم بلا @ — نصحّحه
    raise ChannelRefError("صيغة غير مفهومة. استخدم -100xxxxxxxxxx أو @username.")


def parse_channel_value(raw: object, *, allow_user_ids: bool = False) -> ChannelRef:
    """
    قراءة قيمة إعداد قناة: `المعرّف [رابط الدعوة]`.

    الاستثناءات: ChannelRefError عند أي صيغة غير صالحة.
    """
    text = normalize_digits(str(raw if raw is not None else "")).strip()
    if not text:
        raise ChannelRefError("القيمة فارغة.")
    parts = text.split()
    if len(parts) > 2:
        raise ChannelRefError("الصيغة: المعرّف ثم (اختيارياً) رابط الدعوة، بمسافة واحدة بينهما.")

    # رابط عام وحده (t.me/name) يُقرأ معرّفاً؛ أما رابط الدعوة +xxx فيُرفض في normalize_chat_ref
    chat_id = normalize_chat_ref(parts[0], allow_user_ids=allow_user_ids)
    link: str | None = None
    if len(parts) == 2:
        if not _LINK_RE.fullmatch(parts[1]):
            raise ChannelRefError("رابط الدعوة يجب أن يكون https://t.me/... كاملاً.")
        link = parts[1]
    return ChannelRef(chat_id=chat_id, link=link)


def try_parse_chat_id(raw: object, *, allow_user_ids: bool = True) -> int | str | None:
    """معرّف المحادثة من نص إعداد، أو None إن كان فارغاً/غير صالح (للاستخدام في مسارات لا ترفع)."""
    text = str(raw if raw is not None else "").strip()
    if not text:
        return None
    try:
        return parse_channel_value(text, allow_user_ids=allow_user_ids).chat_id
    except ChannelRefError:
        return None
