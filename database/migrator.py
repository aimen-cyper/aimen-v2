"""
مُرحِّل قاعدة البيانات (Migrations Runner).

الفكرة:
    • كل تعديل على المخطط يوضع في ملف SQL مرقّم داخل database/migrations/.
    • تُطبَّق الملفات بالترتيب مرة واحدة فقط، ويُسجَّل ما طُبِّق في جدول schema_migrations.
    • لكل ملف بصمة SHA-256؛ إذا عُدِّل ملف سبق تطبيقه يُرفع خطأ فوراً
      (لأن ذلك يعني أن قواعد بيانات مختلفة أصبحت بمخططات مختلفة).
    • كل ملف يُطبَّق داخل معاملة واحدة: إما ينجح كاملاً أو لا شيء.

قواعد كتابة ملفات الترحيل:
    • لا تضع PRAGMA ولا BEGIN/COMMIT داخل الملف.
    • لا تعدّل ملفاً مطبقاً؛ أنشئ ملفاً جديداً بدلاً منه.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from core.exceptions import MigrationChecksumError, MigrationError
from database.database import Database
from utils.logging_setup import get_logger

logger = get_logger(__name__)

MIGRATIONS_DIR: Path = Path(__file__).resolve().parent / "migrations"

#: نمط اسم الملف: 0001_name.sql
_FILENAME_RE = re.compile(r"^(\d{4})_([a-zA-Z0-9_\-]+)\.sql$")


@dataclass(frozen=True)
class MigrationFile:
    """ملف ترحيل واحد بعد قراءته."""

    version: str
    name: str
    sql: str
    checksum: str
    path: Path


#: كلمات ممنوعة في بداية أي عبارة داخل ملف ترحيل
#: (المُرحِّل هو من يفتح المعاملة ويضبط الـ PRAGMA؛ وجودها في الملف يكسر ذرّية الترحيل)
_FORBIDDEN_STARTS: tuple[str, ...] = (
    "begin", "commit", "end transaction", "rollback", "pragma", "attach", "detach", "vacuum",
)


def _split_statements(sql: str) -> list[str]:
    """
    تقسيم نص SQL إلى عبارات مكتملة.

    نعتمد على sqlite3.complete_statement لأنه يفهم علامات الاقتباس والتعليقات
    وأجسام TRIGGER (BEGIN … END)، فلا ينكسر التقسيم عند وجود فاصلة منقوطة داخلها.
    """
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement and not _is_comment_only(statement):
                statements.append(statement)
            buffer = ""
    leftover = buffer.strip()
    if leftover and not _is_comment_only(leftover):
        raise MigrationError(f"عبارة SQL غير مكتملة في نهاية الملف: {leftover[:80]}…")
    return statements


def _is_comment_only(statement: str) -> bool:
    """هل هذه الكتلة تعليقات فقط بلا SQL فعلي؟"""
    for line in statement.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            return False
    return True


def _strip_leading_comments(statement: str) -> str:
    """إزالة أسطر التعليق من بداية العبارة للتحقق من كلمتها الأولى."""
    lines = statement.splitlines()
    index = 0
    while index < len(lines) and (not lines[index].strip() or lines[index].strip().startswith("--")):
        index += 1
    return "\n".join(lines[index:]).strip()


class Migrator:
    """مسؤول عن قراءة ملفات الترحيل وتطبيق الناقص منها."""

    def __init__(self, db: Database, migrations_dir: Path | str = MIGRATIONS_DIR) -> None:
        """تهيئة المُرحِّل بقاعدة بيانات متصلة ومجلد الترحيلات."""
        self.db = db
        self.dir = Path(migrations_dir)

    # ------------------------------ القراءة ------------------------------ #

    def load_files(self) -> list[MigrationFile]:
        """
        قراءة كل ملفات الترحيل من المجلد وترتيبها تصاعدياً حسب رقم الإصدار.

        الاستثناءات:
            MigrationError : اسم ملف غير مطابق للنمط، أو تكرار رقم إصدار.
        """
        if not self.dir.exists():
            raise MigrationError(f"مجلد الترحيلات غير موجود: {self.dir}")

        files: list[MigrationFile] = []
        seen: set[str] = set()
        for path in sorted(self.dir.glob("*.sql")):
            match = _FILENAME_RE.match(path.name)
            if not match:
                raise MigrationError(
                    f"اسم ملف ترحيل غير صالح: {path.name} — الصيغة المطلوبة 0001_description.sql"
                )
            version, name = match.group(1), match.group(2)
            if version in seen:
                raise MigrationError(f"رقم إصدار مكرر في الترحيلات: {version}")
            seen.add(version)
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            files.append(MigrationFile(version=version, name=name, sql=sql, checksum=checksum, path=path))
        return files

    async def ensure_table(self) -> None:
        """إنشاء جدول تتبع الترحيلات إن لم يكن موجوداً."""
        await self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                checksum   TEXT NOT NULL,
                applied_at TEXT NOT NULL
            );
            """
        )

    async def applied(self) -> dict[str, str]:
        """إرجاع الترحيلات المطبقة على شكل: رقم الإصدار → البصمة."""
        rows = await self.db.fetchall("SELECT version, checksum FROM schema_migrations")
        return {row["version"]: row["checksum"] for row in rows}

    # ------------------------------ التطبيق ------------------------------ #

    async def apply_all(self) -> list[str]:
        """
        تطبيق كل الترحيلات غير المطبقة بالترتيب.

        المخرجات: قائمة بأرقام الإصدارات التي طُبِّقت في هذه المرة (فارغة إذا كان كل شيء محدّثاً).

        الاستثناءات:
            MigrationChecksumError : ملف مطبق سابقاً تم تعديله.
            MigrationError         : فشل تنفيذ SQL (مع التراجع الكامل عن الملف).
        """
        await self.ensure_table()
        done = await self.applied()
        files = self.load_files()

        # التحقق من عدم تعديل أي ملف سبق تطبيقه
        for migration in files:
            previous = done.get(migration.version)
            if previous is not None and previous != migration.checksum:
                raise MigrationChecksumError(
                    f"الملف {migration.path.name} تم تعديله بعد تطبيقه. "
                    "أنشئ ملف ترحيل جديداً بدل تعديل القديم."
                )

        newly_applied: list[str] = []
        for migration in files:
            if migration.version in done:
                continue
            await self._apply_one(migration)
            newly_applied.append(migration.version)
            logger.info("تم تطبيق الترحيل %s_%s", migration.version, migration.name)

        if not newly_applied:
            logger.info("قاعدة البيانات محدّثة — لا توجد ترحيلات جديدة.")
        return newly_applied

    def _prepare_statements(self, migration: MigrationFile) -> list[str]:
        """
        تجهيز عبارات ملف الترحيل والتحقق من خلوّها من الممنوعات.

        الاستثناءات:
            MigrationError : الملف فارغ، أو يحتوي BEGIN/COMMIT/PRAGMA … داخله.
        """
        statements = _split_statements(migration.sql)
        if not statements:
            raise MigrationError(f"ملف الترحيل فارغ بلا أي عبارة: {migration.path.name}")
        for statement in statements:
            head = _strip_leading_comments(statement).lower()
            for forbidden in _FORBIDDEN_STARTS:
                if head.startswith(forbidden):
                    raise MigrationError(
                        f"العبارة «{forbidden.upper()}» ممنوعة داخل ملف الترحيل "
                        f"{migration.path.name} — المُرحِّل يتكفل بالمعاملات وإعدادات PRAGMA."
                    )
        return statements

    async def _apply_one(self, migration: MigrationFile) -> None:
        """
        تطبيق ملف ترحيل واحد داخل معاملة ذرّية مع تسجيله في جدول التتبع.

        ملاحظة مهمة: لا نستخدم executescript هنا لأنه يُثبِّت (COMMIT) أي معاملة مفتوحة
        قبل تنفيذ النص، فتضيع ذرّية الترحيل؛ لذلك نُقسِّم الملف وننفّذ عباراته واحدة
        واحدة داخل معاملة واحدة يديرها كائن Database.
        """
        statements = self._prepare_statements(migration)
        try:
            async with self.db.transaction() as tx:
                for statement in statements:
                    await tx.execute(statement)
                await tx.execute(
                    """
                    INSERT INTO schema_migrations (version, name, checksum, applied_at)
                    VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                    """,
                    (migration.version, migration.name, migration.checksum),
                )
        except sqlite3.Error as exc:
            raise MigrationError(f"فشل تطبيق الترحيل {migration.path.name}: {exc}") from exc

    # ------------------------------ التحقق ------------------------------- #

    async def current_version(self) -> str | None:
        """آخر رقم إصدار مطبق على قاعدة البيانات."""
        return await self.db.fetchval(
            "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
        )

    async def pending(self) -> list[str]:
        """قائمة الترحيلات غير المطبقة بعد."""
        await self.ensure_table()
        done = await self.applied()
        return [m.version for m in self.load_files() if m.version not in done]
