"""اختبارات النسخ الاحتياطي (المرحلة 10): الخدمة، الجدولة، الاحتفاظ، الكتالوج، الشاشات، والاستعادة."""

from __future__ import annotations

import gzip
import sqlite3
import stat
from datetime import timedelta
from pathlib import Path

import pytest

from core.exceptions import BackupBusyError, BackupError, PermissionDeniedError, ValidationError
from core.permissions import Permission
from database.database import Database
from database.repositories import Repositories
from handlers.admin import backup as backup_handlers
from keyboards.admin_kb import admin_menu_kb
from keyboards.callback_data import NS_ADM_BKP, pack
from services import build_services
from tests.integration.test_user_interface import bot, context, load_user, press  # noqa: F401
from tests.telegram_fakes import FakeBot
from utils import backup_files
from utils.datetime_utils import to_iso, utc_now

pytestmark = pytest.mark.asyncio

CHANNEL_ID = -1001234567890


@pytest.fixture
def backup_dir(db: Database) -> Path:
    """مجلد النسخ الذي تستعمله خدمة الاختبار (بجوار ملف القاعدة المؤقت)."""
    return db.path.parent / "backups"


@pytest.fixture
def with_channel(db, repos, secret_box, tmp_path):
    """حاوية خدمات بقناة نسخ مضبوطة (القناة وهمية: `FakeBot` يسجّل الإرسال)."""
    return build_services(
        db, repos, secret_box=secret_box, settings_ttl_seconds=0, backup_channel_id=CHANNEL_ID, app_version="t"
    )


def _read_gz_db(path: Path, tmp_path: Path) -> sqlite3.Connection:
    """فك نسخة مضغوطة إلى ملف مؤقت وفتحها للقراءة."""
    target = tmp_path / "unpacked.db"
    target.write_bytes(gzip.decompress(path.read_bytes()))
    return sqlite3.connect(target)


# ================================ إنشاء النسخة ================================ #


