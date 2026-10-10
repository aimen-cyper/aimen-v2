"""
اختبار القبول النهائي للمرحلة 2 — الدورة الكاملة كما طلبها المالك:

    تسجيل → تصفح → طلب → شحن → اعتماد → خصم → إرسال للمزود → متابعة آلية
    → إكمال → إشعار → سجل → إحصائيات

والمسار البديل:

    فشل المزود → استرجاع آمن → حركة مالية → إشعار المستخدم والأدمن

كل خطوة هنا تمرّ عبر الخدمات الحقيقية ولا شيء فيها وهمي إلا واجهة المزود
(`MockProviderClient`) وواجهة إرسال رسائل تيليجرام (`CollectingSender`)، لأن
الاثنين شبكة خارجية.
"""

from __future__ import annotations

import pytest

from core.enums import (
    FINAL_ORDER_STATUSES,
    NotificationType,
    OrderStatus,
    PaymentStatus,
    TransactionType,
)
from core.exceptions import InsufficientBalanceError, ProviderPermanentError
from database.database import Database
from database.models import Service, User
from database.repositories import Repositories
from services import ServiceContainer
from utils.datetime_utils import iso_plus_seconds


class CollectingSender:
    """بديل واجهة تيليجرام: يجمع الرسائل المرسلة ليُتحقق منها في الاختبار."""

    def __init__(self) -> None:
        """تهيئة قائمة الرسائل المجمّعة."""
        self.messages: list[tuple[int, str, str]] = []

    async def __call__(self, telegram_id: int, title: str, message: str) -> int:
        """محاكاة إرسال رسالة وإرجاع معرف رسالة."""
        self.messages.append((telegram_id, title, message))
        return len(self.messages)

    def to(self, telegram_id: int) -> list[tuple[str, str]]:
        """كل ما وصل إلى مستخدم بعينه (عنوان، نص)."""
        return [(title, body) for chat_id, title, body in self.messages if chat_id == telegram_id]


async def _follow_until_final(
    services: ServiceContainer, repos: Repositories, order_id: int, *, rounds: int = 8
) -> None:
    """تشغيل حلقة المتابعة الآلية مع تقديم مواعيد الفحص حتى تستقر حالة الطلب."""
    for _ in range(rounds):
        order = await repos.orders.get(order_id)
        assert order is not None
        if order.status in FINAL_ORDER_STATUSES:
            return
        async with repos.db.transaction() as tx:
            await repos.orders.update_fields(tx, order_id, next_check_at=iso_plus_seconds(-10))
        await services.orders.process_due_orders()


# ======================================================================== #
#                         المسار الكامل الناجح                              #
# ======================================================================== #


