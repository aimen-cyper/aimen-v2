"""المرحلة 12.1 — سباقات الحالة: الإذاعة وآخر super admin وحدود المحادثة."""

from __future__ import annotations

import asyncio

import pytest

from core.enums import BroadcastStatus
from database.models import User
from services import ServiceContainer
from tests.integration.test_user_interface import bot, context  # noqa: F401

pytestmark = pytest.mark.asyncio


async def _audience(services: ServiceContainer, count: int = 3) -> None:
    """مستخدمون عاديون كجمهور للإذاعة."""
    async with services.db.transaction() as tx:
        for index in range(count):
            await services.repos.users.create(
                tx, telegram_id=8100 + index, username=f"r{index}", first_name="مستخدم", role="user"
            )


class _Sender:
    """مرسل يسجّل المستلمين."""

    def __init__(self) -> None:
        self.ids: list[int] = []

    async def __call__(self, telegram_id: int, text: str, media_file_id, media_type) -> int:
        self.ids.append(telegram_id)
        return len(self.ids)


# --------------------------------- الإذاعة --------------------------------- #


async def test_set_status_is_conditional_on_previous_state(services: ServiceContainer, super_admin: User) -> None:
    """`set_status(expected_statuses=…)` لا يغيّر شيئاً إن كانت الحالة الحالية غير متوقعة."""
    await _audience(services)
    broadcast = await services.broadcasts.create(super_admin, text="نص", target="all")
    await services.broadcasts.cancel(super_admin, broadcast.id)

    async with services.db.transaction() as tx:
        changed = await services.repos.broadcasts.set_status(
            tx, broadcast.id, BroadcastStatus.RUNNING,
            expected_statuses=(BroadcastStatus.DRAFT, BroadcastStatus.PAUSED),
        )
    assert changed is False
    assert (await services.repos.broadcasts.get(broadcast.id)).status == BroadcastStatus.CANCELLED


async def test_complete_never_overwrites_a_concurrent_cancel(services: ServiceContainer, super_admin: User) -> None:
    """إلغاء حدث بين قراءة الإكمال وكتابته: يبقى الإلغاء ولا إشعار «اكتملت»."""
    await _audience(services, 1)
    broadcast = await services.broadcasts.create(super_admin, text="نص", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)

    original_get = services.repos.broadcasts.get
    stale = await original_get(broadcast.id)                         # لقطة «تعمل» قديمة

    calls = {"n": 0}

    async def stale_get(broadcast_id: int):
        calls["n"] += 1
        if calls["n"] == 1:
            await services.broadcasts.cancel(super_admin, broadcast_id)   # الإلغاء يقع بعد القراءة
            return stale
        return await original_get(broadcast_id)

    services.repos.broadcasts.get = stale_get                        # type: ignore[method-assign]
    try:
        await services.broadcasts._complete(broadcast.id)
    finally:
        services.repos.broadcasts.get = original_get                 # type: ignore[method-assign]

    assert (await original_get(broadcast.id)).status == BroadcastStatus.CANCELLED
    done = await services.db.fetchall("SELECT 1 FROM notifications WHERE dedupe_key LIKE ?", (f"%broadcast:{broadcast.id}:done%",))
    assert not done


async def test_concurrent_start_and_cancel_end_consistent(services: ServiceContainer, super_admin: User) -> None:
    """بدء وإلغاء متزامنان: إن نجح الإلغاء فالحالة النهائية cancelled دائماً (لا تعود running)."""
    await _audience(services)
    broadcast = await services.broadcasts.create(super_admin, text="نص", target="all")
    results = await asyncio.gather(
        services.broadcasts.start(super_admin, broadcast.id),
        services.broadcasts.cancel(super_admin, broadcast.id),
        return_exceptions=True,
    )
    final = (await services.repos.broadcasts.get(broadcast.id)).status
    if results[1] is True:
        assert final == BroadcastStatus.CANCELLED
    else:
        assert final == BroadcastStatus.RUNNING
    sender = _Sender()
    if final == BroadcastStatus.CANCELLED:
        assert (await services.broadcasts.send_batch(sender)).claimed == 0 and not sender.ids


