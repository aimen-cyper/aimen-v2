"""المرحلة 12.1 — فشل COMMIT نفسه لا يترك اتصال الكتابة داخل معاملة مفتوحة."""

from __future__ import annotations

import sqlite3

import pytest

from database.database import Database

pytestmark = pytest.mark.asyncio


async def test_commit_failure_rolls_back_and_database_stays_usable(db: Database, monkeypatch) -> None:
    """COMMIT يفشل مرة: التغيير لا يُحفظ، والاستثناء يصل للمستدعي، والمعاملة التالية تعمل."""
    async with db.transaction() as tx:
        await tx.execute("CREATE TABLE probe (k TEXT)")
        await tx.execute("INSERT INTO probe (k) VALUES ('probe_a')")

    conn = db._write_conn
    real_execute = conn.execute
    state = {"failed": False}

    async def boom():
        """COMMIT فاشل مع بقاء المعاملة مفتوحة (كما في SQLITE_BUSY/IOERR): يجب أن يتراجع عنها الكود."""
        raise sqlite3.OperationalError("disk I/O error")

    def flaky_execute(sql, *args, **kwargs):
        if sql == "COMMIT" and not state["failed"]:
            state["failed"] = True
            return boom()
        return real_execute(sql, *args, **kwargs)

    monkeypatch.setattr(conn, "execute", flaky_execute)

    with pytest.raises(sqlite3.OperationalError):
        async with db.transaction() as tx:
            await tx.execute("INSERT INTO probe (k) VALUES ('probe_b')")

    assert state["failed"]
    assert await db.fetchval("SELECT COUNT(*) FROM probe WHERE k = 'probe_b'") == 0, "تغيير معاملة فاشلة حُفظ"

    async with db.transaction() as tx:                 # يجب ألا يفشل بـ«within a transaction»
        await tx.execute("INSERT INTO probe (k) VALUES ('probe_c')")
    assert await db.fetchval("SELECT COUNT(*) FROM probe WHERE k IN ('probe_a', 'probe_c')") == 2
