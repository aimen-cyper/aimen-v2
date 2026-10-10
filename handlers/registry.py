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
from handlers.user import account, catalog, deposit, favorites, order_flow, orders, support, wallet
from keyboards.callback_data import (
    NS_ACCOUNT,
    NS_CATALOG,
    NS_DEPOSIT,
    NS_NAV,
    NS_SUB,
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
        CallbackQueryHandler(navigation.subscription_check_callback, pattern=pattern(NS_SUB, "check")),
        # الخدمات
        CallbackQueryHandler(catalog.categories_screen, pattern=pattern(NS_CATALOG, "list")),
        CallbackQueryHandler(catalog.services_screen, pattern=pattern(NS_CATALOG, "open")),
        CallbackQueryHandler(catalog.service_card_screen, pattern=pattern(NS_CATALOG, "svc")),
        *favorites.handlers(),
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
        CallbackQueryHandler(account.help_screen, pattern=pattern(NS_ACCOUNT, "help")),
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

    for conversation_handler in conversation_handlers():
        handlers.append((MAIN_GROUP, conversation_handler))

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
