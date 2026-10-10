"""
مُهدِّئ التنبيهات المتكررة (المرحلة 9).

المشكلة: عطل واحد (مثل انقطاع قاعدة البيانات) قد يولّد مئات الأخطاء في الدقيقة؛
لو أرسلنا تنبيهاً لكل خطأ لأغرقنا الأدمن وأخفينا التنبيه المهم وسط الضجيج.

الحل: تنبيه واحد لكل «بصمة خطأ» خلال فترة تهدئة، مع عدّ ما كُبت ليُذكر في التنبيه
التالي («تكرر 37 مرة»)، وسقف إجمالي للتنبيهات في النافذة نفسها حتى لو تنوّعت الأخطاء.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

#: أقصى عدد بصمات تُحفظ في الذاكرة (حماية من نموّ غير محدود)
MAX_TRACKED_KEYS = 500


@dataclass(frozen=True, slots=True)
class ThrottleDecision:
    """
    قرار المُهدِّئ.

    الحقول:
        allow      : هل يُرسل التنبيه الآن؟
        suppressed : عدد مرات الكبت السابقة لهذه البصمة (يُذكر عند السماح).
    """

    allow: bool
    suppressed: int = 0


class AlertThrottle:
    """تهدئة بحسب البصمة + سقف إجمالي لكل نافذة تهدئة."""

    def __init__(
        self, *, max_per_window: int = 5, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """
        المدخلات:
            max_per_window : أقصى تنبيهات مسموحة في نافذة التهدئة عبر كل البصمات.
            clock          : ساعة قابلة للحقن (الاختبارات تتحكم بالزمن بلا انتظار).
        """
        self._max_per_window = max_per_window
        self._clock = clock
        self._last_sent: dict[str, float] = {}
        self._suppressed: dict[str, int] = {}
        self._window_sent: list[float] = []

    def check(self, key: str, *, cooldown_seconds: float) -> ThrottleDecision:
        """
        تقرير إرسال تنبيه لهذه البصمة الآن.

        القواعد:
            1. إن أُرسل تنبيه للبصمة خلال فترة التهدئة ⇒ كبت (وعدّ).
            2. إن بلغ إجمالي التنبيهات في النافذة السقف ⇒ كبت (وعدّ).
            3. غير ذلك ⇒ سماح وتصفير عدّاد الكبت للبصمة.
        """
        now = self._clock()
        self._window_sent = [stamp for stamp in self._window_sent if now - stamp < cooldown_seconds]

        last = self._last_sent.get(key)
        if last is not None and now - last < cooldown_seconds:
            self._suppressed[key] = self._suppressed.get(key, 0) + 1
            return ThrottleDecision(False)
        if len(self._window_sent) >= self._max_per_window:
            self._suppressed[key] = self._suppressed.get(key, 0) + 1
            return ThrottleDecision(False)

        if len(self._last_sent) >= MAX_TRACKED_KEYS:
            self._evict_oldest()
        suppressed = self._suppressed.pop(key, 0)
        self._last_sent[key] = now
        self._window_sent.append(now)
        return ThrottleDecision(True, suppressed)

    def _evict_oldest(self) -> None:
        """حذف أقدم بصمة عند امتلاء الذاكرة."""
        oldest = min(self._last_sent, key=self._last_sent.__getitem__)
        self._last_sent.pop(oldest, None)
        self._suppressed.pop(oldest, None)
