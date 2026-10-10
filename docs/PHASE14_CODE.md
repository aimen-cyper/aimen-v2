# الكود الكامل — المرحلة الثانية من ملاحظات v1.0.1 (الإصدار 1.2.0)

كل ما هنا منسوخ آلياً من ملفات المشروع الفعلية. الملفات الأطول من 760 سطراً غير مُكرَّرة هنا؛ مسارها في الفهرس وهي مسلَّمة كاملة في المشروع.

## الفهرس

- `database/migrations/0012_phase14_sync_search.sql` — 24 سطراً
- `core/constants.py` — 53 سطراً
- `main.py` — 302 سطراً
- `utils/telegram_retry.py` — 188 سطراً
- `handlers/common/ui.py` — 144 سطراً
- `handlers/common/errors.py` — 261 سطراً
- `handlers/common/fallbacks.py` — 109 سطراً
- `database/models.py` — 500 سطراً
- `database/repositories/services.py` — 351 سطراً
- `services/catalog_service.py` — 979 سطراً (غير مُكرَّر: كبير)
- `services/order_service.py` — 1695 سطراً (غير مُكرَّر: كبير)
- `handlers/admin/catalog.py` — 1008 سطراً (غير مُكرَّر: كبير)
- `handlers/admin/providers.py` — 1293 سطراً (غير مُكرَّر: كبير)
- `keyboards/admin_kb.py` — 1782 سطراً (غير مُكرَّر: كبير)
- `texts/ar.py` — 407 سطراً
- `texts/admin_ar.py` — 1613 سطراً (غير مُكرَّر: كبير)
- `tests/telegram_fakes.py` — 292 سطراً
- `tests/integration/test_phase14_sync_search.py` — 400 سطراً
- `tests/integration/test_phase14_orders.py` — 297 سطراً
- `tests/integration/test_phase14_statuses.py` — 242 سطراً
- `tests/integration/test_phase14_favorites.py` — 96 سطراً
- `tests/integration/test_phase14_telegram_errors.py` — 308 سطراً

---

## `database/migrations/0012_phase14_sync_search.sql`

```sql
-- =====================================================================
-- الترحيل 0012 — المرحلة الثانية من ملاحظات v1.0.1 (المزامنة والبحث)
--
-- ما يضيفه:
--   1) services.provider_missing_at : متى لاحظت المزامنة لأول مرة أن الخدمة اختفت من قائمة المزود
--      (NULL ⇒ موجودة لدى المزود). لا تُحذف الخدمة ولا تُمسّ طلباتها السابقة.
--   2) services.disabled_by_sync    : 1 ⇒ عطّلتها المزامنة (اختفت لدى المزود) فتعود تلقائياً إن
--      عادت، أما التعطيل اليدوي فلا يضع هذه العلامة ولا تلغيه المزامنة أبداً.
--   3) فهرس provider_service_id وحده: البحث بمعرّف المزود (دون معرّف المزود الداخلي) يبقى سريعاً
--      مع آلاف الخدمات.
--   4) إعداد sync_auto_disable_missing: تعطيل الخدمات المختفية لدى المزود تلقائياً بعد المزامنة.
--
-- لا حذف ولا إعادة بناء لأي جدول (ALTER ADD COLUMN وفهرس وإعداد فقط).
-- =====================================================================

ALTER TABLE services ADD COLUMN provider_missing_at TEXT;
ALTER TABLE services ADD COLUMN disabled_by_sync INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_services_provider_sid ON services(provider_service_id);

INSERT OR IGNORE INTO settings (key, value, value_type, group_code, name_ar, description_ar, is_editable, updated_at) VALUES
    ('sync_auto_disable_missing', 'true', 'bool', 'general', 'تعطيل الخدمات المختفية لدى المزود عند المزامنة',
     'عند التفعيل تُعطَّل تلقائياً الخدمة التي لم تعد في قائمة المزود (لا تُحذف ولا يُمس تاريخ طلباتها) وتعود تلقائياً إن عادت. لا يُطبَّق إن أعاد المزود قائمة فارغة أو اختفى أكثر من نصف خدماتنا دفعة واحدة (يُعدّ ذلك عطلاً لا حذفاً)', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
```

---

## `core/constants.py`

```python
"""ثوابت عامة للنظام (قيم لا تتغير أثناء التشغيل)."""

from __future__ import annotations

#: اسم المشروع وإصداره
APP_NAME: str = "SMM Telegram Bot"
APP_VERSION = "1.2.0"

#: مدة قفل الطلب أثناء معالجته بواسطة job (بالثواني)
ORDER_LOCK_SECONDS: int = 120

#: مهل اتصال تيليجرام (ثوانٍ): الافتراضي في PTB خمس ثوانٍ فقط فيكثر `TimedOut` على الاستضافات المجانية/الشبكات البطيئة
TELEGRAM_CONNECT_TIMEOUT: float = 10.0
TELEGRAM_READ_TIMEOUT: float = 20.0
TELEGRAM_WRITE_TIMEOUT: float = 20.0
TELEGRAM_POOL_TIMEOUT: float = 10.0
#: مهلة قراءة `getUpdates` (تُضاف إلى مدة long-polling نفسها)
TELEGRAM_POLLING_READ_TIMEOUT: float = 20.0

#: أقصى عدد محاولات لإرسال الطلب إلى المزود عند الفشل الآمن (قبل اعتباره فاشلاً)
MAX_SUBMIT_ATTEMPTS: int = 3

#: أقصى عدد محاولات إرسال إشعار قبل اعتباره فاشلاً
MAX_NOTIFICATION_ATTEMPTS: int = 5

#: تدرج فترات إعادة فحص حالة الطلب (بالثواني)
ORDER_CHECK_BACKOFF: tuple[int, ...] = (60, 300, 900, 1800, 3600)

#: تدرج فترات إعادة إرسال الإشعار الفاشل (بالثواني)
NOTIFICATION_BACKOFF: tuple[int, ...] = (10, 60, 300, 1800, 3600)

#: مدة صلاحية مفاتيح منع التكرار الافتراضية (بالثواني)
IDEMPOTENCY_TTL_SECONDS: int = 24 * 3600

#: طول أقصى للنصوص المُخزَّنة من استجابات المزود (منعاً لتضخم قاعدة البيانات)
PROVIDER_RESPONSE_SNIPPET_LEN: int = 500

#: عدد العناصر في صفحة القوائم داخل تيليجرام
PAGE_SIZE: int = 8

#: صيغة مراجع الحركات المالية (تُستخدم لمنع التكرار)
REF_ORDER_DEBIT: str = "order:{order_id}"
REF_ORDER_REFUND: str = "refund:order:{order_id}"
REF_ORDER_PARTIAL_REFUND: str = "partial_refund:order:{order_id}"
REF_PAYMENT_DEPOSIT: str = "payment:{payment_id}"
REF_MANUAL: str = "manual:{kind}:{admin_id}:{token}"

#: صيغة مفاتيح منع تكرار الإشعارات
NOTIF_KEY_ORDER: str = "order:{order_id}:{event}"
NOTIF_KEY_PAYMENT: str = "payment:{payment_id}:{event}"
NOTIF_KEY_TICKET: str = "ticket:{ticket_id}:{event}"
NOTIF_KEY_MANUAL: str = "manual:{token}"
```

---

## `main.py`

```python
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
    BotCommand("start", "القائمة الرئيسية"),
    BotCommand("help", "شرح استخدام البوت"),
    BotCommand("cancel", "إلغاء العملية الحالية"),
    BotCommand("id", "عرض معرفي في تيليجرام"),
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
            error_callback=guard.on_polling_error,
        )
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
```

---

## `utils/telegram_retry.py`

```python
"""
التعامل مع أعطال الاتصال بتيليجرام (Timeout / ConnectError / RetryAfter) — تمييز الخارجي من الداخلي.

لماذا؟
    `TimedOut` و`ConnectError` أعطال **خارجية** (شبكة/خوادم تيليجرام) وليست خطأ في كودنا، ويجب ألا:
        • تُسقط البوت أو المعالج بعد أن أُنجزت العملية المالية (الطلب أُنشئ والرصيد خُصم)؛
        • تُضيع إشعاراً (للإشعارات صندوق دائم بمحاولات مجدولة)؛
        • تُخفي أخطاء الكود الحقيقية — و`BadRequest` فرع من `NetworkError` في PTB لذلك يُفحص **قبله دائماً**.

سياسة إعادة المحاولة (`call_telegram`):
    • عملية **متساوية الأثر** (تحرير رسالة، الرد على زر): تُعاد عند أي عطل شبكي.
    • عملية **غير متساوية الأثر** (إرسال رسالة جديدة): تُعاد فقط حين يكون التسليم مستحيلاً
      (فشل اتصال / مهلة تجمّع الاتصالات / `RetryAfter`)؛ أما مهلة القراءة فالرسالة قد تكون وصلت،
      وإعادة الإرسال تُكرّرها — فلا تُعاد (والأثر المالي محمي أصلاً بمفتاح منع التكرار وصندوق الإشعارات).

التصنيف (`classify`):
    external  : مهلة/انقطاع/قيود معدّل — مؤقت وخارجي ⇒ تحذير فقط وبلا إنذار لكل حالة.
    user_side : المستخدم حظر البوت (Forbidden).
    benign    : رفض غير ضار («message is not modified»، ضغطة زر قديمة…).
    internal  : أي شيء آخر (منه `BadRequest` غير الضار = خطأ في طلبنا نحن) ⇒ خطأ كامل مع تنبيه.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import TypeVar

from telegram.error import BadRequest, Conflict, Forbidden, NetworkError, RetryAfter, TimedOut

from utils.logging_setup import get_logger
from utils.security import sanitize

logger = get_logger(__name__)

T = TypeVar("T")

#: فواصل الانتظار بين المحاولات (ثوانٍ) — قصيرة: المعالجة متسلسلة فلا نُعطّل بقية المستخدمين
RETRY_DELAYS: tuple[float, ...] = (0.4, 1.2)

#: أقصى انتظار نقبله لطلب `RetryAfter` داخل معالج تفاعلي (بعدها نستسلم بدل تجميد البوت)
MAX_RETRY_AFTER_WAIT = 5.0

#: نصوص رفض غير ضارة من تيليجرام (بحروف صغيرة) — حالات طبيعية لا تستحق خطأً
BENIGN_BAD_REQUESTS: tuple[str, ...] = (
    "message is not modified",
    "query is too old",
    "query id is invalid",
    "message to edit not found",
    "message can't be edited",
    "message to delete not found",
    "message can't be deleted",
)

#: نافذة وعتبة اعتبار الانقطاع مستمراً (عدد الأعطال الخارجية خلال النافذة) لتنبيه الأدمن
OUTAGE_WINDOW_SECONDS = 300
OUTAGE_THRESHOLD = 10


def classify(error: BaseException | None) -> str:
    """
    تصنيف استثناء تيليجرام: `external` | `user_side` | `benign` | `internal`.

    الترتيب مهم: `BadRequest` و`Forbidden` و`Conflict` فروع من `NetworkError`/`TelegramError`
    فتُفحص قبل الفرع الشبكي العام وإلا اختفت أخطاء الكود الحقيقية تحت «انقطاع مؤقت».
    """
    if isinstance(error, Forbidden):
        return "user_side"
    if isinstance(error, BadRequest):
        text = str(error).lower()
        return "benign" if any(marker in text for marker in BENIGN_BAD_REQUESTS) else "internal"
    if isinstance(error, (RetryAfter, TimedOut, NetworkError, Conflict)):
        return "external"
    return "internal"


def delivery_is_impossible(error: BaseException) -> bool:
    """
    هل الفشل حدث **قبل** وصول الطلب لتيليجرام؟ (إعادة الإرسال آمنة ولا تكرّر الرسالة)

    PTB يحوّل أعطال httpx إلى: `TimedOut("Pool timeout"/"Connect timeout"/"Read timeout"/"Write timeout")`
    و`NetworkError("httpx.ConnectError: …")`. فقط الاتصال/التجمّع/RetryAfter مؤكَّد عدم التسليم فيها.
    """
    if isinstance(error, RetryAfter):
        return True
    text = str(error).lower()
    if isinstance(error, TimedOut):
        return "pool timeout" in text or "connect timeout" in text
    if isinstance(error, NetworkError) and not isinstance(error, BadRequest):
        return "connecterror" in text or "connecttimeout" in text
    return False


def _retry_after_seconds(error: RetryAfter) -> float:
    """مدة الانتظار التي طلبها تيليجرام (PTB 21 تُرجع عدداً صحيحاً، وإصدارات أحدث `timedelta`)."""
    value = error.retry_after
    return value.total_seconds() if isinstance(value, timedelta) else float(value)


async def call_telegram(
    factory: Callable[[], Awaitable[T]],
    *,
    what: str,
    idempotent: bool,
    delays: tuple[float, ...] | None = None,
) -> T:
    """
    تنفيذ نداء تيليجرام مع إعادة محاولة محكومة، وإعادة رفع الخطأ الأخير إن استنفدت المحاولات.

    المدخلات:
        factory    : دالة تُنشئ coroutine جديدة لكل محاولة (النداء نفسه).
        what       : وصف قصير للّوق («تحرير رسالة»).
        idempotent : هل تكرار النداء بلا أثر جانبي؟ (تحرير/إجابة زر = نعم، إرسال رسالة = لا).

    الاستثناءات: ما لم يكن مؤقتاً قابلاً للإعادة يُرفع فوراً (BadRequest، Forbidden، …).
    """
    waits = RETRY_DELAYS if delays is None else delays
    attempt = 0
    while True:
        try:
            return await factory()
        except (BadRequest, Forbidden):
            raise                                     # ليس شبكياً: لا فائدة من الإعادة (BadRequest فرع NetworkError)
        except RetryAfter as exc:
            wait = _retry_after_seconds(exc)
            if attempt >= len(waits) or wait > MAX_RETRY_AFTER_WAIT:
                raise
            logger.warning("تيليجرام طلب الانتظار %.1fث قبل «%s» (محاولة %s)", wait, what, attempt + 1)
            await asyncio.sleep(wait)
        except (TimedOut, NetworkError) as exc:
            if attempt >= len(waits) or not (idempotent or delivery_is_impossible(exc)):
                raise
            logger.warning(
                "عطل اتصال أثناء «%s» (%s: %s) — إعادة المحاولة %s/%s",
                what, type(exc).__name__, sanitize(str(exc))[:120], attempt + 1, len(waits),
            )
            await asyncio.sleep(waits[attempt])
        attempt += 1


class TelegramHealth:
    """
    عدّاد أعطال الاتصال الخارجية في نافذة زمنية، لاكتشاف الانقطاع المستمر (لا العطل العابر).

    عطل أو اثنان كل بضع دقائق أمر عادي على الشبكات الضعيفة؛ العشرة خلال خمس دقائق انقطاع يستحق إبلاغ الأدمن.
    """

    def __init__(
        self,
        *,
        window_seconds: int = OUTAGE_WINDOW_SECONDS,
        threshold: int = OUTAGE_THRESHOLD,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """تهيئة العدّاد بنافذة وعتبة وساعة قابلة للحقن (للاختبار)."""
        self._window = window_seconds
        self._threshold = threshold
        self._clock = clock
        self._events: deque[float] = deque()
        self.total_external = 0

    def record_external(self) -> int:
        """تسجيل عطل خارجي وإرجاع عدد الأعطال داخل النافذة الحالية."""
        now = self._clock()
        self._events.append(now)
        self.total_external += 1
        self._trim(now)
        return len(self._events)

    def _trim(self, now: float) -> None:
        """إسقاط الأحداث الأقدم من النافذة."""
        while self._events and now - self._events[0] > self._window:
            self._events.popleft()

    @property
    def recent(self) -> int:
        """عدد الأعطال الخارجية في النافذة الحالية."""
        self._trim(self._clock())
        return len(self._events)

    @property
    def outage(self) -> bool:
        """هل بلغنا عتبة الانقطاع المستمر؟"""
        return self.recent >= self._threshold
```

---

## `handlers/common/ui.py`

```python
"""
أدوات عرض موحّدة: إرسال الشاشات وتحريرها والرد على ضغطات الأزرار.

لماذا؟
    • التنقل في البوت يكون بتحرير نفس الرسالة (`edit_message_text`) لا بإغراق
      المحادثة برسائل جديدة — هذا يحتاج تعاملاً موحّداً مع نوعي التحديث
      (ضغطة زر / رسالة نصية).
    • تيليجرام يرفض تحرير رسالة بنفس محتواها برسالة الخطأ
      «message is not modified»؛ وهي حالة طبيعية (ضغط الزر مرتين) نتعامل معها
      بوضوح بدل كتمان كل الأخطاء.
    • أعطال الاتصال (TimedOut/ConnectError/RetryAfter) خارجية: تُعاد محاولتها بحدود (`call_telegram`) ثم
      تُسجَّل كتحذير **دون أن تُسقط المعالج** — فالعملية المالية/الحالة التي سبقت العرض ثابتة في القاعدة،
      وإشعار المستخدم بها يصله من صندوق الإشعارات الدائم، فلا يبقى الطلب «معلّقاً» لأن الشاشة لم تُرسم.
"""

from __future__ import annotations

from telegram import InlineKeyboardMarkup, LinkPreviewOptions, Message, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TelegramError, TimedOut
from telegram.ext import ContextTypes

from utils.logging_setup import get_logger
from utils.telegram_retry import call_telegram

logger = get_logger(__name__)

#: نص خطأ تيليجرام عند تحرير رسالة بمحتوى مطابق (ليس خطأً حقيقياً)
NOT_MODIFIED = "message is not modified"


async def answer_callback(update: Update, text: str = "", *, alert: bool = False) -> None:
    """
    الرد على ضغطة الزر لإزالة مؤشر الانتظار عند المستخدم.

    يُستدعى في بداية كل معالج أزرار؛ تجاهله يُبقي الزر «يدور» عند المستخدم.
    """
    query = update.callback_query
    if query is None:
        return
    try:
        await call_telegram(
            lambda: query.answer(text=text or None, show_alert=alert), what="الرد على ضغطة زر", idempotent=True
        )
    except BadRequest as exc:
        # الاستعلام القديم (أكثر من 48 ساعة) لا يمكن الرد عليه — نسجّل ونكمل
        logger.debug("تعذر الرد على ضغطة زر قديمة: %s", exc)
    except (TimedOut, NetworkError, RetryAfter) as exc:
        # الرد على الزر تجميلي (يُزيل مؤشر الانتظار) — عطل الشبكة لا يمنع تنفيذ الوظيفة نفسها
        logger.warning("تعذر الرد على ضغطة زر بسبب اتصال تيليجرام: %s", exc)


async def render(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
    *,
    disable_preview: bool = True,
) -> None:
    """
    عرض شاشة: تحرير الرسالة الحالية إن جاء التحديث من زر، وإلا إرسال رسالة جديدة.

    المدخلات:
        text   : نص الشاشة (بتنسيق HTML).
        markup : لوحة الأزرار المرافقة.
    """
    query = update.callback_query
    if query is not None and query.message is not None:
        try:
            await call_telegram(
                lambda: query.edit_message_text(
                    text=text,
                    reply_markup=markup,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=LinkPreviewOptions(is_disabled=disable_preview),
                ),
                what="تحرير رسالة",
                idempotent=True,            # التحرير بالنص نفسه لا أثر جانبياً له
            )
            return
        except BadRequest as exc:
            if NOT_MODIFIED in str(exc).lower():
                return                      # المستخدم ضغط نفس الزر — لا جديد يُعرض
            logger.warning("تعذر تحرير الرسالة، سيُرسل بديل: %s", exc)
        except (TimedOut, NetworkError, RetryAfter) as exc:
            # الشبكة معطّلة: الإرسال البديل سيفشل غالباً وقد يُكرّر الشاشة إن كان التحرير نجح فعلاً
            logger.warning("تعذر عرض الشاشة بسبب اتصال تيليجرام (الحالة محفوظة): %s", exc)
            return

    await send(update, context, text, markup, disable_preview=disable_preview)


async def send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
    *,
    disable_preview: bool = True,
) -> Message | None:
    """إرسال رسالة جديدة إلى محادثة المستخدم (تُستخدم للنتائج والتنبيهات)؛ تُرجع الرسالة المُرسلة إن نجح."""
    chat = update.effective_chat
    if chat is None:
        logger.warning("تحديث بلا محادثة — تعذر الإرسال")
        return None
    try:
        return await call_telegram(
            lambda: context.bot.send_message(
                chat_id=chat.id,
                text=text,
                reply_markup=markup,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=disable_preview),
            ),
            what="إرسال رسالة",
            idempotent=False,               # لا تُعاد إلا حين يستحيل التسليم (لا نكرّر رسالة وصلت)
        )
    except Forbidden:
        # المستخدم حظر البوت — تُعلَّم الحالة في قاعدة البيانات عبر مهمة الإشعارات
        logger.info("المستخدم %s حظر البوت", chat.id)
        return None
    except BadRequest:
        raise                               # رفض من تيليجرام لطلبنا (HTML فاسد…) = خطأ كود يجب أن يظهر
    except (TimedOut, NetworkError, RetryAfter) as exc:
        logger.warning("تعذر إرسال رسالة إلى %s بسبب اتصال تيليجرام (الحالة محفوظة): %s", chat.id, exc)
        return None


async def delete_quietly(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int | None) -> bool:
    """
    حذف رسالة بلا إزعاج إن تعذّر (قديمة >48س، محذوفة أصلاً، أو بلا صلاحية).

    هو إجراء تجميلي لتقليل الفوضى في المحادثة؛ فشله لا يؤثر على أي وظيفة، ويُسجَّل على مستوى debug.
    """
    if not message_id:
        return False
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramError as exc:
        logger.debug("تعذّر حذف الرسالة %s: %s", message_id, exc)
        return False
    return True
```

---

## `handlers/common/errors.py`

