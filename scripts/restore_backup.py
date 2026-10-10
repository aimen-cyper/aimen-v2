"""
استعادة نسخة احتياطية من سطر الأوامر (المرحلة 10) — **والبوت متوقف**.

لماذا خارج البوت؟
    استبدال ملف القاعدة والبوت يعمل يعني اتصالات مفتوحة على الملف القديم وعمليات
    مالية جارية. الاستعادة من داخل تيليجرام ستكون زرّاً خطراً يمكن لأدمن مخترَق أن
    يضغطه فيعود النظام لحالة قديمة (أرصدة قديمة = أموال مكرَّرة). لذلك هي عملية
    تشغيلية يقوم بها مالك السيرفر فقط.

الاستخدام (من مجلد المشروع):
    python -m scripts.restore_backup --list                       # عرض النسخ الموجودة على القرص
    python -m scripts.restore_backup --latest                     # أحدث نسخة يدوية/مجدولة موثَّقة
    python -m scripts.restore_backup --id 12                      # حسب رقمها في سجل النسخ
    python -m scripts.restore_backup --file /path/smm_backup_....db.gz
    python -m scripts.restore_backup --latest --yes               # بلا سؤال التأكيد (للأتمتة)

الضمانات (بالترتيب):
    1. يرفض العمل إن كان البوت يعمل (قفل `bot.lock` ممسوك).
    2. يتحقق من بصمة sha256 مقابل الملف الجانبي، ثم يفك الضغط لملف مؤقت ويفحص
       `integrity_check` والجداول الأساسية، ويرفض نسخة مخطَّطها أحدث من كود هذا الإصدار.
    3. يأخذ نسخة أمان من القاعدة الحالية (أو يحفظها كما هي إن كانت تالفة) — لا يُحذف شيء.
    4. يحذف ملفي -wal و-shm القديمين (تطبيقهما على قاعدة مختلفة يفسدها) ثم يستبدل الملف ذرّياً.
    5. يضبط صلاحية 0600 ويسجّل `backup.restore` في سجل التدقيق (source=cli).

كود الخروج: 0 نجاح · 1 رفض/فشل · 2 خطأ في الإعدادات أو الوسائط.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:                      # تشغيل مباشر بلا تثبيت الحزمة
    sys.path.insert(0, str(ROOT))

from config import Config, ConfigError                                  # noqa: E402
from core.constants import APP_VERSION                                  # noqa: E402
from core.exceptions import BackupError                                 # noqa: E402
from database.database import Database                                  # noqa: E402
from database.migrator import MIGRATIONS_DIR                            # noqa: E402
from database.repositories import Repositories                          # noqa: E402
from services.backup_service import create_backup_file                  # noqa: E402
from utils.backup_files import (                                        # noqa: E402
    SqliteCheck,
    chmod_private,
    gunzip_file,
    human_size,
    inspect_sqlite,
    is_valid_backup_name,
    list_backup_files,
    read_sidecar,
    safe_backup_path,
    sha256_file,
)
from utils.datetime_utils import utc_now                                # noqa: E402
from utils.logging_setup import get_logger, setup_logging               # noqa: E402
from utils.single_instance import AlreadyRunningError, SingleInstance   # noqa: E402

logger = get_logger(__name__)

#: الكلمة التي يجب كتابتها حرفياً لتأكيد الاستبدال بلا `--yes`
CONFIRM_WORD = "RESTORE"


@dataclass(slots=True)
class Prepared:
    """نسخة جُهِّزت للاستعادة: ملف قاعدة مؤقت مفحوص + معلومات للعرض."""

    source: Path
    temp_db: Path
    check: SqliteCheck
    sha_status: str          # verified | no_sidecar | skipped_plain
    created_at: str


# ================================ دوال مساعدة ================================ #


def local_schema_version() -> str:
    """أحدث رقم ترحيل يعرفه كود هذا الإصدار (من ملفات migrations)."""
    versions = [path.name.split("_", 1)[0] for path in Path(MIGRATIONS_DIR).glob("*.sql")]
    return max(versions) if versions else ""


def list_candidates(backup_dir: Path) -> list[tuple[Path, dict | None]]:
    """نسخ القرص من الأحدث للأقدم مع ملفاتها الجانبية (لا يحتاج قاعدة بيانات سليمة)."""
    return [(path, read_sidecar(path)) for path in reversed(list_backup_files(backup_dir))]


def print_list(backup_dir: Path) -> int:
    """طباعة النسخ الموجودة على القرص."""
    items = list_candidates(backup_dir)
    if not items:
        print(f"لا توجد نسخ في {backup_dir}")
        return 0
    print(f"النسخ في {backup_dir}:")
    for path, meta in items:
        size = human_size(path.stat().st_size)
        when = (meta or {}).get("created_at", "؟")
        schema = (meta or {}).get("schema_version", "؟")
        flag = "" if meta else "  ⚠️ بلا ملف جانبي"
        print(f"  • {path.name}  [{size}]  {when}  schema={schema}{flag}")
    return 0


def resolve_source(config: Config, *, file: str | None, backup_id: int | None, latest: bool) -> Path:
    """
    تحديد ملف النسخة المطلوبة.

    الاستثناءات: BackupError برسالة واضحة إن لم توجد.
    """
    if file:
        path = Path(file).expanduser()
        if not path.is_file():
            raise BackupError(f"الملف غير موجود: {path}")
        return path.resolve()
    if backup_id is not None:
        if not config.database_path.exists():
            raise BackupError("لا توجد قاعدة حالية لقراءة سجل النسخ منها — استعمل --file أو --latest")
        try:
            connection = sqlite3.connect(f"file:{config.database_path.resolve().as_posix()}?mode=ro", uri=True)
            try:
                row = connection.execute("SELECT filename FROM backups WHERE id = ?", (backup_id,)).fetchone()
            finally:
                connection.close()
        except sqlite3.Error as exc:
            raise BackupError(f"تعذّر قراءة سجل النسخ: {exc} — استعمل --file") from exc
        if row is None:
            raise BackupError(f"لا نسخة بالرقم {backup_id} في السجل")
        if not is_valid_backup_name(str(row[0])):
            raise BackupError("اسم الملف في السجل غير صالح")
        path = safe_backup_path(config.backup_dir, str(row[0]))
        if not path.is_file():
            raise BackupError(f"ملف النسخة غير موجود على القرص: {path.name}")
        return path
    if latest:
        for path, meta in list_candidates(config.backup_dir):
            # الأحدث الموثَّق من النوع اليدوي/المجدول. نسخ pre_operation (أمان قبل ترقية/استعادة/ضغط)
            # لا تُختار تلقائياً وإلا أعاد تكرار الأمر الحالة السابقة للاستعادة نفسها؛ تُختار بـ--id/--file.
            if meta is not None and not path.name.endswith("_pre_operation.db.gz"):
                return path
        raise BackupError("لا توجد نسخة يدوية/مجدولة موثَّقة في مجلد النسخ (استعمل --id أو --file)")
    raise BackupError("حدّد --latest أو --id أو --file أو --list")


def prepare(source: Path, workdir: Path) -> Prepared:
    """
    فحص النسخة وتجهيز ملف قاعدة مؤقت في `workdir` (نفس نظام الملفات ⇒ استبدال ذرّي).

    الاستثناءات: BackupError عند أي فحص فاشل (ويُحذف الملف المؤقت).
    """
    meta = read_sidecar(source)
    sha_status = "skipped_plain"
    temp = workdir / f".restore_{os.getpid()}.db"
    temp.unlink(missing_ok=True)
    try:
        if source.name.endswith(".gz"):
            if meta and meta.get("sha256"):
                if sha256_file(source) != meta["sha256"]:
                    raise BackupError("بصمة sha256 لا تطابق الملف الجانبي — النسخة تالفة أو معدَّلة")
                sha_status = "verified"
            else:
                sha_status = "no_sidecar"
            gunzip_file(source, temp)
        else:
            temp.write_bytes(source.read_bytes())
        chmod_private(temp)
        check = inspect_sqlite(temp)
        if not check.integrity_ok:
            raise BackupError(f"فحص السلامة فشل: {check.integrity_message}")
        if check.missing_tables:
            raise BackupError("جداول أساسية ناقصة: " + "، ".join(check.missing_tables))
        local = local_schema_version()
        if check.schema_version and local and check.schema_version > local:
            raise BackupError(
                f"مخطَّط النسخة ({check.schema_version}) أحدث من كود هذا الإصدار ({local}) — حدّث الكود أولاً"
            )
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return Prepared(
        source=source,
        temp_db=temp,
        check=check,
        sha_status=sha_status,
        created_at=str((meta or {}).get("created_at", "؟")),
    )


def _remove_wal_files(database_path: Path) -> None:
    """حذف ملفَي -wal و-shm المرافقين للقاعدة القديمة."""
    for suffix in ("-wal", "-shm"):
        Path(str(database_path) + suffix).unlink(missing_ok=True)


async def _safety_copy(config: Config) -> str:
    """
    حفظ القاعدة الحالية قبل استبدالها، وإرجاع وصف ما حُفظ.

    سليمة ⇒ نسخة `pre_operation` موثَّقة. تالفة ⇒ تُنقل كما هي باسم `.corrupt-<ختم>` (لا حذف).
    """
    current = config.database_path
    if not current.exists():
        return "لا قاعدة حالية (استعادة على سيرفر جديد)"
    check = await asyncio.to_thread(inspect_sqlite, current)
    if not check.integrity_ok:
        stamp = utc_now().strftime("%Y%m%d_%H%M%S")
        kept = current.with_name(f"{current.name}.corrupt-{stamp}")
        os.replace(current, kept)
        for suffix in ("-wal", "-shm"):
            wal = Path(str(current) + suffix)
            if wal.exists():
                os.replace(wal, Path(str(kept) + suffix))
        chmod_private(kept)
        return f"القاعدة الحالية تالفة — حُفظت كما هي: {kept.name}"
    db = Database(current)
    await db.connect()
    try:
        artifact = await create_backup_file(
            db, config.backup_dir, backup_type="pre_operation", app_version=APP_VERSION
        )
    finally:
        await db.close()
    return f"نسخة أمان من القاعدة الحالية: {artifact.filename}"


async def _write_audit(config: Config, prepared: Prepared, safety_note: str) -> str | None:
    """تسجيل `backup.restore` داخل القاعدة المستعادة. يرجع نص تحذير إن تعذّر (لا يُفشل الاستعادة)."""
    db = Database(config.database_path)
    try:
        await db.connect()
        repos = Repositories(db)
        async with db.transaction() as tx:
            await repos.audit.log(
                tx,
                action="backup.restore",
                target_type="backup",
                target_id=prepared.source.name,
                details={
                    "restored_from": prepared.source.name,
                    "backup_created_at": prepared.created_at,
                    "schema_version": prepared.check.schema_version,
                    "sha": prepared.sha_status,
                    "safety": safety_note,
                },
                source="cli",
            )
    except Exception as exc:                                      # noqa: BLE001
        logger.exception("تعذّر تسجيل التدقيق بعد الاستعادة")
        return f"تعذّر تسجيل التدقيق: {type(exc).__name__}"
    finally:
        await db.close()
    return None


# ================================== التنفيذ ================================== #


async def run(
    *,
    list_only: bool = False,
    file: str | None = None,
    backup_id: int | None = None,
    latest: bool = False,
    assume_yes: bool = False,
    input_fn: Callable[[str], str] = input,
) -> int:
    """تنفيذ الاستعادة كاملة وإرجاع كود الخروج (انظر الوصف أعلى الملف)."""
    try:
        config = Config.load()
    except ConfigError as exc:
        print(f"❌ خطأ في الإعدادات: {exc}")
        return 2
    if os.name == "posix":
        os.umask(0o077)
    config.ensure_directories()
    setup_logging(config.log_file, config.log_level, console=False)

    if list_only:
        return print_list(config.backup_dir)

    lock = SingleInstance(config.data_dir / "bot.lock")
    try:
        lock.acquire()
    except AlreadyRunningError:
        print("❌ البوت يعمل الآن. أوقفه أولاً ثم أعد تشغيل الاستعادة.")
        return 1
    try:
        try:
            source = resolve_source(config, file=file, backup_id=backup_id, latest=latest)
            prepared = await asyncio.to_thread(prepare, source, config.database_path.parent)
        except BackupError as exc:
            print(f"❌ {exc}")
            return 1

        check = prepared.check
        print("— النسخة المطلوبة —")
        print(f"  الملف     : {source.name}")
        print(f"  أُنشئت    : {prepared.created_at}")
        print(f"  البصمة    : {_sha_text(prepared.sha_status)}")
        print(f"  المخطَّط  : {check.schema_version} (كود هذا الإصدار: {local_schema_version()})")
        print(f"  محتواها   : {check.users_count} مستخدم · {check.orders_count} طلب")
        if config.database_path.exists():
            current = await asyncio.to_thread(inspect_sqlite, config.database_path)
            print(f"  الحالية   : {current.users_count} مستخدم · {current.orders_count} طلب  ← ستُستبدل")
        print("⚠️ كل ما حدث بعد وقت النسخة (طلبات، أرصدة، شحنات) سيختفي من القاعدة الحية.")

        if not assume_yes:
            try:
                answer = input_fn(f"للمتابعة اكتب {CONFIRM_WORD} حرفياً: ").strip()
            except EOFError:
                answer = ""
            if answer != CONFIRM_WORD:
                prepared.temp_db.unlink(missing_ok=True)
                print("أُلغيت الاستعادة — لم يتغير شيء.")
                return 1

        try:
            safety_note = await _safety_copy(config)
            print(f"🛟 {safety_note}")
            _remove_wal_files(config.database_path)
            os.replace(prepared.temp_db, config.database_path)           # استبدال ذرّي
            chmod_private(config.database_path)
        except (OSError, BackupError) as exc:
            prepared.temp_db.unlink(missing_ok=True)
            logger.exception("فشلت الاستعادة")
            print(f"❌ فشل الاستبدال: {exc}")
            return 1

        final = await asyncio.to_thread(inspect_sqlite, config.database_path)
        if not final.is_restorable:
            print("❌ القاعدة بعد الاستبدال لا تجتاز الفحص — راجع نسخة الأمان في مجلد النسخ.")
            return 1
        warning = await _write_audit(config, prepared, safety_note)
        if warning:
            print(f"⚠️ {warning}")
        logger.warning("تمت استعادة القاعدة من %s", source.name)
        print(f"✅ تمت الاستعادة من {source.name}.")
        print("   شغّل البوت الآن؛ أي ترحيل ناقص سيُطبَّق عند الإقلاع بعد نسخة أمان تلقائية.")
        return 0
    finally:
        lock.release()


def _sha_text(status: str) -> str:
    """وصف حالة التحقق من البصمة."""
    return {
        "verified": "✅ مطابقة للملف الجانبي",
        "no_sidecar": "⚠️ لا ملف جانبي (فُحصت السلامة فقط)",
    }.get(status, "— ملف غير مضغوط")


def main() -> int:
    """نقطة الدخول: قراءة الوسائط وتشغيل الاستعادة."""
    parser = argparse.ArgumentParser(description="استعادة نسخة احتياطية (والبوت متوقف)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="عرض النسخ الموجودة")
    group.add_argument("--latest", action="store_true", help="أحدث نسخة موثَّقة")
    group.add_argument("--id", type=int, help="رقم النسخة في سجل النسخ")
    group.add_argument("--file", help="مسار ملف نسخة (.db.gz أو .db)")
    parser.add_argument("--yes", action="store_true", help="تخطّي سؤال التأكيد")
    args = parser.parse_args()
    return asyncio.run(
        run(
            list_only=args.list,
            file=args.file,
            backup_id=args.id,
            latest=args.latest,
            assume_yes=args.yes,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
