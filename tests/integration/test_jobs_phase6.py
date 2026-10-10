"""
اختبارات المرحلة 6: الإشراف على المهام، الفحص الجماعي، مراقبة المزودين،
الملخص اليومي، صيانة القاعدة، وشاشة «⏱ المهام الدورية».

كل الاختبارات تستدعي المهام مباشرة بسياق مزيّف — بلا مؤقتات حقيقية وبلا شبكة.
"""

from __future__ import annotations

import asyncio

import pytest

from core.enums import OrderStatus
from database.models import Service, User
from database.repositories import Repositories
from handlers.admin import dashboard, system as admin_system
from jobs.maintenance_jobs import database_maintenance
from jobs.order_jobs import check_active_orders
from jobs.provider_jobs import refresh_provider_balances, watch_provider_health
from jobs.report_jobs import send_admin_daily_digest
from jobs.runner import JOB_REGISTRY, JobRegistry, supervise
from keyboards.callback_data import pack
from services import ServiceContainer
from tests.integration.test_user_interface import (
    bot,  # noqa: F401
    context,  # noqa: F401
    load_user,
    press,
)
from tests.telegram_fakes import FakeBot, FakeContext
from utils.datetime_utils import iso_plus_seconds, utc_now_iso

pytestmark = pytest.mark.asyncio


@pytest.fixture
def job_context(bot: FakeBot, services: ServiceContainer) -> FakeContext:
    """سياق مزيّف يحمل الخدمات كما تفعل JobQueue في التشغيل الحقيقي."""
    return FakeContext(bot, services)


@pytest.fixture
def clean_registry():
    """سجل المهام العام يُفرَّغ قبل كل اختبار يعتمد عليه وبعده."""
    JOB_REGISTRY.clear()
    yield JOB_REGISTRY
    JOB_REGISTRY.clear()


async def _credit(services: ServiceContainer, user: User, admin: User, units: int = 100_000) -> None:
    """شحن رصيد اختباري عبر الخدمة المركزية الوحيدة المسؤولة عن المال."""
    await services.wallet.adjust_balance(
        target=user, amount_units=units, admin=admin, reason="رصيد اختبار", credit=True
    )


async def _place_order(services: ServiceContainer, user: User, service: Service, link_suffix: str):
    """إنشاء طلب جاهز للإرسال (أداة مشتركة بين الاختبارات)."""
    return await services.orders.create_order(
        user,
        service_id=service.id,
        link=f"https://instagram.com/{link_suffix}",
        quantity=1_000,
    )


# ======================================================================== #
#                        1) الإشراف على المهام                             #
# ======================================================================== #


async def test_supervisor_records_successful_run(job_context: FakeContext) -> None:
    """الجولة الناجحة تُحدِّث العدّادات وتترك المهمة سليمة."""
    registry = JobRegistry()
    calls = []

    async def job(_context) -> None:
        """مهمة اختبارية ناجحة."""
        calls.append(1)

    runner = supervise(job, name="demo_ok", registry=registry, interval_seconds=30)
    await runner(job_context)

    stats = registry.get("demo_ok")
    assert calls == [1]
    assert stats.runs == 1
    assert stats.failures == 0
    assert stats.is_healthy
    assert stats.last_success_at is not None
    assert stats.last_duration_ms is not None


async def test_supervisor_swallows_error_and_logs_it(
    job_context: FakeContext, services: ServiceContainer, repos: Repositories
) -> None:
    """استثناء داخل المهمة لا يُسقط المهمة الدورية ويُكتب في `error_logs`."""
    registry = JobRegistry()
    before = await repos.error_logs.count_since(utc_now_iso()[:10])

    async def failing(_context) -> None:
        """مهمة اختبارية تفشل دائماً."""
        raise RuntimeError("انفجار اختباري")

    runner = supervise(failing, name="demo_fail", registry=registry, interval_seconds=30)
    await runner(job_context)                       # لا يرفع استثناءً

    stats = registry.get("demo_fail")
    assert stats.failures == 1
    assert stats.consecutive_failures == 1
    assert not stats.is_healthy
    assert "انفجار اختباري" in stats.last_error

    errors = await services.audit.recent_errors(limit=10)
    assert any("demo_fail" in str(row.get("source")) for row in errors)
    assert await repos.error_logs.count_since(utc_now_iso()[:10]) > before


