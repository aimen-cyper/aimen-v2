"""
المرحلة الثانية (v1.0.1) — بند 16: كل حالات المزود (Pending/Processing/Completed/Partial/Canceled/Failed…).

الاختبار يمرّ عبر **عميل Perfect Panel الحقيقي** (نقل httpx وهمي يحاكي ردود اللوحة بصيغتها الفعلية: أرقام كنصوص،
بلا delivered/quantity) إلى خدمة الطلبات الحقيقية، ثم يفحص الحالة والمال والإشعارات لكل حالة.

    الحالات المدعومة: Pending · Awaiting · In progress · Processing · Completed · Partial · Canceled/Cancelled · Refunded ·
                      Fail/Failed/Error/Rejected.
    Refill: لا يوجد مسار «إعادة تعبئة» في النظام (علامة refill_enabled للعرض فقط)، فأي حالة غير معروفة (ومنها Refill…)
            لا تغيّر الطلب ولا المال وتُسجَّل تحذيراً — وهذا ما يُثبته الاختبار.
"""

from __future__ import annotations

import httpx
import pytest

from core.enums import OrderStatus, TransactionType
from core.order_state import map_provider_status
from integrations.providers import registry
from integrations.providers.perfect_panel import PerfectPanelClient
from utils.datetime_utils import iso_plus_seconds

pytestmark = pytest.mark.asyncio

LINK = "https://instagram.com/p/statuses"


class FakePanel:
    """لوحة Perfect Panel وهمية بصيغة الردود الفعلية: add ثم status بحسب ما يبرمجه الاختبار."""

    def __init__(self) -> None:
        """حالة افتراضية وسجل نداءات."""
        self.status_payload: dict = {"status": "Pending", "remains": "1000", "start_count": "0", "charge": "0.5", "currency": "USD"}
        self.status_http: int = 200
        self.raise_on_status: Exception | None = None
        self.calls: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        """يردّ على add/status/orders."""
        body = dict(pair.split("=", 1) for pair in request.content.decode().split("&"))
        action = body.get("action")
        self.calls.append(action)
        if action == "add":
            return httpx.Response(200, json={"order": 9001})
        if self.raise_on_status is not None:
            raise self.raise_on_status
        return httpx.Response(self.status_http, json=self.status_payload)


@pytest.fixture
def panel(monkeypatch):
    """يسجّل عميل Perfect Panel الحقيقي (بنقل وهمي) تحت نوع المزود الاختباري، ويُعيد السجل الأصلي بعدها."""
    fake = FakePanel()
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    original = dict(registry._REGISTRY)
    registry.enable_dev_types(True)
    registry.register_client(
        "mock", lambda **kw: PerfectPanelClient(api_url=kw["api_url"], api_key=kw["api_key"], client=http)
    )
    yield fake
    registry._REGISTRY.clear()
    registry._REGISTRY.update(original)


async def _submitted(services, repos, user, super_admin, service):
    """طلب بقيمة 10000 وحدة أُرسل للمزود (صار submitted)."""
    await services.wallet.adjust_balance(target=user, amount_units=100_000, admin=super_admin, reason="رصيد", credit=True)
    order = await services.orders.create_order(user, service_id=service.id, link=LINK, quantity=1000)
    await services.orders.process_pending_orders()
    stored = await repos.orders.get(order.id)
    assert stored.status == OrderStatus.SUBMITTED and stored.provider_order_id == "9001"
    return stored


async def _check(services, db, order_id, times=1):
    """تشغيل فحص الحالة (يُقدَّم موعده أولاً)."""
    for _ in range(times):
        async with db.transaction() as tx:
            await tx.execute("UPDATE orders SET next_check_at = ?, locked_until = NULL WHERE id = ?", (iso_plus_seconds(-30), order_id))
        await services.orders.process_due_orders()


