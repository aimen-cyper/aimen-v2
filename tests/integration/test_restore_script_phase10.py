"""اختبارات سكربت الاستعادة وحماية الترقية (المرحلة 10)."""

from __future__ import annotations

import argparse
import gzip
import json
import sqlite3
import stat
from pathlib import Path

import pytest

from database.database import Database
from database.migrator import Migrator
from database.repositories import Repositories
from scripts import init_db, restore_backup
from services import build_services
from utils import backup_files
from utils.security import SecretBox, generate_encryption_key
from utils.single_instance import SingleInstance

pytestmark = pytest.mark.asyncio


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """بيئة CLI معزولة: مسارات القاعدة والنسخ واللوق على مجلد مؤقت."""
    paths = {
        "db": tmp_path / "data" / "smm.db",
        "backups": tmp_path / "backups",
        "log": tmp_path / "logs" / "bot.log",
        "tmp": tmp_path,
    }
    paths["db"].parent.mkdir()
    monkeypatch.setenv("DATABASE_PATH", str(paths["db"]))
    monkeypatch.setenv("BACKUP_DIR", str(paths["backups"]))
    monkeypatch.setenv("LOG_FILE", str(paths["log"]))
    for key in ("BOT_TOKEN", "ENCRYPTION_KEY", "SUPER_ADMIN_IDS"):
        monkeypatch.delenv(key, raising=False)
    return paths


async def _make_db_with_backup(env: dict[str, Path], users: int = 2):
    """قاعدة فيها `users` مستخدمين + نسخة موثَّقة منها. يرجع معلومة النسخة."""
    db = Database(env["db"])
    await db.connect()
    await Migrator(db).apply_all()
    repos = Repositories(db)
    async with db.transaction() as tx:
        root = await repos.users.create(tx, telegram_id=1, first_name="Root", role="super_admin")
        for index in range(users - 1):
            await repos.users.create(tx, telegram_id=100 + index, first_name=f"U{index}")
    services = build_services(
        db, repos, secret_box=SecretBox(generate_encryption_key()), settings_ttl_seconds=0, backup_dir=env["backups"]
    )
    info = await services.backups.create(root)
    await db.close()
    return info


async def _count_users(path: Path) -> int:
    """عدد المستخدمين في ملف قاعدة (قراءة مباشرة)."""
    connection = sqlite3.connect(path)
    try:
        return int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])
    finally:
        connection.close()


async def _add_user(path: Path, telegram_id: int) -> None:
    """إضافة مستخدم بعد أخذ النسخة (ليثبت أن الاستعادة تمحوه)."""
    db = Database(path)
    await db.connect()
    repos = Repositories(db)
    async with db.transaction() as tx:
        await repos.users.create(tx, telegram_id=telegram_id, first_name="Late")
    await db.close()


# ================================ الاستعادة ================================ #


async def test_restore_latest_roundtrip(env, capsys) -> None:
    """استعادة أحدث نسخة تُرجع القاعدة لحالتها، وتحفظ نسخة أمان، وتدقّق، وتضبط 0600."""
    await _make_db_with_backup(env, users=2)
    await _add_user(env["db"], 555)
    assert await _count_users(env["db"]) == 3

    code = await restore_backup.run(latest=True, assume_yes=True)

    assert code == 0, capsys.readouterr().out
    assert await _count_users(env["db"]) == 2
    assert stat.S_IMODE(env["db"].stat().st_mode) == 0o600
    assert not Path(str(env["db"]) + "-wal").exists()
    safety = [p for p in backup_files.list_backup_files(env["backups"]) if "pre_operation" in p.name]
    assert len(safety) == 1                                       # القاعدة الحالية محفوظة قبل الاستبدال
    connection = sqlite3.connect(env["db"])
    try:
        row = connection.execute("SELECT source, details_json FROM audit_logs WHERE action = 'backup.restore'").fetchone()
    finally:
        connection.close()
    assert row[0] == "cli" and json.loads(row[1])["sha"] == "verified"


