"""
حد معدل الاستخدام (Rate limit) وحارس الإساءة — حماية البوت وقاعدة البيانات.

الطبقات (المرحلة 9):
    1. `RateLimiter`: نافذة منزلقة في الذاكرة لكل (مستخدم، سلة). السلة `general`
       للتصفح، و`sensitive` للإجراءات المالية الحسّاسة (تأكيد، رفع إثبات…)
       بحدّ أضيق، حتى لا يستطيع مستخدم يضغط التأكيد عشرات المرات.
    2. `AbuseGuard`: عدّاد مخالفات. من يتجاوز الحد مراراً خلال نافذة المخالفات
       يُوقَف مؤقتاً، ويُتجاهل خلال الإيقاف **بصمت** (لا ردود ولا استعلامات
       قاعدة بيانات) — فالرد على المُغرِق يضاعف الضغط بدل أن يخففه.

لماذا في الذاكرة؟
    الحد وسيلة حماية من الضغط السريع لا سجل محاسبي؛ كتابته في قاعدة البيانات
    تعني كتابة عند كل ضغطة زر — وهو ما يُراد تجنّبه أصلاً. يُعاد ضبطه عند
    إعادة التشغيل وهذا مقبول ومقصود. أما **بدء الإيقاف** فيُكتب في سجل
    التدقيق (حدث `security.rate_limit_block`) لأنه قرار أمني يستحق الأثر.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass

from keyboards.callback_data import NS_ADM_BKP, NS_ADM_STATS

#: طول النافذة الزمنية بالثواني
WINDOW_SECONDS: float = 60.0

#: أقصى عدد مفاتيح نحتفظ بسجلها قبل التنظيف الدوري
MAX_TRACKED_USERS: int = 10_000

#: السلة العامة والسلة الحسّاسة
BUCKET_GENERAL = "general"
BUCKET_SENSITIVE = "sensitive"

#: سلة الفحص المسبق (قبل قراءة المستخدم من القاعدة): حدّها الأعلى بين حدّي العادي والأدمن
BUCKET_PRE = "pre"

#: سقف إدخالات `AbuseGuard` في الذاكرة (يمنع تضخمها بسيل معرّفات مختلفة)
MAX_GUARD_ENTRIES: int = 10_000

#: نافذة احتساب المخالفات (ثانية): المخالفات الأقدم لا تُحتسب
STRIKE_WINDOW_SECONDS: float = 600.0

#: أقل فاصل بين تحذيرين متتاليين لنفس المستخدم (ثانية) — لا نغرقه بالتحذيرات
WARNING_COOLDOWN_SECONDS: float = 10.0

#: الإجراءات الحسّاسة داخل أزرار المحادثات (تأكيدات تنفّذ عملاً مالياً أو إنشائياً)
SENSITIVE_FLOW_ACTIONS: frozenset[str] = frozenset({"confirm"})

#: أزرار لوحة الأدمن الحسّاسة خارج المحادثات: (المساحة ← الإجراءات) — ثقيلة أو تخرج بيانات (م10)
SENSITIVE_ADMIN_ACTIONS: dict[str, frozenset[str]] = {
    NS_ADM_BKP: frozenset({"new", "chan", "dl", "vac"}),
    NS_ADM_STATS: frozenset({"exp"}),
}


class RateLimiter:
    """عدّاد إجراءات لكل (مستخدم، سلة) ضمن نافذة زمنية منزلقة."""

    def __init__(
        self, *, window_seconds: float = WINDOW_SECONDS, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """تهيئة العدّاد بنافذة زمنية محددة ومصدر وقت قابل للحقن في الاختبارات."""
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[tuple[int, str], deque[float]] = defaultdict(deque)

    def hit(self, user_id: int, limit: int, *, bucket: str = BUCKET_GENERAL) -> bool:
        """
        تسجيل إجراء جديد وفحص تجاوز الحد.

        المدخلات:
            user_id : معرف تيليجرام للمستخدم.
            limit   : الحد المسموح خلال النافذة (صفر أو أقل = بلا حد).
            bucket  : سلة العدّ (`general` أو `sensitive`).

        المخرجات: True إذا كان الإجراء مسموحاً، False إذا تجاوز الحد.
        """
        if limit <= 0:
            return True

        now = self._clock()
        bucket_hits = self._hits[(user_id, bucket)]
        threshold = now - self._window
        while bucket_hits and bucket_hits[0] < threshold:        # إسقاط ما خرج من النافذة
            bucket_hits.popleft()

        if len(bucket_hits) >= limit:
            return False

        bucket_hits.append(now)
        if len(self._hits) > MAX_TRACKED_USERS:                  # تنظيف وقائي للذاكرة
            self._cleanup(threshold)
        return True

    def remaining(self, user_id: int, limit: int, *, bucket: str = BUCKET_GENERAL) -> int:
        """عدد الإجراءات المتبقية للمستخدم في النافذة الحالية."""
        if limit <= 0:
            return limit
        bucket_hits = self._hits.get((user_id, bucket))
        if not bucket_hits:
            return limit
        threshold = self._clock() - self._window
        active = sum(1 for moment in bucket_hits if moment >= threshold)
        return max(0, limit - active)

    def reset(self, user_id: int) -> None:
        """تصفير سجل مستخدم في كل السلال (الاختبارات، رفع الإيقاف)."""
        for key in [key for key in self._hits if key[0] == user_id]:
            self._hits.pop(key, None)

    def _cleanup(self, threshold: float) -> None:
        """إزالة المفاتيح التي لم تُسجَّل لها أي حركة داخل النافذة."""
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] < threshold]
        for key in stale:
            self._hits.pop(key, None)


@dataclass(frozen=True, slots=True)
class BlockInfo:
    """مستخدم موقوف مؤقتاً: معرفه والثواني المتبقية وعدد مخالفاته."""

    telegram_id: int
    seconds_left: int
    strikes: int


@dataclass(frozen=True, slots=True)
class ViolationResult:
    """نتيجة تسجيل مخالفة: هل بدأ الإيقاف؟ وهل نرسل تحذيراً الآن؟"""

    strikes: int
    blocked: bool
    warn: bool


class AbuseGuard:
    """
    عدّاد المخالفات والإيقاف المؤقت للمفرطين.

    كل تجاوز للحد = «مخالفة». عند بلوغ `strikes_limit` مخالفة داخل نافذة
    `STRIKE_WINDOW_SECONDS` يُوقَف صاحبها `block_seconds`. الحالة في الذاكرة.
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        """تهيئة الحارس بمصدر وقت قابل للحقن."""
        self._clock = clock
        self._strikes: dict[int, deque[float]] = defaultdict(deque)
        self._blocked_until: dict[int, float] = {}
        self._last_warning: dict[int, float] = {}
        self.total_violations: int = 0
        self.total_blocks: int = 0

    def seconds_blocked(self, telegram_id: int) -> float:
        """الثواني المتبقية من إيقاف المستخدم (صفر = غير موقوف). ينظّف الإيقاف المنتهي."""
        until = self._blocked_until.get(telegram_id)
        if until is None:
            return 0.0
        left = until - self._clock()
        if left <= 0:
            self._blocked_until.pop(telegram_id, None)
            self._strikes.pop(telegram_id, None)
            return 0.0
        return left

    def is_blocked(self, telegram_id: int) -> bool:
        """هل المستخدم موقوف مؤقتاً الآن؟"""
        return self.seconds_blocked(telegram_id) > 0

    def record_violation(
        self, telegram_id: int, *, strikes_limit: int, block_seconds: float
    ) -> ViolationResult:
        """
        تسجيل مخالفة جديدة وتقرير الإيقاف.

        المدخلات:
            strikes_limit : عدد المخالفات التي تُوجب الإيقاف.
            block_seconds : مدة الإيقاف.

        المخرجات: عدد المخالفات الحالية + هل بدأ الإيقاف + هل يُرسَل تحذير الآن
        (التحذير مُهدَّأ كل `WARNING_COOLDOWN_SECONDS`، وإشعار الإيقاف يُرسل دائماً).
        """
        now = self._clock()
        self.total_violations += 1
        if len(self._strikes) >= MAX_GUARD_ENTRIES:
            self._prune(now)
        strikes = self._strikes[telegram_id]
        threshold = now - STRIKE_WINDOW_SECONDS
        while strikes and strikes[0] < threshold:
            strikes.popleft()
        strikes.append(now)

        if len(strikes) >= max(1, strikes_limit):
            self._blocked_until[telegram_id] = now + block_seconds
            self.total_blocks += 1
            return ViolationResult(strikes=len(strikes), blocked=True, warn=True)

        last = self._last_warning.get(telegram_id)
        warn = last is None or now - last >= WARNING_COOLDOWN_SECONDS
        if warn:
            self._last_warning[telegram_id] = now
        return ViolationResult(strikes=len(strikes), blocked=False, warn=warn)

    def _prune(self, now: float) -> None:
        """
        تقليص ذاكرة الحارس: إسقاط المخالفات المنتهية والإيقافات المنقضية والتحذيرات القديمة.

        إن بقي العدد فوق السقف بعد ذلك (سيل معرّفات نشطة) أُسقطت أقدم السجلات غير الموقوفة؛ **الموقوفون لا
        يُسقَطون أبداً** حتى لا يُرفع إيقاف مُغرِق بإغراقه بمعرّفات أخرى.
        """
        window = now - STRIKE_WINDOW_SECONDS
        for telegram_id in [tid for tid, until in self._blocked_until.items() if until <= now]:
            self._blocked_until.pop(telegram_id, None)
        for telegram_id in [
            tid for tid, strikes in self._strikes.items()
            if tid not in self._blocked_until and (not strikes or strikes[-1] < window)
        ]:
            self._strikes.pop(telegram_id, None)
        for telegram_id in [tid for tid, last in self._last_warning.items() if now - last >= WARNING_COOLDOWN_SECONDS]:
            self._last_warning.pop(telegram_id, None)

        overflow = len(self._strikes) - MAX_GUARD_ENTRIES + 1
        if overflow > 0:
            removable = sorted(
                (tid for tid in self._strikes if tid not in self._blocked_until),
                key=lambda tid: self._strikes[tid][-1] if self._strikes[tid] else 0.0,
            )
            for telegram_id in removable[:overflow]:
                self._strikes.pop(telegram_id, None)
                self._last_warning.pop(telegram_id, None)

    def clear(self, telegram_id: int) -> bool:
        """رفع الإيقاف وتصفير المخالفات (إجراء إداري). يُرجع True إن كان موقوفاً فعلاً."""
        was_blocked = self.is_blocked(telegram_id)
        self._blocked_until.pop(telegram_id, None)
        self._strikes.pop(telegram_id, None)
        self._last_warning.pop(telegram_id, None)
        return was_blocked

    def blocked_snapshot(self) -> list[BlockInfo]:
        """قائمة الموقوفين حالياً (الأطول إيقافاً أولاً) لشاشة الأمان."""
        result = []
        for telegram_id in list(self._blocked_until):
            left = self.seconds_blocked(telegram_id)
            if left > 0:
                result.append(BlockInfo(telegram_id, int(left) + 1, len(self._strikes.get(telegram_id, ()))))
        return sorted(result, key=lambda info: -info.seconds_left)