async def test_create_makes_verified_private_gz_with_sidecar(services, super_admin, backup_dir, tmp_path) -> None:
    """النسخة اليدوية: ملف مضغوط سليم + ملف جانبي + صلاحية المالك فقط + محتوى القاعدة نفسه."""
    info = await services.backups.create(super_admin, reason="اختبار")
    path = backup_dir / info.filename
    assert info.is_ok and info.type == "manual" and info.sha256
    assert path.is_file() and backup_files.sidecar_path(path).is_file()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert backup_files.sha256_file(path) == info.sha256
    connection = _read_gz_db(path, tmp_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        connection.close()


async def test_create_is_audited(services, db, super_admin) -> None:
    """إنشاء النسخة يُدوَّن في سجل التدقيق باسم المنفِّذ."""
    info = await services.backups.create(super_admin)
    row = await db.fetchone("SELECT admin_id, target_id FROM audit_logs WHERE action = 'backup.create'")
    assert row["admin_id"] == super_admin.id and str(row["target_id"]) == str(info.id)


async def test_create_requires_permission(services, user, admin, backup_dir) -> None:
    """العميل والأدمن العادي (بلا backup.create) لا ينشئان نسخة، ولا يُكتب ملف."""
    for actor in (user, admin):
        with pytest.raises(PermissionDeniedError):
            await services.backups.create(actor)
    assert not list(backup_files.list_backup_files(backup_dir))


async def test_two_backups_same_second_get_distinct_files(services, super_admin) -> None:
    """نسختان متتاليتان لا تكتب إحداهما فوق الأخرى حتى في الثانية نفسها."""
    first = await services.backups.create(super_admin)
    second = await services.backups.create(super_admin)
    assert first.filename != second.filename


async def test_concurrent_create_is_rejected_as_busy(services, super_admin) -> None:
    """طلب نسخة أثناء نسخة قيد الإنشاء يُرفض برسالة «مشغول» بدل نسختين متزامنتين."""
    async with services.backups._lock:
        with pytest.raises(BackupBusyError):
            await services.backups.create(super_admin)


async def test_insufficient_disk_records_failed_row(services, super_admin, monkeypatch) -> None:
    """نقص المساحة يفشل النسخ بوضوح ويُسجَّل صف `failed` لا يُحتسب «سليماً»."""
    monkeypatch.setattr("services.backup_service.free_disk_bytes", lambda _p: 0)
    with pytest.raises(BackupError):
        await services.backups.create(super_admin)
    summary = await services.backups.build_summary()
    assert summary.last_ok is None and summary.bad_count == 1
    failures = await services.repos.backups.latest_failure_after(to_iso(utc_now() - timedelta(minutes=5)))
    assert failures is not None and failures["error_text"]


# ================================ الفحص والتلف ================================ #


async def test_verify_ok_then_detects_tamper_and_missing(services, super_admin, backup_dir) -> None:
    """الفحص: سليمة ← ok؛ بعد العبث ← corrupt؛ بعد حذف الملف ← missing؛ ولا تُحتسب كآخر سليمة."""
    info = await services.backups.create(super_admin)
    assert (await services.backups.verify(super_admin, info.id)).ok

    path = backup_dir / info.filename
    path.write_bytes(path.read_bytes() + b"tamper")
    bad = await services.backups.verify(super_admin, info.id)
    assert not bad.ok and bad.status == "corrupt"
    assert (await services.backups.build_summary()).last_ok is None

    other = await services.backups.create(super_admin)
    (backup_dir / other.filename).unlink()
    gone = await services.backups.verify(super_admin, other.id)
    assert gone.status == "missing"


async def test_verify_unknown_id_is_validation_error(services, super_admin) -> None:
    """رقم نسخة غير موجود يرفع خطأ تحقق (لا استثناء خام)."""
    with pytest.raises(ValidationError):
        await services.backups.verify(super_admin, 9999)


# ================================ الأمان والمسارات ================================ #


@pytest.mark.parametrize(
    "name",
    ["../../etc/passwd", "smm_backup_20260101_000000_manual.db.gz/../x", "evil.db.gz", "/abs/smm_backup_20260101_000000_manual.db.gz"],
)
def test_safe_backup_path_rejects_traversal(tmp_path: Path, name: str) -> None:
    """أي اسم خارج الصيغة المعتمدة أو يخرج من المجلد يُرفض."""
    with pytest.raises(BackupError):
        backup_files.safe_backup_path(tmp_path, name)


async def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    """رابط رمزي باسم صحيح يشير خارج مجلد النسخ يُرفض."""
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"x")
    folder = tmp_path / "b"
    folder.mkdir()
    link = folder / "smm_backup_20260101_000000_manual.db.gz"
    link.symlink_to(outside)
    with pytest.raises(BackupError):
        backup_files.safe_backup_path(folder, link.name)


def test_inspect_sqlite_rejects_garbage_and_incomplete(tmp_path: Path) -> None:
    """ملف عشوائي أو قاعدة ناقصة الجداول ليست «قابلة للاستعادة»."""
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"not a database at all" * 50)
    assert not backup_files.inspect_sqlite(junk).is_restorable
    partial = tmp_path / "partial.db"
    connection = sqlite3.connect(partial)
    connection.execute("CREATE TABLE users (id INTEGER)")
    connection.commit()
    connection.close()
    check = backup_files.inspect_sqlite(partial)
    assert check.integrity_ok and not check.is_restorable and "orders" in check.missing_tables


def test_gunzip_enforces_size_cap(tmp_path: Path) -> None:
    """قنبلة ضغط تتجاوز السقف تُقطع بخطأ ولا تملأ القرص."""
    source = tmp_path / "bomb.gz"
    source.write_bytes(gzip.compress(b"\0" * 200_000))
    with pytest.raises(BackupError):
        backup_files.gunzip_file(source, tmp_path / "out", max_bytes=10_000)


# ================================ الجدولة ================================ #