```python
"""
المعالج العام للأخطاء غير المتوقعة.

ما يفعله عند أي استثناء يصل إليه:
    1. يسجّله في اللوق مع كامل التتبع (Traceback).
    2. يحفظه في جدول `error_logs` ليراه الأدمن لاحقاً داخل البوت (المرحلة 4).
    3. يُبلغ المستخدم برسالة عربية مهذّبة بلا أي تفاصيل تقنية.

مبدأ ملزم: **لا ابتلاع أخطاء**. كل خطأ يُسجَّل ويُرى، والمستخدم لا يُترك
أمام شاشة صامتة.
"""

from __future__ import annotations

import html
import time
import traceback

from telegram import Update
from telegram.ext import ContextTypes

from core.permissions import Permission
from handlers.common.ui import answer_callback, send
from texts import ar
from utils.logging_setup import get_logger
from utils.security import sanitize
from utils.telegram_retry import OUTAGE_THRESHOLD, TelegramHealth, classify
from utils.throttle import AlertThrottle

logger = get_logger(__name__)

#: أقصى طول نص خطأ يُخزَّن في قاعدة البيانات
MAX_STORED_ERROR = 4000

#: أقصى طول لمقتطف الخطأ داخل تنبيه الأدمن
MAX_ALERT_SNIPPET = 200

#: مفتاح مُهدِّئ تنبيهات الأخطاء في `bot_data`
THROTTLE_KEY = "error_alert_throttle"

#: مفاتيح `bot_data` لعدّاد صحة الاتصال بتيليجرام ومُهدِّئ تنبيه الانقطاع/تسجيله
HEALTH_KEY = "telegram_health"
NETWORK_THROTTLE_KEY = "telegram_network_throttle"

#: فترة تهدئة تسجيل/تنبيه الانقطاع (ثوانٍ): مرة كل نصف ساعة للتنبيه، وخمس دقائق للتسجيل
NETWORK_ALERT_COOLDOWN = 1800
NETWORK_LOG_COOLDOWN = 300


def _describe_update(update: object) -> str:
    """وصف مختصر للتحديث الذي سبّب الخطأ (بلا بيانات حساسة)."""
    if not isinstance(update, Update):
        return "تحديث غير معروف"
    user = update.effective_user
    parts = [f"user={user.id}" if user else "user=?"]
    if update.callback_query is not None:
        parts.append(f"button={update.callback_query.data}")
    elif update.effective_message is not None and update.effective_message.text:
        text = update.effective_message.text
        # نصّ المستخدم العادي قد يحوي سراً (مفتاح مزود يُكتب في محادثة) فلا نسجّله؛ الأوامر فقط
        if text.startswith("/"):
            parts.append(f"command={text.split()[0][:30]!r}")
        else:
            parts.append(f"text=<{len(text)} حرف>")
    return " | ".join(parts)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    المعالج العام: يُستدعى لكل استثناء لم يُلتقط داخل المعالجات.

    أخطاء الشبكة المؤقتة تُسجَّل كتحذير فقط (ستُعاد المحاولة تلقائياً)،
    وغيرها يُسجَّل كخطأ كامل في اللوق وقاعدة البيانات.
    """
    error = context.error
    description = _describe_update(update)
    kind = classify(error)

    # الترتيب في `classify` هو الذي يضمن أن BadRequest (فرع من NetworkError) لا يُخفي خطأ كود حقيقياً
    if kind == "external":
        await _handle_external(update, context, error, description)
        return

    if kind == "benign":
        logger.info("رفض غير ضار من تيليجرام (%s): %s", description, error)
        return

    if kind == "user_side":
        # المستخدم حظر البوت — نعلّمه في قاعدة البيانات ولا نزعج اللوق بخطأ كامل
        logger.info("المستخدم حظر البوت (%s)", description)
        await _mark_blocked(update, context)
        return

    trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    logger.error("خطأ غير متوقع (%s): %s\n%s", description, error, trace)

    await _store_error(context, description, error, trace)
    await _alert_admins(context, error)

    if isinstance(update, Update):
        # فشل إبلاغ المستخدم لا يجب أن يخفي الخطأ الأصلي ولا أن يولّد خطأً جديداً
        try:
            await answer_callback(update)
            await send(update, context, ar.ERR_GENERIC)
        except Exception as notify_error:          # noqa: BLE001 - المعالج العام لا يُسقَط
            logger.warning("تعذر إبلاغ المستخدم بالخطأ: %s", notify_error)


async def _handle_external(
    update: object, context: ContextTypes.DEFAULT_TYPE, error: BaseException | None, description: str
) -> None:
    """
    عطل خارجي (مهلة/انقطاع/RetryAfter): ليس خطأ كود ولا يستحق إنذاراً لكل حالة.

    ما يحدث: تحذير منقّى في اللوق + عدّ في نافذة زمنية؛ تسجيل في `error_logs` بمستوى WARNING مرة كل
    خمس دقائق؛ وإن بلغ العدد عتبة الانقطاع المستمر يُنبَّه الأدمن مرة كل نصف ساعة. ثم يُطلب من المستخدم
    إعادة المحاولة (إن أمكن) — الحالة المالية لا تتأثر لأن كل عملية محفوظة قبل أي إرسال.
    """
    logger.warning("عطل اتصال خارجي بتيليجرام (%s): %s: %s", description, type(error).__name__, sanitize(str(error))[:200])
    bot_data = context.application.bot_data
    health = bot_data.setdefault(HEALTH_KEY, TelegramHealth())
    recent = health.record_external()
    throttle = bot_data.setdefault(NETWORK_THROTTLE_KEY, AlertThrottle(max_per_window=2))

    services = bot_data.get("services")
    if services is not None:
        try:
            if throttle.check("log", cooldown_seconds=NETWORK_LOG_COOLDOWN).allow:
                async with services.db.transaction() as tx:
                    await services.repos.error_logs.log(
                        tx,
                        level="WARNING",
                        source="telegram_network",
                        error_type=type(error).__name__,
                        message=f"عطل اتصال خارجي: {type(error).__name__}: {sanitize(str(error))}"[:500],
                        update_summary=description,
                    )
            if health.outage and throttle.check("alert", cooldown_seconds=NETWORK_ALERT_COOLDOWN).allow:
                async with services.db.transaction() as tx:
                    await services.notifications.notify_admins(
                        tx,
                        permission=Permission.LOGS_VIEW,
                        token=f"tgnet:{_epoch_bucket(NETWORK_ALERT_COOLDOWN // 60)}",
                        title="📡 اتصال تيليجرام غير مستقر",
                        message=(
                            f"{recent} عطل اتصال خارجي (مهلة/انقطاع) خلال آخر 5 دقائق (العتبة {OUTAGE_THRESHOLD}).\n"
                            "هذا خارجي (شبكة الاستضافة أو خوادم تيليجرام) وليس خطأ كود: الطلبات والأرصدة محفوظة "
                            "والإشعارات تُعاد تلقائياً. راجع اتصال الخادم إن استمر."
                        ),
                    )
        except Exception as record_error:             # noqa: BLE001 - تسجيل العطل لا يُسقط المعالج العام
            logger.error("تعذر تسجيل عطل الاتصال أو تنبيه الأدمن: %s", record_error)

    if isinstance(update, Update):
        try:
            await send(update, context, ar.ERR_TELEGRAM_TEMP)
        except Exception as notify_error:            # noqa: BLE001 - لا خطأ جديداً من إبلاغ المستخدم
            logger.warning("تعذر إبلاغ المستخدم بعطل الاتصال: %s", notify_error)


def _error_fingerprint(error: BaseException | None) -> str:
    """
    بصمة الخطأ لتجميع المتشابه: نوعه + موضع رمي الاستثناء (آخر إطار في التتبع).

    الموضع أدق من النوع وحده (`KeyError` في مكانين مختلفين خطآن مختلفان)،
    وأدق من النص (الذي يحوي أرقاماً متغيرة فيكسر التجميع).
    """
    if error is None:
        return "unknown"
    location = "?"
    tb = error.__traceback__
    while tb is not None and tb.tb_next is not None:
        tb = tb.tb_next
    if tb is not None:
        location = f"{tb.tb_frame.f_code.co_filename.rsplit('/', 1)[-1]}:{tb.tb_lineno}"
    return f"{type(error).__name__}@{location}"


async def _alert_admins(context: ContextTypes.DEFAULT_TYPE, error: BaseException | None) -> None:
    """
    تنبيه من يملك `logs.view` بخطأ غير متوقع — مرة لكل بصمة في فترة التهدئة.

    يُعطَّل بالإعداد `error_alert_enabled`. النص المرسل نوع الخطأ + مقتطف منقّى فقط
    (لا تتبّع كامل ولا بيانات مستخدم)، والتفاصيل في «السجلات ← الأخطاء».
    فشل التنبيه نفسه يُسجَّل ولا يُسقط المعالج.
    """
    services = context.application.bot_data.get("services")
    if services is None:
        return
    try:
        if not await services.settings.get_bool("error_alert_enabled", True):
            return
        cooldown_minutes = await services.settings.get_int("error_alert_cooldown_minutes", 15)
        throttle = context.application.bot_data.setdefault(THROTTLE_KEY, AlertThrottle())
        fingerprint = _error_fingerprint(error)
        decision = throttle.check(fingerprint, cooldown_seconds=cooldown_minutes * 60)
        if not decision.allow:
            return

        snippet = sanitize(f"{error}")[:MAX_ALERT_SNIPPET] if error else ""
        repeated = f"\nتكرر قبل ذلك: {decision.suppressed} مرة (كُبتت تنبيهاتها)." if decision.suppressed else ""
        message = (
            f"النوع: {type(error).__name__ if error else 'غير معروف'}\n"
            f"الموضع: {fingerprint.split('@', 1)[-1]}\n"
            f"المقتطف: {html.escape(snippet) or '—'}{repeated}\n"
            "التفاصيل في: لوحة التحكم ← السجلات ← الأخطاء."
        )
        async with services.db.transaction() as tx:
            await services.notifications.notify_admins(
                tx,
                permission=Permission.LOGS_VIEW,
                token=f"error:{fingerprint}:{_epoch_bucket(cooldown_minutes)}",
                title="🚨 خطأ غير متوقع في البوت",
                message=message,
            )
    except Exception as alert_error:               # noqa: BLE001 - تنبيه الخطأ لا يُسقط المعالج العام
        logger.error("تعذر إرسال تنبيه الخطأ للأدمن: %s", alert_error)


def _epoch_bucket(cooldown_minutes: int) -> int:
    """رقم الشريحة الزمنية الحالية (يمنع تكرار إدراج الإشعار نفسه ضمن فترة التهدئة)."""
    return int(time.time() // max(60, cooldown_minutes * 60))


async def _store_error(
    context: ContextTypes.DEFAULT_TYPE, description: str, error: BaseException | None, trace: str
) -> None:
    """حفظ الخطأ في جدول `error_logs` (مع عدم إسقاط البوت إن فشل الحفظ نفسه)."""
    services = context.application.bot_data.get("services")
    if services is None:
        return
    try:
        async with services.db.transaction() as tx:
            await services.repos.error_logs.log(
                tx,
                level="ERROR",
                source="telegram_handler",
                error_type=type(error).__name__,
                message=f"{type(error).__name__}: {error}"[:500],
                traceback_snippet=html.unescape(trace)[:MAX_STORED_ERROR],
                update_summary=description,
            )
    except Exception as storage_error:            # noqa: BLE001 - تسجيل فشل التسجيل نفسه
        logger.error("تعذر حفظ الخطأ في قاعدة البيانات: %s", storage_error)


async def _mark_blocked(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تعليم المستخدم الذي حظر البوت حتى تتوقف محاولات الإرسال إليه."""
    services = context.application.bot_data.get("services")
    if services is None or not isinstance(update, Update):
        return
    telegram_user = update.effective_user
    if telegram_user is None:
        return
    try:
        user = await services.users.get_by_telegram(telegram_user.id)
        if user is not None:
            await services.users.mark_bot_blocked(user.id, True)
    except Exception as exc:                      # noqa: BLE001 - لا نُسقط المعالج العام
        logger.error("تعذر تعليم المستخدم كحاظر للبوت: %s", exc)
```

---

## `handlers/common/fallbacks.py`

```python
"""
المسارات الاحتياطية: ما يحدث عند ضغط زر قديم أو إرسال نص خارج أي محادثة.

الهدف: ألا يصطدم المستخدم بصمت أبداً. أي تفاعل غير متوقع يُقابَل برسالة
عربية توضّح ما حدث وتعيده إلى القائمة الرئيسية.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from handlers.common import navigation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.callback_data import CALLBACK_VERSION, CallbackError, unpack
from keyboards.user_kb import main_menu_kb
from middlewares.context import current_user, services_of
from texts import ar
from utils.datetime_utils import iso_plus_seconds
from utils.logging_setup import get_logger

logger = get_logger(__name__)


@guarded
async def unknown_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    زر لم يلتقطه أي معالج: إما من إصدار قديم أو من رسالة قديمة جداً.

    نميّز الحالتين حتى تكون الرسالة صادقة مع المستخدم.
    """
    query = update.callback_query
    raw = query.data if query else ""
    data = None
    try:
        data = unpack(raw)
        outdated = not data.is_current_version
    except CallbackError:
        outdated = False                      # بيانات تالفة/غير مُهيكلة: «زر غير معروف» لا «قديم»

    logger.info("زر غير معالَج: %r (الإصدار الحالي v%s)", raw, CALLBACK_VERSION)
    if data is not None and not outdated and data.namespace == "flow":
        await _stale_flow_button(update, context, data.action)
        return
    message = ar.ERR_OLD_BUTTON if outdated else ar.ERR_UNKNOWN_BUTTON
    await answer_callback(update, message, alert=True)
    await render(update, context, message, main_menu_kb())


#: نافذة اعتبار الطلب «قبل لحظات» عند ضغط تأكيد قديم (ثوانٍ)
RECENT_ORDER_SECONDS = 300


async def _stale_flow_button(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
    """
    زر محادثة (تأكيد/إلغاء…) انتهت محادثته — الحالة الشائعة: **ضغطة مزدوجة** على «تأكيد الطلب».

    ممنوع هنا تحرير الرسالة: الضغطة الأولى استبدلتها بإيصال «تم إنشاء طلبك»، وتحريرها الآن
    بـ«زر غير معروف» يوحي بفشل طلب نجح فيدفع المستخدم لتكراره. نكتفي بتنبيه منبثق، وإن كان
    للمستخدم طلب حديث نذكر رقمه صراحة.
    """
    message = ar.ERR_FLOW_STALE
    user = current_user(context)
    if action == "confirm" and user is not None:
        latest = await services_of(context).orders.list_for_user(user, limit=1)
        if latest and latest[0].created_at >= iso_plus_seconds(-RECENT_ORDER_SECONDS):
            message = ar.ORDER_ALREADY_CREATED.format(code=latest[0].public_code or f"#{latest[0].id}")
    await answer_callback(update, message, alert=True)


@guarded
async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """أمر غير معروف (/anything)."""
    await send(update, context, ar.UNKNOWN_COMMAND, main_menu_kb())


@guarded
async def free_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """نص حر خارج أي محادثة — نذكّر المستخدم بأن التنقل بالأزرار."""
    await send(update, context, ar.UNKNOWN_TEXT, main_menu_kb())


@guarded
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الأمر /cancel خارج أي محادثة: تطمين المستخدم وعرض القائمة."""
    await send(update, context, ar.CANCELLED, main_menu_kb())


def exit_conversation(*flow_keys: str):
    """
    بناء معالج يُنهي محادثة جارية عند إرسال /start ويعيد المستخدم للقائمة.

    المدخلات:
        flow_keys : مفاتيح بيانات المحادثة التي تُمسح قبل الخروج.

    المخرجات: معالج جاهز للوضع في `fallbacks` الخاصة بالمحادثة.
    """

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """إنهاء المحادثة الحالية وعرض شاشة البداية."""
        if context.user_data is not None:
            for key in flow_keys:
                context.user_data.pop(key, None)
        await navigation.start_command(update, context)
        return ConversationHandler.END

    return handler
```

---

## `database/models.py`

