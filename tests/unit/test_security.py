"""اختبارات أدوات الأمان: تشفير مفاتيح المزودين ومنع تسرب الأسرار."""

from __future__ import annotations

import logging

import pytest

from core.exceptions import EncryptionError
from utils.logging_setup import SecretRedactionFilter
from utils.security import (
    SecretBox,
    fingerprint,
    generate_encryption_key,
    mask_secret,
    new_token,
    sanitize,
    secret_hint,
)


def test_encrypt_decrypt_roundtrip() -> None:
    """التشفير وفك التشفير يعيدان النص الأصلي، والنص المشفّر لا يحتوي السر."""
    box = SecretBox(generate_encryption_key())
    secret = "sk_live_4f8a9b2c7d1e"
    encrypted = box.encrypt(secret)
    assert encrypted != secret
    assert secret not in encrypted
    assert box.decrypt(encrypted) == secret


def test_encryption_is_not_deterministic() -> None:
    """تشفير نفس القيمة مرتين يعطي نصين مختلفين (Fernet يضيف IV عشوائياً)."""
    box = SecretBox(generate_encryption_key())
    assert box.encrypt("same-key") != box.encrypt("same-key")


def test_wrong_key_cannot_decrypt() -> None:
    """مفتاح مختلف لا يستطيع فك التشفير — يُرفع خطأ واضح لا نتيجة خاطئة."""
    encrypted = SecretBox(generate_encryption_key()).encrypt("secret-value")
    other = SecretBox(generate_encryption_key())
    with pytest.raises(EncryptionError):
        other.decrypt(encrypted)


def test_missing_or_invalid_key_rejected() -> None:
    """غياب المفتاح أو تلفه يُكتشف عند الإقلاع لا عند أول استخدام."""
    with pytest.raises(EncryptionError):
        SecretBox(None)
    with pytest.raises(EncryptionError):
        SecretBox("مفتاح-غير-صالح")


def test_empty_plaintext_rejected() -> None:
    """لا يُسمح بتشفير قيمة فارغة (يعني غالباً خطأ في الإدخال)."""
    with pytest.raises(EncryptionError):
        SecretBox(generate_encryption_key()).encrypt("")


def test_mask_secret_shows_tail_only() -> None:
    """العرض في الواجهة يُظهر آخر أربعة محارف فقط."""
    assert mask_secret("abcd1234efgh") == "••••efgh"
    assert mask_secret(None) == "غير محدد"
    assert "abcd1234" not in mask_secret("abcd1234efgh")


def test_secret_hint_and_fingerprint() -> None:
    """التلميح والبصمة لا يكشفان السر ولا يمكن عكسهما."""
    secret = "verylongapikey987654"
    assert secret_hint(secret) == "7654"
    assert secret_hint("ab") == "****"
    digest = fingerprint(secret)
    assert len(digest) == 16
    assert secret not in digest
    assert fingerprint(secret) == digest  # ثابتة


def test_sanitize_removes_known_secret_patterns() -> None:
    """التنقية تحذف التوكن والمفاتيح من أي نص قبل تسجيله."""
    text = "GET https://panel.test/api?key=SUPERSECRET&action=add"
    clean = sanitize(text)
    assert "SUPERSECRET" not in clean
    assert "action=add" in clean

    bot_log = "فشل الاتصال بالتوكن 123456789:AAFakeTokenValue1234567890abcdefghi"
    assert "AAFakeTokenValue" not in sanitize(bot_log)

    payload = 'api_key: "abc123xyz"'
    assert "abc123xyz" not in sanitize(payload)


def test_sanitize_removes_explicit_secrets() -> None:
    """أي قيمة سرية معروفة تُحذف حرفياً حتى لو لم تطابق نمطاً."""
    clean = sanitize("الرد: {'balance': 10, 'k': 'PLAINKEY'}", extra_secrets=("PLAINKEY",))
    assert "PLAINKEY" not in clean
    assert "***" in clean
    assert sanitize(None) == ""


def test_new_token_is_unique() -> None:
    """الرموز العشوائية لا تتكرر (تُستخدم كمراجع فريدة)."""
    tokens = {new_token() for _ in range(100)}
    assert len(tokens) == 100


def test_log_filter_redacts_secrets() -> None:
    """مرشّح اللوق يحذف الأسرار قبل كتابتها في الملف."""
    log_filter = SecretRedactionFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="طلب إلى المزود key=TOPSECRET123 تم", args=(), exc_info=None,
    )
    assert log_filter.filter(record) is True
    assert "TOPSECRET123" not in record.getMessage()


def test_log_filter_redacts_arguments() -> None:
    """الأسرار الممرَّرة كوسائط للوق تُنقّى أيضاً."""
    log_filter = SecretRedactionFilter()
    record = logging.LogRecord(
        name="test", level=logging.ERROR, pathname=__file__, lineno=1,
        msg="خطأ في %s", args=("token=ABCDEF123456",), exc_info=None,
    )
    log_filter.filter(record)
    assert "ABCDEF123456" not in record.getMessage()
