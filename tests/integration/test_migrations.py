"""اختبارات نظام الترحيلات وسلامة المخطط الناتج عنه."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.exceptions import MigrationChecksumError, MigrationError
from database.database import Database
from database.migrator import Migrator
from scripts.init_db import EXPECTED_TABLES


async def test_all_expected_tables_created(db: Database) -> None:
    """كل الجداول المتوقعة موجودة بعد تطبيق الترحيلات."""
    tables = set(await db.table_names())
    missing = [name for name in EXPECTED_TABLES if name not in tables]
    assert not missing, f"جداول ناقصة: {missing}"


async def test_migrations_are_recorded(db: Database) -> None:
    """كل ترحيل مطبق مسجَّل في جدول التتبع ببصمته."""
    migrator = Migrator(db)
    applied = await migrator.applied()
    files = migrator.load_files()
    assert len(applied) == len(files)
    for migration in files:
        assert applied[migration.version] == migration.checksum


async def test_apply_all_is_idempotent(db: Database) -> None:
    """إعادة التشغيل لا تطبق شيئاً مرتين ولا تسبب أخطاء."""
    migrator = Migrator(db)
    assert await migrator.apply_all() == []
    assert await migrator.pending() == []


async def test_modified_migration_is_rejected(tmp_path: Path) -> None:
    """تعديل ملف ترحيل سبق تطبيقه يُرفض فوراً."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_init.sql").write_text("CREATE TABLE demo (id INTEGER PRIMARY KEY);", encoding="utf-8")

    database = Database(tmp_path / "m.db")
    await database.connect()
    try:
        migrator = Migrator(database, migrations)
        assert await migrator.apply_all() == ["0001"]

        (migrations / "0001_init.sql").write_text(
            "CREATE TABLE demo (id INTEGER PRIMARY KEY, extra TEXT);", encoding="utf-8"
        )
        with pytest.raises(MigrationChecksumError):
            await migrator.apply_all()
    finally:
        await database.close()


async def test_failed_migration_rolls_back(tmp_path: Path) -> None:
    """فشل ترحيل في منتصفه لا يترك أثراً جزئياً في قاعدة البيانات."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_bad.sql").write_text(
        "CREATE TABLE good (id INTEGER PRIMARY KEY);\nCREATE TABLE bad (id INTEGER PRIMARY KEY;",
        encoding="utf-8",
    )
    database = Database(tmp_path / "bad.db")
    await database.connect()
    try:
        migrator = Migrator(database, migrations)
        with pytest.raises(MigrationError):
            await migrator.apply_all()
        tables = await database.table_names()
        assert "good" not in tables  # تراجع كامل
        assert await migrator.applied() == {}
    finally:
        await database.close()


async def test_seed_data_present(db: Database) -> None:
    """بيانات الزرع الأساسية موجودة: أدوار وصلاحيات وإعدادات وتصنيفات."""
    roles = await db.fetchval("SELECT COUNT(*) FROM roles")
    permissions = await db.fetchval("SELECT COUNT(*) FROM permissions")
    settings = await db.fetchval("SELECT COUNT(*) FROM settings")
    categories = await db.fetchval("SELECT COUNT(*) FROM service_categories")
    assert roles == 4
    assert permissions > 30
    assert settings > 20
    assert categories == 8


async def test_no_payment_methods_seeded(db: Database) -> None:
    """لا تُزرع طرق دفع وهمية — يضيفها الأدمن ببياناته الحقيقية."""
    assert await db.fetchval("SELECT COUNT(*) FROM payment_methods") == 0


async def test_foreign_keys_enabled(db: Database) -> None:
    """المفاتيح الأجنبية مفعّلة على مستوى الاتصال."""
    assert await db.fetchval("PRAGMA foreign_keys") == 1


async def test_wal_mode_enabled(db: Database) -> None:
    """وضع WAL مفعّل للسماح بالقراءة أثناء الكتابة."""
    assert str(await db.fetchval("PRAGMA journal_mode")).lower() == "wal"


async def test_transaction_keywords_rejected_in_migration(tmp_path: Path) -> None:
    """ملف ترحيل يحتوي BEGIN/COMMIT يُرفض (المُرحِّل وحده يدير المعاملات)."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_tx.sql").write_text(
        "BEGIN;\nCREATE TABLE demo (id INTEGER PRIMARY KEY);\nCOMMIT;", encoding="utf-8"
    )
    database = Database(tmp_path / "tx.db")
    await database.connect()
    try:
        with pytest.raises(MigrationError, match="ممنوعة"):
            await Migrator(database, migrations).apply_all()
        assert "demo" not in await database.table_names()
    finally:
        await database.close()


async def test_pragma_rejected_in_migration(tmp_path: Path) -> None:
    """ملف ترحيل يحتوي PRAGMA يُرفض (الإعدادات تُضبط عند الاتصال)."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_pragma.sql").write_text(
        "PRAGMA foreign_keys = OFF;\nCREATE TABLE demo (id INTEGER PRIMARY KEY);", encoding="utf-8"
    )
    database = Database(tmp_path / "pragma.db")
    await database.connect()
    try:
        with pytest.raises(MigrationError, match="ممنوعة"):
            await Migrator(database, migrations).apply_all()
    finally:
        await database.close()


async def test_comments_and_multiline_statements_parsed(tmp_path: Path) -> None:
    """التعليقات والعبارات متعددة الأسطر والفاصلة المنقوطة داخل نص لا تكسر التقسيم."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "0001_mix.sql").write_text(
        "-- تعليق افتتاحي\n"
        "CREATE TABLE demo (\n    id INTEGER PRIMARY KEY,\n    label TEXT NOT NULL\n);\n\n"
        "-- إدراج قيمة تحتوي فاصلة منقوطة\n"
        "INSERT INTO demo (label) VALUES ('a;b');\n"
        "-- تعليق ختامي\n",
        encoding="utf-8",
    )
    database = Database(tmp_path / "mix.db")
    await database.connect()
    try:
        assert await Migrator(database, migrations).apply_all() == ["0001"]
        assert await database.fetchval("SELECT label FROM demo") == "a;b"
    finally:
        await database.close()


async def test_migration_file_naming_enforced(tmp_path: Path) -> None:
    """اسم ملف ترحيل مخالف للنمط يُرفض بدل تطبيقه بترتيب عشوائي."""
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    (migrations / "initial.sql").write_text("CREATE TABLE demo (id INTEGER);", encoding="utf-8")
    database = Database(tmp_path / "name.db")
    await database.connect()
    try:
        with pytest.raises(MigrationError):
            await Migrator(database, migrations).apply_all()
    finally:
        await database.close()