# ------------------------------- آخر super admin ------------------------------- #


async def test_two_super_admins_cannot_demote_each_other_concurrently(services: ServiceContainer) -> None:
    """أدمنان أعلى يخفّض كلٌّ منهما الآخر معاً: ينجح واحد فقط ويبقى أدمن أعلى فعّال واحد على الأقل."""
    from core.exceptions import PermissionDeniedError

    async with services.db.transaction() as tx:
        first = await services.repos.users.create(tx, telegram_id=9101, username="s1", first_name="أ", role="super_admin")
        second = await services.repos.users.create(tx, telegram_id=9102, username="s2", first_name="ب", role="super_admin")

    results = await asyncio.gather(
        services.auth.set_role(first, second.id, "user"),
        services.auth.set_role(second, first.id, "user"),
        return_exceptions=True,
    )
    assert sum(r is True for r in results) == 1, results
    assert sum(isinstance(r, PermissionDeniedError) for r in results) == 1, results
    remaining = await services.db.fetchval("SELECT COUNT(*) FROM users WHERE role = 'super_admin' AND is_banned = 0")
    assert remaining == 1
    events = await services.repos.audit.count_by_action_prefix("security.last_super_admin_protected")
    assert events == 1, "الحدث الأمني يُسجَّل رغم رفض العملية"


# ------------------------ حد المعدل قبل القاعدة + ذاكرة الحارس ------------------------ #


async def test_flood_is_cut_before_any_database_read(bot, context, services, super_admin) -> None:  # noqa: F811
    """سيل تحديثات من معرّف واحد: `get_or_create` لا يجري أكثر من الحد المسبق، والباقي يُقطع في الذاكرة."""
    from middlewares.context import UserContextMiddleware
    from middlewares.rate_limit import AbuseGuard, RateLimiter
    from tests.integration.test_security_phase9 import Clock, _tap

    await services.settings.set("rate_limit_actions_per_minute", "3", admin_id=super_admin.id)
    await services.settings.set("rate_limit_admin_actions_per_minute", "10", admin_id=super_admin.id)
    clock = Clock()
    middleware = UserContextMiddleware(RateLimiter(clock=clock), AbuseGuard(clock=clock))

    calls = {"n": 0}
    original = services.users.get_or_create

    async def counting(**kwargs):
        calls["n"] += 1
        return await original(**kwargs)

    services.users.get_or_create = counting                         # type: ignore[method-assign]
    try:
        results = [await _tap(middleware, bot, context, user_id=616_161) for _ in range(40)]
    finally:
        services.users.get_or_create = original                     # type: ignore[method-assign]

    assert results[:3] == [True, True, True] and not any(results[3:])
    assert calls["n"] <= 10, f"قراءات القاعدة تجاوزت الحد المسبق: {calls['n']}"


def test_abuse_guard_memory_is_bounded_and_keeps_blocked(monkeypatch) -> None:
    """سيل معرّفات مختلفة لا يضخّم ذاكرة الحارس، والموقوف لا يُسقَط من السجل."""
    import middlewares.rate_limit as rl

    monkeypatch.setattr(rl, "MAX_GUARD_ENTRIES", 50)

    class _Clock:
        now = 1000.0

        def __call__(self) -> float:
            return self.now

    clock = _Clock()
    guard = rl.AbuseGuard(clock=clock)
    assert guard.record_violation(1, strikes_limit=1, block_seconds=10_000).blocked
    for telegram_id in range(100, 2_000):
        clock.now += 0.01
        guard.record_violation(telegram_id, strikes_limit=5, block_seconds=60)

    assert len(guard._strikes) <= 51
    assert guard.is_blocked(1), "المُوقَف أُسقط من الذاكرة بسبب السيل"