async def test_latest_skips_safety_copies(env) -> None:
    """تكرار `--latest` لا يعيد حالة «ما قبل الاستعادة» (نسخ الأمان لا تُختار تلقائياً)."""
    await _make_db_with_backup(env, users=2)
    await _add_user(env["db"], 555)
    assert await restore_backup.run(latest=True, assume_yes=True) == 0
    await _add_user(env["db"], 556)
    assert await restore_backup.run(latest=True, assume_yes=True) == 0
    assert await _count_users(env["db"]) == 2                     # من النسخة الأصلية لا من نسخة الأمان


async def test_restore_by_id_and_by_file(env) -> None:
    """الاستعادة بالرقم وبمسار الملف تعملان."""
    info = await _make_db_with_backup(env, users=2)
    await _add_user(env["db"], 555)
    assert await restore_backup.run(backup_id=info.id, assume_yes=True) == 0
    assert await _count_users(env["db"]) == 2
    await _add_user(env["db"], 556)
    assert await restore_backup.run(file=str(env["backups"] / info.filename), assume_yes=True) == 0
    assert await _count_users(env["db"]) == 2


async def test_confirmation_word_is_required(env, capsys) -> None:
    """بلا `--yes`: أي إجابة غير RESTORE تلغي العملية ولا تمس القاعدة."""
    await _make_db_with_backup(env, users=2)
    await _add_user(env["db"], 555)
    code = await restore_backup.run(latest=True, input_fn=lambda _p: "yes")
    assert code == 1 and await _count_users(env["db"]) == 3
    assert "أُلغيت" in capsys.readouterr().out
    assert await restore_backup.run(latest=True, input_fn=lambda _p: "RESTORE") == 0
    assert await _count_users(env["db"]) == 2


async def test_eof_on_prompt_cancels(env) -> None:
    """إغلاق stdin (تشغيل غير تفاعلي بلا --yes) يلغي بدل أن يستبدل."""
    await _make_db_with_backup(env, users=2)
    await _add_user(env["db"], 555)

    def _eof(_prompt: str) -> str:
        raise EOFError

    assert await restore_backup.run(latest=True, input_fn=_eof) == 1
    assert await _count_users(env["db"]) == 3


async def test_refuses_while_bot_is_running(env, capsys) -> None:
    """قفل البوت ممسوك ⇒ رفض فوري ولا تغيير."""
    await _make_db_with_backup(env, users=2)
    await _add_user(env["db"], 555)
    holder = SingleInstance(env["db"].parent / "bot.lock")
    holder.acquire()
    try:
        code = await restore_backup.run(latest=True, assume_yes=True)
    finally:
        holder.release()
    assert code == 1 and "البوت يعمل" in capsys.readouterr().out
    assert await _count_users(env["db"]) == 3


async def test_tampered_backup_is_rejected_and_db_untouched(env, capsys) -> None:
    """تغيير بايت واحد في النسخة ⇒ البصمة لا تطابق ⇒ رفض والقاعدة كما هي."""
    info = await _make_db_with_backup(env, users=2)
    await _add_user(env["db"], 555)
    path = env["backups"] / info.filename
    path.write_bytes(path.read_bytes() + b"x")
    assert await restore_backup.run(latest=True, assume_yes=True) == 1
    assert "بصمة" in capsys.readouterr().out
    assert await _count_users(env["db"]) == 3
    assert not list(env["db"].parent.glob(".restore_*"))             # لا ملفات مؤقتة متروكة


