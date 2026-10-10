"""
أدوات الأمان: تشفير أسرار المزودين، وإخفاء الأسرار عند العرض والتسجيل.

قواعد صارمة:
    • مفاتيح API للمزودين تُخزَّن مشفّرة (Fernet) ولا تُعرض كاملة أبداً.
    • لا يُكتب أي سر في ملفات اللوق.
"""

from __future__ import annotations

import hashlib
import re
import secrets

from cryptography.fernet import Fernet, InvalidToken

from core.exceptions import EncryptionError


def generate_encryption_key() -> str:
    """توليد مفتاح تشفير جديد (يوضع في متغير البيئة ENCRYPTION_KEY)."""
    return Fernet.generate_key().decode("utf-8")


class SecretBox:
    """
    صندوق تشفير متماثل للأسرار المخزَّنة في قاعدة البيانات.

    الاستخدام: تشفير api_key للمزود قبل الحفظ، وفك التشفير عند الاستدعاء فقط.
    """

    def __init__(self, key: str | None) -> None:
        """تهيئة الصندوق بمفتاح Fernet؛ يُرفع خطأ واضح إذا كان المفتاح ناقصاً أو تالفاً."""
        if not key:
            raise EncryptionError(
                "متغير البيئة ENCRYPTION_KEY غير موجود. "
                "ولّد مفتاحاً عبر: python -m scripts.init_db --gen-key"
            )
        try:
            self._fernet = Fernet(key.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise EncryptionError("قيمة ENCRYPTION_KEY غير صالحة (يجب أن تكون مفتاح Fernet).") from exc

    def encrypt(self, plaintext: str) -> str:
        """تشفير نص سري وإرجاعه كنص قابل للتخزين."""
        if not plaintext:
            raise EncryptionError("لا يمكن تشفير قيمة فارغة.")
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """فك تشفير نص مخزَّن؛ يُرفع خطأ إذا كان المفتاح خاطئاً أو البيانات تالفة."""
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError, TypeError) as exc:
            raise EncryptionError(
                "تعذر فك تشفير المفتاح المخزَّن — تأكد أن ENCRYPTION_KEY هو نفسه المستخدم عند الحفظ."
            ) from exc


def mask_secret(value: str | None, visible: int = 4) -> str:
    """
    إخفاء سر للعرض في الواجهة (يُظهر آخر أربعة محارف فقط).

    مثال: "abcd1234efgh" → "••••efgh"
    """
    if not value:
        return "غير محدد"
    tail = value[-visible:] if len(value) > visible else value
    return f"••••{tail}"


def secret_hint(value: str) -> str:
    """تلميح قصير يُخزَّن في قاعدة البيانات بجانب المفتاح المشفّر (آخر 4 محارف)."""
    return value[-4:] if len(value) >= 4 else "****"


def fingerprint(value: str) -> str:
    """بصمة SHA-256 مختصرة لقيمة سرية (للمقارنة دون كشف القيمة)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def new_token(length: int = 16) -> str:
    """توليد رمز عشوائي آمن (يُستخدم كمرجع فريد أو مفتاح منع تكرار)."""
    return secrets.token_urlsafe(length)


#: قيمة سرية: كل ما يلي علامة = أو : حتى أول فاصل، مع تجاهل علامات الاقتباس المحيطة
_SECRET_VALUE = r"[\"']?\s*[=:]\s*[\"']?[^\s,;&'\"}\])]+"

#: أنماط نصية يجب حذفها من أي نص يُسجَّل في اللوقات أو يُخزَّن في قاعدة البيانات
#: كل عنصر: (النمط، النص البديل)
_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # توكن بوت تيليجرام 123456789:AA... وكذلك داخل روابط API: /bot123456789:AA.../getUpdates
    # (لا نشترط حدّ كلمة قبل الرقم لأن "bot" ملتصقة به في الرابط)
    (re.compile(r"(?<!\d)(?:bot)?\d{6,12}:[A-Za-z0-9_\-]{30,}(?![A-Za-z0-9_\-])"), "***"),
    # رموز Fernet المشفّرة (مفاتيح المزودين المخزَّنة) تبدأ دائماً بـ gAAAA
    (re.compile(r"\bgAAAA[A-Za-z0-9_\-=]{40,}"), "***"),
    # api_key / token / secret / password بأي صيغة (JSON أو query أو سطر إعداد)
    (
        re.compile(
            r"(?i)\b(api[_-]?key|api[_-]?token|access[_-]?token|auth[_-]?token|token|secret"
            r"|password|passwd|pwd)\b" + _SECRET_VALUE
        ),
        r"\1=***",
    ),
    # المعامل key= المستخدم في لوحات SMM (perfect panel)
    (re.compile(r"(?i)\bkey\b" + _SECRET_VALUE), "key=***"),
    # بيانات اعتماد داخل الرابط: https://user:pass@host
    (re.compile(r"(?i)\b(https?://)[^\s/@:]+:[^\s/@]+@"), r"\1***@"),
)

#: أسرار معروفة وقت التشغيل (التوكن ومفتاح التشفير …) تُحذف حرفياً من أي نص
_KNOWN_SECRETS: set[str] = set()

#: أقصر طول مقبول لسر مسجَّل (قيمة أقصر تمسح كلمات عادية من النصوص)
MIN_REGISTERED_SECRET_LENGTH = 8


def register_secret(value: str | None) -> None:
    """
    تسجيل سر معروف (مثل BOT_TOKEN أو ENCRYPTION_KEY) ليُحذف حرفياً من كل لوق وحقل مخزَّن.

    لماذا إضافة للأنماط؟ النمط يلتقط الصيغ المعروفة فقط، أما التسجيل الصريح فيلتقط
    القيمة نفسها أياً كان موضعها (داخل traceback أو رسالة خطأ مكتبة خارجية).
    """
    if value and len(value) >= MIN_REGISTERED_SECRET_LENGTH:
        _KNOWN_SECRETS.add(value)


def clear_registered_secrets() -> None:
    """مسح الأسرار المسجَّلة (للاختبارات فقط)."""
    _KNOWN_SECRETS.clear()


def sanitize(text: str | None, extra_secrets: tuple[str, ...] = ()) -> str:
    """
    تنقية نص من الأسرار قبل تسجيله في اللوق أو حفظه في قاعدة البيانات.

    المدخلات:
        text           : النص الخام (مثل استجابة المزود أو رسالة الخطأ).
        extra_secrets  : قيم سرية معروفة يجب حذفها حرفياً (مثل مفتاح المزود الحالي).

    المخرجات: نص آمن للتسجيل.
    """
    if not text:
        return ""
    clean = str(text)
    for secret in (*extra_secrets, *_KNOWN_SECRETS):
        if secret:
            clean = clean.replace(secret, "***")
    for pattern, replacement in _SECRET_PATTERNS:
        clean = pattern.sub(replacement, clean)
    return clean
