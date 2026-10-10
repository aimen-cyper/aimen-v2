"""
قسم «🛍 الكتالوج» في لوحة التحكم: التصنيفات والخدمات وأسعارها.

ما ينفّذه هذا الملف:
    • عرض كل التصنيفات (حتى الفارغة والمعطّلة — الأدمن يرى ما لا يراه العميل).
    • قائمة خدمات التصنيف مع مؤشر التفعيل والسعر.
    • بطاقة الخدمة: السعر، تكلفة المزود، الهامش، الحدود، الحالة.
    • تفعيل/تعطيل الخدمة، تغيير السعر (مع تحذير البيع بخسارة)، الأرشفة.
    • إنشاء تصنيف جديد.
    • إنشاء خدمة جديدة يدوياً (أُضيف في المرحلة 5 بعد توفّر شاشات المزودين):
      تصنيف ← مزود ← رقم الخدمة لديه ← اسم ← تكلفة ← سعر ← حدود ← تأكيد.

الاستيراد الجماعي من قائمة المزود ومزامنة الأسعار موجودان في قسم «🔌 المزودون»
(`handlers/admin/providers.py`) لأنهما يبدآن من المزود لا من الكتالوج.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from core.exceptions import ValidationError
from core.permissions import Permission
from handlers.common.conversation import conversation
from handlers.admin.common import (
    ADMIN_FLOW_KEY,
    PAGE_SIZE,
    admin_required,
    args,
    cancel_admin_flow,
    clear_flow,
    flow,
    permissions_of,
    start_flow,
    symbol_of,
    update_flow,
)
from handlers.common.fallbacks import exit_conversation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    back_panel_kb,
    cancel_only_kb,
    catalog_home_kb,
    catalog_search_results_kb,
    catalog_services_kb,
    category_picker_kb,
    confirm_cancel_kb,
    provider_picker_kb,
    service_card_kb,
    service_edit_fields_kb,
    service_rule_picker_kb,
    skip_cancel_kb,
)
from keyboards.callback_data import NS_ADM_CAT, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from core.money import format_usd
from utils.formatters import money_text, safe
from utils.link_rules import LINK_RULES, rule_label
from utils.logging_setup import get_logger
from utils.validators import (
    clean_text,
    normalize_digits,
    parse_amount_units,
    validate_amount_range,
)

logger = get_logger(__name__)

#: حالات محادثة تغيير السعر
ASK_PRICE, CONFIRM_PRICE = range(2)

#: حالة محادثة الأرشفة
CONFIRM_ARCHIVE = 20

#: حالات محادثة إنشاء تصنيف
ASK_CATEGORY_NAME, ASK_CATEGORY_EMOJI = range(10, 12)

#: حالات محادثة إنشاء خدمة جديدة يدوياً (المرحلة 5)
(
    NEW_PICK_CATEGORY,
    NEW_PICK_PROVIDER,
    NEW_ASK_PROVIDER_SERVICE_ID,
    NEW_ASK_NAME,
    NEW_ASK_COST,
    NEW_ASK_PRICE,
    NEW_ASK_MIN,
    NEW_ASK_MAX,
    NEW_CONFIRM,
) = range(30, 39)


async def _render_service(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int, *, as_new: bool = False
) -> None:
    """عرض بطاقة خدمة بعد أي إجراء عليها."""
    services = services_of(context)
    admin = require_user(context)
    service = await services.catalog.admin_get_service(admin, service_id)
    category = await services.catalog.admin_get_category(admin, service.category_id)
    provider = await services.providers.get(service.provider_id)
    symbol = await symbol_of(context)
    perms = await permissions_of(context)

    margin = service.margin_units
    usd_rate = await services.settings.usd_rate()
    text = t.SERVICE_CARD.format(
        name=safe(service.name, limit=60),
        service_id=service.id,
        category=safe(category.title, limit=30),
        provider=safe(provider.name if provider else t.SERVICE_UNKNOWN_PROVIDER, limit=25),
        provider_id=service.provider_id,
        provider_service_id=safe(service.provider_service_id, limit=20),
        price=money_text(service.price_per_1000_units, symbol),
        usd=(f" ({usd_text})" if (usd_text := format_usd(service.price_per_1000_units, usd_rate)) else ""),
        speed=safe(service.speed_text or service.avg_time_text) or "غير محددة",
        quality=safe(service.quality_text) or "غير محددة",
        guarantee=safe(service.guarantee_text) or "غير محددة",
        link_rule=rule_label(service.link_rule),
        cost=money_text(service.provider_price_per_1000_units, symbol)
        if service.provider_price_per_1000_units
        else "—",
        margin=money_text(margin, symbol) if margin is not None else t.SERVICE_MARGIN_UNKNOWN,
        min_quantity=service.min_quantity,
        max_quantity=service.max_quantity,
        status=t.SERVICE_STATUS_ACTIVE if service.is_active else t.SERVICE_STATUS_INACTIVE,
        archived_line=t.SERVICE_ARCHIVED_LINE if service.is_archived else "",
        description_line=t.SERVICE_DESCRIPTION_LINE.format(
            description=safe(service.description, limit=200)
        )
        if service.description
        else "",
    )
    markup = service_card_kb(service, perms)
    if as_new:
        await send(update, context, text, markup)
    else:
        await render(update, context, text, markup)


#: حالات محادثة «تعديل بيانات العرض»
EDIT_PICK_FIELD, EDIT_ASK_VALUE, EDIT_PICK_RULE = range(50, 53)

#: رمز الحقل في الزر ⇒ اسم العمود
_EDIT_FIELDS = {"speed": "speed_text", "quality": "quality_text", "guarantee": "guarantee_text", "rule": "link_rule"}


# ============================= شاشات القراءة =========================== #


@guarded
@admin_required(Permission.SERVICES_VIEW)
async def catalog_home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة الكتالوج: كل التصنيفات."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    categories = await services.catalog.admin_categories(admin)
    perms = await permissions_of(context)
    active_services = await services.catalog.active_services_count()

    text = (
        t.CATALOG_HOME.format(categories=len(categories), active_services=active_services)
        if categories
        else t.CATALOG_NO_CATEGORIES
    )
    await render(update, context, text, catalog_home_kb(categories, perms))


@guarded
@admin_required(Permission.SERVICES_VIEW)
async def category_services_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة خدمات تصنيف (تشمل المعطّلة)."""
    await answer_callback(update)
    data = args(update)
    category_id = data.int_arg(0)
    services = services_of(context)
    admin = require_user(context)
    symbol = await symbol_of(context)

    category = await services.catalog.admin_get_category(admin, category_id)
    page_data = await services.catalog.admin_services_page(
        admin, category_id, page=data.int_arg(1, 1), page_size=PAGE_SIZE
    )

    if not page_data.items:
        await render(
            update,
            context,
            t.CATALOG_SERVICES_EMPTY,
            catalog_services_kb(
                [], category_id=category_id, page=1, total_pages=1, symbol=symbol
            ),
        )
        return

    await render(
        update,
        context,
        t.CATALOG_SERVICES_TITLE.format(
            category=safe(category.title, limit=40),
            count=page_data.total_items,
            page=page_data.page,
            pages=page_data.total_pages,
        ),
        catalog_services_kb(
            page_data.items,
            category_id=category_id,
            page=page_data.page,
            total_pages=page_data.total_pages,
            symbol=symbol,
        ),
    )