async def test_supervisor_alerts_admin_after_threshold(
    job_context: FakeContext, services: ServiceContainer, admin: User
) -> None:
    """بعد بلوغ حد الإخفاقات المتتالية يصل تنبيه للأدمن (مرة واحدة لكل عدد)."""

    async def failing(_context) -> None:
        """مهمة تفشل دائماً لاختبار التنبيه."""
        raise RuntimeError("فشل متكرر")

    registry = JobRegistry()
    runner = supervise(
        failing,
        name="demo_alert",
        registry=registry,
        interval_seconds=30,
        failure_alert_threshold=2,
    )

    await runner(job_context)
    assert await services.notifications.queued_count() == 0      # أول فشل: لا تنبيه

    await runner(job_context)
    assert await services.notifications.queued_count() >= 1      # بلغ الحد ⇒ تنبيه

    notifications = await services.repos.notifications.list_for_user(admin.id, limit=5)
    assert any("مهمة دورية" in (item.title or "") for item in notifications)


async def test_supervisor_skips_overlapping_round(job_context: FakeContext) -> None:
    """جولة جديدة لا تبدأ فوق جولة لم تنتهِ — تُحتسب «تخطّياً» لا فشلاً."""
    registry = JobRegistry()
    release = asyncio.Event()
    entered = asyncio.Event()

    async def slow(_context) -> None:
        """مهمة بطيئة تبقى عاملة حتى نحرّرها."""
        entered.set()
        await release.wait()

    runner = supervise(slow, name="demo_slow", registry=registry, interval_seconds=5)
    first = asyncio.create_task(runner(job_context))
    await entered.wait()

    await runner(job_context)                        # الجولة الثانية أثناء الأولى
    stats = registry.get("demo_slow")
    assert stats.skipped == 1
    assert stats.runs == 0                           # الأولى لم تنتهِ بعد

    release.set()
    await first
    assert registry.get("demo_slow").runs == 1


async def test_supervisor_timeout_counts_as_failure(job_context: FakeContext) -> None:
    """الجولة التي تتجاوز المهلة تُلغى وتُسجَّل كفشل بدل أن تُعلَّق للأبد."""
    registry = JobRegistry()

    async def hanging(_context) -> None:
        """مهمة لا تنتهي أبداً."""
        await asyncio.sleep(30)

    runner = supervise(
        hanging, name="demo_timeout", registry=registry, interval_seconds=5, timeout_seconds=0.05
    )
    await runner(job_context)

    stats = registry.get("demo_timeout")
    assert stats.failures == 1
    assert not stats.is_healthy


# ======================================================================== #
#                   2) الفحص الجماعي لحالات الطلبات                        #
# ======================================================================== #


async def test_check_round_uses_single_multi_status_call(
    job_context: FakeContext,
    services: ServiceContainer,
    repos: Repositories,
    user: User,
    admin: User,
    mock_service: Service,
    mock_client,
    db,
) -> None:
    """ثلاثة طلبات لمزود واحد ⇒ استعلام جماعي واحد لا ثلاثة استعلامات."""
    await _credit(services, user, admin)
    user = await repos.users.get_by_id(user.id)

    for index in range(3):
        await _place_order(services, user, mock_service, f"user{index}")
    await services.orders.process_pending_orders(limit=5)

    async with db.transaction() as tx:
        await tx.execute(
            "UPDATE orders SET next_check_at = ? WHERE status IN ('submitted','in_progress')",
            (iso_plus_seconds(-60),),
        )

    await check_active_orders(job_context)

    rows = await db.fetchall(
        "SELECT request_summary FROM provider_requests WHERE request_summary LIKE 'multi-status%'"
    )
    assert len(rows) == 1, "كان يجب استعلام جماعي واحد لكل مزود في الجولة"
    assert "count=3" in rows[0]["request_summary"]


