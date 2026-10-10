"""اختبارات قواعد التحقق من الإعدادات (المرحلة 9)."""

from __future__ import annotations

import pytest

from core.exceptions import ValidationError
from core.setting_rules import check_ordered_pairs, normalize_decimal_text, normalize_setting_value


@pytest.mark.parametrize(
    ("key", "value", "value_type", "expected"),
    [
        ("rate_limit_actions_per_minute", "30", "int", "30"),
        ("rate_limit_actions_per_minute", "٣٠", "int", "30"),         # أرقام هندية
        ("admin_digest_hour", "0", "int", "0"),
        ("admin_digest_hour", "23", "int", "23"),
        ("maintenance_mode", "نعم", "bool", "true"),
        ("maintenance_mode", "off", "bool", "false"),
        ("maintenance_mode", True, "bool", "true"),
        ("support_username", "", "str", ""),
        ("support_username", "@my_support", "str", "@my_support"),
        ("currency_code", "YER", "str", "YER"),
        ("admin_adjust_max_units", "0", "money", "0"),
        ("admin_alert_chat_id", "-1001234567890", "str", "-1001234567890"),
    ],
)
def test_valid_values_are_normalized(key: str, value: object, value_type: str, expected: str) -> None:
    """القيم الصحيحة تُقبل وتُطبَّع."""
    assert normalize_setting_value(key, value, value_type) == expected


@pytest.mark.parametrize(
    ("key", "value", "value_type"),
    [
        ("rate_limit_actions_per_minute", "0", "int"),         # تعطيل الحماية بصفر
        ("rate_limit_actions_per_minute", "2", "int"),
        ("rate_limit_actions_per_minute", "100000", "int"),
        ("rate_limit_actions_per_minute", "abc", "int"),
        ("rate_limit_block_minutes", "0", "int"),
        ("admin_digest_hour", "24", "int"),
        ("admin_digest_hour", "-1", "int"),
        ("order_submit_interval_seconds", "1", "int"),         # أقل من حد الجدولة
        ("maintenance_mode", "ربما", "bool"),
        ("currency_code", "ريال", "str"),
        ("currency_code", "TOOLONGCODE", "str"),
        ("support_username", "ab", "str"),
        ("bot_name", "x" * 200, "str"),
        ("bot_name", "", "str"),
        ("admin_adjust_max_units", "-1", "money"),
        ("min_deposit_units", "0", "money"),
        ("some_json", "{broken", "json"),
        ("admin_alert_chat_id", "abc", "str"),
    ],
)
def test_invalid_values_are_rejected(key: str, value: object, value_type: str) -> None:
    """القيم الخارجة عن النطاق أو الصيغة تُرفض برسالة تحقق."""
    with pytest.raises(ValidationError):
        normalize_setting_value(key, value, value_type)


def test_unknown_key_gets_generic_limits() -> None:
    """مفتاح بلا قاعدة خاصة يخضع للحدود العامة بحسب نوعه."""
    assert normalize_setting_value("brand_new_key", "5", "int") == "5"
    with pytest.raises(ValidationError):
        normalize_setting_value("brand_new_key", "9" * 18, "int")


def test_ordered_pairs_min_must_not_exceed_max() -> None:
    """الحد الأدنى للشحن لا يتجاوز الأعلى وبالعكس."""
    current = {"min_deposit_units": "10000", "max_deposit_units": "500000"}
    check_ordered_pairs("min_deposit_units", "20000", current)
    with pytest.raises(ValidationError):
        check_ordered_pairs("min_deposit_units", "600000", current)
    with pytest.raises(ValidationError):
        check_ordered_pairs("max_deposit_units", "5000", current)


def test_ordered_pairs_ignores_unrelated_keys() -> None:
    """مفتاح خارج الأزواج لا يُفحص."""
    check_ordered_pairs("bot_name", "x", {"min_deposit_units": "1", "max_deposit_units": "0"})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("530.50", "530.5"), ("٥٣٠٫٥".replace("٫", "."), "530.5"), ("1,5", "1.5"), ("1", "1"), ("0.00000001", "0.00000001")],
)
def test_decimal_text_is_normalized(raw: str, expected: str) -> None:
    """سعر الصرف: أرقام هندية وفاصلة عربية وأصفار زائدة تُطبَّع."""
    assert normalize_decimal_text(raw) == expected


@pytest.mark.parametrize("raw", ["0", "-5", "NaN", "inf", "abc", "", "1.123456789", "1000000001"])
def test_decimal_text_rejects_invalid(raw: str) -> None:
    """صفر/سالب/NaN/لانهاية/خانات كثيرة/أكبر من مليار ⇒ رفض."""
    with pytest.raises(ValidationError):
        normalize_decimal_text(raw)
