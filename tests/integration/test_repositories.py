"""اختبارات المستودعات: سلوك العمليات الحقيقية على البيانات."""

from __future__ import annotations

import asyncio

from core.enums import OrderStatus
from database.database import Database
from database.repositories import Repositories
from utils.datetime_utils import iso_minus_days, utc_now_iso


# ------------------------------- المستخدمون ------------------------------- #


async def test_create_and_fetch_user(db: Database, repos: Repositories) -> None:
    """إنشاء مستخدم وجلبه بمعرف تيليجرام."""
    async with db.transaction() as tx:
        created = await repos.users.create(tx, telegram_id=777, username="ali", first_name="علي")
    fetched = await repos.users.get_by_telegram_id(777)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.display_name == "@ali"
    assert fetched.balance_units == 0
    assert fetched.role == "user"


async def test_ban_and_unban(db: Database, repos: Repositories, user) -> None:
    """الحظر يسجل السبب والوقت، وفك الحظر يمسحهما."""
    async with db.transaction() as tx:
        await repos.users.set_ban(tx, user.id, banned=True, reason="إساءة")
    banned = await repos.users.get_by_id(user.id)
    assert banned is not None and banned.banned and banned.ban_reason == "إساءة"

    async with db.transaction() as tx:
        await repos.users.set_ban(tx, user.id, banned=False)
    unbanned = await repos.users.get_by_id(user.id)
    assert unbanned is not None and not unbanned.banned and unbanned.ban_reason is None


async def test_search_user_by_id_and_name(db: Database, repos: Repositories, user) -> None:
    """البحث يعمل بالرقم وبالاسم."""
    assert len(await repos.users.search("100200300")) == 1
    assert len(await repos.users.search("@tester")) == 1
    assert len(await repos.users.search("لا-يوجد")) == 0


async def test_broadcast_targets_exclude_banned_and_blocked(db: Database, repos: Repositories, user) -> None:
    """قائمة الإذاعة تستثني المحظور ومن حظر البوت."""
    async with db.transaction() as tx:
        blocked = await repos.users.create(tx, telegram_id=888, first_name="حظر")
        await repos.users.set_blocked_bot(tx, blocked.id, True)
        banned = await repos.users.create(tx, telegram_id=999, first_name="محظور")
        await repos.users.set_ban(tx, banned.id, banned=True, reason="x")
    targets = await repos.users.telegram_ids_for_broadcast()
    assert targets == [user.telegram_id]


# -------------------------------- الصلاحيات -------------------------------- #


async def test_role_permissions_hierarchy(db: Database, repos: Repositories) -> None:
    """الأدوار تحمل الصلاحيات الصحيحة: المستخدم لا شيء، الدعم محدود، الأدمن الأعلى الكل."""
    user_perms = await repos.rbac.role_permissions("user")
    support_perms = await repos.rbac.role_permissions("support")
    admin_perms = await repos.rbac.role_permissions("admin")
    super_perms = await repos.rbac.role_permissions("super_admin")

    assert user_perms == set()
    assert "tickets.reply" in support_perms
    assert "users.balance.credit" not in support_perms
    assert "payments.approve" in admin_perms
    assert "admins.manage" not in admin_perms
    assert admin_perms < super_perms


async def test_user_permission_override(db: Database, repos: Repositories, user) -> None:
    """الاستثناء الفردي يتجاوز صلاحيات الدور في الاتجاهين."""
    assert await repos.rbac.has_permission(user.id, "user", "payments.approve") is False

    async with db.transaction() as tx:
        await repos.rbac.set_user_override(tx, user.id, "payments.approve", allow=True)
    assert await repos.rbac.has_permission(user.id, "user", "payments.approve") is True

    async with db.transaction() as tx:
        await repos.rbac.set_user_override(tx, user.id, "tickets.reply", allow=False)
    assert await repos.rbac.has_permission(user.id, "support", "tickets.reply") is False


# -------------------------------- الإعدادات -------------------------------- #


async def test_settings_typed_reads(db: Database, repos: Repositories) -> None:
    """قراءة الإعدادات بأنواعها الصحيحة."""
    assert await repos.settings.get_bool("maintenance_mode") is False
    assert await repos.settings.get_int("order_check_interval_seconds") == 120
    assert await repos.settings.get_str("currency_code") == "YER"
    assert await repos.settings.get_int("غير_موجود", 42) == 42


