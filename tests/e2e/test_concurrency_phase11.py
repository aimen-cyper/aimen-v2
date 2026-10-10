"""
المرحلة 11 — اختبارات التزامن (Race Conditions) على الخدمات الحقيقية.

لماذا هذه الاختبارات؟
    بقية الاختبارات تشغّل العمليات واحدة تلو الأخرى، بينما الواقع: ضغطتان متزامنتان على «اعتماد»،
    أو مهمتا إرسال تعملان معاً، أو عميل ينقر «تأكيد» عشر مرات. أي ثغرة هنا = **مال يتكرر أو يضيع**.

المنهج: `asyncio.gather` على عمليات متنافسة + قاعدة بيانات حقيقية، ثم فحص ثوابت لا يجوز كسرها:
    • لا رصيد سالب أبداً · • كل عملية مالية تحدث مرة واحدة فقط · • الدفتر يطابق الرصيد
    • الطلب لا يُرسل للمزود أكثر من مرة.
"""

from __future__ import annotations

import asyncio

import pytest

from core.enums import OrderStatus, PaymentStatus, TransactionType
from database.database import Database
from database.models import Service, User
from database.repositories import Repositories
from services import ServiceContainer

pytestmark = pytest.mark.asyncio


async def _settle(results: list) -> tuple[list, list[BaseException]]:
    """فصل نتائج `gather(return_exceptions=True)` إلى ناجحة وفاشلة."""
    ok = [item for item in results if not isinstance(item, BaseException)]
    failed = [item for item in results if isinstance(item, BaseException)]
    return ok, failed


async def _fund(services: ServiceContainer, user: User, admin: User, units: int) -> None:
    """شحن رصيد عبر المحفظة المركزية (المسار الوحيد المسموح لتغيير الرصيد)."""
    await services.wallet.adjust_balance(target=user, amount_units=units, admin=admin, reason="رصيد اختبار", credit=True)


async def _slow_provider(mock_client, delay: float = 0.01) -> None:
    """جعل إرسال المزود يتأخر فعلاً (يفرض تداخل المهام المتزامنة بدل تنفيذها تسلسلياً بالصدفة)."""
    original = mock_client.add_order

    async def slow(**kwargs):
        await asyncio.sleep(delay)
        return await original(**kwargs)

    mock_client.add_order = slow


# ======================================================================== #
#                               الطلبات والرصيد                              #
# ======================================================================== #


async def test_concurrent_orders_never_overdraw_balance(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service,
) -> None:
    """10 طلبات متزامنة والرصيد يكفي 3 فقط ⇒ ينجح 3 بالضبط ولا رصيد سالب ولا طلب بلا خصم."""
    await _fund(services, user, admin, 30_000)
    await services.settings.set("duplicate_order_window_minutes", 0)

    results = await asyncio.gather(
        *[
            services.orders.create_order(
                user, service_id=mock_service.id, link=f"https://instagram.com/race{i}", quantity=1000
            )
            for i in range(10)
        ],
        return_exceptions=True,
    )
    ok, failed = await _settle(results)

    assert len(ok) == 3, f"نجح {len(ok)} طلباً والرصيد يكفي 3"
    assert len(failed) == 7
    assert await services.wallet.balance_units(user.id) == 0
    assert await repos.orders.count_by_user(user.id) == 3
    charges = [t for t in await repos.transactions.list_by_user(user.id, limit=50) if t.type == TransactionType.ORDER]
    assert len(charges) == 3
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


async def test_double_click_same_order_creates_one_order(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service,
) -> None:
    """نقرتان متزامنتان على «تأكيد» لنفس الطلب (نفس الرابط والكمية) ⇒ طلب واحد وخصم واحد."""
    await _fund(services, user, admin, 100_000)
    results = await asyncio.gather(
        *[
            services.orders.create_order(
                user, service_id=mock_service.id, link="https://instagram.com/p/same", quantity=1000
            )
            for _ in range(5)
        ],
        return_exceptions=True,
    )
    ok, _failed = await _settle(results)

    assert len(ok) == 1, "حماية الطلب المكرر لم تصمد تحت التزامن"
    assert await repos.orders.count_by_user(user.id) == 1
    assert await services.wallet.balance_units(user.id) == 90_000
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


