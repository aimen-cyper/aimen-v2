"""
المفضلة: إضافة/إزالة خدمة من بطاقتها، وقائمة المفضلة من القائمة الرئيسية.

الشاشات:
    fav:list:<صفحة>                   : قائمة المفضلة (المتاحة للطلب فقط).
    fav:add:<خدمة>:<تصنيف>:<صفحة>     : إضافة (بلا تكرار) ثم تحديث البطاقة نفسها.
    fav:del:<خدمة>:<تصنيف>:<صفحة>     : إزالة ثم تحديث البطاقة نفسها.
التصنيف 0 يعني أن البطاقة فُتحت من المفضلة.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from core.exceptions import ServiceNotAvailableError
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render
from handlers.user.catalog import show_service_card
from keyboards.callback_data import NS_FAV, pattern, unpack
from keyboards.user_kb import favorites_kb
from middlewares.context import require_user, services_of
from texts import ar

#: عدد الخدمات في صفحة المفضلة
PAGE_SIZE = 6


@guarded
async def favorites_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة مفضلة المستخدم (الأحدث إضافةً أولاً)."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    services = services_of(context)
    user = require_user(context)
    items, page, pages = await services.catalog.favorites_page(user, page=data.int_arg(0, 1), page_size=PAGE_SIZE)
    symbol = await services.settings.money_symbol()
    usd_rate = await services.settings.usd_rate()
    if not items:
        await render(update, context, ar.FAVORITES_EMPTY, favorites_kb([], page=1, total_pages=1, symbol=symbol, usd_rate=usd_rate))
        return
    await render(
        update,
        context,
        ar.FAVORITES_TITLE.format(page=page, pages=pages),
        favorites_kb(items, page=page, total_pages=pages, symbol=symbol, usd_rate=usd_rate),
    )


@guarded
async def favorite_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إضافة/إزالة ثم إعادة عرض بطاقة الخدمة (تحرير نفس الرسالة)."""
    data = unpack(update.callback_query.data if update.callback_query else None)
    service_id, category_id, page = data.int_arg(0), data.int_arg(1), max(1, data.int_arg(2, 1))
    services = services_of(context)
    user = require_user(context)
    try:
        if data.action == "add":
            added = await services.catalog.add_favorite(user, service_id)
            await answer_callback(update, ar.FAVORITE_ADDED if added else ar.FAVORITE_EXISTS)
        else:
            removed = await services.catalog.remove_favorite(user, service_id)
            await answer_callback(update, ar.FAVORITE_REMOVED if removed else ar.FAVORITE_NOT_FOUND)
    except ServiceNotAvailableError:
        await answer_callback(update, "❌ هذه الخدمة لم تعد متاحة", alert=True)
        await favorites_screen(update, context)
        return
    await show_service_card(update, context, service_id, category_id, page)


def handlers() -> list[CallbackQueryHandler]:
    """أزرار المفضلة."""
    return [
        CallbackQueryHandler(favorites_screen, pattern=pattern(NS_FAV, "list")),
        CallbackQueryHandler(favorite_toggle, pattern=pattern(NS_FAV, "add")),
        CallbackQueryHandler(favorite_toggle, pattern=pattern(NS_FAV, "del")),
    ]