async def test_settings_update_and_protect_readonly(db: Database, repos: Repositories, user) -> None:
    """الإعداد القابل للتعديل يتغير، والمحمي يُرفض تعديله."""
    async with db.transaction() as tx:
        assert await repos.settings.set(tx, "maintenance_mode", "1", updated_by=user.id) is True
        assert await repos.settings.set(tx, "schema_money_scale", "100") is False
    assert await repos.settings.get_bool("maintenance_mode") is True
    assert await repos.settings.get_int("schema_money_scale") == 10_000


# --------------------------- التصنيفات والخدمات ---------------------------- #


async def test_categories_with_services_only(db: Database, repos: Repositories, service) -> None:
    """لا يظهر للمستخدم إلا التصنيف الذي يحتوي خدمة متاحة فعلاً."""
    visible = await repos.categories.list_with_available_services()
    assert len(visible) == 1
    assert visible[0].id == service.category_id

    async with db.transaction() as tx:
        await repos.services.set_active(tx, service.id, False)
    assert await repos.categories.list_with_available_services() == []


async def test_service_price_change_records_history(db: Database, repos: Repositories, service) -> None:
    """تغيير السعر يُسجَّل في سجل الأسعار بالقيمتين القديمة والجديدة."""
    async with db.transaction() as tx:
        assert await repos.services.change_price(
            tx, service.id, new_price_units=12_000, changed_by=None, source="admin"
        ) is True
    history = await repos.services.price_history(service.id)
    updated = await repos.services.get(service.id)
    assert updated is not None and updated.price_per_1000_units == 12_000
    assert len(history) == 1
    assert history[0]["old_price_units"] == 10_000
    assert history[0]["new_price_units"] == 12_000


async def test_archive_hides_service_but_keeps_data(db: Database, repos: Repositories, service) -> None:
    """الأرشفة تُخفي الخدمة دون حذفها (حذف ناعم)."""
    async with db.transaction() as tx:
        await repos.services.archive(tx, service.id)
    assert await repos.services.get_available(service.id) is None
    assert await repos.services.get(service.id) is not None


async def test_negative_margin_detection(db: Database, repos: Repositories, service) -> None:
    """كشف الخدمات التي أصبح سعر بيعها أقل من تكلفتها."""
    assert await repos.services.negative_margin_services() == []
    async with db.transaction() as tx:
        await repos.services.update_fields(tx, service.id, price_per_1000_units=5_000)
    assert len(await repos.services.negative_margin_services()) == 1


# --------------------------------- الطلبات --------------------------------- #


async def _order(db: Database, repos: Repositories, user, service, crid: str):
    """أداة مساعدة: إنشاء طلب اختباري."""
    async with db.transaction() as tx:
        return await repos.orders.create(
            tx,
            user_id=user.id,
            service_id=service.id,
            provider_id=service.provider_id,
            service_name_snapshot=service.name,
            price_per_1000_snapshot_units=service.price_per_1000_units,
            link="https://example.com/p/1",
            quantity=1000,
            cost_units=10_000,
            client_request_id=crid,
        )


async def test_order_status_guard(db: Database, repos: Repositories, user, service) -> None:
    """تغيير الحالة مشروط بالحالة السابقة: الانتقال الخاطئ يفشل بهدوء."""
    order = await _order(db, repos, user, service, "o1")
    async with db.transaction() as tx:
        ok = await repos.orders.update_status(
            tx, order.id, new_status=OrderStatus.SUBMITTED,
            expected_statuses=[OrderStatus.SUBMITTING],
        )
    assert ok is False  # الحالة الحالية pending وليست submitting

    async with db.transaction() as tx:
        ok = await repos.orders.update_status(
            tx, order.id, new_status=OrderStatus.SUBMITTING, expected_statuses=[OrderStatus.PENDING]
        )
    assert ok is True


