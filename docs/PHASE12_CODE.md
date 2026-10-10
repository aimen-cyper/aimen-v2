# الكود الكامل — المرحلة 12 (الإصدار النهائي 1.0.0)

كل ما في هذا الملف منسوخ آلياً من ملفات المشروع الفعلية وقت كتابة التقرير.

> الملفات الكبيرة التي تغيّر منها جزء محدود تُعرض كمقتطف موسوم بوضوح، وفيه الدوال المتغيرة **كاملة**. الملفان المولَّدان `docs/SETTINGS.md` و`docs/PERMISSIONS.md` لا يُعرضان هنا (يولّدهما `python -m scripts.gen_reference_docs` ويفحصهما الاختبار). تعديلات اختبارية صغيرة غير معروضة: `test_dispatcher_phase11.py` (LinkPreviewOptions + توقيع `do_request`)، `test_ledger_fuzz_phase11.py` (تشغيل `audit_ledger` على بيانات الـfuzz)، واختبارا الإحصائيات اليومية (الأيام الخالية). الملفات غير المذكورة لم تتغيّر عن المرحلة 11.

## الفهرس

- `main.py` — 222 سطراً (جديد/مُحدَّث: التقاط أخطاء الإقلاع بلا تسريب التوكن + LinkPreviewOptions)
- `core/constants.py` — 44 سطراً (مُحدَّث: APP_VERSION=1.0.0)
- `handlers/common/conversation.py` — 88 سطراً (مُحدَّث: إسكات تحذير per_message الاستشاري)
- `handlers/common/ui.py` — 100 سطراً (مُحدَّث: link_preview_options بدل المعامل المهجور)
- `jobs/telegram_sender.py` — 145 سطراً (مُحدَّث: link_preview_options بدل المعامل المهجور)
- `services/stats_service.py` — 29 سطراً (مُحدَّث (مقتطف): StatsService._daily — تعبئة الأيام الخالية بصفر)
- `handlers/admin/stats.py` — 34 سطراً (مُحدَّث (مقتطف): daily_screen)
- `scripts/audit_ledger.py` — 268 سطراً (جديد: التدقيق المالي للقراءة فقط)
- `scripts/gen_reference_docs.py` — 159 سطراً (جديد: مولّد SETTINGS.md وPERMISSIONS.md)
- `README.md` — 142 سطراً (جديد)
- `docs/RUNBOOK.md` — 237 سطراً (جديد)
- `tests/integration/test_startup_phase12.py` — 90 سطراً (جديد)
- `tests/integration/test_audit_ledger_phase12.py` — 145 سطراً (جديد)
- `tests/unit/test_release_phase12.py` — 148 سطراً (جديد)

---

## `main.py`

> جديد/مُحدَّث: التقاط أخطاء الإقلاع بلا تسريب التوكن + LinkPreviewOptions

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
from telegram.error import InvalidToken, NetworkError, TimedOut    # noqa: E402
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
from utils.security import SecretBox, sanitize                      # noqa: E402
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

    المخرجات: رمز خروج للنظام (0 إيقاف سليم، 1 خطأ إعداد أو فشل إقلاع/انهيار، 2 نسخة تعمل بالفعل).

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
        # drop_pending_updates: تجاهل ما تراكم أثناء التوقف حتى لا تُنفَّذ ضغطات
        # أزرار قديمة على حالة تغيّرت — الطلبات نفسها تُستأنف من قاعدة البيانات.
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "my_chat_member"],
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

## `core/constants.py`

> مُحدَّث: APP_VERSION=1.0.0

```python
"""ثوابت عامة للنظام (قيم لا تتغير أثناء التشغيل)."""

from __future__ import annotations

#: اسم المشروع وإصداره
APP_NAME: str = "SMM Telegram Bot"
APP_VERSION = "1.0.0"

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

---

## `handlers/common/conversation.py`

> مُحدَّث: إسكات تحذير per_message الاستشاري

```python
"""
مصنع المحادثات الموحّد مع مهلة عدم النشاط (المرحلة 9).

المشكلة:
    محادثة تأكيد مالية (اعتماد شحن، تعديل رصيد، إرسال إذاعة…) تبقى مفتوحة
    للأبد في ذاكرة البوت. لو ترك الأدمن شاشة «تأكيد» ثم عاد بعد يومين وضغط
    الزر القديم لنُفِّذت عملية بناءً على قرار نسيه — وقد تتغير حالة الحساب
    أو صلاحياته خلال ذلك. كذلك كل محادثة معلّقة تحجز ذاكرة بلا نهاية.

الحل:
    كل محادثات المشروع تُبنى عبر `conversation(...)` فتنتهي تلقائياً بعد
    `CONVERSATION_TIMEOUT_SECONDS` من آخر تفاعل: تُمسح بيانات كل المسارات
    ويُعلَم المستخدم برسالة واضحة، فيتحول الزر القديم إلى «زر منتهٍ» عادي
    تتعامل معه المسارات الاحتياطية بدل أن ينفّذ شيئاً.
"""

from __future__ import annotations

import warnings
from typing import Any

from telegram import Update
from telegram.warnings import PTBUserWarning
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from handlers.common.ui import send
from keyboards.user_kb import main_menu_kb
from texts import ar
from utils.logging_setup import get_logger

# تحذير PTB «per_message=False» استشاري: كل محادثاتنا تتتبّع المستخدم/المحادثة عمداً (لا الرسالة الواحدة)،
# وإظهاره عند كل إقلاع يُخفي التحذيرات الحقيقية في اللوق ⇒ نُسكت هذا النص تحديداً لا غير.
warnings.filterwarnings("ignore", message=r".*per_message=False.*CallbackQueryHandler.*", category=PTBUserWarning)

logger = get_logger(__name__)

#: مهلة عدم النشاط قبل إنهاء المحادثة (ثانية) — 15 دقيقة
CONVERSATION_TIMEOUT_SECONDS: int = 15 * 60

#: كل مفاتيح بيانات المسارات في `user_data` (تُمسح كلها عند انتهاء المهلة)
FLOW_DATA_KEYS: tuple[str, ...] = (
    "admin_flow",
    "order_flow",
    "deposit_flow",
    "ticket_flow",
    "ticket_reply_flow",
)


async def on_conversation_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    إنهاء محادثة منتهية المهلة: مسح بياناتها وإبلاغ المستخدم بوضوح.

    المخرجات: `ConversationHandler.END`.
    """
    if context.user_data is not None:
        for key in FLOW_DATA_KEYS:
            context.user_data.pop(key, None)
    user = update.effective_user
    logger.info("انتهت مهلة محادثة المستخدم %s بسبب عدم النشاط", user.id if user else "?")
    await send(update, context, ar.CONVERSATION_TIMED_OUT, main_menu_kb())
    return ConversationHandler.END


def conversation(*, states: dict[Any, list], **kwargs: Any) -> ConversationHandler:
    """
    بناء `ConversationHandler` بمهلة عدم نشاط موحّدة.

    يقبل نفس وسائط `ConversationHandler` (entry_points/fallbacks/name/per_chat…)،
    ويضيف حالة `TIMEOUT` تمسح البيانات وتُبلغ المستخدم. لا يُسمح بتمرير
    `conversation_timeout` يدوياً حتى لا تشذّ محادثة عن السياسة.
    """
    if "conversation_timeout" in kwargs:
        raise ValueError("المهلة موحّدة في CONVERSATION_TIMEOUT_SECONDS ولا تُمرَّر يدوياً")
    merged = dict(states)
    merged[ConversationHandler.TIMEOUT] = [
        CallbackQueryHandler(on_conversation_timeout),
        MessageHandler(filters.ALL, on_conversation_timeout),
    ]
    return ConversationHandler(
        states=merged, conversation_timeout=CONVERSATION_TIMEOUT_SECONDS, **kwargs
    )

```

---

## `handlers/common/ui.py`

> مُحدَّث: link_preview_options بدل المعامل المهجور

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
"""

from __future__ import annotations

from telegram import InlineKeyboardMarkup, LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes

from utils.logging_setup import get_logger

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
        await query.answer(text=text or None, show_alert=alert)
    except BadRequest as exc:
        # الاستعلام القديم (أكثر من 48 ساعة) لا يمكن الرد عليه — نسجّل ونكمل
        logger.debug("تعذر الرد على ضغطة زر قديمة: %s", exc)


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
            await query.edit_message_text(
                text=text,
                reply_markup=markup,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=disable_preview),
            )
            return
        except BadRequest as exc:
            if NOT_MODIFIED in str(exc).lower():
                return                      # المستخدم ضغط نفس الزر — لا جديد يُعرض
            logger.warning("تعذر تحرير الرسالة، سيُرسل بديل: %s", exc)

    await send(update, context, text, markup, disable_preview=disable_preview)


async def send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
    *,
    disable_preview: bool = True,
) -> None:
    """إرسال رسالة جديدة إلى محادثة المستخدم (تُستخدم للنتائج والتنبيهات)."""
    chat = update.effective_chat
    if chat is None:
        logger.warning("تحديث بلا محادثة — تعذر الإرسال")
        return
    try:
        await context.bot.send_message(
            chat_id=chat.id,
            text=text,
            reply_markup=markup,
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=disable_preview),
        )
    except Forbidden:
        # المستخدم حظر البوت — تُعلَّم الحالة في قاعدة البيانات عبر مهمة الإشعارات
        logger.info("المستخدم %s حظر البوت", chat.id)

```

---

## `jobs/telegram_sender.py`

> مُحدَّث: link_preview_options بدل المعامل المهجور

```python
"""
جسر الإرسال بين طابور الإشعارات وتيليجرام.

خدمة الإشعارات لا تعرف تيليجرام إطلاقاً — تطلب فقط دالة إرسال بالشكل:
    ``async sender(telegram_id, title, message) -> message_id | None``

هذا الملف يوفّر تلك الدالة ويُترجم أخطاء تيليجرام إلى استثناءات الطابور
حتى يقرر الطابور بنفسه: يُعيد المحاولة (مؤقت) أم يتوقف (محظور/نهائي).
"""

from __future__ import annotations

import html

from core.exceptions import (
    NotificationBlockedError,
    NotificationPermanentError,
    NotificationTemporaryError,
)
from telegram import Bot, LinkPreviewOptions
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TimedOut

#: أقصى طول نص رسالة في تيليجرام (نقتطع قبله بهامش أمان)
MAX_MESSAGE_LEN = 3900


