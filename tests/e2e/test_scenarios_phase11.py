"""
المرحلة 11 — مصفوفة السيناريوهات الشاملة (رحلات متعددة الخطوات عبر الخدمات الحقيقية).

(قائمة «البند 39» الأصلية غير متاحة، فالسيناريوهات مشتقّة من DoD والمخاطر R والقرارات A/D.)

كل سيناريو يتحقق من الأثر الكامل: الحالة · المال (الدفتر) · الإشعارات · التدقيق · عدم تكرار الإرسال.

    S1  R1  نتيجة إرسال غير مؤكدة ⇒ لا إعادة إرسال ⇒ الأدمن يحسم ⇒ استرجاع كامل
    S2  D5  رصيد المزود غير كافٍ ⇒ انتظار ⇒ نجاح بعد الشحن
    S3  D5  رصيد المزود غير كافٍ ⇒ تجاوز المهلة ⇒ فشل + استرجاع تلقائي
    S4  A8  تنفيذ جزئي ⇒ استرجاع الباقي فقط
    S5  D11 إلغاء قبل الإرسال ينجح، وبعده يُرفض بلا استرجاع
    S6  A10 انتهاء دفعة ⇒ لا يمكن اعتمادها لاحقاً ولا إيداع
    S7      مستخدم محظور: لا طلبات جديدة، والطلب الجاري يكتمل
    S8      وضع الصيانة: يمنع المستخدم ويستثني الأدمن، والطلب الجاري يكتمل
    S9  A12 قاطع الدائرة: تعطيل المزود بعد فشل متتالٍ ثم استئناف بلا فقد للطلبات
    S10 R8  رفض الصلاحيات (RBAC): لا أثر مالي ويُسجَّل حدث أمني
    S11 R12 اعتماد/رفض مزدوج لنفس الدفعة ⇒ إيداع واحد
    S12 R9  استرجاع تلقائي بعد فشل نهائي ⇒ مالياً صفر صافٍ وإشعار للمستخدم والأدمن
"""

from __future__ import annotations

import pytest

from core.enums import OrderStatus, PaymentStatus, TransactionType
from core.exceptions import (
    InvalidStateTransitionError,
    MaintenanceModeError,
    PermissionDeniedError,
    ProviderPermanentError,
    ProviderTemporaryError,
    ProviderUncertainError,
    SMMBotError,
    UserBannedError,
)
from database.database import Database
from database.models import Service, User
from services import ServiceContainer
from utils.datetime_utils import iso_plus_seconds

pytestmark = pytest.mark.asyncio

LINK = "https://instagram.com/scenario"


class Inbox:
    """مرسل إشعارات يجمع ما يصل لكل محادثة."""

    def __init__(self) -> None:
        """قائمة الرسائل."""
        self.messages: list[tuple[int, str, str]] = []

    async def __call__(self, telegram_id: int, title: str, message: str) -> int:
        """تسجيل رسالة."""
        self.messages.append((telegram_id, title, message))
        return len(self.messages)

    def text_for(self, telegram_id: int) -> str:
        """كل ما وصل لمحادثة معيّنة نصاً واحداً."""
        return "\n".join(f"{t}\n{m}" for chat, t, m in self.messages if chat == telegram_id)


async def _fund(services: ServiceContainer, user: User, super_admin: User, units: int = 100_000) -> None:
    """شحن رصيد عبر المسار الرسمي."""
    await services.wallet.adjust_balance(target=user, amount_units=units, admin=super_admin, reason="رصيد", credit=True)


async def _order(services: ServiceContainer, user: User, service: Service, *, link: str = LINK, quantity: int = 1000):
    """إنشاء طلب."""
    return await services.orders.create_order(user, service_id=service.id, link=link, quantity=quantity)


async def _due(db: Database, order_id: int) -> None:
    """تقديم موعد الفحص/المحاولة."""
    async with db.transaction() as tx:
        await tx.execute("UPDATE orders SET next_check_at = ? WHERE id = ?", (iso_plus_seconds(-30), order_id))