async def test_claim_pending_only_once(db: Database, repos: Repositories, user, service) -> None:
    """الطلب المعلّق يُحجز مرة واحدة فقط — لا يعالجه worker ثانٍ."""
    await _order(db, repos, user, service, "claim-1")
    async with db.transaction() as tx:
        first = await repos.orders.claim_pending_for_submit(tx, worker="w1", limit=10)
    async with db.transaction() as tx:
        second = await repos.orders.claim_pending_for_submit(tx, worker="w2", limit=10)
    assert len(first) == 1
    assert second == []
    assert first[0].status == OrderStatus.SUBMITTING
    assert first[0].submit_attempts == 1


async def test_concurrent_claims_do_not_duplicate(db: Database, repos: Repositories, user, service) -> None:
    """حجز متزامن من عدة عمال لا يعطي نفس الطلب لأكثر من واحد."""
    for index in range(5):
        await _order(db, repos, user, service, f"cc-{index}")

    async def claim(worker: str) -> list[int]:
        """محاولة حجز دفعة طلبات."""
        async with db.transaction() as tx:
            orders = await repos.orders.claim_pending_for_submit(tx, worker=worker, limit=5)
        return [o.id for o in orders]

    batches = await asyncio.gather(claim("w1"), claim("w2"), claim("w3"))
    all_ids = [oid for batch in batches for oid in batch]
    assert len(all_ids) == 5
    assert len(set(all_ids)) == 5  # لا تكرار


async def test_recover_submitting_orders(db: Database, repos: Repositories, user, service) -> None:
    """بعد إعادة التشغيل تُنقل الطلبات العالقة في submitting إلى submit_uncertain."""
    await _order(db, repos, user, service, "rec-1")
    async with db.transaction() as tx:
        await repos.orders.claim_pending_for_submit(tx, worker="w1", limit=1)
    async with db.transaction() as tx:
        recovered = await repos.orders.recover_submitting_orders(tx)
    assert len(recovered) == 1
    order = await repos.orders.get(recovered[0])
    assert order is not None and order.status == OrderStatus.SUBMIT_UNCERTAIN
    history = await repos.orders.history(order.id)
    assert history[-1].to_status == OrderStatus.SUBMIT_UNCERTAIN


async def test_duplicate_order_detection(db: Database, repos: Repositories, user, service) -> None:
    """كشف الطلب المكرر خلال النافذة الزمنية."""
    await _order(db, repos, user, service, "dup-1")
    found = await repos.orders.find_recent_duplicate(
        user_id=user.id, service_id=service.id, link="https://example.com/p/1",
        quantity=1000, since_iso=iso_minus_days(1),
    )
    assert found is not None
    not_found = await repos.orders.find_recent_duplicate(
        user_id=user.id, service_id=service.id, link="https://example.com/other",
        quantity=1000, since_iso=iso_minus_days(1),
    )
    assert not_found is None


async def test_order_history_and_counts(db: Database, repos: Repositories, user, service) -> None:
    """سجل الحالات يُكتب، وعدّادات الحالات تعمل."""
    order = await _order(db, repos, user, service, "hist-1")
    async with db.transaction() as tx:
        await repos.orders.add_history(
            tx, order_id=order.id, from_status=None, to_status=OrderStatus.PENDING, actor_type="user"
        )
    assert len(await repos.orders.history(order.id)) == 1
    assert (await repos.orders.status_counts())["pending"] == 1


# -------------------------------- المدفوعات -------------------------------- #


async def test_payment_status_guard_prevents_double_approve(
    db: Database, repos: Repositories, user, payment_method
) -> None:
    """اعتماد الدفعة مرتين مستحيل: المحاولة الثانية تُرجع False."""
    async with db.transaction() as tx:
        payment = await repos.payments.create(
            tx, user_id=user.id, method_id=payment_method.id, amount_units=50_000
        )
    async with db.transaction() as tx:
        first = await repos.payments.set_status(
            tx, payment.id, new_status="approved", admin_id=user.id, credited_units=50_000
        )
    async with db.transaction() as tx:
        second = await repos.payments.set_status(
            tx, payment.id, new_status="approved", admin_id=user.id, credited_units=50_000
        )
    assert first is True
    assert second is False