async def test_check_round_falls_back_for_unanswered_order(
    job_context: FakeContext,
    services: ServiceContainer,
    repos: Repositories,
    user: User,
    admin: User,
    mock_service: Service,
    mock_client,
    db,
) -> None:
    """الطلب الذي لم يُجب عنه الاستعلام الجماعي يُفحص فردياً ولا يُهمَل."""
    await _credit(services, user, admin)
    user = await repos.users.get_by_id(user.id)

    for index in range(2):
        await _place_order(services, user, mock_service, f"partial{index}")
    await services.orders.process_pending_orders(limit=5)

    original_multi = mock_client.get_multi_status

    async def partial_multi(provider_order_ids):
        """ردّ ناقص: يُجيب عن أول طلب فقط كما تفعل بعض اللوحات."""
        answers = await original_multi(provider_order_ids[:1])
        return answers

    mock_client.get_multi_status = partial_multi            # type: ignore[method-assign]
    mock_client.calls.clear()

    async with db.transaction() as tx:
        await tx.execute(
            "UPDATE orders SET next_check_at = ? WHERE status IN ('submitted','in_progress')",
            (iso_plus_seconds(-60),),
        )
    report = await services.orders.process_due_orders(limit=10)

    assert report.claimed == 2
    single_calls = [call for call in mock_client.calls if call[0] == "status"]
    assert single_calls, "لم يُفحص الطلب الناقص فردياً"


async def test_batch_failure_releases_orders_without_losing_them(
    job_context: FakeContext,
    services: ServiceContainer,
    repos: Repositories,
    user: User,
    admin: User,
    mock_service: Service,
    mock_client,
    db,
) -> None:
    """فشل الاستعلام الجماعي يؤجل الطلبات بتدرج ولا يغيّر حالتها ولا يفقدها."""
    from core.exceptions import ProviderTemporaryError

    await _credit(services, user, admin)
    user = await repos.users.get_by_id(user.id)

    for index in range(2):
        await _place_order(services, user, mock_service, f"down{index}")
    await services.orders.process_pending_orders(limit=5)

    async def broken_multi(_ids):
        """محاكاة انقطاع المزود أثناء الاستعلام الجماعي."""
        raise ProviderTemporaryError("انقطاع مؤقت")

    mock_client.get_multi_status = broken_multi             # type: ignore[method-assign]

    async with db.transaction() as tx:
        await tx.execute(
            "UPDATE orders SET next_check_at = ? WHERE status IN ('submitted','in_progress')",
            (iso_plus_seconds(-60),),
        )
    report = await services.orders.process_due_orders(limit=10)

    assert report.claimed == 2
    assert report.unchanged == 2
    orders = await repos.orders.list_by_statuses(
        [OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS]
    )
    assert len(orders) == 2
    assert all(order.locked_by is None for order in orders), "بقيت الطلبات محجوزة بعد الفشل"


# ======================================================================== #
#                      3) مهام مراقبة المزودين                             #
# ======================================================================== #


async def test_balance_job_updates_provider_and_snapshot(
    job_context: FakeContext, repos: Repositories, mock_provider, mock_client, db
) -> None:
    """مهمة الأرصدة تحفظ الرصيد في صف المزود وتضيف لقطة تاريخية."""
    updated = await refresh_provider_balances(job_context)

    assert updated == 1
    provider = await repos.providers.get(mock_provider.id)
    assert provider.balance_units == mock_client.balance_units
    assert provider.balance_checked_at is not None

    snapshots = await db.fetchall(
        "SELECT * FROM provider_balance_snapshots WHERE provider_id = ?", (mock_provider.id,)
    )
    assert len(snapshots) == 1


async def test_balance_job_alerts_admin_on_low_balance(
    job_context: FakeContext,
    services: ServiceContainer,
    repos: Repositories,
    mock_provider,
    mock_client,
    admin: User,
    db,
) -> None:
    """الرصيد تحت الحد ⇒ تنبيه للأدمن (ولا يتكرر لنفس القيمة)."""
    async with db.transaction() as tx:
        await repos.providers.update_fields(
            tx, mock_provider.id, low_balance_threshold_units=mock_client.balance_units + 1
        )

    await refresh_provider_balances(job_context)
    first = await services.notifications.queued_count()
    await refresh_provider_balances(job_context)
    second = await services.notifications.queued_count()

    assert first >= 1, "لم يصل تنبيه انخفاض الرصيد"
    assert second == first, "تكرر التنبيه نفسه في الجولة الثانية"


async def test_health_watch_recovers_provider(
    job_context: FakeContext,
    services: ServiceContainer,
    repos: Repositories,
    mock_provider,
    mock_client,
    admin: User,
    db,
) -> None:
    """مزود متعثر انتهت مدة إيقافه وعاد يستجيب ⇒ تصفير العداد + إشعار تعافٍ."""
    async with db.transaction() as tx:
        for _ in range(3):
            await repos.providers.record_failure(tx, mock_provider.id, "مهلة")
        await repos.providers.update_fields(
            tx, mock_provider.id, disabled_until=iso_plus_seconds(-60)
        )

    recovered = await watch_provider_health(job_context)

    assert recovered == 1
    provider = await repos.providers.get(mock_provider.id)
    assert provider.consecutive_failures == 0
    assert provider.disabled_until is None

    notifications = await services.repos.notifications.list_for_user(admin.id, limit=5)
    assert any("تعافى" in (item.title or "") for item in notifications)


