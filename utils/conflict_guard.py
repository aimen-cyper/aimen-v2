"""
حارس «Conflict» في getUpdates: يُميّز التعارض العابر عن تشغيل نسختين دائماً بنفس التوكن.

الخلفية:
    تيليجرام يسمح لعملية **واحدة** فقط بـ`getUpdates` لكل توكن؛ الثانية تتلقى `Conflict: terminated by other
    getUpdates request`. هذا **ليس خطأ كود** بل بيئة تشغيل: نسخة محلية ما زالت تعمل، أو نشر Render يتداخل فيه
    القديم مع الجديد دقائق، أو خدمتان بنفس التوكن، أو Webhook مفعّل.

السياسة:
    • أول تعارض ⇒ تحذير يشرح الأسباب وطريقة الحل (لا traceback مزعج).
    • تعارض **عابر** (نشر متداخل) يزول وحده ⇒ نتابع بلا تدخل.
    • تعارض **مستمر** (≥ `MIN_EVENTS` أحداث على امتداد ≥ `PERSIST_SECONDS`) ⇒ إيقاف آمن للنسخة الخاسرة
      (إغلاق نظيف + رمز خروج مميّز) بدل حلقة أبدية تتنازع فيها النسختان على الرسائل وتُضاعف الإشعارات.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

from telegram.error import Conflict, TelegramError

from utils.logging_setup import get_logger
from utils.security import sanitize

logger = get_logger(__name__)

#: رمز الخروج عند الإيقاف بسبب تعارض مستمر (يميّزه المشغّل ومراقب الخدمة عن الانهيار=1)
EXIT_CODE_CONFLICT = 3

#: أقل عدد تعارضات لاعتباره مستمراً
MIN_EVENTS = 5
#: أقل امتداد زمني (ثانية) بين أول تعارض وآخره لاعتباره مستمراً لا عابراً
PERSIST_SECONDS = 60.0
#: نافذة الاحتفاظ بالأحداث (ثانية): ما أقدم منها يُنسى فيُعدّ التعارض قد زال
WINDOW_SECONDS = 180.0

GUIDANCE = (
    "تعارض getUpdates: نسخة أخرى من البوت تستخدم نفس التوكن الآن. الأسباب المعتادة: "
    "(1) نسخة محلية/جهاز آخر ما زال يعمل، (2) نشر Render قديم لم يُوقَف بعد أو خدمتان بنفس التوكن، "
    "(3) عملية بوت أخرى على نفس السيرفر. الحل: أوقف النسخة الزائدة (أو أنشئ توكناً منفصلاً للتطوير)."
)


class ConflictGuard:
    """يُغذَّى `on_polling_error` من `errors.error_handler` عند وصول Conflict بلا update (PTB لا يقبل error_callback)."""

    def __init__(
        self,
        stop: Callable[[], None],
        *,
        min_events: int = MIN_EVENTS,
        persist_seconds: float = PERSIST_SECONDS,
        window_seconds: float = WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """
        تهيئة الحارس.

        المدخلات:
            stop : دالة الإيقاف الآمن (`application.stop_running`) — تُستدعى مرة واحدة عند التعارض المستمر.
        """
        self._stop = stop
        self._min_events = min_events
        self._persist_seconds = persist_seconds
        self._window_seconds = window_seconds
        self._clock = clock
        self._events: deque[float] = deque()
        self._warned = False
        self.tripped = False

    def on_polling_error(self, error: TelegramError) -> None:
        """
        معالجة خطأ من حلقة الاستقبال (دالة متزامنة كما يشترط PTB).

        غير التعارض: يُسجَّل تحذيراً منقّىً (رسالة تيليجرام قد تحمل التوكن) والمكتبة تعيد المحاولة وحدها.
        """
        if not isinstance(error, Conflict):
            logger.warning("خطأ مؤقت في استقبال التحديثات: %s: %s", type(error).__name__, sanitize(str(error))[:200])
            return

        now = self._clock()
        self._events.append(now)
        while self._events and now - self._events[0] > self._window_seconds:
            self._events.popleft()

        if not self._warned:
            self._warned = True
            logger.warning("%s", GUIDANCE)
        if self.tripped:
            return

        persistent = len(self._events) >= self._min_events and now - self._events[0] >= self._persist_seconds
        if persistent:
            self.tripped = True
            logger.critical(
                "تعارض مستمر منذ %.0f ثانية (%s حدثاً) — إيقاف هذه النسخة بأمان. %s",
                now - self._events[0], len(self._events), GUIDANCE,
            )
            self._stop()

    @property
    def recent_conflicts(self) -> int:
        """عدد التعارضات ضمن النافذة الحالية (للتشخيص)."""
        now = self._clock()
        return sum(1 for moment in self._events if now - moment <= self._window_seconds)
