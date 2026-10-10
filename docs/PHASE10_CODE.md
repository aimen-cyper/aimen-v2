# الكود الكامل — المرحلة 10 (النسخ الاحتياطي والتقارير والسجلات)

كل ما في هذا الملف منسوخ آلياً من ملفات المشروع الفعلية وقت كتابة التقرير.

> الملفات الكبيرة التي تغيّر منها جزء محدود تُعرض كمقتطف موسوم بوضوح («مُحدَّث (مقتطف)») وفيه الدوال المتغيرة كاملة؛ وما عداها كامل.

> الملفات غير المذكورة هنا لم تتغيّر عن المرحلة 9، باستثناء: `core/permissions.py` و`core/setting_rules.py` (إضافة صلاحية `stats.export` وقواعد 3 إعدادات: `backup_send_to_channel`, `backup_min_keep`, `export_max_rows`)، `services/order_service.py` (حذف `recent_revenue_units`)، `tests/telegram_fakes.py` (تسجيل محتوى المستند المُرسَل)، واختبارات عُدِّلت لتوافق السلوك الجديد (`test_stats_service`, `test_security_phase9`, `test_jobs`, `test_no_dead_buttons`).

## الفهرس

- `database/migrations/0009_phase10_backup_reports.sql` — 58 سطراً (جديد)
- `core/constants.py` — 44 سطراً (مُحدَّث)
- `main.py` — 205 سطراً (مُحدَّث)
- `.env.example` — 37 سطراً (مُحدَّث)
- `scripts/init_db.py` — 199 سطراً (مُحدَّث)
- `utils/backup_files.py` — 295 سطراً (جديد)
- `services/backup_service.py` — 953 سطراً (جديد)
- `jobs/backup_jobs.py` — 31 سطراً (جديد)
- `jobs/__init__.py` — 319 سطراً (مُحدَّث)
- `scripts/restore_backup.py` — 382 سطراً (جديد)
- `handlers/admin/backup.py` — 343 سطراً (جديد)
- `utils/datetime_utils.py` — 151 سطراً (مُحدَّث)
- `services/stats_service.py` — 807 سطراً (مُحدَّث)
- `jobs/report_jobs.py` — 70 سطراً (مُحدَّث)
- `handlers/admin/stats.py` — 310 سطراً (جديد)
- `services/audit_service.py` — 232 سطراً (مُحدَّث)
- `handlers/admin/logs.py` — 383 سطراً (مُحدَّث)
- `services/__init__.py` — 198 سطراً (مُحدَّث)
- `handlers/admin/__init__.py` — 85 سطراً (مُحدَّث)
- `handlers/registry.py` — 301 سطراً (مُحدَّث)
- `middlewares/rate_limit.py` — 214 سطراً (مُحدَّث)
- `keyboards/callback_data.py` — 165 سطراً (مُحدَّث)
- `core/exceptions.py` — 9 سطراً (مُحدَّث (مقتطف))
- `database/database.py` — 20 سطراً (مُحدَّث (مقتطف))
- `database/repositories/orders.py` — 191 سطراً (مُحدَّث (مقتطف))
- `database/repositories/users.py` — 3 سطراً (مُحدَّث (مقتطف))
- `database/repositories/audit.py` — 28 سطراً (مُحدَّث (مقتطف))
- `database/repositories/misc.py` — 290 سطراً (مُحدَّث (مقتطف))
- `texts/templates.py` — 32 سطراً (مُحدَّث (مقتطف))
- `keyboards/admin_kb.py (السجلات)` — 198 سطراً (مُحدَّث (مقتطف))
- `keyboards/admin_kb.py (النسخ والإحصائيات)` — 139 سطراً (مُحدَّث (مقتطف))
- `texts/admin_ar.py (السجلات)` — 23 سطراً (مُحدَّث (مقتطف))
- `texts/admin_ar.py (أيقونات/فئات/تفاصيل التدقيق)` — 85 سطراً (مُحدَّث (مقتطف))
- `texts/admin_ar.py (النسخ والإحصائيات)` — 198 سطراً (جديد (مقتطف))
- `tests/integration/test_backup_phase10.py` — 546 سطراً (جديد)
- `tests/integration/test_restore_script_phase10.py` — 258 سطراً (جديد)
- `tests/integration/test_stats_phase10.py` — 408 سطراً (جديد)
- `tests/integration/test_logs_phase10.py` — 449 سطراً (جديد)

## قاعدة البيانات والإعدادات والتهيئة

### `database/migrations/0009_phase10_backup_reports.sql` — جديد

```sql
-- =====================================================================
-- الترحيل 0009 — المرحلة 10 (النسخ الاحتياطي والتقارير)
--
-- لماذا هذا الترحيل؟
--   1) جدول `backups` وُلد في المرحلة 1 بلا أي كود فوقه. النسخ الفعلية تحتاج
--      أعمدة تثبت أن النسخة سليمة وأين وُزِّعت:
--        verified_at        : آخر مرة أُعيد فيها فحص الملف (بصمة + سلامة SQLite).
--        schema_version     : إصدار مخطط القاعدة داخل النسخة (يمنع استعادة نسخة
--                             أحدث من الكود، ويُعرض للأدمن).
--        channel_message_id : رقم رسالة النسخة في قناة النسخ الخارجية (قرار D7).
--        channel_sent_at    : وقت إرسالها للقناة (NULL ⇒ لم تُرسل).
--        error_text         : سبب الفشل (للنسخ الفاشلة فقط، منقّى من الأسرار).
--   2) تصدير التقارير ملفات CSV تحوي بيانات مالية ومعرّفات مستخدمين، فتحتاج
--      صلاحية مستقلة (stats.export) لا تمنحها stats.view.
--   3) إعدادات تحكّم جديدة: إرسال النسخ للقناة، الحد الأدنى للنسخ المحفوظة مهما
--      قصرت مدة الاحتفاظ، وسقف صفوف التصدير.
--
-- ملاحظات تقنية:
--   • لا حذف ولا إعادة بناء لأي جدول — ALTER ADD COLUMN وصفوف بذور فقط.
--   • نسخة «حُذف ملفها» لا يُحذف سجلها: حالتها تصير 'purged' فيبقى الأثر.
-- =====================================================================

-- ------------------------------ أعمدة النسخ ------------------------------ --
ALTER TABLE backups ADD COLUMN verified_at        TEXT;
ALTER TABLE backups ADD COLUMN schema_version     TEXT;
ALTER TABLE backups ADD COLUMN channel_message_id INTEGER;
ALTER TABLE backups ADD COLUMN channel_sent_at    TEXT;
ALTER TABLE backups ADD COLUMN error_text         TEXT;

CREATE INDEX IF NOT EXISTS idx_backups_status ON backups(status, id DESC);

-- ----------------------------- صلاحية جديدة ---------------------------- --
INSERT OR IGNORE INTO permissions (code, name_ar, group_code, is_dangerous) VALUES
    ('stats.export', 'تصدير التقارير كملفات CSV', 'stats', 1);

-- للأدمن والأدمن الأعلى (الدعم الفني لا يصدّر بيانات مالية).
INSERT OR IGNORE INTO role_permissions (role_code, permission_code) VALUES
    ('super_admin', 'stats.export'),
    ('admin',       'stats.export');

-- ----------------------------- إعدادات جديدة --------------------------- --
INSERT OR IGNORE INTO settings (key, value, value_type, group_code, name_ar, description_ar, is_editable, updated_at) VALUES
    ('backup_send_to_channel', 'true', 'bool', 'backup', 'إرسال النسخ لقناة النسخ الخارجية',
     'يعمل فقط إذا ضُبط BACKUP_CHANNEL_ID في ملف البيئة. القناة يجب أن تكون خاصة: النسخة تحوي بيانات العملاء', 1,
     strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('backup_min_keep', '5', 'int', 'backup', 'أقل عدد نسخ سليمة يُحتفظ بها دائماً',
     'سياسة الاحتفاظ بالأيام لا تحذف آخر هذا العدد من النسخ السليمة مهما كان عمرها. القيمة بين 1 و100', 1,
     strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('export_max_rows', '20000', 'int', 'reports', 'أقصى عدد صفوف في ملف التصدير الواحد',
     'يحمي البوت من ملف ضخم يستهلك الذاكرة أو يتجاوز حد تيليجرام. القيمة بين 100 و100000', 1,
     strftime('%Y-%m-%dT%H:%M:%fZ','now'));

-- فاصل النسخ: الصفر يعني «تعطيل النسخ التلقائي» كما كان موصوفاً في الوصف منذ البداية
UPDATE settings
   SET description_ar = 'صفر يعني تعطيل النسخ التلقائي (يبقى النسخ اليدوي متاحاً). القيمة بين 0 و720'
 WHERE key = 'backup_interval_hours';
```

### `core/constants.py` — مُحدَّث

```python
"""ثوابت عامة للنظام (قيم لا تتغير أثناء التشغيل)."""

from __future__ import annotations

#: اسم المشروع وإصداره
APP_NAME: str = "SMM Telegram Bot"
APP_VERSION: str = "0.11.0-phase10"

#: مدة قفل الطلب أثناء معالجته بواسطة job (بالثواني)
ORDER_LOCK_SECONDS: int = 120

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

### `main.py` — مُحدَّث

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

from telegram import BotCommand                                     # noqa: E402
from telegram.ext import Application, ApplicationBuilder, Defaults  # noqa: E402
from telegram.constants import ParseMode                            # noqa: E402

from config import Config, ConfigError                              # noqa: E402
from core.constants import APP_VERSION                              # noqa: E402
from database.database import Database                              # noqa: E402
from database.migrator import Migrator                              # noqa: E402
from database.repositories import Repositories                      # noqa: E402
from handlers.registry import register_handlers                     # noqa: E402
from jobs import run_startup_recovery, schedule_jobs                # noqa: E402
from services import build_services                                 # noqa: E402
from core.enums import BackupType                                   # noqa: E402
from core.exceptions import BackupError                             # noqa: E402
from services.backup_service import create_backup_file              # noqa: E402
from utils.fs_security import check_paths                            # noqa: E402
from utils.logging_setup import get_logger, setup_logging           # noqa: E402
from utils.security import SecretBox                                # noqa: E402
from utils.single_instance import AlreadyRunningError, SingleInstance  # noqa: E402

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


def build_application(config: Config) -> Application:
    """
    بناء تطبيق تيليجرام وربط كل مكوناته.

    المخرجات: تطبيق جاهز للتشغيل عبر `run_polling`.
    """
    # block=True (الافتراضي): معالجة متسلسلة للتحديث الواحد — لا سباق على الرصيد
    defaults = Defaults(parse_mode=ParseMode.HTML, disable_web_page_preview=True)

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
            app_version=APP_VERSION,
        )
        application.bot_data["services"] = services
        application.bot_data["config"] = config

        await services.backups.sync_catalog()           # يسجّل نسخاً وُجدت على القرص بلا سجل
        await run_startup_recovery(services)
        await schedule_jobs(application, services)
        await application.bot.set_my_commands(BOT_COMMANDS)

        me = await application.bot.get_me()
        logger.info("البوت جاهز: @%s (الإصدار %s)", me.username, APP_VERSION)
        if await services.settings.is_maintenance():
            logger.warning("النظام في وضع الصيانة — المستخدمون سيرون رسالة الصيانة")

    async def post_shutdown(application: Application) -> None:
        """إغلاق الموارد بنظافة بعد توقف التطبيق."""
        services = application.bot_data.get("services")
        if services is not None:
            await services.db.close()
            logger.info("تم إغلاق قاعدة البيانات")

    application = (
        ApplicationBuilder()
        .token(config.bot_token)
        .defaults(defaults)
        .concurrent_updates(False)       # معالجة متسلسلة: أأمن مع SQLite والعمليات المالية
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

    المخرجات: رمز خروج للنظام (0 نجاح، 1 خطأ إعداد، 2 نسخة تعمل بالفعل).
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

    try:
        application = build_application(config)
        # drop_pending_updates: تجاهل ما تراكم أثناء التوقف حتى لا تُنفَّذ ضغطات
        # أزرار قديمة على حالة تغيّرت — الطلبات نفسها تُستأنف من قاعدة البيانات.
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "my_chat_member"],
        )
    except (KeyboardInterrupt, SystemExit):
        logger.info("إيقاف البوت بطلب من المشغّل")
    finally:
        lock.release()
        logger.info("انتهى التشغيل")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### `.env.example` — مُحدَّث

```
# ==========================================================
#  ملف إعدادات البيئة — انسخه إلى .env ثم املأ القيم
#  ⚠️ لا ترفع ملف .env إلى Git أبداً
#  🔒 اضبط صلاحيته: chmod 600 .env   (يفحصه البوت ويضبطه عند الإقلاع، ويفحصه
#     الأمر: python -m scripts.security_check)
# ==========================================================

# توكن البوت من BotFather (مطلوب لتشغيل البوت، غير مطلوب لتهيئة قاعدة البيانات)
# الصيغة: 123456789:AA... بلا مسافات أو علامات اقتباس (تُفحص عند التحميل)
BOT_TOKEN=

# معرفات تيليجرام لأصحاب صلاحية الأدمن الأعلى، مفصولة بفواصل
# تُستخدم لزرع أول حساب إداري وللطوارئ فقط — معرّفات أشخاص موجبة (ليست مجموعات)
SUPER_ADMIN_IDS=

# مفتاح تشفير مفاتيح المزودين (Fernet)
# ولّده بالأمر: python -m scripts.init_db --gen-key
ENCRYPTION_KEY=

# مسار ملف قاعدة البيانات
DATABASE_PATH=data/smm_bot.db

# إعدادات السجلات: DEBUG / INFO / WARNING / ERROR / CRITICAL
LOG_LEVEL=INFO
LOG_FILE=logs/bot.log

# مجلد النسخ الاحتياطية
BACKUP_DIR=backups

# المنطقة الزمنية المستخدمة في العرض (التخزين دائماً UTC)
TIMEZONE=Asia/Aden

# قناة أو مجموعة خاصة لاستقبال تنبيهات النظام (اختياري)
ADMIN_ALERT_CHAT_ID=

# قناة خاصة لحفظ النسخ الاحتياطية خارج السيرفر (اختياري)
BACKUP_CHANNEL_ID=
```

### `scripts/init_db.py` — مُحدَّث

```python
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
from core.enums import Role
from core.exceptions import BackupError
from database.database import Database
from database.migrator import Migrator
from database.repositories import Repositories
from services.backup_service import create_backup_file
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
    "error_logs", "backups",
)


async def seed_super_admins(db: Database, telegram_ids: tuple[int, ...]) -> list[str]:
    """
    إنشاء أو ترقية حسابات الأدمن الأعلى المذكورة في متغير البيئة.

    المخرجات: قائمة رسائل توضح ما تم لكل معرف.
    """
    repos = Repositories(db)
    messages: list[str] = []
    for telegram_id in telegram_ids:
        existing = await repos.users.get_by_telegram_id(telegram_id)
        async with db.transaction() as tx:
            if existing is None:
                await repos.users.create(
                    tx, telegram_id=telegram_id, first_name="Super Admin", role=Role.SUPER_ADMIN
                )
                await repos.audit.log(
                    tx, action="system.seed_super_admin", target_type="user", target_id=telegram_id,
                    details={"source": "SUPER_ADMIN_IDS"}, source="script",
                )
                messages.append(f"✅ أُنشئ حساب أدمن أعلى للمعرف {telegram_id}")
            elif existing.role != Role.SUPER_ADMIN:
                await repos.users.set_role(tx, existing.id, Role.SUPER_ADMIN)
                await repos.audit.log(
                    tx, action="system.promote_super_admin", target_type="user", target_id=existing.id,
                    before={"role": existing.role}, after={"role": str(Role.SUPER_ADMIN)}, source="script",
                )
                messages.append(f"⬆️ تمت ترقية المستخدم {telegram_id} إلى أدمن أعلى")
            else:
                messages.append(f"ℹ️ المعرف {telegram_id} أدمن أعلى بالفعل")
    return messages


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
```

## النسخ الاحتياطي والاستعادة

### `utils/backup_files.py` — جديد

```python
"""
أدوات ملفات النسخ الاحتياطي (المرحلة 10) — دوال **متزامنة بحتة** بلا تيليجرام وبلا خدمات.

لماذا ملف مستقل؟
    يستعمله مساران لا يجمعهما شيء سوى الملف نفسه:
        1. خدمة النسخ داخل البوت (`services/backup_service.py`).
        2. سكربت الاستعادة `scripts/restore_backup.py` الذي يعمل **والبوت متوقف**
           فلا حلقة أحداث ولا خدمات ولا اتصال بقاعدة البيانات.
    وضع المنطق الحرج (التحقق من البصمة وسلامة SQLite) في مكان واحد يضمن أن ما
    تعدّه الخدمة «نسخة سليمة» هو بالضبط ما يقبله سكربت الاستعادة.

شكل النسخة على القرص (بجوار بعضهما):
    smm_backup_20261005_093000_scheduled.db.gz        ← قاعدة SQLite مضغوطة
    smm_backup_20261005_093000_scheduled.db.gz.meta.json  ← بصمة SHA-256 وإصدار المخطط ونوعها

الملف الجانبي (`.meta.json`) يتيح التحقق والاستعادة حتى لو ضاعت قاعدة البيانات
نفسها (وهي الحالة التي نحتاج فيها النسخة أصلاً).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from core.exceptions import BackupError

#: بادئة اسم كل ملف نسخة (تمنع الخلط مع ملفات أخرى في المجلد)
BACKUP_PREFIX = "smm_backup_"

#: لاحقة الملف الجانبي
SIDECAR_SUFFIX = ".meta.json"

#: امتداد النسخة المضغوطة
BACKUP_SUFFIX = ".db.gz"

#: حد رفع الملفات عبر Bot API (50MB) مع هامش أمان
TELEGRAM_UPLOAD_LIMIT_BYTES = 49 * 1024 * 1024

#: أقصى حجم مسموح بعد فك الضغط (حماية من «قنبلة ضغط» في ملف مزوَّر)
MAX_UNCOMPRESSED_BYTES = 20 * 1024**3

#: اسم ملف النسخة المقبول: يمنع المسارات (../) والأسماء الغريبة تماماً
_NAME_RE = re.compile(r"^smm_backup_\d{8}_\d{6}_[a-z_]{3,20}\.db\.gz$")

#: الجداول التي يجب أن تحويها أي قاعدة صالحة للاستعادة
REQUIRED_TABLES: frozenset[str] = frozenset(
    {
        "users", "orders", "transactions", "payments", "settings", "audit_logs",
        "schema_migrations", "providers", "services", "backups",
    }
)

#: حجم كتلة القراءة عند حساب البصمة والضغط (1MB)
_CHUNK = 1024 * 1024


@dataclass(frozen=True, slots=True)
class SqliteCheck:
    """نتيجة فحص ملف SQLite (قراءة فقط)."""

    integrity_ok: bool
    integrity_message: str
    tables: frozenset[str]
    schema_version: str | None
    users_count: int
    orders_count: int

    @property
    def missing_tables(self) -> list[str]:
        """الجداول الأساسية الناقصة (فارغة إن كانت القاعدة كاملة)."""
        return sorted(REQUIRED_TABLES - self.tables)

    @property
    def is_restorable(self) -> bool:
        """هل الملف سليم وفيه كل الجداول الأساسية؟"""
        return self.integrity_ok and not self.missing_tables


# ============================== الأسماء والمسارات ============================== #


def build_backup_name(backup_type: str, stamp: str) -> str:
    """
    اسم ملف نسخة جديدة.

    المدخلات:
        backup_type : manual / scheduled / pre_operation.
        stamp       : وقت بصيغة `YYYYmmdd_HHMMSS` (UTC).
    """
    name = f"{BACKUP_PREFIX}{stamp}_{backup_type}{BACKUP_SUFFIX}"
    if not _NAME_RE.match(name):
        raise BackupError(f"اسم نسخة غير صالح: {name!r}")
    return name


def is_valid_backup_name(name: str) -> bool:
    """هل الاسم بصيغة ملفات النسخ المعتمدة؟"""
    return bool(_NAME_RE.match(name or ""))


def safe_backup_path(backup_dir: Path, filename: str) -> Path:
    """
    مسار ملف نسخة **داخل** مجلد النسخ فقط.

    يمنع الخروج من المجلد (`../../etc/passwd`) أو الروابط الرمزية إلى خارجه،
    حتى لو وصل اسم ملف مشبوه من قاعدة البيانات أو من سطر الأوامر.

    الاستثناءات: BackupError عند اسم غير مطابق أو مسار خارج المجلد.
    """
    if not is_valid_backup_name(filename):
        raise BackupError(f"اسم ملف النسخة مرفوض: {filename!r}")
    base = backup_dir.resolve()
    candidate = (base / filename).resolve()
    if candidate.parent != base:
        raise BackupError("مسار النسخة خارج مجلد النسخ الاحتياطية")
    return candidate


def sidecar_path(backup_path: Path) -> Path:
    """مسار الملف الجانبي لنسخة."""
    return backup_path.with_name(backup_path.name + SIDECAR_SUFFIX)


def list_backup_files(backup_dir: Path) -> list[Path]:
    """كل ملفات النسخ في المجلد بصيغتها المعتمدة (الأقدم أولاً)."""
    if not backup_dir.is_dir():
        return []
    return sorted(
        (entry for entry in backup_dir.iterdir() if entry.is_file() and is_valid_backup_name(entry.name)),
        key=lambda entry: entry.name,
    )


# ================================ البصمة والضغط ================================ #


def sha256_file(path: Path) -> str:
    """بصمة SHA-256 لملف (قراءة على كتل فلا تُحمَّل النسخة كلها في الذاكرة)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def gzip_file(source: Path, destination: Path) -> int:
    """
    ضغط ملف إلى `destination` وإرجاع حجم الملف الناتج بالبايت.

    الاستثناءات: OSError عند فشل الكتابة (يُحوَّل لـBackupError عند المستدعي).
    """
    with source.open("rb") as raw, gzip.open(destination, "wb", compresslevel=6) as packed:
        shutil.copyfileobj(raw, packed, _CHUNK)
    return destination.stat().st_size


def gunzip_file(source: Path, destination: Path, *, max_bytes: int = MAX_UNCOMPRESSED_BYTES) -> int:
    """
    فك ضغط ملف مع سقف للحجم الناتج (حماية من قنبلة الضغط).

    المخرجات: عدد البايتات المكتوبة.
    الاستثناءات: BackupError إن تجاوز الناتج السقف أو كان الملف تالفاً.
    """
    written = 0
    try:
        with gzip.open(source, "rb") as packed, destination.open("wb") as out:
            while chunk := packed.read(_CHUNK):
                written += len(chunk)
                if written > max_bytes:
                    raise BackupError("حجم النسخة بعد فك الضغط يتجاوز السقف المسموح")
                out.write(chunk)
    except (OSError, EOFError, gzip.BadGzipFile) as exc:
        destination.unlink(missing_ok=True)
        raise BackupError(f"ملف النسخة تالف أو لا يمكن فك ضغطه: {type(exc).__name__}") from exc
    except BackupError:
        destination.unlink(missing_ok=True)
        raise
    return written


# ================================== فحص SQLite ================================== #


def inspect_sqlite(path: Path) -> SqliteCheck:
    """
    فحص ملف SQLite بوضع القراءة فقط: السلامة، الجداول، إصدار المخطط، عدّادات أساسية.

    لا يعدّل الملف إطلاقاً (`mode=ro`) ولا يمرّر مساره عبر SQL.
    """
    uri = f"file:{quote(path.resolve().as_posix())}?mode=ro"   # ترميز أي ? أو # في المسار
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=5)
    except sqlite3.Error as exc:
        return SqliteCheck(False, f"تعذّر فتح الملف: {exc}", frozenset(), None, 0, 0)
    try:
        try:
            rows = connection.execute("PRAGMA integrity_check").fetchall()
        except sqlite3.DatabaseError as exc:
            return SqliteCheck(False, f"الملف ليس قاعدة SQLite سليمة: {exc}", frozenset(), None, 0, 0)
        message = "; ".join(str(row[0]) for row in rows[:3])
        integrity_ok = len(rows) == 1 and str(rows[0][0]).lower() == "ok"

        tables = frozenset(
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        )
        schema_version = None
        users_count = orders_count = 0
        if "schema_migrations" in tables:
            row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
            schema_version = str(row[0]) if row and row[0] is not None else None
        if "users" in tables:
            users_count = int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        if "orders" in tables:
            orders_count = int(connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0])
        return SqliteCheck(integrity_ok, message, tables, schema_version, users_count, orders_count)
    except sqlite3.DatabaseError as exc:
        return SqliteCheck(False, f"فشل فحص الملف: {exc}", frozenset(), None, 0, 0)
    finally:
        connection.close()


# =============================== الملف الجانبي =============================== #


def write_sidecar(backup_path: Path, meta: dict[str, Any]) -> Path:
    """كتابة الملف الجانبي (JSON) بصلاحية المالك فقط، وإرجاع مساره."""
    target = sidecar_path(backup_path)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, target)
    _chmod_private(target)
    return target


def read_sidecar(backup_path: Path) -> dict[str, Any] | None:
    """قراءة الملف الجانبي؛ None إذا غاب أو كان تالفاً (لا نخمّن محتواه)."""
    target = sidecar_path(backup_path)
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# ================================= أدوات عامة ================================= #


def _chmod_private(path: Path) -> None:
    """صلاحية المالك فقط (0600) على أنظمة يونكس؛ لا شيء على غيرها."""
    if os.name == "posix":
        os.chmod(path, 0o600)


def ensure_private_dir(path: Path) -> None:
    """إنشاء مجلد بصلاحية المالك فقط (0700) إن لم يوجد، وتشديده إن وُجد."""
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        os.chmod(path, 0o700)


def chmod_private(path: Path) -> None:
    """واجهة عامة لضبط صلاحية ملف خاص (للخدمة والسكربت)."""
    _chmod_private(path)


def human_size(size_bytes: int) -> str:
    """حجم مقروء: `812 بايت` · `3.4 كيلوبايت` · `12.6 ميغابايت` · `1.2 غيغابايت`."""
    size = float(max(0, size_bytes))
    if size < 1024:
        return f"{int(size)} بايت"
    for unit in ("كيلوبايت", "ميغابايت", "غيغابايت"):
        size /= 1024
        if size < 1024 or unit == "غيغابايت":
            return f"{size:.1f} {unit}"
    return f"{size:.1f} غيغابايت"