class TelegramNotificationSender:
    """مُرسل إشعارات عبر تيليجرام مع تصنيف دقيق للأخطاء."""

    def __init__(self, bot: Bot) -> None:
        """تهيئة المرسل ببوت تيليجرام الجاهز."""
        self.bot = bot

    async def __call__(self, telegram_id: int, title: str, message: str) -> int | None:
        """
        إرسال إشعار واحد.

        المخرجات: رقم الرسالة في تيليجرام عند النجاح.

        الاستثناءات:
            NotificationBlockedError   : المستخدم حظر البوت (لا تُعاد المحاولة).
            NotificationTemporaryError : شبكة/مهلة/حد معدل (تُعاد المحاولة).
            NotificationPermanentError : رسالة غير صالحة أو محادثة غير موجودة.
        """
        text = self._format(title, message)
        try:
            sent = await self.bot.send_message(
                chat_id=telegram_id,
                text=text,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        except Forbidden as exc:
            raise NotificationBlockedError(f"المستخدم {telegram_id} حظر البوت: {exc}") from exc
        except RetryAfter as exc:
            raise NotificationTemporaryError(
                f"تجاوز حد الإرسال، إعادة المحاولة بعد {exc.retry_after}ث"
            ) from exc
        except (TimedOut, NetworkError) as exc:
            raise NotificationTemporaryError(f"خطأ شبكة أثناء الإرسال: {exc}") from exc
        except BadRequest as exc:
            text_error = str(exc).lower()
            if "chat not found" in text_error or "user is deactivated" in text_error:
                raise NotificationBlockedError(f"محادثة غير متاحة: {exc}") from exc
            raise NotificationPermanentError(f"رسالة مرفوضة من تيليجرام: {exc}") from exc
        return sent.message_id

    @staticmethod
    def _format(title: str, message: str) -> str:
        """تنسيق الإشعار: عنوان عريض ثم النص، مع تهريب HTML واقتطاع الطويل."""
        safe_title = html.escape(title or "")
        safe_message = html.escape(message or "")
        body = f"<b>{safe_title}</b>\n\n{safe_message}" if safe_title else safe_message
        if len(body) > MAX_MESSAGE_LEN:
            body = body[: MAX_MESSAGE_LEN - 1] + "…"
        return body


class TelegramBroadcastSender:
    """
    مُرسل الرسائل الجماعية (نص أو صورة بتعليق) بنفس تصنيف أخطاء الإشعارات.

    لماذا مُرسل مستقل عن `TelegramNotificationSender`؟
        إشعار النظام له عنوان ونص ويُنسَّق بـHTML، أما الإذاعة فنص يكتبه الأدمن
        بحروفه وقد يرافقه ملف. خلطهما في دالة واحدة كان سيجبرنا على معاملات
        اختيارية تُربك الطرفين. التصنيف الدقيق للأخطاء مشترك عبر `_classify`.
    """

    def __init__(self, bot: Bot) -> None:
        """تهيئة المرسل ببوت تيليجرام الجاهز."""
        self.bot = bot

    async def __call__(
        self,
        telegram_id: int,
        text: str,
        media_file_id: str | None = None,
        media_type: str | None = None,
    ) -> int | None:
        """
        إرسال رسالة إذاعة واحدة.

        المخرجات: رقم الرسالة في تيليجرام عند النجاح.

        الاستثناءات: نفس استثناءات الإشعارات (محظور / مؤقت / نهائي) ليتعامل
        معها طابور الإذاعة بنفس المنطق المختبر.
        """
        body = html.escape(text or "")[:MAX_MESSAGE_LEN]
        try:
            if media_file_id and media_type == "photo":
                sent = await self.bot.send_photo(
                    chat_id=telegram_id,
                    photo=media_file_id,
                    caption=body[:1024] or None,
                    parse_mode=ParseMode.HTML,
                )
            elif media_file_id and media_type == "document":
                sent = await self.bot.send_document(
                    chat_id=telegram_id,
                    document=media_file_id,
                    caption=body[:1024] or None,
                    parse_mode=ParseMode.HTML,
                )
            else:
                sent = await self.bot.send_message(
                    chat_id=telegram_id,
                    text=body,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
        except Forbidden as exc:
            raise NotificationBlockedError(f"المستخدم {telegram_id} حظر البوت: {exc}") from exc
        except RetryAfter as exc:
            raise NotificationTemporaryError(
                f"تجاوز حد الإرسال، إعادة المحاولة بعد {exc.retry_after}ث"
            ) from exc
        except (TimedOut, NetworkError) as exc:
            raise NotificationTemporaryError(f"خطأ شبكة أثناء الإرسال: {exc}") from exc
        except BadRequest as exc:
            text_error = str(exc).lower()
            if "chat not found" in text_error or "user is deactivated" in text_error:
                raise NotificationBlockedError(f"محادثة غير متاحة: {exc}") from exc
            raise NotificationPermanentError(f"رسالة مرفوضة من تيليجرام: {exc}") from exc
        return sent.message_id

```

---

## `services/stats_service.py`

> مُحدَّث (مقتطف): StatsService._daily — تعبئة الأيام الخالية بصفر

```python
    async def _daily(self, period: Period) -> list[dict]:
        """
        تجميع الطلبات بأيام **محلية** مع ملء الأيام الخالية بأصفار (قرار المالك).

        الفترات محدودة (≤ 90 يوماً) فالملء آمن؛ وسقف 400 يوم حماية إضافية.
        """
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
        for day in self._days_in(period):
            days[day]        # defaultdict: يُنشئ صفراً لليوم الخالي
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
```

---

## `handlers/admin/stats.py`

> مُحدَّث (مقتطف): daily_screen

```python
@guarded
@admin_required(Permission.STATS_VIEW)
async def daily_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """سلسلة يومية بأيام محلية مع شريط اتجاه، والمجموع يشمل كل الأيام حتى المقطوعة من العرض."""
    await answer_callback(update)
    period = build_period(_period_key(update))
    series = await services_of(context).stats.daily_series(require_user(context), period=period)
    if not any(int(item["orders_count"]) for item in series):      # لا طلب في الفترة كلها
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
```

---

## `scripts/audit_ledger.py`

> جديد: التدقيق المالي للقراءة فقط

```python
"""
تدقيق مالي للقراءة فقط (المرحلة 12) — يطابق أرصدة المحافظ مع دفتر الحركات وحالة الطلبات والمدفوعات.

لماذا؟ الأرصدة تُعدَّل من خدمة واحدة فقط، لكن المشغّل يحتاج أداة مستقلة تثبت (أو تنفي) سلامة
البيانات بعد استعادة نسخة أو ترقية أو تعديل يدوي على القاعدة. هذه الأداة تُشغَّل في أي وقت
(حتى والبوت يعمل) ولا تكتب أي شيء: الاتصال في وضع `query_only`.

الفحوص:
    1. سلامة ملف SQLite (`PRAGMA integrity_check`) والمفاتيح الأجنبية.
    2. رصيد كل مستخدم = مجموع حركاته (دائن − مدين)، ولا رصيد سالب.
    3. سلسلة الحركات: رصيد «قبل» كل حركة = رصيد «بعد» السابقة، والحساب الحسابي صحيح.
    4. لكل طلب حركة خصم واحدة بالضبط بقيمة التكلفة.
    5. مجموع استرجاعات الطلب = `orders.refund_amount_units` ولا يتجاوز التكلفة.
    6. اتساق الحالة النهائية مع الاسترجاع (مكتمل بلا استرجاع، مُسترجَع بالكامل).
    7. تاريخ حالات الطلب سلسلة متصلة وآخر سجل فيه = حالته الحالية.
    8. كل دفعة معتمدة لها إيداع واحد بقيمة `credited_units`، ولا إيداع لدفعة غير معتمدة.
    9. طلبات عالقة في `submitting` أكثر من 10 دقائق (تنبيه، لا خطأ مالي).

طريقة التشغيل (من مجلد المشروع):
    python -m scripts.audit_ledger               # يقرأ DATABASE_PATH من .env
    python -m scripts.audit_ledger --db path.db  # أو نسخة/قاعدة محددة (مثلاً نسخة مستعادة للمعاينة)
    python -m scripts.audit_ledger --limit 50    # عدد الأمثلة المعروضة لكل فحص (الافتراضي 10)

كود الخروج: 0 سليم (قد توجد تنبيهات) · 1 اكتُشف خلل مالي/بنيوي · 2 تعذّر فتح القاعدة.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:                      # تشغيل مباشر بلا تثبيت الحزمة
    sys.path.insert(0, str(ROOT))

from config import Config, ConfigError                      # noqa: E402
from core.constants import APP_VERSION                       # noqa: E402
from core.money import MONEY_SCALE                           # noqa: E402

STUCK_SUBMITTING_MINUTES = 10                  # بعد هذه المدة يُعدّ الطلب في `submitting` عالقاً


@dataclass
class Finding:
    """نتيجة فحص واحد: عنوانه، شدته، عدد المخالفات، وأمثلة منها."""

    title: str                                  # اسم الفحص بالعربية
    severity: str                               # "bad" خلل · "warn" تنبيه
    count: int = 0                              # عدد المخالفات الكلي
    samples: list[str] = field(default_factory=list)   # أمثلة (سقف --limit)


def _units(value: int) -> str:
    """تنسيق وحدات مالية صحيحة كمبلغ مقروء (بلا حسابات عائمة)."""
    sign = "-" if value < 0 else ""
    whole, frac = divmod(abs(int(value)), MONEY_SCALE)
    return f"{sign}{whole}.{frac:04d}".rstrip("0").rstrip(".") or "0"


def _scan(conn: sqlite3.Connection, title: str, severity: str, sql: str, fmt, limit: int, params=()) -> Finding:
    """تنفيذ استعلام يعيد صفوف المخالفات فقط، وتحويله إلى `Finding` بأمثلة مقروءة."""
    rows = conn.execute(sql, params).fetchall()
    return Finding(title, severity, len(rows), [fmt(row) for row in rows[:limit]])


def audit(conn: sqlite3.Connection, *, limit: int = 10, now: datetime | None = None) -> list[Finding]:
    """
    تشغيل كل الفحوص على اتصال للقراءة فقط وإرجاع نتائجها بالترتيب.

    المدخلات: اتصال sqlite3 · limit عدد الأمثلة لكل فحص · now للاختبار.
    المخرجات: قائمة `Finding` (count=0 تعني أن الفحص سليم).
    """
    conn.row_factory = sqlite3.Row
    out: list[Finding] = []

    integrity = [row[0] for row in conn.execute("PRAGMA integrity_check").fetchall()]
    bad_integrity = [] if integrity == ["ok"] else integrity
    out.append(Finding("سلامة ملف القاعدة (integrity_check)", "bad", len(bad_integrity), bad_integrity[:limit]))
    out.append(_scan(conn, "انتهاكات المفاتيح الأجنبية", "bad", "PRAGMA foreign_key_check",
                     lambda r: f"جدول {r[0]} صف {r[1]} ⇒ {r[2]}", limit))

    out.append(_scan(
        conn, "رصيد المحفظة لا يساوي مجموع الحركات", "bad",
        """
        SELECT u.id, u.telegram_id, u.balance_units AS stored,
               COALESCE((SELECT SUM(CASE WHEN t.direction = 'credit' THEN t.amount_units ELSE -t.amount_units END)
                           FROM transactions t WHERE t.user_id = u.id), 0) AS ledger
          FROM users u
         WHERE u.balance_units <> ledger
         ORDER BY u.id
        """,
        lambda r: f"مستخدم #{r['id']} (tg {r['telegram_id']}): مخزَّن {_units(r['stored'])} ≠ دفتر {_units(r['ledger'])}",
        limit,
    ))
    out.append(_scan(conn, "رصيد سالب", "bad", "SELECT id, balance_units FROM users WHERE balance_units < 0",
                     lambda r: f"مستخدم #{r['id']}: {_units(r['balance_units'])}", limit))

    out.append(_scan(
        conn, "انقطاع سلسلة الحركات أو خطأ حسابي فيها", "bad",
        """
        SELECT id, user_id, balance_before_units AS before, balance_after_units AS after, direction, amount_units,
               prev_after
          FROM (SELECT t.*, LAG(balance_after_units, 1, 0) OVER (PARTITION BY user_id ORDER BY id) AS prev_after
                  FROM transactions t)
         WHERE before <> prev_after
            OR after <> before + CASE WHEN direction = 'credit' THEN amount_units ELSE -amount_units END
         ORDER BY id
        """,
        lambda r: (f"حركة #{r['id']} (مستخدم #{r['user_id']}): قبل {_units(r['before'])} "
                   f"/ السابقة {_units(r['prev_after'])} / بعد {_units(r['after'])}"),
        limit,
    ))

    out.append(_scan(
        conn, "طلب بلا حركة خصم واحدة بقيمة التكلفة", "bad",
        """
        SELECT o.id, o.cost_units, COUNT(t.id) AS n, COALESCE(SUM(t.amount_units), 0) AS total
          FROM orders o
          LEFT JOIN transactions t ON t.order_id = o.id AND t.type = 'order' AND t.direction = 'debit'
         GROUP BY o.id
        HAVING n <> 1 OR total <> o.cost_units
         ORDER BY o.id
        """,
        lambda r: f"طلب #{r['id']}: التكلفة {_units(r['cost_units'])} · حركات الخصم {r['n']} بمجموع {_units(r['total'])}",
        limit,
    ))
    out.append(_scan(
        conn, "مجموع الاسترجاعات لا يطابق حقل الاسترجاع في الطلب (أو يتجاوز التكلفة)", "bad",
        """
        SELECT o.id, o.cost_units, o.refund_amount_units AS stored, COALESCE(SUM(t.amount_units), 0) AS ledger
          FROM orders o
          LEFT JOIN transactions t ON t.order_id = o.id AND t.type IN ('refund', 'partial_refund')
                                  AND t.direction = 'credit'
         GROUP BY o.id
        HAVING stored <> ledger OR ledger > o.cost_units
         ORDER BY o.id
        """,
        lambda r: f"طلب #{r['id']}: مخزَّن {_units(r['stored'])} · دفتر {_units(r['ledger'])} · تكلفة {_units(r['cost_units'])}",
        limit,
    ))
    out.append(_scan(
        conn, "حالة نهائية لا تتسق مع الاسترجاع", "bad",
        """
        SELECT id, status, cost_units, refund_amount_units AS refund FROM orders
         WHERE (status = 'completed' AND refund <> 0)
            OR (status IN ('refunded', 'canceled') AND refund <> cost_units)
            OR (status = 'partial' AND refund >= cost_units)
            OR (status IN ('pending', 'submitting', 'submit_uncertain', 'submitted', 'in_progress') AND refund <> 0)
         ORDER BY id
        """,
        lambda r: f"طلب #{r['id']} [{r['status']}]: تكلفة {_units(r['cost_units'])} · مُسترجَع {_units(r['refund'])}",
        limit,
    ))
    out.append(_scan(
        conn, "آخر سجل في تاريخ الحالات لا يساوي حالة الطلب", "bad",
        """
        SELECT o.id, o.status, h.to_status
          FROM orders o
          JOIN order_status_history h ON h.id = (SELECT MAX(id) FROM order_status_history WHERE order_id = o.id)
         WHERE h.to_status <> o.status
         ORDER BY o.id
        """,
        lambda r: f"طلب #{r['id']}: الحالة {r['status']} ≠ آخر سجل {r['to_status']}",
        limit,
    ))

    out.append(_scan(
        conn, "انقطاع في سلسلة تاريخ حالات الطلب", "bad",
        """
        SELECT order_id, id, from_status, prev_to
          FROM (SELECT h.*, LAG(to_status) OVER (PARTITION BY order_id ORDER BY id) AS prev_to
                  FROM order_status_history h)
         WHERE COALESCE(from_status, '') <> COALESCE(prev_to, '')
         ORDER BY id
        """,
        lambda r: f"طلب #{r['order_id']} سجل #{r['id']}: من «{r['from_status']}» لكن السابق انتهى «{r['prev_to']}»",
        limit,
    ))

    out.append(_scan(
        conn, "دفعة معتمدة بلا إيداع واحد مطابق، أو إيداع لدفعة غير معتمدة", "bad",
        """
        SELECT p.id, p.status, p.credited_units AS credited, COUNT(t.id) AS n, COALESCE(SUM(t.amount_units), 0) AS total
          FROM payments p
          LEFT JOIN transactions t ON t.payment_id = p.id AND t.type = 'deposit'
         GROUP BY p.id
        HAVING (p.status = 'approved' AND (n <> 1 OR p.credited_units IS NULL OR total <> p.credited_units))
            OR (p.status <> 'approved' AND n > 0)
         ORDER BY p.id
        """,
        lambda r: f"دفعة #{r['id']} [{r['status']}]: المعتمد {_units(r['credited'] or 0)} · إيداعات {r['n']} بمجموع {_units(r['total'])}",
        limit,
    ))

    reference = now or datetime.now(timezone.utc)
    cutoff = (reference - timedelta(minutes=STUCK_SUBMITTING_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    out.append(_scan(
        conn, f"طلبات عالقة في «submitting» أكثر من {STUCK_SUBMITTING_MINUTES} دقائق", "warn",
        "SELECT id, updated_at FROM orders WHERE status = 'submitting' AND replace(substr(updated_at, 1, 19), 'T', ' ') < ? ORDER BY id",
        lambda r: f"طلب #{r['id']} منذ {r['updated_at']}",
        limit, (cutoff,),
    ))
    return out


def open_readonly(path: Path) -> sqlite3.Connection:
    """فتح القاعدة بوضع `query_only` (يرفض أي كتابة حتى لو وُجد خطأ في الأداة نفسها)."""
    if not path.exists():
        raise FileNotFoundError(f"ملف القاعدة غير موجود: {path}")
    conn = sqlite3.connect(str(path), timeout=10)
    conn.execute("PRAGMA query_only = ON")
    return conn


def render(findings: list[Finding], path: Path) -> str:
    """تنسيق التقرير النصي النهائي مع الملخص."""
    lines = [f"🧮 تدقيق مالي — SMM Bot {APP_VERSION}", f"القاعدة: {path}", "─" * 44]
    for item in findings:
        if item.count == 0:
            lines.append(f"  ✅ {item.title}")
            continue
        mark = "⛔" if item.severity == "bad" else "⚠️ "
        lines.append(f"  {mark} {item.title}: {item.count}")
        lines.extend(f"       • {sample}" for sample in item.samples)
        if item.count > len(item.samples):
            lines.append(f"       … و{item.count - len(item.samples)} أخرى (زد --limit لعرضها)")
    bad = sum(1 for f in findings if f.count and f.severity == "bad")
    warn = sum(1 for f in findings if f.count and f.severity == "warn")
    lines += ["─" * 44, f"النتيجة: {bad} فحص فاشل · {warn} تنبيه · {len(findings) - bad - warn} سليم"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """نقطة الدخول: قراءة الوسائط، تشغيل التدقيق، طباعة التقرير، وإرجاع رمز الخروج."""
    parser = argparse.ArgumentParser(description="تدقيق مالي للقراءة فقط")
    parser.add_argument("--db", type=Path, help="مسار قاعدة بيانات محددة (الافتراضي DATABASE_PATH)")
    parser.add_argument("--limit", type=int, default=10, help="عدد الأمثلة لكل فحص")
    args = parser.parse_args(argv)

    path = args.db
    if path is None:
        try:
            path = Config.load().database_path
        except ConfigError as exc:
            print(f"⛔ خطأ في الإعدادات: {exc}", file=sys.stderr)
            return 2
    try:
        conn = open_readonly(path)
    except (FileNotFoundError, sqlite3.Error) as exc:
        print(f"⛔ تعذّر فتح القاعدة: {exc}", file=sys.stderr)
        return 2
    try:
        findings = audit(conn, limit=max(1, args.limit))
    except sqlite3.Error as exc:
        print(f"⛔ فشل التدقيق (هل نُفّذت الترحيلات؟ شغّل init_db): {exc}", file=sys.stderr)
        return 2
    finally:
        conn.close()
    print(render(findings, path))
    return 1 if any(f.count and f.severity == "bad" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())

```

---

## `scripts/gen_reference_docs.py`

> جديد: مولّد SETTINGS.md وPERMISSIONS.md

```python
"""
توليد المراجع الآلية للمشغّل من مصدر الحقيقة (الكود + ترحيلات القاعدة).

الاستخدام (من مجلد المشروع):
    python -m scripts.gen_reference_docs           # يكتب docs/SETTINGS.md و docs/PERMISSIONS.md
    python -m scripts.gen_reference_docs --check   # يفشل (رمز 1) إن كان أي ملف قديماً عن الكود

لماذا؟ جداول الإعدادات والصلاحيات تتغير عبر المراحل؛ كتابتها يدوياً تعني توثيقاً كاذباً مع الوقت.
اختبار `test_release_phase12` يستدعي نفس الدالة ويفشل لو تخلّف التوثيق عن الكود.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

from config import BASE_DIR
from core.permissions import PERMISSIONS, ROLE_DEFAULTS, ROLES
from core.setting_rules import GENERIC_MONEY_MAX, SETTING_RULES
from database.database import Database
from database.migrator import Migrator

DOCS_DIR = BASE_DIR / "docs"
TYPE_AR = {"str": "نص", "int": "عدد صحيح", "bool": "نعم/لا", "json": "JSON", "money": "مبلغ (وحدات صحيحة)"}
GROUP_AR = {
    "general": "عامة", "orders": "الطلبات", "payments": "الشحن", "notifications": "الإشعارات",
    "security": "الأمان", "providers": "المزودون", "tickets": "الدعم الفني", "backup": "النسخ الاحتياطي",
    "reports": "التقارير", "stats": "الإحصائيات", "users": "المستخدمون", "catalog": "الكتالوج",
    "system": "النظام", "broadcast": "الإذاعة", "jobs": "المهام",
}


def _cell(value: object, limit: int = 70) -> str:
    """نص صالح لخلية جدول Markdown (بلا أسطر جديدة أو `|`) مع اقتطاف الطويل."""
    text = " ".join(str(value if value is not None else "").split()).replace("|", "¦")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _range_text(key: str, value_type: str) -> str:
    """وصف النطاق المسموح لإعداد من قواعد `SETTING_RULES`."""
    rule = SETTING_RULES.get(key)
    if rule is None:
        return "ضمن الحدود العامة"
    parts: list[str] = []
    if rule.minimum is not None or rule.maximum is not None:
        high = "∞" if rule.maximum is None or rule.maximum >= GENERIC_MONEY_MAX else f"{rule.maximum:,}"
        parts.append(f"{(rule.minimum if rule.minimum is not None else 0):,} … {high}")
    if rule.max_length:
        parts.append(f"حتى {rule.max_length} حرفاً")
    if rule.hint:
        parts.append(rule.hint)
    if rule.allow_empty:
        parts.append("يقبل الفراغ")
    if rule.decimal:
        parts.append("عدد عشري موجب")
    return "؛ ".join(parts) or ("نعم/لا" if value_type == "bool" else "—")


async def _settings_rows() -> list[dict]:
    """الإعدادات المزروعة فعلاً بعد تطبيق كل الترحيلات على قاعدة مؤقتة."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "reference.db")
        await db.connect()
        try:
            await Migrator(db).apply_all()
            rows = await db.fetchall(
                "SELECT key, value, value_type, group_code, name_ar, description_ar, is_editable "
                "FROM settings ORDER BY group_code, key"
            )
            return [dict(row) for row in rows]
        finally:
            await db.close()


def render_settings(rows: list[dict]) -> str:
    """نص `SETTINGS.md`: كل إعداد مع قيمته الافتراضية ونطاقه المسموح."""
    lines = [
        "# مرجع الإعدادات",
        "",
        "> **مولَّد آلياً** بالأمر `python -m scripts.gen_reference_docs` من ترحيلات القاعدة وقواعد "
        "`core/setting_rules.py` — لا تعدّله يدوياً (اختبار الإصدار يفشل إن تخلّف عن الكود).",
        "",
        f"عدد الإعدادات: **{len(rows)}** — تُعدَّل من البوت: «⚙️ الإعدادات»، وكل قيمة تُفحص قبل الحفظ "
        "بمصدر واحد (`SettingsService.set`) وتُدقَّق التغييرات.",
    ]
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["group_code"], []).append(row)
    for group, items in groups.items():
        lines += ["", f"## {GROUP_AR.get(group, group)} (`{group}`)", "",
                  "| المفتاح | الاسم | النوع | الافتراضي | النطاق المسموح | قابل للتعديل |",
                  "|---|---|---|---|---|---|"]
        for row in items:
            lines.append(
                f"| `{row['key']}` | {_cell(row['name_ar'], 40)} | {TYPE_AR.get(row['value_type'], row['value_type'])} "
                f"| `{_cell(row['value'], 40)}` | {_cell(_range_text(row['key'], row['value_type']), 80)} "
                f"| {'نعم' if row['is_editable'] else 'لا'} |"
            )
    return "\n".join(lines) + "\n"


def render_permissions() -> str:
    """نص `PERMISSIONS.md`: كتالوج الصلاحيات ومن يملكها افتراضياً (قابلة للتغيير من قاعدة البيانات)."""
    names = {role.code: role.name_ar for role in ROLES}
    columns = ["support", "admin", "super_admin"]
    lines = [
        "# مرجع الأدوار والصلاحيات",
        "",
        "> **مولَّد آلياً** بالأمر `python -m scripts.gen_reference_docs` من `core/permissions.py`. "
        "هذه **القيم الافتراضية** المزروعة عند التهيئة؛ الصلاحيات الفعلية تُقرأ من جداول "
        "`role_permissions` و`user_permissions` في قاعدة البيانات (لا أدمن ثابت في الكود). "
        "⚠️ = صلاحية خطِرة: منحها فردياً لغير الأدمن الأعلى محجوب، ويرصد «فحص الأمان» أي استثناء ممنوح لها.",
        "",
        f"عدد الصلاحيات: **{len(PERMISSIONS)}** (منها خطِرة: **{sum(p.is_dangerous for p in PERMISSIONS)}**).",
        "",
        "| الصلاحية | الوصف | المجموعة | " + " | ".join(names[c] for c in columns) + " |",
        "|---|---|---|" + "|".join("---" for _ in columns) + "|",
    ]
    for perm in PERMISSIONS:
        marks = ["✅" if perm.code in ROLE_DEFAULTS.get(c, ()) else "—" for c in columns]
        flag = " ⚠️" if perm.is_dangerous else ""
        lines.append(f"| `{perm.code}`{flag} | {_cell(perm.name_ar, 60)} | {perm.group_code} | " + " | ".join(marks) + " |")
    lines += ["", "المستخدم العادي (`user`) بلا أي صلاحية إدارية. أول أدمن أعلى يُزرع من `SUPER_ADMIN_IDS`، "
              "وتغيير دور مستخدم يتم من شاشته في «👥 المستخدمون» (🎚 تغيير الدور) أو بـ`python -m scripts.create_admin`. "
              "الاستثناءات الفردية (منح/منع صلاحية لشخص) تدعمها `AuthService.set_user_permission` لكن **لا شاشة لها في البوت** بعد."]
    return "\n".join(lines) + "\n"


def render_all() -> dict[Path, str]:
    """كل الملفات المولَّدة: مسارها ⇒ نصها الحالي المتوقَّع."""
    rows = asyncio.run(_settings_rows())
    return {DOCS_DIR / "SETTINGS.md": render_settings(rows), DOCS_DIR / "PERMISSIONS.md": render_permissions()}


def main(argv: list[str] | None = None) -> int:
    """كتابة المراجع أو التحقق من حداثتها (`--check`). رمز الخروج 1 إن كانت قديمة."""
    parser = argparse.ArgumentParser(description="توليد مراجع الإعدادات والصلاحيات")
    parser.add_argument("--check", action="store_true", help="تحقق فقط دون كتابة")
    args = parser.parse_args(argv)
    stale = 0
    for path, text in render_all().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if args.check:
            if current != text:
                print(f"❌ قديم: {path.relative_to(BASE_DIR)} — شغّل: python -m scripts.gen_reference_docs")
                stale = 1
            else:
                print(f"✅ حديث: {path.relative_to(BASE_DIR)}")
        else:
            path.write_text(text, encoding="utf-8")
            print(f"✍️  كُتب {path.relative_to(BASE_DIR)}")
    return stale


if __name__ == "__main__":
    sys.exit(main())

```

---

## `README.md`

> جديد

`````markdown
# SMM Bot — بوت تيليجرام لإدارة وبيع خدمات SMM

نظام متكامل (عميل + لوحة أدمن داخل تيليجرام) لبيع خدمات التسويق عبر وسائل التواصل: كتالوج، محفظة، شحن بإثبات واعتماد
يدوي، طلبات تُرسَل للمزوِّد وتُتابَع آلياً حتى النهاية، استرجاع آمن عند الفشل، دعم فني بالتذاكر، إشعارات، إذاعة،
إحصائيات، سجلات تدقيق، صلاحيات، نسخ احتياطي. **الواجهة عربية بالكامل.**

> الإصدار: **1.0.0** · Python **3.11+** (مُختبَر على 3.13) · `python-telegram-bot 21.9` · SQLite (WAL) · `asyncio` + `JobQueue`

---

## 1) ما الذي يعمله النظام (الدورة الكاملة)

```
تسجيل ← تصفح الكتالوج ← طلب ← (شحن ← اعتماد الأدمن) ← خصم من المحفظة ← إرسال للمزوِّد ← متابعة آلية
      ← إكمال ← إشعار العميل ← سجل التدقيق ← إحصائيات
فشل المزوِّد: فشل ← استرجاع آمن (حركة مالية مرجعها فريد) ← إشعار العميل والأدمن
```

| المجال | أبرز ما فيه |
|---|---|
| العميل | `/start`، تصفح التصنيفات/الخدمات، طلب بالتحقق من الرابط والكمية، شحن بإثبات، سجل طلبات ومعاملات، تذاكر دعم، إلغاء قبل الإرسال |
| الأدمن | 14 قسماً في «🛠 لوحة التحكم»: المستخدمون · المدفوعات (🏦 طرق الشحن) · الطلبات · الدعم · الكتالوج · الإعدادات · السجلات · صحة النظام · المزودون · الإذاعة · قوالب الإشعارات · الأمان · النسخ الاحتياطي · الإحصائيات |
| المال | وحدات صحيحة (1 = 0.0001) لا أعداد عائمة · خدمة محفظة واحدة تُغيّر الرصيد · دفتر حركات بمرجع فريد · لا استرجاع بلا حركة |
| الطلبات | آلة حالات صارمة · لا تغيير حالة بلا تحقق من السابقة · لا إرسال مزدوج عند إعادة المحاولة · مسار `submit_uncertain` للإرسال غير المؤكد |
| المزودون | عميل Perfect Panel (v2) · مفاتيح مشفّرة (Fernet) لا تظهر كاملة أبداً · حماية SSRF · تعطيل مؤقت تلقائي للمزوِّد عند تكرار الفشل |
| الأمان | صلاحيات من قاعدة البيانات (47 صلاحية، 3 أدوار) · تقييد معدل · تنقية الأسرار من السجلات · صلاحيات ملفات 0600 |
| التشغيل | 12 مهمة دورية · نسخ احتياطي تلقائي + قناة خارجية اختيارية · استعادة من سطر الأوامر · صيانة يومية للقاعدة |

## 2) التثبيت السريع

```bash
git clone <مستودعك> smm_bot && cd smm_bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env && chmod 600 .env
python -m scripts.init_db --gen-key          # يطبع مفتاح تشفير جديداً ⇒ ضعه في ENCRYPTION_KEY داخل .env
nano .env                                    # BOT_TOKEN و SUPER_ADMIN_IDS و ENCRYPTION_KEY

python -m scripts.init_db                    # إنشاء القاعدة + الصلاحيات + الإعدادات الافتراضية
python -m scripts.create_admin <telegram_id> super_admin
python -m scripts.security_check --fix       # فحص أمني دون اتصال
python -m scripts.boot_check                 # فحص الإقلاع دون تيليجرام
python main.py                               # تشغيل البوت
```

> **احفظ `ENCRYPTION_KEY` في مكان منفصل وآمن** (مدير كلمات مرور). بدونه تتعذّر قراءة مفاتيح المزودين المخزّنة،
> ولا يوجد في النسخ الاحتياطية عمداً. التفاصيل والتشغيل كخدمة (systemd) في [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

## 3) الإعداد (`.env`)

| المتغير | مطلوب | الوصف |
|---|---|---|
| `BOT_TOKEN` | للتشغيل | توكن @BotFather (لا يُطبع ولا يُسجَّل) |
| `SUPER_ADMIN_IDS` | نعم | معرّفات الأدمن الأعلى (أشخاص، مفصولة بفواصل) — للزرع الأول والطوارئ |
| `ENCRYPTION_KEY` | نعم | مفتاح Fernet لتشفير مفاتيح المزودين |
| `DATABASE_PATH` | لا | الافتراضي `data/smm_bot.db` |
| `LOG_LEVEL` / `LOG_FILE` | لا | الافتراضي `INFO` / `logs/bot.log` (دوّار، 5MB × 5) |
| `BACKUP_DIR` | لا | الافتراضي `backups` |
| `TIMEZONE` | لا | للعرض فقط (`Asia/Aden`)، التخزين UTC |
| `ADMIN_ALERT_CHAT_ID` | لا | محادثة/قناة خاصة لتنبيهات النظام |
| `BACKUP_CHANNEL_ID` | لا | **قناة خاصة** لنسخ احتياطية خارج السيرفر (انظر التحذير أدناه) |

بقية الإعدادات (64 إعداداً: حدود، مهل، رسوم، إشعارات…) تُدار من داخل البوت «⚙️ الإعدادات» وتُوثَّق في
[`docs/SETTINGS.md`](docs/SETTINGS.md).

## 4) أوامر وأدوات

أوامر البوت: `/start` · `/help` · `/cancel` · `/id`.

| الأداة | الغرض |
|---|---|
| `python -m scripts.init_db [--gen-key \| --status]` | إنشاء/ترقية القاعدة، توليد مفتاح، عرض الحالة |
| `python -m scripts.create_admin <id> [role] [--force]` | إنشاء أول أدمن أو تعيين دور (`support` · `admin` · `super_admin`) |
| `python -m scripts.security_check [--fix]` | فحص أمني للأسرار والملفات والإعدادات |
| `python -m scripts.boot_check` | فحص الإقلاع: ملفات، قاعدة، خدمات، معالجات، أزرار، مهام |
| `python -m scripts.audit_ledger [--db FILE]` | **تدقيق مالي للقراءة فقط**: الأرصدة × الدفتر × الطلبات × الدفعات |
| `python -m scripts.restore_backup (--list \| --latest \| --id N \| --file F) [--yes]` | استعادة نسخة (والبوت متوقف) |
| `python -m scripts.demo_cycle [--keep]` | تشغيل الدورة الكاملة + مسار الفشل على قاعدة مؤقتة ومزوِّد وهمي |
| `python -m scripts.gen_reference_docs [--check]` | توليد `docs/SETTINGS.md` و`docs/PERMISSIONS.md` من الكود |

## 5) الاختبار

```bash
pip install -r requirements-dev.txt
python -m pytest                      # الحزمة الكاملة (وحدة + تكامل + e2e)
python -m scripts.demo_cycle          # الدورة الكاملة على مزوِّد وهمي
```

الحزمة تتضمن اختبارات وحدة وتكامل واختبار «dispatcher» حقيقياً يمرّ بكل أزرار لوحة الأدمن، واختباراً عشوائياً
موجَّهاً (fuzz) للثوابت المحاسبية، واختبارات تزامن، واختبار انحراف الوثائق (الوثائق المولَّدة يجب أن تطابق الكود).

## 6) هيكل المشروع

```
main.py            نقطة التشغيل (يبني التطبيق، يسجّل المعالجات والمهام، يمنع نسختين)
config.py          قراءة .env والتحقق منه
core/              ثوابت، تعدادات، آلة حالات الطلب/الدفع، الصلاحيات، قواعد الإعدادات، المال
database/          الاتصال، migrations (0001…0009)، النماذج، المستودعات (Repositories)
services/          منطق الأعمال (16 خدمة) — الوحيد الذي يُغيّر الرصيد: wallet_service
handlers/          معالجات العميل والأدمن (ConversationHandler) + registry
keyboards/ texts/  لوحات الأزرار والنصوص العربية
middlewares/       سياق التحديث (تسجيل المستخدم، الحظر، الصيانة، الصلاحيات) + تقييد المعدل
integrations/      عملاء المزودين (Perfect Panel) + مزوِّد وهمي للاختبار
jobs/              المهام الدورية (الإرسال، المتابعة، النسخ، الصيانة، الإذاعة…)
scripts/           أدوات سطر الأوامر
docs/              تصميم المرحلة 0، تقارير المراحل، SETTINGS, PERMISSIONS, RUNBOOK
tests/             unit · integration · e2e
```

## 7) تحذيرات أمنية مهمة

- **قناة النسخ الاحتياطي يجب أن تكون خاصة وبأعضاء موثوقين فقط.** النسخة المرسلة إليها **غير مشفّرة** (قرار المالك):
  تحوي بيانات العملاء (معرّفات، أرصدة، طلبات، حوالات). مفاتيح المزودين فيها مشفّرة بـ`ENCRYPTION_KEY` الذي لا يُرسَل.
  إن لم تُرد ذلك فعطّل الإعداد `backup_send_to_channel`.
- لا ترفع `.env` ولا مجلدات `data/` و`backups/` و`logs/` إلى Git.
- التوكن لا يُطبع في اللوق ولا في رسائل فشل الإقلاع. إن اشتبهت بتسرّبه فاستبدله من @BotFather فوراً.

## 8) القيود المعروفة (صراحةً)

- **لم يُجرَّب التشغيل مع توكن بوت حقيقي ولا مع مزوِّد حقيقي** في بيئة التطوير؛ جُرِّب الإقلاع على تثبيت نظيف حتى
  رفض تيليجرام التوكن الوهمي، وكل منطق المزوِّد مُختبَر على مزوِّد وهمي ومحاكاة بروتوكول Perfect Panel. اجعل أول
  تشغيل على مزوِّد حقيقي بمبلغ صغير وراقب «🔌 استدعاءات المزودين».
- نموذج systemd في الـRUNBOOK **غير مُجرَّب** على سيرفر حقيقي.
- عملية واحدة فقط (قفل `bot.lock`) — لا تشغيل متعدد النسخ/السيرفرات على نفس القاعدة.
- **لا شاشة في البوت لاستثناءات الصلاحيات الفردية** (الخدمة موجودة: `AuthService.set_user_permission`)؛ المتاح تغيير
  الدور من «🎚 تغيير الدور»، أو التعديل المباشر على جدول الاستثناءات.
- لا 2FA للأدمن · الحظر المؤقت (تقييد المعدل) يضيع عند إعادة التشغيل · لا failover بين مزوّدين · الملخص اليومي أرقام فقط.
- `admin_cancel` على طلب `submitted` يسترجع الرصيد رغم أن المزوِّد قد يكون بدأ التنفيذ (قرار المالك).
- الحماية من DNS rebinding في روابط المزودين جزئية (فحص عند الحفظ وعند الاتصال، لا تثبيت IP).
- مشاكل SQLite: كاتب واحد في كل لحظة؛ مناسب لآلاف الطلبات يومياً، وللأحمال الأكبر يلزم الانتقال لـPostgreSQL
  (الطبقة مفصولة عبر Repositories لكن الانتقال غير منفَّذ).

## 9) الوثائق

| الملف | المحتوى |
|---|---|
| [`docs/RUNBOOK.md`](docs/RUNBOOK.md) | التشغيل اليومي، systemd، النسخ والاستعادة، استكشاف الأخطاء، الترقية |
| [`docs/SETTINGS.md`](docs/SETTINGS.md) | كل الإعدادات: الافتراضي والنطاق (مولَّد) |
| [`docs/PERMISSIONS.md`](docs/PERMISSIONS.md) | الصلاحيات ومصفوفة الأدوار (مولَّد) |
| [`docs/PHASE0_DESIGN.md`](docs/PHASE0_DESIGN.md) | التصميم الأصلي: المعمارية، ERD، التدفقات، المخاطر |
| `docs/PHASE{1..12}_REPORT.md` | تقرير كل مرحلة (ما نُفّذ وما اختُبر والقيود) |

`````

---

## `docs/RUNBOOK.md`

> جديد

`````markdown
# دليل التشغيل (RUNBOOK) — SMM Bot 1.0.0

موجَّه لمن يشغّل البوت يومياً. كل الأوامر من مجلد المشروع وبالبيئة الافتراضية مفعّلة (`source .venv/bin/activate`).

---

## 1) التثبيت على سيرفر لينكس

### 1.1 المتطلبات
Python 3.11+ · صلاحية كتابة على مجلد المشروع · وصول صادر إلى `api.telegram.org:443` وإلى لوحة المزوِّد (https/443).
لا حاجة لقاعدة بيانات خارجية ولا Docker (غير مُجهَّز في هذا الإصدار).

### 1.2 خطوات التثبيت (جُرِّبت على تثبيت نظيف)
```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin smmbot      # مستخدم مخصّص (موصى به)
sudo -u smmbot -H bash -c '
  cd ~ && git clone <مستودعك> smm_bot && cd smm_bot
  python3 -m venv .venv && . .venv/bin/activate
  pip install -r requirements.txt
  cp .env.example .env && chmod 600 .env
  python -m scripts.init_db --gen-key        # انسخ المفتاح الناتج إلى ENCRYPTION_KEY
'
sudo -u smmbot nano /home/smmbot/smm_bot/.env      # BOT_TOKEN, SUPER_ADMIN_IDS, ENCRYPTION_KEY
sudo -u smmbot -H bash -c 'cd ~/smm_bot && . .venv/bin/activate &&
  python -m scripts.init_db &&
  python -m scripts.create_admin <telegram_id> super_admin &&
  python -m scripts.security_check --fix &&
  python -m scripts.boot_check'
```
النتيجة المتوقعة لتثبيت جديد: `init_db` ⇒ 29 جدولاً و47 صلاحية و64 إعداداً · `security_check` ⇒ 0 «خطر» (وقد تظهر
تنبيهات: لا قناة تنبيهات، أدمن أعلى واحد، لا نسخة بعد) · `boot_check` ⇒ تحذير «لا طريقة شحن مفعّلة» حتى تُنشئها.

**احفظ نسخة من `ENCRYPTION_KEY` خارج السيرفر.** فقدانه يعني تعذّر قراءة مفاتيح المزودين (الحل: إعادة إدخالها بـ«🔑 تغيير المفتاح»).

### 1.3 التشغيل كخدمة (systemd) — ⚠️ نموذج غير مُجرَّب على سيرفر حقيقي
`/etc/systemd/system/smmbot.service`:
```ini
[Unit]
Description=SMM Telegram Bot
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
User=smmbot
WorkingDirectory=/home/smmbot/smm_bot
ExecStart=/home/smmbot/smm_bot/.venv/bin/python main.py
Restart=on-failure
RestartSec=15
# رمز 2 = نسخة أخرى تعمل بالفعل (لا فائدة من إعادة المحاولة)
RestartPreventExitStatus=2
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload && sudo systemctl enable --now smmbot
journalctl -u smmbot -f            # المتابعة الحيّة       |   tail -f logs/bot.log
sudo systemctl restart smmbot      # إعادة التشغيل (آمنة: الحالة كلها في القاعدة)
```
**رموز الخروج:** `0` إيقاف سليم · `1` خطأ إعداد/توكن مرفوض/شبكة عند الإقلاع/انهيار · `2` نسخة أخرى تعمل.
رسائل الفشل عربية ولا تحوي التوكن.

### 1.4 قائمة «أول تشغيل حقيقي» (لأن النظام لم يُجرَّب بتوكن/مزوِّد حقيقيين)
1. شغّل `python main.py`، أرسل `/start` من حساب الأدمن الأعلى ⇒ يظهر الزر «🛠 لوحة التحكم».
2. «🏦 طرق الشحن» ← أنشئ طريقة شحن وفعّلها (بدونها لا يستطيع العملاء الشحن).
3. «🔌 المزودون» ← «➕ مزود جديد» ← «🔍 اختبار الاتصال» ← «💵 تحديث الرصيد» ← «🔄 مزامنة الخدمات».
4. «🛍 الكتالوج» ← فعّل خدمة واحدة بسعر مناسب.
5. من حساب عميل تجريبي: اشحن مبلغاً صغيراً ← اعتمده ← اطلب أقل كمية ← راقب «📦 الطلبات» و«🔌 استدعاءات المزودين»
   (في «📝 السجلات») حتى يكتمل.
6. اضبط `admin_alert_chat_id` (قناة تنبيهات خاصة) وجرّب «🆕 نسخة الآن» من «💾 النسخ الاحتياطي».
7. شغّل `python -m scripts.audit_ledger` — يجب أن تكون النتيجة «0 فحص فاشل».

---

## 2) المهام الدورية (تعمل داخل نفس العملية)

| المهمة | الغرض |
|---|---|
| `notifications_dispatch` | إرسال الإشعارات المعلّقة (مع إعادة المحاولة وتعليم من حظر البوت) |
| `broadcast_dispatch` | إرسال الإذاعات على دفعات مع إيقاف/استئناف |
| `orders_submit` | إرسال الطلبات `pending` للمزوِّد (مرة واحدة لكل طلب) |
| `orders_check` | متابعة الطلبات المُرسَلة حتى النهاية (إكمال/جزئي/فشل + استرجاع) |
| `payments_expire` | انتهاء صلاحية طلبات الشحن المعلّقة |
| `tickets_auto_close` | إغلاق التذاكر الخاملة |
| `orders_stuck_alert` | تنبيه الأدمن بالطلبات العالقة (`order_stuck_alert_hours`) |
| `providers_balance` / `providers_health` | رصيد المزودين وتنبيه الانخفاض / فحص الصحة |
| `admin_daily_digest` | ملخص يومي (أرقام) للأدمن |
| `database_maintenance` | يومياً (`db_maintenance_hour`): حذف مفاتيح التكرار المنتهية + WAL checkpoint + optimize — **بلا حذف بيانات تاريخية** |
| `backups_auto` | نسخة تلقائية كل `backup_interval_hours` + تنظيف حسب الاحتفاظ |

الحالة والفترات والتشغيل اليدوي: «🛠 لوحة التحكم» ← «⏱ المهام الدورية» (زر «▶️ تشغيل الآن»).
تنبيه الأدمن بعد `job_failure_alert_threshold` فشلاً متتالياً لمهمة.

---

## 3) النسخ الاحتياطي والاستعادة

### 3.1 ما يحدث تلقائياً
- نسخة متّسقة عبر `VACUUM INTO` (آمنة والبوت يعمل) ⇒ `backups/smm_backup_*.db.gz` + `.meta.json` (بصمة SHA-256).
- تُرسَل للقناة `BACKUP_CHANNEL_ID` إن وُجدت وكان `backup_send_to_channel` مفعّلاً.
- الاحتفاظ: `backup_retention_days` (14) مع حدّ أدنى `backup_min_keep` (5) لا يُحذف تحته شيء.

### 3.2 ⚠️ النسخ غير مشفّرة والقناة يجب أن تكون خاصة
النسخة تحوي بيانات العملاء والمال. **قناة النسخ يجب أن تكون خاصة وأعضاؤها موثوقون فقط.** مفاتيح المزودين داخلها
مشفّرة بـ`ENCRYPTION_KEY` غير المخزّن فيها. لتعطيل الإرسال: عطّل `backup_send_to_channel`.

### 3.3 الاستعادة (خارج البوت دائماً)
```bash
sudo systemctl stop smmbot                              # الأداة ترفض العمل والبوت يعمل
python -m scripts.restore_backup --list                 # عرض النسخ
python -m scripts.restore_backup --latest               # أو --id N أو --file /path/x.db.gz  (أضف --yes لتخطي السؤال)
python -m scripts.audit_ledger                          # تحقق مالي بعد الاستعادة
python -m scripts.boot_check
sudo systemctl start smmbot
```
قبل الاستبدال تُنشئ الأداة **نسخة أمان** للقاعدة الحالية. للنسخة من القناة: نزّل الملف ثم `--file`.
عند الاستعادة على سيرفر جديد استخدم **نفس `ENCRYPTION_KEY`**.

بعد الاستعادة: قد توجد طلبات أُرسلت للمزوِّد بعد وقت النسخة (غير موجودة في القاعدة المستعادة) — قارن لوحة المزوِّد
بطلبات الفترة يدوياً، ولا تُعد إرسالها قبل التأكد (خطر إرسال مزدوج).

### 3.4 ضغط القاعدة
«💾 النسخ الاحتياطي» ← «🧹 ضغط القاعدة» (يُنشئ نسخة أمان أولاً ويقفل الكتابة ثوانٍ). يدوي دائماً، لا تلقائي.

---

## 4) الفحوص الدورية الموصى بها

| متى | الأمر | المتوقع |
|---|---|---|
| أسبوعياً وبعد أي استعادة/ترقية | `python -m scripts.audit_ledger` | `0 فحص فاشل` (يُشغَّل والبوت يعمل؛ للقراءة فقط) |
| بعد تغيير `.env` أو النقل | `python -m scripts.security_check --fix` | 0 «خطر» |
| قبل الترقية | `python -m scripts.boot_check` | كل الأقسام ✓ |
| يومياً (من البوت) | «🩺 صحة النظام» | لا أخطاء حمراء، المزودون متصلون |

مخرجات `audit_ledger` وكيفية التصرف:

| الفحص الفاشل | المعنى | التصرف |
|---|---|---|
| رصيد ≠ مجموع الحركات | رصيد المحفظة خُرِّب خارج الخدمة (تعديل يدوي/استعادة خاطئة) | **أوقف البوت**، خذ نسخة، حقّق في المستخدمين المذكورين، لا تصحّح الرصيد بـSQL؛ صحّحه بتسوية من الأدمن (`➕/➖` تُنشئ حركة) بعد فهم السبب |
| انقطاع سلسلة الحركات | حركة حُذفت/عُدّلت | استعد نسخة سليمة قبل أول انقطاع |
| طلب بلا خصم واحد / استرجاع غير مطابق | خلل في طلب | افحص الطلب في «📦 الطلبات» وسجل حالاته |
| دفعة معتمدة بلا إيداع | اعتماد لم يكتمل أو حُذفت حركته | استعادة أو تسوية موثّقة |
| submitting عالق (تنبيه) | البوت توقف أثناء الإرسال | أعد تشغيل البوت (يحوّلها لـ`submit_uncertain`) ثم انظر §5.3 |

---

## 5) استكشاف الأخطاء

### 5.1 البوت لا يعمل / يخرج فوراً
| العَرَض | السبب والحل |
|---|---|
| `❌ رفض تيليجرام التوكن` (رمز 1) | `BOT_TOKEN` خاطئ/مُلغى ⇒ انسخه من @BotFather بلا مسافات أو اقتباس |
| `❌ تعذّر الاتصال بتيليجرام` (رمز 1) | شبكة/DNS/جدار ناري/حجب `api.telegram.org` ⇒ systemd يعيد المحاولة تلقائياً |
| `❌ ...نسخة أخرى تعمل` (رمز 2) | عملية ثانية تحمل `data/bot.lock` ⇒ `pgrep -af main.py` ثم أوقف المكرّر. لا تحذف القفل يدوياً دون التأكد |
| خطأ إعداد (رمز 1) | الرسالة تحدد المتغير؛ قارن مع `.env.example` |
| `انهيار غير متوقع` | التتبّع في `logs/bot.log` (الأسرار مُنقّاة) |

### 5.2 البوت يعمل لكن لا يستجيب
1. `journalctl -u smmbot -n 100` — ابحث عن `CRITICAL`/`ERROR`.
2. تحقق أنه ليس في **وضع الصيانة** («⚙️ الإعدادات» ← «🚧»)؛ الأدمن لا يتأثر والعملاء يرون رسالة الصيانة.
3. تأكد أن الحساب غير محظور وأن الدور صحيح («👥 المستخدمون»).
4. تقييد المعدل: «🛡️ الأمان» ← «⏱ الموقوفون مؤقتاً» ← «🔓 رفع الإيقاف».

### 5.3 الطلبات
| الحالة | المعنى | التصرف |
|---|---|---|
| `pending` طويلاً | المزوِّد معطّل/رصيده غير كافٍ (ينتظر ~6 ساعات ثم يفشل ويُسترجع) | «🔌 المزودون»: اختبار الاتصال، تحديث الرصيد، اشحن رصيد المزوِّد |
| `submitting` عالق | توقف البوت أثناء الإرسال | **لا تُعد الإرسال يدوياً.** عند إعادة تشغيل البوت تُنقل هذه الطلبات تلقائياً إلى `submit_uncertain` (مصيرها غير معروف) ويُحرَّر قفلها — ثم اتبع الصف التالي |
| `submit_uncertain` | لا يُعرف هل وصل الطلب للمزوِّد (مهلة) | افحص لوحة المزوِّد بالرابط/الوقت: وُجد ⇒ «🔗 ربط رقم المزود»؛ لم يوجد ⇒ «⛔ تعليم كفاشل + استرجاع» |
| `submitted/in_progress` طويلاً | المزوِّد بطيء | «🔄 إعادة فحص الآن»؛ تنبيه العالق يصل بعد `order_stuck_alert_hours` |
| طلب خاطئ تماماً | — | «❌ إلغاء + استرجاع» (مسموح قبل الإرسال؛ بعده قرار الأدمن وقد ينفّذ المزوِّد) |

كل تغيير يدوي يُسجَّل في سجل الحالات وسجل التدقيق باسم الأدمن.

### 5.4 المال والمدفوعات
- «لم يصلني رصيدي»: «💰 المدفوعات» ← «🔎 بحث عن حوالة»؛ إن كانت `pending` فاعتمدها/ارفضها. المعتمدة تُنشئ حركة إيداع واحدة فقط (اعتماد مزدوج مستحيل).
- تسوية يدوية: «👥 المستخدمون» ← «➕ إضافة رصيد»/«➖ خصم رصيد» (سبب إلزامي، حركة مسجَّلة، صلاحية خاصة).
- فرق في الأرصدة: `python -m scripts.audit_ledger` (§4).

### 5.5 المزوِّد
- بعد `provider_failure_threshold` أخطاء متتالية يُعطَّل المزوِّد `provider_disable_minutes` تلقائياً ويصل تنبيه.
- مفتاح API يُعرض مقنّعاً دائماً؛ لتغييره «🔑 تغيير المفتاح». لا يُسجَّل في أي لوق.
- رفض رابط المزوِّد: يُقبل https فقط، منفذ 443/8443، ومضيف عام (حماية SSRF).

### 5.6 قاعدة البيانات
- `database is locked` متقطع: SQLite كاتب واحد؛ يُعاد المحاولة داخلياً. إن تكرر كثيراً فالحمل يستدعي نقلاً لـPostgreSQL.
- ملف `-wal` كبير: تنظّفه الصيانة اليومية؛ يدوياً أوقف البوت وشغّل «ضغط القاعدة».
- `python -m scripts.init_db --status` يعرض إصدار المخطط والترحيلات الناقصة (للقراءة فقط).

### 5.7 تسرّب أسرار
- **توكن البوت:** أنشئ توكناً جديداً من @BotFather (`/revoke`) ثم حدّث `.env` وأعد التشغيل.
- **`ENCRYPTION_KEY`:** لا تدوير آلي في هذا الإصدار. الإجراء: ولّد مفتاحاً جديداً، ضعه في `.env`، ثم أعد إدخال مفتاح كل مزوِّد عبر «🔑 تغيير المفتاح» (القديمة غير قابلة للقراءة بالمفتاح الجديد).
- **مفتاح مزوِّد:** بدّله من لوحة المزوِّد ثم في البوت.
- **القناة/النسخ:** إن كانت القناة غير خاصة فاعتبر بيانات العملاء مكشوفة وأبلغ المعنيين.

---

## 6) الصلاحيات والأدوار

- الأدوار: `user` · `support` · `admin` · `super_admin` — والمصفوفة الكاملة (47 صلاحية، 25 خطِرة) في [`PERMISSIONS.md`](PERMISSIONS.md).
- الصلاحيات تُقرأ من جداول قاعدة البيانات (لا أدمن ثابت في الكود)؛ `SUPER_ADMIN_IDS` للزرع الأول فقط.
- أنشئ/ارفع أدمن: `python -m scripts.create_admin <id> <role>` أو «🎚 تغيير الدور» من البوت.
- **فجوة معروفة:** لا شاشة لاستثناءات الصلاحيات الفردية؛ الخدمة (`set_user_permission`) جاهزة، وحتى تُبنى الشاشة يلزم تعديل جدول الاستثناءات مباشرة (اتبع الحذر وسجّل ذلك).

---

## 7) الترقية

1. «💾 النسخ الاحتياطي» ← «🆕 نسخة الآن» (وتأكد أنها وصلت القناة أو نزّلها).
2. `sudo systemctl stop smmbot`
3. استبدل الكود (`git pull`) ثم `pip install -r requirements.txt`.
4. `python -m scripts.init_db` — يطبّق الترحيلات الجديدة فقط (Migrations إضافية، لا تعديل على القديمة). (وإن نسيته فالبوت يطبّقها عند الإقلاع بعد أخذ نسخة أمان تلقائية؛ وفشل هذه النسخة يوقف الإقلاع بدل ترقية بلا شبكة أمان.)
5. `python -m scripts.boot_check && python -m scripts.audit_ledger`
6. `sudo systemctl start smmbot` ثم راقب `journalctl -u smmbot -f` دقائق.

الرجوع للخلف: أوقف الخدمة، أعد الكود القديم، واستعد نسخة ما قبل الترقية (§3.3) — الترحيلات لا تُعكَس تلقائياً.

---

## 8) السجلات

- `logs/bot.log` دوّار (5MB × 5 ملفات) ويُنقّى من التوكن والمفاتيح. `LOG_LEVEL=DEBUG` للتشخيص المؤقت فقط.
- من البوت «📝 السجلات»: 🧾 سجل التدقيق (من فعل ماذا) · ❗ سجل الأخطاء · 🔌 استدعاءات المزودين (الفاشلة فقط بفلتر).
- «🛡️ الأمان» ← «📜 الأحداث الأمنية»: محاولات الوصول المرفوضة والعمليات الخطِرة.

---

## 9) قيود معروفة تؤثر على التشغيل
عملية واحدة فقط · لا Docker · نموذج systemd غير مُجرَّب · لا failover بين مزودين · الحظر المؤقت يضيع عند إعادة التشغيل ·
لا 2FA · نسخ القناة غير مشفّرة · `admin_cancel` على طلب مُرسَل يسترجع رغم احتمال تنفيذ المزوِّد · لم يُجرَّب مع توكن/مزوِّد حقيقيين.

`````

---

## `tests/integration/test_startup_phase12.py`

> جديد

```python
"""
المرحلة 12 — فشل الإقلاع لا يسرّب أسراراً ويخرج برمز فشل ويحرّر القفل.

اكتُشف عند أول تشغيل حقيقي لـ`main.py` على تثبيت نظيف بتوكن مرفوض: استثناء `InvalidToken` يحمل
التوكن كاملاً في نصه وكان يُطبع كتتبّع خام في الطرفية/journald، بينما ملف اللوق نظيف.
"""

from __future__ import annotations

import pytest
from telegram.error import InvalidToken, NetworkError

import main as app_main
from utils.logging_setup import RedactingFormatter
from utils.security import clear_registered_secrets

TOKEN = "123456789:AAStartupLeakTestTokenDoNotUse0123456789"


class _FakeApp:
    """تطبيق مزيّف: `run_polling` يرفع الاستثناء المطلوب كما يفعل عند فشل الإقلاع الحقيقي."""

    def __init__(self, error: BaseException) -> None:
        """تخزين الاستثناء الذي سيُرفع."""
        self.error = error

    def run_polling(self, **_: object) -> None:
        """محاكاة فشل الإقلاع."""
        raise self.error


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    """بيئة تشغيل معزولة: مسارات مؤقتة وتوكن اختباري، وبلا ملف .env حقيقي."""
    monkeypatch.setenv("BOT_TOKEN", TOKEN)
    monkeypatch.setenv("SUPER_ADMIN_IDS", "111222333")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "data" / "t.db"))
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "logs" / "bot.log"))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.setattr(app_main, "setup_logging", lambda *a, **k: None)   # لا نلمس إعداد اللوق العام
    yield tmp_path
    clear_registered_secrets()


@pytest.mark.parametrize(
    "error",
    [
        InvalidToken(f"The token `{TOKEN}` was rejected by the server."),
        NetworkError(f"httpx.ConnectError: https://api.telegram.org/bot{TOKEN}/getMe"),
        RuntimeError(f"boom with {TOKEN}"),
    ],
    ids=["invalid-token", "network", "unexpected"],
)
def test_startup_failure_exits_1_without_leaking_token(isolated_env, monkeypatch, capsys, caplog, error) -> None:
    """أي فشل إقلاع ⇒ رمز 1، لا توكن في الطرفية ولا في السجلات، والقفل يُحرَّر (يمكن إعادة التشغيل)."""
    monkeypatch.setattr(app_main, "build_application", lambda config: _FakeApp(error))
    with caplog.at_level("DEBUG"):
        code = app_main.main()
    assert code == 1
    captured = capsys.readouterr()
    assert "❌" in captured.err
    assert TOKEN not in captured.err and TOKEN not in captured.out
    rendered = "\n".join(RedactingFormatter("%(message)s").format(record) for record in caplog.records)
    assert TOKEN not in rendered, "التوكن ظهر في السجلات بعد التنقية"
    # القفل محرَّر: التشغيل التالي لا يفشل بـ«نسخة تعمل بالفعل»
    monkeypatch.setattr(app_main, "build_application", lambda config: _FakeApp(KeyboardInterrupt()))
    assert app_main.main() == 0


def test_clean_shutdown_returns_zero(isolated_env, monkeypatch) -> None:
    """إيقاف المشغّل (Ctrl+C) ⇒ رمز 0."""
    monkeypatch.setattr(app_main, "build_application", lambda config: _FakeApp(KeyboardInterrupt()))
    assert app_main.main() == 0


def test_second_instance_is_refused_with_code_2(isolated_env, monkeypatch, capsys) -> None:
    """نسخة ثانية أثناء عمل الأولى ⇒ رمز 2 ورسالة واضحة (حماية R9)."""
    from config import Config
    from utils.single_instance import SingleInstance

    config = Config.load(require_bot_token=True)
    holder = SingleInstance(config.data_dir / "bot.lock")
    holder.acquire()
    try:
        monkeypatch.setattr(app_main, "build_application", lambda c: _FakeApp(KeyboardInterrupt()))
        assert app_main.main() == 2
        assert "❌" in capsys.readouterr().err
    finally:
        holder.release()

```

---

## `tests/integration/test_audit_ledger_phase12.py`

> جديد

```python
"""
المرحلة 12 — أداة التدقيق المالي `scripts.audit_ledger`:
    • تُبلغ «سليم» على بيانات حقيقية ناتجة عن الخدمات (شحن + طلب مكتمل + طلب فاشل مُسترجَع).
    • تكشف كل نوع تلاعب/تلف متعمَّد في القاعدة (كل فحص بحقنه مباشرة بـSQL).
    • للقراءة فقط (لا تكتب شيئاً)، وكود الخروج صحيح.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.enums import OrderStatus
from core.exceptions import ProviderPermanentError
from scripts import audit_ledger
from utils.datetime_utils import iso_plus_seconds

pytestmark = pytest.mark.asyncio


async def _populate(services, repos, db, user, admin, mock_service, mock_client, payment_method) -> None:
    """بناء بيانات واقعية: رصيد، طلب مكتمل، وطلب رفضه المزود نهائياً فاسترُجع بالكامل."""
    await services.wallet.adjust_balance(target=user, amount_units=500 * 10_000, admin=admin, reason="شحن للتدقيق", credit=True)
    done = await services.orders.create_order(user, service_id=mock_service.id, link="https://example.com/a", quantity=1000)
    await services.orders.process_pending_orders(limit=10)
    provider_id = (await repos.orders.get(done.id)).provider_order_id
    mock_client.advance(provider_id, to="completed")
    async with db.transaction() as tx:                        # جعل موعد المتابعة حالّاً دون انتظار
        await tx.execute("UPDATE orders SET next_check_at = ? WHERE id = ?", (iso_plus_seconds(-30), done.id))
    await services.orders.process_due_orders(limit=10)

    mock_client.fail_next_add = ProviderPermanentError("رفض المزود")
    failed = await services.orders.create_order(user, service_id=mock_service.id, link="https://example.com/f", quantity=1000)
    await services.orders.process_pending_orders(limit=10)
    assert (await repos.orders.get(done.id)).status == OrderStatus.COMPLETED
    assert (await repos.orders.get(failed.id)).refund_amount_units > 0, "الطلب الفاشل يجب أن يُسترجع ليختبر التدقيق مساراً حقيقياً"


@pytest.fixture
async def populated(services, repos, db, user, admin, mock_service, mock_client, payment_method):
    """قاعدة مليئة بالبيانات + مسار ملفها (نفس الملف الذي تعمل عليه الخدمات)."""
    await _populate(services, repos, db, user, admin, mock_service, mock_client, payment_method)
    return Path(db.path)


def _run(path: Path) -> list[audit_ledger.Finding]:
    """تشغيل التدقيق على ملف القاعدة بوضع القراءة فقط."""
    conn = audit_ledger.open_readonly(path)
    try:
        return audit_ledger.audit(conn)
    finally:
        conn.close()


def _failed(findings: list[audit_ledger.Finding]) -> set[str]:
    """عناوين الفحوص الفاشلة (الشديدة فقط)."""
    return {f.title for f in findings if f.count and f.severity == "bad"}


async def test_clean_database_reports_no_findings(populated: Path) -> None:
    """بيانات سليمة ناتجة عن الخدمات ⇒ لا فحص فاشل ولا تنبيه."""
    findings = _run(populated)
    assert len(findings) >= 11
    assert [f for f in findings if f.count] == []


async def test_cli_exit_codes_and_report(populated: Path, capsys) -> None:
    """سليم ⇒ 0 وتقرير عربي · خلل ⇒ 1 · قاعدة غير موجودة ⇒ 2."""
    assert audit_ledger.main(["--db", str(populated)]) == 0
    assert "النتيجة: 0 فحص فاشل" in capsys.readouterr().out
    conn = sqlite3.connect(populated)
    conn.execute("UPDATE users SET balance_units = balance_units + 1 WHERE telegram_id = 100200300")
    conn.commit()
    conn.close()
    assert audit_ledger.main(["--db", str(populated)]) == 1
    assert "⛔" in capsys.readouterr().out
    assert audit_ledger.main(["--db", str(populated.parent / "missing.db")]) == 2


async def test_audit_is_read_only(populated: Path) -> None:
    """الاتصال في وضع query_only: أي كتابة عبره تُرفض."""
    conn = audit_ledger.open_readonly(populated)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("UPDATE users SET balance_units = 0")
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("UPDATE users SET balance_units = balance_units + 7", "رصيد المحفظة لا يساوي مجموع الحركات"),
        ("UPDATE transactions SET balance_before_units = balance_before_units + 1 WHERE id = (SELECT MAX(id) FROM transactions)",
         "انقطاع سلسلة الحركات أو خطأ حسابي فيها"),
        ("DELETE FROM transactions WHERE type = 'order'", "طلب بلا حركة خصم واحدة بقيمة التكلفة"),
        ("UPDATE orders SET refund_amount_units = 5", "مجموع الاسترجاعات لا يطابق حقل الاسترجاع في الطلب (أو يتجاوز التكلفة)"),
        ("UPDATE orders SET status = 'refunded'", "حالة نهائية لا تتسق مع الاسترجاع"),
        ("UPDATE orders SET status = 'in_progress'", "آخر سجل في تاريخ الحالات لا يساوي حالة الطلب"),
        ("DELETE FROM order_status_history WHERE id = (SELECT MIN(id) + 1 FROM order_status_history)",
         "انقطاع في سلسلة تاريخ حالات الطلب"),
    ],
    ids=["balance", "chain", "missing-charge", "refund-mismatch", "final-status", "history-last", "history-gap"],
)
async def test_each_tampering_is_detected(populated: Path, sql: str, expected: str) -> None:
    """كل نوع تلف متعمَّد يُكتشف بالفحص المخصص له."""
    conn = sqlite3.connect(populated)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA ignore_check_constraints = ON")
    conn.execute(sql)
    conn.commit()
    conn.close()
    assert expected in _failed(_run(populated))


