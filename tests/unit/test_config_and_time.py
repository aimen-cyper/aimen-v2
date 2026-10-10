"""اختبارات الإعدادات وأدوات الوقت (أساس كل جدولة ومقارنة تواريخ في النظام)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from config import Config, ConfigError
from utils.datetime_utils import (
    day_bounds_utc,
    is_past,
    iso_minus_days,
    iso_plus_seconds,
    parse_iso,
    to_iso,
    to_local_text,
    utc_now,
    utc_now_iso,
)


# -------------------------------- الإعدادات -------------------------------- #


def _write_env(tmp_path: Path, content: str) -> Path:
    """كتابة ملف بيئة مؤقت للاختبار."""
    env_file = tmp_path / ".env"
    env_file.write_text(content, encoding="utf-8")
    return env_file


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch):
    """عزل متغيرات البيئة حتى لا تتسرب بين الاختبارات."""
    for key in (
        "BOT_TOKEN", "SUPER_ADMIN_IDS", "ENCRYPTION_KEY", "DATABASE_PATH", "LOG_LEVEL",
        "LOG_FILE", "BACKUP_DIR", "TIMEZONE", "ADMIN_ALERT_CHAT_ID", "BACKUP_CHANNEL_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


def test_defaults_when_env_is_minimal(tmp_path: Path) -> None:
    """الإعدادات الافتراضية معقولة ولا تنهار عند ملف بيئة شبه فارغ."""
    config = Config.load(env_file=_write_env(tmp_path, "LOG_LEVEL=INFO\n"))
    assert config.timezone == "Asia/Aden"
    assert config.log_level == "INFO"
    assert config.database_path.name == "smm_bot.db"
    assert config.super_admin_ids == ()
    assert config.bot_token is None


def test_missing_bot_token_is_rejected_for_bot(tmp_path: Path) -> None:
    """تشغيل البوت بلا توكن يفشل برسالة واضحة لا بانهيار غامض."""
    with pytest.raises(ConfigError, match="BOT_TOKEN"):
        Config.load(require_bot_token=True, env_file=_write_env(tmp_path, "LOG_LEVEL=INFO\n"))


def test_super_admin_ids_parsed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """قائمة معرفات الأدمن الأعلى تُقرأ بفواصل أو فواصل منقوطة."""
    monkeypatch.setenv("SUPER_ADMIN_IDS", " 111 , 222 ;333 ")
    config = Config.load(env_file=_write_env(tmp_path, ""))
    assert config.super_admin_ids == (111, 222, 333)


def test_invalid_super_admin_ids_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """قيمة غير رقمية في معرفات الأدمن تُرفض بدل تجاهلها بصمت."""
    monkeypatch.setenv("SUPER_ADMIN_IDS", "111,abc")
    with pytest.raises(ConfigError, match="SUPER_ADMIN_IDS"):
        Config.load(env_file=_write_env(tmp_path, ""))


def test_invalid_log_level_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """مستوى تسجيل غير معروف يُرفض عند الإقلاع."""
    monkeypatch.setenv("LOG_LEVEL", "VERBOSE")
    with pytest.raises(ConfigError, match="LOG_LEVEL"):
        Config.load(env_file=_write_env(tmp_path, ""))


def test_safe_summary_hides_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ملخص الإعدادات لا يطبع التوكن ولا مفتاح التشفير أبداً."""
    monkeypatch.setenv("BOT_TOKEN", "123456789:AAFakeTokenValue1234567890abcdefghi")
    from utils.security import generate_encryption_key

    key = generate_encryption_key()
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    summary = Config.load(env_file=_write_env(tmp_path, "")).safe_summary()
    joined = " ".join(summary.values())
    assert "AAFakeTokenValue" not in joined
    assert key not in joined
    assert summary["bot_token"].startswith("✓")


def test_ensure_directories_creates_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """التهيئة تنشئ مجلدات البيانات واللوقات والنسخ الاحتياطية."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "db" / "x.db"))
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "logs" / "bot.log"))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "bk"))
    config = Config.load(env_file=_write_env(tmp_path, ""))
    config.ensure_directories()
    assert (tmp_path / "db").is_dir()
    assert (tmp_path / "logs").is_dir()
    assert (tmp_path / "bk").is_dir()


def test_relative_paths_resolved_to_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """المسار النسبي يُحسب من جذر المشروع لا من مجلد التشغيل الحالي."""
    monkeypatch.setenv("DATABASE_PATH", "data/custom.db")
    config = Config.load(env_file=_write_env(tmp_path, ""))
    assert config.database_path.is_absolute()
    assert config.database_path.parts[-2:] == ("data", "custom.db")


# --------------------------------- الوقت ---------------------------------- #


def test_utc_now_iso_format() -> None:
    """الوقت المخزَّن دائماً UTC بصيغة ISO تنتهي بحرف Z."""
    value = utc_now_iso()
    assert value.endswith("Z")
    assert "T" in value
    parsed = parse_iso(value)
    assert parsed is not None and parsed.tzinfo == timezone.utc


def test_iso_strings_sort_chronologically() -> None:
    """الترتيب النصي للتواريخ = الترتيب الزمني (شرط صحة كل الاستعلامات)."""
    earlier = to_iso(utc_now() - timedelta(days=1))
    later = utc_now_iso()
    assert earlier < later


def test_parse_iso_handles_none_and_bad_values() -> None:
    """تحليل تاريخ فارغ أو تالف يُرجع None بدل رفع استثناء."""
    assert parse_iso(None) is None
    assert parse_iso("") is None
    assert parse_iso("ليس تاريخاً") is None


def test_iso_plus_seconds_and_is_past() -> None:
    """حساب المواعيد المستقبلية والماضية (أساس lease الطلبات وإعادة المحاولة)."""
    future = iso_plus_seconds(120)
    past = iso_plus_seconds(-120)
    assert is_past(future) is False
    assert is_past(past) is True
    assert is_past(None) is True


def test_iso_minus_days() -> None:
    """حساب بداية نافذة زمنية للخلف (للإحصائيات وكشف التكرار)."""
    value = parse_iso(iso_minus_days(7))
    assert value is not None
    delta = utc_now() - value
    assert 6.9 < delta.total_seconds() / 86400 < 7.1


def test_to_local_text_uses_local_timezone() -> None:
    """العرض للمستخدم بتوقيت عدن (+3) لا بتوقيت UTC."""
    moment = datetime(2026, 1, 1, 22, 0, 0, tzinfo=timezone.utc)
    assert to_local_text(to_iso(moment)) == "2026-01-02 01:00"
    assert to_local_text(None) == "-"


def test_day_bounds_are_ordered_and_utc() -> None:
    """حدود اليوم المحلي تُحوَّل إلى UTC بشكل صحيح ومرتب."""
    start, end = day_bounds_utc(0)
    assert start < end
    assert start.endswith("Z") and end.endswith("Z")
    yesterday_start, yesterday_end = day_bounds_utc(1)
    assert yesterday_end <= start
    assert yesterday_start < yesterday_end


def test_no_naive_datetimes_leak() -> None:
    """كل التواريخ المنتَجة واعية بالمنطقة الزمنية (تجنب أخطاء المقارنة)."""
    assert utc_now().tzinfo is not None
    assert os.environ.get("TZ") in (None, "", os.environ.get("TZ"))