async def _ledger_ok(services: ServiceContainer, *users: User) -> None:
    """الدفتر متوازن والرصيد غير سالب."""
    for user in users:
        check = await services.wallet.verify_ledger(user.id)
        assert check.is_balanced and check.stored_units >= 0


# ----------------------------------- S1 ----------------------------------- #


async def test_s1_uncertain_submit_no_resend_then_admin_refunds(
    services, repos, db, user, admin, super_admin, mock_service, mock_client
) -> None:
    """S1: غموض الإرسال لا يُعاد إرساله أبداً، وحسم الأدمن يُرجع المال مرة واحدة."""
    await _fund(services, user, super_admin)
    order = await _order(services, user, mock_service)
    mock_client.always_fail_add = ProviderUncertainError("انتهت المهلة")
    await services.orders.process_pending_orders()
    mock_client.always_fail_add = None                      # حتى لو عاد المزود سليماً لا نعيد الإرسال

    for _ in range(3):
        await _due(db, order.id)
        await services.orders.process_pending_orders()
        await services.orders.process_due_orders()
    adds = [c for c in mock_client.calls if c[0] == "add"]
    assert len(adds) == 1, "أُعيد إرسال طلب غير مؤكد"
    assert (await repos.orders.get(order.id)).status == OrderStatus.SUBMIT_UNCERTAIN
    assert await services.wallet.balance_units(user.id) == 90_000

    refunded = await services.orders.admin_mark_failed(admin, order.id, "تأكدنا من لوحة المزود")
    assert refunded == 10_000 and await services.wallet.balance_units(user.id) == 100_000
    with pytest.raises(InvalidStateTransitionError):
        await services.orders.admin_mark_failed(admin, order.id, "مرة ثانية")
    assert await services.wallet.balance_units(user.id) == 100_000
    audit = await db.fetchall("SELECT 1 FROM audit_logs WHERE action = 'orders.refund' AND target_id = ?", (order.id,))
    assert len(audit) == 1
    inbox = Inbox()
    await services.notifications.dispatch_pending(inbox, limit=100)
    assert inbox.text_for(user.telegram_id), "لم يُبلَّغ المستخدم بنتيجة الحسم"
    await _ledger_ok(services, user)


# --------------------------------- S2 / S3 --------------------------------- #


async def test_s2_provider_out_of_funds_waits_then_succeeds_after_topup(
    services, repos, db, user, admin, super_admin, mock_service, mock_client
) -> None:
    """S2: رصيد المزود غير كافٍ ⇒ يبقى pending دون خصم مضاعف، وينفَّذ بعد شحن المزود."""
    await _fund(services, user, super_admin)
    order = await _order(services, user, mock_service)
    mock_client.balance_units = 0
    report = await services.orders.process_pending_orders()
    assert report.succeeded == 0
    current = await repos.orders.get(order.id)
    assert current.status == OrderStatus.PENDING and current.refund_amount_units == 0
    assert await services.wallet.balance_units(user.id) == 90_000
    assert await repos.notifications.count_queued() >= 1, "يجب تنبيه الأدمن برصيد المزود"

    mock_client.balance_units = 1_000_000                   # الأدمن شحن حساب المزود
    await _due(db, order.id)
    await services.orders.process_pending_orders()
    done = await repos.orders.get(order.id)
    assert done.status in (OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS) and done.provider_order_id
    assert len(await repos.transactions.list_by_order(order.id)) == 1      # خصم واحد فقط
    await _ledger_ok(services, user)