async def test_full_happy_cycle_from_registration_to_statistics(
    services: ServiceContainer,
    db: Database,
    repos: Repositories,
    admin: User,
    super_admin: User,
    mock_service: Service,
    mock_client,
    payment_method,
) -> None:
    """الدورة الكاملة من /start حتى ظهور الطلب في الإحصائيات وسجلات التدقيق."""

    # 1) التسجيل — أول تفاعل مع البوت ينشئ الحساب برصيد صفر
    customer, created = await services.users.get_or_create(
        telegram_id=555000111, username="ClientOne", first_name="عميل"
    )
    assert created is True
    assert customer.balance_units == 0
    again, created_again = await services.users.get_or_create(telegram_id=555000111)
    assert created_again is False and again.id == customer.id

    # 2) التصفح — التصنيفات ثم خدمات التصنيف ثم التسعيرة
    categories = await services.catalog.categories()
    assert categories
    page = await services.catalog.services_page(categories[0].id)
    assert any(item.id == mock_service.id for item in page.items)
    chosen = await services.catalog.get_available_service(mock_service.id)
    quote = await services.catalog.quote(chosen, 1000)
    assert quote.cost_units == 10_000

    # 3) محاولة الطلب بلا رصيد — تُرفض ولا تترك أي أثر
    with pytest.raises(InsufficientBalanceError):
        await services.orders.create_order(
            customer, service_id=chosen.id, link="https://instagram.com/p/abc", quantity=1000
        )
    assert await repos.orders.count_by_user(customer.id) == 0

    # 4) الشحن — المستخدم يرسل إثبات تحويل
    payment = await services.payments.create_payment(
        customer,
        method_id=payment_method.id,
        raw_amount="5",
        transaction_reference="TRX-E2E-1",
        proof_file_id="proof-file",
        proof_file_type="photo",
    )
    assert payment.status == PaymentStatus.PENDING
    assert await services.wallet.balance_units(customer.id) == 0

    # 5) الاعتماد — الأدمن يعتمد فيُضاف الرصيد عبر المحفظة المركزية وحدها
    deposit_tx = await services.payments.approve(admin, payment.id)
    assert deposit_tx.type == TransactionType.DEPOSIT
    assert await services.wallet.balance_units(customer.id) == 50_000

    # 6) الطلب — الخصم يتم داخل نفس معاملة إنشاء الطلب
    order = await services.orders.create_order(
        customer, service_id=chosen.id, link="https://instagram.com/p/abc", quantity=1000
    )
    assert order.status == OrderStatus.PENDING
    assert order.cost_units == 10_000
    assert order.public_code == f"ORD-{order.id:06d}"
    assert await services.wallet.balance_units(customer.id) == 40_000

    # 7) الإرسال للمزود — مهمة الخلفية تلتقط الطلب وترسله
    batch = await services.orders.process_pending_orders()
    assert (batch.claimed, batch.succeeded, batch.failed) == (1, 1, 0)
    after_submit = await repos.orders.get(order.id)
    assert after_submit is not None
    assert after_submit.status == OrderStatus.SUBMITTED
    assert after_submit.provider_order_id is not None
    assert after_submit.provider_cost_units == 6_000
    assert mock_client.calls[0][0] == "add"

    # 8) المتابعة الآلية حتى الإكمال
    await _follow_until_final(services, repos, order.id)
    completed = await repos.orders.get(order.id)
    assert completed is not None
    assert completed.status == OrderStatus.COMPLETED
    assert completed.delivered_quantity == 1000
    assert completed.remains == 0
    assert completed.completed_at is not None

    # 9) الإشعارات — تصل فعلاً إلى تيليجرام عبر مهمة الإرسال
    sender = CollectingSender()
    report = await services.notifications.dispatch_pending(sender, limit=50)
    assert report.sent >= 3
    customer_titles = " | ".join(title for title, _ in sender.to(customer.telegram_id))
    assert "طلب" in customer_titles
    types = {item.type for item in await repos.notifications.list_for_user(customer.id)}
    assert {
        NotificationType.PAYMENT_APPROVED,
        NotificationType.ORDER_CREATED,
        NotificationType.ORDER_COMPLETED,
    } <= types
    assert await services.notifications.queued_count() == 0

    # 10) السجلات — حركات مالية متوازنة وسجل تدقيق لإجراء الأدمن
    movements = await repos.transactions.list_by_user(customer.id, limit=10)
    assert [item.type for item in movements] == [TransactionType.ORDER, TransactionType.DEPOSIT]
    ledger = await services.wallet.verify_ledger(customer.id)
    assert ledger.is_balanced
    assert ledger.stored_units == 40_000
    approve_logs = await services.audit.by_target("payment", payment.id)
    assert any(log.action == "payments.approve" and log.admin_id == admin.id for log in approve_logs)
    statuses = [row.to_status for row in await repos.orders.history(order.id)]
    assert statuses[0] == OrderStatus.PENDING
    assert OrderStatus.SUBMITTED in statuses
    assert statuses[-1] == OrderStatus.COMPLETED

    # 11) الإحصائيات — الدورة ظاهرة بأرقام حقيقية
    dashboard = await services.stats.dashboard(admin)
    assert dashboard.orders_today == 1
    assert dashboard.revenue_today_units == 10_000
    assert dashboard.orders_by_status.get(OrderStatus.COMPLETED) == 1

    financial = await services.stats.financial_report(super_admin, days=1)
    assert financial.deposits_units == 50_000
    assert financial.revenue_units == 10_000
    assert financial.refunds_units == 0
    assert financial.profit_units == 4_000          # 10000 مبيعات − 6000 تكلفة مزود

    operations = await services.stats.operations_report(admin, days=1)
    assert operations.total_orders == 1 and operations.completed == 1
    assert operations.success_rate == 100.0


# ======================================================================== #
#                      المسار البديل: فشل المزود                           #
# ======================================================================== #