async def test_run_scheduled_creates_when_none_then_waits(services, super_admin) -> None:
    """لا نسخة ⇒ تُنشأ مجدولة؛ الجولة التالية مباشرة لا تنشئ أخرى."""
    first = await services.backups.run_scheduled(FakeBot())
    assert first["created"] == 1
    second = await services.backups.run_scheduled(FakeBot())
    assert second["created"] == 0
    assert (await services.backups.build_summary()).ok_count == 1


async def test_scheduled_due_after_interval(services, db, super_admin) -> None:
    """بعد مرور الفاصل على آخر نسخة سليمة تُنشأ نسخة جديدة."""
    await services.backups.run_scheduled(FakeBot())
    old = to_iso(utc_now() - timedelta(hours=13))
    await db.execute_raw("UPDATE backups SET created_at = ?", (old,))
    assert (await services.backups.run_scheduled(FakeBot()))["created"] == 1


async def test_interval_zero_disables_auto(services, super_admin) -> None:
    """الفاصل 0 يعطّل النسخ التلقائي (والمنطق الآخر يعمل)."""
    await services.settings.set("backup_interval_hours", "0", admin_id=super_admin.id)
    report = await services.backups.run_scheduled(FakeBot())
    assert report["created"] == 0
    assert not (await services.backups.build_summary()).auto_enabled


async def test_manual_backup_postpones_schedule_but_pre_operation_does_not(services, super_admin) -> None:
    """النسخة اليدوية الحديثة تؤجّل المجدولة، أما نسخ ما قبل العمليات فلا."""
    await services.backups.create(super_admin, backup_type="pre_operation")
    assert (await services.backups.run_scheduled(FakeBot()))["created"] == 1
    # الآن توجد مجدولة حديثة ⇒ لا تُنشأ أخرى
    assert (await services.backups.run_scheduled(FakeBot()))["created"] == 0


async def test_failure_cooldown_prevents_hammering(services, super_admin, monkeypatch) -> None:
    """بعد فشل النسخ المجدول لا نعيد المحاولة كل جولة (تهدئة)، وتصل رسالة تنبيه للأدمن مرة."""
    monkeypatch.setattr("services.backup_service.free_disk_bytes", lambda _p: 0)
    first = await services.backups.run_scheduled(FakeBot())
    assert first["created"] == 0
    failures_before = (await services.backups.build_summary()).bad_count
    await services.backups.run_scheduled(FakeBot())
    assert (await services.backups.build_summary()).bad_count == failures_before     # لا محاولة جديدة
    alerts = await services.repos.notifications.count_queued()
    await services.backups.run_scheduled(FakeBot())
    assert await services.repos.notifications.count_queued() == alerts               # لا تكرار يومي


# ================================ القناة الخارجية ================================ #


async def test_channel_send_marks_row_and_uses_protected_content(with_channel, super_admin) -> None:
    """الإرسال للقناة: ملف + تعليق + protect_content، ويُسجَّل رقم الرسالة ووقتها."""
    fake = FakeBot()
    info = await with_channel.backups.create(super_admin)
    sent = await with_channel.backups.send_to_channel(super_admin, fake, info.id)
    assert sent.sent_to_channel and sent.channel_message_id
    document = fake.sent[-1]
    assert document.kind == "document" and document.chat_id == CHANNEL_ID
    assert document.kwargs["protect_content"] is True
    assert info.filename in str(document.kwargs.get("filename"))


async def test_channel_not_configured_is_clear_error(services, super_admin) -> None:
    """بلا BACKUP_CHANNEL_ID يُرفض الإرسال برسالة واضحة."""
    info = await services.backups.create(super_admin)
    with pytest.raises(BackupError) as caught:
        await services.backups.send_to_channel(super_admin, FakeBot(), info.id)
    assert "BACKUP_CHANNEL_ID" in caught.value.user_message


async def test_scheduled_round_sends_latest_once(with_channel, super_admin) -> None:
    """الجولة الدورية ترسل أحدث نسخة مرة واحدة فقط."""
    fake = FakeBot()
    first = await with_channel.backups.run_scheduled(fake)
    assert first["created"] == 1 and first["sent"] == 1
    second = await with_channel.backups.run_scheduled(fake)
    assert second["sent"] == 0
    assert len([m for m in fake.sent if m.kind == "document"]) == 1


