"""
المرحلة الثانية (v1.0.1) — بند 14: منع الطلبات المكررة، وبند 15: دورة الطلب الناجحة الكاملة.

    14: ضغط مزدوج (تسلسلي ومتزامن) · إعادة بنفس المفتاح بعد Timeout · محادثة جديدة بمحتوى مطابق ·
        إعادة الإرسال للمزود · إلغاء مزدوج ⇒ لا خصم/استرجاع مرتين ولا طلب ثانٍ ولا رسالة تُكتب فوق الإيصال.
    15: pending → submitting → submitted → in_progress → completed بكل أثرها (حالات، سجل، مال، إشعارات، مزود).
"""

from __future__ import annotations

import asyncio

import pytest
from telegram.error import TimedOut

from core.enums import OrderStatus, TransactionType
from core.exceptions import DuplicateOperationError
from handlers.common import fallbacks
from handlers.user import order_flow
from keyboards.callback_data import pack
from tests.integration.test_user_interface import bot, context, load_user, press, write  # noqa: F401,F811
from utils import telegram_retry
from utils.datetime_utils import iso_plus_seconds

pytestmark = pytest.mark.asyncio

LINK = "https://instagram.com/p/phase14"


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """إعادة محاولة تيليجرام بلا انتظار حقيقي في الاختبارات."""
    monkeypatch.setattr(telegram_retry, "RETRY_DELAYS", (0.0, 0.0))


async def _fund(services, user, super_admin, units=100_000):
    """شحن رصيد عبر المسار الرسمي."""
    await services.wallet.adjust_balance(target=user, amount_units=units, admin=super_admin, reason="رصيد", credit=True)


async def _flow_until_summary(bot, context, user, service, *, link=LINK, quantity="1000"):  # noqa: F811
    """بدء محادثة الطلب حتى شاشة التأكيد."""
    await press(bot, context, order_flow.start_order, pack("new", "start", service.id), user.telegram_id)
    await write(bot, context, order_flow.receive_link, link, user.telegram_id)
    await write(bot, context, order_flow.receive_quantity, quantity, user.telegram_id)


async def _count(db, sql, params=()):
    """عدّ صفوف."""
    return (await db.fetchone(sql, params))["n"]


async def _due(db, order_id):
    """تقديم موعد الفحص."""
    async with db.transaction() as tx:
        await tx.execute("UPDATE orders SET next_check_at = ? WHERE id = ?", (iso_plus_seconds(-30), order_id))


# ============================ 14 — منع التكرار ============================ #


async def test_concurrent_confirms_with_same_key_create_one_order_and_one_charge(services, db, user, super_admin, mock_service) -> None:
    """عشر ضغطات متزامنة بنفس مفتاح الطلب ⇒ طلب واحد وخصم واحد وإشعار إنشاء واحد."""
    await _fund(services, user, super_admin)
    results = await asyncio.gather(
        *[services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="same-key") for _ in range(10)],
        return_exceptions=True,
    )
    orders = [r for r in results if not isinstance(r, BaseException)]
    assert len({o.id for o in orders}) == 1, results
    assert await _count(db, "SELECT COUNT(*) AS n FROM orders") == 1
    assert await _count(db, "SELECT COUNT(*) AS n FROM transactions WHERE type = ?", (TransactionType.ORDER,)) == 1
    assert await services.wallet.balance_units(user.id) == 90_000
    assert await _count(db, "SELECT COUNT(*) AS n FROM notifications WHERE type = 'order_created'") == 1


async def test_concurrent_identical_orders_with_different_keys_only_one_succeeds(services, db, user, super_admin, mock_service) -> None:
    """محادثتان مختلفتان (مفتاحان) بمحتوى مطابق وبالتزامن ⇒ الأولى تنجح والثانية تُرفض كمكررة؛ خصم واحد."""
    await _fund(services, user, super_admin)
    results = await asyncio.gather(
        services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="k1"),
        services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="k2"),
        return_exceptions=True,
    )
    assert sum(isinstance(r, DuplicateOperationError) for r in results) == 1
    assert await _count(db, "SELECT COUNT(*) AS n FROM orders") == 1
    assert await services.wallet.balance_units(user.id) == 90_000


