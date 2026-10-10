# الكود الكامل — المرحلة 3 (واجهة تيليجرام + المهام الدورية)

كل ما في هذا الملف منسوخ آلياً من ملفات المشروع الفعلية وقت كتابة التقرير،
فلا يوجد اختلاف بين ما تقرأه هنا وما يعمل عندك.

> الملفات غير المذكورة هنا لم تتغيّر عن المرحلتين 1 و2.

## الفهرس

**نقطة التشغيل والتسجيل**

- `main.py` — 166 سطراً
- `handlers/registry.py` — 270 سطراً
- `utils/single_instance.py` — 125 سطراً

**الطبقة الوسيطة**

- `middlewares/__init__.py` — 21 سطراً
- `middlewares/context.py` — 174 سطراً
- `middlewares/rate_limit.py` — 79 سطراً

**الأدوات المشتركة للمعالجات**

- `handlers/__init__.py` — 1 سطراً
- `handlers/common/__init__.py` — 1 سطراً
- `handlers/common/ui.py` — 100 سطراً
- `handlers/common/guards.py` — 57 سطراً
- `handlers/common/errors.py` — 110 سطراً
- `handlers/common/fallbacks.py` — 81 سطراً
- `handlers/common/navigation.py` — 100 سطراً

**لوحات الأزرار والنصوص والتنسيق**

- `keyboards/__init__.py` — 1 سطراً
- `keyboards/callback_data.py` — 144 سطراً
- `keyboards/common_kb.py` — 109 سطراً
- `keyboards/user_kb.py` — 367 سطراً
- `texts/ar.py` — 334 سطراً
- `utils/formatters.py` — 179 سطراً

**شاشات العميل**

- `handlers/user/__init__.py` — 1 سطراً
- `handlers/user/catalog.py` — 104 سطراً
- `handlers/user/order_flow.py` — 229 سطراً
- `handlers/user/orders.py` — 189 سطراً
- `handlers/user/wallet.py` — 65 سطراً
- `handlers/user/deposit.py` — 291 سطراً
- `handlers/user/support.py` — 332 سطراً
- `handlers/user/account.py` — 105 سطراً

**المهام الدورية**

- `jobs/__init__.py` — 100 سطراً
- `jobs/telegram_sender.py` — 77 سطراً
- `jobs/notification_jobs.py` — 35 سطراً
- `jobs/order_jobs.py` — 52 سطراً
- `jobs/maintenance_jobs.py` — 33 سطراً

**أدوات الفحص**

- `scripts/boot_check.py` — 189 سطراً

**الاختبارات**

- `tests/telegram_fakes.py` — 212 سطراً
- `tests/unit/test_callback_data.py` — 97 سطراً
- `tests/unit/test_ui_helpers.py` — 134 سطراً
- `tests/integration/test_no_dead_buttons.py` — 229 سطراً
- `tests/integration/test_handler_registry.py` — 175 سطراً
- `tests/integration/test_user_interface.py` — 510 سطراً
- `tests/integration/test_user_screens.py` — 418 سطراً
- `tests/integration/test_jobs.py` — 249 سطراً

**الإجمالي: 41 ملفاً / 6245 سطراً**

---

## نقطة التشغيل والتسجيل

### `main.py`

```python
"""
نقطة تشغيل البوت.

التسلسل الكامل عند الإقلاع:
    1. تحميل الإعدادات من ‎.env‎ والتحقق من وجود التوكن.
    2. تهيئة اللوق (ملف متدحرج + شاشة).
    3. حجز قفل «نسخة واحدة» حتى لا يعمل بوتان على نفس القاعدة.
    4. فتح قاعدة البيانات وتطبيق أي ترحيلات ناقصة.
    5. بناء حاوية الخدمات (المنطق كله) وحقنها في `bot_data`.
    6. تسجيل المعالجات (`handlers/registry.py`) والمعالج العام للأخطاء.
    7. استرداد ما علق من تشغيل سابق، ثم جدولة المهام الدورية.
    8. بدء الاستقبال (polling) حتى إشارة إيقاف، ثم إغلاق نظيف.

التشغيل:
    python -m main            # من داخل مجلد المشروع
    python main.py
"""

from __future__ import annotations

import asyncio
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
from middlewares.rate_limit import RateLimiter                      # noqa: E402
from services import build_services                                 # noqa: E402
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


async def _open_database(config: Config) -> Database:
    """فتح قاعدة البيانات وتطبيق الترحيلات الناقصة قبل بدء الخدمة."""
    db = Database(config.database_path)
    await db.connect()
    migrator = Migrator(db)
    pending = await migrator.pending()
    if pending:
        logger.info("تطبيق %s ترحيل ناقص: %s", len(pending), ", ".join(pending))
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
        repos = Repositories(db)
        services = build_services(
            db,
            repos,
            secret_box=SecretBox(config.encryption_key),
            super_admin_ids=config.super_admin_ids,
        )
        application.bot_data["services"] = services
        application.bot_data["config"] = config

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

    limiter = RateLimiter()
    count = register_handlers(application, limiter)
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

    config.ensure_directories()
    setup_logging(config.log_file, config.log_level)
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

### `handlers/registry.py`

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
from middlewares.rate_limit import RateLimiter

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
    return ConversationHandler(
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
    return ConversationHandler(
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
    return ConversationHandler(
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
    return ConversationHandler(
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
    ]


def conversation_handlers() -> list[ConversationHandler]:
    """كل محادثات واجهة العميل بالترتيب الذي تُسجَّل به."""
    return [
        _order_conversation(),
        _deposit_conversation(),
        _new_ticket_conversation(),
        _ticket_reply_conversation(),
    ]


def build_handlers(limiter: RateLimiter | None = None) -> list[tuple[int, BaseHandler]]:
    """
    بناء قائمة (المجموعة، المعالج) بالترتيب الصحيح.

    الترتيب داخل المجموعة 0:
        المحادثات ← الأوامر العامة ← أزرار الشاشات ← المسارات الاحتياطية.
    السبب: المحادثة النشطة يجب أن تلتقط /start و/cancel قبل المعالج العام،
    والمسار الاحتياطي يجب أن يكون الأخير حتى لا يبتلع أزراراً صحيحة.
    """
    handlers: list[tuple[int, BaseHandler]] = [
        (MIDDLEWARE_GROUP, TypeHandler(Update, UserContextMiddleware(limiter)))
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


def register_handlers(application: Application, limiter: RateLimiter | None = None) -> int:
    """
    تسجيل كل المعالجات على التطبيق وإرجاع عددها.

    المخرجات: عدد المعالجات المسجَّلة (يُطبع في سجل الإقلاع للتأكيد).
    """
    registered = build_handlers(limiter)
    for group, handler in registered:
        application.add_handler(handler, group=group)
    application.add_error_handler(errors.error_handler)
    return len(registered)
```

### `utils/single_instance.py`

```python
"""
قفل «نسخة واحدة فقط» من البوت.

لماذا هذا مهم هنا تحديداً؟
    تشغيل نسختين من البوت على نفس قاعدة البيانات يسبب:
        • تعارض `getUpdates` في تيليجرام (Conflict 409) وفقدان رسائل.
        • معالجة الطلب نفسه مرتين من مهمتي الإرسال (رغم وجود الحجز، لا داعي
          لاختبار حظّنا بأموال المستخدمين).
    لذلك نحجز ملف قفل على القرص عند الإقلاع ونرفض التشغيل إن كان محجوزاً.

التنفيذ يستخدم `fcntl.flock` على أنظمة يونكس (قفل يتحرر تلقائياً إن مات
المسار فجأة)، ويسقط إلى فحص PID على ويندوز.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import TracebackType

from utils.logging_setup import get_logger

logger = get_logger(__name__)

try:                                    # يونكس/لينكس/ماك
    import fcntl

    HAS_FCNTL = True
except ImportError:                     # ويندوز
    fcntl = None                        # type: ignore[assignment]
    HAS_FCNTL = False


class AlreadyRunningError(RuntimeError):
    """نسخة أخرى من البوت تعمل بالفعل على نفس ملف القفل."""


class SingleInstance:
    """
    مدير سياق يضمن تشغيل نسخة واحدة من البوت.

    الاستخدام:
        with SingleInstance(Path("data/bot.lock")):
            ...
    """

    def __init__(self, lock_path: Path | str) -> None:
        """تهيئة القفل بمسار ملفه (يُنشأ المجلد تلقائياً)."""
        self.lock_path = Path(lock_path)
        self._handle = None

    def acquire(self) -> None:
        """
        حجز القفل.

        الاستثناءات:
            AlreadyRunningError : نسخة أخرى تعمل بالفعل.
        """
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.lock_path, "a+", encoding="utf-8")   # noqa: SIM115 - يبقى مفتوحاً عمداً

        if HAS_FCNTL:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                handle.close()
                raise AlreadyRunningError(
                    f"نسخة أخرى من البوت تعمل بالفعل (القفل: {self.lock_path})"
                ) from exc
        else:
            handle.seek(0)
            existing = handle.read().strip()
            if existing.isdigit() and _pid_alive(int(existing)):
                handle.close()
                raise AlreadyRunningError(
                    f"نسخة أخرى من البوت تعمل بالفعل (PID {existing})"
                )

        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        self._handle = handle
        logger.debug("تم حجز قفل النسخة الواحدة: %s", self.lock_path)

    def release(self) -> None:
        """تحرير القفل وحذف ملفه (يُستدعى تلقائياً عند الخروج)."""
        if self._handle is None:
            return
        try:
            if HAS_FCNTL:
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        except OSError as exc:
            logger.warning("تعذر تحرير القفل: %s", exc)
        finally:
            self._handle.close()
            self._handle = None
            try:
                self.lock_path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("تعذر حذف ملف القفل: %s", exc)
            logger.debug("تم تحرير قفل النسخة الواحدة")

    def __enter__(self) -> "SingleInstance":
        """حجز القفل عند الدخول في سياق `with`."""
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """تحرير القفل عند الخروج مهما كان سبب الخروج."""
        self.release()


def _pid_alive(pid: int) -> bool:
    """فحص ما إذا كانت العملية بهذا الرقم ما تزال تعمل (مسار ويندوز)."""
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True
```

## الطبقة الوسيطة

### `middlewares/__init__.py`

```python
"""الطبقات الوسيطة التي تسبق كل معالج: المستخدم، الحظر، الصيانة، حد الاستخدام."""

from middlewares.context import (
    UserContextMiddleware,
    current_user,
    refresh_user,
    reload_user,
    require_user,
    services_of,
)
from middlewares.rate_limit import RateLimiter

__all__ = [
    "RateLimiter",
    "UserContextMiddleware",
    "current_user",
    "refresh_user",
    "reload_user",
    "require_user",
    "services_of",
]
```

### `middlewares/context.py`

```python
"""
الطبقة الوسيطة (Middleware) التي تسبق كل معالج.

تُسجَّل كـ`TypeHandler` في المجموعة `-10`، أي قبل أي معالج آخر، وتؤدي بالترتيب:

    1. تجاهل التحديثات خارج المحادثة الخاصة (البوت خاص بالاستخدام الفردي).
    2. تسجيل المستخدم أو تحديث بياناته (`UserService.get_or_create`).
    3. رفض المحظورين برسالة تشرح السبب.
    4. تطبيق وضع الصيانة على غير الأدمن.
    5. تطبيق حد معدل الاستخدام.
    6. تحديث آخر نشاط (مرة كل دقيقة على الأكثر لتفادي كتابة عند كل ضغطة).

أي رفض يوقف سلسلة المعالجات عبر `ApplicationHandlerStop` فلا يصل التحديث
إلى بقية المعالجات إطلاقاً — وهذا ما يمنع تكرار فحوص الأمان داخل كل معالج.
"""

from __future__ import annotations

import time

from telegram import Update
from telegram.ext import ApplicationHandlerStop, ContextTypes

from core.exceptions import MaintenanceModeError, UserBannedError, ValidationError
from database.models import User
from handlers.common.ui import answer_callback, send
from middlewares.rate_limit import RateLimiter
from services import ServiceContainer
from texts import ar
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: مفاتيح التخزين داخل `context.user_data`
USER_KEY = "db_user"
LAST_TOUCH_KEY = "last_activity_touch"

#: لا نحدّث «آخر نشاط» أكثر من مرة خلال هذه المدة (ثانية)
ACTIVITY_THROTTLE_SECONDS: float = 60.0


def services_of(context: ContextTypes.DEFAULT_TYPE) -> ServiceContainer:
    """
    جلب حاوية الخدمات المحقونة في التطبيق عند الإقلاع.

    الاستثناءات:
        RuntimeError : التطبيق لم يُهيَّأ بالخدمات (خطأ برمجي لا يحدث في التشغيل الصحيح).
    """
    services = context.application.bot_data.get("services")
    if services is None:
        raise RuntimeError("حاوية الخدمات غير محقونة في bot_data — راجع main.py")
    return services


def current_user(context: ContextTypes.DEFAULT_TYPE) -> User | None:
    """المستخدم المحمَّل من قاعدة البيانات لهذا التحديث (None إن لم يُحمَّل بعد)."""
    if context.user_data is None:
        return None
    return context.user_data.get(USER_KEY)


def require_user(context: ContextTypes.DEFAULT_TYPE) -> User:
    """
    المستخدم الحالي مع ضمان وجوده.

    الاستثناءات:
        RuntimeError : استُدعي معالج قبل الطبقة الوسيطة (خطأ تسجيل handlers).
    """
    user = current_user(context)
    if user is None:
        raise RuntimeError("المستخدم غير محمَّل — تأكد من تسجيل الطبقة الوسيطة في المجموعة -10")
    return user


def refresh_user(context: ContextTypes.DEFAULT_TYPE, user: User) -> None:
    """تحديث نسخة المستخدم المخزَّنة بعد أي تغيير (رصيد، دور، حظر)."""
    if context.user_data is not None:
        context.user_data[USER_KEY] = user


async def reload_user(context: ContextTypes.DEFAULT_TYPE) -> User:
    """إعادة قراءة المستخدم من قاعدة البيانات (بعد عملية غيّرت رصيده مثلاً)."""
    services = services_of(context)
    user = require_user(context)
    fresh = await services.users.get(user.id)
    if fresh is not None:
        refresh_user(context, fresh)
        return fresh
    return user


class UserContextMiddleware:
    """الطبقة الوسيطة الموحّدة لتحميل المستخدم وفرض قواعد الأمان."""

    def __init__(self, limiter: RateLimiter | None = None) -> None:
        """تهيئة الطبقة مع عدّاد حد الاستخدام (يُحقن في الاختبارات)."""
        self.limiter = limiter or RateLimiter()

    async def __call__(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        تنفيذ الفحوص قبل أي معالج.

        الاستثناءات:
            ApplicationHandlerStop : التحديث مرفوض (حظر/صيانة/حد استخدام/تسجيل مغلق).
        """
        telegram_user = update.effective_user
        chat = update.effective_chat
        if telegram_user is None or telegram_user.is_bot:
            raise ApplicationHandlerStop

        # البوت مصمَّم للمحادثة الخاصة فقط — المجموعات تُرفض برسالة واضحة مرة واحدة
        if chat is not None and chat.type != "private":
            await send(update, context, ar.ERR_NO_PRIVATE)
            raise ApplicationHandlerStop

        services = services_of(context)

        try:
            user, created = await services.users.get_or_create(
                telegram_id=telegram_user.id,
                username=telegram_user.username,
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
            )
        except ValidationError as exc:
            # التسجيل مغلق من الإعدادات ومحاولة إنشاء حساب جديد
            await answer_callback(update)
            await send(update, context, exc.user_message)
            raise ApplicationHandlerStop from None

        if context.user_data is not None:
            context.user_data[USER_KEY] = user
            context.user_data["is_new_user"] = created

        # 1) الحظر — يسبق كل شيء
        try:
            await services.auth.ensure_not_banned(user)
        except UserBannedError as exc:
            await answer_callback(update, "🚫")
            await send(update, context, exc.user_message)
            raise ApplicationHandlerStop from None

        # 2) الصيانة — لا تمنع الأدمن
        try:
            await services.auth.ensure_available(user)
        except MaintenanceModeError as exc:
            await answer_callback(update, "🚧")
            await send(update, context, exc.user_message)
            raise ApplicationHandlerStop from None

        # 3) حد معدل الاستخدام
        limit = await services.settings.get_int("rate_limit_actions_per_minute", 30)
        if not self.limiter.hit(telegram_user.id, limit):
            logger.info("تجاوز المستخدم %s حد الاستخدام (%s/دقيقة)", telegram_user.id, limit)
            await answer_callback(update, ar.ERR_RATE_LIMITED, alert=True)
            if update.callback_query is None:
                await send(update, context, ar.ERR_RATE_LIMITED)
            raise ApplicationHandlerStop

        # 4) تحديث آخر نشاط بتهدئة
        await self._touch_activity(context, services, user)

    async def _touch_activity(
        self, context: ContextTypes.DEFAULT_TYPE, services: ServiceContainer, user: User
    ) -> None:
        """تحديث وقت آخر نشاط مرة واحدة كل دقيقة على الأكثر."""
        if context.user_data is None:
            return
        now = time.monotonic()
        last = context.user_data.get(LAST_TOUCH_KEY, 0.0)
        if now - last < ACTIVITY_THROTTLE_SECONDS:
            return
        context.user_data[LAST_TOUCH_KEY] = now
        await services.users.touch_activity(user.id)
```

### `middlewares/rate_limit.py`

```python
"""
حد معدل الاستخدام (Rate limit) لكل مستخدم — حماية البوت وقاعدة البيانات.

الآلية: نافذة منزلقة بسيطة في الذاكرة لكل `telegram_id`؛ نحتفظ بأوقات آخر
الإجراءات ونرفض ما يتجاوز الحد المسموح خلال 60 ثانية.

لماذا في الذاكرة؟
    الحد وسيلة حماية من الضغط السريع لا سجل محاسبي؛ كتابته في قاعدة البيانات
    تعني كتابة عند كل ضغطة زر — وهو ما يُراد تجنّبه أصلاً. يُعاد ضبطه عند
    إعادة التشغيل وهذا مقبول ومقصود.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

#: طول النافذة الزمنية بالثواني
WINDOW_SECONDS: float = 60.0

#: أقصى عدد مستخدمين نحتفظ بسجلهم قبل التنظيف الدوري
MAX_TRACKED_USERS: int = 10_000


class RateLimiter:
    """عدّاد إجراءات لكل مستخدم ضمن نافذة زمنية منزلقة."""

    def __init__(self, *, window_seconds: float = WINDOW_SECONDS) -> None:
        """تهيئة العدّاد بنافذة زمنية محددة."""
        self._window = window_seconds
        self._hits: dict[int, deque[float]] = defaultdict(deque)

    def hit(self, user_id: int, limit: int) -> bool:
        """
        تسجيل إجراء جديد وفحص تجاوز الحد.

        المدخلات:
            user_id : معرف تيليجرام للمستخدم.
            limit   : الحد المسموح خلال النافذة (صفر أو أقل = بلا حد).

        المخرجات: True إذا كان الإجراء مسموحاً، False إذا تجاوز الحد.
        """
        if limit <= 0:
            return True

        now = time.monotonic()
        bucket = self._hits[user_id]
        threshold = now - self._window
        while bucket and bucket[0] < threshold:        # إسقاط ما خرج من النافذة
            bucket.popleft()

        if len(bucket) >= limit:
            return False

        bucket.append(now)
        if len(self._hits) > MAX_TRACKED_USERS:        # تنظيف وقائي للذاكرة
            self._cleanup(threshold)
        return True

    def remaining(self, user_id: int, limit: int) -> int:
        """عدد الإجراءات المتبقية للمستخدم في النافذة الحالية."""
        if limit <= 0:
            return limit
        bucket = self._hits.get(user_id)
        if not bucket:
            return limit
        threshold = time.monotonic() - self._window
        active = sum(1 for moment in bucket if moment >= threshold)
        return max(0, limit - active)

    def reset(self, user_id: int) -> None:
        """تصفير سجل مستخدم (يُستخدم في الاختبارات وعند رفع الحظر)."""
        self._hits.pop(user_id, None)

    def _cleanup(self, threshold: float) -> None:
        """إزالة المستخدمين الذين لم ينفّذوا أي إجراء داخل النافذة."""
        stale = [user_id for user_id, bucket in self._hits.items() if not bucket or bucket[-1] < threshold]
        for user_id in stale:
            self._hits.pop(user_id, None)
```

## الأدوات المشتركة للمعالجات

### `handlers/__init__.py`

```python
"""معالجات تيليجرام: واجهة العميل (المرحلة 3) ولوحة الأدمن (المرحلة 4)."""
```

### `handlers/common/__init__.py`

```python
"""معالجات مشتركة: العرض، الأخطاء، التنقل، والمسارات الاحتياطية."""
```

### `handlers/common/ui.py`

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

from telegram import InlineKeyboardMarkup, Update
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
                disable_web_page_preview=disable_preview,
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
            disable_web_page_preview=disable_preview,
        )
    except Forbidden:
        # المستخدم حظر البوت — تُعلَّم الحالة في قاعدة البيانات عبر مهمة الإشعارات
        logger.info("المستخدم %s حظر البوت", chat.id)
```

### `handlers/common/guards.py`

```python
"""
مُغلِّف موحّد لمعالجات الواجهة: تحويل أخطاء النظام إلى رسائل عربية مفهومة.

لماذا؟
    خدمات المرحلة 2 ترفع استثناءات مُصنّفة ولكل منها `user_message` عربي جاهز
    (رصيد غير كافٍ، كمية خارج الحدود، صلاحية مرفوضة...). بدل تكرار `try/except`
    في كل معالج، نلفّ المعالج مرة واحدة:

        • `SMMBotError`      ⇐ تُعرض رسالتها للمستخدم (خطأ متوقع، يُسجَّل كمعلومة).
        • أي استثناء آخر     ⇐ يُترك ليعالجه المعالج العام في `errors.py`
                               (يُسجَّل كخطأ حقيقي مع كامل التتبع).

ملاحظة مهمة لمحادثات `ConversationHandler`:
    عند الخطأ المتوقع نُعيد `None` فيبقى المستخدم في نفس الخطوة ويستطيع
    إعادة المحاولة فوراً — بدل إسقاط المحادثة كلها وإجباره على البدء من جديد.
"""