```python
"""
نماذج البيانات (Data Models) — تمثيل صفوف الجداول ككائنات Python.

لماذا dataclasses بدل ORM كامل؟
    • خفيفة وسريعة ولا تُخفي ما يحدث في SQL.
    • تُبقي كل عبارات SQL ظاهرة في المستودعات (repositories) مما يسهّل
      مراجعتها أمنياً ونقلها لاحقاً إلى PostgreSQL.

كل نموذج يوفّر from_row لتحويل صف قاعدة البيانات إلى كائن، مع تجاهل أي أعمدة إضافية.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Iterable, Mapping, TypeVar

from core.money import from_units

_T = TypeVar("_T", bound="BaseModel")


@dataclass(slots=True)
class BaseModel:
    """أساس كل النماذج: يوفّر التحويل من صف قاعدة بيانات إلى كائن."""

    @classmethod
    def from_row(cls: type[_T], row: Mapping[str, Any] | None) -> _T | None:
        """تحويل صف واحد إلى كائن النموذج، أو None إذا لم يوجد صف."""
        if row is None:
            return None
        allowed = {f.name for f in fields(cls)}
        data = {key: row[key] for key in row.keys() if key in allowed}
        return cls(**data)  # type: ignore[arg-type]

    @classmethod
    def from_rows(cls: type[_T], rows: Iterable[Mapping[str, Any]]) -> list[_T]:
        """تحويل مجموعة صفوف إلى قائمة كائنات."""
        result: list[_T] = []
        for row in rows:
            item = cls.from_row(row)
            if item is not None:
                result.append(item)
        return result


# ------------------------------- المستخدمون ------------------------------- #


@dataclass(slots=True)
class User(BaseModel):
    """مستخدم البوت (عميل أو أدمن)."""

    id: int
    telegram_id: int
    created_at: str
    updated_at: str
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    balance_units: int = 0
    total_spent_units: int = 0
    total_deposited_units: int = 0
    role: str = "user"
    is_banned: int = 0
    ban_reason: str | None = None
    banned_at: str | None = None
    blocked_bot: int = 0
    language: str = "ar"
    referrer_id: int | None = None
    notes: str | None = None
    last_activity: str | None = None

    @property
    def balance(self):
        """الرصيد كقيمة عشرية للعرض فقط (التخزين والحساب يبقى بالنقاط)."""
        return from_units(self.balance_units)

    @property
    def display_name(self) -> str:
        """اسم مناسب للعرض في لوحة الأدمن."""
        if self.username:
            return f"@{self.username}"
        return self.first_name or f"ID:{self.telegram_id}"

    @property
    def banned(self) -> bool:
        """هل المستخدم محظور؟"""
        return bool(self.is_banned)


# -------------------------------- المزودون -------------------------------- #


@dataclass(slots=True)
class Provider(BaseModel):
    """مزود خدمات SMM خارجي."""

    id: int
    name: str
    api_url: str
    api_key_enc: str
    created_at: str
    updated_at: str
    api_key_hint: str | None = None
    api_type: str = "perfect_panel"
    balance_units: int = 0
    currency: str = "USD"
    #: سعر الصرف: 1 وحدة من `currency` = X من عملة النظام (نص Decimal)؛ None ⇒ لا سعر (يُقبل فقط عند تطابق العملتين)
    exchange_rate: str | None = None
    balance_checked_at: str | None = None
    low_balance_threshold_units: int | None = None
    is_active: int = 1
    priority: int = 100
    timeout_seconds: int = 30
    consecutive_failures: int = 0
    disabled_until: str | None = None
    last_error: str | None = None
    last_success_at: str | None = None

    @property
    def active(self) -> bool:
        """هل المزود مفعّل؟ (التعطيل المؤقت يُفحص في ProviderService)."""
        return bool(self.is_active)


# --------------------------- التصنيفات والخدمات ---------------------------- #


@dataclass(slots=True)
class ServiceCategory(BaseModel):
    """تصنيف خدمات (منصة مثل انستغرام أو تيك توك)."""

    id: int
    name_ar: str
    created_at: str
    updated_at: str
    name_en: str | None = None
    emoji: str = "📦"
    sort_order: int = 100
    is_active: int = 1

    @property
    def title(self) -> str:
        """العنوان المعروض على الزر."""
        return f"{self.emoji} {self.name_ar}"


@dataclass(slots=True)
class Service(BaseModel):
    """خدمة معروضة للبيع."""

    id: int
    category_id: int
    provider_id: int
    provider_service_id: str
    name: str
    price_per_1000_units: int
    min_quantity: int
    max_quantity: int
    created_at: str
    updated_at: str
    description: str | None = None
    service_type: str = "default"
    provider_price_per_1000_units: int | None = None
    dripfeed_enabled: int = 0
    refill_enabled: int = 0
    cancel_enabled: int = 0
    link_pattern: str | None = None
    avg_time_text: str | None = None
    is_active: int = 1
    is_archived: int = 0
    sort_order: int = 100
    link_rule: str | None = None
    speed_text: str | None = None
    quality_text: str | None = None
    guarantee_text: str | None = None
    provider_missing_at: str | None = None
    disabled_by_sync: int = 0

    @property
    def available(self) -> bool:
        """هل الخدمة متاحة للطلب الآن؟"""
        return bool(self.is_active) and not bool(self.is_archived)

    @property
    def margin_units(self) -> int | None:
        """هامش الربح لكل ألف (None إذا لم تُسجَّل تكلفة المزود)."""
        if self.provider_price_per_1000_units is None:
            return None
        return self.price_per_1000_units - self.provider_price_per_1000_units


# --------------------------------- الطلبات -------------------------------- #


@dataclass(slots=True)
class Order(BaseModel):
    """طلب عميل على خدمة."""

    id: int
    user_id: int
    service_id: int
    provider_id: int
    service_name_snapshot: str
    price_per_1000_snapshot_units: int
    link: str
    quantity: int
    cost_units: int
    client_request_id: str
    created_at: str
    updated_at: str
    public_code: str | None = None
    provider_cost_units: int | None = None
    status: str = "pending"
    provider_status: str | None = None
    provider_order_id: str | None = None
    start_count: int | None = None
    remains: int | None = None
    delivered_quantity: int | None = None
    refund_amount_units: int = 0
    refunded_at: str | None = None
    submit_attempts: int = 0
    checks_count: int = 0
    last_error: str | None = None
    locked_by: str | None = None
    locked_until: str | None = None
    next_check_at: str | None = None
    submitted_at: str | None = None
    completed_at: str | None = None
    cancelled_at: str | None = None

    @property
    def refundable_units(self) -> int:
        """المبلغ المتبقي القابل للاسترجاع (التكلفة ناقص ما استُرجع)."""
        return max(0, self.cost_units - self.refund_amount_units)


@dataclass(slots=True)
class OrderStatusHistory(BaseModel):
    """سجل انتقال حالة طلب."""

    id: int
    order_id: int
    to_status: str
    created_at: str
    from_status: str | None = None
    actor_type: str = "system"
    actor_id: int | None = None
    reason: str | None = None
    provider_status_raw: str | None = None


# ----------------------------- الحركات المالية ----------------------------- #


@dataclass(slots=True)
class Transaction(BaseModel):
    """حركة مالية في دفتر الأستاذ (إضافة فقط — لا تُعدَّل ولا تُحذف)."""

    id: int
    user_id: int
    type: str
    direction: str
    amount_units: int
    balance_before_units: int
    balance_after_units: int
    created_at: str
    order_id: int | None = None
    payment_id: int | None = None
    description: str | None = None
    reference: str | None = None
    actor_id: int | None = None

    @property
    def signed_amount_units(self) -> int:
        """المبلغ بإشارته (موجب للإضافة وسالب للخصم) لعرضه في السجل."""
        return self.amount_units if self.direction == "credit" else -self.amount_units


# -------------------------------- المدفوعات -------------------------------- #


@dataclass(slots=True)
class PaymentMethod(BaseModel):
    """طريقة شحن رصيد قابلة للتهيئة من لوحة الأدمن."""

    id: int
    code: str
    name_ar: str
    created_at: str
    updated_at: str
    type: str = "manual"
    instructions_ar: str = ""
    account_details: str = ""
    min_amount_units: int = 0
    max_amount_units: int | None = None
    requires_proof: int = 1
    is_active: int = 1
    sort_order: int = 100
    fee_percent_bp: int = 0      # رسوم نسبية بنقاط الأساس (250 = 2.5%)
    fee_fixed_units: int = 0     # رسوم ثابتة بالنقاط تُخصم من كل حوالة

    @property
    def has_fees(self) -> bool:
        """هل لهذه الطريقة رسوم تُخصم من مبلغ الحوالة؟"""
        return self.fee_percent_bp > 0 or self.fee_fixed_units > 0


@dataclass(slots=True)
class Payment(BaseModel):
    """طلب شحن رصيد."""

    id: int
    user_id: int
    method_id: int
    amount_units: int
    created_at: str
    updated_at: str
    credited_units: int | None = None
    status: str = "pending"
    transaction_reference: str | None = None
    proof_file_id: str | None = None
    proof_file_type: str | None = None
    user_note: str | None = None
    admin_id: int | None = None
    admin_note: str | None = None
    reject_reason: str | None = None
    reviewed_at: str | None = None
    expires_at: str | None = None
    fee_units: int = 0           # لقطة رسوم الطريقة وقت الإرسال (لا تتغير لاحقاً)

    @property
    def net_units(self) -> int:
        """
        المبلغ الصافي المتوقع إضافته للرصيد = المبلغ المحوَّل − الرسوم.

        يُستخدم كقيمة افتراضية في شاشة الاعتماد، ويبقى للأدمن حق تعديله.
        """
        return max(0, int(self.amount_units) - int(self.fee_units or 0))


# ---------------------------------- الدعم ---------------------------------- #


@dataclass(slots=True)
class SupportTicket(BaseModel):
    """تذكرة دعم فني."""

    id: int
    user_id: int
    subject: str
    created_at: str
    updated_at: str
    category: str = "other"
    related_order_id: int | None = None
    status: str = "open"
    priority: str = "normal"
    assigned_admin: int | None = None
    last_message_at: str | None = None
    closed_by: int | None = None
    close_reason: str | None = None
    closed_at: str | None = None

    @property
    def is_open(self) -> bool:
        """هل التذكرة ما زالت مفتوحة؟"""
        return self.status != "closed"


@dataclass(slots=True)
class SupportMessage(BaseModel):
    """رسالة داخل تذكرة دعم."""

    id: int
    ticket_id: int
    sender_type: str
    message: str
    created_at: str
    sender_id: int | None = None
    attachment_file_id: str | None = None
    attachment_type: str | None = None
    telegram_message_id: int | None = None
    is_read_by_user: int = 0
    is_read_by_admin: int = 0


# -------------------------------- الإشعارات -------------------------------- #


@dataclass(slots=True)
class Notification(BaseModel):
    """إشعار في صندوق الإرسال (Outbox)."""

    id: int
    user_id: int
    type: str
    message: str
    dedupe_key: str
    created_at: str
    title: str = ""
    payload_json: str | None = None
    status: str = "queued"
    attempts: int = 0
    next_attempt_at: str | None = None
    last_error: str | None = None
    telegram_message_id: int | None = None
    is_read: int = 0
    sent_at: str | None = None


@dataclass(slots=True)
class ChannelPost(BaseModel):
    """منشور في صندوق إرسال القنوات الإدارية (تنبيهات الإدارة / توثيق الطلبات)."""

    id: int
    kind: str
    message: str
    dedupe_key: str
    created_at: str
    title: str = ""
    status: str = "queued"
    attempts: int = 0
    next_attempt_at: str | None = None
    last_error: str | None = None
    sent_at: str | None = None


# ------------------------------ الإعدادات والسجل ---------------------------- #


@dataclass(slots=True)
class Setting(BaseModel):
    """إعداد عام من جدول settings."""

    key: str
    value: str
    updated_at: str
    value_type: str = "str"
    group_code: str = "general"
    name_ar: str = ""
    description_ar: str | None = None
    is_editable: int = 1
    updated_by: int | None = None


@dataclass(slots=True)
class AuditLog(BaseModel):
    """سجل عملية إدارية حساسة."""

    id: int
    action: str
    created_at: str
    admin_id: int | None = None
    target_type: str | None = None
    target_id: str | None = None
    details_json: str | None = None
    before_json: str | None = None
    after_json: str | None = None
    source: str = "telegram"


@dataclass(slots=True)
class Broadcast(BaseModel):
    """رسالة جماعية."""

    id: int
    created_at: str
    admin_id: int | None = None
    message_text: str = ""
    parse_mode: str | None = None
    media_file_id: str | None = None
    media_type: str | None = None
    buttons_json: str | None = None
    target: str = "all"
    target_filter_json: str | None = None
    total_count: int = 0
    sent_count: int = 0
    failed_count: int = 0
    blocked_count: int = 0
    status: str = "draft"
    started_at: str | None = None
    finished_at: str | None = None


@dataclass(slots=True)
class NotificationTemplate(BaseModel):
    """قالب إشعار مخصّص من لوحة التحكم (المرحلة 8) — غيابه يعني استعمال النص الافتراضي."""

    code: str
    title: str
    body: str
    updated_at: str
    is_active: int = 1
    updated_by: int | None = None

    @property
    def enabled(self) -> bool:
        """هل القالب المخصّص مفعّل فعلاً (وإلا يعود النظام للنص المدمج)؟"""
        return bool(self.is_active)
```

---

## `database/repositories/services.py`

```python
"""
مستودع الخدمات — الخدمات المعروضة للبيع وارتباطها بالمزودين.

قاعدة مهمة: الخدمة التي لها طلبات سابقة لا تُحذف نهائياً، بل تُعطَّل أو تُؤرشف،
حتى لا تُكسر المراجع التاريخية في جدول الطلبات.
"""

from __future__ import annotations

from typing import Any

from database.database import Tx
from database.models import Service
from database.repositories.base import BaseRepository

_ALLOWED_FIELDS = {
    "category_id",
    "provider_id",
    "provider_service_id",
    "name",
    "description",
    "service_type",
    "price_per_1000_units",
    "provider_price_per_1000_units",
    "min_quantity",
    "max_quantity",
    "dripfeed_enabled",
    "refill_enabled",
    "cancel_enabled",
    "link_pattern",
    "avg_time_text",
    "is_active",
    "is_archived",
    "sort_order",
    "link_rule",
    "speed_text",
    "quality_text",
    "guarantee_text",
    "provider_missing_at",
    "disabled_by_sync",
}


def _like_escape(text: str) -> str:
    """تعطيل أحرف LIKE الخاصة (`%` و`_` و`\\`) حتى يُبحث عنها كنص عادي مع `ESCAPE '\\'`."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ServicesRepository(BaseRepository):
    """عمليات قراءة وكتابة الخدمات."""

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, service_id: int) -> Service | None:
        """جلب خدمة بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM services WHERE id = ?", (service_id,))
        return Service.from_row(row)

    async def get_available(self, service_id: int) -> Service | None:
        """جلب خدمة متاحة للطلب فقط (مفعّلة وغير مؤرشفة)."""
        row = await self.db.fetchone(
            "SELECT * FROM services WHERE id = ? AND is_active = 1 AND is_archived = 0", (service_id,)
        )
        return Service.from_row(row)

    async def list_by_category(
        self, category_id: int, *, only_available: bool = True, limit: int = 8, offset: int = 0
    ) -> list[Service]:
        """قائمة خدمات تصنيف معين مع ترقيم صفحات."""
        sql = "SELECT * FROM services WHERE category_id = ?"
        params: list[Any] = [category_id]
        if only_available:
            sql += " AND is_active = 1 AND is_archived = 0"
        sql += " ORDER BY sort_order, id LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = await self.db.fetchall(sql, params)
        return Service.from_rows(rows)

    async def count_by_category(self, category_id: int, *, only_available: bool = True) -> int:
        """عدد خدمات تصنيف (لحساب عدد الصفحات)."""
        where = "category_id = ?"
        if only_available:
            where += " AND is_active = 1 AND is_archived = 0"
        return await self.count("services", where, (category_id,))

    async def find_by_provider_service(self, provider_id: int, provider_service_id: str) -> Service | None:
        """البحث عن خدمة مرتبطة بمعرف خدمة معين عند المزود (يُستخدم في المزامنة)."""
        row = await self.db.fetchone(
            "SELECT * FROM services WHERE provider_id = ? AND provider_service_id = ?",
            (provider_id, str(provider_service_id)),
        )
        return Service.from_row(row)

    async def list_by_provider(self, provider_id: int, *, limit: int = 50, offset: int = 0) -> list[Service]:
        """خدمات مزود معين."""
        rows = await self.db.fetchall(
            "SELECT * FROM services WHERE provider_id = ? ORDER BY id LIMIT ? OFFSET ?",
            (provider_id, limit, offset),
        )
        return Service.from_rows(rows)

    async def list_all_by_provider(self, provider_id: int) -> list[Service]:
        """كل خدمات مزود بلا سقف (المزامنة يجب أن ترى الكتالوج كاملاً مهما كبر)، مرتّبة بالمعرّف."""
        rows = await self.db.fetchall(
            "SELECT * FROM services WHERE provider_id = ? ORDER BY id", (provider_id,)
        )
        return Service.from_rows(rows)

    async def count_by_provider(self, provider_id: int) -> int:
        """عدد خدمات مزود (لترقيم الصفحات في بطاقة المزود)."""
        return await self.count("services", "provider_id = ?", (provider_id,))

    async def search(self, text: str, *, limit: int = 10) -> list[Service]:
        """بحث نصي في أسماء الخدمات (الأحرف الخاصة `%` و`_` تُعامل كنص عادي)."""
        pattern = f"%{_like_escape(text.strip())}%"
        rows = await self.db.fetchall(
            "SELECT * FROM services WHERE name LIKE ? ESCAPE '\\' ORDER BY id LIMIT ?", (pattern, limit)
        )
        return Service.from_rows(rows)

    @staticmethod
    def _admin_search_clause(tokens: list[str], numeric: int | None, exact: bool) -> tuple[str, list[Any]]:
        """
        شرط بحث الأدمن: كل كلمة يجب أن تطابق (اسم الخدمة أو القسم أو المزود أو معرّف المزود للخدمة).

        إن كان الاستعلام رقماً صرفاً ووُجدت مطابقة تامة لمعرّف الخدمة عندنا أو لمعرّف المزود (`exact`)
        فالبحث يقتصر على المطابقة التامة؛ فلا يغرق «#12» بكل خدمة يحوي معرّفها أو اسمها «12».
        """
        conditions: list[str] = []
        params: list[Any] = []
        for token in tokens:
            pattern = f"%{_like_escape(token)}%"
            conditions.append(
                "(s.name LIKE ? ESCAPE '\\' OR c.name_ar LIKE ? ESCAPE '\\' OR c.name_en LIKE ? ESCAPE '\\' "
                "OR p.name LIKE ? ESCAPE '\\' OR s.provider_service_id LIKE ? ESCAPE '\\')"
            )
            params.extend([pattern] * 5)
        clause = " AND ".join(conditions) if conditions else "0"
        if numeric is not None and exact:
            return "(s.id = ? OR s.provider_service_id = ?)", [numeric, str(numeric)]
        return clause, params

    async def has_exact_id(self, number: int) -> bool:
        """هل يطابق الرقم معرّف خدمة عندنا أو معرّف خدمة لدى مزود بالضبط؟"""
        row = await self.db.fetchone(
            "SELECT 1 FROM services WHERE id = ? OR provider_service_id = ? LIMIT 1", (number, str(number))
        )
        return row is not None

    async def admin_search(
        self, tokens: list[str], *, numeric: int | None = None, exact: bool = False, limit: int = 8, offset: int = 0
    ) -> list[Service]:
        """
        بحث الأدمن (كل الخدمات بما فيها المعطّلة والمؤرشفة): اسم/قسم/مزود/معرّف المزود/معرّف الخدمة.

        الترتيب: المطابقة التامة لمعرّف الخدمة أولاً ثم لمعرّف المزود ثم بحسب المعرّف.
        """
        clause, params = self._admin_search_clause(tokens, numeric, exact)
        order = "ORDER BY s.id"
        order_params: list[Any] = []
        if numeric is not None:
            order = "ORDER BY (s.id = ?) DESC, (s.provider_service_id = ?) DESC, s.id"
            order_params = [numeric, str(numeric)]
        rows = await self.db.fetchall(
            f"""
            SELECT s.* FROM services s
              JOIN service_categories c ON c.id = s.category_id
              JOIN providers p ON p.id = s.provider_id
             WHERE {clause}
             {order} LIMIT ? OFFSET ?
            """,
            (*params, *order_params, limit, offset),
        )
        return Service.from_rows(rows)

    async def admin_search_count(self, tokens: list[str], *, numeric: int | None = None, exact: bool = False) -> int:
        """عدد نتائج بحث الأدمن (لترقيم الصفحات)."""
        clause, params = self._admin_search_clause(tokens, numeric, exact)
        row = await self.db.fetchone(
            f"""
            SELECT COUNT(*) AS n FROM services s
              JOIN service_categories c ON c.id = s.category_id
              JOIN providers p ON p.id = s.provider_id
             WHERE {clause}
            """,
            params,
        )
        return int(row["n"]) if row else 0

    async def count_active(self) -> int:
        """عدد الخدمات المتاحة حالياً."""
        return await self.count("services", "is_active = 1 AND is_archived = 0")

    async def has_orders(self, service_id: int) -> bool:
        """هل توجد طلبات مرتبطة بهذه الخدمة؟ (يمنع الحذف الفعلي)."""
        row = await self.db.fetchone("SELECT 1 FROM orders WHERE service_id = ? LIMIT 1", (service_id,))
        return row is not None

    async def negative_margin_services(self, provider_id: int | None = None) -> list[Service]:
        """الخدمات التي أصبح سعر بيعها أقل من تكلفتها (تحذير بعد مزامنة الأسعار)، ولمزود بعينه إن حُدّد."""
        provider_clause = "" if provider_id is None else "AND provider_id = ?"
        rows = await self.db.fetchall(
            f"""
            SELECT * FROM services
             WHERE provider_price_per_1000_units IS NOT NULL
               AND price_per_1000_units < provider_price_per_1000_units
               AND is_archived = 0 {provider_clause}
             ORDER BY id
            """,
            () if provider_id is None else (provider_id,),
        )
        return Service.from_rows(rows)

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        category_id: int,
        provider_id: int,
        provider_service_id: str,
        name: str,
        price_per_1000_units: int,
        min_quantity: int,
        max_quantity: int,
        description: str | None = None,
        provider_price_per_1000_units: int | None = None,
        service_type: str = "default",
        link_pattern: str | None = None,
        avg_time_text: str | None = None,
        sort_order: int = 100,
        link_rule: str | None = None,
        speed_text: str | None = None,
        quality_text: str | None = None,
        guarantee_text: str | None = None,
    ) -> Service:
        """إضافة خدمة جديدة (مع حقول العرض: قاعدة الرابط والسرعة والجودة والضمان)."""
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO services (category_id, provider_id, provider_service_id, name, description,
                                  service_type, price_per_1000_units, provider_price_per_1000_units,
                                  min_quantity, max_quantity, link_pattern, avg_time_text,
                                  sort_order, created_at, updated_at,
                                  link_rule, speed_text, quality_text, guarantee_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                category_id, provider_id, str(provider_service_id), name, description,
                service_type, price_per_1000_units, provider_price_per_1000_units,
                min_quantity, max_quantity, link_pattern, avg_time_text, sort_order, now, now,
                link_rule, speed_text, quality_text, guarantee_text,
            ),
        )
        row = await tx.fetchone("SELECT * FROM services WHERE id = ?", (result.lastrowid,))
        service = Service.from_row(row)
        assert service is not None
        return service

    async def update_fields(self, tx: Tx, service_id: int, **fields: Any) -> bool:
        """تعديل حقول مسموح بها للخدمة."""
        return await self._update_by_id(tx, "services", service_id, fields, _ALLOWED_FIELDS)

    async def change_price(
        self,
        tx: Tx,
        service_id: int,
        *,
        new_price_units: int,
        new_min: int | None = None,
        new_max: int | None = None,
        changed_by: int | None = None,
        source: str = "admin",
    ) -> bool:
        """
        تغيير سعر أو حدود خدمة مع تسجيل التغيير في سجل الأسعار.

        السبب: الحاجة لتفسير محاسبي لأي فرق سعر بين الطلبات القديمة والجديدة.
        """
        current = await tx.fetchone(
            "SELECT price_per_1000_units, min_quantity, max_quantity FROM services WHERE id = ?",
            (service_id,),
        )
        if current is None:
            return False

        fields: dict[str, Any] = {"price_per_1000_units": new_price_units}
        if new_min is not None:
            fields["min_quantity"] = new_min
        if new_max is not None:
            fields["max_quantity"] = new_max
        updated = await self._update_by_id(tx, "services", service_id, fields, _ALLOWED_FIELDS)
        if not updated:
            return False

        await tx.execute(
            """
            INSERT INTO service_price_history (service_id, old_price_units, new_price_units,
                                               old_min, new_min, old_max, new_max,
                                               changed_by, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                service_id,
                current["price_per_1000_units"],
                new_price_units,
                current["min_quantity"],
                new_min if new_min is not None else current["min_quantity"],
                current["max_quantity"],
                new_max if new_max is not None else current["max_quantity"],
                changed_by,
                source,
                self.now(),
            ),
        )
        return True

    async def set_active(self, tx: Tx, service_id: int, active: bool) -> bool:
        """
        تفعيل أو تعطيل خدمة بقرار بشري/إداري؛ يمسح علامة «عطّلتها المزامنة» لتصبح القرار النهائي للأدمن
        (فلا تعيد المزامنة تفعيل ما عطّله يدوياً، ولا تعطّل ما فعّله يدوياً بلا سبب جديد).
        """
        return await self._update_by_id(
            tx, "services", service_id,
            {"is_active": 1 if active else 0, "disabled_by_sync": 0},
            _ALLOWED_FIELDS,
        )

    async def disable_by_sync(self, tx: Tx, service_id: int) -> bool:
        """تعطيل خدمة اختفت من قائمة المزود (تُميَّز بعلامة لتعود تلقائياً إن عادت)."""
        return await self._update_by_id(
            tx, "services", service_id,
            {"is_active": 0, "disabled_by_sync": 1, "provider_missing_at": self.now()},
            _ALLOWED_FIELDS,
        )

    async def archive(self, tx: Tx, service_id: int) -> bool:
        """أرشفة خدمة (حذف ناعم): تُخفى عن المستخدمين ويبقى تاريخها سليماً."""
        return await self._update_by_id(
            tx, "services", service_id, {"is_archived": 1, "is_active": 0}, _ALLOWED_FIELDS
        )

    async def price_history(self, service_id: int, limit: int = 10) -> list[dict]:
        """آخر تغييرات السعر لخدمة."""
        rows = await self.db.fetchall(
            "SELECT * FROM service_price_history WHERE service_id = ? ORDER BY id DESC LIMIT ?",
            (service_id, limit),
        )
        return [dict(row) for row in rows]
```

---

## `texts/ar.py`

