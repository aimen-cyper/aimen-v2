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
