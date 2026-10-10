"""
اختبارات خدمة الطلبات — قلب النظام.

تغطي: الإنشاء والخصم الذرّي، منع التكرار، الحدود، الإرسال للمزود،
المتابعة حتى الاكتمال، التنفيذ الجزئي، الفشل والاسترجاع، النتيجة غير المؤكدة،
إجراءات الأدمن، والاسترداد بعد إعادة التشغيل.
"""

from __future__ import annotations

import asyncio

import pytest

from core.enums import OrderStatus, TransactionType
from core.exceptions import (
    DuplicateOperationError,
    InsufficientBalanceError,
    InvalidStateTransitionError,
    PermissionDeniedError,
    ProviderPermanentError,
    ProviderTemporaryError,
    ProviderUncertainError,
    RateLimitedError,
    ValidationError,
)
from database.database import Database
from database.models import Service, User
from database.repositories import Repositories
from integrations.providers.mock import MockProviderClient
from services import ServiceContainer
from utils.datetime_utils import iso_plus_seconds

ORDER_COST = 10_000  # تكلفة طلب 1000 وحدة بسعر 10000/ألف


async def _fund(services: ServiceContainer, user: User, admin: User, amount_units: int) -> None:
    """شحن رصيد اختباري عبر المسار الرسمي للمحفظة."""
    await services.wallet.adjust_balance(
        target=user, amount_units=amount_units, admin=admin, reason="رصيد اختبار", credit=True
    )


async def _create(
    services: ServiceContainer, user: User, service: Service, *, link: str = "https://instagram.com/test", quantity: int = 1000
):
    """اختصار لإنشاء طلب."""
    return await services.orders.create_order(
        user, service_id=service.id, link=link, quantity=quantity
    )


async def _make_due(repos: Repositories, order_id: int) -> None:
    """تقديم موعد الفحص/المحاولة إلى الماضي (محاكاة مرور الوقت في الاختبار)."""
    async with repos.db.transaction() as tx:
        await repos.orders.update_fields(tx, order_id, next_check_at=iso_plus_seconds(-10))


# ============================== الإنشاء ================================= #


async def test_create_order_charges_balance_and_records_everything(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service
) -> None:
    """الإنشاء الناجح: خصم + سجل حالة + إشعار + رمز عام للطلب."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)

    assert order.status == OrderStatus.PENDING
    assert order.public_code == f"ORD-{order.id:06d}"
    assert order.cost_units == ORDER_COST
    assert await services.wallet.balance_units(user.id) == 40_000

    transactions = await repos.transactions.list_by_order(order.id)
    assert len(transactions) == 1 and transactions[0].type == TransactionType.ORDER

    history = await repos.orders.history(order.id)
    assert history[0].to_status == OrderStatus.PENDING

    inbox = await repos.notifications.list_for_user(user.id)
    assert any("order_created" == item.type for item in inbox)


async def test_create_order_without_balance_leaves_no_trace(
    services: ServiceContainer, repos: Repositories, user: User, mock_service: Service
) -> None:
    """فشل الخصم يُلغي إنشاء الطلب بالكامل (ذرّية المعاملة)."""
    with pytest.raises(InsufficientBalanceError):
        await _create(services, user, mock_service)

    assert await repos.orders.count_by_user(user.id) == 0
    assert await repos.transactions.count_by_user(user.id) == 0


async def test_same_client_request_id_returns_same_order(
    services: ServiceContainer, user: User, admin: User, mock_service: Service
) -> None:
    """الضغط المزدوج بنفس المفتاح يُعيد الطلب الأول بلا خصم جديد."""
    await _fund(services, user, admin, 50_000)
    first = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/a", quantity=1000,
        client_request_id="same-key",
    )
    second = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/a", quantity=1000,
        client_request_id="same-key",
    )

    assert first.id == second.id
    assert await services.wallet.balance_units(user.id) == 40_000


async def test_duplicate_order_window_blocks_identical_order(
    services: ServiceContainer, user: User, admin: User, mock_service: Service
) -> None:
    """طلب مطابق خلال نافذة التكرار يُرفض برسالة واضحة."""
    await _fund(services, user, admin, 50_000)
    await _create(services, user, mock_service, link="https://instagram.com/same")

    with pytest.raises(DuplicateOperationError):
        await _create(services, user, mock_service, link="https://instagram.com/same")


async def test_daily_order_limit_enforced(
    services: ServiceContainer, user: User, admin: User, mock_service: Service
) -> None:
    """الحد اليومي لعدد الطلبات مطبَّق من الإعدادات."""
    await services.settings.set("max_orders_per_day", 1)
    await _fund(services, user, admin, 50_000)
    await _create(services, user, mock_service, link="https://instagram.com/one")

    with pytest.raises(RateLimitedError):
        await _create(services, user, mock_service, link="https://instagram.com/two")


async def test_minimum_order_amount_enforced(
    services: ServiceContainer, user: User, admin: User, mock_service: Service
) -> None:
    """الحد الأدنى لقيمة الطلب يمنع الطلبات الصغيرة جداً."""
    await services.settings.set("min_order_amount_units", 20_000)
    await _fund(services, user, admin, 50_000)

    with pytest.raises(ValidationError):
        await _create(services, user, mock_service, quantity=1000)  # قيمته 10000 فقط


async def test_banned_user_cannot_order(
    services: ServiceContainer, user: User, admin: User, mock_service: Service
) -> None:
    """المستخدم المحظور لا يستطيع إنشاء طلب."""
    await _fund(services, user, admin, 50_000)
    await services.users.ban(admin, user.id, reason="مخالفة")
    banned = await services.users.get(user.id)
    assert banned is not None

    from core.exceptions import UserBannedError

    with pytest.raises(UserBannedError):
        await _create(services, user=banned, service=mock_service)


# ============================== الإرسال ================================= #


async def test_submit_pending_order_to_provider(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """الطلب المعلّق يُرسل للمزود ويحصل على رقم عنده."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)

    report = await services.orders.process_pending_orders()
    assert report.claimed == 1 and report.succeeded == 1

    submitted = await repos.orders.get(order.id)
    assert submitted is not None
    assert submitted.status == OrderStatus.SUBMITTED
    assert submitted.provider_order_id
    assert submitted.locked_by is None
    assert any(call[0] == "add" for call in mock_client.calls)


