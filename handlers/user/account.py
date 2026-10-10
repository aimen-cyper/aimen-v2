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
from keyboards.user_kb import account_kb, help_kb, info_kb, notifications_kb
from middlewares.context import require_user, services_of
from texts import ar, help_ar
from utils.formatters import datetime_text, member_days, money_text, notification_line, safe

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

    days = member_days(user.created_at)
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
        member_days=ar.MEMBER_DAYS.format(days=days) if days else ar.MEMBER_TODAY,
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


@guarded
async def help_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    «📖 التعليمات»: بلا وسيط ⇒ الفهرس؛ وبرمز موضوع ⇒ صفحة الموضوع مع تنقل سابق/تالي.

    موضوع غير معروف (زر قديم أو callback معدَّل) يُرد بتنبيه ويُعرض الفهرس — لا استثناء ولا شاشة فارغة.
    """
    data = unpack(update.callback_query.data if update.callback_query else None)
    topic = data.arg(0, "")
    if not topic:
        await answer_callback(update)
        await render(update, context, help_ar.HELP_INDEX, help_kb(None))
        return
    if topic not in help_ar.HELP_PAGES:
        await answer_callback(update, help_ar.HELP_TOPIC_UNKNOWN, alert=True)
        await render(update, context, help_ar.HELP_INDEX, help_kb(None))
        return
    await answer_callback(update)
    text = help_ar.HELP_PAGES[topic]
    if topic == "contact":
        support = safe(await services_of(context).settings.get_str("support_username", ""))
        text = text.format(support=support or help_ar.HELP_SUPPORT_FALLBACK)
    await render(update, context, text, help_kb(topic))