async def test_retry_with_same_key_after_success_returns_same_order_without_charging(services, repos, db, user, super_admin, mock_service) -> None:
    """إعادة نفس المفتاح بعد النجاح (مثلاً بعد Timeout) تعيد الطلب الأول ولا تخصم ولا تُرفض كمكررة."""
    await _fund(services, user, super_admin)
    first = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="retry-1")
    again = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="retry-1")
    assert again.id == first.id and await services.wallet.balance_units(user.id) == 90_000
    # ولو تغيّر الرصيد بين المحاولتين (أُنفق في طلب آخر) تبقى الإعادة آمنة
    await services.orders.create_order(user, service_id=mock_service.id, link=LINK + "2", quantity=1000, client_request_id="other")
    third = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="retry-1")
    assert third.id == first.id and await services.wallet.balance_units(user.id) == 80_000
    assert await _count(db, "SELECT COUNT(*) AS n FROM orders") == 2


async def test_new_flow_with_identical_content_is_blocked_inside_window_only(services, repos, db, user, super_admin, mock_service) -> None:
    """نفس (الخدمة+الرابط+الكمية) ضمن النافذة يُرفض؛ بعدها أو مع اختلاف أي عنصر أو إلغاء الأول أو إغلاق النافذة يُقبل."""
    await _fund(services, user, super_admin, 500_000)
    first = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="a")
    with pytest.raises(DuplicateOperationError):
        await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="b")
    await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1001, client_request_id="c")      # كمية مختلفة
    await services.orders.create_order(user, service_id=mock_service.id, link=LINK + "x", quantity=1000, client_request_id="d")  # رابط مختلف
    assert await _count(db, "SELECT COUNT(*) AS n FROM orders") == 3

    other, _ = await services.users.get_or_create(telegram_id=555_000_999, first_name="Other")
    await _fund(services, other, super_admin)
    await services.orders.create_order(other, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="e")      # مستخدم آخر

    async with db.transaction() as tx:                                           # خارج النافذة
        await tx.execute("UPDATE orders SET created_at = ? WHERE id = ?", (iso_plus_seconds(-3 * 3600), first.id))
    await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="f")

    await services.orders.cancel_by_user(user, first.id)                         # إلغاء الأقدم لا يهم؛ ألغِ الأحدث المطابق
    latest = (await services.orders.list_for_user(user, limit=1))[0]
    await services.orders.cancel_by_user(user, latest.id)
    await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="g")      # المطابق السابق أُلغي

    await services.settings.set("duplicate_order_window_minutes", "0", admin_id=super_admin.id)
    await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="h")      # النافذة مغلقة
    check = await services.wallet.verify_ledger(user.id)
    assert check.is_balanced and check.stored_units >= 0


async def test_ui_timeout_after_order_creation_does_not_lose_or_duplicate(bot, context, services, db, user, super_admin, mock_service) -> None:  # noqa: F811
    """
    انقطاع تيليجرام لحظة عرض إيصال الطلب (TimedOut ×3): الطلب يبقى واحداً، المحادثة تُنهى، الإشعار في الصندوق،
    وإعادة المحاولة اللاحقة بنفس المحتوى لا تخصم ثانية.
    """
    await _fund(services, user, super_admin)
    await load_user(bot, context, user)
    await _flow_until_summary(bot, context, user, mock_service)
    bot.fail("edit", TimedOut("Read timeout"), times=3, delivered=False)       # المحاولة الأولى + إعادتان
    state = await press(bot, context, order_flow.confirm_order, pack("flow", "confirm"), user.telegram_id)
    assert state == order_flow.ConversationHandler.END
    assert order_flow.FLOW_KEY not in context.user_data                          # لا حالة معلّقة
    assert await _count(db, "SELECT COUNT(*) AS n FROM orders") == 1
    assert await services.wallet.balance_units(user.id) == 90_000
    # الإيصال وصل عبر صندوق الإشعارات الدائم رغم تعذّر الشاشة
    sent = []

    async def sender(telegram_id, title, message):
        sent.append((telegram_id, message))
        return 1

    await services.notifications.dispatch_pending(sender, limit=50)
    assert any("تم إنشاء" in message or "طلب" in message for _, message in sent)

    # المستخدم يعيد الطلب من الصفر بنفس المحتوى ⇒ مرفوض كمكرر لا خصم ثانٍ
    bot.clear()
    await _flow_until_summary(bot, context, user, mock_service)
    await press(bot, context, order_flow.confirm_order, pack("flow", "confirm"), user.telegram_id)
    assert "لديك طلب مطابق" in " ".join(m.text for m in bot.sent)
    assert await _count(db, "SELECT COUNT(*) AS n FROM orders") == 1
    assert await services.wallet.balance_units(user.id) == 90_000