# ------------------------------ جدول التعيين ------------------------------ #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Pending", OrderStatus.SUBMITTED), ("pending", OrderStatus.SUBMITTED), ("Awaiting", OrderStatus.SUBMITTED),
        ("In queue", OrderStatus.SUBMITTED), ("In progress", OrderStatus.IN_PROGRESS), ("  IN   PROGRESS ", OrderStatus.IN_PROGRESS),
        ("Processing", OrderStatus.IN_PROGRESS), ("Running", OrderStatus.IN_PROGRESS), ("Active", OrderStatus.IN_PROGRESS),
        ("Completed", OrderStatus.COMPLETED), ("Complete", OrderStatus.COMPLETED), ("Success", OrderStatus.COMPLETED),
        ("Partial", OrderStatus.PARTIAL), ("Canceled", OrderStatus.CANCELED), ("Cancelled", OrderStatus.CANCELED),
        ("Refunded", OrderStatus.CANCELED), ("Fail", OrderStatus.FAILED), ("Failed", OrderStatus.FAILED),
        ("Error", OrderStatus.FAILED), ("Rejected", OrderStatus.FAILED),
        ("Refill", None), ("Refilling", None), ("Weird status", None), ("", None), (None, None),
    ],
)
async def test_provider_status_mapping_table(raw, expected) -> None:
    """كل نص حالة معروف يُعيَّن بدقة، وكل مجهول (ومنه Refill) يُعاد None فلا يُغيَّر الطلب."""
    assert map_provider_status(raw) == expected


# ------------------------ أثر كل حالة على الطلب والمال ------------------------ #


