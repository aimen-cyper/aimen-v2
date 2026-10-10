"""
اختبارات المهام الدورية (JobQueue) بلا مؤقتات حقيقية.

نستدعي دوال المهام مباشرة بسياق مزيّف — فنختبر المنطق والأثر في قاعدة
البيانات دون انتظار ثوانٍ، ودون أي اتصال بتيليجرام.
"""

from __future__ import annotations

import pytest

from core.enums import OrderStatus, PaymentStatus
from database.models import Service, User
from database.repositories import Repositories
from jobs import run_startup_recovery
from jobs.maintenance_jobs import auto_close_tickets, expire_old_payments
from jobs.notification_jobs import dispatch_notifications
from jobs.order_jobs import check_active_orders, submit_pending_orders
from jobs.telegram_sender import TelegramNotificationSender
from services import ServiceContainer
from tests.telegram_fakes import FakeBot, FakeContext

pytestmark = pytest.mark.asyncio


@pytest.fixture
def bot() -> FakeBot:
    """بوت مزيّف لتسجيل ما كان سيُرسل."""
    return FakeBot()


@pytest.fixture
def job_context(bot: FakeBot, services: ServiceContainer) -> FakeContext:
    """سياق مزيّف يحمل الخدمات كما تفعل JobQueue في التشغيل."""
    return FakeContext(bot, services)


async def test_dispatch_notifications_sends_and_marks(
    bot: FakeBot, job_context: FakeContext, services: ServiceContainer, db, user: User
) -> None:
    """مهمة الإشعارات ترسل ما في الطابور ولا تعيد إرساله في الجولة التالية."""
    async with db.transaction() as tx:
        await services.notifications.notify_user_manual(
            tx, user_id=user.id, token="job-test-1", title="عنوان", message="نص الإشعار"
        )
    assert await services.notifications.queued_count() == 1

    await dispatch_notifications(job_context)

    assert len(bot.sent) == 1
    assert "نص الإشعار" in bot.last.text
    assert await services.notifications.queued_count() == 0

    bot.clear()
    await dispatch_notifications(job_context)
    assert bot.sent == [], "أُعيد إرسال إشعار سبق إرساله"


async def test_blocked_user_notification_is_not_retried(
    bot: FakeBot, job_context: FakeContext, services: ServiceContainer, db, repos: Repositories, user: User
) -> None:
    """حظر المستخدم للبوت يُسجَّل ولا يبقى الإشعار يدور في الطابور إلى الأبد."""
    from telegram.error import Forbidden

    async def blocked_send(*_args, **_kwargs):
        """محاكاة رفض تيليجرام الإرسال لأن المستخدم حظر البوت."""
        raise Forbidden("bot was blocked by the user")

    bot.send_message = blocked_send                      # type: ignore[method-assign]

    async with db.transaction() as tx:
        await services.notifications.notify_user_manual(
            tx, user_id=user.id, token="job-blocked", title="عنوان", message="نص"
        )

    await dispatch_notifications(job_context)

    refreshed = await repos.users.get_by_id(user.id)
    assert refreshed.blocked_bot == 1
    assert await services.notifications.queued_count() == 0


async def test_order_jobs_complete_cycle(
    bot: FakeBot,
    job_context: FakeContext,
    services: ServiceContainer,
    user: User,
    admin: User,
    mock_service: Service,
    mock_client,
) -> None:
    """مهمة الإرسال ثم مهمة الفحص تنقلان الطلب إلى حالته النهائية تلقائياً."""
    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/job", quantity=1000
    )

    await submit_pending_orders(job_context)
    after_submit = await services.orders.get_for_user(user, order.id)
    assert after_submit.status in {OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS}

    mock_client.force_complete = True
    for _ in range(3):
        await check_active_orders(job_context)
        current = await services.orders.get_for_user(user, order.id)
        if current.status in {OrderStatus.COMPLETED, OrderStatus.PARTIAL}:
            break
        # تقديم موعد الفحص التالي يدوياً بدل انتظار الفاصل الزمني الحقيقي
        async with services.db.transaction() as tx:
            await tx.execute(
                "UPDATE orders SET next_check_at = ? WHERE id = ?",
                ("2020-01-01T00:00:00+00:00", order.id),
            )

    final = await services.orders.get_for_user(user, order.id)
    assert final.status == OrderStatus.COMPLETED


