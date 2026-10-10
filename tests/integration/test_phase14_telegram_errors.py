"""
المرحلة الثانية (v1.0.1) — بند 20: Telegram Timeout/ConnectError دون انهيار أو فقد أو تكرار أو حالة غامضة،
مع التمييز الصارم بين الخطأ الخارجي (شبكة/تيليجرام) والداخلي (كود).

كل شيء هنا بلا شبكة: أعطال تيليجرام تُبرمَج في FakeBot بنفس أنواع استثناءات PTB الحقيقية.
"""

from __future__ import annotations

import pytest
from telegram.error import BadRequest, Conflict, Forbidden, InvalidToken, NetworkError, RetryAfter, TimedOut

import main as app_main
from core.enums import OrderStatus
from handlers.common import errors, ui
from jobs.telegram_sender import TelegramNotificationSender
from tests.integration.test_user_interface import bot, context, load_user  # noqa: F401,F811
from tests.telegram_fakes import make_callback_update, make_message_update
from texts import ar
from utils import telegram_retry
from utils.telegram_retry import TelegramHealth, call_telegram, classify, delivery_is_impossible

pytestmark = pytest.mark.asyncio

READ = "Timed out"                                             # نص PTB لمهلة القراءة/الكتابة (وصول الطلب غير مؤكد)


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    """إلغاء تأخيرات إعادة المحاولة كي لا ينتظر الاختبار."""
    monkeypatch.setattr(telegram_retry, "RETRY_DELAYS", (0.0, 0.0))


# ------------------------------- التصنيف -------------------------------- #


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (TimedOut("Timed out"), "external"), (TimedOut("Pool timeout: all connections are busy"), "external"),
        (NetworkError("httpx.ConnectError: All connection attempts failed"), "external"),
        (RetryAfter(3), "external"), (Conflict("terminated by other getUpdates request"), "external"),
        (Forbidden("bot was blocked by the user"), "user_side"),
        (BadRequest("Message is not modified: specified new message content..."), "benign"),
        (BadRequest("Query is too old and response timeout expired or query id is invalid"), "benign"),
        (BadRequest("Can't parse entities: unsupported start tag"), "internal"),
        (BadRequest("Button_data_invalid"), "internal"),
        (RuntimeError("bug"), "internal"), (KeyError("x"), "internal"), (None, "internal"),
    ],
)
async def test_classify_separates_external_from_internal(error, kind) -> None:
    """خطأ الشبكة/تيليجرام خارجي، وBadRequest الحقيقي والاستثناءات البرمجية داخلية (لا تُخفى تحت «انقطاع»)."""
    assert classify(error) == kind


@pytest.mark.parametrize(
    ("error", "impossible"),
    [
        (TimedOut("Pool timeout: all connections are busy"), True), (TimedOut("Connect timeout"), True),
        (NetworkError("httpx.ConnectError: All connection attempts failed"), True), (RetryAfter(2), True),
        (TimedOut("Timed out"), False), (TimedOut("Read timeout"), False), (TimedOut("Write timeout"), False),
        (NetworkError("httpx.ReadError: connection reset"), False), (BadRequest("x"), False),
    ],
)
async def test_delivery_is_impossible_only_when_request_never_reached_telegram(error, impossible) -> None:
    """إعادة الإرسال آمنة فقط حين يستحيل أن يكون الطلب وصل (اتصال/تجمّع) — وإلا خطر تكرار الرسالة."""
    assert delivery_is_impossible(error) is impossible


# --------------------------- إعادة المحاولة المحكومة --------------------------- #


def _flaky(errors_list, result="ok"):
    """مصنع نداء يفشل بالأخطاء المعطاة بالترتيب ثم ينجح؛ يعدّ المحاولات."""
    state = {"calls": 0}

    async def factory():
        state["calls"] += 1
        if state["calls"] <= len(errors_list):
            raise errors_list[state["calls"] - 1]
        return result

    return factory, state


async def test_idempotent_call_retries_on_timeout_then_succeeds() -> None:
    """تحرير/إجابة (متساوي الأثر): مهلتان ثم نجاح ⇒ ثلاث محاولات ونتيجة سليمة."""
    factory, state = _flaky([TimedOut(READ), NetworkError("httpx.ReadError")])
    assert await call_telegram(factory, what="تحرير", idempotent=True) == "ok" and state["calls"] == 3