async def test_s3_provider_out_of_funds_past_deadline_fails_and_refunds(
    services, repos, db, user, admin, super_admin, mock_service, mock_client
) -> None:
    """S3: بعد المهلة القصوى يفشل الطلب ويُسترجع المبلغ كاملاً مرة واحدة."""
    await _fund(services, user, super_admin)
    order = await _order(services, user, mock_service)
    mock_client.balance_units = 0
    async with db.transaction() as tx:                      # عمر الطلب 7 ساعات > مهلة 6 ساعات
        await tx.execute("UPDATE orders SET created_at = ? WHERE id = ?", (iso_plus_seconds(-7 * 3600), order.id))
    await services.orders.process_pending_orders()
    current = await repos.orders.get(order.id)
    assert current.status in (OrderStatus.FAILED, OrderStatus.REFUNDED)
    assert current.refund_amount_units == 10_000
    assert await services.wallet.balance_units(user.id) == 100_000
    refunds = [t for t in await repos.transactions.list_by_order(order.id) if t.type == TransactionType.REFUND]
    assert len(refunds) == 1
    await _ledger_ok(services, user)


# ----------------------------------- S4 ----------------------------------- #


async def test_s4_partial_refunds_only_the_remaining_quantity(
    services, repos, db, user, super_admin, mock_service, mock_client
) -> None:
    """S4: تسليم 250 من 1000 ⇒ استرجاع 75% فقط، وإعادة الفحص لا تكرر الاسترجاع."""
    await _fund(services, user, super_admin)
    order = await _order(services, user, mock_service)
    await services.orders.process_pending_orders()
    pid = (await repos.orders.get(order.id)).provider_order_id
    mock_client.advance(pid, to="Partial", delivered=250)
    for _ in range(3):
        await _due(db, order.id)
        await services.orders.process_due_orders()
    final = await repos.orders.get(order.id)
    assert final.status == OrderStatus.PARTIAL and final.delivered_quantity == 250
    assert final.refund_amount_units == 7_500
    assert await services.wallet.balance_units(user.id) == 97_500
    await _ledger_ok(services, user)


# ----------------------------------- S5 ----------------------------------- #


async def test_s5_cancel_allowed_only_before_submission(
    services, repos, db, user, super_admin, mock_service, mock_client
) -> None:
    """S5: الإلغاء قبل الإرسال ⇒ استرجاع كامل؛ بعد الإرسال ⇒ رفض وبلا أي أثر مالي."""
    await _fund(services, user, super_admin)
    early = await _order(services, user, mock_service, link=LINK + "/a")
    assert await services.orders.cancel_by_user(user, early.id) == 10_000
    assert (await repos.orders.get(early.id)).status in (OrderStatus.CANCELED, OrderStatus.REFUNDED)

    late = await _order(services, user, mock_service, link=LINK + "/b")
    await services.orders.process_pending_orders()
    balance = await services.wallet.balance_units(user.id)
    with pytest.raises(InvalidStateTransitionError):
        await services.orders.cancel_by_user(user, late.id)
    assert await services.wallet.balance_units(user.id) == balance
    with pytest.raises(InvalidStateTransitionError):
        await services.orders.cancel_by_user(user, early.id)           # لا استرجاع مزدوج
    await _ledger_ok(services, user)


# ----------------------------------- S6 ----------------------------------- #


async def test_s6_expired_payment_cannot_be_approved(
    services, repos, db, user, admin, payment_method
) -> None:
    """S6: دفعة انتهت مهلتها ⇒ حالتها منتهية ولا إيداع عند محاولة اعتمادها."""
    payment = await services.payments.create_payment(
        user, method_id=payment_method.id, raw_amount="5", transaction_reference="EXP-1",
        proof_file_id="p", proof_file_type="photo",
    )
    async with db.transaction() as tx:
        await tx.execute("UPDATE payments SET expires_at = ? WHERE id = ?", (iso_plus_seconds(-5), payment.id))
    assert await services.payments.expire_due() >= 1
    with pytest.raises(SMMBotError):
        await services.payments.approve(admin, payment.id)
    assert (await repos.payments.get(payment.id)).status == PaymentStatus.EXPIRED
    assert await services.wallet.balance_units(user.id) == 0
    await _ledger_ok(services, user)


