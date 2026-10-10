"""
المرحلة 13 — البنود 12 و13 و7(جزء /start): الأدمن الأعلى من البيئة، تعارض getUpdates، خادم الصحة، رسالة /start.
"""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import pytest
from telegram.error import Conflict, NetworkError
from telegram.ext import Application

import main as app_main
from config import Config
from handlers.common import errors, navigation
from services import ServiceContainer
from tests.integration.test_user_interface import bot, context, load_user, run_middleware  # noqa: F401
from tests.telegram_fakes import make_message_update
from utils.conflict_guard import ConflictGuard
from utils.health_server import HealthServer

pytestmark = pytest.mark.asyncio


# --------------------------------- البند 12: الأدمن الأعلى من البيئة --------------------------------- #


async def test_bootstrap_creates_promotes_and_unbans_then_is_idempotent(services: ServiceContainer, repos, user) -> None:
    """إنشاء حساب جديد، ترقية مستخدم قائم، رفع حظر — ومرة ثانية لا يكتب شيئاً."""
    async with repos.db.transaction() as tx:
        await repos.users.set_ban(tx, user.id, banned=True, reason="خطأ")
    outcomes = await services.auth.bootstrap_super_admins((user.telegram_id, 4_040_404_040))
    assert {item.telegram_id: item.action for item in outcomes} == {
        user.telegram_id: "promoted_unbanned",
        4_040_404_040: "created",
    }
    promoted = await services.users.get(user.id)
    assert promoted.role == "super_admin" and not promoted.is_banned
    created = await services.users.get_by_telegram(4_040_404_040)
    assert created.role == "super_admin"

    audits_before = await repos.db.fetchval("SELECT COUNT(*) FROM audit_logs WHERE action = 'system.bootstrap_super_admin'")
    assert audits_before == 2
    again = await services.auth.bootstrap_super_admins((user.telegram_id, 4_040_404_040))
    assert [item.action for item in again] == ["unchanged", "unchanged"]
    assert await repos.db.fetchval("SELECT COUNT(*) FROM audit_logs WHERE action = 'system.bootstrap_super_admin'") == audits_before


async def test_bootstrap_uses_env_ids_by_default(services: ServiceContainer, repos) -> None:
    """بلا وسيط: يستعمل `SUPER_ADMIN_IDS` المحقونة في الخدمة (كما يفعل main.post_init)."""
    services.auth.super_admin_ids = (6_060_606_060,)
    outcomes = await services.auth.bootstrap_super_admins()
    assert [item.action for item in outcomes] == ["created"]
    assert (await services.users.get_by_telegram(6_060_606_060)).role == "super_admin"


async def test_middleware_heals_demoted_env_super_admin_instantly(bot, context, services, repos, super_admin) -> None:  # noqa: F811
    """أدمن أعلى من البيئة فقد دوره أو حُظر خطأً: أول تحديث منه يُصلح الحساب ويدخل اللوحة."""
    services.auth.super_admin_ids = (super_admin.telegram_id,)
    async with repos.db.transaction() as tx:
        await repos.users.set_role(tx, super_admin.id, "user")
        await repos.users.set_ban(tx, super_admin.id, banned=True, reason="خطأ")
    update = make_message_update(bot, text="/start", user_id=super_admin.telegram_id)
    assert await run_middleware(bot, context, update)
    healed = await services.users.get(super_admin.id)
    assert healed.role == "super_admin" and not healed.is_banned
    assert await services.auth.is_admin(healed)


async def test_env_super_admin_enters_even_when_registration_is_closed(bot, context, services) -> None:  # noqa: F811
    """إغلاق التسجيل لا يقفل المالك خارج بوته (أول دخول له يُنشئ حسابه)، ويبقى المستخدم العادي مرفوضاً."""
    services.auth.super_admin_ids = (7_070_707_070,)
    await services.settings.set("registration_enabled", "false", admin_id=None)
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=7_070_707_070))
    assert (await services.users.get_by_telegram(7_070_707_070)).role == "super_admin"
    bot.clear()
    assert not await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=8_080_808_080))


async def test_non_env_user_never_becomes_super_admin(bot, context, services, user) -> None:  # noqa: F811
    """من ليس في البيئة لا يترقّى بأي مسار."""
    services.auth.super_admin_ids = (1,)
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=user.telegram_id))
    assert (await services.users.get(user.id)).role == "user"