from __future__ import annotations

from functools import wraps
from typing import Awaitable, Callable, TypeVar

from telegram import Update
from telegram.ext import ContextTypes

from core.exceptions import SMMBotError
from handlers.common.ui import answer_callback, send
from utils.logging_setup import get_logger

logger = get_logger(__name__)

Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[object]]
_T = TypeVar("_T", bound=Handler)


def guarded(func: _T) -> _T:
    """
    لفّ معالج واجهة لعرض أخطاء النظام المتوقعة برسالة عربية بدل تعطّل البوت.

    المخرجات: نفس المعالج مغلَّفاً (يحافظ على قيمة الإرجاع في المسار الناجح).
    """

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(update, context)
        except SMMBotError as exc:
            user = update.effective_user
            logger.info(
                "خطأ متوقع في %s للمستخدم %s: %s",
                func.__name__, user.id if user else "?", exc,
            )
            await answer_callback(update)
            await send(update, context, exc.user_message)
            return None

    return wrapper  # type: ignore[return-value]
```

### `handlers/common/errors.py`

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
import traceback

from telegram import Update
from telegram.error import Forbidden, NetworkError, RetryAfter, TimedOut
from telegram.ext import ContextTypes

from handlers.common.ui import answer_callback, send
from texts import ar
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: أقصى طول نص خطأ يُخزَّن في قاعدة البيانات
MAX_STORED_ERROR = 4000


def _describe_update(update: object) -> str:
    """وصف مختصر للتحديث الذي سبّب الخطأ (بلا بيانات حساسة)."""
    if not isinstance(update, Update):
        return "تحديث غير معروف"
    user = update.effective_user
    parts = [f"user={user.id}" if user else "user=?"]
    if update.callback_query is not None:
        parts.append(f"button={update.callback_query.data}")
    elif update.effective_message is not None and update.effective_message.text:
        parts.append(f"text={update.effective_message.text[:40]!r}")
    return " | ".join(parts)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    المعالج العام: يُستدعى لكل استثناء لم يُلتقط داخل المعالجات.

    أخطاء الشبكة المؤقتة تُسجَّل كتحذير فقط (ستُعاد المحاولة تلقائياً)،
    وغيرها يُسجَّل كخطأ كامل في اللوق وقاعدة البيانات.
    """
    error = context.error
    description = _describe_update(update)

    if isinstance(error, (TimedOut, NetworkError, RetryAfter)):
        logger.warning("خطأ شبكة مؤقت (%s): %s", description, error)
        return

    if isinstance(error, Forbidden):
        # المستخدم حظر البوت — نعلّمه في قاعدة البيانات ولا نزعج اللوق بخطأ كامل
        logger.info("المستخدم حظر البوت (%s)", description)
        await _mark_blocked(update, context)
        return

    trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    logger.error("خطأ غير متوقع (%s): %s\n%s", description, error, trace)

    await _store_error(context, description, error, trace)

    if isinstance(update, Update):
        await answer_callback(update)
        await send(update, context, ar.ERR_GENERIC)


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

### `handlers/common/fallbacks.py`

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
from texts import ar
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
    try:
        data = unpack(raw)
        outdated = not data.is_current_version
    except CallbackError:
        outdated = False

    logger.info("زر غير معالَج: %r (الإصدار الحالي v%s)", raw, CALLBACK_VERSION)
    message = ar.ERR_OLD_BUTTON if outdated else ar.ERR_UNKNOWN_BUTTON
    await answer_callback(update, message, alert=True)
    await render(update, context, message, main_menu_kb())


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

### `handlers/common/navigation.py`

```python
"""
شاشة البداية والقائمة الرئيسية والأوامر العامة.

يشمل:
    /start  : تسجيل/ترحيب ثم القائمة الرئيسية.
    /help   : شرح مختصر لطريقة الاستخدام.
    /id     : عرض معرف تيليجرام (يطلبه الدعم أحياناً).
    nav:home: العودة للقائمة الرئيسية من أي شاشة.
    nav:page: زر عدّاد الصفحات — يعرض موضع المستخدم بدل أن يكون زراً صامتاً.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.callback_data import unpack
from keyboards.user_kb import main_menu_kb
from middlewares.context import require_user, services_of
from texts import ar
from utils.formatters import money_text, safe


async def main_menu_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    بناء نص القائمة الرئيسية بأرقام حقيقية (رصيد، طلبات نشطة، تذاكر مفتوحة).

    المخرجات: نص HTML جاهز للعرض.
    """
    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    summary = await services.users.summary(user)
    return ar.MAIN_MENU_BODY.format(
        balance=money_text(user.balance_units, symbol),
        active_orders=summary.active_orders,
        open_tickets=summary.tickets_open,
    )


@guarded
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الأمر /start: رسالة ترحيب (مختلفة للجديد) ثم القائمة الرئيسية."""
    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    is_new = bool(context.user_data and context.user_data.get("is_new_user"))

    if is_new:
        welcome = await services.settings.get_str(
            "welcome_message", "أهلاً بك في بوت خدمات التواصل الاجتماعي."
        )
        text = ar.WELCOME_NEW.format(
            name=safe(user.first_name or "", limit=30),
            welcome=safe(welcome),
            balance=money_text(user.balance_units, symbol),
        )
    else:
        text = ar.WELCOME_BACK.format(
            name=safe(user.first_name or "", limit=30),
            balance=money_text(user.balance_units, symbol),
        )

    await send(update, context, text)
    await send(update, context, await main_menu_text(context), main_menu_kb())


@guarded
async def home_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """زر «القائمة الرئيسية» من أي شاشة."""
    await answer_callback(update)
    await render(update, context, await main_menu_text(context), main_menu_kb())


@guarded
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الأمر /help: شرح خطوات الاستخدام والأوامر المتاحة."""
    await send(update, context, ar.HELP_TEXT, main_menu_kb())


@guarded
async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الأمر /id: عرض معرف المستخدم في تيليجرام."""
    user = require_user(context)
    await send(update, context, ar.ID_TEXT.format(telegram_id=user.telegram_id))


@guarded
async def page_indicator_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    زر عدّاد الصفحات: يعرض موضع المستخدم الحالي كتنبيه منبثق.

    سبب وجوده: القاعدة تمنع الأزرار بلا وظيفة — فحتى زر العرض يفعل شيئاً مفيداً.
    """
    data = unpack(update.callback_query.data if update.callback_query else None)
    await answer_callback(
        update, ar.PAGE_INFO.format(page=data.int_arg(0, 1), pages=data.int_arg(1, 1))
    )
```

## لوحات الأزرار والنصوص والتنسيق

### `keyboards/__init__.py`

```python
"""حزمة لوحات الأزرار: بناء كل الأزرار في مكان واحد (المرحلة 3)."""
```

### `keyboards/callback_data.py`

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

#: كل المساحات المعروفة — تُستخدم في اختبار «لا أزرار بلا وظيفة»
ALL_NAMESPACES: tuple[str, ...] = (
    NS_NAV, NS_CATALOG, NS_NEW, NS_ORDERS, NS_WALLET, NS_DEPOSIT, NS_SUPPORT, NS_ACCOUNT, NS_FLOW,
)
```

### `keyboards/common_kb.py`

```python
"""
أزرار مشتركة بين كل الشاشات: رجوع، إلغاء، تأكيد، تخطي، وترقيم الصفحات.

قاعدة الواجهة المعتمدة (المرحلة 0 — البند 4.4):
    • كل شاشة فيها «🔙 رجوع» وكل محادثة فيها «❌ إلغاء».
    • الترقيم موحّد: ⬅️ السابق | 📄 2/5 | التالي ➡️
    • زر عدّاد الصفحات ليس زراً ميتاً: ضغطه يعرض موضعك الحالي كتنبيه.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from keyboards.callback_data import (
    NS_FLOW,
    NS_NAV,
    pack,
)
from texts import ar

# --------------------------- أزرار مفردة ------------------------------- #


def home_button() -> InlineKeyboardButton:
    """زر العودة إلى القائمة الرئيسية."""
    return InlineKeyboardButton(ar.BTN_HOME, callback_data=pack(NS_NAV, "home"))


def back_button(namespace: str, action: str, *args: object, label: str = ar.BTN_BACK) -> InlineKeyboardButton:
    """زر رجوع إلى شاشة محددة (يُمرَّر هدفه صراحة حتى لا يضيع المستخدم)."""
    return InlineKeyboardButton(label, callback_data=pack(namespace, action, *args))


def cancel_button(label: str = ar.BTN_CANCEL) -> InlineKeyboardButton:
    """زر إلغاء المحادثة الحالية (يعمل داخل كل ConversationHandler)."""
    return InlineKeyboardButton(label, callback_data=pack(NS_FLOW, "cancel"))


def confirm_button(label: str = ar.BTN_CONFIRM) -> InlineKeyboardButton:
    """زر تأكيد الخطوة الأخيرة في المحادثة."""
    return InlineKeyboardButton(label, callback_data=pack(NS_FLOW, "confirm"))


def skip_button(label: str = ar.BTN_SKIP) -> InlineKeyboardButton:
    """زر تخطي خطوة اختيارية داخل المحادثة."""
    return InlineKeyboardButton(label, callback_data=pack(NS_FLOW, "skip"))


# --------------------------- صفوف جاهزة -------------------------------- #


def cancel_markup() -> InlineKeyboardMarkup:
    """لوحة فيها زر إلغاء فقط (تُرفق بكل سؤال داخل المحادثات)."""
    return InlineKeyboardMarkup([[cancel_button()]])


def confirm_cancel_markup() -> InlineKeyboardMarkup:
    """لوحة تأكيد/إلغاء لخطوة المراجعة النهائية."""
    return InlineKeyboardMarkup([[confirm_button(), cancel_button()]])


def skip_cancel_markup() -> InlineKeyboardMarkup:
    """لوحة تخطي/إلغاء لخطوة اختيارية."""
    return InlineKeyboardMarkup([[skip_button(), cancel_button()]])


def pagination_row(
    namespace: str, action: str, *, page: int, total_pages: int, prefix_args: tuple[object, ...] = ()
) -> list[InlineKeyboardButton]:
    """
    بناء صف ترقيم موحّد لأي قائمة.

    المدخلات:
        namespace/action : وجهة أزرار التنقل.
        page/total_pages : الصفحة الحالية وعددها الكلي.
        prefix_args      : وسائط تسبق رقم الصفحة في الزر (مثل معرف التصنيف).

    المخرجات: صف أزرار (قد يكون فارغاً إذا كانت صفحة واحدة فقط).
    """
    if total_pages <= 1:
        return []
    row: list[InlineKeyboardButton] = []
    if page > 1:
        row.append(
            InlineKeyboardButton(ar.BTN_PREV, callback_data=pack(namespace, action, *prefix_args, page - 1))
        )
    row.append(
        InlineKeyboardButton(
            f"📄 {page}/{total_pages}", callback_data=pack(NS_NAV, "page", page, total_pages)
        )
    )
    if page < total_pages:
        row.append(
            InlineKeyboardButton(ar.BTN_NEXT, callback_data=pack(namespace, action, *prefix_args, page + 1))
        )
    return row


def back_home_row(namespace: str | None = None, action: str | None = None, *args: object) -> list[InlineKeyboardButton]:
    """
    صف سفلي موحّد: رجوع (إن وُجدت وجهة) + القائمة الرئيسية.

    يُستخدم في أسفل كل شاشة حتى لا يعلق المستخدم في أي مكان.
    """
    row: list[InlineKeyboardButton] = []
    if namespace and action:
        row.append(back_button(namespace, action, *args))
    row.append(home_button())
    return row
```

### `keyboards/user_kb.py`

```python
"""
لوحات أزرار واجهة العميل — كل شاشة لها دالة واحدة تبني أزرارها.

مبدأ ملزم: **لا زر بلا وظيفة**. كل `callback_data` هنا يقابله معالج مسجَّل في
`handlers/registry.py`، ويتحقق من ذلك اختبار `tests/integration/test_no_dead_buttons.py`.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from database.models import (
    Notification,
    Order,
    Payment,
    PaymentMethod,
    Service,
    ServiceCategory,
    SupportTicket,
)
from core.enums import OrderStatus, PaymentStatus
from keyboards.callback_data import (
    NS_ACCOUNT,
    NS_CATALOG,
    NS_DEPOSIT,
    NS_FLOW,
    NS_NEW,
    NS_ORDERS,
    NS_SUPPORT,
    NS_WALLET,
    pack,
)
from keyboards.common_kb import back_home_row, home_button, pagination_row
from texts import ar
from utils.formatters import money_text, order_list_line, ticket_list_line

#: تصفية قوائم الطلبات المعروضة للمستخدم (الرمز ⇐ الحالات المشمولة)
ORDER_FILTERS: dict[str, tuple[str, tuple[str, ...]]] = {
    "all": (ar.FILTER_ALL, ()),
    "active": (
        ar.FILTER_ACTIVE,
        (
            OrderStatus.PENDING,
            OrderStatus.SUBMITTING,
            OrderStatus.SUBMIT_UNCERTAIN,
            OrderStatus.SUBMITTED,
            OrderStatus.IN_PROGRESS,
        ),
    ),
    "done": (ar.FILTER_COMPLETED, (OrderStatus.COMPLETED, OrderStatus.PARTIAL)),
    "rfnd": (
        ar.FILTER_REFUNDED,
        (OrderStatus.REFUNDED, OrderStatus.CANCELED, OrderStatus.FAILED),
    ),
}


# ============================ القائمة الرئيسية ========================== #


def main_menu_kb() -> InlineKeyboardMarkup:
    """القائمة الرئيسية — ست شاشات في ثلاثة صفوف."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(ar.BTN_SERVICES, callback_data=pack(NS_CATALOG, "list", 1)),
                InlineKeyboardButton(ar.BTN_WALLET, callback_data=pack(NS_WALLET, "home")),
            ],
            [
                InlineKeyboardButton(ar.BTN_ORDERS, callback_data=pack(NS_ORDERS, "list", "all", 1)),
                InlineKeyboardButton(ar.BTN_SUPPORT, callback_data=pack(NS_SUPPORT, "home")),
            ],
            [
                InlineKeyboardButton(ar.BTN_ACCOUNT, callback_data=pack(NS_ACCOUNT, "home")),
                InlineKeyboardButton(ar.BTN_INFO, callback_data=pack(NS_ACCOUNT, "info")),
            ],
        ]
    )


# ============================== الخدمات ================================ #


def categories_kb(categories: list[ServiceCategory]) -> InlineKeyboardMarkup:
    """أزرار التصنيفات المتاحة (زرّان في كل صف)."""
    rows: list[list[InlineKeyboardButton]] = []
    for index in range(0, len(categories), 2):
        chunk = categories[index : index + 2]
        rows.append(
            [
                InlineKeyboardButton(category.title, callback_data=pack(NS_CATALOG, "open", category.id, 1))
                for category in chunk
            ]
        )
    rows.append([home_button()])
    return InlineKeyboardMarkup(rows)


def services_kb(
    services: list[Service], *, category_id: int, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """أزرار خدمات تصنيف مع ترقيم صفحات وزر رجوع للتصنيفات."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                f"{service.name} — {money_text(service.price_per_1000_units, symbol)}/1000",
                callback_data=pack(NS_CATALOG, "svc", service.id, category_id, page),
            )
        ]
        for service in services
    ]
    nav = pagination_row(
        NS_CATALOG, "open", page=page, total_pages=total_pages, prefix_args=(category_id,)
    )
    if nav:
        rows.append(nav)
    rows.append(back_home_row(NS_CATALOG, "list", 1))
    return InlineKeyboardMarkup(rows)


def service_card_kb(service: Service, *, category_id: int, page: int) -> InlineKeyboardMarkup:
    """بطاقة الخدمة: زر الطلب + الرجوع لقائمة الخدمات."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(ar.BTN_ORDER_NOW, callback_data=pack(NS_NEW, "start", service.id))],
            back_home_row(NS_CATALOG, "open", category_id, page),
        ]
    )


def insufficient_balance_kb(category_id: int, page: int) -> InlineKeyboardMarkup:
    """لوحة تُعرض عند عدم كفاية الرصيد: شحن مباشر أو رجوع."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(ar.BTN_DEPOSIT_NOW, callback_data=pack(NS_DEPOSIT, "start"))],
            back_home_row(NS_CATALOG, "open", category_id, page),
        ]
    )


# ============================== طلباتي ================================= #


def orders_filters_row(current: str) -> list[InlineKeyboardButton]:
    """صف أزرار تصفية الطلبات مع تمييز التصفية الحالية."""
    row: list[InlineKeyboardButton] = []
    for code, (label, _statuses) in ORDER_FILTERS.items():
        mark = "• " if code == current else ""
        row.append(InlineKeyboardButton(f"{mark}{label}", callback_data=pack(NS_ORDERS, "list", code, 1)))
    return row


def orders_kb(
    orders: list[Order], *, filter_code: str, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """قائمة طلبات المستخدم مع التصفية والترقيم."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                order_list_line(order, symbol=symbol),
                callback_data=pack(NS_ORDERS, "view", order.id, filter_code, page),
            )
        ]
        for order in orders
    ]
    rows.append(orders_filters_row(filter_code))
    nav = pagination_row(
        NS_ORDERS, "list", page=page, total_pages=total_pages, prefix_args=(filter_code,)
    )
    if nav:
        rows.append(nav)
    rows.append([home_button()])
    return InlineKeyboardMarkup(rows)


def order_card_kb(
    order: Order, *, filter_code: str, page: int, can_cancel: bool
) -> InlineKeyboardMarkup:
    """
    بطاقة الطلب.

    زر الإلغاء يظهر فقط عندما يسمح به منطق الخدمة فعلاً — لا زر معطّل ولا زر كاذب.
    """
    rows: list[list[InlineKeyboardButton]] = []
    if can_cancel:
        rows.append(
            [InlineKeyboardButton(ar.BTN_ORDER_CANCEL, callback_data=pack(NS_ORDERS, "cancel", order.id))]
        )
    rows.append(
        [InlineKeyboardButton(ar.BTN_ORDER_TICKET, callback_data=pack(NS_SUPPORT, "neworder", order.id))]
    )
    rows.append(back_home_row(NS_ORDERS, "list", filter_code, page))
    return InlineKeyboardMarkup(rows)


def order_cancel_confirm_kb(order_id: int) -> InlineKeyboardMarkup:
    """تأكيد إلغاء الطلب (خطوة إضافية قبل أي حركة مالية)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(ar.BTN_CONFIRM, callback_data=pack(NS_ORDERS, "cancelyes", order_id)),
                InlineKeyboardButton(ar.BTN_BACK, callback_data=pack(NS_ORDERS, "view", order_id, "all", 1)),
            ]
        ]
    )


# ============================== المحفظة ================================ #


def wallet_kb() -> InlineKeyboardMarkup:
    """شاشة المحفظة: شحن، سجل العمليات، طلبات الشحن."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(ar.BTN_DEPOSIT_NOW, callback_data=pack(NS_DEPOSIT, "start"))],
            [
                InlineKeyboardButton(ar.BTN_WALLET_HISTORY, callback_data=pack(NS_WALLET, "history", 1)),
                InlineKeyboardButton(ar.BTN_MY_DEPOSITS, callback_data=pack(NS_DEPOSIT, "list", 1)),
            ],
            [home_button()],
        ]
    )


def history_kb(*, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """سجل العمليات المالية مع الترقيم."""
    rows: list[list[InlineKeyboardButton]] = []
    nav = pagination_row(NS_WALLET, "history", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(back_home_row(NS_WALLET, "home"))
    return InlineKeyboardMarkup(rows)


# =============================== الشحن ================================= #


def deposit_methods_kb(methods: list[PaymentMethod]) -> InlineKeyboardMarkup:
    """أزرار طرق الشحن المفعّلة."""
    rows = [
        [InlineKeyboardButton(method.name_ar, callback_data=pack(NS_DEPOSIT, "method", method.id))]
        for method in methods
    ]
    rows.append(back_home_row(NS_WALLET, "home"))
    return InlineKeyboardMarkup(rows)


def deposits_kb(payments: list[Payment], *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """قائمة طلبات الشحن السابقة مع إمكانية إلغاء المعلّق منها."""
    rows: list[list[InlineKeyboardButton]] = []
    for payment in payments:
        if payment.status == PaymentStatus.PENDING:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"🛑 إلغاء طلب #{payment.id}",
                        callback_data=pack(NS_DEPOSIT, "cancel", payment.id),
                    )
                ]
            )
    nav = pagination_row(NS_DEPOSIT, "list", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(back_home_row(NS_WALLET, "home"))
    return InlineKeyboardMarkup(rows)


# =============================== الدعم ================================= #


def support_kb() -> InlineKeyboardMarkup:
    """شاشة الدعم الرئيسية."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(ar.BTN_TICKET_NEW, callback_data=pack(NS_SUPPORT, "new"))],
            [InlineKeyboardButton(ar.BTN_TICKETS_LIST, callback_data=pack(NS_SUPPORT, "list", 1))],
            [home_button()],
        ]
    )


def ticket_categories_kb() -> InlineKeyboardMarkup:
    """أزرار تصنيفات التذكرة الجديدة."""
    rows = [
        [InlineKeyboardButton(label, callback_data=pack(NS_SUPPORT, "cat", code))]
        for code, label in ar.TICKET_CATEGORIES.items()
    ]
    rows.append([InlineKeyboardButton(ar.BTN_CANCEL, callback_data=pack(NS_FLOW, "cancel"))])
    return InlineKeyboardMarkup(rows)


def tickets_kb(tickets: list[SupportTicket], *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """قائمة تذاكر المستخدم."""
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(ticket_list_line(ticket), callback_data=pack(NS_SUPPORT, "view", ticket.id))]
        for ticket in tickets
    ]
    nav = pagination_row(NS_SUPPORT, "list", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(back_home_row(NS_SUPPORT, "home"))
    return InlineKeyboardMarkup(rows)


def ticket_card_kb(ticket: SupportTicket) -> InlineKeyboardMarkup:
    """بطاقة التذكرة: الرد والإغلاق (تظهر فقط ما دامت مفتوحة)."""
    rows: list[list[InlineKeyboardButton]] = []
    if ticket.is_open:
        rows.append(
            [
                InlineKeyboardButton(ar.BTN_TICKET_REPLY, callback_data=pack(NS_SUPPORT, "reply", ticket.id)),
                InlineKeyboardButton(ar.BTN_TICKET_CLOSE, callback_data=pack(NS_SUPPORT, "close", ticket.id)),
            ]
        )
    else:
        rows.append(
            [InlineKeyboardButton(ar.BTN_TICKET_REPLY, callback_data=pack(NS_SUPPORT, "reply", ticket.id))]
        )
    rows.append(back_home_row(NS_SUPPORT, "list", 1))
    return InlineKeyboardMarkup(rows)


# ============================== الحساب ================================= #


def account_kb(unread: int) -> InlineKeyboardMarkup:
    """شاشة الحساب مع عدّاد الإشعارات غير المقروءة."""
    badge = f" ({unread})" if unread else ""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(ar.BTN_NOTIFICATIONS + badge, callback_data=pack(NS_ACCOUNT, "notif", 1))],
            [
                InlineKeyboardButton(ar.BTN_WALLET, callback_data=pack(NS_WALLET, "home")),
                InlineKeyboardButton(ar.BTN_ORDERS, callback_data=pack(NS_ORDERS, "list", "all", 1)),
            ],
            [home_button()],
        ]
    )


def notifications_kb(*, page: int, total_pages: int, unread: int) -> InlineKeyboardMarkup:
    """صندوق الإشعارات مع زر تعليم الكل كمقروء."""
    rows: list[list[InlineKeyboardButton]] = []
    if unread:
        rows.append(
            [InlineKeyboardButton(ar.BTN_MARK_ALL_READ, callback_data=pack(NS_ACCOUNT, "readall"))]
        )
    nav = pagination_row(NS_ACCOUNT, "notif", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(back_home_row(NS_ACCOUNT, "home"))
    return InlineKeyboardMarkup(rows)


def info_kb() -> InlineKeyboardMarkup:
    """شاشة المعلومات."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(ar.BTN_SUPPORT, callback_data=pack(NS_SUPPORT, "home"))],
            [home_button()],
        ]
    )


def notifications_only_back_kb() -> InlineKeyboardMarkup:
    """لوحة رجوع بسيطة تُستخدم بعد الإجراءات السريعة."""
    return InlineKeyboardMarkup([back_home_row(NS_ACCOUNT, "home")])
```