```python
"""
نصوص الواجهة العربية — مصدر واحد لكل ما يراه المستخدم على الشاشة.

لماذا مركزية؟
    نفس العبارة تتكرر في عدة شاشات؛ وجودها في مكان واحد يمنع التناقض،
    ويجعل تعديل الصياغة (أو إضافة لغة ثانية لاحقاً) تعديلاً في ملف واحد.

تقسيم المسؤولية:
    • `texts/ar.py`        : نصوص الشاشات والأزرار والرسائل الفورية (هذا الملف).
    • `texts/templates.py` : نصوص الإشعارات المرسلة عبر صندوق الإشعارات.
"""

from __future__ import annotations

# ============================ أزرار عامة ============================== #

BTN_BACK = "🔙 رجوع"
BTN_HOME = "🏠 القائمة الرئيسية"
BTN_CANCEL = "❌ إلغاء"
BTN_CONFIRM = "✅ تأكيد"
BTN_SKIP = "⏭ تخطي"
BTN_PREV = "⬅️ السابق"
BTN_NEXT = "التالي ➡️"
BTN_REFRESH = "🔄 تحديث"

# ========================= القائمة الرئيسية =========================== #

BTN_SERVICES = "🛍 الخدمات"
BTN_WALLET = "💰 المحفظة"
BTN_ORDERS = "📦 طلباتي"
BTN_SUPPORT = "🎫 الدعم"
BTN_ACCOUNT = "👤 حسابي"
BTN_INFO = "ℹ️ معلومات"

MAIN_MENU_TITLE = "القائمة الرئيسية"

WELCOME_NEW = (
    "👋 أهلاً بك {name}!\n\n"
    "{welcome}\n\n"
    "استخدم الأزرار بالأسفل للتنقل. رصيدك الحالي: <b>{balance}</b>"
)
WELCOME_BACK = "👋 أهلاً بعودتك {name}\n\nرصيدك الحالي: <b>{balance}</b>"

START_NEW = (
    "{welcome}\n"
    "👤 <b>{name}</b>\n\n"
    "🚀 <b>ابدأ بخطوتين:</b> اشحن رصيدك من 💰 المحفظة، ثم اختر خدمتك من 🛍 الخدمات.\n\n"
)
START_BACK = "👋 أهلاً بعودتك <b>{name}</b>\n\n"

MAIN_MENU_BODY = (
    "🏠 <b>القائمة الرئيسية</b>\n\n"
    "💰 الرصيد: <b>{balance}</b>\n"
    "📦 طلبات نشطة: <b>{active_orders}</b>\n"
    "🎫 تذاكر مفتوحة: <b>{open_tickets}</b>\n\n"
    "اختر ما تريد:"
)

# ========================= الاشتراك الإجباري ========================== #

SUB_GATE_TITLE = (
    "📢 <b>الاشتراك مطلوب</b>\n\n"
    "للاستفادة من البوت اشترك في القنوات التالية ثم اضغط «✅ تحقق من الاشتراك»:\n\n"
)
SUB_LINE_OK = "✅ {title}"
SUB_LINE_MISSING = "❌ {title}"
SUB_LINE_UNKNOWN = "⚠️ {title} — تعذّر التحقق منها حالياً"
SUB_GATE_UNVERIFIABLE_NOTE = (
    "\n\n⚠️ تعذّر التحقق من بعض القنوات (مشكلة عند الإدارة أو في الاتصال). "
    "حاول بعد قليل، وإن استمر الأمر فأبلغ الدعم."
)
SUB_BTN_JOIN = "➕ {title}"
SUB_BTN_CHECK = "✅ تحقق من الاشتراك"
SUB_CHECK_FAILED = "لم يكتمل اشتراكك بعد: {names}"
SUB_CHECK_UNVERIFIED = "تعذّر التحقق الآن، حاول بعد قليل."
SUB_CHECK_OK = "✅ تم التحقق — أهلاً بك!"

# ============================== الخدمات =============================== #

CATEGORIES_TITLE = "🛍 <b>اختر التصنيف</b>\n\nاختر المنصة التي تريد خدمة لها:"
CATEGORIES_EMPTY = "📭 لا توجد خدمات متاحة حالياً.\nتابعنا لاحقاً — يجري تجهيز الخدمات."
SERVICES_TITLE = "{emoji} <b>{category}</b>\n\nالصفحة {page} من {pages} — اختر خدمة:"
SERVICES_EMPTY = "📭 لا توجد خدمات في هذا التصنيف حالياً."

SERVICE_CARD = (
    "📄 <b>{name}</b>\n"
    "🆔 رقم الخدمة: <b>#{service_id}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "💵 السعر لكل 1000: <b>{usd}</b>\n"
    "💴 ما يعادل: <b>{local}</b>\n"
    "💱 سعر الصرف: 1$ = {rate} {symbol}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🚀 السرعة: {speed}\n"
    "💎 الجودة: {quality}\n"
    "🛡 الضمان: {guarantee}\n"
    "🔢 الحد الأدنى: <b>{min_quantity}</b>\n"
    "🔢 الحد الأقصى: <b>{max_quantity}</b>\n"
    "{description}"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "💰 رصيدك: <b>{balance}</b>"
)
BTN_ORDER_NOW = "🛒 طلب"
BTN_FAV_ADD = "⭐ مفضلة"
BTN_FAV_REMOVE = "★ إزالة من المفضلة"
AVG_TIME_UNKNOWN = "غير محددة"
FIELD_UNSET = "غير محددة"

# ============================== المفضلة ============================== #

FAVORITES_TITLE = "⭐ <b>مفضلتي</b>\n\nالصفحة {page} من {pages} — اختر خدمة:"
FAVORITES_EMPTY = (
    "⭐ <b>مفضلتي</b>\n\nلا توجد خدمات في المفضلة بعد.\n"
    "افتح أي خدمة واضغط «⭐ مفضلة» لتصلها أسرع لاحقاً."
)
FAVORITE_ADDED = "⭐ أُضيفت إلى المفضلة"
FAVORITE_EXISTS = "هذه الخدمة في مفضلتك مسبقاً"
FAVORITE_REMOVED = "أُزيلت من المفضلة"
FAVORITE_NOT_FOUND = "هذه الخدمة ليست في مفضلتك"
FAVORITE_LIMIT = "وصلت للحد الأقصى للمفضلة ({limit} خدمة). أزل بعضها أولاً."
BTN_FAVORITES = "⭐ المفضلة"

# ============================ مسار الطلب ============================== #

ORDER_LINK_HINT_GENERIC = "أرسل الرابط كرسالة نصية (مثال: https://instagram.com/username)."
ORDER_LINK_HINT_RULE = "أرسل رابط <b>{label}</b> كرسالة نصية.\nمثال: <code>{example}</code>"
ORDER_ASK_LINK = (
    "🔗 <b>أرسل رابط الهدف</b>\n\n"
    "الخدمة: {service}\n\n"
    "{hint}\n"
    "يمكنك الإلغاء في أي لحظة."
)
ORDER_ASK_QUANTITY = (
    "🔢 <b>أرسل الكمية المطلوبة</b>\n\n"
    "الخدمة: {service}\n"
    "الرابط: {link}\n\n"
    "الكمية المسموحة من <b>{min_quantity}</b> إلى <b>{max_quantity}</b>."
)
ORDER_SUMMARY = (
    "🧾 <b>ملخص الطلب</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📄 الخدمة: {service}\n"
    "🔗 الرابط: {link}\n"
    "🔢 الكمية: <b>{quantity}</b>\n"
    "💵 التكلفة: <b>{cost}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "💰 رصيدك الحالي: {balance}\n"
    "💰 رصيدك بعد الطلب: <b>{balance_after}</b>\n\n"
    "اضغط تأكيد لإنشاء الطلب."
)
ORDER_SUMMARY_NO_BALANCE = (
    "🧾 <b>ملخص الطلب</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📄 الخدمة: {service}\n"
    "🔗 الرابط: {link}\n"
    "🔢 الكمية: <b>{quantity}</b>\n"
    "💵 التكلفة: <b>{cost}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "💰 رصيدك: {balance}\n"
    "❌ <b>الناقص: {missing}</b>\n\n"
    "اشحن رصيدك ثم أعد الطلب."
)
BTN_DEPOSIT_NOW = "➕ شحن الرصيد"
ORDER_CREATED = (
    "✅ <b>تم إنشاء طلبك</b>\n\n"
    "🔖 رقم الطلب: <b>{code}</b>\n"
    "📄 الخدمة: {service}\n"
    "🔢 الكمية: {quantity}\n"
    "💵 المخصوم: {cost}\n"
    "💰 رصيدك الآن: {balance}\n\n"
    "سيُرسل الطلب إلى المزود خلال لحظات، وستصلك إشعارات بتقدمه."
)
ORDER_CANCELLED_FLOW = "❌ تم إلغاء العملية. لم يُخصم أي مبلغ."

# ============================== طلباتي ================================ #

ORDERS_TITLE = "📦 <b>طلباتي</b> — {filter_name}\n\nالصفحة {page} من {pages}"
ORDERS_EMPTY = "📭 لا توجد طلبات ضمن هذا التصنيف."
FILTER_ALL = "الكل"
FILTER_ACTIVE = "نشطة"
FILTER_COMPLETED = "مكتملة"
FILTER_REFUNDED = "مسترجعة"

ORDER_CARD = (
    "📦 <b>الطلب {code}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📄 الخدمة: {service}\n"
    "🔗 الرابط: {link}\n"
    "🔢 الكمية: {quantity}\n"
    "{progress}"
    "💵 التكلفة: {cost}\n"
    "{refund}"
    "📊 الحالة: <b>{status}</b>\n"
    "🕒 التاريخ: {created}\n"
    "{error}"
)
ORDER_PROGRESS_LINE = "📈 المنفَّذ: {delivered} — المتبقي: {remains}\n"
ORDER_REFUND_LINE = "↩️ المسترجع: {refund}\n"
ORDER_ERROR_LINE = "⚠️ ملاحظة: {error}\n"
BTN_ORDER_CANCEL = "🛑 إلغاء الطلب"
BTN_ORDER_TICKET = "🎫 فتح تذكرة عن الطلب"
ORDER_CANCEL_CONFIRM = (
    "🛑 <b>تأكيد إلغاء الطلب {code}</b>\n\n"
    "سيُعاد المبلغ <b>{cost}</b> إلى رصيدك فوراً.\n"
    "هل أنت متأكد؟"
)
ORDER_CANCEL_DONE = "✅ أُلغي الطلب {code} وأُعيد إليك <b>{refund}</b>."

# ============================== المحفظة =============================== #

WALLET_TITLE = (
    "💰 <b>محفظتي</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "💵 الرصيد الحالي: <b>{balance}</b>\n"
    "📥 إجمالي الإيداع: {deposited}\n"
    "📤 إجمالي الإنفاق: {spent}\n"
    "━━━━━━━━━━━━━━━━━━━━"
)
BTN_WALLET_HISTORY = "📜 سجل العمليات"
BTN_MY_DEPOSITS = "🧾 طلبات الشحن"
HISTORY_TITLE = "📜 <b>سجل العمليات</b>\n\nالصفحة {page} من {pages}\n━━━━━━━━━━━━━━━━━━━━\n{lines}"
HISTORY_EMPTY = "📭 لا توجد عمليات بعد."

# ============================== الشحن ================================= #

DEPOSIT_METHODS_TITLE = (
    "➕ <b>شحن الرصيد</b>\n\n"
    "اختر طريقة التحويل المناسبة لك:"
)
DEPOSIT_METHODS_EMPTY = (
    "⚠️ لا توجد طرق شحن مفعّلة حالياً.\n"
    "تواصل مع الدعم الفني وسنفعّلها في أقرب وقت."
)
DEPOSIT_ASK_AMOUNT = (
    "💵 <b>{method}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{instructions}\n"
    "{account}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{limits}\n"
    "{fee_line}"
    "\nأرسل <b>المبلغ الذي حوّلته</b> كرقم."
)
#: يظهر فقط للطرق التي لها رسوم (وعندما يسمح الإعداد بإظهارها)
DEPOSIT_FEE_NOTICE = "🧾 رسوم هذه الطريقة: {fee} — تُخصم من المبلغ المحوَّل.\n"
DEPOSIT_ASK_REFERENCE = (
    "🧾 أرسل <b>رقم عملية التحويل</b> كما يظهر في إشعار الحوالة.\n\n"
    "المبلغ: {amount}"
)
DEPOSIT_ASK_PROOF = (
    "📸 أرسل <b>صورة الإيصال</b> (اختياري).\n\n"
    "يمكنك الضغط على «تخطي» إذا كان رقم العملية كافياً."
)
DEPOSIT_SUMMARY = (
    "🧾 <b>مراجعة طلب الشحن</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🏦 الطريقة: {method}\n"
    "💵 المبلغ المحوَّل: <b>{amount}</b>\n"
    "{fee_lines}"
    "🔢 رقم العملية: {reference}\n"
    "📸 الإيصال: {proof}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "سيراجع الفريق طلبك ويُضاف الرصيد بعد الاعتماد."
)
#: سطرا الرسوم والصافي داخل المراجعة وإشعار الاستلام
DEPOSIT_FEE_LINES = "🧾 رسوم الطريقة: {fee}\n💰 سيُضاف لرصيدك: <b>{net}</b>\n"
DEPOSIT_PROOF_ATTACHED = "مرفقة ✅"
DEPOSIT_PROOF_NONE = "بدون صورة"
DEPOSIT_CREATED = (
    "✅ <b>استلمنا طلب الشحن #{payment_id}</b>\n\n"
    "💵 المبلغ المحوَّل: {amount}\n"
    "{fee_lines}"
    "📊 الحالة: قيد المراجعة\n\n"
    "سيصلك إشعار فور اعتماده أو رفضه."
)
DEPOSITS_TITLE = "🧾 <b>طلبات الشحن</b>\n\n{lines}"
DEPOSITS_EMPTY = "📭 لا توجد طلبات شحن سابقة."
BTN_DEPOSIT_CANCEL = "🛑 إلغاء الطلب"
DEPOSIT_CANCELLED = "✅ أُلغي طلب الشحن #{payment_id}."

# ============================== الدعم ================================= #

SUPPORT_TITLE = (
    "🎫 <b>الدعم الفني</b>\n\n"
    "تذاكرك المفتوحة: <b>{open_count}</b>\n\n"
    "يمكنك فتح تذكرة واحدة في كل مرة، وسنرد عليك في أقرب وقت."
)
BTN_TICKET_NEW = "➕ تذكرة جديدة"
BTN_TICKETS_LIST = "📂 تذاكري"
TICKETS_TITLE = "📂 <b>تذاكري</b>\n\nالصفحة {page} من {pages}"
TICKETS_EMPTY = "📭 لا توجد تذاكر بعد."
TICKET_ASK_CATEGORY = "🗂 <b>تذكرة جديدة</b>\n\nاختر تصنيف المشكلة:"
TICKET_ASK_SUBJECT = "✏️ أرسل <b>عنواناً مختصراً</b> للمشكلة (3 أحرف على الأقل)."
TICKET_ASK_MESSAGE = "📝 اشرح مشكلتك بالتفصيل في رسالة واحدة."
TICKET_ASK_MESSAGE_ORDER = (
    "🎫 <b>تذكرة بخصوص الطلب {code}</b>\n"
    "📦 {service}\n\n"
    "📝 اشرح المشكلة بالتفصيل في رسالة واحدة."
)
TICKET_CREATED = (
    "✅ <b>تم فتح التذكرة #{ticket_id}</b>\n\n"
    "📌 الموضوع: {subject}\n\n"
    "سيصلك إشعار عند رد فريق الدعم."
)
TICKET_CARD = (
    "🎫 <b>التذكرة #{ticket_id}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📌 الموضوع: {subject}\n"
    "🗂 التصنيف: {category}\n"
    "📊 الحالة: <b>{status}</b>\n"
    "🕒 آخر تحديث: {updated}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{messages}"
)
TICKET_MESSAGE_LINE = "{icon} <b>{sender}</b> — {time}\n{text}\n"
BTN_TICKET_REPLY = "💬 إضافة رد"
BTN_TICKET_CLOSE = "✖️ إغلاق التذكرة"
TICKET_ASK_REPLY = "💬 أرسل ردك على التذكرة #{ticket_id}."
TICKET_REPLY_SENT = "✅ أُرسل ردك إلى فريق الدعم."
TICKET_CLOSED_BY_USER = "✅ أُغلقت التذكرة #{ticket_id}. شكراً لك."
TICKET_CATEGORIES: dict[str, str] = {
    "order": "📦 مشكلة في طلب",
    "payment": "💳 مشكلة في الشحن",
    "service": "🛍 استفسار عن خدمة",
    "account": "👤 مشكلة في الحساب",
    "other": "📝 موضوع آخر",
}

# ============================== الحساب ================================ #

ACCOUNT_CARD = (
    "👤 <b>حسابي</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🆔 المعرف: <code>{telegram_id}</code>\n"
    "👤 الاسم: {name}\n"
    "🏷 النوع: {role}\n"
    "💰 الرصيد: <b>{balance}</b>\n"
    "📦 الطلبات: {orders_count} (نشطة: {active_orders})\n"
    "🧾 طلبات الشحن: {payments_count}\n"
    "🎫 تذاكر مفتوحة: {tickets_open}\n"
    "📅 تاريخ الانضمام: {joined}\n"
    "━━━━━━━━━━━━━━━━━━━━"
)
BTN_NOTIFICATIONS = "🔔 إشعاراتي"
NOTIFICATIONS_TITLE = "🔔 <b>إشعاراتي</b>\n\nغير مقروء: <b>{unread}</b>\nالصفحة {page} من {pages}\n━━━━━━━━━━━━━━━━━━━━\n{lines}"
NOTIFICATIONS_EMPTY = "📭 لا توجد إشعارات."
BTN_MARK_ALL_READ = "✅ تعليم الكل كمقروء"
MARKED_READ = "✅ عُلّمت {count} إشعاراً كمقروء."

ROLE_LABELS: dict[str, str] = {
    "user": "عميل",
    "support": "دعم فني",
    "admin": "مشرف",
    "super_admin": "مشرف أعلى",
}

# ============================== معلومات =============================== #

INFO_TITLE = (
    "ℹ️ <b>{bot_name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{rules}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📞 للتواصل مع الدعم: {support}\n"
    "🔖 الإصدار: {version}"
)
INFO_NO_RULES = "لم تُضف شروط استخدام بعد."
INFO_NO_SUPPORT = "استخدم زر 🎫 الدعم داخل البوت."

# ======================== رسائل فورية وأخطاء ========================== #

ERR_GENERIC = "⚠️ حدث خطأ غير متوقع. تم تسجيل المشكلة وسنعالجها."
ERR_TELEGRAM_TEMP = "📡 تعذّر الاتصال بتيليجرام لحظياً. بياناتك محفوظة — أعد المحاولة بعد قليل (وإن كنت أرسلت طلباً فراجع «📦 طلباتي» قبل تكراره)."
ERR_OLD_BUTTON = "⚠️ هذا الزر من نسخة قديمة. اضغط /start لفتح القائمة المحدثة."
ERR_FLOW_STALE = "ℹ️ انتهت هذه العملية أو أُنجزت أصلاً. اضغط /start أو راجع «📦 طلباتي» للتأكد."
ORDER_ALREADY_CREATED = "✅ طلبك مسجَّل أصلاً برقم {code} — لا حاجة لتأكيده مرة ثانية. تتبّعه من «📦 طلباتي»."
ERR_UNKNOWN_BUTTON = "⚠️ زر غير معروف. اضغط /start للعودة إلى القائمة."
ERR_SESSION_LOST = "⚠️ انتهت الجلسة. ابدأ من جديد عبر /start."
ERR_NOT_TEXT = "⚠️ أرسل رسالة نصية من فضلك."
ERR_RATE_LIMITED = "⏳ أبطئ قليلاً — أرسلت طلبات كثيرة خلال وقت قصير."
ERR_RATE_BLOCKED = (
    "🚫 تم إيقاف استخدامك للبوت مؤقتاً لمدة {minutes} دقيقة بسبب كثرة الطلبات المتكررة.\n"
    "ستعود الخدمة تلقائياً بعد انتهاء المدة."
)
CONVERSATION_TIMED_OUT = (
    "⌛ انتهت الجلسة بسبب عدم النشاط وأُلغيت العملية الجارية حفاظاً على أمان حسابك.\n"
    "ابدأ من جديد من القائمة."
)
ERR_NO_PRIVATE = "ℹ️ هذا البوت يعمل في المحادثة الخاصة فقط."
UNKNOWN_COMMAND = "❓ أمر غير معروف. اضغط /start لعرض القائمة."
UNKNOWN_TEXT = "💡 استخدم الأزرار للتنقل، أو اضغط /start لعرض القائمة."
CANCELLED = "❌ أُلغيت العملية."
LOADING = "⏳ لحظة من فضلك..."
PAGE_INFO = "📄 الصفحة {page} من {pages}"
HELP_TEXT = (
    "🤖 <b>كيف أستخدم البوت؟</b>\n\n"
    "1️⃣ اشحن رصيدك من 💰 المحفظة ← ➕ شحن الرصيد\n"
    "2️⃣ اختر خدمة من 🛍 الخدمات\n"
    "3️⃣ أرسل الرابط والكمية ثم أكّد\n"
    "4️⃣ تابع التنفيذ من 📦 طلباتي\n\n"
    "الأوامر المتاحة:\n"
    "/start — القائمة الرئيسية\n"
    "/help — هذه الرسالة\n"
    "/cancel — إلغاء العملية الحالية\n"
    "/id — عرض معرفك في تيليجرام"
)
ID_TEXT = "🆔 معرفك في تيليجرام: <code>{telegram_id}</code>"
```

---

## `tests/telegram_fakes.py`

