"""
أدوات الوقت — قاعدة ثابتة في المشروع:

    • كل ما يُخزَّن في قاعدة البيانات بتوقيت UTC وبصيغة ISO-8601 منتهية بحرف Z.
    • التحويل إلى التوقيت المحلي (Asia/Aden افتراضياً) يتم عند العرض فقط.

السبب: خلط التوقيتات يفسد الإحصائيات اليومية ويجعل مقارنة الأوقات غير موثوقة.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

ISO_FORMAT: str = "%Y-%m-%dT%H:%M:%S.%fZ"

#: المنطقة الزمنية المعتمدة للعرض وللمهام اليومية (تُستخدم عند عدم تمرير غيرها)
DEFAULT_TIMEZONE: str = "Asia/Aden"

#: كائن المنطقة الزمنية الجاهز (يحتاجه `run_daily` في JobQueue)
APP_TIMEZONE: ZoneInfo = ZoneInfo(DEFAULT_TIMEZONE)


def utc_now() -> datetime:
    """الوقت الحالي بتوقيت UTC ككائن datetime واعٍ بالمنطقة الزمنية."""
    return datetime.now(UTC)


def to_iso(moment: datetime) -> str:
    """تحويل datetime إلى نص ISO-8601 بتوقيت UTC (الصيغة المعتمدة للتخزين)."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime(ISO_FORMAT)


def utc_now_iso() -> str:
    """الوقت الحالي جاهزاً للتخزين في قاعدة البيانات."""
    return to_iso(utc_now())


def parse_iso(value: str | None) -> datetime | None:
    """تحويل نص مخزَّن إلى datetime، وإرجاع None إذا كانت القيمة فارغة أو غير صالحة."""
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def iso_plus_seconds(seconds: int, *, base: datetime | None = None) -> str:
    """نص ISO لوقت مستقبلي بعد عدد من الثواني (يُستخدم للقفول ومواعيد الفحص)."""
    return to_iso((base or utc_now()) + timedelta(seconds=seconds))


def iso_minus_days(days: int, *, base: datetime | None = None) -> str:
    """نص ISO لوقت ماضٍ قبل عدد من الأيام (يُستخدم في التقارير والتنظيف)."""
    return to_iso((base or utc_now()) - timedelta(days=days))


def is_past(value: str | None) -> bool:
    """هل مرّ هذا الوقت المخزَّن؟ (تُعامل القيمة الفارغة على أنها منتهية)."""
    moment = parse_iso(value)
    return True if moment is None else moment <= utc_now()


def to_local_text(value: str | None, timezone: str = "Asia/Aden", fmt: str = "%Y-%m-%d %H:%M") -> str:
    """
    تحويل وقت مخزَّن (UTC) إلى نص بالتوقيت المحلي للعرض على المستخدم.

    المدخلات:
        value    : النص المخزَّن في قاعدة البيانات.
        timezone : المنطقة الزمنية للعرض.
        fmt      : صيغة العرض.

    المخرجات: نص منسّق، أو "-" إذا لم توجد قيمة.
    """
    moment = parse_iso(value)
    if moment is None:
        return "-"
    try:
        zone = ZoneInfo(timezone)
    except (KeyError, ValueError, OSError):  # منطقة زمنية غير معروفة — نعرض بتوقيت UTC بدل الانهيار
        zone = UTC
    return moment.astimezone(zone).strftime(fmt)


def day_bounds_utc(days_back: int = 0, timezone: str = "Asia/Aden") -> tuple[str, str]:
    """
    حدود يوم محلي كاملة معبَّراً عنها بتوقيت UTC (لاستعلامات الإحصائيات اليومية).

    المدخلات:
        days_back : 0 = اليوم، 1 = أمس ... إلخ.
        timezone  : المنطقة الزمنية المحلية المعتمدة للعرض.

    المخرجات: (بداية اليوم، نهاية اليوم) كنصين ISO بتوقيت UTC.
    """
    try:
        zone = ZoneInfo(timezone)
    except (KeyError, ValueError, OSError):   # اسم منطقة غير صالح ⇒ UTC
        zone = UTC
    local_now = utc_now().astimezone(zone) - timedelta(days=days_back)
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return to_iso(start_local), to_iso(end_local)


def _zone(timezone: str) -> tzinfo:
    """كائن المنطقة الزمنية، وUTC إذا كان الاسم غير معروف (لا نفشل في التقارير بسبب إعداد)."""
    try:
        return ZoneInfo(timezone)
    except (KeyError, ValueError, OSError):                # اسم منطقة غير صالح/ناقص tzdata
        return UTC


def local_range_utc(
    first_days_back: int, last_days_back: int = 0, timezone: str = DEFAULT_TIMEZONE
) -> tuple[str, str]:
    """
    مدى أيام محلية كاملة بتوقيت UTC: من بداية اليوم `first_days_back` حتى نهاية اليوم `last_days_back`.

    مثال: `(6, 0)` = آخر 7 أيام تقويمية شاملةً اليوم · `(1, 1)` = أمس وحده.
    الحساب بتاريخ المنطقة المحلية (لا بطرح 24 ساعة) فلا ينحرف مع تغيّر التوقيت الصيفي.
    """
    zone = _zone(timezone)
    today = utc_now().astimezone(zone).date()
    start_day = today - timedelta(days=first_days_back)
    end_day = today - timedelta(days=last_days_back) + timedelta(days=1)
    start = datetime(start_day.year, start_day.month, start_day.day, tzinfo=zone)
    end = datetime(end_day.year, end_day.month, end_day.day, tzinfo=zone)
    return to_iso(start), to_iso(end)


def local_month_range_utc(timezone: str = DEFAULT_TIMEZONE) -> tuple[str, str]:
    """من بداية الشهر المحلي الحالي حتى نهاية اليوم المحلي (بتوقيت UTC)."""
    zone = _zone(timezone)
    today = utc_now().astimezone(zone).date()
    start = datetime(today.year, today.month, 1, tzinfo=zone)
    return to_iso(start), local_range_utc(0, 0, timezone)[1]


def local_day_of(value: str | None, timezone: str = DEFAULT_TIMEZONE) -> str | None:
    """تاريخ اليوم المحلي `YYYY-MM-DD` لوقت مخزَّن (None إذا كانت القيمة غير صالحة)."""
    moment = parse_iso(value)
    if moment is None:
        return None
    return moment.astimezone(_zone(timezone)).strftime("%Y-%m-%d")