### `texts/ar.py`

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

MAIN_MENU_BODY = (
    "🏠 <b>القائمة الرئيسية</b>\n\n"
    "💰 الرصيد: <b>{balance}</b>\n"
    "📦 طلبات نشطة: <b>{active_orders}</b>\n"
    "🎫 تذاكر مفتوحة: <b>{open_tickets}</b>\n\n"
    "اختر ما تريد:"
)

# ============================== الخدمات =============================== #

CATEGORIES_TITLE = "🛍 <b>اختر التصنيف</b>\n\nاختر المنصة التي تريد خدمة لها:"
CATEGORIES_EMPTY = "📭 لا توجد خدمات متاحة حالياً.\nتابعنا لاحقاً — يجري تجهيز الخدمات."
SERVICES_TITLE = "{emoji} <b>{category}</b>\n\nالصفحة {page} من {pages} — اختر خدمة:"
SERVICES_EMPTY = "📭 لا توجد خدمات في هذا التصنيف حالياً."

SERVICE_CARD = (
    "📄 <b>{name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "💵 السعر لكل 1000: <b>{price}</b>\n"
    "🔢 الحد الأدنى: <b>{min_quantity}</b>\n"
    "🔢 الحد الأقصى: <b>{max_quantity}</b>\n"
    "⏱ مدة التنفيذ: {avg_time}\n"
    "{description}"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "💰 رصيدك: <b>{balance}</b>"
)
BTN_ORDER_NOW = "🛒 اطلب الآن"
AVG_TIME_UNKNOWN = "غير محددة"

# ============================ مسار الطلب ============================== #

