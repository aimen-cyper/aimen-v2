"""
نقطة تشغيل البوت.

التسلسل الكامل عند الإقلاع:
    1. تحميل الإعدادات من ‎.env‎ والتحقق من وجود التوكن.
    2. تهيئة اللوق (ملف متدحرج + شاشة).
    3. حجز قفل «نسخة واحدة» حتى لا يعمل بوتان على نفس القاعدة.
    4. فتح قاعدة البيانات، وأخذ نسخة أمان قبل أي ترحيل ناقص على قاعدة قائمة، ثم تطبيقه.
    5. بناء حاوية الخدمات (المنطق كله) وحقنها في `bot_data`.
    6. تسجيل المعالجات (`handlers/registry.py`) والمعالج العام للأخطاء.
    7. استرداد ما علق من تشغيل سابق، ثم جدولة المهام الدورية.
    8. بدء الاستقبال (polling) حتى إشارة إيقاف، ثم إغلاق نظيف.

التشغيل:
    python -m main            # من داخل مجلد المشروع
    python main.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:                       # تشغيل مباشر بلا تثبيت الحزمة
    sys.path.insert(0, str(ROOT))

from telegram import BotCommand, LinkPreviewOptions                  # noqa: E402
from telegram.error import BadRequest, InvalidToken, NetworkError, RetryAfter, TimedOut  # noqa: E402
from telegram.ext import Application, ApplicationBuilder, Defaults  # noqa: E402
from telegram.constants import ParseMode                            # noqa: E402

from config import Config, ConfigError                              # noqa: E402
from core.constants import (                                         # noqa: E402
    APP_VERSION,
    TELEGRAM_CONNECT_TIMEOUT,
    TELEGRAM_POLLING_READ_TIMEOUT,
    TELEGRAM_POOL_TIMEOUT,
    TELEGRAM_READ_TIMEOUT,
    TELEGRAM_WRITE_TIMEOUT,
)
from database.database import Database                              # noqa: E402
from database.migrator import Migrator                              # noqa: E402
from database.repositories import Repositories                      # noqa: E402
from handlers.registry import register_handlers                     # noqa: E402
from jobs import run_startup_recovery, schedule_jobs                # noqa: E402
from services import build_services                                 # noqa: E402
from core.enums import BackupType                                   # noqa: E402
from core.exceptions import BackupError                             # noqa: E402
from services.backup_service import create_backup_file              # noqa: E402
from utils.conflict_guard import EXIT_CODE_CONFLICT, ConflictGuard  # noqa: E402
from utils.fs_security import check_paths                            # noqa: E402
from utils.health_server import HealthServer                         # noqa: E402
from utils.logging_setup import get_logger, setup_logging           # noqa: E402
from utils.security import SecretBox, sanitize                      # noqa: E402
from utils.single_instance import AlreadyRunningError, SingleInstance  # noqa: E402
from utils.telegram_retry import call_telegram                       # noqa: E402

#: فواصل إعادة محاولة نداءات الإقلاع غير الحرجة (ثوانٍ)
STARTUP_RETRY_DELAYS = (1.0, 3.0, 6.0)

logger = get_logger(__name__)

#: أوامر البوت التي تظهر في قائمة تيليجرام
BOT_COMMANDS = [
    BotCommand("start", "🏠 القائمة الرئيسية"),
    BotCommand("help", "📖 التعليمات وطريقة الاستخدام"),
    BotCommand("cancel", "❌ إلغاء العملية الحالية"),
    BotCommand("id", "🆔 عرض معرفي في تيليجرام"),
]


def harden_filesystem(config: Config) -> int:
    """
    ضبط صلاحيات الملفات الحسّاسة (.env، القاعدة، النسخ، اللوقات) وإرجاع عدد المخالفات المتبقية.

    تُستدعى مرتين: عند الإقلاع (للملفات الموجودة)، وبعد فتح القاعدة (لملفات WAL/SHM
    التي تُنشأ عند أول اتصال). ما تعذّر ضبطه يُسجَّل كتحذير ولا يوقف البوت.
    """
    results = check_paths(config.sensitive_paths(), fix=True)
    remaining = [item for item in results if item.insecure]
    for item in remaining:
        logger.warning(
            "⚠️ %s ما زال مفتوحاً لغير المالك (صلاحية %s) %s", item.label, item.mode_text, item.note
        )
    return len(remaining)


async def _open_database(config: Config) -> Database:
    """فتح قاعدة البيانات وتطبيق الترحيلات الناقصة قبل بدء الخدمة."""
    db = Database(config.database_path)
    await db.connect()
    migrator = Migrator(db)
    pending = await migrator.pending()
    if pending:
        logger.info("تطبيق %s ترحيل ناقص: %s", len(pending), ", ".join(pending))
        if await migrator.applied():
            # قاعدة قائمة ستُرقّى: نسخة أمان أولاً (A13). فشلها يوقف الإقلاع — لا ترقية بلا شبكة أمان.
            try:
                artifact = await create_backup_file(
                    db, config.backup_dir, backup_type=str(BackupType.PRE_OPERATION), app_version=APP_VERSION
                )
            except BackupError as exc:
                await db.close()
                raise SystemExit(
                    f"❌ تعذّر أخذ نسخة أمان قبل ترقية قاعدة البيانات: {exc}\n"
                    "   حرّر مساحة على القرص أو افحص صلاحيات مجلد النسخ ثم أعد التشغيل."
                ) from exc
            logger.info("نسخة أمان قبل الترحيل: %s", artifact.filename)
        applied = await migrator.apply_all()
        logger.info("تم تطبيق الترحيلات: %s", ", ".join(applied))
    logger.info("إصدار مخطط قاعدة البيانات: %s", await migrator.current_version())
    return db


async def _best_effort_telegram(factory, *, what: str):
    """
    نداء تيليجرام غير حرج أثناء الإقلاع: يُعاد عند الأعطال المؤقتة، وإن استمرت يُسجَّل تحذير ويُكمل الإقلاع.

    المخرجات: نتيجة النداء، أو None إن تعذّر بسبب الاتصال. `BadRequest`/`InvalidToken` تُرفع (خطأ حقيقي).
    """
    try:
        return await call_telegram(factory, what=what, idempotent=True, delays=STARTUP_RETRY_DELAYS)
    except (BadRequest, InvalidToken):
        raise
    except (NetworkError, TimedOut, RetryAfter) as exc:
        logger.warning("تعذّر «%s» أثناء الإقلاع بسبب اتصال تيليجرام (يُكمل البوت): %s", what, sanitize(str(exc)))
        return None


async def _log_webhook_state(application: Application) -> None:
    """
    تشخيص تعارض الاستقبال: هل يوجد webhook مفعّل بنفس التوكن؟ (الـwebhook مع polling يسبّبان Conflict).

    يُسجَّل **اسم المضيف فقط** (مسار الـwebhook قد يحمل سراً)؛ فشل النداء لا يؤثر على الإقلاع.
    """
    info = await _best_effort_telegram(application.bot.get_webhook_info, what="قراءة حالة webhook")
    if info is None:
        return
    if getattr(info, "url", ""):
        logger.warning(
            "يوجد webhook مفعّل لهذا البوت (%s) — قد يسبّب Conflict مع polling؛ سيُحذف عند بدء polling "
            "وقد تكون نسخة أخرى تعيد ضبطه",
            sanitize(urlparse(str(info.url)).hostname or "?")[:80],
        )
    else:
        logger.info("لا webhook مفعّل — الاستقبال عبر polling فقط")


def _health_status(application: Application) -> dict:
    """حالة عامة لخادم الصحة: بلا أي بيانات حسّاسة (إصدار + هل أُوقف الحارس بسبب تعارض)."""
    guard = application.bot_data.get("conflict_guard")
    return {
        "status": "conflict" if guard is not None and guard.tripped else "ok",
        "version": APP_VERSION,
        "recent_conflicts": guard.recent_conflicts if guard is not None else 0,
    }


def build_application(config: Config) -> Application:
    """
    بناء تطبيق تيليجرام وربط كل مكوناته.

    المخرجات: تطبيق جاهز للتشغيل عبر `run_polling`.
    """
    # block=True (الافتراضي): معالجة متسلسلة للتحديث الواحد — لا سباق على الرصيد
    defaults = Defaults(parse_mode=ParseMode.HTML, link_preview_options=LinkPreviewOptions(is_disabled=True))

    async def post_init(application: Application) -> None:
        """ما يُنفَّذ بعد تهيئة التطبيق وقبل استقبال أول تحديث."""
        db = await _open_database(config)
        harden_filesystem(config)               # ملفات WAL/SHM وُلدت الآن
        repos = Repositories(db)
        services = build_services(
            db,
            repos,
            secret_box=SecretBox(config.encryption_key),
            super_admin_ids=config.super_admin_ids,
            backup_dir=config.backup_dir,
            backup_channel_id=config.backup_channel_id,
            admin_alert_chat_id=config.admin_alert_chat_id,
            app_version=APP_VERSION,
        )
        application.bot_data["services"] = services
        application.bot_data["config"] = config

        # الأدمن الأعلى من متغيرات البيئة: إنشاء/ترقية/رفع حظر تلقائي عند كل إقلاع (بلا Shell ولا تعديل DB)
        if config.super_admin_ids:
            for outcome in await services.auth.bootstrap_super_admins():
                if outcome.changed:
                    logger.warning("تثبيت الأدمن الأعلى %s من SUPER_ADMIN_IDS: %s", outcome.telegram_id, outcome.action)
            logger.info("الأدمن الأعلى المعتمدون من البيئة: %s", len(config.super_admin_ids))
        else:
            logger.warning("SUPER_ADMIN_IDS غير مضبوط — لن يوجد أدمن أعلى جديد إلا إن كان في قاعدة البيانات أصلاً")

        # خادم الصحة (اختياري): يعمل فقط إن وُفّر PORT (Render Web Service)
        if config.health_port:
            health = HealthServer(config.health_port, lambda: _health_status(application))
            await health.start()
            application.bot_data["health_server"] = health

        await services.backups.sync_catalog()           # يسجّل نسخاً وُجدت على القرص بلا سجل
        await run_startup_recovery(services)
        await schedule_jobs(application, services)
        # نداءان تجميليان/معلوماتيان: عطل الشبكة المؤقت فيهما (TimedOut/ConnectError) خارجي ولا يستحق إسقاط
        # الإقلاع بعد أن أُنجزت الترحيلات والاستعادة؛ أما BadRequest فخطأ كود (أوامر غير صالحة) ويُرفع.
        await _best_effort_telegram(
            lambda: application.bot.set_my_commands(BOT_COMMANDS), what="تسجيل أوامر البوت"
        )
        me = await _best_effort_telegram(application.bot.get_me, what="قراءة هوية البوت")
        await _log_webhook_state(application)
        logger.info("البوت جاهز: @%s (الإصدار %s)", me.username if me else "?", APP_VERSION)
        if await services.settings.is_maintenance():
            logger.warning("النظام في وضع الصيانة — المستخدمون سيرون رسالة الصيانة")

    async def post_shutdown(application: Application) -> None:
        """إغلاق الموارد بنظافة بعد توقف التطبيق."""
        health = application.bot_data.get("health_server")
        if health is not None:
            await health.stop()
        services = application.bot_data.get("services")
        if services is not None:
            await services.db.close()
            logger.info("تم إغلاق قاعدة البيانات")

    application = (
        ApplicationBuilder()
        .token(config.bot_token)
        .defaults(defaults)
        .concurrent_updates(False)       # معالجة متسلسلة: أأمن مع SQLite والعمليات المالية
        .connect_timeout(TELEGRAM_CONNECT_TIMEOUT)
        .read_timeout(TELEGRAM_READ_TIMEOUT)
        .write_timeout(TELEGRAM_WRITE_TIMEOUT)
        .pool_timeout(TELEGRAM_POOL_TIMEOUT)
        .get_updates_connect_timeout(TELEGRAM_CONNECT_TIMEOUT)
        .get_updates_read_timeout(TELEGRAM_POLLING_READ_TIMEOUT)
        .get_updates_pool_timeout(TELEGRAM_POOL_TIMEOUT)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    count = register_handlers(application)
    logger.info("تم تسجيل %s معالجاً", count)
    return application


def main() -> int:
    """
    تشغيل البوت حتى إشارة الإيقاف.

    المخرجات: رمز خروج للنظام (0 إيقاف سليم، 1 خطأ إعداد أو فشل إقلاع/انهيار، 2 نسخة تعمل بالفعل محلياً،
    3 تعارض getUpdates مستمر مع نسخة أخرى بنفس التوكن).

    أخطاء الإقلاع (توكن مرفوض، شبكة، انهيار) تُلتقط وتُطبع منقّاة من الأسرار: رسالة استثناء
    تيليجرام تحمل التوكن كاملاً، وتتبّع الاستثناء الخام كان سيُكتب في journald/الطرفية.
    """
    try:
        config = Config.load(require_bot_token=True)
    except ConfigError as exc:
        print(f"❌ خطأ في الإعدادات: {exc}", file=sys.stderr)
        return 1

    if os.name == "posix":
        os.umask(0o077)                         # كل ملف/مجلد جديد خاص بالمالك من لحظة إنشائه
    config.ensure_directories()
    setup_logging(config.log_file, config.log_level)
    harden_filesystem(config)
    logger.info("بدء تشغيل البوت — الإصدار %s", APP_VERSION)

    lock = SingleInstance(config.data_dir / "bot.lock")
    try:
        lock.acquire()
    except AlreadyRunningError as exc:
        logger.error("%s", exc)
        print(f"❌ {exc}", file=sys.stderr)
        return 2

    exit_code = 0
    try:
        application = build_application(config)
        guard = ConflictGuard(application.stop_running)
        application.bot_data["conflict_guard"] = guard
        # drop_pending_updates: تجاهل ما تراكم أثناء التوقف حتى لا تُنفَّذ ضغطات
        # أزرار قديمة على حالة تغيّرت — الطلبات نفسها تُستأنف من قاعدة البيانات.
        application.run_polling(
            drop_pending_updates=True,
            bootstrap_retries=-1,         # الإقلاع بلا شبكة: إعادة محاولة بلا نهاية بدل الخروج (لا يستهلك Restart الاستضافة)
            allowed_updates=["message", "callback_query", "my_chat_member"],
        )
        # ملاحظة: أخطاء الاستقبال (ومنها Conflict) تصل `handlers.common.errors.error_handler` بالتوقيع
        # (update=None, context) فيمرّرها للحارس؛ `run_polling` في PTB لا يقبل `error_callback`.
        if guard.tripped:
            exit_code = EXIT_CODE_CONFLICT
            print(
                "❌ تعارض مستمر: نسخة أخرى تستخدم نفس التوكن (Conflict getUpdates). أُوقفت هذه النسخة بأمان.\n"
                "   أوقف النسخة الزائدة (محلية/Render قديمة/خدمة ثانية) أو استعمل توكناً منفصلاً للتطوير.",
                file=sys.stderr,
            )
    except (KeyboardInterrupt, SystemExit):
        logger.info("إيقاف البوت بطلب من المشغّل")
    except InvalidToken:
        exit_code = 1
        logger.critical("رفض تيليجرام التوكن (BOT_TOKEN) — انسخه من @BotFather من جديد")
        print("❌ رفض تيليجرام التوكن — راجع BOT_TOKEN في ملف .env (انسخه كاملاً من @BotFather).", file=sys.stderr)
    except (NetworkError, TimedOut) as exc:
        exit_code = 1
        logger.critical("تعذّر الاتصال بتيليجرام عند الإقلاع: %s", sanitize(str(exc)))
        print("❌ تعذّر الاتصال بتيليجرام — تحقق من الشبكة/الجدار الناري ثم أعد التشغيل.", file=sys.stderr)
    except Exception:  # noqa: BLE001 - آخر حاجز: نسجّل التتبّع منقّىً ونخرج برمز فشل بدل traceback خام
        exit_code = 1
        logger.critical("انهيار غير متوقع أثناء التشغيل", exc_info=True)
        print("❌ انهيار غير متوقع — التفاصيل في ملف اللوق (الأسرار مُنقّاة).", file=sys.stderr)
    finally:
        lock.release()
        logger.info("انتهى التشغيل")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
