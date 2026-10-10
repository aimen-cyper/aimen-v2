"""
اختبارات صندوق الإشعارات (Outbox).

المبدأ: الإشعار يُكتب في قاعدة البيانات داخل معاملة العملية، ثم تُرسله مهمة
مستقلة. فشل الإرسال لا يُسقط العملية المالية، والمستخدم الذي حظر البوت لا
يُستنزف عليه الطابور.
"""

from __future__ import annotations

from core.enums import NotificationType
from core.exceptions import (
    NotificationBlockedError,
    NotificationPermanentError,
    NotificationTemporaryError,
)
from core.permissions import Permission
from database.database import Database
from database.models import User
from database.repositories import Repositories
from services import ServiceContainer


class FakeSender:
    """مرسل وهمي يسجّل ما أُرسل ويُمكن برمجته ليفشل (بديل تيليجرام في الاختبار)."""

    def __init__(self, *, error: Exception | None = None) -> None:
        """تهيئة المرسل مع استثناء اختياري يُرفع عند كل إرسال."""
        self.sent: list[tuple[int, str, str]] = []
        self.error = error

    async def __call__(self, telegram_id: int, title: str, message: str) -> int:
        """محاكاة إرسال رسالة وإرجاع معرف رسالة تيليجرام."""
        if self.error is not None:
            raise self.error
        self.sent.append((telegram_id, title, message))
        return 1_000 + len(self.sent)


async def _enqueue(services: ServiceContainer, db: Database, user: User, token: str = "t1") -> int | None:
    """إدراج إشعار يدوي في الطابور."""
    async with db.transaction() as tx:
        return await services.notifications.notify_user_manual(
            tx, user_id=user.id, token=token, title="عنوان", message="نص الإشعار"
        )


async def test_enqueue_then_dispatch_marks_sent(
    services: ServiceContainer, db: Database, repos: Repositories, user: User
) -> None:
    """الإشعار يُدرج أولاً ثم يُرسل ويُعلَّم كمُرسل."""
    await _enqueue(services, db, user)
    assert await services.notifications.queued_count() == 1

    sender = FakeSender()
    report = await services.notifications.dispatch_pending(sender)

    assert report.claimed == 1 and report.sent == 1
    assert sender.sent[0][0] == user.telegram_id
    assert await services.notifications.queued_count() == 0


async def test_duplicate_token_is_not_enqueued_twice(
    services: ServiceContainer, db: Database, user: User
) -> None:
    """مفتاح منع التكرار يمنع إدراج نفس الإشعار مرتين."""
    first = await _enqueue(services, db, user, token="same")
    second = await _enqueue(services, db, user, token="same")

    assert first is not None
    assert second is None
    assert await services.notifications.queued_count() == 1


async def test_blocked_user_is_skipped_and_flagged(
    services: ServiceContainer, db: Database, repos: Repositories, user: User
) -> None:
    """من يحظر البوت يُعلَّم في قاعدة البيانات ولا تُعاد المحاولة عليه."""
    await _enqueue(services, db, user)
    report = await services.notifications.dispatch_pending(
        FakeSender(error=NotificationBlockedError("bot was blocked by the user"))
    )

    assert report.skipped == 1 and report.sent == 0
    refreshed = await repos.users.get_by_id(user.id)
    assert refreshed is not None and refreshed.blocked_bot == 1


async def test_temporary_failure_keeps_notification_for_retry(
    services: ServiceContainer, db: Database, repos: Repositories, user: User
) -> None:
    """الفشل المؤقت يُبقي الإشعار لإعادة المحاولة لاحقاً."""
    await _enqueue(services, db, user)
    first = await services.notifications.dispatch_pending(
        FakeSender(error=NotificationTemporaryError("timeout"))
    )
    assert first.failed == 1

    notification = (await repos.notifications.list_for_user(user.id))[0]
    assert notification.status in {"queued", "failed"}
    assert notification.attempts >= 1


async def test_permanent_failure_stops_retrying(
    services: ServiceContainer, db: Database, repos: Repositories, user: User
) -> None:
    """الفشل النهائي يوقف المحاولات ولا يبقى الإشعار في الطابور."""
    await _enqueue(services, db, user)
    await services.notifications.dispatch_pending(
        FakeSender(error=NotificationPermanentError("chat not found"))
    )
    assert await services.notifications.queued_count() == 0


async def test_notify_admins_targets_permission_holders_only(
    services: ServiceContainer, db: Database, repos: Repositories,
    user: User, admin: User, super_admin: User,
) -> None:
    """تنبيه الأدمن يذهب لمن يملك الصلاحية فقط، لا لكل من له دور إداري."""
    async with db.transaction() as tx:
        count = await services.notifications.notify_admins(
            tx,
            permission=Permission.ORDERS_VIEW,
            token="test-alert",
            title="تنبيه",
            message="طلب يحتاج مراجعة",
        )

    assert count == 2  # admin + super_admin
    assert await repos.notifications.list_for_user(admin.id)
    assert await repos.notifications.list_for_user(super_admin.id)
    assert not await repos.notifications.list_for_user(user.id)


async def test_notify_admins_respects_individual_denial(
    services: ServiceContainer, db: Database, repos: Repositories, admin: User, super_admin: User
) -> None:
    """من مُنع فردياً من صلاحية لا يصله تنبيهها."""
    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.PAYMENTS_APPROVE, allow=False
    )
    async with db.transaction() as tx:
        await services.notifications.notify_admins(
            tx,
            permission=Permission.PAYMENTS_APPROVE,
            token="payment-alert",
            title="شحن جديد",
            message="طلب شحن بانتظار المراجعة",
        )

    assert not await repos.notifications.list_for_user(admin.id)
    assert await repos.notifications.list_for_user(super_admin.id)


async def test_unread_count_and_mark_all_read(
    services: ServiceContainer, db: Database, user: User
) -> None:
    """عدّاد غير المقروء يعمل ويمكن تصفيره دفعة واحدة."""
    await _enqueue(services, db, user, token="a")
    await _enqueue(services, db, user, token="b")
    assert await services.notifications.unread_count(user.id) == 2

    assert await services.notifications.mark_all_read(user.id) == 2
    assert await services.notifications.unread_count(user.id) == 0


async def test_order_notifications_use_event_specific_keys(
    services: ServiceContainer, db: Database, repos: Repositories, user: User
) -> None:
    """إشعارات الطلب الواحد تختلف بحسب الحدث فلا يبتلع أحدها الآخر."""
    async with db.transaction() as tx:
        first = await services.notifications.notify_order(
            tx, user_id=user.id, order_id=1, event=NotificationType.ORDER_CREATED,
            title="أُنشئ", message="تم إنشاء طلبك",
        )
        second = await services.notifications.notify_order(
            tx, user_id=user.id, order_id=1, event=NotificationType.ORDER_COMPLETED,
            title="اكتمل", message="اكتمل طلبك",
        )
        third = await services.notifications.notify_order(
            tx, user_id=user.id, order_id=1, event=NotificationType.ORDER_CREATED,
            title="أُنشئ مجدداً", message="تكرار",
        )

    assert first is not None and second is not None
    assert third is None, "نفس الحدث لنفس الطلب يجب ألا يتكرر"
    assert len(await repos.notifications.list_for_user(user.id)) == 2
