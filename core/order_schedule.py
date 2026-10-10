"""
سياسة جدولة فحص حالة الطلب لدى المزود (دوال خالصة بلا قاعدة بيانات).

لماذا ملف مستقل؟ تشخيص v1.3.0 أثبت بالتجربة أن التباطؤ كان مرتبطاً بـ`checks_count` فيتحول طلب سليم يُفحص بنجاح إلى
فحص كل ساعة (120 ← 900 ← 1800 ← 3600 ثانية)، فيبقى «قيد التنفيذ» ساعة بعد اكتماله فعلاً. الجدولة الجديدة تفصل:

  • **نجاح الاستعلام** (المزود ردّ): الفاصل = الفاصل الأساسي، يتدرج ببطء مع عمر الطلب وبسقف صغير قابل للضبط.
  • **فشل الاتصال** (مهلة/انقطاع): تباطؤ أسّي حسب عدد الإخفاقات المتتالية لهذا الطلب، بسقف قابل للضبط.
    فشل الاتصال لا يعني فشل الطلب، ولا يُغيّر حالته ولا ماله.

كل الأرقام تأتي من الإعدادات؛ الثوابت هنا مجرد قواعد التدرج لا قيم تشغيلية.
"""

from __future__ import annotations

#: كل كم ثانية من عمر الطلب يُضاف فاصل أساسي إضافي (تباطؤ بطيء لطلب لم يتغير منذ زمن)
ORDER_CHECK_AGE_STEP_SECONDS: int = 1800

#: بداية التباطؤ الأسّي عند فشل الاتصال (ثانية)
ORDER_CHECK_ERROR_BASE_SECONDS: int = 60


def success_delay_seconds(*, base: int, active_max: int, age_seconds: float) -> int:
    """
    فاصل الفحص التالي بعد استعلام **ناجح**.

    المعادلة: `base × (1 + عمر_الطلب ÷ 30 دقيقة)` بسقف `max(active_max, base)`.
    مثال (base=120, active_max=300): 120 حتى نصف ساعة، 240 حتى ساعة، ثم 300 كحد أقصى — لا ساعة كاملة أبداً.
    """
    base = max(1, int(base))
    cap = max(int(active_max), base)
    steps = max(0, int(age_seconds // ORDER_CHECK_AGE_STEP_SECONDS))
    return min(cap, base * (1 + steps))


def failure_delay_seconds(*, streak: int, error_max: int, base: int = ORDER_CHECK_ERROR_BASE_SECONDS) -> int:
    """
    فاصل إعادة الفحص بعد **فشل اتصال**: `base × 2^(streak-1)` بسقف `error_max` (streak ≥ 1 هو الإخفاق الحالي).
    """
    exponent = max(0, min(int(streak) - 1, 16))
    return min(max(int(error_max), 1), max(1, int(base)) * (2 ** exponent))