# --------------------------------- S7 / S8 --------------------------------- #


async def test_s7_banned_user_blocked_but_inflight_order_completes(
    services, repos, db, user, admin, super_admin, mock_service, mock_client
) -> None:
    """S7: الحظر يمنع الجديد، ولا يترك طلباً مدفوعاً معلّقاً بلا نهاية."""
    await _fund(services, user, super_admin)
    order = await _order(services, user, mock_service)
    await services.orders.process_pending_orders()
    await services.users.ban(admin, user.id, "مخالفة")
    banned = await repos.users.get_by_id(user.id)
    with pytest.raises(UserBannedError):
        await _order(services, banned, mock_service, link=LINK + "/new")
    for _ in range(4):
        await _due(db, order.id)
        await services.orders.process_due_orders()
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED
    await _ledger_ok(services, user)


async def test_s8_maintenance_blocks_users_not_admins_and_inflight_continues(
    services, repos, db, user, admin, super_admin, mock_service, mock_client
) -> None:
    """S8: وضع الصيانة يوقف طلبات المستخدمين الجديدة فقط."""
    await _fund(services, user, super_admin)
    await _fund(services, admin, super_admin)
    order = await _order(services, user, mock_service)
    await services.orders.process_pending_orders()
    await services.settings.set("maintenance_mode", True, admin_id=super_admin.id)
    with pytest.raises(MaintenanceModeError):
        await _order(services, user, mock_service, link=LINK + "/m")
    assert (await _order(services, admin, mock_service, link=LINK + "/adm")).status == OrderStatus.PENDING
    for _ in range(4):
        await _due(db, order.id)
        await services.orders.process_due_orders()
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED
    await _ledger_ok(services, user, admin)


# ----------------------------------- S9 ----------------------------------- #


async def test_s9_circuit_breaker_pauses_provider_then_resumes_without_loss(
    services, repos, db, user, admin, super_admin, mock_service, mock_client
) -> None:
    """S9: بعد فشل متتالٍ يُعطَّل المزود مؤقتاً (لا مزيد من المحاولات) ثم يُستأنف بلا فقد."""
    await _fund(services, user, super_admin)
    threshold = await services.settings.get_int("provider_failure_threshold", 5)
    orders = [await _order(services, user, mock_service, link=f"{LINK}/cb{i}") for i in range(threshold + 2)]
    mock_client.always_fail_add = ProviderTemporaryError("انقطاع")
    for _ in range(threshold + 3):
        for o in orders:
            await _due(db, o.id)
        await services.orders.process_pending_orders(limit=50)
    provider_id = (await repos.orders.get(orders[0].id)).provider_id
    disabled = await repos.providers.get(provider_id)
    assert disabled.disabled_until, "لم يُعطَّل المزود بعد الفشل المتتالي"

    attempts = len([c for c in mock_client.calls if c[0] == "add"])
    for o in orders:
        await _due(db, o.id)
    await services.orders.process_pending_orders(limit=50)
    assert len([c for c in mock_client.calls if c[0] == "add"]) == attempts, "محاولات إرسال أثناء التعطيل"
    for o in orders:
        assert (await repos.orders.get(o.id)).refund_amount_units == 0, "استرجاع خاطئ بسبب فشل مؤقت"

    mock_client.always_fail_add = None                      # المزود عاد + انتهى التعطيل
    async with db.transaction() as tx:
        await tx.execute("UPDATE providers SET disabled_until = NULL, consecutive_failures = 0 WHERE id = ?", (provider_id,))
    for o in orders:
        await _due(db, o.id)
    await services.orders.process_pending_orders(limit=50)
    states = [(await repos.orders.get(o.id)).status for o in orders]
    assert all(s in (OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS) for s in states), states
    assert len({(await repos.orders.get(o.id)).provider_order_id for o in orders}) == len(orders)
    await _ledger_ok(services, user)