async def test_channel_failure_keeps_backup_and_retries_next_round(with_channel, super_admin) -> None:
    """فشل الإرسال لا يُفشل النسخة، ويُعاد في الجولة التالية بعد إصلاح القناة."""

    class BrokenBot(FakeBot):
        async def send_document(self, *args, **kwargs):  # type: ignore[override]
            from telegram.error import TelegramError

            raise TelegramError("Forbidden: bot is not a member of the channel chat")

    first = await with_channel.backups.run_scheduled(BrokenBot())
    assert first["created"] == 1 and first["sent"] == 0
    summary = await with_channel.backups.build_summary()
    assert summary.ok_count == 1 and summary.last_ok is not None and not summary.last_ok.sent_to_channel
    healed = await with_channel.backups.run_scheduled(FakeBot())
    assert healed["sent"] == 1


async def test_send_to_channel_disabled_by_setting(with_channel, super_admin) -> None:
    """تعطيل `backup_send_to_channel` يوقف الإرسال التلقائي."""
    await with_channel.settings.set("backup_send_to_channel", "false", admin_id=super_admin.id)
    fake = FakeBot()
    report = await with_channel.backups.run_scheduled(fake)
    assert report["created"] == 1 and report["sent"] == 0 and not fake.sent


async def test_channel_send_requires_download_permission(with_channel, super_admin, admin) -> None:
    """الإرسال/التنزيل يتطلبان backup.download."""
    info = await with_channel.backups.create(super_admin)
    with pytest.raises(PermissionDeniedError):
        await with_channel.backups.send_to_channel(admin, FakeBot(), info.id)
    with pytest.raises(PermissionDeniedError):
        await with_channel.backups.download(admin, FakeBot(), info.id, chat_id=1)


async def test_download_sends_to_admin_chat_and_is_audited(services, db, super_admin) -> None:
    """التنزيل يرسل الملف لمحادثة الأدمن ويُدقَّق."""
    fake = FakeBot()
    info = await services.backups.create(super_admin)
    await services.backups.download(super_admin, fake, info.id, chat_id=555)
    assert fake.sent[-1].kind == "document" and fake.sent[-1].chat_id == 555
    row = await db.fetchone("SELECT admin_id FROM audit_logs WHERE action = 'backup.download'")
    assert row["admin_id"] == super_admin.id


async def test_corrupt_backup_cannot_be_sent(with_channel, super_admin, backup_dir) -> None:
    """نسخة تالفة لا تُرسل أبداً (تُفحص قبل الرفع)."""
    info = await with_channel.backups.create(super_admin)
    path = backup_dir / info.filename
    path.write_bytes(path.read_bytes()[:-8] + b"XXXXXXXX")
    with pytest.raises(BackupError):
        await with_channel.backups.send_to_channel(super_admin, FakeBot(), info.id)


# ================================ الاحتفاظ والكتالوج ================================ #


async def _age_all(db: Database, days: int) -> None:
    """إرجاع تاريخ كل النسخ للوراء (لاختبار سياسة الاحتفاظ)."""
    await db.execute_raw("UPDATE backups SET created_at = ?", (to_iso(utc_now() - timedelta(days=days)),))


async def test_retention_purges_old_but_keeps_min_and_history(services, db, super_admin, backup_dir) -> None:
    """الاحتفاظ يحذف ملفات الأقدم من المدة فقط، ويحمي أحدث `backup_min_keep`، ويُبقي السجل `purged`."""
    await services.settings.set("backup_min_keep", "2", admin_id=super_admin.id)
    infos = [await services.backups.create(super_admin) for _ in range(5)]
    await _age_all(db, 60)                                          # كلها أقدم من مدة الاحتفاظ (14 يوماً)
    assert await services.backups.enforce_retention() == 3
    rows = {i.id: await services.repos.backups.get(i.id) for i in infos}
    statuses = sorted(r["status"] for r in rows.values())
    assert statuses == ["ok", "ok", "purged", "purged", "purged"]
    for row in rows.values():
        exists = (backup_dir / row["filename"]).exists()
        assert exists == (row["status"] == "ok")                    # الملف يُحذف مع purged فقط
    assert await services.repos.backups.get(infos[0].id) is not None