async def test_concurrent_submitters_send_each_order_once(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service, mock_client,
) -> None:
    """4 مهام إرسال متزامنة على 6 طلبات ⇒ كل طلب يُرسل للمزود مرة واحدة (لا طلب مزدوج = لا خسارة)."""
    await _fund(services, user, admin, 500_000)
    await services.settings.set("duplicate_order_window_minutes", 0)
    for i in range(6):
        await services.orders.create_order(
            user, service_id=mock_service.id, link=f"https://instagram.com/sub{i}", quantity=1000
        )
    await _slow_provider(mock_client)

    await asyncio.gather(*[services.orders.process_pending_orders(worker=f"w{i}", limit=3) for i in range(4)])
    await services.orders.process_pending_orders(limit=10)      # ما فات المهام الأولى

    adds = [call for call in mock_client.calls if call[0] == "add"]
    assert len(adds) == 6, f"أُرسل {len(adds)} استدعاء إنشاء لـ6 طلبات"
    links = [call[1].get("link") for call in adds]
    assert len(set(links)) == 6, "رابط أُرسل مرتين للمزود"
    statuses = {o.status for o in await repos.orders.list_by_user(user.id, limit=20)}
    assert statuses == {OrderStatus.SUBMITTED}


async def test_concurrent_cancel_refunds_exactly_once(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service,
) -> None:
    """إلغاء المستخدم + إلغاء الأدمن + تعليم الفشل في اللحظة نفسها ⇒ استرجاع واحد فقط."""
    await _fund(services, user, admin, 50_000)
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/c", quantity=1000
    )
    assert await services.wallet.balance_units(user.id) == 40_000

    results = await asyncio.gather(
        services.orders.cancel_by_user(user, order.id),
        services.orders.cancel_by_user(user, order.id),
        services.orders.admin_cancel(admin, order.id, "اختبار تزامن"),
        services.orders.admin_mark_failed(admin, order.id, "اختبار تزامن"),
        return_exceptions=True,
    )
    ok, _failed = await _settle(results)

    assert len(ok) >= 1
    assert await services.wallet.balance_units(user.id) == 50_000, "استرجاع مكرر أو ناقص"
    refunds = [t for t in await repos.transactions.list_by_user(user.id, limit=50) if t.type == TransactionType.REFUND]
    assert len(refunds) == 1
    assert (await services.wallet.verify_ledger(user.id)).is_balanced
    final = await repos.orders.get(order.id)
    assert final is not None and final.refund_amount_units == 10_000


async def test_concurrent_due_checks_complete_order_once(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service, mock_client,
) -> None:
    """3 مهام متابعة متزامنة ⇒ الاكتمال والإشعار مرة واحدة."""
    await _fund(services, user, admin, 50_000)
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/d", quantity=1000
    )
    await services.orders.process_pending_orders()
    submitted = await repos.orders.get(order.id)
    assert submitted is not None and submitted.provider_order_id
    mock_client.advance(submitted.provider_order_id, to="Completed", delivered=1000)
    async with repos.db.transaction() as tx:
        await repos.orders.update_fields(tx, order.id, next_check_at="2000-01-01T00:00:00+00:00")

    await asyncio.gather(*[services.orders.process_due_orders(worker=f"c{i}") for i in range(3)])

    final = await repos.orders.get(order.id)
    assert final is not None and final.status == OrderStatus.COMPLETED
    completed_notes = [
        n for n in await repos.notifications.list_for_user(user.id) if n.type == "order_completed"
    ]
    assert len(completed_notes) == 1, "إشعار اكتمال مكرر"
    history = [row.to_status for row in await repos.orders.history(order.id)]
    assert history.count(OrderStatus.COMPLETED) == 1


# ======================================================================== #
#                                  المدفوعات                                 #
# ======================================================================== #


async def _pending_payment(services: ServiceContainer, user: User, method_id: int, ref: str = "TRX-RACE"):
    """إنشاء طلب شحن معلّق جاهز للمراجعة."""
    return await services.payments.create_payment(
        user, method_id=method_id, raw_amount="5", transaction_reference=ref,
        proof_file_id="proof", proof_file_type="photo",
    )


