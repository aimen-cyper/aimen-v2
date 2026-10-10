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
from utils.formatters import local_amount, price_pair, safe

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
    usd_rate = await services.settings.usd_rate()
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
            usd_rate=usd_rate,
        ),
    )


@guarded
async def service_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة خدمة واحدة: الرقم، السعر بالدولار ومقابله، السرعة/الجودة/الضمان، الحدّان، ورصيد المستخدم."""
    await answer_callback(update)
    data = unpack(update.callback_query.data if update.callback_query else None)
    await show_service_card(update, context, data.int_arg(0), data.int_arg(1), max(1, data.int_arg(2, 1)))


async def show_service_card(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int, category_id: int, page: int
) -> None:
    """
    عرض بطاقة خدمة (تُستعمل من التصفح ومن المفضلة ومن تبديل ⭐ دون تكرار الكود).

    الحقول الناقصة تُعرض «غير محددة» لا فراغاً؛ والسرعة تسقط إلى `avg_time_text` القديم إن لم تُضبط.
    """
    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    usd_rate = await services.settings.usd_rate()
    service = await services.catalog.get_available_service(service_id)
    balance_units = (await services.users.get(user.id) or user).balance_units

    usd, local = price_pair(service.price_per_1000_units, symbol, usd_rate)
    if usd:
        price_lines = ar.SERVICE_PRICE_LINES_USD.format(
            usd=usd, local=local, rate=f"{usd_rate.normalize():f}", symbol=safe(symbol)
        )
    else:
        price_lines = ar.SERVICE_PRICE_LINES_LOCAL.format(local=local)
    description = f"📝 {safe(service.description, limit=300)}\n" if service.description else ""
    text = ar.SERVICE_CARD.format(
        name=safe(service.name),
        service_id=service.id,
        price_lines=price_lines,
        speed=safe(service.speed_text or service.avg_time_text) or ar.FIELD_UNSET,
        quality=safe(service.quality_text) or ar.FIELD_UNSET,
        guarantee=safe(service.guarantee_text) or ar.FIELD_UNSET,
        min_quantity=f"{service.min_quantity:,}",
        max_quantity=f"{service.max_quantity:,}",
        description=description,
        balance=local_amount(balance_units, symbol),
    )
    favorite = await services.catalog.is_favorite(user, service.id)
    await render(
        update, context, text, service_card_kb(service, category_id=category_id, page=page, is_favorite=favorite)
    )