```python
"""
بدائل اختبارية لواجهة تيليجرام (بلا أي اتصال بالشبكة).

الفكرة: نستخدم كائنات `telegram.Update` **حقيقية** (مبنية عبر `de_json`) حتى
نختبر نفس المسارات التي تعمل في الإنتاج، لكن مع بوت مزيّف يسجّل ما كان
سيُرسَل بدل إرساله. هكذا يفحص الاختبار النص النهائي والأزرار الفعلية.
"""

from __future__ import annotations

from types import SimpleNamespace

import itertools
import time
from dataclasses import dataclass, field
from typing import Any

from telegram import InlineKeyboardMarkup, Update

#: عدّاد معرفات التحديثات حتى لا يتكرر رقم داخل اختبار واحد
_update_ids = itertools.count(1000)

#: معرف البوت المزيّف
BOT_ID = 999_000_111


@dataclass
class SentMessage:
    """رسالة مسجّلة (أُرسلت أو عُدِّلت) مع نصها وأزرارها."""

    kind: str                       # "send" أو "edit"
    chat_id: int | None
    text: str
    markup: InlineKeyboardMarkup | None
    kwargs: dict[str, Any] = field(default_factory=dict)

    @property
    def buttons(self) -> list[str]:
        """كل `callback_data` الموجودة في اللوحة المرافقة."""
        if self.markup is None:
            return []
        return [
            button.callback_data
            for row in self.markup.inline_keyboard
            for button in row
            if button.callback_data
        ]

    @property
    def labels(self) -> list[str]:
        """نصوص الأزرار كما يراها المستخدم."""
        if self.markup is None:
            return []
        return [button.text for row in self.markup.inline_keyboard for button in row]


class FakeMessage:
    """ردّ مبسّط يحاكي `Message` المُعاد من تيليجرام بعد الإرسال."""

    def __init__(self, message_id: int, chat_id: int, text: str) -> None:
        """تهيئة الرسالة المزيّفة بالحد الأدنى من الحقول المستخدمة."""
        self.message_id = message_id
        self.chat_id = chat_id
        self.text = text


class FakeBot:
    """
    بوت مزيّف يسجّل كل نداء بدل الاتصال بتيليجرام.

    يدعم فقط ما تستخدمه الواجهة فعلاً: الإرسال، التحرير، الرد على الأزرار،
    وإرسال الصور — وأي نداء آخر يرفع `AttributeError` واضحاً بدل الصمت.
    """

    def __init__(self) -> None:
        """تهيئة البوت المزيّف بسجلات فارغة."""
        self.sent: list[SentMessage] = []
        self.answers: list[dict[str, Any]] = []
        self.id = BOT_ID
        self.username = "fake_bot"
        self._message_ids = itertools.count(1)
        self.deleted: list[tuple[int, int]] = []
        #: عضويات القنوات: (chat_id, user_id) ⇒ حالة العضوية؛ غير الموجود ⇒ «User not found» (غير مشترك)
        self.memberships: dict[tuple[Any, int], str] = {}
        #: أخطاء تُرفع عند `get_chat_member` لقناة بعينها (استثناء جاهز)
        self.member_errors: dict[Any, BaseException] = {}
        self.member_calls: list[tuple[Any, int]] = []
        #: نتائج `get_chat` لوجهات بعينها (كائن أو استثناء)
        self.chats: dict[Any, Any] = {}
        #: أعطال مبرمجة لكل عملية ("send" | "edit" | "answer" | "photo" | "document"): (استثناء، هل وصلت فعلاً؟)
        #: `delivered=True` يحاكي مهلة قراءة بعد أن نفّذ تيليجرام الطلب (الحالة الغامضة)
        self.faults: dict[str, list[tuple[BaseException, bool]]] = {}
        #: عدد محاولات كل عملية (ناجحة أو فاشلة)
        self.attempts: dict[str, int] = {}

    def fail(self, operation: str, error: BaseException, *, times: int = 1, delivered: bool = False) -> None:
        """برمجة فشل `times` محاولة قادمة للعملية (يُرفع `error` ويُسجَّل الأثر إن كان `delivered`)."""
        self.faults.setdefault(operation, []).extend([(error, delivered)] * times)

    def _fault(self, operation: str) -> tuple[BaseException, bool] | None:
        """عدّ المحاولة وإرجاع العطل المبرمج التالي (إن وُجد)."""
        self.attempts[operation] = self.attempts.get(operation, 0) + 1
        queue = self.faults.get(operation)
        return queue.pop(0) if queue else None

    # ------------------------------ الإرسال ------------------------------ #

    async def send_message(
        self, chat_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None, **kwargs: Any
    ) -> FakeMessage:
        """تسجيل رسالة جديدة وإرجاع كائن يشبه رسالة تيليجرام."""
        fault = self._fault("send")
        if fault is not None:
            if fault[1]:
                self.sent.append(SentMessage("send", chat_id, text, reply_markup, kwargs))
            raise fault[0]
        self.sent.append(SentMessage("send", chat_id, text, reply_markup, kwargs))
        return FakeMessage(next(self._message_ids), chat_id, text)

    async def edit_message_text(
        self,
        text: str,
        chat_id: int | None = None,
        message_id: int | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
        **kwargs: Any,
    ) -> FakeMessage:
        """تسجيل تحرير رسالة قائمة (هذا هو المسار الطبيعي للتنقل بين الشاشات)."""
        fault = self._fault("edit")
        if fault is not None:
            if fault[1]:
                self.sent.append(SentMessage("edit", chat_id, text, reply_markup, kwargs))
            raise fault[0]
        self.sent.append(SentMessage("edit", chat_id, text, reply_markup, kwargs))
        return FakeMessage(message_id or 0, chat_id or 0, text)

    async def send_photo(self, chat_id: int, photo: Any, caption: str = "", **kwargs: Any) -> FakeMessage:
        """تسجيل إرسال صورة (يُستخدم في إشعارات الإثباتات لاحقاً)."""
        self.sent.append(SentMessage("photo", chat_id, caption, kwargs.get("reply_markup"), kwargs))
        return FakeMessage(next(self._message_ids), chat_id, caption)

    async def send_document(
        self, chat_id: int, document: Any, caption: str = "", **kwargs: Any
    ) -> FakeMessage:
        """تسجيل إرسال مستند (إثبات دفع مرفوع كملف في لوحة الأدمن)."""
        self.sent.append(
            SentMessage("document", chat_id, caption, kwargs.get("reply_markup"), {**kwargs, "document": document})
        )
        return FakeMessage(next(self._message_ids), chat_id, caption)

    async def answer_callback_query(
        self, callback_query_id: str, text: str | None = None, show_alert: bool = False, **kwargs: Any
    ) -> bool:
        """تسجيل الرد على ضغطة زر (إزالة مؤشر الانتظار)."""
        fault = self._fault("answer")
        if fault is not None:
            raise fault[0]
        self.answers.append({"id": callback_query_id, "text": text, "alert": show_alert})
        return True

    async def delete_message(self, chat_id: int, message_id: int, **kwargs: Any) -> bool:
        """تسجيل حذف رسالة (تنظيف المحادثة عند /start)."""
        self.deleted.append((chat_id, message_id))
        return True

    async def get_chat_member(self, chat_id: Any, user_id: int, **kwargs: Any) -> Any:
        """عضوية قابلة للبرمجة: خطأ مبرمج للقناة، وإلا حالة من `memberships`، وإلا «User not found»."""
        from telegram.error import BadRequest

        self.member_calls.append((chat_id, user_id))
        if chat_id in self.member_errors:
            raise self.member_errors[chat_id]
        status = self.memberships.get((chat_id, user_id))
        if status is None:
            raise BadRequest("User not found")
        return SimpleNamespace(status=status, is_member=status == "restricted", can_post_messages=True)

    async def get_chat(self, chat_id: Any, **kwargs: Any) -> Any:
        """بيانات محادثة مبرمجة (استثناء يُرفع، أو كائن يُعاد)."""
        result = self.chats.get(chat_id)
        if isinstance(result, BaseException):
            raise result
        if result is None:
            from telegram.error import BadRequest

            raise BadRequest("Chat not found")
        return result

    async def get_me(self, **kwargs: Any) -> Any:
        """هوية البوت (للتحقق من عضويته في القنوات)."""
        return SimpleNamespace(id=self.id, username=self.username)

    # ------------------------------ مساعدات ------------------------------ #

    @property
    def last(self) -> SentMessage:
        """آخر رسالة أُرسلت أو عُدِّلت."""
        if not self.sent:
            raise AssertionError("لم تُرسل أي رسالة بعد")
        return self.sent[-1]

    @property
    def texts(self) -> list[str]:
        """نصوص كل الرسائل المسجَّلة."""
        return [message.text for message in self.sent]

    def clear(self) -> None:
        """تفريغ السجلات بين خطوات الاختبار."""
        self.sent.clear()
        self.answers.clear()


class FakeApplication:
    """تطبيق مزيّف يحمل `bot_data` فقط (ما تحتاجه المعالجات)."""

    def __init__(self, bot: FakeBot, services: Any) -> None:
        """تهيئة التطبيق المزيّف بحاوية الخدمات."""
        self.bot = bot
        self.bot_data: dict[str, Any] = {"services": services}


class FakeContext:
    """سياق مزيّف يحاكي `ContextTypes.DEFAULT_TYPE` بالقدر الذي تستخدمه الواجهة."""

    def __init__(self, bot: FakeBot, services: Any) -> None:
        """تهيئة السياق ببوت وخدمات وذاكرة مستخدم فارغة."""
        self.bot = bot
        self.application = FakeApplication(bot, services)
        self.bot_data = self.application.bot_data
        self.user_data: dict[str, Any] = {}
        self.chat_data: dict[str, Any] = {}
        self.error: BaseException | None = None


def make_message_update(
    bot: FakeBot, *, text: str, user_id: int, chat_id: int | None = None, photo: bool = False
) -> Update:
    """
    بناء تحديث رسالة نصية حقيقي (أو صورة عند `photo=True`).

    المدخلات:
        text    : نص الرسالة (أو التعليق مع الصورة).
        user_id : معرف المستخدم في تيليجرام.
    """
    chat = chat_id if chat_id is not None else user_id
    message: dict[str, Any] = {
        "message_id": next(bot._message_ids),
        "date": int(time.time()),
        "chat": {"id": chat, "type": "private"},
        "from": {"id": user_id, "is_bot": False, "first_name": "Tester"},
    }
    if photo:
        message["photo"] = [
            {"file_id": "photo-file-id", "file_unique_id": "uniq", "width": 90, "height": 90}
        ]
        if text:
            message["caption"] = text
    else:
        message["text"] = text
        if text.startswith("/"):
            # تيليجرام يرفق كيان bot_command مع الأوامر — بدونه لا يلتقطها CommandHandler
            command = text.split()[0]
            message["entities"] = [
                {"type": "bot_command", "offset": 0, "length": len(command)}
            ]
    payload = {"update_id": next(_update_ids), "message": message}
    return Update.de_json(payload, bot)


def make_callback_update(
    bot: FakeBot, *, data: str, user_id: int, chat_id: int | None = None, message_id: int = 555
) -> Update:
    """بناء تحديث ضغطة زر حقيقي يحمل `callback_data` المطلوب."""
    chat = chat_id if chat_id is not None else user_id
    payload = {
        "update_id": next(_update_ids),
        "callback_query": {
            "id": f"cb-{next(_update_ids)}",
            "chat_instance": "test-instance",
            "data": data,
            "from": {"id": user_id, "is_bot": False, "first_name": "Tester"},
            "message": {
                "message_id": message_id,
                "date": int(time.time()),
                "chat": {"id": chat, "type": "private"},
                "from": {"id": BOT_ID, "is_bot": True, "first_name": "Bot", "username": "fake_bot"},
                "text": "شاشة سابقة",
            },
        },
    }
    return Update.de_json(payload, bot)
```

---

## `tests/integration/test_phase14_sync_search.py`