async def test_concurrent_approvals_credit_once(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, super_admin: User, payment_method,
) -> None:
    """5 اعتمادات متزامنة (أدمنان) لنفس الدفعة ⇒ رصيد يُضاف مرة واحدة وحركة إيداع واحدة (R12)."""
    payment = await _pending_payment(services, user, payment_method.id)

    results = await asyncio.gather(
        *[services.payments.approve(admin if i % 2 else super_admin, payment.id) for i in range(5)],
        return_exceptions=True,
    )
    ok, failed = await _settle(results)

    assert len(ok) == 1 and len(failed) == 4
    assert await services.wallet.balance_units(user.id) == 50_000
    deposits = [t for t in await repos.transactions.list_by_user(user.id, limit=20) if t.type == TransactionType.DEPOSIT]
    assert len(deposits) == 1
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


async def test_approve_and_reject_race_has_single_winner(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, super_admin: User, payment_method,
) -> None:
    """اعتماد ورفض في اللحظة نفسها ⇒ قرار واحد نهائي، ورصيد متسق مع القرار."""
    payment = await _pending_payment(services, user, payment_method.id, "TRX-RACE2")

    results = await asyncio.gather(
        services.payments.approve(admin, payment.id),
        services.payments.reject(super_admin, payment.id, "اختبار تزامن"),
        return_exceptions=True,
    )
    ok, _failed = await _settle(results)

    assert len(ok) == 1
    final = await repos.payments.get(payment.id)
    assert final is not None
    balance = await services.wallet.balance_units(user.id)
    if final.status == PaymentStatus.APPROVED:
        assert balance == 50_000
    else:
        assert final.status == PaymentStatus.REJECTED and balance == 0
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


async def test_same_transaction_reference_cannot_be_used_twice_concurrently(
    services: ServiceContainer, repos: Repositories, user: User, payment_method,
) -> None:
    """نفس رقم الحوالة من تسجيلين متزامنين (R5: احتيال مرجع مكرر) ⇒ دفعة واحدة فقط."""
    results = await asyncio.gather(
        *[_pending_payment(services, user, payment_method.id, "TRX-DUP") for _ in range(4)],
        return_exceptions=True,
    )
    ok, failed = await _settle(results)
    assert len(ok) == 1 and len(failed) == 3


async def test_concurrent_expiry_sweeps_expire_once(
    services: ServiceContainer, repos: Repositories, db: Database, user: User, payment_method,
) -> None:
    """3 مهام انتهاء صلاحية متزامنة ⇒ تنتهي الدفعة مرة واحدة ولا يتكرر الإشعار."""
    payment = await _pending_payment(services, user, payment_method.id, "TRX-EXP")
    async with db.transaction() as tx:
        await tx.execute("UPDATE payments SET expires_at = '2000-01-01T00:00:00+00:00' WHERE id = ?", (payment.id,))

    counts = await asyncio.gather(*[services.payments.expire_due() for _ in range(3)])

    assert sum(counts) == 1
    final = await repos.payments.get(payment.id)
    assert final is not None and final.status == PaymentStatus.EXPIRED
    assert await services.wallet.balance_units(user.id) == 0


# ======================================================================== #
#                              تسويات الأدمن اليدوية                         #
# ======================================================================== #


async def test_concurrent_manual_debits_cannot_overdraw(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, super_admin: User,
) -> None:
    """خصومات يدوية متزامنة تفوق الرصيد ⇒ لا رصيد سالب وكل خصم ناجح له حركة."""
    await _fund(services, user, super_admin, 100_000)

    results = await asyncio.gather(
        *[
            services.wallet.adjust_balance(
                target=user, amount_units=30_000, admin=admin, reason=f"تسوية {i}", credit=False
            )
            for i in range(10)
        ],
        return_exceptions=True,
    )
    ok, _failed = await _settle(results)

    balance = await services.wallet.balance_units(user.id)
    assert balance >= 0
    assert balance == 100_000 - 30_000 * len(ok)
    assert len(ok) <= 3
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


# ======================================================================== #
#                      حدود المستخدم تحت التزامن (Limits)                      #
# ======================================================================== #