async def test_double_tap_on_confirm_never_overwrites_the_receipt(bot, context, services, db, user, super_admin, mock_service) -> None:  # noqa: F811
    """الضغطة الثانية (زر قديم بعد انتهاء المحادثة): تنبيه منبثق بالرقم فقط، دون تحرير الإيصال ودون طلب ثانٍ."""
    await _fund(services, user, super_admin)
    await load_user(bot, context, user)
    await _flow_until_summary(bot, context, user, mock_service)
    await press(bot, context, order_flow.confirm_order, pack("flow", "confirm"), user.telegram_id)
    receipt = bot.last
    assert "تم إنشاء طلبك" in receipt.text
    bot.sent.clear()

    await press(bot, context, fallbacks.unknown_callback, pack("flow", "confirm"), user.telegram_id)
    assert bot.sent == [], "الضغطة الثانية كتبت فوق الإيصال"
    alert = bot.answers[-1]
    assert alert["alert"] is True and "طلبك مسجَّل أصلاً" in alert["text"]
    order = (await services.orders.list_for_user(user, limit=1))[0]
    assert (order.public_code or f"#{order.id}") in alert["text"]
    assert await _count(db, "SELECT COUNT(*) AS n FROM orders") == 1


async def test_stale_flow_button_without_recent_order_gets_generic_hint(bot, context, user) -> None:  # noqa: F811
    """زر محادثة قديم بلا طلب حديث ⇒ تنبيه عام بلا تحرير رسالة."""
    await load_user(bot, context, user)
    await press(bot, context, fallbacks.unknown_callback, pack("flow", "confirm"), user.telegram_id)
    assert bot.sent == [] and "انتهت هذه العملية" in bot.answers[-1]["text"]


async def test_concurrent_provider_submission_sends_once(services, repos, user, super_admin, mock_service, mock_client) -> None:
    """مهمتا إرسال متزامنتان على الطلب نفسه ⇒ نداء add واحد للمزود فقط."""
    await _fund(services, user, super_admin)
    order = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000)
    await asyncio.gather(*[services.orders.process_pending_orders() for _ in range(4)])
    adds = [c for c in mock_client.calls if c[0] == "add"]
    assert len(adds) == 1
    stored = await repos.orders.get(order.id)
    assert stored.status == OrderStatus.SUBMITTED and stored.provider_order_id


async def test_double_cancel_refunds_once(services, repos, db, user, super_admin, mock_service) -> None:
    """إلغاءان متزامنان قبل الإرسال ⇒ استرجاع واحد، والآخر يُرفض بلا أثر مالي."""
    await _fund(services, user, super_admin)
    order = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000)
    results = await asyncio.gather(
        services.orders.cancel_by_user(user, order.id), services.orders.cancel_by_user(user, order.id), return_exceptions=True
    )
    assert sorted(type(r).__name__ for r in results) == ["InvalidStateTransitionError", "int"]
    assert [r for r in results if isinstance(r, int)] == [10_000]
    assert await services.wallet.balance_units(user.id) == 100_000
    assert await _count(db, "SELECT COUNT(*) AS n FROM transactions WHERE order_id = ? AND type = 'refund'", (order.id,)) == 1
    check = await services.wallet.verify_ledger(user.id)
    assert check.is_balanced


# ====================== 15 — دورة الطلب الناجحة الكاملة ====================== #