async def test_retention_never_deletes_below_min_when_some_are_bad(services, db, super_admin, backup_dir) -> None:
    """التالفة لا تُحتسب ضمن الحد الأدنى: إن لم تبقَ سليمة كافية لا يُحذف شيء من السليمة."""
    await services.settings.set("backup_min_keep", "5", admin_id=super_admin.id)
    for _ in range(3):
        await services.backups.create(super_admin)
    await _age_all(db, 90)
    assert await services.backups.enforce_retention() == 0


async def test_sync_catalog_imports_orphans_and_flags_missing(services, db, super_admin, backup_dir) -> None:
    """مزامنة الكتالوج: ملف يتيم بملف جانبي مطابق يُستورد، وسجل بلا ملف يصير `missing`."""
    kept = await services.backups.create(super_admin)
    lost = await services.backups.create(super_admin)
    (backup_dir / lost.filename).unlink()

    # إخفاء السجل الأول من الكتالوج ليصبح ملفه «يتيماً»
    await db.execute_raw("DELETE FROM backups WHERE id = ?", (kept.id,))
    result = await services.backups.sync_catalog()
    assert result == {"imported": 1, "missing": 1}
    again = await services.backups.sync_catalog()
    assert again == {"imported": 0, "missing": 0}                   # لا تكرار
    row = await services.repos.backups.get_by_filename(kept.filename)
    assert row is not None and row["status"] == "ok"
    assert (await services.repos.backups.get(lost.id))["status"] == "missing"


async def test_sync_catalog_orphan_without_sidecar_is_marked_corrupt(services, backup_dir, super_admin) -> None:
    """ملف يتيم بلا ملف جانبي لا نثق به ⇒ يُسجَّل `corrupt` مع ملاحظة (لا `ok` مختلق)."""
    info = await services.backups.create(super_admin)
    path = backup_dir / info.filename
    renamed = backup_dir / "smm_backup_20200101_000000_manual.db.gz"
    path.rename(renamed)
    backup_files.sidecar_path(path).unlink()
    await services.backups.sync_catalog()
    row = await services.repos.backups.get_by_filename(renamed.name)
    assert row is not None and row["status"] == "corrupt" and row["error_text"]


# ================================ الضغط (VACUUM) ================================ #


async def test_vacuum_takes_safety_backup_first(services, super_admin, db) -> None:
    """الضغط يأخذ نسخة أمان `pre_operation` أولاً ويُدقَّق، والقاعدة تبقى سليمة بعده."""
    before, after, safety = await services.backups.vacuum(super_admin)
    assert safety.type == "pre_operation" and safety.is_ok
    assert before > 0 and after > 0
    assert await db.integrity_check()
    row = await db.fetchone("SELECT details_json FROM audit_logs WHERE action = 'backup.vacuum'")
    assert row is not None


async def test_vacuum_aborts_when_safety_backup_fails(services, super_admin, monkeypatch) -> None:
    """فشل نسخة الأمان يلغي الضغط."""
    monkeypatch.setattr("services.backup_service.free_disk_bytes", lambda _p: 0)
    with pytest.raises(BackupError):
        await services.backups.vacuum(super_admin)


# ================================ فحوص الأمان والصحة ================================ #


async def test_posture_reports_backup_state(services, super_admin) -> None:
    """فحوص الأمان تعرض حالة النسخ ونسخة خارج السيرفر دون اختلاق «سليم»."""
    from services.security_service import LEVEL_OK, LEVEL_WARN, EnvPosture

    checks = {c.title: c for c in await services.security.posture(super_admin, EnvPosture())}
    assert checks["النسخ الاحتياطي"].level == LEVEL_WARN          # لا نسخة بعد
    assert checks["نسخة خارج السيرفر"].level == LEVEL_WARN        # لا قناة
    await services.backups.create(super_admin)
    checks = {c.title: c for c in await services.security.posture(super_admin, EnvPosture())}
    assert checks["النسخ الاحتياطي"].level == LEVEL_OK