async def test_full_delivery_completes_order(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """المتابعة الدورية تنقل الطلب إلى in_progress ثم completed."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    await services.orders.process_pending_orders()

    for _ in range(4):
        await _make_due(repos, order.id)
        await services.orders.process_due_orders()
        current = await repos.orders.get(order.id)
        assert current is not None
        if current.status == OrderStatus.COMPLETED:
            break

    final = await repos.orders.get(order.id)
    assert final is not None
    assert final.status == OrderStatus.COMPLETED
    assert final.remains == 0
    assert final.completed_at is not None
    assert final.refund_amount_units == 0
    assert await services.wallet.balance_units(user.id) == 40_000


async def test_partial_delivery_triggers_partial_refund(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """التنفيذ الجزئي يسترجع قيمة الكمية غير المنفَّذة تلقائياً."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    await services.orders.process_pending_orders()

    submitted = await repos.orders.get(order.id)
    assert submitted is not None and submitted.provider_order_id
    mock_client.advance(submitted.provider_order_id, to="Partial", delivered=600)

    await _make_due(repos, order.id)
    await services.orders.process_due_orders()

    final = await repos.orders.get(order.id)
    assert final is not None
    assert final.status == OrderStatus.PARTIAL
    assert final.delivered_quantity == 600
    assert final.refund_amount_units == 4_000          # 40% من 10000
    assert await services.wallet.balance_units(user.id) == 44_000

    refunds = [
        transaction for transaction in await repos.transactions.list_by_order(order.id)
        if transaction.type == TransactionType.PARTIAL_REFUND
    ]
    assert len(refunds) == 1


async def test_provider_cancellation_refunds_fully(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """إلغاء المزود للطلب يُعيد كامل المبلغ وينقله إلى refunded."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    await services.orders.process_pending_orders()

    submitted = await repos.orders.get(order.id)
    assert submitted is not None and submitted.provider_order_id
    mock_client.advance(submitted.provider_order_id, to="Canceled")

    await _make_due(repos, order.id)
    await services.orders.process_due_orders()

    final = await repos.orders.get(order.id)
    assert final is not None
    assert final.status == OrderStatus.REFUNDED
    assert final.refund_amount_units == ORDER_COST
    assert await services.wallet.balance_units(user.id) == 50_000


# ============================== الإخفاقات =============================== #


async def test_permanent_provider_failure_refunds_and_alerts(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """رفض المزود النهائي ⇒ فشل + استرجاع كامل + إشعار المستخدم والأدمن + سجل خطأ."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    mock_client.always_fail_add = ProviderPermanentError("الخدمة غير موجودة لدى المزود")

    report = await services.orders.process_pending_orders()
    assert report.failed == 1

    final = await repos.orders.get(order.id)
    assert final is not None
    assert final.status == OrderStatus.REFUNDED
    assert final.refund_amount_units == ORDER_COST
    assert await services.wallet.balance_units(user.id) == 50_000

    user_inbox = await repos.notifications.list_for_user(user.id)
    assert any(item.type == "order_failed" for item in user_inbox)
    admin_inbox = await repos.notifications.list_for_user(admin.id)
    assert admin_inbox, "يجب تنبيه الأدمن عند فشل الطلب"

    errors = await repos.error_logs.list_recent(limit=10)
    assert any("فشل الطلب" in row["message"] for row in errors)


async def test_temporary_failure_retries_then_fails_after_max_attempts(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """الفشل المؤقت يُعيد الطلب للانتظار، وبعد استنفاد المحاولات يفشل ويُسترجع المبلغ."""
    from core.constants import MAX_SUBMIT_ATTEMPTS

    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    mock_client.always_fail_add = ProviderTemporaryError("انقطاع مؤقت")

    statuses = []
    for _ in range(MAX_SUBMIT_ATTEMPTS + 1):
        await _make_due(repos, order.id)
        await services.orders.process_pending_orders()
        current = await repos.orders.get(order.id)
        assert current is not None
        statuses.append(current.status)
        if current.status == OrderStatus.REFUNDED:
            break

    assert OrderStatus.PENDING in statuses, "يجب أن يعود الطلب للانتظار بعد الفشل المؤقت"
    final = await repos.orders.get(order.id)
    assert final is not None
    assert final.status == OrderStatus.REFUNDED
    assert final.submit_attempts >= MAX_SUBMIT_ATTEMPTS
    assert await services.wallet.balance_units(user.id) == 50_000


async def test_uncertain_result_is_never_resubmitted(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """
    النتيجة غير المؤكدة: لا استرجاع ولا إعادة إرسال — تدخّل أدمن فقط.

    هذا أخطر سيناريو: إعادة الإرسال تعني طلباً مكرراً عند المزود ومالاً مهدوراً.
    """
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    mock_client.always_fail_add = ProviderUncertainError("انتهت المهلة بعد الإرسال")

    report = await services.orders.process_pending_orders()
    assert report.uncertain == 1

    current = await repos.orders.get(order.id)
    assert current is not None
    assert current.status == OrderStatus.SUBMIT_UNCERTAIN
    assert current.refund_amount_units == 0
    assert await services.wallet.balance_units(user.id) == 40_000  # المال ما زال محجوزاً

    # جولة إرسال جديدة يجب ألا تلتقطه إطلاقاً
    calls_before = len(mock_client.calls)
    second = await services.orders.process_pending_orders()
    assert second.claimed == 0
    assert len(mock_client.calls) == calls_before

    admin_inbox = await repos.notifications.list_for_user(admin.id)
    assert admin_inbox, "يجب تنبيه الأدمن فوراً بالحالة غير المؤكدة"


async def test_unknown_provider_status_does_not_change_order(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """حالة مزود غير معروفة تُسجَّل كتحذير ولا تغيّر حالة الطلب."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    await services.orders.process_pending_orders()

    submitted = await repos.orders.get(order.id)
    assert submitted is not None and submitted.provider_order_id
    mock_client.advance(submitted.provider_order_id, to="Weird New Status")

    await _make_due(repos, order.id)
    await services.orders.process_due_orders()

    unchanged = await repos.orders.get(order.id)
    assert unchanged is not None
    assert unchanged.status == OrderStatus.SUBMITTED
    errors = await repos.error_logs.list_recent(limit=10)
    assert any("حالة مزود غير معروفة" in row["message"] for row in errors)


# ========================== إجراءات المستخدم والأدمن ===================== #


async def test_user_can_cancel_before_submission(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service
) -> None:
    """إلغاء المستخدم قبل الإرسال يعيد كامل المبلغ."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)

    refunded = await services.orders.cancel_by_user(user, order.id)
    assert refunded == ORDER_COST

    final = await repos.orders.get(order.id)
    assert final is not None and final.status == OrderStatus.REFUNDED
    assert await services.wallet.balance_units(user.id) == 50_000


async def test_user_cannot_cancel_after_submission(
    services: ServiceContainer, user: User, admin: User, mock_service: Service, mock_client: MockProviderClient
) -> None:
    """بعد الإرسال للمزود لا يملك المستخدم حق الإلغاء."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    await services.orders.process_pending_orders()

    with pytest.raises(InvalidStateTransitionError):
        await services.orders.cancel_by_user(user, order.id)


async def test_user_cannot_touch_another_users_order(
    services: ServiceContainer, db: Database, repos: Repositories, user: User, admin: User, mock_service: Service
) -> None:
    """لا يرى المستخدم طلبات غيره ولا يلغيها."""
    from core.exceptions import OrderError

    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)

    async with db.transaction() as tx:
        other = await repos.users.create(tx, telegram_id=555000111, first_name="Other")

    with pytest.raises(OrderError):
        await services.orders.get_for_user(other, order.id)
    with pytest.raises(OrderError):
        await services.orders.cancel_by_user(other, order.id)


async def test_admin_mark_failed_refunds_uncertain_order(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """تأكيد الأدمن أن الطلب لم يصل المزود ⇒ استرجاع كامل وتسجيل تدقيق."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    mock_client.always_fail_add = ProviderUncertainError("مهلة")
    await services.orders.process_pending_orders()

    refunded = await services.orders.admin_mark_failed(admin, order.id, "تأكدنا أنه لم يصل المزود")
    assert refunded == ORDER_COST

    final = await repos.orders.get(order.id)
    assert final is not None and final.status == OrderStatus.REFUNDED
    assert await services.wallet.balance_units(user.id) == 50_000

    logs = await services.audit.by_target("order", order.id)
    assert any(log.action == "orders.refund" for log in logs)


async def test_admin_link_provider_order_requires_super_admin(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, super_admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """ربط رقم المزود يدوياً صلاحية للأدمن الأعلى فقط، وينقل الطلب إلى submitted."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    mock_client.always_fail_add = ProviderUncertainError("مهلة")
    await services.orders.process_pending_orders()

    with pytest.raises(PermissionDeniedError):
        await services.orders.admin_link_provider_order(admin, order.id, "99887")

    assert await services.orders.admin_link_provider_order(super_admin, order.id, "99887")
    linked = await repos.orders.get(order.id)
    assert linked is not None
    assert linked.status == OrderStatus.SUBMITTED
    assert linked.provider_order_id == "99887"


async def test_status_override_requires_reason_and_logs_audit(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, super_admin: User, mock_service: Service
) -> None:
    """التجاوز الإداري يتطلب سبباً واضحاً ويُسجَّل كاملاً."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)

    with pytest.raises(ValidationError):
        await services.orders.admin_override_status(super_admin, order.id, OrderStatus.FAILED, "x")

    assert await services.orders.admin_override_status(
        super_admin, order.id, OrderStatus.FAILED, "طلب تجريبي أُنشئ بالخطأ"
    )
    logs = await services.audit.by_target("order", order.id)
    assert any(log.action == "orders.status.override" for log in logs)


# ============================ الاسترداد والسباق ========================== #


async def test_recover_after_restart_marks_submitting_as_uncertain(
    services: ServiceContainer, db: Database, repos: Repositories, user: User, admin: User, mock_service: Service
) -> None:
    """الطلب العالق في submitting بعد إعادة التشغيل يصبح غير مؤكد ويُنبَّه الأدمن."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)

    async with db.transaction() as tx:   # محاكاة انقطاع أثناء الإرسال
        await repos.orders.update_status(
            tx, order.id, new_status=OrderStatus.SUBMITTING,
            expected_statuses=[OrderStatus.PENDING],
            extra_fields={"locked_by": "worker-1", "locked_until": iso_plus_seconds(-5)},
        )

    report = await services.orders.recover_after_restart()
    assert report["uncertain"] == 1

    recovered = await repos.orders.get(order.id)
    assert recovered is not None
    assert recovered.status == OrderStatus.SUBMIT_UNCERTAIN
    assert await repos.notifications.list_for_user(admin.id)


async def test_concurrent_order_creation_respects_balance(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service
) -> None:
    """
    50 طلباً متزامناً برصيد يكفي 10 فقط ⇒ 10 طلبات بالضبط في قاعدة البيانات.

    يضمن أن الخصم وإنشاء الطلب ذرّيان معاً: لا طلب بلا خصم ولا خصم بلا طلب.
    """
    await services.settings.set("max_orders_per_day", 0)        # تعطيل الحد اليومي
    await services.settings.set("duplicate_order_window_minutes", 0)
    await _fund(services, user, admin, ORDER_COST * 10)

    async def attempt(index: int) -> bool:
        """محاولة إنشاء طلب واحد."""
        try:
            await services.orders.create_order(
                user,
                service_id=mock_service.id,
                link=f"https://instagram.com/user{index}",
                quantity=1000,
                client_request_id=f"race-{index}",
            )
            return True
        except InsufficientBalanceError:
            return False

    results = await asyncio.gather(*(attempt(i) for i in range(50)))

    assert sum(results) == 10
    assert await repos.orders.count_by_user(user.id) == 10
    assert await services.wallet.balance_units(user.id) == 0
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


async def test_two_workers_never_submit_the_same_order_twice(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """عاملان متزامنان لا يرسلان الطلب نفسه مرتين (قفل الحجز)."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)

    first, second = await asyncio.gather(
        services.orders.process_pending_orders(worker="w1"),
        services.orders.process_pending_orders(worker="w2"),
    )

    assert first.claimed + second.claimed == 1
    add_calls = [call for call in mock_client.calls if call[0] == "add"]
    assert len(add_calls) == 1

    final = await repos.orders.get(order.id)
    assert final is not None and final.status == OrderStatus.SUBMITTED