async def test_payment_checks_detect_orphan_and_unapproved_deposits(
    services, repos, db, user, admin, payment_method
) -> None:
    """دفعة معتمدة بلا إيداع، وإيداع لدفعة غير معتمدة — كلاهما يُكتشف."""
    now = "2026-01-01T00:00:00Z"
    async with db.transaction() as tx:
        await tx.execute(
            "INSERT INTO payments (user_id, method_id, amount_units, credited_units, status, created_at, updated_at)"
            " VALUES (?, ?, 100000, 100000, 'approved', ?, ?)", (user.id, payment_method.id, now, now))
    title = "دفعة معتمدة بلا إيداع واحد مطابق، أو إيداع لدفعة غير معتمدة"
    assert title in _failed(_run(Path(db.path)))


async def test_stuck_submitting_is_warning_only(
    services, repos, db, user, admin, mock_service, mock_client, payment_method
) -> None:
    """طلب عالق في submitting ⇒ تنبيه (warn) لا يُفشل الخروج."""
    await services.wallet.adjust_balance(target=user, amount_units=100 * 10_000, admin=admin, reason="شحن", credit=True)
    order = await services.orders.create_order(user, service_id=mock_service.id, link="https://example.com/b", quantity=1000)
    async with db.transaction() as tx:
        await tx.execute("UPDATE orders SET status = ?, updated_at = '2020-01-01T00:00:00Z' WHERE id = ?", (OrderStatus.SUBMITTING, order.id))
        await tx.execute(
            "INSERT INTO order_status_history (order_id, from_status, to_status, actor_type, created_at)"
            " VALUES (?, ?, ?, 'system', '2020-01-01T00:00:00Z')", (order.id, order.status, OrderStatus.SUBMITTING))
    findings = _run(Path(db.path))
    stuck = [f for f in findings if f.severity == "warn"]
    assert stuck and stuck[0].count == 1
    assert _failed(findings) == set()