async def test_health_text_mentions_last_backup(services, super_admin) -> None:
    """شاشة صحة النظام تعرض آخر نسخة سليمة (أو تنبّه لغيابها)."""
    assert "لا توجد نسخة" in await services.stats.health_text(super_admin)
    await services.backups.create(super_admin)
    assert "آخر نسخة سليمة" in await services.stats.health_text(super_admin)


# ================================ الشاشات ================================ #


async def test_menu_shows_backup_button_only_with_permission(services, super_admin, admin, user) -> None:
    """زر القسم يظهر لمن يملك backup.create فقط."""
    target = pack(NS_ADM_BKP, "home")
    for person, expected in ((super_admin, True), (admin, False)):
        perms = await services.auth.permissions_of(person)
        callbacks = [b.callback_data for row in admin_menu_kb(perms).inline_keyboard for b in row]
        assert (target in callbacks) is expected


async def test_home_screen_renders_and_new_backup_button_works(bot, context, services, super_admin) -> None:  # noqa: F811
    """الشاشة الرئيسية تعرض الحالة، وزر «نسخة الآن» ينشئ نسخة فعلاً ويعرض نتيجتها."""
    await load_user(bot, context, super_admin)
    await press(bot, context, backup_handlers.home_screen, "bk:home", super_admin.telegram_id)
    assert "النسخ الاحتياطي" in bot.last.text and "لا شيء بعد" in bot.last.text
    await press(bot, context, backup_handlers.new_backup, "bk:new", super_admin.telegram_id)
    assert "تم إنشاء النسخة" in bot.last.text
    assert (await services.backups.build_summary()).ok_count == 1


async def test_all_screens_denied_without_permission(bot, context, services, user, admin) -> None:  # noqa: F811
    """العميل العادي والأدمن بلا الصلاحية لا يرون أي شاشة ولا ينفّذون أي إجراء."""
    for person in (user, admin):
        await load_user(bot, context, person)
        for action, handler in (
            ("home", backup_handlers.home_screen),
            ("new", backup_handlers.new_backup),
            ("list:1", backup_handlers.list_screen),
            ("view:1:1", backup_handlers.view_screen),
            ("verify:1:1", backup_handlers.verify_action),
            ("chan:1:1", backup_handlers.channel_action),
            ("dlask:1:1", backup_handlers.download_ask),
            ("dl:1:1", backup_handlers.download_action),
            ("vacask", backup_handlers.vacuum_ask),
            ("vac", backup_handlers.vacuum_action),
            ("guide", backup_handlers.guide_screen),
        ):
            bot.clear()
            await press(bot, context, handler, f"bk:{action}", person.telegram_id)
            assert not bot.sent, f"{action} عُرضت لمن لا يملك الصلاحية"
    assert not list(backup_files.list_backup_files(services.backups.backup_dir))


async def test_list_view_verify_flow(bot, context, services, super_admin) -> None:  # noqa: F811
    """سجل النسخ ← تفاصيل ← فحص: كلها تعمل وتعرض الحالة الصحيحة."""
    info = await services.backups.create(super_admin)
    await load_user(bot, context, super_admin)
    await press(bot, context, backup_handlers.list_screen, "bk:list:1", super_admin.telegram_id)
    assert f"#{info.id}" in bot.last.text
    assert pack(NS_ADM_BKP, "view", info.id, 1) in bot.last.buttons
    await press(bot, context, backup_handlers.view_screen, f"bk:view:{info.id}:1", super_admin.telegram_id)
    assert info.filename in bot.last.text
    await press(bot, context, backup_handlers.verify_action, f"bk:verify:{info.id}:1", super_admin.telegram_id)
    assert "الفحص ناجح" in bot.last.text


async def test_list_page_out_of_range_falls_back(bot, context, services, super_admin) -> None:  # noqa: F811
    """صفحة خارج النطاق لا تعرض قائمة فارغة خاطئة."""
    await services.backups.create(super_admin)
    await load_user(bot, context, super_admin)
    await press(bot, context, backup_handlers.list_screen, "bk:list:99", super_admin.telegram_id)
    assert "#1" in bot.last.text


