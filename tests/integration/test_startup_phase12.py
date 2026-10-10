"""
المرحلة 12 — فشل الإقلاع لا يسرّب أسراراً ويخرج برمز فشل ويحرّر القفل.

اكتُشف عند أول تشغيل حقيقي لـ`main.py` على تثبيت نظيف بتوكن مرفوض: استثناء `InvalidToken` يحمل
التوكن كاملاً في نصه وكان يُطبع كتتبّع خام في الطرفية/journald، بينما ملف اللوق نظيف.
"""

from __future__ import annotations

import inspect

import pytest
from telegram.error import InvalidToken, NetworkError
from telegram.ext import Application

import main as app_main
from utils.logging_setup import RedactingFormatter
from utils.security import clear_registered_secrets

TOKEN = "123456789:AAStartupLeakTestTokenDoNotUse0123456789"


class _FakeApp:
    """تطبيق مزيّف: `run_polling` يرفع الاستثناء المطلوب كما يفعل عند فشل الإقلاع الحقيقي."""

    def __init__(self, error: BaseException) -> None:
        """تخزين الاستثناء الذي سيُرفع."""
        self.error = error
        self.bot_data: dict = {}

    def stop_running(self) -> None:
        """إيقاف آمن (يستدعيه ConflictGuard) — لا شيء يعمل فعلاً هنا."""

    def run_polling(self, **kwargs: object) -> None:
        """محاكاة فشل الإقلاع (بتوقيع PTB الحقيقي: كلمة غير مدعومة ⇒ TypeError كما في الإنتاج)."""
        inspect.signature(Application.run_polling).bind(None, **kwargs)
        raise self.error


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """بيئة تشغيل معزولة: مسارات مؤقتة وتوكن اختباري، وبلا ملف .env حقيقي."""
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.setenv("SUPER_ADMIN_IDS", "111222333")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "t.db"))
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "logs" / "bot.log"))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(app_main, "setup_logging", lambda *a, **k: None)   # لا نلمس إعداد اللوق العام
    yield tmp_path
    clear_registered_secrets()


@pytest.mark.parametrize(
    "error",
    [
        InvalidToken(f"The token `{TOKEN}` was rejected by the server."),
        NetworkError(f"httpx.ConnectError: https://api.telegram.org/bot{TOKEN}/getMe"),
        RuntimeError(f"boom with {TOKEN}"),
    ],
    ids=["invalid-token", "network", "unexpected"],
)
def test_startup_failure_exits_1_without_leaking_token(isolated_env, monkeypatch, capsys, caplog, error) -> None:
    """أي فشل إقلاع ⇒ رمز 1، لا توكن في الطرفية ولا في السجلات، والقفل يُحرَّر (يمكن إعادة التشغيل)."""
    monkeypatch.setattr(app_main, "build_application", lambda config: _FakeApp(error))
    with caplog.at_level("DEBUG"):
        code = app_main.main()
    assert code == 1
    captured = capsys.readouterr()
    assert "❌" in captured.err
    assert TOKEN not in captured.err and TOKEN not in captured.out
    rendered = "\n".join(RedactingFormatter("%(message)s").format(record) for record in caplog.records)
    assert TOKEN not in rendered, "التوكن ظهر في السجلات بعد التنقية"
    # القفل محرَّر: التشغيل التالي لا يفشل بـ«نسخة تعمل بالفعل»
    monkeypatch.setattr(app_main, "build_application", lambda config: _FakeApp(KeyboardInterrupt()))
    assert app_main.main() == 0


def test_clean_shutdown_returns_zero(isolated_env, monkeypatch) -> None:
    """إيقاف المشغّل (Ctrl+C) ⇒ رمز 0."""
    monkeypatch.setattr(app_main, "build_application", lambda config: _FakeApp(KeyboardInterrupt()))
    assert app_main.main() == 0


def test_second_instance_is_refused_with_code_2(isolated_env, monkeypatch, capsys) -> None:
    """نسخة ثانية أثناء عمل الأولى ⇒ رمز 2 ورسالة واضحة (حماية R9)."""
    from config import Config
    from utils.single_instance import SingleInstance

    config = Config.load(require_bot_token=True)
    holder = SingleInstance(config.data_dir / "bot.lock")
    holder.acquire()
    try:
        monkeypatch.setattr(app_main, "build_application", lambda c: _FakeApp(KeyboardInterrupt()))
        assert app_main.main() == 2
        assert "❌" in capsys.readouterr().err
    finally:
        holder.release()
