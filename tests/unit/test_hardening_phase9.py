"""اختبارات المُهدِّئ وصلاحيات الملفات وتشديد الإعدادات (المرحلة 9)."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from config import Config, ConfigError
from utils.fs_security import DIR_MODE, FILE_MODE, check_paths
from utils.security import generate_encryption_key, sanitize
from utils.throttle import AlertThrottle

posix_only = pytest.mark.skipif(os.name != "posix", reason="صلاحيات POSIX فقط")


# ------------------------------ المُهدِّئ ------------------------------ #


class Clock:
    """ساعة يدوية."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_throttle_allows_first_then_suppresses_then_reports_count() -> None:
    """أول تنبيه يمر، والمتكرر يُكبت، ثم يذكر التنبيه التالي عدد المكبوت."""
    clock = Clock()
    throttle = AlertThrottle(clock=clock)
    assert throttle.check("a", cooldown_seconds=60).allow is True
    clock.now = 10
    assert throttle.check("a", cooldown_seconds=60).allow is False
    assert throttle.check("a", cooldown_seconds=60).allow is False
    clock.now = 61
    decision = throttle.check("a", cooldown_seconds=60)
    assert decision.allow is True and decision.suppressed == 2


def test_throttle_distinct_keys_independent_but_capped_per_window() -> None:
    """بصمات مختلفة مستقلة، لكن سقف النافذة يمنع الإغراق عند تنوّع الأخطاء."""
    throttle = AlertThrottle(max_per_window=3, clock=Clock())
    results = [throttle.check(f"k{i}", cooldown_seconds=60).allow for i in range(5)]
    assert results == [True, True, True, False, False]


def test_throttle_window_resets() -> None:
    """بعد مرور النافذة يعود السماح."""
    clock = Clock()
    throttle = AlertThrottle(max_per_window=1, clock=clock)
    assert throttle.check("a", cooldown_seconds=60).allow
    assert not throttle.check("b", cooldown_seconds=60).allow
    clock.now = 61
    assert throttle.check("b", cooldown_seconds=60).allow


# --------------------------- صلاحيات الملفات --------------------------- #


@posix_only
def test_check_paths_detects_and_fixes_insecure_files(tmp_path: Path) -> None:
    """ملف مفتوح للجميع يُكتشف بلا إصلاح، ثم يُضبط 600 مع الإصلاح."""
    secret = tmp_path / "secret.env"
    secret.write_text("X=1", encoding="utf-8")
    secret.chmod(0o644)
    entries = [(secret, "ملف سرّي", FILE_MODE)]

    [report] = check_paths(entries, fix=False)
    assert report.insecure and not report.fixed
    assert stat.S_IMODE(secret.stat().st_mode) == 0o644, "الفحص وحده لا يجب أن يعدّل"

    [fixed] = check_paths(entries, fix=True)
    assert fixed.fixed and not fixed.insecure
    assert stat.S_IMODE(secret.stat().st_mode) == 0o600


@posix_only
def test_check_paths_fixes_directories_and_skips_missing(tmp_path: Path) -> None:
    """المجلد يُضبط 700، والمسار غير الموجود يُتجاهل بلا خطأ."""
    folder = tmp_path / "backups"
    folder.mkdir()
    folder.chmod(0o755)
    entries = [(folder, "نسخ", DIR_MODE), (tmp_path / "missing.db", "قاعدة", FILE_MODE)]
    results = check_paths(entries, fix=True)
    assert len(results) == 1 and results[0].fixed
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700


@posix_only
def test_check_paths_secure_file_untouched(tmp_path: Path) -> None:
    """ملف سليم الصلاحية لا يُعدَّل ولا يُعلَّم كمخالف."""
    ok = tmp_path / "ok.db"
    ok.write_text("x", encoding="utf-8")
    ok.chmod(0o600)
    [report] = check_paths([(ok, "قاعدة", FILE_MODE)], fix=True)
    assert not report.insecure and not report.fixed


# ----------------------------- تشديد الإعدادات ----------------------------- #


def _env(tmp_path: Path, content: str) -> Path:
    """كتابة ملف بيئة مؤقت."""
    path = tmp_path / ".env"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    """عزل متغيرات البيئة."""
    for key in ("BOT_TOKEN", "ENCRYPTION_KEY", "SUPER_ADMIN_IDS"):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize("token", ["abc", "123:short", "notanumber:AAFakeTokenValue1234567890abcdefghi", "12345:AA bad token with spaces 1234567890"])
def test_malformed_bot_token_rejected_without_echoing_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, token: str) -> None:
    """توكن بصيغة خاطئة يُرفض عند التحميل، والرسالة لا تحتوي قيمته."""
    monkeypatch.setenv("BOT_TOKEN", token)
    with pytest.raises(ConfigError) as info:
        Config.load(env_file=_env(tmp_path, ""))
    assert token not in str(info.value)


def test_invalid_encryption_key_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """مفتاح تشفير ليس Fernet يُرفض مبكراً."""
    monkeypatch.setenv("ENCRYPTION_KEY", "not-a-fernet-key")
    with pytest.raises(ConfigError, match="ENCRYPTION_KEY"):
        Config.load(env_file=_env(tmp_path, ""))


@pytest.mark.parametrize("ids", ["-100123", "0", "5,-7"])
def test_non_positive_super_admin_ids_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ids: str) -> None:
    """معرّفات الأدمن الأعلى يجب أن تكون موجبة."""
    monkeypatch.setenv("SUPER_ADMIN_IDS", ids)
    with pytest.raises(ConfigError, match="SUPER_ADMIN_IDS"):
        Config.load(env_file=_env(tmp_path, ""))


def test_valid_secrets_are_registered_for_sanitizing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """بعد التحميل يُحذف التوكن والمفتاح حرفياً من أي نص حتى بلا صيغة معروفة."""
    key = generate_encryption_key()
    monkeypatch.setenv("BOT_TOKEN", "123456789:AAFakeTokenValue1234567890abcdefghi")
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    Config.load(env_file=_env(tmp_path, ""))
    assert key not in sanitize(f"فشل بسبب المفتاح {key} أثناء الفك")
    token = "123456789:AAFakeTokenValue1234567890abcdefghi"
    assert "AAFakeTokenValue" not in sanitize(f"استجابة غريبة [{token}] انتهت")


def test_sensitive_paths_cover_db_sidecars_and_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """قائمة المسارات الحسّاسة تشمل .env وملفات WAL/SHM والمجلدات."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "d" / "x.db"))
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "l" / "bot.log"))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "b"))
    config = Config.load(env_file=_env(tmp_path, ""))
    names = {path.name for path, _label, _mode in config.sensitive_paths(tmp_path / ".env")}
    assert {".env", "x.db", "x.db-wal", "x.db-shm", "b", "l", "d"} <= names