@guarded
@admin_required(Permission.SERVICES_VIEW)
async def service_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة خدمة واحدة."""
    await answer_callback(update)
    await _render_service(update, context, args(update).int_arg(0))


@guarded
@admin_required(Permission.SERVICES_UPDATE)
async def toggle_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تفعيل أو تعطيل خدمة (الحالة تنعكس فوراً على واجهة العملاء)."""
    services = services_of(context)
    admin = require_user(context)
    service_id = args(update).int_arg(0)
    service = await services.catalog.admin_get_service(admin, service_id)

    await services.catalog.set_service_active(admin, service_id, not service.is_active)
    await answer_callback(
        update,
        t.SERVICE_TOGGLED_OFF if service.is_active else t.SERVICE_TOGGLED_ON,
        alert=False,
    )
    await _render_service(update, context, service_id)


# ============================ محادثة بحث الخدمات ========================== #

#: مفتاح حفظ نص آخر بحث لدى الأدمن (للتنقل بين صفحات النتائج بلا تضخيم callback_data)
SEARCH_TERM_KEY = "admin_service_search_term"
ASK_SEARCH_TERM = 60


async def _show_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE, term: str, page: int) -> None:
    """تنفيذ البحث وعرض الصفحة المطلوبة من النتائج (تحرير الرسالة الحالية أو إرسال جديدة)."""
    services = services_of(context)
    admin = require_user(context)
    symbol = await symbol_of(context)
    result = await services.catalog.admin_search_services(admin, term, page=page, page_size=PAGE_SIZE)
    if not result.items:
        await render(
            update,
            context,
            t.CATALOG_SEARCH_EMPTY.format(term=safe(term, limit=40)),
            catalog_search_results_kb([], page=1, total_pages=1, symbol=symbol),
        )
        return
    await render(
        update,
        context,
        t.CATALOG_SEARCH_TITLE.format(
            term=safe(term, limit=40), total=result.total_items, page=result.page, pages=result.total_pages
        ),
        catalog_search_results_kb(result.items, page=result.page, total_pages=result.total_pages, symbol=symbol),
    )


