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
