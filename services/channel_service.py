"""
خدمة القنوات الإدارية: النشر الدائم (تنبيهات الإدارة + توثيق الطلبات) وتشخيص وجهات الإرسال.

المبادئ:
    • **النشر عبر صندوق دائم** (`channel_outbox`): يُكتب المنشور في معاملة الحدث، ويرسله job بمحاولات
      متدرجة. فشل تيليجرام المؤقت لا يُسقط طلباً ولا يضيّع سجلاً.
    • **قناة النسخ الاحتياطي للنسخ فقط**: لا يُنشر فيها شيء آخر؛ وإن تطابقت وجهة تنبيه/توثيق معها
      تُرفض الوجهة وتُسجَّل المشكلة (ولا يُرسل إليها).
    • فشل **دائم** (قناة غير موجودة / البوت ليس مشرفاً) يُنبِّه الأدمن مرة يومياً بسبب واضح، بلا
      تكرار للمنشور الفاشل وبلا حلقة تنبيهات (تنبيه الفشل نفسه لا يُنسخ للقناة).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Awaitable, Callable

from core.exceptions import (
    NotificationBlockedError,
    NotificationPermanentError,
    NotificationTemporaryError,
)
from core.permissions import Permission
from database.database import Database, Tx
from database.repositories import Repositories
from services.notification_service import NotificationSender, NotificationService
from services.settings_service import SettingsService
from telegram.error import BadRequest, Forbidden, NetworkError, TelegramError, TimedOut
from utils.channel_ref import try_parse_chat_id
from utils.datetime_utils import parse_iso, to_iso, utc_now
from utils.logging_setup import get_logger
from utils.security import sanitize

logger = get_logger(__name__)

#: أنواع المنشورات
KIND_ADMIN_ALERT = "admin_alert"
KIND_ORDERS_LOG = "orders_log"

#: مفتاح الإعداد لوجهة كل نوع
_SETTING_FOR_KIND = {KIND_ADMIN_ALERT: "admin_alert_chat_id", KIND_ORDERS_LOG: "orders_log_chat_id"}

#: فاصل بين منشورين متتاليين (حد تيليجرام ~20 رسالة/دقيقة للقناة الواحدة)
POST_GAP_SECONDS = 0.4

#: تأجيل منشور توثيق لم تُضبط وجهته بعد (يبقى بالطابور حتى `channel_post_ttl_hours` ثم يُتخطّى)
NO_DESTINATION_RETRY_SECONDS = 600

#: ردّ نداء عند نجاح نشر: (المنشور، المحادثة، رقم الرسالة) — لتسجيل مرجع رسالة قابلة للتحديث
OnPostSent = Callable[[Any, Any, Any], Awaitable[None]]


@dataclass(slots=True)
class FlushReport:
    """حصيلة جولة نشر."""

    claimed: int = 0
    sent: int = 0
    retried: int = 0
    failed: int = 0
    skipped: int = 0
    deferred: int = 0


@dataclass(slots=True)
class ChannelCheck:
    """نتيجة فحص وجهة: ok=True سليمة، False مشكلة مؤكدة، None تعذّر الجزم (شبكة)."""

    label: str
    ref: int | str | None
    ok: bool | None
    title: str = ""
    problem: str = ""
    hints: list[str] = field(default_factory=list)


class ChannelService:
    """نشر منشورات القنوات وفحص صحة الوجهات."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        notifications: NotificationService,
        *,
        alert_chat_fallback: int | str | None = None,
        backup_channel_id: int | str | None = None,
    ) -> None:
        """
        تهيئة الخدمة.

        المدخلات:
            alert_chat_fallback : `ADMIN_ALERT_CHAT_ID` من البيئة (يُستعمل إن لم يُضبط الإعداد).
            backup_channel_id   : قناة النسخ (محجوزة للنسخ؛ ممنوع استعمالها كوجهة تنبيه/توثيق).
        """
        self.db = db
        self.repos = repos
        self.settings = settings
        self.notifications = notifications
        self.alert_chat_fallback = alert_chat_fallback
        self.backup_channel_id = backup_channel_id

    # ------------------------------- الإدراج ------------------------------ #

    async def enqueue(self, tx: Tx, *, kind: str, title: str, message: str, dedupe_key: str) -> int | None:
        """وضع منشور في الصندوق داخل معاملة قائمة (None ⇒ موجود مسبقاً بنفس المفتاح)."""
        return await self.repos.channel_outbox.enqueue(
            tx, kind=kind, title=title, message=message, dedupe_key=dedupe_key
        )

    # ------------------------------- الوجهات ------------------------------ #

    async def destination(self, kind: str) -> tuple[int | str | None, str]:
        """
        وجهة منشورات نوع معيّن.

        المخرجات: (المعرّف أو None، سبب عدم وجود وجهة إن وُجد). التعارض مع قناة النسخ ⇒ لا وجهة.
        """
        key = _SETTING_FOR_KIND[kind]
        chat = try_parse_chat_id(await self.settings.get_str(key, ""), allow_user_ids=True)
        if chat is None and kind == KIND_ADMIN_ALERT:
            chat = try_parse_chat_id(self.alert_chat_fallback, allow_user_ids=True)
        if chat is None:
            return None, "لا وجهة مضبوطة"
        if self.backup_channel_id is not None and str(chat) == str(self.backup_channel_id):
            return None, "الوجهة هي قناة النسخ الاحتياطي (مخصصة للنسخ فقط)"
        return chat, ""

    # -------------------------------- النشر ------------------------------- #

    async def flush(
        self,
        sender: NotificationSender,
        *,
        limit: int = 20,
        on_sent: OnPostSent | None = None,
        budget_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> FlushReport:
        """
        نشر دفعة من الصندوق.

        المدخلات:
            sender  : نفس مُرسل الإشعارات `(chat_id, title, message)`، يرفع استثناءات الإشعارات المصنّفة.
            budget_seconds : سقف زمن الجولة؛ ما تبقّى يعود للطابور فوراً (WP7).
            on_sent : ردّ نداء اختياري بعد كل نشر ناجح (تسجيل مرجع منشور الطلب)؛ فشله لا يمس النشر.
        """
        report = FlushReport()
        async with self.db.transaction() as tx:
            posts = await self.repos.channel_outbox.claim_batch(tx, limit=limit)
        report.claimed = len(posts)

        alerted: set[str] = set()
        started = clock()
        for index, post in enumerate(posts):
            if budget_seconds is not None and clock() - started >= budget_seconds:
                rest = [item.id for item in posts[index:]]
                async with self.db.transaction() as tx:
                    await self.repos.channel_outbox.release_claims(tx, rest)
                report.deferred = len(rest)
                logger.warning("نفدت ميزانية جولة القنوات (%.0fث): أُعيد %d إلى الطابور", budget_seconds, len(rest))
                break
            chat, why = await self.destination(post.kind)
            if chat is None:
                if await self._keep_waiting_for_destination(post, why):
                    report.retried += 1
                    continue
                async with self.db.transaction() as tx:
                    await self.repos.channel_outbox.mark_skipped(tx, post.id, why)
                report.skipped += 1
                if "النسخ" in why and post.kind not in alerted:
                    alerted.add(post.kind)
                    await self._alert_problem(post.kind, why)
                continue

            if index:
                await asyncio.sleep(POST_GAP_SECONDS)
            try:
                message_id = await sender(chat, post.title, post.message)
            except NotificationTemporaryError as exc:
                async with self.db.transaction() as tx:
                    await self.repos.channel_outbox.mark_failed(tx, post.id, error=str(exc))
                report.retried += 1
            except (NotificationBlockedError, NotificationPermanentError) as exc:
                reason = sanitize(str(exc))[:200]
                async with self.db.transaction() as tx:
                    await self.repos.channel_outbox.mark_failed(tx, post.id, error=reason, permanent=True)
                report.failed += 1
                logger.error("تعذّر النشر في القناة (%s): %s", post.kind, reason)
                if post.kind not in alerted:
                    alerted.add(post.kind)
                    await self._alert_problem(post.kind, reason)
            else:
                async with self.db.transaction() as tx:
                    await self.repos.channel_outbox.mark_sent(tx, post.id)
                report.sent += 1
                if on_sent is not None:
                    try:
                        await on_sent(post, chat, message_id)
                    except Exception:                        # noqa: BLE001 - تسجيل المرجع تجميلي
                        logger.exception("تعذّر تسجيل مرجع منشور القناة %s", post.id)
        return report

    async def _keep_waiting_for_destination(self, post: Any, why: str) -> bool:
        """
        منشور توثيق الطلبات بلا وجهة: يبقى بالطابور (بتأجيل) حتى `channel_post_ttl_hours` بدل التخطي النهائي.

        كان التخطي نهائياً فيضيع توثيق كل طلب أُنشئ قبل ضبط القناة. تنبيهات الإدارة لا تُؤجَّل (قيمتها لحظية)،
        وتعارض قناة النسخ يبقى تخطياً فورياً.
        """
        if post.kind != KIND_ORDERS_LOG or "النسخ" in why:
            return False
        ttl_hours = await self.settings.get_int("channel_post_ttl_hours", 72)
        created = parse_iso(post.created_at)
        if created is None or utc_now() - created > timedelta(hours=ttl_hours):
            return False
        async with self.db.transaction() as tx:
            await self.repos.channel_outbox.defer(
                tx, post.id, seconds=NO_DESTINATION_RETRY_SECONDS, reason=f"بانتظار الوجهة: {why}"
            )
        return True

    async def requeue_failed(self, kind: str | None = None) -> int:
        """
        إعادة المنشورات الفاشلة/المتخطّاة (ضمن مدة الصلاحية) للطابور — بعد تصحيح الوجهة.

        المخرجات: عدد ما أُعيد. تُستدعى تلقائياً عند تعديل `orders_log_chat_id`/`admin_alert_chat_id`.
        """
        ttl_hours = await self.settings.get_int("channel_post_ttl_hours", 72)
        since = to_iso(utc_now() - timedelta(hours=ttl_hours))
        async with self.db.transaction() as tx:
            count = await self.repos.channel_outbox.requeue_failed(tx, kind=kind, created_after_iso=since)
        if count:
            logger.info("أُعيد %s منشور قناة إلى الطابور (%s)", count, kind or "كل الأنواع")
        return count

    async def _alert_problem(self, kind: str, reason: str) -> None:
        """تنبيه الأدمن (مرة يومياً لكل نوع) بأن وجهة النشر معطّلة — بلا نسخ للقناة (تفادياً للحلقة)."""
        label = "تنبيهات الإدارة" if kind == KIND_ADMIN_ALERT else "توثيق الطلبات"
        async with self.db.transaction() as tx:
            await self.notifications.notify_admins(
                tx,
                permission=Permission.SETTINGS_UPDATE,
                token=f"channel-dest:{kind}:{utc_now().strftime('%Y%m%d')}",
                title=f"⚠️ تعذّر النشر في قناة {label}",
                message=(
                    f"السبب: {reason}\n"
                    "افتح: لوحة التحكم ← 📢 القنوات للتشخيص، وتأكد أن البوت مشرف في القناة "
                    "وأن المعرّف بصيغة -100xxxxxxxxxx أو @username."
                ),
                copy_to_channel=False,
            )

    # -------------------------------- التشخيص ----------------------------- #

    async def diagnose(self, bot: Any, label: str, ref: int | str | None, *, needs_post: bool = True) -> ChannelCheck:
        """
        فحص وجهة فعلياً عبر تيليجرام: هل تُرى؟ وهل البوت قادر على النشر فيها؟

        المدخلات:
            needs_post : True للوجهات التي ينشر فيها البوت (تنبيهات/توثيق/نسخ)، False لقنوات الاشتراك
                         (يكفي أن يرى البوت العضوية، وهذا يتطلب أن يكون مشرفاً في القناة).
        """
        if ref is None:
            return ChannelCheck(label=label, ref=None, ok=None, problem="غير مضبوطة")
        try:
            chat = await bot.get_chat(ref)
        except BadRequest as exc:
            return self._bad(label, ref, exc)
        except Forbidden:
            return ChannelCheck(
                label=label, ref=ref, ok=False,
                problem="البوت محظور/مطرود من هذه المحادثة",
                hints=["أعد إضافة البوت مشرفاً في القناة."],
            )
        except (TimedOut, NetworkError) as exc:
            return ChannelCheck(label=label, ref=ref, ok=None, problem=f"تعذّر الاتصال بتيليجرام ({type(exc).__name__})")
        except TelegramError as exc:
            return ChannelCheck(label=label, ref=ref, ok=False, problem=sanitize(str(exc))[:150])

        title = str(getattr(chat, "title", None) or getattr(chat, "full_name", None) or "")
        chat_type = str(getattr(chat, "type", ""))
        if chat_type == "private":
            return ChannelCheck(label=label, ref=ref, ok=True, title=title)

        try:
            me = await bot.get_me()
            member = await bot.get_chat_member(chat.id, me.id)
        except (BadRequest, Forbidden) as exc:             # يسبق NetworkError: BadRequest فرع منه في PTB
            return ChannelCheck(label=label, ref=ref, ok=False, title=title, problem=sanitize(str(exc))[:150])
        except (TimedOut, NetworkError) as exc:
            return ChannelCheck(label=label, ref=ref, ok=None, title=title, problem=f"تعذّر الاتصال ({type(exc).__name__})")
        except TelegramError as exc:
            return ChannelCheck(label=label, ref=ref, ok=False, title=title, problem=sanitize(str(exc))[:150])

        status = str(getattr(member, "status", ""))
        if chat_type == "channel" and status != "administrator" and status != "creator":
            return ChannelCheck(
                label=label, ref=ref, ok=False, title=title,
                problem="البوت ليس مشرفاً في القناة",
                hints=["أضِف البوت مشرفاً (Administrator) في القناة."],
            )
        if needs_post and chat_type == "channel" and getattr(member, "can_post_messages", True) is False:
            return ChannelCheck(
                label=label, ref=ref, ok=False, title=title,
                problem="البوت مشرف لكن بلا صلاحية «نشر الرسائل»",
                hints=["فعّل صلاحية Post Messages للبوت في إعدادات المشرف."],
            )
        if status in {"left", "kicked"}:
            return ChannelCheck(label=label, ref=ref, ok=False, title=title, problem="البوت ليس عضواً في المحادثة")
        return ChannelCheck(label=label, ref=ref, ok=True, title=title)

    @staticmethod
    def _bad(label: str, ref: int | str, exc: BadRequest) -> ChannelCheck:
        """تفسير BadRequest (غالباً chat not found) بسبب وحل واضحين."""
        text = str(exc).lower()
        if "chat not found" in text or "channel_invalid" in text:
            hints = [
                "المعرّف خاطئ، أو البوت ليس عضواً/مشرفاً في هذه القناة (القناة الخاصة لا تُرى بلا عضوية).",
                "للقناة الخاصة استعمل -100xxxxxxxxxx (وليس رابط الدعوة)، وأضِف البوت مشرفاً أولاً.",
            ]
            if isinstance(ref, int) and ref > 0:
                hints.insert(0, "معرّف القنوات سالب ويبدأ بـ -100.")
            return ChannelCheck(label=label, ref=ref, ok=False, problem="Chat not found", hints=hints)
        return ChannelCheck(label=label, ref=ref, ok=False, problem=sanitize(str(exc))[:150])
