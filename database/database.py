"""
طبقة الوصول إلى قاعدة البيانات (SQLite عبر aiosqlite).

التصميم:
    • اتصال كتابة واحد محمي بقفل asyncio  ← لأن SQLite يسمح بكاتب واحد فقط،
      والتسلسل الصريح يمنع أخطاء "database is locked" العشوائية.
    • مجموعة اتصالات للقراءة (WAL يسمح بقراءات متوازية أثناء الكتابة).
    • كل كتابة تتم داخل معاملة BEGIN IMMEDIATE ... COMMIT، مع دعم المعاملات المتداخلة
      (إذا فتحت خدمة معاملة ثم نادت خدمة أخرى، تُستخدم نفس المعاملة ولا تُفتح ثانية).
    • إعادة محاولة تلقائية محدودة عند قفل قاعدة البيانات.

كل عبارات SQL هنا وفي المستودعات (repositories) مُعلَّمة بـ ? — لا بناء نصوص SQL يدوياً.
"""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Sequence

import aiosqlite

from core.exceptions import DatabaseError, DatabaseLockedError
from utils.logging_setup import get_logger

logger = get_logger(__name__)

SQLParams = Sequence[Any] | dict[str, Any]


@dataclass(frozen=True)
class ExecResult:
    """نتيجة تنفيذ عبارة كتابة: عدد الصفوف المتأثرة ومعرف آخر صف مُدرج."""

    rowcount: int
    lastrowid: int | None


def _is_locked_error(exc: BaseException) -> bool:
    """هل هذا الخطأ ناتج عن قفل مؤقت لقاعدة البيانات (قابل لإعادة المحاولة)؟"""
    return isinstance(exc, sqlite3.OperationalError) and (
        "locked" in str(exc).lower() or "busy" in str(exc).lower()
    )


class Tx:
    """
    مقبض معاملة مفتوحة على اتصال الكتابة.

    يُمرَّر إلى دوال المستودعات التي تُعدِّل البيانات، لضمان أن كل التعديلات
    المترابطة (خصم رصيد + إنشاء طلب + تسجيل حركة + إشعار) تتم كوحدة واحدة.
    """

    def __init__(self, conn: aiosqlite.Connection) -> None:
        """ربط المعاملة باتصال aiosqlite المفتوح."""
        self._conn = conn

    async def execute(self, sql: str, params: SQLParams = ()) -> ExecResult:
        """تنفيذ عبارة كتابة (INSERT/UPDATE/DELETE) وإرجاع عدد الصفوف والمعرف الجديد."""
        async with self._conn.execute(sql, params) as cursor:
            return ExecResult(rowcount=cursor.rowcount, lastrowid=cursor.lastrowid)

    async def executemany(self, sql: str, seq: Iterable[SQLParams]) -> ExecResult:
        """تنفيذ نفس العبارة على مجموعة قيم (إدراج جماعي)."""
        async with self._conn.executemany(sql, seq) as cursor:
            return ExecResult(rowcount=cursor.rowcount, lastrowid=cursor.lastrowid)

    async def fetchone(self, sql: str, params: SQLParams = ()) -> aiosqlite.Row | None:
        """قراءة صف واحد داخل المعاملة (يرى التعديلات غير المثبتة بعد)."""
        async with self._conn.execute(sql, params) as cursor:
            return await cursor.fetchone()

    async def fetchall(self, sql: str, params: SQLParams = ()) -> list[aiosqlite.Row]:
        """قراءة كل الصفوف داخل المعاملة."""
        async with self._conn.execute(sql, params) as cursor:
            return list(await cursor.fetchall())

    async def fetchval(self, sql: str, params: SQLParams = (), default: Any = None) -> Any:
        """قراءة قيمة واحدة (أول عمود من أول صف) داخل المعاملة."""
        row = await self.fetchone(sql, params)
        if row is None:
            return default
        value = row[0]
        return default if value is None else value


#: المعاملة النشطة في السياق الحالي (لدعم المعاملات المتداخلة بأمان)
_current_tx: ContextVar[Tx | None] = ContextVar("smm_current_tx", default=None)