def free_disk_bytes(directory: Path) -> int:
    """المساحة الحرة (بايت) على القرص الذي يحوي المجلد (أقرب مجلد موجود)."""
    probe = directory
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    return shutil.disk_usage(probe).free
```

### `services/backup_service.py` — جديد

```python
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
        channel_id: int | None = None,
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

    async def _deliver(self, bot: Any, chat_id: int, info: BackupInfo) -> int | None:
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
            raise BackupError(
                f"فشل رفع النسخة: {type(exc).__name__}: {reason}",
                user_message=f"❌ تعذّر إرسال الملف عبر تيليجرام: {reason or type(exc).__name__}",
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
```

### `jobs/backup_jobs.py` — جديد

```python
"""
مهمة النسخ الاحتياطي الدورية (المرحلة 10).

مهمة واحدة تعمل كل بضع دقائق وتقرّر بنفسها ما يلزم:
    1. هل حان موعد نسخة جديدة؟ (من عمر آخر نسخة سليمة وإعداد `backup_interval_hours`).
    2. هل أُرسلت أحدث نسخة للقناة الخارجية؟
    3. هل في القرص نسخ أقدم من مدة الاحتفاظ تُحذف ملفاتها؟
    4. هل النسخ فاشل أو متأخر ⇒ تنبيه الأدمن (مرة يومياً).

لماذا فحص دوري بدل «كل N ساعة» ثابتة؟
    جدولة ثابتة تُنتج نسخة عند كل إعادة تشغيل، ولا تلتقط تغيير الفاصل إلا بعد
    إعادة جدولة. أما الفحص الدوري فيحسب الموعد من آخر نسخة فعلية: تشغيل البوت
    مراراً لا يُنتج نسخاً زائدة، وانقطاعه ساعات ينتج نسخة فور عودته.
"""

from __future__ import annotations

from telegram.ext import ContextTypes

from utils.logging_setup import get_logger

logger = get_logger(__name__)


async def run_backups(context: ContextTypes.DEFAULT_TYPE) -> dict[str, int]:
    """جولة النسخ الاحتياطي: إنشاء إن حان الموعد + إرسال + احتفاظ + تنبيه."""
    services = context.application.bot_data["services"]
    report = await services.backups.run_scheduled(context.bot)
    if any(report.values()):
        logger.info("جولة النسخ الاحتياطي: %s", report)
    return report
```

### `jobs/__init__.py` — مُحدَّث

```python
"""
جدولة المهام الدورية على JobQueue الخاص بـpython-telegram-bot.

لماذا JobQueue بدل asyncio.create_task يدوياً؟
    لأنه يعمل داخل حلقة التطبيق نفسها، ويتوقف معه بنظافة عند الإغلاق،
    ويمنحنا `first`/`interval`/`run_daily` ومعالج أخطاء موحّداً. لا حاجة
    لعفريت خارجي ولا cron.

كل الفترات الزمنية تُقرأ من جدول الإعدادات (`settings`) لا من ثوابت في الكود،
فيستطيع الأدمن ضبط إيقاع النظام من داخل البوت دون إعادة نشر.

**المرحلة 6:** كل مهمة تُسجَّل الآن عبر `jobs.runner.supervise` فتكتسب:
منع التداخل، مهلة قصوى للجولة، التقاط كل استثناء إلى `error_logs`، تنبيه
الأدمن عند تكرار الفشل، وسجل حالة تعرضه شاشة «⏱ المهام الدورية».
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from telegram.ext import Application, JobQueue

from jobs.backup_jobs import run_backups
from jobs.broadcast_jobs import dispatch_broadcasts
from jobs.maintenance_jobs import auto_close_tickets, database_maintenance, expire_old_payments
from jobs.notification_jobs import dispatch_notifications
from jobs.order_jobs import alert_stuck_orders, check_active_orders, submit_pending_orders
from jobs.provider_jobs import refresh_provider_balances, watch_provider_health
from jobs.report_jobs import send_admin_daily_digest
from jobs.runner import JOB_REGISTRY, JobCallback, JobRegistry, supervise
from services import ServiceContainer
from utils.datetime_utils import APP_TIMEZONE
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: الحد الأدنى المقبول لأي فترة تكرار (حماية من قيمة إعداد خاطئة تُغرق النظام)
MIN_INTERVAL_SECONDS = 5

#: مهلة الجولة الواحدة لكل نوع مهمة (ثوانٍ) — بعدها تُلغى الجولة وتُسجَّل كفشل
FAST_JOB_TIMEOUT = 120.0
SLOW_JOB_TIMEOUT = 600.0

#: فاصل فحص «هل حان موعد النسخة؟» (ثانية) — الفاصل الفعلي للنسخ من الإعدادات
BACKUP_CHECK_SECONDS = 600.0

__all__ = [
    "schedule_jobs",
    "reschedule_for_setting",
    "run_startup_recovery",
    "JOB_REGISTRY",
    "JOB_LABELS",
]

#: أسماء عربية للمهام تُعرض في لوحة التحكم (الاسم التقني يبقى للّوقات)
JOB_LABELS: dict[str, str] = {
    "notifications_dispatch": "📨 إرسال الإشعارات",
    "broadcast_dispatch": "📣 إرسال الرسائل الجماعية",
    "orders_submit": "📤 إرسال الطلبات للمزود",
    "orders_check": "🔄 متابعة حالة الطلبات",
    "payments_expire": "⌛️ إنهاء صلاحية طلبات الشحن",
    "tickets_auto_close": "🎫 إغلاق التذاكر الراكدة",
    "orders_stuck_alert": "⏰ تنبيه الطلبات المتوقفة",
    "providers_balance": "💵 فحص أرصدة المزودين",
    "providers_health": "🩺 مراقبة صحة المزودين",
    "admin_daily_digest": "📊 الملخص اليومي",
    "database_maintenance": "🗄 صيانة قاعدة البيانات",
    "backups_auto": "💾 النسخ الاحتياطي",
}


async def _interval(services: ServiceContainer, key: str, default: int) -> float:
    """قراءة فترة تكرار من الإعدادات مع فرض حد أدنى آمن."""
    value = await services.settings.get_int(key, default)
    return float(max(MIN_INTERVAL_SECONDS, value))


def _every_text(seconds: float) -> str:
    """وصف عربي مختصر لفترة التكرار (يُعرض في شاشة المهام)."""
    seconds = int(seconds)
    if seconds < 60:
        return f"كل {seconds} ثانية"
    if seconds < 3600:
        return f"كل {seconds // 60} دقيقة"
    if seconds < 86400:
        return f"كل {seconds // 3600} ساعة"
    return f"كل {seconds // 86400} يوم"


def _daily_time(hour: int) -> dt.time:
    """ساعة تشغيل يومية بتوقيت التطبيق (Asia/Aden افتراضياً) مع حصر 0..23."""
    return dt.time(hour=max(0, min(23, hour)), minute=0, tzinfo=APP_TIMEZONE)


@dataclass(frozen=True, slots=True)
class JobSpec:
    """
    وصف مهمة دورية واحدة كما تُحسب من الإعدادات الحالية.

    الحقول:
        name        : اسم المهمة (مفتاح السجل واللوحة).
        callback    : دالة المهمة الأصلية.
        interval    : فترة التكرار بالثواني (None للمهام اليومية).
        daily_hour  : ساعة التشغيل اليومية (None للمتكررة).
        first       : تأخير أول تشغيل (للمتكررة).
        timeout     : مهلة الجولة الواحدة.
    """

    name: str
    callback: JobCallback
    interval: float | None
    daily_hour: int | None
    first: float
    timeout: float


#: ربط مفتاح إعداد بالمهمة التي يتحكم بإيقاعها (يُستخدم في إعادة الجدولة الحيّة)
JOB_SETTING_KEYS: dict[str, str] = {
    "notification_dispatch_seconds": "notifications_dispatch",
    "broadcast_interval_seconds": "broadcast_dispatch",
    "order_submit_interval_seconds": "orders_submit",
    "order_check_interval_seconds": "orders_check",
    "provider_balance_check_minutes": "providers_balance",
    "provider_health_watch_minutes": "providers_health",
    "admin_digest_hour": "admin_daily_digest",
    "db_maintenance_hour": "database_maintenance",
}

#: مفتاح يؤثر على كل المهام (عتبة تنبيه الفشل مغلَّفة داخل كل مهمة)
ALL_JOBS_SETTING_KEY = "job_failure_alert_threshold"


async def build_job_specs(services: ServiceContainer) -> list[JobSpec]:
    """
    حساب جدول المهام من قيم الإعدادات **الحالية** (يُستدعى عند الإقلاع وعند أي تعديل).

    فصل الحساب عن التركيب هو ما يتيح تغيير الإيقاع دون إعادة تشغيل: نعيد حساب
    الجدول ثم نستبدل المهمة المتأثرة فقط.
    """
    return [
        JobSpec("notifications_dispatch", dispatch_notifications,
                await _interval(services, "notification_dispatch_seconds", 10), None, 5.0, FAST_JOB_TIMEOUT),
        JobSpec("broadcast_dispatch", dispatch_broadcasts,
                await _interval(services, "broadcast_interval_seconds", 5), None, 8.0, FAST_JOB_TIMEOUT),
        JobSpec("orders_submit", submit_pending_orders,
                await _interval(services, "order_submit_interval_seconds", 30), None, 12.0, SLOW_JOB_TIMEOUT),
        JobSpec("orders_check", check_active_orders,
                await _interval(services, "order_check_interval_seconds", 120), None, 25.0, SLOW_JOB_TIMEOUT),
        JobSpec("payments_expire", expire_old_payments, 900.0, None, 60.0, FAST_JOB_TIMEOUT),
        JobSpec("tickets_auto_close", auto_close_tickets, 3600.0, None, 120.0, FAST_JOB_TIMEOUT),
        JobSpec("orders_stuck_alert", alert_stuck_orders, 3600.0, None, 300.0, FAST_JOB_TIMEOUT),
        JobSpec("providers_balance", refresh_provider_balances,
                await _interval(services, "provider_balance_check_minutes", 30) * 60.0,
                None, 90.0, SLOW_JOB_TIMEOUT),
        JobSpec("providers_health", watch_provider_health,
                await _interval(services, "provider_health_watch_minutes", 10) * 60.0,
                None, 150.0, SLOW_JOB_TIMEOUT),
        JobSpec("admin_daily_digest", send_admin_daily_digest, None,
                await services.settings.get_int("admin_digest_hour", 21), 0.0, SLOW_JOB_TIMEOUT),
        JobSpec("database_maintenance", database_maintenance, None,
                await services.settings.get_int("db_maintenance_hour", 4), 0.0, SLOW_JOB_TIMEOUT),
        # فحص دوري ثابت: الموعد الفعلي يُحسب من آخر نسخة سليمة وإعداد backup_interval_hours
        JobSpec("backups_auto", run_backups, BACKUP_CHECK_SECONDS, None, 180.0, SLOW_JOB_TIMEOUT),
    ]


def _install_job(
    queue: JobQueue,
    spec: JobSpec,
    *,
    registry: JobRegistry,
    alert_threshold: int,
    keep_history: bool,
) -> str:
    """
    تركيب مهمة واحدة على JobQueue (واستبدال نسختها القديمة إن وُجدت).

    المخرجات: وصف نصي قصير للسجل (مثل `orders_check(120s)`).
    """
    for old in queue.get_jobs_by_name(spec.name):          # إزالة الجدولة القديمة أولاً
        old.schedule_removal()

    if spec.daily_hour is not None:
        run_at = _daily_time(spec.daily_hour)
        supervised = supervise(
            spec.callback, name=spec.name, registry=registry, interval_seconds=86400.0,
            schedule_text=f"يومياً {run_at.strftime('%H:%M')}", timeout_seconds=spec.timeout,
            failure_alert_threshold=alert_threshold, keep_history=keep_history,
        )
        queue.run_daily(supervised, time=run_at, name=spec.name)
        return f"{spec.name}(daily {run_at.strftime('%H:%M')})"

    interval = float(spec.interval or MIN_INTERVAL_SECONDS)
    supervised = supervise(
        spec.callback, name=spec.name, registry=registry, interval_seconds=interval,
        schedule_text=_every_text(interval), timeout_seconds=spec.timeout,
        failure_alert_threshold=alert_threshold, keep_history=keep_history,
    )
    queue.run_repeating(supervised, interval=interval, first=spec.first, name=spec.name)
    return f"{spec.name}({int(interval)}s)"


async def schedule_jobs(
    application: Application,
    services: ServiceContainer,
    *,
    registry: JobRegistry = JOB_REGISTRY,
) -> list[str]:
    """
    جدولة كل المهام الدورية وإرجاع أسمائها (تُطبع في سجل الإقلاع).

    المهام المتكررة:
        notifications_dispatch : إرسال الإشعارات المتراكمة.
        broadcast_dispatch     : إرسال دفعة من مستلمي الرسالة الجماعية الجارية.
        orders_submit          : إرسال الطلبات المعلّقة للمزود.
        orders_check           : متابعة الطلبات النشطة حتى حالتها النهائية.
        payments_expire        : إنهاء صلاحية طلبات الشحن القديمة.
        tickets_auto_close     : إغلاق التذاكر الراكدة.
        orders_stuck_alert     : تنبيه الأدمن بالطلبات المتوقفة.
        providers_balance      : قراءة أرصدتنا لدى المزودين + تنبيه الانخفاض.
        providers_health       : إعادة تفعيل المزود المتعثر فور تعافيه.

    المهام اليومية (بتوقيت التطبيق):
        admin_daily_digest     : الملخص اليومي للأدمن.
        database_maintenance   : صيانة تقنية لقاعدة البيانات.

    مهمة النسخ الاحتياطي `backups_auto` تفحص كل 10 دقائق هل حان موعد نسخة (المرحلة 10).

    **المرحلة 9:** تُسجَّل أيضاً دالة مراقبة على الإعدادات: أي تعديل لمفتاح إيقاع
    (فترة/ساعة) يعيد جدولة مهمته فوراً بلا إعادة تشغيل (`reschedule_for_setting`).
    """
    queue = application.job_queue
    if queue is None:
        raise RuntimeError(
            "JobQueue غير متاح — ثبّت الحزمة بالشكل: pip install 'python-telegram-bot[job-queue]'"
        )

    registry.clear()
    alert_threshold = await services.settings.get_int("job_failure_alert_threshold", 3)

    names = [
        _install_job(queue, spec, registry=registry, alert_threshold=alert_threshold, keep_history=False)
        for spec in await build_job_specs(services)
    ]
    _attach_setting_listener(application, services, registry)
    logger.info("تمت جدولة %s مهمة دورية: %s", len(names), ", ".join(names))
    return names


async def reschedule_for_setting(
    application: Application,
    services: ServiceContainer,
    key: str,
    *,
    registry: JobRegistry = JOB_REGISTRY,
) -> list[str]:
    """
    إعادة جدولة المهمة (أو المهام) التي يتحكم بها مفتاح إعداد تغيّر للتو.

    المدخلات:
        key : المفتاح الذي تغيّر (غير المرتبط بأي مهمة لا يُحدث شيئاً).

    المخرجات: أوصاف المهام التي أُعيدت جدولتها (قائمة فارغة إن لم يتأثر شيء).

    تُحفظ عدّادات المهمة وقفلها: جولة جارية لا تتداخل مع الجديدة ولا يضيع سجلها.
    """
    queue = application.job_queue
    if queue is None:
        return []
    if key == ALL_JOBS_SETTING_KEY:
        affected = None                                      # كل المهام
    elif key in JOB_SETTING_KEYS:
        affected = {JOB_SETTING_KEYS[key]}
    else:
        return []

    alert_threshold = await services.settings.get_int(ALL_JOBS_SETTING_KEY, 3)
    done: list[str] = []
    for spec in await build_job_specs(services):
        if affected is not None and spec.name not in affected:
            continue
        done.append(
            _install_job(queue, spec, registry=registry, alert_threshold=alert_threshold, keep_history=True)
        )
    logger.info("إعادة جدولة حيّة بعد تعديل %s: %s", key, ", ".join(done))
    return done


def _attach_setting_listener(
    application: Application, services: ServiceContainer, registry: JobRegistry
) -> None:
    """ربط مراقب الإعدادات بإعادة الجدولة (مرة واحدة لكل تطبيق)."""
    if application.bot_data.get("_jobs_listener_attached"):
        return
    application.bot_data["_jobs_listener_attached"] = True

    async def on_change(key: str, value: str) -> None:
        """يُستدعى بعد كل تعديل إعداد ناجح."""
        await reschedule_for_setting(application, services, key, registry=registry)

    services.settings.add_listener(on_change)


async def run_startup_recovery(services: ServiceContainer) -> dict[str, int]:
    """
    استرداد الحالة بعد إعادة التشغيل — يُستدعى مرة واحدة قبل بدء الاستقبال.

    يعالج الطلبات التي كانت «قيد الإرسال» لحظة الإغلاق (تُنقل إلى
    `submit_uncertain` لتُراجَع بدل أن تُرسل مرتين)، ويحرّر الأقفال المنتهية.

    المخرجات: عدّادات ما تم استرداده.
    """
    result = await services.orders.recover_after_restart()
    if any(result.values()):
        logger.warning("استرداد بعد إعادة التشغيل: %s", result)
    else:
        logger.info("لا توجد طلبات عالقة من تشغيل سابق")
    return result
```

### `scripts/restore_backup.py` — جديد

```python
"""
استعادة نسخة احتياطية من سطر الأوامر (المرحلة 10) — **والبوت متوقف**.

لماذا خارج البوت؟
    استبدال ملف القاعدة والبوت يعمل يعني اتصالات مفتوحة على الملف القديم وعمليات
    مالية جارية. الاستعادة من داخل تيليجرام ستكون زرّاً خطراً يمكن لأدمن مخترَق أن
    يضغطه فيعود النظام لحالة قديمة (أرصدة قديمة = أموال مكرَّرة). لذلك هي عملية
    تشغيلية يقوم بها مالك السيرفر فقط.

الاستخدام (من مجلد المشروع):
    python -m scripts.restore_backup --list                       # عرض النسخ الموجودة على القرص
    python -m scripts.restore_backup --latest                     # أحدث نسخة يدوية/مجدولة موثَّقة
    python -m scripts.restore_backup --id 12                      # حسب رقمها في سجل النسخ
    python -m scripts.restore_backup --file /path/smm_backup_....db.gz
    python -m scripts.restore_backup --latest --yes               # بلا سؤال التأكيد (للأتمتة)

الضمانات (بالترتيب):
    1. يرفض العمل إن كان البوت يعمل (قفل `bot.lock` ممسوك).
    2. يتحقق من بصمة sha256 مقابل الملف الجانبي، ثم يفك الضغط لملف مؤقت ويفحص
       `integrity_check` والجداول الأساسية، ويرفض نسخة مخطَّطها أحدث من كود هذا الإصدار.
    3. يأخذ نسخة أمان من القاعدة الحالية (أو يحفظها كما هي إن كانت تالفة) — لا يُحذف شيء.
    4. يحذف ملفي -wal و-shm القديمين (تطبيقهما على قاعدة مختلفة يفسدها) ثم يستبدل الملف ذرّياً.
    5. يضبط صلاحية 0600 ويسجّل `backup.restore` في سجل التدقيق (source=cli).

كود الخروج: 0 نجاح · 1 رفض/فشل · 2 خطأ في الإعدادات أو الوسائط.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sqlite3
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:                      # تشغيل مباشر بلا تثبيت الحزمة
    sys.path.insert(0, str(ROOT))

from config import Config, ConfigError                                  # noqa: E402
from core.constants import APP_VERSION                                  # noqa: E402
from core.exceptions import BackupError                                 # noqa: E402
from database.database import Database                                  # noqa: E402
from database.migrator import MIGRATIONS_DIR                            # noqa: E402
from database.repositories import Repositories                          # noqa: E402
from services.backup_service import create_backup_file                  # noqa: E402
from utils.backup_files import (                                        # noqa: E402
    SqliteCheck,
    chmod_private,
    gunzip_file,
    human_size,
    inspect_sqlite,
    is_valid_backup_name,
    list_backup_files,
    read_sidecar,
    safe_backup_path,
    sha256_file,
)
from utils.datetime_utils import utc_now                                # noqa: E402
from utils.logging_setup import get_logger, setup_logging               # noqa: E402
from utils.single_instance import AlreadyRunningError, SingleInstance   # noqa: E402

logger = get_logger(__name__)

#: الكلمة التي يجب كتابتها حرفياً لتأكيد الاستبدال بلا `--yes`
CONFIRM_WORD = "RESTORE"


@dataclass(slots=True)
class Prepared:
    """نسخة جُهِّزت للاستعادة: ملف قاعدة مؤقت مفحوص + معلومات للعرض."""

    source: Path
    temp_db: Path
    check: SqliteCheck
    sha_status: str          # verified | no_sidecar | skipped_plain
    created_at: str


# ================================ دوال مساعدة ================================ #


def local_schema_version() -> str:
    """أحدث رقم ترحيل يعرفه كود هذا الإصدار (من ملفات migrations)."""
    versions = [path.name.split("_", 1)[0] for path in Path(MIGRATIONS_DIR).glob("*.sql")]
    return max(versions) if versions else ""


def list_candidates(backup_dir: Path) -> list[tuple[Path, dict | None]]:
    """نسخ القرص من الأحدث للأقدم مع ملفاتها الجانبية (لا يحتاج قاعدة بيانات سليمة)."""
    return [(path, read_sidecar(path)) for path in reversed(list_backup_files(backup_dir))]


def print_list(backup_dir: Path) -> int:
    """طباعة النسخ الموجودة على القرص."""
    items = list_candidates(backup_dir)
    if not items:
        print(f"لا توجد نسخ في {backup_dir}")
        return 0
    print(f"النسخ في {backup_dir}:")
    for path, meta in items:
        size = human_size(path.stat().st_size)
        when = (meta or {}).get("created_at", "؟")
        schema = (meta or {}).get("schema_version", "؟")
        flag = "" if meta else "  ⚠️ بلا ملف جانبي"
        print(f"  • {path.name}  [{size}]  {when}  schema={schema}{flag}")
    return 0


def resolve_source(config: Config, *, file: str | None, backup_id: int | None, latest: bool) -> Path:
    """
    تحديد ملف النسخة المطلوبة.

    الاستثناءات: BackupError برسالة واضحة إن لم توجد.
    """
    if file:
        path = Path(file).expanduser()
        if not path.is_file():
            raise BackupError(f"الملف غير موجود: {path}")
        return path.resolve()
    if backup_id is not None:
        if not config.database_path.exists():
            raise BackupError("لا توجد قاعدة حالية لقراءة سجل النسخ منها — استعمل --file أو --latest")
        try:
            connection = sqlite3.connect(f"file:{config.database_path.resolve().as_posix()}?mode=ro", uri=True)
            try:
                row = connection.execute("SELECT filename FROM backups WHERE id = ?", (backup_id,)).fetchone()
            finally:
                connection.close()
        except sqlite3.Error as exc:
            raise BackupError(f"تعذّر قراءة سجل النسخ: {exc} — استعمل --file") from exc
        if row is None:
            raise BackupError(f"لا نسخة بالرقم {backup_id} في السجل")
        if not is_valid_backup_name(str(row[0])):
            raise BackupError("اسم الملف في السجل غير صالح")
        path = safe_backup_path(config.backup_dir, str(row[0]))
        if not path.is_file():
            raise BackupError(f"ملف النسخة غير موجود على القرص: {path.name}")
        return path
    if latest:
        for path, meta in list_candidates(config.backup_dir):
            # الأحدث الموثَّق من النوع اليدوي/المجدول. نسخ pre_operation (أمان قبل ترقية/استعادة/ضغط)
            # لا تُختار تلقائياً وإلا أعاد تكرار الأمر الحالة السابقة للاستعادة نفسها؛ تُختار بـ--id/--file.
            if meta is not None and not path.name.endswith("_pre_operation.db.gz"):
                return path
        raise BackupError("لا توجد نسخة يدوية/مجدولة موثَّقة في مجلد النسخ (استعمل --id أو --file)")
    raise BackupError("حدّد --latest أو --id أو --file أو --list")


def prepare(source: Path, workdir: Path) -> Prepared:
    """
    فحص النسخة وتجهيز ملف قاعدة مؤقت في `workdir` (نفس نظام الملفات ⇒ استبدال ذرّي).

    الاستثناءات: BackupError عند أي فحص فاشل (ويُحذف الملف المؤقت).
    """
    meta = read_sidecar(source)
    sha_status = "skipped_plain"
    temp = workdir / f".restore_{os.getpid()}.db"
    temp.unlink(missing_ok=True)
    try:
        if source.name.endswith(".gz"):
            if meta and meta.get("sha256"):
                if sha256_file(source) != meta["sha256"]:
                    raise BackupError("بصمة sha256 لا تطابق الملف الجانبي — النسخة تالفة أو معدَّلة")
                sha_status = "verified"
            else:
                sha_status = "no_sidecar"
            gunzip_file(source, temp)
        else:
            temp.write_bytes(source.read_bytes())
        chmod_private(temp)
        check = inspect_sqlite(temp)
        if not check.integrity_ok:
            raise BackupError(f"فحص السلامة فشل: {check.integrity_message}")
        if check.missing_tables:
            raise BackupError("جداول أساسية ناقصة: " + "، ".join(check.missing_tables))
        local = local_schema_version()
        if check.schema_version and local and check.schema_version > local:
            raise BackupError(
                f"مخطَّط النسخة ({check.schema_version}) أحدث من كود هذا الإصدار ({local}) — حدّث الكود أولاً"
            )
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return Prepared(
        source=source,
        temp_db=temp,
        check=check,
        sha_status=sha_status,
        created_at=str((meta or {}).get("created_at", "؟")),
    )


def _remove_wal_files(database_path: Path) -> None:
    """حذف ملفَي -wal و-shm المرافقين للقاعدة القديمة."""
    for suffix in ("-wal", "-shm"):
        Path(str(database_path) + suffix).unlink(missing_ok=True)


async def _safety_copy(config: Config) -> str:
    """
    حفظ القاعدة الحالية قبل استبدالها، وإرجاع وصف ما حُفظ.

    سليمة ⇒ نسخة `pre_operation` موثَّقة. تالفة ⇒ تُنقل كما هي باسم `.corrupt-<ختم>` (لا حذف).
    """
    current = config.database_path
    if not current.exists():
        return "لا قاعدة حالية (استعادة على سيرفر جديد)"
    check = await asyncio.to_thread(inspect_sqlite, current)
    if not check.integrity_ok:
        stamp = utc_now().strftime("%Y%m%d_%H%M%S")
        kept = current.with_name(f"{current.name}.corrupt-{stamp}")
        os.replace(current, kept)
        for suffix in ("-wal", "-shm"):
            wal = Path(str(current) + suffix)
            if wal.exists():
                os.replace(wal, Path(str(kept) + suffix))
        chmod_private(kept)
        return f"القاعدة الحالية تالفة — حُفظت كما هي: {kept.name}"
    db = Database(current)
    await db.connect()
    try:
        artifact = await create_backup_file(
            db, config.backup_dir, backup_type="pre_operation", app_version=APP_VERSION
        )
    finally:
        await db.close()
    return f"نسخة أمان من القاعدة الحالية: {artifact.filename}"


async def _write_audit(config: Config, prepared: Prepared, safety_note: str) -> str | None:
    """تسجيل `backup.restore` داخل القاعدة المستعادة. يرجع نص تحذير إن تعذّر (لا يُفشل الاستعادة)."""
    db = Database(config.database_path)
    try:
        await db.connect()
        repos = Repositories(db)
        async with db.transaction() as tx:
            await repos.audit.log(
                tx,
                action="backup.restore",
                target_type="backup",
                target_id=prepared.source.name,
                details={
                    "restored_from": prepared.source.name,
                    "backup_created_at": prepared.created_at,
                    "schema_version": prepared.check.schema_version,
                    "sha": prepared.sha_status,
                    "safety": safety_note,
                },
                source="cli",
            )
    except Exception as exc:                                      # noqa: BLE001
        logger.exception("تعذّر تسجيل التدقيق بعد الاستعادة")
        return f"تعذّر تسجيل التدقيق: {type(exc).__name__}"
    finally:
        await db.close()
    return None


# ================================== التنفيذ ================================== #


async def run(
    *,
    list_only: bool = False,
    file: str | None = None,
    backup_id: int | None = None,
    latest: bool = False,
    assume_yes: bool = False,
    input_fn: Callable[[str], str] = input,
) -> int:
    """تنفيذ الاستعادة كاملة وإرجاع كود الخروج (انظر الوصف أعلى الملف)."""
    try:
        config = Config.load()
    except ConfigError as exc:
        print(f"❌ خطأ في الإعدادات: {exc}")
        return 2
    if os.name == "posix":
        os.umask(0o077)
    config.ensure_directories()
    setup_logging(config.log_file, config.log_level, console=False)

    if list_only:
        return print_list(config.backup_dir)

    lock = SingleInstance(config.data_dir / "bot.lock")
    try:
        lock.acquire()
    except AlreadyRunningError:
        print("❌ البوت يعمل الآن. أوقفه أولاً ثم أعد تشغيل الاستعادة.")
        return 1
    try:
        try:
            source = resolve_source(config, file=file, backup_id=backup_id, latest=latest)
            prepared = await asyncio.to_thread(prepare, source, config.database_path.parent)
        except BackupError as exc:
            print(f"❌ {exc}")
            return 1

        check = prepared.check
        print("— النسخة المطلوبة —")
        print(f"  الملف     : {source.name}")
        print(f"  أُنشئت    : {prepared.created_at}")
        print(f"  البصمة    : {_sha_text(prepared.sha_status)}")
        print(f"  المخطَّط  : {check.schema_version} (كود هذا الإصدار: {local_schema_version()})")
        print(f"  محتواها   : {check.users_count} مستخدم · {check.orders_count} طلب")
        if config.database_path.exists():
            current = await asyncio.to_thread(inspect_sqlite, config.database_path)
            print(f"  الحالية   : {current.users_count} مستخدم · {current.orders_count} طلب  ← ستُستبدل")
        print("⚠️ كل ما حدث بعد وقت النسخة (طلبات، أرصدة، شحنات) سيختفي من القاعدة الحية.")

        if not assume_yes:
            try:
                answer = input_fn(f"للمتابعة اكتب {CONFIRM_WORD} حرفياً: ").strip()
            except EOFError:
                answer = ""
            if answer != CONFIRM_WORD:
                prepared.temp_db.unlink(missing_ok=True)
                print("أُلغيت الاستعادة — لم يتغير شيء.")
                return 1

        try:
            safety_note = await _safety_copy(config)
            print(f"🛟 {safety_note}")
            _remove_wal_files(config.database_path)
            os.replace(prepared.temp_db, config.database_path)           # استبدال ذرّي
            chmod_private(config.database_path)
        except (OSError, BackupError) as exc:
            prepared.temp_db.unlink(missing_ok=True)
            logger.exception("فشلت الاستعادة")
            print(f"❌ فشل الاستبدال: {exc}")
            return 1

        final = await asyncio.to_thread(inspect_sqlite, config.database_path)
        if not final.is_restorable:
            print("❌ القاعدة بعد الاستبدال لا تجتاز الفحص — راجع نسخة الأمان في مجلد النسخ.")
            return 1
        warning = await _write_audit(config, prepared, safety_note)
        if warning:
            print(f"⚠️ {warning}")
        logger.warning("تمت استعادة القاعدة من %s", source.name)
        print(f"✅ تمت الاستعادة من {source.name}.")
        print("   شغّل البوت الآن؛ أي ترحيل ناقص سيُطبَّق عند الإقلاع بعد نسخة أمان تلقائية.")
        return 0
    finally:
        lock.release()


def _sha_text(status: str) -> str:
    """وصف حالة التحقق من البصمة."""
    return {
        "verified": "✅ مطابقة للملف الجانبي",
        "no_sidecar": "⚠️ لا ملف جانبي (فُحصت السلامة فقط)",
    }.get(status, "— ملف غير مضغوط")


def main() -> int:
    """نقطة الدخول: قراءة الوسائط وتشغيل الاستعادة."""
    parser = argparse.ArgumentParser(description="استعادة نسخة احتياطية (والبوت متوقف)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="عرض النسخ الموجودة")
    group.add_argument("--latest", action="store_true", help="أحدث نسخة موثَّقة")
    group.add_argument("--id", type=int, help="رقم النسخة في سجل النسخ")
    group.add_argument("--file", help="مسار ملف نسخة (.db.gz أو .db)")
    parser.add_argument("--yes", action="store_true", help="تخطّي سؤال التأكيد")
    args = parser.parse_args()
    return asyncio.run(
        run(
            list_only=args.list,
            file=args.file,
            backup_id=args.id,
            latest=args.latest,
            assume_yes=args.yes,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
```

### `handlers/admin/backup.py` — جديد

```python
"""
قسم «💾 النسخ الاحتياطي» في لوحة التحكم (المرحلة 10).

الشاشات (مساحة `bk`):
    bk:home                : الحالة (آخر نسخة، العمر، الاحتفاظ، نسخة خارج السيرفر، المساحة).
    bk:new                 : إنشاء نسخة يدوية فوراً.
    bk:list:<p>            : سجل النسخ (صفحات).
    bk:view:<id>:<p>       : تفاصيل نسخة.
    bk:verify:<id>:<p>     : فحص حقيقي للنسخة (بصمة + فك ضغط + integrity_check).
    bk:chan:<id>:<p>       : إرسال نسخة لقناة النسخ (backup.download).
    bk:dlask / bk:dl       : تأكيد ثانٍ ثم إرسال الملف لمحادثة الأدمن (backup.download).
    bk:vacask / bk:vac     : تأكيد ثانٍ ثم ضغط القاعدة بعد نسخة أمان (backup.create).
    bk:guide               : دليل الاستعادة من السيرفر.

قواعد ملزمة:
    • فحص الصلاحية على كل callback (والخدمة تعيده داخلها).
    • لا زر «استعادة» هنا عمداً — الاستعادة خارج البوت (`scripts/restore_backup.py`).
    • التنزيل والضغط خلف تأكيد ثانٍ، وكلاهما يُدقَّق وخاضع للحد الحسّاس.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from core.permissions import Permission
from handlers.admin.common import admin_required, args, paginate, permissions_of
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render
from keyboards.admin_kb import (
    backup_confirm_kb,
    backup_guide_kb,
    backup_home_kb,
    backup_list_kb,
    backup_view_kb,
)
from keyboards.callback_data import NS_ADM_BKP, pattern
from middlewares.context import require_user, services_of
from services.backup_service import BackupInfo, BackupSummary
from texts import admin_ar as t
from utils.backup_files import human_size
from utils.formatters import datetime_text, safe
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: عدد النسخ في صفحة السجل
BACKUP_PAGE_SIZE = 6


def age_text(hours: float | None) -> str:
    """عمر مقروء: «منذ 35 دقيقة» · «منذ 5 ساعات» · «منذ 3 أيام»."""
    if hours is None:
        return t.BACKUP_NEVER
    minutes = int(hours * 60)
    if minutes < 1:
        return "الآن"
    if minutes < 60:
        return f"منذ {minutes} دقيقة"
    if hours < 48:
        return f"منذ {int(hours)} ساعة"
    return f"منذ {int(hours // 24)} يوماً"


def health_line(summary: BackupSummary) -> str:
    """سطر الحكم العام على حالة النسخ (الأخطر أولاً)."""
    if summary.last_ok is None:
        return t.BACKUP_HEALTH_NONE
    if summary.overdue:
        return t.BACKUP_HEALTH_OVERDUE
    if not summary.auto_enabled:
        return t.BACKUP_HEALTH_AUTO_OFF
    return t.BACKUP_HEALTH_OK


def home_text(summary: BackupSummary, *, notice: str = "") -> str:
    """نص الشاشة الرئيسية (دالة نقية قابلة للاختبار)."""
    if summary.off_server_copy:
        offsite = t.BACKUP_OFFSITE_ON
    elif not summary.channel_configured:
        offsite = t.BACKUP_OFFSITE_NO_CHANNEL
    else:
        offsite = t.BACKUP_OFFSITE_DISABLED
    return t.BACKUP_HOME.format(
        health=health_line(summary),
        last=age_text(summary.age_hours) if summary.last_ok else t.BACKUP_NEVER,
        ok_count=summary.ok_count,
        ok_size=human_size(summary.ok_bytes),
        bad_count=summary.bad_count,
        auto=t.BACKUP_AUTO_ON.format(hours=summary.interval_hours) if summary.auto_enabled else t.BACKUP_AUTO_OFF,
        retention=summary.retention_days,
        min_keep=summary.min_keep,
        offsite=offsite,
        db_size=human_size(summary.db_bytes),
        free=human_size(summary.free_bytes),
        notice=("\n" + notice) if notice else "",
    )


async def _show_home(update: Update, context: ContextTypes.DEFAULT_TYPE, *, notice: str = "") -> None:
    """عرض الشاشة الرئيسية (مشتركة بين فتحها وبعد الإجراءات)."""
    summary = await services_of(context).backups.summary(require_user(context))
    await render(update, context, home_text(summary, notice=notice), backup_home_kb())


async def _show_view(
    update: Update, context: ContextTypes.DEFAULT_TYPE, backup_id: int, page: int, *, notice: str = ""
) -> None:
    """عرض تفاصيل نسخة (مشتركة بين فتحها وبعد الفحص/الإرسال)."""
    services = services_of(context)
    admin = require_user(context)
    info: BackupInfo = await services.backups.get(admin, backup_id)
    creator = t.BACKUP_BY_SYSTEM
    if info.created_by:
        owner = await services.users.get(info.created_by)
        if owner is not None:
            creator = safe(owner.display_name, limit=25)
    perms = await permissions_of(context)
    text = t.BACKUP_VIEW.format(
        id=info.id,
        status=t.BACKUP_STATUS_LABELS.get(info.status, safe(info.status)),
        type=t.BACKUP_TYPE_LABELS.get(info.type, safe(info.type)),
        filename=safe(info.filename),
        size=human_size(info.size_bytes),
        created=datetime_text(info.created_at),
        by=creator,
        schema=safe(info.schema_version or "—"),
        verified=datetime_text(info.verified_at) if info.verified_at else t.BACKUP_VIEW_NEVER,
        channel=(
            t.BACKUP_VIEW_CHANNEL_SENT.format(when=datetime_text(info.channel_sent_at))
            if info.sent_to_channel
            else t.BACKUP_VIEW_CHANNEL_NO
        ),
        sha=safe((info.sha256 or "—")[:24]),
        error=t.BACKUP_VIEW_ERROR.format(error=safe(info.error_text, limit=200)) if info.error_text else "",
        notice=("\n" + notice) if notice else "",
    )
    await render(
        update,
        context,
        text,
        backup_view_kb(
            info.id,
            page,
            perms,
            channel_ready=services.backups.channel_id is not None,
            usable=info.is_ok,
        ),
    )


@guarded
@admin_required(Permission.BACKUP_CREATE)
async def home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الشاشة الرئيسية لقسم النسخ."""
    await answer_callback(update)
    await _show_home(update, context)


@guarded
@admin_required(Permission.BACKUP_CREATE)
async def new_backup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إنشاء نسخة يدوية الآن، وإرسالها للقناة إن كانت مضبوطة ومفعّلة وكان المنفّذ يملك `backup.download`."""
    await answer_callback(update, "⏳ جارٍ إنشاء النسخة…")
    services = services_of(context)
    admin = require_user(context)
    info = await services.backups.create(admin, reason="طلب يدوي من لوحة التحكم")
    notice = t.BACKUP_CREATED.format(id=info.id, size=human_size(info.size_bytes))

    perms = await permissions_of(context)
    wants_channel = (
        services.backups.channel_id is not None
        and Permission.BACKUP_DOWNLOAD in perms
        and await services.settings.get_bool("backup_send_to_channel", True)
    )
    if wants_channel:
        try:
            await services.backups.send_to_channel(admin, context.bot, info.id)
            notice += t.BACKUP_CHANNEL_DONE
        except Exception as exc:                                   # noqa: BLE001
            # الفشل لا يُلغي النسخة (سليمة محلياً)؛ يُسجَّل ويُخبَر الأدمن، والمهمة الدورية تعيد المحاولة
            logger.error("تعذّر إرسال النسخة اليدوية للقناة: %s", type(exc).__name__, exc_info=True)
            notice += t.BACKUP_CREATED_CHANNEL_FAIL
    await _show_home(update, context, notice=notice)


@guarded
@admin_required(Permission.BACKUP_CREATE)
async def list_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """صفحة من سجل النسخ (الأحدث أولاً)."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    requested = args(update).int_arg(0, 1)
    items, total = await services.backups.list_page(admin, page=requested, page_size=BACKUP_PAGE_SIZE)
    page, pages, _offset = paginate(total, requested, BACKUP_PAGE_SIZE)
    if page != requested:                                   # صفحة خارج النطاق ⇒ أعد الجلب للصحيحة
        items, total = await services.backups.list_page(admin, page=page, page_size=BACKUP_PAGE_SIZE)
    if not items:
        await render(update, context, t.BACKUP_LIST_EMPTY, backup_list_kb([], page=1, total_pages=1))
        return
    lines = "\n\n".join(
        t.BACKUP_LIST_LINE.format(
            status=t.BACKUP_STATUS_LABELS.get(info.status, info.status).split(" ", 1)[0],
            id=info.id,
            type=t.BACKUP_TYPE_LABELS.get(info.type, safe(info.type)),
            size=human_size(info.size_bytes),
            when=datetime_text(info.created_at),
            channel=t.BACKUP_LIST_CHANNEL_MARK if info.sent_to_channel else "",
        )
        for info in items
    )
    buttons = [
        (info.id, f"{t.BACKUP_STATUS_LABELS.get(info.status, '•').split(' ', 1)[0]} #{info.id} · "
                  f"{t.BACKUP_TYPE_LABELS.get(info.type, info.type)}")
        for info in items
    ]
    await render(
        update,
        context,
        t.BACKUP_LIST_TITLE.format(page=page, pages=pages, lines=lines),
        backup_list_kb(buttons, page=page, total_pages=pages),
    )


@guarded
@admin_required(Permission.BACKUP_CREATE)
async def view_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تفاصيل نسخة."""
    await answer_callback(update)
    parsed = args(update)
    await _show_view(update, context, parsed.int_arg(0, 0), parsed.int_arg(1, 1))


@guarded
@admin_required(Permission.BACKUP_CREATE)
async def verify_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """فحص نسخة وعرض النتيجة (تتغير حالة النسخة الفاسدة إلى corrupt/missing)."""
    await answer_callback(update, "🔍 جارٍ الفحص…")
    parsed = args(update)
    backup_id, page = parsed.int_arg(0, 0), parsed.int_arg(1, 1)
    result = await services_of(context).backups.verify(require_user(context), backup_id)
    notice = (t.BACKUP_VERIFY_OK if result.ok else t.BACKUP_VERIFY_FAIL).format(message=safe(result.message, limit=200))
    await _show_view(update, context, backup_id, page, notice=notice)


@guarded
@admin_required(Permission.BACKUP_DOWNLOAD)
async def channel_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إرسال نسخة محددة إلى قناة النسخ الخارجية."""
    await answer_callback(update, "📤 جارٍ الإرسال…")
    parsed = args(update)
    backup_id, page = parsed.int_arg(0, 0), parsed.int_arg(1, 1)
    await services_of(context).backups.send_to_channel(require_user(context), context.bot, backup_id)
    await _show_view(update, context, backup_id, page, notice=t.BACKUP_CHANNEL_DONE)


@guarded
@admin_required(Permission.BACKUP_DOWNLOAD)
async def download_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة التأكيد الثانٍ قبل إرسال ملف النسخة لمحادثة الأدمن."""
    await answer_callback(update)
    parsed = args(update)
    backup_id, page = parsed.int_arg(0, 0), parsed.int_arg(1, 1)
    await services_of(context).backups.get(require_user(context), backup_id)    # يتأكد من وجودها أولاً
    await render(
        update,
        context,
        t.BACKUP_DOWNLOAD_ASK.format(id=backup_id),
        backup_confirm_kb(t.BTN_BACKUP_CONFIRM_DL, "dl", backup_id, page, back=("view", (backup_id, page))),
    )


@guarded
@admin_required(Permission.BACKUP_DOWNLOAD)
async def download_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إرسال ملف النسخة إلى محادثة الأدمن (بعد التأكيد، ويُدقَّق)."""
    await answer_callback(update, "⬇️ جارٍ الإرسال…")
    parsed = args(update)
    backup_id, page = parsed.int_arg(0, 0), parsed.int_arg(1, 1)
    chat = update.effective_chat
    if chat is None:
        logger.warning("تنزيل نسخة بلا محادثة فعّالة")
        return
    await services_of(context).backups.download(require_user(context), context.bot, backup_id, chat_id=chat.id)
    await _show_view(update, context, backup_id, page, notice=t.BACKUP_DOWNLOAD_DONE)


@guarded
@admin_required(Permission.BACKUP_CREATE)
async def vacuum_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة التأكيد الثانٍ قبل ضغط القاعدة."""
    await answer_callback(update)
    await render(
        update,
        context,
        t.BACKUP_VACUUM_ASK,
        backup_confirm_kb(t.BTN_BACKUP_CONFIRM_VAC, "vac", back=("home", ())),
    )


@guarded
@admin_required(Permission.BACKUP_CREATE)
async def vacuum_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ضغط القاعدة بعد نسخة أمان إلزامية، وعرض الحجم قبل/بعد."""
    await answer_callback(update, "🧹 جارٍ الضغط…")
    before, after, safety = await services_of(context).backups.vacuum(require_user(context))
    await _show_home(
        update,
        context,
        notice=t.BACKUP_VACUUM_DONE.format(before=human_size(before), after=human_size(after), safety=safety.id),
    )


@guarded
@admin_required(Permission.BACKUP_CREATE)
async def guide_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دليل الاستعادة (نص ثابت: الاستعادة من السيرفر لا من البوت)."""
    await answer_callback(update)
    await render(update, context, t.BACKUP_GUIDE, backup_guide_kb())


def conversations() -> list:
    """لا محادثات في قسم النسخ — شاشات وتأكيدات بأزرار."""
    return []


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم النسخ الاحتياطي."""
    table = (
        ("home", home_screen),
        ("new", new_backup),
        ("list", list_screen),
        ("view", view_screen),
        ("verify", verify_action),
        ("chan", channel_action),
        ("dlask", download_ask),
        ("dl", download_action),
        ("vacask", vacuum_ask),
        ("vac", vacuum_action),
        ("guide", guide_screen),
    )
    return [CallbackQueryHandler(handler, pattern=pattern(NS_ADM_BKP, action)) for action, handler in table]
```

## الإحصائيات والتصدير

### `utils/datetime_utils.py` — مُحدَّث

```python
"""
أدوات الوقت — قاعدة ثابتة في المشروع:

    • كل ما يُخزَّن في قاعدة البيانات بتوقيت UTC وبصيغة ISO-8601 منتهية بحرف Z.
    • التحويل إلى التوقيت المحلي (Asia/Aden افتراضياً) يتم عند العرض فقط.

السبب: خلط التوقيتات يفسد الإحصائيات اليومية ويجعل مقارنة الأوقات غير موثوقة.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

ISO_FORMAT: str = "%Y-%m-%dT%H:%M:%S.%fZ"

#: المنطقة الزمنية المعتمدة للعرض وللمهام اليومية (تُستخدم عند عدم تمرير غيرها)
DEFAULT_TIMEZONE: str = "Asia/Aden"

#: كائن المنطقة الزمنية الجاهز (يحتاجه `run_daily` في JobQueue)
APP_TIMEZONE: ZoneInfo = ZoneInfo(DEFAULT_TIMEZONE)


def utc_now() -> datetime:
    """الوقت الحالي بتوقيت UTC ككائن datetime واعٍ بالمنطقة الزمنية."""
    return datetime.now(UTC)


def to_iso(moment: datetime) -> str:
    """تحويل datetime إلى نص ISO-8601 بتوقيت UTC (الصيغة المعتمدة للتخزين)."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime(ISO_FORMAT)


def utc_now_iso() -> str:
    """الوقت الحالي جاهزاً للتخزين في قاعدة البيانات."""
    return to_iso(utc_now())


def parse_iso(value: str | None) -> datetime | None:
    """تحويل نص مخزَّن إلى datetime، وإرجاع None إذا كانت القيمة فارغة أو غير صالحة."""
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def iso_plus_seconds(seconds: int, *, base: datetime | None = None) -> str:
    """نص ISO لوقت مستقبلي بعد عدد من الثواني (يُستخدم للقفول ومواعيد الفحص)."""
    return to_iso((base or utc_now()) + timedelta(seconds=seconds))


def iso_minus_days(days: int, *, base: datetime | None = None) -> str:
    """نص ISO لوقت ماضٍ قبل عدد من الأيام (يُستخدم في التقارير والتنظيف)."""
    return to_iso((base or utc_now()) - timedelta(days=days))


def is_past(value: str | None) -> bool:
    """هل مرّ هذا الوقت المخزَّن؟ (تُعامل القيمة الفارغة على أنها منتهية)."""
    moment = parse_iso(value)
    return True if moment is None else moment <= utc_now()


def to_local_text(value: str | None, timezone: str = "Asia/Aden", fmt: str = "%Y-%m-%d %H:%M") -> str:
    """
    تحويل وقت مخزَّن (UTC) إلى نص بالتوقيت المحلي للعرض على المستخدم.

    المدخلات:
        value    : النص المخزَّن في قاعدة البيانات.
        timezone : المنطقة الزمنية للعرض.
        fmt      : صيغة العرض.

    المخرجات: نص منسّق، أو "-" إذا لم توجد قيمة.
    """
    moment = parse_iso(value)
    if moment is None:
        return "-"
    try:
        zone = ZoneInfo(timezone)
    except Exception:  # منطقة زمنية غير معروفة — نعرض بتوقيت UTC بدل الانهيار
        zone = UTC
    return moment.astimezone(zone).strftime(fmt)


def day_bounds_utc(days_back: int = 0, timezone: str = "Asia/Aden") -> tuple[str, str]:
    """
    حدود يوم محلي كاملة معبَّراً عنها بتوقيت UTC (لاستعلامات الإحصائيات اليومية).

    المدخلات:
        days_back : 0 = اليوم، 1 = أمس ... إلخ.
        timezone  : المنطقة الزمنية المحلية المعتمدة للعرض.

    المخرجات: (بداية اليوم، نهاية اليوم) كنصين ISO بتوقيت UTC.
    """
    try:
        zone = ZoneInfo(timezone)
    except Exception:
        zone = UTC
    local_now = utc_now().astimezone(zone) - timedelta(days=days_back)
    start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return to_iso(start_local), to_iso(end_local)


def _zone(timezone: str) -> tzinfo:
    """كائن المنطقة الزمنية، وUTC إذا كان الاسم غير معروف (لا نفشل في التقارير بسبب إعداد)."""
    try:
        return ZoneInfo(timezone)
    except Exception:                                      # noqa: BLE001 - اسم منطقة غير صالح/ناقص tzdata
        return UTC


def local_range_utc(
    first_days_back: int, last_days_back: int = 0, timezone: str = DEFAULT_TIMEZONE
) -> tuple[str, str]:
    """
    مدى أيام محلية كاملة بتوقيت UTC: من بداية اليوم `first_days_back` حتى نهاية اليوم `last_days_back`.

    مثال: `(6, 0)` = آخر 7 أيام تقويمية شاملةً اليوم · `(1, 1)` = أمس وحده.
    الحساب بتاريخ المنطقة المحلية (لا بطرح 24 ساعة) فلا ينحرف مع تغيّر التوقيت الصيفي.
    """
    zone = _zone(timezone)
    today = utc_now().astimezone(zone).date()
    start_day = today - timedelta(days=first_days_back)
    end_day = today - timedelta(days=last_days_back) + timedelta(days=1)
    start = datetime(start_day.year, start_day.month, start_day.day, tzinfo=zone)
    end = datetime(end_day.year, end_day.month, end_day.day, tzinfo=zone)
    return to_iso(start), to_iso(end)


def local_month_range_utc(timezone: str = DEFAULT_TIMEZONE) -> tuple[str, str]:
    """من بداية الشهر المحلي الحالي حتى نهاية اليوم المحلي (بتوقيت UTC)."""
    zone = _zone(timezone)
    today = utc_now().astimezone(zone).date()
    start = datetime(today.year, today.month, 1, tzinfo=zone)
    return to_iso(start), local_range_utc(0, 0, timezone)[1]


def local_day_of(value: str | None, timezone: str = DEFAULT_TIMEZONE) -> str | None:
    """تاريخ اليوم المحلي `YYYY-MM-DD` لوقت مخزَّن (None إذا كانت القيمة غير صالحة)."""
    moment = parse_iso(value)
    if moment is None:
        return None
    return moment.astimezone(_zone(timezone)).strftime("%Y-%m-%d")
```

### `services/stats_service.py` — مُحدَّث

```python
"""
خدمة الإحصائيات والتقارير — أرقام حقيقية من قاعدة البيانات فقط.

المبدأ الحاكم: **لا رقم تقديري ولا بيانات وهمية**. كل قيمة هنا ناتجة عن استعلام
فعلي؛ وإن تعذّر حساب قيمة (مثل الربح بلا تكلفة مزود مسجّلة) تُعاد `None` ويُوضَّح
ذلك في العرض بدل اختراع رقم.

دلالة الأرقام (م10 — صُحِّحت عن الإصدارات السابقة):
    • **الإيراد الصافي** = Σ(cost − refund_amount) لطلبات الفترة. الطلب الملغى/الفاشل المسترجَع
      كاملاً لا يُحتسب، والجزئي يُحتسب بما بقي مخصوماً. (سابقاً كان المجموع الخام يُضخّم الإيراد.)
    • **الربح التقديري** للطلبات المنتهية (مكتمل/جزئي) المسجَّلة التكلفة فقط، مع نسبة التغطية
      معلنة؛ والتكلفة الفعلية للجزئي تُقسَّم بنسبة ما بقي مخصوماً.
    • الفترات بأيام **محلية** كاملة (Asia/Aden) لا بطرح 24 ساعة.

المحتوى:
    • لوحة المعلومات السريعة (Dashboard) وملخصات الفترات.
    • تقارير مالية (إيراد، ربح، التزامات المحفظة) وتشغيلية (نجاح، عالق، مزودون).
    • الأفضل: خدمات، عملاء؛ سلسلة يومية؛ تصدير CSV (خطِر: `stats.export`).
    • صحة النظام: الأخطاء، صندوق الإشعارات، حجم قاعدة البيانات، آخر نسخة.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass, field

from core.enums import OrderStatus, TransactionType
from core.exceptions import ValidationError
from core.money import format_units, from_units
from core.permissions import Permission
from database.database import Database
from database.models import User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.provider_service import ProviderService
from services.settings_service import SettingsService
from utils.datetime_utils import (
    DEFAULT_TIMEZONE,
    day_bounds_utc,
    iso_minus_days,
    iso_plus_seconds,
    local_day_of,
    local_month_range_utc,
    local_range_utc,
    to_local_text,
    utc_now_iso,
)
from utils.formatters import datetime_text
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: مفاتيح الفترات المدعومة في الواجهة (بالترتيب المعروض)
PERIOD_KEYS: tuple[str, ...] = ("today", "yesterday", "7d", "30d", "90d", "month")

#: أسماء الفترات بالعربية
PERIOD_LABELS: dict[str, str] = {
    "today": "اليوم",
    "yesterday": "أمس",
    "7d": "آخر 7 أيام",
    "30d": "آخر 30 يوماً",
    "90d": "آخر 90 يوماً",
    "month": "هذا الشهر",
}

#: أنواع التصدير المدعومة
EXPORT_KINDS: tuple[str, ...] = ("orders", "daily")

#: أول محارف خلية CSV التي تجعل Excel/Sheets يفسّرها معادلة (حقن صيغ)
_FORMULA_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r", "\n")

#: أقصى طول لخلية نصية في التصدير
_CELL_LIMIT = 200


@dataclass(frozen=True, slots=True)
class Period:
    """فترة تقرير: مفتاح + اسم عربي + حدود UTC (بداية شاملة، نهاية حصرية)."""

    key: str
    label: str
    start_iso: str
    end_iso: str


def build_period(key: str, timezone: str = DEFAULT_TIMEZONE) -> Period:
    """
    فترة من مفتاحها (`today`/`yesterday`/`7d`/`30d`/`90d`/`month`) بأيام محلية كاملة.

    الاستثناءات: ValidationError لمفتاح غير معروف (قيمة زر عبث بها مستخدم).
    """
    if key == "today":
        start, end = local_range_utc(0, 0, timezone)
    elif key == "yesterday":
        start, end = local_range_utc(1, 1, timezone)
    elif key in ("7d", "30d", "90d"):
        start, end = local_range_utc(int(key[:-1]) - 1, 0, timezone)
    elif key == "month":
        start, end = local_month_range_utc(timezone)
    else:
        raise ValidationError(f"فترة غير معروفة: {key!r}", user_message="❌ فترة غير معروفة.")
    return Period(key=key, label=PERIOD_LABELS[key], start_iso=start, end_iso=end)


def period_for_days(days: int, timezone: str = DEFAULT_TIMEZONE) -> Period:
    """فترة «آخر N يوماً» تقويمية (تشمل اليوم) — مدخل التوافق للواجهات التي تمرّر `days`."""
    days = max(1, int(days))
    start, end = local_range_utc(days - 1, 0, timezone)
    return Period(key=f"{days}d", label=f"آخر {days} يوم", start_iso=start, end_iso=end)


def csv_safe_text(value: object) -> str:
    """
    تحييد خلية نصية قبل كتابتها في CSV.

    • الخلية التي تبدأ بـ`= + - @` أو محرف تحكم تُسبق بفاصلة عليا فلا تُنفَّذ كمعادلة عند فتح الملف.
    • تُقصّ الخلايا الطويلة ويُستبدل فيها فاصل السطر بمسافة (يحافظ على بنية الصف).
    """
    text = "" if value is None else str(value)
    text = text.replace("\r", " ").replace("\n", " ")[:_CELL_LIMIT]
    if text.startswith(_FORMULA_PREFIXES):
        text = "'" + text
    return text


def money_cell(units: int | None) -> str:
    """مبلغ للتصدير كرقم عشري ثابت (بلا رمز عملة ولا فواصل آلاف) أو فارغ إن لم يُحسب."""
    return "" if units is None else f"{from_units(units):.4f}"


@dataclass(slots=True)
class DashboardStats:
    """أرقام لوحة المعلومات الرئيسية (الإيراد صافٍ)."""

    users_total: int
    users_new_today: int
    users_active_7d: int
    users_banned: int
    orders_today: int
    orders_by_status: dict[str, int]
    revenue_today_units: int
    revenue_7d_units: int
    deposits_today_units: int
    pending_payments: int
    open_tickets: int
    queued_notifications: int
    active_services: int
    errors_24h: int

    def as_dict(self) -> dict[str, object]:
        """تحويل الأرقام إلى قاموس (لتسجيلها أو إرسالها كتقرير)."""
        return {
            "users_total": self.users_total,
            "users_new_today": self.users_new_today,
            "users_active_7d": self.users_active_7d,
            "users_banned": self.users_banned,
            "orders_today": self.orders_today,
            "orders_by_status": self.orders_by_status,
            "revenue_today_units": self.revenue_today_units,
            "revenue_7d_units": self.revenue_7d_units,
            "deposits_today_units": self.deposits_today_units,
            "pending_payments": self.pending_payments,
            "open_tickets": self.open_tickets,
            "queued_notifications": self.queued_notifications,
            "active_services": self.active_services,
            "errors_24h": self.errors_24h,
        }


@dataclass(slots=True)
class FinancialReport:
    """
    تقرير مالي لفترة محددة.

    `revenue_units` **صافٍ** (بعد الاسترجاع). `provider_cost_units` تكلفة الطلبات المغطّاة فقط
    (لا كل الطلبات). الربح `None` إن لم يكن مسموحاً أو لا توجد طلبات منتهية مغطّاة.
    """

    start_iso: str
    end_iso: str
    orders_count: int
    revenue_units: int
    provider_cost_units: int
    profit_units: int | None
    deposits_units: int
    refunds_units: int
    partial_refunds_units: int
    manual_credit_units: int
    manual_debit_units: int
    gross_units: int = 0
    order_refund_units: int = 0
    buyers: int = 0
    profit_covered_orders: int = 0
    profit_eligible_orders: int = 0

    @property
    def profit_known(self) -> bool:
        """هل الربح محسوب فعلياً؟ (يتطلب طلبات منتهية مسجَّلة التكلفة وصلاحية الربح)."""
        return self.profit_units is not None

    @property
    def profit_coverage_pct(self) -> int | None:
        """نسبة الطلبات المنتهية التي دخلت حساب الربح (None إن لم توجد طلبات منتهية)."""
        if self.profit_eligible_orders <= 0:
            return None
        return round(self.profit_covered_orders * 100 / self.profit_eligible_orders)


@dataclass(slots=True)
class OperationsReport:
    """تقرير تشغيلي عن جودة التنفيذ."""

    total_orders: int
    completed: int
    partial: int
    failed: int
    canceled: int
    refunded: int
    success_rate: float
    stuck_orders: int
    uncertain_orders: int


@dataclass(slots=True)
class PeriodSummary:
    """ملخص شامل لفترة (شاشة الإحصائيات الرئيسية): المال + التشغيل + المستخدمون."""

    period: Period
    financial: FinancialReport
    by_status: dict[str, int]
    new_users: int
    finished_orders: int
    success_rate: float | None
    avg_order_units: int

    @property
    def active_orders(self) -> int:
        """طلبات الفترة التي لم تنتهِ بعد."""
        return sum(
            self.by_status.get(status, 0)
            for status in (
                OrderStatus.PENDING,
                OrderStatus.SUBMITTING,
                OrderStatus.SUBMIT_UNCERTAIN,
                OrderStatus.SUBMITTED,
                OrderStatus.IN_PROGRESS,
            )
        )


@dataclass(slots=True)
class BuyerRow:
    """عميل في قائمة الأكثر إنفاقاً."""

    name: str
    orders_count: int
    net_units: int


@dataclass(slots=True)
class ExportFile:
    """ملف تصدير جاهز للإرسال."""

    filename: str
    content: bytes
    rows: int
    truncated: bool
    period: Period
    columns: list[str] = field(default_factory=list)


class StatsService:
    """تجميع الإحصائيات والتقارير للوحة الأدمن."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        auth: AuthService,
        providers: ProviderService,
        audit: AuditService | None = None,
    ) -> None:
        """تهيئة الخدمة بالاعتماديات المطلوبة (`audit` لتدقيق التصدير؛ بدونه يُرفض التصدير)."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.auth = auth
        self.providers = providers
        self.audit = audit

    # ===================================================================== #
    #                           لوحة المعلومات                              #
    # ===================================================================== #

    async def dashboard(self, actor: User) -> DashboardStats:
        """
        أرقام لوحة المعلومات السريعة (صلاحية `stats.view`) — الإيراد **صافٍ**.

        الاستثناءات: PermissionDeniedError
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)

        start_today, end_today = day_bounds_utc(0)
        week_start, week_end = local_range_utc(6, 0)
        week_ago = iso_minus_days(7)
        day_ago = iso_minus_days(1)

        return DashboardStats(
            users_total=await self.repos.users.count_all(),
            users_new_today=await self.repos.users.count_since(start_today),
            users_active_7d=await self.repos.users.count_active_since(week_ago),
            users_banned=await self.repos.users.count_banned(),
            orders_today=await self.repos.orders.count_between(start_today, end_today),
            orders_by_status=await self.repos.orders.status_counts(),
            revenue_today_units=await self.repos.orders.sum_net_between(start_today, end_today),
            revenue_7d_units=await self.repos.orders.sum_net_between(week_start, week_end),
            deposits_today_units=await self.repos.payments.sum_approved_between(
                start_today, end_today
            ),
            pending_payments=await self.repos.payments.count_pending(),
            open_tickets=await self.repos.tickets.count_open(),
            queued_notifications=await self.repos.notifications.count_queued(),
            active_services=await self.repos.services.count_active(),
            errors_24h=await self.repos.error_logs.count_since(day_ago),
        )

    async def dashboard_text(self, actor: User) -> str:
        """لوحة المعلومات كنص عربي جاهز للإرسال في تيليجرام."""
        stats = await self.dashboard(actor)
        symbol = await self.settings.money_symbol()
        by_status = stats.orders_by_status
        active = (
            by_status.get(OrderStatus.PENDING, 0)
            + by_status.get(OrderStatus.SUBMITTED, 0)
            + by_status.get(OrderStatus.IN_PROGRESS, 0)
        )
        lines = [
            "📊 <b>لوحة المعلومات</b>",
            "",
            f"👥 المستخدمون: {stats.users_total} (جديد اليوم: {stats.users_new_today})",
            f"🔥 نشطون آخر 7 أيام: {stats.users_active_7d} • محظورون: {stats.users_banned}",
            "",
            f"🧾 طلبات اليوم: {stats.orders_today} • قيد التنفيذ الآن: {active}",
            f"✅ مكتملة: {by_status.get(OrderStatus.COMPLETED, 0)} • "
            f"⚠️ جزئية: {by_status.get(OrderStatus.PARTIAL, 0)} • "
            f"❌ فاشلة: {by_status.get(OrderStatus.FAILED, 0)}",
            f"❓ غير مؤكدة: {by_status.get(OrderStatus.SUBMIT_UNCERTAIN, 0)}",
            "",
            f"💰 مبيعات اليوم (صافي): {format_units(stats.revenue_today_units, symbol=symbol)}",
            f"💰 مبيعات 7 أيام (صافي): {format_units(stats.revenue_7d_units, symbol=symbol)}",
            f"💳 إيداعات اليوم: {format_units(stats.deposits_today_units, symbol=symbol)}",
            "",
            f"🧮 طلبات شحن معلّقة: {stats.pending_payments}",
            f"🎫 تذاكر مفتوحة: {stats.open_tickets}",
            f"📨 إشعارات بانتظار الإرسال: {stats.queued_notifications}",
            f"🛒 خدمات مفعّلة: {stats.active_services}",
            f"🐞 أخطاء آخر 24 ساعة: {stats.errors_24h}",
        ]
        return "\n".join(lines)

    # ===================================================================== #
    #                           التقارير المالية                            #
    # ===================================================================== #

    async def _financial(self, actor: User, period: Period, *, include_profit: bool) -> FinancialReport:
        """بناء التقرير المالي لفترة (الفحص الأمني يجري في الدالة العامة المستدعية)."""
        start, end = period.start_iso, period.end_iso
        totals = await self.repos.orders.period_totals(start, end)
        inputs = await self.repos.orders.profit_inputs(start, end)

        can_see_profit = include_profit and await self.auth.has_permission(actor, Permission.STATS_PROFIT)
        profit: int | None = None
        if can_see_profit and inputs["covered_orders"] > 0:
            profit = inputs["covered_net_units"] - inputs["covered_cost_units"]

        tx = self.repos.transactions
        return FinancialReport(
            start_iso=start,
            end_iso=end,
            orders_count=totals["orders_count"],
            revenue_units=totals["net_units"],
            provider_cost_units=inputs["covered_cost_units"] if can_see_profit else 0,
            profit_units=profit,
            deposits_units=await self.repos.payments.sum_approved_between(start, end),
            refunds_units=await tx.sum_by_type(TransactionType.REFUND, start_iso=start, end_iso=end),
            partial_refunds_units=await tx.sum_by_type(
                TransactionType.PARTIAL_REFUND, start_iso=start, end_iso=end
            ),
            manual_credit_units=await tx.sum_by_type(TransactionType.MANUAL_CREDIT, start_iso=start, end_iso=end),
            manual_debit_units=await tx.sum_by_type(TransactionType.MANUAL_DEBIT, start_iso=start, end_iso=end),
            gross_units=totals["gross_units"],
            order_refund_units=totals["refund_units"],
            buyers=totals["buyers"],
            profit_covered_orders=inputs["covered_orders"] if can_see_profit else 0,
            profit_eligible_orders=inputs["eligible_orders"] if can_see_profit else 0,
        )

    async def financial_report(
        self, actor: User, *, days: int = 7, include_profit: bool = True, period: Period | None = None
    ) -> FinancialReport:
        """
        تقرير مالي لفترة (بالأيام أو بكائن `Period`).

        الربح يُحسب للطلبات المنتهية المسجَّلة التكلفة فقط، ويتطلب عرضه `stats.profit`؛
        وإلا `None` بدل رقم مضلل.
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        return await self._financial(actor, period or period_for_days(days), include_profit=include_profit)

    async def financial_report_text(self, actor: User, *, days: int = 7) -> str:
        """التقرير المالي كنص عربي جاهز للعرض."""
        report = await self.financial_report(actor, days=days)
        symbol = await self.settings.money_symbol()
        lines = [
            f"💼 <b>التقرير المالي — آخر {days} يوم</b>",
            "",
            f"🧾 عدد الطلبات: {report.orders_count}",
            f"💰 صافي المبيعات: {format_units(report.revenue_units, symbol=symbol)} "
            f"(الإجمالي {format_units(report.gross_units, symbol=symbol)} − المسترجع "
            f"{format_units(report.order_refund_units, symbol=symbol)})",
            f"💳 إجمالي الإيداعات المعتمدة: {format_units(report.deposits_units, symbol=symbol)}",
            f"↩️ استرجاع كامل: {format_units(report.refunds_units, symbol=symbol)}",
            f"↩️ استرجاع جزئي: {format_units(report.partial_refunds_units, symbol=symbol)}",
            f"➕ إضافات يدوية: {format_units(report.manual_credit_units, symbol=symbol)}",
            f"➖ خصومات يدوية: {format_units(report.manual_debit_units, symbol=symbol)}",
        ]
        if report.profit_known and report.profit_units is not None:
            lines.append(
                f"📈 الربح التقديري: {format_units(report.profit_units, symbol=symbol)} "
                f"(تكلفة المزود: {format_units(report.provider_cost_units, symbol=symbol)} • "
                f"تغطية {report.profit_coverage_pct}% من الطلبات المنتهية)"
            )
        else:
            lines.append("📈 الربح: غير محسوب — لا طلبات منتهية بتكلفة مزود مسجّلة، أو لا تملك صلاحية الربح.")
        return "\n".join(lines)

    async def summary(self, actor: User, period: Period, *, include_profit: bool = True) -> PeriodSummary:
        """
        ملخص شامل لفترة لشاشة الإحصائيات (`stats.view`؛ الربح لمن يملك `stats.profit` فقط).

        نسبة النجاح = (مكتمل + جزئي) ÷ الطلبات **المنتهية** (لا الجارية): الطلب الجاري لم يُحسم بعد
        فلا يُحسب فشلاً. `None` إن لم يُنهَ أي طلب.
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        financial = await self._financial(actor, period, include_profit=include_profit)
        by_status = await self.repos.orders.status_counts_between(period.start_iso, period.end_iso)
        finished = sum(
            by_status.get(status, 0)
            for status in (
                OrderStatus.COMPLETED,
                OrderStatus.PARTIAL,
                OrderStatus.FAILED,
                OrderStatus.CANCELED,
                OrderStatus.REFUNDED,
            )
        )
        succeeded = by_status.get(OrderStatus.COMPLETED, 0) + by_status.get(OrderStatus.PARTIAL, 0)
        return PeriodSummary(
            period=period,
            financial=financial,
            by_status=by_status,
            new_users=await self.repos.users.count_between(period.start_iso, period.end_iso),
            finished_orders=finished,
            success_rate=round(succeeded * 100 / finished, 1) if finished else None,
            avg_order_units=(financial.revenue_units // financial.orders_count) if financial.orders_count else 0,
        )

    async def wallet_liability(self, actor: User) -> tuple[int, int, int]:
        """
        التزامات المحفظة: (مجموع أرصدة المستخدمين، إجمالي الإيداعات، إجمالي الإنفاق).

        يساعد على معرفة المبلغ المستحق للعملاء في أي لحظة.
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        total_balance = await self.repos.users.total_balance_units()
        deposits = await self.repos.transactions.sum_by_type(TransactionType.DEPOSIT)
        spent = await self.repos.transactions.sum_by_type(TransactionType.ORDER)
        return total_balance, deposits, spent

    # ===================================================================== #
    #                          التقارير التشغيلية                           #
    # ===================================================================== #

    async def operations_report(
        self, actor: User, *, days: int = 7, period: Period | None = None
    ) -> OperationsReport:
        """
        تقرير جودة التنفيذ: نسب الاكتمال والفشل والطلبات التي تحتاج تدخلاً.
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        chosen = period or period_for_days(days)
        start_iso, end_iso = chosen.start_iso, chosen.end_iso

        total = await self.repos.orders.count_between(start_iso, end_iso)
        counts = await self.repos.orders.status_counts_between(start_iso, end_iso)
        completed = counts.get(OrderStatus.COMPLETED, 0)
        partial = counts.get(OrderStatus.PARTIAL, 0)

        stuck_hours = await self.settings.get_int("order_stuck_alert_hours", 24)
        stuck = len(
            await self.repos.orders.stuck_orders(
                before_iso=iso_plus_seconds(-max(1, stuck_hours) * 3600), limit=200
            )
        )
        uncertain = (await self.repos.orders.status_counts()).get(
            OrderStatus.SUBMIT_UNCERTAIN, 0
        )
        success_rate = round((completed + partial) * 100 / total, 1) if total else 0.0

        return OperationsReport(
            total_orders=total,
            completed=completed,
            partial=partial,
            failed=counts.get(OrderStatus.FAILED, 0),
            canceled=counts.get(OrderStatus.CANCELED, 0),
            refunded=counts.get(OrderStatus.REFUNDED, 0),
            success_rate=success_rate,
            stuck_orders=stuck,
            uncertain_orders=uncertain,
        )

    async def top_services(
        self, actor: User, *, days: int = 30, limit: int = 5, period: Period | None = None
    ) -> list[dict]:
        """أكثر الخدمات طلباً خلال فترة (اسم الخدمة، العدد، الصافي `total_units`، الإجمالي `gross_units`)."""
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        chosen = period or period_for_days(days)
        return await self.repos.orders.top_services(
            start_iso=chosen.start_iso, end_iso=chosen.end_iso, limit=limit
        )

    async def top_buyers(
        self, actor: User, *, period: Period, limit: int = 5
    ) -> list[BuyerRow]:
        """أكثر العملاء إنفاقاً صافياً خلال فترة (من طلبات الفترة نفسها لا من عدّاد تراكمي)."""
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        rows = await self.repos.orders.top_buyers(
            start_iso=period.start_iso, end_iso=period.end_iso, limit=limit
        )
        result: list[BuyerRow] = []
        for row in rows:
            user = await self.repos.users.get_by_id(int(row["user_id"]))
            result.append(
                BuyerRow(
                    name=user.display_name if user else f"#{row['user_id']}",
                    orders_count=int(row["orders_count"]),
                    net_units=int(row["net_units"]),
                )
            )
        return result

    async def top_users(
        self, actor: User, *, limit: int = 5, days: int = 30, period: Period | None = None
    ) -> list[tuple[str, int]]:
        """أكثر المستخدمين إنفاقاً صافياً: (الاسم الظاهر، الصافي). غلاف توافق فوق `top_buyers`."""
        buyers = await self.top_buyers(actor, period=period or period_for_days(days), limit=limit)
        return [(row.name, row.net_units) for row in buyers]

    async def _daily(self, period: Period) -> list[dict]:
        """تجميع الطلبات بأيام **محلية** (بلا ملء الأيام الفارغة)."""
        buckets = await self.repos.orders.minute_buckets(period.start_iso, period.end_iso)
        days: dict[str, dict[str, int]] = defaultdict(
            lambda: {"orders_count": 0, "gross_units": 0, "refund_units": 0}
        )
        for bucket in buckets:
            day = local_day_of(f"{bucket['minute']}:00Z")
            if day is None:
                continue
            days[day]["orders_count"] += int(bucket["orders_count"])
            days[day]["gross_units"] += int(bucket["gross_units"])
            days[day]["refund_units"] += int(bucket["refund_units"])
        return [
            {
                "day": day,
                "orders_count": values["orders_count"],
                "gross_units": values["gross_units"],
                "refund_units": values["refund_units"],
                "total_units": values["gross_units"] - values["refund_units"],
            }
            for day, values in sorted(days.items())
        ]

    async def daily_series(
        self, actor: User, *, days: int = 14, period: Period | None = None
    ) -> list[dict]:
        """سلسلة يومية (محلية): عدد الطلبات، الإجمالي، المسترجع، والصافي `total_units`."""
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        return await self._daily(period or period_for_days(days))

    # ===================================================================== #
    #                               التصدير                                 #
    # ===================================================================== #

    async def export_csv(self, actor: User, kind: str, period: Period) -> ExportFile:
        """
        تصدير تقرير كملف CSV (عملية خطِرة: `stats.export`، وتُدقَّق).

        الأنواع: `orders` (طلبات الفترة) · `daily` (ملخص يومي).
        الضمانات: سقف `export_max_rows` (القطع معلن)، تحييد حقن الصيغ في كل خلية نصية،
        عدم تضمين رابط العميل ولا معرّف تيليجرام، وأعمدة الربح لمن يملك `stats.profit` فقط.
        الترميز UTF-8 مع BOM ليفتحه Excel بالعربية صحيحاً.

        الاستثناءات: PermissionDeniedError · ValidationError (نوع غير معروف).
        """
        await self.auth.require_permission(actor, Permission.STATS_EXPORT, context=f"stats.export:{kind}")
        if kind not in EXPORT_KINDS:
            raise ValidationError(f"نوع تصدير غير معروف: {kind!r}", user_message="❌ نوع تصدير غير معروف.")
        if self.audit is None:
            raise ValidationError("خدمة التدقيق غير موصولة", user_message="❌ التصدير غير متاح الآن.")
        include_profit = await self.auth.has_permission(actor, Permission.STATS_PROFIT)
        cap = max(1, await self.settings.get_int("export_max_rows", 20_000))

        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\r\n")
        if kind == "orders":
            columns, rows, truncated = await self._orders_rows(period, cap, include_profit)
        else:
            columns, rows, truncated = await self._daily_rows(period, cap)
        writer.writerow(columns)
        writer.writerows(rows)

        stamp = to_local_text(utc_now_iso(), fmt="%Y%m%d_%H%M")
        filename = f"smm_{kind}_{period.key}_{stamp}.csv"
        await self.audit.log_standalone(
            action="stats.export",
            admin_id=actor.id,
            target_type="report",
            target_id=kind,
            details={
                "period": period.key,
                "rows": len(rows),
                "truncated": truncated,
                "with_profit": include_profit and kind == "orders",
            },
            source="telegram",
        )
        return ExportFile(
            filename=filename,
            content=("\ufeff" + buffer.getvalue()).encode("utf-8"),
            rows=len(rows),
            truncated=truncated,
            period=period,
            columns=columns,
        )

    async def _orders_rows(
        self, period: Period, cap: int, include_profit: bool
    ) -> tuple[list[str], list[list[str]], bool]:
        """أعمدة وصفوف تصدير الطلبات (الأقدم أولاً) مع كشف القطع بسقف الصفوف."""
        fetched = await self.repos.orders.export_rows(period.start_iso, period.end_iso, limit=cap + 1)
        truncated = len(fetched) > cap
        fetched = fetched[:cap]
        columns = [
            "order_id", "code", "created_at_local", "user_id", "service", "quantity",
            "delivered", "status", "gross", "refund", "net",
        ]
        if include_profit:
            columns += ["provider_cost", "est_profit"]
        rows: list[list[str]] = []
        for row in fetched:
            cost, refund = int(row["cost_units"]), int(row["refund_amount_units"])
            line = [
                str(row["id"]),
                csv_safe_text(row["public_code"]),
                to_local_text(row["created_at"], fmt="%Y-%m-%d %H:%M"),
                str(row["user_id"]),
                csv_safe_text(row["service_name"]),
                str(row["quantity"]),
                "" if row["delivered_quantity"] is None else str(row["delivered_quantity"]),
                csv_safe_text(row["status"]),
                money_cell(cost),
                money_cell(refund),
                money_cell(cost - refund),
            ]
            if include_profit:
                provider_cost = row["provider_cost_units"]
                finished = row["status"] in (OrderStatus.COMPLETED, OrderStatus.PARTIAL)
                if provider_cost is None:
                    line += ["", ""]
                else:
                    effective = (int(provider_cost) * (cost - refund)) // cost if cost > 0 else int(provider_cost)
                    line += [money_cell(effective), money_cell(cost - refund - effective) if finished else ""]
            rows.append(line)
        return columns, rows, truncated

    async def _daily_rows(self, period: Period, cap: int) -> tuple[list[str], list[list[str]], bool]:
        """أعمدة وصفوف التصدير اليومي (محلي)."""
        series = await self._daily(period)
        truncated = len(series) > cap
        columns = ["day", "orders", "gross", "refund", "net"]
        rows = [
            [
                item["day"],
                str(item["orders_count"]),
                money_cell(item["gross_units"]),
                money_cell(item["refund_units"]),
                money_cell(item["total_units"]),
            ]
            for item in series[:cap]
        ]
        return columns, rows, truncated

    # ===================================================================== #
    #                            صحة النظام                                 #
    # ===================================================================== #

    async def system_digest(self) -> dict[str, int]:
        """
        أرقام الملخص اليومي — **بلا فاعل بشري**.

        لماذا بلا `actor` ولا فحص صلاحية؟ لأن المستدعي مهمة دورية لا مستخدم،
        والنتيجة لا تُعرض لأحد مباشرة: تُحوَّل إلى إشعار يوزَّع على من يملك
        `stats.view` فعلاً عبر `notify_admins`. فالحارس في مكان التوزيع لا هنا.

        المخرجات: قاموس أرقام جاهز لقالب الإشعار.
        """
        start_today, end_today = day_bounds_utc(0)
        by_status = await self.repos.orders.status_counts()
        today_status = await self.repos.orders.status_counts_between(start_today, end_today)
        totals = await self.repos.orders.period_totals(start_today, end_today)
        attention = sum(
            by_status.get(status, 0)
            for status in (OrderStatus.SUBMIT_UNCERTAIN, OrderStatus.FAILED)
        )
        return {
            "orders_today": totals["orders_count"],
            "revenue_today_units": totals["net_units"],
            "refunds_today_units": totals["refund_units"],
            "completed_today": today_status.get(OrderStatus.COMPLETED, 0) + today_status.get(OrderStatus.PARTIAL, 0),
            "failed_today": today_status.get(OrderStatus.FAILED, 0),
            "deposits_today_units": await self.repos.payments.sum_approved_between(
                start_today, end_today
            ),
            "pending_payments": await self.repos.payments.count_pending(),
            "attention_orders": attention,
            "open_tickets": await self.repos.tickets.count_open(),
            "new_users_today": await self.repos.users.count_since(start_today),
            "errors_24h": await self.repos.error_logs.count_since(iso_minus_days(1)),
        }

    async def system_health(self, actor: User) -> dict[str, object]:
        """
        مؤشرات صحة النظام: المزودون، صندوق الإشعارات، الأخطاء، حجم قاعدة البيانات.

        الاستثناءات: PermissionDeniedError
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)

        providers = await self.repos.providers.list_all()
        provider_rows: list[dict[str, object]] = []
        for provider in providers:
            health = await self.providers.health(provider)
            provider_rows.append(
                {
                    "name": provider.name,
                    "usable": health.is_usable,
                    "reason": health.reason,
                    "consecutive_failures": provider.consecutive_failures,
                    "balance_units": provider.balance_units,
                    "last_success_at": provider.last_success_at,
                }
            )

        db_size_bytes = self.db.path.stat().st_size if self.db.path.exists() else 0
        last_backup = await self.repos.backups.latest(status="ok")
        return {
            "providers": provider_rows,
            "queued_notifications": await self.repos.notifications.count_queued(),
            "errors_24h": await self.repos.error_logs.count_since(iso_minus_days(1)),
            "db_size_mb": round(db_size_bytes / (1024 * 1024), 2),
            "db_path": str(self.db.path),
            "last_backup_at": (last_backup or {}).get("created_at"),
        }

    async def health_text(self, actor: User) -> str:
        """مؤشرات صحة النظام كنص عربي."""
        health = await self.system_health(actor)
        symbol = await self.settings.money_symbol()
        lines = ["🩺 <b>صحة النظام</b>", ""]

        providers = health["providers"]
        if isinstance(providers, list) and providers:
            for row in providers:
                mark = "🟢" if row["usable"] else "🔴"
                lines.append(
                    f"{mark} {row['name']} — {row['reason']} • "
                    f"رصيد: {format_units(int(row['balance_units']), symbol=symbol)}"
                )
        else:
            lines.append("⚠️ لا يوجد مزودون مسجّلون بعد.")

        lines += [
            "",
            f"📨 إشعارات بانتظار الإرسال: {health['queued_notifications']}",
            f"🐞 أخطاء آخر 24 ساعة: {health['errors_24h']}",
            f"🗄 حجم قاعدة البيانات: {health['db_size_mb']} ميغابايت",
            (
                f"💾 آخر نسخة سليمة: {datetime_text(str(health['last_backup_at']))}"
                if health["last_backup_at"]
                else "⚠️ 💾 لا توجد نسخة احتياطية سليمة بعد"
            ),
        ]
        return "\n".join(lines)
```

### `jobs/report_jobs.py` — مُحدَّث

```python
"""
مهام التقارير الدورية (المرحلة 6).

حالياً مهمة واحدة: **الملخص اليومي للأدمن**.

لماذا؟
    لوحة التحكم تعرض الأرقام لمن يدخلها، لكن النظام الذي يعمل وحده يحتاج أن
    يتكلم: رسالة واحدة في وقت محدد يومياً تختصر حركة اليوم وما ينتظر تدخلاً.
    وهي كذلك نبضة حياة: غيابها مؤشر على أن شيئاً ما توقف.

الملخص يمر عبر طابور الإشعارات كغيره (`notify_admins`) فلا يرتبط نجاحه
باتصال الشبكة لحظة التوليد، ولا يُرسل مرتين لنفس اليوم (رمز منع التكرار).
"""

from __future__ import annotations

from telegram.ext import ContextTypes

from core.enums import OrderStatus
from core.permissions import Permission
from texts import templates
from utils.datetime_utils import day_bounds_utc
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: الحالات التي تعني «طلب يحتاج تدخل الأدمن الآن»
ATTENTION_STATUSES = (OrderStatus.SUBMIT_UNCERTAIN, OrderStatus.FAILED)


async def send_admin_daily_digest(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    إرسال الملخص اليومي لكل من يملك `stats.view`.

    المخرجات: True إذا أُدرج الملخص في الطابور (False إذا كان قد أُرسل اليوم).
    """
    services = context.application.bot_data["services"]
    digest = await services.stats.system_digest()
    symbol = await services.settings.money_symbol()
    today = day_bounds_utc(0)[0][:10]

    title, message = templates.admin_daily_digest(
        orders_today=digest["orders_today"],
        revenue_today_units=digest["revenue_today_units"],
        deposits_today_units=digest["deposits_today_units"],
        pending_payments=digest["pending_payments"],
        attention_orders=digest["attention_orders"],
        open_tickets=digest["open_tickets"],
        new_users=digest["new_users_today"],
        errors_24h=digest["errors_24h"],
        refunds_today_units=digest["refunds_today_units"],
        completed_today=digest["completed_today"],
        failed_today=digest["failed_today"],
        symbol=symbol,
    )

    async with services.db.transaction() as tx:
        inserted = await services.notifications.notify_admins(
            tx,
            permission=Permission.STATS_VIEW,
            token=f"digest:{today}",
            title=title,
            message=message,
        )

    if inserted:
        logger.info("أُدرج الملخص اليومي لـ%s أدمن", inserted)
    else:
        logger.info("الملخص اليومي لـ%s أُرسل سابقاً — تم تخطّيه", today)
    return bool(inserted)
```

### `handlers/admin/stats.py` — جديد

```python
"""
قسم «📈 الإحصائيات» في لوحة التحكم (المرحلة 10).

الشاشات (مساحة `st`):
    st:home:<p>          : ملخص الفترة (طلبات، إيراد صافٍ، مسترجع، ربح تقديري، مستخدمون).
    st:svc:<p>           : أكثر الخدمات طلباً.
    st:usr:<p>           : أكثر العملاء إنفاقاً صافياً.
    st:day:<p>           : سلسلة يومية (بأيام محلية).
    st:wal               : التزامات المحفظة.
    st:expm:<p>          : قائمة التصدير (`stats.export`).
    st:expask:<k>:<p>    : تأكيد ثانٍ قبل التصدير.
    st:exp:<k>:<p>       : إرسال ملف CSV (يُدقَّق).

الفترات: today · yesterday · 7d · 30d · 90d · month (أيام محلية كاملة).

قواعد ملزمة:
    • كل شاشة تفحص `stats.view` على الـcallback؛ التصدير `stats.export` (والخدمة تعيد الفحص).
    • الربح يظهر لمن يملك `stats.profit` فقط (الخدمة لا تحسبه لغيره أصلاً).
    • لا أرقام تقديرية مخفية: التغطية معلنة، و«غير محسوب» يُقال صراحة.
"""

from __future__ import annotations

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler, ContextTypes

from core.permissions import Permission
from handlers.admin.common import admin_required, args, permissions_of, symbol_of
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    stats_export_confirm_kb,
    stats_export_menu_kb,
    stats_home_kb,
    stats_sub_kb,
    stats_wallet_kb,
)
from keyboards.callback_data import NS_ADM_STATS, pattern
from middlewares.context import require_user, services_of
from services.stats_service import EXPORT_KINDS, PeriodSummary, build_period
from texts import admin_ar as t
from utils.formatters import money_text, safe
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: أقصى عدد أيام تُعرض في الشاشة اليومية (حد رسالة تيليجرام 4096 حرفاً)
DAILY_MAX_LINES = 31

#: عرض شريط الاتجاه اليومي بالمربعات
BAR_WIDTH = 8


def summary_text(summary: PeriodSummary, symbol: str, *, can_see_profit: bool) -> str:
    """
    نص ملخص الفترة (دالة نقية قابلة للاختبار).

    الربح: يُعرض لمن يملك `stats.profit` فقط. إن لم تُغطَّ كل الطلبات المنتهية يُنبَّه صراحة.
    """
    report = summary.financial
    profit = ""
    if can_see_profit:
        if report.profit_units is None:
            profit = t.STATS_PROFIT_NONE
        else:
            profit = t.STATS_PROFIT_LINE.format(
                profit=money_text(report.profit_units, symbol),
                cost=money_text(report.provider_cost_units, symbol),
                pct=report.profit_coverage_pct if report.profit_coverage_pct is not None else 0,
                covered=report.profit_covered_orders,
                eligible=report.profit_eligible_orders,
            )
            if report.profit_covered_orders < report.profit_eligible_orders:
                profit += t.STATS_PROFIT_PARTIAL_NOTE
    return t.STATS_HOME.format(
        label=summary.period.label,
        orders=report.orders_count,
        active=summary.active_orders,
        finished=summary.finished_orders,
        success=(f"{summary.success_rate}%" if summary.success_rate is not None else t.STATS_NO_SUCCESS),
        gross=money_text(report.gross_units, symbol),
        refund=money_text(report.order_refund_units, symbol),
        net=money_text(report.revenue_units, symbol),
        avg=money_text(summary.avg_order_units, symbol),
        profit=profit,
        buyers=report.buyers,
        new_users=summary.new_users,
        deposits=money_text(report.deposits_units, symbol),
        credit=money_text(report.manual_credit_units, symbol),
        debit=money_text(report.manual_debit_units, symbol),
    )


def _bar(value: int, peak: int) -> str:
    """شريط مربعات نسبي لاتجاه يومي (فارغ إن لم يوجد إيراد)."""
    if peak <= 0 or value <= 0:
        return "▫️"
    filled = max(1, round(value * BAR_WIDTH / peak))
    return "█" * filled


def _period_key(update: Update, index: int = 0) -> str:
    """مفتاح الفترة من وسائط الزر (الافتراضي: اليوم). القيم الغريبة يرفضها `build_period`."""
    return args(update).arg(index) or "today"


@guarded
@admin_required(Permission.STATS_VIEW)
async def home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ملخص الفترة المختارة."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    period = build_period(_period_key(update))
    perms = await permissions_of(context)
    summary = await services.stats.summary(admin, period)
    text = summary_text(summary, await symbol_of(context), can_see_profit=Permission.STATS_PROFIT in perms)
    await render(update, context, text, stats_home_kb(period.key, perms))


@guarded
@admin_required(Permission.STATS_VIEW)
async def services_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """أكثر الخدمات طلباً في الفترة."""
    await answer_callback(update)
    period = build_period(_period_key(update))
    rows = await services_of(context).stats.top_services(require_user(context), period=period, limit=10)
    if not rows:
        await render(update, context, t.STATS_SERVICES_EMPTY.format(label=period.label), stats_sub_kb("svc", period.key))
        return
    symbol = await symbol_of(context)
    lines = "\n".join(
        t.STATS_SERVICES_LINE.format(
            rank=index,
            name=safe(row["service_name"], limit=40),
            count=row["orders_count"],
            net=money_text(int(row["total_units"]), symbol),
        )
        for index, row in enumerate(rows, start=1)
    )
    await render(
        update, context, t.STATS_SERVICES_TITLE.format(label=period.label, lines=lines), stats_sub_kb("svc", period.key)
    )


@guarded
@admin_required(Permission.STATS_VIEW)
async def buyers_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """أكثر العملاء إنفاقاً صافياً في الفترة."""
    await answer_callback(update)
    period = build_period(_period_key(update))
    buyers = await services_of(context).stats.top_buyers(require_user(context), period=period, limit=10)
    if not buyers:
        await render(update, context, t.STATS_BUYERS_EMPTY.format(label=period.label), stats_sub_kb("usr", period.key))
        return
    symbol = await symbol_of(context)
    lines = "\n".join(
        t.STATS_BUYERS_LINE.format(
            rank=index,
            name=safe(row.name, limit=30),
            count=row.orders_count,
            net=money_text(row.net_units, symbol),
        )
        for index, row in enumerate(buyers, start=1)
    )
    await render(
        update, context, t.STATS_BUYERS_TITLE.format(label=period.label, lines=lines), stats_sub_kb("usr", period.key)
    )


@guarded
@admin_required(Permission.STATS_VIEW)
async def daily_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """سلسلة يومية بأيام محلية مع شريط اتجاه، والمجموع يشمل كل الأيام حتى المقطوعة من العرض."""
    await answer_callback(update)
    period = build_period(_period_key(update))
    series = await services_of(context).stats.daily_series(require_user(context), period=period)
    if not series:
        await render(update, context, t.STATS_DAILY_EMPTY.format(label=period.label), stats_sub_kb("day", period.key))
        return
    symbol = await symbol_of(context)
    shown = series[-DAILY_MAX_LINES:]
    peak = max(int(item["total_units"]) for item in shown)
    lines = "\n".join(
        t.STATS_DAILY_LINE.format(
            day=item["day"],
            bar=_bar(int(item["total_units"]), peak),
            count=item["orders_count"],
            net=money_text(int(item["total_units"]), symbol),
        )
        for item in shown
    )
    footer = t.STATS_DAILY_FOOTER.format(
        count=sum(int(item["orders_count"]) for item in series),
        net=money_text(sum(int(item["total_units"]) for item in series), symbol),
    )
    if len(series) > len(shown):
        footer = t.STATS_DAILY_CUT.format(shown=len(shown), total=len(series)).strip() + "\n" + footer
    await render(
        update,
        context,
        t.STATS_DAILY_TITLE.format(label=period.label, lines=lines, footer=footer),
        stats_sub_kb("day", period.key),
    )


@guarded
@admin_required(Permission.STATS_VIEW)
async def wallet_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """التزامات المحفظة: ما يدين به النظام للعملاء الآن."""
    await answer_callback(update)
    balance, deposits, spent = await services_of(context).stats.wallet_liability(require_user(context))
    symbol = await symbol_of(context)
    await render(
        update,
        context,
        t.STATS_WALLET.format(
            balance=money_text(balance, symbol), deposits=money_text(deposits, symbol), spent=money_text(spent, symbol)
        ),
        stats_wallet_kb(),
    )


@guarded
@admin_required(Permission.STATS_EXPORT)
async def export_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة اختيار نوع التقرير للتصدير."""
    await answer_callback(update)
    period = build_period(_period_key(update))
    cap = await services_of(context).settings.get_int("export_max_rows", 20_000)
    await render(
        update, context, t.STATS_EXPORT_MENU.format(label=period.label, cap=cap), stats_export_menu_kb(period.key)
    )


def _kind_of(update: Update) -> str:
    """نوع التصدير من وسائط الزر؛ أي قيمة غير معروفة تُنقل كما هي لترفضها الخدمة."""
    return args(update).arg(0)


@guarded
@admin_required(Permission.STATS_EXPORT)
async def export_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة التأكيد الثانٍ للتصدير (لا يُنشأ أي ملف هنا)."""
    await answer_callback(update)
    kind = _kind_of(update)
    period = build_period(_period_key(update, 1))
    if kind not in EXPORT_KINDS:
        await answer_callback(update, "❌ نوع تصدير غير معروف.", alert=True)
        return
    await render(
        update,
        context,
        t.STATS_EXPORT_ASK.format(kind=t.STATS_EXPORT_KIND_LABELS[kind], label=period.label),
        stats_export_confirm_kb(kind, period.key),
    )


@guarded
@admin_required(Permission.STATS_EXPORT)
async def export_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إنشاء ملف CSV وإرساله لمحادثة الأدمن (الخدمة تتحقق من الصلاحية وتُدقّق)."""
    await answer_callback(update, "⏳ جارٍ التجهيز…")
    kind = _kind_of(update)
    period = build_period(_period_key(update, 1))
    chat = update.effective_chat
    if chat is None:
        logger.warning("تصدير بلا محادثة فعّالة")
        return
    exported = await services_of(context).stats.export_csv(require_user(context), kind, period)
    caption = t.STATS_EXPORT_CAPTION.format(
        kind=t.STATS_EXPORT_KIND_LABELS.get(kind, kind),
        label=period.label,
        rows=exported.rows,
        cut=t.STATS_EXPORT_CUT if exported.truncated else "",
    )
    try:
        await context.bot.send_document(
            chat_id=chat.id,
            document=exported.content,
            filename=exported.filename,
            caption=caption,
            protect_content=True,
        )
    except TelegramError as exc:
        logger.error("فشل إرسال ملف التصدير: %s", type(exc).__name__, exc_info=True)
        await send(update, context, f"❌ تعذّر إرسال الملف عبر تيليجرام: {safe(str(exc), limit=120)}")
        return
    await send(update, context, t.STATS_EXPORT_DONE.format(rows=exported.rows), stats_export_menu_kb(period.key))


def conversations() -> list:
    """لا محادثات في قسم الإحصائيات — شاشات وأزرار فقط."""
    return []


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم الإحصائيات."""
    table = (
        ("home", home_screen),
        ("svc", services_screen),
        ("usr", buyers_screen),
        ("day", daily_screen),
        ("wal", wallet_screen),
        ("expm", export_menu),
        ("expask", export_ask),
        ("exp", export_action),
    )
    return [CallbackQueryHandler(handler, pattern=pattern(NS_ADM_STATS, action)) for action, handler in table]
```

## السجلات (تدقيق/أخطاء/استدعاءات المزودين)

### `services/audit_service.py` — مُحدَّث

```python
"""
خدمة سجل التدقيق: تسجيل كل عملية إدارية حسّاسة بمن نفّذها وما تغيّر.

قاعدة المشروع: أي إجراء إداري يمسّ المال أو الصلاحيات أو بيانات المستخدمين
يجب أن يترك أثراً في هذا السجل — والسجل لا يُحذف.
"""

from __future__ import annotations

from typing import Any

from core.exceptions import ValidationError
from database.database import Database, Tx
from database.models import AuditLog
from database.repositories import Repositories
from utils.logging_setup import get_logger
from utils.security import sanitize

logger = get_logger(__name__)

#: فئات فلتر سجل التدقيق: مفتاح الفئة ← بادئات أسماء الإجراءات الفعلية المسجَّلة في النظام.
#: (الفئة `all` بلا بادئات = كل السجلات). لا تداخل بين الفئات عمداً حتى يطابق العدّ ما يُعرض.
AUDIT_CATEGORIES: dict[str, tuple[str, ...]] = {
    "all": (),
    "users": ("users.register", "users.role", "users.ban", "users.unban", "users.note"),
    "money": ("payments.", "users.balance."),
    "orders": ("orders.",),
    "catalog": ("services.", "providers."),
    "tickets": ("tickets.",),
    "settings": ("settings.", "notifications.", "broadcast."),
    "security": ("security.", "admins.", "admin."),
    "system": ("backup.", "stats.", "system."),
}


class AuditService:
    """كتابة وقراءة سجل التدقيق."""

    def __init__(self, db: Database, repos: Repositories) -> None:
        """تهيئة الخدمة."""
        self.db = db
        self.repos = repos

    # ------------------------------- الكتابة ------------------------------ #

    async def log(
        self,
        tx: Tx,
        *,
        action: str,
        admin_id: int | None = None,
        target_type: str | None = None,
        target_id: str | int | None = None,
        before: Any = None,
        after: Any = None,
        details: Any = None,
        source: str = "telegram",
    ) -> int | None:
        """
        تسجيل عملية داخل معاملة قائمة (حتى يسقط السجل مع العملية إن فشلت).

        ملاحظة أمنية: كل النصوص تمر على أداة تنقية الأسرار قبل التخزين.
        """
        return await self.repos.audit.log(
            tx,
            action=action,
            admin_id=admin_id,
            target_type=target_type,
            target_id=target_id,
            before=_clean(before),
            after=_clean(after),
            details=_clean(details),
            source=source,
        )

    async def log_standalone(
        self,
        *,
        action: str,
        admin_id: int | None = None,
        target_type: str | None = None,
        target_id: str | int | None = None,
        details: Any = None,
        source: str = "system",
    ) -> int | None:
        """تسجيل عملية بمعاملة مستقلة (عندما لا توجد معاملة جارية)."""
        async with self.db.transaction() as tx:
            return await self.log(
                tx,
                action=action,
                admin_id=admin_id,
                target_type=target_type,
                target_id=target_id,
                details=details,
                source=source,
            )

    async def log_permission_denied(
        self, *, user_id: int, permission: str, context: str = ""
    ) -> None:
        """
        تسجيل محاولة وصول مرفوضة.

        تُسجَّل دائماً لأنها مؤشر أمني مهم (محاولة استخدام زر إداري بلا صلاحية).
        """
        async with self.db.transaction() as tx:
            await self.repos.audit.log(
                tx,
                action="security.permission_denied",
                admin_id=user_id,
                target_type="permission",
                target_id=permission,
                details={"context": sanitize(context)},
                source="security",
            )
        logger.warning("رُفض وصول المستخدم %s إلى الصلاحية %s (%s)", user_id, permission, context)

    async def log_security_event(
        self,
        *,
        event: str,
        user_id: int | None,
        target_type: str | None = None,
        target_id: str | int | None = None,
        details: Any = None,
    ) -> None:
        """
        تسجيل حدث أمني مستقل (معاملة خاصة به) — يبقى حتى لو فشلت العملية الأصلية.

        المدخلات:
            event   : اسم الحدث بلا بادئة (مثل `hierarchy_denied`) فيُخزَّن `security.<event>`.
            user_id : المستخدم المنفِّذ (أو None لحدث نظام).

        لماذا معاملة منفصلة؟ الأحداث الأمنية تُسجَّل غالباً لحظة رفض العملية،
        والعملية المرفوضة تتراجع — ولو شاركتها المعاملة لضاع الأثر مع التراجع.
        """
        async with self.db.transaction() as tx:
            await self.repos.audit.log(
                tx,
                action=f"security.{event}",
                admin_id=user_id,
                target_type=target_type,
                target_id=target_id,
                details=_clean(details),
                source="security",
            )
        logger.warning("حدث أمني %s: المستخدم %s ← %s:%s %s", event, user_id, target_type, target_id, details)

    # ------------------------------- القراءة ------------------------------ #

    async def recent(self, *, limit: int = 20, offset: int = 0) -> list[AuditLog]:
        """أحدث عمليات التدقيق (لعرضها في اللوحة)."""
        return await self.repos.audit.list_recent(limit=limit, offset=offset)

    async def by_admin(self, admin_id: int, *, limit: int = 20, offset: int = 0) -> list[AuditLog]:
        """سجل عمليات أدمن محدد."""
        return await self.repos.audit.list_by_admin(admin_id, limit=limit, offset=offset)

    async def by_target(self, target_type: str, target_id: str | int, *, limit: int = 20) -> list[AuditLog]:
        """سجل العمليات التي جرت على هدف محدد (مستخدم، طلب، إعداد…)."""
        return await self.repos.audit.list_by_target(target_type, target_id, limit=limit)

    async def count(self) -> int:
        """إجمالي عدد السجلات."""
        return await self.repos.audit.count_all()

    async def recent_errors(self, *, limit: int = 10, offset: int = 0) -> list[dict]:
        """
        آخر الأخطاء المسجَّلة في `error_logs` (شاشة «السجلات ← الأخطاء»).

        وُضعت هنا لأن شاشة السجلات واحدة في لوحة الأدمن: التدقيق والأخطاء معاً،
        وفحص صلاحية `logs.view` يتم في طبقة المعالجات قبل الوصول إليها.
        """
        return await self.repos.error_logs.list_recent(limit=limit, offset=offset)

    # ----------------------- الفلترة والتفاصيل (المرحلة 10) ---------------------- #

    @staticmethod
    def category_prefixes(category: str) -> tuple[str, ...]:
        """بادئات فئة فلتر؛ فئة غير معروفة ترفع `ValidationError` (لا تُحوَّل صامتاً إلى «الكل»)."""
        if category not in AUDIT_CATEGORIES:
            raise ValidationError(f"فئة سجل غير معروفة: {category!r}", user_message="❌ فئة سجل غير معروفة.")
        return AUDIT_CATEGORIES[category]

    async def list_filtered(self, category: str = "all", *, limit: int = 8, offset: int = 0) -> list[AuditLog]:
        """صفحة من سجل التدقيق ضمن فئة (الأحدث أولاً)."""
        return await self.repos.audit.list_by_prefixes(self.category_prefixes(category), limit=limit, offset=offset)

    async def count_filtered(self, category: str = "all") -> int:
        """عدد سجلات التدقيق ضمن فئة (لحساب الصفحات)."""
        return await self.repos.audit.count_by_prefixes(self.category_prefixes(category))

    async def get_entry(self, audit_id: int) -> AuditLog | None:
        """سجل تدقيق واحد بمعرّفه."""
        return await self.repos.audit.get(audit_id)

    async def count_errors(self) -> int:
        """إجمالي الأخطاء المسجلة (لترقيم شاشة الأخطاء بدقة)."""
        return await self.repos.error_logs.count_all()

    async def get_error(self, error_id: int) -> dict | None:
        """خطأ واحد بمعرّفه (لشاشة التفاصيل)."""
        return await self.repos.error_logs.get(error_id)

    async def provider_calls(self, *, only_failed: bool = False, limit: int = 8, offset: int = 0) -> list[dict]:
        """صفحة من سجل استدعاءات المزودين (الأحدث أولاً)."""
        return await self.repos.provider_requests.list_page(only_failed=only_failed, limit=limit, offset=offset)

    async def count_provider_calls(self, *, only_failed: bool = False) -> int:
        """عدد استدعاءات المزودين (أو الفاشلة فقط)."""
        return await self.repos.provider_requests.count_calls(only_failed=only_failed)

    async def get_provider_call(self, request_id: int) -> dict | None:
        """استدعاء مزود واحد بمعرّفه."""
        return await self.repos.provider_requests.get_call(request_id)

    async def errors_since(self, since_iso: str) -> int:
        """عدد الأخطاء منذ وقت محدد (يُعرض كمؤشر في رأس شاشة الأخطاء)."""
        return await self.repos.error_logs.count_since(since_iso)


def _clean(value: Any) -> Any:
    """تنقية القيم النصية من الأسرار قبل حفظها في السجل."""
    if value is None:
        return None
    if isinstance(value, str):
        return sanitize(value)
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    return value
```

### `handlers/admin/logs.py` — مُحدَّث

```python
"""
قسم «📝 السجلات» في لوحة التحكم: التدقيق والأخطاء واستدعاءات المزودين.

لماذا هذه الشاشة مهمة؟
    سجل التدقيق هو الجواب على سؤال «من فعل ماذا ومتى» — وهو شرط أساسي في
    أي نظام يتعامل مع أموال. عرضه داخل البوت يعني ألا يحتاج صاحب النظام
    فتح قاعدة البيانات ليعرف ما جرى.

الشاشات (مساحة `al`):
    al:home                       : اختيار السجل.
    al:audit:<p> / al:acat:<c>:<p>: سجل التدقيق (كل السجلات / ضمن فئة) مع ترقيم دقيق.
    al:afl[:<c>]                  : قائمة فلتر الفئات.
    al:aud:<id>:<c>:<p>           : تفاصيل سجل تدقيق (قبل/بعد/تفاصيل).
    al:errors:<p> / al:err:<id>:<p>: قائمة الأخطاء وتفصيل الخطأ.
    al:prq|prqf:<p> / al:prqd:<id>:<m>:<p> : استدعاءات المزودين (الكل/الفاشلة) وتفصيل الاستدعاء.

ملاحظات:
    • العرض للقراءة فقط — لا تعديل ولا حذف لأي سجل من الواجهة إطلاقاً.
    • كل شاشة تفحص `logs.view` على الـcallback نفسه.
    • النصوص تُنقّى من الأسرار مرة ثانية عند العرض (دفاع متعدد الطبقات) وتُهرَّب وتُقتطع.
"""

from __future__ import annotations

import json

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from core.permissions import Permission
from handlers.admin.common import (
    LOG_PAGE_SIZE,
    admin_required,
    args,
    paginate,
)
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render
from keyboards.admin_kb import (
    logs_audit_detail_kb,
    logs_audit_filter_kb,
    logs_audit_kb,
    logs_call_detail_kb,
    logs_calls_kb,
    logs_error_detail_kb,
    logs_errors_kb,
    logs_home_kb,
    logs_page_kb,
)
from keyboards.callback_data import NS_ADM_LOG, pattern
from middlewares.context import services_of
from services.audit_service import AUDIT_CATEGORIES
from texts import admin_ar as t
from utils.formatters import datetime_text, safe
from utils.security import sanitize

#: أقصى طول لكتلة JSON/نص في شاشة التفاصيل (حد رسالة تيليجرام 4096 حرفاً مع بقية الحقول)
DETAIL_BLOCK_LIMIT = 700


def _audit_icon(action: str) -> str:
    """اختيار أيقونة السطر حسب بادئة اسم الإجراء (users.ban ⇐ 👤)."""
    prefix = (action or "").split(".", 1)[0]
    return t.AUDIT_ICONS.get(prefix, "🔸")


def _pretty(raw: str | None) -> str:
    """
    تهيئة قيمة JSON مخزّنة للعرض: تنسيق مقروء، تنقية أسرار، اقتطاع، تهريب HTML.

    إن لم تكن القيمة JSON صالحاً تُعرض كنص كما هي (بعد التنقية).
    """
    if not raw:
        return ""
    try:
        text = json.dumps(json.loads(raw), ensure_ascii=False, indent=1)
    except (TypeError, ValueError):
        text = raw
    return safe(sanitize(text), limit=DETAIL_BLOCK_LIMIT)


def _category_arg(update: Update, index: int) -> str:
    """فئة الفلتر من وسائط الزر (الافتراضي all)؛ القيمة الغريبة تُرفض لاحقاً في الخدمة."""
    return args(update).arg(index) or "all"


async def _admin_label(services, cache: dict[int, str], admin_id: int | None) -> str:
    """اسم منفّذ العملية للعرض (مع تخزين مؤقت داخل الشاشة الواحدة)."""
    if not admin_id:
        return "النظام"
    if admin_id not in cache:
        user = await services.users.get(admin_id)
        cache[admin_id] = user.display_name if user else str(admin_id)
    return cache[admin_id]


@guarded
@admin_required(Permission.LOGS_VIEW)
async def logs_home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة اختيار السجل."""
    await answer_callback(update)
    await render(update, context, t.LOGS_HOME, logs_home_kb())


@guarded
@admin_required(Permission.LOGS_VIEW)
async def audit_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    سجل التدقيق: آخر العمليات الإدارية مع منفّذها وهدفها ووقتها.

    الأزرار: `al:audit:<page>` (كل السجلات) و`al:acat:<category>:<page>` (ضمن فئة).
    """
    await answer_callback(update)
    services = services_of(context)
    call = args(update)
    if call.action == "acat":
        category, page_arg = _category_arg(update, 0), call.int_arg(1, 1)
    else:
        category, page_arg = "all", call.int_arg(0, 1)
    label = t.AUDIT_CATEGORY_LABELS.get(category, category)
    total = await services.audit.count_filtered(category)
    page, total_pages, offset = paginate(total, page_arg, LOG_PAGE_SIZE)
    entries = await services.audit.list_filtered(category, limit=LOG_PAGE_SIZE, offset=offset)

    if not entries:
        await render(
            update,
            context,
            t.AUDIT_EMPTY.format(category=label),
            logs_audit_kb([], category=category, page=1, total_pages=1),
        )
        return

    admins: dict[int, str] = {}
    lines: list[str] = []
    for entry in entries:
        target = f"{entry.target_type}:{entry.target_id}" if entry.target_type else "—"
        lines.append(
            t.AUDIT_LINE.format(
                id=entry.id,
                icon=_audit_icon(entry.action),
                action=safe(entry.action, limit=40),
                admin=safe(await _admin_label(services, admins, entry.admin_id), limit=25),
                target=safe(target, limit=30),
                when=datetime_text(entry.created_at),
            )
        )

    await render(
        update,
        context,
        t.AUDIT_TITLE.format(
            category=label, total=total, page=page, pages=total_pages, lines="\n\n".join(lines)
        ),
        logs_audit_kb([entry.id for entry in entries], category=category, page=page, total_pages=total_pages),
    )


@guarded
@admin_required(Permission.LOGS_VIEW)
async def audit_filter_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة فئات الفلتر (لا تغيّر أي بيانات؛ الاختيار زر `acat`)."""
    await answer_callback(update)
    category = _category_arg(update, 0)
    await render(update, context, t.AUDIT_FILTER_MENU, logs_audit_filter_kb(category if category in AUDIT_CATEGORIES else "all"))


@guarded
@admin_required(Permission.LOGS_VIEW)
async def audit_detail_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تفاصيل سجل تدقيق: الإجراء، المنفّذ، الهدف، المصدر، وقيم قبل/بعد/تفاصيل مُنقّاة."""
    await answer_callback(update)
    services = services_of(context)
    call = args(update)
    category, page = _category_arg(update, 1), max(1, call.int_arg(2, 1))
    if category not in AUDIT_CATEGORIES:
        category = "all"
    entry = await services.audit.get_entry(call.int_arg(0, 0))
    if entry is None:
        await render(update, context, t.AUDIT_NOT_FOUND, logs_audit_detail_kb(category, page))
        return
    blocks = ""
    for key, raw in (("before", entry.before_json), ("after", entry.after_json), ("details", entry.details_json)):
        body = _pretty(raw)
        if body:
            blocks += t.AUDIT_DETAIL_BLOCK.format(title=t.AUDIT_DETAIL_BLOCK_TITLES[key], body=body)
    target = f"{entry.target_type}:{entry.target_id}" if entry.target_type else "—"
    text = t.AUDIT_DETAIL.format(
        id=entry.id,
        action=safe(entry.action, limit=80),
        admin=safe(await _admin_label(services, {}, entry.admin_id), limit=40),
        target=safe(target, limit=60),
        source=safe(entry.source, limit=20),
        when=datetime_text(entry.created_at),
        blocks=blocks or t.AUDIT_DETAIL_NO_DATA,
    )
    await render(update, context, text, logs_audit_detail_kb(category, page))


@guarded
@admin_required(Permission.LOGS_VIEW)
async def errors_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """سجل الأخطاء: آخر ما سجّله النظام من أعطال (ترقيم بإجمالي معروف)."""
    await answer_callback(update)
    services = services_of(context)
    total = await services.audit.count_errors()
    page, total_pages, offset = paginate(total, args(update).int_arg(0, 1), LOG_PAGE_SIZE)
    entries = await services.audit.recent_errors(limit=LOG_PAGE_SIZE, offset=offset)

    if not entries:
        await render(update, context, t.ERRORS_EMPTY, logs_page_kb("errors", page=1, total_pages=1))
        return

    lines = "\n\n".join(
        t.ERROR_LINE.format(
            id=entry["id"],
            level=safe(str(entry.get("level", "ERROR")), limit=10),
            source=safe(str(entry.get("source") or "—"), limit=30),
            message=safe(str(entry.get("message") or "—"), limit=160),
            when=datetime_text(str(entry.get("created_at") or "")),
        )
        for entry in entries
    )
    await render(
        update,
        context,
        t.ERRORS_TITLE.format(total=total, page=page, pages=total_pages, lines=lines),
        logs_errors_kb([int(entry["id"]) for entry in entries], page=page, total_pages=total_pages),
    )


@guarded
@admin_required(Permission.LOGS_VIEW)
async def error_detail_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تفاصيل خطأ: الرسالة الكاملة (مقتطعة) ومقتطف الأثر وملخص التحديث — كلها مُنقّاة."""
    await answer_callback(update)
    services = services_of(context)
    call = args(update)
    page = max(1, call.int_arg(1, 1))
    entry = await services.audit.get_error(call.int_arg(0, 0))
    if entry is None:
        await render(update, context, t.ERROR_NOT_FOUND, logs_error_detail_kb(page))
        return
    extra = ""
    if entry.get("update_summary"):
        extra += t.ERROR_DETAIL_UPDATE.format(summary=safe(sanitize(entry["update_summary"]), limit=DETAIL_BLOCK_LIMIT))
    if entry.get("traceback_snippet"):
        extra += t.ERROR_DETAIL_TRACE.format(trace=safe(sanitize(entry["traceback_snippet"]), limit=1200))
    user_label = "—"
    if entry.get("user_id"):
        user = await services.users.get(int(entry["user_id"]))
        user_label = safe(user.display_name if user else str(entry["user_id"]), limit=40)
    text = t.ERROR_DETAIL.format(
        id=entry["id"],
        level=safe(str(entry.get("level") or "ERROR"), limit=10),
        source=safe(str(entry.get("source") or "—"), limit=40),
        error_type=safe(str(entry.get("error_type") or "—"), limit=60),
        when=datetime_text(str(entry.get("created_at") or "")),
        user=user_label,
        notified="نعم" if entry.get("notified_admin") else "لا",
        message=safe(sanitize(str(entry.get("message") or "—")), limit=800),
        extra=extra,
    )
    await render(update, context, text, logs_error_detail_kb(page))


async def _calls_list(update: Update, context: ContextTypes.DEFAULT_TYPE, *, failed_only: bool) -> None:
    """عرض قائمة استدعاءات المزودين (الكل أو الفاشلة) — منطق مشترك للزرين."""
    services = services_of(context)
    mode_label = t.PROVIDER_CALLS_MODE["failed" if failed_only else "all"]
    total = await services.audit.count_provider_calls(only_failed=failed_only)
    page, total_pages, offset = paginate(total, args(update).int_arg(0, 1), LOG_PAGE_SIZE)
    rows = await services.audit.provider_calls(only_failed=failed_only, limit=LOG_PAGE_SIZE, offset=offset)
    if not rows:
        await render(
            update,
            context,
            t.PROVIDER_CALLS_EMPTY.format(mode=mode_label),
            logs_calls_kb([], failed_only=failed_only, page=1, total_pages=1),
        )
        return
    lines = "\n\n".join(
        t.PROVIDER_CALL_LINE.format(
            id=row["id"],
            icon="✅" if row["is_success"] else "❌",
            provider=safe(str(row.get("provider_name") or f"#{row['provider_id']}"), limit=30),
            action=safe(str(row["action"]), limit=12),
            meta=_call_meta(row),
            when=datetime_text(str(row.get("created_at") or "")),
        )
        for row in rows
    )
    await render(
        update,
        context,
        t.PROVIDER_CALLS_TITLE.format(mode=mode_label, total=total, page=page, pages=total_pages, lines=lines),
        logs_calls_kb([int(row["id"]) for row in rows], failed_only=failed_only, page=page, total_pages=total_pages),
    )


def _call_meta(row: dict) -> str:
    """سطر وصفي مختصر: HTTP · المدة · الطلب · نوع الخطأ (للحقول الموجودة فقط)."""
    parts: list[str] = []
    if row.get("http_status") is not None:
        parts.append(f"HTTP {row['http_status']}")
    if row.get("duration_ms") is not None:
        parts.append(f"{row['duration_ms']}ms")
    if row.get("order_id"):
        parts.append(f"طلب #{row['order_id']}")
    if row.get("error_type"):
        parts.append(safe(str(row["error_type"]), limit=30))
    return " · ".join(parts) or "—"


@guarded
@admin_required(Permission.LOGS_VIEW)
async def calls_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """سجل استدعاءات المزودين (الكل)."""
    await answer_callback(update)
    await _calls_list(update, context, failed_only=False)


@guarded
@admin_required(Permission.LOGS_VIEW)
async def calls_failed_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """سجل استدعاءات المزودين الفاشلة فقط."""
    await answer_callback(update)
    await _calls_list(update, context, failed_only=True)


@guarded
@admin_required(Permission.LOGS_VIEW)
async def call_detail_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تفاصيل استدعاء مزود: ملخص الطلب ومقتطف الرد (منقّيان من الأسرار عند التخزين والعرض)."""
    await answer_callback(update)
    services = services_of(context)
    call = args(update)
    mode = "f" if call.arg(1) == "f" else "a"
    page = max(1, call.int_arg(2, 1))
    row = await services.audit.get_provider_call(call.int_arg(0, 0))
    if row is None:
        await render(update, context, t.PROVIDER_CALL_NOT_FOUND, logs_call_detail_kb(mode, page))
        return
    extra = ""
    if row.get("request_summary"):
        extra += t.PROVIDER_CALL_REQUEST.format(body=safe(sanitize(row["request_summary"]), limit=DETAIL_BLOCK_LIMIT))
    if row.get("response_snippet"):
        extra += t.PROVIDER_CALL_RESPONSE.format(body=safe(sanitize(row["response_snippet"]), limit=DETAIL_BLOCK_LIMIT))
    text = t.PROVIDER_CALL_DETAIL.format(
        id=row["id"],
        provider=safe(str(row.get("provider_name") or f"#{row['provider_id']}"), limit=40),
        action=safe(str(row["action"]), limit=12),
        result="✅ نجح" if row["is_success"] else "❌ فشل",
        http=row["http_status"] if row.get("http_status") is not None else "—",
        duration=f"{row['duration_ms']}ms" if row.get("duration_ms") is not None else "—",
        order=f"#{row['order_id']}" if row.get("order_id") else "—",
        error_type=safe(str(row.get("error_type") or "—"), limit=60),
        when=datetime_text(str(row.get("created_at") or "")),
        extra=extra,
    )
    await render(update, context, text, logs_call_detail_kb(mode, page))


def conversations() -> list:
    """لا محادثات في قسم السجلات (عرض فقط)."""
    return []


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم السجلات."""
    table = (
        ("home", logs_home_screen),
        ("audit", audit_screen),
        ("acat", audit_screen),
        ("afl", audit_filter_screen),
        ("aud", audit_detail_screen),
        ("errors", errors_screen),
        ("err", error_detail_screen),
        ("prq", calls_screen),
        ("prqf", calls_failed_screen),
        ("prqd", call_detail_screen),
    )
    return [CallbackQueryHandler(handler, pattern=pattern(NS_ADM_LOG, action)) for action, handler in table]
```

## الربط والتسجيل

### `services/__init__.py` — مُحدَّث

```python
"""
حزمة الخدمات — طبقة منطق العمل بين الواجهة (المرحلة 3+) وقاعدة البيانات.

لماذا حاوية خدمات؟
    الخدمات مترابطة (الطلبات تحتاج المحفظة والمزودين والإشعارات...). بدل أن تبني كل
    نقطة دخول اعتمادياتها بنفسها — فتتسرب الأخطاء وتتكرر الكائنات — تُبنى هنا مرة
    واحدة بترتيب صحيح، ويُمرَّر كائن `ServiceContainer` واحد إلى بقية النظام.

ترتيب البناء (من الأدنى اعتماداً إلى الأعلى):
    settings → audit → notifications → auth → wallet → users → catalog
    → providers → orders → payments → tickets → stats → templates → broadcasts → security → backups
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from database.database import Database
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.backup_service import BackupService
from services.broadcast_service import BroadcastService
from services.catalog_service import CatalogService
from services.notification_service import NotificationService
from services.order_service import OrderService
from services.payment_service import PaymentService
from services.provider_service import ProviderService
from services.security_service import SecurityService
from services.settings_service import SettingsService
from services.stats_service import StatsService
from services.template_service import TemplateService
from services.ticket_service import TicketService
from services.user_service import UserService
from services.wallet_service import WalletService
from utils.logging_setup import get_logger
from utils.security import SecretBox

logger = get_logger(__name__)

__all__ = [
    "AuditService",
    "AuthService",
    "BackupService",
    "BroadcastService",
    "CatalogService",
    "NotificationService",
    "OrderService",
    "PaymentService",
    "ProviderService",
    "ServiceContainer",
    "SecurityService",
    "SettingsService",
    "StatsService",
    "TemplateService",
    "TicketService",
    "UserService",
    "WalletService",
    "build_services",
]


@dataclass(slots=True)
class ServiceContainer:
    """
    حاوية تضم نسخة واحدة من كل خدمة، جاهزة للتمرير إلى معالجات تيليجرام والمهام.

    الاستخدام:
        services = build_services(db, repos, secret_box=box, super_admin_ids=(123,))
        user, is_new = await services.users.get_or_create(...)
        order = await services.orders.create_order(user, service_id=1, link="...", quantity=100)
    """

    db: Database
    repos: Repositories
    settings: SettingsService
    audit: AuditService
    notifications: NotificationService
    auth: AuthService
    wallet: WalletService
    users: UserService
    catalog: CatalogService
    providers: ProviderService
    orders: OrderService
    payments: PaymentService
    tickets: TicketService
    stats: StatsService
    templates: TemplateService
    broadcasts: BroadcastService
    security: SecurityService
    backups: BackupService

    def invalidate_caches(self) -> None:
        """
        إبطال الذاكرة المؤقتة للإعدادات بعد أي تعديل خارجي عليها.

        ملاحظة: عملاء المزودين تُفتح وتُغلق داخل كل عملية (`client.close()` في finally)،
        فلا توجد جلسات شبكة معلّقة تحتاج إغلاقاً عند إيقاف البوت.
        """
        self.settings.invalidate()

    async def startup_recovery(self) -> dict[str, int]:
        """
        إجراءات الاسترداد التي تُنفَّذ مرة واحدة عند إقلاع البوت.

        تشمل: تحرير الأقفال المنتهية ونقل الطلبات العالقة في الإرسال إلى «غير مؤكد».

        المخرجات: عدّادات ما تم استرداده.
        """
        report = await self.orders.recover_after_restart()
        # المرحلة 8: تحميل قوالب الإشعارات المخصّصة قبل إرسال أول رسالة،
        # وإلا خرجت أول الإشعارات بالنص الافتراضي رغم تعديل الأدمن له.
        report["templates_loaded"] = await self.templates.refresh_cache()
        logger.info("استرداد الإقلاع: %s", report)
        return report


def build_services(
    db: Database,
    repos: Repositories | None = None,
    *,
    secret_box: SecretBox,
    super_admin_ids: tuple[int, ...] = (),
    settings_ttl_seconds: float | None = None,
    backup_dir: Path | None = None,
    backup_channel_id: int | None = None,
    app_version: str = "",
) -> ServiceContainer:
    """
    بناء كل الخدمات وربط اعتمادياتها بالترتيب الصحيح.

    المدخلات:
        db                   : اتصال قاعدة البيانات (مفتوح مسبقاً).
        repos                : المستودعات (تُبنى تلقائياً إن لم تُمرَّر).
        secret_box           : صندوق التشفير لمفاتيح المزودين (إجباري — لا مفاتيح واضحة).
        super_admin_ids      : معرفات الأدمن الأعلى من ملف البيئة (مسار طوارئ فقط).
        settings_ttl_seconds : مدة صلاحية كاش الإعدادات (يُستخدم 0 في الاختبارات لإلغاء الكاش).
        backup_dir           : مجلد النسخ الاحتياطية (الافتراضي: `backups` بجوار ملف القاعدة).
        backup_channel_id    : قناة النسخ الخارجية (None ⇒ غير مضبوطة).
        app_version          : إصدار التطبيق (يُدوَّن في الملف الجانبي لكل نسخة).

    المخرجات: حاوية الخدمات الجاهزة للاستخدام.
    """
    repositories = repos if repos is not None else Repositories(db)

    settings = (
        SettingsService(db, repositories, ttl_seconds=settings_ttl_seconds)
        if settings_ttl_seconds is not None
        else SettingsService(db, repositories)
    )
    audit = AuditService(db, repositories)
    notifications = NotificationService(db, repositories, settings)
    auth = AuthService(db, repositories, settings, audit, super_admin_ids=super_admin_ids)
    wallet = WalletService(db, repositories, settings=settings, auth=auth)
    users = UserService(db, repositories, settings, audit, auth, notifications)
    catalog = CatalogService(db, repositories, settings, audit, auth)
    providers = ProviderService(
        db, repositories, settings, audit, auth, notifications, secret_box
    )
    orders = OrderService(
        db, repositories, settings, wallet, catalog, providers, notifications, audit, auth
    )
    payments = PaymentService(db, repositories, settings, wallet, notifications, audit, auth)
    tickets = TicketService(db, repositories, settings, notifications, audit, auth)
    stats = StatsService(db, repositories, settings, auth, providers, audit)
    template_service = TemplateService(db, repositories, auth, audit)
    broadcasts = BroadcastService(db, repositories, auth, audit, notifications, settings)

    backups = BackupService(
        db, repositories, settings, audit, auth, notifications,
        backup_dir=backup_dir if backup_dir is not None else db.path.parent / "backups",
        channel_id=backup_channel_id,
        app_version=app_version,
    )
    security = SecurityService(db, repositories, settings, auth, audit, backups)

    logger.info("تم بناء طبقة الخدمات (%s خدمة)", 16)
    return ServiceContainer(
        db=db,
        repos=repositories,
        settings=settings,
        audit=audit,
        notifications=notifications,
        auth=auth,
        wallet=wallet,
        users=users,
        catalog=catalog,
        providers=providers,
        orders=orders,
        payments=payments,
        tickets=tickets,
        stats=stats,
        templates=template_service,
        broadcasts=broadcasts,
        security=security,
        backups=backups,
    )
```

### `handlers/admin/__init__.py` — مُحدَّث

```python
"""
حزمة لوحة التحكم: تجميع معالجات كل الأقسام في مكانين فقط.

تصدّر هذه الحزمة دالتين يستهلكهما `handlers/registry.py`:

    admin_conversations()   : كل محادثات الأدمن (تُسجَّل قبل أزرار الشاشات).
    admin_screen_handlers() : كل أزرار شاشات الأدمن.

كل وحدة قسم (`users`, `payments`, ...) تصدّر `conversations()` و`screens()`
فيبقى ترتيب التسجيل في مكان واحد ويظل من السهل التأكد أن كل زر له معالج.
"""

from __future__ import annotations

from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler

from handlers.admin import (
    backup,
    broadcast,
    catalog,
    dashboard,
    logs,
    orders,
    payment_methods,
    payments,
    providers,
    security,
    settings,
    stats,
    system,
    templates,
    tickets,
    users,
)
from keyboards.callback_data import NS_ADMIN, pattern

#: وحدات الأقسام بالترتيب الذي تُسجَّل به معالجاتها
SECTIONS = (
    users,
    payments,
    payment_methods,
    orders,
    tickets,
    catalog,
    providers,
    settings,
    logs,
    broadcast,
    templates,
    security,
    backup,
    stats,
    system,
)

__all__ = [
    "admin_conversations",
    "admin_screen_handlers",
    "admin_command_handlers",
    "SECTIONS",
]


def admin_conversations() -> list[ConversationHandler]:
    """كل محادثات لوحة التحكم مجموعة من كل الأقسام."""
    collected: list[ConversationHandler] = []
    for section in SECTIONS:
        collected.extend(section.conversations())
    return collected


def admin_screen_handlers() -> list[CallbackQueryHandler]:
    """كل أزرار شاشات لوحة التحكم (خارج المحادثات)."""
    collected: list[CallbackQueryHandler] = [
        CallbackQueryHandler(dashboard.panel_screen, pattern=pattern(NS_ADMIN, "home")),
        CallbackQueryHandler(dashboard.health_screen, pattern=pattern(NS_ADMIN, "health")),
    ]
    for section in SECTIONS:
        collected.extend(section.screens())
    return collected


def admin_command_handlers() -> list[CommandHandler]:
    """أوامر لوحة التحكم (/admin فقط حالياً)."""
    return [CommandHandler("admin", dashboard.admin_command)]
```

### `handlers/registry.py` — مُحدَّث

```python
"""
تسجيل كل معالجات البوت في مكان واحد.

لماذا ملف تسجيل مستقل؟
    • ترتيب المعالجات مهم جداً في python-telegram-bot: المحادثات قبل الأوامر
      العامة، والمسارات الاحتياطية في النهاية. تجميعها هنا يجعل الترتيب مرئياً
      ومراجعته سهلة بدل تناثره في `main.py`.
    • يتيح اختباراً آلياً يتحقق أن **كل زر في الواجهة له معالج فعلي**
      (`tests/integration/test_no_dead_buttons.py`) — تطبيقاً لقاعدة
      «ممنوع أزرار بلا وظيفة».

ترتيب المجموعات:
    المجموعة -10 : الطبقة الوسيطة (مستخدم/حظر/صيانة/حد استخدام) — تسبق كل شيء.
    المجموعة  0  : المحادثات ثم الأوامر ثم أزرار الشاشات ثم المسارات الاحتياطية.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import (
    Application,
    BaseHandler,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from handlers.common.conversation import conversation
from handlers.admin import (
    admin_command_handlers,
    admin_conversations,
    admin_screen_handlers,
)
from handlers.common import errors, fallbacks, navigation
from handlers.user import account, catalog, deposit, order_flow, orders, support, wallet
from keyboards.callback_data import (
    NS_ACCOUNT,
    NS_CATALOG,
    NS_DEPOSIT,
    NS_NAV,
    NS_NEW,
    NS_ORDERS,
    NS_SUPPORT,
    NS_WALLET,
    pattern,
)
from middlewares.context import UserContextMiddleware
from middlewares.rate_limit import AbuseGuard, RateLimiter

#: مجموعة الطبقة الوسيطة (قبل كل المعالجات)
MIDDLEWARE_GROUP = -10

#: المجموعة الرئيسية لكل معالجات الواجهة
MAIN_GROUP = 0


def _order_conversation() -> ConversationHandler:
    """محادثة إنشاء طلب: رابط ← كمية ← تأكيد."""
    cancel_handlers = [
        CallbackQueryHandler(order_flow.cancel_order_flow, pattern=pattern("flow", "cancel")),
        CommandHandler("cancel", order_flow.cancel_order_flow),
        CommandHandler("start", fallbacks.exit_conversation(order_flow.FLOW_KEY)),
    ]
    return conversation(
        entry_points=[CallbackQueryHandler(order_flow.start_order, pattern=pattern(NS_NEW, "start"))],
        states={
            order_flow.ASK_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, order_flow.receive_link)
            ],
            order_flow.ASK_QUANTITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, order_flow.receive_quantity)
            ],
            order_flow.CONFIRM: [
                CallbackQueryHandler(order_flow.confirm_order, pattern=pattern("flow", "confirm"))
            ],
        },
        fallbacks=cancel_handlers,
        name="order_flow",
        per_chat=True,
        per_user=True,
    )


def _deposit_conversation() -> ConversationHandler:
    """محادثة شحن الرصيد: طريقة ← مبلغ ← مرجع ← إيصال ← تأكيد."""
    cancel_handlers = [
        CallbackQueryHandler(deposit.cancel_deposit_flow, pattern=pattern("flow", "cancel")),
        CommandHandler("cancel", deposit.cancel_deposit_flow),
        CommandHandler("start", fallbacks.exit_conversation(deposit.FLOW_KEY)),
    ]
    return conversation(
        entry_points=[CallbackQueryHandler(deposit.start_deposit, pattern=pattern(NS_DEPOSIT, "start"))],
        states={
            deposit.CHOOSE_METHOD: [
                CallbackQueryHandler(deposit.choose_method, pattern=pattern(NS_DEPOSIT, "method"))
            ],
            deposit.ASK_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, deposit.receive_amount)
            ],
            deposit.ASK_REFERENCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, deposit.receive_reference)
            ],
            deposit.ASK_PROOF: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, deposit.receive_proof),
                CallbackQueryHandler(deposit.skip_proof, pattern=pattern("flow", "skip")),
                MessageHandler(filters.TEXT & ~filters.COMMAND, deposit.receive_proof),
            ],
            deposit.CONFIRM: [
                CallbackQueryHandler(deposit.confirm_deposit, pattern=pattern("flow", "confirm"))
            ],
        },
        fallbacks=cancel_handlers,
        name="deposit_flow",
        per_chat=True,
        per_user=True,
    )


def _new_ticket_conversation() -> ConversationHandler:
    """محادثة فتح تذكرة: تصنيف ← عنوان ← شرح (أو مباشرة من بطاقة الطلب)."""
    cancel_handlers = [
        CallbackQueryHandler(support.cancel_support_flow, pattern=pattern("flow", "cancel")),
        CommandHandler("cancel", support.cancel_support_flow),
        CommandHandler("start", fallbacks.exit_conversation(support.NEW_FLOW_KEY)),
    ]
    return conversation(
        entry_points=[
            CallbackQueryHandler(support.start_new_ticket, pattern=pattern(NS_SUPPORT, "new")),
            CallbackQueryHandler(
                support.start_ticket_for_order, pattern=pattern(NS_SUPPORT, "neworder")
            ),
        ],
        states={
            support.ASK_CATEGORY: [
                CallbackQueryHandler(support.choose_ticket_category, pattern=pattern(NS_SUPPORT, "cat"))
            ],
            support.ASK_SUBJECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, support.receive_subject)
            ],
            support.ASK_MESSAGE: [
                MessageHandler(
                    (filters.TEXT | filters.PHOTO) & ~filters.COMMAND, support.receive_ticket_message
                )
            ],
        },
        fallbacks=cancel_handlers,
        name="new_ticket_flow",
        per_chat=True,
        per_user=True,
    )


def _ticket_reply_conversation() -> ConversationHandler:
    """محادثة إضافة رد على تذكرة قائمة."""
    cancel_handlers = [
        CallbackQueryHandler(support.cancel_support_flow, pattern=pattern("flow", "cancel")),
        CommandHandler("cancel", support.cancel_support_flow),
        CommandHandler("start", fallbacks.exit_conversation(support.REPLY_FLOW_KEY)),
    ]
    return conversation(
        entry_points=[
            CallbackQueryHandler(support.start_reply, pattern=pattern(NS_SUPPORT, "reply"))
        ],
        states={
            support.ASK_REPLY: [
                MessageHandler(
                    (filters.TEXT | filters.PHOTO) & ~filters.COMMAND, support.receive_reply
                )
            ],
        },
        fallbacks=cancel_handlers,
        name="ticket_reply_flow",
        per_chat=True,
        per_user=True,
    )


def screen_handlers() -> list[CallbackQueryHandler]:
    """
    معالجات أزرار الشاشات (خارج المحادثات).

    القائمة مرتبة حسب الشاشة، وكل سطر هنا يقابل زراً فعلياً في `keyboards/`.
    """
    return [
        # التنقل العام
        CallbackQueryHandler(navigation.home_callback, pattern=pattern(NS_NAV, "home")),
        CallbackQueryHandler(navigation.page_indicator_callback, pattern=pattern(NS_NAV, "page")),
        # الخدمات
        CallbackQueryHandler(catalog.categories_screen, pattern=pattern(NS_CATALOG, "list")),
        CallbackQueryHandler(catalog.services_screen, pattern=pattern(NS_CATALOG, "open")),
        CallbackQueryHandler(catalog.service_card_screen, pattern=pattern(NS_CATALOG, "svc")),
        # الطلبات
        CallbackQueryHandler(orders.orders_list_screen, pattern=pattern(NS_ORDERS, "list")),
        CallbackQueryHandler(orders.order_card_screen, pattern=pattern(NS_ORDERS, "view")),
        CallbackQueryHandler(orders.order_cancel_confirm, pattern=pattern(NS_ORDERS, "cancel")),
        CallbackQueryHandler(orders.order_cancel_execute, pattern=pattern(NS_ORDERS, "cancelyes")),
        # المحفظة والشحن
        CallbackQueryHandler(wallet.wallet_screen, pattern=pattern(NS_WALLET, "home")),
        CallbackQueryHandler(wallet.history_screen, pattern=pattern(NS_WALLET, "history")),
        CallbackQueryHandler(deposit.deposits_list_screen, pattern=pattern(NS_DEPOSIT, "list")),
        CallbackQueryHandler(deposit.cancel_payment, pattern=pattern(NS_DEPOSIT, "cancel")),
        # الدعم
        CallbackQueryHandler(support.support_home, pattern=pattern(NS_SUPPORT, "home")),
        CallbackQueryHandler(support.tickets_list_screen, pattern=pattern(NS_SUPPORT, "list")),
        CallbackQueryHandler(support.ticket_card_screen, pattern=pattern(NS_SUPPORT, "view")),
        CallbackQueryHandler(support.close_ticket, pattern=pattern(NS_SUPPORT, "close")),
        # الحساب والمعلومات
        CallbackQueryHandler(account.account_screen, pattern=pattern(NS_ACCOUNT, "home")),
        CallbackQueryHandler(account.notifications_screen, pattern=pattern(NS_ACCOUNT, "notif")),
        CallbackQueryHandler(account.mark_all_read, pattern=pattern(NS_ACCOUNT, "readall")),
        CallbackQueryHandler(account.info_screen, pattern=pattern(NS_ACCOUNT, "info")),
        # لوحة التحكم (كل معالج يفحص صلاحيته بنفسه عبر admin_required)
        *admin_screen_handlers(),
    ]


def conversation_handlers() -> list[ConversationHandler]:
    """
    كل المحادثات بالترتيب الذي تُسجَّل به: محادثات العميل ثم محادثات لوحة الأدمن.

    محادثات الأدمن تأتي بعد محادثات العميل ولكن **قبل** أزرار الشاشات، لأن
    نقاط دخولها أزرار يجب أن تلتقطها المحادثة لا معالج الشاشة.
    """
    return [
        _order_conversation(),
        _deposit_conversation(),
        _new_ticket_conversation(),
        _ticket_reply_conversation(),
        *admin_conversations(),
    ]


def build_handlers(
    limiter: RateLimiter | None = None, guard: AbuseGuard | None = None
) -> list[tuple[int, BaseHandler]]:
    """
    بناء قائمة (المجموعة، المعالج) بالترتيب الصحيح.

    الترتيب داخل المجموعة 0:
        المحادثات ← الأوامر العامة ← أزرار الشاشات ← المسارات الاحتياطية.
    السبب: المحادثة النشطة يجب أن تلتقط /start و/cancel قبل المعالج العام،
    والمسار الاحتياطي يجب أن يكون الأخير حتى لا يبتلع أزراراً صحيحة.
    """
    handlers: list[tuple[int, BaseHandler]] = [
        (MIDDLEWARE_GROUP, TypeHandler(Update, UserContextMiddleware(limiter, guard)))
    ]

    for conversation in conversation_handlers():
        handlers.append((MAIN_GROUP, conversation))

    handlers.extend(
        [
            (MAIN_GROUP, CommandHandler("start", navigation.start_command)),
            (MAIN_GROUP, CommandHandler("help", navigation.help_command)),
            (MAIN_GROUP, CommandHandler("id", navigation.id_command)),
            (MAIN_GROUP, CommandHandler("cancel", fallbacks.cancel_command)),
        ]
    )

    for command in admin_command_handlers():
        handlers.append((MAIN_GROUP, command))

    for handler in screen_handlers():
        handlers.append((MAIN_GROUP, handler))

    handlers.extend(
        [
            (MAIN_GROUP, CallbackQueryHandler(fallbacks.unknown_callback)),
            (MAIN_GROUP, MessageHandler(filters.COMMAND, fallbacks.unknown_command)),
            (MAIN_GROUP, MessageHandler(filters.TEXT | filters.ATTACHMENT, fallbacks.free_text)),
        ]
    )
    return handlers


def register_handlers(
    application: Application,
    limiter: RateLimiter | None = None,
    guard: AbuseGuard | None = None,
) -> int:
    """
    تسجيل كل المعالجات على التطبيق وإرجاع عددها.

    يُنشئ عدّاد الحد وحارس الإساءة هنا (إن لم يُمرَّرا) ويحفظهما في `bot_data`
    ليراهما شاشة «🛡️ الأمان» (قائمة الموقوفين مؤقتاً وزر رفع الإيقاف).

    المخرجات: عدد المعالجات المسجَّلة (يُطبع في سجل الإقلاع للتأكيد).
    """
    limiter = limiter or RateLimiter()
    guard = guard or AbuseGuard()
    application.bot_data["rate_limiter"] = limiter
    application.bot_data["abuse_guard"] = guard

    registered = build_handlers(limiter, guard)
    for group, handler in registered:
        application.add_handler(handler, group=group)
    application.add_error_handler(errors.error_handler)
    return len(registered)
```

### `middlewares/rate_limit.py` — مُحدَّث

```python
"""
حد معدل الاستخدام (Rate limit) وحارس الإساءة — حماية البوت وقاعدة البيانات.

الطبقات (المرحلة 9):
    1. `RateLimiter`: نافذة منزلقة في الذاكرة لكل (مستخدم، سلة). السلة `general`
       للتصفح، و`sensitive` للإجراءات المالية الحسّاسة (تأكيد، رفع إثبات…)
       بحدّ أضيق، حتى لا يستطيع مستخدم يضغط التأكيد عشرات المرات.
    2. `AbuseGuard`: عدّاد مخالفات. من يتجاوز الحد مراراً خلال نافذة المخالفات
       يُوقَف مؤقتاً، ويُتجاهل خلال الإيقاف **بصمت** (لا ردود ولا استعلامات
       قاعدة بيانات) — فالرد على المُغرِق يضاعف الضغط بدل أن يخففه.

لماذا في الذاكرة؟
    الحد وسيلة حماية من الضغط السريع لا سجل محاسبي؛ كتابته في قاعدة البيانات
    تعني كتابة عند كل ضغطة زر — وهو ما يُراد تجنّبه أصلاً. يُعاد ضبطه عند
    إعادة التشغيل وهذا مقبول ومقصود. أما **بدء الإيقاف** فيُكتب في سجل
    التدقيق (حدث `security.rate_limit_block`) لأنه قرار أمني يستحق الأثر.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass

from keyboards.callback_data import NS_ADM_BKP, NS_ADM_STATS

#: طول النافذة الزمنية بالثواني
WINDOW_SECONDS: float = 60.0

#: أقصى عدد مفاتيح نحتفظ بسجلها قبل التنظيف الدوري
MAX_TRACKED_USERS: int = 10_000

#: السلة العامة والسلة الحسّاسة
BUCKET_GENERAL = "general"
BUCKET_SENSITIVE = "sensitive"

#: نافذة احتساب المخالفات (ثانية): المخالفات الأقدم لا تُحتسب
STRIKE_WINDOW_SECONDS: float = 600.0

#: أقل فاصل بين تحذيرين متتاليين لنفس المستخدم (ثانية) — لا نغرقه بالتحذيرات
WARNING_COOLDOWN_SECONDS: float = 10.0

#: الإجراءات الحسّاسة داخل أزرار المحادثات (تأكيدات تنفّذ عملاً مالياً أو إنشائياً)
SENSITIVE_FLOW_ACTIONS: frozenset[str] = frozenset({"confirm"})

#: أزرار لوحة الأدمن الحسّاسة خارج المحادثات: (المساحة ← الإجراءات) — ثقيلة أو تخرج بيانات (م10)
SENSITIVE_ADMIN_ACTIONS: dict[str, frozenset[str]] = {
    NS_ADM_BKP: frozenset({"new", "chan", "dl", "vac"}),
    NS_ADM_STATS: frozenset({"exp"}),
}


class RateLimiter:
    """عدّاد إجراءات لكل (مستخدم، سلة) ضمن نافذة زمنية منزلقة."""

    def __init__(
        self, *, window_seconds: float = WINDOW_SECONDS, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """تهيئة العدّاد بنافذة زمنية محددة ومصدر وقت قابل للحقن في الاختبارات."""
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[tuple[int, str], deque[float]] = defaultdict(deque)

    def hit(self, user_id: int, limit: int, *, bucket: str = BUCKET_GENERAL) -> bool:
        """
        تسجيل إجراء جديد وفحص تجاوز الحد.

        المدخلات:
            user_id : معرف تيليجرام للمستخدم.
            limit   : الحد المسموح خلال النافذة (صفر أو أقل = بلا حد).
            bucket  : سلة العدّ (`general` أو `sensitive`).

        المخرجات: True إذا كان الإجراء مسموحاً، False إذا تجاوز الحد.
        """
        if limit <= 0:
            return True

        now = self._clock()
        bucket_hits = self._hits[(user_id, bucket)]
        threshold = now - self._window
        while bucket_hits and bucket_hits[0] < threshold:        # إسقاط ما خرج من النافذة
            bucket_hits.popleft()

        if len(bucket_hits) >= limit:
            return False

        bucket_hits.append(now)
        if len(self._hits) > MAX_TRACKED_USERS:                  # تنظيف وقائي للذاكرة
            self._cleanup(threshold)
        return True

    def remaining(self, user_id: int, limit: int, *, bucket: str = BUCKET_GENERAL) -> int:
        """عدد الإجراءات المتبقية للمستخدم في النافذة الحالية."""
        if limit <= 0:
            return limit
        bucket_hits = self._hits.get((user_id, bucket))
        if not bucket_hits:
            return limit
        threshold = self._clock() - self._window
        active = sum(1 for moment in bucket_hits if moment >= threshold)
        return max(0, limit - active)

    def reset(self, user_id: int) -> None:
        """تصفير سجل مستخدم في كل السلال (الاختبارات، رفع الإيقاف)."""
        for key in [key for key in self._hits if key[0] == user_id]:
            self._hits.pop(key, None)

    def _cleanup(self, threshold: float) -> None:
        """إزالة المفاتيح التي لم تُسجَّل لها أي حركة داخل النافذة."""
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] < threshold]
        for key in stale:
            self._hits.pop(key, None)


@dataclass(frozen=True, slots=True)
class BlockInfo:
    """مستخدم موقوف مؤقتاً: معرفه والثواني المتبقية وعدد مخالفاته."""

    telegram_id: int
    seconds_left: int
    strikes: int


@dataclass(frozen=True, slots=True)
class ViolationResult:
    """نتيجة تسجيل مخالفة: هل بدأ الإيقاف؟ وهل نرسل تحذيراً الآن؟"""

    strikes: int
    blocked: bool
    warn: bool


class AbuseGuard:
    """
    عدّاد المخالفات والإيقاف المؤقت للمفرطين.

    كل تجاوز للحد = «مخالفة». عند بلوغ `strikes_limit` مخالفة داخل نافذة
    `STRIKE_WINDOW_SECONDS` يُوقَف صاحبها `block_seconds`. الحالة في الذاكرة.
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        """تهيئة الحارس بمصدر وقت قابل للحقن."""
        self._clock = clock
        self._strikes: dict[int, deque[float]] = defaultdict(deque)
        self._blocked_until: dict[int, float] = {}
        self._last_warning: dict[int, float] = {}
        self.total_violations: int = 0
        self.total_blocks: int = 0

    def seconds_blocked(self, telegram_id: int) -> float:
        """الثواني المتبقية من إيقاف المستخدم (صفر = غير موقوف). ينظّف الإيقاف المنتهي."""
        until = self._blocked_until.get(telegram_id)
        if until is None:
            return 0.0
        left = until - self._clock()
        if left <= 0:
            self._blocked_until.pop(telegram_id, None)
            self._strikes.pop(telegram_id, None)
            return 0.0
        return left

    def is_blocked(self, telegram_id: int) -> bool:
        """هل المستخدم موقوف مؤقتاً الآن؟"""
        return self.seconds_blocked(telegram_id) > 0

    def record_violation(
        self, telegram_id: int, *, strikes_limit: int, block_seconds: float
    ) -> ViolationResult:
        """
        تسجيل مخالفة جديدة وتقرير الإيقاف.

        المدخلات:
            strikes_limit : عدد المخالفات التي تُوجب الإيقاف.
            block_seconds : مدة الإيقاف.

        المخرجات: عدد المخالفات الحالية + هل بدأ الإيقاف + هل يُرسَل تحذير الآن
        (التحذير مُهدَّأ كل `WARNING_COOLDOWN_SECONDS`، وإشعار الإيقاف يُرسل دائماً).
        """
        now = self._clock()
        self.total_violations += 1
        strikes = self._strikes[telegram_id]
        threshold = now - STRIKE_WINDOW_SECONDS
        while strikes and strikes[0] < threshold:
            strikes.popleft()
        strikes.append(now)

        if len(strikes) >= max(1, strikes_limit):
            self._blocked_until[telegram_id] = now + block_seconds
            self.total_blocks += 1
            return ViolationResult(strikes=len(strikes), blocked=True, warn=True)

        last = self._last_warning.get(telegram_id)
        warn = last is None or now - last >= WARNING_COOLDOWN_SECONDS
        if warn:
            self._last_warning[telegram_id] = now
        return ViolationResult(strikes=len(strikes), blocked=False, warn=warn)

    def clear(self, telegram_id: int) -> bool:
        """رفع الإيقاف وتصفير المخالفات (إجراء إداري). يُرجع True إن كان موقوفاً فعلاً."""
        was_blocked = self.is_blocked(telegram_id)
        self._blocked_until.pop(telegram_id, None)
        self._strikes.pop(telegram_id, None)
        self._last_warning.pop(telegram_id, None)
        return was_blocked

    def blocked_snapshot(self) -> list[BlockInfo]:
        """قائمة الموقوفين حالياً (الأطول إيقافاً أولاً) لشاشة الأمان."""
        result = []
        for telegram_id in list(self._blocked_until):
            left = self.seconds_blocked(telegram_id)
            if left > 0:
                result.append(BlockInfo(telegram_id, int(left) + 1, len(self._strikes.get(telegram_id, ()))))
        return sorted(result, key=lambda info: -info.seconds_left)
```

### `keyboards/callback_data.py` — مُحدَّث

```python
"""
ترميز وفك بيانات الأزرار (callback_data) بشكل مُهيكل وآمن.

لماذا ملف مستقل؟
    تيليجرام يسمح بـ64 بايت فقط لكل `callback_data`، وأي زر قديم في محادثة
    مستخدم قد يُضغط بعد تحديث البوت. لذلك نعتمد صيغة واحدة في كل المشروع:

        namespace:action:arg1:arg2...:vN

    • `namespace` يحدد الشاشة (cat / ord / wal / dep / sup / acc / nav / flow).
    • `action` يحدد الإجراء داخل الشاشة.
    • `vN` لاحقة الإصدار؛ إذا تغيّرت بنية الأزرار مستقبلاً نرفع الرقم،
      فتُرفض الأزرار القديمة برسالة واضحة بدل تنفيذ إجراء خاطئ.

قواعد ملزِمة:
    • ممنوع زر بلا معنى: كل `callback_data` يُبنى من هنا وله معالج مسجَّل
      (يتحقق من ذلك اختبار `test_no_dead_buttons`).
    • ممنوع تمرير نص حر من المستخدم داخل `callback_data` (طوله غير مضمون).
"""

from __future__ import annotations

from dataclasses import dataclass

#: إصدار بنية الأزرار الحالي — يُلحق بكل زر
CALLBACK_VERSION: int = 1

#: الحد الأقصى الذي تسمح به تيليجرام لحجم callback_data (بايت)
MAX_CALLBACK_BYTES: int = 64

#: الفاصل بين أجزاء الزر
SEPARATOR: str = ":"


class CallbackError(ValueError):
    """خطأ في بناء أو قراءة بيانات زر (بنية غير صحيحة أو طول زائد)."""


@dataclass(frozen=True, slots=True)
class Callback:
    """بيانات زر بعد فكّها: المساحة، الإجراء، الوسائط، الإصدار."""

    namespace: str
    action: str
    args: tuple[str, ...]
    version: int

    def arg(self, index: int, default: str = "") -> str:
        """قراءة وسيط نصي بموضعه مع قيمة افتراضية إن لم يوجد."""
        if index < len(self.args):
            return self.args[index]
        return default

    def int_arg(self, index: int, default: int = 0) -> int:
        """قراءة وسيط رقمي بموضعه (يُعيد الافتراضي إن كان غير رقمي)."""
        raw = self.arg(index)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    @property
    def is_current_version(self) -> bool:
        """هل هذا الزر من الإصدار الحالي لبنية الأزرار؟"""
        return self.version == CALLBACK_VERSION


def pack(namespace: str, action: str, *args: object) -> str:
    """
    بناء `callback_data` مُهيكلة والتحقق من صلاحيتها.

    المدخلات:
        namespace : مساحة الشاشة (حروف صغيرة بلا فواصل).
        action    : اسم الإجراء.
        args      : وسائط إضافية (أرقام أو كلمات قصيرة بلا الفاصل `:`).

    المخرجات: نص جاهز لوضعه في زر.

    الاستثناءات:
        CallbackError : وجود الفاصل داخل جزء، أو تجاوز حد 64 بايت.
    """
    parts = [namespace, action, *[str(arg) for arg in args]]
    for part in parts:
        if SEPARATOR in part:
            raise CallbackError(f"جزء زر يحتوي الفاصل الممنوع '{SEPARATOR}': {part!r}")
        if part == "":
            raise CallbackError("جزء زر فارغ غير مسموح")
    data = SEPARATOR.join([*parts, f"v{CALLBACK_VERSION}"])
    if len(data.encode("utf-8")) > MAX_CALLBACK_BYTES:
        raise CallbackError(f"طول callback_data تجاوز {MAX_CALLBACK_BYTES} بايت: {data!r}")
    return data


def unpack(data: str | None) -> Callback:
    """
    فكّ `callback_data` إلى أجزائها.

    المخرجات: كائن `Callback`؛ والإصدار يكون 0 إذا كان الزر قديماً بلا لاحقة إصدار.

    الاستثناءات:
        CallbackError : البيانات فارغة أو لا تحوي مساحة وإجراءً.
    """
    if not data:
        raise CallbackError("callback_data فارغة")
    parts = data.split(SEPARATOR)
    if len(parts) < 2:
        raise CallbackError(f"callback_data غير مُهيكلة: {data!r}")

    version = 0
    if parts[-1].startswith("v") and parts[-1][1:].isdigit():
        version = int(parts[-1][1:])
        parts = parts[:-1]

    namespace, action, *args = parts
    return Callback(namespace=namespace, action=action, args=tuple(args), version=version)


def pattern(namespace: str, action: str | None = None) -> str:
    """
    بناء تعبير نمطي لتسجيل المعالج على مساحة (أو مساحة+إجراء) بعينها.

    مثال: `pattern("cat")` ⇒ `^cat:` و`pattern("cat", "open")` ⇒ `^cat:open(:|$)`.
    """
    if action is None:
        return rf"^{namespace}{SEPARATOR}"
    return rf"^{namespace}{SEPARATOR}{action}({SEPARATOR}|$)"


# ----------------------- مساحات الأزرار المعتمدة ------------------------- #

NS_NAV = "nav"      # التنقل بين الشاشات الرئيسية
NS_CATALOG = "cat"  # التصنيفات والخدمات
NS_NEW = "new"      # بدء طلب جديد
NS_ORDERS = "ord"   # طلباتي
NS_WALLET = "wal"   # المحفظة
NS_DEPOSIT = "dep"  # شحن الرصيد
NS_SUPPORT = "sup"  # الدعم الفني
NS_ACCOUNT = "acc"  # الحساب والإشعارات
NS_FLOW = "flow"    # أزرار داخل المحادثات (تأكيد/إلغاء/تخطي/رجوع)

# ----------------------- مساحات لوحة الأدمن ----------------------------- #
# مختصرة عمداً: حدّ تيليجرام 64 بايت، وبعض الأزرار تحمل معرفات طويلة.

NS_ADMIN = "adm"      # لوحة التحكم والصحة العامة
NS_ADM_USERS = "au"   # إدارة المستخدمين
NS_ADM_PAY = "ap"     # مراجعة طلبات الشحن
NS_ADM_ORD = "ao"     # إدارة الطلبات
NS_ADM_TKT = "at"     # تذاكر الدعم (جانب الأدمن)
NS_ADM_CAT = "ac"     # إدارة الكتالوج (تصنيفات/خدمات)
NS_ADM_SET = "as"     # الإعدادات
NS_ADM_LOG = "al"     # السجلات (تدقيق/أخطاء)
NS_ADM_PRV = "pv"     # المزودون وربط الـAPI (المرحلة 5)
NS_ADM_PMT = "pm"     # طرق الشحن وإدارتها (المرحلة 7)
NS_ADM_BRD = "bc"     # الرسائل الجماعية (المرحلة 8)
NS_ADM_TPL = "tp"     # قوالب الإشعارات (المرحلة 8)
NS_ADM_SEC = "sc"     # شاشة الأمان (المرحلة 9)
NS_ADM_BKP = "bk"     # النسخ الاحتياطي (المرحلة 10)
NS_ADM_STATS = "st"   # الإحصائيات والتصدير (المرحلة 10)

#: كل المساحات المعروفة — تُستخدم في اختبار «لا أزرار بلا وظيفة»
ALL_NAMESPACES: tuple[str, ...] = (
    NS_NAV, NS_CATALOG, NS_NEW, NS_ORDERS, NS_WALLET, NS_DEPOSIT, NS_SUPPORT, NS_ACCOUNT, NS_FLOW,
    NS_ADMIN, NS_ADM_USERS, NS_ADM_PAY, NS_ADM_ORD, NS_ADM_TKT, NS_ADM_CAT, NS_ADM_SET, NS_ADM_LOG,
    NS_ADM_PRV, NS_ADM_PMT, NS_ADM_BRD, NS_ADM_TPL, NS_ADM_SEC, NS_ADM_BKP, NS_ADM_STATS,
)
```

## مقتطفات من ملفات كبيرة (الدوال المتغيرة كاملة)

### `core/exceptions.py` — مُحدَّث (مقتطف)

```python
class BackupError(SMMBotError):
    """فشل في إنشاء نسخة احتياطية أو فحصها أو إرسالها."""

    user_message = "❌ تعذّرت عملية النسخ الاحتياطي. راجع سجل الأخطاء."

class BackupBusyError(BackupError):
    """نسخة أخرى قيد الإنشاء الآن (لا نُنشئ نسختين متزامنتين)."""

    user_message = "⏳ هناك نسخة احتياطية قيد الإنشاء الآن. انتظر انتهاءها."
```

### `database/database.py` — مُحدَّث (مقتطف)

```python
    async def snapshot_to(self, destination: str | Path) -> None:
        """
        نسخة متّسقة من القاعدة الحيّة إلى ملف جديد (`VACUUM INTO`) دون إيقاف البوت.

        لماذا `VACUUM INTO` وليس نسخ الملف؟ ملف WAL قد يحوي معاملات مثبّتة لم تُدمج
        بعد في الملف الرئيسي، فنسخ الملف وحده قد يعطي نسخة ناقصة أو تالفة. هذا الأمر
        يقرأ لقطة واحدة متّسقة عبر اتصال قراءة (لا يحجب الكتابة) ويكتب ملفاً مدمجاً.

        المدخلات: مسار ملف غير موجود (يُرفض الاستبدال حتى لا نكتب فوق نسخة قائمة).
        الاستثناءات: DatabaseError عند وجود الملف أو فشل الأمر.
        """
        target = Path(destination)
        if target.exists():
            raise DatabaseError(f"ملف النسخة موجود مسبقاً: {target.name}")
        async with self._reader() as conn:
            try:
                await conn.execute("VACUUM INTO ?", (str(target),))
            except sqlite3.Error as exc:
                target.unlink(missing_ok=True)
                raise DatabaseError(f"فشل أخذ لقطة من القاعدة: {exc}") from exc
```

### `database/repositories/orders.py` — مُحدَّث (مقتطف)

```python
    async def period_totals(self, start_iso: str, end_iso: str) -> dict[str, int]:
        """
        مجاميع فترة: عدد الطلبات، الإجمالي، المسترجع، الصافي، وعدد المشترين المختلفين.

        المخرجات: orders_count, gross_units, refund_units, net_units, buyers.
        """
        row = await self.db.fetchone(
            """
            SELECT COUNT(*)                                   AS orders_count,
                   COALESCE(SUM(cost_units), 0)               AS gross_units,
                   COALESCE(SUM(refund_amount_units), 0)      AS refund_units,
                   COUNT(DISTINCT user_id)                    AS buyers
              FROM orders
             WHERE created_at >= ? AND created_at < ?
            """,
            (start_iso, end_iso),
        )
        gross = int(row["gross_units"]) if row else 0
        refund = int(row["refund_units"]) if row else 0
        return {
            "orders_count": int(row["orders_count"]) if row else 0,
            "gross_units": gross,
            "refund_units": refund,
            "net_units": gross - refund,
            "buyers": int(row["buyers"]) if row else 0,
        }

    async def sum_net_between(self, start_iso: str, end_iso: str) -> int:
        """الإيراد الصافي لفترة (الإجمالي − المسترجع) بوحدات المال الصحيحة."""
        return (await self.period_totals(start_iso, end_iso))["net_units"]

    async def status_counts_between(self, start_iso: str, end_iso: str) -> dict[str, int]:
        """عدد طلبات الفترة في كل حالة."""
        rows = await self.db.fetchall(
            """
            SELECT status, COUNT(*) AS c FROM orders
             WHERE created_at >= ? AND created_at < ? GROUP BY status
            """,
            (start_iso, end_iso),
        )
        return {row["status"]: int(row["c"]) for row in rows}

    async def profit_inputs(self, start_iso: str, end_iso: str) -> dict[str, int]:
        """
        مدخلات الربح التقديري لفترة — **للطلبات المنتهية فقط** (مكتمل/جزئي).

        لماذا المنتهية فقط؟ إيراد الطلب الجاري غير مُحقَّق وقد يُسترجع، فخلطه بتكلفة مزود
        لم تُحسم يعطي ربحاً وهمياً. ولماذا «المغطّاة» فقط؟ تكلفة المزود تُسجَّل حين يردّ
        المزود بها؛ الطلب بلا تكلفة مسجّلة لا يدخل الحساب ويُعلن نسبة التغطية بدل التخمين.

        التكلفة الفعلية للطلب الجزئي تُقسَّم بنسبة ما بقي مخصوماً: `تكلفة × (cost−refund)/cost`
        (المزود لم يُسلّم الباقي). تُحسب بحساب صحيح في بايثون للصفوف ذات الاسترجاع (قليلة)،
        وفي SQL لغيرها (لا مضروبات ضخمة تتحول إلى أعداد عشرية).

        المخرجات:
            eligible_orders / eligible_net_units : كل الطلبات المنتهية وصافيها.
            covered_orders  / covered_net_units  : المغطّاة بتكلفة مزود وصافيها.
            covered_cost_units                   : تكلفة المزود الفعلية لها.
        """
        eligible = await self.db.fetchone(
            """
            SELECT COUNT(*) AS n, COALESCE(SUM(cost_units - refund_amount_units), 0) AS net
              FROM orders
             WHERE created_at >= ? AND created_at < ? AND status IN ('completed', 'partial')
            """,
            (start_iso, end_iso),
        )
        full = await self.db.fetchone(
            """
            SELECT COUNT(*) AS n,
                   COALESCE(SUM(cost_units), 0) AS net,
                   COALESCE(SUM(provider_cost_units), 0) AS cost
              FROM orders
             WHERE created_at >= ? AND created_at < ? AND status IN ('completed', 'partial')
               AND provider_cost_units IS NOT NULL AND refund_amount_units = 0
            """,
            (start_iso, end_iso),
        )
        prorated = await self.db.fetchall(
            """
            SELECT cost_units, refund_amount_units, provider_cost_units FROM orders
             WHERE created_at >= ? AND created_at < ? AND status IN ('completed', 'partial')
               AND provider_cost_units IS NOT NULL AND refund_amount_units > 0
            """,
            (start_iso, end_iso),
        )
        covered_orders = int(full["n"]) if full else 0
        covered_net = int(full["net"]) if full else 0
        covered_cost = int(full["cost"]) if full else 0
        for row in prorated:
            cost, refund, provider_cost = (int(row[k]) for k in ("cost_units", "refund_amount_units", "provider_cost_units"))
            net = cost - refund
            covered_orders += 1
            covered_net += net
            covered_cost += (provider_cost * net) // cost if cost > 0 else provider_cost
        return {
            "eligible_orders": int(eligible["n"]) if eligible else 0,
            "eligible_net_units": int(eligible["net"]) if eligible else 0,
            "covered_orders": covered_orders,
            "covered_net_units": covered_net,
            "covered_cost_units": covered_cost,
        }

    async def top_services(
        self, *, start_iso: str, end_iso: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """
        أكثر الخدمات طلباً خلال فترة (مرتبة بعدد الطلبات ثم بالصافي).

        المخرجات: صفوف فيها service_name و orders_count و total_units (الصافي) و gross_units.
        """
        rows = await self.db.fetchall(
            """
            SELECT service_name_snapshot                         AS service_name,
                   COUNT(*)                                       AS orders_count,
                   COALESCE(SUM(cost_units), 0)                   AS gross_units,
                   COALESCE(SUM(cost_units - refund_amount_units), 0) AS total_units
              FROM orders
             WHERE created_at >= ? AND created_at < ?
             GROUP BY service_id
             ORDER BY orders_count DESC, total_units DESC, service_id
             LIMIT ?
            """,
            (start_iso, end_iso, limit),
        )
        return [dict(row) for row in rows]

    async def top_buyers(self, *, start_iso: str, end_iso: str, limit: int = 5) -> list[dict[str, Any]]:
        """
        أكثر العملاء إنفاقاً **صافياً** خلال فترة (من الطلبات لا من عدّاد المستخدم المتراكم).

        المخرجات: صفوف فيها user_id و orders_count و net_units (الأعلى أولاً، بلا أصفار).
        """
        rows = await self.db.fetchall(
            """
            SELECT user_id,
                   COUNT(*) AS orders_count,
                   COALESCE(SUM(cost_units - refund_amount_units), 0) AS net_units
              FROM orders
             WHERE created_at >= ? AND created_at < ?
             GROUP BY user_id
            HAVING net_units > 0
             ORDER BY net_units DESC, user_id
             LIMIT ?
            """,
            (start_iso, end_iso, limit),
        )
        return [dict(row) for row in rows]

    async def minute_buckets(self, start_iso: str, end_iso: str) -> list[dict[str, Any]]:
        """
        تجميع الطلبات بالدقيقة (UTC) بدل اليوم: يترك للخدمة تجميعها بأيام **محلية**.

        لماذا؟ `substr(created_at,1,10)` يقسّم اليوم عند منتصف الليل UTC لا المحلي، فتظهر
        طلبات ما بعد الثالثة فجراً (توقيت عدن) في اليوم الخطأ. التجميع بالدقيقة صحيح
        لأي إزاحة (حتى نصف الساعة) وعدد الصفوف لا يتجاوز عدد الطلبات.
        """
        rows = await self.db.fetchall(
            """
            SELECT substr(created_at, 1, 16)                    AS minute,
                   COUNT(*)                                      AS orders_count,
                   COALESCE(SUM(cost_units), 0)                  AS gross_units,
                   COALESCE(SUM(refund_amount_units), 0)         AS refund_units
              FROM orders
             WHERE created_at >= ? AND created_at < ?
             GROUP BY minute
             ORDER BY minute
            """,
            (start_iso, end_iso),
        )
        return [dict(row) for row in rows]

    async def export_rows(self, start_iso: str, end_iso: str, *, limit: int) -> list[dict[str, Any]]:
        """
        صفوف طلبات الفترة للتصدير (الأقدم أولاً). لا رابط العميل ولا معرّف تيليجرام عمداً.

        المخرجات: حتى `limit` صفاً (اطلب سقفاً+1 لمعرفة هل قُطعت النتيجة).
        """
        rows = await self.db.fetchall(
            """
            SELECT id, public_code, created_at, user_id, service_name_snapshot AS service_name,
                   quantity, status, cost_units, refund_amount_units, provider_cost_units,
                   delivered_quantity
              FROM orders
             WHERE created_at >= ? AND created_at < ?
             ORDER BY id
             LIMIT ?
            """,
            (start_iso, end_iso, limit),
        )
        return [dict(row) for row in rows]
```

### `database/repositories/users.py` — مُحدَّث (مقتطف)

```python
    async def count_between(self, start_iso: str, end_iso: str) -> int:
        """عدد المستخدمين المسجَّلين بين وقتين (بداية شاملة، نهاية حصرية)."""
        return await self.count("users", "created_at >= ? AND created_at < ?", (start_iso, end_iso))
```

### `database/repositories/audit.py` — مُحدَّث (مقتطف)

```python
    @staticmethod
    def _prefix_clause(prefixes: tuple[str, ...]) -> tuple[str, list[str]]:
        """شرط WHERE لعدة بادئات إجراء (OR بينها)؛ قائمة فارغة = بلا شرط (كل السجلات)."""
        if not prefixes:
            return "", []
        clause = " OR ".join("action LIKE ? ESCAPE '\\'" for _ in prefixes)
        return f" WHERE {clause}", [_like_prefix(prefix) for prefix in prefixes]

    async def list_by_prefixes(
        self, prefixes: tuple[str, ...], *, limit: int = 8, offset: int = 0
    ) -> list[AuditLog]:
        """سجلات تطابق أي بادئة من القائمة، الأحدث أولاً (فلتر الفئات في شاشة السجلات)."""
        where, params = self._prefix_clause(prefixes)
        rows = await self.db.fetchall(
            f"SELECT * FROM audit_logs{where} ORDER BY id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        )
        return AuditLog.from_rows(rows)

    async def count_by_prefixes(self, prefixes: tuple[str, ...]) -> int:
        """عدد السجلات المطابقة لأي بادئة من القائمة."""
        where, params = self._prefix_clause(prefixes)
        return int(await self.db.fetchval(f"SELECT COUNT(*) FROM audit_logs{where}", params, default=0))

    async def get(self, audit_id: int) -> AuditLog | None:
        """سجل تدقيق واحد بمعرّفه (لشاشة التفاصيل)."""
        row = await self.db.fetchone("SELECT * FROM audit_logs WHERE id = ?", (audit_id,))
        return AuditLog.from_row(row) if row else None
```

### `database/repositories/misc.py` — مُحدَّث (مقتطف)

```python
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
```

### `texts/templates.py` — مُحدَّث (مقتطف)

```python
def admin_daily_digest(
    *,
    orders_today: int,
    revenue_today_units: int,
    deposits_today_units: int,
    pending_payments: int,
    attention_orders: int,
    open_tickets: int,
    new_users: int,
    errors_24h: int,
    symbol: str = "",
    refunds_today_units: int = 0,
    completed_today: int = 0,
    failed_today: int = 0,
) -> tuple[str, str]:
    """
    الملخص اليومي للأدمن: أرقام اليوم في رسالة واحدة.

    المبيعات **صافية** (بعد الاسترجاع). لا ربح هنا عمداً: الرسالة تصل كل من يملك `stats.view`.
    """
    return (
        "📊 الملخص اليومي",
        f"📦 طلبات اليوم: {orders_today} (✅ منتهية: {completed_today} · ❌ فاشلة: {failed_today})\n"
        f"💰 صافي مبيعات اليوم: {money(revenue_today_units, symbol)}\n"
        f"↩️ مسترجع من طلبات اليوم: {money(refunds_today_units, symbol)}\n"
        f"💳 إيداعات معتمدة اليوم: {money(deposits_today_units, symbol)}\n"
        f"👥 مستخدمون جدد: {new_users}\n"
        f"⏳ طلبات شحن تنتظر المراجعة: {pending_payments}\n"
        f"⚠️ طلبات تحتاج انتباهك: {attention_orders}\n"
        f"🎫 تذاكر مفتوحة: {open_tickets}\n"
        f"🐞 أخطاء آخر 24 ساعة: {errors_24h}",
    )
```

### `keyboards/admin_kb.py (السجلات)` — مُحدَّث (مقتطف)

```
def logs_home_kb() -> InlineKeyboardMarkup:
    """اختيار نوع السجل."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_LOG_AUDIT, callback_data=pack(NS_ADM_LOG, "audit", 1))],
            [InlineKeyboardButton(t.BTN_LOG_ERRORS, callback_data=pack(NS_ADM_LOG, "errors", 1))],
            [InlineKeyboardButton(t.BTN_LOG_PROVIDER_CALLS, callback_data=pack(NS_ADM_LOG, "prq", 1))],
            _panel_row(),
        ]
    )