@guarded
@admin_required(Permission.SERVICES_VIEW)
async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء البحث عن خدمة: سؤال النص المطلوب."""
    await answer_callback(update)
    start_flow(context)
    await render(update, context, t.CATALOG_SEARCH_ASK, cancel_only_kb())
    return ASK_SEARCH_TERM


@guarded
@admin_required(Permission.SERVICES_VIEW)
async def receive_search_term(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استلام نص البحث وعرض النتائج؛ المحادثة تنتهي والتنقل بين الصفحات بأزرار `ac:found`."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_SEARCH_TERM
    term = message.text.strip()
    # الفشل المتوقع (نص قصير جداً) يبقي المحادثة في نفس الخطوة عبر @guarded فلا يُحفظ النص
    await _show_search_results(update, context, term, 1)
    if context.user_data is not None:
        context.user_data[SEARCH_TERM_KEY] = term          # للتنقل بين الصفحات بلا تضخيم callback_data
    clear_flow(context)
    return ConversationHandler.END


@guarded
@admin_required(Permission.SERVICES_VIEW)
async def search_page_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """صفحة أخرى من نتائج آخر بحث (النص محفوظ بالذاكرة؛ إن ضاع بإعادة التشغيل يُطلب بحث جديد)."""
    await answer_callback(update)
    term = (context.user_data or {}).get(SEARCH_TERM_KEY)
    if not term:
        await render(update, context, t.CATALOG_SEARCH_EXPIRED, back_panel_kb())
        return
    await _show_search_results(update, context, term, args(update).int_arg(0, 1))


# ======================= محادثة تعديل بيانات العرض ======================= #


@guarded
@admin_required(Permission.SERVICES_UPDATE)
async def start_edit_display(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء تعديل السرعة/الجودة/الضمان/قاعدة الرابط: عرض قائمة الحقول."""
    await answer_callback(update)
    service_id = args(update).int_arg(0)
    services = services_of(context)
    await services.catalog.admin_get_service(require_user(context), service_id)
    start_flow(context, service_id=service_id)
    await render(
        update,
        context,
        t.SERVICE_EDIT_PICK.format(service_id=service_id),
        service_edit_fields_kb(),
    )
    return EDIT_PICK_FIELD