ORDER_ASK_LINK = (
    "🔗 <b>أرسل رابط الهدف</b>\n\n"
    "الخدمة: {service}\n\n"
    "أرسل الرابط كرسالة نصية (مثال: https://instagram.com/username).\n"
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
DEPOSIT_METHODS_EMPTY = "⚠️ لا توجد طرق شحن مفعّلة حالياً. تواصل مع الدعم."
DEPOSIT_ASK_AMOUNT = (
    "💵 <b>{method}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{instructions}\n"
    "{account}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{limits}\n\n"
    "أرسل <b>المبلغ الذي حوّلته</b> كرقم."
)
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
    "💵 المبلغ: <b>{amount}</b>\n"
    "🔢 رقم العملية: {reference}\n"
    "📸 الإيصال: {proof}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "سيراجع الفريق طلبك ويُضاف الرصيد بعد الاعتماد."
)
DEPOSIT_PROOF_ATTACHED = "مرفقة ✅"
DEPOSIT_PROOF_NONE = "بدون صورة"
DEPOSIT_CREATED = (
    "✅ <b>استلمنا طلب الشحن #{payment_id}</b>\n\n"
    "💵 المبلغ: {amount}\n"
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
ERR_OLD_BUTTON = "⚠️ هذا الزر من نسخة قديمة. اضغط /start لفتح القائمة المحدثة."
ERR_UNKNOWN_BUTTON = "⚠️ زر غير معروف. اضغط /start للعودة إلى القائمة."
ERR_SESSION_LOST = "⚠️ انتهت الجلسة. ابدأ من جديد عبر /start."
ERR_NOT_TEXT = "⚠️ أرسل رسالة نصية من فضلك."
ERR_RATE_LIMITED = "⏳ أبطئ قليلاً — أرسلت طلبات كثيرة خلال وقت قصير."
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

### `utils/formatters.py`

```python
"""
أدوات تنسيق العرض: تحويل بيانات قاعدة البيانات إلى نصوص عربية جاهزة للشاشة.

قاعدة: لا منطق أعمال هنا — تنسيق فقط. وأي رقم مالي يُنسَّق من النقاط الصحيحة
عبر `core.money` ولا يُحسب هنا إطلاقاً.
"""

from __future__ import annotations

from html import escape

from core.enums import (
    NotificationType,
    OrderStatus,
    PaymentStatus,
    TicketStatus,
    TransactionType,
)
from core.money import format_units
from utils.datetime_utils import to_local_text

#: أيقونة ووصف عربي لكل حالة طلب
ORDER_STATUS_LABELS: dict[str, str] = {
    OrderStatus.PENDING: "⏳ بانتظار الإرسال",
    OrderStatus.SUBMITTING: "📤 جاري الإرسال",
    OrderStatus.SUBMIT_UNCERTAIN: "❓ قيد المراجعة اليدوية",
    OrderStatus.SUBMITTED: "📨 أُرسل للمزود",
    OrderStatus.IN_PROGRESS: "🔄 قيد التنفيذ",
    OrderStatus.PARTIAL: "⚠️ نُفِّذ جزئياً",
    OrderStatus.COMPLETED: "✅ مكتمل",
    OrderStatus.CANCELED: "🛑 ملغي",
    OrderStatus.FAILED: "❌ فشل",
    OrderStatus.REFUNDED: "↩️ مسترجع",
}

#: وصف عربي لحالات طلب الشحن
PAYMENT_STATUS_LABELS: dict[str, str] = {
    PaymentStatus.PENDING: "⏳ قيد المراجعة",
    PaymentStatus.APPROVED: "✅ معتمد",
    PaymentStatus.REJECTED: "❌ مرفوض",
    PaymentStatus.CANCELLED: "🛑 ملغي",
    PaymentStatus.EXPIRED: "⌛ منتهي",
}

#: وصف عربي لحالات التذكرة
TICKET_STATUS_LABELS: dict[str, str] = {
    TicketStatus.OPEN: "🟢 مفتوحة",
    TicketStatus.PENDING_ADMIN: "⏳ بانتظار الدعم",
    TicketStatus.PENDING_USER: "💬 بانتظار ردك",
    TicketStatus.CLOSED: "🔒 مغلقة",
}

#: وصف عربي لأنواع الحركات المالية
TRANSACTION_LABELS: dict[str, str] = {
    TransactionType.DEPOSIT: "📥 شحن رصيد",
    TransactionType.ORDER: "🛒 دفع طلب",
    TransactionType.REFUND: "↩️ استرجاع",
    TransactionType.PARTIAL_REFUND: "↩️ استرجاع جزئي",
    TransactionType.MANUAL_CREDIT: "➕ إضافة إدارية",
    TransactionType.MANUAL_DEBIT: "➖ خصم إداري",
    TransactionType.WITHDRAW: "📤 سحب",
    TransactionType.ADJUSTMENT: "🔧 تسوية",
}

#: أيقونة لكل نوع إشعار (للعرض في صندوق إشعارات المستخدم)
NOTIFICATION_ICONS: dict[str, str] = {
    NotificationType.ORDER_CREATED: "🛒",
    NotificationType.ORDER_SUBMITTED: "📨",
    NotificationType.ORDER_IN_PROGRESS: "🔄",
    NotificationType.ORDER_COMPLETED: "✅",
    NotificationType.ORDER_PARTIAL: "⚠️",
    NotificationType.ORDER_FAILED: "❌",
    NotificationType.ORDER_CANCELED: "🛑",
    NotificationType.ORDER_REFUNDED: "↩️",
    NotificationType.PAYMENT_RECEIVED: "📥",
    NotificationType.PAYMENT_APPROVED: "✅",
    NotificationType.PAYMENT_REJECTED: "❌",
    NotificationType.BALANCE_CREDITED: "➕",
    NotificationType.BALANCE_DEBITED: "➖",
    NotificationType.TICKET_REPLIED: "💬",
    NotificationType.TICKET_CLOSED: "🔒",
    NotificationType.BROADCAST: "📣",
    NotificationType.SYSTEM: "ℹ️",
}


def order_status_text(status: str) -> str:
    """وصف عربي لحالة الطلب (مع إيموجي)."""
    return ORDER_STATUS_LABELS.get(status, f"❔ {status}")


def payment_status_text(status: str) -> str:
    """وصف عربي لحالة طلب الشحن."""
    return PAYMENT_STATUS_LABELS.get(status, f"❔ {status}")


def ticket_status_text(status: str) -> str:
    """وصف عربي لحالة التذكرة."""
    return TICKET_STATUS_LABELS.get(status, f"❔ {status}")


def transaction_type_text(tx_type: str) -> str:
    """وصف عربي لنوع الحركة المالية."""
    return TRANSACTION_LABELS.get(tx_type, f"❔ {tx_type}")


def notification_icon(notification_type: str) -> str:
    """أيقونة نوع الإشعار."""
    return NOTIFICATION_ICONS.get(notification_type, "🔔")


def money_text(units: int, symbol: str = "", decimals: int = 2) -> str:
    """عرض مبلغ من النقاط الصحيحة بصيغة قابلة للقراءة مع رمز العملة."""
    return format_units(units, symbol, decimals)


def safe(text: str | None, *, limit: int = 0) -> str:
    """
    تهريب نص المستخدم قبل عرضه بتنسيق HTML (حماية من كسر التنسيق أو الحقن).

    المدخلات:
        text  : النص الخام (قد يكون None).
        limit : قص النص عند هذا الطول مع إضافة «…» (صفر = بلا قص).
    """
    value = (text or "").strip()
    if limit and len(value) > limit:
        value = value[: limit - 1].rstrip() + "…"
    return escape(value, quote=False)


def datetime_text(iso_value: str | None, timezone: str = "Asia/Aden") -> str:
    """عرض تاريخ ISO بتوقيت المستخدم المحلي."""
    return to_local_text(iso_value, timezone)


def short_link(link: str, *, limit: int = 45) -> str:
    """اختصار رابط طويل للعرض داخل البطاقات."""
    return safe(link, limit=limit)


def transaction_line(transaction, *, symbol: str = "", timezone: str = "Asia/Aden") -> str:
    """سطر واحد يمثل حركة مالية في سجل العمليات."""
    sign = "+" if transaction.direction == "credit" else "−"
    amount = money_text(transaction.amount_units, symbol)
    label = transaction_type_text(transaction.type)
    when = datetime_text(transaction.created_at, timezone)
    return f"{label}\n   {sign}{amount} • الرصيد بعدها {money_text(transaction.balance_after_units, symbol)}\n   🕒 {when}"


def payment_line(payment, *, symbol: str = "", timezone: str = "Asia/Aden") -> str:
    """سطر واحد يمثل طلب شحن في قائمة طلبات الشحن."""
    status = payment_status_text(payment.status)
    amount = money_text(payment.amount_units, symbol)
    when = datetime_text(payment.created_at, timezone)
    return f"#{payment.id} • {amount} • {status}\n   🕒 {when}"


def notification_line(notification, *, timezone: str = "Asia/Aden") -> str:
    """سطر واحد يمثل إشعاراً في صندوق الإشعارات."""
    icon = notification_icon(notification.type)
    unread = "" if notification.is_read else " 🆕"
    when = datetime_text(notification.created_at, timezone)
    title = safe(notification.title or "", limit=60)
    body = safe(notification.message or "", limit=120)
    return f"{icon} <b>{title}</b>{unread}\n   {body}\n   🕒 {when}"


def order_list_line(order, *, symbol: str = "") -> str:
    """نص زر الطلب في قائمة الطلبات (سطر واحد قصير)."""
    code = order.public_code or f"#{order.id}"
    status = order_status_text(order.status).split(" ", 1)[0]
    return f"{status} {code} • {money_text(order.cost_units, symbol)}"


def ticket_list_line(ticket) -> str:
    """نص زر التذكرة في قائمة التذاكر."""
    status = ticket_status_text(ticket.status).split(" ", 1)[0]
    subject = safe(ticket.subject, limit=30)
    return f"{status} #{ticket.id} • {subject}"
```

## شاشات العميل

### `handlers/user/__init__.py`

```python
"""معالجات واجهة العميل: الخدمات، الطلبات، المحفظة، الشحن، الدعم، الحساب."""
```

### `handlers/user/catalog.py`

```python
"""
شاشات تصفح الخدمات: التصنيفات ← خدمات التصنيف (بصفحات) ← بطاقة الخدمة.

كل البيانات تأتي من `CatalogService`، ولا تُعرض خدمة غير متاحة للطلب
(معطّلة أو مؤرشفة أو مزودها متوقف) — القائمة نفسها مفلترة من طبقة الخدمات.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render
from keyboards.callback_data import unpack
from keyboards.user_kb import categories_kb, service_card_kb, services_kb
from middlewares.context import require_user, services_of
from texts import ar
from utils.formatters import money_text, safe

#: عدد الخدمات المعروضة في كل صفحة
PAGE_SIZE = 6


@guarded
async def categories_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض التصنيفات التي تحتوي خدمات متاحة فعلاً."""
    await answer_callback(update)
    services = services_of(context)
    categories = await services.catalog.categories()
    if not categories:
        await render(update, context, ar.CATEGORIES_EMPTY, categories_kb([]))
        return
    await render(update, context, ar.CATEGORIES_TITLE, categories_kb(categories))


@guarded
async def services_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض صفحة من خدمات تصنيف معيّن."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    category_id = data.int_arg(0)
    page_number = max(1, data.int_arg(1, 1))

    services = services_of(context)
    symbol = await services.settings.money_symbol()
    page = await services.catalog.services_page(category_id, page=page_number, page_size=PAGE_SIZE)

    categories = {category.id: category for category in await services.catalog.categories()}
    category = categories.get(category_id)
    if category is None or not page.items:
        await render(
            update,
            context,
            ar.SERVICES_EMPTY,
            services_kb([], category_id=category_id, page=1, total_pages=1, symbol=symbol),
        )
        return

    text = ar.SERVICES_TITLE.format(
        emoji=category.emoji,
        category=safe(category.name_ar),
        page=page.page,
        pages=page.total_pages,
    )
    await render(
        update,
        context,
        text,
        services_kb(
            page.items,
            category_id=category_id,
            page=page.page,
            total_pages=page.total_pages,
            symbol=symbol,
        ),
    )


@guarded
async def service_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة خدمة واحدة: السعر والحدود ومدة التنفيذ ورصيد المستخدم."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    service_id = data.int_arg(0)
    category_id = data.int_arg(1)
    page = max(1, data.int_arg(2, 1))

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    service = await services.catalog.get_available_service(service_id)

    description = f"📝 {safe(service.description, limit=300)}\n" if service.description else ""
    text = ar.SERVICE_CARD.format(
        name=safe(service.name),
        price=money_text(service.price_per_1000_units, symbol),
        min_quantity=service.min_quantity,
        max_quantity=service.max_quantity,
        avg_time=safe(service.avg_time_text) or ar.AVG_TIME_UNKNOWN,
        description=description,
        balance=money_text(user.balance_units, symbol),
    )
    await render(update, context, text, service_card_kb(service, category_id=category_id, page=page))
```

### `handlers/user/order_flow.py`

```python
"""
محادثة إنشاء طلب جديد (ConversationHandler).

المسار: بطاقة الخدمة ← 🔗 الرابط ← 🔢 الكمية ← 🧾 المراجعة ← ✅ تأكيد.

ضمانات مهمة:
    • `client_request_id` يُولَّد **مرة واحدة عند بدء المحادثة**، فالضغط المزدوج
      على «تأكيد» يُعيد نفس الطلب ولا ينشئ طلبين (منع تكرار من طبقة الخدمات).
    • التحقق من الرابط والكمية يتم عند الإدخال، وتتكرر الخطوة عند الخطأ بدل
      إسقاط المحادثة.
    • عدم كفاية الرصيد لا يُنهي المسار بصمت: تُعرض قيمة النقص مع زر شحن مباشر.
    • الإلغاء متاح في كل خطوة (زر ❌ أو الأمر /cancel) ولا يُخصم شيء قبل التأكيد.
"""

from __future__ import annotations

import uuid

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from core.exceptions import InsufficientBalanceError
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.callback_data import unpack
from keyboards.common_kb import cancel_markup, confirm_cancel_markup
from keyboards.user_kb import insufficient_balance_kb, main_menu_kb
from middlewares.context import reload_user, require_user, services_of
from texts import ar
from utils.formatters import money_text, safe, short_link

#: حالات المحادثة
ASK_LINK, ASK_QUANTITY, CONFIRM = range(3)

#: مفتاح بيانات المحادثة داخل `user_data`
FLOW_KEY = "order_flow"


def _flow(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """قراءة بيانات المحادثة الحالية (قاموس فارغ إن ضاعت الجلسة)."""
    if context.user_data is None:
        return {}
    return context.user_data.get(FLOW_KEY) or {}


def _clear(context: ContextTypes.DEFAULT_TYPE) -> None:
    """مسح بيانات المحادثة بعد انتهائها أو إلغائها."""
    if context.user_data is not None:
        context.user_data.pop(FLOW_KEY, None)


@guarded
async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء المحادثة من زر «🛒 اطلب الآن» وسؤال المستخدم عن الرابط."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    service_id = data.int_arg(0)

    services = services_of(context)
    service = await services.catalog.get_available_service(service_id)

    if context.user_data is not None:
        context.user_data[FLOW_KEY] = {
            "service_id": service.id,
            "service_name": service.name,
            # معرف فريد للطلب يُولَّد الآن: الضغط المزدوج على تأكيد لن يُنشئ طلبين
            "client_request_id": uuid.uuid4().hex,
        }

    await render(
        update,
        context,
        ar.ORDER_ASK_LINK.format(service=safe(service.name)),
        cancel_markup(),
    )
    return ASK_LINK


@guarded
async def receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال الرابط والتحقق منه ثم سؤال المستخدم عن الكمية."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, ar.ERR_NOT_TEXT, cancel_markup())
        return ASK_LINK

    flow = _flow(context)
    if not flow:
        await send(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    services = services_of(context)
    service = await services.catalog.get_available_service(flow["service_id"])

    from utils.validators import validate_link      # تحقق فوري قبل إزعاج المستخدم بخطوة أخرى

    link = validate_link(message.text, pattern=service.link_pattern)
    flow["link"] = link

    await send(
        update,
        context,
        ar.ORDER_ASK_QUANTITY.format(
            service=safe(service.name),
            link=short_link(link),
            min_quantity=service.min_quantity,
            max_quantity=service.max_quantity,
        ),
        cancel_markup(),
    )
    return ASK_QUANTITY


@guarded
async def receive_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال الكمية وحساب التكلفة وعرض ملخص الطلب قبل التأكيد."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, ar.ERR_NOT_TEXT, cancel_markup())
        return ASK_QUANTITY

    flow = _flow(context)
    if not flow or "link" not in flow:
        await send(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    service = await services.catalog.get_available_service(flow["service_id"])

    quote = await services.catalog.quote(service, message.text)
    flow["quantity"] = quote.quantity
    flow["cost_units"] = quote.cost_units

    balance = user.balance_units
    if balance < quote.cost_units:
        text = ar.ORDER_SUMMARY_NO_BALANCE.format(
            service=safe(service.name),
            link=short_link(flow["link"]),
            quantity=quote.quantity,
            cost=money_text(quote.cost_units, symbol),
            balance=money_text(balance, symbol),
            missing=money_text(quote.cost_units - balance, symbol),
        )
        await send(update, context, text, insufficient_balance_kb(service.category_id, 1))
        _clear(context)
        return ConversationHandler.END

    text = ar.ORDER_SUMMARY.format(
        service=safe(service.name),
        link=short_link(flow["link"]),
        quantity=quote.quantity,
        cost=money_text(quote.cost_units, symbol),
        balance=money_text(balance, symbol),
        balance_after=money_text(balance - quote.cost_units, symbol),
    )
    await send(update, context, text, confirm_cancel_markup())
    return CONFIRM


@guarded
async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تأكيد الطلب: إنشاؤه عبر `OrderService` (خصم + سجل + إشعار في معاملة واحدة)."""
    await answer_callback(update)
    flow = _flow(context)
    if not flow or "quantity" not in flow:
        await render(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()

    try:
        order = await services.orders.create_order(
            user,
            service_id=flow["service_id"],
            link=flow["link"],
            quantity=flow["quantity"],
            client_request_id=flow["client_request_id"],
        )
    except InsufficientBalanceError:
        # قد يكون الرصيد أُنفق في محادثة أخرى بين المراجعة والتأكيد
        service = await services.catalog.get_available_service(flow["service_id"])
        fresh = await reload_user(context)
        await render(
            update,
            context,
            ar.ORDER_SUMMARY_NO_BALANCE.format(
                service=safe(service.name),
                link=short_link(flow["link"]),
                quantity=flow["quantity"],
                cost=money_text(flow["cost_units"], symbol),
                balance=money_text(fresh.balance_units, symbol),
                missing=money_text(max(0, flow["cost_units"] - fresh.balance_units), symbol),
            ),
            insufficient_balance_kb(service.category_id, 1),
        )
        _clear(context)
        return ConversationHandler.END

    fresh = await reload_user(context)
    await render(
        update,
        context,
        ar.ORDER_CREATED.format(
            code=order.public_code or f"#{order.id}",
            service=safe(order.service_name_snapshot),
            quantity=order.quantity,
            cost=money_text(order.cost_units, symbol),
            balance=money_text(fresh.balance_units, symbol),
        ),
        main_menu_kb(),
    )
    _clear(context)
    return ConversationHandler.END


@guarded
async def cancel_order_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء المحادثة في أي خطوة (زر ❌ أو الأمر /cancel) — لا خصم ولا طلب."""
    await answer_callback(update)
    _clear(context)
    if update.callback_query is not None:
        await render(update, context, ar.ORDER_CANCELLED_FLOW, main_menu_kb())
    else:
        await send(update, context, ar.ORDER_CANCELLED_FLOW, main_menu_kb())
    return ConversationHandler.END
```

### `handlers/user/orders.py`

```python
"""
شاشات «📦 طلباتي»: القائمة بالتصفية والترقيم، بطاقة الطلب، وإلغاء الطلب.

قواعد:
    • المستخدم يرى طلباته فقط (الفحص داخل `OrderService.get_for_user`).
    • زر الإلغاء يظهر فقط عندما يكون الإلغاء ممكناً فعلاً حسب حالة الطلب
      وإعداد `user_cancel_before_submit` — لا أزرار كاذبة.
    • الإلغاء يمر بخطوة تأكيد، والاسترجاع يتم عبر المحفظة المركزية وحدها.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from core.enums import OrderStatus
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render
from keyboards.callback_data import unpack
from keyboards.user_kb import (
    ORDER_FILTERS,
    main_menu_kb,
    order_card_kb,
    order_cancel_confirm_kb,
    orders_kb,
)
from middlewares.context import reload_user, require_user, services_of
from texts import ar
from utils.formatters import (
    datetime_text,
    money_text,
    order_status_text,
    safe,
    short_link,
)

#: عدد الطلبات في الصفحة الواحدة
PAGE_SIZE = 6

#: الحالات التي يُسمح فيها للمستخدم بطلب الإلغاء (قبل وصول الطلب للمزود)
USER_CANCELABLE = (OrderStatus.PENDING,)


async def _can_cancel(context: ContextTypes.DEFAULT_TYPE, order) -> bool:
    """هل يُسمح للمستخدم بإلغاء هذا الطلب الآن؟ (حالة الطلب + إعداد النظام)."""
    if order.status not in USER_CANCELABLE:
        return False
    services = services_of(context)
    return await services.settings.get_bool("user_cancel_before_submit", True)


@guarded
async def orders_list_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة طلبات المستخدم حسب التصفية المختارة."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    filter_code = data.arg(0, "all")
    if filter_code not in ORDER_FILTERS:
        filter_code = "all"
    page = max(1, data.int_arg(1, 1))

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    statuses = list(ORDER_FILTERS[filter_code][1]) or None

    total = await services.orders.count_for_user(user, statuses=statuses)
    total_pages = max(1, -(-total // PAGE_SIZE))
    page = min(page, total_pages)
    orders = await services.orders.list_for_user(
        user, statuses=statuses, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE
    )

    if not orders:
        await render(
            update,
            context,
            ar.ORDERS_EMPTY,
            orders_kb([], filter_code=filter_code, page=1, total_pages=1, symbol=symbol),
        )
        return

    text = ar.ORDERS_TITLE.format(
        filter_name=ORDER_FILTERS[filter_code][0], page=page, pages=total_pages
    )
    await render(
        update,
        context,
        text,
        orders_kb(orders, filter_code=filter_code, page=page, total_pages=total_pages, symbol=symbol),
    )


@guarded
async def order_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة طلب واحد بكل تفاصيله الحقيقية."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    order_id = data.int_arg(0)
    filter_code = data.arg(1, "all")
    page = max(1, data.int_arg(2, 1))

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    order = await services.orders.get_for_user(user, order_id)

    progress = ""
    if order.delivered_quantity is not None or order.remains is not None:
        delivered = order.delivered_quantity or 0
        remains = order.remains if order.remains is not None else max(0, order.quantity - delivered)
        progress = ar.ORDER_PROGRESS_LINE.format(delivered=delivered, remains=remains)

    refund = ""
    if order.refund_amount_units:
        refund = ar.ORDER_REFUND_LINE.format(refund=money_text(order.refund_amount_units, symbol))

    error = ""
    if order.last_error and order.status in {OrderStatus.FAILED, OrderStatus.REFUNDED}:
        error = ar.ORDER_ERROR_LINE.format(error=safe(order.last_error, limit=120))

    text = ar.ORDER_CARD.format(
        code=order.public_code or f"#{order.id}",
        service=safe(order.service_name_snapshot),
        link=short_link(order.link),
        quantity=order.quantity,
        progress=progress,
        cost=money_text(order.cost_units, symbol),
        refund=refund,
        status=order_status_text(order.status),
        created=datetime_text(order.created_at),
        error=error,
    )
    await render(
        update,
        context,
        text,
        order_card_kb(
            order,
            filter_code=filter_code,
            page=page,
            can_cancel=await _can_cancel(context, order),
        ),
    )


@guarded
async def order_cancel_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """خطوة التأكيد قبل إلغاء الطلب (لا حركة مالية قبل الضغط على تأكيد)."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    order_id = data.int_arg(0)

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    order = await services.orders.get_for_user(user, order_id)

    text = ar.ORDER_CANCEL_CONFIRM.format(
        code=order.public_code or f"#{order.id}",
        cost=money_text(order.cost_units, symbol),
    )
    await render(update, context, text, order_cancel_confirm_kb(order.id))


@guarded
async def order_cancel_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تنفيذ الإلغاء فعلياً عبر `OrderService` واسترجاع المبلغ كاملاً."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    order_id = data.int_arg(0)

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    order = await services.orders.get_for_user(user, order_id)

    refunded = await services.orders.cancel_by_user(user, order_id)
    await reload_user(context)

    await render(
        update,
        context,
        ar.ORDER_CANCEL_DONE.format(
            code=order.public_code or f"#{order.id}",
            refund=money_text(refunded, symbol),
        ),
        main_menu_kb(),
    )
```

### `handlers/user/wallet.py`

```python
"""
شاشات «💰 المحفظة»: الرصيد وملخص الإيداع والإنفاق، وسجل العمليات بصفحات.

كل الأرقام تُقرأ من دفتر الحركات (`transactions`) ومن صف المستخدم — لا حساب
مالي يجري في طبقة الواجهة إطلاقاً.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render
from keyboards.callback_data import unpack
from keyboards.user_kb import history_kb, wallet_kb
from middlewares.context import require_user, services_of
from texts import ar
from utils.formatters import money_text, transaction_line

#: عدد الحركات المعروضة في الصفحة
PAGE_SIZE = 5


@guarded
async def wallet_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الشاشة الرئيسية للمحفظة."""
    await answer_callback(update)
    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()

    text = ar.WALLET_TITLE.format(
        balance=money_text(user.balance_units, symbol),
        deposited=money_text(user.total_deposited_units, symbol),
        spent=money_text(user.total_spent_units, symbol),
    )
    await render(update, context, text, wallet_kb())


@guarded
async def history_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """سجل العمليات المالية للمستخدم مع ترقيم الصفحات."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    page = max(1, data.int_arg(0, 1))

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()

    total = await services.wallet.history_count(user.id)
    total_pages = max(1, -(-total // PAGE_SIZE))
    page = min(page, total_pages)
    movements = await services.wallet.history(
        user.id, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE
    )

    if not movements:
        await render(update, context, ar.HISTORY_EMPTY, history_kb(page=1, total_pages=1))
        return

    lines = "\n\n".join(transaction_line(item, symbol=symbol) for item in movements)
    text = ar.HISTORY_TITLE.format(page=page, pages=total_pages, lines=lines)
    await render(update, context, text, history_kb(page=page, total_pages=total_pages))
```

### `handlers/user/deposit.py`

```python
"""
محادثة شحن الرصيد (ConversationHandler) + شاشة طلبات الشحن السابقة.

المسار: 🏦 اختيار الطريقة ← 💵 المبلغ ← 🧾 رقم العملية ← 📸 الإيصال (اختياري)
        ← 🧾 مراجعة ← ✅ إرسال للمراجعة.

قواعد:
    • لا يُضاف أي رصيد هنا إطلاقاً — الطلب يُسجَّل بحالة «قيد المراجعة» فقط،
      والرصيد يُضاف من لوحة الأدمن عبر `PaymentService.approve` (المرحلة 4).
    • حدود المبلغ تأتي من طريقة الدفع وإلا من الإعدادات العامة.
    • رقم العملية يُفحص فوراً ضد التكرار (منع إعادة استخدام نفس الإيصال).
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.callback_data import unpack
from keyboards.common_kb import cancel_markup, confirm_cancel_markup, skip_cancel_markup
from keyboards.user_kb import deposit_methods_kb, deposits_kb, main_menu_kb, wallet_kb
from middlewares.context import require_user, services_of
from texts import ar
from utils.formatters import money_text, payment_line, safe
from core.money import from_units
from utils.validators import (
    parse_amount_units,
    validate_amount_range,
    validate_transaction_reference,
)

#: حالات المحادثة
CHOOSE_METHOD, ASK_AMOUNT, ASK_REFERENCE, ASK_PROOF, CONFIRM = range(5)

#: مفتاح بيانات المحادثة
FLOW_KEY = "deposit_flow"

#: عدد طلبات الشحن المعروضة في الصفحة
PAGE_SIZE = 5


def _flow(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """قراءة بيانات محادثة الشحن الحالية."""
    if context.user_data is None:
        return {}
    return context.user_data.get(FLOW_KEY) or {}


def _clear(context: ContextTypes.DEFAULT_TYPE) -> None:
    """مسح بيانات المحادثة بعد الانتهاء أو الإلغاء."""
    if context.user_data is not None:
        context.user_data.pop(FLOW_KEY, None)


async def _summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """عرض مراجعة نهائية لطلب الشحن قبل إرساله."""
    flow = _flow(context)
    services = services_of(context)
    symbol = await services.settings.money_symbol()
    text = ar.DEPOSIT_SUMMARY.format(
        method=safe(flow.get("method_name", "")),
        amount=money_text(flow.get("amount_units", 0), symbol),
        reference=safe(flow.get("reference") or "—"),
        proof=ar.DEPOSIT_PROOF_ATTACHED if flow.get("proof_file_id") else ar.DEPOSIT_PROOF_NONE,
    )
    await send(update, context, text, confirm_cancel_markup())
    return CONFIRM


@guarded
async def start_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء محادثة الشحن بعرض طرق الدفع المفعّلة."""
    await answer_callback(update)
    services = services_of(context)
    methods = await services.payments.active_methods()
    if not methods:
        await render(update, context, ar.DEPOSIT_METHODS_EMPTY, wallet_kb())
        return ConversationHandler.END

    if context.user_data is not None:
        context.user_data[FLOW_KEY] = {}
    await render(update, context, ar.DEPOSIT_METHODS_TITLE, deposit_methods_kb(methods))
    return CHOOSE_METHOD


@guarded
async def choose_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ الطريقة المختارة وعرض تعليماتها وحدودها وسؤال المستخدم عن المبلغ."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    method_id = data.int_arg(0)

    services = services_of(context)
    method = await services.payments.get_method(method_id)
    limits = await services.payments.limits_text(method)

    if context.user_data is not None:
        context.user_data[FLOW_KEY] = {
            "method_id": method.id,
            "method_name": method.name_ar,
            "requires_proof": bool(method.requires_proof),
        }

    text = ar.DEPOSIT_ASK_AMOUNT.format(
        method=safe(method.name_ar),
        instructions=safe(method.instructions_ar or ""),
        account=safe(method.account_details or ""),
        limits=limits,
    )
    await render(update, context, text, cancel_markup())
    return ASK_AMOUNT


@guarded
async def receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال المبلغ والتحقق من الحدود قبل الانتقال لرقم العملية."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, ar.ERR_NOT_TEXT, cancel_markup())
        return ASK_AMOUNT

    flow = _flow(context)
    if not flow.get("method_id"):
        await send(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    services = services_of(context)
    symbol = await services.settings.money_symbol()
    method = await services.payments.get_method(flow["method_id"])
    minimum, maximum = await services.payments.method_limits(method)

    amount_units = parse_amount_units(message.text)
    validate_amount_range(
        amount_units, min_units=minimum, max_units=maximum, label="مبلغ الشحن"
    )
    flow["amount_units"] = amount_units
    # نحتفظ بالمبلغ نصاً عشرياً دقيقاً (لا float) لأن خدمة الدفع تُعيد تحليله بنفسها
    flow["raw_amount"] = str(from_units(amount_units))

    if flow.get("requires_proof"):
        await send(
            update,
            context,
            ar.DEPOSIT_ASK_REFERENCE.format(amount=money_text(amount_units, symbol)),
            cancel_markup(),
        )
        return ASK_REFERENCE

    return await _summary(update, context)


@guarded
async def receive_reference(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال رقم عملية التحويل ثم طلب صورة الإيصال (اختيارية)."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, ar.ERR_NOT_TEXT, cancel_markup())
        return ASK_REFERENCE

    flow = _flow(context)
    if not flow.get("amount_units"):
        await send(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    flow["reference"] = validate_transaction_reference(message.text, required=True)
    await send(update, context, ar.DEPOSIT_ASK_PROOF, skip_cancel_markup())
    return ASK_PROOF


@guarded
async def receive_proof(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال صورة الإيصال وحفظ معرف الملف لعرضه لاحقاً للأدمن."""
    message = update.effective_message
    flow = _flow(context)
    if not flow:
        await send(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    if message is not None and message.photo:
        flow["proof_file_id"] = message.photo[-1].file_id      # أعلى دقة متاحة
        flow["proof_file_type"] = "photo"
    elif message is not None and message.document:
        flow["proof_file_id"] = message.document.file_id
        flow["proof_file_type"] = "document"
    else:
        await send(update, context, ar.DEPOSIT_ASK_PROOF, skip_cancel_markup())
        return ASK_PROOF

    return await _summary(update, context)


@guarded
async def skip_proof(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تخطي إرفاق الإيصال والانتقال إلى المراجعة."""
    await answer_callback(update)
    return await _summary(update, context)


@guarded
async def confirm_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إرسال طلب الشحن للمراجعة (بلا أي إضافة رصيد)."""
    await answer_callback(update)
    flow = _flow(context)
    if not flow.get("amount_units"):
        await render(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()

    payment = await services.payments.create_payment(
        user,
        method_id=flow["method_id"],
        raw_amount=flow["raw_amount"],
        transaction_reference=flow.get("reference"),
        proof_file_id=flow.get("proof_file_id"),
        proof_file_type=flow.get("proof_file_type"),
    )

    await render(
        update,
        context,
        ar.DEPOSIT_CREATED.format(
            payment_id=payment.id, amount=money_text(payment.amount_units, symbol)
        ),
        main_menu_kb(),
    )
    _clear(context)
    return ConversationHandler.END


@guarded
async def cancel_deposit_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء محادثة الشحن في أي خطوة."""
    await answer_callback(update)
    _clear(context)
    if update.callback_query is not None:
        await render(update, context, ar.CANCELLED, wallet_kb())
    else:
        await send(update, context, ar.CANCELLED, wallet_kb())
    return ConversationHandler.END


# ---------------------- شاشات خارج المحادثة ---------------------------- #


@guarded
async def deposits_list_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة طلبات الشحن السابقة مع إمكانية إلغاء المعلّق منها."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    page = max(1, data.int_arg(0, 1))

    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()

    payments = await services.payments.list_for_user(
        user, limit=PAGE_SIZE + 1, offset=(page - 1) * PAGE_SIZE
    )
    has_next = len(payments) > PAGE_SIZE
    payments = payments[:PAGE_SIZE]
    total_pages = page + 1 if has_next else page

    if not payments:
        await render(update, context, ar.DEPOSITS_EMPTY, deposits_kb([], page=1, total_pages=1))
        return

    lines = "\n\n".join(payment_line(item, symbol=symbol) for item in payments)
    await render(
        update,
        context,
        ar.DEPOSITS_TITLE.format(lines=lines),
        deposits_kb(payments, page=page, total_pages=total_pages),
    )


@guarded
async def cancel_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إلغاء طلب شحن معلّق أرسله المستخدم بالخطأ."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    payment_id = data.int_arg(0)

    services = services_of(context)
    user = require_user(context)
    await services.payments.cancel_by_user(user, payment_id)
    await render(update, context, ar.DEPOSIT_CANCELLED.format(payment_id=payment_id), wallet_kb())
```

### `handlers/user/support.py`

```python
"""
شاشات ومحادثات «🎫 الدعم الفني».

يشمل:
    • الشاشة الرئيسية وقائمة التذاكر وبطاقة التذكرة مع كامل المحادثة.
    • محادثة فتح تذكرة جديدة: 🗂 التصنيف ← ✏️ العنوان ← 📝 الشرح.
    • محادثة إضافة رد على تذكرة قائمة.
    • فتح تذكرة مرتبطة بطلب مباشرة من بطاقة الطلب.
    • إغلاق التذكرة من المستخدم نفسه.

قاعدة من طبقة الخدمات تُحترم هنا: تذكرة مفتوحة واحدة لكل مستخدم — ومحاولة
فتح ثانية تُرفض برسالة توجّهه إلى تذكرته الحالية.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.callback_data import unpack
from keyboards.common_kb import cancel_markup
from keyboards.user_kb import (
    main_menu_kb,
    support_kb,
    ticket_card_kb,
    ticket_categories_kb,
    tickets_kb,
)
from middlewares.context import require_user, services_of
from texts import ar
from utils.formatters import datetime_text, safe, ticket_status_text

#: حالات محادثة التذكرة الجديدة
ASK_CATEGORY, ASK_SUBJECT, ASK_MESSAGE = range(3)

#: حالة محادثة الرد على تذكرة
ASK_REPLY = 10

#: مفاتيح بيانات المحادثات
NEW_FLOW_KEY = "ticket_flow"
REPLY_FLOW_KEY = "ticket_reply_flow"

#: عدد التذاكر في الصفحة
PAGE_SIZE = 6

#: أقصى عدد رسائل تُعرض داخل بطاقة التذكرة
MESSAGES_LIMIT = 10


def _flow(context: ContextTypes.DEFAULT_TYPE, key: str) -> dict:
    """قراءة بيانات محادثة الدعم المطلوبة."""
    if context.user_data is None:
        return {}
    return context.user_data.get(key) or {}


def _clear(context: ContextTypes.DEFAULT_TYPE, key: str) -> None:
    """مسح بيانات محادثة الدعم."""
    if context.user_data is not None:
        context.user_data.pop(key, None)


# =============================== الشاشات ================================ #


@guarded
async def support_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الشاشة الرئيسية للدعم مع عدد التذاكر المفتوحة."""
    await answer_callback(update)
    services = services_of(context)
    user = require_user(context)
    summary = await services.users.summary(user)
    await render(
        update, context, ar.SUPPORT_TITLE.format(open_count=summary.tickets_open), support_kb()
    )


@guarded
async def tickets_list_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة تذاكر المستخدم بصفحات."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    page = max(1, data.int_arg(0, 1))

    services = services_of(context)
    user = require_user(context)
    tickets = await services.tickets.list_for_user(
        user, limit=PAGE_SIZE + 1, offset=(page - 1) * PAGE_SIZE
    )
    has_next = len(tickets) > PAGE_SIZE
    tickets = tickets[:PAGE_SIZE]
    total_pages = page + 1 if has_next else page

    if not tickets:
        await render(update, context, ar.TICKETS_EMPTY, tickets_kb([], page=1, total_pages=1))
        return

    await render(
        update,
        context,
        ar.TICKETS_TITLE.format(page=page, pages=total_pages),
        tickets_kb(tickets, page=page, total_pages=total_pages),
    )


@guarded
async def ticket_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة التذكرة مع آخر رسائل المحادثة (وتُعلَّم كمقروءة من طرف المستخدم)."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    ticket_id = data.int_arg(0)

    services = services_of(context)
    user = require_user(context)
    ticket = await services.tickets.get_for_user(user, ticket_id)
    messages = await services.tickets.conversation_for_user(user, ticket_id, limit=MESSAGES_LIMIT)

    lines = []
    for item in messages:
        is_user = item.sender_type == "user"
        lines.append(
            ar.TICKET_MESSAGE_LINE.format(
                icon="👤" if is_user else "🛠",
                sender="أنت" if is_user else "الدعم",
                time=datetime_text(item.created_at),
                text=safe(item.message, limit=400),
            )
        )

    text = ar.TICKET_CARD.format(
        ticket_id=ticket.id,
        subject=safe(ticket.subject),
        category=ar.TICKET_CATEGORIES.get(ticket.category, ticket.category),
        status=ticket_status_text(ticket.status),
        updated=datetime_text(ticket.last_message_at or ticket.updated_at),
        messages="\n".join(lines),
    )
    await render(update, context, text, ticket_card_kb(ticket))


@guarded
async def close_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إغلاق التذكرة بطلب من صاحبها."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    ticket_id = data.int_arg(0)

    services = services_of(context)
    user = require_user(context)
    await services.tickets.close_by_user(user, ticket_id)
    await render(update, context, ar.TICKET_CLOSED_BY_USER.format(ticket_id=ticket_id), support_kb())


# ======================= محادثة تذكرة جديدة ============================= #


@guarded
async def start_new_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء محادثة فتح تذكرة: اختيار التصنيف."""
    await answer_callback(update)
    if context.user_data is not None:
        context.user_data[NEW_FLOW_KEY] = {}
    await render(update, context, ar.TICKET_ASK_CATEGORY, ticket_categories_kb())
    return ASK_CATEGORY


@guarded
async def start_ticket_for_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    فتح تذكرة مرتبطة بطلب مباشرة من بطاقة الطلب.

    يُتخطى اختيار التصنيف (تصنيفها «مشكلة في طلب») ويُربط رقم الطلب بالتذكرة.
    """
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    order_id = data.int_arg(0)

    services = services_of(context)
    user = require_user(context)
    order = await services.orders.get_for_user(user, order_id)   # تحقق من ملكية الطلب

    if context.user_data is not None:
        context.user_data[NEW_FLOW_KEY] = {
            "category": "order",
            "related_order_id": order.id,
            "subject": f"مشكلة في الطلب {order.public_code or order.id}",
        }
    await render(
        update,
        context,
        ar.TICKET_ASK_MESSAGE_ORDER.format(
            code=order.public_code or f"#{order.id}",
            service=safe(order.service_name_snapshot),
        ),
        cancel_markup(),
    )
    return ASK_MESSAGE


@guarded
async def choose_ticket_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ تصنيف التذكرة وسؤال المستخدم عن العنوان."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    category = data.arg(0, "other")
    if category not in ar.TICKET_CATEGORIES:
        category = "other"

    flow = _flow(context, NEW_FLOW_KEY)
    flow["category"] = category
    if context.user_data is not None:
        context.user_data[NEW_FLOW_KEY] = flow

    await render(update, context, ar.TICKET_ASK_SUBJECT, cancel_markup())
    return ASK_SUBJECT


@guarded
async def receive_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال عنوان التذكرة ثم طلب شرح المشكلة."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, ar.ERR_NOT_TEXT, cancel_markup())
        return ASK_SUBJECT

    from utils.validators import validate_subject       # تحقق مبكر من الطول

    flow = _flow(context, NEW_FLOW_KEY)
    flow["subject"] = validate_subject(message.text)
    if context.user_data is not None:
        context.user_data[NEW_FLOW_KEY] = flow

    await send(update, context, ar.TICKET_ASK_MESSAGE, cancel_markup())
    return ASK_MESSAGE


@guarded
async def receive_ticket_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال شرح المشكلة وإنشاء التذكرة فعلياً."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, ar.ERR_NOT_TEXT, cancel_markup())
        return ASK_MESSAGE

    flow = _flow(context, NEW_FLOW_KEY)
    if not flow:
        await send(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    services = services_of(context)
    user = require_user(context)
    ticket = await services.tickets.create_ticket(
        user,
        subject=flow.get("subject") or message.text[:60],
        message=message.text,
        category=flow.get("category", "other"),
        related_order_id=flow.get("related_order_id"),
        attachment_file_id=message.photo[-1].file_id if message.photo else None,
        attachment_type="photo" if message.photo else None,
    )

    await send(
        update,
        context,
        ar.TICKET_CREATED.format(ticket_id=ticket.id, subject=safe(ticket.subject)),
        support_kb(),
    )
    _clear(context, NEW_FLOW_KEY)
    return ConversationHandler.END


# ========================= محادثة الرد ================================== #


@guarded
async def start_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء محادثة إضافة رد على تذكرة."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    ticket_id = data.int_arg(0)

    services = services_of(context)
    user = require_user(context)
    await services.tickets.get_for_user(user, ticket_id)       # تحقق من الملكية قبل السؤال

    if context.user_data is not None:
        context.user_data[REPLY_FLOW_KEY] = {"ticket_id": ticket_id}
    await render(update, context, ar.TICKET_ASK_REPLY.format(ticket_id=ticket_id), cancel_markup())
    return ASK_REPLY


@guarded
async def receive_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إرسال رد المستخدم إلى فريق الدعم."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, ar.ERR_NOT_TEXT, cancel_markup())
        return ASK_REPLY

    flow = _flow(context, REPLY_FLOW_KEY)
    if not flow.get("ticket_id"):
        await send(update, context, ar.ERR_SESSION_LOST, main_menu_kb())
        return ConversationHandler.END

    services = services_of(context)
    user = require_user(context)
    await services.tickets.reply_as_user(
        user,
        flow["ticket_id"],
        message.text,
        attachment_file_id=message.photo[-1].file_id if message.photo else None,
        attachment_type="photo" if message.photo else None,
    )

    await send(update, context, ar.TICKET_REPLY_SENT, support_kb())
    _clear(context, REPLY_FLOW_KEY)
    return ConversationHandler.END


@guarded
async def cancel_support_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء أي محادثة دعم جارية."""
    await answer_callback(update)
    _clear(context, NEW_FLOW_KEY)
    _clear(context, REPLY_FLOW_KEY)
    if update.callback_query is not None:
        await render(update, context, ar.CANCELLED, support_kb())
    else:
        await send(update, context, ar.CANCELLED, support_kb())
    return ConversationHandler.END
```

### `handlers/user/account.py`

```python
"""
شاشات «👤 حسابي» و«🔔 إشعاراتي» و«ℹ️ معلومات».

لا شيء هنا يُعدِّل بيانات مالية؛ عرض فقط + تعليم الإشعارات كمقروءة.
"""

from __future__ import annotations

from core.constants import APP_VERSION
from telegram import Update
from telegram.ext import ContextTypes

from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render
from keyboards.callback_data import unpack
from keyboards.user_kb import account_kb, info_kb, notifications_kb
from middlewares.context import require_user, services_of
from texts import ar
from utils.formatters import datetime_text, money_text, notification_line, safe

#: عدد الإشعارات في الصفحة
PAGE_SIZE = 5


@guarded
async def account_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة الحساب: المعرف، الدور، الرصيد، عدد الطلبات والتذاكر، تاريخ الانضمام."""
    await answer_callback(update)
    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    summary = await services.users.summary(user)
    unread = await services.notifications.unread_count(user.id)

    text = ar.ACCOUNT_CARD.format(
        telegram_id=user.telegram_id,
        name=safe(user.display_name, limit=40),
        role=ar.ROLE_LABELS.get(user.role, user.role),
        balance=money_text(user.balance_units, symbol),
        orders_count=summary.orders_count,
        active_orders=summary.active_orders,
        payments_count=summary.payments_count,
        tickets_open=summary.tickets_open,
        joined=datetime_text(user.created_at),
    )
    await render(update, context, text, account_kb(unread))


@guarded
async def notifications_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """صندوق إشعارات المستخدم بصفحات."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    page = max(1, data.int_arg(0, 1))

    services = services_of(context)
    user = require_user(context)
    unread = await services.notifications.unread_count(user.id)

    items = await services.notifications.user_inbox(
        user.id, limit=PAGE_SIZE + 1, offset=(page - 1) * PAGE_SIZE
    )
    has_next = len(items) > PAGE_SIZE
    items = items[:PAGE_SIZE]
    total_pages = page + 1 if has_next else page

    if not items:
        await render(
            update, context, ar.NOTIFICATIONS_EMPTY, notifications_kb(page=1, total_pages=1, unread=0)
        )
        return

    lines = "\n\n".join(notification_line(item) for item in items)
    text = ar.NOTIFICATIONS_TITLE.format(unread=unread, page=page, pages=total_pages, lines=lines)
    await render(
        update, context, text, notifications_kb(page=page, total_pages=total_pages, unread=unread)
    )


@guarded
async def mark_all_read(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تعليم كل إشعارات المستخدم كمقروءة ثم إعادة عرض الصندوق."""
    services = services_of(context)
    user = require_user(context)
    count = await services.notifications.mark_all_read(user.id)
    await answer_callback(update, ar.MARKED_READ.format(count=count))
    await notifications_screen(update, context)


@guarded
async def info_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة المعلومات: اسم البوت، الشروط، حساب الدعم، الإصدار."""
    await answer_callback(update)
    services = services_of(context)
    bot_name = await services.settings.get_str("bot_name", "SMM Bot")
    rules = await services.settings.get_str("rules_text", "")
    support = await services.settings.get_str("support_username", "")

    text = ar.INFO_TITLE.format(
        bot_name=safe(bot_name),
        rules=safe(rules) or ar.INFO_NO_RULES,
        support=safe(support) or ar.INFO_NO_SUPPORT,
        version=APP_VERSION,
    )
    await render(update, context, text, info_kb())
```

## المهام الدورية

### `jobs/__init__.py`

```python
"""
جدولة المهام الدورية على JobQueue الخاص بـpython-telegram-bot.

لماذا JobQueue بدل asyncio.create_task يدوياً؟
    لأنه يعمل داخل حلقة التطبيق نفسها، ويتوقف معه بنظافة عند الإغلاق،
    ويمنحنا `first`/`interval` ومعالج أخطاء موحّداً. لا حاجة لعفريت خارجي.

كل الفترات الزمنية تُقرأ من جدول الإعدادات (`settings`) لا من ثوابت في الكود،
فيستطيع الأدمن ضبط إيقاع النظام من داخل البوت لاحقاً دون إعادة نشر.
"""

from __future__ import annotations

from telegram.ext import Application

from jobs.maintenance_jobs import auto_close_tickets, expire_old_payments
from jobs.notification_jobs import dispatch_notifications
from jobs.order_jobs import alert_stuck_orders, check_active_orders, submit_pending_orders
from services import ServiceContainer
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: الحد الأدنى المقبول لأي فترة تكرار (حماية من قيمة إعداد خاطئة تُغرق النظام)
MIN_INTERVAL_SECONDS = 5

__all__ = ["schedule_jobs", "run_startup_recovery"]


async def _interval(services: ServiceContainer, key: str, default: int) -> float:
    """قراءة فترة تكرار من الإعدادات مع فرض حد أدنى آمن."""
    value = await services.settings.get_int(key, default)
    return float(max(MIN_INTERVAL_SECONDS, value))


async def schedule_jobs(application: Application, services: ServiceContainer) -> list[str]:
    """
    جدولة كل المهام الدورية وإرجاع أسمائها (تُطبع في سجل الإقلاع).

    المهام:
        notifications_dispatch : إرسال الإشعارات المتراكمة.
        orders_submit          : إرسال الطلبات المعلّقة للمزود.
        orders_check           : متابعة الطلبات النشطة حتى حالتها النهائية.
        payments_expire        : إنهاء صلاحية طلبات الشحن القديمة.
        tickets_auto_close     : إغلاق التذاكر الراكدة.
        orders_stuck_alert     : تنبيه الأدمن بالطلبات المتوقفة.
    """
    queue = application.job_queue
    if queue is None:
        raise RuntimeError(
            "JobQueue غير متاح — ثبّت الحزمة بالشكل: pip install 'python-telegram-bot[job-queue]'"
        )

    plan = [
        (
            "notifications_dispatch",
            dispatch_notifications,
            await _interval(services, "notification_dispatch_seconds", 10),
            5.0,
        ),
        (
            "orders_submit",
            submit_pending_orders,
            await _interval(services, "order_submit_interval_seconds", 30),
            12.0,
        ),
        (
            "orders_check",
            check_active_orders,
            await _interval(services, "order_check_interval_seconds", 120),
            25.0,
        ),
        ("payments_expire", expire_old_payments, 900.0, 60.0),
        ("tickets_auto_close", auto_close_tickets, 3600.0, 120.0),
        ("orders_stuck_alert", alert_stuck_orders, 3600.0, 300.0),
    ]

    names: list[str] = []
    for name, callback, interval, first in plan:
        queue.run_repeating(callback, interval=interval, first=first, name=name)
        names.append(f"{name}({int(interval)}s)")
    logger.info("تمت جدولة %s مهمة دورية: %s", len(names), ", ".join(names))
    return names


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

### `jobs/telegram_sender.py`

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
from telegram import Bot
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
                disable_web_page_preview=True,
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
```

### `jobs/notification_jobs.py`

```python
"""
مهمة إرسال الإشعارات من الطابور إلى تيليجرام.

لماذا طابور بدل الإرسال المباشر؟
    لأن الإرسال المباشر داخل المعاملة يربط نجاح العملية المالية بنجاح الشبكة.
    هنا: العملية تُسجَّل في قاعدة البيانات وتُدرج رسالتها في `notifications`،
    ثم تأتي هذه المهمة كل بضع ثوانٍ وتُرسل ما تراكم. انقطاع الشبكة يؤخر
    الإشعار فقط ولا يُفسد أي عملية.
"""

from __future__ import annotations

from telegram.ext import ContextTypes

from jobs.telegram_sender import TelegramNotificationSender
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: أقصى عدد إشعارات تُرسل في الجولة الواحدة (حماية من حدود تيليجرام)
BATCH_LIMIT = 20


async def dispatch_notifications(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    جولة إرسال واحدة: تحجز دفعة من الطابور وترسلها ثم تسجّل الحصيلة.

    الأخطاء هنا لا تُسقط المهمة الدورية: خدمة الإشعارات تُصنّف كل فشل
    (محظور / مؤقت / نهائي) وتتعامل معه، وما يصل إلى هنا يُسجَّل في اللوق.
    """
    services = context.application.bot_data["services"]
    sender = TelegramNotificationSender(context.bot)
    report = await services.notifications.dispatch_pending(sender, limit=BATCH_LIMIT)
    if report.claimed:
        logger.info("جولة إشعارات: %s", report.as_dict())
```

### `jobs/order_jobs.py`

```python
"""
مهام دورة حياة الطلب: الإرسال للمزود، فحص الحالة، تنبيه الطلبات العالقة.

منطق العمل كله داخل `OrderService` (المرحلة 2) — هذه الملفات مجرد جدولة
زمنية تستدعيه. الفائدة: يبقى المنطق قابلاً للاختبار بلا تيليجرام ولا مؤقتات.
"""

from __future__ import annotations

from telegram.ext import ContextTypes

from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: عدد الطلبات التي تُرسل للمزود في الجولة الواحدة
SUBMIT_BATCH = 5

#: عدد الطلبات التي تُفحص حالتها في الجولة الواحدة
CHECK_BATCH = 20


async def submit_pending_orders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    إرسال الطلبات المعلّقة إلى المزودين.

    الحجز (lease) داخل الخدمة يمنع إرسال الطلب مرتين حتى لو تداخلت جولتان.
    """
    services = context.application.bot_data["services"]
    report = await services.orders.process_pending_orders(worker="submitter", limit=SUBMIT_BATCH)
    if report.claimed:
        logger.info("جولة إرسال الطلبات: %s", report.as_dict())


async def check_active_orders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    فحص حالة الطلبات النشطة عند المزود وتحديثها (إكمال/جزئي/فشل + استرجاع).

    هذه هي المهمة التي تجعل الطلب «يمشي لوحده» حتى حالته النهائية.
    """
    services = context.application.bot_data["services"]
    report = await services.orders.process_due_orders(worker="checker", limit=CHECK_BATCH)
    if report.claimed:
        logger.info("جولة فحص الطلبات: %s", report.as_dict())


async def alert_stuck_orders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """تنبيه الأدمن بالطلبات التي لم تتقدم منذ مدة طويلة (مؤشر خلل صامت)."""
    services = context.application.bot_data["services"]
    count = await services.orders.alert_stuck_orders()
    if count:
        logger.warning("طلبات متوقفة بلا تقدم: %s", count)
```

### `jobs/maintenance_jobs.py`

```python
"""
مهام الصيانة الدورية: انتهاء صلاحية طلبات الشحن، وإغلاق التذاكر الراكدة.

كلاهما يمنع تراكم سجلات معلّقة إلى ما لا نهاية، وكلاهما يُشعر صاحب الشأن
بما حدث بدل أن «يختفي» طلبه بصمت.
"""

from __future__ import annotations

from telegram.ext import ContextTypes

from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: عدد طلبات الشحن التي تُفحص صلاحيتها في الجولة الواحدة
EXPIRE_BATCH = 50


async def expire_old_payments(context: ContextTypes.DEFAULT_TYPE) -> None:
    """تعليم طلبات الشحن التي تجاوزت مهلة المراجعة كمنتهية + إشعار أصحابها."""
    services = context.application.bot_data["services"]
    count = await services.payments.expire_due(limit=EXPIRE_BATCH)
    if count:
        logger.info("طلبات شحن انتهت صلاحيتها: %s", count)


async def auto_close_tickets(context: ContextTypes.DEFAULT_TYPE) -> None:
    """إغلاق تذاكر الدعم التي لم يرد عليها أصحابها خلال المدة المحددة في الإعدادات."""
    services = context.application.bot_data["services"]
    count = await services.tickets.auto_close_idle()
    if count:
        logger.info("تذاكر أُغلقت تلقائياً لركودها: %s", count)
```

## أدوات الفحص

### `scripts/boot_check.py`

```python
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

from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ConversationHandler  # noqa: E402

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
        ok("طرق الدفع الفعّالة:", len(await services.payments.active_methods()))
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
```

## الاختبارات

### `tests/telegram_fakes.py`

```python
"""
بدائل اختبارية لواجهة تيليجرام (بلا أي اتصال بالشبكة).

الفكرة: نستخدم كائنات `telegram.Update` **حقيقية** (مبنية عبر `de_json`) حتى
نختبر نفس المسارات التي تعمل في الإنتاج، لكن مع بوت مزيّف يسجّل ما كان
سيُرسَل بدل إرساله. هكذا يفحص الاختبار النص النهائي والأزرار الفعلية.
"""

from __future__ import annotations

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

    # ------------------------------ الإرسال ------------------------------ #

    async def send_message(
        self, chat_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None, **kwargs: Any
    ) -> FakeMessage:
        """تسجيل رسالة جديدة وإرجاع كائن يشبه رسالة تيليجرام."""
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
        self.sent.append(SentMessage("edit", chat_id, text, reply_markup, kwargs))
        return FakeMessage(message_id or 0, chat_id or 0, text)

    async def send_photo(self, chat_id: int, photo: Any, caption: str = "", **kwargs: Any) -> FakeMessage:
        """تسجيل إرسال صورة (يُستخدم في إشعارات الإثباتات لاحقاً)."""
        self.sent.append(SentMessage("photo", chat_id, caption, kwargs.get("reply_markup"), kwargs))
        return FakeMessage(next(self._message_ids), chat_id, caption)

    async def answer_callback_query(
        self, callback_query_id: str, text: str | None = None, show_alert: bool = False, **kwargs: Any
    ) -> bool:
        """تسجيل الرد على ضغطة زر (إزالة مؤشر الانتظار)."""
        self.answers.append({"id": callback_query_id, "text": text, "alert": show_alert})
        return True

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

### `tests/unit/test_callback_data.py`

```python
"""
اختبارات ترميز `callback_data`.

هذه الطبقة صغيرة لكنها حرجة: خطأ فيها يعني أزراراً لا تعمل عند كل المستخدمين،
أو — أسوأ — زراً ينفّذ أمراً غير المقصود.
"""

from __future__ import annotations

import pytest

from keyboards.callback_data import (
    CALLBACK_VERSION,
    MAX_CALLBACK_BYTES,
    Callback,
    CallbackError,
    pack,
    pattern,
    unpack,
)


def test_pack_unpack_roundtrip() -> None:
    """الترميز ثم الفك يعيدان نفس القيم."""
    raw = pack("ord", "view", 12, "all", 3)
    data = unpack(raw)
    assert data.namespace == "ord"
    assert data.action == "view"
    assert data.int_arg(0) == 12
    assert data.arg(1) == "all"
    assert data.int_arg(2) == 3
    assert data.version == CALLBACK_VERSION


def test_pack_includes_version_suffix() -> None:
    """كل زر يحمل رقم إصدار حتى نميّز أزرار النسخ القديمة."""
    assert pack("nav", "home").endswith(f"v{CALLBACK_VERSION}")


def test_unpack_rejects_empty_and_malformed() -> None:
    """المدخلات الفارغة أو المشوّهة تُرفض باستثناء واضح لا بصمت."""
    with pytest.raises(CallbackError):
        unpack("")
    with pytest.raises(CallbackError):
        unpack(None)
    with pytest.raises(CallbackError):
        unpack("onlynamespace")


def test_old_version_is_detected() -> None:
    """زر من إصدار سابق يُكتشف بدل تنفيذه بافتراضات خاطئة."""
    data = unpack("nav:home::v0")
    assert data.is_current_version is False


def test_int_arg_default_when_missing_or_invalid() -> None:
    """الوسيط الرقمي الناقص أو غير الرقمي يرجع القيمة الافتراضية لا استثناء."""
    data = unpack(pack("cat", "list"))
    assert data.int_arg(0, 7) == 7
    broken = unpack(pack("cat", "list", "abc"))
    assert broken.int_arg(0, 1) == 1


def test_pack_rejects_too_long_payload() -> None:
    """تيليجرام يحدّ `callback_data` بـ64 بايت — نمنع التجاوز عند البناء لا عند الإرسال."""
    with pytest.raises(CallbackError):
        pack("sup", "view", "x" * (MAX_CALLBACK_BYTES + 10))


def test_pack_rejects_separator_inside_argument() -> None:
    """وسيط يحتوي الفاصل سيكسر الفك — يُرفض مبكراً."""
    with pytest.raises(CallbackError):
        pack("ord", "view", "12:34")


@pytest.mark.parametrize(
    ("candidate", "should_match"),
    [
        ("ord:cancel:5:v1", True),
        ("ord:cancelyes:5:v1", False),      # الفرق بين تأكيد الإلغاء وتنفيذه
        ("ord:cancel:v1", True),
        ("xord:cancel:5:v1", False),
    ],
)
def test_pattern_matches_exact_action(candidate: str, should_match: bool) -> None:
    """نمط المعالج يطابق الفعل بدقة ولا يبتلع فعلاً آخر يبدأ بنفس الحروف."""
    import re

    compiled = re.compile(pattern("ord", "cancel"))
    assert bool(compiled.search(candidate)) is should_match


def test_callback_dataclass_arg_defaults() -> None:
    """`Callback.arg` يرجع الافتراضي عند تجاوز عدد الوسائط."""
    data = Callback(namespace="acc", action="notif", args=("2",), version=CALLBACK_VERSION)
    assert data.arg(0) == "2"
    assert data.arg(5, "fallback") == "fallback"
```

### `tests/unit/test_ui_helpers.py`

```python
"""
اختبارات أدوات العرض وحد الاستخدام.

تركّز على ثلاث نقاط تُسبب أعطالاً حقيقية إن أُهملت:
    • تهريب HTML (اسم مستخدم فيه `<` يكسر الرسالة كلها أو يحقن وسماً).
    • تنسيق المال من النقاط الصحيحة (لا حساب عائم في طبقة العرض).
    • دقة نافذة حد الاستخدام.
"""

from __future__ import annotations

from types import SimpleNamespace

from middlewares.rate_limit import RateLimiter
from utils.formatters import (
    money_text,
    order_status_text,
    safe,
    short_link,
    ticket_status_text,
    transaction_line,
)


# ----------------------------- تهريب وتقصير ----------------------------- #


def test_safe_escapes_html() -> None:
    """أي نص من المستخدم يُهرَّب قبل العرض بتنسيق HTML."""
    assert safe("<b>اسم</b>") == "&lt;b&gt;اسم&lt;/b&gt;"
    assert "&amp;" in safe("شركة & شركاه")


def test_safe_truncates_long_text() -> None:
    """النص الطويل يُقتطع بعلامة واضحة بدل كسر الشاشة."""
    result = safe("ا" * 200, limit=20)
    assert len(result) <= 21
    assert result.endswith("…")


def test_safe_handles_none() -> None:
    """القيمة الفارغة لا تُسبب استثناء ولا تطبع None للمستخدم."""
    assert safe(None) == ""


def test_short_link_keeps_head_and_tail() -> None:
    """الرابط الطويل يُعرض مختصراً مع بقاء بدايته مفهومة."""
    link = "https://instagram.com/" + "x" * 100
    shortened = short_link(link)
    assert len(shortened) < len(link)
    assert shortened.startswith("https://instagram.com/")


# ------------------------------- المال ---------------------------------- #


def test_money_text_formats_units() -> None:
    """10000 نقطة = 1.00 من العملة (لا قسمة عائمة في العرض)."""
    assert money_text(10_000, "ر.ي").startswith("1.00")
    assert "ر.ي" in money_text(10_000, "ر.ي")


def test_money_text_zero_and_large() -> None:
    """الصفر والمبالغ الكبيرة تُعرض بلا كسور عشرية خاطئة."""
    assert money_text(0, "").strip().startswith("0.00")
    assert money_text(1_234_567_890, "").strip().startswith("123,456.79")


# ------------------------------ الحالات --------------------------------- #


def test_status_labels_are_arabic_and_known() -> None:
    """كل حالة تُترجم لنص عربي، والحالة المجهولة لا تُسقط الواجهة."""
    assert "مكتمل" in order_status_text("completed")
    assert "مفتوحة" in ticket_status_text("open")
    assert order_status_text("weird_status")


def test_transaction_line_shows_direction() -> None:
    """سطر الحركة المالية يوضّح الاتجاه (+/-) والرصيد بعدها."""
    transaction = SimpleNamespace(
        direction="credit",
        amount_units=25_000,
        balance_after_units=75_000,
        type="deposit",
        created_at="2026-01-01T10:00:00+00:00",
    )
    line = transaction_line(transaction, symbol="ر.ي")
    assert "+" in line
    assert "2.50" in line


# --------------------------- حد الاستخدام -------------------------------- #


def test_rate_limiter_allows_up_to_limit() -> None:
    """يسمح بعدد الإجراءات المحدد ثم يمنع ما بعده."""
    limiter = RateLimiter()
    assert all(limiter.hit(1, 3) for _ in range(3))
    assert limiter.hit(1, 3) is False


def test_rate_limiter_is_per_user() -> None:
    """تجاوز مستخدم للحد لا يؤثر على غيره."""
    limiter = RateLimiter()
    for _ in range(3):
        limiter.hit(1, 3)
    assert limiter.hit(2, 3) is True


def test_rate_limiter_window_slides() -> None:
    """بعد انقضاء النافذة تعود المحاولات مسموحة."""
    limiter = RateLimiter(window_seconds=0.01)
    import time

    assert limiter.hit(5, 1) is True
    assert limiter.hit(5, 1) is False
    time.sleep(0.02)
    assert limiter.hit(5, 1) is True


def test_rate_limiter_zero_limit_means_unlimited() -> None:
    """الحد صفر يعني بلا حد (تعطيل الميزة من الإعدادات)."""
    limiter = RateLimiter()
    assert all(limiter.hit(9, 0) for _ in range(100))


def test_rate_limiter_remaining_and_reset() -> None:
    """عدّاد المتبقي صحيح، والتصفير يعيد الحالة كما كانت."""
    limiter = RateLimiter()
    limiter.hit(7, 5)
    assert limiter.remaining(7, 5) == 4
    limiter.reset(7)
    assert limiter.remaining(7, 5) == 5
```

### `tests/integration/test_no_dead_buttons.py`

```python
"""
اختبار القاعدة الملزِمة: **لا زر بلا وظيفة**.

الطريقة:
    1. نستدعي كل باني لوحة أزرار في `keyboards/` ببيانات تجريبية.
    2. نجمع كل قيم `callback_data` الناتجة.
    3. نتأكد أن كل قيمة يلتقطها معالج مسجَّل فعلاً في `handlers/registry.py`
       (مع استبعاد المعالج الاحتياطي الشامل، وإلا لصار الاختبار بلا معنى).

كما نتحقق من العكس: كل معالج مسجَّل له نمط مفهوم وبإصدار `callback` الحالي.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from telegram import InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, ConversationHandler

from handlers.registry import build_handlers
from keyboards import common_kb, user_kb
from keyboards.callback_data import CALLBACK_VERSION, unpack


def _fake_category(index: int = 1) -> SimpleNamespace:
    """تصنيف تجريبي بالحقول التي تستخدمها اللوحات فقط."""
    return SimpleNamespace(
        id=index, name_ar=f"تصنيف {index}", emoji="📱", title=f"📱 تصنيف {index}"
    )


def _fake_service(index: int = 1) -> SimpleNamespace:
    """خدمة تجريبية."""
    return SimpleNamespace(
        id=index,
        name=f"خدمة {index}",
        description="وصف",
        price_per_1000_units=10_000,
        min_quantity=100,
        max_quantity=1000,
        avg_time_text="ساعة",
        link_pattern=None,
        category_id=1,
    )


def _fake_order(index: int = 1, status: str = "pending") -> SimpleNamespace:
    """طلب تجريبي."""
    return SimpleNamespace(
        id=index,
        public_code=f"ORD-{index}",
        status=status,
        cost_units=10_000,
        quantity=1000,
        delivered_quantity=0,
        remains=1000,
        refund_amount_units=0,
        last_error=None,
        service_name_snapshot="خدمة",
        link="https://example.com/u",
        created_at="2026-01-01T10:00:00+00:00",
    )


def _fake_payment(index: int = 1, status: str = "pending") -> SimpleNamespace:
    """طلب شحن تجريبي."""
    return SimpleNamespace(
        id=index, amount_units=50_000, status=status, created_at="2026-01-01T10:00:00+00:00"
    )


def _fake_method(index: int = 1) -> SimpleNamespace:
    """طريقة دفع تجريبية."""
    return SimpleNamespace(
        id=index,
        name_ar=f"طريقة {index}",
        instructions_ar="حوّل ثم أرسل",
        account_details="123456",
        requires_proof=True,
    )


def _fake_ticket(index: int = 1, status: str = "open") -> SimpleNamespace:
    """تذكرة دعم تجريبية."""
    return SimpleNamespace(
        id=index,
        subject="مشكلة",
        status=status,
        category="other",
        last_message_at="2026-01-01T10:00:00+00:00",
        updated_at="2026-01-01T10:00:00+00:00",
        is_open=status == "open",
    )


def all_markups() -> list[tuple[str, InlineKeyboardMarkup]]:
    """
    بناء كل لوحات الواجهة مرة واحدة.

    أي لوحة جديدة تُضاف في `keyboards/user_kb.py` يجب أن تُضاف هنا — وهذا مقصود:
    اللوحة التي لا تُختبر لا تُضمن أزرارها.
    """
    categories = [_fake_category(1), _fake_category(2)]
    services = [_fake_service(1), _fake_service(2)]
    orders = [_fake_order(1), _fake_order(2, status="completed")]
    tickets = [_fake_ticket(1), _fake_ticket(2, status="closed")]
    payments = [_fake_payment(1), _fake_payment(2, status="approved")]

    return [
        ("main_menu_kb", user_kb.main_menu_kb()),
        ("categories_kb", user_kb.categories_kb(categories)),
        ("categories_kb_empty", user_kb.categories_kb([])),
        (
            "services_kb",
            user_kb.services_kb(services, category_id=1, page=2, total_pages=3, symbol="ر.ي"),
        ),
        ("service_card_kb", user_kb.service_card_kb(_fake_service(1), category_id=1, page=1)),
        ("insufficient_balance_kb", user_kb.insufficient_balance_kb(1, 1)),
        (
            "orders_kb",
            user_kb.orders_kb(orders, filter_code="all", page=1, total_pages=2, symbol="ر.ي"),
        ),
        (
            "order_card_kb_cancelable",
            user_kb.order_card_kb(_fake_order(1), can_cancel=True, filter_code="all", page=1),
        ),
        (
            "order_card_kb_plain",
            user_kb.order_card_kb(
                _fake_order(2, status="completed"), can_cancel=False, filter_code="done", page=1
            ),
        ),
        ("order_cancel_confirm_kb", user_kb.order_cancel_confirm_kb(1)),
        ("wallet_kb", user_kb.wallet_kb()),
        ("history_kb", user_kb.history_kb(page=2, total_pages=4)),
        ("deposit_methods_kb", user_kb.deposit_methods_kb([_fake_method(1), _fake_method(2)])),
        ("deposits_kb", user_kb.deposits_kb(payments, page=1, total_pages=2)),
        ("support_kb", user_kb.support_kb()),
        ("ticket_categories_kb", user_kb.ticket_categories_kb()),
        ("tickets_kb", user_kb.tickets_kb(tickets, page=1, total_pages=1)),
        ("ticket_card_kb_open", user_kb.ticket_card_kb(_fake_ticket(1))),
        ("ticket_card_kb_closed", user_kb.ticket_card_kb(_fake_ticket(2, status="closed"))),
        ("account_kb", user_kb.account_kb(3)),
        ("notifications_kb", user_kb.notifications_kb(page=1, total_pages=2, unread=5)),
        ("info_kb", user_kb.info_kb()),
        ("notifications_only_back_kb", user_kb.notifications_only_back_kb()),
        ("cancel_markup", common_kb.cancel_markup()),
        ("confirm_cancel_markup", common_kb.confirm_cancel_markup()),
        ("skip_cancel_markup", common_kb.skip_cancel_markup()),
    ]


def registered_patterns() -> list[re.Pattern]:
    """
    كل أنماط الأزرار التي يلتقطها البوت فعلاً.

    تشمل معالجات الشاشات ومداخل المحادثات وحالاتها ومساراتها الاحتياطية،
    وتستبعد المعالج الشامل (الذي بلا نمط) لأنه شبكة أمان لا دليل تغطية.
    """
    patterns: list[re.Pattern] = []

    def collect(handler: object) -> None:
        """جمع النمط من معالج واحد (أو من محادثة كاملة)."""
        if isinstance(handler, CallbackQueryHandler):
            if handler.pattern is not None:
                patterns.append(handler.pattern)
        elif isinstance(handler, ConversationHandler):
            for entry in handler.entry_points:
                collect(entry)
            for state_handlers in handler.states.values():
                for state_handler in state_handlers:
                    collect(state_handler)
            for fallback in handler.fallbacks:
                collect(fallback)

    for _group, handler in build_handlers():
        collect(handler)
    return patterns


ALL_BUTTONS = sorted(
    {
        data
        for _name, markup in all_markups()
        for row in markup.inline_keyboard
        for button in row
        if (data := button.callback_data)
    }
)


def test_keyboards_produce_buttons() -> None:
    """تأكيد أن اللوحات فعلاً تنتج أزراراً (حماية من اختبار فارغ يمر زوراً).."""
    assert len(ALL_BUTTONS) >= 25


@pytest.mark.parametrize("callback_data", ALL_BUTTONS)
def test_every_button_has_handler(callback_data: str) -> None:
    """كل زر في الواجهة يلتقطه معالج مسجَّل — لا أزرار ميتة."""
    patterns = registered_patterns()
    matched = [pattern.pattern for pattern in patterns if pattern.search(callback_data)]
    assert matched, f"الزر {callback_data!r} بلا معالج مسجَّل في handlers/registry.py"


@pytest.mark.parametrize("callback_data", ALL_BUTTONS)
def test_every_button_is_well_formed(callback_data: str) -> None:
    """كل زر مُرمَّز بالصيغة المعتمدة وبإصدار callback الحالي."""
    data = unpack(callback_data)
    assert data.namespace
    assert data.action
    assert data.version == CALLBACK_VERSION
    assert len(callback_data.encode("utf-8")) <= 64   # حد تيليجرام الصارم


def test_no_button_matches_more_than_one_screen_handler() -> None:
    """
    لا يلتقط زرَّاً واحداً أكثر من معالج شاشة.

    التقاط زر بمعالجين يعني سلوكاً يعتمد على ترتيب التسجيل — مصدر أعطال صامتة.
    المحادثات مستثناة لأن حالاتها معزولة زمنياً (لا تعمل إلا داخل المحادثة).
    """
    from handlers.registry import screen_handlers

    patterns = [handler.pattern for handler in screen_handlers() if handler.pattern]
    for callback_data in ALL_BUTTONS:
        matches = [pattern.pattern for pattern in patterns if pattern.search(callback_data)]
        assert len(matches) <= 1, f"الزر {callback_data!r} يلتقطه أكثر من معالج: {matches}"
```

### `tests/integration/test_handler_registry.py`

```python
"""
اختبارات تسجيل المعالجات على تطبيق PTB حقيقي (بلا اتصال بالشبكة).

ما الذي يُثبته هذا الملف؟
    • كل المعالجات تُسجَّل في المجموعات الصحيحة وبالترتيب الصحيح.
    • التحديث يصل للمعالج المقصود لا لغيره (نختبر `check_update` مباشرة).
    • الطبقة الوسيطة تسبق الجميع، والمسار الاحتياطي يأتي أخيراً فلا يبتلع
      زراً صحيحاً.
"""

from __future__ import annotations

import pytest
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    TypeHandler,
)

from handlers.registry import MAIN_GROUP, MIDDLEWARE_GROUP, build_handlers, register_handlers
from keyboards.callback_data import pack
from tests.telegram_fakes import FakeBot, make_callback_update, make_message_update

#: توكن شكلي صالح البنية — لا يُستخدم في أي اتصال فعلي
DUMMY_TOKEN = "123456789:AAEssentialDummyTokenForLocalTestsOnly"


@pytest.fixture
def bot() -> FakeBot:
    """بوت مزيّف لبناء التحديثات."""
    return FakeBot()


def test_middleware_is_registered_first() -> None:
    """الطبقة الوسيطة وحدها في المجموعة -10 قبل كل المعالجات."""
    handlers = build_handlers()
    group, handler = handlers[0]
    assert group == MIDDLEWARE_GROUP
    assert isinstance(handler, TypeHandler)
    assert all(group == MAIN_GROUP for group, _ in handlers[1:])


def test_conversations_registered_before_global_commands() -> None:
    """المحادثات تسبق /start العام حتى تلتقط أوامر الخروج أثناء المحادثة."""
    handlers = [handler for _group, handler in build_handlers()]
    first_command = next(
        index for index, handler in enumerate(handlers) if isinstance(handler, CommandHandler)
    )
    last_conversation = max(
        index for index, handler in enumerate(handlers) if isinstance(handler, ConversationHandler)
    )
    assert last_conversation < first_command


def test_catch_all_handlers_are_last() -> None:
    """المعالج الشامل للأزرار والنصوص في آخر القائمة (شبكة أمان لا حاجز)."""
    handlers = [handler for _group, handler in build_handlers()]
    catch_all_callback = next(
        index
        for index, handler in enumerate(handlers)
        if isinstance(handler, CallbackQueryHandler) and handler.pattern is None
    )
    specific_callbacks = [
        index
        for index, handler in enumerate(handlers)
        if isinstance(handler, CallbackQueryHandler) and handler.pattern is not None
    ]
    assert catch_all_callback > max(specific_callbacks)
    assert isinstance(handlers[-1], MessageHandler)


def test_register_handlers_on_real_application() -> None:
    """التسجيل على تطبيق PTB حقيقي ينجح ويضع كل معالج في مجموعته."""
    application = ApplicationBuilder().token(DUMMY_TOKEN).build()
    count = register_handlers(application)

    assert count == len(build_handlers())
    assert len(application.handlers[MIDDLEWARE_GROUP]) == 1
    assert len(application.handlers[MAIN_GROUP]) == count - 1
    assert application.error_handlers, "لم يُسجَّل معالج الأخطاء العام"


@pytest.mark.parametrize(
    ("callback_data", "expected_module"),
    [
        (pack("nav", "home"), "handlers.common.navigation"),
        (pack("cat", "list", 1), "handlers.user.catalog"),
        (pack("cat", "svc", 3, 1, 1), "handlers.user.catalog"),
        (pack("ord", "list", "all", 1), "handlers.user.orders"),
        (pack("ord", "cancel", 5), "handlers.user.orders"),
        (pack("ord", "cancelyes", 5), "handlers.user.orders"),
        (pack("wal", "history", 2), "handlers.user.wallet"),
        (pack("dep", "list", 1), "handlers.user.deposit"),
        (pack("sup", "view", 4), "handlers.user.support"),
        (pack("acc", "notif", 1), "handlers.user.account"),
    ],
)
def test_button_reaches_expected_handler(
    bot: FakeBot, callback_data: str, expected_module: str
) -> None:
    """كل زر يلتقطه المعالج المقصود لا معالجاً آخر سبقه في الترتيب."""
    update = make_callback_update(bot, data=callback_data, user_id=4242)
    claimed: list[str] = []

    for _group, handler in build_handlers():
        if isinstance(handler, TypeHandler):
            continue                                   # الطبقة الوسيطة تلتقط كل شيء بطبيعتها
        if handler.check_update(update) is not False and handler.check_update(update) is not None:
            callback = getattr(handler, "callback", None)
            if callback is not None:
                claimed.append(callback.__module__)
                break

    assert claimed and claimed[0] == expected_module, (
        f"الزر {callback_data} التقطه {claimed or 'لا أحد'} بدل {expected_module}"
    )


def test_order_cancel_and_cancelyes_are_distinct(bot: FakeBot) -> None:
    """تأكيد الإلغاء وتنفيذه زران مختلفان ولا يتداخل نمطاهما."""
    from handlers.registry import screen_handlers

    confirm_update = make_callback_update(bot, data=pack("ord", "cancel", 9), user_id=1)
    execute_update = make_callback_update(bot, data=pack("ord", "cancelyes", 9), user_id=1)

    matched_confirm = [
        handler.callback.__name__
        for handler in screen_handlers()
        if handler.check_update(confirm_update)
    ]
    matched_execute = [
        handler.callback.__name__
        for handler in screen_handlers()
        if handler.check_update(execute_update)
    ]
    assert matched_confirm == ["order_cancel_confirm"]
    assert matched_execute == ["order_cancel_execute"]


def test_free_text_outside_conversation_hits_fallback(bot: FakeBot) -> None:
    """نص حر خارج المحادثات يصل لمعالج الرسائل الاحتياطي لا لشيء آخر."""
    update = make_message_update(bot, text="مرحبا كيف أطلب؟", user_id=777)
    matched = [
        handler.callback.__name__
        for _group, handler in build_handlers()
        if isinstance(handler, MessageHandler) and handler.check_update(update)
    ]
    assert matched == ["free_text"]


def test_unknown_command_hits_its_handler(bot: FakeBot) -> None:
    """أمر غير معروف يصل لمعالج الأوامر المجهولة لا لمعالج النصوص."""
    update = make_message_update(bot, text="/whatever", user_id=777)
    matched = [
        handler.callback.__name__
        for _group, handler in build_handlers()
        if isinstance(handler, MessageHandler) and handler.check_update(update)
    ]
    assert matched[0] == "unknown_command"


def test_known_commands_are_registered(bot: FakeBot) -> None:
    """الأوامر المعلنة للمستخدم (/start /help /id /cancel) كلها مسجَّلة فعلاً."""
    from main import BOT_COMMANDS

    registered = {
        tuple(handler.commands)[0]
        for _group, handler in build_handlers()
        if isinstance(handler, CommandHandler) and handler.commands
    }
    for command in BOT_COMMANDS:
        assert command.command in registered, f"الأمر /{command.command} معلن بلا معالج"
```

### `tests/integration/test_user_interface.py`

```python
"""
اختبارات واجهة العميل: من ضغطة الزر إلى أثرها في قاعدة البيانات.

لا شبكة ولا `Application` حقيقي: نبني تحديثات `telegram.Update` حقيقية،
ونمرّرها للمعالجات مباشرة مع بوت مزيّف يسجّل النصوص والأزرار، وقاعدة بيانات
مؤقتة حقيقية. أي خلل في النص أو الأزرار أو الأثر المالي يظهر هنا.
"""

from __future__ import annotations

import pytest
from telegram.ext import ApplicationHandlerStop, ConversationHandler

from core.enums import OrderStatus, PaymentStatus
from database.models import Service, User
from database.repositories import Repositories
from handlers.common import fallbacks, navigation
from handlers.user import account, catalog, deposit, order_flow, orders, support, wallet
from keyboards.callback_data import pack
from middlewares.context import USER_KEY, UserContextMiddleware
from middlewares.rate_limit import RateLimiter
from services import ServiceContainer
from tests.telegram_fakes import (
    FakeBot,
    FakeContext,
    make_callback_update,
    make_message_update,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def bot() -> FakeBot:
    """بوت مزيّف جديد لكل اختبار."""
    return FakeBot()


@pytest.fixture
def context(bot: FakeBot, services: ServiceContainer) -> FakeContext:
    """سياق مزيّف محقون بالخدمات الحقيقية على قاعدة بيانات مؤقتة."""
    return FakeContext(bot, services)


async def run_middleware(bot: FakeBot, context: FakeContext, update) -> bool:
    """
    تمرير التحديث عبر الطبقة الوسيطة كما يحدث في التشغيل الحقيقي.

    المخرجات: True إذا سُمح بمتابعة المعالجة، False إذا أوقفتها الطبقة.
    """
    middleware = UserContextMiddleware(RateLimiter())
    try:
        await middleware(update, context)
    except ApplicationHandlerStop:
        return False
    return True


async def press(bot: FakeBot, context: FakeContext, handler, data: str, user_id: int):
    """محاكاة ضغطة زر: بناء التحديث ثم استدعاء المعالج مباشرة."""
    update = make_callback_update(bot, data=data, user_id=user_id)
    context.user_data.setdefault("db_user", context.user_data.get(USER_KEY))
    return await handler(update, context)


async def write(bot: FakeBot, context: FakeContext, handler, text: str, user_id: int, *, photo: bool = False):
    """محاكاة إرسال المستخدم رسالة نصية (أو صورة)."""
    update = make_message_update(bot, text=text, user_id=user_id, photo=photo)
    return await handler(update, context)


async def load_user(bot: FakeBot, context: FakeContext, user: User) -> None:
    """تحميل المستخدم في السياق عبر الطبقة الوسيطة (كما في التشغيل الفعلي)."""
    update = make_message_update(bot, text="/start", user_id=user.telegram_id)
    allowed = await run_middleware(bot, context, update)
    assert allowed, "الطبقة الوسيطة رفضت مستخدماً عادياً"
    bot.clear()


# ======================================================================== #
#                            الشاشة الأولى والتنقل                          #
# ======================================================================== #


async def test_start_registers_user_and_shows_menu(
    bot: FakeBot, context: FakeContext, services: ServiceContainer
) -> None:
    """أول /start ينشئ المستخدم ويعرض القائمة الرئيسية بأزرارها الست."""
    update = make_message_update(bot, text="/start", user_id=55_001)
    assert await run_middleware(bot, context, update)
    await navigation.start_command(update, context)

    created = await services.users.get_by_telegram(55_001)
    assert created is not None
    assert bot.last.kind == "send"
    assert len(bot.last.buttons) == 6
    assert "cat:list:1:v1" in bot.last.buttons
    assert "wal:home::v1" in bot.last.buttons or "wal:home:v1" in bot.last.buttons


async def test_home_button_edits_same_message(
    bot: FakeBot, context: FakeContext, user: User
) -> None:
    """زر «الرئيسية» يحرّر نفس الرسالة بدل إرسال رسالة جديدة."""
    await load_user(bot, context, user)
    await press(bot, context, navigation.home_callback, pack("nav", "home"), user.telegram_id)
    assert bot.last.kind == "edit"
    assert bot.answers, "لم يُرد البوت على ضغطة الزر — سيبقى المؤشر يدور عند المستخدم"


async def test_unknown_button_does_not_fail_silently(
    bot: FakeBot, context: FakeContext, user: User
) -> None:
    """زر قديم/غير معروف يُقابَل برسالة واضحة وبالقائمة الرئيسية."""
    await load_user(bot, context, user)
    await press(bot, context, fallbacks.unknown_callback, "zz:gone:1:v9", user.telegram_id)
    assert bot.answers[-1]["alert"] is True
    assert bot.last.buttons, "رسالة الزر المجهول بلا أزرار — المستخدم يصل لطريق مسدود"


# ======================================================================== #
#                          تصفح الخدمات وبطاقة الخدمة                       #
# ======================================================================== #


async def test_catalog_screens(
    bot: FakeBot, context: FakeContext, user: User, mock_service: Service
) -> None:
    """التصنيفات ← الخدمات ← بطاقة الخدمة: كل شاشة تعرض أزرار الانتقال التالية."""
    await load_user(bot, context, user)

    await press(bot, context, catalog.categories_screen, pack("cat", "list", 1), user.telegram_id)
    category_buttons = [b for b in bot.last.buttons if b.startswith("cat:open")]
    assert category_buttons, "لا تصنيفات معروضة رغم وجود خدمة متاحة"

    await press(bot, context, catalog.services_screen, category_buttons[0], user.telegram_id)
    service_buttons = [b for b in bot.last.buttons if b.startswith("cat:svc")]
    assert service_buttons

    await press(bot, context, catalog.service_card_screen, service_buttons[0], user.telegram_id)
    assert mock_service.name in bot.last.text
    assert any(b.startswith("new:start") for b in bot.last.buttons), "بطاقة الخدمة بلا زر طلب"


# ======================================================================== #
#                              مسار الطلب الكامل                            #
# ======================================================================== #


async def test_order_flow_happy_path(
    bot: FakeBot,
    context: FakeContext,
    services: ServiceContainer,
    user: User,
    admin: User,
    mock_service: Service,
) -> None:
    """طلب كامل: رابط ← كمية ← ملخص ← تأكيد ⇒ طلب في القاعدة ورصيد مخصوم."""
    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    await load_user(bot, context, user)

    state = await press(
        bot, context, order_flow.start_order, pack("new", "start", mock_service.id), user.telegram_id
    )
    assert state == order_flow.ASK_LINK
    assert any(b.startswith("flow:cancel") for b in bot.last.buttons), "خطوة بلا زر إلغاء"

    state = await write(
        bot, context, order_flow.receive_link, "https://instagram.com/p/abc", user.telegram_id
    )
    assert state == order_flow.ASK_QUANTITY

    state = await write(bot, context, order_flow.receive_quantity, "1000", user.telegram_id)
    assert state == order_flow.CONFIRM
    summary = bot.last.text
    assert "1000" in summary
    assert any(b.startswith("flow:confirm") for b in bot.last.buttons)

    state = await press(
        bot, context, order_flow.confirm_order, pack("flow", "confirm"), user.telegram_id
    )
    assert state == ConversationHandler.END

    created = await services.orders.list_for_user(user, statuses=())
    assert len(created) == 1
    assert created[0].quantity == 1000
    assert created[0].status == OrderStatus.PENDING
    assert await services.wallet.balance_units(user.id) == 40_000
    assert order_flow.FLOW_KEY not in context.user_data, "بيانات المحادثة لم تُنظَّف"


async def test_order_flow_double_confirm_creates_one_order(
    bot: FakeBot,
    context: FakeContext,
    services: ServiceContainer,
    user: User,
    admin: User,
    mock_service: Service,
) -> None:
    """الضغط المزدوج على «تأكيد» لا ينشئ طلبين (client_request_id ثابت للمحادثة)."""
    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    await load_user(bot, context, user)

    await press(
        bot, context, order_flow.start_order, pack("new", "start", mock_service.id), user.telegram_id
    )
    await write(bot, context, order_flow.receive_link, "https://instagram.com/p/abc", user.telegram_id)
    await write(bot, context, order_flow.receive_quantity, "1000", user.telegram_id)

    flow = dict(context.user_data[order_flow.FLOW_KEY])
    await press(bot, context, order_flow.confirm_order, pack("flow", "confirm"), user.telegram_id)
    context.user_data[order_flow.FLOW_KEY] = flow        # محاكاة ضغطة ثانية على نفس الرسالة
    await press(bot, context, order_flow.confirm_order, pack("flow", "confirm"), user.telegram_id)

    created = await services.orders.list_for_user(user, statuses=())
    assert len(created) == 1, "تكرّر الطلب عند الضغط المزدوج"
    assert await services.wallet.balance_units(user.id) == 40_000


async def test_order_flow_insufficient_balance_offers_topup(
    bot: FakeBot,
    context: FakeContext,
    services: ServiceContainer,
    user: User,
    mock_service: Service,
) -> None:
    """رصيد غير كافٍ ⇒ عرض المبلغ الناقص وزر شحن مباشر، بلا إنشاء طلب."""
    await load_user(bot, context, user)

    await press(
        bot, context, order_flow.start_order, pack("new", "start", mock_service.id), user.telegram_id
    )
    await write(bot, context, order_flow.receive_link, "https://instagram.com/p/abc", user.telegram_id)
    state = await write(bot, context, order_flow.receive_quantity, "1000", user.telegram_id)

    assert state == ConversationHandler.END
    assert "الناقص" in bot.last.text
    assert any(b.startswith("dep:start") for b in bot.last.buttons), "لا زر شحن عند نقص الرصيد"
    assert await services.orders.count_for_user(user, statuses=()) == 0


async def test_order_flow_rejects_bad_quantity_and_keeps_step(
    bot: FakeBot,
    context: FakeContext,
    services: ServiceContainer,
    user: User,
    admin: User,
    mock_service: Service,
) -> None:
    """كمية خارج الحدود: رسالة خطأ والبقاء في نفس الخطوة (لا إسقاط للمحادثة)."""
    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    await load_user(bot, context, user)
    await press(
        bot, context, order_flow.start_order, pack("new", "start", mock_service.id), user.telegram_id
    )
    await write(bot, context, order_flow.receive_link, "https://instagram.com/p/abc", user.telegram_id)

    state = await write(bot, context, order_flow.receive_quantity, "5", user.telegram_id)
    assert state is None, "الحارس يُبقي المستخدم في نفس خطوة المحادثة"
    assert "❌" in bot.last.text
    assert await services.orders.count_for_user(user, statuses=()) == 0


async def test_order_cancel_by_user_refunds(
    bot: FakeBot,
    context: FakeContext,
    services: ServiceContainer,
    user: User,
    admin: User,
    mock_service: Service,
) -> None:
    """إلغاء المستخدم لطلب لم يُرسل بعد ⇒ استرجاع كامل موثّق في المحفظة."""
    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/x", quantity=1000
    )
    await load_user(bot, context, user)

    await press(
        bot, context, orders.order_cancel_confirm, pack("ord", "cancel", order.id), user.telegram_id
    )
    assert any(b.startswith("ord:cancelyes") for b in bot.last.buttons)

    await press(
        bot, context, orders.order_cancel_execute, pack("ord", "cancelyes", order.id), user.telegram_id
    )
    refreshed = await services.orders.get_for_user(user, order.id)
    assert refreshed.status in {OrderStatus.CANCELED, OrderStatus.REFUNDED}
    assert await services.wallet.balance_units(user.id) == 50_000


# ======================================================================== #
#                            المحفظة وطلبات الشحن                          #
# ======================================================================== #


async def test_wallet_screen_shows_balance(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User
) -> None:
    """شاشة المحفظة تعرض الرصيد الحقيقي من قاعدة البيانات."""
    await services.wallet.adjust_balance(
        target=user, amount_units=25_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    await load_user(bot, context, user)
    await press(bot, context, wallet.wallet_screen, pack("wal", "home"), user.telegram_id)
    assert "2.50" in bot.last.text
    assert any(b.startswith("dep:start") for b in bot.last.buttons)


async def test_deposit_flow_creates_pending_payment(
    bot: FakeBot,
    context: FakeContext,
    services: ServiceContainer,
    user: User,
    payment_method,
) -> None:
    """مسار الشحن ينشئ طلباً «بانتظار المراجعة» ولا يضيف رصيداً إطلاقاً."""
    await load_user(bot, context, user)
    balance_before = await services.wallet.balance_units(user.id)

    state = await press(bot, context, deposit.start_deposit, pack("dep", "start"), user.telegram_id)
    assert state == deposit.CHOOSE_METHOD
    method_buttons = [b for b in bot.last.buttons if b.startswith("dep:method")]
    assert method_buttons, "لا طرق دفع معروضة"

    state = await press(bot, context, deposit.choose_method, method_buttons[0], user.telegram_id)
    assert state == deposit.ASK_AMOUNT

    state = await write(bot, context, deposit.receive_amount, "10", user.telegram_id)
    assert state == deposit.ASK_REFERENCE

    state = await write(bot, context, deposit.receive_reference, "TRX-99887", user.telegram_id)
    assert state == deposit.ASK_PROOF

    state = await write(bot, context, deposit.receive_proof, "", user.telegram_id, photo=True)
    assert state == deposit.CONFIRM

    state = await press(
        bot, context, deposit.confirm_deposit, pack("flow", "confirm"), user.telegram_id
    )
    assert state == ConversationHandler.END

    payments = await services.payments.list_for_user(user, limit=10)
    assert len(payments) == 1
    assert payments[0].status == PaymentStatus.PENDING
    assert payments[0].amount_units == 100_000
    assert await services.wallet.balance_units(user.id) == balance_before, "الشحن غيّر الرصيد قبل الاعتماد"


async def test_deposit_cancel_keeps_nothing(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, payment_method
) -> None:
    """إلغاء مسار الشحن لا يترك أي طلب شحن ولا بيانات محادثة."""
    await load_user(bot, context, user)
    await press(bot, context, deposit.start_deposit, pack("dep", "start"), user.telegram_id)
    state = await press(
        bot, context, deposit.cancel_deposit_flow, pack("flow", "cancel"), user.telegram_id
    )
    assert state == ConversationHandler.END
    assert deposit.FLOW_KEY not in context.user_data
    assert await services.payments.list_for_user(user, limit=10) == []


# ======================================================================== #
#                                الدعم الفني                               #
# ======================================================================== #


async def test_ticket_flow_creates_ticket(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User
) -> None:
    """فتح تذكرة: تصنيف ← عنوان ← شرح ⇒ تذكرة مفتوحة برسالة واحدة."""
    await load_user(bot, context, user)

    state = await press(bot, context, support.start_new_ticket, pack("sup", "new"), user.telegram_id)
    assert state == support.ASK_CATEGORY
    category_buttons = [b for b in bot.last.buttons if b.startswith("sup:cat")]
    assert category_buttons

    state = await press(bot, context, support.choose_ticket_category, category_buttons[0], user.telegram_id)
    assert state == support.ASK_SUBJECT

    state = await write(bot, context, support.receive_subject, "طلبي متأخر", user.telegram_id)
    assert state == support.ASK_MESSAGE

    state = await write(
        bot, context, support.receive_ticket_message, "مضى يومان بلا تنفيذ", user.telegram_id
    )
    assert state == ConversationHandler.END

    tickets = await services.tickets.list_for_user(user, limit=10)
    assert len(tickets) == 1
    assert tickets[0].subject == "طلبي متأخر"


async def test_ticket_reply_and_close(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User
) -> None:
    """الرد على تذكرة ثم إغلاقها من المستخدم نفسه."""
    ticket = await services.tickets.create_ticket(
        user, subject="سؤال", message="هل الخدمة متاحة؟", category="other"
    )
    await load_user(bot, context, user)

    state = await press(
        bot, context, support.start_reply, pack("sup", "reply", ticket.id), user.telegram_id
    )
    assert state == support.ASK_REPLY

    state = await write(bot, context, support.receive_reply, "شكراً، وصلتني", user.telegram_id)
    assert state == ConversationHandler.END

    conversation = await services.tickets.conversation_for_user(user, ticket.id)
    assert len(conversation) >= 2

    await press(bot, context, support.close_ticket, pack("sup", "close", ticket.id), user.telegram_id)
    closed = await services.tickets.get_for_user(user, ticket.id)
    assert closed.status == "closed"


# ======================================================================== #
#                            الحساب والإشعارات                             #
# ======================================================================== #


async def test_account_and_notifications_screens(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User
) -> None:
    """شاشة الحساب تعرض بيانات حقيقية، وصندوق الإشعارات يُعلَّم مقروءاً."""
    await services.wallet.adjust_balance(
        target=user, amount_units=15_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    await load_user(bot, context, user)

    await press(bot, context, account.account_screen, pack("acc", "home"), user.telegram_id)
    assert str(user.telegram_id) in bot.last.text

    await press(bot, context, account.notifications_screen, pack("acc", "notif", 1), user.telegram_id)
    assert bot.last.buttons

    await press(bot, context, account.mark_all_read, pack("acc", "readall"), user.telegram_id)
    assert await services.notifications.unread_count(user.id) == 0


async def test_info_screen_has_version(bot: FakeBot, context: FakeContext, user: User) -> None:
    """شاشة المعلومات تعرض إصدار النظام وزر الرجوع."""
    from core.constants import APP_VERSION

    await load_user(bot, context, user)
    await press(bot, context, account.info_screen, pack("acc", "info"), user.telegram_id)
    assert APP_VERSION in bot.last.text
    assert bot.last.buttons


# ======================================================================== #
#                        الطبقة الوسيطة: حظر وصيانة وحد                     #
# ======================================================================== #


async def test_banned_user_is_blocked(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, db, repos: Repositories, user: User
) -> None:
    """المستخدم المحظور يُمنع من كل شيء برسالة تشرح السبب."""
    async with db.transaction() as tx:
        await repos.users.set_ban(tx, user.id, banned=True, reason="اختبار")

    update = make_message_update(bot, text="/start", user_id=user.telegram_id)
    assert await run_middleware(bot, context, update) is False
    assert bot.sent, "المحظور لم يتلقَّ أي رسالة — حظر صامت غير مقبول"


async def test_maintenance_blocks_normal_user_only(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, super_admin: User
) -> None:
    """وضع الصيانة يوقف المستخدم العادي ويسمح للأدمن."""
    await services.settings.set("maintenance_mode", "true", admin_id=super_admin.id)

    update = make_message_update(bot, text="/start", user_id=user.telegram_id)
    assert await run_middleware(bot, context, update) is False

    admin_context = FakeContext(bot, services)
    admin_update = make_message_update(bot, text="/start", user_id=super_admin.telegram_id)
    assert await run_middleware(bot, admin_context, admin_update) is True


async def test_rate_limit_stops_flood(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, super_admin: User
) -> None:
    """تجاوز حد الاستخدام يوقف المعالجة ويُعلم المستخدم."""
    await services.settings.set("rate_limit_actions_per_minute", "3", admin_id=super_admin.id)
    middleware = UserContextMiddleware(RateLimiter())

    allowed = 0
    for _ in range(5):
        update = make_message_update(bot, text="مرحبا", user_id=user.telegram_id)
        try:
            await middleware(update, context)
            allowed += 1
        except ApplicationHandlerStop:
            break
    assert allowed == 3
    assert any("كثيرة" in text or "انتظر" in text for text in bot.texts)
```

### `tests/integration/test_user_screens.py`

```python
"""
تغطية بقية شاشات العميل: القوائم، السجلات، الحالات الفارغة، والأوامر.

الهدف من هذا الملف: ألا يبقى أي معالج في الواجهة بلا استدعاء واحد على الأقل
في الاختبارات — فالمعالج غير المُستدعى هو مكمن أخطاء `AttributeError` الصامتة.
"""

from __future__ import annotations

import pytest

from core.enums import PaymentStatus
from database.models import Service, User
from handlers.common import errors, fallbacks, navigation
from handlers.user import catalog, deposit, orders, support, wallet
from keyboards.callback_data import pack
from services import ServiceContainer
from tests.integration.test_user_interface import load_user, press, write
from tests.telegram_fakes import FakeBot, FakeContext, make_message_update

pytestmark = pytest.mark.asyncio


@pytest.fixture
def bot() -> FakeBot:
    """بوت مزيّف لكل اختبار."""
    return FakeBot()


@pytest.fixture
def context(bot: FakeBot, services: ServiceContainer) -> FakeContext:
    """سياق مزيّف بالخدمات الحقيقية."""
    return FakeContext(bot, services)


# ============================ الأوامر النصية ============================= #


async def test_help_and_id_commands(bot: FakeBot, context: FakeContext, user: User) -> None:
    """/help يشرح الاستخدام، و/id يعرض معرف المستخدم الحقيقي."""
    await load_user(bot, context, user)

    update = make_message_update(bot, text="/help", user_id=user.telegram_id)
    await navigation.help_command(update, context)
    assert len(bot.last.text) > 40

    update = make_message_update(bot, text="/id", user_id=user.telegram_id)
    await navigation.id_command(update, context)
    assert str(user.telegram_id) in bot.last.text


async def test_cancel_command_outside_conversation(
    bot: FakeBot, context: FakeContext, user: User
) -> None:
    """/cancel خارج أي محادثة يطمئن المستخدم ويعيده للقائمة بدل الصمت."""
    await load_user(bot, context, user)
    update = make_message_update(bot, text="/cancel", user_id=user.telegram_id)
    await fallbacks.cancel_command(update, context)
    assert bot.last.buttons


async def test_unknown_command_and_free_text(
    bot: FakeBot, context: FakeContext, user: User
) -> None:
    """الأمر المجهول والنص الحر يُقابلان برد واضح وأزرار تنقل."""
    await load_user(bot, context, user)

    await fallbacks.unknown_command(
        make_message_update(bot, text="/nothing", user_id=user.telegram_id), context
    )
    assert bot.last.buttons

    await fallbacks.free_text(
        make_message_update(bot, text="السلام عليكم", user_id=user.telegram_id), context
    )
    assert bot.last.buttons


async def test_exit_conversation_fallback_clears_flow(
    bot: FakeBot, context: FakeContext, user: User
) -> None:
    """/start أثناء محادثة يُنهيها وينظّف بياناتها ويعرض القائمة."""
    from telegram.ext import ConversationHandler

    await load_user(bot, context, user)
    context.user_data["order_flow"] = {"service_id": 1}
    handler = fallbacks.exit_conversation("order_flow")

    result = await handler(
        make_message_update(bot, text="/start", user_id=user.telegram_id), context
    )
    assert result == ConversationHandler.END
    assert "order_flow" not in context.user_data


async def test_page_indicator_is_not_a_dead_button(
    bot: FakeBot, context: FakeContext, user: User
) -> None:
    """زر رقم الصفحة يرد بتلميح بدل أن يبدو معطلاً."""
    await load_user(bot, context, user)
    await press(
        bot, context, navigation.page_indicator_callback, pack("nav", "page", 2, 5), user.telegram_id
    )
    assert bot.answers, "زر الصفحة لم يرد على المستخدم"
    assert "2" in (bot.answers[-1]["text"] or "")


# =========================== الحالات الفارغة ============================= #


async def test_empty_screens_render_safely(
    bot: FakeBot, context: FakeContext, user: User
) -> None:
    """قوائم فارغة (خدمات/طلبات/سجل/إيداعات/تذاكر) تعرض رسالة وأزرار رجوع."""
    await load_user(bot, context, user)

    screens = [
        (catalog.categories_screen, pack("cat", "list", 1)),
        (orders.orders_list_screen, pack("ord", "list", "all", 1)),
        (wallet.history_screen, pack("wal", "history", 1)),
        (deposit.deposits_list_screen, pack("dep", "list", 1)),
        (support.tickets_list_screen, pack("sup", "list", 1)),
        (support.support_home, pack("sup", "home")),
    ]
    for handler, data in screens:
        bot.clear()
        await press(bot, context, handler, data, user.telegram_id)
        assert bot.last.text, f"{handler.__name__} عرض شاشة فارغة بلا نص"
        assert bot.last.buttons, f"{handler.__name__} شاشة بلا أي زر — طريق مسدود"


# ======================= قوائم فيها بيانات حقيقية ======================== #


async def test_orders_list_filters_and_card(
    bot: FakeBot,
    context: FakeContext,
    services: ServiceContainer,
    user: User,
    admin: User,
    mock_service: Service,
) -> None:
    """قائمة الطلبات تعرض الطلب، والتصفية تعمل، وبطاقة الطلب تفتح بتفاصيله."""
    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/list", quantity=1000
    )
    await load_user(bot, context, user)

    await press(bot, context, orders.orders_list_screen, pack("ord", "list", "all", 1), user.telegram_id)
    assert any(b.startswith("ord:view") for b in bot.last.buttons)

    await press(
        bot, context, orders.orders_list_screen, pack("ord", "list", "active", 1), user.telegram_id
    )
    assert any(b.startswith("ord:view") for b in bot.last.buttons)

    await press(
        bot, context, orders.orders_list_screen, pack("ord", "list", "done", 1), user.telegram_id
    )
    assert not any(b.startswith("ord:view") for b in bot.last.buttons)

    await press(
        bot, context, orders.order_card_screen, pack("ord", "view", order.id, "all", 1), user.telegram_id
    )
    assert order.public_code in bot.last.text
    assert any(b.startswith("sup:neworder") for b in bot.last.buttons), "بطاقة الطلب بلا زر دعم"


async def test_wallet_history_shows_transactions(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User
) -> None:
    """سجل العمليات يعرض الحركة المالية الحقيقية بعلامتها."""
    await services.wallet.adjust_balance(
        target=user, amount_units=30_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    await load_user(bot, context, user)
    await press(bot, context, wallet.history_screen, pack("wal", "history", 1), user.telegram_id)
    assert "3.00" in bot.last.text


async def test_deposits_list_and_cancel(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, payment_method
) -> None:
    """قائمة طلبات الشحن تعرض المعلّق مع زر إلغائه، والإلغاء يُنفَّذ فعلاً."""
    payment = await services.payments.create_payment(
        user, method_id=payment_method.id, raw_amount="20", transaction_reference="TRX-LIST-1"
    )
    await load_user(bot, context, user)

    await press(bot, context, deposit.deposits_list_screen, pack("dep", "list", 1), user.telegram_id)
    assert any(b.startswith("dep:cancel") for b in bot.last.buttons)

    await press(
        bot, context, deposit.cancel_payment, pack("dep", "cancel", payment.id), user.telegram_id
    )
    refreshed = await services.payments.get_for_user(user, payment.id)
    assert refreshed.status == PaymentStatus.CANCELLED


async def test_ticket_from_order_prefills_subject(
    bot: FakeBot,
    context: FakeContext,
    services: ServiceContainer,
    user: User,
    admin: User,
    mock_service: Service,
) -> None:
    """فتح تذكرة من بطاقة الطلب يتخطى السؤال عن التصنيف ويربطها بالطلب."""
    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/tkt", quantity=1000
    )
    await load_user(bot, context, user)

    state = await press(
        bot, context, support.start_ticket_for_order, pack("sup", "neworder", order.id), user.telegram_id
    )
    assert state == support.ASK_MESSAGE
    assert order.public_code in bot.last.text

    await write(bot, context, support.receive_ticket_message, "الطلب متوقف", user.telegram_id)
    tickets = await services.tickets.list_for_user(user, limit=5)
    assert len(tickets) == 1
    assert tickets[0].related_order_id == order.id


async def test_ticket_card_shows_conversation(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User
) -> None:
    """بطاقة التذكرة تعرض الرسائل وأزرار الرد والإغلاق."""
    ticket = await services.tickets.create_ticket(
        user, subject="استفسار", message="هل يمكن تعديل الرابط؟", category="other"
    )
    await load_user(bot, context, user)

    await press(bot, context, support.ticket_card_screen, pack("sup", "view", ticket.id), user.telegram_id)
    assert "استفسار" in bot.last.text
    assert any(b.startswith("sup:reply") for b in bot.last.buttons)
    assert any(b.startswith("sup:close") for b in bot.last.buttons)


# ============================ معالج الأخطاء ============================== #


async def test_error_handler_logs_and_informs_user(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, repos, user: User
) -> None:
    """خطأ غير متوقع: يُسجَّل في قاعدة البيانات ويُبلَّغ المستخدم برسالة مهذبة."""
    await load_user(bot, context, user)
    update = make_message_update(bot, text="أي نص", user_id=user.telegram_id)
    context.error = RuntimeError("انفجار اختباري")

    await errors.error_handler(update, context)

    stored = await repos.error_logs.list_recent(limit=5)
    assert stored, "الخطأ لم يُسجَّل في جدول error_logs"
    assert "انفجار اختباري" in stored[0]["message"]
    assert bot.sent, "المستخدم لم يُبلَّغ بأي شيء بعد الخطأ"


async def test_error_handler_ignores_network_noise(
    bot: FakeBot, context: FakeContext, repos, user: User
) -> None:
    """أخطاء الشبكة المؤقتة لا تُغرق جدول الأخطاء ولا تُزعج المستخدم."""
    from telegram.error import TimedOut

    await load_user(bot, context, user)
    update = make_message_update(bot, text="أي نص", user_id=user.telegram_id)
    context.error = TimedOut()

    await errors.error_handler(update, context)

    assert await repos.error_logs.list_recent(limit=5) == []
    assert bot.sent == []


async def test_error_handler_marks_blocked_user(
    bot: FakeBot, context: FakeContext, repos, user: User
) -> None:
    """حظر المستخدم للبوت يُعلَّم في قاعدة البيانات بدل تكرار محاولات الإرسال."""
    from telegram.error import Forbidden

    await load_user(bot, context, user)
    update = make_message_update(bot, text="أي نص", user_id=user.telegram_id)
    context.error = Forbidden("bot was blocked by the user")

    await errors.error_handler(update, context)

    refreshed = await repos.users.get_by_id(user.id)
    assert refreshed.blocked_bot == 1


# ========================= مسارات الإلغاء والتخطي ======================== #


async def test_cancel_order_flow_leaves_no_trace(
    bot: FakeBot,
    context: FakeContext,
    services: ServiceContainer,
    user: User,
    admin: User,
    mock_service: Service,
) -> None:
    """إلغاء مسار الطلب في منتصفه: لا طلب ولا خصم ولا بيانات محادثة متبقية."""
    from telegram.ext import ConversationHandler

    from handlers.user import order_flow

    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    await load_user(bot, context, user)

    await press(
        bot, context, order_flow.start_order, pack("new", "start", mock_service.id), user.telegram_id
    )
    await write(bot, context, order_flow.receive_link, "https://instagram.com/p/c", user.telegram_id)

    state = await press(
        bot, context, order_flow.cancel_order_flow, pack("flow", "cancel"), user.telegram_id
    )
    assert state == ConversationHandler.END
    assert order_flow.FLOW_KEY not in context.user_data
    assert await services.orders.count_for_user(user, statuses=()) == 0
    assert await services.wallet.balance_units(user.id) == 50_000
    assert bot.last.buttons, "شاشة الإلغاء بلا أزرار"


async def test_cancel_order_flow_by_command(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, mock_service: Service
) -> None:
    """الأمر /cancel داخل المحادثة يُنهيها كما يفعل الزر تماماً."""
    from telegram.ext import ConversationHandler

    from handlers.user import order_flow

    await load_user(bot, context, user)
    await press(
        bot, context, order_flow.start_order, pack("new", "start", mock_service.id), user.telegram_id
    )

    update = make_message_update(bot, text="/cancel", user_id=user.telegram_id)
    state = await order_flow.cancel_order_flow(update, context)
    assert state == ConversationHandler.END
    assert order_flow.FLOW_KEY not in context.user_data


async def test_skip_proof_when_optional(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, db, repos, user: User
) -> None:
    """طريقة دفع لا تطلب إثباتاً: زر «تخطي» ينقل المستخدم للملخص مباشرة."""
    async with db.transaction() as tx:
        method = await repos.payment_methods.create(
            tx,
            code="no_proof_wallet",
            name_ar="محفظة بلا إثبات",
            instructions_ar="حوّل فقط",
            requires_proof=0,
        )
    await load_user(bot, context, user)

    await press(bot, context, deposit.start_deposit, pack("dep", "start"), user.telegram_id)
    await press(bot, context, deposit.choose_method, pack("dep", "method", method.id), user.telegram_id)
    state = await write(bot, context, deposit.receive_amount, "15", user.telegram_id)

    assert state == deposit.CONFIRM, "طريقة بلا إثبات يجب أن تقفز للملخص مباشرة"
    assert any(b.startswith("flow:confirm") for b in bot.last.buttons)

    state = await press(
        bot, context, deposit.confirm_deposit, pack("flow", "confirm"), user.telegram_id
    )
    payments = await services.payments.list_for_user(user, limit=5)
    assert len(payments) == 1
    assert payments[0].amount_units == 150_000


async def test_cancel_support_flow(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User
) -> None:
    """إلغاء مسار التذكرة لا يترك تذكرة ولا بيانات محادثة."""
    from telegram.ext import ConversationHandler

    await load_user(bot, context, user)
    await press(bot, context, support.start_new_ticket, pack("sup", "new"), user.telegram_id)

    state = await press(
        bot, context, support.cancel_support_flow, pack("flow", "cancel"), user.telegram_id
    )
    assert state == ConversationHandler.END
    assert support.NEW_FLOW_KEY not in context.user_data
    assert await services.tickets.list_for_user(user, limit=5) == []


async def test_skip_proof_button_goes_to_summary(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, payment_method
) -> None:
    """زر «تخطي» في خطوة الإيصال ينتقل للملخص مع بقاء رقم العملية محفوظاً."""
    await load_user(bot, context, user)
    await press(bot, context, deposit.start_deposit, pack("dep", "start"), user.telegram_id)
    await press(
        bot, context, deposit.choose_method, pack("dep", "method", payment_method.id), user.telegram_id
    )
    await write(bot, context, deposit.receive_amount, "12", user.telegram_id)
    await write(bot, context, deposit.receive_reference, "TRX-SKIP-1", user.telegram_id)

    state = await press(bot, context, deposit.skip_proof, pack("flow", "skip"), user.telegram_id)
    assert state == deposit.CONFIRM
    assert any(b.startswith("flow:confirm") for b in bot.last.buttons)

    await press(bot, context, deposit.confirm_deposit, pack("flow", "confirm"), user.telegram_id)
    payments = await services.payments.list_for_user(user, limit=5)
    assert payments[0].transaction_reference == "TRX-SKIP-1"
    assert payments[0].proof_file_id is None
```

### `tests/integration/test_jobs.py`

```python
"""
اختبارات المهام الدورية (JobQueue) بلا مؤقتات حقيقية.

نستدعي دوال المهام مباشرة بسياق مزيّف — فنختبر المنطق والأثر في قاعدة
البيانات دون انتظار ثوانٍ، ودون أي اتصال بتيليجرام.
"""

from __future__ import annotations

import pytest

from core.enums import OrderStatus, PaymentStatus
from database.models import Service, User
from database.repositories import Repositories
from jobs import run_startup_recovery
from jobs.maintenance_jobs import auto_close_tickets, expire_old_payments
from jobs.notification_jobs import dispatch_notifications
from jobs.order_jobs import check_active_orders, submit_pending_orders
from jobs.telegram_sender import TelegramNotificationSender
from services import ServiceContainer
from tests.telegram_fakes import FakeBot, FakeContext

pytestmark = pytest.mark.asyncio


@pytest.fixture
def bot() -> FakeBot:
    """بوت مزيّف لتسجيل ما كان سيُرسل."""
    return FakeBot()


@pytest.fixture
def job_context(bot: FakeBot, services: ServiceContainer) -> FakeContext:
    """سياق مزيّف يحمل الخدمات كما تفعل JobQueue في التشغيل."""
    return FakeContext(bot, services)


async def test_dispatch_notifications_sends_and_marks(
    bot: FakeBot, job_context: FakeContext, services: ServiceContainer, db, user: User
) -> None:
    """مهمة الإشعارات ترسل ما في الطابور ولا تعيد إرساله في الجولة التالية."""
    async with db.transaction() as tx:
        await services.notifications.notify_user_manual(
            tx, user_id=user.id, token="job-test-1", title="عنوان", message="نص الإشعار"
        )
    assert await services.notifications.queued_count() == 1

    await dispatch_notifications(job_context)

    assert len(bot.sent) == 1
    assert "نص الإشعار" in bot.last.text
    assert await services.notifications.queued_count() == 0

    bot.clear()
    await dispatch_notifications(job_context)
    assert bot.sent == [], "أُعيد إرسال إشعار سبق إرساله"


async def test_blocked_user_notification_is_not_retried(
    bot: FakeBot, job_context: FakeContext, services: ServiceContainer, db, repos: Repositories, user: User
) -> None:
    """حظر المستخدم للبوت يُسجَّل ولا يبقى الإشعار يدور في الطابور إلى الأبد."""
    from telegram.error import Forbidden

    async def blocked_send(*_args, **_kwargs):
        """محاكاة رفض تيليجرام الإرسال لأن المستخدم حظر البوت."""
        raise Forbidden("bot was blocked by the user")

    bot.send_message = blocked_send                      # type: ignore[method-assign]

    async with db.transaction() as tx:
        await services.notifications.notify_user_manual(
            tx, user_id=user.id, token="job-blocked", title="عنوان", message="نص"
        )

    await dispatch_notifications(job_context)

    refreshed = await repos.users.get_by_id(user.id)
    assert refreshed.blocked_bot == 1
    assert await services.notifications.queued_count() == 0


async def test_order_jobs_complete_cycle(
    bot: FakeBot,
    job_context: FakeContext,
    services: ServiceContainer,
    user: User,
    admin: User,
    mock_service: Service,
    mock_client,
) -> None:
    """مهمة الإرسال ثم مهمة الفحص تنقلان الطلب إلى حالته النهائية تلقائياً."""
    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/job", quantity=1000
    )

    await submit_pending_orders(job_context)
    after_submit = await services.orders.get_for_user(user, order.id)
    assert after_submit.status in {OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS}

    mock_client.force_complete = True
    for _ in range(3):
        await check_active_orders(job_context)
        current = await services.orders.get_for_user(user, order.id)
        if current.status in {OrderStatus.COMPLETED, OrderStatus.PARTIAL}:
            break
        # تقديم موعد الفحص التالي يدوياً بدل انتظار الفاصل الزمني الحقيقي
        async with services.db.transaction() as tx:
            await tx.execute(
                "UPDATE orders SET next_check_at = ? WHERE id = ?",
                ("2020-01-01T00:00:00+00:00", order.id),
            )

    final = await services.orders.get_for_user(user, order.id)
    assert final.status == OrderStatus.COMPLETED


async def test_expire_old_payments_marks_expired(
    bot: FakeBot,
    job_context: FakeContext,
    services: ServiceContainer,
    db,
    repos: Repositories,
    user: User,
    payment_method,
) -> None:
    """طلب شحن تجاوز مهلته يُعلَّم منتهياً ويُشعر صاحبه (ولا يُضاف أي رصيد)."""
    payment = await services.payments.create_payment(
        user, method_id=payment_method.id, raw_amount="10", transaction_reference="TRX-EXP-1"
    )
    async with db.transaction() as tx:
        await tx.execute(
            "UPDATE payments SET expires_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", payment.id),
        )

    await expire_old_payments(job_context)

    refreshed = await services.payments.get_for_user(user, payment.id)
    assert refreshed.status == PaymentStatus.EXPIRED
    assert await services.wallet.balance_units(user.id) == 0


async def test_auto_close_tickets_job_runs(
    job_context: FakeContext, services: ServiceContainer, user: User
) -> None:
    """مهمة إغلاق التذاكر الراكدة تعمل بلا أخطاء ولا تغلق تذكرة حديثة."""
    ticket = await services.tickets.create_ticket(
        user, subject="سؤال", message="متى يصل الطلب؟", category="other"
    )
    await auto_close_tickets(job_context)
    still_open = await services.tickets.get_for_user(user, ticket.id)
    assert still_open.status != "closed"


async def test_startup_recovery_handles_stuck_submitting(
    services: ServiceContainer,
    db,
    repos: Repositories,
    user: User,
    admin: User,
    mock_service: Service,
) -> None:
    """طلب عالق في «جاري الإرسال» وقت الإغلاق يُنقل إلى حالة مراجعة لا إلى إرسال ثانٍ."""
    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/stuck", quantity=1000
    )
    async with db.transaction() as tx:
        await tx.execute(
            "UPDATE orders SET status = ?, locked_by = ?, locked_until = ? WHERE id = ?",
            (OrderStatus.SUBMITTING, "dead-worker", "2020-01-01T00:00:00+00:00", order.id),
        )

    result = await run_startup_recovery(services)

    refreshed = await repos.orders.get(order.id)
    assert refreshed.status == OrderStatus.SUBMIT_UNCERTAIN
    assert sum(result.values()) >= 1


async def test_telegram_sender_escapes_html(bot: FakeBot) -> None:
    """المرسل يهرّب وسوم HTML فلا يكسر التنسيق ولا يحقن وسوماً."""
    sender = TelegramNotificationSender(bot)
    await sender(123, "<b>عنوان", "نص فيه <script>alert(1)</script>")
    assert "&lt;script&gt;" in bot.last.text
    assert "<b>&lt;b&gt;عنوان</b>" in bot.last.text


async def test_alert_stuck_orders_notifies_admin(
    job_context: FakeContext,
    services: ServiceContainer,
    db,
    repos: Repositories,
    user: User,
    admin: User,
    mock_service: Service,
) -> None:
    """طلب متوقف منذ وقت طويل يُنتج تنبيهاً للأدمن مرة واحدة لا عند كل جولة."""
    from jobs.order_jobs import alert_stuck_orders

    await services.wallet.adjust_balance(
        target=user, amount_units=50_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/old", quantity=1000
    )
    async with db.transaction() as tx:
        await tx.execute(
            "UPDATE orders SET created_at = ?, updated_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00", order.id),
        )

    await alert_stuck_orders(job_context)
    first = await services.notifications.queued_count()

    await alert_stuck_orders(job_context)
    second = await services.notifications.queued_count()

    assert first >= 1, "لم يُنبَّه الأدمن بطلب متوقف"
    assert second == first, "تكرر التنبيه نفسه في الجولة الثانية"


async def test_schedule_jobs_registers_all_periodic_jobs(services: ServiceContainer) -> None:
    """الجدولة تضع كل المهام الدورية على JobQueue بأسمائها وفتراتها."""
    from telegram.ext import ApplicationBuilder

    from jobs import schedule_jobs

    application = ApplicationBuilder().token("123456789:AAJobsTestDummyTokenNotUsedAtAll").build()
    try:
        names = await schedule_jobs(application, services)
        scheduled = {job.name for job in application.job_queue.jobs()}
        assert scheduled == {
            "notifications_dispatch",
            "orders_submit",
            "orders_check",
            "payments_expire",
            "tickets_auto_close",
            "orders_stuck_alert",
        }
        assert len(names) == len(scheduled)
    finally:
        await application.shutdown()
```