def logs_page_kb(action: str, *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """ترقيم صفحات السجلات."""
    rows: list[list[InlineKeyboardButton]] = []
    nav = pagination_row(NS_ADM_LOG, action, page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_LOG, "home"))
    return InlineKeyboardMarkup(rows)


def _id_buttons(ids: list[int], namespace: str, action: str, *tail: object) -> list[list[InlineKeyboardButton]]:
    """أزرار «#المعرّف» لفتح تفاصيل عناصر الصفحة (4 في الصف)."""
    buttons = [
        InlineKeyboardButton(f"#{item_id}", callback_data=pack(namespace, action, item_id, *tail))
        for item_id in ids
    ]
    return [buttons[i : i + 4] for i in range(0, len(buttons), 4)]


def logs_audit_kb(ids: list[int], *, category: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """سجل التدقيق: أزرار تفاصيل + ترقيم ضمن الفئة + زر الفلتر."""
    rows = _id_buttons(ids, NS_ADM_LOG, "aud", category, page)
    nav = pagination_row(NS_ADM_LOG, "acat", page=page, total_pages=total_pages, prefix_args=(category,))
    if nav:
        rows.append(nav)
    label = t.AUDIT_CATEGORY_LABELS.get(category, category)
    rows.append([InlineKeyboardButton(t.BTN_LOG_FILTER.format(label=label), callback_data=pack(NS_ADM_LOG, "afl", category))])
    rows.append(_back_row(NS_ADM_LOG, "home"))
    return InlineKeyboardMarkup(rows)


def logs_audit_filter_kb(current: str) -> InlineKeyboardMarkup:
    """قائمة اختيار فئة سجل التدقيق (الفئة الحالية بعلامة ✔)."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'✔ ' if key == current else ''}{label}", callback_data=pack(NS_ADM_LOG, "acat", key, 1)
            )
        ]
        for key, label in t.AUDIT_CATEGORY_LABELS.items()
    ]
    rows.append(_back_row(NS_ADM_LOG, "acat", current, 1))
    return InlineKeyboardMarkup(rows)


def logs_audit_detail_kb(category: str, page: int) -> InlineKeyboardMarkup:
    """تفاصيل سجل تدقيق: رجوع لنفس الصفحة والفئة."""
    return InlineKeyboardMarkup([_back_row(NS_ADM_LOG, "acat", category, page)])


def logs_errors_kb(ids: list[int], *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """سجل الأخطاء: أزرار تفاصيل + ترقيم."""
    rows = _id_buttons(ids, NS_ADM_LOG, "err", page)
    nav = pagination_row(NS_ADM_LOG, "errors", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_LOG, "home"))
    return InlineKeyboardMarkup(rows)


def logs_error_detail_kb(page: int) -> InlineKeyboardMarkup:
    """تفاصيل خطأ: رجوع لنفس الصفحة."""
    return InlineKeyboardMarkup([_back_row(NS_ADM_LOG, "errors", page)])


def logs_calls_kb(ids: list[int], *, failed_only: bool, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """سجل استدعاءات المزودين: تفاصيل + ترقيم + تبديل «الفاشلة فقط/الكل»."""
    mode = "f" if failed_only else "a"
    list_action = "prqf" if failed_only else "prq"
    rows = _id_buttons(ids, NS_ADM_LOG, "prqd", mode, page)
    nav = pagination_row(NS_ADM_LOG, list_action, page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    toggle = (
        InlineKeyboardButton(t.BTN_LOG_ALL_CALLS, callback_data=pack(NS_ADM_LOG, "prq", 1))
        if failed_only
        else InlineKeyboardButton(t.BTN_LOG_FAILED_ONLY, callback_data=pack(NS_ADM_LOG, "prqf", 1))
    )
    rows.append([toggle])
    rows.append(_back_row(NS_ADM_LOG, "home"))
    return InlineKeyboardMarkup(rows)


def logs_call_detail_kb(mode: str, page: int) -> InlineKeyboardMarkup:
    """تفاصيل استدعاء مزود: رجوع لنفس القائمة والصفحة."""
    return InlineKeyboardMarkup([_back_row(NS_ADM_LOG, "prqf" if mode == "f" else "prq", page)])

def logs_home_kb() -> InlineKeyboardMarkup:
    """اختيار نوع السجل."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_LOG_AUDIT, callback_data=pack(NS_ADM_LOG, "audit", 1))],
            [InlineKeyboardButton(t.BTN_LOG_ERRORS, callback_data=pack(NS_ADM_LOG, "errors", 1))],
            [InlineKeyboardButton(t.BTN_LOG_PROVIDER_CALLS, callback_data=pack(NS_ADM_LOG, "prq", 1))],
            _panel_row(),
        ]
    )


