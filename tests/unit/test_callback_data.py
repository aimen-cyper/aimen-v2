"""
اختبارات ترميز `callback_data`.

هذه الطبقة صغيرة لكنها حرجة: خطأ فيها يعني أزراراً لا تعمل عند كل المستخدمين،
أو — أسوأ — زراً ينفّذ أمراً غير المقصود.
"""

from __future__ import annotations

import pytest

from keyboards.callback_data import (
    CALLBACK_VERSION,
    MAX_CALLBACK_BYTES,
    Callback,
    CallbackError,
    pack,
    pattern,
    unpack,
)


def test_pack_unpack_roundtrip() -> None:
    """الترميز ثم الفك يعيدان نفس القيم."""
    raw = pack("ord", "view", 12, "all", 3)
    data = unpack(raw)
    assert data.namespace == "ord"
    assert data.action == "view"
    assert data.int_arg(0) == 12
    assert data.arg(1) == "all"
    assert data.int_arg(2) == 3
    assert data.version == CALLBACK_VERSION


def test_pack_includes_version_suffix() -> None:
    """كل زر يحمل رقم إصدار حتى نميّز أزرار النسخ القديمة."""
    assert pack("nav", "home").endswith(f"v{CALLBACK_VERSION}")


def test_unpack_rejects_empty_and_malformed() -> None:
    """المدخلات الفارغة أو المشوّهة تُرفض باستثناء واضح لا بصمت."""
    with pytest.raises(CallbackError):
        unpack("")
    with pytest.raises(CallbackError):
        unpack(None)
    with pytest.raises(CallbackError):
        unpack("onlynamespace")


def test_old_version_is_detected() -> None:
    """زر من إصدار سابق يُكتشف بدل تنفيذه بافتراضات خاطئة."""
    data = unpack("nav:home::v0")
    assert data.is_current_version is False


def test_int_arg_default_when_missing_or_invalid() -> None:
    """الوسيط الرقمي الناقص أو غير الرقمي يرجع القيمة الافتراضية لا استثناء."""
    data = unpack(pack("cat", "list"))
    assert data.int_arg(0, 7) == 7
    broken = unpack(pack("cat", "list", "abc"))
    assert broken.int_arg(0, 1) == 1


def test_pack_rejects_too_long_payload() -> None:
    """تيليجرام يحدّ `callback_data` بـ64 بايت — نمنع التجاوز عند البناء لا عند الإرسال."""
    with pytest.raises(CallbackError):
        pack("sup", "view", "x" * (MAX_CALLBACK_BYTES + 10))


def test_pack_rejects_separator_inside_argument() -> None:
    """وسيط يحتوي الفاصل سيكسر الفك — يُرفض مبكراً."""
    with pytest.raises(CallbackError):
        pack("ord", "view", "12:34")


@pytest.mark.parametrize(
    ("candidate", "should_match"),
    [
        ("ord:cancel:5:v1", True),
        ("ord:cancelyes:5:v1", False),      # الفرق بين تأكيد الإلغاء وتنفيذه
        ("ord:cancel:v1", True),
        ("xord:cancel:5:v1", False),
    ],
)
def test_pattern_matches_exact_action(candidate: str, should_match: bool) -> None:
    """نمط المعالج يطابق الفعل بدقة ولا يبتلع فعلاً آخر يبدأ بنفس الحروف."""
    import re

    compiled = re.compile(pattern("ord", "cancel"))
    assert bool(compiled.search(candidate)) is should_match


def test_callback_dataclass_arg_defaults() -> None:
    """`Callback.arg` يرجع الافتراضي عند تجاوز عدد الوسائط."""
    data = Callback(namespace="acc", action="notif", args=("2",), version=CALLBACK_VERSION)
    assert data.arg(0) == "2"
    assert data.arg(5, "fallback") == "fallback"