```python
"""
المرحلة الثانية (v1.0.1) — بند 17 (مزامنة الخدمات) وبند 18 (بحث الأدمن مع آلاف الخدمات).

    مزامنة: خدمات جديدة · تغيّر التكلفة · تغيّر الحدود · اختفاء/عودة · حماية العطل · سعر البيع ثابت ·
            تاريخ الطلبات سليم · كتالوج >1000 خدمة · ذرّية المعاملة · نص التقرير ضمن حد تيليجرام.
    بحث:    معرّف الخدمة · معرّف المزود · اسم · قسم · مزود · عدة كلمات · محارف LIKE الخاصة · ترقيم · أداء 10 آلاف.
"""

from __future__ import annotations

import time

import pytest

from core.enums import OrderStatus
from core.exceptions import PermissionDeniedError, ValidationError
from handlers.admin import catalog as admin_catalog
from handlers.admin import providers as admin_providers
from integrations.providers.base import ProviderServiceItem
from keyboards.callback_data import NS_ADM_CAT, pack
from tests.integration.test_user_interface import bot, context, load_user, press, write  # noqa: F401,F811
from utils.datetime_utils import iso_plus_seconds

pytestmark = pytest.mark.asyncio


def _item(psid, *, rate=6_000, lo=100, hi=100_000, name=None, service_type="default"):
    """عنصر من قائمة المزود."""
    return ProviderServiceItem(
        provider_service_id=str(psid),
        name=name or f"Provider service {psid}",
        rate_per_1000_units=rate,
        min_quantity=lo,
        max_quantity=hi,
        service_type=service_type,
    )


async def _bulk_services(db, repos, provider, count, *, start=1000, name="Bulk service"):
    """إدراج عدد كبير من الخدمات دفعة واحدة (بدل استيراد كل خدمة عبر الخدمة)."""
    category = (await repos.categories.list_all())[0]
    stamp = "2026-01-01T00:00:00.000Z"
    async with db.transaction() as tx:
        for index in range(count):
            await tx.execute(
                "INSERT INTO services (category_id, provider_id, provider_service_id, name, price_per_1000_units,"
                " provider_price_per_1000_units, min_quantity, max_quantity, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (category.id, provider.id, str(start + index), f"{name} {start + index}", 10_000, 6_000, 100, 100_000, stamp, stamp),
            )


# ============================== مزامنة (17) ============================== #


async def test_sync_updates_cost_and_limits_but_never_the_selling_price(services, repos, super_admin, mock_provider, mock_service) -> None:
    """تغيّر التكلفة والحدود لدى المزود ⇒ يتحدثان؛ سعر البيع كما هو؛ التقرير يحمل القديم والجديد والهامش."""
    report = await services.catalog.sync_provider_services(
        super_admin, provider_id=mock_provider.id, items=[_item(555, rate=7_500, lo=50, hi=20_000)]
    )
    after = await repos.services.get(mock_service.id)
    assert after.price_per_1000_units == mock_service.price_per_1000_units == 10_000      # سعر البيع ثابت
    assert after.provider_price_per_1000_units == 7_500
    assert (after.min_quantity, after.max_quantity) == (50, 20_000)
    assert report.updated == 1 and report.unchanged == 0
    change = report.cost_changes[0]
    assert (change.old_cost_units, change.new_cost_units, change.new_margin_units) == (6_000, 7_500, 2_500)
    assert [s.id for s in report.limit_changes] == [mock_service.id]
    row = await repos.settings.db.fetchone("SELECT before_json, after_json FROM audit_logs WHERE action = 'services.sync'")
    assert str(mock_service.id) in row["before_json"] and "7500" in row["after_json"]


async def test_sync_with_identical_data_changes_nothing_and_writes_no_audit(services, repos, super_admin, mock_provider, mock_service) -> None:
    """مزامنة بلا فروق ⇒ unchanged=1 ولا سجل تدقيق ولا كتابة."""
    report = await services.catalog.sync_provider_services(
        super_admin, provider_id=mock_provider.id, items=[_item(555, rate=6_000, lo=100, hi=100_000)]
    )
    assert (report.updated, report.unchanged, report.missing, report.new_items) == (0, 1, [], [])
    row = await repos.settings.db.fetchone("SELECT COUNT(*) AS n FROM audit_logs WHERE action = 'services.sync'")
    assert row["n"] == 0


async def test_sync_reports_new_provider_services_without_importing_them(services, repos, super_admin, mock_provider, mock_service) -> None:
    """الجديد لدى المزود يُبلَّغ به (المدعوم فقط) ولا يُستورد آلياً."""
    items = [_item(555), _item(900, name="New followers"), _item(901, name="Custom comments", service_type="custom_comments")]
    report = await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=items)
    assert [i.provider_service_id for i in report.new_items] == ["900"]
    assert await repos.services.find_by_provider_service(mock_provider.id, "900") is None


async def test_missing_service_is_disabled_not_deleted_and_orders_history_survives(
    services, repos, db, user, super_admin, mock_provider, mock_service, mock_client
) -> None:
    """اختفاء الخدمة ⇒ تعطيل بعلامة (لا حذف)؛ الطلب القائم يكمل دورته والتاريخ والسعر كما هي."""
    await services.wallet.adjust_balance(target=user, amount_units=100_000, admin=super_admin, reason="رصيد", credit=True)
    order = await services.orders.create_order(user, service_id=mock_service.id, link="https://instagram.com/keep", quantity=1000)
    before = await repos.orders.get(order.id)

    report = await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=[_item(777)])
    assert [s.id for s in report.disabled_missing] == [mock_service.id]
    gone = await repos.services.get(mock_service.id)
    assert gone.is_active == 0 and gone.disabled_by_sync == 1 and gone.provider_missing_at
    assert gone.price_per_1000_units == 10_000
    assert await repos.services.get_available(mock_service.id) is None            # لا يُباع للعملاء

    same = await repos.orders.get(order.id)                                      # الطلب لم يُمسّ
    assert (same.status, same.cost_units, same.service_id, same.quantity) == (before.status, before.cost_units, before.service_id, before.quantity)
    await services.orders.process_pending_orders()                                # ويكمل دورته
    submitted = await repos.orders.get(order.id)
    assert submitted.status == OrderStatus.SUBMITTED
    mock_client.advance(submitted.provider_order_id, to="Completed")
    async with db.transaction() as tx:
        await tx.execute("UPDATE orders SET next_check_at = ? WHERE id = ?", (iso_plus_seconds(-30), order.id))
    await services.orders.process_due_orders()
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED
    assert (await repos.services.get(mock_service.id)).is_archived == 0


async def test_service_that_reappears_is_restored_but_manual_disable_is_respected(services, repos, db, super_admin, mock_provider, mock_service) -> None:
    """عودة الخدمة تعيد تفعيلها تلقائياً فقط إن كانت المزامنة هي من عطّلها؛ التعطيل اليدوي يبقى."""
    await _bulk_services(db, repos, mock_provider, 1, start=2000, name="Manual")
    manual = await repos.services.find_by_provider_service(mock_provider.id, "2000")
    await services.catalog.set_service_active(super_admin, manual.id, False)       # تعطيل يدوي

    await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=[_item(9999)])
    assert (await repos.services.get(mock_service.id)).disabled_by_sync == 1
    assert (await repos.services.get(manual.id)).disabled_by_sync == 0              # اليدوي بلا علامة

    report = await services.catalog.sync_provider_services(
        super_admin, provider_id=mock_provider.id, items=[_item(555), _item(2000)]
    )
    assert [s.id for s in report.restored] == [mock_service.id]
    back = await repos.services.get(mock_service.id)
    assert back.is_active == 1 and back.disabled_by_sync == 0 and back.provider_missing_at is None
    assert (await repos.services.get(manual.id)).is_active == 0                     # بقي معطّلاً يدوياً


async def test_admin_manual_enable_overrides_sync_flag(services, repos, super_admin, mock_provider, mock_service) -> None:
    """إن فعّل الأدمن خدمة عطّلتها المزامنة ⇒ تُمسح العلامة (القرار البشري هو الأخير)."""
    await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=[_item(1)])
    await services.catalog.set_service_active(super_admin, mock_service.id, True)
    current = await repos.services.get(mock_service.id)
    assert current.is_active == 1 and current.disabled_by_sync == 0


async def test_empty_provider_list_is_treated_as_outage_not_deletion(services, repos, super_admin, mock_provider, mock_service) -> None:
    """قائمة فارغة من المزود ⇒ عطل: لا يُعطَّل شيء ويُعلَّم التقرير."""
    report = await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=[])
    assert report.missing_suspicious and report.disabled_missing == []
    assert (await repos.services.get(mock_service.id)).is_active == 1


async def test_mass_disappearance_is_treated_as_outage(services, repos, db, super_admin, mock_provider) -> None:
    """اختفاء أكثر من نصف 12 خدمة دفعة واحدة ⇒ عطل؛ واختفاء القليل ⇒ تعطيل عادي."""
    await _bulk_services(db, repos, mock_provider, 12)
    keep = [_item(1000 + i) for i in range(5)]
    report = await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=keep)
    assert report.missing_suspicious and len(report.missing) == 7 and report.disabled_missing == []

    keep = [_item(1000 + i) for i in range(10)]                                      # اختفاء خدمتين فقط
    report = await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=keep)
    assert not report.missing_suspicious and len(report.disabled_missing) == 2
    assert await repos.services.count_active() == 10


async def test_auto_disable_can_be_switched_off(services, repos, super_admin, mock_provider, mock_service) -> None:
    """مع إيقاف الإعداد: تُدرج المفقودة في التقرير فقط ولا تُعطَّل."""
    await services.settings.set("sync_auto_disable_missing", "false", admin_id=super_admin.id)
    report = await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=[_item(1)])
    assert [s.id for s in report.missing] == [mock_service.id] and report.disabled_missing == []
    assert (await repos.services.get(mock_service.id)).is_active == 1


async def test_type_change_to_unsupported_disables_without_touching_price(services, repos, super_admin, mock_provider, mock_service) -> None:
    """تغيّر النوع لدى المزود إلى غير default ⇒ تعطيل وعدم تحديث تكلفته."""
    report = await services.catalog.sync_provider_services(
        super_admin, provider_id=mock_provider.id, items=[_item(555, rate=9_999, service_type="custom_comments")]
    )
    assert [s.id for s in report.unsupported] == [mock_service.id]
    after = await repos.services.get(mock_service.id)
    assert after.is_active == 0 and after.provider_price_per_1000_units == 6_000


async def test_sync_handles_a_catalog_larger_than_1000_services(services, repos, db, super_admin, mock_provider) -> None:
    """كتالوج 1500 خدمة: كلها تُفحص وتُحدَّث (كان السقف الصامت 1000)، وبزمن معقول."""
    await _bulk_services(db, repos, mock_provider, 1500)
    items = [_item(1000 + i, rate=6_500) for i in range(1500)]
    started = time.perf_counter()
    report = await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=items)
    elapsed = time.perf_counter() - started
    assert report.checked == 1500 and report.updated == 1500 and len(report.cost_changes) == 1500
    assert report.missing == [] and elapsed < 15
    row = await db.fetchone("SELECT COUNT(*) AS n FROM services WHERE provider_price_per_1000_units = 6500")
    assert row["n"] == 1500
    assert len(await services.catalog.services_of_provider(super_admin, mock_provider.id)) == 1500


async def test_sync_is_atomic_when_a_write_fails_midway(services, repos, db, super_admin, mock_provider, monkeypatch) -> None:
    """فشل أثناء المزامنة ⇒ لا تحديث جزئي (معاملة واحدة)."""
    await _bulk_services(db, repos, mock_provider, 5)
    original = repos.services.update_fields
    calls = {"n": 0}

    async def flaky(tx, service_id, **fields):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("boom")
        return await original(tx, service_id, **fields)

    monkeypatch.setattr(repos.services, "update_fields", flaky)
    with pytest.raises(RuntimeError):
        await services.catalog.sync_provider_services(
            super_admin, provider_id=mock_provider.id, items=[_item(1000 + i, rate=8_000) for i in range(5)]
        )
    row = await db.fetchone("SELECT COUNT(*) AS n FROM services WHERE provider_price_per_1000_units = 8000")
    assert row["n"] == 0


async def test_sync_requires_the_sync_permission(services, user, mock_provider, mock_service) -> None:
    """مستخدم عادي لا يزامن."""
    with pytest.raises(PermissionDeniedError):
        await services.catalog.sync_provider_services(user, provider_id=mock_provider.id, items=[_item(555)])


async def test_negative_margin_after_sync_is_reported_for_that_provider_only(services, repos, super_admin, mock_provider, mock_service) -> None:
    """تكلفة صارت فوق سعر البيع ⇒ تُدرج في تحذير الهامش السالب (والسعر لا يُعدَّل)."""
    report = await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=[_item(555, rate=12_000)])
    assert [s.id for s in report.negative_margin] == [mock_service.id]
    assert (await repos.services.get(mock_service.id)).price_per_1000_units == 10_000


async def test_sync_report_text_stays_under_telegram_limit_and_shows_every_category(services, repos, db, super_admin, mock_provider) -> None:
    """مئات التغييرات ⇒ نص التقرير مقتطع ضمن 4096 حرفاً ويحوي الفئات (تكلفة/جديدة/معطّلة)."""
    await _bulk_services(db, repos, mock_provider, 300)
    items = [_item(1000 + i, rate=7_000) for i in range(280)] + [_item(5000 + i, name="X" * 60) for i in range(40)]
    report = await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=items)
    text = admin_providers.sync_report_text(mock_provider.name, report, "﷼")
    assert len(text) < 4096
    for needle in ("تغيّرت تكلفتها", "خدمات جديدة لدى المزود", "و275 أخرى", "جديدة لدى المزود (لم تُستورد): 40"):
        assert needle in text
    assert report.missing_suspicious is False and len(report.disabled_missing) == 20
    assert "عُطِّلت لاختفائها" in text


async def test_sync_button_end_to_end_through_the_handler(bot, context, super_admin, mock_provider, mock_service, mock_client) -> None:  # noqa: F811
    """زر «مزامنة الخدمات»: يجلب قائمة Mock (555/556) ويعرض التقرير بالجديد (556) دون استيراده."""
    await load_user(bot, context, super_admin)
    await press(bot, context, admin_providers.sync_provider, pack("pv", "sync", mock_provider.id), super_admin.telegram_id)
    text = " ".join(m.text or "" for m in bot.sent)
    assert "نتيجة المزامنة" in text and "جديدة لدى المزود (لم تُستورد): 1" in text and "556" in text


# ============================== بحث الأدمن (18) ============================== #


async def _seed_search(services, repos, db, super_admin, mock_provider):
    """مجموعة خدمات متنوعة: أسماء/أقسام/معرّفات مزود، مع معطّلة ومؤرشفة."""
    cat_ig = (await repos.categories.list_all())[0]
    async with db.transaction() as tx:
        cat_tt = await repos.categories.create(tx, name_ar="تيك توك", emoji="🎵")
    rows = [
        ("2511", "Instagram Followers Fast", cat_ig.id),
        ("2512", "Instagram Likes", cat_ig.id),
        ("3001", "TikTok Views 100%", cat_tt.id),
        ("3002", "TikTok_Likes", cat_tt.id),
    ]
    async with db.transaction() as tx:
        for psid, name, category_id in rows:
            await tx.execute(
                "INSERT INTO services (category_id, provider_id, provider_service_id, name, price_per_1000_units,"
                " min_quantity, max_quantity, created_at, updated_at) VALUES (?,?,?,?,10000,10,1000,'2026-01-01','2026-01-01')",
                (category_id, mock_provider.id, psid, name),
            )
    return {psid: await repos.services.find_by_provider_service(mock_provider.id, psid) for psid, *_ in rows}, cat_ig, cat_tt


async def test_admin_search_by_every_key(services, repos, db, super_admin, mock_provider) -> None:
    """معرّف الخدمة (مع #) · معرّف المزود · الاسم · القسم · المزود · عدة كلمات."""
    found, cat_ig, cat_tt = await _seed_search(services, repos, db, super_admin, mock_provider)

    async def ids(term):
        return [s.provider_service_id for s in (await services.catalog.admin_search_services(super_admin, term)).items]

    assert await ids(f"#{found['2511'].id}") == ["2511"]
    assert await ids(str(found["3001"].id)) == ["3001"]
    assert await ids("2512") == ["2512"]                                    # معرّف المزود
    assert await ids("followers") == ["2511"]                               # اسم (غير حساس لحالة الأحرف)
    assert await ids("تيك") == ["3001", "3002"]                             # اسم القسم
    assert await ids(mock_provider.name) == ["2511", "2512", "3001", "3002"]  # اسم المزود
    assert await ids("tiktok likes") == ["3002"]                            # كل الكلمات يجب أن تتحقق
    assert await ids("tiktok followers") == []                              # كلمة غائبة ⇒ لا نتيجة
    assert await ids("tiktok views") == ["3001"]
    assert await ids("instagram likes") == ["2512"]
    assert await ids("zzzz-nothing") == []


async def test_admin_search_numeric_prefers_exact_matches_and_falls_back_to_text(services, repos, db, super_admin, mock_provider) -> None:
    """رقم يطابق معرّف خدمة ⇒ المطابقة التامة وحدها؛ رقم بلا مطابقة تامة ⇒ بحث نصي (اسم يحوي الرقم)."""
    found, *_ = await _seed_search(services, repos, db, super_admin, mock_provider)
    target = found["2512"]
    async with db.transaction() as tx:
        await tx.execute("UPDATE services SET name = ? WHERE id = ?", (f"Package {target.id} deluxe", found["2511"].id))
    page = await services.catalog.admin_search_services(super_admin, str(target.id))
    assert [s.id for s in page.items] == [target.id]                          # لا يغرق بالنتائج الجزئية
    async with db.transaction() as tx:
        await tx.execute("UPDATE services SET name = 'Package 8888 deluxe' WHERE id = ?", (found["2511"].id,))
    fallback = await services.catalog.admin_search_services(super_admin, "8888")
    assert [s.id for s in fallback.items] == [found["2511"].id]


async def test_admin_search_includes_disabled_and_archived_and_treats_wildcards_literally(services, repos, db, super_admin, mock_provider) -> None:
    """الأدمن يرى المعطّلة والمؤرشفة، و`%`/`_` نص عادي لا أحرف بدل."""
    found, *_ = await _seed_search(services, repos, db, super_admin, mock_provider)
    await services.catalog.set_service_active(super_admin, found["2511"].id, False)
    async with db.transaction() as tx:
        await repos.services.archive(tx, found["2512"].id)
    page = await services.catalog.admin_search_services(super_admin, "instagram")
    assert {s.provider_service_id for s in page.items} == {"2511", "2512"}
    assert [s.provider_service_id for s in (await services.catalog.admin_search_services(super_admin, "100%")).items] == ["3001"]
    assert [s.provider_service_id for s in (await services.catalog.admin_search_services(super_admin, "tok_")).items] == ["3002"]
    assert (await services.catalog.admin_search_services(super_admin, "tok_v")).items == []   # _ ليس حرف بدل
    assert (await services.catalog.admin_search_services(super_admin, "%%")).items == []     # لا يطابق كل شيء
    assert (await services.catalog.admin_search_services(super_admin, "a_b")).items == []


async def test_admin_search_validation_permission_and_pagination(services, repos, db, user, super_admin, mock_provider) -> None:
    """نص قصير يُرفض، العادي ممنوع، والصفحات تعمل (والصفحة الزائدة تُقصّ لآخر صفحة)."""
    with pytest.raises(ValidationError):
        await services.catalog.admin_search_services(super_admin, "a")
    with pytest.raises(PermissionDeniedError):
        await services.catalog.admin_search_services(user, "followers")
    await _bulk_services(db, repos, mock_provider, 23)
    first = await services.catalog.admin_search_services(super_admin, "Bulk service", page=1, page_size=8)
    third = await services.catalog.admin_search_services(super_admin, "Bulk service", page=3, page_size=8)
    beyond = await services.catalog.admin_search_services(super_admin, "Bulk service", page=99, page_size=8)
    assert (first.total_items, first.total_pages, len(first.items)) == (23, 3, 8)
    assert len(third.items) == 7 and beyond.page == 3
    seen = {s.id for p in (first, await services.catalog.admin_search_services(super_admin, "Bulk service", page=2, page_size=8), third) for s in p.items}
    assert len(seen) == 23                                                   # لا تكرار ولا فقد بين الصفحات


async def test_admin_search_is_fast_with_ten_thousand_services(services, repos, db, super_admin, mock_provider) -> None:
    """10 آلاف خدمة: كل أنواع البحث تنتهي بزمن قصير والنتائج صحيحة."""
    await _bulk_services(db, repos, mock_provider, 10_000, start=100_000)
    target = await repos.services.find_by_provider_service(mock_provider.id, "107777")
    timings = {}
    for label, term, expected_total in (
        ("by_id", str(target.id), 1),
        ("by_psid", "107777", 1),
        ("by_name", "Bulk service 107777", 1),
        ("by_text", "Bulk service", 10_000),
        ("two_words", "bulk 1077", 101),
    ):
        started = time.perf_counter()
        page = await services.catalog.admin_search_services(super_admin, term)
        timings[label] = time.perf_counter() - started
        assert page.total_items == expected_total, label
    assert max(timings.values()) < 1.0, timings


# ----------------------------- واجهة البحث ----------------------------- #


async def test_search_button_flow_results_pagination_and_open_card(bot, context, db, repos, super_admin, mock_provider) -> None:  # noqa: F811
    """الزر ⇐ سؤال ⇐ نتائج بأزرار ⇐ صفحة ثانية ⇐ فتح بطاقة خدمة."""
    await _bulk_services(db, repos, mock_provider, 15)
    await load_user(bot, context, super_admin)
    state = await press(bot, context, admin_catalog.start_search, pack(NS_ADM_CAT, "find"), super_admin.telegram_id)
    assert state == admin_catalog.ASK_SEARCH_TERM and "بحث عن خدمة" in bot.last.text
    await write(bot, context, admin_catalog.receive_search_term, "bulk service", super_admin.telegram_id)
    assert "العدد: 15" in bot.last.text and "الصفحة 1 من" in bot.last.text
    service_buttons = [b for b in bot.last.buttons if b.startswith("ac:svc:")]
    assert len(service_buttons) >= 5 and pack(NS_ADM_CAT, "find") in bot.last.buttons

    await press(bot, context, admin_catalog.search_page_screen, pack(NS_ADM_CAT, "found", 2), super_admin.telegram_id)
    assert "الصفحة 2 من" in bot.last.text
    await press(bot, context, admin_catalog.service_card_screen, service_buttons[0], super_admin.telegram_id)
    assert "Bulk service" in bot.last.text


async def test_search_button_empty_short_and_expired_cases(bot, context, super_admin, mock_provider, mock_service) -> None:  # noqa: F811
    """لا نتائج ⇒ رسالة واضحة؛ نص قصير ⇒ تبقى الخطوة؛ صفحة بلا بحث محفوظ ⇒ انتهت الصلاحية."""
    await load_user(bot, context, super_admin)
    await press(bot, context, admin_catalog.start_search, pack(NS_ADM_CAT, "find"), super_admin.telegram_id)
    state = await write(bot, context, admin_catalog.receive_search_term, "x", super_admin.telegram_id)
    assert state is None and "حرفين" in bot.last.text
    await write(bot, context, admin_catalog.receive_search_term, "nothing-here", super_admin.telegram_id)
    assert "لا نتائج" in bot.last.text
    context.user_data.pop(admin_catalog.SEARCH_TERM_KEY, None)
    await press(bot, context, admin_catalog.search_page_screen, pack(NS_ADM_CAT, "found", 2), super_admin.telegram_id)
    assert "انتهت صلاحية" in bot.last.text


async def test_provider_services_screen_paginates_beyond_1000(bot, context, db, repos, super_admin, mock_provider) -> None:  # noqa: F811
    """بطاقة «خدماتنا من المزود» تعرض العدد الكلي الصحيح (1200) وتصفح بلا سقف."""
    await _bulk_services(db, repos, mock_provider, 1200)
    await load_user(bot, context, super_admin)
    await press(bot, context, admin_providers.provider_services_screen, pack("pv", "svcs", mock_provider.id, 2), super_admin.telegram_id)
    assert "العدد: 1200" in bot.last.text and "الصفحة 2 من" in bot.last.text
```

---

## `tests/integration/test_phase14_orders.py`