async def test_pending_payments_limit_holds_under_concurrency(
    services: ServiceContainer, repos: Repositories, user: User, payment_method,
) -> None:
    """حد الطلبات المعلّقة (3) لا يُتجاوز بإرسال 8 طلبات شحن متزامنة بمراجع مختلفة."""
    results = await asyncio.gather(
        *[_pending_payment(services, user, payment_method.id, f"TRX-LIM-{i}") for i in range(8)],
        return_exceptions=True,
    )
    ok, _failed = await _settle(results)
    assert len(ok) == 3
    assert await repos.payments.count_pending_by_user(user.id) == 3


async def test_daily_order_limit_holds_under_concurrency(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service,
) -> None:
    """الحد اليومي للطلبات لا يُتجاوز بطلبات متزامنة."""
    await _fund(services, user, admin, 500_000)
    await services.settings.set("duplicate_order_window_minutes", 0)
    await services.settings.set("max_orders_per_day", 2)

    results = await asyncio.gather(
        *[
            services.orders.create_order(
                user, service_id=mock_service.id, link=f"https://instagram.com/day{i}", quantity=1000
            )
            for i in range(6)
        ],
        return_exceptions=True,
    )
    ok, _failed = await _settle(results)
    assert len(ok) == 2
    assert await repos.orders.count_by_user(user.id) == 2


async def test_same_client_request_id_returns_single_order(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service,
) -> None:
    """نفس مفتاح الطلب من 5 نداءات متزامنة ⇒ طلب واحد، والجميع يستلمون الطلب نفسه بلا أخطاء ولا خصم مكرر."""
    await _fund(services, user, admin, 100_000)
    results = await asyncio.gather(
        *[
            services.orders.create_order(
                user, service_id=mock_service.id, link="https://instagram.com/p/k", quantity=1000,
                client_request_id="req-fixed-1",
            )
            for _ in range(5)
        ],
        return_exceptions=True,
    )
    ok, failed = await _settle(results)
    assert not failed, failed
    assert {order.id for order in ok} == {ok[0].id}
    assert await services.wallet.balance_units(user.id) == 90_000


async def test_concurrent_first_start_registers_user_once(
    services: ServiceContainer, repos: Repositories,
) -> None:
    """ثلاث /start متزامنة من مستخدم جديد ⇒ حساب واحد، ومرة واحدة فقط «أُنشئ الآن»."""
    results = await asyncio.gather(
        *[services.users.get_or_create(telegram_id=424242, username="racer", first_name="R") for _ in range(3)],
        return_exceptions=True,
    )
    ok, failed = await _settle(results)
    assert not failed, failed
    assert sum(1 for _user, created in ok if created) == 1
    assert len({u.id for u, _c in ok}) == 1
    assert await repos.users.count_all() == 1


async def test_one_open_ticket_per_user_under_concurrency(
    services: ServiceContainer, repos: Repositories, user: User,
) -> None:
    """فتح 5 تذاكر متزامنة ⇒ تذكرة واحدة فقط (قاعدة «تذكرة مفتوحة واحدة لكل مستخدم»)."""
    results = await asyncio.gather(
        *[
            services.tickets.create_ticket(user, subject="مشكلة في الطلب", message="التفاصيل هنا كاملة", category="other")
            for _ in range(5)
        ],
        return_exceptions=True,
    )
    ok, _failed = await _settle(results)
    assert len(ok) == 1


# ======================================================================== #
#                         الإشعارات والإذاعة تحت التزامن                      #
# ======================================================================== #


class _Sender:
    """مرسل بطيء يسجّل كل رسالة (يفرض تداخل عاملي الإرسال)."""

    def __init__(self) -> None:
        """قائمة الرسائل المرسلة."""
        self.sent: list[tuple[int, str]] = []

    async def __call__(self, telegram_id: int, title: str, message: str) -> int:
        """تسجيل رسالة بعد تأخير قصير."""
        await asyncio.sleep(0.005)
        self.sent.append((telegram_id, title))
        return len(self.sent)