def logs_page_kb(action: str, *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """ترقيم صفحات السجلات."""
    rows: list[list[InlineKeyboardButton]] = []
    nav = pagination_row(NS_ADM_LOG, action, page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_LOG, "home"))
    return InlineKeyboardMarkup(rows)


def _id_buttons(ids: list[int], namespace: str, action: str, *tail: object) -> list[list[InlineKeyboardButton]]:
    """أزرار «#المعرّف» لفتح تفاصيل عناصر الصفحة (4 في الصف)."""
    buttons = [
        InlineKeyboardButton(f"#{item_id}", callback_data=pack(namespace, action, item_id, *tail))
        for item_id in ids
    ]
    return [buttons[i : i + 4] for i in range(0, len(buttons), 4)]


def logs_audit_kb(ids: list[int], *, category: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """سجل التدقيق: أزرار تفاصيل + ترقيم ضمن الفئة + زر الفلتر."""
    rows = _id_buttons(ids, NS_ADM_LOG, "aud", category, page)
    nav = pagination_row(NS_ADM_LOG, "acat", page=page, total_pages=total_pages, prefix_args=(category,))
    if nav:
        rows.append(nav)
    label = t.AUDIT_CATEGORY_LABELS.get(category, category)
    rows.append([InlineKeyboardButton(t.BTN_LOG_FILTER.format(label=label), callback_data=pack(NS_ADM_LOG, "afl", category))])
    rows.append(_back_row(NS_ADM_LOG, "home"))
    return InlineKeyboardMarkup(rows)


def logs_audit_filter_kb(current: str) -> InlineKeyboardMarkup:
    """قائمة اختيار فئة سجل التدقيق (الفئة الحالية بعلامة ✔)."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'✔ ' if key == current else ''}{label}", callback_data=pack(NS_ADM_LOG, "acat", key, 1)
            )
        ]
        for key, label in t.AUDIT_CATEGORY_LABELS.items()
    ]
    rows.append(_back_row(NS_ADM_LOG, "acat", current, 1))
    return InlineKeyboardMarkup(rows)


def logs_audit_detail_kb(category: str, page: int) -> InlineKeyboardMarkup:
    """تفاصيل سجل تدقيق: رجوع لنفس الصفحة والفئة."""
    return InlineKeyboardMarkup([_back_row(NS_ADM_LOG, "acat", category, page)])


def logs_errors_kb(ids: list[int], *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """سجل الأخطاء: أزرار تفاصيل + ترقيم."""
    rows = _id_buttons(ids, NS_ADM_LOG, "err", page)
    nav = pagination_row(NS_ADM_LOG, "errors", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_LOG, "home"))
    return InlineKeyboardMarkup(rows)


def logs_error_detail_kb(page: int) -> InlineKeyboardMarkup:
    """تفاصيل خطأ: رجوع لنفس الصفحة."""
    return InlineKeyboardMarkup([_back_row(NS_ADM_LOG, "errors", page)])


def logs_calls_kb(ids: list[int], *, failed_only: bool, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """سجل استدعاءات المزودين: تفاصيل + ترقيم + تبديل «الفاشلة فقط/الكل»."""
    mode = "f" if failed_only else "a"
    list_action = "prqf" if failed_only else "prq"
    rows = _id_buttons(ids, NS_ADM_LOG, "prqd", mode, page)
    nav = pagination_row(NS_ADM_LOG, list_action, page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    toggle = (
        InlineKeyboardButton(t.BTN_LOG_ALL_CALLS, callback_data=pack(NS_ADM_LOG, "prq", 1))
        if failed_only
        else InlineKeyboardButton(t.BTN_LOG_FAILED_ONLY, callback_data=pack(NS_ADM_LOG, "prqf", 1))
    )
    rows.append([toggle])
    rows.append(_back_row(NS_ADM_LOG, "home"))
    return InlineKeyboardMarkup(rows)


def logs_call_detail_kb(mode: str, page: int) -> InlineKeyboardMarkup:
    """تفاصيل استدعاء مزود: رجوع لنفس القائمة والصفحة."""
    return InlineKeyboardMarkup([_back_row(NS_ADM_LOG, "prqf" if mode == "f" else "prq", page)])
```

### `keyboards/admin_kb.py (النسخ والإحصائيات)` — مُحدَّث (مقتطف)

```
def backup_home_kb() -> InlineKeyboardMarkup:
    """الشاشة الرئيسية للنسخ: نسخة الآن، السجل، ضغط القاعدة، دليل الاستعادة."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_BACKUP_NEW, callback_data=pack(NS_ADM_BKP, "new"))],
            [
                InlineKeyboardButton(t.BTN_BACKUP_LIST, callback_data=pack(NS_ADM_BKP, "list", 1)),
                InlineKeyboardButton(t.BTN_BACKUP_VACUUM, callback_data=pack(NS_ADM_BKP, "vacask")),
            ],
            [InlineKeyboardButton(t.BTN_BACKUP_GUIDE, callback_data=pack(NS_ADM_BKP, "guide"))],
            [InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADM_BKP, "home"))],
            _panel_row(),
        ]
    )