async def test_newer_schema_is_rejected(env, tmp_path, capsys) -> None:
    """نسخة مخطَّطها أحدث من كود هذا الإصدار تُرفض (لا نشغّل كوداً قديماً على مخطط جديد)."""
    info = await _make_db_with_backup(env, users=2)
    raw = tmp_path / "newer.db"
    raw.write_bytes(gzip.decompress((env["backups"] / info.filename).read_bytes()))
    connection = sqlite3.connect(raw)
    connection.execute("INSERT INTO schema_migrations(version, name, checksum, applied_at) VALUES ('9999','x','x','2030-01-01')")
    connection.commit()
    connection.close()
    assert await restore_backup.run(file=str(raw), assume_yes=True) == 1
    assert "أحدث" in capsys.readouterr().out


async def test_garbage_file_is_rejected(env, tmp_path, capsys) -> None:
    """ملف ليس قاعدة SQLite يُرفض."""
    await _make_db_with_backup(env, users=2)
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"hello" * 1000)
    assert await restore_backup.run(file=str(junk), assume_yes=True) == 1
    assert await _count_users(env["db"]) == 2


async def test_corrupt_current_db_is_kept_aside_not_deleted(env) -> None:
    """القاعدة الحالية التالفة تُنقل باسم `.corrupt-…` (تحليل لاحق) ثم تُستعاد النسخة."""
    await _make_db_with_backup(env, users=2)
    env["db"].write_bytes(b"corrupted" * 500)
    assert await restore_backup.run(latest=True, assume_yes=True) == 0
    assert await _count_users(env["db"]) == 2
    kept = list(env["db"].parent.glob("smm.db.corrupt-*"))
    assert len(kept) == 1 and kept[0].read_bytes().startswith(b"corrupted")


async def test_restore_on_fresh_server_without_current_db(env) -> None:
    """على سيرفر جديد بلا قاعدة: تُستعاد النسخة عبر `--file` بلا خطأ."""
    info = await _make_db_with_backup(env, users=2)
    env["db"].unlink()
    for suffix in ("-wal", "-shm"):
        Path(str(env["db"]) + suffix).unlink(missing_ok=True)
    assert await restore_backup.run(file=str(env["backups"] / info.filename), assume_yes=True) == 0
    assert await _count_users(env["db"]) == 2


async def test_no_selector_and_unknown_id_fail_cleanly(env, capsys) -> None:
    """رقم غير موجود أو ملف غير موجود يعطي رسالة واضحة وكود 1."""
    await _make_db_with_backup(env, users=2)
    assert await restore_backup.run(backup_id=9999, assume_yes=True) == 1
    assert await restore_backup.run(file="/nonexistent/x.db.gz", assume_yes=True) == 1
    assert "غير موجود" in capsys.readouterr().out


async def test_list_shows_backups_without_touching_anything(env, capsys) -> None:
    """`--list` يعرض النسخ ولا يحجز قفلاً ولا يعدّل."""
    info = await _make_db_with_backup(env, users=2)
    assert await restore_backup.run(list_only=True) == 0
    assert info.filename in capsys.readouterr().out


# ============================ نسخة أمان قبل الترقية ============================ #


async def test_init_db_takes_safety_backup_before_pending_migrations(env, monkeypatch, capsys) -> None:
    """ترقية قاعدة قائمة بترحيل ناقص تسبقها نسخة `pre_operation` موثَّقة."""
    await _make_db_with_backup(env, users=2)
    before = len(backup_files.list_backup_files(env["backups"]))

    async def _pending(self):
        return ["9999"]

    async def _apply(self):
        return ["9999"]

    monkeypatch.setattr(Migrator, "pending", _pending)
    monkeypatch.setattr(Migrator, "apply_all", _apply)
    await init_db.run(argparse.Namespace(status=False))
    files = backup_files.list_backup_files(env["backups"])
    assert len(files) == before + 1 and any("pre_operation" in f.name for f in files)
    assert "نسخة أمان قبل الترقية" in capsys.readouterr().out


async def test_init_db_fresh_database_takes_no_backup(env) -> None:
    """قاعدة جديدة (لا ترحيلات سابقة) لا تحتاج نسخة أمان."""
    await init_db.run(argparse.Namespace(status=False))
    assert not backup_files.list_backup_files(env["backups"])