async def test_non_idempotent_send_is_not_retried_after_uncertain_timeout() -> None:
    """إرسال رسالة + مهلة قراءة (قد تكون وصلت) ⇒ لا إعادة إطلاقاً (منعاً للتكرار) والخطأ يُرفع."""
    factory, state = _flaky([TimedOut(READ)])
    with pytest.raises(TimedOut):
        await call_telegram(factory, what="إرسال", idempotent=False)
    assert state["calls"] == 1


async def test_non_idempotent_send_retries_when_connection_never_established() -> None:
    """إرسال + ConnectError (لم يصل شيء) ⇒ إعادة آمنة تنجح."""
    factory, state = _flaky([NetworkError("httpx.ConnectError: boom"), TimedOut("Pool timeout")])
    assert await call_telegram(factory, what="إرسال", idempotent=False) == "ok" and state["calls"] == 3


async def test_exhausted_retries_raise_last_error_and_real_errors_are_immediate() -> None:
    """استنفاد المحاولات يرفع آخر خطأ؛ وBadRequest/Forbidden تُرفع فوراً دون إعادة."""
    factory, state = _flaky([TimedOut(READ)] * 5)
    with pytest.raises(TimedOut):
        await call_telegram(factory, what="تحرير", idempotent=True)
    assert state["calls"] == 3                                            # المحاولة الأولى + تأخيران
    for error in (BadRequest("Can't parse entities"), Forbidden("blocked")):
        factory, state = _flaky([error])
        with pytest.raises(type(error)):
            await call_telegram(factory, what="x", idempotent=True)
        assert state["calls"] == 1


async def test_retry_after_is_honoured_when_short_and_raised_when_long() -> None:
    """RetryAfter قصير ⇒ ينتظر ويعيد؛ طويل (> 5ث) ⇒ يُرفع ليتولاه المتصل بدل تجميد المعالج."""
    factory, state = _flaky([RetryAfter(0)])
    assert await call_telegram(factory, what="x", idempotent=False) == "ok" and state["calls"] == 2
    factory, state = _flaky([RetryAfter(60)])
    with pytest.raises(RetryAfter):
        await call_telegram(factory, what="x", idempotent=True)
    assert state["calls"] == 1


# ------------------------------- عدّاد الانقطاع ------------------------------- #


async def test_telegram_health_window_and_threshold() -> None:
    """عشرة أعطال في نافذة 5 دقائق ⇒ انقطاع؛ والأحداث الأقدم من النافذة تسقط."""
    now = [0.0]
    health = TelegramHealth(clock=lambda: now[0])
    for _ in range(9):
        health.record_external()
    assert not health.outage and health.recent == 9
    health.record_external()
    assert health.outage
    now[0] = 301.0
    assert health.recent == 0 and not health.outage and health.total_external == 10


# ------------------------------ المعالج العام للأخطاء ------------------------------ #


async def _log_rows(db, **where):
    """صفوف error_logs بحسب المصدر."""
    return await db.fetchall("SELECT * FROM error_logs WHERE source = ?", (where["source"],))


async def test_external_failures_are_throttled_and_never_look_like_code_errors(bot, context, services, db, user, super_admin) -> None:  # noqa: F811
    """15 مهلة متتالية: صف WARNING واحد فقط، لا صف ERROR، تنبيه أدمن واحد، ورسالة «حاول لاحقاً» للمستخدم."""
    await load_user(bot, context, user)
    for index in range(15):
        context.error = TimedOut(READ) if index % 2 else NetworkError("httpx.ConnectError: down")
        update = make_message_update(bot, text="شيء", user_id=user.telegram_id)
        await errors.error_handler(update, context)                          # لا استثناء يتسرّب
    rows = await _log_rows(db, source="telegram_network")
    assert len(rows) == 1 and rows[0]["level"] == "WARNING"
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM error_logs WHERE level = 'ERROR'"))["n"] == 0
    alerts = await db.fetchall("SELECT * FROM notifications WHERE title LIKE '%غير مستقر%'")
    assert len(alerts) >= 1 and len({a["dedupe_key"] for a in alerts}) == 1
    assert all("خارجي" in a["message"] for a in alerts)
    assert sum(ar.ERR_TELEGRAM_TEMP in m.text for m in bot.sent) == 15