class Database:
    """مدير الاتصال بقاعدة البيانات: اتصال كتابة واحد + مجموعة اتصالات قراءة."""

    def __init__(
        self,
        path: str | Path,
        *,
        read_pool_size: int = 3,
        busy_timeout_ms: int = 5_000,
        max_retries: int = 5,
    ) -> None:
        """تهيئة المدير دون فتح الاتصال (الفتح يتم في connect)."""
        self.path = Path(path)
        self._read_pool_size = max(1, read_pool_size)
        self._busy_timeout_ms = busy_timeout_ms
        self._max_retries = max_retries
        self._write_conn: aiosqlite.Connection | None = None
        self._read_pool: asyncio.Queue[aiosqlite.Connection] | None = None
        self._read_conns: list[aiosqlite.Connection] = []
        self._write_lock = asyncio.Lock()
        self._connected = False

    # ------------------------------ الاتصال ------------------------------ #

    async def connect(self) -> None:
        """فتح الاتصالات وتطبيق إعدادات SQLite المطلوبة (WAL، المفاتيح الأجنبية...)."""
        if self._connected:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self._write_conn = await self._open_connection()
        self._read_pool = asyncio.Queue(maxsize=self._read_pool_size)
        for _ in range(self._read_pool_size):
            conn = await self._open_connection()
            self._read_conns.append(conn)
            self._read_pool.put_nowait(conn)

        self._connected = True
        logger.info("تم الاتصال بقاعدة البيانات: %s", self.path)

    async def _open_connection(self) -> aiosqlite.Connection:
        """فتح اتصال واحد وضبط إعداداته (isolation_level=None للتحكم اليدوي بالمعاملات)."""
        conn = await aiosqlite.connect(self.path, isolation_level=None)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode = WAL")
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.execute(f"PRAGMA busy_timeout = {int(self._busy_timeout_ms)}")
        await conn.execute("PRAGMA synchronous = NORMAL")
        await conn.execute("PRAGMA temp_store = MEMORY")
        return conn

    async def close(self) -> None:
        """إغلاق كل الاتصالات بأمان."""
        if not self._connected:
            return
        for conn in self._read_conns:
            await conn.close()
        self._read_conns.clear()
        if self._write_conn is not None:
            await self._write_conn.close()
            self._write_conn = None
        self._read_pool = None
        self._connected = False
        logger.info("تم إغلاق الاتصال بقاعدة البيانات.")

    def _require_connected(self) -> None:
        """التأكد من أن الاتصال مفتوح قبل أي عملية."""
        if not self._connected or self._write_conn is None or self._read_pool is None:
            raise DatabaseError("قاعدة البيانات غير متصلة — نادِ connect() أولاً.")

    # ------------------------------ المعاملات ----------------------------- #

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Tx]:
        """
        فتح معاملة كتابة ذرّية (BEGIN IMMEDIATE ... COMMIT).

        الاستخدام:
            async with db.transaction() as tx:
                await repo.do_something(tx, ...)

        الضمانات:
            • أي استثناء داخل الكتلة يؤدي إلى ROLLBACK كامل.
            • المعاملات المتداخلة تُعيد استخدام نفس المعاملة (لا commit مبكر).
            • إعادة محاولة محدودة إذا كانت قاعدة البيانات مقفولة مؤقتاً.
        """
        self._require_connected()
        existing = _current_tx.get()
        if existing is not None:
            # معاملة متداخلة: نكمل ضمن نفس المعاملة الخارجية
            yield existing
            return

        async with self._write_lock:
            conn = self._write_conn
            assert conn is not None
            await self._begin_with_retry(conn)
            tx = Tx(conn)
            token = _current_tx.set(tx)
            try:
                yield tx
                await conn.execute("COMMIT")
            except BaseException:
                # يشمل فشل COMMIT نفسه: بدون ROLLBACK يبقى اتصال الكتابة داخل معاملة مفتوحة
                # فيفشل كل `BEGIN IMMEDIATE` التالي حتى إعادة تشغيل البوت.
                await self._rollback_quietly(conn)
                raise
            finally:
                _current_tx.reset(token)

    async def _begin_with_retry(self, conn: aiosqlite.Connection) -> None:
        """بدء معاملة فورية مع إعادة محاولة عند القفل المؤقت."""
        delay = 0.05
        for attempt in range(1, self._max_retries + 1):
            try:
                await conn.execute("BEGIN IMMEDIATE")
                return
            except sqlite3.OperationalError as exc:
                if not _is_locked_error(exc) or attempt == self._max_retries:
                    if _is_locked_error(exc):
                        raise DatabaseLockedError(
                            "تعذر بدء المعاملة: قاعدة البيانات مقفولة."
                        ) from exc
                    raise DatabaseError(f"خطأ في بدء المعاملة: {exc}") from exc
                logger.warning("قاعدة البيانات مقفولة، إعادة المحاولة %s/%s", attempt, self._max_retries)
                await asyncio.sleep(delay)
                delay *= 2

    async def _rollback_quietly(self, conn: aiosqlite.Connection) -> None:
        """تنفيذ ROLLBACK مع تسجيل أي مشكلة (دون إخفاء الخطأ الأصلي)."""
        try:
            await conn.execute("ROLLBACK")
        except sqlite3.Error as exc:  # نسجل ولا نبتلع: الخطأ الأصلي هو الأهم
            if "no transaction is active" in str(exc):
                logger.debug("لا معاملة نشطة للتراجع عنها (SQLite أنهتها بنفسها): %s", exc)
            else:
                logger.error("فشل التراجع عن المعاملة: %s", exc)

    # ------------------------------- القراءة ------------------------------ #

    @asynccontextmanager
    async def _reader(self) -> AsyncIterator[aiosqlite.Connection]:
        """حجز اتصال قراءة من المجموعة وإعادته بعد الانتهاء."""
        self._require_connected()
        assert self._read_pool is not None
        conn = await self._read_pool.get()
        try:
            yield conn
        finally:
            self._read_pool.put_nowait(conn)

    async def fetchone(self, sql: str, params: SQLParams = ()) -> aiosqlite.Row | None:
        """قراءة صف واحد (تستخدم المعاملة الحالية إن وُجدت، وإلا اتصال قراءة)."""
        tx = _current_tx.get()
        if tx is not None:
            return await tx.fetchone(sql, params)
        async with self._reader() as conn, conn.execute(sql, params) as cursor:
            return await cursor.fetchone()

    async def fetchall(self, sql: str, params: SQLParams = ()) -> list[aiosqlite.Row]:
        """قراءة كل الصفوف المطابقة."""
        tx = _current_tx.get()
        if tx is not None:
            return await tx.fetchall(sql, params)
        async with self._reader() as conn, conn.execute(sql, params) as cursor:
            return list(await cursor.fetchall())

    async def fetchval(self, sql: str, params: SQLParams = (), default: Any = None) -> Any:
        """قراءة قيمة مفردة (مثل COUNT أو SUM)."""
        row = await self.fetchone(sql, params)
        if row is None:
            return default
        value = row[0]
        return default if value is None else value

    # ------------------------------ أدوات إدارية --------------------------- #

    async def executescript(self, script: str) -> None:
        """
        تنفيذ سكربت SQL كامل على اتصال الكتابة (يُستخدم للترحيلات فقط).

        تحذير: هذه الدالة تتحكم بالمعاملات بنفسها، لذا لا تُستدعى داخل transaction().
        """
        self._require_connected()
        assert self._write_conn is not None
        async with self._write_lock:
            await self._write_conn.executescript(script)

    async def execute_raw(self, sql: str, params: SQLParams = ()) -> ExecResult:
        """
        تنفيذ عبارة كتابة مفردة خارج معاملة صريحة (للأدوات الإدارية فقط).

        ⚠️ ممنوع استخدامها في أي عملية مالية — تلك تمر عبر transaction() دائماً.
        """
        self._require_connected()
        assert self._write_conn is not None
        async with self._write_lock:
            async with self._write_conn.execute(sql, params) as cursor:
                return ExecResult(rowcount=cursor.rowcount, lastrowid=cursor.lastrowid)

    async def table_names(self) -> list[str]:
        """قائمة بأسماء جداول قاعدة البيانات (للتحقق والاختبارات)."""
        rows = await self.fetchall(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        return [row["name"] for row in rows]

    async def integrity_check(self) -> bool:
        """فحص سلامة ملف قاعدة البيانات (يُستخدم قبل/بعد النسخ الاحتياطي)."""
        result = await self.fetchval("PRAGMA integrity_check")
        return str(result).lower() == "ok"

    async def foreign_key_check(self) -> list[aiosqlite.Row]:
        """فحص وجود أي انتهاك للمفاتيح الأجنبية (يجب أن تكون النتيجة فارغة)."""
        return await self.fetchall("PRAGMA foreign_key_check")

    async def vacuum(self) -> None:
        """ضغط ملف قاعدة البيانات بعد عمليات الحذف الكبيرة."""
        self._require_connected()
        assert self._write_conn is not None
        async with self._write_lock:
            await self._write_conn.execute("VACUUM")

    async def snapshot_to(self, destination: str | Path) -> None:
        """
        نسخة متّسقة من القاعدة الحيّة إلى ملف جديد (`VACUUM INTO`) دون إيقاف البوت.

        لماذا `VACUUM INTO` وليس نسخ الملف؟ ملف WAL قد يحوي معاملات مثبّتة لم تُدمج
        بعد في الملف الرئيسي، فنسخ الملف وحده قد يعطي نسخة ناقصة أو تالفة. هذا الأمر
        يقرأ لقطة واحدة متّسقة عبر اتصال قراءة (لا يحجب الكتابة) ويكتب ملفاً مدمجاً.

        المدخلات: مسار ملف غير موجود (يُرفض الاستبدال حتى لا نكتب فوق نسخة قائمة).
        الاستثناءات: DatabaseError عند وجود الملف أو فشل الأمر.
        """
        target = Path(destination)
        if target.exists():
            raise DatabaseError(f"ملف النسخة موجود مسبقاً: {target.name}")
        async with self._reader() as conn:
            try:
                await conn.execute("VACUUM INTO ?", (str(target),))
            except sqlite3.Error as exc:
                target.unlink(missing_ok=True)
                raise DatabaseError(f"فشل أخذ لقطة من القاعدة: {exc}") from exc
