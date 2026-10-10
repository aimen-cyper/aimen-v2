"""اختبارات تنقية الأسرار من النصوص واللوقات (المرحلة 9)."""

from __future__ import annotations

import logging

import pytest

from utils.logging_setup import RedactingFormatter, SecretRedactionFilter
from utils.security import register_secret, sanitize

TOKEN = "123456789:AAFakeTokenValue1234567890abcdefghi"


@pytest.mark.parametrize(
    "text",
    [
        f"https://api.telegram.org/bot{TOKEN}/getUpdates",
        f"token={TOKEN}",
        "api_key=abcdef123456",
        '{"api_key": "abcdef123456"}',
        "key=SECRETVALUE99",
        "password: hunter2hunter2",
        "https://user:pass1234@host.com/x",
        "Authorization failed secret='my-long-secret'",
    ],
)
def test_known_secret_shapes_are_removed(text: str) -> None:
    """الصيغ الشائعة للأسرار تُحذف قيمها."""
    clean = sanitize(text)
    for leaked in ("AAFakeTokenValue", "abcdef123456", "SECRETVALUE99", "hunter2hunter2", "pass1234", "my-long-secret"):
        assert leaked not in clean, clean


def test_fernet_ciphertext_is_removed() -> None:
    """نص Fernet المشفّر (مفتاح مزود مخزَّن) لا يظهر في أي نص."""
    cipher = "gAAAAAB" + "x" * 80
    assert cipher not in sanitize(f"stored value {cipher} end")


def test_registered_secret_is_removed_anywhere() -> None:
    """السر المسجَّل يُحذف حرفياً حتى لو لم يطابق أي نمط."""
    register_secret("plain-looking-secret-value")
    assert "plain-looking-secret-value" not in sanitize("خطأ: plain-looking-secret-value في الاتصال")


def test_short_registered_secret_is_ignored() -> None:
    """سر أقصر من الحد لا يُسجَّل (حتى لا يمسح كلمات عادية)."""
    register_secret("abc")
    assert sanitize("abc def") == "abc def"


def test_extra_secrets_are_removed() -> None:
    """الأسرار الإضافية الممرَّرة وقت الاستدعاء تُحذف أيضاً."""
    assert "provider-key-77" not in sanitize("bad provider-key-77 here", ("provider-key-77",))


def test_sanitize_handles_empty() -> None:
    """None والنص الفارغ ينتجان نصاً فارغاً."""
    assert sanitize(None) == ""
    assert sanitize("") == ""


def test_ordinary_text_is_untouched() -> None:
    """نص عادي بلا أسرار لا يتغير (لا إيجابيات كاذبة)."""
    text = "تم إنشاء الطلب ORD-123 بنجاح لعدد 1000"
    assert sanitize(text) == text


def test_log_file_never_contains_secrets(tmp_path) -> None:
    """
    ما يُكتب في ملف اللوق ينقّى حتى من استثناءات تحمل السر.

    نركّب المعالج بنفس فلتر ومنسّق الإنتاج على مسجّل خاص بالاختبار، فلا نعتمد
    على الحالة العامة لـ`setup_logging` (تُهيَّأ مرة واحدة في العملية).
    """
    log_file = tmp_path / "bot.log"
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.addFilter(SecretRedactionFilter())
    handler.setFormatter(RedactingFormatter("%(levelname)s %(message)s"))
    logger = logging.getLogger("phase9.test.isolated")
    logger.propagate = False
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        try:
            raise RuntimeError(f"فشل الاتصال token={TOKEN}")
        except RuntimeError:
            logger.exception("خطأ مع %s", "api_key=abcdef123456")
        handler.flush()
    finally:
        logger.removeHandler(handler)
        handler.close()
    content = log_file.read_text(encoding="utf-8")
    assert "AAFakeTokenValue" not in content
    assert "abcdef123456" not in content
    assert "فشل الاتصال" in content
