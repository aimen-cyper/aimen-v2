"""
خدمة النسخ الاحتياطي (المرحلة 10).

المسؤوليات:
    • إنشاء نسخة متّسقة من القاعدة الحيّة دون إيقاف البوت (يدوية/مجدولة/قبل عملية خطِرة).
    • التحقق الحقيقي من كل نسخة: بصمة SHA-256 + فتحها وفحص سلامتها وجداولها.
    • إرسال النسخة إلى قناة خاصة خارج السيرفر (قرار D7) وتنزيلها للأدمن.
    • سياسة الاحتفاظ: حذف **ملفات** النسخ القديمة مع إبقاء سجلها، وبحدّ أدنى لا يُمسّ.
    • مراقبة الموثوقية: تنبيه الأدمن إن فشلت النسخة أو تأخرت عن موعدها.
    • ضغط القاعدة (`VACUUM`) بعد نسخة أمان إلزامية.

الاستعادة **ليست** هنا عمداً: استبدال قاعدة بيانات تعمل من داخل البوت نفسه يعني أن
البوت يكتب فوق الملف الذي يقرأ منه. الاستعادة تتم من `scripts/restore_backup.py` والبوت
متوقف، وتأخذ نسخة أمان من الحالة الحالية قبل أي استبدال.

الأمان:
    • الصلاحية على كل عملية (`backup.create` للإنشاء والفحص، `backup.download` للإرسال).
    • أسماء الملفات تُبنى من السجل وتُحصر داخل مجلد النسخ (`safe_backup_path`).
    • ملفات النسخ بصلاحية المالك فقط (0600) والمجلد (0700).
    • كل عملية مُدقَّقة في `audit_logs`، ولا يُكتب في أي سجل ما يخص أسرار البيئة.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from telegram.error import TelegramError

from core.enums import BackupType
from core.exceptions import BackupBusyError, BackupError, ValidationError
from core.permissions import Permission
from database.database import Database
from database.models import User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.notification_service import NotificationService
from services.settings_service import SettingsService
from utils.backup_files import (
    TELEGRAM_UPLOAD_LIMIT_BYTES,
    build_backup_name,
    chmod_private,
    ensure_private_dir,
    free_disk_bytes,
    gunzip_file,
    gzip_file,
    human_size,
    inspect_sqlite,
    list_backup_files,
    read_sidecar,
    safe_backup_path,
    sha256_file,
    sidecar_path,
    write_sidecar,
)
from utils.datetime_utils import iso_minus_days, parse_iso, to_iso, utc_now
from utils.logging_setup import get_logger
from utils.security import new_token, sanitize

logger = get_logger(__name__)

#: أقل فاصل بين محاولتين تلقائيتين بعد فشل (دقيقة) — لا نُغرق القرص بمحاولات فاشلة
RETRY_AFTER_FAILURE_MINUTES = 30

#: نسخة تأخرت أكثر من هذا المضاعف لفاصلها تُعدّ «متأخرة» ويُنبَّه الأدمن
OVERDUE_FACTOR = 2

#: أقل قيمة لمهلة التأخر بالساعات (حتى لو كان الفاصل ساعة واحدة)
MIN_OVERDUE_HOURS = 2

#: أنواع النسخ التي تؤجّل موعد النسخة المجدولة (نسخ ما قبل العمليات لا تفعل)
_SCHEDULE_RELEVANT_TYPES = (BackupType.MANUAL, BackupType.SCHEDULED)

#: حالات النسخة المعتبرة سليمة
STATUS_OK = "ok"

#: أقصى عدد ثوانٍ نتقدّمها لتفادي تصادم اسم النسخة
MAX_NAME_COLLISIONS = 120


# ============================== نماذج البيانات ============================== #


@dataclass(frozen=True, slots=True)
class BackupArtifact:
    """نتيجة إنشاء ملف نسخة على القرص (قبل تسجيلها في قاعدة البيانات)."""

    filename: str
    path: Path
    size_bytes: int
    sha256: str
    schema_version: str | None
    backup_type: str
    created_at: str
    db_bytes: int


@dataclass(frozen=True, slots=True)
class BackupInfo:
    """نسخة مسجَّلة (صف من جدول `backups` بحقول مسمّاة)."""

    id: int
    filename: str
    size_bytes: int
    sha256: str | None
    type: str
    status: str
    created_at: str
    created_by: int | None
    schema_version: str | None
    verified_at: str | None
    channel_message_id: int | None
    channel_sent_at: str | None
    error_text: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> BackupInfo:
        """بناء الكائن من صف قاعدة البيانات."""
        return cls(
            id=int(row["id"]),
            filename=str(row["filename"]),
            size_bytes=int(row["size_bytes"] or 0),
            sha256=row.get("sha256"),
            type=str(row["type"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            created_by=row.get("created_by"),
            schema_version=row.get("schema_version"),
            verified_at=row.get("verified_at"),
            channel_message_id=row.get("channel_message_id"),
            channel_sent_at=row.get("channel_sent_at"),
            error_text=row.get("error_text"),
        )

    @property
    def is_ok(self) -> bool:
        """هل النسخة سليمة وقابلة للاستعمال؟"""
        return self.status == STATUS_OK

    @property
    def sent_to_channel(self) -> bool:
        """هل أُرسلت للقناة الخارجية؟"""
        return bool(self.channel_sent_at)


@dataclass(frozen=True, slots=True)
class VerifyResult:
    """نتيجة فحص نسخة."""

    status: str
    message: str
    schema_version: str | None = None

    @property
    def ok(self) -> bool:
        """هل الفحص ناجح؟"""
        return self.status == STATUS_OK


@dataclass(frozen=True, slots=True)
class BackupSummary:
    """ملخص حالة النسخ للشاشة الرئيسية ولفحوص الأمان."""

    last_ok: BackupInfo | None
    age_hours: float | None
    ok_count: int
    ok_bytes: int
    bad_count: int
    interval_hours: int
    retention_days: int
    min_keep: int
    channel_configured: bool
    send_to_channel: bool
    overdue: bool
    db_bytes: int
    free_bytes: int

    @property
    def auto_enabled(self) -> bool:
        """هل النسخ التلقائي مفعّل؟"""
        return self.interval_hours > 0

    @property
    def off_server_copy(self) -> bool:
        """هل تُرسل نسخة خارج السيرفر فعلاً؟ (قناة مضبوطة والإرسال مفعّل)"""
        return self.channel_configured and self.send_to_channel


# ===================== إنشاء ملف النسخة (يُستعمل أيضاً عند الإقلاع) ===================== #


def _check_disk_space(backup_dir: Path, db_bytes: int) -> None:
    """التأكد من وجود مساحة كافية (قاعدة خام + مضغوطة + هامش) قبل البدء."""
    needed = db_bytes * 2 + 20 * 1024 * 1024
    free = free_disk_bytes(backup_dir)
    if free < needed:
        raise BackupError(
            f"مساحة القرص غير كافية للنسخ: متاح {human_size(free)} والمطلوب {human_size(needed)}",
            user_message="❌ مساحة القرص غير كافية لإنشاء نسخة احتياطية.",
        )


def _finalize_blocking(raw: Path, backup_dir: Path, name: str, backup_type: str, meta_extra: dict[str, Any]):
    """
    الجزء الثقيل (يعمل في خيط): فحص اللقطة ← ضغط ← بصمة ← ملف جانبي.

    يرفع BackupError إن كانت اللقطة نفسها غير سليمة؛ فلا نحتفظ بنسخة معطوبة
    ونحسبها نسخة جيدة.
    """
    check = inspect_sqlite(raw)
    if not check.is_restorable:
        reason = check.integrity_message if not check.integrity_ok else f"جداول ناقصة: {check.missing_tables}"
        raise BackupError(f"اللقطة غير سليمة فلن تُحفظ: {reason}")

    final = safe_backup_path(backup_dir, name)
    partial = final.with_name(f".partial_{new_token(8)}.gz")
    try:
        size = gzip_file(raw, partial)
        chmod_private(partial)
        os.replace(partial, final)
    finally:
        partial.unlink(missing_ok=True)

    digest = sha256_file(final)
    created_at = meta_extra["created_at"]
    write_sidecar(
        final,
        {
            "filename": name,
            "sha256": digest,
            "size_bytes": size,
            "type": backup_type,
            "created_at": created_at,
            "schema_version": check.schema_version,
            "users_count": check.users_count,
            "orders_count": check.orders_count,
            "db_bytes": raw.stat().st_size,
            "app_version": meta_extra.get("app_version"),
            "created_by": meta_extra.get("created_by"),
        },
    )
    return final, size, digest, check.schema_version, raw.stat().st_size


async def create_backup_file(
    db: Database,
    backup_dir: Path,
    *,
    backup_type: str,
    app_version: str = "",
    created_by: int | None = None,
) -> BackupArtifact:
    """
    إنشاء ملف نسخة مضغوطة وموثَّقة من القاعدة الحيّة (بلا أي تسجيل في الجدول).

    دالة مستقلة لأن مسار الإقلاع (نسخة ما قبل الترحيل) يحتاجها قبل بناء الخدمات.

    الاستثناءات: BackupError عند نقص المساحة أو فشل اللقطة أو عدم سلامتها.
    """
    ensure_private_dir(backup_dir)
    db_bytes = db.path.stat().st_size if db.path.exists() else 0
    _check_disk_space(backup_dir, db_bytes)

    now = utc_now()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    name = build_backup_name(backup_type, stamp)
    for _attempt in range(MAX_NAME_COLLISIONS):
        if not safe_backup_path(backup_dir, name).exists():
            break
        # نسخ متتالية في الثانية نفسها: نتقدّم ثانية بدل الكتابة فوق نسخة موجودة
        now += timedelta(seconds=1)
        name = build_backup_name(backup_type, now.strftime("%Y%m%d_%H%M%S"))
    else:
        raise BackupError("تعذّر اختيار اسم فريد للنسخة (تصادم متكرر)")

    raw = backup_dir / f".raw_{new_token(8)}.db"
    try:
        await db.snapshot_to(raw)
        chmod_private(raw)
        meta = {"created_at": to_iso(now), "app_version": app_version, "created_by": created_by}
        final, size, digest, schema, raw_bytes = await asyncio.to_thread(
            _finalize_blocking, raw, backup_dir, name, backup_type, meta
        )
    except BackupError:
        raise
    except Exception as exc:                                      # noqa: BLE001
        # أي فشل غير متوقع (قرص/صلاحيات/SQLite) يُحوَّل لخطأ نسخ بنص واضح، والأصل في اللوق
        logger.exception("فشل إنشاء نسخة احتياطية")
        raise BackupError(f"فشل إنشاء النسخة: {type(exc).__name__}: {sanitize(str(exc))[:200]}") from exc
    finally:
        raw.unlink(missing_ok=True)

    return BackupArtifact(
        filename=name,
        path=final,
        size_bytes=size,
        sha256=digest,
        schema_version=schema,
        backup_type=backup_type,
        created_at=to_iso(now),
        db_bytes=raw_bytes,
    )


def _verify_blocking(path: Path, expected_sha: str | None, backup_dir: Path) -> VerifyResult:
    """
    فحص نسخة كاملاً (يعمل في خيط): وجود الملف ← البصمة ← فك الضغط ← سلامة SQLite.

    الترتيب من الأرخص إلى الأغلى، فنتوقف عند أول عطب ونذكر سببه بدقة.
    """
    if not path.is_file():
        return VerifyResult("missing", "ملف النسخة غير موجود على القرص")

    actual = sha256_file(path)
    if expected_sha and actual != expected_sha:
        return VerifyResult("corrupt", "بصمة الملف لا تطابق المسجَّلة — الملف تغيّر أو تلف")
    sidecar = read_sidecar(path)
    if sidecar and sidecar.get("sha256") and sidecar["sha256"] != actual:
        return VerifyResult("corrupt", "بصمة الملف لا تطابق ملفه الجانبي")

    probe = backup_dir / f".verify_{new_token(8)}.db"
    try:
        try:
            gunzip_file(path, probe)
        except BackupError as exc:
            return VerifyResult("corrupt", str(exc))
        check = inspect_sqlite(probe)
    finally:
        probe.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm"):
            probe.with_name(probe.name + suffix).unlink(missing_ok=True)

    if not check.integrity_ok:
        return VerifyResult("corrupt", f"فحص سلامة القاعدة فشل: {check.integrity_message[:150]}")
    if check.missing_tables:
        return VerifyResult("corrupt", f"جداول أساسية ناقصة: {', '.join(check.missing_tables)}")
    return VerifyResult(STATUS_OK, "البصمة صحيحة والقاعدة سليمة", check.schema_version)


# ================================== الخدمة ================================== #


class BackupService:
    """إدارة النسخ الاحتياطي: إنشاء، فحص، إرسال، احتفاظ، مراقبة، ضغط القاعدة."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        audit: AuditService,
        auth: AuthService,
        notifications: NotificationService,
        *,
        backup_dir: Path,
        channel_id: int | str | None = None,
        app_version: str = "",
    ) -> None:
        """
        تهيئة الخدمة.

        المدخلات:
            backup_dir  : مجلد النسخ (يُنشأ عند أول نسخة).
            channel_id  : قناة النسخ الخارجية (None ⇒ غير مضبوطة).
            app_version : يُكتب في الملف الجانبي لتتبّع أي إصدار أنتج النسخة.
        """
        self.db = db
        self.repos = repos
        self.settings = settings
        self.audit = audit
        self.auth = auth
        self.notifications = notifications
        self.backup_dir = Path(backup_dir)
        self.channel_id = channel_id
        self.app_version = app_version
        self._lock = asyncio.Lock()

    # ----------------------------- أدوات داخلية ----------------------------- #

    def path_of(self, info: BackupInfo) -> Path:
        """مسار ملف نسخة — يُبنى من الاسم المسجَّل ويُحصر داخل مجلد النسخ."""
        return safe_backup_path(self.backup_dir, info.filename)

    async def _require(self, actor: User, permission: str, *, context: str) -> None:
        """فحص صلاحية الفاعل (دفاع ثانٍ بعد فحص المعالج)."""
        await self.auth.require_permission(actor, permission, context=context)

    async def _load(self, backup_id: int) -> BackupInfo:
        """تحميل نسخة أو رفع خطأ تحقق واضح."""
        row = await self.repos.backups.get(backup_id)
        if row is None:
            raise ValidationError(
                f"نسخة غير موجودة: {backup_id}", user_message="❌ هذه النسخة غير موجودة."
            )
        return BackupInfo.from_row(row)

    # ------------------------------- الإنشاء ------------------------------- #

    async def create(
        self,
        actor: User | None,
        *,
        backup_type: str = BackupType.MANUAL,
        reason: str = "",
    ) -> BackupInfo:
        """
        إنشاء نسخة جديدة وتسجيلها وتدقيقها.

        المدخلات:
            actor       : الأدمن المنفِّذ (None للنظام: المجدولة وما قبل العمليات).
            backup_type : manual / scheduled / pre_operation.
            reason      : سبب النسخة (يُدوَّن في التدقيق، مثل «قبل ضغط القاعدة»).

        الاستثناءات:
            PermissionDeniedError : الفاعل بلا `backup.create`.
            BackupBusyError       : نسخة أخرى قيد الإنشاء.
            BackupError           : فشل الإنشاء (يُسجَّل صف `failed` بسببه).
        """
        if actor is not None:
            await self._require(actor, Permission.BACKUP_CREATE, context="backup.create")
        if self._lock.locked():
            raise BackupBusyError("نسخة قيد الإنشاء")

        async with self._lock:
            try:
                artifact = await create_backup_file(
                    self.db,
                    self.backup_dir,
                    backup_type=str(backup_type),
                    app_version=self.app_version,
                    created_by=actor.id if actor else None,
                )
            except BackupError as exc:
                await self._record_failure(actor, str(backup_type), str(exc))
                raise

            async with self.db.transaction() as tx:
                backup_id = await self.repos.backups.add(
                    tx,
                    filename=artifact.filename,
                    path=artifact.filename,
                    size_bytes=artifact.size_bytes,
                    sha256=artifact.sha256,
                    type=str(backup_type),
                    created_by=actor.id if actor else None,
                    status=STATUS_OK,
                    schema_version=artifact.schema_version,
                    created_at=artifact.created_at,
                )
                await self.audit.log(
                    tx,
                    action="backup.create",
                    admin_id=actor.id if actor else None,
                    target_type="backup",
                    target_id=backup_id,
                    after={
                        "filename": artifact.filename,
                        "type": str(backup_type),
                        "size_bytes": artifact.size_bytes,
                        "sha256_prefix": artifact.sha256[:12],
                        "schema_version": artifact.schema_version,
                    },
                    details={"reason": reason} if reason else None,
                    source="telegram" if actor else "system",
                )
        assert backup_id is not None
        logger.info("نسخة احتياطية جديدة: %s (%s)", artifact.filename, human_size(artifact.size_bytes))
        return await self._load(backup_id)

    async def _record_failure(self, actor: User | None, backup_type: str, message: str) -> None:
        """تسجيل نسخة فاشلة (سجل + تدقيق + خطأ) لتظهر في اللوحة ولا تضيع بصمت."""
        clean = sanitize(message)[:500]
        stamp = utc_now().strftime("%Y%m%d_%H%M%S")
        async with self.db.transaction() as tx:
            await self.repos.backups.add(
                tx,
                filename=f"failed_{backup_type}_{stamp}",
                path="",
                size_bytes=0,
                type=backup_type,
                created_by=actor.id if actor else None,
                status="failed",
                error_text=clean,
            )
            await self.audit.log(
                tx,
                action="backup.create_failed",
                admin_id=actor.id if actor else None,
                target_type="backup",
                details={"type": backup_type, "error": clean},
                source="telegram" if actor else "system",
            )
            await self.repos.error_logs.log(
                tx, message=f"فشل نسخة احتياطية ({backup_type}): {clean}", source="backup", error_type="BackupError"
            )

    # -------------------------------- القراءة -------------------------------- #

    async def list_page(self, actor: User, *, page: int, page_size: int) -> tuple[list[BackupInfo], int]:
        """صفحة من النسخ (الأحدث أولاً) مع العدد الكلي."""
        await self._require(actor, Permission.BACKUP_CREATE, context="backup.list")
        total = await self.repos.backups.count_visible()
        rows = await self.repos.backups.list_page(limit=page_size, offset=max(0, page - 1) * page_size)
        return [BackupInfo.from_row(row) for row in rows], total

    async def get(self, actor: User, backup_id: int) -> BackupInfo:
        """تفاصيل نسخة."""
        await self._require(actor, Permission.BACKUP_CREATE, context=f"backup:{backup_id}")
        return await self._load(backup_id)

    async def summary(self, actor: User) -> BackupSummary:
        """ملخص الحالة للشاشة الرئيسية."""
        await self._require(actor, Permission.BACKUP_CREATE, context="backup.summary")
        return await self.build_summary()

    async def build_summary(self) -> BackupSummary:
        """ملخص الحالة بلا فاعل (للمهمة الدورية ولفحوص الأمان — الحارس عند المستدعي)."""
        interval = await self.settings.get_int("backup_interval_hours", 12)
        retention = await self.settings.get_int("backup_retention_days", 14)
        min_keep = await self.settings.get_int("backup_min_keep", 5)
        send_flag = await self.settings.get_bool("backup_send_to_channel", True)
        totals = await self.repos.backups.totals()
        last_row = await self._latest_relevant_ok()
        last = BackupInfo.from_row(last_row) if last_row else None
        age = self._age_hours(last.created_at) if last else None
        db_bytes = self.db.path.stat().st_size if self.db.path.exists() else 0
        return BackupSummary(
            last_ok=last,
            age_hours=age,
            ok_count=totals["ok_count"],
            ok_bytes=totals["ok_bytes"],
            bad_count=totals["bad_count"],
            interval_hours=interval,
            retention_days=retention,
            min_keep=min_keep,
            channel_configured=self.channel_id is not None,
            send_to_channel=send_flag,
            overdue=self._is_overdue(interval, age),
            db_bytes=db_bytes,
            free_bytes=free_disk_bytes(self.backup_dir),
        )

    async def _latest_relevant_ok(self) -> dict | None:
        """أحدث نسخة سليمة يدوية أو مجدولة (نسخ ما قبل العمليات لا تُحتسب للموعد)."""
        for row in await self.repos.backups.list_ok_newest_first():
            if row["type"] in _SCHEDULE_RELEVANT_TYPES:
                return row
        return None

    @staticmethod
    def _age_hours(created_at: str) -> float | None:
        """عمر نسخة بالساعات (None إن تعذّر قراءة وقتها)."""
        moment = parse_iso(created_at)
        if moment is None:
            return None
        return max(0.0, (utc_now() - moment).total_seconds() / 3600)

    @staticmethod
    def _is_overdue(interval_hours: int, age_hours: float | None) -> bool:
        """
        هل تأخرت النسخ عن موعدها؟ (يتطلب نسخاً تلقائياً مفعّلاً).

        لا نسخة سليمة إطلاقاً ⇒ متأخرة. وإلا العمر أكبر من ضعف الفاصل (بحدّ أدنى ساعتان).
        """
        if interval_hours <= 0:
            return False
        if age_hours is None:
            return True
        return age_hours > max(MIN_OVERDUE_HOURS, interval_hours * OVERDUE_FACTOR)

    async def is_overdue(self) -> bool:
        """هل النسخ التلقائي متأخر؟ (يغذّي فحص الأمان وشاشة الصحة)."""
        return (await self.build_summary()).overdue

    # --------------------------------- الفحص --------------------------------- #

    async def verify(self, actor: User | None, backup_id: int) -> VerifyResult:
        """
        فحص نسخة فحصاً حقيقياً وتسجيل النتيجة (الحالة + وقت الفحص).

        النتيجة الفاشلة تُغيّر حالة النسخة إلى `corrupt`/`missing` فلا تُستعمل ولا
        تُحتسب ضمن «آخر نسخة سليمة».
        """
        if actor is not None:
            await self._require(actor, Permission.BACKUP_CREATE, context=f"backup.verify:{backup_id}")
        info = await self._load(backup_id)
        if info.status in ("failed", "purged"):
            return VerifyResult(info.status, "لا ملف لهذه النسخة (فاشلة أو محذوفة بسياسة الاحتفاظ)")

        path = self.path_of(info)
        result = await asyncio.to_thread(_verify_blocking, path, info.sha256, self.backup_dir)
        async with self.db.transaction() as tx:
            await self.repos.backups.set_verification(
                tx, info.id, status=result.status, error_text=None if result.ok else result.message
            )
            await self.audit.log(
                tx,
                action="backup.verify",
                admin_id=actor.id if actor else None,
                target_type="backup",
                target_id=info.id,
                before={"status": info.status},
                after={"status": result.status, "message": result.message},
                source="telegram" if actor else "system",
            )
        if not result.ok:
            logger.error("نسخة %s فشل فحصها: %s", info.filename, result.message)
        return result

    # --------------------------------- الإرسال --------------------------------- #

    def _ensure_sendable(self, info: BackupInfo) -> Path:
        """التحقق أن الملف موجود وسليم ظاهرياً (البصمة) وفي حدود رفع تيليجرام."""
        if not info.is_ok:
            raise BackupError(f"النسخة ليست سليمة (الحالة: {info.status})", user_message="❌ لا يمكن إرسال نسخة غير سليمة.")
        path = self.path_of(info)
        if not path.is_file():
            raise BackupError("ملف النسخة غير موجود", user_message="❌ ملف النسخة غير موجود على القرص.")
        size = path.stat().st_size
        if size > TELEGRAM_UPLOAD_LIMIT_BYTES:
            raise BackupError(
                f"حجم النسخة {human_size(size)} يتجاوز حد رفع البوت",
                user_message=f"❌ حجم النسخة ({human_size(size)}) يتجاوز حد رفع تيليجرام (50MB). انسخها من السيرفر مباشرة.",
            )
        if info.sha256 and sha256_file(path) != info.sha256:
            raise BackupError("بصمة النسخة لا تطابق المسجَّلة", user_message="❌ بصمة النسخة لا تطابق المسجَّلة — لن تُرسل.")
        return path

    @staticmethod
    def _caption(info: BackupInfo) -> str:
        """وصف الملف المُرسل: بيانات تعريفية فقط بلا أي سر."""
        sha = (info.sha256 or "—")[:12]
        return (
            f"💾 نسخة احتياطية ({info.type})\n"
            f"الحجم: {human_size(info.size_bytes)}\n"
            f"المخطط: {info.schema_version or '—'}\n"
            f"SHA-256: {sha}…\n"
            f"الوقت (UTC): {info.created_at[:19].replace('T', ' ')}"
        )

    async def _deliver(self, bot: Any, chat_id: int | str, info: BackupInfo) -> int | None:
        """رفع ملف النسخة إلى محادثة وإرجاع رقم الرسالة."""
        path = await asyncio.to_thread(self._ensure_sendable, info)
        try:
            with path.open("rb") as handle:
                message = await bot.send_document(
                    chat_id=chat_id,
                    document=handle,
                    filename=info.filename,
                    caption=self._caption(info),
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=30,
                    protect_content=True,
                )
        except (TelegramError, OSError) as exc:
            reason = sanitize(str(exc))[:150]
            logger.error("فشل رفع النسخة %s إلى تيليجرام: %s", info.filename, reason)
            hint = ""
            if "chat not found" in reason.lower():
                hint = (
                    "\nالسبب المعتاد: BACKUP_CHANNEL_ID خاطئ أو البوت ليس مشرفاً في القناة. "
                    "للقناة الخاصة استعمل -100xxxxxxxxxx (وليس رابط الدعوة) وأضِف البوت مشرفاً بصلاحية النشر. "
                    "افحصها من: لوحة التحكم ← 📢 القنوات."
                )
            raise BackupError(
                f"فشل رفع النسخة: {type(exc).__name__}: {reason}",
                user_message=f"❌ تعذّر إرسال الملف عبر تيليجرام: {reason or type(exc).__name__}{hint}",
            ) from exc
        return getattr(message, "message_id", None)

    async def send_to_channel(self, actor: User | None, bot: Any, backup_id: int) -> BackupInfo:
        """
        إرسال نسخة إلى قناة النسخ الخارجية وتسجيل رقم الرسالة.

        الاستثناءات:
            PermissionDeniedError : الفاعل بلا `backup.download`.
            BackupError           : القناة غير مضبوطة، أو النسخة غير صالحة للإرسال.
        """
        if actor is not None:
            await self._require(actor, Permission.BACKUP_DOWNLOAD, context=f"backup.channel:{backup_id}")
        if self.channel_id is None:
            raise BackupError(
                "BACKUP_CHANNEL_ID غير مضبوط",
                user_message="❌ قناة النسخ غير مضبوطة (BACKUP_CHANNEL_ID في ملف البيئة).",
            )
        info = await self._load(backup_id)
        message_id = await self._deliver(bot, self.channel_id, info)
        async with self.db.transaction() as tx:
            await self.repos.backups.mark_channel_sent(tx, info.id, message_id=message_id)
            await self.audit.log(
                tx,
                action="backup.send_channel",
                admin_id=actor.id if actor else None,
                target_type="backup",
                target_id=info.id,
                after={"channel_message_id": message_id},
                source="telegram" if actor else "system",
            )
        return await self._load(backup_id)

    async def download(self, actor: User, bot: Any, backup_id: int, *, chat_id: int) -> BackupInfo:
        """
        إرسال نسخة إلى محادثة الأدمن الطالب (عملية خطِرة: البيانات كلها داخل الملف).

        الاستثناءات: PermissionDeniedError · BackupError.
        """
        await self._require(actor, Permission.BACKUP_DOWNLOAD, context=f"backup.download:{backup_id}")
        info = await self._load(backup_id)
        await self._deliver(bot, chat_id, info)
        await self.audit.log_standalone(
            action="backup.download",
            admin_id=actor.id,
            target_type="backup",
            target_id=info.id,
            details={"filename": info.filename},
            source="telegram",
        )
        return info

    # ----------------------------- الاحتفاظ والكتالوج ----------------------------- #

    async def enforce_retention(self) -> int:
        """
        حذف **ملفات** النسخ الأقدم من مدة الاحتفاظ، مع حماية أحدث `backup_min_keep` نسخة سليمة.

        السجل لا يُحذف (تصير حالته `purged`) فيبقى أثر أن النسخة وُجدت. المخرجات: عدد المحذوفة.
        """
        days = await self.settings.get_int("backup_retention_days", 14)
        min_keep = max(1, await self.settings.get_int("backup_min_keep", 5))
        newest_ok = await self.repos.backups.list_ok_newest_first()
        protected = {row["id"] for row in newest_ok[:min_keep]}

        purged = 0
        for row in await self.repos.backups.list_older_than(iso_minus_days(days)):
            if row["id"] in protected or row["status"] == "failed":
                continue
            info = BackupInfo.from_row(row)
            try:
                path = self.path_of(info)
            except BackupError:
                logger.warning("نسخة باسم غير معتمد تُركت دون حذف: %r", info.filename)
                continue
            for target in (path, sidecar_path(path)):
                try:
                    target.unlink(missing_ok=True)
                except OSError as exc:
                    logger.error("تعذّر حذف %s: %s", target.name, exc)
                    break
            else:
                async with self.db.transaction() as tx:
                    if await self.repos.backups.mark_purged(tx, info.id):
                        purged += 1
                        await self.audit.log(
                            tx,
                            action="backup.purge",
                            admin_id=None,
                            target_type="backup",
                            target_id=info.id,
                            details={"filename": info.filename, "retention_days": days},
                            source="system",
                        )
        if purged:
            logger.info("سياسة الاحتفاظ: حُذفت ملفات %s نسخة قديمة", purged)
        return purged

    async def sync_catalog(self) -> dict[str, int]:
        """
        مواءمة السجل مع القرص (عند الإقلاع):
            • ملف على القرص بلا سجل (مثل نسخة ما قبل الترحيل، أو بعد استعادة قاعدة أقدم) ⇒ يُسجَّل.
            • سجل سليم بلا ملف ⇒ تصير حالته `missing`.

        المخرجات: `{"imported": n, "missing": m}`.
        """
        imported = missing = 0
        known = {row["filename"] for row in await self.repos.backups.list_page(limit=100_000, include_purged=True)}

        for path in list_backup_files(self.backup_dir):
            if path.name in known:
                continue
            sidecar = read_sidecar(path) or {}
            digest = await asyncio.to_thread(sha256_file, path)
            trusted = bool(sidecar.get("sha256")) and sidecar["sha256"] == digest
            note = None if trusted else "استُورد دون ملف جانبي مطابق — افحصه قبل الاعتماد عليه"
            created = sidecar.get("created_at") or to_iso(datetime.fromtimestamp(path.stat().st_mtime, tz=UTC))
            backup_type = sidecar.get("type") if sidecar.get("type") in {str(t) for t in BackupType} else str(BackupType.MANUAL)
            async with self.db.transaction() as tx:
                await self.repos.backups.add(
                    tx,
                    filename=path.name,
                    path=path.name,
                    size_bytes=path.stat().st_size,
                    sha256=digest,
                    type=backup_type,
                    created_by=None,
                    status=STATUS_OK if trusted else "corrupt",
                    schema_version=sidecar.get("schema_version"),
                    error_text=note,
                    created_at=created,
                )
            imported += 1

        for row in await self.repos.backups.list_ok_newest_first():
            info = BackupInfo.from_row(row)
            try:
                exists = self.path_of(info).is_file()
            except BackupError:
                exists = False
            if not exists:
                async with self.db.transaction() as tx:
                    await self.repos.backups.set_verification(
                        tx, info.id, status="missing", error_text="الملف غير موجود على القرص"
                    )
                missing += 1
        if imported or missing:
            logger.warning("مواءمة النسخ: استيراد %s · مفقودة %s", imported, missing)
        return {"imported": imported, "missing": missing}

    # ------------------------------- المهمة الدورية ------------------------------- #

    async def run_scheduled(self, bot: Any) -> dict[str, int]:
        """
        جولة المهمة الدورية: نسخة إن حان موعدها ← إرسال للقناة ← احتفاظ ← تنبيه عند العطل.

        مصمَّمة لتُستدعى كل بضع دقائق: القرار «هل حان الموعد؟» من آخر نسخة سليمة،
        فإعادة تشغيل البوت لا تُنتج نسخة جديدة في كل مرة، وتغيير الفاصل يسري فوراً.
        فاصل صفر يعطّل النسخ التلقائي (الاحتفاظ والتنبيه يعملان كالمعتاد).

        المخرجات: عدّادات الجولة.
        """
        report = {"created": 0, "sent": 0, "purged": 0, "alerts": 0}
        interval = await self.settings.get_int("backup_interval_hours", 12)

        if interval > 0 and await self._is_due(interval):
            try:
                await self.create(None, backup_type=BackupType.SCHEDULED, reason="جدولة تلقائية")
                report["created"] = 1
            except BackupBusyError:
                logger.info("نسخة يدوية قيد الإنشاء — تأجيل الجدولة للجولة القادمة")
            except BackupError as exc:
                logger.error("فشل النسخ المجدول: %s", exc)

        report["sent"] = await self._ensure_latest_delivered(bot)
        report["purged"] = await self.enforce_retention()
        report["alerts"] = await self._alert_if_unhealthy(interval)
        return report

    async def _is_due(self, interval_hours: int) -> bool:
        """هل حان موعد نسخة مجدولة؟ (مع تهدئة بعد الفشل)."""
        cooldown_since = to_iso(utc_now() - timedelta(minutes=RETRY_AFTER_FAILURE_MINUTES))
        if await self.repos.backups.latest_failure_after(cooldown_since) is not None:
            return False
        last = await self._latest_relevant_ok()
        if last is None:
            return True
        age = self._age_hours(last["created_at"])
        return age is None or age >= interval_hours

    async def _ensure_latest_delivered(self, bot: Any) -> int:
        """
        إرسال أحدث نسخة سليمة للقناة إن لم تُرسل (نسخة جديدة، أو إصلاح قناة كانت معطّلة).

        فشل الإرسال لا يُسقط النسخة (هي سليمة محلياً) بل يُسجَّل ويُنبَّه الأدمن.
        المخرجات: 1 إن أُرسلت نسخة، 0 خلاف ذلك.
        """
        if self.channel_id is None or not await self.settings.get_bool("backup_send_to_channel", True):
            return 0
        row = await self._latest_relevant_ok()
        if row is None or row.get("channel_sent_at"):
            return 0
        try:
            await self.send_to_channel(None, bot, int(row["id"]))
            return 1
        except Exception as exc:                                  # noqa: BLE001
            # شبكة/صلاحيات قناة/حجم: لا نُسقط الجولة، ونُنبّه الأدمن مرة يومياً
            logger.error("تعذّر إرسال النسخة %s للقناة: %s", row["filename"], sanitize(str(exc)))
            await self._notify_admins(
                token=f"backup-channel:{utc_now().strftime('%Y%m%d')}",
                title="⚠️ تعذّر إرسال النسخة للقناة",
                message=(
                    "النسخة محفوظة على السيرفر لكن إرسالها لقناة النسخ فشل.\n"
                    f"السبب: {sanitize(str(exc))[:200]}\n"
                    "تأكد أن البوت مشرف في القناة وأن BACKUP_CHANNEL_ID صحيح."
                ),
            )
            return 0

    async def _alert_if_unhealthy(self, interval_hours: int) -> int:
        """تنبيه (مرة يومياً) إن فشل النسخ أو تأخر عن موعده."""
        problems: list[str] = []
        since = to_iso(utc_now() - timedelta(hours=24))
        failure = await self.repos.backups.latest_failure_after(since)
        if failure is not None:
            problems.append(f"آخر محاولة فشلت: {sanitize(failure.get('error_text') or '—')[:160]}")
        if interval_hours > 0:
            last = await self._latest_relevant_ok()
            age = self._age_hours(last["created_at"]) if last else None
            if self._is_overdue(interval_hours, age):
                problems.append("لا توجد نسخة سليمة حديثة (النسخ التلقائي متأخر عن موعده)")
        if not problems:
            return 0
        return await self._notify_admins(
            token=f"backup-health:{utc_now().strftime('%Y%m%d')}",
            title="🚨 تحذير: النسخ الاحتياطي",
            message="\n".join(f"• {item}" for item in problems) + "\n\nافتح: لوحة التحكم ← 💾 النسخ الاحتياطي",
        )

    async def _notify_admins(self, *, token: str, title: str, message: str) -> int:
        """إدراج تنبيه لمن يملك `backup.create` (مرة لكل رمز، فلا تكرار)."""
        async with self.db.transaction() as tx:
            return await self.notifications.notify_admins(
                tx, permission=Permission.BACKUP_CREATE, token=token, title=title, message=message
            )

    # ------------------------------- ضغط القاعدة ------------------------------- #

    async def vacuum(self, actor: User) -> tuple[int, int, BackupInfo]:
        """
        ضغط ملف القاعدة (`VACUUM`) بعد نسخة أمان إلزامية.

        يقفل الكتابة طوال العملية (ثوانٍ لقواعد صغيرة)، لذلك لا يجري تلقائياً أبداً.
        المخرجات: (الحجم قبل، الحجم بعد، نسخة الأمان).

        الاستثناءات: PermissionDeniedError · BackupError (فشل نسخة الأمان يلغي الضغط).
        """
        await self._require(actor, Permission.BACKUP_CREATE, context="backup.vacuum")
        safety = await self.create(actor, backup_type=BackupType.PRE_OPERATION, reason="قبل ضغط القاعدة VACUUM")

        try:
            await self.db.execute_raw("PRAGMA wal_checkpoint(TRUNCATE)")   # حجم «قبل» الحقيقي بلا ذيل WAL
        except Exception as exc:                                  # noqa: BLE001
            logger.exception("فشل checkpoint قبل VACUUM")
            raise BackupError(f"فشل تفريغ سجل WAL: {sanitize(str(exc))[:200]}") from exc
        before = self.db.path.stat().st_size
        needed = before + 20 * 1024 * 1024
        if free_disk_bytes(self.db.path.parent) < needed:
            raise BackupError(
                "مساحة غير كافية للضغط",
                user_message="❌ مساحة القرص غير كافية لعملية الضغط (تحتاج مساحة بحجم القاعدة تقريباً).",
            )
        try:
            await self.db.execute_raw("VACUUM")
            await self.db.execute_raw("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception as exc:                                  # noqa: BLE001
            logger.exception("فشل VACUUM")
            raise BackupError(f"فشل ضغط القاعدة: {sanitize(str(exc))[:200]}") from exc
        after = self.db.path.stat().st_size
        await self.audit.log_standalone(
            action="backup.vacuum",
            admin_id=actor.id,
            target_type="database",
            details={"before_bytes": before, "after_bytes": after, "safety_backup_id": safety.id},
            source="telegram",
        )
        return before, after, safety
