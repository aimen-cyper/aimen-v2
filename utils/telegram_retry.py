"""
التعامل مع أعطال الاتصال بتيليجرام (Timeout / ConnectError / RetryAfter) — تمييز الخارجي من الداخلي.

لماذا؟
    `TimedOut` و`ConnectError` أعطال **خارجية** (شبكة/خوادم تيليجرام) وليست خطأ في كودنا، ويجب ألا:
        • تُسقط البوت أو المعالج بعد أن أُنجزت العملية المالية (الطلب أُنشئ والرصيد خُصم)؛
        • تُضيع إشعاراً (للإشعارات صندوق دائم بمحاولات مجدولة)؛
        • تُخفي أخطاء الكود الحقيقية — و`BadRequest` فرع من `NetworkError` في PTB لذلك يُفحص **قبله دائماً**.

سياسة إعادة المحاولة (`call_telegram`):
    • عملية **متساوية الأثر** (تحرير رسالة، الرد على زر): تُعاد عند أي عطل شبكي.
    • عملية **غير متساوية الأثر** (إرسال رسالة جديدة): تُعاد فقط حين يكون التسليم مستحيلاً
      (فشل اتصال / مهلة تجمّع الاتصالات / `RetryAfter`)؛ أما مهلة القراءة فالرسالة قد تكون وصلت،
      وإعادة الإرسال تُكرّرها — فلا تُعاد (والأثر المالي محمي أصلاً بمفتاح منع التكرار وصندوق الإشعارات).

التصنيف (`classify`):
    external  : مهلة/انقطاع/قيود معدّل — مؤقت وخارجي ⇒ تحذير فقط وبلا إنذار لكل حالة.
    user_side : المستخدم حظر البوت (Forbidden).
    benign    : رفض غير ضار («message is not modified»، ضغطة زر قديمة…).
    internal  : أي شيء آخر (منه `BadRequest` غير الضار = خطأ في طلبنا نحن) ⇒ خطأ كامل مع تنبيه.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import TypeVar

from telegram.error import BadRequest, Conflict, Forbidden, NetworkError, RetryAfter, TimedOut

from utils.logging_setup import get_logger
from utils.security import sanitize

logger = get_logger(__name__)

T = TypeVar("T")

#: فواصل الانتظار بين المحاولات (ثوانٍ) — قصيرة: المعالجة متسلسلة فلا نُعطّل بقية المستخدمين
RETRY_DELAYS: tuple[float, ...] = (0.4, 1.2)

#: أقصى انتظار نقبله لطلب `RetryAfter` داخل معالج تفاعلي (بعدها نستسلم بدل تجميد البوت)
MAX_RETRY_AFTER_WAIT = 5.0

#: نصوص رفض غير ضارة من تيليجرام (بحروف صغيرة) — حالات طبيعية لا تستحق خطأً
BENIGN_BAD_REQUESTS: tuple[str, ...] = (
    "message is not modified",
    "query is too old",
    "query id is invalid",
    "message to edit not found",
    "message can't be edited",
    "message to delete not found",
    "message can't be deleted",
)

#: نافذة وعتبة اعتبار الانقطاع مستمراً (عدد الأعطال الخارجية خلال النافذة) لتنبيه الأدمن
OUTAGE_WINDOW_SECONDS = 300
OUTAGE_THRESHOLD = 10


def classify(error: BaseException | None) -> str:
    """
    تصنيف استثناء تيليجرام: `external` | `user_side` | `benign` | `internal`.

    الترتيب مهم: `BadRequest` و`Forbidden` و`Conflict` فروع من `NetworkError`/`TelegramError`
    فتُفحص قبل الفرع الشبكي العام وإلا اختفت أخطاء الكود الحقيقية تحت «انقطاع مؤقت».
    """
    if isinstance(error, Forbidden):
        return "user_side"
    if isinstance(error, BadRequest):
        text = str(error).lower()
        return "benign" if any(marker in text for marker in BENIGN_BAD_REQUESTS) else "internal"
    if isinstance(error, (RetryAfter, TimedOut, NetworkError, Conflict)):
        return "external"
    return "internal"


def delivery_is_impossible(error: BaseException) -> bool:
    """
    هل الفشل حدث **قبل** وصول الطلب لتيليجرام؟ (إعادة الإرسال آمنة ولا تكرّر الرسالة)

    PTB يحوّل أعطال httpx إلى: `TimedOut("Pool timeout"/"Connect timeout"/"Read timeout"/"Write timeout")`
    و`NetworkError("httpx.ConnectError: …")`. فقط الاتصال/التجمّع/RetryAfter مؤكَّد عدم التسليم فيها.
    """
    if isinstance(error, RetryAfter):
        return True
    text = str(error).lower()
    if isinstance(error, TimedOut):
        return "pool timeout" in text or "connect timeout" in text
    if isinstance(error, NetworkError) and not isinstance(error, BadRequest):
        return "connecterror" in text or "connecttimeout" in text
    return False


def _retry_after_seconds(error: RetryAfter) -> float:
    """مدة الانتظار التي طلبها تيليجرام (PTB 21 تُرجع عدداً صحيحاً، وإصدارات أحدث `timedelta`)."""
    value = error.retry_after
    return value.total_seconds() if isinstance(value, timedelta) else float(value)


async def call_telegram(
    factory: Callable[[], Awaitable[T]],
    *,
    what: str,
    idempotent: bool,
    delays: tuple[float, ...] | None = None,
) -> T:
    """
    تنفيذ نداء تيليجرام مع إعادة محاولة محكومة، وإعادة رفع الخطأ الأخير إن استنفدت المحاولات.

    المدخلات:
        factory    : دالة تُنشئ coroutine جديدة لكل محاولة (النداء نفسه).
        what       : وصف قصير للّوق («تحرير رسالة»).
        idempotent : هل تكرار النداء بلا أثر جانبي؟ (تحرير/إجابة زر = نعم، إرسال رسالة = لا).

    الاستثناءات: ما لم يكن مؤقتاً قابلاً للإعادة يُرفع فوراً (BadRequest، Forbidden، …).
    """
    waits = RETRY_DELAYS if delays is None else delays
    attempt = 0
    while True:
        try:
            return await factory()
        except (BadRequest, Forbidden):
            raise                                     # ليس شبكياً: لا فائدة من الإعادة (BadRequest فرع NetworkError)
        except RetryAfter as exc:
            wait = _retry_after_seconds(exc)
            if attempt >= len(waits) or wait > MAX_RETRY_AFTER_WAIT:
                raise
            logger.warning("تيليجرام طلب الانتظار %.1fث قبل «%s» (محاولة %s)", wait, what, attempt + 1)
            await asyncio.sleep(wait)
        except (TimedOut, NetworkError) as exc:
            if attempt >= len(waits) or not (idempotent or delivery_is_impossible(exc)):
                raise
            logger.warning(
                "عطل اتصال أثناء «%s» (%s: %s) — إعادة المحاولة %s/%s",
                what, type(exc).__name__, sanitize(str(exc))[:120], attempt + 1, len(waits),
            )
            await asyncio.sleep(waits[attempt])
        attempt += 1


class TelegramHealth:
    """
    عدّاد أعطال الاتصال الخارجية في نافذة زمنية، لاكتشاف الانقطاع المستمر (لا العطل العابر).

    عطل أو اثنان كل بضع دقائق أمر عادي على الشبكات الضعيفة؛ العشرة خلال خمس دقائق انقطاع يستحق إبلاغ الأدمن.
    """

    def __init__(
        self,
        *,
        window_seconds: int = OUTAGE_WINDOW_SECONDS,
        threshold: int = OUTAGE_THRESHOLD,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """تهيئة العدّاد بنافذة وعتبة وساعة قابلة للحقن (للاختبار)."""
        self._window = window_seconds
        self._threshold = threshold
        self._clock = clock
        self._events: deque[float] = deque()
        self.total_external = 0

    def record_external(self) -> int:
        """تسجيل عطل خارجي وإرجاع عدد الأعطال داخل النافذة الحالية."""
        now = self._clock()
        self._events.append(now)
        self.total_external += 1
        self._trim(now)
        return len(self._events)

    def _trim(self, now: float) -> None:
        """إسقاط الأحداث الأقدم من النافذة."""
        while self._events and now - self._events[0] > self._window:
            self._events.popleft()

    @property
    def recent(self) -> int:
        """عدد الأعطال الخارجية في النافذة الحالية."""
        self._trim(self._clock())
        return len(self._events)

    @property
    def outage(self) -> bool:
        """هل بلغنا عتبة الانقطاع المستمر؟"""
        return self.recent >= self._threshold