async def test_health_watch_skips_provider_still_disabled(
    job_context: FakeContext, repos: Repositories, mock_provider, mock_client, db
) -> None:
    """المزود الموقوف مؤقتاً لا يُختبر قبل انتهاء مدته — نحترم فترة التهدئة."""
    async with db.transaction() as tx:
        await repos.providers.record_failure(tx, mock_provider.id, "مهلة")
        await repos.providers.update_fields(
            tx, mock_provider.id, disabled_until=iso_plus_seconds(600)
        )

    recovered = await watch_provider_health(job_context)

    assert recovered == 0
    provider = await repos.providers.get(mock_provider.id)
    assert provider.consecutive_failures == 1


# ======================================================================== #
#                   4) الملخص اليومي وصيانة القاعدة                        #
# ======================================================================== #


async def test_daily_digest_is_queued_once_per_day(
    job_context: FakeContext, services: ServiceContainer, admin: User
) -> None:
    """الملخص اليومي يُدرج مرة واحدة لليوم نفسه مهما تكرر استدعاء المهمة."""
    assert await send_admin_daily_digest(job_context) is True
    assert await send_admin_daily_digest(job_context) is False

    notifications = await services.repos.notifications.list_for_user(admin.id, limit=5)
    assert any("الملخص اليومي" in (item.title or "") for item in notifications)


async def test_database_maintenance_removes_only_expired_keys(
    job_context: FakeContext, services: ServiceContainer, repos: Repositories, user: User, db
) -> None:
    """الصيانة تحذف مفاتيح منع التكرار المنتهية فقط — ولا تمسّ البيانات التاريخية."""
    async with db.transaction() as tx:
        await repos.idempotency.try_acquire(tx, "fresh-key", scope="test", ttl_seconds=3600)
        await repos.idempotency.try_acquire(tx, "old-key", scope="test", ttl_seconds=3600)
        await tx.execute(
            "UPDATE idempotency_keys SET expires_at = ? WHERE key = 'old-key'",
            (iso_plus_seconds(-60),),
        )

    users_before = await repos.users.count_all()
    result = await database_maintenance(job_context)

    assert result["idempotency_keys_removed"] == 1
    assert await repos.idempotency.exists("fresh-key") is True
    assert await repos.idempotency.exists("old-key") is False
    assert await repos.users.count_all() == users_before


# ======================================================================== #
#                      5) شاشة «⏱ المهام الدورية»                          #
# ======================================================================== #


def _register_demo_jobs(registry) -> None:
    """تسجيل مهمتين في السجل العام: واحدة سليمة وواحدة متعثرة (للعرض)."""
    healthy = registry.register(
        "orders_check", interval_seconds=120, schedule_text="كل 2 دقيقة"
    )
    healthy.runs = 5
    healthy.last_finished_at = utc_now_iso()
    healthy.last_duration_ms = 320
    healthy.total_duration_ms = 1_600
    healthy.last_success_at = utc_now_iso()

    failing = registry.register(
        "providers_balance", interval_seconds=1800, schedule_text="كل 30 دقيقة"
    )
    failing.runs = 2
    failing.failures = 2
    failing.consecutive_failures = 2
    failing.last_error = "انقطاع الاتصال بالمزود"
    failing.last_finished_at = utc_now_iso()
    failing.last_duration_ms = 980
    failing.total_duration_ms = 1_900


async def test_jobs_screen_shows_state_of_each_job(
    bot: FakeBot, context: FakeContext, admin: User, clean_registry
) -> None:
    """شاشة المهام تعرض كل مهمة بحالتها وآخر خطأ للمتعثرة."""
    _register_demo_jobs(clean_registry)
    await load_user(bot, context, admin)
    await press(bot, context, admin_system.jobs_screen, pack("adm", "jobs"), admin.telegram_id)

    text = bot.last.text
    assert "متابعة حالة الطلبات" in text
    assert "أرصدة المزودين" in text
    assert "انقطاع الاتصال بالمزود" in text
    assert "🔴" in text and "🟢" in text
    assert any(data.startswith("adm:jobrun:") for data in bot.last.buttons)


