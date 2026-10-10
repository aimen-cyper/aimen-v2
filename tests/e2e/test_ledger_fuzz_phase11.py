"""
المرحلة 11 — اختبار عشوائي موجَّه (Randomized Stateful Fuzz) للثوابت المحاسبية.

الفكرة: بدل توقّع السيناريوهات يدوياً، نُشغّل مئات العمليات العشوائية (بذور ثابتة قابلة للإعادة)
من كل نوع — شحن/اعتماد/رفض/إلغاء/طلبات/فشل مزود/استرجاع جزئي/تسويات الأدمن/انتهاء صلاحية —
ثم نتحقق من ثوابت **لا يجوز كسرها مهما كان الترتيب**:

    I1  الرصيد المخزَّن = مجموع الحركات (لكل مستخدم) ولا رصيد سالب.
    I2  لكل طلب خصم واحد بقيمته بالضبط، ومجموع استرجاعاته = `refund_amount_units` ≤ التكلفة.
    I3  اتساق الحالة النهائية مع المبلغ المسترجع (مكتمل=0 · ملغى/مسترجع=كامل · جزئي=أقل من الكامل).
    I4  سجل الحالات سلسلة متصلة وكل انتقال مسموح في آلة الحالة.
    I5  لا طلبان بنفس رقم المزود، ولا طلب أُنشئ عند المزود أكثر من مرة.
    I6  كل دفعة معتمدة لها حركة إيداع واحدة بالضبط، والمرفوضة/المنتهية بلا حركة.
    I7  بعد «تصريف» الطلبات لا طلب عالق في `submitting`.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

import pytest

from core.enums import FINAL_ORDER_STATUSES, OrderStatus, PaymentStatus, TransactionType
from core.exceptions import (
    ProviderPermanentError,
    ProviderTemporaryError,
    ProviderUncertainError,
    SMMBotError,
)
from core.order_state import can_transition
from database.database import Database
from database.models import Service, User
from database.repositories import Repositories
from scripts import audit_ledger
from services import ServiceContainer
from utils.datetime_utils import iso_plus_seconds

pytestmark = pytest.mark.asyncio

SEEDS = (1, 7, 42, 2026)
STEPS = 70


class World:
    """حالة عالم الاختبار: المستخدمون والعدّادات وكل ما يلزم لتنفيذ عملية عشوائية."""

    def __init__(self, services, repos, db, users, admin, super_admin, mock_service, mock_client, rng) -> None:
        """تخزين الاعتماديات."""
        self.services, self.repos, self.db = services, repos, db
        self.users, self.admin, self.super_admin = users, admin, super_admin
        self.service, self.client, self.rng = mock_service, mock_client, rng
        self.counter = 0
        self.method_id: int | None = None

    def next(self) -> int:
        """رقم تسلسلي فريد للروابط والمراجع."""
        self.counter += 1
        return self.counter

    async def order_ids(self, *statuses: str) -> list[int]:
        """معرّفات الطلبات (كلها أو بحالات معينة)."""
        if statuses:
            marks = ",".join("?" for _ in statuses)
            rows = await self.db.fetchall(f"SELECT id FROM orders WHERE status IN ({marks})", statuses)
        else:
            rows = await self.db.fetchall("SELECT id FROM orders")
        return [int(r["id"]) for r in rows]

    async def pay_ids(self, status: str) -> list[int]:
        """معرّفات الدفعات بحالة معينة."""
        rows = await self.db.fetchall("SELECT id FROM payments WHERE status = ?", (status,))
        return [int(r["id"]) for r in rows]


# ------------------------------- العمليات العشوائية ------------------------------- #


async def act_deposit(w: World) -> None:
    """طلب شحن ثم (اعتماد | رفض | إلغاء المستخدم | تركه معلّقاً)."""
    user = w.rng.choice(w.users)
    payment = await w.services.payments.create_payment(
        user, method_id=w.method_id, raw_amount=str(w.rng.randint(1, 30)),
        transaction_reference=f"TRX-{w.next()}", proof_file_id="p", proof_file_type="photo",
    )
    choice = w.rng.random()
    if choice < 0.6:
        await w.services.payments.approve(w.admin, payment.id)
    elif choice < 0.8:
        await w.services.payments.reject(w.admin, payment.id, "مرفوض عشوائياً")
    elif choice < 0.9:
        await w.services.payments.cancel_by_user(user, payment.id)


async def act_order(w: World) -> None:
    """طلب جديد (قد يفشل لنقص الرصيد وهذا مقبول)."""
    user = w.rng.choice(w.users)
    await w.services.orders.create_order(
        user, service_id=w.service.id, link=f"https://instagram.com/fz{w.next()}",
        quantity=w.rng.choice([100, 500, 1000, 2500]),
    )


async def act_provider_hiccup(w: World) -> None:
    """برمجة فشل للإرسال القادم (مؤقت/نهائي/غير مؤكد)."""
    w.client.fail_next_add = w.rng.choice(
        [ProviderTemporaryError("انقطاع"), ProviderPermanentError("رفض"), ProviderUncertainError("مهلة")]
    )


async def act_submit(w: World) -> None:
    """مهمة الإرسال."""
    await w.services.orders.process_pending_orders(limit=w.rng.randint(1, 5))


async def act_provider_progress(w: World) -> None:
    """المزود يغيّر حالة طلب عنده (اكتمال/جزئي/إلغاء) ثم تعمل المتابعة الآلية."""
    live = [oid for oid in await w.order_ids(OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS)]
    if live:
        order = await w.repos.orders.get(w.rng.choice(live))
        if order and order.provider_order_id in w.client.orders:
            kind = w.rng.choice(["Completed", "Partial", "Canceled", "In progress"])
            delivered = w.rng.randint(0, order.quantity - 1) if kind == "Partial" else None
            w.client.advance(order.provider_order_id, to=kind, delivered=delivered)
    await _due_now(w)
    await w.services.orders.process_due_orders()


async def _due_now(w: World) -> None:
    """تقديم موعد الفحص لكل الطلبات النشطة."""
    async with w.db.transaction() as tx:
        await tx.execute(
            "UPDATE orders SET next_check_at = ? WHERE status IN ('submitted','in_progress')",
            (iso_plus_seconds(-30),),
        )


async def act_user_cancel(w: World) -> None:
    """إلغاء المستخدم لطلب منتظر."""
    pending = await w.order_ids(OrderStatus.PENDING)
    if pending:
        order = await w.repos.orders.get(w.rng.choice(pending))
        owner = next(u for u in w.users if u.id == order.user_id)
        await w.services.orders.cancel_by_user(owner, order.id)


async def act_admin_resolve(w: World) -> None:
    """الأدمن يحسم طلباً غير مؤكد أو يلغي/يُفشل طلباً غير نهائي."""
    pool = await w.order_ids(OrderStatus.SUBMIT_UNCERTAIN, OrderStatus.PENDING, OrderStatus.SUBMITTED)
    if not pool:
        return
    oid = w.rng.choice(pool)
    if w.rng.random() < 0.5:
        await w.services.orders.admin_cancel(w.admin, oid, "إلغاء إداري عشوائي")
    else:
        await w.services.orders.admin_mark_failed(w.admin, oid, "فشل مؤكد إدارياً")


async def act_adjust(w: World) -> None:
    """تسوية يدوية (إضافة/خصم) من الأدمن الأعلى."""
    user = w.rng.choice(w.users)
    await w.services.wallet.adjust_balance(
        target=user, amount_units=w.rng.randint(1, 50) * 1000, admin=w.super_admin,
        reason="تسوية عشوائية", credit=w.rng.random() < 0.6,
    )


async def act_expire(w: World) -> None:
    """انتهاء صلاحية دفعات معلّقة."""
    async with w.db.transaction() as tx:
        await tx.execute("UPDATE payments SET expires_at = ? WHERE status = 'pending'", (iso_plus_seconds(-10),))
    await w.services.payments.expire_due()


ACTIONS = [
    (act_deposit, 18), (act_order, 30), (act_provider_hiccup, 6), (act_submit, 14),
    (act_provider_progress, 14), (act_user_cancel, 4), (act_admin_resolve, 4), (act_adjust, 5), (act_expire, 2),
]


# ----------------------------------- الثوابت ----------------------------------- #


async def check_invariants(w: World) -> None:
    """فحص كل الثوابت المحاسبية والتشغيلية (I1…I6)."""
    services, repos, db = w.services, w.repos, w.db

    # I1 — الرصيد = الدفتر ولا سالب
    for user in w.users:
        check = await services.wallet.verify_ledger(user.id)
        assert check.is_balanced, f"اختلال محاسبي للمستخدم {user.id}: فرق {check.difference_units}"
        assert check.stored_units >= 0, f"رصيد سالب للمستخدم {user.id}: {check.stored_units}"

    provider_ids: dict[str, int] = {}
    for oid in await w.order_ids():
        order = await repos.orders.get(oid)
        assert order is not None
        txs = await services.wallet.order_transactions(oid)

        # I2 — خصم واحد بقيمة الطلب، ومجموع الاسترجاع = المسجَّل على الطلب
        charges = [t.amount_units for t in txs if t.type == TransactionType.ORDER]
        refunds = sum(t.amount_units for t in txs if t.type in (TransactionType.REFUND, TransactionType.PARTIAL_REFUND))
        assert charges == [order.cost_units], f"طلب {oid}: الخصومات {charges} والتكلفة {order.cost_units}"
        assert refunds == order.refund_amount_units, f"طلب {oid}: استرجاع الدفتر {refunds} ≠ {order.refund_amount_units}"
        assert 0 <= order.refund_amount_units <= order.cost_units

        # I3 — اتساق الحالة مع المبلغ المسترجع
        if order.status == OrderStatus.COMPLETED:
            assert order.refund_amount_units == 0, f"طلب {oid} مكتمل ومعه استرجاع"
        elif order.status in (OrderStatus.REFUNDED, OrderStatus.CANCELED):
            assert order.refund_amount_units == order.cost_units, f"طلب {oid} {order.status} باسترجاع ناقص"
        elif order.status == OrderStatus.PARTIAL:
            assert order.refund_amount_units < order.cost_units, f"طلب {oid} جزئي باسترجاع كامل"
        elif order.status not in FINAL_ORDER_STATUSES and order.status != OrderStatus.FAILED:
            assert order.refund_amount_units == 0, f"طلب {oid} غير منتهٍ ({order.status}) ومعه استرجاع"

        # I4 — سجل الحالات متصل ومسموح
        history = await repos.orders.history(oid)
        previous: str | None = None
        for row in history:
            assert row.from_status == previous, f"طلب {oid}: انقطاع في السجل عند {row.to_status}"
            if previous is not None:
                assert can_transition(previous, row.to_status), f"طلب {oid}: انتقال محظور {previous}→{row.to_status}"
            previous = row.to_status
        assert previous == order.status, f"طلب {oid}: آخر سجل {previous} ≠ الحالة {order.status}"

        # I5 — رقم المزود فريد
        if order.provider_order_id:
            assert order.provider_order_id not in provider_ids, "طلبان بنفس رقم المزود"
            provider_ids[order.provider_order_id] = oid
    assert len(w.client.orders) == len(provider_ids), "طلبات عند المزود أكثر من المسجَّلة محلياً (إرسال مزدوج)"

    # I6 — الدفعات والإيداعات
    deposits = await db.fetchall("SELECT payment_id FROM transactions WHERE type = 'deposit'")
    deposited = [int(r["payment_id"]) for r in deposits]
    assert len(deposited) == len(set(deposited)), "دفعة أُضيفت مرتين"
    assert set(deposited) == set(await w.pay_ids(PaymentStatus.APPROVED)), "دفعات معتمدة بلا إيداع أو العكس"


async def drain(w: World) -> None:
    """تصريف الطلبات: مزود سليم، تكرار الإرسال والمتابعة حتى الاستقرار (I7)."""
    w.client.fail_next_add = None
    w.client.always_fail_add = None
    for _ in range(25):
        await w.services.orders.process_pending_orders(limit=20)
        await _due_now(w)
        await w.services.orders.process_due_orders(limit=50)
        async with w.db.transaction() as tx:                # تجاوز انتظار إعادة المحاولة (backoff)
            await tx.execute("UPDATE orders SET next_check_at = ? WHERE status = 'pending'", (iso_plus_seconds(-30),))
    stuck = await w.order_ids(OrderStatus.SUBMITTING)
    assert not stuck, f"طلبات عالقة في submitting: {stuck}"


# -------------------------------------- الاختبار -------------------------------------- #


@pytest.mark.parametrize("seed", SEEDS)
async def test_random_operations_never_break_money_invariants(
    seed: int, services: ServiceContainer, repos: Repositories, db: Database, admin: User, super_admin: User,
    mock_service: Service, mock_client, payment_method,
) -> None:
    """عمليات عشوائية بالبذرة المحددة ثم تصريف ⇒ كل الثوابت المحاسبية سليمة."""
    rng = random.Random(seed)
    await services.settings.set("duplicate_order_window_minutes", 0)
    await services.settings.set("max_pending_payments_per_user", 50)
    users = [
        (await services.users.get_or_create(telegram_id=910_000 + i, username=f"fz{i}", first_name=f"F{i}"))[0]
        for i in range(4)
    ]
    world = World(services, repos, db, users, admin, super_admin, mock_service, mock_client, rng)
    world.method_id = payment_method.id
    # رصيد افتتاحي لضمان طلبات ناجحة كثيرة
    for user in users:
        await services.wallet.adjust_balance(target=user, amount_units=80_000, admin=super_admin, reason="افتتاحي", credit=True)

    actions, weights = zip(*ACTIONS, strict=True)
    executed = 0
    for step in range(STEPS):
        action = rng.choices(actions, weights=weights)[0]
        try:
            await action(world)
            executed += 1
        except SMMBotError:
            pass   # رفض منطقي مشروع (رصيد/حالة/حد…) — المهم ألا يترك أثراً مالياً
        if step % 10 == 9:
            await check_invariants(world)

    await drain(world)
    await check_invariants(world)
    # أداة التدقيق المستقلة (م12) تُجمع مع الثوابت: يجب أن تُجمع على «سليم» لنفس البيانات العشوائية
    conn = audit_ledger.open_readonly(Path(db.path))
    try:
        dirty = [f for f in audit_ledger.audit(conn) if f.count]
    finally:
        conn.close()
    assert dirty == [], f"أداة audit_ledger رصدت خللاً لم تلتقطه الثوابت: {dirty}"
    if os.environ.get("FUZZ_DEBUG"):
        rows = await db.fetchall("SELECT status, COUNT(*) c FROM orders GROUP BY status")
        pays = await db.fetchall("SELECT status, COUNT(*) c FROM payments GROUP BY status")
        print("SEED", seed, "executed", executed, {r["status"]: r["c"] for r in rows}, {r["status"]: r["c"] for r in pays})
    assert executed > STEPS // 3, "معظم العمليات فشلت — الاختبار لا يغطي شيئاً"
    assert len(await world.order_ids()) >= 5, "عدد الطلبات قليل جداً لإثبات شيء"


async def test_invariant_checker_detects_corruption(
    services: ServiceContainer, repos: Repositories, db: Database, admin: User, super_admin: User,
    mock_service: Service, mock_client, payment_method,
) -> None:
    """اختبار الاختبار: لو أفسدنا الدفتر أو الطلب عمداً يجب أن تفشل الثوابت (لا نجاح أعمى)."""
    user = (await services.users.get_or_create(telegram_id=920_001, username="c1", first_name="C"))[0]
    await services.wallet.adjust_balance(target=user, amount_units=100_000, admin=super_admin, reason="x", credit=True)
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/corrupt", quantity=1000
    )
    await services.orders.process_pending_orders(limit=5)
    world = World(services, repos, db, [user], admin, super_admin, mock_service, mock_client, random.Random(0))
    await check_invariants(world)                       # سليم قبل العبث

    async with db.transaction() as tx:                  # (أ) إفساد الرصيد المخزَّن فقط
        await tx.execute("UPDATE users SET balance_units = balance_units + 1 WHERE id = ?", (user.id,))
    with pytest.raises(AssertionError, match="اختلال محاسبي"):
        await check_invariants(world)
    async with db.transaction() as tx:
        await tx.execute("UPDATE users SET balance_units = balance_units - 1 WHERE id = ?", (user.id,))

    async with db.transaction() as tx:                  # (ب) تسجيل استرجاع على الطلب بلا حركة مالية
        await tx.execute("UPDATE orders SET refund_amount_units = 5 WHERE id = ?", (order.id,))
    with pytest.raises(AssertionError):
        await check_invariants(world)
