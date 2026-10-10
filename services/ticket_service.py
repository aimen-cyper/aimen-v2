"""
خدمة الدعم الفني — التذاكر والمحادثة بين المستخدم والأدمن.

المسؤوليات:
    • فتح تذكرة جديدة بتحقق كامل (حد يومي، تذكرة مفتوحة واحدة، طول النص).
    • تبادل الرسائل بين المستخدم وفريق الدعم مع إشعار الطرف الآخر.
    • الإسناد والأولوية والإغلاق وإعادة الفتح.
    • الإغلاق التلقائي للتذاكر الراكدة عبر job دوري.

قواعد:
    • لا تُحذف التذاكر أو الرسائل إطلاقاً — الإغلاق فقط (حفظ السجل التاريخي).
    • كل إجراء أدمن على تذكرة يُسجَّل في سجل التدقيق.
    • إشعار الرد يحمل مفتاح منع تكرار خاصاً بكل رسالة، فلا يُبتلع الرد الثاني.
"""

from __future__ import annotations

from core.enums import NotificationType, SenderType, TicketPriority, TicketStatus
from core.exceptions import PermissionDeniedError, TicketError, ValidationError
from core.permissions import Permission
from database.database import Database
from database.models import SupportMessage, SupportTicket, User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.notification_service import NotificationService
from services.settings_service import SettingsService
from texts import templates
from utils.datetime_utils import day_bounds_utc, iso_plus_seconds, parse_iso, utc_now
from utils.logging_setup import get_logger
from utils.validators import validate_message, validate_subject

logger = get_logger(__name__)

#: تصنيفات التذاكر المسموحة (مطابقة لقيد CHECK في قاعدة البيانات)
TICKET_CATEGORIES: dict[str, str] = {
    "order": "مشكلة في طلب",
    "payment": "مشكلة في الشحن",
    "service": "استفسار عن خدمة",
    "other": "أخرى",
}

#: الحالات المفتوحة التي تظهر لفريق الدعم
OPEN_STATUSES: tuple[str, ...] = (
    TicketStatus.OPEN,
    TicketStatus.PENDING_ADMIN,
    TicketStatus.PENDING_USER,
)

#: طول المقتطف الظاهر في الإشعار
PREVIEW_LENGTH: int = 120


