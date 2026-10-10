"""
أدوات ملفات النسخ الاحتياطي (المرحلة 10) — دوال **متزامنة بحتة** بلا تيليجرام وبلا خدمات.

لماذا ملف مستقل؟
    يستعمله مساران لا يجمعهما شيء سوى الملف نفسه:
        1. خدمة النسخ داخل البوت (`services/backup_service.py`).
        2. سكربت الاستعادة `scripts/restore_backup.py` الذي يعمل **والبوت متوقف**
           فلا حلقة أحداث ولا خدمات ولا اتصال بقاعدة البيانات.
    وضع المنطق الحرج (التحقق من البصمة وسلامة SQLite) في مكان واحد يضمن أن ما
    تعدّه الخدمة «نسخة سليمة» هو بالضبط ما يقبله سكربت الاستعادة.

شكل النسخة على القرص (بجوار بعضهما):
    smm_backup_20261005_093000_scheduled.db.gz        ← قاعدة SQLite مضغوطة
    smm_backup_20261005_093000_scheduled.db.gz.meta.json  ← بصمة SHA-256 وإصدار المخطط ونوعها

الملف الجانبي (`.meta.json`) يتيح التحقق والاستعادة حتى لو ضاعت قاعدة البيانات
نفسها (وهي الحالة التي نحتاج فيها النسخة أصلاً).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from core.exceptions import BackupError

#: بادئة اسم كل ملف نسخة (تمنع الخلط مع ملفات أخرى في المجلد)
BACKUP_PREFIX = "smm_backup_"

#: لاحقة الملف الجانبي
SIDECAR_SUFFIX = ".meta.json"

#: امتداد النسخة المضغوطة
BACKUP_SUFFIX = ".db.gz"

#: حد رفع الملفات عبر Bot API (50MB) مع هامش أمان
TELEGRAM_UPLOAD_LIMIT_BYTES = 49 * 1024 * 1024

#: أقصى حجم مسموح بعد فك الضغط (حماية من «قنبلة ضغط» في ملف مزوَّر)
MAX_UNCOMPRESSED_BYTES = 20 * 1024**3

#: اسم ملف النسخة المقبول: يمنع المسارات (../) والأسماء الغريبة تماماً
_NAME_RE = re.compile(r"^smm_backup_\d{8}_\d{6}_[a-z_]{3,20}\.db\.gz$")

#: الجداول التي يجب أن تحويها أي قاعدة صالحة للاستعادة
REQUIRED_TABLES: frozenset[str] = frozenset(
    {
        "users", "orders", "transactions", "payments", "settings", "audit_logs",
        "schema_migrations", "providers", "services", "backups",
    }
)

#: حجم كتلة القراءة عند حساب البصمة والضغط (1MB)
_CHUNK = 1024 * 1024


@dataclass(frozen=True, slots=True)
class SqliteCheck:
    """نتيجة فحص ملف SQLite (قراءة فقط)."""

    integrity_ok: bool
    integrity_message: str
    tables: frozenset[str]
    schema_version: str | None
    users_count: int
    orders_count: int

    @property
    def missing_tables(self) -> list[str]:
        """الجداول الأساسية الناقصة (فارغة إن كانت القاعدة كاملة)."""
        return sorted(REQUIRED_TABLES - self.tables)

    @property
    def is_restorable(self) -> bool:
        """هل الملف سليم وفيه كل الجداول الأساسية؟"""
        return self.integrity_ok and not self.missing_tables


# ============================== الأسماء والمسارات ============================== #


def build_backup_name(backup_type: str, stamp: str) -> str:
    """
    اسم ملف نسخة جديدة.

    المدخلات:
        backup_type : manual / scheduled / pre_operation.
        stamp       : وقت بصيغة `YYYYmmdd_HHMMSS` (UTC).
    """
    name = f"{BACKUP_PREFIX}{stamp}_{backup_type}{BACKUP_SUFFIX}"
    if not _NAME_RE.match(name):
        raise BackupError(f"اسم نسخة غير صالح: {name!r}")
    return name


def is_valid_backup_name(name: str) -> bool:
    """هل الاسم بصيغة ملفات النسخ المعتمدة؟"""
    return bool(_NAME_RE.match(name or ""))


def safe_backup_path(backup_dir: Path, filename: str) -> Path:
    """
    مسار ملف نسخة **داخل** مجلد النسخ فقط.

    يمنع الخروج من المجلد (`../../etc/passwd`) أو الروابط الرمزية إلى خارجه،
    حتى لو وصل اسم ملف مشبوه من قاعدة البيانات أو من سطر الأوامر.

    الاستثناءات: BackupError عند اسم غير مطابق أو مسار خارج المجلد.
    """
    if not is_valid_backup_name(filename):
        raise BackupError(f"اسم ملف النسخة مرفوض: {filename!r}")
    base = backup_dir.resolve()
    candidate = (base / filename).resolve()
    if candidate.parent != base:
        raise BackupError("مسار النسخة خارج مجلد النسخ الاحتياطية")
    return candidate


def sidecar_path(backup_path: Path) -> Path:
    """مسار الملف الجانبي لنسخة."""
    return backup_path.with_name(backup_path.name + SIDECAR_SUFFIX)


def list_backup_files(backup_dir: Path) -> list[Path]:
    """كل ملفات النسخ في المجلد بصيغتها المعتمدة (الأقدم أولاً)."""
    if not backup_dir.is_dir():
        return []
    return sorted(
        (entry for entry in backup_dir.iterdir() if entry.is_file() and is_valid_backup_name(entry.name)),
        key=lambda entry: entry.name,
    )


# ================================ البصمة والضغط ================================ #


def sha256_file(path: Path) -> str:
    """بصمة SHA-256 لملف (قراءة على كتل فلا تُحمَّل النسخة كلها في الذاكرة)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def gzip_file(source: Path, destination: Path) -> int:
    """
    ضغط ملف إلى `destination` وإرجاع حجم الملف الناتج بالبايت.

    الاستثناءات: OSError عند فشل الكتابة (يُحوَّل لـBackupError عند المستدعي).
    """
    with source.open("rb") as raw, gzip.open(destination, "wb", compresslevel=6) as packed:
        shutil.copyfileobj(raw, packed, _CHUNK)
    return destination.stat().st_size


