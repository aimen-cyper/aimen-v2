"""
المرحلة 12.1 (تقوية) — سلامة إرسال الطلبات للمزود وسياسات الأدمن:

    P0-1  `submitting` لا يعلق للأبد: إلغاء الجولة/انهيار/انتهاء القفل ⇒ `submit_uncertain` + تنبيه، بلا إعادة إرسال.
    P0-2  نجاح المزود ثم فشل القاعدة لا يُنتج طلباً مزدوجاً: إعادة محاولة الحفظ ثم «غير مؤكد» مع رقم المزود.
    P0-3/4 الأدمن لا يسترجع/يُغلق/يتجاوز طلباً قيد الإرسال، و«تعليم كفاشل» لا يشمل الطلبات المُرسلة.
    + ثغرة وجدناها: طلب فاشل بلا استرجاع (تعطيل التلقائي) لم يكن له أي مسار استرجاع.
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

from core.enums import OrderStatus, TransactionType
from core.exceptions import InvalidStateTransitionError, ProviderPermanentError
from core.order_state import override_targets
from database.models import Service, User
from services import ServiceContainer
from services.order_service import OrderService
from utils.datetime_utils import iso_plus_seconds

pytestmark = pytest.mark.asyncio

COST = 10_000


async def _fund(services, user, admin, amount=100_000) -> None:
    """شحن رصيد اختباري عبر المسار الرسمي."""
    await services.wallet.adjust_balance(target=user, amount_units=amount, admin=admin, reason="رصيد اختبار", credit=True)


async def _order(services, user, service, n: int = 1):
    """إنشاء طلب بروابط مختلفة (لتفادي فحص التكرار)."""
    return await services.orders.create_order(
        user, service_id=service.id, link=f"https://instagram.com/safety{n}", quantity=1000
    )


async def _status(repos, order_id: int):
    """قراءة الطلب الحالي."""
    order = await repos.orders.get(order_id)
    assert order is not None
    return order


def _hang_after_accept(mock_client, seconds: float = 30.0) -> None:
    """مزود يقبل الطلب فعلاً ثم «يضيع الرد» (يتأخر طويلاً) — أخطر سيناريو مهلة."""
    original = mock_client.add_order

    async def slow(**kwargs):
        result = await original(**kwargs)
        await asyncio.sleep(seconds)
        return result

    mock_client.add_order = slow


# ----------------------------- P0-1: submitting لا يعلق ----------------------------- #


async def test_job_timeout_marks_in_flight_order_uncertain_and_requeues_the_rest(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service, mock_client
) -> None:
    """إلغاء جولة الإرسال (مهلة المهمة) أثناء انتظار المزود: الطلب الجاري «غير مؤكد»، وغير المبدوء يعود pending."""
    await _fund(services, user, admin)
    first = await _order(services, user, mock_service, 1)
    second = await _order(services, user, mock_service, 2)
    _hang_after_accept(mock_client)

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(services.orders.process_pending_orders(limit=5), timeout=0.3)

    assert (await _status(repos, first.id)).status == OrderStatus.SUBMIT_UNCERTAIN
    assert (await _status(repos, second.id)).status == OrderStatus.PENDING, "طلب لم يُرسل شيء منه يجب أن يعود للانتظار"
    assert len(mock_client.orders) == 1, "المزود استلم الطلب الأول فقط"

    # لا إعادة إرسال تلقائية للطلب غير المؤكد، والثاني يُرسل لاحقاً مرة واحدة
    mock_client.add_order = type(mock_client).add_order.__get__(mock_client)
    async with repos.db.transaction() as tx:
        await repos.orders.update_fields(tx, second.id, next_check_at=iso_plus_seconds(-5))
    await services.orders.process_pending_orders(limit=5)
    assert (await _status(repos, first.id)).status == OrderStatus.SUBMIT_UNCERTAIN
    assert len(mock_client.orders) == 2
    assert (await services.wallet.balance_units(user.id)) == 100_000 - 2 * COST, "لا استرجاع تلقائي لغير المؤكد"


async def test_unexpected_exception_during_submit_becomes_uncertain(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service, mock_client
) -> None:
    """استثناء غير متوقع (ليس من المزود) أثناء الإرسال ⇒ غير مؤكد بدل البقاء submitting."""
    await _fund(services, user, admin)
    order = await _order(services, user, mock_service)
    mock_client.always_fail_add = RuntimeError("انهيار غير متوقع")
    report = await services.orders.process_pending_orders()
    assert report.uncertain == 1
    assert (await _status(repos, order.id)).status == OrderStatus.SUBMIT_UNCERTAIN
    logged = await repos.db.fetchall("SELECT message FROM error_logs WHERE error_type = 'ProviderUncertainError'")
    assert len(logged) == 1 and "RuntimeError" in str(logged[0]["message"])


async def test_periodic_recovery_moves_expired_submitting_to_uncertain(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service, mock_client
) -> None:
    """طلب علق في submitting وانتهى قفله ⇒ الاسترداد الدوري يجعله غير مؤكد وينبّه، ولا يمسّ ما قفله ساري."""
    await _fund(services, user, admin)
    stale = await _order(services, user, mock_service, 1)
    live = await _order(services, user, mock_service, 2)
    async with repos.db.transaction() as tx:
        claimed = await repos.orders.claim_pending_for_submit(tx, worker="w", limit=5, lock_seconds=120)
        assert {o.id for o in claimed} == {stale.id, live.id}
        await repos.orders.update_fields(tx, stale.id, locked_until=iso_plus_seconds(-10))

    assert await services.orders.recover_stale_submissions() == 1
    assert (await _status(repos, stale.id)).status == OrderStatus.SUBMIT_UNCERTAIN
    assert (await _status(repos, live.id)).status == OrderStatus.SUBMITTING, "قفل ساري ⇒ عامل حيّ يرسله"
    assert await services.orders.recover_stale_submissions() == 0, "الاسترداد idempotent"

    history = await repos.orders.history(stale.id)
    assert history[-1].to_status == OrderStatus.SUBMIT_UNCERTAIN
    errors = await repos.db.fetchall("SELECT error_type FROM error_logs WHERE error_type = 'SubmitStalled'")
    assert len(errors) == 1
    # لا يُعاد التقاطه للإرسال
    assert (await services.orders.process_pending_orders()).claimed == 0
    assert len(mock_client.orders) == 0


async def test_submit_job_runs_recovery_first(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service
) -> None:
    """مهمة `orders_submit` الدورية تستدعي الاسترداد قبل الحجز."""
    from jobs.order_jobs import submit_pending_orders

    await _fund(services, user, admin)
    order = await _order(services, user, mock_service)
    async with repos.db.transaction() as tx:
        await repos.orders.claim_pending_for_submit(tx, worker="w", limit=5, lock_seconds=120)
        await repos.orders.update_fields(tx, order.id, locked_until=iso_plus_seconds(-1))

    class _App:
        bot_data = {"services": services}

    class _Ctx:
        application = _App()

    await submit_pending_orders(_Ctx())
    assert (await _status(repos, order.id)).status == OrderStatus.SUBMIT_UNCERTAIN


async def test_lock_is_renewed_before_each_submit(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service
) -> None:
    """الطلب الأخير في دفعة طويلة لا يُعدّ عالقاً: القفل يُمدَّد قبل إرساله."""
    await _fund(services, user, admin)
    order = await _order(services, user, mock_service)
    async with repos.db.transaction() as tx:
        claimed = await repos.orders.claim_pending_for_submit(tx, worker="w1", limit=1, lock_seconds=1)
        await repos.orders.update_fields(tx, order.id, locked_until=iso_plus_seconds(-1))
    async with repos.db.transaction() as tx:
        assert await repos.orders.renew_submit_lock(tx, order.id, worker="w1", lock_seconds=100)
        assert not await repos.orders.renew_submit_lock(tx, order.id, worker="other", lock_seconds=100)
    assert (await _status(repos, order.id)).locked_until > iso_plus_seconds(50)
    assert claimed


# ------------------- P0-2: نجاح المزود ثم فشل القاعدة (لا طلب مزدوج) ------------------- #


def _fail_submitted_update(monkeypatch, repos, *, times: int) -> dict[str, int]:
    """يجعل تحديث الطلب إلى submitted يفشل `times` مرة (خطأ SQLite) ثم يعمل."""
    original = repos.orders.update_status
    state = {"calls": 0}

    async def flaky(tx, order_id, *, new_status, expected_statuses, extra_fields=None):
        if new_status == OrderStatus.SUBMITTED and state["calls"] < times:
            state["calls"] += 1
            raise sqlite3.OperationalError("database is locked")
        return await original(tx, order_id, new_status=new_status, expected_statuses=expected_statuses, extra_fields=extra_fields)

    monkeypatch.setattr(repos.orders, "update_status", flaky)
    return state


async def test_db_failure_after_provider_success_never_resubmits(
    services: ServiceContainer, repos, user: User, admin: User, super_admin: User, mock_service: Service, mock_client,
    monkeypatch, caplog,
) -> None:
    """المزود قبل الطلب ثم فشل الحفظ دائماً ⇒ غير مؤكد + رقم المزود في التنبيه واللوق، وطلب واحد فقط عند المزود."""
    monkeypatch.setattr(OrderService, "PERSIST_RETRY_DELAYS", (0.0, 0.0, 0.0))
    await _fund(services, user, admin)
    order = await _order(services, user, mock_service)
    state = _fail_submitted_update(monkeypatch, repos, times=99)

    with caplog.at_level("CRITICAL"):
        report = await services.orders.process_pending_orders()
    assert report.uncertain == 1 and state["calls"] == 3
    current = await _status(repos, order.id)
    assert current.status == OrderStatus.SUBMIT_UNCERTAIN and current.provider_order_id is None
    provider_id = next(iter(mock_client.orders))
    assert provider_id in (current.last_error or ""), "رقم المزود يجب أن يظهر ليُربط يدوياً"
    assert provider_id in caplog.text

    # لا إعادة إرسال مهما تكررت الجولات
    for _ in range(3):
        await services.orders.recover_stale_submissions()
        await services.orders.process_pending_orders()
    assert len(mock_client.orders) == 1

    # الأدمن الأعلى يربط الرقم ⇒ الدورة تكتمل
    monkeypatch.undo()
    assert await services.orders.admin_link_provider_order(super_admin, order.id, provider_id)
    assert (await _status(repos, order.id)).status == OrderStatus.SUBMITTED


async def test_transient_db_failure_is_retried_and_order_is_submitted(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service, mock_client, monkeypatch
) -> None:
    """فشل حفظ مؤقت (محاولتان) ثم نجاح ⇒ submitted بلا تدخل بشري وبطلب واحد عند المزود."""
    monkeypatch.setattr(OrderService, "PERSIST_RETRY_DELAYS", (0.0, 0.0, 0.0))
    await _fund(services, user, admin)
    order = await _order(services, user, mock_service)
    state = _fail_submitted_update(monkeypatch, repos, times=2)

    report = await services.orders.process_pending_orders()
    assert report.succeeded == 1 and state["calls"] == 2
    current = await _status(repos, order.id)
    assert current.status == OrderStatus.SUBMITTED and current.provider_order_id in mock_client.orders
    assert len(mock_client.orders) == 1


# ---------------------- P0-3/4: سياسات الأدمن أثناء الإرسال ---------------------- #


async def _claim(repos, order_id: int) -> None:
    """وضع الطلب في submitting كأن عاملاً حجزه الآن (قفل ساري)."""
    async with repos.db.transaction() as tx:
        claimed = await repos.orders.claim_pending_for_submit(tx, worker="w", limit=10, lock_seconds=120)
    assert order_id in {o.id for o in claimed}


async def test_admin_cannot_cancel_or_fail_or_override_in_flight_order(
    services: ServiceContainer, repos, user: User, admin: User, super_admin: User, mock_service: Service
) -> None:
    """طلب قيد الإرسال الآن: لا إلغاء ولا تعليم كفاشل ولا تجاوز، ولا يتحرك أي مبلغ."""
    await _fund(services, user, admin)
    order = await _order(services, user, mock_service)
    await _claim(repos, order.id)
    balance = await services.wallet.balance_units(user.id)

    with pytest.raises(InvalidStateTransitionError):
        await services.orders.admin_cancel(admin, order.id, "إلغاء أثناء الإرسال")
    with pytest.raises(InvalidStateTransitionError):
        await services.orders.admin_mark_failed(admin, order.id, "فشل أثناء الإرسال")
    with pytest.raises(InvalidStateTransitionError):
        await services.orders.admin_override_status(super_admin, order.id, OrderStatus.FAILED, "تجاوز أثناء الإرسال")

    assert (await _status(repos, order.id)).status == OrderStatus.SUBMITTING
    assert await services.wallet.balance_units(user.id) == balance


async def test_mark_failed_only_for_orders_that_did_not_reach_provider(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service, mock_client
) -> None:
    """«تعليم كفاشل + استرجاع» مرفوض لطلب عند المزود (submitted)، ومسموح لـpending."""
    await _fund(services, user, admin)
    sent = await _order(services, user, mock_service, 1)
    await services.orders.process_pending_orders()
    assert (await _status(repos, sent.id)).status == OrderStatus.SUBMITTED
    balance = await services.wallet.balance_units(user.id)
    with pytest.raises(InvalidStateTransitionError):
        await services.orders.admin_mark_failed(admin, sent.id, "محاولة تعليم طلب مُرسَل")
    assert await services.wallet.balance_units(user.id) == balance

    waiting = await _order(services, user, mock_service, 2)
    assert await services.orders.admin_mark_failed(admin, waiting.id, "الرابط خاطئ والطلب لم يُرسل") == COST


async def test_override_follows_state_machine_and_money_policy(
    services: ServiceContainer, repos, user: User, admin: User, super_admin: User, mock_service: Service, mock_client
) -> None:
    """التجاوز: لا قفز في آلة الحالات، لا حالات إرسال/مال، ولا حالة تتطلب رقم مزود بلا رقم."""
    await _fund(services, user, admin)
    pending = await _order(services, user, mock_service, 1)
    for target in (OrderStatus.COMPLETED, OrderStatus.PENDING, OrderStatus.CANCELED, OrderStatus.REFUNDED, OrderStatus.SUBMITTING):
        with pytest.raises(InvalidStateTransitionError):
            await services.orders.admin_override_status(super_admin, pending.id, target, "محاولة تجاوز ممنوعة")
    assert (await _status(repos, pending.id)).status == OrderStatus.PENDING

    mock_client.always_fail_add = None
    await services.orders.process_pending_orders()
    sent = await _status(repos, pending.id)
    assert sent.status == OrderStatus.SUBMITTED
    for target in (OrderStatus.CANCELED, OrderStatus.REFUNDED, OrderStatus.PENDING):
        with pytest.raises(InvalidStateTransitionError):
            await services.orders.admin_override_status(super_admin, sent.id, target, "محاولة تجاوز ممنوعة")
    assert await services.orders.admin_override_status(super_admin, sent.id, OrderStatus.COMPLETED, "أكّد المزود الاكتمال يدوياً")
    assert (await _status(repos, sent.id)).status == OrderStatus.COMPLETED


async def test_override_blocked_from_uncertain_state(
    services: ServiceContainer, repos, user: User, admin: User, super_admin: User, mock_service: Service, mock_client
) -> None:
    """غير مؤكد: مساره «ربط الرقم» أو «تعليم كفاشل» فقط."""
    await _fund(services, user, admin)
    order = await _order(services, user, mock_service)
    mock_client.always_fail_add = RuntimeError("x")
    await services.orders.process_pending_orders()
    assert (await _status(repos, order.id)).status == OrderStatus.SUBMIT_UNCERTAIN
    for target in (OrderStatus.SUBMITTED, OrderStatus.FAILED):
        with pytest.raises(InvalidStateTransitionError):
            await services.orders.admin_override_status(super_admin, order.id, target, "تجاوز غير مسموح هنا")


def test_override_targets_pure_function() -> None:
    """منطق الأزرار: ما يُعرض للأدمن = آلة الحالات ∩ السياسة."""
    assert override_targets(OrderStatus.SUBMITTING, has_provider_id=False) == []
    assert override_targets(OrderStatus.SUBMIT_UNCERTAIN, has_provider_id=False) == []
    assert override_targets(OrderStatus.PENDING, has_provider_id=False) == [OrderStatus.FAILED]
    assert OrderStatus.COMPLETED in override_targets(OrderStatus.SUBMITTED, has_provider_id=True)
    assert OrderStatus.CANCELED not in override_targets(OrderStatus.SUBMITTED, has_provider_id=True)
    assert override_targets(OrderStatus.COMPLETED, has_provider_id=True) == []


# ------------- ثغرة مكتشفة: طلب فاشل بلا استرجاع لا مسار لاسترجاعه ------------- #


async def test_failed_order_without_auto_refund_can_be_refunded_once_manually(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service, mock_client
) -> None:
    """الاسترجاع التلقائي معطّل ⇒ الطلب failed والمال محجوز ⇒ «تعليم كفاشل» يسترجعه مرة واحدة فقط."""
    await services.settings.set("auto_refund_on_provider_fail", False)
    await _fund(services, user, admin)
    order = await _order(services, user, mock_service)
    mock_client.always_fail_add = ProviderPermanentError("رفض المزود")
    await services.orders.process_pending_orders()
    assert (await _status(repos, order.id)).status == OrderStatus.FAILED
    assert await services.wallet.balance_units(user.id) == 100_000 - COST

    assert await services.orders.admin_mark_failed(admin, order.id, "استرجاع يدوي بعد مراجعة") == COST
    final = await _status(repos, order.id)
    assert final.status == OrderStatus.REFUNDED and final.refund_amount_units == COST
    assert await services.wallet.balance_units(user.id) == 100_000

    with pytest.raises(InvalidStateTransitionError):                     # مغلق الآن
        await services.orders.admin_mark_failed(admin, order.id, "استرجاع ثانٍ")
    txs = await services.wallet.order_transactions(order.id)
    assert [t.type for t in txs].count(TransactionType.REFUND) == 1