@guarded
@admin_required(Permission.SERVICES_UPDATE)
async def pick_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """اختيار الحقل: نصي ⇒ نسأل القيمة، وقاعدة الرابط ⇒ نعرض قائمة القواعد."""
    await answer_callback(update)
    data = flow(context)
    service_id = int(data.get("service_id") or 0)
    code = str(args(update).arg(0) or "")
    field = _EDIT_FIELDS.get(code)
    if not service_id or field is None:
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END
    services = services_of(context)
    service = await services.catalog.admin_get_service(require_user(context), service_id)
    update_flow(context, field=field)

    if field == "link_rule":
        await render(
            update,
            context,
            t.SERVICE_EDIT_RULE_PICK.format(service_id=service_id, current=rule_label(service.link_rule)),
            service_rule_picker_kb(list(LINK_RULES.values()), current=service.link_rule),
        )
        return EDIT_PICK_RULE
    current = getattr(service, field) or "غير محددة"
    await render(
        update,
        context,
        t.SERVICE_EDIT_ASK.format(
            label=t.SERVICE_EDIT_FIELD_LABELS[field], service_id=service_id, current=safe(current, limit=60)
        ),
        cancel_only_kb(),
    )
    return EDIT_ASK_VALUE


async def _finish_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, value: str | None) -> int:
    """حفظ الحقل عبر الخدمة المركزية (تدقيق + صلاحية) ثم عرض بطاقة الخدمة."""
    data = flow(context)
    service_id = int(data.get("service_id") or 0)
    field = str(data.get("field") or "")
    if not service_id or field not in _EDIT_FIELDS.values():
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END
    await services_of(context).catalog.admin_set_display_field(require_user(context), service_id, field, value)
    clear_flow(context)
    await send(
        update,
        context,
        t.SERVICE_EDIT_DONE.format(label=t.SERVICE_EDIT_FIELD_LABELS[field], service_id=service_id),
    )
    await _render_service(update, context, service_id, as_new=True)
    return ConversationHandler.END


@guarded
@admin_required(Permission.SERVICES_UPDATE)
async def receive_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال نص السرعة/الجودة/الضمان؛ `-` يمسح الحقل."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return EDIT_ASK_VALUE
    text = message.text.strip()
    return await _finish_edit(update, context, None if text == "-" else text)


@guarded
@admin_required(Permission.SERVICES_UPDATE)
async def pick_edit_rule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """اختيار قاعدة الرابط (0 = بلا قيد، وإلا ترتيب القاعدة في `LINK_RULES` ابتداءً من 1)."""
    await answer_callback(update)
    index = args(update).int_arg(0, -1)
    keys = list(LINK_RULES)
    if index < 0 or index > len(keys):
        await answer_callback(update, t.ERR_SESSION_LOST, alert=True)
        return ConversationHandler.END
    return await _finish_edit(update, context, None if index == 0 else keys[index - 1])


# =========================== محادثة تغيير السعر ======================== #


