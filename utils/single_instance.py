"""
قفل «نسخة واحدة فقط» من البوت.

لماذا هذا مهم هنا تحديداً؟
    تشغيل نسختين من البوت على نفس قاعدة البيانات يسبب:
        • تعارض `getUpdates` في تيليجرام (Conflict 409) وفقدان رسائل.
        • معالجة الطلب نفسه مرتين من مهمتي الإرسال (رغم وجود الحجز، لا داعي
          لاختبار حظّنا بأموال المستخدمين).
    لذلك نحجز ملف قفل على القرص عند الإقلاع ونرفض التشغيل إن كان محجوزاً.

التنفيذ يستخدم `fcntl.flock` على أنظمة يونكس (قفل يتحرر تلقائياً إن مات
المسار فجأة)، ويسقط إلى فحص PID على ويندوز.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType

from utils.logging_setup import get_logger

logger = get_logger(__name__)

try:                                    # يونكس/لينكس/ماك
    import fcntl

    HAS_FCNTL = True
except ImportError:                     # ويندوز
    fcntl = None                        # type: ignore[assignment]
    HAS_FCNTL = False


class AlreadyRunningError(RuntimeError):
    """نسخة أخرى من البوت تعمل بالفعل على نفس ملف القفل."""


class SingleInstance:
    """
    مدير سياق يضمن تشغيل نسخة واحدة من البوت.

    الاستخدام:
        with SingleInstance(Path("data/bot.lock")):
            ...
    """

    def __init__(self, lock_path: Path | str) -> None:
        """تهيئة القفل بمسار ملفه (يُنشأ المجلد تلقائياً)."""
        self.lock_path = Path(lock_path)
        self._handle = None

    def acquire(self) -> None:
        """
        حجز القفل.

        الاستثناءات:
            AlreadyRunningError : نسخة أخرى تعمل بالفعل.
        """
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.lock_path, "a+", encoding="utf-8")   # noqa: SIM115 - يبقى مفتوحاً عمداً

        if HAS_FCNTL:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                handle.close()
                raise AlreadyRunningError(
                    f"نسخة أخرى من البوت تعمل بالفعل (القفل: {self.lock_path})"
                ) from exc
        else:
            handle.seek(0)
            existing = handle.read().strip()
            if existing.isdigit() and _pid_alive(int(existing)):
                handle.close()
                raise AlreadyRunningError(
                    f"نسخة أخرى من البوت تعمل بالفعل (PID {existing})"
                )

        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        self._handle = handle
        logger.debug("تم حجز قفل النسخة الواحدة: %s", self.lock_path)

    def release(self) -> None:
        """تحرير القفل وحذف ملفه (يُستدعى تلقائياً عند الخروج)."""
        if self._handle is None:
            return
        try:
            if HAS_FCNTL:
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except OSError as exc:
            logger.warning("تعذر تحرير القفل: %s", exc)
        finally:
            self._handle.close()
            self._handle = None
            try:
                self.lock_path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("تعذر حذف ملف القفل: %s", exc)
            logger.debug("تم تحرير قفل النسخة الواحدة")

    def __enter__(self) -> "SingleInstance":
        """حجز القفل عند الدخول في سياق `with`."""
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """تحرير القفل عند الخروج مهما كان سبب الخروج."""
        self.release()


def _pid_alive(pid: int) -> bool:
    """فحص ما إذا كانت العملية بهذا الرقم ما تزال تعمل (مسار ويندوز)."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