async def test_payment_duplicate_reference_detection(
    db: Database, repos: Repositories, user, payment_method
) -> None:
    """كشف استخدام نفس رقم الحوالة في طلب شحن آخر."""
    async with db.transaction() as tx:
        await repos.payments.create(
            tx, user_id=user.id, method_id=payment_method.id, amount_units=10_000,
            transaction_reference="TRX-999",
        )
    assert await repos.payments.find_duplicate_reference("TRX-999") is not None
    assert await repos.payments.find_duplicate_reference("TRX-000") is None


# ---------------------------------- الدعم ---------------------------------- #


async def test_ticket_flow(db: Database, repos: Repositories, user) -> None:
    """دورة تذكرة كاملة: إنشاء، رسالة مستخدم، رد أدمن، إغلاق."""
    async with db.transaction() as tx:
        ticket = await repos.tickets.create(tx, user_id=user.id, subject="مشكلة في طلب")
        await repos.tickets.add_message(
            tx, ticket_id=ticket.id, sender_type="user", message="طلبي لم يصل", sender_id=user.id
        )
    after_user = await repos.tickets.get(ticket.id)
    assert after_user is not None and after_user.status == "pending_admin"

    async with db.transaction() as tx:
        await repos.tickets.add_message(
            tx, ticket_id=ticket.id, sender_type="admin", message="تمت المتابعة", sender_id=user.id
        )
    after_admin = await repos.tickets.get(ticket.id)
    assert after_admin is not None and after_admin.status == "pending_user"

    async with db.transaction() as tx:
        assert await repos.tickets.close(tx, ticket.id, closed_by=user.id, reason="تم الحل") is True
    async with db.transaction() as tx:
        assert await repos.tickets.close(tx, ticket.id, closed_by=user.id) is False  # لا إغلاق مزدوج

    assert len(await repos.tickets.messages(ticket.id)) == 2
    assert await repos.tickets.count_open() == 0


# -------------------------------- الإشعارات -------------------------------- #


async def test_notification_outbox_cycle(db: Database, repos: Repositories, user) -> None:
    """دورة الإشعار: إدراج ← حجز ← تعليم كمُرسل."""
    async with db.transaction() as tx:
        await repos.notifications.enqueue(
            tx, user_id=user.id, type="order_completed", message="اكتمل طلبك", dedupe_key="order:5:completed"
        )
    async with db.transaction() as tx:
        batch = await repos.notifications.claim_batch(tx, limit=10)
    assert len(batch) == 1

    async with db.transaction() as tx:
        assert await repos.notifications.mark_sent(tx, batch[0].id, 12345) is True
    async with db.transaction() as tx:
        assert await repos.notifications.mark_sent(tx, batch[0].id, 12345) is False  # لا إرسال مزدوج

    assert await repos.notifications.count_queued() == 0


async def test_notification_retry_backoff(db: Database, repos: Repositories, user) -> None:
    """الفشل المؤقت يعيد الإشعار للطابور بموعد لاحق، والفشل النهائي يوقفه."""
    async with db.transaction() as tx:
        notification_id = await repos.notifications.enqueue(
            tx, user_id=user.id, type="system", message="اختبار", dedupe_key="n:retry"
        )
    assert notification_id is not None

    async with db.transaction() as tx:
        await repos.notifications.mark_failed(tx, notification_id, error="شبكة")
    retried = await repos.notifications.get(notification_id)
    assert retried is not None and retried.status == "queued" and retried.attempts == 1

    async with db.transaction() as tx:
        await repos.notifications.mark_failed(tx, notification_id, error="محظور", permanent=True)
    final = await repos.notifications.get(notification_id)
    assert final is not None and final.status == "failed"


# ------------------------------ منع التكرار -------------------------------- #


async def test_idempotency_key_acquired_once(db: Database, repos: Repositories, user) -> None:
    """المفتاح يُحجز مرة واحدة فقط — الضغط المزدوج لا ينفّذ العملية مرتين."""
    async with db.transaction() as tx:
        first = await repos.idempotency.try_acquire(tx, "approve:7", scope="payment", user_id=user.id)
    async with db.transaction() as tx:
        second = await repos.idempotency.try_acquire(tx, "approve:7", scope="payment", user_id=user.id)
    assert first is True
    assert second is False

    async with db.transaction() as tx:
        await repos.idempotency.save_result(tx, "approve:7", {"payment_id": 7, "ok": True})
    assert (await repos.idempotency.get_result("approve:7"))["payment_id"] == 7


