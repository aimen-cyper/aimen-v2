"""
قسم «⚙️ الإعدادات» في لوحة التحكم.

ما ينفّذه هذا الملف:
    • عرض مجموعات الإعدادات ثم مفاتيح كل مجموعة بقيمها الحالية.
    • تعديل قيمة أي مفتاح قابل للتعديل (مع فرض نوع القيمة عند الحفظ).
    • مفتاح وضع الصيانة بزر واحد مع تأكيد.

قواعد مطبّقة:
    • المفاتيح غير القابلة للتعديل (`is_editable = 0`) تُعرض ولا يظهر لها زر.
    • كل تعديل يُسجَّل في سجل التدقيق باسم الأدمن (داخل `SettingsService.set`).
    • الكاش يُبطَل تلقائياً بعد الحفظ فتسري القيمة فوراً على كل الطلبات.
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

from core.setting_rules import normalize_setting_value
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
    paginate,
    permissions_of,
    start_flow,
)
from handlers.common.fallbacks import exit_conversation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    cancel_only_kb,
    confirm_cancel_kb,
    settings_group_kb,
    settings_home_kb,
)
from keyboards.callback_data import NS_ADM_SET, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from utils.formatters import safe
from utils.logging_setup import get_logger
from utils.validators import clean_text

logger = get_logger(__name__)

#: حالة محادثة تعديل قيمة مفتاح
ASK_VALUE = 0

#: حالة تأكيد تبديل وضع الصيانة
CONFIRM_MAINTENANCE = 10

#: مفتاح وضع الصيانة في جدول الإعدادات
MAINTENANCE_KEY = "maintenance_mode"

@guarded
@admin_required(Permission.SETTINGS_VIEW)
async def settings_home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة الإعدادات: المجموعات + حالة وضع الصيانة."""
    await answer_callback(update)
    services = services_of(context)
    groups = await services.settings.groups()
    perms = await permissions_of(context)
    maintenance = await services.settings.is_maintenance()

    await render(
        update,
        context,
        t.SETTINGS_HOME.format(
            maintenance=t.MAINTENANCE_ON if maintenance else t.MAINTENANCE_OFF
        ),
        settings_home_kb(groups, perms, maintenance_on=maintenance),
    )


@guarded
@admin_required(Permission.SETTINGS_VIEW)
async def settings_group_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """مفاتيح مجموعة إعدادات مع قيمها الحالية."""
    await answer_callback(update)
    data = args(update)
    group = data.arg(0)
    services = services_of(context)
    perms = await permissions_of(context)

    items = await services.settings.group(group)
    if not items:
        await render(
            update,
            context,
            t.SETTINGS_GROUP_EMPTY,
            settings_group_kb([], group=group, page=1, total_pages=1, perms=perms),
        )
        return

    page, total_pages, offset = paginate(len(items), data.int_arg(1, 1))
    window = items[offset : offset + PAGE_SIZE]
    lines = "\n\n".join(
        t.SETTING_LINE.format(
            name=safe(item.name_ar or item.key, limit=50),
            key=safe(item.key, limit=50),
            value=safe(item.value, limit=60),
        )
        + ("" if item.is_editable else "\n   🔒 غير قابل للتعديل")
        for item in window
    )
    await render(
        update,
        context,
        t.SETTINGS_GROUP_TITLE.format(
            group=safe(t.setting_group_label(group), limit=40), page=page, pages=total_pages, lines=lines
        ),
        settings_group_kb(
            window, group=group, page=page, total_pages=total_pages, perms=perms
        ),
    )


# =========================== محادثة تعديل القيمة ======================= #