async def test_expire_old_payments_marks_expired(
    bot: FakeBot,
    job_context: FakeContext,
    services: ServiceContainer,
    db,
    repos: Repositories,
    user: User,
    payment_method,
) -> None:
    """طلب شحن تجاوز مهلته يُعلَّم منتهياً ويُشعر صاحبه (ولا يُضاف أي رصيد)."""
    payment = await services.payments.create_payment(
        user, method_id=payment_method.id, raw_amount="10", transaction_reference="TRX-EXP-1"
    )
    async with db.transaction() as tx:
        await tx.execute(
            "UPDATE payments SET expires_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", payment.id),
        )

    await expire_old_payments(job_context)

    refreshed = await services.payments.get_for_user(user, payment.id)
    assert refreshed.status == PaymentStatus.EXPIRED
    assert await services.wallet.balance_units(user.id) == 0


async def test_auto_close_tickets_job_runs(
    job_context: FakeContext, services: ServiceContainer, user: User
) -> None:
    """مهمة إغلاق التذاكر الراكدة تعمل بلا أخطاء ولا تغلق تذكرة حديثة."""
    ticket = await services.tickets.create_ticket(
        user, subject="سؤال", message="متى يصل الطلب؟", category="other"
    )
    await auto_close_tickets(job_context)
    still_open = await services.tickets.get_for_user(user, ticket.id)
    assert still_open.status != "closed"


async def test_startup_recovery_handles_stuck_submitting(
    services: ServiceContainer,
    db,
    repos: Repositories,
    user: User,
    admin: User,
    mock_service: Service,
) -> None:
    """طلب عالق في «جاري الإرسال» وقت الإغلاق يُنقل إلى حالة مراجعة لا إلى إرسال ثانٍ."""
    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/stuck", quantity=1000
    )
    async with db.transaction() as tx:
        await tx.execute(
            "UPDATE orders SET status = ?, locked_by = ?, locked_until = ? WHERE id = ?",
            (OrderStatus.SUBMITTING, "dead-worker", "2020-01-01T00:00:00+00:00", order.id),
        )

    result = await run_startup_recovery(services)

    refreshed = await repos.orders.get(order.id)
    assert refreshed.status == OrderStatus.SUBMIT_UNCERTAIN
    assert sum(result.values()) >= 1


async def test_telegram_sender_escapes_html(bot: FakeBot) -> None:
    """المرسل يهرّب وسوم HTML فلا يكسر التنسيق ولا يحقن وسوماً."""
    sender = TelegramNotificationSender(bot)
    await sender(123, "<b>عنوان", "نص فيه <script>alert(1)</script>")
    assert "&lt;script&gt;" in bot.last.text
    assert "<b>&lt;b&gt;عنوان</b>" in bot.last.text


async def test_alert_stuck_orders_notifies_admin(
    job_context: FakeContext,
    services: ServiceContainer,
    db,
    repos: Repositories,
    user: User,
    admin: User,
    mock_service: Service,
) -> None:
    """طلب متوقف منذ وقت طويل يُنتج تنبيهاً للأدمن مرة واحدة لا عند كل جولة."""
    from jobs.order_jobs import alert_stuck_orders

    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/old", quantity=1000
    )
    async with db.transaction() as tx:
        await tx.execute(
            "UPDATE orders SET created_at = ?, updated_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00", order.id),
        )

    await alert_stuck_orders(job_context)
    first = await services.notifications.queued_count()

    await alert_stuck_orders(job_context)
    second = await services.notifications.queued_count()

    assert first >= 1, "لم يُنبَّه الأدمن بطلب متوقف"
    assert second == first, "تكرر التنبيه نفسه في الجولة الثانية"


async def test_schedule_jobs_registers_all_periodic_jobs(services: ServiceContainer) -> None:
    """الجدولة تضع كل المهام الدورية على JobQueue بأسمائها وفتراتها."""
    from telegram.ext import ApplicationBuilder

    from jobs import schedule_jobs

    application = ApplicationBuilder().token("123456789:AAJobsTestDummyTokenNotUsedAtAll").build()
    try:
        names = await schedule_jobs(application, services)
        scheduled = {job.name for job in application.job_queue.jobs()}
        assert scheduled == {
            "notifications_dispatch",
            "broadcast_dispatch",       # المرحلة 8
            "orders_submit",
            "orders_check",
            "orders_refresh_messages",  # v1.3.1: تحديث رسائل الطلبات
            "payments_expire",
            "tickets_auto_close",
            "orders_stuck_alert",
            "providers_balance",        # المرحلة 6
            "providers_health",         # المرحلة 6
            "admin_daily_digest",       # المرحلة 6 (يومية)
            "database_maintenance",     # المرحلة 6 (يومية)
            "backups_auto",             # المرحلة 10
        }
        assert len(names) == len(scheduled)
    finally:
        await application.shutdown()