```python
"""
المرحلة الثانية (v1.0.1) — بند 14: منع الطلبات المكررة، وبند 15: دورة الطلب الناجحة الكاملة.

    14: ضغط مزدوج (تسلسلي ومتزامن) · إعادة بنفس المفتاح بعد Timeout · محادثة جديدة بمحتوى مطابق ·
        إعادة الإرسال للمزود · إلغاء مزدوج ⇒ لا خصم/استرجاع مرتين ولا طلب ثانٍ ولا رسالة تُكتب فوق الإيصال.
    15: pending → submitting → submitted → in_progress → completed بكل أثرها (حالات، سجل، مال، إشعارات، مزود).
"""

from __future__ import annotations

import asyncio

import pytest
from telegram.error import TimedOut

from core.enums import OrderStatus, TransactionType
from core.exceptions import DuplicateOperationError
from handlers.common import fallbacks
from handlers.user import order_flow
from keyboards.callback_data import pack
from tests.integration.test_user_interface import bot, context, load_user, press, write  # noqa: F401,F811
from utils import telegram_retry
from utils.datetime_utils import iso_plus_seconds

pytestmark = pytest.mark.asyncio

LINK = "https://instagram.com/p/phase14"


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """إعادة محاولة تيليجرام بلا انتظار حقيقي في الاختبارات."""
    monkeypatch.setattr(telegram_retry, "RETRY_DELAYS", (0.0, 0.0))


async def _fund(services, user, super_admin, units=100_000):
    """شحن رصيد عبر المسار الرسمي."""
    await services.wallet.adjust_balance(target=user, amount_units=units, admin=super_admin, reason="رصيد", credit=True)


async def _flow_until_summary(bot, context, user, service, *, link=LINK, quantity="1000"):  # noqa: F811
    """بدء محادثة الطلب حتى شاشة التأكيد."""
    await press(bot, context, order_flow.start_order, pack("new", "start", service.id), user.telegram_id)
    await write(bot, context, order_flow.receive_link, link, user.telegram_id)
    await write(bot, context, order_flow.receive_quantity, quantity, user.telegram_id)


async def _count(db, sql, params=()):
    """عدّ صفوف."""
    return (await db.fetchone(sql, params))["n"]


async def _due(db, order_id):
    """تقديم موعد الفحص."""
    async with db.transaction() as tx:
        await tx.execute("UPDATE orders SET next_check_at = ? WHERE id = ?", (iso_plus_seconds(-30), order_id))


# ============================ 14 — منع التكرار ============================ #


async def test_concurrent_confirms_with_same_key_create_one_order_and_one_charge(services, db, user, super_admin, mock_service) -> None:
    """عشر ضغطات متزامنة بنفس مفتاح الطلب ⇒ طلب واحد وخصم واحد وإشعار إنشاء واحد."""
    await _fund(services, user, super_admin)
    results = await asyncio.gather(
        *[services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="same-key") for _ in range(10)],
        return_exceptions=True,
    )
    orders = [r for r in results if not isinstance(r, BaseException)]
    assert len({o.id for o in orders}) == 1, results
    assert await _count(db, "SELECT COUNT(*) AS n FROM orders") == 1
    assert await _count(db, "SELECT COUNT(*) AS n FROM transactions WHERE type = ?", (TransactionType.ORDER,)) == 1
    assert await services.wallet.balance_units(user.id) == 90_000
    assert await _count(db, "SELECT COUNT(*) AS n FROM notifications WHERE type = 'order_created'") == 1


async def test_concurrent_identical_orders_with_different_keys_only_one_succeeds(services, db, user, super_admin, mock_service) -> None:
    """محادثتان مختلفتان (مفتاحان) بمحتوى مطابق وبالتزامن ⇒ الأولى تنجح والثانية تُرفض كمكررة؛ خصم واحد."""
    await _fund(services, user, super_admin)
    results = await asyncio.gather(
        services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="k1"),
        services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="k2"),
        return_exceptions=True,
    )
    assert sum(isinstance(r, DuplicateOperationError) for r in results) == 1
    assert await _count(db, "SELECT COUNT(*) AS n FROM orders") == 1
    assert await services.wallet.balance_units(user.id) == 90_000


async def test_retry_with_same_key_after_success_returns_same_order_without_charging(services, repos, db, user, super_admin, mock_service) -> None:
    """إعادة نفس المفتاح بعد النجاح (مثلاً بعد Timeout) تعيد الطلب الأول ولا تخصم ولا تُرفض كمكررة."""
    await _fund(services, user, super_admin)
    first = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="retry-1")
    again = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="retry-1")
    assert again.id == first.id and await services.wallet.balance_units(user.id) == 90_000
    # ولو تغيّر الرصيد بين المحاولتين (أُنفق في طلب آخر) تبقى الإعادة آمنة
    await services.orders.create_order(user, service_id=mock_service.id, link=LINK + "2", quantity=1000, client_request_id="other")
    third = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="retry-1")
    assert third.id == first.id and await services.wallet.balance_units(user.id) == 80_000
    assert await _count(db, "SELECT COUNT(*) AS n FROM orders") == 2


async def test_new_flow_with_identical_content_is_blocked_inside_window_only(services, repos, db, user, super_admin, mock_service) -> None:
    """نفس (الخدمة+الرابط+الكمية) ضمن النافذة يُرفض؛ بعدها أو مع اختلاف أي عنصر أو إلغاء الأول أو إغلاق النافذة يُقبل."""
    await _fund(services, user, super_admin, 500_000)
    first = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="a")
    with pytest.raises(DuplicateOperationError):
        await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="b")
    await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1001, client_request_id="c")      # كمية مختلفة
    await services.orders.create_order(user, service_id=mock_service.id, link=LINK + "x", quantity=1000, client_request_id="d")  # رابط مختلف
    assert await _count(db, "SELECT COUNT(*) AS n FROM orders") == 3

    other, _ = await services.users.get_or_create(telegram_id=555_000_999, first_name="Other")
    await _fund(services, other, super_admin)
    await services.orders.create_order(other, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="e")      # مستخدم آخر

    async with db.transaction() as tx:                                           # خارج النافذة
        await tx.execute("UPDATE orders SET created_at = ? WHERE id = ?", (iso_plus_seconds(-3 * 3600), first.id))
    await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="f")

    await services.orders.cancel_by_user(user, first.id)                         # إلغاء الأقدم لا يهم؛ ألغِ الأحدث المطابق
    latest = (await services.orders.list_for_user(user, limit=1))[0]
    await services.orders.cancel_by_user(user, latest.id)
    await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="g")      # المطابق السابق أُلغي

    await services.settings.set("duplicate_order_window_minutes", "0", admin_id=super_admin.id)
    await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000, client_request_id="h")      # النافذة مغلقة
    check = await services.wallet.verify_ledger(user.id)
    assert check.is_balanced and check.stored_units >= 0


async def test_ui_timeout_after_order_creation_does_not_lose_or_duplicate(bot, context, services, db, user, super_admin, mock_service) -> None:  # noqa: F811
    """
    انقطاع تيليجرام لحظة عرض إيصال الطلب (TimedOut ×3): الطلب يبقى واحداً، المحادثة تُنهى، الإشعار في الصندوق،
    وإعادة المحاولة اللاحقة بنفس المحتوى لا تخصم ثانية.
    """
    await _fund(services, user, super_admin)
    await load_user(bot, context, user)
    await _flow_until_summary(bot, context, user, mock_service)
    bot.fail("edit", TimedOut("Read timeout"), times=3, delivered=False)       # المحاولة الأولى + إعادتان
    state = await press(bot, context, order_flow.confirm_order, pack("flow", "confirm"), user.telegram_id)
    assert state == order_flow.ConversationHandler.END
    assert order_flow.FLOW_KEY not in context.user_data                          # لا حالة معلّقة
    assert await _count(db, "SELECT COUNT(*) AS n FROM orders") == 1
    assert await services.wallet.balance_units(user.id) == 90_000
    # الإيصال وصل عبر صندوق الإشعارات الدائم رغم تعذّر الشاشة
    sent = []

    async def sender(telegram_id, title, message):
        sent.append((telegram_id, message))
        return 1

    await services.notifications.dispatch_pending(sender, limit=50)
    assert any("تم إنشاء" in message or "طلب" in message for _, message in sent)

    # المستخدم يعيد الطلب من الصفر بنفس المحتوى ⇒ مرفوض كمكرر لا خصم ثانٍ
    bot.clear()
    await _flow_until_summary(bot, context, user, mock_service)
    await press(bot, context, order_flow.confirm_order, pack("flow", "confirm"), user.telegram_id)
    assert "لديك طلب مطابق" in " ".join(m.text for m in bot.sent)
    assert await _count(db, "SELECT COUNT(*) AS n FROM orders") == 1
    assert await services.wallet.balance_units(user.id) == 90_000


async def test_double_tap_on_confirm_never_overwrites_the_receipt(bot, context, services, db, user, super_admin, mock_service) -> None:  # noqa: F811
    """الضغطة الثانية (زر قديم بعد انتهاء المحادثة): تنبيه منبثق بالرقم فقط، دون تحرير الإيصال ودون طلب ثانٍ."""
    await _fund(services, user, super_admin)
    await load_user(bot, context, user)
    await _flow_until_summary(bot, context, user, mock_service)
    await press(bot, context, order_flow.confirm_order, pack("flow", "confirm"), user.telegram_id)
    receipt = bot.last
    assert "تم إنشاء طلبك" in receipt.text
    bot.sent.clear()

    await press(bot, context, fallbacks.unknown_callback, pack("flow", "confirm"), user.telegram_id)
    assert bot.sent == [], "الضغطة الثانية كتبت فوق الإيصال"
    alert = bot.answers[-1]
    assert alert["alert"] is True and "طلبك مسجَّل أصلاً" in alert["text"]
    order = (await services.orders.list_for_user(user, limit=1))[0]
    assert (order.public_code or f"#{order.id}") in alert["text"]
    assert await _count(db, "SELECT COUNT(*) AS n FROM orders") == 1


async def test_stale_flow_button_without_recent_order_gets_generic_hint(bot, context, user) -> None:  # noqa: F811
    """زر محادثة قديم بلا طلب حديث ⇒ تنبيه عام بلا تحرير رسالة."""
    await load_user(bot, context, user)
    await press(bot, context, fallbacks.unknown_callback, pack("flow", "confirm"), user.telegram_id)
    assert bot.sent == [] and "انتهت هذه العملية" in bot.answers[-1]["text"]


async def test_concurrent_provider_submission_sends_once(services, repos, user, super_admin, mock_service, mock_client) -> None:
    """مهمتا إرسال متزامنتان على الطلب نفسه ⇒ نداء add واحد للمزود فقط."""
    await _fund(services, user, super_admin)
    order = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000)
    await asyncio.gather(*[services.orders.process_pending_orders() for _ in range(4)])
    adds = [c for c in mock_client.calls if c[0] == "add"]
    assert len(adds) == 1
    stored = await repos.orders.get(order.id)
    assert stored.status == OrderStatus.SUBMITTED and stored.provider_order_id


async def test_double_cancel_refunds_once(services, repos, db, user, super_admin, mock_service) -> None:
    """إلغاءان متزامنان قبل الإرسال ⇒ استرجاع واحد، والآخر يُرفض بلا أثر مالي."""
    await _fund(services, user, super_admin)
    order = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000)
    results = await asyncio.gather(
        services.orders.cancel_by_user(user, order.id), services.orders.cancel_by_user(user, order.id), return_exceptions=True
    )
    assert sorted(type(r).__name__ for r in results) == ["InvalidStateTransitionError", "int"]
    assert [r for r in results if isinstance(r, int)] == [10_000]
    assert await services.wallet.balance_units(user.id) == 100_000
    assert await _count(db, "SELECT COUNT(*) AS n FROM transactions WHERE order_id = ? AND type = 'refund'", (order.id,)) == 1
    check = await services.wallet.verify_ledger(user.id)
    assert check.is_balanced


# ====================== 15 — دورة الطلب الناجحة الكاملة ====================== #


async def test_full_successful_cycle_pending_to_completed(services, repos, db, user, super_admin, mock_service, mock_client) -> None:
    """
    دورة كاملة: إنشاء ⇒ إرسال ⇒ Pending لدى المزود (يبقى submitted) ⇒ Processing ⇒ Completed.
    يُتحقق من: تسلسل الحالات في السجل بلا قفزات، نداء add واحد، خصم واحد وصافي مال صحيح،
    إشعارات (إنشاء/قيد التنفيذ/مكتمل) مرة واحدة، لا استرجاع، وإعادة الفحص بعد الاكتمال لا تغيّر شيئاً.
    """
    mock_client.auto_complete = False                                            # نحرّك حالات المزود يدوياً بدقة
    await _fund(services, user, super_admin)
    order = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000)
    assert order.status == OrderStatus.PENDING and order.cost_units == 10_000

    batch = await services.orders.process_pending_orders()
    assert batch.succeeded == 1
    submitted = await repos.orders.get(order.id)
    assert submitted.status == OrderStatus.SUBMITTED and submitted.provider_order_id
    assert submitted.submitted_at and submitted.next_check_at

    await _due(db, order.id)
    await services.orders.process_due_orders()                                   # المزود ما زال Pending
    assert (await repos.orders.get(order.id)).status == OrderStatus.SUBMITTED

    mock_client.advance(submitted.provider_order_id, to="In progress")
    await _due(db, order.id)
    await services.orders.process_due_orders()
    assert (await repos.orders.get(order.id)).status == OrderStatus.IN_PROGRESS

    mock_client.advance(submitted.provider_order_id, to="Completed", delivered=1000)
    await _due(db, order.id)
    await services.orders.process_due_orders()
    done = await repos.orders.get(order.id)
    assert done.status == OrderStatus.COMPLETED and done.completed_at
    assert done.delivered_quantity == 1000 and done.remains == 0 and done.refund_amount_units == 0
    assert done.next_check_at is None and done.locked_by is None

    for _ in range(2):                                                           # لا شيء يتغير بعد النهاية
        await _due(db, order.id)
        await services.orders.process_due_orders()
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED

    history = [h.to_status for h in await repos.orders.history(order.id)]
    assert history[0] == OrderStatus.PENDING and history[-1] == OrderStatus.COMPLETED
    assert history == [OrderStatus.PENDING, OrderStatus.SUBMITTING, OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS, OrderStatus.COMPLETED]
    assert len([c for c in mock_client.calls if c[0] == "add"]) == 1
    assert await services.wallet.balance_units(user.id) == 90_000
    types = [r["type"] for r in await db.fetchall("SELECT type FROM transactions WHERE order_id = ?", (order.id,))]
    assert types == [TransactionType.ORDER]
    events = [r["type"] for r in await db.fetchall("SELECT type FROM notifications WHERE user_id = ? ORDER BY id", (user.id,))]
    for needed in ("order_created", "order_in_progress", "order_completed"):
        assert events.count(needed) == 1, events
    check = await services.wallet.verify_ledger(user.id)
    assert check.is_balanced and check.stored_units == 90_000
    row = await db.fetchone("SELECT COUNT(*) AS n FROM audit_logs WHERE action LIKE 'orders.refund%'")
    assert row["n"] == 0


async def test_completed_straight_from_submitted_is_allowed_and_final(services, repos, db, user, super_admin, mock_service, mock_client) -> None:
    """مزود سريع: Completed مباشرة بلا Processing ⇒ مقبول، ونهائي لا رجعة منه."""
    await _fund(services, user, super_admin)
    order = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000)
    await services.orders.process_pending_orders()
    pid = (await repos.orders.get(order.id)).provider_order_id
    mock_client.advance(pid, to="Completed")
    await _due(db, order.id)
    await services.orders.process_due_orders()
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED
    mock_client.advance(pid, to="In progress")                                   # مزود يعيد حالة أقدم بالخطأ
    await _due(db, order.id)
    await services.orders.process_due_orders()
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED


async def test_malformed_callback_data_is_an_unknown_button_not_an_error(bot, context, user) -> None:  # noqa: F811
    """callback_data تالفة (zzz/-) تصل لـunknown_callback ⇒ رد لطيف لا استثناء (انحدار أُصلح أثناء البند 14)."""
    await load_user(bot, context, user)
    for data in ("zzz", "-", "flow", "x:y:z:1"):
        await press(bot, context, fallbacks.unknown_callback, data, user.telegram_id)
    assert not any("Traceback" in (m.text or "") for m in bot.sent)
```

---

## `tests/integration/test_phase14_statuses.py`

```python
"""
المرحلة الثانية (v1.0.1) — بند 16: كل حالات المزود (Pending/Processing/Completed/Partial/Canceled/Failed…).

الاختبار يمرّ عبر **عميل Perfect Panel الحقيقي** (نقل httpx وهمي يحاكي ردود اللوحة بصيغتها الفعلية: أرقام كنصوص،
بلا delivered/quantity) إلى خدمة الطلبات الحقيقية، ثم يفحص الحالة والمال والإشعارات لكل حالة.

    الحالات المدعومة: Pending · Awaiting · In progress · Processing · Completed · Partial · Canceled/Cancelled · Refunded ·
                      Fail/Failed/Error/Rejected.
    Refill: لا يوجد مسار «إعادة تعبئة» في النظام (علامة refill_enabled للعرض فقط)، فأي حالة غير معروفة (ومنها Refill…)
            لا تغيّر الطلب ولا المال وتُسجَّل تحذيراً — وهذا ما يُثبته الاختبار.
"""

from __future__ import annotations

import httpx
import pytest

from core.enums import OrderStatus, TransactionType
from core.order_state import map_provider_status
from integrations.providers import registry
from integrations.providers.perfect_panel import PerfectPanelClient
from utils.datetime_utils import iso_plus_seconds

pytestmark = pytest.mark.asyncio

LINK = "https://instagram.com/p/statuses"


class FakePanel:
    """لوحة Perfect Panel وهمية بصيغة الردود الفعلية: add ثم status بحسب ما يبرمجه الاختبار."""

    def __init__(self) -> None:
        """حالة افتراضية وسجل نداءات."""
        self.status_payload: dict = {"status": "Pending", "remains": "1000", "start_count": "0", "charge": "0.5", "currency": "USD"}
        self.status_http: int = 200
        self.raise_on_status: Exception | None = None
        self.calls: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        """يردّ على add/status/orders."""
        body = dict(pair.split("=", 1) for pair in request.content.decode().split("&"))
        action = body.get("action")
        self.calls.append(action)
        if action == "add":
            return httpx.Response(200, json={"order": 9001})
        if self.raise_on_status is not None:
            raise self.raise_on_status
        return httpx.Response(self.status_http, json=self.status_payload)


@pytest.fixture
def panel(monkeypatch):
    """يسجّل عميل Perfect Panel الحقيقي (بنقل وهمي) تحت نوع المزود الاختباري، ويُعيد السجل الأصلي بعدها."""
    fake = FakePanel()
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
    original = dict(registry._REGISTRY)
    registry.enable_dev_types(True)
    registry.register_client(
        "mock", lambda **kw: PerfectPanelClient(api_url=kw["api_url"], api_key=kw["api_key"], client=http)
    )
    yield fake
    registry._REGISTRY.clear()
    registry._REGISTRY.update(original)


async def _submitted(services, repos, user, super_admin, service):
    """طلب بقيمة 10000 وحدة أُرسل للمزود (صار submitted)."""
    await services.wallet.adjust_balance(target=user, amount_units=100_000, admin=super_admin, reason="رصيد", credit=True)
    order = await services.orders.create_order(user, service_id=service.id, link=LINK, quantity=1000)
    await services.orders.process_pending_orders()
    stored = await repos.orders.get(order.id)
    assert stored.status == OrderStatus.SUBMITTED and stored.provider_order_id == "9001"
    return stored


async def _check(services, db, order_id, times=1):
    """تشغيل فحص الحالة (يُقدَّم موعده أولاً)."""
    for _ in range(times):
        async with db.transaction() as tx:
            await tx.execute("UPDATE orders SET next_check_at = ?, locked_until = NULL WHERE id = ?", (iso_plus_seconds(-30), order_id))
        await services.orders.process_due_orders()


# ------------------------------ جدول التعيين ------------------------------ #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Pending", OrderStatus.SUBMITTED), ("pending", OrderStatus.SUBMITTED), ("Awaiting", OrderStatus.SUBMITTED),
        ("In queue", OrderStatus.SUBMITTED), ("In progress", OrderStatus.IN_PROGRESS), ("  IN   PROGRESS ", OrderStatus.IN_PROGRESS),
        ("Processing", OrderStatus.IN_PROGRESS), ("Running", OrderStatus.IN_PROGRESS), ("Active", OrderStatus.IN_PROGRESS),
        ("Completed", OrderStatus.COMPLETED), ("Complete", OrderStatus.COMPLETED), ("Success", OrderStatus.COMPLETED),
        ("Partial", OrderStatus.PARTIAL), ("Canceled", OrderStatus.CANCELED), ("Cancelled", OrderStatus.CANCELED),
        ("Refunded", OrderStatus.CANCELED), ("Fail", OrderStatus.FAILED), ("Failed", OrderStatus.FAILED),
        ("Error", OrderStatus.FAILED), ("Rejected", OrderStatus.FAILED),
        ("Refill", None), ("Refilling", None), ("Weird status", None), ("", None), (None, None),
    ],
)
async def test_provider_status_mapping_table(raw, expected) -> None:
    """كل نص حالة معروف يُعيَّن بدقة، وكل مجهول (ومنه Refill) يُعاد None فلا يُغيَّر الطلب."""
    assert map_provider_status(raw) == expected


# ------------------------ أثر كل حالة على الطلب والمال ------------------------ #


async def test_pending_keeps_submitted_then_processing_then_completed(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """Pending ⇒ يبقى submitted · Processing ⇒ in_progress · Completed (remains 0) ⇒ completed، بلا استرجاع."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    await _check(services, db, order.id)
    assert (await repos.orders.get(order.id)).status == OrderStatus.SUBMITTED
    panel.status_payload = {"status": "Processing", "remains": "700", "start_count": "10", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id)
    mid = await repos.orders.get(order.id)
    assert mid.status == OrderStatus.IN_PROGRESS and mid.remains == 700 and mid.start_count == 10
    panel.status_payload = {"status": "Completed", "remains": "0", "start_count": "10", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id)
    done = await repos.orders.get(order.id)
    assert done.status == OrderStatus.COMPLETED and done.delivered_quantity == 1000 and done.refund_amount_units == 0
    assert await services.wallet.balance_units(user.id) == 90_000
    assert panel.calls.count("add") == 1


async def test_pending_after_processing_is_not_a_regression_nor_an_error(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """«Pending» العابرة بعد «Processing» لا تُرجع الطلب ولا تكتب خطأً مضلِّلاً."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.status_payload = {"status": "Processing", "remains": "900", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id)
    panel.status_payload = {"status": "Pending", "remains": "900", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id)
    after = await repos.orders.get(order.id)
    assert after.status == OrderStatus.IN_PROGRESS and not after.last_error


async def test_partial_refunds_only_the_remaining_share_once(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """Partial بـremains=250 من 1000 ⇒ استرجاع 2500 من 10000 مرة واحدة حتى مع تكرار الفحص، وإشعار جزئي."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.status_payload = {"status": "Partial", "remains": "250", "start_count": "5", "charge": "0.4", "currency": "USD"}
    await _check(services, db, order.id, times=3)
    final = await repos.orders.get(order.id)
    assert final.status == OrderStatus.PARTIAL and final.delivered_quantity == 750 and final.remains == 250
    assert final.refund_amount_units == 2_500
    assert await services.wallet.balance_units(user.id) == 92_500
    rows = await db.fetchall("SELECT type, amount_units FROM transactions WHERE order_id = ? ORDER BY id", (order.id,))
    assert [(r["type"], r["amount_units"]) for r in rows] == [(TransactionType.ORDER, 10_000), (TransactionType.PARTIAL_REFUND, 2_500)]
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM notifications WHERE type = 'order_partial'"))["n"] == 1
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


@pytest.mark.parametrize("raw", ["Canceled", "Cancelled", "Refunded"])
async def test_canceled_by_provider_refunds_in_full_once(raw, services, repos, db, user, super_admin, mock_service, panel) -> None:
    """Canceled/Cancelled/Refunded لدى المزود ⇒ إلغاء ثم استرجاع كامل (الحالة النهائية refunded) مرة واحدة + إشعار."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.status_payload = {"status": raw, "remains": "1000", "charge": "0", "currency": "USD"}
    await _check(services, db, order.id, times=3)
    final = await repos.orders.get(order.id)
    assert final.status == OrderStatus.REFUNDED and final.refund_amount_units == 10_000
    assert [h.to_status for h in await repos.orders.history(order.id)][-2:] == [OrderStatus.CANCELED, OrderStatus.REFUNDED]
    assert await services.wallet.balance_units(user.id) == 100_000
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM transactions WHERE order_id = ? AND type = 'refund'", (order.id,)))["n"] == 1
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM notifications WHERE type = 'order_canceled'"))["n"] == 1
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


@pytest.mark.parametrize("raw", ["Fail", "Failed", "Error", "Rejected"])
async def test_failed_by_provider_refunds_and_notifies_user_and_admins(raw, services, repos, db, user, super_admin, mock_service, panel) -> None:
    """Fail/Failed/Error/Rejected ⇒ فشل ثم استرجاع كامل (الحالة النهائية refunded) + إشعار المستخدم والأدمن."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.status_payload = {"status": raw, "remains": "1000", "charge": "0", "currency": "USD"}
    await _check(services, db, order.id, times=2)
    final = await repos.orders.get(order.id)
    assert final.status == OrderStatus.REFUNDED and final.refund_amount_units == 10_000
    assert await services.wallet.balance_units(user.id) == 100_000
    history = [h.to_status for h in await repos.orders.history(order.id)]
    assert history[-2:] == [OrderStatus.FAILED, OrderStatus.REFUNDED]
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND type = 'order_failed'", (user.id,)))["n"] == 1
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM transactions WHERE order_id = ? AND type = 'refund'", (order.id,)))["n"] == 1
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


@pytest.mark.parametrize("raw", ["Refill", "Refilling", "Something new"])
async def test_unknown_statuses_never_change_order_or_money_and_are_logged(raw, services, repos, db, user, super_admin, mock_service, panel) -> None:
    """حالة مجهولة (ومنها Refill) ⇒ لا تغيير حالة ولا مال، وتحذير مسجَّل في error_logs، والطلب يُكمل لاحقاً عند حالة معروفة."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.status_payload = {"status": raw, "remains": "500", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id, times=2)
    unchanged = await repos.orders.get(order.id)
    assert unchanged.status == OrderStatus.SUBMITTED and unchanged.refund_amount_units == 0
    assert await services.wallet.balance_units(user.id) == 90_000
    logged = await db.fetchall("SELECT * FROM error_logs WHERE error_type = 'UnknownProviderStatus'")
    assert len(logged) >= 1 and raw in logged[0]["message"]
    panel.status_payload = {"status": "Completed", "remains": "0", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id)
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED


async def test_terminal_status_is_never_reopened_by_a_later_provider_status(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """بعد Completed لا تُعيد «Processing»/«Canceled» المتأخرة فتح الطلب ولا تسترجع مالاً."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.status_payload = {"status": "Completed", "remains": "0", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id)
    for late in ("Processing", "Canceled", "Failed", "Partial"):
        panel.status_payload = {"status": late, "remains": "500", "charge": "0", "currency": "USD"}
        await _check(services, db, order.id)
        stored = await repos.orders.get(order.id)
        assert stored.status == OrderStatus.COMPLETED and stored.refund_amount_units == 0
    assert await services.wallet.balance_units(user.id) == 90_000


async def test_partial_when_refund_disabled_or_remains_unknown_refunds_nothing(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """Partial مع إيقاف الاسترجاع الجزئي ⇒ حالة partial بلا حركة مالية (قرار المالك)."""
    await services.settings.set("partial_refund_enabled", "false", admin_id=super_admin.id)
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.status_payload = {"status": "Partial", "remains": "400", "charge": "0.3", "currency": "USD"}
    await _check(services, db, order.id)
    final = await repos.orders.get(order.id)
    assert final.status == OrderStatus.PARTIAL and final.refund_amount_units == 0
    assert await services.wallet.balance_units(user.id) == 90_000


# --------------------------- أعطال الاتصال بالمزود --------------------------- #


async def test_provider_http_errors_and_timeouts_during_status_do_not_change_anything(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """HTTP 500 / مهلة / رد خطأ عند الفحص ⇒ لا تغيير ولا استرجاع، ثم يكتمل الطلب حين يعود المزود."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.status_http, panel.status_payload = 500, {"error": "boom"}
    await _check(services, db, order.id)
    panel.status_http, panel.raise_on_status = 200, httpx.ReadTimeout("slow")
    await _check(services, db, order.id)
    panel.raise_on_status, panel.status_payload = None, {"error": "Incorrect order ID"}
    await _check(services, db, order.id)
    mid = await repos.orders.get(order.id)
    assert mid.status == OrderStatus.SUBMITTED and mid.refund_amount_units == 0 and mid.last_error
    assert await services.wallet.balance_units(user.id) == 90_000

    panel.status_payload = {"status": "Completed", "remains": "0", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id)
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED
    assert panel.calls.count("add") == 1
```

---

## `tests/integration/test_phase14_favorites.py`