def test_super_admin_ids_parsing_is_forgiving(monkeypatch, tmp_path) -> None:
    """الصيغ الشائعة عند اللصق في Render: أقواس، علامات اقتباس، مسافات، فاصلة عربية."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "d" / "t.db"))
    for raw in ('123456789,987654321', '[123456789, 987654321]', '"123456789" ، "987654321"', "123456789 987654321", "123456789;987654321"):
        monkeypatch.setenv("SUPER_ADMIN_IDS", raw)
        assert Config.load(env_file=tmp_path / "none.env").super_admin_ids == (123456789, 987654321), raw
    monkeypatch.setenv("SUPER_ADMIN_IDS", "123,abc")
    from config import ConfigError

    with pytest.raises(ConfigError):
        Config.load(env_file=tmp_path / "none.env")


async def test_init_db_seed_uses_same_service(db, repos) -> None:
    """`scripts.init_db.seed_super_admins` يمر من نفس الخدمة (مصدر واحد) وidempotent."""
    from scripts.init_db import seed_super_admins

    first = await seed_super_admins(db, (9_090_909_090,))
    second = await seed_super_admins(db, (9_090_909_090,))
    assert "أُنشئ" in first[0] and "بالفعل" in second[0]


# ------------------------------------ البند 13: Conflict ------------------------------------ #


class _Clock:
    """ساعة يدوية لاختبار نوافذ الزمن."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _guard(stops: list[int]) -> tuple[ConflictGuard, _Clock]:
    clock = _Clock()
    return ConflictGuard(lambda: stops.append(1), clock=clock), clock


def test_transient_conflict_does_not_stop_the_bot() -> None:
    """تعارض عابر (نشر Render متداخل) يزول خلال أقل من دقيقة ⇒ لا إيقاف."""
    stops: list[int] = []
    guard, clock = _guard(stops)
    for _ in range(8):
        guard.on_polling_error(Conflict("terminated by other getUpdates request"))
        clock.now += 4
    assert not stops and not guard.tripped


def test_persistent_conflict_stops_once_with_clear_reason(caplog) -> None:
    """تعارض مستمر ≥ 60ث و≥ 5 أحداث ⇒ إيقاف آمن مرة واحدة فقط وسجل CRITICAL يشرح الحل."""
    stops: list[int] = []
    guard, clock = _guard(stops)
    with caplog.at_level("WARNING"):
        for _ in range(20):
            guard.on_polling_error(Conflict("terminated by other getUpdates request"))
            clock.now += 10
    assert guard.tripped and stops == [1]
    assert any("نفس التوكن" in record.getMessage() and record.levelname == "CRITICAL" for record in caplog.records)


def test_conflict_that_stops_for_a_while_is_forgotten() -> None:
    """تعارضات متباعدة جداً (أقدم من النافذة) لا تتجمع لتصبح «مستمرة»."""
    stops: list[int] = []
    guard, clock = _guard(stops)
    for _ in range(4):
        guard.on_polling_error(Conflict("x"))
        clock.now += 1
    clock.now += 600
    for _ in range(4):
        guard.on_polling_error(Conflict("x"))
        clock.now += 1
    assert not stops and guard.recent_conflicts == 4


def test_other_errors_are_logged_without_token_and_never_stop(caplog) -> None:
    """أخطاء الشبكة العادية لا توقف شيئاً، ونص الخطأ يُنقّى من التوكن."""
    from utils.security import register_secret

    token = "123456789:AAConflictGuardSecretToken0123456789"
    register_secret(token)
    stops: list[int] = []
    guard, _ = _guard(stops)
    with caplog.at_level("WARNING"):
        for _ in range(50):
            guard.on_polling_error(NetworkError(f"boom https://api.telegram.org/bot{token}/getUpdates"))
    assert not stops and not guard.tripped
    assert token not in " ".join(record.getMessage() for record in caplog.records)


def test_main_returns_distinct_exit_code_on_persistent_conflict(monkeypatch, tmp_path, capsys) -> None:
    """main(): تعارض مستمر ⇒ رمز خروج 3 ورسالة عربية واضحة (لا 0 ولا 1)."""
    token = "123456789:AAConflictExitCodeToken0123456789012"
    monkeypatch.setenv("BOT_TOKEN", token)
    monkeypatch.setenv("SUPER_ADMIN_IDS", "111222333")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "t.db"))
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "logs" / "bot.log"))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(app_main, "setup_logging", lambda *a, **k: None)

    class _App:
        def __init__(self) -> None:
            self.bot_data: dict = {}
            self.stopped = False

        def stop_running(self) -> None:
            self.stopped = True

        def run_polling(self, **kwargs) -> None:
            # v1.3.1: توقيع PTB الحقيقي (لا error_callback)؛ الأخطاء تصل عبر معالج الأخطاء العام (update=None)
            inspect.signature(Application.run_polling).bind(None, **kwargs)
            clock_value = [0.0]
            guard = self.bot_data["conflict_guard"]
            guard._clock = lambda: clock_value[0]
            context = SimpleNamespace(
                error=Conflict("terminated by other getUpdates request"), application=self
            )
            for _ in range(10):
                asyncio.run(errors.error_handler(None, context))
                clock_value[0] += 10

    app = _App()
    monkeypatch.setattr(app_main, "build_application", lambda config: app)
    assert app_main.main() == 3
    assert app.stopped
    assert "نفس التوكن" in capsys.readouterr().err