def backup_list_kb(items: list[tuple[int, str]], *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """سجل النسخ: زر لكل نسخة (رقم + حالتها) + ترقيم + رجوع."""
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(label, callback_data=pack(NS_ADM_BKP, "view", backup_id, page))]
        for backup_id, label in items
    ]
    nav = pagination_row(NS_ADM_BKP, "list", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_BKP, "home"))
    return InlineKeyboardMarkup(rows)


def backup_view_kb(backup_id: int, page: int, perms: set[str], *, channel_ready: bool, usable: bool) -> InlineKeyboardMarkup:
    """
    تفاصيل نسخة: فحص + (إرسال للقناة/تنزيل لمن يملك `backup.download` وللنسخة السليمة فقط).

    المدخلات:
        channel_ready : قناة النسخ مضبوطة (وإلا لا معنى لزر الإرسال).
        usable        : النسخة سليمة ولها ملف (وإلا لا يظهر إرسال/تنزيل).
    """
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(t.BTN_BACKUP_VERIFY, callback_data=pack(NS_ADM_BKP, "verify", backup_id, page))]
    ]
    if usable and Permission.BACKUP_DOWNLOAD in perms:
        if channel_ready:
            rows.append(
                [InlineKeyboardButton(t.BTN_BACKUP_CHANNEL, callback_data=pack(NS_ADM_BKP, "chan", backup_id, page))]
            )
        rows.append(
            [InlineKeyboardButton(t.BTN_BACKUP_DOWNLOAD, callback_data=pack(NS_ADM_BKP, "dlask", backup_id, page))]
        )
    rows.append(_back_row(NS_ADM_BKP, "list", page))
    return InlineKeyboardMarkup(rows)