@guarded
@admin_required(Permission.SERVICES_PRICE)
async def start_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء تغيير سعر خدمة."""
    await answer_callback(update)
    service_id = args(update).int_arg(0)
    services = services_of(context)
    admin = require_user(context)
    service = await services.catalog.admin_get_service(admin, service_id)
    symbol = await symbol_of(context)
    start_flow(context, service_id=service_id)

    await render(
        update,
        context,
        t.SERVICE_ASK_PRICE.format(
            name=safe(service.name, limit=50),
            price=money_text(service.price_per_1000_units, symbol),
            cost=money_text(service.provider_price_per_1000_units, symbol)
            if service.provider_price_per_1000_units
            else "—",
        ),
        cancel_only_kb(),
    )
    return ASK_PRICE


@guarded
@admin_required(Permission.SERVICES_PRICE)
async def receive_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    استقبال السعر الجديد.

    إن كان أقل من تكلفة المزود نعرض شاشة تأكيد إضافية (بيع بخسارة)، وإلا
    نُنفّذ مباشرة لأن التغيير غير خطير ماليّاً على المستخدمين.
    """
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_PRICE

    data = flow(context)
    if not data.get("service_id"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    units = validate_amount_range(parse_amount_units(message.text), min_units=1, label="السعر")
    services = services_of(context)
    admin = require_user(context)
    service = await services.catalog.admin_get_service(admin, int(data["service_id"]))
    symbol = await symbol_of(context)

    cost = service.provider_price_per_1000_units or 0
    if cost and units < cost:
        update_flow(context, price_units=units)
        await send(update, context, t.SERVICE_PRICE_BELOW_COST, confirm_cancel_kb())
        return CONFIRM_PRICE

    await services.catalog.change_price(admin, service.id, units)
    clear_flow(context)
    await send(update, context, t.SERVICE_PRICE_DONE.format(price=money_text(units, symbol)))
    await _render_service(update, context, service.id, as_new=True)
    return ConversationHandler.END


@guarded
@admin_required(Permission.SERVICES_PRICE)
async def confirm_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تأكيد سعر أقل من تكلفة المزود."""
    await answer_callback(update)
    data = flow(context)
    if not data.get("service_id") or not data.get("price_units"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    service_id = int(data["service_id"])
    units = int(data["price_units"])
    symbol = await symbol_of(context)

    await services.catalog.change_price(admin, service_id, units)
    clear_flow(context)
    logger.info("غيّر الأدمن %s سعر الخدمة %s إلى %s", admin.telegram_id, service_id, units)

    await render(update, context, t.SERVICE_PRICE_DONE.format(price=money_text(units, symbol)))
    await _render_service(update, context, service_id, as_new=True)
    return ConversationHandler.END


# ============================ محادثة الأرشفة =========================== #


@guarded
@admin_required(Permission.SERVICES_ARCHIVE)
async def start_archive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """عرض تأكيد أرشفة الخدمة (إخفاؤها نهائياً عن العملاء)."""
    await answer_callback(update)
    service_id = args(update).int_arg(0)
    services = services_of(context)
    admin = require_user(context)
    service = await services.catalog.admin_get_service(admin, service_id)
    start_flow(context, service_id=service_id)

    await render(
        update,
        context,
        t.SERVICE_ARCHIVE_CONFIRM.format(name=safe(service.name, limit=50)),
        confirm_cancel_kb(),
    )
    return CONFIRM_ARCHIVE


@guarded
@admin_required(Permission.SERVICES_ARCHIVE)
async def confirm_archive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ الأرشفة بعد التأكيد."""
    await answer_callback(update)
    data = flow(context)
    if not data.get("service_id"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    service_id = int(data["service_id"])
    await services.catalog.archive_service(admin, service_id)
    clear_flow(context)

    await render(update, context, t.SERVICE_ARCHIVED)
    await _render_service(update, context, service_id, as_new=True)
    return ConversationHandler.END


# ========================== محادثة تصنيف جديد ========================== #


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def start_new_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء إنشاء تصنيف جديد."""
    await answer_callback(update)
    start_flow(context)
    await render(update, context, t.CATEGORY_ASK_NAME, cancel_only_kb())
    return ASK_CATEGORY_NAME


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def receive_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال اسم التصنيف ثم سؤال الأيقونة (قابلة للتخطي)."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_CATEGORY_NAME

    name = clean_text(message.text, field="اسم التصنيف", max_length=60, min_length=2)
    update_flow(context, name=name)
    await send(update, context, t.CATEGORY_ASK_EMOJI, skip_cancel_kb())
    return ASK_CATEGORY_EMOJI


async def _create_category(
    update: Update, context: ContextTypes.DEFAULT_TYPE, emoji: str
) -> int:
    """إنشاء التصنيف فعلياً وعرض الكتالوج محدَّثاً."""
    data = flow(context)
    if not data.get("name"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    category = await services.catalog.create_category(
        admin, name_ar=str(data["name"]), emoji=emoji
    )
    clear_flow(context)
    logger.info("أنشأ الأدمن %s التصنيف %s", admin.telegram_id, category.id)

    await send(update, context, t.CATEGORY_CREATED.format(name=safe(category.title, limit=40)))
    await catalog_home_screen(update, context)
    return ConversationHandler.END


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def receive_category_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال أيقونة التصنيف وإنشاؤه."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, skip_cancel_kb())
        return ASK_CATEGORY_EMOJI
    emoji = clean_text(message.text, field="الأيقونة", max_length=4, min_length=1)
    return await _create_category(update, context, emoji)


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def skip_category_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تخطي الأيقونة واستخدام الافتراضية."""
    await answer_callback(update)
    return await _create_category(update, context, "📦")


# ====================== محادثة: إنشاء خدمة جديدة يدوياً ================== #


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def start_new_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    بدء إنشاء خدمة: اختيار التصنيف.

    تُرفض البداية إن لم يوجد أي مزود، لأن خدمة بلا مزود تعني طلباً لا يمكن تنفيذه.
    """
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)

    providers = await services.providers.list_all()
    if not providers:
        await render(update, context, t.SERVICE_NEW_NO_PROVIDER, back_panel_kb())
        return ConversationHandler.END

    categories = await services.catalog.admin_categories(admin)
    if not categories:
        await render(update, context, t.CATALOG_NO_CATEGORIES, back_panel_kb())
        return ConversationHandler.END

    start_flow(context)
    await render(
        update,
        context,
        t.SERVICE_NEW_ASK_CATEGORY,
        category_picker_kb(categories, NS_ADM_CAT, "ncat"),
    )
    return NEW_PICK_CATEGORY


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def new_service_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ التصنيف المختار ثم عرض قائمة المزودين."""
    await answer_callback(update)
    category_id = args(update).int_arg(0)
    services = services_of(context)
    admin = require_user(context)
    await services.catalog.admin_get_category(admin, category_id)     # يتحقق من وجوده
    update_flow(context, category_id=category_id)

    providers = await services.providers.list_all()
    await render(
        update,
        context,
        t.SERVICE_NEW_ASK_PROVIDER,
        provider_picker_kb(providers, NS_ADM_CAT, "nprv"),
    )
    return NEW_PICK_PROVIDER


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def new_service_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ المزود المختار ثم طلب رقم الخدمة لديه."""
    await answer_callback(update)
    provider_id = args(update).int_arg(0)
    services = services_of(context)
    provider = await services.providers.get(provider_id)
    if provider is None:
        await answer_callback(update, t.PROVIDER_NOT_FOUND, alert=True)
        return NEW_PICK_PROVIDER

    update_flow(context, provider_id=provider_id, provider_name=provider.name)
    await render(
        update,
        context,
        t.SERVICE_NEW_ASK_PROVIDER_SERVICE_ID.format(provider=safe(provider.name, limit=30)),
        cancel_only_kb(),
    )
    return NEW_ASK_PROVIDER_SERVICE_ID


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def new_service_provider_service_id(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """حفظ رقم الخدمة لدى المزود ثم طلب الاسم الذي سيراه العميل."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return NEW_ASK_PROVIDER_SERVICE_ID

    provider_service_id = clean_text(
        normalize_digits(message.text), field="رقم الخدمة لدى المزود", max_length=40, min_length=1
    )
    update_flow(context, provider_service_id=provider_service_id)
    await send(update, context, t.SERVICE_NEW_ASK_NAME, cancel_only_kb())
    return NEW_ASK_NAME


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def new_service_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ اسم الخدمة ثم طلب تكلفة الألف لدى المزود."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return NEW_ASK_NAME

    name = clean_text(message.text, field="اسم الخدمة", max_length=120, min_length=3)
    update_flow(context, name=name)
    await send(update, context, t.SERVICE_NEW_ASK_COST, cancel_only_kb())
    return NEW_ASK_COST


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def new_service_cost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ تكلفة المزود ثم طلب سعر البيع."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return NEW_ASK_COST

    cost = validate_amount_range(parse_amount_units(message.text), min_units=1, label="التكلفة")
    update_flow(context, cost_units=cost)
    symbol = await symbol_of(context)
    await send(
        update,
        context,
        t.SERVICE_NEW_ASK_PRICE.format(cost=money_text(cost, symbol)),
        cancel_only_kb(),
    )
    return NEW_ASK_PRICE


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def new_service_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ سعر البيع ثم طلب أقل كمية."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return NEW_ASK_PRICE

    price = validate_amount_range(parse_amount_units(message.text), min_units=1, label="السعر")
    update_flow(context, price_units=price)
    await send(update, context, t.SERVICE_NEW_ASK_MIN, cancel_only_kb())
    return NEW_ASK_MIN


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def new_service_min(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ أقل كمية ثم طلب أكبر كمية."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return NEW_ASK_MIN

    raw = normalize_digits(message.text.strip())
    if not raw.isdigit() or int(raw) <= 0:
        raise ValidationError(
            f"أقل كمية غير صالحة: {raw}", user_message="❌ أرسل عدداً صحيحاً موجباً."
        )
    update_flow(context, min_quantity=int(raw))
    await send(update, context, t.SERVICE_NEW_ASK_MAX.format(min_q=int(raw)), cancel_only_kb())
    return NEW_ASK_MAX


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def new_service_max(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ أكبر كمية ثم عرض ملخص التأكيد (مع تحذير صريح عند البيع بخسارة)."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return NEW_ASK_MAX

    data = flow(context)
    minimum = int(data.get("min_quantity", 0))
    raw = normalize_digits(message.text.strip())
    if not raw.isdigit() or int(raw) <= minimum:
        await send(update, context, t.SERVICE_NEW_BAD_MAX.format(min_q=minimum), cancel_only_kb())
        return NEW_ASK_MAX

    data = update_flow(context, max_quantity=int(raw))
    services = services_of(context)
    admin = require_user(context)
    category = await services.catalog.admin_get_category(admin, int(data["category_id"]))
    symbol = await symbol_of(context)
    price = int(data["price_units"])
    cost = int(data["cost_units"])

    await send(
        update,
        context,
        t.SERVICE_NEW_CONFIRM.format(
            name=safe(str(data["name"]), limit=60),
            category=safe(category.title, limit=30),
            provider=safe(str(data.get("provider_name", "—")), limit=30),
            provider_service_id=safe(str(data["provider_service_id"]), limit=20),
            cost=money_text(cost, symbol),
            price=money_text(price, symbol),
            profit=money_text(price - cost, symbol),
            min_q=minimum,
            max_q=int(raw),
            warning=t.SERVICE_NEW_WARN_LOSS if price < cost else t.SERVICE_NEW_WARN_OK,
        ),
        confirm_cancel_kb(),
    )
    return NEW_CONFIRM


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def confirm_new_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إنشاء الخدمة فعلياً بعد التأكيد (التدقيق داخل `CatalogService.create_service`)."""
    await answer_callback(update)
    data = flow(context)
    required = (
        "category_id",
        "provider_id",
        "provider_service_id",
        "name",
        "cost_units",
        "price_units",
        "min_quantity",
        "max_quantity",
    )
    if any(key not in data for key in required):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    service = await services.catalog.create_service(
        admin,
        category_id=int(data["category_id"]),
        provider_id=int(data["provider_id"]),
        provider_service_id=str(data["provider_service_id"]),
        name=str(data["name"]),
        price_per_1000_units=int(data["price_units"]),
        min_quantity=int(data["min_quantity"]),
        max_quantity=int(data["max_quantity"]),
        provider_price_per_1000_units=int(data["cost_units"]),
    )
    clear_flow(context)
    logger.info("أنشأ الأدمن %s الخدمة %s يدوياً", admin.telegram_id, service.id)

    await render(
        update,
        context,
        t.SERVICE_NEW_DONE.format(name=safe(service.name, limit=60), service_id=service.id),
    )
    await _render_service(update, context, service.id, as_new=True)
    return ConversationHandler.END


# ============================== التسجيل ================================ #


def _fallbacks() -> list:
    """المسارات الاحتياطية الموحّدة لمحادثات هذا القسم."""
    return [
        CallbackQueryHandler(cancel_admin_flow, pattern=pattern(NS_FLOW, "cancel")),
        CommandHandler("cancel", cancel_admin_flow),
        CommandHandler("start", exit_conversation(ADMIN_FLOW_KEY)),
    ]


def conversations() -> list[ConversationHandler]:
    """محادثات الكتالوج: تغيير السعر، الأرشفة، تصنيف جديد، خدمة جديدة."""
    edit_display = conversation(
        entry_points=[CallbackQueryHandler(start_edit_display, pattern=pattern(NS_ADM_CAT, "edit"))],
        states={
            EDIT_PICK_FIELD: [CallbackQueryHandler(pick_edit_field, pattern=pattern(NS_ADM_CAT, "fld"))],
            EDIT_ASK_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edit_value)],
            EDIT_PICK_RULE: [CallbackQueryHandler(pick_edit_rule, pattern=pattern(NS_ADM_CAT, "rul"))],
        },
        fallbacks=_fallbacks(),
        name="admin_service_display",
        per_chat=True,
        per_user=True,
    )

    price = conversation(
        entry_points=[CallbackQueryHandler(start_price, pattern=pattern(NS_ADM_CAT, "price"))],
        states={
            ASK_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_price)],
            CONFIRM_PRICE: [
                CallbackQueryHandler(confirm_price, pattern=pattern(NS_FLOW, "confirm"))
            ],
        },
        fallbacks=_fallbacks(),
        name="admin_service_price",
        per_chat=True,
        per_user=True,
    )

    archive = conversation(
        entry_points=[
            CallbackQueryHandler(start_archive, pattern=pattern(NS_ADM_CAT, "archive"))
        ],
        states={
            CONFIRM_ARCHIVE: [
                CallbackQueryHandler(confirm_archive, pattern=pattern(NS_FLOW, "confirm"))
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_service_archive",
        per_chat=True,
        per_user=True,
    )

    new_category = conversation(
        entry_points=[
            CallbackQueryHandler(start_new_category, pattern=pattern(NS_ADM_CAT, "newcat"))
        ],
        states={
            ASK_CATEGORY_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_category_name)
            ],
            ASK_CATEGORY_EMOJI: [
                CallbackQueryHandler(skip_category_emoji, pattern=pattern(NS_FLOW, "skip")),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_category_emoji),
            ],
        },
        fallbacks=_fallbacks(),
        name="admin_new_category",
        per_chat=True,
        per_user=True,
    )
    new_service = conversation(
        entry_points=[
            CallbackQueryHandler(start_new_service, pattern=pattern(NS_ADM_CAT, "newsvc"))
        ],
        states={
            NEW_PICK_CATEGORY: [
                CallbackQueryHandler(new_service_category, pattern=pattern(NS_ADM_CAT, "ncat"))
            ],
            NEW_PICK_PROVIDER: [
                CallbackQueryHandler(new_service_provider, pattern=pattern(NS_ADM_CAT, "nprv"))
            ],
            NEW_ASK_PROVIDER_SERVICE_ID: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, new_service_provider_service_id
                )
            ],
            NEW_ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_service_name)],
            NEW_ASK_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_service_cost)],
            NEW_ASK_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_service_price)],
            NEW_ASK_MIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_service_min)],
            NEW_ASK_MAX: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_service_max)],
            NEW_CONFIRM: [
                CallbackQueryHandler(confirm_new_service, pattern=pattern(NS_FLOW, "confirm"))
            ],
        },
        fallbacks=_fallbacks(),
        name="admin_new_service",
        per_chat=True,
        per_user=True,
    )
    search = conversation(
        entry_points=[CallbackQueryHandler(start_search, pattern=pattern(NS_ADM_CAT, "find"))],
        states={ASK_SEARCH_TERM: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_search_term)]},
        fallbacks=_fallbacks(),
        name="admin_service_search",
        per_chat=True,
        per_user=True,
    )
    return [price, edit_display, archive, new_category, new_service, search]


def screens() -> list[CallbackQueryHandler]:
    """أزرار الكتالوج خارج المحادثات."""
    return [
        CallbackQueryHandler(catalog_home_screen, pattern=pattern(NS_ADM_CAT, "home")),
        CallbackQueryHandler(category_services_screen, pattern=pattern(NS_ADM_CAT, "cat")),
        CallbackQueryHandler(service_card_screen, pattern=pattern(NS_ADM_CAT, "svc")),
        CallbackQueryHandler(toggle_service, pattern=pattern(NS_ADM_CAT, "toggle")),
        CallbackQueryHandler(search_page_screen, pattern=pattern(NS_ADM_CAT, "found")),
    ]
