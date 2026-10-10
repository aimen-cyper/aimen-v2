"""
إنشاء أو ترقية حساب إداري من سطر الأوامر.

الاستخدام (من مجلد المشروع):
    python -m scripts.create_admin 123456789 admin
    python -m scripts.create_admin 123456789 support
    python -m scripts.create_admin 123456789 user        # تنزيل الصلاحيات
    python -m scripts.create_admin 123456789 user --force  # تنزيل آخر أدمن أعلى (خطِر)

الفائدة: التعافي عند فقدان الوصول للوحة، أو إعداد فريق العمل قبل تشغيل البوت.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from config import Config, ConfigError
from core.enums import Role
from database.database import Database
from database.repositories import Repositories
from utils.fs_security import check_paths
from utils.logging_setup import setup_logging

VALID_ROLES = {str(role) for role in Role}


async def run(telegram_id: int, role: str, *, force: bool = False) -> int:
    """
    تنفيذ إنشاء/ترقية الحساب وإرجاع كود الخروج.

    حمايتان (المرحلة 9):
        • معرّف تيليجرام للأشخاص عدد موجب (السالب/الصفر خطأ إدخال).
        • لا يُنزَّل **آخر أدمن أعلى فعّال** إلا بـ`--force`، وإلا فقد النظام كل من
          يملك صلاحية الأمان وإدارة الأدوار ولا يعود إلا بسكربت طوارئ.
    """
    if telegram_id <= 0:
        print("❌ معرّف تيليجرام يجب أن يكون عدداً موجباً.")
        return 2
    if role not in VALID_ROLES:
        print(f"❌ دور غير معروف: {role} — الأدوار المتاحة: {', '.join(sorted(VALID_ROLES))}")
        return 2

    try:
        config = Config.load()
    except ConfigError as exc:
        print(f"❌ خطأ في الإعدادات: {exc}")
        return 2

    if os.name == "posix":
        os.umask(0o077)                     # ملفات خاصة بالمالك من لحظة إنشائها
    config.ensure_directories()
    setup_logging(config.log_file, config.log_level, console=False)

    db = Database(config.database_path)
    await db.connect()
    try:
        repos = Repositories(db)
        user = await repos.users.get_by_telegram_id(telegram_id)
        if user is not None and user.role == Role.SUPER_ADMIN and role != Role.SUPER_ADMIN and not force:
            supers = [
                item for item in await repos.users.list_by_role(str(Role.SUPER_ADMIN))
                if not item.is_banned
            ]
            if len(supers) <= 1:
                print("❌ هذا آخر أدمن أعلى فعّال — تنزيله يقفل لوحة الإدارة. أضف أدمن أعلى آخر أولاً، أو استعمل --force إن كنت متأكداً.")
                return 1
        async with db.transaction() as tx:
            if user is None:
                user = await repos.users.create(tx, telegram_id=telegram_id, role=role)
                await repos.audit.log(
                    tx, action="admin.create_via_script", target_type="user", target_id=user.id,
                    after={"role": role}, source="script",
                )
                print(f"✅ تم إنشاء المستخدم {telegram_id} بالدور: {role}")
            else:
                old_role = user.role
                await repos.users.set_role(tx, user.id, role)
                await repos.audit.log(
                    tx, action="admin.role_change_via_script", target_type="user", target_id=user.id,
                    before={"role": old_role}, after={"role": role}, source="script",
                )
                print(f"✅ تم تغيير دور المستخدم {telegram_id} من {old_role} إلى {role}")

        permissions = await repos.rbac.effective_permissions(user.id, role)
        print(f"🔐 عدد الصلاحيات الفعلية: {len(permissions)}")
        for item in check_paths(config.sensitive_paths(), fix=True):
            if item.insecure:
                print(f"⚠️ {item.label}: صلاحية {item.mode_text} مفتوحة لغير المالك {item.note}")
        return 0
    finally:
        await db.close()


def main() -> int:
    """نقطة الدخول: قراءة الوسائط وتشغيل العملية."""
    parser = argparse.ArgumentParser(description="إنشاء أو ترقية حساب إداري")
    parser.add_argument("telegram_id", type=int, help="معرف تيليجرام الرقمي")
    parser.add_argument(
        "role", nargs="?", default=str(Role.ADMIN), help="الدور: user / support / admin / super_admin"
    )
    parser.add_argument("--force", action="store_true", help="السماح بتنزيل آخر أدمن أعلى")
    args = parser.parse_args()
    return asyncio.run(run(args.telegram_id, args.role, force=args.force))


if __name__ == "__main__":
    sys.exit(main())
