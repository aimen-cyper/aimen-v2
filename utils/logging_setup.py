"""
إعداد نظام التسجيل (Logging) المركزي.

الميزات:
    • ملف دوّار (RotatingFileHandler) حتى لا يتضخم حجم اللوق.
    • إخراج على الشاشة أثناء التطوير.
    • فلتر أمني يحذف أي توكن أو مفتاح API قبل الكتابة.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from utils.security import sanitize

_CONFIGURED: bool = False


class SecretRedactionFilter(logging.Filter):
    """فلتر يمنع كتابة الأسرار (التوكن/المفاتيح) داخل ملفات اللوق."""

    def filter(self, record: logging.LogRecord) -> bool:
        """تنقية نص الرسالة قبل إخراجها؛ يُرجع True دائماً لأننا لا نحذف السجلات."""
        try:
            message = record.getMessage()
        except (TypeError, ValueError, KeyError):  # فشل تنسيق الرسالة (args غير مطابقة) ⇒ نمرّر السجل كما هو
            return True
        cleaned = sanitize(message)
        if cleaned != message:
            record.msg = cleaned
            record.args = ()
        return True


class RedactingFormatter(logging.Formatter):
    """
    منسّق يحذف الأسرار من **السطر النهائي كاملاً** بما فيه تتبّع الاستثناء.

    لماذا لا يكفي الفلتر وحده؟ الفلتر يرى `record.msg` فقط، أما `exc_info`
    فيُنسَّق لاحقاً داخل المنسّق — واستثناءات httpx/تيليجرام تحمل الرابط الكامل
    (وفيه التوكن) في نص الخطأ. التنقية هنا تسدّ هذه الثغرة.
    """

    def format(self, record: logging.LogRecord) -> str:
        """تنسيق السجل ثم تنقية الناتج النهائي من الأسرار."""
        return sanitize(super().format(record))


def setup_logging(
    log_file: Path | str = "logs/bot.log",
    level: str = "INFO",
    *,
    console: bool = True,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
) -> logging.Logger:
    """
    تهيئة اللوق المركزي للمشروع (تُستدعى مرة واحدة عند الإقلاع).

    المدخلات:
        log_file     : مسار ملف اللوق.
        level        : مستوى التسجيل (DEBUG/INFO/WARNING/ERROR/CRITICAL).
        console      : إظهار السجلات على الشاشة أيضاً.
        max_bytes    : الحجم الأقصى للملف قبل التدوير.
        backup_count : عدد الملفات المحفوظة بعد التدوير.

    المخرجات: اللوجر الجذري بعد التهيئة.
    """
    global _CONFIGURED

    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    if _CONFIGURED:
        return root

    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter = RedactingFormatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    redaction = SecretRedactionFilter()

    file_handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redaction)
    root.addHandler(file_handler)

    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(redaction)
        root.addHandler(stream_handler)

    # تخفيف ضجيج المكتبات الخارجية
    for noisy in ("httpx", "httpcore", "aiosqlite", "telegram.vendor", "apscheduler"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
    return root


def get_logger(name: str) -> logging.Logger:
    """الحصول على لوجر باسم الوحدة الحالية."""
    return logging.getLogger(name)