async def test_two_notification_dispatchers_never_double_send(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service,
) -> None:
    """عاملا إرسال إشعارات متزامنان ⇒ كل إشعار يصل مرة واحدة فقط (لا رسائل مكررة للعميل)."""
    await _fund(services, user, admin, 500_000)
    await services.settings.set("duplicate_order_window_minutes", 0)
    for i in range(5):
        await services.orders.create_order(
            user, service_id=mock_service.id, link=f"https://instagram.com/n{i}", quantity=1000
        )
    queued = await services.notifications.queued_count()
    assert queued >= 5
    sender = _Sender()

    await asyncio.gather(
        services.notifications.dispatch_pending(sender, limit=50),
        services.notifications.dispatch_pending(sender, limit=50),
        services.notifications.dispatch_pending(sender, limit=50),
    )
    await services.notifications.dispatch_pending(sender, limit=50)

    assert len(sender.sent) == queued, f"أُرسل {len(sender.sent)} من {queued} (تكرار أو فقد)"
    assert await services.notifications.queued_count() == 0


async def test_two_broadcast_workers_never_double_send(
    services: ServiceContainer, repos: Repositories, super_admin: User,
) -> None:
    """عاملا إذاعة متزامنان على 12 مستلماً ⇒ كل مستلم يصله النص مرة واحدة والعدّادات تطابق الواقع."""
    for index in range(12):
        await services.users.get_or_create(telegram_id=700_000 + index, username=f"b{index}", first_name="B")
    broadcast = await services.broadcasts.create(super_admin, text="رسالة جماعية", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    delivered: list[int] = []

    async def sender(telegram_id: int, text: str, media_file_id, media_type) -> int:
        """إرسال بطيء مسجَّل."""
        await asyncio.sleep(0.005)
        delivered.append(telegram_id)
        return len(delivered)

    for _ in range(4):
        await asyncio.gather(
            services.broadcasts.send_batch(sender, limit=4),
            services.broadcasts.send_batch(sender, limit=4),
        )
    final = await services.broadcasts.get(super_admin, broadcast.id)

    assert len(delivered) == len(set(delivered)), "مستلم وصلته الرسالة مرتين"
    assert final.status == "completed"
    assert final.sent_count == len(delivered)


async def test_concurrent_ticket_close_notifies_once(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
) -> None:
    """5 إغلاقات متزامنة لنفس التذكرة ⇒ إغلاق واحد وإشعار واحد للمستخدم."""
    ticket = await services.tickets.create_ticket(user, subject="موضوع", message="نص التذكرة", category="other")
    results = await asyncio.gather(*[services.tickets.close(admin, ticket.id, "تم") for _ in range(5)], return_exceptions=True)
    assert not [r for r in results if isinstance(r, BaseException)], results
    assert results.count(True) == 1
    inbox = await repos.notifications.list_for_user(user.id, limit=50)
    assert len([n for n in inbox if n.type == "ticket_closed"]) == 1, "إشعار الإغلاق تكرر أو فُقد"


async def test_concurrent_provider_creation_with_same_name_fails_cleanly(
    services: ServiceContainer, super_admin: User, repos: Repositories,
) -> None:
    """4 محاولات متزامنة لإنشاء مزود بنفس الاسم ⇒ واحد ينجح والبقية خطأ عربي مفهوم (لا IntegrityError خام)."""
    from core.exceptions import SMMBotError

    async def attempt():
        """محاولة إنشاء مزود."""
        return await services.providers.create_provider(
            super_admin, name="مزود متزامن", api_url="https://provider.example.com/api/v2", api_key="key-1234567890",
        )

    results = await asyncio.gather(*[attempt() for _ in range(4)], return_exceptions=True)
    successes = [r for r in results if not isinstance(r, BaseException)]
    failures = [r for r in results if isinstance(r, BaseException)]
    assert len(successes) == 1, results
    assert all(isinstance(f, SMMBotError) for f in failures), [type(f).__name__ for f in failures]


async def test_concurrent_payment_method_same_code_fails_cleanly(
    services: ServiceContainer, super_admin: User,
) -> None:
    """إنشاء طريقة شحن بنفس الكود 4 مرات متزامنة ⇒ واحدة تنجح والبقية خطأ تحقق عربي (لا IntegrityError)."""
    from core.exceptions import SMMBotError

    async def attempt():
        """محاولة إنشاء طريقة شحن."""
        return await services.payments.create_method(super_admin, name_ar="طريقة", code="dup_code")

    results = await asyncio.gather(*[attempt() for _ in range(4)], return_exceptions=True)
    failures = [r for r in results if isinstance(r, BaseException)]
    assert len(results) - len(failures) == 1, results
    assert all(isinstance(f, SMMBotError) for f in failures), [type(f).__name__ for f in failures]