async def test_below_threshold_failures_do_not_alert_admins(bot, context, services, db, user, super_admin) -> None:  # noqa: F811
    """تسعة أعطال (دون العتبة) ⇒ لا تنبيه للأدمن."""
    await load_user(bot, context, user)
    for _ in range(9):
        context.error = TimedOut(READ)
        await errors.error_handler(make_message_update(bot, text="x", user_id=user.telegram_id), context)
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM notifications WHERE title LIKE '%غير مستقر%'"))["n"] == 0


async def test_internal_error_is_logged_as_error_and_alerts_admins_but_bad_request_noise_is_quiet(bot, context, services, db, user, super_admin) -> None:  # noqa: F811
    """RuntimeError/BadRequest الحقيقي ⇒ ERROR + تنبيه؛ «message is not modified» ⇒ صمت؛ Forbidden ⇒ علامة حظر فقط."""
    await load_user(bot, context, user)
    update = make_message_update(bot, text="x", user_id=user.telegram_id)

    context.error = BadRequest("Message is not modified: same content")
    await errors.error_handler(update, context)
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM error_logs"))["n"] == 0

    context.error = Forbidden("bot was blocked by the user")
    await errors.error_handler(update, context)
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM error_logs"))["n"] == 0
    assert (await services.repos.users.get_by_id(user.id)).blocked_bot

    context.error = BadRequest("Can't parse entities: unsupported start tag")
    await errors.error_handler(update, context)
    rows = await db.fetchall("SELECT * FROM error_logs")
    assert len(rows) == 1 and rows[0]["level"] == "ERROR" and rows[0]["error_type"] == "BadRequest"
    assert any(ar.ERR_GENERIC in m.text for m in bot.sent)


async def test_error_handler_survives_failures_while_notifying_the_user(bot, context, services, db, user) -> None:  # noqa: F811
    """حتى لو تعطّل إرسال رسالة الاعتذار نفسها (تيليجرام لا يزال معطلاً) لا ينهار المعالج ولا يتولد خطأ جديد."""
    await load_user(bot, context, user)
    bot.fail("send", NetworkError("httpx.ConnectError: down"), times=10)
    context.error = TimedOut(READ)
    await errors.error_handler(make_message_update(bot, text="x", user_id=user.telegram_id), context)
    context.error = RuntimeError("bug")
    await errors.error_handler(make_message_update(bot, text="x", user_id=user.telegram_id), context)
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM error_logs WHERE level = 'ERROR'"))["n"] == 1


# ----------------------------- مسار الواجهة (ui.py) ----------------------------- #


async def test_ui_edit_retries_after_timeout_and_applies_exactly_once(bot, context, user) -> None:  # noqa: F811
    """تحرير بمهلة قراءة (قد يكون طُبّق) ثم نجاح ⇒ النص النهائي مرة واحدة بلا رسائل مكررة."""
    await load_user(bot, context, user)
    update = make_callback_update(bot, data="noop", user_id=user.telegram_id)
    bot.clear()
    bot.fail("edit", TimedOut(READ), times=1, delivered=True)
    await ui.render(update, context, "النص النهائي", None)
    assert bot.attempts["edit"] == 2
    assert [m.text for m in bot.sent].count("النص النهائي") == 2             # أثر المحاولة الأولى + الإعادة (تحرير بنفس النص)
    assert not any(m.kind == "send" for m in bot.sent)                         # لا رسالة جديدة مكررة


async def test_ui_send_never_duplicates_on_uncertain_timeout_but_retries_on_connect_error(bot, context, user) -> None:  # noqa: F811
    """send: مهلة غير مؤكدة ⇒ محاولة واحدة ويعود None بلا استثناء (لا تكرار)؛ ConnectError ثم نجاح ⇒ رسالة واحدة."""
    await load_user(bot, context, user)
    update = make_message_update(bot, text="x", user_id=user.telegram_id)
    bot.clear()
    bot.attempts.clear()
    bot.fail("send", TimedOut(READ), times=1, delivered=True)
    assert await ui.send(update, context, "رسالة 1") is None                 # العطل الخارجي لا يُسقط المعالج
    assert bot.attempts["send"] == 1 and [m.text for m in bot.sent] == ["رسالة 1"]

    bot.clear()
    bot.attempts.clear()
    bot.fail("send", NetworkError("httpx.ConnectError: down"), times=2, delivered=False)
    await ui.send(update, context, "رسالة 2")
    assert bot.attempts["send"] == 3 and [m.text for m in bot.sent] == ["رسالة 2"]


