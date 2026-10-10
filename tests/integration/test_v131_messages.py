"""
اختبارات الانحدار v1.3.1 — تحديث الرسائل (بند 4): R11 · R12 · R13 · E1.

كل شيء Mock: `FakeBot` بدل تيليجرام، وعميل Perfect Panel بنقل httpx وهمي. لا شبكة ولا مزود حقيقي.
"""

from __future__ import annotations

import pytest
from telegram.error import BadRequest, TimedOut

from core.enums import OrderStatus
from jobs.telegram_sender import TelegramNotificationSender
from keyboards.callback_data import pack
from tests.integration.test_phase14_statuses import LINK, _check, _submitted, panel  # noqa: F401
from tests.integration.test_user_interface import load_user, press
from tests.telegram_fakes import FakeBot, FakeContext

try:                                    # على v1.3.0 الأصلية لا وجود له ⇒ تفشل الاختبارات المعتمدة عليه فرادى لا عند التجميع
    from jobs.telegram_sender import TelegramMessageEditor
except ImportError:                     # pragma: no cover
    TelegramMessageEditor = None        # type: ignore[assignment,misc]

pytestmark = pytest.mark.asyncio

DONE = {"status": "Completed", "remains": "0", "start_count": "0", "charge": "0.5", "currency": "USD"}


@pytest.fixture
def bot() -> FakeBot:
    return FakeBot()


@pytest.fixture
def context(bot, services) -> FakeContext:
    return FakeContext(bot, services)


async def test_r11_edit_failure_never_touches_order_status_and_is_retried(services, repos, db, user, super_admin, mock_service, panel, bot) -> None:
    """R11: فشل تعديل الرسالة لا يغيّر `orders.status` (محفوظ مسبقاً)، ويُعاد لاحقاً حتى ينجح."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    assert await services.order_messages.register(order_id=order.id, kind="user_confirm", chat_id=555, message_id=77)
    editor = TelegramMessageEditor(bot)

    panel.status_payload = DONE
    await _check(services, db, order.id)                              # الحالة تتحدث في القاعدة أولاً
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED

    bot.fail("edit", TimedOut("slow"), times=1)
    report = await services.order_messages.refresh_due(editor)
    assert report.retried == 1 and report.edited == 0
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED            # لم تُمَس
    ref = await repos.order_message_refs.get(order.id, "user_confirm")
    assert ref.fail_count == 1 and not ref.is_dead and ref.rendered_status == OrderStatus.SUBMITTED

    async with db.transaction() as tx:                                # يحين موعد إعادة المحاولة
        await tx.execute("UPDATE order_message_refs SET next_try_at = NULL WHERE id = ?", (ref.id,))
    report = await services.order_messages.refresh_due(editor)
    assert report.edited == 1
    ref = await repos.order_message_refs.get(order.id, "user_confirm")
    assert ref.fail_count == 0 and ref.rendered_status == OrderStatus.COMPLETED
    edit = bot.last
    assert edit.kind == "edit" and "مكتمل" in edit.text and any(b.startswith("ord:view") for b in edit.buttons)
    assert (await services.order_messages.refresh_due(editor)).claimed == 0              # لا تعديل مكرر


async def test_r11b_deleted_message_stops_only_that_reference(services, repos, db, user, super_admin, mock_service, panel, bot) -> None:
    """رسالة محذوفة ⇒ يتوقف مرجعها وحده، والحالة والمال لا يتأثران."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    await services.order_messages.register(order_id=order.id, kind="user_confirm", chat_id=555, message_id=77)
    panel.status_payload = DONE
    await _check(services, db, order.id)
    bot.fail("edit", BadRequest("Message to edit not found"), times=1)
    report = await services.order_messages.refresh_due(TelegramMessageEditor(bot))
    assert report.dead == 1
    assert (await repos.order_message_refs.get(order.id, "user_confirm")).is_dead == 1
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED


async def test_r11c_not_modified_counts_as_success(services, repos, db, user, super_admin, mock_service, panel, bot) -> None:
    """«message is not modified» ليس خطأً: المرجع يُعتبر محدَّثاً."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    await services.order_messages.register(order_id=order.id, kind="user_confirm", chat_id=555, message_id=77)
    panel.status_payload = DONE
    await _check(services, db, order.id)
    bot.fail("edit", BadRequest("Bad Request: message is not modified"), times=1)
    assert (await services.order_messages.refresh_due(TelegramMessageEditor(bot))).edited == 1


async def test_r11d_navigation_releases_the_reference(services, repos, db, user, super_admin, mock_service, panel, bot, context) -> None:
    """المستخدم تنقّل داخل الرسالة نفسها ⇒ لا نكتب فوق شاشته (يُوقَف المرجع)."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    await load_user(bot, context, user)
    await services.order_messages.register(order_id=order.id, kind="user_confirm", chat_id=user.telegram_id, message_id=555)
    from handlers.user import orders as order_handlers
    await press(bot, context, order_handlers.order_card_screen, pack("ord", "view", order.id, "all", 1), user.telegram_id)
    assert (await repos.order_message_refs.get(order.id, "user_confirm")).is_dead == 1