async def test_full_successful_cycle_pending_to_completed(services, repos, db, user, super_admin, mock_service, mock_client) -> None:
    """
    دورة كاملة: إنشاء ⇒ إرسال ⇒ Pending لدى المزود (يبقى submitted) ⇒ Processing ⇒ Completed.
    يُتحقق من: تسلسل الحالات في السجل بلا قفزات، نداء add واحد، خصم واحد وصافي مال صحيح،
    إشعارات (إنشاء/قيد التنفيذ/مكتمل) مرة واحدة، لا استرجاع، وإعادة الفحص بعد الاكتمال لا تغيّر شيئاً.
    """
    mock_client.auto_complete = False                                            # نحرّك حالات المزود يدوياً بدقة
    await _fund(services, user, super_admin)
    order = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000)
    assert order.status == OrderStatus.PENDING and order.cost_units == 10_000

    batch = await services.orders.process_pending_orders()
    assert batch.succeeded == 1
    submitted = await repos.orders.get(order.id)
    assert submitted.status == OrderStatus.SUBMITTED and submitted.provider_order_id
    assert submitted.submitted_at and submitted.next_check_at

    await _due(db, order.id)
    await services.orders.process_due_orders()                                   # المزود ما زال Pending
    assert (await repos.orders.get(order.id)).status == OrderStatus.SUBMITTED

    mock_client.advance(submitted.provider_order_id, to="In progress")
    await _due(db, order.id)
    await services.orders.process_due_orders()
    assert (await repos.orders.get(order.id)).status == OrderStatus.IN_PROGRESS

    mock_client.advance(submitted.provider_order_id, to="Completed", delivered=1000)
    await _due(db, order.id)
    await services.orders.process_due_orders()
    done = await repos.orders.get(order.id)
    assert done.status == OrderStatus.COMPLETED and done.completed_at
    assert done.delivered_quantity == 1000 and done.remains == 0 and done.refund_amount_units == 0
    assert done.next_check_at is None and done.locked_by is None

    for _ in range(2):                                                           # لا شيء يتغير بعد النهاية
        await _due(db, order.id)
        await services.orders.process_due_orders()
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED

    history = [h.to_status for h in await repos.orders.history(order.id)]
    assert history[0] == OrderStatus.PENDING and history[-1] == OrderStatus.COMPLETED
    assert history == [OrderStatus.PENDING, OrderStatus.SUBMITTING, OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS, OrderStatus.COMPLETED]
    assert len([c for c in mock_client.calls if c[0] == "add"]) == 1
    assert await services.wallet.balance_units(user.id) == 90_000
    types = [r["type"] for r in await db.fetchall("SELECT type FROM transactions WHERE order_id = ?", (order.id,))]
    assert types == [TransactionType.ORDER]
    events = [r["type"] for r in await db.fetchall("SELECT type FROM notifications WHERE user_id = ? ORDER BY id", (user.id,))]
    for needed in ("order_created", "order_in_progress", "order_completed"):
        assert events.count(needed) == 1, events
    check = await services.wallet.verify_ledger(user.id)
    assert check.is_balanced and check.stored_units == 90_000
    row = await db.fetchone("SELECT COUNT(*) AS n FROM audit_logs WHERE action LIKE 'orders.refund%'")
    assert row["n"] == 0


async def test_completed_straight_from_submitted_is_allowed_and_final(services, repos, db, user, super_admin, mock_service, mock_client) -> None:
    """مزود سريع: Completed مباشرة بلا Processing ⇒ مقبول، ونهائي لا رجعة منه."""
    await _fund(services, user, super_admin)
    order = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000)
    await services.orders.process_pending_orders()
    pid = (await repos.orders.get(order.id)).provider_order_id
    mock_client.advance(pid, to="Completed")
    await _due(db, order.id)
    await services.orders.process_due_orders()
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED
    mock_client.advance(pid, to="In progress")                                   # مزود يعيد حالة أقدم بالخطأ
    await _due(db, order.id)
    await services.orders.process_due_orders()
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED


async def test_malformed_callback_data_is_an_unknown_button_not_an_error(bot, context, user) -> None:  # noqa: F811
    """callback_data تالفة (zzz/-) تصل لـunknown_callback ⇒ رد لطيف لا استثناء (انحدار أُصلح أثناء البند 14)."""
    await load_user(bot, context, user)
    for data in ("zzz", "-", "flow", "x:y:z:1"):
        await press(bot, context, fallbacks.unknown_callback, data, user.telegram_id)
    assert not any("Traceback" in (m.text or "") for m in bot.sent)
