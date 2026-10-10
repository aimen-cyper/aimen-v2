"""
تحديث رسائل تيليجرام التي تعرض حالة طلب (بند 4).

المبادئ:
    • **حالة الطلب في `orders` هي المصدر الوحيد**؛ تُكتب في معاملة الفحص/الإجراء. هذه الخدمة تعمل **بعدها وبمعزل**:
      فشل تعديل رسالة (حذفها المستخدم، حد معدل، انقطاع) يزيد عدّاد المرجع فقط ولا يلمس `orders` ولا المال.
    • كل رسالة قابلة للتحديث لها صف في `order_message_refs` (النوع/المحادثة/الرسالة/مفتاح الحالة المعروضة).
      المهمة الدورية تختار الصفوف التي مفتاحها ≠ حالة الطلب الآن وتعدّلها؛ «message is not modified» = نجاح.
    • رسائل الأحداث (اكتمل/فشل/أُلغي/استُرجع) تبقى **رسائل جديدة** (تنبيه صوتي) — هذه الخدمة لا تستبدلها.
    • رسالة المستخدم التي ينتقل فيها إلى شاشة أخرى (تحرير نفس الرسالة) تُوقَف فلا نكتب فوق شاشته (`release_message`).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Protocol

from core.exceptions import (
    NotificationBlockedError,
    NotificationPermanentError,
    NotificationTemporaryError,
)
from database.database import Database
from database.models import OrderMessageRef
from database.repositories import Repositories
from database.repositories.order_message_refs import (
    KIND_CHANNEL_POST,
    KIND_USER_CONFIRM,
    KIND_USER_NOTICE,
)
from services.settings_service import SettingsService
from texts.channel_posts import order_post
from texts.order_messages import user_status_card
from utils.formatters import build_order_view
from utils.logging_setup import get_logger
from utils.security import sanitize

logger = get_logger(__name__)

__all__ = ["OrderMessageService", "MessageEditor", "RefreshReport", "KIND_CHANNEL_POST", "KIND_USER_CONFIRM", "KIND_USER_NOTICE"]

#: تأجيل أول بعد فشل مؤقت (يتضاعف بعدد الإخفاقات)
RETRY_BASE_SECONDS = 60

_USER_KINDS = (KIND_USER_CONFIRM, KIND_USER_NOTICE)

#: مفتاح منع تكرار منشور «طلب جديد» في صندوق القناة: `order:<id>`
_ORDER_POST_KEY = re.compile(r"^order:(\d+)$")


class MessageEditor(Protocol):
    """مُحرِّر الرسائل (يوفّره جسر تيليجرام): يرفع استثناءات الإشعارات المصنّفة، و«لم يتغير» ليس خطأً."""

    async def edit_card(self, chat_id: str, message_id: int, html: str, order_id: int) -> None:
        """تعديل بطاقة حالة المستخدم (HTML جاهز + زر عرض الطلب)."""

    async def edit_post(self, chat_id: str, message_id: int, title: str, message: str) -> None:
        """تعديل منشور قناة التوثيق (يُنسَّق كبقية المنشورات)."""


@dataclass(slots=True)
class RefreshReport:
    """حصيلة جولة تحديث الرسائل."""

    claimed: int = 0
    edited: int = 0
    retried: int = 0
    dead: int = 0


class OrderMessageService:
    """تسجيل رسائل الطلبات وتحديثها عند تغيّر الحالة."""

    def __init__(self, db: Database, repos: Repositories, settings: SettingsService) -> None:
        """تهيئة الخدمة (مفاتيح رسائل المستخدم الحيّة تُحمَّل كسولاً عند أول `release_message`)."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self._live_user_keys: set[tuple[str, int]] | None = None

    # ------------------------------- التسجيل ------------------------------ #

    async def register(self, *, order_id: int, kind: str, chat_id: int | str, message_id: int | None) -> bool:
        """
        تسجيل رسالة تعرض حالة الطلب (آخر تسجيل للنوع يحلّ محل السابق).

        المخرجات: True إن سُجّلت. لا يرفع أبداً: التسجيل ميزة تجميلية لا يجوز أن تُفشل طلباً.
        """
        if not message_id:
            return False
        try:
            order = await self.repos.orders.get(order_id)
            if order is None:
                return False
            async with self.db.transaction() as tx:
                await self.repos.order_message_refs.upsert(
                    tx, order=order, kind=kind, chat_id=chat_id, message_id=message_id
                )
            if kind in _USER_KINDS and self._live_user_keys is not None:
                self._live_user_keys.add((str(chat_id), int(message_id)))
            return True
        except Exception:                                    # noqa: BLE001
            logger.exception("تعذّر تسجيل مرجع رسالة الطلب %s (%s)", order_id, kind)
            return False

    async def on_channel_post_sent(self, post, chat_id: int | str, message_id: int | None) -> None:
        """ردّ نداء `ChannelService.flush`: منشور «طلب جديد» نُشر ⇒ نسجّل مرجعه ليُعدَّل عند تغيّر الحالة."""
        match = _ORDER_POST_KEY.match(getattr(post, "dedupe_key", "") or "")
        if getattr(post, "kind", "") != "orders_log" or match is None:
            return
        await self.register(
            order_id=int(match.group(1)), kind=KIND_CHANNEL_POST, chat_id=chat_id, message_id=message_id
        )

    async def release_message(self, chat_id: int | str, message_id: int) -> None:
        """
        رسالة مستخدم صارت تعرض شاشة أخرى (تنقّل فيها): نوقف تحديثها حتى لا نكتب فوق شاشته.

        رخيصة: بعد التحميل الأول تُفحص ذاكرياً ولا تلمس القاعدة إلا عند وجود مرجع فعلي. لا ترفع أبداً.
        """
        try:
            if self._live_user_keys is None:
                self._live_user_keys = await self.repos.order_message_refs.list_live_user_keys()
            key = (str(chat_id), int(message_id))
            if key not in self._live_user_keys:
                return
            self._live_user_keys.discard(key)
            async with self.db.transaction() as tx:
                await self.repos.order_message_refs.kill_message(tx, chat_id, message_id)
        except Exception:                                    # noqa: BLE001
            logger.exception("تعذّر إيقاف مرجع الرسالة %s/%s", chat_id, message_id)

    # -------------------------------- التحديث ----------------------------- #

    async def refresh_due(
        self, editor: MessageEditor, *, limit: int = 15, budget_seconds: float = 10.0
    ) -> RefreshReport:
        """
        تعديل الرسائل المتأخرة عن حالة طلباتها (جولة واحدة بحد عدد وميزانية زمنية).

        فشل رسالة لا يوقف البقية، إلا حدّ المعدل المؤقت فيوقف الجولة (لا نطرق تيليجرام وهو يطلب الانتظار).
        """
        report = RefreshReport()
        if not await self.settings.get_bool("order_message_refresh_enabled", True):
            return report
        refs = await self.repos.order_message_refs.list_stale(limit=limit)
        report.claimed = len(refs)
        if not refs:
            return report

        symbol = await self.settings.money_symbol()
        usd_rate = await self.settings.usd_rate()
        deadline = time.monotonic() + budget_seconds
        for ref in refs:
            if time.monotonic() >= deadline:
                break
            outcome = await self._refresh_one(editor, ref, symbol=symbol, usd_rate=usd_rate)
            if outcome == "edited":
                report.edited += 1
            elif outcome == "dead":
                report.dead += 1
            else:
                report.retried += 1
                if outcome == "stop":
                    break
        if report.claimed:
            logger.info("جولة تحديث رسائل الطلبات: %s", report)
        return report

    async def _refresh_one(self, editor: MessageEditor, ref: OrderMessageRef, *, symbol: str, usd_rate) -> str:
        """تحديث مرجع واحد؛ المخرجات: edited | dead | retry | stop."""
        order = await self.repos.orders.get(ref.order_id)
        if order is None:
            await self._mark_failed(ref, "الطلب غير موجود", dead=True)
            return "dead"
        try:
            if ref.kind in _USER_KINDS:
                view = build_order_view(order, symbol)
                text = user_status_card(
                    view, service_name=order.service_name_snapshot, link=order.link,
                    updated_at=order.last_check_ok_at or order.updated_at,
                )
                await editor.edit_card(ref.chat_id, ref.message_id, text, order.id)
            else:
                title, message = await self._channel_post(order, symbol=symbol, usd_rate=usd_rate)
                await editor.edit_post(ref.chat_id, ref.message_id, title, message)
        except (NotificationBlockedError, NotificationPermanentError) as exc:
            await self._mark_failed(ref, sanitize(str(exc)), dead=True)
            return "dead"
        except NotificationTemporaryError as exc:
            await self._mark_failed(ref, sanitize(str(exc)), dead=False)
            return "stop"
        except Exception as exc:                             # noqa: BLE001 - لا نُسقط الجولة لرسالة واحدة
            logger.exception("خطأ غير متوقع في تحديث رسالة الطلب %s", ref.order_id)
            await self._mark_failed(ref, f"{type(exc).__name__}: {sanitize(str(exc))}", dead=False)
            return "retry"
        async with self.db.transaction() as tx:
            await self.repos.order_message_refs.mark_rendered(tx, ref.id, order=order)
        return "edited"

    async def _channel_post(self, order, *, symbol: str, usd_rate) -> tuple[str, str]:
        """إعادة بناء منشور القناة بحالة الطلب الحالية (نفس بيانات المنشور الأول، مقنَّعة)."""
        service = await self.repos.services.get(order.service_id)
        category = await self.repos.categories.get(service.category_id) if service else None
        owner = await self.repos.users.get_by_id(order.user_id)
        return order_post(
            category_name=category.name_ar if category else "",
            service_name=order.service_name_snapshot,
            order_code=order.public_code or f"#{order.id}",
            quantity=order.quantity,
            cost_units=order.cost_units,
            symbol=symbol,
            usd_rate=usd_rate,
            user=owner,
            link=order.link,
            status=order.status,
        )

    async def _mark_failed(self, ref: OrderMessageRef, error: str, *, dead: bool) -> None:
        """تسجيل فشل تعديل — في جدول المراجع فقط (لا يمس `orders`)."""
        async with self.db.transaction() as tx:
            await self.repos.order_message_refs.mark_failed(
                tx, ref.id, error=error, retry_seconds=RETRY_BASE_SECONDS, dead=dead
            )
        logger.warning("تعذّر تحديث رسالة الطلب %s (%s): %s", ref.order_id, ref.kind, error)
