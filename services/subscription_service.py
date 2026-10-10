"""
خدمة الاشتراك الإجباري: التحقق **الفعلي** من عضوية المستخدم في القنوات المطلوبة.

القواعد:
    • القنوات الأربع (الرسمية، توثيق الطلبات، التحديثات، العروض) تُدار من الإعدادات؛ القناة الفارغة غير مطلوبة،
      وإذا كانت كلها فارغة أو `subscription_required=false` فلا بوابة.
    • العضوية تُقرأ من تيليجرام (`getChatMember`) — لا نفترضها: الحالات المعتمدة فقط `creator/administrator/member`
      أو `restricted` مع `is_member`. ما عداها (`left/kicked`) غير مشترك.
    • **الفشل مغلق**: تعذّر التحقق (قناة غير مضبوطة صحيحاً، البوت ليس مشرفاً، انقطاع) لا يُعدّ اشتراكاً.
      الاستثناء الوحيد: مستخدم تأكّد اشتراكه خلال الساعة الأخيرة وتعذّر التحقق مؤقتاً بسبب **شبكة** (لا إعداد).
    • نتيجة «مشترك» تُخزَّن في الذاكرة 5 دقائق لتخفيف النداءات (4 نداءات لكل تحقق)؛ ضغط «تحقق» يتجاوز الكاش.
    • الفريق الإداري معفى (يقرّر ذلك الطبقة الوسيطة)، حتى لا يُقفل الأدمن عن لوحة تصحيح القنوات نفسها.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from database.database import Database
from database.repositories import Repositories
from services.notification_service import NotificationService
from services.settings_service import SettingsService
from telegram.error import BadRequest, Forbidden, NetworkError, TelegramError, TimedOut
from utils.channel_ref import ChannelRef, ChannelRefError, parse_channel_value
from utils.datetime_utils import utc_now
from utils.logging_setup import get_logger
from utils.security import sanitize

logger = get_logger(__name__)

#: القنوات المطلوبة: (مفتاح الإعداد، أيقونة، اسم العرض)
REQUIRED_CHANNEL_SPECS: tuple[tuple[str, str, str], ...] = (
    ("channel_official", "📢", "القناة الرسمية"),
    ("channel_proofs", "📚", "قناة توثيق/متابعة الطلبات"),
    ("channel_updates", "🔔", "قناة التحديثات"),
    ("channel_offers", "🎁", "قناة العروض"),
)

#: حالات العضوية المعتمدة
MEMBER_STATUSES = frozenset({"creator", "administrator", "member"})

#: مدة اعتماد نتيجة «مشترك» من الكاش (ثانية)
CACHE_TTL_SECONDS = 300.0
#: مدة سماح عند تعذّر التحقق بسبب الشبكة لمن تأكّد اشتراكه سابقاً
NETWORK_GRACE_SECONDS = 3600.0
#: سقف ذاكرة الكاش (مدخلات)
MAX_CACHE_ENTRIES = 20_000


@dataclass(frozen=True, slots=True)
class RequiredChannel:
    """قناة مطلوبة بعد القراءة من الإعدادات."""

    key: str
    emoji: str
    label: str
    ref: ChannelRef

    @property
    def title(self) -> str:
        """اسم العرض مع الأيقونة."""
        return f"{self.emoji} {self.label}"


@dataclass(slots=True)
class SubscriptionStatus:
    """حصيلة التحقق: المطلوبة، غير المشترك فيها، وما تعذّر التحقق منه (مع السبب)."""

    channels: list[RequiredChannel] = field(default_factory=list)
    missing: list[RequiredChannel] = field(default_factory=list)
    unverifiable: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """مشترك في الكل فعلاً؟ (تعذّر التحقق ≠ اشتراك)."""
        return not self.missing and not self.unverifiable


class SubscriptionService:
    """قراءة القنوات المطلوبة والتحقق من اشتراك المستخدم."""

    def __init__(
        self, db: Database, repos: Repositories, settings: SettingsService, notifications: NotificationService
    ) -> None:
        """تهيئة الخدمة (الكاش في الذاكرة فقط)."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.notifications = notifications
        self._verified_at: dict[tuple[int, str], float] = {}
        self._alerted: set[str] = set()                    # تنبيهات الإعداد المُدرجة اليوم (حماية من قاعدة البيانات)

    # ----------------------------- الإعدادات ------------------------------ #

    async def required_channels(self) -> list[RequiredChannel]:
        """القنوات المطلوبة حالياً (فارغ إن عُطِّلت البوابة أو لم تُضبط قناة). الصيغة الخاطئة تُتجاهل مع تحذير."""
        if not await self.settings.get_bool("subscription_required", True):
            return []
        channels: list[RequiredChannel] = []
        for key, emoji, label in REQUIRED_CHANNEL_SPECS:
            raw = (await self.settings.get_str(key, "")).strip()
            if not raw:
                continue
            try:
                ref = parse_channel_value(raw)
            except ChannelRefError as exc:
                logger.warning("إعداد القناة %s غير صالح (%s) — تُتجاهل في البوابة", key, exc)
                continue
            channels.append(RequiredChannel(key=key, emoji=emoji, label=label, ref=ref))
        return channels

    # ------------------------------- التحقق ------------------------------- #

    async def check(self, bot: Any, telegram_id: int, *, force: bool = False) -> SubscriptionStatus:
        """
        التحقق من اشتراك المستخدم في كل القنوات المطلوبة (بالتوازي).

        المدخلات:
            force : تجاوز كاش «مشترك» (يُستعمل عند ضغط زر «تحقق»).
        """
        channels = await self.required_channels()
        status = SubscriptionStatus(channels=channels)
        if not channels:
            return status
        results = await asyncio.gather(
            *(self._check_one(bot, telegram_id, channel, force=force) for channel in channels)
        )
        for channel, (state, reason) in zip(channels, results):
            if state == "member":
                continue
            if state == "missing":
                status.missing.append(channel)
            else:
                status.unverifiable[channel.key] = reason
        if status.unverifiable:
            await self._alert_config_problem(channels, status.unverifiable)
        return status

    async def _check_one(
        self, bot: Any, telegram_id: int, channel: RequiredChannel, *, force: bool
    ) -> tuple[str, str]:
        """فحص قناة واحدة؛ المخرجات: ("member"|"missing"|"error", سبب)."""
        cache_key = (telegram_id, channel.key + str(channel.ref.chat_id))
        now = time.monotonic()
        verified = self._verified_at.get(cache_key)
        if not force and verified is not None and now - verified < CACHE_TTL_SECONDS:
            return "member", ""
        try:
            member = await bot.get_chat_member(channel.ref.chat_id, telegram_id)
        except BadRequest as exc:                          # يسبق NetworkError: BadRequest فرع منه في PTB
            text = str(exc).lower()
            if "user not found" in text or "participant_id_invalid" in text or "user_not_participant" in text:
                self._verified_at.pop(cache_key, None)
                return "missing", ""
            return "error", sanitize(str(exc))[:150]       # chat not found وغيره: إعداد القناة/البوت
        except Forbidden as exc:
            return "error", sanitize(str(exc))[:150] or "البوت ليس مشرفاً في القناة"
        except (TimedOut, NetworkError) as exc:
            if verified is not None and now - verified < NETWORK_GRACE_SECONDS:
                return "member", ""              # شبكة فقط + اشتراك مؤكَّد حديثاً
            return "error", f"تعذّر الاتصال بتيليجرام ({type(exc).__name__})"
        except TelegramError as exc:
            return "error", sanitize(str(exc))[:150]

        status = str(getattr(member, "status", ""))
        is_member = status in MEMBER_STATUSES or (status == "restricted" and bool(getattr(member, "is_member", False)))
        if is_member:
            self._remember(cache_key, now)
            return "member", ""
        self._verified_at.pop(cache_key, None)
        return "missing", ""

    def _remember(self, key: tuple[int, str], now: float) -> None:
        """حفظ نتيجة «مشترك» مع سقف لحجم الذاكرة (تُحذف المنتهية ثم الأقدم)."""
        if len(self._verified_at) >= MAX_CACHE_ENTRIES:
            expired = [k for k, ts in self._verified_at.items() if now - ts >= NETWORK_GRACE_SECONDS]
            for old in expired:
                self._verified_at.pop(old, None)
            while len(self._verified_at) >= MAX_CACHE_ENTRIES:
                self._verified_at.pop(next(iter(self._verified_at)))
        self._verified_at[key] = now

    def forget(self, telegram_id: int) -> None:
        """نسيان كاش مستخدم (بعد تغيير إعداد القنوات مثلاً)."""
        for key in [k for k in self._verified_at if k[0] == telegram_id]:
            self._verified_at.pop(key, None)

    def clear_cache(self) -> None:
        """تفريغ الكاش كله (عند تعديل القنوات من الإعدادات)."""
        self._verified_at.clear()

    async def _alert_config_problem(self, channels: list[RequiredChannel], problems: dict[str, str]) -> None:
        """تنبيه الأدمن (مرة يومياً لكل قناة) بأن القناة لا يمكن التحقق منها (إعداد/صلاحية البوت)."""
        from core.permissions import Permission

        by_key = {channel.key: channel for channel in channels}
        for key, reason in problems.items():
            channel = by_key.get(key)
            if channel is None or reason.startswith("تعذّر الاتصال"):
                continue                                   # الشبكة المؤقتة ليست مشكلة إعداد
            day_key = f"{key}:{utc_now().strftime('%Y%m%d')}"
            if day_key in self._alerted:
                continue
            if len(self._alerted) > 200:
                self._alerted.clear()
            self._alerted.add(day_key)
            try:
                async with self.db.transaction() as tx:
                    await self.notifications.notify_admins(
                        tx,
                        permission=Permission.SETTINGS_UPDATE,
                        token=f"sub-config:{key}:{utc_now().strftime('%Y%m%d')}",
                        title=f"⚠️ تعذّر التحقق من {channel.label}",
                        message=(
                            f"السبب: {reason}\n"
                            "المستخدمون الجدد لن يتجاوزوا بوابة الاشتراك حتى يُصلَح. تأكد أن البوت مشرف في "
                            "القناة وأن المعرّف صحيح (لوحة التحكم ← 📢 القنوات)."
                        ),
                    )
            except Exception:                              # noqa: BLE001 - التنبيه لا يجوز أن يكسر بوابة المستخدم
                logger.exception("تعذّر إدراج تنبيه مشكلة القناة %s", key)
