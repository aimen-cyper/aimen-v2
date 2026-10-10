"""
مستودعات مساعدة صغيرة:
    • ProviderRequestsRepository: سجل استدعاءات APIs المزودين (بدون أسرار).
    • ErrorLogsRepository      : تسجيل الأخطاء المهمة في قاعدة البيانات.
    • BackupsRepository        : سجل النسخ الاحتياطية.
"""

from __future__ import annotations

from core.constants import PROVIDER_RESPONSE_SNIPPET_LEN
from database.database import Tx
from database.repositories.base import BaseRepository
from utils.security import sanitize


class ProviderRequestsRepository(BaseRepository):
    """سجل استدعاءات المزودين لأغراض التشخيص (منقّى من الأسرار)."""

    async def log(
        self,
        tx: Tx,
        *,
        provider_id: int,
        action: str,
        is_success: bool,
        order_id: int | None = None,
        request_summary: str | None = None,
        http_status: int | None = None,
        response_snippet: str | None = None,
        duration_ms: int | None = None,
        error_type: str | None = None,
        secrets: tuple[str, ...] = (),
    ) -> None:
        """
        تسجيل استدعاء واحد لمزود.

        ملاحظة أمنية: يمر النص على دالة التنقية لحذف أي مفتاح قبل التخزين،
        ويُقتطع الرد حتى لا تتضخم قاعدة البيانات.
        """
        await tx.execute(
            """
            INSERT INTO provider_requests (provider_id, order_id, action, request_summary, http_status,
                                           response_snippet, duration_ms, is_success, error_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provider_id,
                order_id,
                action,
                sanitize(request_summary, secrets)[:PROVIDER_RESPONSE_SNIPPET_LEN],
                http_status,
                sanitize(response_snippet, secrets)[:PROVIDER_RESPONSE_SNIPPET_LEN],
                duration_ms,
                1 if is_success else 0,
                error_type,
                self.now(),
            ),
        )

    async def list_by_provider(self, provider_id: int, *, limit: int = 20) -> list[dict]:
        """آخر استدعاءات مزود معين."""
        rows = await self.db.fetchall(
            "SELECT * FROM provider_requests WHERE provider_id = ? ORDER BY id DESC LIMIT ?",
            (provider_id, limit),
        )
        return [dict(row) for row in rows]

    _CALL_SELECT = (
        "SELECT r.*, p.name AS provider_name FROM provider_requests r "
        "LEFT JOIN providers p ON p.id = r.provider_id"
    )

    async def list_page(self, *, only_failed: bool = False, limit: int = 8, offset: int = 0) -> list[dict]:
        """صفحة من سجل استدعاءات كل المزودين (الأحدث أولاً) مع اسم المزود؛ اختيارياً الفاشلة فقط."""
        where = " WHERE r.is_success = 0" if only_failed else ""
        rows = await self.db.fetchall(
            f"{self._CALL_SELECT}{where} ORDER BY r.id DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        return [dict(row) for row in rows]

    async def count_calls(self, *, only_failed: bool = False) -> int:
        """عدد الاستدعاءات المسجلة (أو الفاشلة فقط)."""
        return await self.count("provider_requests", "is_success = 0" if only_failed else "")

    async def get_call(self, request_id: int) -> dict | None:
        """استدعاء واحد بمعرّفه مع اسم المزود (لشاشة التفاصيل)."""
        row = await self.db.fetchone(f"{self._CALL_SELECT} WHERE r.id = ?", (request_id,))
        return dict(row) if row else None

    async def delete_old(self, tx: Tx, before_iso: str) -> int:
        """حذف السجلات الأقدم من تاريخ معين."""
        result = await tx.execute("DELETE FROM provider_requests WHERE created_at < ?", (before_iso,))
        return result.rowcount


class ErrorLogsRepository(BaseRepository):
    """تسجيل الأخطاء المهمة في قاعدة البيانات لعرضها في لوحة الأدمن."""

    async def log(
        self,
        tx: Tx,
        *,
        message: str,
        level: str = "ERROR",
        source: str = "app",
        error_type: str | None = None,
        traceback_snippet: str | None = None,
        user_id: int | None = None,
        update_summary: str | None = None,
    ) -> int | None:
        """تسجيل خطأ (بعد تنقيته من أي أسرار)."""
        result = await tx.execute(
            """
            INSERT INTO error_logs (level, source, error_type, message, traceback_snippet,
                                    user_id, update_summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                level, source, error_type, sanitize(message)[:1000],
                sanitize(traceback_snippet)[:2000] if traceback_snippet else None,
                user_id, sanitize(update_summary)[:500] if update_summary else None, self.now(),
            ),
        )
        return result.lastrowid

    async def mark_notified(self, tx: Tx, error_id: int) -> None:
        """تعليم أنه تم إشعار الأدمن بهذا الخطأ (منعاً لتكرار التنبيه)."""
        await tx.execute("UPDATE error_logs SET notified_admin = 1 WHERE id = ?", (error_id,))

    async def list_recent(self, *, limit: int = 20, offset: int = 0) -> list[dict]:
        """آخر الأخطاء المسجلة."""
        rows = await self.db.fetchall(
            "SELECT * FROM error_logs ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        return [dict(row) for row in rows]

    async def get(self, error_id: int) -> dict | None:
        """خطأ واحد بمعرّفه (لشاشة التفاصيل)."""
        row = await self.db.fetchone("SELECT * FROM error_logs WHERE id = ?", (error_id,))
        return dict(row) if row else None

    async def count_all(self) -> int:
        """إجمالي الأخطاء المسجلة."""
        return await self.count("error_logs")

    async def count_since(self, since_iso: str) -> int:
        """عدد الأخطاء منذ وقت معين (مؤشر صحة النظام)."""
        return await self.count("error_logs", "created_at >= ?", (since_iso,))

    async def delete_old(self, tx: Tx, before_iso: str) -> int:
        """حذف الأخطاء القديمة."""
        result = await tx.execute("DELETE FROM error_logs WHERE created_at < ?", (before_iso,))
        return result.rowcount


class BackupsRepository(BaseRepository):
    """
    سجل النسخ الاحتياطية (المرحلة 10: مكتمل).

    الحالات (`status`):
        ok       : نسخة سليمة (آخر فحص نجح).
        failed   : فشل إنشاؤها (لا ملف لها؛ السبب في `error_text`).
        corrupt  : فشل فحصها لاحقاً (بصمة مختلفة أو قاعدة تالفة) — لا تُستعمل للاستعادة.
        missing  : سجلها موجود وملفها غائب عن القرص.
        purged   : حُذف ملفها بسياسة الاحتفاظ (يبقى السجل أثراً تاريخياً).
    """

    async def add(
        self,
        tx: Tx,
        *,
        filename: str,
        path: str,
        size_bytes: int,
        sha256: str | None = None,
        type: str = "manual",
        created_by: int | None = None,
        status: str = "ok",
        schema_version: str | None = None,
        error_text: str | None = None,
        created_at: str | None = None,
    ) -> int | None:
        """تسجيل نسخة احتياطية جديدة (`created_at` يُمرَّر عند استيراد نسخة من القرص)."""
        result = await tx.execute(
            """
            INSERT INTO backups (filename, path, size_bytes, sha256, type, created_by, status,
                                 schema_version, error_text, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (filename, path, size_bytes, sha256, type, created_by, status,
             schema_version, error_text, created_at or self.now()),
        )
        return result.lastrowid

    async def get(self, backup_id: int) -> dict | None:
        """نسخة بمعرّفها (None إن لم توجد)."""
        row = await self.db.fetchone("SELECT * FROM backups WHERE id = ?", (backup_id,))
        return dict(row) if row else None

    async def get_by_filename(self, filename: str) -> dict | None:
        """نسخة باسم ملفها (للاستيراد من القرص ومنع التكرار)."""
        row = await self.db.fetchone(
            "SELECT * FROM backups WHERE filename = ? ORDER BY id DESC LIMIT 1", (filename,)
        )
        return dict(row) if row else None

    async def list_recent(self, *, limit: int = 10) -> list[dict]:
        """آخر النسخ الاحتياطية."""
        rows = await self.db.fetchall(
            "SELECT * FROM backups ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in rows]

    async def list_page(
        self, *, limit: int, offset: int = 0, include_purged: bool = False
    ) -> list[dict]:
        """صفحة من النسخ (الأحدث أولاً). المحذوفة بالاحتفاظ مخفية افتراضياً."""
        where = "" if include_purged else "WHERE status <> 'purged'"
        rows = await self.db.fetchall(
            f"SELECT * FROM backups {where} ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        return [dict(row) for row in rows]

    async def count_visible(self, *, include_purged: bool = False) -> int:
        """عدد النسخ المعروضة."""
        where = "" if include_purged else "status <> 'purged'"
        return await self.count("backups", where) if where else await self.count("backups")

    async def latest(self, *, status: str = "ok", backup_type: str | None = None) -> dict | None:
        """أحدث نسخة بحالة معينة (ونوع اختياري)."""
        if backup_type is None:
            row = await self.db.fetchone(
                "SELECT * FROM backups WHERE status = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                (status,),
            )
        else:
            row = await self.db.fetchone(
                """
                SELECT * FROM backups WHERE status = ? AND type = ?
                 ORDER BY created_at DESC, id DESC LIMIT 1
                """,
                (status, backup_type),
            )
        return dict(row) if row else None

    async def latest_failure_after(self, since_iso: str) -> dict | None:
        """أحدث نسخة فاشلة بعد وقت معين (لتنبيه الأدمن)."""
        row = await self.db.fetchone(
            "SELECT * FROM backups WHERE status = 'failed' AND created_at > ? ORDER BY id DESC LIMIT 1",
            (since_iso,),
        )
        return dict(row) if row else None

    async def list_ok_newest_first(self) -> list[dict]:
        """كل النسخ السليمة الأحدث أولاً (أساس سياسة الاحتفاظ)."""
        rows = await self.db.fetchall(
            "SELECT * FROM backups WHERE status = 'ok' ORDER BY created_at DESC, id DESC"
        )
        return [dict(row) for row in rows]

    async def list_older_than(self, before_iso: str) -> list[dict]:
        """النسخ الأقدم من تاريخ معين (لحذف ملفاتها ضمن سياسة الاحتفاظ)."""
        rows = await self.db.fetchall(
            "SELECT * FROM backups WHERE created_at < ? AND status <> 'purged' ORDER BY id",
            (before_iso,),
        )
        return [dict(row) for row in rows]

    async def totals(self) -> dict[str, int]:
        """عدّادات للشاشة: عدد النسخ السليمة وحجمها الكلي وعدد الفاشلة/التالفة."""
        row = await self.db.fetchone(
            """
            SELECT COALESCE(SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END), 0)              AS ok_count,
                   COALESCE(SUM(CASE WHEN status = 'ok' THEN size_bytes ELSE 0 END), 0)     AS ok_bytes,
                   COALESCE(SUM(CASE WHEN status IN ('failed','corrupt','missing') THEN 1 ELSE 0 END), 0)
                                                                                            AS bad_count
              FROM backups
            """
        )
        return {
            "ok_count": int(row["ok_count"]) if row else 0,
            "ok_bytes": int(row["ok_bytes"]) if row else 0,
            "bad_count": int(row["bad_count"]) if row else 0,
        }

    async def set_verification(self, tx: Tx, backup_id: int, *, status: str, error_text: str | None) -> bool:
        """تسجيل نتيجة فحص: الحالة الجديدة ووقت الفحص وسبب الفشل (إن وُجد)."""
        result = await tx.execute(
            "UPDATE backups SET status = ?, verified_at = ?, error_text = ? WHERE id = ? AND status <> 'purged'",
            (status, self.now(), error_text, backup_id),
        )
        return result.rowcount > 0

    async def mark_purged(self, tx: Tx, backup_id: int) -> bool:
        """تعليم نسخة كمحذوفة الملف (يبقى السجل)."""
        result = await tx.execute(
            "UPDATE backups SET status = 'purged' WHERE id = ? AND status <> 'purged'", (backup_id,)
        )
        return result.rowcount > 0

    async def mark_channel_sent(self, tx: Tx, backup_id: int, *, message_id: int | None) -> bool:
        """تسجيل إرسال النسخة لقناة النسخ الخارجية."""
        result = await tx.execute(
            "UPDATE backups SET channel_message_id = ?, channel_sent_at = ? WHERE id = ?",
            (message_id, self.now(), backup_id),
        )
        return result.rowcount > 0