async def test_broadcast_rate_setting_paces_sending(services: ServiceContainer, super_admin: User) -> None:
    """`broadcast_rate_per_second` يضبط الفاصل بين الرسائل فعلاً (5/ث ⇒ ≥ 0.2ث بين رسالتين)."""
    import time

    await services.settings.set("broadcast_rate_per_second", "5", admin_id=super_admin.id)
    await _audience(services, 4)
    broadcast = await services.broadcasts.create(super_admin, text="نص", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)

    stamps: list[float] = []

    async def sender(telegram_id: int, text: str, media_file_id, media_type) -> int:
        stamps.append(time.monotonic())
        return 1

    report = await services.broadcasts.send_batch(sender, limit=10)
    assert report.sent == len(stamps) >= 4
    gaps = [later - earlier for earlier, later in zip(stamps, stamps[1:])]
    assert all(gap >= 0.18 for gap in gaps), gaps


# ------------------------------- قناة تنبيهات الأدمن (#17) ------------------------------- #


async def _notify(services: ServiceContainer, token: str) -> int:
    """إدراج تنبيه أدمن عبر الخدمة (كما تفعل الخدمات الأخرى)."""
    from core.permissions import Permission

    async with services.db.transaction() as tx:
        return await services.notifications.notify_admins(
            tx, permission=Permission.ORDERS_VIEW, token=token, title="تنبيه تجريبي", message="نص التنبيه"
        )


async def test_alert_channel_receives_copy_from_env_or_setting(services: ServiceContainer, admin: User, super_admin: User) -> None:
    """نسخة التنبيه تصل لقناة التنبيهات: الإعداد أولاً وإلا متغير البيئة، ولا تُكرَّر لكل أدمن."""
    sent: list[tuple[int, str, str]] = []

    async def sender(chat_id: int, title: str, message: str) -> int:
        sent.append((chat_id, title, message))
        return 1

    services.channels.alert_chat_fallback = -100111
    assert await _notify(services, "alert:1") >= 2                 # أدمنان على الأقل
    report = await services.channels.flush(sender)
    assert report.sent == 1
    assert sent == [(-100111, "تنبيه تجريبي", "نص التنبيه")]

    await services.settings.set("admin_alert_chat_id", "-100222333", admin_id=super_admin.id)
    await _notify(services, "alert:2")
    await services.channels.flush(sender)
    assert sent[-1][0] == -100222333, "الإعداد يتقدم على متغير البيئة"

    # تنبيه مكرر (نفس token) لا يُنسخ مرة ثانية
    assert await _notify(services, "alert:2") == 0
    assert (await services.channels.flush(sender)).claimed == 0


async def test_alert_channel_unset_skips_and_failures_do_not_raise(services: ServiceContainer, admin: User) -> None:
    """بلا قناة: لا تراكم (skipped). وفشل الإرسال المؤقت يُعاد لاحقاً ولا يُسقط المهمة."""
    from core.exceptions import NotificationTemporaryError

    await _notify(services, "alert:3")
    report = await services.channels.flush(_never_called)
    assert (report.claimed, report.skipped, report.sent) == (1, 1, 0)
    assert (await services.repos.channel_outbox.count_by_status()).get("skipped") == 1

    async def failing(chat_id: int, title: str, message: str) -> int:
        raise NotificationTemporaryError("شبكة")

    services.channels.alert_chat_fallback = -100999
    await _notify(services, "alert:4")
    report = await services.channels.flush(failing)
    assert (report.sent, report.retried) == (0, 1)
    assert (await services.repos.channel_outbox.count_by_status()).get("queued") == 1, "يبقى في الصندوق للمحاولة التالية"


async def _never_called(chat_id: int, title: str, message: str) -> int:
    raise AssertionError("لا قناة مضبوطة ⇒ لا إرسال")