async def test_jobs_screen_without_maintenance_has_no_run_buttons(
    bot: FakeBot, context: FakeContext, user: User, super_admin: User, clean_registry, services
) -> None:
    """من يرى الإحصائيات بلا صلاحية الصيانة يقرأ الحالة ولا يملك «تشغيل الآن»."""
    _register_demo_jobs(clean_registry)
    for permission in ("admin.access", "stats.view"):
        await services.auth.set_user_permission(super_admin, user.id, permission, allow=True)
    await load_user(bot, context, user)
    await press(bot, context, admin_system.jobs_screen, pack("adm", "jobs"), user.telegram_id)

    assert "المهام الدورية" in bot.last.text
    assert not any(data.startswith("adm:jobrun:") for data in bot.last.buttons)


async def test_run_job_now_executes_and_reports(
    bot: FakeBot, context: FakeContext, super_admin: User, clean_registry, services
) -> None:
    """زر «تشغيل الآن» ينفّذ المهمة فوراً ويعرض نتيجتها."""
    calls: list[int] = []

    async def job(_context) -> None:
        """مهمة اختبارية تُسجّل استدعاءها."""
        calls.append(1)

    supervise(job, name="orders_check", registry=clean_registry, interval_seconds=120)
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        admin_system.run_job_now,
        pack("adm", "jobrun", "orders_check"),
        super_admin.telegram_id,
    )

    assert calls == [1]
    texts = " ".join(message.text or "" for message in bot.sent)
    assert "✅" in texts
    assert clean_registry.get("orders_check").runs == 1


async def test_run_job_now_reports_failure_without_crashing(
    bot: FakeBot, context: FakeContext, super_admin: User, clean_registry
) -> None:
    """فشل المهمة المُشغَّلة يدوياً يُعرض للأدمن ولا يُسقط المعالج."""

    async def failing(_context) -> None:
        """مهمة اختبارية تفشل."""
        raise RuntimeError("خطأ يدوي")

    supervise(failing, name="orders_check", registry=clean_registry, interval_seconds=120)
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        admin_system.run_job_now,
        pack("adm", "jobrun", "orders_check"),
        super_admin.telegram_id,
    )

    texts = " ".join(message.text or "" for message in bot.sent)
    assert "❌" in texts
    assert "خطأ يدوي" in texts


async def test_run_job_now_blocked_for_plain_admin(
    bot: FakeBot, context: FakeContext, admin: User, clean_registry
) -> None:
    """دور `admin` بلا `settings.maintenance`؟ يُحجب التشغيل اليدوي."""
    calls: list[int] = []

    async def job(_context) -> None:
        """مهمة لا يجب أن تعمل في هذا الاختبار."""
        calls.append(1)

    supervise(job, name="orders_check", registry=clean_registry, interval_seconds=120)
    await load_user(bot, context, admin)
    has_maintenance = await context.application.bot_data["services"].auth.has_permission(
        admin, "settings.maintenance"
    )

    await press(
        bot,
        context,
        admin_system.run_job_now,
        pack("adm", "jobrun", "orders_check"),
        admin.telegram_id,
    )

    assert calls == ([1] if has_maintenance else [])


async def test_run_unknown_job_is_rejected(
    bot: FakeBot, context: FakeContext, super_admin: User, clean_registry
) -> None:
    """طلب تشغيل مهمة غير مجدولة يُرفض برسالة واضحة بلا انهيار."""
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        admin_system.run_job_now,
        pack("adm", "jobrun", "no_such_job"),
        super_admin.telegram_id,
    )

    assert bot.answers, "لم يصل أي ردّ على الزر"
    assert "غير مجدولة" in bot.answers[-1]["text"]


async def test_health_screen_includes_jobs_summary(
    bot: FakeBot, context: FakeContext, admin: User, clean_registry
) -> None:
    """شاشة صحة النظام تلخّص حالة المهام وتعرض زر الدخول لشاشتها."""
    _register_demo_jobs(clean_registry)
    await load_user(bot, context, admin)
    await press(bot, context, dashboard.health_screen, pack("adm", "health"), admin.telegram_id)

    assert "المهام:" in bot.last.text
    assert "adm:jobs:v1" in bot.last.buttons
