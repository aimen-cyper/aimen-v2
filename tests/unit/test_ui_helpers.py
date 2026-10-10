"""
اختبارات أدوات العرض وحد الاستخدام.

تركّز على ثلاث نقاط تُسبب أعطالاً حقيقية إن أُهملت:
    • تهريب HTML (اسم مستخدم فيه `<` يكسر الرسالة كلها أو يحقن وسماً).
    • تنسيق المال من النقاط الصحيحة (لا حساب عائم في طبقة العرض).
    • دقة نافذة حد الاستخدام.
"""

from __future__ import annotations

from types import SimpleNamespace

from middlewares.rate_limit import RateLimiter
from utils.formatters import (
    money_text,
    order_status_text,
    safe,
    short_link,
    ticket_status_text,
    transaction_line,
)


# ----------------------------- تهريب وتقصير ----------------------------- #


def test_safe_escapes_html() -> None:
    """أي نص من المستخدم يُهرَّب قبل العرض بتنسيق HTML."""
    assert safe("<b>اسم</b>") == "&lt;b&gt;اسم&lt;/b&gt;"
    assert "&amp;" in safe("شركة & شركاه")


def test_safe_truncates_long_text() -> None:
    """النص الطويل يُقتطع بعلامة واضحة بدل كسر الشاشة."""
    result = safe("ا" * 200, limit=20)
    assert len(result) <= 21
    assert result.endswith("…")


def test_safe_handles_none() -> None:
    """القيمة الفارغة لا تُسبب استثناء ولا تطبع None للمستخدم."""
    assert safe(None) == ""


def test_short_link_keeps_head_and_tail() -> None:
    """الرابط الطويل يُعرض مختصراً مع بقاء بدايته مفهومة."""
    link = "https://instagram.com/" + "x" * 100
    shortened = short_link(link)
    assert len(shortened) < len(link)
    assert shortened.startswith("https://instagram.com/")


# ------------------------------- المال ---------------------------------- #


def test_money_text_formats_units() -> None:
    """10000 نقطة = 1.00 من العملة (لا قسمة عائمة في العرض)."""
    assert money_text(10_000, "ر.ي").startswith("1.00")
    assert "ر.ي" in money_text(10_000, "ر.ي")


def test_money_text_zero_and_large() -> None:
    """الصفر والمبالغ الكبيرة تُعرض بلا كسور عشرية خاطئة."""
    assert money_text(0, "").strip().startswith("0.00")
    assert money_text(1_234_567_890, "").strip().startswith("123,456.79")


# ------------------------------ الحالات --------------------------------- #


def test_status_labels_are_arabic_and_known() -> None:
    """كل حالة تُترجم لنص عربي، والحالة المجهولة لا تُسقط الواجهة."""
    assert "مكتمل" in order_status_text("completed")
    assert "مفتوحة" in ticket_status_text("open")
    assert order_status_text("weird_status")


def test_transaction_line_shows_direction() -> None:
    """سطر الحركة المالية يوضّح الاتجاه (+/-) والرصيد بعدها."""
    transaction = SimpleNamespace(
        direction="credit",
        amount_units=25_000,
        balance_after_units=75_000,
        type="deposit",
        created_at="2026-01-01T10:00:00+00:00",
    )
    line = transaction_line(transaction, symbol="ر.ي")
    assert "+" in line
    assert "2.50" in line


# --------------------------- حد الاستخدام -------------------------------- #


def test_rate_limiter_allows_up_to_limit() -> None:
    """يسمح بعدد الإجراءات المحدد ثم يمنع ما بعده."""
    limiter = RateLimiter()
    assert all(limiter.hit(1, 3) for _ in range(3))
    assert limiter.hit(1, 3) is False


def test_rate_limiter_is_per_user() -> None:
    """تجاوز مستخدم للحد لا يؤثر على غيره."""
    limiter = RateLimiter()
    for _ in range(3):
        limiter.hit(1, 3)
    assert limiter.hit(2, 3) is True


def test_rate_limiter_window_slides() -> None:
    """بعد انقضاء النافذة تعود المحاولات مسموحة."""
    limiter = RateLimiter(window_seconds=0.01)
    import time

    assert limiter.hit(5, 1) is True
    assert limiter.hit(5, 1) is False
    time.sleep(0.02)
    assert limiter.hit(5, 1) is True


def test_rate_limiter_zero_limit_means_unlimited() -> None:
    """الحد صفر يعني بلا حد (تعطيل الميزة من الإعدادات)."""
    limiter = RateLimiter()
    assert all(limiter.hit(9, 0) for _ in range(100))


def test_rate_limiter_remaining_and_reset() -> None:
    """عدّاد المتبقي صحيح، والتصفير يعيد الحالة كما كانت."""
    limiter = RateLimiter()
    limiter.hit(7, 5)
    assert limiter.remaining(7, 5) == 4
    limiter.reset(7)
    assert limiter.remaining(7, 5) == 5