def backup_confirm_kb(confirm_label: str, confirm_action: str, *args: object, back: tuple[str, tuple[object, ...]]) -> InlineKeyboardMarkup:
    """شاشة تأكيد ثانٍ: زر التنفيذ + إلغاء يعيد للشاشة السابقة."""
    back_action, back_args = back
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(confirm_label, callback_data=pack(NS_ADM_BKP, confirm_action, *args))],
            [InlineKeyboardButton("❌ إلغاء", callback_data=pack(NS_ADM_BKP, back_action, *back_args))],
        ]
    )


def backup_guide_kb() -> InlineKeyboardMarkup:
    """دليل الاستعادة: رجوع فقط."""
    return InlineKeyboardMarkup([_back_row(NS_ADM_BKP, "home")])


# ============================ الإحصائيات (م10) ============================ #


def _stats_period_rows(action: str, current: str, *, extra: tuple[object, ...] = ()) -> list[list[InlineKeyboardButton]]:
    """صفّا أزرار الفترات (3+3) تُعلَّم فيها الفترة الحالية بنقطة، وتحمل `extra` قبل مفتاح الفترة."""
    from services.stats_service import PERIOD_KEYS, PERIOD_LABELS

    buttons = [
        InlineKeyboardButton(
            ("• " if key == current else "") + PERIOD_LABELS[key],
            callback_data=pack(NS_ADM_STATS, action, *extra, key),
        )
        for key in PERIOD_KEYS
    ]
    return [buttons[:3], buttons[3:]]