async def test_concurrent_idempotency_single_winner(db: Database, repos: Repositories, user) -> None:
    """عند التزاحم على نفس المفتاح ينجح واحد فقط."""

    async def acquire() -> bool:
        """محاولة حجز المفتاح."""
        async with db.transaction() as tx:
            return await repos.idempotency.try_acquire(tx, "race:key", scope="test")

    results = await asyncio.gather(*(acquire() for _ in range(10)))
    assert sum(results) == 1


# --------------------------- السجلات والإذاعة ------------------------------ #


async def test_audit_log_written(db: Database, repos: Repositories, user) -> None:
    """سجل التدقيق يحفظ الحالة قبل وبعد."""
    async with db.transaction() as tx:
        await repos.audit.log(
            tx, action="users.balance.credit", admin_id=user.id, target_type="user",
            target_id=user.id, before={"balance": 0}, after={"balance": 1000},
        )
    logs = await repos.audit.list_by_target("user", user.id)
    assert len(logs) == 1
    assert logs[0].action == "users.balance.credit"
    assert "1000" in (logs[0].after_json or "")


async def test_broadcast_recipients_no_double_count(db: Database, repos: Repositories, user) -> None:
    """المستلم يُحتسب مرة واحدة فقط حتى لو تكرر تحديثه."""
    async with db.transaction() as tx:
        broadcast = await repos.broadcasts.create(tx, admin_id=user.id, message_text="إعلان")
        await repos.broadcasts.add_recipients(tx, broadcast.id, [user.id, user.id])

    async with db.transaction() as tx:
        recipients = await repos.broadcasts.claim_recipients(tx, broadcast.id, limit=10)
    assert len(recipients) == 1

    async with db.transaction() as tx:
        assert await repos.broadcasts.mark_recipient(tx, recipients[0]["id"], status="sent") is True
    async with db.transaction() as tx:
        assert await repos.broadcasts.mark_recipient(tx, recipients[0]["id"], status="sent") is False

    updated = await repos.broadcasts.get(broadcast.id)
    assert updated is not None and updated.sent_count == 1 and updated.total_count == 1


async def test_provider_failure_tracking(db: Database, repos: Repositories, provider) -> None:
    """تتبع الأخطاء المتتالية للمزود وتصفيرها عند النجاح."""
    async with db.transaction() as tx:
        count = await repos.providers.record_failure(tx, provider.id, "timeout")
    assert count == 1
    async with db.transaction() as tx:
        count = await repos.providers.record_failure(tx, provider.id, "timeout")
    assert count == 2
    async with db.transaction() as tx:
        await repos.providers.record_success(tx, provider.id)
    refreshed = await repos.providers.get(provider.id)
    assert refreshed is not None and refreshed.consecutive_failures == 0


async def test_provider_request_log_sanitizes_secrets(db: Database, repos: Repositories, provider) -> None:
    """سجل استدعاءات المزود لا يحتفظ بالمفتاح السري إطلاقاً."""
    async with db.transaction() as tx:
        await repos.provider_requests.log(
            tx, provider_id=provider.id, action="add", is_success=True,
            request_summary="key=SUPERSECRET123&action=add&service=555",
            response_snippet='{"order": 999}', secrets=("SUPERSECRET123",),
        )
    logs = await repos.provider_requests.list_by_provider(provider.id)
    assert "SUPERSECRET123" not in logs[0]["request_summary"]
    assert "***" in logs[0]["request_summary"]


async def test_error_log_written(db: Database, repos: Repositories, user) -> None:
    """تسجيل الأخطاء في قاعدة البيانات لعرضها في اللوحة."""
    async with db.transaction() as tx:
        await repos.error_logs.log(
            tx, message="فشل الاتصال بالمزود", source="job", error_type="ProviderError", user_id=user.id
        )
    logs = await repos.error_logs.list_recent()
    assert len(logs) == 1
    assert await repos.error_logs.count_since(iso_minus_days(1)) == 1
    assert logs[0]["created_at"] <= utc_now_iso()