async def test_r12_orders_log_post_waits_for_destination_and_is_not_lost(services, repos, db, user, super_admin, mock_service, panel, bot) -> None:
    """R12: منشور القناة بلا وجهة يبقى بالطابور، يُنشر بعد ضبطها، ثم يُعدَّل عند اكتمال الطلب."""
    sender = TelegramNotificationSender(bot)
    await services.wallet.adjust_balance(target=user, amount_units=100_000, admin=super_admin, reason="رصيد", credit=True)
    order = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000)
    post = await repos.channel_outbox.get_by_dedupe(f"order:{order.id}")
    assert post is not None and post.status == "queued"

    report = await services.channels.flush(sender, on_sent=services.order_messages.on_channel_post_sent)
    assert report.retried == 1 and report.skipped == 0 and not bot.sent
    waiting = await repos.channel_outbox.get_by_dedupe(f"order:{order.id}")
    assert waiting.status == "queued" and "بانتظار الوجهة" in (waiting.last_error or "")

    await services.settings.set("orders_log_chat_id", "-1003000000001", admin_id=super_admin.id)
    await services.channels.requeue_failed("orders_log")
    report = await services.channels.flush(sender, on_sent=services.order_messages.on_channel_post_sent)
    assert report.sent == 1 and bot.last.kind == "send"
    ref = await repos.order_message_refs.get(order.id, "channel_post")
    assert ref is not None and ref.chat_id == "-1003000000001"

    await services.orders.process_pending_orders()                    # الإرسال للمزود
    panel.status_payload = DONE
    await _check(services, db, order.id)
    report = await services.order_messages.refresh_due(TelegramMessageEditor(bot))
    assert report.edited == 1 and bot.last.kind == "edit" and "اكتمل التنفيذ" in bot.last.text
    assert "private" not in bot.last.text and "100200300" not in bot.last.text           # لا تسريب بعد التعديل


async def test_r12b_failed_post_is_requeued_when_destination_is_fixed(services, repos, db, super_admin, bot) -> None:
    """منشور فشل نهائياً بسبب وجهة خاطئة يعود للطابور تلقائياً عند تعديل الوجهة (لا يضيع)."""
    async with db.transaction() as tx:
        await services.channels.enqueue(tx, kind="orders_log", title="t", message="m", dedupe_key="order:9999")
    await services.settings.set("orders_log_chat_id", "-1003000000009", admin_id=super_admin.id)
    sender = TelegramNotificationSender(bot)
    bot.fail("send", BadRequest("Chat not found"), times=1)
    report = await services.channels.flush(sender)
    assert report.failed == 1
    assert (await repos.channel_outbox.get_by_dedupe("order:9999")).status == "failed"

    await services.settings.set("orders_log_chat_id", "-1003000000010", admin_id=super_admin.id)
    assert await services.channels.requeue_failed("orders_log") == 1
    assert (await services.channels.flush(sender)).sent == 1


async def test_r12c_post_older_than_ttl_is_finally_skipped(services, repos, db, super_admin, bot) -> None:
    """بعد `channel_post_ttl_hours` بلا وجهة يُتخطّى (لا طابور أبدي)."""
    async with db.transaction() as tx:
        await services.channels.enqueue(tx, kind="orders_log", title="t", message="m", dedupe_key="order:8888")
        await tx.execute("UPDATE channel_outbox SET created_at = '2020-01-01T00:00:00.000Z' WHERE dedupe_key='order:8888'")
    report = await services.channels.flush(TelegramNotificationSender(bot))
    assert report.skipped == 1
    assert (await repos.channel_outbox.get_by_dedupe("order:8888")).status == "skipped"