def stats_home_kb(period: str, perms: set[str]) -> InlineKeyboardMarkup:
    """الشاشة الرئيسية للإحصائيات: الفترات + الأقسام الفرعية + التصدير لمن يملك `stats.export`."""
    rows = _stats_period_rows("home", period)
    rows.append(
        [
            InlineKeyboardButton(t.BTN_STATS_SERVICES, callback_data=pack(NS_ADM_STATS, "svc", period)),
            InlineKeyboardButton(t.BTN_STATS_BUYERS, callback_data=pack(NS_ADM_STATS, "usr", period)),
            InlineKeyboardButton(t.BTN_STATS_DAILY, callback_data=pack(NS_ADM_STATS, "day", period)),
        ]
    )
    last = [InlineKeyboardButton(t.BTN_STATS_WALLET, callback_data=pack(NS_ADM_STATS, "wal"))]
    if Permission.STATS_EXPORT in perms:
        last.append(InlineKeyboardButton(t.BTN_STATS_EXPORT, callback_data=pack(NS_ADM_STATS, "expm", period)))
    rows.append(last)
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def stats_sub_kb(action: str, period: str) -> InlineKeyboardMarkup:
    """شاشة فرعية (خدمات/عملاء/يومي): تبديل الفترة + رجوع للملخص."""
    rows = _stats_period_rows(action, period)
    rows.append(_back_row(NS_ADM_STATS, "home", period))
    return InlineKeyboardMarkup(rows)


def stats_wallet_kb() -> InlineKeyboardMarkup:
    """شاشة التزامات المحفظة: تحديث + رجوع."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADM_STATS, "wal"))],
            _back_row(NS_ADM_STATS, "home", "today"),
        ]
    )


def stats_export_menu_kb(period: str) -> InlineKeyboardMarkup:
    """قائمة التصدير: نوع التقرير (يقود لشاشة تأكيد) + رجوع."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_STATS_EXPORT_ORDERS, callback_data=pack(NS_ADM_STATS, "expask", "orders", period))],
            [InlineKeyboardButton(t.BTN_STATS_EXPORT_DAILY, callback_data=pack(NS_ADM_STATS, "expask", "daily", period))],
            _back_row(NS_ADM_STATS, "home", period),
        ]
    )


def stats_export_confirm_kb(kind: str, period: str) -> InlineKeyboardMarkup:
    """تأكيد ثانٍ للتصدير + إلغاء يعود لقائمة التصدير."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_STATS_EXPORT_CONFIRM, callback_data=pack(NS_ADM_STATS, "exp", kind, period))],
            [InlineKeyboardButton("❌ إلغاء", callback_data=pack(NS_ADM_STATS, "expm", period))],
        ]
    )
```

### `texts/admin_ar.py (السجلات)` — مُحدَّث (مقتطف)

```
# ============================ السجلات ================================== #

LOGS_HOME = "📝 <b>السجلات</b>\n━━━━━━━━━━━━━━━━━━━━\n\nاختر السجل الذي تريد مراجعته."
BTN_LOG_AUDIT = "🧾 سجل التدقيق"
BTN_LOG_ERRORS = "❗ سجل الأخطاء"
BTN_LOG_PROVIDER_CALLS = "🔌 استدعاءات المزودين"
BTN_LOG_FILTER = "🔎 فلتر: {label}"
BTN_LOG_FAILED_ONLY = "❌ الفاشلة فقط"
BTN_LOG_ALL_CALLS = "📋 كل الاستدعاءات"

AUDIT_TITLE = (
    "🧾 <b>سجل التدقيق</b> · {category}\n━━━━━━━━━━━━━━━━━━━━\n"
    "{total} سجلاً · الصفحة {page} من {pages}\n\n{lines}\n\nاضغط رقم السجل لعرض تفاصيله."
)
AUDIT_EMPTY = "🧾 لا عمليات مسجّلة في هذه الفئة ({category})."
AUDIT_LINE = "{icon} <b>#{id} · {action}</b>\n   👮 {admin} · 🎯 {target}\n   🕒 {when}"

ERRORS_TITLE = (
    "❗ <b>آخر الأخطاء</b>\n━━━━━━━━━━━━━━━━━━━━\n{total} خطأً · الصفحة {page} من {pages}\n\n{lines}"
    "\n\nاضغط رقم الخطأ لعرض تفاصيله."
)
ERRORS_EMPTY = "✅ لا أخطاء مسجّلة — النظام نظيف."
ERROR_LINE = "<b>#{id} · {level}</b> · {source}\n   {message}\n   🕒 {when}"
```

### `texts/admin_ar.py (أيقونات/فئات/تفاصيل التدقيق)` — مُحدَّث (مقتطف)

```
#: أيقونة لكل نوع إجراء في سجل التدقيق (تُطابق الجزء الأول من اسم الإجراء الفعلي: `users.ban` ⇐ 👤)
AUDIT_ICONS: dict[str, str] = {
    "users": "👤",
    "payments": "💳",
    "orders": "📦",
    "services": "🛍",
    "providers": "🏢",
    "tickets": "🎫",
    "settings": "⚙️",
    "notifications": "🔔",
    "broadcast": "📣",
    "security": "🔐",
    "admins": "🛡",
    "admin": "🛡",
    "backup": "💾",
    "stats": "📈",
    "system": "🖥",
}

#: أسماء فئات فلتر سجل التدقيق (المفاتيح تطابق `AUDIT_CATEGORIES`)
AUDIT_CATEGORY_LABELS: dict[str, str] = {
    "all": "📋 الكل",
    "users": "👤 المستخدمون",
    "money": "💰 المال",
    "orders": "📦 الطلبات",
    "catalog": "🛍 الخدمات والمزودون",
    "tickets": "🎫 التذاكر",
    "settings": "⚙️ الإعدادات والإشعارات",
    "security": "🔐 الأمن والصلاحيات",
    "system": "🖥 النظام والنسخ",
}

AUDIT_FILTER_MENU = "🔎 <b>فلتر سجل التدقيق</b>\n━━━━━━━━━━━━━━━━━━━━\nاختر الفئة التي تريد عرضها:"

AUDIT_DETAIL = (
    "🧾 <b>سجل تدقيق #{id}</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    "⚙️ الإجراء: <code>{action}</code>\n"
    "👮 المنفّذ: {admin}\n"
    "🎯 الهدف: {target}\n"
    "📡 المصدر: {source}\n"
    "🕒 الوقت: {when}\n"
    "{blocks}"
)
AUDIT_DETAIL_BLOCK = "\n<b>{title}</b>\n<pre>{body}</pre>"
AUDIT_DETAIL_BLOCK_TITLES = {"before": "قبل التعديل", "after": "بعد التعديل", "details": "تفاصيل"}
AUDIT_DETAIL_NO_DATA = "\nℹ️ لا بيانات إضافية مسجّلة لهذه العملية."
AUDIT_NOT_FOUND = "❌ سجل التدقيق غير موجود."

ERROR_DETAIL = (
    "❗ <b>خطأ #{id}</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    "المستوى: <b>{level}</b>\n"
    "المصدر: {source}\n"
    "النوع: <code>{error_type}</code>\n"
    "🕒 الوقت: {when}\n"
    "👤 المستخدم: {user}\n"
    "🔔 أُبلغ الأدمن: {notified}\n\n"
    "<b>الرسالة</b>\n{message}\n"
    "{extra}"
)
ERROR_DETAIL_TRACE = "\n<b>أثر الاستدعاء (مقتطف)</b>\n<pre>{trace}</pre>"
ERROR_DETAIL_UPDATE = "\n<b>ملخص التحديث</b>\n<pre>{summary}</pre>"
ERROR_NOT_FOUND = "❌ سجل الخطأ غير موجود."

PROVIDER_CALLS_TITLE = (
    "🔌 <b>استدعاءات المزودين</b> · {mode}\n━━━━━━━━━━━━━━━━━━━━\n"
    "{total} استدعاءً · الصفحة {page} من {pages}\n\n{lines}\n\nاضغط رقم الاستدعاء لعرض تفاصيله."
)
PROVIDER_CALLS_EMPTY = "🔌 لا استدعاءات مسجّلة ({mode})."
PROVIDER_CALLS_MODE = {"all": "الكل", "failed": "الفاشلة فقط"}
PROVIDER_CALL_LINE = "{icon} <b>#{id} · {provider}</b> · {action}\n   {meta}\n   🕒 {when}"
PROVIDER_CALL_DETAIL = (
    "🔌 <b>استدعاء مزود #{id}</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    "المزود: {provider}\n"
    "العملية: <code>{action}</code>\n"
    "النتيجة: {result}\n"
    "HTTP: {http}\n"
    "المدة: {duration}\n"
    "الطلب المرتبط: {order}\n"
    "نوع الخطأ: <code>{error_type}</code>\n"
    "🕒 الوقت: {when}\n"
    "{extra}"
)
PROVIDER_CALL_REQUEST = "\n<b>ملخص الطلب</b>\n<pre>{body}</pre>"
PROVIDER_CALL_RESPONSE = "\n<b>مقتطف الرد</b>\n<pre>{body}</pre>"
PROVIDER_CALL_NOT_FOUND = "❌ سجل الاستدعاء غير موجود."
```

### `texts/admin_ar.py (النسخ والإحصائيات)` — جديد (مقتطف)

```
#                 النسخ الاحتياطي والاستعادة (المرحلة 10)                  #
# ======================================================================== #

MENU_BACKUP = "💾 النسخ الاحتياطي"
BTN_BACKUP_NEW = "🆕 نسخة الآن"
BTN_BACKUP_LIST = "📋 سجل النسخ"
BTN_BACKUP_VACUUM = "🧹 ضغط القاعدة"
BTN_BACKUP_GUIDE = "📖 دليل الاستعادة"
BTN_BACKUP_VERIFY = "🔍 فحص النسخة"
BTN_BACKUP_CHANNEL = "📤 إرسال للقناة"
BTN_BACKUP_DOWNLOAD = "⬇️ تنزيل لمحادثتي"
BTN_BACKUP_CONFIRM_DL = "✅ نعم، أرسل الملف"
BTN_BACKUP_CONFIRM_VAC = "✅ نعم، اضغط القاعدة"

BACKUP_STATUS_LABELS: dict[str, str] = {
    "ok": "✅ سليمة",
    "failed": "❌ فاشلة",
    "corrupt": "⛔ تالفة",
    "missing": "❓ الملف مفقود",
    "purged": "🗑 حُذف ملفها (الاحتفاظ)",
}
BACKUP_TYPE_LABELS: dict[str, str] = {
    "manual": "يدوية",
    "scheduled": "مجدولة",
    "pre_operation": "قبل عملية",
}

BACKUP_HOME = (
    "💾 <b>النسخ الاحتياطي</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "{health}\n\n"
    "• آخر نسخة سليمة: <b>{last}</b>\n"
    "• النسخ السليمة المحفوظة: <b>{ok_count}</b> ({ok_size})\n"
    "• نسخ بها مشكلة: <b>{bad_count}</b>\n"
    "• النسخ التلقائي: <b>{auto}</b>\n"
    "• الاحتفاظ: <b>{retention} يوماً</b> (لا يقل عن {min_keep} نسخ)\n"
    "• نسخة خارج السيرفر: <b>{offsite}</b>\n"
    "• حجم القاعدة: <b>{db_size}</b> · المتاح على القرص: <b>{free}</b>\n"
    "{notice}"
)
BACKUP_HEALTH_OK = "✅ النسخ الاحتياطي سليم"
BACKUP_HEALTH_NONE = "⛔ لا توجد أي نسخة سليمة بعد — خذ نسخة الآن"
BACKUP_HEALTH_OVERDUE = "⚠️ النسخ متأخر عن موعده"
BACKUP_HEALTH_AUTO_OFF = "⚠️ النسخ التلقائي معطّل — أنت تعتمد على النسخ اليدوي"
BACKUP_AUTO_ON = "كل {hours} ساعة"
BACKUP_AUTO_OFF = "معطّل"
BACKUP_OFFSITE_ON = "✅ تُرسل للقناة"
BACKUP_OFFSITE_NO_CHANNEL = "⚠️ لا — BACKUP_CHANNEL_ID غير مضبوط (النسخ على نفس السيرفر فقط)"
BACKUP_OFFSITE_DISABLED = "⚠️ لا — الإرسال للقناة معطّل في الإعدادات"
BACKUP_NEVER = "لا شيء بعد"

BACKUP_LIST_TITLE = "📋 <b>سجل النسخ</b> — صفحة {page}/{pages}\n━━━━━━━━━━━━━━━━━━━━\n\n{lines}"
BACKUP_LIST_EMPTY = "📋 <b>سجل النسخ</b>\n\nلا توجد نسخ مسجَّلة بعد."
BACKUP_LIST_LINE = "{status} <b>#{id}</b> · {type} · {size}\n      {when}{channel}"
BACKUP_LIST_CHANNEL_MARK = " · 📤"

BACKUP_VIEW = (
    "💾 <b>نسخة #{id}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "• الحالة: {status}\n"
    "• النوع: <b>{type}</b>\n"
    "• الملف: <code>{filename}</code>\n"
    "• الحجم: <b>{size}</b>\n"
    "• أُنشئت: <b>{created}</b> — بواسطة {by}\n"
    "• إصدار المخطَّط: <code>{schema}</code>\n"
    "• آخر فحص: <b>{verified}</b>\n"
    "• خارج السيرفر: <b>{channel}</b>\n"
    "• البصمة: <code>{sha}</code>\n"
    "{error}{notice}"
)
BACKUP_VIEW_ERROR = "\n⚠️ <b>سبب المشكلة:</b> {error}\n"
BACKUP_VIEW_NEVER = "لم تُفحص بعد"
BACKUP_VIEW_CHANNEL_SENT = "أُرسلت {when}"
BACKUP_VIEW_CHANNEL_NO = "لم تُرسل"
BACKUP_BY_SYSTEM = "النظام"

BACKUP_CREATED = "\n✅ تم إنشاء النسخة <b>#{id}</b> ({size}).\n"
BACKUP_CREATED_CHANNEL_FAIL = "⚠️ لكن إرسالها للقناة فشل — ستُعاد المحاولة تلقائياً.\n"
BACKUP_VERIFY_OK = "\n✅ الفحص ناجح: {message}\n"
BACKUP_VERIFY_FAIL = "\n⛔ الفحص فشل: {message}\n"
BACKUP_CHANNEL_DONE = "\n📤 أُرسلت النسخة إلى قناة النسخ.\n"
BACKUP_DOWNLOAD_DONE = "\n⬇️ أُرسل الملف إلى محادثتك — احذفه بعد حفظه.\n"
BACKUP_DOWNLOAD_ASK = (
    "⚠️ <b>تنزيل نسخة #{id}</b>\n\n"
    "الملف يحوي <b>كل بيانات النظام</b>: المستخدمون، الأرصدة، الطلبات، ومفاتيح المزودين "
    "(مشفّرة بـ<code>ENCRYPTION_KEY</code>). من يملكه مع المفتاح يملك النظام.\n\n"
    "• لا تُحوّله لأي أحد ولا تحفظه في مكان غير مشفّر.\n"
    "• يُسجَّل التنزيل في سجل التدقيق باسمك.\n\n"
    "هل تريد إرساله إلى هذه المحادثة؟"
)
BACKUP_VACUUM_ASK = (
    "🧹 <b>ضغط قاعدة البيانات</b>\n\n"
    "يُعيد بناء الملف ليسترد المساحة الفارغة. أثناء الضغط (ثوانٍ لقاعدة صغيرة، وأكثر للكبيرة) "
    "تتوقف الكتابة فيتأخر البوت قليلاً.\n\n"
    "سأأخذ <b>نسخة أمان</b> أولاً، وإن فشلت يُلغى الضغط. المتابعة؟"
)
BACKUP_VACUUM_DONE = (
    "\n🧹 تم الضغط: <b>{before}</b> ← <b>{after}</b>\n"
    "نسخة الأمان: <b>#{safety}</b>\n"
)
BACKUP_NOT_FOUND = "❌ هذه النسخة غير موجودة."

BACKUP_GUIDE = (
    "📖 <b>دليل استعادة نسخة</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "الاستعادة تتم <b>من السيرفر والبوت متوقف</b> — ليست زراً هنا عمداً، حتى لا يُستغل "
    "حساب أدمن مخترَق في إرجاع النظام لحالة قديمة.\n\n"
    "<b>الخطوات:</b>\n"
    "1) أوقف البوت.\n"
    "2) اعرض النسخ: <code>python -m scripts.restore_backup --list</code>\n"
    "3) استعد: <code>python -m scripts.restore_backup --latest</code>\n"
    "    أو <code>--id 12</code> أو <code>--file المسار</code>\n"
    "4) اكتب <code>RESTORE</code> عند السؤال.\n"
    "5) شغّل البوت.\n\n"
    "<b>ما يفعله السكربت:</b> يتحقق من البصمة والسلامة والمخطَّط، يحفظ القاعدة الحالية "
    "(لا يحذفها)، يستبدل الملف ذرّياً، ويسجّل العملية في التدقيق.\n\n"
    "<b>على سيرفر جديد:</b> انسخ ملف النسخة من قناة النسخ، ضع <code>.env</code> "
    "<b>بنفس ENCRYPTION_KEY</b> (بدونه لا تُفك مفاتيح المزودين)، ثم نفّذ الأمر أعلاه بـ<code>--file</code>.\n\n"
    "⚠️ كل ما حدث بعد وقت النسخة يضيع. راجع طلبات المزود والشحنات المعلّقة بعد الاستعادة."
)


# ======================================================================== #
#                      شاشة الإحصائيات (المرحلة 10)                        #
# ======================================================================== #

MENU_STATS = "📈 الإحصائيات"
BTN_STATS_SERVICES = "🏆 الخدمات"
BTN_STATS_BUYERS = "👥 العملاء"
BTN_STATS_DAILY = "📅 يومياً"
BTN_STATS_WALLET = "💼 المحفظة"
BTN_STATS_EXPORT = "📤 تصدير CSV"
BTN_STATS_EXPORT_ORDERS = "🧾 الطلبات (CSV)"
BTN_STATS_EXPORT_DAILY = "📅 الملخص اليومي (CSV)"
BTN_STATS_EXPORT_CONFIRM = "✅ نعم، صدّر وأرسل الملف"

STATS_HOME = (
    "📈 <b>الإحصائيات — {label}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "🧾 الطلبات: <b>{orders}</b> (جارية {active} · منتهية {finished})\n"
    "✅ نسبة النجاح: <b>{success}</b>\n\n"
    "💰 إجمالي المخصوم: <b>{gross}</b>\n"
    "↩️ المسترجَع: <b>{refund}</b>\n"
    "💵 <b>الإيراد الصافي: {net}</b>\n"
    "🧮 متوسط الطلب (صافي): <b>{avg}</b>\n"
    "{profit}\n"
    "👥 مشترون: <b>{buyers}</b> · مستخدمون جدد: <b>{new_users}</b>\n"
    "💳 إيداعات معتمدة: <b>{deposits}</b>\n"
    "➕ إضافات يدوية: <b>{credit}</b> · ➖ خصومات يدوية: <b>{debit}</b>\n\n"
    "ℹ️ <i>الفترة بوقت إنشاء الطلب وبتوقيت عدن. الصافي = المخصوم − المسترجَع.</i>"
)
STATS_PROFIT_LINE = (
    "\n📈 الربح التقديري: <b>{profit}</b>\n"
    "      تكلفة المزود: {cost} · تغطية {pct}% ({covered}/{eligible} طلباً منتهياً)\n"
)
STATS_PROFIT_NONE = "\n📈 الربح التقديري: <b>غير محسوب</b>\n      لا طلبات منتهية بتكلفة مزود مسجّلة في هذه الفترة.\n"
STATS_PROFIT_PARTIAL_NOTE = "      ⚠️ الأرقام تخص الطلبات المغطّاة فقط، لا كل الطلبات.\n"
STATS_NO_SUCCESS = "— (لا طلبات منتهية)"

STATS_SERVICES_TITLE = "🏆 <b>أكثر الخدمات طلباً — {label}</b>\n━━━━━━━━━━━━━━━━━━━━\n\n{lines}"
STATS_SERVICES_LINE = "{rank}. <b>{name}</b>\n      {count} طلب · صافي {net}"
STATS_SERVICES_EMPTY = "🏆 <b>أكثر الخدمات طلباً — {label}</b>\n\nلا طلبات في هذه الفترة."

STATS_BUYERS_TITLE = "👥 <b>أكثر العملاء إنفاقاً — {label}</b>\n━━━━━━━━━━━━━━━━━━━━\n\n{lines}"
STATS_BUYERS_LINE = "{rank}. <b>{name}</b>\n      {count} طلب · صافي {net}"
STATS_BUYERS_EMPTY = "👥 <b>أكثر العملاء إنفاقاً — {label}</b>\n\nلا إنفاق صافٍ في هذه الفترة."

STATS_DAILY_TITLE = "📅 <b>يومياً — {label}</b>\n━━━━━━━━━━━━━━━━━━━━\n\n{lines}\n\n{footer}"
STATS_DAILY_LINE = "<code>{day}</code> {bar} {count} طلب · {net}"
STATS_DAILY_EMPTY = "📅 <b>يومياً — {label}</b>\n\nلا طلبات في هذه الفترة."
STATS_DAILY_FOOTER = "المجموع: <b>{count}</b> طلب · صافي <b>{net}</b>"
STATS_DAILY_CUT = "\n(عُرضت أحدث {shown} يوماً من {total}؛ المجموع أدناه يشمل الكل)"

STATS_WALLET = (
    "💼 <b>التزامات المحفظة</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "💳 مجموع أرصدة العملاء الآن: <b>{balance}</b>\n"
    "   (هذا ما تدين به لهم)\n"
    "➕ إجمالي ما أُودع عبر الشحن: <b>{deposits}</b>\n"
    "🛒 إجمالي ما أُنفق على الطلبات: <b>{spent}</b>"
)

STATS_EXPORT_MENU = (
    "📤 <b>تصدير CSV — {label}</b>\n\n"
    "اختر التقرير. الملفات تحوي بيانات تجارية حسّاسة، وكل تصدير يُسجَّل في التدقيق باسمك.\n"
    "• لا يشمل روابط العملاء ولا معرّفات تيليجرام.\n"
    "• الحد الأقصى {cap} صفاً للملف."
)
STATS_EXPORT_ASK = (
    "⚠️ <b>تأكيد التصدير</b>\n\n"
    "التقرير: <b>{kind}</b>\n"
    "الفترة: <b>{label}</b>\n\n"
    "سيُرسل الملف إلى هذه المحادثة. لا تحوّله لمن لا يحق له رؤية الأرقام. المتابعة؟"
)
STATS_EXPORT_KIND_LABELS: dict[str, str] = {"orders": "الطلبات", "daily": "الملخص اليومي"}
STATS_EXPORT_CAPTION = "📤 {kind} — {label}\nالصفوف: {rows}{cut}"
STATS_EXPORT_CUT = " ⚠️ قُطع عند الحد الأقصى — ضيّق الفترة للحصول على الكل."
STATS_EXPORT_DONE = "✅ أُرسل الملف ({rows} صفاً)."
```

## الاختبارات الجديدة

### `tests/integration/test_backup_phase10.py` — جديد

```python
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
```

### `tests/integration/test_restore_script_phase10.py` — جديد

```python
"""اختبارات سكربت الاستعادة وحماية الترقية (المرحلة 10)."""

from __future__ import annotations

import argparse
import gzip
import json
import sqlite3
import stat
from pathlib import Path

import pytest

from database.database import Database
from database.migrator import Migrator
from database.repositories import Repositories
from scripts import init_db, restore_backup
from services import build_services
from utils import backup_files
from utils.security import SecretBox, generate_encryption_key
from utils.single_instance import SingleInstance

pytestmark = pytest.mark.asyncio


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """بيئة CLI معزولة: مسارات القاعدة والنسخ واللوق على مجلد مؤقت."""
    paths = {
        "db": tmp_path / "data" / "smm.db",
        "backups": tmp_path / "backups",
        "log": tmp_path / "logs" / "bot.log",
        "tmp": tmp_path,
    }
    paths["db"].parent.mkdir()
    monkeypatch.setenv("DATABASE_PATH", str(paths["db"]))
    monkeypatch.setenv("BACKUP_DIR", str(paths["backups"]))
    monkeypatch.setenv("LOG_FILE", str(paths["log"]))
    for key in ("BOT_TOKEN", "ENCRYPTION_KEY", "SUPER_ADMIN_IDS"):
        monkeypatch.delenv(key, raising=False)
    return paths


async def _make_db_with_backup(env: dict[str, Path], users: int = 2):
    """قاعدة فيها `users` مستخدمين + نسخة موثَّقة منها. يرجع معلومة النسخة."""
    db = Database(env["db"])
    await db.connect()
    await Migrator(db).apply_all()
    repos = Repositories(db)
    async with db.transaction() as tx:
        root = await repos.users.create(tx, telegram_id=1, first_name="Root", role="super_admin")
        for index in range(users - 1):
            await repos.users.create(tx, telegram_id=100 + index, first_name=f"U{index}")
    services = build_services(
        db, repos, secret_box=SecretBox(generate_encryption_key()), settings_ttl_seconds=0, backup_dir=env["backups"]
    )
    info = await services.backups.create(root)
    await db.close()
    return info


async def _count_users(path: Path) -> int:
    """عدد المستخدمين في ملف قاعدة (قراءة مباشرة)."""
    connection = sqlite3.connect(path)
    try:
        return int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])
    finally:
        connection.close()


async def _add_user(path: Path, telegram_id: int) -> None:
    """إضافة مستخدم بعد أخذ النسخة (ليثبت أن الاستعادة تمحوه)."""
    db = Database(path)
    await db.connect()
    repos = Repositories(db)
    async with db.transaction() as tx:
        await repos.users.create(tx, telegram_id=telegram_id, first_name="Late")
    await db.close()


# ================================ الاستعادة ================================ #


async def test_restore_latest_roundtrip(env, capsys) -> None:
    """استعادة أحدث نسخة تُرجع القاعدة لحالتها، وتحفظ نسخة أمان، وتدقّق، وتضبط 0600."""
    await _make_db_with_backup(env, users=2)
    await _add_user(env["db"], 555)
    assert await _count_users(env["db"]) == 3

    code = await restore_backup.run(latest=True, assume_yes=True)

    assert code == 0, capsys.readouterr().out
    assert await _count_users(env["db"]) == 2
    assert stat.S_IMODE(env["db"].stat().st_mode) == 0o600
    assert not Path(str(env["db"]) + "-wal").exists()
    safety = [p for p in backup_files.list_backup_files(env["backups"]) if "pre_operation" in p.name]
    assert len(safety) == 1                                       # القاعدة الحالية محفوظة قبل الاستبدال
    connection = sqlite3.connect(env["db"])
    try:
        row = connection.execute("SELECT source, details_json FROM audit_logs WHERE action = 'backup.restore'").fetchone()
    finally:
        connection.close()
    assert row[0] == "cli" and json.loads(row[1])["sha"] == "verified"


async def test_latest_skips_safety_copies(env) -> None:
    """تكرار `--latest` لا يعيد حالة «ما قبل الاستعادة» (نسخ الأمان لا تُختار تلقائياً)."""
    await _make_db_with_backup(env, users=2)
    await _add_user(env["db"], 555)
    assert await restore_backup.run(latest=True, assume_yes=True) == 0
    await _add_user(env["db"], 556)
    assert await restore_backup.run(latest=True, assume_yes=True) == 0
    assert await _count_users(env["db"]) == 2                     # من النسخة الأصلية لا من نسخة الأمان


async def test_restore_by_id_and_by_file(env) -> None:
    """الاستعادة بالرقم وبمسار الملف تعملان."""
    info = await _make_db_with_backup(env, users=2)
    await _add_user(env["db"], 555)
    assert await restore_backup.run(backup_id=info.id, assume_yes=True) == 0
    assert await _count_users(env["db"]) == 2
    await _add_user(env["db"], 556)
    assert await restore_backup.run(file=str(env["backups"] / info.filename), assume_yes=True) == 0
    assert await _count_users(env["db"]) == 2


async def test_confirmation_word_is_required(env, capsys) -> None:
    """بلا `--yes`: أي إجابة غير RESTORE تلغي العملية ولا تمس القاعدة."""
    await _make_db_with_backup(env, users=2)
    await _add_user(env["db"], 555)
    code = await restore_backup.run(latest=True, input_fn=lambda _p: "yes")
    assert code == 1 and await _count_users(env["db"]) == 3
    assert "أُلغيت" in capsys.readouterr().out
    assert await restore_backup.run(latest=True, input_fn=lambda _p: "RESTORE") == 0
    assert await _count_users(env["db"]) == 2


async def test_eof_on_prompt_cancels(env) -> None:
    """إغلاق stdin (تشغيل غير تفاعلي بلا --yes) يلغي بدل أن يستبدل."""
    await _make_db_with_backup(env, users=2)
    await _add_user(env["db"], 555)

    def _eof(_prompt: str) -> str:
        raise EOFError

    assert await restore_backup.run(latest=True, input_fn=_eof) == 1
    assert await _count_users(env["db"]) == 3


async def test_refuses_while_bot_is_running(env, capsys) -> None:
    """قفل البوت ممسوك ⇒ رفض فوري ولا تغيير."""
    await _make_db_with_backup(env, users=2)
    await _add_user(env["db"], 555)
    holder = SingleInstance(env["db"].parent / "bot.lock")
    holder.acquire()
    try:
        code = await restore_backup.run(latest=True, assume_yes=True)
    finally:
        holder.release()
    assert code == 1 and "البوت يعمل" in capsys.readouterr().out
    assert await _count_users(env["db"]) == 3


async def test_tampered_backup_is_rejected_and_db_untouched(env, capsys) -> None:
    """تغيير بايت واحد في النسخة ⇒ البصمة لا تطابق ⇒ رفض والقاعدة كما هي."""
    info = await _make_db_with_backup(env, users=2)
    await _add_user(env["db"], 555)
    path = env["backups"] / info.filename
    path.write_bytes(path.read_bytes() + b"x")
    assert await restore_backup.run(latest=True, assume_yes=True) == 1
    assert "بصمة" in capsys.readouterr().out
    assert await _count_users(env["db"]) == 3
    assert not list(env["db"].parent.glob(".restore_*"))             # لا ملفات مؤقتة متروكة


async def test_newer_schema_is_rejected(env, tmp_path, capsys) -> None:
    """نسخة مخطَّطها أحدث من كود هذا الإصدار تُرفض (لا نشغّل كوداً قديماً على مخطط جديد)."""
    info = await _make_db_with_backup(env, users=2)
    raw = tmp_path / "newer.db"
    raw.write_bytes(gzip.decompress((env["backups"] / info.filename).read_bytes()))
    connection = sqlite3.connect(raw)
    connection.execute("INSERT INTO schema_migrations(version, name, checksum, applied_at) VALUES ('9999','x','x','2030-01-01')")
    connection.commit()
    connection.close()
    assert await restore_backup.run(file=str(raw), assume_yes=True) == 1
    assert "أحدث" in capsys.readouterr().out


async def test_garbage_file_is_rejected(env, tmp_path, capsys) -> None:
    """ملف ليس قاعدة SQLite يُرفض."""
    await _make_db_with_backup(env, users=2)
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"hello" * 1000)
    assert await restore_backup.run(file=str(junk), assume_yes=True) == 1
    assert await _count_users(env["db"]) == 2


async def test_corrupt_current_db_is_kept_aside_not_deleted(env) -> None:
    """القاعدة الحالية التالفة تُنقل باسم `.corrupt-…` (تحليل لاحق) ثم تُستعاد النسخة."""
    await _make_db_with_backup(env, users=2)
    env["db"].write_bytes(b"corrupted" * 500)
    assert await restore_backup.run(latest=True, assume_yes=True) == 0
    assert await _count_users(env["db"]) == 2
    kept = list(env["db"].parent.glob("smm.db.corrupt-*"))
    assert len(kept) == 1 and kept[0].read_bytes().startswith(b"corrupted")


async def test_restore_on_fresh_server_without_current_db(env) -> None:
    """على سيرفر جديد بلا قاعدة: تُستعاد النسخة عبر `--file` بلا خطأ."""
    info = await _make_db_with_backup(env, users=2)
    env["db"].unlink()
    for suffix in ("-wal", "-shm"):
        Path(str(env["db"]) + suffix).unlink(missing_ok=True)
    assert await restore_backup.run(file=str(env["backups"] / info.filename), assume_yes=True) == 0
    assert await _count_users(env["db"]) == 2


async def test_no_selector_and_unknown_id_fail_cleanly(env, capsys) -> None:
    """رقم غير موجود أو ملف غير موجود يعطي رسالة واضحة وكود 1."""
    await _make_db_with_backup(env, users=2)
    assert await restore_backup.run(backup_id=9999, assume_yes=True) == 1
    assert await restore_backup.run(file="/nonexistent/x.db.gz", assume_yes=True) == 1
    assert "غير موجود" in capsys.readouterr().out


async def test_list_shows_backups_without_touching_anything(env, capsys) -> None:
    """`--list` يعرض النسخ ولا يحجز قفلاً ولا يعدّل."""
    info = await _make_db_with_backup(env, users=2)
    assert await restore_backup.run(list_only=True) == 0
    assert info.filename in capsys.readouterr().out


# ============================ نسخة أمان قبل الترقية ============================ #


async def test_init_db_takes_safety_backup_before_pending_migrations(env, monkeypatch, capsys) -> None:
    """ترقية قاعدة قائمة بترحيل ناقص تسبقها نسخة `pre_operation` موثَّقة."""
    await _make_db_with_backup(env, users=2)
    before = len(backup_files.list_backup_files(env["backups"]))

    async def _pending(self):
        return ["9999"]

    async def _apply(self):
        return ["9999"]

    monkeypatch.setattr(Migrator, "pending", _pending)
    monkeypatch.setattr(Migrator, "apply_all", _apply)
    await init_db.run(argparse.Namespace(status=False))
    files = backup_files.list_backup_files(env["backups"])
    assert len(files) == before + 1 and any("pre_operation" in f.name for f in files)
    assert "نسخة أمان قبل الترقية" in capsys.readouterr().out


async def test_init_db_fresh_database_takes_no_backup(env) -> None:
    """قاعدة جديدة (لا ترحيلات سابقة) لا تحتاج نسخة أمان."""
    await init_db.run(argparse.Namespace(status=False))
    assert not backup_files.list_backup_files(env["backups"])
```

### `tests/integration/test_stats_phase10.py` — جديد

```python
"""
اختبارات المرحلة 10 — الإحصائيات: الفترات المحلية، شاشات الواجهة، الصلاحيات، وتصدير CSV.

تغطي: حدود الفترات (Asia/Aden)، تمييز «لا صلاحية للربح» عن «غير محسوب»، تحييد حقن الصيغ،
سقف الصفوف، غياب البيانات الخاصة من الملف، التدقيق، ورفض الصلاحية على الـcallback نفسه.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

import pytest

from core.permissions import Permission
from database.models import Service, User
from database.repositories import Repositories
from handlers.admin import stats as stats_handlers
from keyboards.callback_data import pack
from services import ServiceContainer
from services.stats_service import EXPORT_KINDS, PERIOD_KEYS, build_period
from tests.integration.test_user_interface import (  # إعادة استخدام أدوات الواجهة نفسها
    bot,  # noqa: F401
    context,  # noqa: F401
    load_user,
    press,
)
from tests.telegram_fakes import FakeBot, FakeContext
from utils.formatters import money_text

pytestmark = pytest.mark.asyncio