async def test_pending_keeps_submitted_then_processing_then_completed(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """Pending ⇒ يبقى submitted · Processing ⇒ in_progress · Completed (remains 0) ⇒ completed، بلا استرجاع."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    await _check(services, db, order.id)
    assert (await repos.orders.get(order.id)).status == OrderStatus.SUBMITTED
    panel.status_payload = {"status": "Processing", "remains": "700", "start_count": "10", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id)
    mid = await repos.orders.get(order.id)
    assert mid.status == OrderStatus.IN_PROGRESS and mid.remains == 700 and mid.start_count == 10
    panel.status_payload = {"status": "Completed", "remains": "0", "start_count": "10", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id)
    done = await repos.orders.get(order.id)
    assert done.status == OrderStatus.COMPLETED and done.delivered_quantity == 1000 and done.refund_amount_units == 0
    assert await services.wallet.balance_units(user.id) == 90_000
    assert panel.calls.count("add") == 1


async def test_pending_after_processing_is_not_a_regression_nor_an_error(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """«Pending» العابرة بعد «Processing» لا تُرجع الطلب ولا تكتب خطأً مضلِّلاً."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.status_payload = {"status": "Processing", "remains": "900", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id)
    panel.status_payload = {"status": "Pending", "remains": "900", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id)
    after = await repos.orders.get(order.id)
    assert after.status == OrderStatus.IN_PROGRESS and not after.last_error


async def test_partial_refunds_only_the_remaining_share_once(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """Partial بـremains=250 من 1000 ⇒ استرجاع 2500 من 10000 مرة واحدة حتى مع تكرار الفحص، وإشعار جزئي."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.status_payload = {"status": "Partial", "remains": "250", "start_count": "5", "charge": "0.4", "currency": "USD"}
    await _check(services, db, order.id, times=3)
    final = await repos.orders.get(order.id)
    assert final.status == OrderStatus.PARTIAL and final.delivered_quantity == 750 and final.remains == 250
    assert final.refund_amount_units == 2_500
    assert await services.wallet.balance_units(user.id) == 92_500
    rows = await db.fetchall("SELECT type, amount_units FROM transactions WHERE order_id = ? ORDER BY id", (order.id,))
    assert [(r["type"], r["amount_units"]) for r in rows] == [(TransactionType.ORDER, 10_000), (TransactionType.PARTIAL_REFUND, 2_500)]
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM notifications WHERE type = 'order_partial'"))["n"] == 1
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


@pytest.mark.parametrize("raw", ["Canceled", "Cancelled", "Refunded"])
async def test_canceled_by_provider_refunds_in_full_once(raw, services, repos, db, user, super_admin, mock_service, panel) -> None:
    """Canceled/Cancelled/Refunded لدى المزود ⇒ إلغاء ثم استرجاع كامل (الحالة النهائية refunded) مرة واحدة + إشعار."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.status_payload = {"status": raw, "remains": "1000", "charge": "0", "currency": "USD"}
    await _check(services, db, order.id, times=3)
    final = await repos.orders.get(order.id)
    assert final.status == OrderStatus.REFUNDED and final.refund_amount_units == 10_000
    assert [h.to_status for h in await repos.orders.history(order.id)][-2:] == [OrderStatus.CANCELED, OrderStatus.REFUNDED]
    assert await services.wallet.balance_units(user.id) == 100_000
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM transactions WHERE order_id = ? AND type = 'refund'", (order.id,)))["n"] == 1
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM notifications WHERE type = 'order_canceled'"))["n"] == 1
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


@pytest.mark.parametrize("raw", ["Fail", "Failed", "Error", "Rejected"])
async def test_failed_by_provider_refunds_and_notifies_user_and_admins(raw, services, repos, db, user, super_admin, mock_service, panel) -> None:
    """Fail/Failed/Error/Rejected ⇒ فشل ثم استرجاع كامل (الحالة النهائية refunded) + إشعار المستخدم والأدمن."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.status_payload = {"status": raw, "remains": "1000", "charge": "0", "currency": "USD"}
    await _check(services, db, order.id, times=2)
    final = await repos.orders.get(order.id)
    assert final.status == OrderStatus.REFUNDED and final.refund_amount_units == 10_000
    assert await services.wallet.balance_units(user.id) == 100_000
    history = [h.to_status for h in await repos.orders.history(order.id)]
    assert history[-2:] == [OrderStatus.FAILED, OrderStatus.REFUNDED]
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND type = 'order_failed'", (user.id,)))["n"] == 1
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM transactions WHERE order_id = ? AND type = 'refund'", (order.id,)))["n"] == 1
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


@pytest.mark.parametrize("raw", ["Refill", "Refilling", "Something new"])
async def test_unknown_statuses_never_change_order_or_money_and_are_logged(raw, services, repos, db, user, super_admin, mock_service, panel) -> None:
    """حالة مجهولة (ومنها Refill) ⇒ لا تغيير حالة ولا مال، وتحذير مسجَّل في error_logs، والطلب يُكمل لاحقاً عند حالة معروفة."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.status_payload = {"status": raw, "remains": "500", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id, times=2)
    unchanged = await repos.orders.get(order.id)
    assert unchanged.status == OrderStatus.SUBMITTED and unchanged.refund_amount_units == 0
    assert await services.wallet.balance_units(user.id) == 90_000
    logged = await db.fetchall("SELECT * FROM error_logs WHERE error_type = 'UnknownProviderStatus'")
    assert len(logged) >= 1 and raw in logged[0]["message"]
    panel.status_payload = {"status": "Completed", "remains": "0", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id)
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED


async def test_terminal_status_is_never_reopened_by_a_later_provider_status(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """بعد Completed لا تُعيد «Processing»/«Canceled» المتأخرة فتح الطلب ولا تسترجع مالاً."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.status_payload = {"status": "Completed", "remains": "0", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id)
    for late in ("Processing", "Canceled", "Failed", "Partial"):
        panel.status_payload = {"status": late, "remains": "500", "charge": "0", "currency": "USD"}
        await _check(services, db, order.id)
        stored = await repos.orders.get(order.id)
        assert stored.status == OrderStatus.COMPLETED and stored.refund_amount_units == 0
    assert await services.wallet.balance_units(user.id) == 90_000


async def test_partial_when_refund_disabled_or_remains_unknown_refunds_nothing(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """Partial مع إيقاف الاسترجاع الجزئي ⇒ حالة partial بلا حركة مالية (قرار المالك)."""
    await services.settings.set("partial_refund_enabled", "false", admin_id=super_admin.id)
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.status_payload = {"status": "Partial", "remains": "400", "charge": "0.3", "currency": "USD"}
    await _check(services, db, order.id)
    final = await repos.orders.get(order.id)
    assert final.status == OrderStatus.PARTIAL and final.refund_amount_units == 0
    assert await services.wallet.balance_units(user.id) == 90_000


# --------------------------- أعطال الاتصال بالمزود --------------------------- #


async def test_provider_http_errors_and_timeouts_during_status_do_not_change_anything(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """HTTP 500 / مهلة / رد خطأ عند الفحص ⇒ لا تغيير ولا استرجاع، ثم يكتمل الطلب حين يعود المزود."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.status_http, panel.status_payload = 500, {"error": "boom"}
    await _check(services, db, order.id)
    panel.status_http, panel.raise_on_status = 200, httpx.ReadTimeout("slow")
    await _check(services, db, order.id)
    panel.raise_on_status, panel.status_payload = None, {"error": "Incorrect order ID"}
    await _check(services, db, order.id)
    mid = await repos.orders.get(order.id)
    assert mid.status == OrderStatus.SUBMITTED and mid.refund_amount_units == 0 and mid.last_check_error
    assert await services.wallet.balance_units(user.id) == 90_000

    panel.status_payload = {"status": "Completed", "remains": "0", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id)
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED
    assert panel.calls.count("add") == 1
