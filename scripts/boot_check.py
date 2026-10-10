"""
فحص الإقلاع بلا تيليجرام — المرحلة 3.

يتحقق من كل ما يحتاجه البوت قبل أول تشغيل حقيقي، دون إرسال أي طلب لتيليجرام
ودون تعديل أي بيانات:

    1. ملف ‎.env‎ والإعدادات الأساسية.
    2. قاعدة البيانات: الاتصال، إصدار المخطط، الترحيلات الناقصة.
    3. حاوية الخدمات والإعدادات المقروءة منها.
    4. تسجيل المعالجات: العدد والمجموعات.
    5. تغطية الأزرار: كل زر في الواجهة له معالج.
    6. جدولة المهام الدورية وفتراتها الفعلية.

طريقة التشغيل (من داخل مجلد المشروع):
    python -m scripts.boot_check
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:                      # تشغيل مباشر بلا تثبيت الحزمة
    sys.path.insert(0, str(ROOT))

from telegram.ext import ApplicationBuilder, ConversationHandler  # noqa: E402

from config import Config, ConfigError                               # noqa: E402
from core.constants import APP_VERSION                               # noqa: E402
from database.database import Database                               # noqa: E402
from database.migrator import Migrator                               # noqa: E402
from database.repositories import Repositories                       # noqa: E402
from handlers.registry import MAIN_GROUP, MIDDLEWARE_GROUP, build_handlers  # noqa: E402
from jobs import schedule_jobs                                       # noqa: E402
from services import build_services                                  # noqa: E402
from utils.logging_setup import setup_logging                        # noqa: E402
from utils.security import SecretBox, generate_encryption_key        # noqa: E402

LINE = "─" * 62

#: توكن شكلي للفحص المحلي فقط (لا يُستخدم في أي اتصال)
DUMMY_TOKEN = "123456789:AABootCheckDummyTokenNotUsedForNetwork"


def step(number: int, title: str) -> None:
    """طباعة عنوان خطوة من الفحص."""
    print(f"\n{LINE}\n▶ {number}. {title}\n{LINE}")


def ok(label: str, value: object = "") -> None:
    """سطر نجاح."""
    print(f"   ✅ {label} {value}")


def warn(label: str, value: object = "") -> None:
    """سطر تحذير (لا يمنع التشغيل لكنه يحتاج انتباهاً)."""
    print(f"   ⚠️  {label} {value}")


def fail(label: str, value: object = "") -> None:
    """سطر فشل (يمنع التشغيل)."""
    print(f"   ❌ {label} {value}")


async def run_check() -> int:
    """
    تنفيذ كل خطوات الفحص بالترتيب.

    المخرجات: 0 إذا كان النظام جاهزاً للتشغيل، 1 إذا وُجد ما يمنع.
    """
    problems = 0
    print(f"\n🔎 فحص إقلاع SMM Bot — الإصدار {APP_VERSION}")

    # ------------------------------------------------------------------ #
    step(1, "الإعدادات (.env)")
    try:
        config = Config.load(require_bot_token=False)
    except ConfigError as exc:
        fail("تعذر تحميل الإعدادات:", exc)
        return 1

    setup_logging(config.log_file, config.log_level, console=False)
    for key, value in config.safe_summary().items():
        ok(f"{key}:", value)
    if not config.bot_token:
        warn("BOT_TOKEN غير موجود — الفحص يكمل، لكن التشغيل الفعلي يحتاجه.")
        problems += 1
    if not config.super_admin_ids:
        warn("SUPER_ADMIN_IDS فارغ — لن يكون هناك مسار طوارئ للأدمن.")

    # ------------------------------------------------------------------ #
    step(2, "قاعدة البيانات")
    if not config.database_path.exists():
        fail("ملف قاعدة البيانات غير موجود:", config.database_path)
        print("      شغّل أولاً: python -m scripts.init_db")
        return 1

    db = Database(config.database_path)
    await db.connect()
    try:
        migrator = Migrator(db)
        ok("الاتصال بقاعدة البيانات:", config.database_path)
        ok("إصدار المخطط:", await migrator.current_version())
        pending = await migrator.pending()
        if pending:
            warn("ترحيلات ناقصة ستُطبَّق عند التشغيل:", ", ".join(pending))
        else:
            ok("الترحيلات:", "مكتملة")

        # -------------------------------------------------------------- #
        step(3, "الخدمات والإعدادات")
        repos = Repositories(db)
        secret_box = (
            SecretBox(config.encryption_key)
            if config.encryption_key
            else SecretBox(generate_encryption_key())
        )
        if not config.encryption_key:
            warn("ENCRYPTION_KEY غير موجود — استُخدم مفتاح مؤقت للفحص فقط.")
            problems += 1
        services = build_services(
            db, repos, secret_box=secret_box, super_admin_ids=config.super_admin_ids
        )
        ok("اسم البوت:", await services.settings.get_str("bot_name", "SMM Bot"))
        code, symbol, decimals = await services.settings.currency()
        ok("العملة:", f"{code} ({symbol}) بـ{decimals} خانات عشرية")
        ok("وضع الصيانة:", "مفعّل ⚠️" if await services.settings.is_maintenance() else "متوقف")
        ok("التسجيل مفتوح:", "نعم" if await services.settings.registration_enabled() else "لا")
        ok("إشعارات منتظرة في الطابور:", await services.notifications.queued_count())
        active_methods = len(await services.payments.active_methods())
        if active_methods:
            ok("طرق الدفع الفعّالة:", active_methods)
        else:
            # بلا طريقة شحن واحدة مفعّلة لا يستطيع أي مستخدم شحن رصيده إطلاقاً
            warn(
                "لا توجد طريقة شحن مفعّلة — المستخدمون لن يتمكنوا من شحن أرصدتهم. "
                "أضفها من: /admin ← 💰 المدفوعات ← 🏦 طرق الشحن"
            )
            problems += 1
        ok("تصنيفات بها خدمات متاحة:", len(await services.catalog.categories()))

        # -------------------------------------------------------------- #
        step(4, "تسجيل المعالجات")
        handlers = build_handlers()
        middleware = [h for group, h in handlers if group == MIDDLEWARE_GROUP]
        main_group = [h for group, h in handlers if group == MAIN_GROUP]
        conversations = [h for h in main_group if isinstance(h, ConversationHandler)]
        ok("إجمالي المعالجات:", len(handlers))
        ok("الطبقة الوسيطة (مجموعة -10):", len(middleware))
        ok("معالجات المجموعة 0:", len(main_group))
        ok("المحادثات (ConversationHandler):", len(conversations))

        # -------------------------------------------------------------- #
        step(5, "تغطية الأزرار")
        from tests.integration.test_no_dead_buttons import ALL_BUTTONS, registered_patterns

        patterns = registered_patterns()
        dead = [data for data in ALL_BUTTONS if not any(p.search(data) for p in patterns)]
        ok("أزرار الواجهة المفحوصة:", len(ALL_BUTTONS))
        if dead:
            fail("أزرار بلا معالج:", ", ".join(dead))
            problems += 1
        else:
            ok("أزرار بلا معالج:", "لا يوجد")

        # -------------------------------------------------------------- #
        step(6, "المهام الدورية")
        application = ApplicationBuilder().token(DUMMY_TOKEN).build()
        names = await schedule_jobs(application, services)
        for name in names:
            ok("مهمة:", name)
        await application.shutdown()

    finally:
        await db.close()

    print(f"\n{LINE}")
    if problems:
        print(f"⚠️  اكتمل الفحص مع {problems} ملاحظة تحتاج معالجة قبل التشغيل الحقيقي.")
    else:
        print("✅ النظام جاهز للتشغيل: python -m main")
    print(LINE)
    return 1 if problems else 0


def main() -> int:
    """نقطة التشغيل من سطر الأوامر."""
    try:
        return asyncio.run(run_check())
    except KeyboardInterrupt:
        print("\nأُلغي الفحص.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