async def _orders(services: ServiceContainer, user: User, admin: User, mock_service: Service, count: int = 2) -> None:
    """رصيد + طلبات حقيقية (كل طلب 10_000 وحدة لكمية 1000)."""
    await services.wallet.adjust_balance(
        target=user, amount_units=10_000_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    await services.settings.set("duplicate_order_window_minutes", 0)
    for index in range(count):
        await services.orders.create_order(
            user, service_id=mock_service.id, link=f"https://instagram.com/private{index}", quantity=1000
        )


def _decode(document: bytes) -> list[list[str]]:
    """فك ملف CSV المُرسَل (UTF-8 مع BOM) إلى صفوف."""
    assert document.startswith("\ufeff".encode()), "الملف بلا BOM فلن يفتحه Excel بالعربية"
    return list(csv.reader(io.StringIO(document.decode("utf-8-sig"))))


# ======================================================================== #
#                                الفترات                                    #
# ======================================================================== #


async def test_every_period_key_is_valid() -> None:
    """كل مفتاح معلن يُبنى فترة صالحة بحدّ بداية قبل النهاية."""
    for key in PERIOD_KEYS:
        period = build_period(key)
        assert period.start_iso < period.end_iso, key


async def test_today_starts_at_local_midnight_not_utc() -> None:
    """«اليوم» يبدأ عند منتصف الليل المحلي (UTC+3) لا منتصف ليل UTC، و«أمس» يتصل به بلا فجوة."""
    today, yesterday = build_period("today"), build_period("yesterday")
    start = datetime.fromisoformat(today.start_iso).astimezone(timezone.utc)
    assert start.hour == 21 and start.minute == 0, today.start_iso   # 00:00 محلياً = 21:00 UTC
    assert yesterday.end_iso == today.start_iso
    assert datetime.fromisoformat(today.end_iso) - datetime.fromisoformat(today.start_iso) == timedelta(days=1)


async def test_unknown_period_is_rejected() -> None:
    """مفتاح فترة عبث به مستخدم يُرفض ولا يُحوَّل صامتاً إلى فترة افتراضية."""
    from core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        build_period("forever")


# ======================================================================== #
#                              شاشات الواجهة                                #
# ======================================================================== #


async def test_home_screen_shows_net_revenue(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User, mock_service: Service,
) -> None:
    """شاشة الملخص تعرض الإيراد الصافي الحقيقي من قاعدة البيانات."""
    await _orders(services, user, admin, mock_service, count=2)
    await load_user(bot, context, admin)
    await press(bot, context, stats_handlers.home_screen, pack("st", "home", "today"), admin.telegram_id)

    symbol = await services.settings.money_symbol()
    assert money_text(20_000, symbol) in bot.last.text
    assert "الإحصائيات" in bot.last.text


@pytest.mark.parametrize("key", PERIOD_KEYS)
async def test_all_screens_render_for_every_period(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User,
    mock_service: Service, key: str,
) -> None:
    """كل شاشة × كل فترة تُعرض بلا استثناء وبأزرار تنقل."""
    await _orders(services, user, admin, mock_service, count=1)
    await load_user(bot, context, admin)
    for handler, action in (
        (stats_handlers.home_screen, "home"),
        (stats_handlers.services_screen, "svc"),
        (stats_handlers.buyers_screen, "usr"),
        (stats_handlers.daily_screen, "day"),
    ):
        bot.clear()
        await press(bot, context, handler, pack("st", action, key), admin.telegram_id)
        assert bot.sent, f"{action}/{key}: لا شاشة"
        assert bot.last.buttons, f"{action}/{key}: بلا أزرار"
        assert "❌" not in bot.last.text, f"{action}/{key}: {bot.last.text}"


async def test_unknown_period_button_shows_error(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """زر بفترة مزوّرة لا يُسقط البوت ويُظهر رسالة خطأ عربية."""
    await load_user(bot, context, admin)
    await press(bot, context, stats_handlers.home_screen, pack("st", "home", "forever"), admin.telegram_id)
    assert "فترة غير معروفة" in " ".join(m.text for m in bot.sent) + " ".join(str(a["text"]) for a in bot.answers)


async def test_buyers_and_services_lists_are_real(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User, mock_service: Service,
) -> None:
    """قائمتا أكثر الخدمات والعملاء تعرضان ما في الطلبات فعلاً."""
    await _orders(services, user, admin, mock_service, count=2)
    await load_user(bot, context, admin)
    await press(bot, context, stats_handlers.services_screen, pack("st", "svc", "today"), admin.telegram_id)
    assert mock_service.name in bot.last.text and "2 طلب" in bot.last.text
    await press(bot, context, stats_handlers.buyers_screen, pack("st", "usr", "today"), admin.telegram_id)
    assert "1." in bot.last.text


async def test_empty_period_screens_say_so(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """فترة بلا طلبات: رسائل «لا طلبات» لا أرقام وهمية."""
    await load_user(bot, context, admin)
    await press(bot, context, stats_handlers.services_screen, pack("st", "svc", "yesterday"), admin.telegram_id)
    assert "لا طلبات" in bot.last.text
    await press(bot, context, stats_handlers.daily_screen, pack("st", "day", "yesterday"), admin.telegram_id)
    assert bot.sent


async def test_wallet_screen(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User,
) -> None:
    """شاشة التزامات المحفظة تعرض مجموع أرصدة العملاء."""
    await services.wallet.adjust_balance(target=user, amount_units=50_000, admin=admin, reason="x", credit=True)
    await load_user(bot, context, admin)
    await press(bot, context, stats_handlers.wallet_screen, pack("st", "wal"), admin.telegram_id)
    symbol = await services.settings.money_symbol()
    assert money_text(50_000, symbol) in bot.last.text


# ======================================================================== #
#                         الصلاحيات (على الـcallback)                        #
# ======================================================================== #


async def test_user_without_stats_view_is_denied_everywhere(
    bot: FakeBot, context: FakeContext, repos: Repositories, services: ServiceContainer
) -> None:
    """دور الدعم لا يملك `stats.view`: كل شاشة تُرفض بلا عرض أي رقم."""
    async with repos.db.transaction() as tx:
        support = await repos.users.create(tx, telegram_id=555000111, username="sup", first_name="Sup", role="support")
    await load_user(bot, context, support)
    for handler, data in (
        (stats_handlers.home_screen, pack("st", "home", "today")),
        (stats_handlers.services_screen, pack("st", "svc", "today")),
        (stats_handlers.buyers_screen, pack("st", "usr", "today")),
        (stats_handlers.daily_screen, pack("st", "day", "today")),
        (stats_handlers.wallet_screen, pack("st", "wal")),
        (stats_handlers.export_menu, pack("st", "expm", "today")),
    ):
        bot.clear()
        await press(bot, context, handler, data, support.telegram_id)
        assert not bot.sent, f"سُرِّب محتوى لمستخدم بلا صلاحية: {data}"
        assert bot.answers and bot.answers[-1]["alert"] is True


async def test_profit_visible_only_with_profit_permission(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User,
    super_admin: User, mock_service: Service,
) -> None:
    """الأدمن العادي لا يرى سطر الربح إطلاقاً؛ الأدمن الأعلى يراه (حتى لو «غير محسوب»)."""
    await _orders(services, user, admin, mock_service, count=1)

    await load_user(bot, context, admin)
    await press(bot, context, stats_handlers.home_screen, pack("st", "home", "today"), admin.telegram_id)
    assert "الربح" not in bot.last.text

    bot.clear()
    await load_user(bot, context, super_admin)
    await press(bot, context, stats_handlers.home_screen, pack("st", "home", "today"), super_admin.telegram_id)
    assert "الربح التقديري" in bot.last.text
    assert "غير محسوب" in bot.last.text          # لا طلبات منتهية بعد ⇒ صراحةً لا صفر مختلق


# ======================================================================== #
#                               التصدير                                      #
# ======================================================================== #


async def test_export_requires_confirmation_step(
    bot: FakeBot, context: FakeContext, super_admin: User
) -> None:
    """شاشة التأكيد لا ترسل ملفاً ولا تُدقّق؛ النوع المجهول يُرفض."""
    await load_user(bot, context, super_admin)
    await press(bot, context, stats_handlers.export_menu, pack("st", "expm", "7d"), super_admin.telegram_id)
    assert bot.last.buttons

    bot.clear()
    await press(bot, context, stats_handlers.export_ask, pack("st", "expask", "orders", "7d"), super_admin.telegram_id)
    assert bot.sent and not any(m.kind == "document" for m in bot.sent)

    bot.clear()
    await press(bot, context, stats_handlers.export_ask, pack("st", "expask", "secrets", "7d"), super_admin.telegram_id)
    assert bot.answers[-1]["alert"] is True and not bot.sent


@pytest.mark.parametrize("kind", EXPORT_KINDS)
async def test_export_sends_csv_and_audits(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, repos: Repositories, user: User,
    admin: User, super_admin: User, mock_service: Service, kind: str,
) -> None:
    """التصدير يرسل ملف CSV كمستند محمي ويُدقَّق في `audit_logs`."""
    await _orders(services, user, admin, mock_service, count=2)
    await load_user(bot, context, super_admin)
    await press(bot, context, stats_handlers.export_action, pack("st", "exp", kind, "today"), super_admin.telegram_id)

    documents = [m for m in bot.sent if m.kind == "document"]
    assert len(documents) == 1
    sent = documents[0]
    assert sent.kwargs["filename"].endswith(".csv")
    assert sent.kwargs["protect_content"] is True
    rows = _decode(sent.kwargs["document"])
    assert len(rows) >= 2                      # رأس + بيانات
    audits = [e for e in await repos.audit.list_recent(limit=20) if e.action == "stats.export"]
    assert audits and audits[0].admin_id == super_admin.id and audits[0].target_id == kind


async def test_export_denied_without_permission(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, repos: Repositories, admin: User,
    super_admin: User,
) -> None:
    """سحب `stats.export` من الأدمن: لا ملف ولا تدقيق نجاح، ويُسجَّل الرفض أمنياً."""
    await services.auth.set_user_permission(super_admin, admin.id, Permission.STATS_EXPORT, allow=False)
    await load_user(bot, context, admin)
    await press(bot, context, stats_handlers.export_action, pack("st", "exp", "orders", "today"), admin.telegram_id)

    assert not any(m.kind == "document" for m in bot.sent)
    entries = await repos.audit.list_recent(limit=20)
    assert not any(e.action == "stats.export" for e in entries)
    assert any(e.action == "security.permission_denied" for e in entries)


async def test_export_excludes_private_data(
    services: ServiceContainer, user: User, admin: User, super_admin: User, mock_service: Service,
) -> None:
    """الملف لا يحوي رابط العميل ولا معرّف تيليجرام ولا أي مفتاح."""
    await _orders(services, user, admin, mock_service, count=2)
    exported = await services.stats.export_csv(super_admin, "orders", build_period("today"))
    text = exported.content.decode("utf-8-sig")
    assert "instagram.com" not in text and "private0" not in text
    assert str(user.telegram_id) not in text
    assert exported.rows == 2


async def test_export_neutralizes_formula_injection(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, super_admin: User,
    mock_service: Service,
) -> None:
    """اسم خدمة يبدأ بـ`=` يُسبق بفاصلة عليا فلا يُنفَّذ كمعادلة في Excel."""
    await _orders(services, user, admin, mock_service, count=1)
    order = (await services.orders.list_for_user(user))[0]
    async with repos.db.transaction() as tx:
        await tx.execute(                                  # اللقطة غير قابلة للتعديل عبر المستودع عمداً
            "UPDATE orders SET service_name_snapshot = ? WHERE id = ?",
            ('=HYPERLINK("http://evil","x")', order.id),
        )
    exported = await services.stats.export_csv(super_admin, "orders", build_period("today"))
    body = _decode(exported.content)
    service_cell = body[1][body[0].index("service")]
    assert service_cell.startswith("'="), service_cell
    for row in body[1:]:
        for cell in row:
            assert not cell.startswith(("=", "+", "@")), cell


async def test_export_row_cap_is_declared(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, super_admin: User,
    mock_service: Service,
) -> None:
    """تجاوز `export_max_rows` يقطع الملف ويعلن القطع (لا قطع صامت)."""
    await _orders(services, user, admin, mock_service, count=3)
    async with repos.db.transaction() as tx:                  # تجاوز حد القاعدة الأدنى للاختبار فقط
        await tx.execute("UPDATE settings SET value = '2' WHERE key = 'export_max_rows'")
    exported = await services.stats.export_csv(super_admin, "orders", build_period("today"))
    assert exported.truncated is True
    assert exported.rows == 2


async def test_profit_columns_follow_profit_permission(
    services: ServiceContainer, user: User, admin: User, super_admin: User, mock_service: Service,
) -> None:
    """أعمدة التكلفة/الربح تظهر لمن يملك `stats.profit` فقط."""
    await _orders(services, user, admin, mock_service, count=1)
    await services.auth.set_user_permission(super_admin, admin.id, Permission.STATS_EXPORT, allow=True)
    plain = await services.stats.export_csv(admin, "orders", build_period("today"))
    full = await services.stats.export_csv(super_admin, "orders", build_period("today"))
    assert "provider_cost" not in plain.columns and "est_profit" not in plain.columns
    assert "provider_cost" in full.columns and "est_profit" in full.columns


async def test_export_unknown_kind_rejected_by_service(
    services: ServiceContainer, super_admin: User
) -> None:
    """الخدمة نفسها ترفض نوعاً غير معروف (لا اعتماد على الواجهة فقط)."""
    from core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        await services.stats.export_csv(super_admin, "users", build_period("today"))


# ======================================================================== #
#                              الملخص اليومي                                 #
# ======================================================================== #


async def test_daily_digest_is_net_and_has_no_profit_line(
    services: ServiceContainer, user: User, admin: User, mock_service: Service,
) -> None:
    """الملخص اليومي يصل لكل من يملك `stats.view` ⇒ بلا ربح ولا تكلفة، والمبيعات صافية."""
    from texts.templates import admin_daily_digest

    await _orders(services, user, admin, mock_service, count=2)
    digest = await services.stats.system_digest()
    assert digest["orders_today"] == 2 and digest["revenue_today_units"] == 20_000
    _title, message = admin_daily_digest(
        orders_today=digest["orders_today"],
        revenue_today_units=digest["revenue_today_units"],
        deposits_today_units=digest["deposits_today_units"],
        pending_payments=digest["pending_payments"],
        attention_orders=digest["attention_orders"],
        open_tickets=digest["open_tickets"],
        new_users=digest["new_users_today"],
        errors_24h=digest["errors_24h"],
        refunds_today_units=digest["refunds_today_units"],
        completed_today=digest["completed_today"],
        failed_today=digest["failed_today"],
    )
    assert "ربح" not in message and "تكلفة" not in message
    assert "صافي مبيعات" in message


# ======================================================================== #
#                       حالات حدّية إضافية للواجهة                           #
# ======================================================================== #


async def test_export_telegram_failure_is_reported_not_swallowed(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User,
    super_admin: User, mock_service: Service, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """فشل إرسال الملف عبر تيليجرام يُبلَّغ للأدمن بوضوح (والتدقيق مسجّل لأن الملف أُنشئ)."""
    from telegram.error import NetworkError

    async def broken(*_args, **_kwargs):
        raise NetworkError("انقطاع اختباري")

    await _orders(services, user, admin, mock_service, count=1)
    await load_user(bot, context, super_admin)
    monkeypatch.setattr(bot, "send_document", broken)
    await press(bot, context, stats_handlers.export_action, pack("st", "exp", "orders", "today"), super_admin.telegram_id)
    assert "تعذّر إرسال الملف" in bot.last.text


async def test_daily_screen_caps_lines_but_totals_cover_all_days(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, repos: Repositories, user: User,
    admin: User, mock_service: Service,
) -> None:
    """أكثر من 31 يوماً: تُقطع الأسطر ويُعلَن القطع، والمجموع يشمل كل الأيام (لا يُخفى مال)."""
    await _orders(services, user, admin, mock_service, count=34)
    order_ids = [int(r["id"]) for r in await repos.db.fetchall("SELECT id FROM orders ORDER BY id")]
    assert len(order_ids) == 34
    async with repos.db.transaction() as tx:               # كل طلب في يوم مختلف (الأيام الخالية لا تظهر)
        for offset, order_id in enumerate(order_ids):
            when = (datetime.now(timezone.utc) - timedelta(days=offset)).isoformat()
            await tx.execute("UPDATE orders SET created_at = ? WHERE id = ?", (when, order_id))
    series = await services.stats.daily_series(admin, days=90)
    assert len(series) == 34

    await load_user(bot, context, admin)
    await press(bot, context, stats_handlers.daily_screen, pack("st", "day", "90d"), admin.telegram_id)
    text = bot.last.text
    assert text.count("█") + text.count("▫️") <= 31 * 8
    assert "31" in text and "34" in text                 # القطع معلن: المعروض 31 من 34
    symbol = await services.settings.money_symbol()
    assert money_text(340_000, symbol) in text         # مجموع الأيام كلها وليس المعروضة فقط
```

### `tests/integration/test_logs_phase10.py` — جديد

```python
"""
اختبارات المرحلة 10 — واجهة السجلات: فلتر فئات التدقيق، التفاصيل، الأخطاء، واستدعاءات المزودين.

تثبّت: دقة الترقيم والعدّ، عدم تسريب الأسرار في التفاصيل (حتى لو دخلت السجل قبل تسجيلها)،
تهريب HTML، رفض الفئات المزوّرة، رفض الصلاحية على الـcallback، وأن الشاشات للقراءة فقط.
"""

from __future__ import annotations

import pytest

from database.models import Provider, User
from database.repositories import Repositories
from handlers.admin import logs
from keyboards.callback_data import pack
from services import ServiceContainer
from services.audit_service import AUDIT_CATEGORIES
from tests.integration.test_user_interface import (  # إعادة استخدام أدوات الواجهة نفسها
    bot,  # noqa: F401
    context,  # noqa: F401
    load_user,
    press,
)
from tests.telegram_fakes import FakeBot, FakeContext
from texts import admin_ar as t

pytestmark = pytest.mark.asyncio

#: كل أسماء الإجراءات التي تكتبها الخدمات والسكربتات فعلياً (مستخرجة من الشيفرة)
REAL_ACTIONS = (
    "admin.create_via_script", "admin.role_change_via_script", "admins.permission.clear",
    "admins.permission.override", "backup.create", "backup.create_failed", "backup.download",
    "backup.purge", "backup.restore", "backup.send_channel", "backup.vacuum", "backup.verify",
    "broadcast.send", "notifications.templates", "orders.cancel", "orders.link_provider_id",
    "orders.refund", "orders.status.override", "payments.approve", "payments.methods",
    "payments.reject", "providers.create", "providers.key.update", "providers.update",
    "security.permission_denied", "services.archive", "services.category.create",
    "services.create", "services.price", "services.sync", "services.update", "settings.update",
    "stats.export", "system.promote_super_admin", "system.seed_super_admin", "tickets.assign",
    "tickets.close", "tickets.reply", "users.balance.credit", "users.balance.debit", "users.ban",
    "users.note", "users.register", "users.role.change", "users.unban",
)


def _categories_of(action: str) -> list[str]:
    """الفئات (غير `all`) التي تلتقط إجراءً بعينه."""
    return [
        key for key, prefixes in AUDIT_CATEGORIES.items()
        if prefixes and any(action.startswith(prefix) for prefix in prefixes)
    ]


async def _log(services: ServiceContainer, action: str, admin: User | None = None, **extra) -> None:
    """تسجيل عملية تدقيق حقيقية عبر الخدمة."""
    await services.audit.log_standalone(
        action=action, admin_id=admin.id if admin else None, target_type="x", target_id="1", **extra
    )


# ======================================================================== #
#                              الفئات والفلتر                                #
# ======================================================================== #


async def test_every_real_action_belongs_to_exactly_one_category() -> None:
    """لا إجراء يضيع من الفلاتر ولا يظهر في فئتين (العدّ يطابق المعروض)."""
    for action in REAL_ACTIONS:
        assert len(_categories_of(action)) == 1, (action, _categories_of(action))


async def test_icons_match_real_action_prefixes() -> None:
    """كل بادئة فعلية لها أيقونة (لا 🔸 افتراضية بسبب أسماء مفردة خاطئة)."""
    for action in REAL_ACTIONS:
        prefix = action.split(".", 1)[0]
        assert prefix in t.AUDIT_ICONS, prefix
        assert logs._audit_icon(action) == t.AUDIT_ICONS[prefix]
    assert logs._audit_icon("unknown.thing") == "🔸"


async def test_category_labels_cover_all_categories() -> None:
    """كل فئة لها اسم عربي ولا اسم بلا فئة."""
    assert set(t.AUDIT_CATEGORY_LABELS) == set(AUDIT_CATEGORIES)


async def test_filter_returns_only_category_and_counts_match(
    services: ServiceContainer, admin: User
) -> None:
    """الفلتر يعيد سجلات الفئة فقط وعدّها مطابق لما يُعرض."""
    for action in ("payments.approve", "payments.reject", "users.ban", "orders.refund", "users.balance.credit"):
        await _log(services, action, admin)

    money = await services.audit.list_filtered("money", limit=50)
    assert {e.action for e in money} == {"payments.approve", "payments.reject", "users.balance.credit"}
    assert await services.audit.count_filtered("money") == 3
    assert await services.audit.count_filtered("orders") == 1
    assert await services.audit.count_filtered("all") == await services.audit.count()


async def test_unknown_category_is_rejected_not_treated_as_all(services: ServiceContainer) -> None:
    """فئة مزوّرة تُرفض في الخدمة (لا تُعرض كل السجلات صامتةً)."""
    from core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        await services.audit.list_filtered("hax")
    with pytest.raises(ValidationError):
        await services.audit.count_filtered("")


async def test_like_wildcards_in_prefix_do_not_match_everything(
    services: ServiceContainer, repos: Repositories, admin: User
) -> None:
    """`_` و`%` في البادئة تُعامل حرفياً (حقن LIKE)."""
    await _log(services, "usersXban", admin)
    assert await repos.audit.count_by_prefixes(("users_ban",)) == 0
    assert await repos.audit.count_by_prefixes(("%",)) == 0


# ======================================================================== #
#                              شاشة التدقيق                                  #
# ======================================================================== #


async def test_audit_screen_paginates_accurately(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, admin: User
) -> None:
    """20 سجلاً بحجم صفحة 8 ⇒ 3 صفحات؛ الصفحة الأخيرة فيها المتبقي فقط."""
    start = await services.audit.count()
    for index in range(20):
        await _log(services, "payments.approve", admin, details={"n": index})
    total = start + 20
    await load_user(bot, context, admin)

    await press(bot, context, logs.audit_screen, pack("al", "acat", "money", 3), admin.telegram_id)
    assert "الصفحة 3 من 3" in bot.last.text
    assert bot.last.text.count("payments.approve") == 20 - 16

    await press(bot, context, logs.audit_screen, pack("al", "audit", 1), admin.telegram_id)
    assert f"{total} سجلاً" in bot.last.text
    detail_buttons = [b for b in bot.last.buttons if b.startswith("al:aud:")]
    assert len(detail_buttons) == 8


async def test_audit_filter_menu_and_selection(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, admin: User
) -> None:
    """قائمة الفلتر فيها كل الفئات وكل زر يعمل؛ الاختيار يعرض فئته فقط."""
    await _log(services, "tickets.close", admin)
    await _log(services, "users.ban", admin)
    await load_user(bot, context, admin)

    await press(bot, context, logs.audit_filter_screen, pack("al", "afl", "all"), admin.telegram_id)
    for key in AUDIT_CATEGORIES:
        assert pack("al", "acat", key, 1) in bot.last.buttons

    await press(bot, context, logs.audit_screen, pack("al", "acat", "tickets", 1), admin.telegram_id)
    assert "tickets.close" in bot.last.text and "users.ban" not in bot.last.text


async def test_empty_category_says_so(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """فئة بلا سجلات: رسالة واضحة وأزرار عودة."""
    await load_user(bot, context, admin)
    await press(bot, context, logs.audit_screen, pack("al", "acat", "catalog", 1), admin.telegram_id)
    assert "لا عمليات" in bot.last.text and bot.last.buttons


async def test_forged_category_button_shows_error(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """زر بفئة مزوّرة لا يُسقط البوت ولا يعرض شيئاً من السجلات."""
    await load_user(bot, context, admin)
    await press(bot, context, logs.audit_screen, pack("al", "acat", "hax", 1), admin.telegram_id)
    shown = " ".join(m.text for m in bot.sent) + " ".join(str(a["text"]) for a in bot.answers)
    assert "فئة سجل غير معروفة" in shown


# ======================================================================== #
#                             تفاصيل سجل التدقيق                             #
# ======================================================================== #


async def test_audit_detail_shows_before_after(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, repos: Repositories, admin: User
) -> None:
    """التفاصيل تعرض الإجراء والمنفّذ وقيم قبل/بعد بتنسيق مقروء."""
    async with repos.db.transaction() as tx:
        entry_id = await services.audit.log(
            tx, action="settings.update", admin_id=admin.id, target_type="setting", target_id="min_order",
            before={"value": "20000"}, after={"value": "30000"}, details={"note": "اختبار"},
        )
    await load_user(bot, context, admin)
    await press(bot, context, logs.audit_detail_screen, pack("al", "aud", entry_id, "settings", 1), admin.telegram_id)

    text = bot.last.text
    assert "settings.update" in text and "20000" in text and "30000" in text
    assert t.AUDIT_DETAIL_BLOCK_TITLES["before"] in text and t.AUDIT_DETAIL_BLOCK_TITLES["after"] in text
    assert pack("al", "acat", "settings", 1) in bot.last.buttons          # الرجوع لنفس الفئة والصفحة


async def test_audit_detail_escapes_html(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, repos: Repositories, admin: User
) -> None:
    """نص يحوي وسوم HTML لا يكسر العرض (يُهرَّب)."""
    async with repos.db.transaction() as tx:
        entry_id = await services.audit.log(
            tx, action="users.note", admin_id=admin.id, details={"note": "<b>خطر</b><script>x</script>"}
        )
    await load_user(bot, context, admin)
    await press(bot, context, logs.audit_detail_screen, pack("al", "aud", entry_id, "all", 1), admin.telegram_id)
    assert "<script>" not in bot.last.text and "&lt;script&gt;" in bot.last.text


async def test_audit_detail_redacts_secrets_even_for_legacy_rows(
    bot: FakeBot, context: FakeContext, repos: Repositories, admin: User, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """سر دخل السجل قبل تسجيله كسرّ معروف لا يظهر في التفاصيل (تنقية ثانية عند العرض)."""
    import utils.security as security

    monkeypatch.setattr(security, "_KNOWN_SECRETS", set(security._KNOWN_SECRETS))
    secret = "LEGACY-SECRET-VALUE-9876543210"
    async with repos.db.transaction() as tx:               # إدخال خام يتجاوز تنقية الكتابة
        cursor = await tx.execute(
            "INSERT INTO audit_logs (admin_id, action, details_json, source, created_at) VALUES (?,?,?,?,?)",
            (admin.id, "providers.update", f'{{"leak": "{secret}"}}', "telegram", "2026-01-01T00:00:00+00:00"),
        )
        entry_id = cursor.lastrowid
    security.register_secret(secret)

    await load_user(bot, context, admin)
    await press(bot, context, logs.audit_detail_screen, pack("al", "aud", entry_id, "all", 1), admin.telegram_id)
    assert secret not in bot.last.text and "***" in bot.last.text


async def test_audit_detail_truncates_long_values(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, repos: Repositories, admin: User
) -> None:
    """قيمة ضخمة تُقتطع فلا تتجاوز حد رسالة تيليجرام."""
    async with repos.db.transaction() as tx:
        entry_id = await services.audit.log(
            tx, action="settings.update", admin_id=admin.id,
            before={"v": "ب" * 5000}, after={"v": "ا" * 5000}, details={"v": "ج" * 5000},
        )
    await load_user(bot, context, admin)
    await press(bot, context, logs.audit_detail_screen, pack("al", "aud", entry_id, "all", 1), admin.telegram_id)
    assert len(bot.last.text) < 4096


async def test_audit_detail_missing_entry(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """معرّف غير موجود: رسالة واضحة لا استثناء."""
    await load_user(bot, context, admin)
    await press(bot, context, logs.audit_detail_screen, pack("al", "aud", 999999, "all", 1), admin.telegram_id)
    assert t.AUDIT_NOT_FOUND in bot.last.text


# ======================================================================== #
#                                  الأخطاء                                  #
# ======================================================================== #


async def _error(repos: Repositories, **kwargs) -> int:
    """تسجيل خطأ اختباري وإرجاع معرّفه."""
    async with repos.db.transaction() as tx:
        return await repos.error_logs.log(tx, **{"message": "خطأ", "source": "tests", **kwargs})


async def test_errors_screen_counts_and_paginates(
    bot: FakeBot, context: FakeContext, repos: Repositories, admin: User
) -> None:
    """11 خطأً ⇒ صفحتان بإجمالي دقيق وأزرار تفاصيل."""
    for index in range(11):
        await _error(repos, message=f"عطل رقم {index}")
    await load_user(bot, context, admin)
    await press(bot, context, logs.errors_screen, pack("al", "errors", 1), admin.telegram_id)
    assert "11 خطأً" in bot.last.text and "الصفحة 1 من 2" in bot.last.text
    assert len([b for b in bot.last.buttons if b.startswith("al:err:")]) == 8

    await press(bot, context, logs.errors_screen, pack("al", "errors", 2), admin.telegram_id)
    assert len([b for b in bot.last.buttons if b.startswith("al:err:")]) == 3


async def test_error_detail_shows_trace_and_redacts(
    bot: FakeBot, context: FakeContext, repos: Repositories, admin: User, user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """تفاصيل الخطأ: النوع والأثر والمستخدم وملخص التحديث؛ والأسرار المسجّلة لاحقاً تُخفى."""
    import utils.security as security

    monkeypatch.setattr(security, "_KNOWN_SECRETS", set(security._KNOWN_SECRETS))
    secret = "TRACE-SECRET-VALUE-1234567890"
    error_id = await _error(
        repos, error_type="KeyError", message="فشل <b>حرج</b>", user_id=user.id,
        traceback_snippet=f"File x.py line 3\n  token={secret}", update_summary="callback:st:home",
    )
    security.register_secret(secret)

    await load_user(bot, context, admin)
    await press(bot, context, logs.error_detail_screen, pack("al", "err", error_id, 1), admin.telegram_id)
    text = bot.last.text
    assert "KeyError" in text and "File x.py" in text and "callback:st:home" in text
    assert secret not in text
    assert "<b>حرج</b>" not in text and "&lt;b&gt;" in text


async def test_error_detail_missing(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """خطأ غير موجود: رسالة واضحة."""
    await load_user(bot, context, admin)
    await press(bot, context, logs.error_detail_screen, pack("al", "err", 424242, 1), admin.telegram_id)
    assert t.ERROR_NOT_FOUND in bot.last.text


# ======================================================================== #
#                           استدعاءات المزودين                                #
# ======================================================================== #


async def _calls(repos: Repositories, provider: Provider) -> None:
    """استدعاءان ناجحان وآخر فاشل."""
    async with repos.db.transaction() as tx:
        await repos.provider_requests.log(
            tx, provider_id=provider.id, action="balance", is_success=True, http_status=200,
            duration_ms=120, response_snippet='{"balance": "10"}',
        )
        await repos.provider_requests.log(
            tx, provider_id=provider.id, action="status", is_success=True, http_status=200, duration_ms=80,
        )
        await repos.provider_requests.log(
            tx, provider_id=provider.id, action="add", is_success=False, http_status=500, duration_ms=2000,
            error_type="ProviderTemporaryError", request_summary="service=1 qty=1000",
            response_snippet="Internal <error>",
        )


async def test_provider_calls_list_and_failed_filter(
    bot: FakeBot, context: FakeContext, repos: Repositories, provider: Provider, admin: User
) -> None:
    """القائمة تعرض الكل مع اسم المزود؛ وفلتر «الفاشلة» يعرض الفاشل فقط."""
    await _calls(repos, provider)
    await load_user(bot, context, admin)

    await press(bot, context, logs.calls_screen, pack("al", "prq", 1), admin.telegram_id)
    assert "3 استدعاءً" in bot.last.text and provider.name in bot.last.text
    assert len([b for b in bot.last.buttons if b.startswith("al:prqd:")]) == 3
    assert pack("al", "prqf", 1) in bot.last.buttons

    await press(bot, context, logs.calls_failed_screen, pack("al", "prqf", 1), admin.telegram_id)
    assert "1 استدعاءً" in bot.last.text and "ProviderTemporaryError" in bot.last.text
    assert len([b for b in bot.last.buttons if b.startswith("al:prqd:")]) == 1
    assert pack("al", "prq", 1) in bot.last.buttons


async def test_provider_call_detail(
    bot: FakeBot, context: FakeContext, repos: Repositories, provider: Provider, admin: User
) -> None:
    """تفاصيل الاستدعاء الفاشل: HTTP والمدة والخطأ وملخص الطلب ومقتطف الرد (مهرَّب)."""
    await _calls(repos, provider)
    failed = (await repos.provider_requests.list_page(only_failed=True, limit=1))[0]
    await load_user(bot, context, admin)
    await press(bot, context, logs.call_detail_screen, pack("al", "prqd", failed["id"], "f", 1), admin.telegram_id)

    text = bot.last.text
    assert "500" in text and "2000ms" in text and "ProviderTemporaryError" in text
    assert "service=1 qty=1000" in text and "Internal &lt;error&gt;" in text
    assert pack("al", "prqf", 1) in bot.last.buttons


async def test_provider_call_detail_never_shows_api_key(
    bot: FakeBot, context: FakeContext, repos: Repositories, provider: Provider, admin: User,
) -> None:
    """مفتاح مزود ظهر في ملخص الطلب يُنقّى عند التخزين ولا يصل للشاشة."""
    key = "sk_live_ABCDEFGHIJKLMNOP1234"
    async with repos.db.transaction() as tx:
        await repos.provider_requests.log(
            tx, provider_id=provider.id, action="add", is_success=False,
            request_summary=f"key={key} service=1", secrets=(key,),
        )
    row = (await repos.provider_requests.list_page(limit=1))[0]
    await load_user(bot, context, admin)
    await press(bot, context, logs.call_detail_screen, pack("al", "prqd", row["id"], "a", 1), admin.telegram_id)
    assert key not in bot.last.text


async def test_provider_calls_empty_and_missing(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """لا استدعاءات: رسالة واضحة؛ معرّف غير موجود: رسالة لا استثناء."""
    await load_user(bot, context, admin)
    await press(bot, context, logs.calls_screen, pack("al", "prq", 1), admin.telegram_id)
    assert "لا استدعاءات" in bot.last.text
    await press(bot, context, logs.call_detail_screen, pack("al", "prqd", 777, "a", 1), admin.telegram_id)
    assert t.PROVIDER_CALL_NOT_FOUND in bot.last.text


# ======================================================================== #
#                       الصلاحيات والقراءة فقط                                #
# ======================================================================== #


async def test_new_log_screens_require_logs_view(
    bot: FakeBot, context: FakeContext, repos: Repositories, services: ServiceContainer
) -> None:
    """دور الدعم (بلا `logs.view`) مرفوض في كل شاشة جديدة: لا محتوى ولا تلميح."""
    async with repos.db.transaction() as tx:
        support = await repos.users.create(tx, telegram_id=555000222, username="sup2", first_name="S", role="support")
    await load_user(bot, context, support)
    for handler, data in (
        (logs.audit_screen, pack("al", "acat", "money", 1)),
        (logs.audit_filter_screen, pack("al", "afl", "all")),
        (logs.audit_detail_screen, pack("al", "aud", 1, "all", 1)),
        (logs.error_detail_screen, pack("al", "err", 1, 1)),
        (logs.calls_screen, pack("al", "prq", 1)),
        (logs.calls_failed_screen, pack("al", "prqf", 1)),
        (logs.call_detail_screen, pack("al", "prqd", 1, "a", 1)),
    ):
        bot.clear()
        await press(bot, context, handler, data, support.telegram_id)
        assert not bot.sent, data
        assert bot.answers[-1]["alert"] is True


async def test_log_screens_are_read_only(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, repos: Repositories,
    provider: Provider, admin: User,
) -> None:
    """لا زر حذف/تعديل/مسح في أي شاشة سجلات جديدة."""
    await _log(services, "users.ban", admin)
    await _error(repos)
    await _calls(repos, provider)
    entry = (await services.audit.list_filtered("all", limit=1))[0]
    err = (await services.audit.recent_errors(limit=1))[0]
    call = (await repos.provider_requests.list_page(limit=1))[0]
    await load_user(bot, context, admin)
    for handler, data in (
        (logs.audit_screen, pack("al", "acat", "users", 1)),
        (logs.audit_filter_screen, pack("al", "afl", "users")),
        (logs.audit_detail_screen, pack("al", "aud", entry.id, "all", 1)),
        (logs.errors_screen, pack("al", "errors", 1)),
        (logs.error_detail_screen, pack("al", "err", err["id"], 1)),
        (logs.calls_screen, pack("al", "prq", 1)),
        (logs.call_detail_screen, pack("al", "prqd", call["id"], "a", 1)),
    ):
        bot.clear()
        await press(bot, context, handler, data, admin.telegram_id)
        for button in bot.last.buttons:
            assert not any(word in button for word in ("del", "edit", "clear", "purge")), button
```