async def test_download_requires_second_confirmation(bot, context, services, super_admin) -> None:  # noqa: F811
    """التنزيل: شاشة التأكيد لا ترسل الملف، والزر الثاني فقط يرسله."""
    info = await services.backups.create(super_admin)
    await load_user(bot, context, super_admin)
    await press(bot, context, backup_handlers.download_ask, f"bk:dlask:{info.id}:1", super_admin.telegram_id)
    assert not [m for m in bot.sent if m.kind == "document"]
    assert pack(NS_ADM_BKP, "dl", info.id, 1) in bot.last.buttons
    await press(bot, context, backup_handlers.download_action, f"bk:dl:{info.id}:1", super_admin.telegram_id)
    assert [m for m in bot.sent if m.kind == "document"]


async def test_vacuum_requires_second_confirmation(bot, context, services, super_admin) -> None:  # noqa: F811
    """الضغط: شاشة التأكيد لا تضغط ولا تنسخ، والزر الثاني ينفّذ ويعرض الحجم قبل/بعد."""
    await load_user(bot, context, super_admin)
    await press(bot, context, backup_handlers.vacuum_ask, "bk:vacask", super_admin.telegram_id)
    assert (await services.backups.build_summary()).ok_count == 0
    await press(bot, context, backup_handlers.vacuum_action, "bk:vac", super_admin.telegram_id)
    assert "تم الضغط" in bot.last.text and (await services.backups.build_summary()).ok_count == 1


async def test_service_error_surfaces_arabic_message_on_screen(bot, context, services, super_admin) -> None:  # noqa: F811
    """نسخة غير موجودة تُظهر رسالة عربية لا استثناءً خاماً."""
    await load_user(bot, context, super_admin)
    await press(bot, context, backup_handlers.view_screen, "bk:view:777:1", super_admin.telegram_id)
    assert "غير موجودة" in bot.last.text


async def test_guide_screen_has_no_restore_button(bot, context, super_admin) -> None:  # noqa: F811
    """الدليل نص فقط والاستعادة خارج البوت: لا زر استعادة في أي شاشة."""
    await load_user(bot, context, super_admin)
    await press(bot, context, backup_handlers.guide_screen, "bk:guide", super_admin.telegram_id)
    assert "restore_backup" in bot.last.text
    for markup in (backup_handlers.backup_home_kb(), backup_handlers.backup_guide_kb()):
        assert all("restore" not in b.callback_data for row in markup.inline_keyboard for b in row)


def test_permission_constants_cover_handlers() -> None:
    """الصلاحيتان المستعملتان موجودتان وخطِرتان."""
    from core.permissions import is_dangerous_permission

    assert is_dangerous_permission(Permission.BACKUP_DOWNLOAD) and is_dangerous_permission(Permission.BACKUP_CREATE)


def test_backup_buttons_are_sensitive_for_rate_limit() -> None:
    """أزرار النسخ الثقيلة/المُخرِجة للبيانات تخضع للحد الحسّاس."""
    from middlewares.rate_limit import SENSITIVE_ADMIN_ACTIONS

    assert {"new", "dl", "vac", "chan"} <= SENSITIVE_ADMIN_ACTIONS[NS_ADM_BKP]


# ============================ مساعدات تحتاج Repositories ============================ #


async def test_repo_catalog_columns_exist(db: Database, repos: Repositories) -> None:  # noqa: ARG001
    """ترحيل 0009 أضاف أعمدة الكتالوج والإعدادات الجديدة."""
    columns = {row["name"] for row in await db.fetchall("PRAGMA table_info(backups)")}
    assert {"verified_at", "schema_version", "channel_message_id", "channel_sent_at", "error_text"} <= columns
    keys = {row["key"] for row in await db.fetchall("SELECT key FROM settings")}
    assert {"backup_send_to_channel", "backup_min_keep", "export_max_rows"} <= keys
