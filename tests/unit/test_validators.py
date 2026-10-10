"""
اختبارات التحقق من مدخلات المستخدم.

كل مُدخل من تيليجرام يمر عبر هذه الدوال، فأي ثغرة هنا تصل مباشرة إلى
قاعدة البيانات أو إلى المزود.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.exceptions import (
    InvalidAmountError,
    InvalidLinkError,
    QuantityOutOfRangeError,
    ValidationError,
)
from utils.validators import (
    clean_text,
    normalize_digits,
    normalize_username,
    parse_amount_units,
    validate_amount_range,
    validate_link,
    validate_message,
    validate_quantity,
    validate_subject,
    validate_telegram_id,
    validate_transaction_reference,
    validate_url,
)


# ------------------------------- الأرقام -------------------------------- #


def test_normalize_arabic_digits() -> None:
    """الأرقام العربية-الهندية تُحوَّل إلى أرقام لاتينية."""
    assert normalize_digits("١٢٣٤٥") == "12345"
    assert normalize_digits("۱۲۳") == "123"
    assert normalize_digits("abc 7") == "abc 7"


# -------------------------------- الروابط -------------------------------- #


@pytest.mark.parametrize(
    "link",
    [
        "https://instagram.com/username",
        "http://tiktok.com/@user/video/123",
        "instagram.com/user",  # بلا بروتوكول — يُضاف تلقائياً
    ],
)
def test_valid_links_accepted(link: str) -> None:
    """الروابط الصحيحة تُقبل وتُعاد بصيغة كاملة."""
    result = validate_link(link)
    assert result.startswith("http")


@pytest.mark.parametrize(
    "link",
    ["", "   ", "ftp://example.com/file", "not a link", "https://localhost", "http://" + "a" * 600],
)
def test_invalid_links_rejected(link: str) -> None:
    """الروابط الفارغة أو ذات البروتوكول غير المدعوم أو بلا نطاق تُرفض."""
    with pytest.raises(InvalidLinkError):
        validate_link(link)


def test_link_pattern_enforced() -> None:
    """نمط الخدمة يمنع إرسال رابط من منصة أخرى."""
    pattern = r"instagram\.com"
    assert validate_link("https://instagram.com/user", pattern=pattern)
    with pytest.raises(InvalidLinkError):
        validate_link("https://tiktok.com/@user", pattern=pattern)


def test_broken_service_pattern_reports_configuration_error() -> None:
    """نمط خاطئ في إعداد الخدمة يُبلَّغ كخطأ إعداد لا كخطأ من المستخدم."""
    with pytest.raises(ValidationError):
        validate_link("https://instagram.com/user", pattern="[unclosed")


# -------------------------------- الكميات -------------------------------- #


def test_quantity_within_range() -> None:
    """الكمية ضمن الحدود تُقبل، وتُقبل أيضاً مكتوبة بأرقام عربية أو بفواصل."""
    assert validate_quantity(500, min_quantity=100, max_quantity=1000) == 500
    assert validate_quantity("١٠٠٠", min_quantity=100, max_quantity=1000) == 1000
    assert validate_quantity("1,000", min_quantity=100, max_quantity=1000) == 1000


@pytest.mark.parametrize("raw", [50, 5000, "abc", "", "-100", True])
def test_quantity_out_of_range_rejected(raw) -> None:
    """الكميات خارج الحدود أو غير الرقمية تُرفض."""
    with pytest.raises(QuantityOutOfRangeError):
        validate_quantity(raw, min_quantity=100, max_quantity=1000)


# -------------------------------- المبالغ -------------------------------- #


def test_parse_amount_units_variants() -> None:
    """المبلغ يُقبل بصيغ متعددة ويُحوَّل إلى وحدات صحيحة (×10000)."""
    assert parse_amount_units("1") == 10_000
    assert parse_amount_units("1.5") == 15_000
    assert parse_amount_units("1,500") == 15_000_000
    assert parse_amount_units(Decimal("2.25")) == 22_500
    assert parse_amount_units("١٠") == 100_000


@pytest.mark.parametrize("raw", ["0", "-5", "abc", ""])
def test_invalid_amounts_rejected(raw: str) -> None:
    """المبالغ الصفرية والسالبة وغير الرقمية تُرفض."""
    with pytest.raises(InvalidAmountError):
        parse_amount_units(raw)


def test_amount_range_enforced() -> None:
    """حدود المبلغ تُطبَّق من الطرفين."""
    assert validate_amount_range(50_000, min_units=10_000, max_units=100_000) == 50_000
    with pytest.raises(InvalidAmountError):
        validate_amount_range(5_000, min_units=10_000, max_units=100_000)
    with pytest.raises(InvalidAmountError):
        validate_amount_range(500_000, min_units=10_000, max_units=100_000)


def test_zero_max_means_no_upper_limit() -> None:
    """الحد الأقصى صفر يعني «بلا حد أقصى»."""
    assert validate_amount_range(10_000_000, min_units=0, max_units=0) == 10_000_000


# ------------------------------ أرقام الحوالات ----------------------------- #


def test_transaction_reference_accepted() -> None:
    """مرجع الحوالة المكوَّن من أرقام/حروف إنجليزية يُقبل."""
    assert validate_transaction_reference("TRX-99812") == "TRX-99812"
    assert validate_transaction_reference("١٢٣٤٥") == "12345"


def test_transaction_reference_required_and_format() -> None:
    """المرجع مطلوب عند الطلب، والرموز غير المسموحة تُرفض."""
    with pytest.raises(ValidationError):
        validate_transaction_reference("", required=True)
    with pytest.raises(ValidationError):
        validate_transaction_reference("ab")          # قصير جداً
    with pytest.raises(ValidationError):
        validate_transaction_reference("حوالة ١٢٣")   # حروف عربية ومسافات
    assert validate_transaction_reference(None, required=False) is None


# ------------------------------- نصوص عامة ------------------------------- #


def test_clean_text_trims_and_limits() -> None:
    """تنظيف النص يوحّد الفراغات ويفرض الحد الأقصى."""
    assert clean_text("  مرحبا   بك  ", field="الاسم", max_length=20) == "مرحبا بك"
    with pytest.raises(ValidationError):
        clean_text("x" * 50, field="الاسم", max_length=20)
    with pytest.raises(ValidationError):
        clean_text("   ", field="الاسم", max_length=20)


def test_subject_and_message_validation() -> None:
    """عنوان التذكرة ونصها يخضعان لحدود الطول."""
    assert validate_subject("مشكلة في طلب") == "مشكلة في طلب"
    assert validate_message("لم يصلني الطلب") == "لم يصلني الطلب"
    with pytest.raises(ValidationError):
        validate_subject("")
    with pytest.raises(ValidationError):
        validate_message("x" * 5000)


def test_telegram_id_and_username() -> None:
    """معرف تيليجرام رقمي موجب، واسم المستخدم بلا @ وبطول صحيح."""
    assert validate_telegram_id("123456789") == 123456789
    with pytest.raises(ValidationError):
        validate_telegram_id("-5")
    with pytest.raises(ValidationError):
        validate_telegram_id("abc")
    assert normalize_username("@Tester_1") == "Tester_1"
    assert normalize_username("ab") is None
    assert normalize_username(None) is None


def test_validate_url_for_provider_api() -> None:
    """رابط API المزود يجب أن يكون http(s) صحيحاً."""
    assert validate_url("https://panel.example.com/api/v2") == "https://panel.example.com/api/v2"
    with pytest.raises(ValidationError):
        validate_url("javascript:alert(1)")
    with pytest.raises(ValidationError):
        validate_url("")