@guarded
@admin_required(Permission.SETTINGS_UPDATE)
async def start_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء تعديل قيمة مفتاح إعداد."""
    await answer_callback(update)
    key = args(update).arg(0)
    services = services_of(context)
    items = {item.key: item for item in await services.settings.all_settings()}
    setting = items.get(key)

    if setting is None:
        await answer_callback(update, t.ERR_SESSION_LOST, alert=True)
        return ConversationHandler.END
    if not setting.is_editable:
        await answer_callback(update, t.SETTING_NOT_EDITABLE, alert=True)
        return ConversationHandler.END

    start_flow(context, key=key, group=setting.group_code)
    await render(
        update,
        context,
        t.SETTING_ASK_VALUE.format(
            name=safe(setting.name_ar or setting.key, limit=50),
            key=safe(setting.key, limit=50),
            value=safe(setting.value, limit=80),
            value_type=safe(setting.value_type, limit=20),
            description=safe(setting.description_ar or "", limit=200),
        ),
        cancel_only_kb(),
    )
    return ASK_VALUE


@guarded
@admin_required(Permission.SETTINGS_UPDATE)
async def receive_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ القيمة الجديدة (التحقق من النوع داخل `SettingsService.set`)."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_VALUE

    data = flow(context)
    if not data.get("key"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    raw = clean_text(message.text, field="القيمة", max_length=500, min_length=1)
    services = services_of(context)
    admin = require_user(context)
    key = str(data["key"])

    items = {item.key: item for item in await services.settings.all_settings()}
    setting = items.get(key)
    if setting is None or not setting.is_editable:
        clear_flow(context)
        await send(update, context, t.SETTING_NOT_EDITABLE)
        return ConversationHandler.END

    # التحقق من النوع والنطاق يتم داخل SettingsService.set (مصدر الحقيقة الوحيد)
    value = normalize_setting_value(key, raw, setting.value_type)
    changed = await services.settings.set(key, value, admin_id=admin.id)
    clear_flow(context)
    logger.info("عدّل الأدمن %s الإعداد %s", admin.telegram_id, key)

    await send(
        update,
        context,
        t.SETTING_UPDATED.format(key=safe(key, limit=50), value=safe(value, limit=80))
        if changed
        else t.SETTING_NOT_EDITABLE,
    )
    await settings_home_screen(update, context)
    return ConversationHandler.END


# ========================== محادثة وضع الصيانة ========================= #


@guarded
@admin_required(Permission.SETTINGS_MAINTENANCE)
async def start_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """عرض تأكيد تبديل وضع الصيانة (يؤثر على كل المستخدمين فوراً)."""
    await answer_callback(update)
    services = services_of(context)
    current = await services.settings.is_maintenance()
    start_flow(context, turn_on=not current)
    await render(
        update,
        context,
        t.MAINTENANCE_CONFIRM_OFF if current else t.MAINTENANCE_CONFIRM_ON,
        confirm_cancel_kb(),
    )
    return CONFIRM_MAINTENANCE


@guarded
@admin_required(Permission.SETTINGS_MAINTENANCE)
async def confirm_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ تبديل وضع الصيانة."""
    await answer_callback(update)
    data = flow(context)
    if "turn_on" not in data:
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    turn_on = bool(data["turn_on"])
    await services.settings.set(MAINTENANCE_KEY, "true" if turn_on else "false", admin_id=admin.id)
    clear_flow(context)
    logger.warning(
        "%s وضع الصيانة بواسطة الأدمن %s", "فعّل" if turn_on else "أوقف", admin.telegram_id
    )

    await render(
        update, context, t.MAINTENANCE_TOGGLED_ON if turn_on else t.MAINTENANCE_TOGGLED_OFF
    )
    await settings_home_screen(update, context)
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
    """محادثتا تعديل قيمة وتبديل وضع الصيانة."""
    edit = conversation(
        entry_points=[CallbackQueryHandler(start_edit, pattern=pattern(NS_ADM_SET, "edit"))],
        states={ASK_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_value)]},
        fallbacks=_fallbacks(),
        name="admin_setting_edit",
        per_chat=True,
        per_user=True,
    )

    maintenance = conversation(
        entry_points=[
            CallbackQueryHandler(start_maintenance, pattern=pattern(NS_ADM_SET, "maint"))
        ],
        states={
            CONFIRM_MAINTENANCE: [
                CallbackQueryHandler(confirm_maintenance, pattern=pattern(NS_FLOW, "confirm"))
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_maintenance",
        per_chat=True,
        per_user=True,
    )
    return [edit, maintenance]


def screens() -> list[CallbackQueryHandler]:
    """أزرار الإعدادات خارج المحادثات."""
    return [
        CallbackQueryHandler(settings_home_screen, pattern=pattern(NS_ADM_SET, "home")),
        CallbackQueryHandler(settings_group_screen, pattern=pattern(NS_ADM_SET, "group")),
    ]