# ------------------------- الإشعارات: لا فقد عند أعطال تيليجرام ------------------------- #


async def test_notification_survives_telegram_outage_and_is_delivered_after_recovery(bot, services, db, user) -> None:  # noqa: F811
    """إشعار طلب + ConnectError ⇒ يبقى queued بعدّاد محاولات (لا يضيع) ثم يُرسل عند عودة الاتصال مرة واحدة."""
    async with db.transaction() as tx:
        await services.notifications.enqueue(tx, user_id=user.id, type="system", title="تم", message="طلبك جاهز", dedupe_key="t14:ok")
    sender = TelegramNotificationSender(bot)
    bot.fail("send", NetworkError("httpx.ConnectError: down"), times=1)
    first = await services.notifications.dispatch_pending(sender)
    assert (first.sent, first.failed) == (0, 1)
    row = await db.fetchone("SELECT status, attempts, last_error FROM notifications WHERE dedupe_key = 't14:ok'")
    assert row["status"] == "queued" and row["attempts"] == 1 and row["last_error"]

    async with db.transaction() as tx:
        await tx.execute("UPDATE notifications SET next_attempt_at = NULL")
    second = await services.notifications.dispatch_pending(sender)
    assert second.sent == 1
    assert [m.text for m in bot.sent if "طلبك جاهز" in m.text].__len__() == 1
    assert (await db.fetchone("SELECT status FROM notifications WHERE dedupe_key = 't14:ok'"))["status"] == "sent"
    third = await services.notifications.dispatch_pending(sender)
    assert third.claimed == 0                                                  # لا تكرار بعد النجاح


async def test_order_state_and_balance_are_unaffected_by_telegram_failures(bot, context, services, repos, db, user, super_admin, mock_service, mock_client) -> None:  # noqa: F811
    """عطل Telegram أثناء إنشاء الطلب/إشعاره لا يمس الرصيد ولا الحالة (الحفظ سابق لأي إرسال)."""
    await services.wallet.adjust_balance(target=user, amount_units=100_000, admin=super_admin, reason="رصيد", credit=True)
    order = await services.orders.create_order(user, service_id=mock_service.id, link="https://instagram.com/p/tg", quantity=1000)
    bot.fail("send", NetworkError("httpx.ConnectError: down"), times=5)
    report = await services.notifications.dispatch_pending(TelegramNotificationSender(bot))
    assert report.sent == 0
    await services.orders.process_pending_orders()
    stored = await repos.orders.get(order.id)
    assert stored.status in (OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS, OrderStatus.COMPLETED)
    assert await services.wallet.balance_units(user.id) == 90_000
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


# ---------------------------------- الإقلاع ---------------------------------- #


async def test_best_effort_startup_call_survives_outage_but_not_real_errors(monkeypatch) -> None:
    """أثناء الإقلاع: انقطاع مؤقت ⇒ None والبوت يُكمل؛ BadRequest/InvalidToken ⇒ تُرفع (خطأ حقيقي)."""
    monkeypatch.setattr(app_main, "STARTUP_RETRY_DELAYS", (0.0, 0.0, 0.0))

    async def always_timeout():
        raise TimedOut("Timed out")

    assert await app_main._best_effort_telegram(always_timeout, what="x") is None

    for error in (BadRequest("Wrong command"), InvalidToken("bad token")):
        async def broken(error=error):
            raise error

        with pytest.raises(type(error)):
            await app_main._best_effort_telegram(broken, what="x")

    calls = {"n": 0}

    async def recovers():
        calls["n"] += 1
        if calls["n"] < 3:
            raise NetworkError("httpx.ConnectError: down")
        return "me"

    assert await app_main._best_effort_telegram(recovers, what="x") == "me" and calls["n"] == 3