async def test_health_server_responds_and_hides_secrets() -> None:
    """GET /health ⇒ 200 JSON بلا أسرار؛ مسار آخر 404؛ POST 405؛ والاتصال يُغلق."""
    server = HealthServer(0, lambda: {"status": "ok", "version": "x"}, host="127.0.0.1")
    port = await server.start()
    try:
        async def request(raw: bytes) -> bytes:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(raw)
            await writer.drain()
            data = await asyncio.wait_for(reader.read(), 5)
            writer.close()
            return data

        ok = await request(b"GET /health HTTP/1.1\r\nHost: x\r\n\r\n")
        assert ok.startswith(b"HTTP/1.1 200") and b'"status": "ok"' in ok
        assert (await request(b"GET /healthz HTTP/1.1\r\n\r\n")).startswith(b"HTTP/1.1 200")
        assert (await request(b"GET /admin HTTP/1.1\r\n\r\n")).startswith(b"HTTP/1.1 404")
        assert (await request(b"POST / HTTP/1.1\r\n\r\n")).startswith(b"HTTP/1.1 405")
        assert (await request(b"garbage\r\n\r\n")).startswith(b"HTTP/1.1 400")
    finally:
        await server.stop()


def test_config_reads_port_for_health_and_rejects_bad_port(monkeypatch, tmp_path) -> None:
    """PORT اختياري: غائب ⇒ لا خادم صحة، صحيح ⇒ يُقرأ، خارج المدى ⇒ خطأ إعداد واضح."""
    from config import ConfigError

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "d" / "t.db"))
    monkeypatch.delenv("PORT", raising=False)
    assert Config.load(env_file=tmp_path / "none.env").health_port is None
    monkeypatch.setenv("PORT", "10000")
    assert Config.load(env_file=tmp_path / "none.env").health_port == 10000
    monkeypatch.setenv("PORT", "70000")
    with pytest.raises(ConfigError):
        Config.load(env_file=tmp_path / "none.env")


# ------------------------------------ البند 7: /start ------------------------------------ #


async def test_start_sends_one_message_and_cleans_previous_menu(bot, context, services, user) -> None:  # noqa: F811
    """/start: رسالة واحدة (ترحيب + قائمة)، تُحذف رسالة الأمر نفسها والقائمة السابقة بدل تراكم الرسائل."""
    first = make_message_update(bot, text="/start", user_id=50_010)
    assert await run_middleware(bot, context, first)
    await navigation.start_command(first, context)
    assert len(bot.sent) == 1 and "رصيدك" in bot.sent[0].text and "أهلاً" in bot.sent[0].text
    assert "ابدأ في ثلاث خطوات" in bot.sent[0].text, "الجديد يرى توجيهاً واضحاً"
    assert (50_010, first.message.message_id) in bot.deleted
    menu_id = context.user_data["menu_msg_id"]

    second = make_message_update(bot, text="/start", user_id=50_010)
    assert await run_middleware(bot, context, second)
    await navigation.start_command(second, context)
    assert len(bot.sent) == 2, "رسالة واحدة جديدة فقط لكل /start"
    assert (50_010, menu_id) in bot.deleted, "القائمة السابقة حُذفت"
    assert "ابدأ بخطوتين" not in bot.sent[1].text, "العائد لا يكرَّر عليه الإرشاد"


# ======================= تنظيف الطابور وترتيب except ======================= #


async def test_maintenance_cleans_only_old_final_channel_posts(bot, services, repos, db) -> None:  # noqa: F811
    """الصيانة تحذف منشورات القنوات المنتهية القديمة فقط؛ المعلّق والحديث يبقيان."""
    from jobs.maintenance_jobs import database_maintenance
    from tests.telegram_fakes import FakeContext
    from utils.datetime_utils import iso_minus_days

    async with db.transaction() as tx:
        ids = {}
        for key, status, age in (("old-sent", "sent", 45), ("old-queued", "queued", 45), ("new-sent", "sent", 1)):
            ids[key] = await repos.channel_outbox.enqueue(tx, kind="orders_log", title="t", message="m", dedupe_key=key)
            await tx.execute(
                "UPDATE channel_outbox SET status=?, created_at=? WHERE id=?", (status, iso_minus_days(age), ids[key])
            )

    result = await database_maintenance(FakeContext(bot, services))
    assert result["channel_posts_removed"] == 1
    remaining = {r["dedupe_key"] for r in await db.fetchall("SELECT dedupe_key FROM channel_outbox")}
    assert remaining == {"old-queued", "new-sent"}


async def test_sender_classifies_badrequest_as_permanent_and_timeout_as_temporary() -> None:
    """BadRequest فرع من NetworkError في PTB: يجب أن يبقى دائماً لا مؤقتاً (ترتيب except)."""
    from telegram.error import BadRequest, TimedOut

    from core.exceptions import NotificationPermanentError, NotificationTemporaryError
    from jobs.telegram_sender import TelegramNotificationSender

    class _Bot:
        def __init__(self, error: Exception) -> None:
            self.error = error

        async def send_message(self, **_kwargs):
            raise self.error

    with pytest.raises(NotificationPermanentError):
        await TelegramNotificationSender(_Bot(BadRequest("Can't parse entities")))(1, "t", "m")
    with pytest.raises(NotificationTemporaryError):
        await TelegramNotificationSender(_Bot(TimedOut("timeout")))(1, "t", "m")
