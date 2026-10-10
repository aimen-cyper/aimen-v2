"""
فحص أمني دون اتصال (المرحلة 9) — يعمل بلا تيليجرام وبلا تعديل بيانات.

يفحص:
    1. الأسرار: وجود التوكن ومفتاح التشفير وصيغتهما (بلا طباعة قيمهما).
    2. صلاحيات الملفات الحسّاسة (.env، القاعدة، النسخ، اللوق) — مع `--fix` لضبطها.
    3. وضع النظام من قاعدة البيانات: الأدمن الأعلى، روابط المزودين، الاستثناءات
       الخطرة، منع التنفيذ الذاتي، سقوف التسوية، حدود الاستخدام، الأخطاء الأخيرة.

طريقة التشغيل (من مجلد المشروع):
    python -m scripts.security_check
    python -m scripts.security_check --fix      # ضبط صلاحيات الملفات تلقائياً

كود الخروج: 0 كل شيء سليم أو تنبيهات فقط · 1 يوجد «خطر» · 2 خطأ في الإعدادات.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:                      # تشغيل مباشر بلا تثبيت الحزمة
    sys.path.insert(0, str(ROOT))

from config import Config, ConfigError                      # noqa: E402
from database.database import Database                      # noqa: E402
from database.repositories import Repositories              # noqa: E402
from services import build_services                         # noqa: E402
from services.security_service import (                     # noqa: E402
    LEVEL_BAD,
    LEVEL_WARN,
    EnvPosture,
)
from utils.fs_security import check_paths                   # noqa: E402
from utils.security import SecretBox, generate_encryption_key  # noqa: E402

ICONS = {"ok": "✅", "warn": "⚠️ ", "bad": "⛔"}


async def run(*, fix: bool) -> int:
    """تنفيذ الفحص وطباعة التقرير وإرجاع كود الخروج."""
    try:
        config = Config.load()
    except ConfigError as exc:
        print(f"⛔ خطأ في الإعدادات: {exc}")
        return 2

    paths = check_paths(config.sensitive_paths(), fix=fix)
    env = EnvPosture(
        bot_token_set=bool(config.bot_token),
        encryption_key_set=bool(config.encryption_key),
        alert_chat_set=config.admin_alert_chat_id is not None,
        path_checks=tuple(paths),
    )

    print("🛡️  فحص الأمان — SMM Bot\n" + "─" * 40)
    for item in paths:
        mark = "✅" if not item.insecure else "⚠️ "
        suffix = " (ضُبطت الآن)" if item.fixed else ""
        print(f"  {mark} {item.label}: {item.mode_text}{suffix} {item.note}".rstrip())
    if not paths:
        print("  ℹ️  لا ملفات حسّاسة موجودة بعد (أو النظام لا يدعم صلاحيات POSIX).")

    if not config.database_path.exists():
        print("\n⚠️  قاعدة البيانات غير موجودة بعد — شغّل: python -m scripts.init_db")
        return 1 if any(item.insecure for item in paths) else 0

    db = Database(config.database_path)
    await db.connect()
    try:
        repos = Repositories(db)
        # صندوق التشفير مطلوب لبناء الخدمات فقط؛ لا يُستخدم هنا لفكّ أي مفتاح
        box = SecretBox(config.encryption_key or generate_encryption_key())
        services = build_services(db, repos, secret_box=box, super_admin_ids=config.super_admin_ids)
        checks = await services.security.run_checks(env)
    finally:
        await db.close()

    print("\n" + "─" * 40)
    for check in checks:
        print(f"  {ICONS.get(check.level, '•')} {check.title}: {check.detail}")

    bad = sum(1 for check in checks if check.level == LEVEL_BAD)
    warn = sum(1 for check in checks if check.level == LEVEL_WARN)
    print("─" * 40)
    print(f"النتيجة: {bad} خطر · {warn} تنبيه · {len(checks) - bad - warn} سليم")
    return 1 if bad else 0


def main() -> int:
    """نقطة الدخول: قراءة الوسائط وتشغيل الفحص."""
    parser = argparse.ArgumentParser(description="فحص أمني دون اتصال")
    parser.add_argument("--fix", action="store_true", help="ضبط صلاحيات الملفات الحسّاسة تلقائياً")
    args = parser.parse_args()
    return asyncio.run(run(fix=args.fix))


if __name__ == "__main__":
    sys.exit(main())
