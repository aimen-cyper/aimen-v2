"""
خدمة الرسائل الجماعية (الإذاعة) — المرحلة 8.

لماذا طابور مستلمين بدل حلقة إرسال واحدة؟
    إرسال رسالة لعشرة آلاف مستخدم داخل معالج زر مستحيل عملياً: تيليجرام يحدّ
    السرعة (~30 رسالة/ثانية)، وأي انقطاع يفقد أثر من وصلته الرسالة ومن لم تصله.
    لذلك: تُسجَّل قائمة المستلمين كاملة في `broadcast_recipients` أولاً، ثم تأتي
    مهمة دورية وترسل دفعة صغيرة كل بضع ثوانٍ وتسجّل نتيجة كل مستلم على حدة.

النتائج المضمونة:
    • لا تكرار: صف المستلم ينتقل من pending إلى نتيجة نهائية بشرط `status='pending'`،
      فحتى لو تداخلت جولتان لا يُرسل لأحد مرتين.
    • استئناف تلقائي: إعادة تشغيل البوت لا تفقد شيئاً — الإذاعة تبقى `running`
      والجولة التالية تكمل من حيث توقفت.
    • إيقاف فوري: زر «⏸ إيقاف مؤقت» يوقف الجولات، والملغاة لا تُستأنف أبداً.
    • من حظر البوت يُسجَّل فوراً (`blocked_bot=1`) فلا نزعج طابور الإشعارات به لاحقاً.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from core.enums import BroadcastStatus, RecipientStatus
from core.exceptions import (
    NotificationBlockedError,
    NotificationPermanentError,
    NotificationTemporaryError,
    ValidationError,
)
from core.permissions import Permission
from database.database import Database
from database.models import Broadcast, User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.notification_service import NotificationService
from services.settings_service import SettingsService
from texts import templates
from utils.datetime_utils import iso_minus_days, utc_now_iso
from utils.logging_setup import get_logger
from utils.security import sanitize
from utils.validators import clean_multiline

logger = get_logger(__name__)

#: توقيع دالة إرسال رسالة إذاعة واحدة (تُمرَّر من طبقة تيليجرام)
#: (telegram_id, text, media_file_id, media_type) -> message_id | None
BroadcastSender = Callable[[int, str, str | None, str | None], Awaitable[int | None]]

#: أقصى طول لنص الإذاعة بلا وسائط (حد تيليجرام 4096 ونترك هامشاً)
MAX_BROADCAST_TEXT = 3500

#: أقصى طول للنص المرافق لصورة (حد التعليق في تيليجرام 1024)
MAX_BROADCAST_CAPTION = 1000

#: شرائح الاستهداف المدعومة ووصفها العربي
TARGETS: dict[str, str] = {
    "all": "👥 كل المستخدمين",
    "active": "🔥 النشطون مؤخراً",
    "buyers": "🛒 من لديه طلب سابق",
    "no_orders": "🌱 مسجّلون بلا طلبات",
}

#: الحالات التي يمكن الإرسال منها
RESUMABLE_STATUSES = (BroadcastStatus.DRAFT, BroadcastStatus.PAUSED)


@dataclass(slots=True)
class BroadcastRound:
    """حصيلة جولة إرسال واحدة (تُسجَّل في اللوق وتظهر في شاشة المهام)."""

    broadcast_id: int = 0
    claimed: int = 0
    sent: int = 0
    failed: int = 0
    blocked: int = 0
    completed: bool = False

    def as_dict(self) -> dict[str, int | bool]:
        """تحويل الحصيلة إلى قاموس للتسجيل."""
        return {
            "broadcast_id": self.broadcast_id,
            "claimed": self.claimed,
            "sent": self.sent,
            "failed": self.failed,
            "blocked": self.blocked,
            "completed": self.completed,
        }


class BroadcastService:
    """إنشاء الرسائل الجماعية وإدارتها وإرسالها على دفعات آمنة."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        auth: AuthService,
        audit: AuditService,
        notifications: NotificationService,
        settings: SettingsService,
    ) -> None:
        """تهيئة الخدمة باعتمادياتها."""
        self.db = db
        self.repos = repos
        self.auth = auth
        self.audit = audit
        self.notifications = notifications
        self.settings = settings
        #: قفل جولة الإرسال: يمنع عاملين متزامنين من حجز المستلمين أنفسهم وإرسال الرسالة مرتين
        #: (التسجيل يتم بعد الإرسال الفعلي، فلا يكفي شرط `status = 'pending'` وحده). صحيح لأن
        #: البوت عملية واحدة بقفل `bot.lock`؛ ولو انقطع التشغيل بين الإرسال والتسجيل يُعاد إرسال رسالة واحدة فقط.
        self._round_lock = asyncio.Lock()

    # ----------------------------- الاستهداف ----------------------------- #

    async def target_label(self, target: str) -> str:
        """وصف عربي للشريحة المستهدفة (يتضمن عدد أيام النشاط عند الحاجة)."""
        if target == "active":
            days = await self.settings.get_int("broadcast_active_days", 30)
            return f"🔥 النشطون آخر {days} يوماً"
        return TARGETS.get(target, target)

    async def audience_ids(self, target: str) -> list[int]:
        """
        معرفات المستخدمين الداخلية للشريحة المطلوبة.

        المستبعدون دائماً: المحظورون ومن حظر البوت — إرسال رسالة لهم مضيعة
        للحصة اليومية ويشوّه إحصائية «وصلت».

        الاستثناءات: ValidationError للشريحة غير المعروفة.
        """
        if target not in TARGETS:
            raise ValidationError(
                f"شريحة إذاعة غير معروفة: {target}",
                user_message="❌ شريحة الاستهداف غير معروفة.",
            )
        since = None
        if target == "active":
            days = await self.settings.get_int("broadcast_active_days", 30)
            since = iso_minus_days(max(1, days))
        return await self.repos.users.ids_for_broadcast(target=target, since_iso=since)

    async def audience_count(self, actor: User, target: str) -> int:
        """عدد من ستصلهم الرسالة فعلاً لو أُرسلت الآن (يُعرض قبل التأكيد)."""
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        return len(await self.audience_ids(target))

    async def audience_summary(self, actor: User) -> list[tuple[str, str, int]]:
        """
        جدول الشرائح: (الرمز، الوصف، العدد الحالي) لشاشة اختيار الشريحة.

        الأرقام محسوبة من قاعدة البيانات لحظة العرض — لا تقديرات.
        """
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        rows: list[tuple[str, str, int]] = []
        for code in TARGETS:
            rows.append((code, await self.target_label(code), len(await self.audience_ids(code))))
        return rows

    # ------------------------------ الإنشاء ------------------------------ #

    def validate_text(self, text: str, *, has_media: bool) -> str:
        """
        تنظيف نص الإذاعة والتحقق من طوله.

        مع صورة يصبح النص تعليقاً، وحد تيليجرام للتعليق أقصر بكثير من الرسالة.

        الاستثناءات: ValidationError عند الفراغ أو تجاوز الحد.
        """
        limit = MAX_BROADCAST_CAPTION if has_media else MAX_BROADCAST_TEXT
        return clean_multiline(text, field="نص الرسالة", max_length=limit, min_length=2)

    async def create(
        self,
        actor: User,
        *,
        text: str,
        target: str,
        media_file_id: str | None = None,
        media_type: str | None = None,
    ) -> Broadcast:
        """
        إنشاء إذاعة بحالة «مسودة» مع تثبيت قائمة مستلميها.

        تثبيت القائمة لحظة الإنشاء مقصود: من يسجّل بعد الضغط على «إرسال»
        لا تصله رسالة قديمة، ومن حُظر بعدها لا يُحذف من السجل بل تُسجَّل محاولته.

        الاستثناءات:
            PermissionDeniedError : بلا صلاحية `broadcast.send`.
            ValidationError       : نص فارغ/طويل، شريحة مجهولة، أو شريحة بلا مستلمين.
        """
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        clean = self.validate_text(text, has_media=bool(media_file_id))
        recipients = await self.audience_ids(target)
        if not recipients:
            raise ValidationError(
                f"لا مستلمين في الشريحة {target}",
                user_message="❌ لا يوجد مستخدمون في هذه الشريحة الآن.",
            )

        async with self.db.transaction() as tx:
            broadcast = await self.repos.broadcasts.create(
                tx,
                admin_id=actor.id,
                message_text=clean,
                target=target,
                media_file_id=media_file_id,
                media_type=media_type,
            )
            total = await self.repos.broadcasts.add_recipients(tx, broadcast.id, recipients)
            await self.audit.log(
                tx,
                action="broadcast.send",
                admin_id=actor.id,
                target_type="broadcast",
                target_id=broadcast.id,
                before=None,
                after={"target": target, "recipients": total, "has_media": bool(media_file_id)},
                details=clean[:200],
            )
        logger.info(
            "أنشأ الأدمن %s إذاعة #%s للشريحة %s بعدد %s مستلم",
            actor.id, broadcast.id, target, total,
        )
        refreshed = await self.repos.broadcasts.get(broadcast.id)
        return refreshed or broadcast

    # ------------------------------ التحكم ------------------------------- #

    async def _require(self, broadcast_id: int) -> Broadcast:
        """
        جلب إذاعة أو رفع خطأ واضح.

        الاستثناءات: ValidationError إذا لم توجد.
        """
        broadcast = await self.repos.broadcasts.get(broadcast_id)
        if broadcast is None:
            raise ValidationError(
                f"إذاعة غير موجودة: {broadcast_id}", user_message="❌ هذه الرسالة غير موجودة."
            )
        return broadcast

    async def start(self, actor: User, broadcast_id: int) -> Broadcast:
        """
        بدء (أو استئناف) الإرسال.

        التحقق من الحالة السابقة إلزامي: لا نعيد تشغيل إذاعة مكتملة أو ملغاة
        حتى لا يُرسل النص مرتين لمن استلمه.

        الاستثناءات: PermissionDeniedError · ValidationError على الحالة غير المسموحة.
        """
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        broadcast = await self._require(broadcast_id)
        if broadcast.status not in RESUMABLE_STATUSES:
            raise ValidationError(
                f"حالة غير قابلة للبدء: {broadcast.status}",
                user_message="⚠️ لا يمكن بدء هذه الرسالة في حالتها الحالية.",
            )
        remaining = await self.repos.broadcasts.pending_count(broadcast_id)
        if remaining == 0:
            raise ValidationError(
                "لا مستلمين متبقين", user_message="⚠️ لا يوجد مستلمون متبقون في هذه الرسالة."
            )

        async with self.db.transaction() as tx:
            started = await self.repos.broadcasts.set_status(
                tx,
                broadcast_id,
                BroadcastStatus.RUNNING,
                expected_statuses=RESUMABLE_STATUSES,       # شرط ذرّي: لا نُحيي إذاعة أُلغيت/اكتملت للتو
                started_at=broadcast.started_at or utc_now_iso(),
            )
            if not started:
                raise ValidationError(
                    f"تغيّرت حالة الإذاعة {broadcast_id} أثناء البدء",
                    user_message="⚠️ تغيّرت حالة هذه الرسالة للتو (أُلغيت أو اكتملت) — حدّث الشاشة.",
                )
            await self.audit.log(
                tx,
                action="broadcast.send",
                admin_id=actor.id,
                target_type="broadcast",
                target_id=broadcast_id,
                before={"status": broadcast.status},
                after={"status": BroadcastStatus.RUNNING.value, "remaining": remaining},
            )
        logger.info("بدأ الأدمن %s إرسال الإذاعة #%s (%s متبقٍ)", actor.id, broadcast_id, remaining)
        return await self._require(broadcast_id)

    async def pause(self, actor: User, broadcast_id: int) -> bool:
        """
        إيقاف مؤقت للإرسال (يمكن استئنافه لاحقاً من نفس النقطة).

        المخرجات: True إن تغيّرت الحالة فعلاً.
        """
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        broadcast = await self._require(broadcast_id)
        if broadcast.status != BroadcastStatus.RUNNING:
            return False
        async with self.db.transaction() as tx:
            changed = await self.repos.broadcasts.set_status(
                tx, broadcast_id, BroadcastStatus.PAUSED, expected_statuses=(BroadcastStatus.RUNNING,)
            )
            if changed:
                await self.audit.log(
                    tx,
                    action="broadcast.send",
                    admin_id=actor.id,
                    target_type="broadcast",
                    target_id=broadcast_id,
                    before={"status": broadcast.status},
                    after={"status": BroadcastStatus.PAUSED.value},
                )
        logger.info("أوقف الأدمن %s الإذاعة #%s مؤقتاً", actor.id, broadcast_id)
        return changed

    async def cancel(self, actor: User, broadcast_id: int) -> bool:
        """
        إلغاء نهائي: لا تُستأنف بعده، ومن وصلته الرسالة تبقى عنده.

        لا نحذف صفوف المستلمين — السجل التاريخي لمن وصلته الرسالة يبقى كاملاً.
        """
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        broadcast = await self._require(broadcast_id)
        if broadcast.status in (BroadcastStatus.COMPLETED, BroadcastStatus.CANCELLED):
            return False
        async with self.db.transaction() as tx:
            changed = await self.repos.broadcasts.set_status(
                tx,
                broadcast_id,
                BroadcastStatus.CANCELLED,
                expected_statuses=(BroadcastStatus.DRAFT, BroadcastStatus.RUNNING, BroadcastStatus.PAUSED),
                finished_at=utc_now_iso(),
            )
            if changed:
                await self.audit.log(
                    tx,
                    action="broadcast.send",
                    admin_id=actor.id,
                    target_type="broadcast",
                    target_id=broadcast_id,
                    before={"status": broadcast.status, "sent": broadcast.sent_count},
                    after={"status": BroadcastStatus.CANCELLED.value},
                )
        logger.warning("ألغى الأدمن %s الإذاعة #%s", actor.id, broadcast_id)
        return changed

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, actor: User, broadcast_id: int) -> Broadcast:
        """جلب إذاعة واحدة للعرض في اللوحة."""
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        return await self._require(broadcast_id)

    async def recent(self, actor: User, *, limit: int = 8) -> list[Broadcast]:
        """آخر الإذاعات (الأحدث أولاً) لشاشة «📣 الرسائل الجماعية»."""
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        return await self.repos.broadcasts.list_recent(limit=limit)

    async def progress(self, actor: User, broadcast_id: int) -> dict[str, Any]:
        """
        تقدم إذاعة بالأرقام الحقيقية: المرسل والفاشل والمحظور والمتبقي.

        كل رقم من قاعدة البيانات مباشرة، لا عدّادات في الذاكرة.
        """
        await self.auth.require_permission(actor, Permission.BROADCAST_SEND)
        broadcast = await self._require(broadcast_id)
        pending = await self.repos.broadcasts.pending_count(broadcast_id)
        done = broadcast.sent_count + broadcast.failed_count + broadcast.blocked_count
        percent = int(done * 100 / broadcast.total_count) if broadcast.total_count else 0
        return {
            "broadcast": broadcast,
            "pending": pending,
            "done": done,
            "percent": min(100, percent),
            "target_label": await self.target_label(broadcast.target),
        }

    # ------------------------------ الإرسال ------------------------------ #

    async def next_running(self) -> Broadcast | None:
        """أقدم إذاعة جارية (نُرسل واحدة في كل جولة حتى لا نتجاوز حدود تيليجرام)."""
        running = await self.repos.broadcasts.list_running()
        return running[0] if running else None

    async def send_batch(self, sender: BroadcastSender, *, limit: int | None = None) -> BroadcastRound:
        """
        جولة إرسال واحدة للإذاعة الجارية الحالية.

        المدخلات:
            sender : دالة إرسال من طبقة تيليجرام ترفع استثناءات الإشعارات المعروفة.
            limit  : حجم الدفعة (الافتراضي من الإعدادات `broadcast_batch_size`).

        المخرجات: حصيلة الجولة. إذاعة بلا متبقٍ تُغلق تلقائياً ويُشعَر منشئها.

        ملاحظة: كل مستلم يُسجَّل في معاملة قصيرة مستقلة، فلا تبقى قاعدة البيانات
        مقفلة أثناء انتظار الشبكة، ولا نفقد نتيجة من أُرسل له عند أي انقطاع.
        """
        if self._round_lock.locked():
            return BroadcastRound()          # جولة أخرى جارية الآن: لا ننتظرها ولا نزاحمها
        async with self._round_lock:
            return await self._send_batch_locked(sender, limit=limit)

    async def _send_batch_locked(self, sender: BroadcastSender, *, limit: int | None) -> BroadcastRound:
        """جسم جولة الإرسال (يُستدعى حصراً تحت `_round_lock`)."""
        broadcast = await self.next_running()
        if broadcast is None:
            return BroadcastRound()

        batch_size = limit or await self.settings.get_int("broadcast_batch_size", 20)
        batch_size = max(1, min(50, batch_size))

        async with self.db.transaction() as tx:
            claimed = await self.repos.broadcasts.claim_recipients(
                tx, broadcast.id, limit=batch_size
            )

        # وتيرة الإرسال من الإعداد `broadcast_rate_per_second` (كان مجرد رقم لا أثر له): فاصل أدنى بين رسالتين
        rate = max(1, await self.settings.get_int("broadcast_rate_per_second", 20))
        gap = 1.0 / rate
        loop = asyncio.get_running_loop()
        last_started: float | None = None

        round_report = BroadcastRound(broadcast_id=broadcast.id, claimed=len(claimed))
        for row in claimed:
            if last_started is not None:
                wait = last_started + gap - loop.time()
                if wait > 0:
                    await asyncio.sleep(wait)
            last_started = loop.time()
            status, error = await self._send_one(sender, broadcast, int(row["telegram_id"]))
            async with self.db.transaction() as tx:
                recorded = await self.repos.broadcasts.mark_recipient(
                    tx, int(row["id"]), status=status, error=error
                )
                if recorded and status == RecipientStatus.BLOCKED:
                    await self.repos.users.set_blocked_bot(tx, int(row["user_id"]), True)
            if not recorded:
                continue  # سُجِّلت نتيجته في جولة أخرى — لا نعدّه مرتين
            if status == RecipientStatus.SENT:
                round_report.sent += 1
            elif status == RecipientStatus.BLOCKED:
                round_report.blocked += 1
            else:
                round_report.failed += 1

        remaining = await self.repos.broadcasts.pending_count(broadcast.id)
        if remaining == 0:
            await self._complete(broadcast.id)
            round_report.completed = True

        if round_report.claimed:
            logger.info("جولة إذاعة: %s", round_report.as_dict())
        return round_report

    async def _send_one(
        self, sender: BroadcastSender, broadcast: Broadcast, telegram_id: int
    ) -> tuple[str, str | None]:
        """
        إرسال رسالة واحدة وتصنيف نتيجتها.

        الأخطاء المؤقتة (شبكة/حد معدل) تُعاد محاولتها **مرة واحدة** بعد ثانية،
        فإن تكررت سُجِّلت كفشل مع نص الخطأ بدل تعليق الطابور إلى الأبد.

        المخرجات: (حالة المستلم، نص الخطأ المختصر أو None).
        """
        for attempt in (1, 2):
            try:
                await sender(
                    telegram_id,
                    broadcast.message_text,
                    broadcast.media_file_id,
                    broadcast.media_type,
                )
            except NotificationBlockedError as exc:
                return RecipientStatus.BLOCKED, sanitize(str(exc))[:200]
            except NotificationTemporaryError as exc:
                if attempt == 1:
                    await asyncio.sleep(1)
                    continue
                return RecipientStatus.FAILED, sanitize(str(exc))[:200]
            except NotificationPermanentError as exc:
                return RecipientStatus.FAILED, sanitize(str(exc))[:200]
            else:
                return RecipientStatus.SENT, None
        return RecipientStatus.FAILED, "تعذر الإرسال بعد محاولتين"

    async def _complete(self, broadcast_id: int) -> None:
        """إغلاق الإذاعة بعد انتهاء مستلميها وإشعار الأدمن الذي أنشأها بالحصيلة."""
        broadcast = await self.repos.broadcasts.get(broadcast_id)
        if broadcast is None or broadcast.status != BroadcastStatus.RUNNING:
            return
        async with self.db.transaction() as tx:
            completed = await self.repos.broadcasts.set_status(
                tx,
                broadcast_id,
                BroadcastStatus.COMPLETED,
                expected_statuses=(BroadcastStatus.RUNNING,),   # إلغاء/إيقاف متزامن لا يُمحى بالإكمال
                finished_at=utc_now_iso(),
            )
            if not completed:
                return
            if broadcast.admin_id:
                title, message = templates.broadcast_finished(
                    broadcast_id=broadcast_id,
                    sent=broadcast.sent_count,
                    failed=broadcast.failed_count,
                    blocked=broadcast.blocked_count,
                )
                await self.notifications.notify_user_manual(
                    tx,
                    user_id=broadcast.admin_id,
                    token=f"broadcast:{broadcast_id}:done",
                    title=title,
                    message=message,
                )
        logger.info(
            "اكتملت الإذاعة #%s: وصلت %s · حظر %s · فشل %s",
            broadcast_id, broadcast.sent_count, broadcast.blocked_count, broadcast.failed_count,
        )