# ---------------------------------- S10 ---------------------------------- #


async def test_s10_rbac_denials_have_no_financial_effect(
    services, repos, db, user, admin, super_admin, mock_service, payment_method
) -> None:
    """S10: مستخدم عادي ودور دعم يحاولان عمليات إدارية ⇒ رفض + لا تغيير رصيد + حدث أمني."""
    support = (await services.users.get_or_create(telegram_id=930_001, username="sup", first_name="S"))[0]
    async with db.transaction() as tx:
        await tx.execute("UPDATE users SET role = 'support' WHERE id = ?", (support.id,))
    support = await repos.users.get_by_id(support.id)
    payment = await services.payments.create_payment(
        user, method_id=payment_method.id, raw_amount="5", transaction_reference="RB-1",
        proof_file_id="p", proof_file_type="photo",
    )
    for actor in (user, support):
        with pytest.raises(PermissionDeniedError):
            await services.payments.approve(actor, payment.id)
        with pytest.raises(PermissionDeniedError):
            await services.wallet.adjust_balance(target=user, amount_units=1_000_000, admin=actor, reason="x", credit=True)
        with pytest.raises(PermissionDeniedError):
            await services.backups.create(actor)
    assert await services.wallet.balance_units(user.id) == 0
    assert (await repos.payments.get(payment.id)).status == PaymentStatus.PENDING
    events = await db.fetchall("SELECT 1 FROM audit_logs WHERE action LIKE 'security.%'")
    assert len(events) >= 3, "الرفض لم يُسجَّل كحدث أمني"
    await _ledger_ok(services, user)


# ---------------------------------- S11 ---------------------------------- #


async def test_s11_double_approve_and_approve_then_reject_credit_once(
    services, repos, db, user, admin, super_admin, payment_method
) -> None:
    """S11: اعتماد مكرر أو رفض بعد الاعتماد لا يغيّر الرصيد."""
    payment = await services.payments.create_payment(
        user, method_id=payment_method.id, raw_amount="5", transaction_reference="DA-1",
        proof_file_id="p", proof_file_type="photo",
    )
    await services.payments.approve(admin, payment.id)
    with pytest.raises(SMMBotError):
        await services.payments.approve(super_admin, payment.id)
    with pytest.raises(SMMBotError):
        await services.payments.reject(admin, payment.id, "متأخر")
    assert await services.wallet.balance_units(user.id) == 50_000
    deposits = [t for t in await repos.transactions.list_by_user(user.id) if t.type == TransactionType.DEPOSIT]
    assert len(deposits) == 1
    await _ledger_ok(services, user)


# ---------------------------------- S12 ---------------------------------- #


async def test_s12_permanent_failure_refunds_and_notifies_user_and_admin(
    services, repos, db, user, admin, super_admin, mock_service, mock_client
) -> None:
    """S12: المسار البديل الكامل: رفض نهائي ⇒ استرجاع ⇒ حركة مالية ⇒ إشعار للمستخدم والأدمن."""
    await _fund(services, user, super_admin)
    order = await _order(services, user, mock_service)
    mock_client.always_fail_add = ProviderPermanentError("رابط غير صالح")
    await services.orders.process_pending_orders()
    final = await repos.orders.get(order.id)
    assert final.status in (OrderStatus.FAILED, OrderStatus.REFUNDED)
    assert await services.wallet.balance_units(user.id) == 100_000
    kinds = sorted(t.type for t in await repos.transactions.list_by_order(order.id))
    assert kinds == [TransactionType.ORDER, TransactionType.REFUND]
    inbox = Inbox()
    await services.notifications.dispatch_pending(inbox, limit=100)
    assert inbox.text_for(user.telegram_id), "لم يصل المستخدم إشعار"
    assert inbox.text_for(admin.telegram_id) or inbox.text_for(super_admin.telegram_id), "لم يصل الأدمن إشعار"
    await _ledger_ok(services, user)
