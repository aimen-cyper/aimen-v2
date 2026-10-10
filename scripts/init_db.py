"""
تهيئة قاعدة البيانات — أول أمر يُنفَّذ عند تثبيت المشروع.

ما تفعله هذه الأداة:
    1. قراءة الإعدادات من .env وإنشاء المجلدات المطلوبة.
    2. إنشاء ملف قاعدة البيانات وتطبيق كل الترحيلات الناقصة.
    3. التحقق من سلامة المخطط والمفاتيح الأجنبية.
    4. زرع حسابات الأدمن الأعلى المذكورة في SUPER_ADMIN_IDS.
    5. طباعة تقرير واضح بالحالة.

طريقة التشغيل (من مجلد المشروع smm_bot):
    python -m scripts.init_db
    python -m scripts.init_db --gen-key     # توليد مفتاح تشفير جديد فقط
    python -m scripts.init_db --status      # عرض الحالة دون تعديل
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from config import Config, ConfigError
from core.constants import APP_VERSION
from core.exceptions import BackupError
from database.database import Database
from database.migrator import Migrator
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.backup_service import create_backup_file
from services.settings_service import SettingsService
from utils.fs_security import check_paths
from utils.logging_setup import setup_logging
from utils.security import generate_encryption_key

#: الجداول التي يجب أن تكون موجودة بعد التهيئة الكاملة
EXPECTED_TABLES: tuple[str, ...] = (
    "schema_migrations", "roles", "permissions", "role_permissions", "users", "user_permissions",
    "user_states", "providers", "provider_balance_snapshots", "service_categories", "services",
    "service_price_history", "payment_methods", "payments", "orders", "order_status_history",
    "transactions", "support_tickets", "support_messages", "notifications", "audit_logs",
    "settings", "broadcasts", "broadcast_recipients", "idempotency_keys", "provider_requests",
    "error_logs", "backups", "favorites", "channel_outbox",
)


async def seed_super_admins(db: Database, telegram_ids: tuple[int, ...]) -> list[str]:
    """
    إنشاء أو ترقية حسابات الأدمن الأعلى المذكورة في متغير البيئة.

    المخرجات: قائمة رسائل توضح ما تم لكل معرف.
    """
    # المصدر الوحيد: AuthService.bootstrap_super_admins (نفسه الذي يعمل عند إقلاع البوت)
    repos = Repositories(db)
    settings = SettingsService(db, repos)
    auth = AuthService(db, repos, settings, AuditService(db, repos), super_admin_ids=telegram_ids)
    labels = {
        "created": "✅ أُنشئ حساب أدمن أعلى للمعرف {id}",
        "promoted": "⬆️ تمت ترقية المستخدم {id} إلى أدمن أعلى",
        "unbanned": "🔓 رُفع الحظر عن الأدمن الأعلى {id}",
        "promoted_unbanned": "⬆️🔓 تمت ترقية {id} إلى أدمن أعلى ورُفع حظره",
        "unchanged": "ℹ️ المعرف {id} أدمن أعلى بالفعل",
    }
    return [labels[item.action].format(id=item.telegram_id) for item in await auth.bootstrap_super_admins()]


async def verify_schema(db: Database) -> list[str]:
    """التحقق من وجود كل الجداول المتوقعة وسلامة قاعدة البيانات."""
    problems: list[str] = []
    tables = set(await db.table_names())
    missing = [name for name in EXPECTED_TABLES if name not in tables]
    if missing:
        problems.append("جداول ناقصة: " + ", ".join(missing))
    if not await db.integrity_check():
        problems.append("فحص سلامة قاعدة البيانات فشل (integrity_check).")
    violations = await db.foreign_key_check()
    if violations:
        problems.append(f"يوجد {len(violations)} انتهاك للمفاتيح الأجنبية.")
    return problems


async def print_status(db: Database, config: Config) -> None:
    """طباعة ملخص حالة قاعدة البيانات بعد التهيئة."""
    repos = Repositories(db)
    migrator = Migrator(db)
    tables = await db.table_names()
    print("\n📊 حالة النظام")
    print("──────────────────────────────")
    print(f"  ملف قاعدة البيانات : {config.database_path}")
    print(f"  إصدار المخطط        : {await migrator.current_version()}")
    print(f"  عدد الجداول         : {len(tables)}")
    print(f"  الأدوار             : {len(await repos.rbac.list_roles())}")
    print(f"  الصلاحيات           : {len(await repos.rbac.list_permissions())}")
    print(f"  الإعدادات           : {len(await repos.settings.all())}")
    print(f"  التصنيفات           : {len(await repos.categories.list_all())}")
    print(f"  المستخدمون          : {await repos.users.count_all()}")
    print(f"  المزودون            : {len(await repos.providers.list_all())}")
    print(f"  الخدمات             : {await repos.services.count_active()}")
    print(f"  طرق الدفع           : {len(await repos.payment_methods.list_all())}")
    print("──────────────────────────────")


async def run(args: argparse.Namespace) -> int:
    """تنفيذ عملية التهيئة الكاملة وإرجاع كود الخروج."""
    try:
        config = Config.load()
    except ConfigError as exc:
        print(f"❌ خطأ في الإعدادات: {exc}")
        return 2

    if os.name == "posix":
        os.umask(0o077)                     # ملفات خاصة بالمالك من لحظة إنشائها
    config.ensure_directories()
    setup_logging(config.log_file, config.log_level, console=False)

    print("🚀 تهيئة قاعدة بيانات SMM Bot")
    for key, value in config.safe_summary().items():
        print(f"  • {key}: {value}")

    db = Database(config.database_path)
    await db.connect()
    try:
        if args.status:
            await print_status(db, config)
            return 0

        migrator = Migrator(db)
        pending = await migrator.pending()
        if pending:
            print(f"\n⚙️ تطبيق {len(pending)} ترحيل: {', '.join(pending)}")
        if pending and await migrator.applied():
            # ترقية قاعدة قائمة: نسخة أمان أولاً، وفشلها يوقف الترقية
            try:
                artifact = await create_backup_file(
                    db, config.backup_dir, backup_type="pre_operation", app_version=APP_VERSION
                )
            except BackupError as exc:
                print(f"❌ تعذّر أخذ نسخة أمان قبل الترقية: {exc}")
                return 1
            print(f"🛟 نسخة أمان قبل الترقية: {artifact.filename}")
        applied = await migrator.apply_all()
        print("✅ تم تطبيق الترحيلات." if applied else "ℹ️ قاعدة البيانات محدّثة مسبقاً.")

        problems = await verify_schema(db)
        if problems:
            print("\n❌ مشاكل في المخطط:")
            for problem in problems:
                print(f"   - {problem}")
            return 1
        print("✅ فحص المخطط والمفاتيح الأجنبية: سليم.")

        if config.super_admin_ids:
            print("\n👤 حسابات الأدمن الأعلى:")
            for message in await seed_super_admins(db, config.super_admin_ids):
                print(f"   {message}")
        else:
            print("\n⚠️ لم يُحدَّد SUPER_ADMIN_IDS في ملف .env — لن تتمكن من دخول لوحة الأدمن.")

        if not config.encryption_key:
            print("\n⚠️ ENCRYPTION_KEY غير موجود — مطلوب لإضافة المزودين لاحقاً.")
            print(f"   مفتاح مقترح: {generate_encryption_key()}")

        await print_status(db, config)
        remaining = [item for item in check_paths(config.sensitive_paths(), fix=True) if item.insecure]
        for item in remaining:
            print(f"⚠️ {item.label}: صلاحية {item.mode_text} مفتوحة لغير المالك {item.note}")
        print("\n🎉 اكتملت التهيئة بنجاح.")
        return 0
    finally:
        await db.close()


def main() -> int:
    """نقطة الدخول: تحليل الوسائط وتشغيل العملية."""
    parser = argparse.ArgumentParser(description="تهيئة قاعدة بيانات SMM Bot")
    parser.add_argument("--gen-key", action="store_true", help="توليد مفتاح تشفير جديد فقط")
    parser.add_argument("--status", action="store_true", help="عرض حالة قاعدة البيانات دون تعديل")
    args = parser.parse_args()

    if args.gen_key:
        print(generate_encryption_key())
        return 0
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