```

---

## `tests/unit/test_release_phase12.py`

> جديد

```python
"""
المرحلة 12 — اختبارات الإصدار النهائي: اتساق الإصدار والوثائق والاعتماديات وملف البيئة.

الفكرة: كل ما يقرؤه المشغّل (README، RUNBOOK، .env.example، requirements، الوثائق المولَّدة) يجب ألا ينحرف
عن الكود. أي انحراف يُفشل الاختبار بدل أن يُكتشف على سيرفر الإنتاج.
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import re
import sys
from pathlib import Path

import pytest

from config import BASE_DIR
from core.constants import APP_VERSION
from core.permissions import PERMISSIONS
from scripts import gen_reference_docs

DOCS = BASE_DIR / "docs"
README = BASE_DIR / "README.md"
RUNBOOK = DOCS / "RUNBOOK.md"

#: اسم الوحدة عند الاستيراد ⇒ اسم الحزمة في requirements
IMPORT_TO_PACKAGE = {
    "telegram": "python-telegram-bot",
    "aiosqlite": "aiosqlite",
    "cryptography": "cryptography",
    "httpx": "httpx",
    "dotenv": "python-dotenv",
}
PRODUCTION_DIRS = ("core", "database", "handlers", "integrations", "jobs", "keyboards", "middlewares",
                   "scripts", "services", "texts", "utils")
LOCAL_TOP_LEVEL = {*PRODUCTION_DIRS, "config", "main", "tests"}


def _requirements(path: Path) -> dict[str, str]:
    """قراءة ملف requirements ⇒ {اسم الحزمة بحروف صغيرة: الإصدار المثبَّت}."""
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?==([^\s;]+)$", line)
        assert match, f"سطر غير مثبَّت بـ== في requirements: {raw!r}"
        result[match.group(1).lower()] = match.group(3)
    return result


def test_version_is_one_point_zero_and_documented() -> None:
    """الإصدار 1.0.0 مذكور في README وRUNBOOK."""
    assert APP_VERSION == "1.0.0"
    assert APP_VERSION in README.read_text(encoding="utf-8")
    assert APP_VERSION in RUNBOOK.read_text(encoding="utf-8")


def test_generated_docs_match_the_code() -> None:
    """docs/SETTINGS.md وPERMISSIONS.md مطابقان تماماً لما يولّده الكود الآن (وإلا شغّل gen_reference_docs)."""
    for path, expected in gen_reference_docs.render_all().items():
        assert path.exists(), f"{path.name} غير موجود — شغّل: python -m scripts.gen_reference_docs"
        assert path.read_text(encoding="utf-8") == expected, (
            f"{path.name} قديم عن الكود — شغّل: python -m scripts.gen_reference_docs"
        )


def test_env_example_matches_config_variables() -> None:
    """مفاتيح .env.example = كل متغيرات البيئة التي يقرؤها config.py، والأسرار فارغة."""
    source = (BASE_DIR / "config.py").read_text(encoding="utf-8")
    used = set(re.findall(r'_get_\w+\(\s*"([A-Z][A-Z0-9_]+)"', source))
    assert {"BOT_TOKEN", "SUPER_ADMIN_IDS", "ENCRYPTION_KEY"} <= used, "فشل استخراج متغيرات config.py"
    example: dict[str, str] = {}
    for raw in (BASE_DIR / ".env.example").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            example[key.strip()] = value.strip()
    assert set(example) == used, f"فرق: ناقص في .env.example={used - set(example)} · زائد={set(example) - used}"
    for secret in ("BOT_TOKEN", "ENCRYPTION_KEY"):
        assert example[secret] == "", f"{secret} يجب أن يكون فارغاً في .env.example"


def test_every_third_party_import_is_pinned_in_requirements() -> None:
    """كل مكتبة طرف ثالث مستوردة في كود الإنتاج مدرجة ومثبَّتة في requirements.txt (والاختبارات في dev)."""
    pinned = _requirements(BASE_DIR / "requirements.txt")
    stdlib = set(sys.stdlib_module_names)
    found: set[str] = set()
    for folder in (*PRODUCTION_DIRS, "."):
        base = BASE_DIR if folder == "." else BASE_DIR / folder
        for file in (base.glob("*.py") if folder == "." else base.rglob("*.py")):
            tree = ast.parse(file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module.split(".")[0]]
                found.update(n for n in names if n not in stdlib and n not in LOCAL_TOP_LEVEL and n != "__future__")
    unknown = found - set(IMPORT_TO_PACKAGE)
    assert not unknown, f"مكتبات مستوردة غير معروفة للاختبار/requirements: {sorted(unknown)}"
    for module in found:
        assert IMPORT_TO_PACKAGE[module] in pinned, f"{module} مستورد لكن {IMPORT_TO_PACKAGE[module]} ليس في requirements.txt"
    dev = _requirements(BASE_DIR / "requirements-dev.txt")
    assert {"pytest", "pytest-asyncio"} <= set(dev)


def test_docs_reference_only_existing_scripts_files_and_links() -> None:
    """كل `python -m scripts.X` وكل رابط وثيقة نسبي في README/RUNBOOK يشير إلى ملف موجود."""
    for doc in (README, RUNBOOK):
        text = doc.read_text(encoding="utf-8")
        for name in set(re.findall(r"python -m scripts\.([a-z_]+)", text)):
            assert (BASE_DIR / "scripts" / f"{name}.py").exists(), f"{doc.name} يذكر scripts.{name} وهو غير موجود"
        for target in re.findall(r"\]\(((?!https?:)[^)#]+)\)", text):
            assert (doc.parent / target).exists(), f"{doc.name}: رابط مكسور → {target}"


def test_readme_numbers_match_reality() -> None:
    """الأرقام المذكورة في README (صلاحيات، إعدادات، مهام، خدمات، معالجات) تطابق الكود."""
    from handlers.registry import build_handlers
    from jobs import JOB_LABELS
    from services import ServiceContainer

    text = README.read_text(encoding="utf-8")
    services = len(dataclasses.fields(ServiceContainer)) - 2          # ناقص db وrepos
    for number, label in (
        (len(PERMISSIONS), "صلاحية"),
        (len(asyncio.run(gen_reference_docs._settings_rows())), "إعداداً"),   # المزروعة فعلاً في القاعدة
        (len(JOB_LABELS), "مهمة"),
        (services, "خدمة"),
    ):
        assert f"{number} {label}" in text or f"({number} {label}" in text, f"README: لا يذكر «{number} {label}»"
    assert len(build_handlers()) > 100


@pytest.mark.parametrize("phase", range(0, 12))
def test_phase_reports_exist(phase: int) -> None:
    """تقارير المراحل السابقة موجودة (تقرير م12 يُسلَّم مع الإصدار)."""
    name = "PHASE0_DESIGN.md" if phase == 0 else f"PHASE{phase}_REPORT.md"
    assert (DOCS / name).exists()


def test_no_secrets_or_runtime_dirs_shipped() -> None:
    """لا .env حقيقي ولا قاعدة/نسخ/لوق داخل شجرة المشروع المسلَّمة."""
    assert not (BASE_DIR / ".env").exists()
    assert not (BASE_DIR / "data").exists() and not (BASE_DIR / "backups").exists()

```
