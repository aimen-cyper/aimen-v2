"""
تصلّب صلاحيات الملفات والمجلدات الحسّاسة (المرحلة 9).

لماذا؟
    ملف `.env` فيه التوكن ومفتاح التشفير، وقاعدة البيانات فيها أرصدة العملاء
    ومفاتيح المزودين (مشفّرة)، والنسخ الاحتياطية نسخة كاملة منها. على خادم
    مشترك أو بعد نسخ ملفات بأمر `cp` يصبح الملف بصلاحية `644` فيقرؤه أي
    مستخدم آخر على الجهاز. نضبط الصلاحيات تلقائياً عند الإقلاع ونبلّغ بما
    تعذّر ضبطه بدل السكوت.

الاستثناء: على ويندوز لا يوجد مكافئ مباشر لـchmod، فنعيد قائمة فارغة.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: الصلاحية المطلوبة للملفات الحسّاسة: قراءة/كتابة للمالك فقط
FILE_MODE = 0o600

#: الصلاحية المطلوبة للمجلدات الحسّاسة: دخول المالك فقط
DIR_MODE = 0o700

#: أي بت ضمن هذه القناع يعني أن المجموعة أو الآخرين يملكون وصولاً
GROUP_OTHER_MASK = 0o077


@dataclass(frozen=True, slots=True)
class PathCheck:
    """
    نتيجة فحص مسار واحد.

    الحقول:
        path     : المسار.
        label    : وصف عربي مختصر (مثل «ملف البيئة .env»).
        mode     : الصلاحية الحالية بعد المعالجة (None إن لم يوجد المسار).
        insecure : هل بقي مفتوحاً للمجموعة/الآخرين؟
        fixed    : هل ضُبطت الصلاحية في هذا الاستدعاء؟
        note     : سبب إن تعذّر الضبط.
    """

    path: Path
    label: str
    mode: int | None
    insecure: bool
    fixed: bool = False
    note: str = ""

    @property
    def mode_text(self) -> str:
        """الصلاحية بصيغة ثمانية مثل 600 (أو «غير موجود»)."""
        return "غير موجود" if self.mode is None else format(self.mode, "03o")


def _check_one(path: Path, label: str, expected: int, *, fix: bool) -> PathCheck | None:
    """فحص مسار واحد وضبطه عند الطلب؛ يُرجع None إن لم يكن موجوداً."""
    try:
        current = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        return None
    except OSError as exc:
        return PathCheck(path, label, None, True, note=f"تعذّر الفحص: {type(exc).__name__}")

    if current & GROUP_OTHER_MASK == 0:
        return PathCheck(path, label, current, False)
    if not fix:
        return PathCheck(path, label, current, True)
    try:
        os.chmod(path, expected)
    except OSError as exc:
        logger.warning("تعذّر ضبط صلاحية %s إلى %o: %s", path, expected, exc)
        return PathCheck(path, label, current, True, note=f"تعذّر الضبط: {type(exc).__name__}")
    logger.info("ضُبطت صلاحية %s من %o إلى %o", path, current, expected)
    return PathCheck(path, label, expected, False, fixed=True)


def sensitive_paths(
    *, env_file: Path, database_path: Path, data_dir: Path, backup_dir: Path, log_dir: Path
) -> list[tuple[Path, str, int]]:
    """
    قائمة المسارات الحسّاسة مع الصلاحية المطلوبة لكل منها.

    تشمل ملفات SQLite الجانبية (`-wal`/`-shm`) لأنها تحوي بيانات حديثة غير مدمجة.
    """
    return [
        (env_file, "ملف البيئة .env (التوكن ومفتاح التشفير)", FILE_MODE),
        (database_path, "قاعدة البيانات", FILE_MODE),
        (Path(f"{database_path}-wal"), "سجل WAL لقاعدة البيانات", FILE_MODE),
        (Path(f"{database_path}-shm"), "ذاكرة SHM لقاعدة البيانات", FILE_MODE),
        (data_dir / "bot.lock", "ملف قفل النسخة الواحدة", FILE_MODE),
        (data_dir, "مجلد البيانات", DIR_MODE),
        (backup_dir, "مجلد النسخ الاحتياطية", DIR_MODE),
        (log_dir, "مجلد اللوقات", DIR_MODE),
    ]


def check_paths(
    entries: list[tuple[Path, str, int]], *, fix: bool = False
) -> list[PathCheck]:
    """
    فحص (وضبط اختيارياً) صلاحيات مجموعة مسارات.

    المدخلات:
        entries : قائمة (المسار، الوصف، الصلاحية المطلوبة).
        fix     : True لضبط المخالف تلقائياً (يُستخدم عند الإقلاع)، False للفحص فقط.

    المخرجات: نتائج المسارات الموجودة فقط. فارغة على ويندوز.
    """
    if os.name != "posix":
        return []
    results = []
    for path, label, expected in entries:
        outcome = _check_one(path, label, expected, fix=fix)
        if outcome is not None:
            results.append(outcome)
    return results