async def test_r13_user_card_has_refresh_provider_progress_and_last_update(services, repos, db, user, super_admin, mock_service, panel, bot, context) -> None:
    """R13: بطاقة المستخدم: زر تحديث + منفَّذ محسوب من remains + «آخر تحديث» (v1.3.0: لا زر ولا آخر تحديث، والمنفَّذ 0)."""
    from handlers.user import orders as order_handlers
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.status_payload = {"status": "In progress", "remains": "700", "start_count": "0", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id)
    await load_user(bot, context, user)
    await press(bot, context, order_handlers.order_card_screen, pack("ord", "view", order.id, "all", 1), user.telegram_id)
    text = bot.last.text
    assert "المنفَّذ: 300" in text and "المتبقي: 700" in text
    assert "آخر تحديث" in text
    assert any(b.startswith("ord:view") for b in bot.last.buttons) and "🔄 تحديث" in bot.last.labels


async def test_order_notifications_carry_view_button_and_creation_notice_is_registered(services, repos, db, user, super_admin, mock_service, panel, bot) -> None:
    """إشعارات الطلب تحمل «📦 عرض الطلب»، وإشعار الإنشاء يُسجَّل مرجعاً ليتجدد."""
    await services.wallet.adjust_balance(target=user, amount_units=100_000, admin=super_admin, reason="رصيد", credit=True)
    order = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000)
    await services.notifications.dispatch_pending(TelegramNotificationSender(bot))
    sent = [m for m in bot.sent if m.kind == "send" and m.chat_id == user.telegram_id]
    assert sent and all(any(b.startswith("ord:view") for b in m.buttons) for m in sent)
    assert (await repos.order_message_refs.get(order.id, "user_notice")) is not None


async def test_e1_refund_after_failure_notifies_user_instead_of_being_deduped(services, repos, db, user, super_admin, mock_service) -> None:
    """E1: استرجاع يدوي بعد فشل بلا استرجاع تلقائي ⇒ إشعار «استرجاع» (v1.3.0: يُبتلع بمفتاح ORDER_FAILED المكرر)."""
    await services.wallet.adjust_balance(target=user, amount_units=100_000, admin=super_admin, reason="رصيد", credit=True)
    await services.settings.set("auto_refund_on_provider_fail", "false", admin_id=super_admin.id)
    order = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000)
    await services.orders._fail_order(order, reason="فشل اختبار")                  # فشل بلا استرجاع
    assert (await repos.orders.get(order.id)).status == OrderStatus.FAILED
    refunded = await services.orders.admin_mark_failed(super_admin, order.id, "استرجاع يدوي بعد المراجعة")
    assert refunded == order.cost_units
    rows = await db.fetchall("SELECT type FROM notifications WHERE user_id=?", (user.id,))
    assert "order_refunded" in {row["type"] for row in rows}


class _SlowClock:
    """ساعة مزيّفة: كل قراءة تقدّم الزمن `step` ثانية (تحاكي إرسالاً بطيئاً دون نوم حقيقي)."""

    def __init__(self, step: float) -> None:
        self.now = 0.0
        self.step = step

    def __call__(self) -> float:
        self.now += self.step
        return self.now


async def test_e2_dispatch_round_has_a_time_budget_and_leftovers_are_not_lost(services, repos, db, user, bot) -> None:
    """E2/WP7: الجولة البطيئة تتوقف عند الميزانية، وما تبقّى يعود للطابور فوراً ويُرسل في الجولة التالية."""
    async with db.transaction() as tx:
        for index in range(6):
            await services.notifications.enqueue(
                tx, user_id=user.id, type="system", title="t", message=f"m{index}", dedupe_key=f"e2:{index}"
            )
    sender = TelegramNotificationSender(bot)
    report = await services.notifications.dispatch_pending(sender, budget_seconds=25, clock=_SlowClock(10))
    assert report.sent < 6 and report.deferred == 6 - report.sent and report.sent >= 1
    # لا انتظار lease: الجولة التالية تلتقط الباقي مباشرة (v1.3.0: لا ميزانية، 6 × مهلة شبكة في جولة واحدة)
    again = await services.notifications.dispatch_pending(sender)
    assert report.sent + again.sent == 6 and again.deferred == 0


async def test_e2b_channel_flush_budget(services, repos, db, super_admin, bot) -> None:
    """نفس الميزانية على صندوق القنوات."""
    await services.settings.set("orders_log_chat_id", "-1003000000001", admin_id=super_admin.id)
    async with db.transaction() as tx:
        for index in range(4):
            await services.channels.enqueue(tx, kind="orders_log", title="t", message=f"m{index}", dedupe_key=f"order:{7000 + index}")
    sender = TelegramNotificationSender(bot)
    first = await services.channels.flush(sender, budget_seconds=15, clock=_SlowClock(10))
    assert first.deferred >= 1 and first.sent + first.deferred == 4
    second = await services.channels.flush(sender)
    assert first.sent + second.sent == 4