class TicketService:
    """إدارة تذاكر الدعم الفني من الفتح حتى الإغلاق."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        notifications: NotificationService,
        audit: AuditService,
        auth: AuthService,
    ) -> None:
        """تهيئة الخدمة بالاعتماديات المطلوبة."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.notifications = notifications
        self.audit = audit
        self.auth = auth

    # ===================================================================== #
    #                             فتح التذاكر                               #
    # ===================================================================== #

    async def create_ticket(
        self,
        user: User,
        *,
        subject: str,
        message: str,
        category: str = "other",
        related_order_id: int | None = None,
        attachment_file_id: str | None = None,
        attachment_type: str | None = None,
    ) -> SupportTicket:
        """
        فتح تذكرة دعم جديدة مع أول رسالة فيها.

        المخرجات: التذكرة بعد إنشائها.

        الاستثناءات:
            UserBannedError · MaintenanceModeError
            ValidationError : موضوع/نص غير صالح، تصنيف غير معروف، أو تجاوز الحد اليومي.
            TicketError     : لدى المستخدم تذكرة مفتوحة بالفعل.
        """
        await self.auth.guard(user)

        if category not in TICKET_CATEGORIES:
            raise ValidationError(
                f"تصنيف تذكرة غير معروف: {category}",
                user_message="❌ اختر تصنيفاً صحيحاً للتذكرة.",
            )
        clean_subject = validate_subject(subject)
        clean_message = validate_message(message)

        order_id = await self._validate_related_order(user, related_order_id)

        async with self.db.transaction() as tx:
            # الفحوص الحاكمة داخل المعاملة (تحت قفل الكتابة) حتى لا تُفتح تذكرتان بنقرتين متزامنتين
            await self._ensure_no_open_ticket(user)
            await self._check_daily_limit(user)
            ticket = await self.repos.tickets.create(
                tx,
                user_id=user.id,
                subject=clean_subject,
                category=category,
                related_order_id=order_id,
            )
            await self.repos.tickets.add_message(
                tx,
                ticket_id=ticket.id,
                sender_type=SenderType.USER,
                sender_id=user.id,
                message=clean_message,
                attachment_file_id=attachment_file_id,
                attachment_type=attachment_type,
            )
            title, admin_message = templates.admin_new_ticket(
                ticket_id=ticket.id, subject=clean_subject, user_label=user.display_name
            )
            await self.notifications.notify_admins(
                tx,
                permission=Permission.TICKETS_VIEW,
                token=f"ticket:{ticket.id}:new",
                title=title,
                message=admin_message,
            )

        logger.info("فتح المستخدم %s التذكرة #%s (%s)", user.id, ticket.id, category)
        return ticket

    async def _ensure_no_open_ticket(self, user: User) -> None:
        """
        التأكد أن المستخدم لا يملك تذكرة مفتوحة (قاعدة: تذكرة مفتوحة واحدة لكل مستخدم).

        الاستثناءات: TicketError إن وُجدت تذكرة مفتوحة.
        """
        if await self.repos.tickets.has_open_ticket(user.id):
            raise TicketError(
                f"المستخدم {user.id} لديه تذكرة مفتوحة",
                user_message="📬 لديك تذكرة مفتوحة بالفعل — تابع محادثتك فيها بدل فتح تذكرة جديدة.",
            )

    async def _check_daily_limit(self, user: User) -> None:
        """
        تطبيق الحد اليومي لعدد التذاكر لكل مستخدم.

        الاستثناءات: ValidationError عند التجاوز.
        """
        max_per_day = await self.settings.get_int("max_tickets_per_day", 5)
        if max_per_day <= 0:
            return
        start_today, _ = day_bounds_utc(0)
        today = await self.repos.tickets.count_today_by_user(user.id, start_today)
        if today >= max_per_day:
            raise ValidationError(
                f"المستخدم {user.id} تجاوز {max_per_day} تذاكر اليوم",
                user_message=f"⏳ وصلت للحد اليومي ({max_per_day} تذاكر). حاول غداً.",
            )

    async def _validate_related_order(self, user: User, order_id: int | None) -> int | None:
        """
        التأكد من أن الطلب المرتبط بالتذكرة يخص المستخدم نفسه.

        الاستثناءات: TicketError إذا كان الطلب لمستخدم آخر أو غير موجود.
        """
        if order_id is None:
            return None
        order = await self.repos.orders.get(order_id)
        if order is None or order.user_id != user.id:
            raise TicketError(
                f"الطلب {order_id} لا يخص المستخدم {user.id}",
                user_message="❌ رقم الطلب المرتبط غير صحيح.",
            )
        return order.id

    # ===================================================================== #
    #                              المحادثة                                 #
    # ===================================================================== #

    async def reply_as_user(
        self,
        user: User,
        ticket_id: int,
        message: str,
        *,
        attachment_file_id: str | None = None,
        attachment_type: str | None = None,
    ) -> SupportMessage:
        """
        إضافة رد من المستخدم على تذكرته وإشعار فريق الدعم.

        التذكرة المغلقة تُعاد فتحها تلقائياً ضمن مهلة `ticket_reopen_hours`.

        الاستثناءات:
            TicketError     : التذكرة غير موجودة أو ليست له أو مغلقة نهائياً.
            ValidationError : نص الرسالة غير صالح.
        """
        await self.auth.guard(user)
        ticket = await self.get_for_user(user, ticket_id)
        clean_message = validate_message(message)
        # إعداد المرحلة 8: هل يُنبَّه الأدمن عند كل رد، أم عند فتح تذكرة جديدة فقط؟
        notify_admins = await self.settings.get_bool("ticket_reply_notify_admins", True)

        if ticket.status == TicketStatus.CLOSED:
            await self._reopen_or_fail(ticket)

        async with self.db.transaction() as tx:
            support_message = await self.repos.tickets.add_message(
                tx,
                ticket_id=ticket.id,
                sender_type=SenderType.USER,
                sender_id=user.id,
                message=clean_message,
                attachment_file_id=attachment_file_id,
                attachment_type=attachment_type,
            )
            if notify_admins:
                title, admin_text = templates.admin_new_ticket(
                    ticket_id=ticket.id,
                    subject=f"رد جديد — {ticket.subject}",
                    user_label=user.display_name,
                )
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.TICKETS_VIEW,
                    token=f"ticket:{ticket.id}:msg:{support_message.id}",
                    title=title,
                    message=admin_text,
                )
        logger.info("رد المستخدم %s على التذكرة #%s", user.id, ticket_id)
        return support_message

    async def _reopen_or_fail(self, ticket: SupportTicket) -> None:
        """
        إعادة فتح تذكرة مغلقة إن كانت ضمن المهلة المسموحة.

        الاستثناءات: TicketError إذا انتهت المهلة أو كانت إعادة الفتح معطّلة.
        """
        reopen_hours = await self.settings.get_int("ticket_reopen_hours", 48)
        closed_at = parse_iso(ticket.closed_at)
        age_hours = ((utc_now() - closed_at).total_seconds() / 3600) if closed_at else 0.0

        if reopen_hours <= 0 or (closed_at is not None and age_hours > reopen_hours):
            raise TicketError(
                f"التذكرة {ticket.id} مغلقة منذ {age_hours:.1f} ساعة",
                user_message="🔒 هذه التذكرة مغلقة. افتح تذكرة جديدة لمتابعة طلبك.",
            )

        async with self.db.transaction() as tx:
            reopened = await self.repos.tickets.reopen(tx, ticket.id)
        if reopened:
            logger.info("أُعيد فتح التذكرة #%s", ticket.id)

    async def reply_as_admin(
        self,
        actor: User,
        ticket_id: int,
        message: str,
        *,
        attachment_file_id: str | None = None,
        attachment_type: str | None = None,
        close_after: bool = False,
    ) -> SupportMessage:
        """
        رد فريق الدعم على تذكرة، مع إسنادها للمُجيب إن لم تكن مُسندة.

        المدخلات:
            close_after : إغلاق التذكرة مباشرة بعد الرد.

        الاستثناءات:
            PermissionDeniedError · TicketError · ValidationError
        """
        await self.auth.require_permission(
            actor, Permission.TICKETS_REPLY, context=f"ticket:{ticket_id}"
        )
        ticket = await self._require_ticket(ticket_id)
        clean_message = validate_message(message)

        async with self.db.transaction() as tx:
            if ticket.status == TicketStatus.CLOSED:
                await self.repos.tickets.reopen(tx, ticket.id)
            if ticket.assigned_admin is None:
                await self.repos.tickets.assign(tx, ticket.id, actor.id)

            support_message = await self.repos.tickets.add_message(
                tx,
                ticket_id=ticket.id,
                sender_type=SenderType.ADMIN,
                sender_id=actor.id,
                message=clean_message,
                attachment_file_id=attachment_file_id,
                attachment_type=attachment_type,
            )
            await self.repos.tickets.mark_read(tx, ticket.id, by_admin=True)

            title, text = templates.ticket_replied(
                ticket_id=ticket.id, preview=clean_message[:PREVIEW_LENGTH]
            )
            await self.notifications.notify_user_manual(
                tx,
                user_id=ticket.user_id,
                token=f"ticket:{ticket.id}:reply:{support_message.id}",
                title=title,
                message=text,
                type=NotificationType.TICKET_REPLIED,
            )
            await self.audit.log(
                tx,
                action="tickets.reply",
                admin_id=actor.id,
                target_type="ticket",
                target_id=ticket.id,
                details={"message_id": support_message.id, "close_after": close_after},
            )

        if close_after:
            await self.close(actor, ticket_id, reason="تم حل المشكلة")
        logger.info("رد الأدمن %s على التذكرة #%s", actor.id, ticket_id)
        return support_message

    # ===================================================================== #
    #                        الإسناد والأولوية والإغلاق                     #
    # ===================================================================== #

    async def assign(self, actor: User, ticket_id: int, admin_id: int) -> bool:
        """
        إسناد التذكرة إلى أدمن معيّن.

        الاستثناءات:
            PermissionDeniedError : المنفّذ لا يملك `tickets.assign`، أو الهدف ليس أدمن.
            TicketError           : التذكرة غير موجودة.
        """
        await self.auth.require_permission(
            actor, Permission.TICKETS_ASSIGN, context=f"ticket:{ticket_id}"
        )
        ticket = await self._require_ticket(ticket_id)

        target = await self.repos.users.get_by_id(admin_id)
        if target is None or not await self.auth.is_admin(target):
            raise PermissionDeniedError(
                f"المستخدم {admin_id} ليس أدمن",
                user_message="❌ لا يمكن إسناد التذكرة لمستخدم غير إداري.",
            )

        async with self.db.transaction() as tx:
            changed = await self.repos.tickets.assign(tx, ticket_id, admin_id)
            if changed:
                await self.audit.log(
                    tx,
                    action="tickets.assign",
                    admin_id=actor.id,
                    target_type="ticket",
                    target_id=ticket_id,
                    before={"assigned_admin": ticket.assigned_admin},
                    after={"assigned_admin": admin_id},
                )
        return changed

    async def set_priority(self, actor: User, ticket_id: int, priority: str) -> bool:
        """
        تغيير أولوية التذكرة (low / normal / high).

        الاستثناءات: PermissionDeniedError · TicketError · ValidationError
        """
        await self.auth.require_permission(
            actor, Permission.TICKETS_ASSIGN, context=f"ticket:{ticket_id}"
        )
        if priority not in set(TicketPriority):
            raise ValidationError(
                f"أولوية غير معروفة: {priority}", user_message="❌ أولوية غير صحيحة."
            )
        ticket = await self._require_ticket(ticket_id)

        async with self.db.transaction() as tx:
            changed = await self.repos.tickets.update_fields(tx, ticket_id, priority=priority)
            if changed:
                await self.audit.log(
                    tx,
                    action="tickets.assign",
                    admin_id=actor.id,
                    target_type="ticket",
                    target_id=ticket_id,
                    before={"priority": ticket.priority},
                    after={"priority": priority},
                )
        return changed

    async def close(self, actor: User, ticket_id: int, reason: str = "") -> bool:
        """
        إغلاق التذكرة من فريق الدعم مع إشعار المستخدم.

        المخرجات: True عند الإغلاق الفعلي (False إذا كانت مغلقة أصلاً).
        """
        await self.auth.require_permission(
            actor, Permission.TICKETS_CLOSE, context=f"ticket:{ticket_id}"
        )
        ticket = await self._require_ticket(ticket_id)
        clean_reason = (reason or "").strip()[:200] or "تم إغلاق التذكرة"
        stamp = len(await self.repos.tickets.messages(ticket_id, limit=500))

        async with self.db.transaction() as tx:
            closed = await self.repos.tickets.close(
                tx, ticket_id, closed_by=actor.id, reason=clean_reason
            )
            if not closed:
                return False
            title, text = templates.ticket_closed(ticket_id=ticket_id, reason=clean_reason)
            await self.notifications.notify_user_manual(
                tx,
                user_id=ticket.user_id,
                token=f"ticket:{ticket_id}:closed:{stamp}",
                title=title,
                message=text,
                type=NotificationType.TICKET_CLOSED,
            )
            await self.audit.log(
                tx,
                action="tickets.close",
                admin_id=actor.id,
                target_type="ticket",
                target_id=ticket_id,
                before={"status": ticket.status},
                after={"status": TicketStatus.CLOSED, "reason": clean_reason},
            )
        logger.info("أغلق الأدمن %s التذكرة #%s", actor.id, ticket_id)
        return True

    async def close_by_user(self, user: User, ticket_id: int) -> bool:
        """إغلاق المستخدم لتذكرته بنفسه بعد حل مشكلته."""
        ticket = await self.get_for_user(user, ticket_id)
        async with self.db.transaction() as tx:
            closed = await self.repos.tickets.close(
                tx, ticket.id, closed_by=user.id, reason="أغلقها المستخدم"
            )
        if closed:
            logger.info("أغلق المستخدم %s التذكرة #%s", user.id, ticket_id)
        return closed

    async def auto_close_idle(self) -> int:
        """
        إغلاق التذاكر الراكدة (بانتظار رد المستخدم) بعد المدة المحددة في الإعدادات.

        المخرجات: عدد التذاكر التي أُغلقت.
        """
        days = await self.settings.get_int("ticket_auto_close_days", 7)
        if days <= 0:
            return 0
        cutoff = iso_plus_seconds(-days * 86400)
        idle = await self.repos.tickets.list_idle(
            statuses=(TicketStatus.PENDING_USER,), before_iso=cutoff, limit=50
        )
        closed_count = 0
        for ticket in idle:
            async with self.db.transaction() as tx:
                closed = await self.repos.tickets.close(
                    tx, ticket.id, closed_by=None, reason=f"إغلاق تلقائي بعد {days} أيام بلا رد"
                )
                if not closed:
                    continue
                title, text = templates.ticket_closed(
                    ticket_id=ticket.id, reason=f"إغلاق تلقائي بعد {days} أيام بلا رد"
                )
                await self.notifications.notify_user_manual(
                    tx,
                    user_id=ticket.user_id,
                    token=f"ticket:{ticket.id}:autoclosed",
                    title=title,
                    message=text,
                    type=NotificationType.TICKET_CLOSED,
                )
            closed_count += 1
        if closed_count:
            logger.info("أُغلقت %s تذكرة راكدة تلقائياً", closed_count)
        return closed_count

    # ===================================================================== #
    #                                القراءة                                #
    # ===================================================================== #

    async def get_for_user(self, user: User, ticket_id: int) -> SupportTicket:
        """
        جلب تذكرة تخص المستخدم نفسه.

        الاستثناءات: TicketError إذا لم توجد أو كانت لمستخدم آخر.
        """
        ticket = await self.repos.tickets.get(ticket_id)
        if ticket is None or ticket.user_id != user.id:
            raise TicketError(
                f"التذكرة {ticket_id} غير متاحة للمستخدم {user.id}",
                user_message="❌ لم يتم العثور على التذكرة.",
            )
        return ticket

    async def _require_ticket(self, ticket_id: int) -> SupportTicket:
        """
        جلب تذكرة للإدارة.

        الاستثناءات: TicketError إذا لم توجد.
        """
        ticket = await self.repos.tickets.get(ticket_id)
        if ticket is None:
            raise TicketError(
                f"التذكرة {ticket_id} غير موجودة", user_message="❌ التذكرة غير موجودة."
            )
        return ticket

    async def list_for_user(
        self, user: User, *, limit: int = 10, offset: int = 0
    ) -> list[SupportTicket]:
        """تذاكر المستخدم من الأحدث للأقدم."""
        return await self.repos.tickets.list_by_user(user.id, limit=limit, offset=offset)

    async def conversation_for_user(
        self, user: User, ticket_id: int, *, limit: int = 50
    ) -> list[SupportMessage]:
        """رسائل تذكرة المستخدم مع تعليمها كمقروءة من طرفه."""
        ticket = await self.get_for_user(user, ticket_id)
        messages = await self.repos.tickets.messages(ticket.id, limit=limit)
        async with self.db.transaction() as tx:
            await self.repos.tickets.mark_read(tx, ticket.id, by_admin=False)
        return messages

    async def admin_list(
        self,
        actor: User,
        *,
        statuses: tuple[str, ...] = OPEN_STATUSES,
        assigned_admin: int | None = None,
        priority: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[SupportTicket]:
        """
        قائمة التذاكر لفريق الدعم (الافتراضي: غير المغلقة).

        المدخلات:
            statuses       : الحالات المطلوبة.
            assigned_admin : حصر النتائج بالتذاكر المسندة لأدمن بعينه (تبويب «المسندة لي»).
            priority       : حصر النتائج بأولوية بعينها (تبويب «العاجلة»).
        """
        await self.auth.require_permission(actor, Permission.TICKETS_VIEW)
        return await self.repos.tickets.list_by_status(
            list(statuses),
            assigned_admin=assigned_admin,
            priority=priority,
            limit=limit,
            offset=offset,
        )

    async def admin_count(
        self,
        actor: User,
        *,
        statuses: tuple[str, ...] = OPEN_STATUSES,
        assigned_admin: int | None = None,
        priority: str | None = None,
    ) -> int:
        """عدد التذاكر المطابقة لتصفية `admin_list` (لحساب عدد الصفحات)."""
        await self.auth.require_permission(actor, Permission.TICKETS_VIEW)
        return await self.repos.tickets.count_by_status(
            list(statuses), assigned_admin=assigned_admin, priority=priority
        )

    async def admin_conversation(
        self, actor: User, ticket_id: int, *, limit: int = 50
    ) -> tuple[SupportTicket, list[SupportMessage]]:
        """
        فتح تذكرة في لوحة الدعم: التذكرة + رسائلها، مع تعليمها كمقروءة من الأدمن.
        """
        await self.auth.require_permission(actor, Permission.TICKETS_VIEW)
        ticket = await self._require_ticket(ticket_id)
        messages = await self.repos.tickets.messages(ticket_id, limit=limit)
        async with self.db.transaction() as tx:
            await self.repos.tickets.mark_read(tx, ticket_id, by_admin=True)
        return ticket, messages

    async def open_count(self) -> int:
        """عدد التذاكر غير المغلقة (شارة لوحة الأدمن)."""
        return await self.repos.tickets.count_open()