async def test_provider_failure_cycle_refunds_and_alerts_everyone(
    services: ServiceContainer,
    db: Database,
    repos: Repositories,
    user: User,
    admin: User,
    mock_service: Service,
    mock_client,
) -> None:
    """فشل المزود ⇒ استرجاع كامل موثّق + إشعار المستخدم والأدمن + مال لا يضيع."""
    await services.wallet.adjust_balance(
        target=user, amount_units=60_000, admin=admin, reason="رصيد افتتاحي", credit=True
    )
    before = await services.wallet.balance_units(user.id)

    mock_client.always_fail_add = ProviderPermanentError("الخدمة غير موجودة لدى المزود")

    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/fail", quantity=1000
    )
    assert await services.wallet.balance_units(user.id) == before - 10_000

    await services.orders.process_pending_orders()

    failed = await repos.orders.get(order.id)
    assert failed is not None
    assert failed.status == OrderStatus.REFUNDED        # فشل ثم استرجاع كامل
    assert failed.refund_amount_units == 10_000
    assert failed.last_error

    # المال عاد كاملاً ومعه حركة مالية موثّقة ودفتر متوازن
    assert await services.wallet.balance_units(user.id) == before
    movements = await repos.transactions.list_by_user(user.id, limit=5)
    assert movements[0].type == TransactionType.REFUND
    assert movements[0].amount_units == 10_000
    assert movements[0].reference == f"refund:order:{order.id}"
    assert (await services.wallet.verify_ledger(user.id)).is_balanced

    # الخطأ مسجَّل للمتابعة الفنية
    errors = await repos.error_logs.list_recent(limit=10)
    assert any("فشل الطلب" in str(row["message"]) for row in errors)

    # إشعار المستخدم وتنبيه الأدمن — كلاهما يصل فعلاً
    sender = CollectingSender()
    await services.notifications.dispatch_pending(sender, limit=50)
    user_inbox = await repos.notifications.list_for_user(user.id)
    user_types = {item.type for item in user_inbox}
    assert NotificationType.ORDER_FAILED in user_types
    failure_text = " ".join(item.message for item in user_inbox if item.type == NotificationType.ORDER_FAILED)
    assert "استرجاع" in failure_text or "أُعيد" in failure_text, "رسالة الفشل يجب أن تُطمئن المستخدم بعودة المبلغ"
    assert sender.to(user.telegram_id)
    assert sender.to(admin.telegram_id), "يجب تنبيه الأدمن بفشل المزود"

    # لا إعادة إرسال للطلب الفاشل مهما تكررت دورات المعالجة
    assert (await services.orders.process_pending_orders()).claimed == 0
    await _follow_until_final(services, repos, order.id, rounds=3)
    still = await repos.orders.get(order.id)
    assert still is not None and still.status == OrderStatus.REFUNDED
    assert await services.wallet.balance_units(user.id) == before


async def test_cycle_survives_restart_without_losing_or_duplicating_money(
    services: ServiceContainer,
    db: Database,
    repos: Repositories,
    user: User,
    admin: User,
    mock_service: Service,
    mock_client,
) -> None:
    """سقوط البوت أثناء الإرسال: لا طلب مكرر لدى المزود ولا مال ضائع."""
    await services.wallet.adjust_balance(
        target=user, amount_units=100_000, admin=admin, reason="رصيد", credit=True
    )
    await services.settings.set("duplicate_order_window_minutes", 0)

    orders = [
        await services.orders.create_order(
            user, service_id=mock_service.id, link=f"https://instagram.com/p/{index}", quantity=1000
        )
        for index in range(3)
    ]

    # محاكاة الانقطاع: طلب عالق في "جاري الإرسال" بلا رقم لدى المزود
    async with db.transaction() as tx:
        await repos.orders.update_fields(
            tx, orders[0].id, status=OrderStatus.SUBMITTING,
            locked_by="worker-crashed", locked_until=iso_plus_seconds(-30),
        )

    recovered = await services.orders.recover_after_restart()
    assert recovered["uncertain"] == 1
    stuck = await repos.orders.get(orders[0].id)
    assert stuck is not None and stuck.status == OrderStatus.SUBMIT_UNCERTAIN

    # بقية الطلبات تُستأنف طبيعياً، والطلب غير المؤكد لا يُرسل تلقائياً أبداً
    batch = await services.orders.process_pending_orders()
    assert batch.claimed == 2 and batch.succeeded == 2
    await _follow_until_final(services, repos, orders[1].id)
    await _follow_until_final(services, repos, orders[2].id)

    add_calls = [call for call in mock_client.calls if call[0] == "add"]
    assert len(add_calls) == 2
    assert {call[1]["link"] for call in add_calls} == {
        "https://instagram.com/p/1", "https://instagram.com/p/2"
    }

    # الأدمن نُبِّه للطلب غير المؤكد ليحسمه يدوياً
    admin_inbox = await repos.notifications.list_for_user(admin.id)
    assert any("مؤكد" in (item.title or "") or "مؤكد" in (item.message or "") for item in admin_inbox)

    # الحسم اليدوي: الأدمن يؤكد أن المزود لم يستلم الطلب ⇒ استرجاع كامل
    refunded_units = await services.orders.admin_mark_failed(
        admin, orders[0].id, "تأكدنا من المزود: الطلب لم يصله"
    )
    assert refunded_units == 10_000
    resolved = await repos.orders.get(orders[0].id)
    assert resolved is not None and resolved.status == OrderStatus.REFUNDED

    # المحصلة النهائية: دفتر متوازن، ولا مال مفقود ولا مضاعف
    ledger = await services.wallet.verify_ledger(user.id)
    assert ledger.is_balanced
    final_orders = await services.orders.list_for_user(user)
    spent = sum(order.cost_units - order.refund_amount_units for order in final_orders)
    assert await services.wallet.balance_units(user.id) == 100_000 - spent
    assert spent == 20_000