def gunzip_file(source: Path, destination: Path, *, max_bytes: int = MAX_UNCOMPRESSED_BYTES) -> int:
    """
    فك ضغط ملف مع سقف للحجم الناتج (حماية من قنبلة الضغط).

    المخرجات: عدد البايتات المكتوبة.
    الاستثناءات: BackupError إن تجاوز الناتج السقف أو كان الملف تالفاً.
    """
    written = 0
    try:
        with gzip.open(source, "rb") as packed, destination.open("wb") as out:
            while chunk := packed.read(_CHUNK):
                written += len(chunk)
                if written > max_bytes:
                    raise BackupError("حجم النسخة بعد فك الضغط يتجاوز السقف المسموح")
                out.write(chunk)
    except (OSError, EOFError, gzip.BadGzipFile) as exc:
        destination.unlink(missing_ok=True)
        raise BackupError(f"ملف النسخة تالف أو لا يمكن فك ضغطه: {type(exc).__name__}") from exc
    except BackupError:
        destination.unlink(missing_ok=True)
        raise
    return written


# ================================== فحص SQLite ================================== #


def inspect_sqlite(path: Path) -> SqliteCheck:
    """
    فحص ملف SQLite بوضع القراءة فقط: السلامة، الجداول، إصدار المخطط، عدّادات أساسية.

    لا يعدّل الملف إطلاقاً (`mode=ro`) ولا يمرّر مساره عبر SQL.
    """
    uri = f"file:{quote(path.resolve().as_posix())}?mode=ro"   # ترميز أي ? أو # في المسار
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=5)
    except sqlite3.Error as exc:
        return SqliteCheck(False, f"تعذّر فتح الملف: {exc}", frozenset(), None, 0, 0)
    try:
        try:
            rows = connection.execute("PRAGMA integrity_check").fetchall()
        except sqlite3.DatabaseError as exc:
            return SqliteCheck(False, f"الملف ليس قاعدة SQLite سليمة: {exc}", frozenset(), None, 0, 0)
        message = "; ".join(str(row[0]) for row in rows[:3])
        integrity_ok = len(rows) == 1 and str(rows[0][0]).lower() == "ok"

        tables = frozenset(
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        )
        schema_version = None
        users_count = orders_count = 0
        if "schema_migrations" in tables:
            row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
            schema_version = str(row[0]) if row and row[0] is not None else None
        if "users" in tables:
            users_count = int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        if "orders" in tables:
            orders_count = int(connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0])
        return SqliteCheck(integrity_ok, message, tables, schema_version, users_count, orders_count)
    except sqlite3.DatabaseError as exc:
        return SqliteCheck(False, f"فشل فحص الملف: {exc}", frozenset(), None, 0, 0)
    finally:
        connection.close()


# =============================== الملف الجانبي =============================== #


def write_sidecar(backup_path: Path, meta: dict[str, Any]) -> Path:
    """كتابة الملف الجانبي (JSON) بصلاحية المالك فقط، وإرجاع مساره."""
    target = sidecar_path(backup_path)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, target)
    _chmod_private(target)
    return target


def read_sidecar(backup_path: Path) -> dict[str, Any] | None:
    """قراءة الملف الجانبي؛ None إذا غاب أو كان تالفاً (لا نخمّن محتواه)."""
    target = sidecar_path(backup_path)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# ================================= أدوات عامة ================================= #


def _chmod_private(path: Path) -> None:
    """صلاحية المالك فقط (0600) على أنظمة يونكس؛ لا شيء على غيرها."""
    if os.name == "posix":
        os.chmod(path, 0o600)


def ensure_private_dir(path: Path) -> None:
    """إنشاء مجلد بصلاحية المالك فقط (0700) إن لم يوجد، وتشديده إن وُجد."""
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(path, 0o700)


def chmod_private(path: Path) -> None:
    """واجهة عامة لضبط صلاحية ملف خاص (للخدمة والسكربت)."""
    _chmod_private(path)


def human_size(size_bytes: int) -> str:
    """حجم مقروء: `812 بايت` · `3.4 كيلوبايت` · `12.6 ميغابايت` · `1.2 غيغابايت`."""
    size = float(max(0, size_bytes))
    if size < 1024:
        return f"{int(size)} بايت"
    for unit in ("كيلوبايت", "ميغابايت", "غيغابايت"):
        size /= 1024
        if size < 1024 or unit == "غيغابايت":
            return f"{size:.1f} {unit}"
    return f"{size:.1f} غيغابايت"


def free_disk_bytes(directory: Path) -> int:
    """المساحة الحرة (بايت) على القرص الذي يحوي المجلد (أقرب مجلد موجود)."""
    probe = directory
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free