```python
"""
المرحلة الثانية (v1.0.1) — بند 19: المفضلة (إضافة · عرض · إزالة · بلا تكرار · تزامن · خدمة اختفت ثم عادت).
"""

from __future__ import annotations

import asyncio

import pytest

from handlers.user import favorites as favorites_handlers
from integrations.providers.base import ProviderServiceItem
from keyboards.callback_data import NS_FAV, pack
from tests.integration.test_user_interface import bot, context, load_user, press  # noqa: F401,F811

pytestmark = pytest.mark.asyncio


async def _many_services(db, repos, provider, count):
    """إدراج عدد من الخدمات المفعّلة."""
    category = (await repos.categories.list_all())[0]
    async with db.transaction() as tx:
        for index in range(count):
            await tx.execute(
                "INSERT INTO services (category_id, provider_id, provider_service_id, name, price_per_1000_units,"
                " min_quantity, max_quantity, created_at, updated_at) VALUES (?,?,?,?,10000,10,1000,'2026-01-01','2026-01-01')",
                (category.id, provider.id, str(7000 + index), f"Fav service {index}"),
            )
    return [await repos.services.find_by_provider_service(provider.id, str(7000 + i)) for i in range(count)]


async def test_concurrent_adds_create_one_row_and_exactly_one_true(services, user, mock_service) -> None:
    """عشر إضافات متزامنة لنفس الخدمة ⇒ صف واحد وأول واحدة فقط تعيد True."""
    results = await asyncio.gather(*[services.catalog.add_favorite(user, mock_service.id) for _ in range(10)])
    assert results.count(True) == 1 and results.count(False) == 9
    assert await services.repos.favorites.count_for_user(user.id) == 1


async def test_add_list_remove_cycle_and_idempotent_remove(services, user, mock_service) -> None:
    """إضافة ⇒ تظهر ⇒ إزالة ⇒ تختفي؛ إزالة ثانية بلا خطأ؛ إعادة الإضافة تعمل."""
    assert await services.catalog.add_favorite(user, mock_service.id) is True
    assert await services.catalog.add_favorite(user, mock_service.id) is False
    items, page, pages = await services.catalog.favorites_page(user, page=1, page_size=6)
    assert [s.id for s in items] == [mock_service.id] and (page, pages) == (1, 1)
    assert await services.catalog.is_favorite(user, mock_service.id)
    assert await services.catalog.remove_favorite(user, mock_service.id) is True
    assert await services.catalog.remove_favorite(user, mock_service.id) is False
    assert (await services.catalog.favorites_page(user, page=1, page_size=6))[0] == []
    assert await services.catalog.add_favorite(user, mock_service.id) is True


async def test_pagination_newest_first_and_page_clamping(services, db, repos, user, mock_provider) -> None:
    """14 مفضلة ⇒ 3 صفحات (6/6/2) بلا تكرار أو فقد، والصفحة الزائدة تُقصّ لآخر صفحة."""
    created = await _many_services(db, repos, mock_provider, 14)
    for service in created:
        await services.catalog.add_favorite(user, service.id)
        await asyncio.sleep(0.002)                                    # فروق زمنية لترتيب «الأحدث أولاً»
    seen = []
    for page in (1, 2, 3):
        items, current, pages = await services.catalog.favorites_page(user, page=page, page_size=6)
        assert (current, pages) == (page, 3)
        seen.extend(s.id for s in items)
    assert len(seen) == 14 and len(set(seen)) == 14
    assert seen[0] == created[-1].id                                  # الأحدث إضافةً أولاً
    items, current, _ = await services.catalog.favorites_page(user, page=99, page_size=6)
    assert current == 3 and len(items) == 2


async def test_favorite_survives_sync_disable_and_returns_when_service_reappears(services, repos, super_admin, user, mock_provider, mock_service) -> None:
    """خدمة مفضلة اختفت لدى المزود ⇒ تُخفى من القائمة (غير قابلة للطلب) دون حذف المفضلة، وتعود عند عودتها."""
    await services.catalog.add_favorite(user, mock_service.id)
    item = ProviderServiceItem("555", "Mock", 6_000, 100, 100_000)
    await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=[ProviderServiceItem("1", "x", 1, 1, 2)])
    assert (await services.catalog.favorites_page(user, page=1, page_size=6))[0] == []
    assert await services.repos.favorites.count_for_user(user.id) == 1       # الصف باقٍ
    await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=[item])
    assert [s.id for s in (await services.catalog.favorites_page(user, page=1, page_size=6))[0]] == [mock_service.id]


async def test_ui_list_shows_title_and_buttons_per_page_and_toggle_on_unavailable_is_graceful(bot, context, services, db, repos, user, mock_provider, mock_service) -> None:  # noqa: F811
    """الواجهة: العنوان والترقيم وزر الخدمة؛ وإضافة خدمة معطّلة ترد برسالة لا باستثناء."""
    created = await _many_services(db, repos, mock_provider, 8)
    for service in created:
        await services.catalog.add_favorite(user, service.id)
    await load_user(bot, context, user)
    await press(bot, context, favorites_handlers.favorites_screen, pack(NS_FAV, "list", 2), user.telegram_id)
    assert "2" in bot.last.text and sum(1 for b in bot.last.buttons if b.startswith("cat:")) >= 2
    assert pack(NS_FAV, "list", 1) in bot.last.buttons                  # زر الصفحة السابقة

    async with db.transaction() as tx:
        await tx.execute("UPDATE services SET is_active = 0 WHERE id = ?", (mock_service.id,))
    bot.clear()
    await press(bot, context, favorites_handlers.favorite_toggle, pack(NS_FAV, "add", mock_service.id, 1, 1), user.telegram_id)
    assert any("لم تعد متاحة" in (a["text"] or "") for a in bot.answers)
    assert await services.repos.favorites.count_for_user(user.id) == 8
```

---

## `tests/integration/test_phase14_telegram_errors.py`

```python
"""
المرحلة الثانية (v1.0.1) — بند 20: Telegram Timeout/ConnectError دون انهيار أو فقد أو تكرار أو حالة غامضة،
مع التمييز الصارم بين الخطأ الخارجي (شبكة/تيليجرام) والداخلي (كود).

كل شيء هنا بلا شبكة: أعطال تيليجرام تُبرمَج في FakeBot بنفس أنواع استثناءات PTB الحقيقية.
"""

from __future__ import annotations

import pytest
from telegram.error import BadRequest, Conflict, Forbidden, InvalidToken, NetworkError, RetryAfter, TimedOut

import main as app_main
from core.enums import OrderStatus
from handlers.common import errors, ui
from jobs.telegram_sender import TelegramNotificationSender
from tests.integration.test_user_interface import bot, context, load_user  # noqa: F401,F811
from tests.telegram_fakes import make_callback_update, make_message_update
from texts import ar
from utils import telegram_retry
from utils.telegram_retry import TelegramHealth, call_telegram, classify, delivery_is_impossible

pytestmark = pytest.mark.asyncio

READ = "Timed out"                                             # نص PTB لمهلة القراءة/الكتابة (وصول الطلب غير مؤكد)


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    """إلغاء تأخيرات إعادة المحاولة كي لا ينتظر الاختبار."""
    monkeypatch.setattr(telegram_retry, "RETRY_DELAYS", (0.0, 0.0))


# ------------------------------- التصنيف -------------------------------- #


@pytest.mark.parametrize(
    ("error", "kind"),
    [
        (TimedOut("Timed out"), "external"), (TimedOut("Pool timeout: all connections are busy"), "external"),
        (NetworkError("httpx.ConnectError: All connection attempts failed"), "external"),
        (RetryAfter(3), "external"), (Conflict("terminated by other getUpdates request"), "external"),
        (Forbidden("bot was blocked by the user"), "user_side"),
        (BadRequest("Message is not modified: specified new message content..."), "benign"),
        (BadRequest("Query is too old and response timeout expired or query id is invalid"), "benign"),
        (BadRequest("Can't parse entities: unsupported start tag"), "internal"),
        (BadRequest("Button_data_invalid"), "internal"),
        (RuntimeError("bug"), "internal"), (KeyError("x"), "internal"), (None, "internal"),
    ],
)
async def test_classify_separates_external_from_internal(error, kind) -> None:
    """خطأ الشبكة/تيليجرام خارجي، وBadRequest الحقيقي والاستثناءات البرمجية داخلية (لا تُخفى تحت «انقطاع»)."""
    assert classify(error) == kind


@pytest.mark.parametrize(
    ("error", "impossible"),
    [
        (TimedOut("Pool timeout: all connections are busy"), True), (TimedOut("Connect timeout"), True),
        (NetworkError("httpx.ConnectError: All connection attempts failed"), True), (RetryAfter(2), True),
        (TimedOut("Timed out"), False), (TimedOut("Read timeout"), False), (TimedOut("Write timeout"), False),
        (NetworkError("httpx.ReadError: connection reset"), False), (BadRequest("x"), False),
    ],
)
async def test_delivery_is_impossible_only_when_request_never_reached_telegram(error, impossible) -> None:
    """إعادة الإرسال آمنة فقط حين يستحيل أن يكون الطلب وصل (اتصال/تجمّع) — وإلا خطر تكرار الرسالة."""
    assert delivery_is_impossible(error) is impossible


# --------------------------- إعادة المحاولة المحكومة --------------------------- #


def _flaky(errors_list, result="ok"):
    """مصنع نداء يفشل بالأخطاء المعطاة بالترتيب ثم ينجح؛ يعدّ المحاولات."""
    state = {"calls": 0}

    async def factory():
        state["calls"] += 1
        if state["calls"] <= len(errors_list):
            raise errors_list[state["calls"] - 1]
        return result

    return factory, state


async def test_idempotent_call_retries_on_timeout_then_succeeds() -> None:
    """تحرير/إجابة (متساوي الأثر): مهلتان ثم نجاح ⇒ ثلاث محاولات ونتيجة سليمة."""
    factory, state = _flaky([TimedOut(READ), NetworkError("httpx.ReadError")])
    assert await call_telegram(factory, what="تحرير", idempotent=True) == "ok" and state["calls"] == 3


async def test_non_idempotent_send_is_not_retried_after_uncertain_timeout() -> None:
    """إرسال رسالة + مهلة قراءة (قد تكون وصلت) ⇒ لا إعادة إطلاقاً (منعاً للتكرار) والخطأ يُرفع."""
    factory, state = _flaky([TimedOut(READ)])
    with pytest.raises(TimedOut):
        await call_telegram(factory, what="إرسال", idempotent=False)
    assert state["calls"] == 1


async def test_non_idempotent_send_retries_when_connection_never_established() -> None:
    """إرسال + ConnectError (لم يصل شيء) ⇒ إعادة آمنة تنجح."""
    factory, state = _flaky([NetworkError("httpx.ConnectError: boom"), TimedOut("Pool timeout")])
    assert await call_telegram(factory, what="إرسال", idempotent=False) == "ok" and state["calls"] == 3


async def test_exhausted_retries_raise_last_error_and_real_errors_are_immediate() -> None:
    """استنفاد المحاولات يرفع آخر خطأ؛ وBadRequest/Forbidden تُرفع فوراً دون إعادة."""
    factory, state = _flaky([TimedOut(READ)] * 5)
    with pytest.raises(TimedOut):
        await call_telegram(factory, what="تحرير", idempotent=True)
    assert state["calls"] == 3                                            # المحاولة الأولى + تأخيران
    for error in (BadRequest("Can't parse entities"), Forbidden("blocked")):
        factory, state = _flaky([error])
        with pytest.raises(type(error)):
            await call_telegram(factory, what="x", idempotent=True)
        assert state["calls"] == 1


async def test_retry_after_is_honoured_when_short_and_raised_when_long() -> None:
    """RetryAfter قصير ⇒ ينتظر ويعيد؛ طويل (> 5ث) ⇒ يُرفع ليتولاه المتصل بدل تجميد المعالج."""
    factory, state = _flaky([RetryAfter(0)])
    assert await call_telegram(factory, what="x", idempotent=False) == "ok" and state["calls"] == 2
    factory, state = _flaky([RetryAfter(60)])
    with pytest.raises(RetryAfter):
        await call_telegram(factory, what="x", idempotent=True)
    assert state["calls"] == 1


# ------------------------------- عدّاد الانقطاع ------------------------------- #


async def test_telegram_health_window_and_threshold() -> None:
    """عشرة أعطال في نافذة 5 دقائق ⇒ انقطاع؛ والأحداث الأقدم من النافذة تسقط."""
    now = [0.0]
    health = TelegramHealth(clock=lambda: now[0])
    for _ in range(9):
        health.record_external()
    assert not health.outage and health.recent == 9
    health.record_external()
    assert health.outage
    now[0] = 301.0
    assert health.recent == 0 and not health.outage and health.total_external == 10


# ------------------------------ المعالج العام للأخطاء ------------------------------ #


async def _log_rows(db, **where):
    """صفوف error_logs بحسب المصدر."""
    return await db.fetchall("SELECT * FROM error_logs WHERE source = ?", (where["source"],))


async def test_external_failures_are_throttled_and_never_look_like_code_errors(bot, context, services, db, user, super_admin) -> None:  # noqa: F811
    """15 مهلة متتالية: صف WARNING واحد فقط، لا صف ERROR، تنبيه أدمن واحد، ورسالة «حاول لاحقاً» للمستخدم."""
    await load_user(bot, context, user)
    for index in range(15):
        context.error = TimedOut(READ) if index % 2 else NetworkError("httpx.ConnectError: down")
        update = make_message_update(bot, text="شيء", user_id=user.telegram_id)
        await errors.error_handler(update, context)                          # لا استثناء يتسرّب
    rows = await _log_rows(db, source="telegram_network")
    assert len(rows) == 1 and rows[0]["level"] == "WARNING"
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM error_logs WHERE level = 'ERROR'"))["n"] == 0
    alerts = await db.fetchall("SELECT * FROM notifications WHERE title LIKE '%غير مستقر%'")
    assert len(alerts) >= 1 and len({a["dedupe_key"] for a in alerts}) == 1
    assert all("خارجي" in a["message"] for a in alerts)
    assert sum(ar.ERR_TELEGRAM_TEMP in m.text for m in bot.sent) == 15


async def test_below_threshold_failures_do_not_alert_admins(bot, context, services, db, user, super_admin) -> None:  # noqa: F811
    """تسعة أعطال (دون العتبة) ⇒ لا تنبيه للأدمن."""
    await load_user(bot, context, user)
    for _ in range(9):
        context.error = TimedOut(READ)
        await errors.error_handler(make_message_update(bot, text="x", user_id=user.telegram_id), context)
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM notifications WHERE title LIKE '%غير مستقر%'"))["n"] == 0


async def test_internal_error_is_logged_as_error_and_alerts_admins_but_bad_request_noise_is_quiet(bot, context, services, db, user, super_admin) -> None:  # noqa: F811
    """RuntimeError/BadRequest الحقيقي ⇒ ERROR + تنبيه؛ «message is not modified» ⇒ صمت؛ Forbidden ⇒ علامة حظر فقط."""
    await load_user(bot, context, user)
    update = make_message_update(bot, text="x", user_id=user.telegram_id)

    context.error = BadRequest("Message is not modified: same content")
    await errors.error_handler(update, context)
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM error_logs"))["n"] == 0

    context.error = Forbidden("bot was blocked by the user")
    await errors.error_handler(update, context)
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM error_logs"))["n"] == 0
    assert (await services.repos.users.get_by_id(user.id)).blocked_bot

    context.error = BadRequest("Can't parse entities: unsupported start tag")
    await errors.error_handler(update, context)
    rows = await db.fetchall("SELECT * FROM error_logs")
    assert len(rows) == 1 and rows[0]["level"] == "ERROR" and rows[0]["error_type"] == "BadRequest"
    assert any(ar.ERR_GENERIC in m.text for m in bot.sent)


async def test_error_handler_survives_failures_while_notifying_the_user(bot, context, services, db, user) -> None:  # noqa: F811
    """حتى لو تعطّل إرسال رسالة الاعتذار نفسها (تيليجرام لا يزال معطلاً) لا ينهار المعالج ولا يتولد خطأ جديد."""
    await load_user(bot, context, user)
    bot.fail("send", NetworkError("httpx.ConnectError: down"), times=10)
    context.error = TimedOut(READ)
    await errors.error_handler(make_message_update(bot, text="x", user_id=user.telegram_id), context)
    context.error = RuntimeError("bug")
    await errors.error_handler(make_message_update(bot, text="x", user_id=user.telegram_id), context)
    assert (await db.fetchone("SELECT COUNT(*) AS n FROM error_logs WHERE level = 'ERROR'"))["n"] == 1


# ----------------------------- مسار الواجهة (ui.py) ----------------------------- #


async def test_ui_edit_retries_after_timeout_and_applies_exactly_once(bot, context, user) -> None:  # noqa: F811
    """تحرير بمهلة قراءة (قد يكون طُبّق) ثم نجاح ⇒ النص النهائي مرة واحدة بلا رسائل مكررة."""
    await load_user(bot, context, user)
    update = make_callback_update(bot, data="noop", user_id=user.telegram_id)
    bot.clear()
    bot.fail("edit", TimedOut(READ), times=1, delivered=True)
    await ui.render(update, context, "النص النهائي", None)
    assert bot.attempts["edit"] == 2
    assert [m.text for m in bot.sent].count("النص النهائي") == 2             # أثر المحاولة الأولى + الإعادة (تحرير بنفس النص)
    assert not any(m.kind == "send" for m in bot.sent)                         # لا رسالة جديدة مكررة


async def test_ui_send_never_duplicates_on_uncertain_timeout_but_retries_on_connect_error(bot, context, user) -> None:  # noqa: F811
    """send: مهلة غير مؤكدة ⇒ محاولة واحدة ويعود None بلا استثناء (لا تكرار)؛ ConnectError ثم نجاح ⇒ رسالة واحدة."""
    await load_user(bot, context, user)
    update = make_message_update(bot, text="x", user_id=user.telegram_id)
    bot.clear()
    bot.attempts.clear()
    bot.fail("send", TimedOut(READ), times=1, delivered=True)
    assert await ui.send(update, context, "رسالة 1") is None                 # العطل الخارجي لا يُسقط المعالج
    assert bot.attempts["send"] == 1 and [m.text for m in bot.sent] == ["رسالة 1"]

    bot.clear()
    bot.attempts.clear()
    bot.fail("send", NetworkError("httpx.ConnectError: down"), times=2, delivered=False)
    await ui.send(update, context, "رسالة 2")
    assert bot.attempts["send"] == 3 and [m.text for m in bot.sent] == ["رسالة 2"]


# ------------------------- الإشعارات: لا فقد عند أعطال تيليجرام ------------------------- #


async def test_notification_survives_telegram_outage_and_is_delivered_after_recovery(bot, services, db, user) -> None:  # noqa: F811
    """إشعار طلب + ConnectError ⇒ يبقى queued بعدّاد محاولات (لا يضيع) ثم يُرسل عند عودة الاتصال مرة واحدة."""
    async with db.transaction() as tx:
        await services.notifications.enqueue(tx, user_id=user.id, type="system", title="تم", message="طلبك جاهز", dedupe_key="t14:ok")
    sender = TelegramNotificationSender(bot)
    bot.fail("send", NetworkError("httpx.ConnectError: down"), times=1)
    first = await services.notifications.dispatch_pending(sender)
    assert (first.sent, first.failed) == (0, 1)
    row = await db.fetchone("SELECT status, attempts, last_error FROM notifications WHERE dedupe_key = 't14:ok'")
    assert row["status"] == "queued" and row["attempts"] == 1 and row["last_error"]

    async with db.transaction() as tx:
        await tx.execute("UPDATE notifications SET next_attempt_at = NULL")
    second = await services.notifications.dispatch_pending(sender)
    assert second.sent == 1
    assert [m.text for m in bot.sent if "طلبك جاهز" in m.text].__len__() == 1
    assert (await db.fetchone("SELECT status FROM notifications WHERE dedupe_key = 't14:ok'"))["status"] == "sent"
    third = await services.notifications.dispatch_pending(sender)
    assert third.claimed == 0                                                  # لا تكرار بعد النجاح


async def test_order_state_and_balance_are_unaffected_by_telegram_failures(bot, context, services, repos, db, user, super_admin, mock_service, mock_client) -> None:  # noqa: F811
    """عطل Telegram أثناء إنشاء الطلب/إشعاره لا يمس الرصيد ولا الحالة (الحفظ سابق لأي إرسال)."""
    await services.wallet.adjust_balance(target=user, amount_units=100_000, admin=super_admin, reason="رصيد", credit=True)
    order = await services.orders.create_order(user, service_id=mock_service.id, link="https://instagram.com/p/tg", quantity=1000)
    bot.fail("send", NetworkError("httpx.ConnectError: down"), times=5)
    report = await services.notifications.dispatch_pending(TelegramNotificationSender(bot))
    assert report.sent == 0
    await services.orders.process_pending_orders()
    stored = await repos.orders.get(order.id)
    assert stored.status in (OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS, OrderStatus.COMPLETED)
    assert await services.wallet.balance_units(user.id) == 90_000
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


# ---------------------------------- الإقلاع ---------------------------------- #


async def test_best_effort_startup_call_survives_outage_but_not_real_errors(monkeypatch) -> None:
    """أثناء الإقلاع: انقطاع مؤقت ⇒ None والبوت يُكمل؛ BadRequest/InvalidToken ⇒ تُرفع (خطأ حقيقي)."""
    monkeypatch.setattr(app_main, "STARTUP_RETRY_DELAYS", (0.0, 0.0, 0.0))

    async def always_timeout():
        raise TimedOut("Timed out")

    assert await app_main._best_effort_telegram(always_timeout, what="x") is None

    for error in (BadRequest("Wrong command"), InvalidToken("bad token")):
        async def broken(error=error):
            raise error

        with pytest.raises(type(error)):
            await app_main._best_effort_telegram(broken, what="x")

    calls = {"n": 0}

    async def recovers():
        calls["n"] += 1
        if calls["n"] < 3:
            raise NetworkError("httpx.ConnectError: down")
        return "me"

    assert await app_main._best_effort_telegram(recovers, what="x") == "me" and calls["n"] == 3
```
