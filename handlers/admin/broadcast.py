"""
قسم «📣 الرسائل الجماعية» في لوحة التحكم (المرحلة 8).

ما يُنفَّذ هنا:
    • شاشة بآخر الرسائل الجماعية وحالة كل منها بأرقامها الحقيقية.
    • محادثة إنشاء رسالة: النص ← صورة اختيارية ← الشريحة ← مراجعة ← إرسال.
    • بطاقة متابعة حيّة: وصلت/فشلت/حظروا/متبقٍ ونسبة التقدم، مع 🔄 تحديث.
    • تحكم كامل أثناء الإرسال: إيقاف مؤقت، استئناف، إلغاء نهائي.

قواعد ملزمة مطبّقة هنا:
    • تأكيد ثانٍ إلزامي قبل أي إرسال جماعي (العملية لا تُستردّ بعد انطلاقها).
    • فحص `broadcast.send` على كل callback، لا على إظهار الزر فقط.
    • كل إنشاء/بدء/إيقاف/إلغاء يمرّ عبر `BroadcastService` فيُسجَّل في التدقيق.
    • المعالج لا يرسل رسالة واحدة بنفسه — الإرسال كله عبر المهمة الدورية،
      فلا يتجمّد البوت أثناء الضغط على زر، ولا تضيع التغذية الراجعة.
"""

from __future__ import annotations

import math

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from core.permissions import Permission
from database.models import Broadcast
from handlers.common.conversation import conversation
from handlers.admin.common import (
    ADMIN_FLOW_KEY,
    admin_required,
    args,
    cancel_admin_flow,
    clear_flow,
    flow,
    permissions_of,
    start_flow,
    update_flow,
)
from handlers.common.fallbacks import exit_conversation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    BROADCAST_STATES,
    broadcast_card_kb,
    broadcast_confirm_kb,
    broadcast_home_kb,
    broadcast_media_kb,
    broadcast_target_kb,
    cancel_only_kb,
)
from keyboards.callback_data import NS_ADM_BRD, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from services.broadcast_service import MAX_BROADCAST_CAPTION, MAX_BROADCAST_TEXT
from texts import admin_ar as t
from utils.datetime_utils import to_local_text
from utils.formatters import safe
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: حالات محادثة «رسالة جماعية جديدة»
ASK_TEXT, ASK_MEDIA, CHOOSE_TARGET, CONFIRM_SEND = range(4)

#: عدد الرسائل المعروضة في شاشة الإذاعات
RECENT_LIMIT = 8


# ======================================================================== #
#                              أدوات داخلية                                #
# ======================================================================== #


async def _card_text(context: ContextTypes.DEFAULT_TYPE, broadcast_id: int) -> tuple[str, Broadcast]:
    """
    بناء نص بطاقة الرسالة الجماعية من أرقام قاعدة البيانات لحظة العرض.

    المخرجات: (نص البطاقة، كائن الإذاعة) — الكائن مطلوب لبناء أزرارها.
    """
    services = services_of(context)
    admin = require_user(context)
    data = await services.broadcasts.progress(admin, broadcast_id)
    broadcast: Broadcast = data["broadcast"]

    text = t.BROADCAST_CARD.format(
        id=broadcast.id,
        state=BROADCAST_STATES.get(broadcast.status, broadcast.status),
        target=data["target_label"],
        total=broadcast.total_count,
        sent=broadcast.sent_count,
        blocked=broadcast.blocked_count,
        failed=broadcast.failed_count,
        pending=data["pending"],
        percent=data["percent"],
        media_line=t.BROADCAST_MEDIA_LINE if broadcast.media_file_id else "",
        created=to_local_text(broadcast.created_at),
        text=safe(broadcast.message_text, limit=600),
    )
    return text, broadcast


async def _render_card(
    update: Update, context: ContextTypes.DEFAULT_TYPE, broadcast_id: int, *, as_new: bool = False
) -> None:
    """عرض بطاقة الرسالة الجماعية (تحديث الرسالة الحالية أو إرسال رسالة جديدة)."""
    text, broadcast = await _card_text(context, broadcast_id)
    perms = await permissions_of(context)
    markup = broadcast_card_kb(broadcast, perms)
    if as_new:
        await send(update, context, text, markup)
    else:
        await render(update, context, text, markup)


async def _pace_text(context: ContextTypes.DEFAULT_TYPE, count: int) -> tuple[int, int, int]:
    """
    حساب إيقاع الإرسال المتوقع: (حجم الدفعة، الفاصل بالثواني، الدقائق التقديرية).

    الأرقام من الإعدادات الفعلية لا من تخمين، فما يراه الأدمن قبل التأكيد
    هو ما سيحدث فعلاً.
    """
    services = services_of(context)
    batch = max(1, await services.settings.get_int("broadcast_batch_size", 20))
    interval = max(1, await services.settings.get_int("broadcast_interval_seconds", 5))
    minutes = math.ceil(math.ceil(count / batch) * interval / 60)
    return batch, interval, max(1, minutes)


# ======================================================================== #
#                             شاشات القراءة                                #
# ======================================================================== #


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def broadcast_home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة الرسائل الجماعية: آخر الرسائل وحالتها، وزر إنشاء رسالة جديدة."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    perms = await permissions_of(context)

    items = await services.broadcasts.recent(admin, limit=RECENT_LIMIT)
    if not items:
        await render(update, context, t.BROADCAST_EMPTY, broadcast_home_kb([], perms))
        return

    lines = []
    for item in items:
        lines.append(
            t.BROADCAST_LINE.format(
                state=BROADCAST_STATES.get(item.status, item.status),
                id=item.id,
                target=await services.broadcasts.target_label(item.target),
                sent=item.sent_count,
                total=item.total_count,
            )
        )
    await render(
        update,
        context,
        t.BROADCAST_HOME.format(lines="".join(lines)),
        broadcast_home_kb(items, perms),
    )


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def broadcast_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة رسالة جماعية واحدة بتقدمها الحالي (زر 🔄 يعيد قراءة الأرقام)."""
    await answer_callback(update)
    await _render_card(update, context, args(update).int_arg(0))


# ======================================================================== #
#                         إجراءات التحكم بالإرسال                          #
# ======================================================================== #


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بدء أو استئناف الإرسال (المهمة الدورية تتكفل بالدفعات بعدها)."""
    # ملاحظة: يُجاب على الـcallback مرة واحدة فقط (برسالة النتيجة) — الرد الثاني يتجاهله تيليجرام
    services = services_of(context)
    admin = require_user(context)
    broadcast_id = args(update).int_arg(0)

    broadcast = await services.broadcasts.start(admin, broadcast_id)
    pending = await services.broadcasts.progress(admin, broadcast_id)
    await answer_callback(
        update,
        t.BROADCAST_STARTED.format(id=broadcast.id, count=pending["pending"]),
    )
    await _render_card(update, context, broadcast_id)


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def pause_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إيقاف مؤقت: الجولة القادمة لا ترسل شيئاً، ويبقى المتبقون محفوظين."""
    # ملاحظة: يُجاب على الـcallback مرة واحدة فقط (برسالة النتيجة) — الرد الثاني يتجاهله تيليجرام
    services = services_of(context)
    admin = require_user(context)
    broadcast_id = args(update).int_arg(0)

    changed = await services.broadcasts.pause(admin, broadcast_id)
    await answer_callback(
        update,
        t.BROADCAST_PAUSED.format(id=broadcast_id) if changed else t.BROADCAST_NOTHING_TO_DO,
        alert=not changed,
    )
    await _render_card(update, context, broadcast_id)


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إلغاء نهائي للرسالة (لا تُستأنف، ومن وصلته تبقى عنده)."""
    # ملاحظة: يُجاب على الـcallback مرة واحدة فقط (برسالة النتيجة) — الرد الثاني يتجاهله تيليجرام
    services = services_of(context)
    admin = require_user(context)
    broadcast_id = args(update).int_arg(0)

    changed = await services.broadcasts.cancel(admin, broadcast_id)
    await answer_callback(
        update,
        t.BROADCAST_CANCELLED.format(id=broadcast_id) if changed else t.BROADCAST_NOTHING_TO_DO,
        alert=not changed,
    )
    await _render_card(update, context, broadcast_id)


# ======================================================================== #
#                      محادثة «رسالة جماعية جديدة»                         #
# ======================================================================== #


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def start_new_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الخطوة 1: طلب نص الرسالة."""
    await answer_callback(update)
    start_flow(context)
    await render(
        update,
        context,
        t.BROADCAST_ASK_TEXT.format(limit=MAX_BROADCAST_TEXT),
        cancel_only_kb(),
    )
    return ASK_TEXT


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def receive_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الخطوة 2: حفظ النص بعد تنظيفه، ثم عرض خطوة الصورة الاختيارية."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_TEXT

    services = services_of(context)
    clean = services.broadcasts.validate_text(message.text, has_media=False)
    update_flow(context, text=clean)

    await send(
        update,
        context,
        t.BROADCAST_ASK_MEDIA.format(limit=MAX_BROADCAST_CAPTION),
        broadcast_media_kb(),
    )
    return ASK_MEDIA


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def receive_broadcast_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    الخطوة 3 (اختيارية): ربط صورة بالرسالة.

    مع الصورة يصبح النص تعليقاً، وحد التعليق في تيليجرام أقصر — فإن كان النص
    أطول نُخبر الأدمن بوضوح بدل أن يُقتطع النص صامتاً عند الإرسال.
    """
    message = update.effective_message
    if message is None or not message.photo:
        await send(
            update,
            context,
            t.BROADCAST_ASK_MEDIA.format(limit=MAX_BROADCAST_CAPTION),
            broadcast_media_kb(),
        )
        return ASK_MEDIA

    data = flow(context)
    text = str(data.get("text", ""))
    if len(text) > MAX_BROADCAST_CAPTION:
        await send(
            update,
            context,
            t.BROADCAST_MEDIA_TOO_LONG.format(limit=MAX_BROADCAST_CAPTION),
            broadcast_media_kb(),
        )
        return ASK_MEDIA

    update_flow(context, media_file_id=message.photo[-1].file_id, media_type="photo")
    return await _ask_target(update, context, as_new=True)


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def skip_broadcast_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تخطي الصورة والانتقال لاختيار الشريحة."""
    await answer_callback(update)
    return await _ask_target(update, context)


async def _ask_target(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, as_new: bool = False
) -> int:
    """عرض الشرائح مع عدد مستلمي كل شريحة الآن."""
    services = services_of(context)
    admin = require_user(context)
    rows = await services.broadcasts.audience_summary(admin)

    body = t.BROADCAST_ASK_TARGET.format(
        lines="".join(
            t.BROADCAST_TARGET_LINE.format(label=label, count=count) for _code, label, count in rows
        )
    )
    markup = broadcast_target_kb(rows)
    if as_new:
        await send(update, context, body, markup)
    else:
        await render(update, context, body, markup)
    return CHOOSE_TARGET


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def choose_broadcast_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """الخطوة 4: حفظ الشريحة وعرض شاشة المراجعة النهائية قبل الإرسال."""
    services = services_of(context)
    admin = require_user(context)
    target = args(update).arg(0)

    count = await services.broadcasts.audience_count(admin, target)
    if count == 0:
        await answer_callback(update, t.BROADCAST_TARGET_EMPTY, alert=True)
        return CHOOSE_TARGET
    await answer_callback(update)

    update_flow(context, target=target, count=count)
    data = flow(context)
    batch, interval, minutes = await _pace_text(context, count)

    await render(
        update,
        context,
        t.BROADCAST_CONFIRM.format(
            target=await services.broadcasts.target_label(target),
            count=count,
            media_line=t.BROADCAST_MEDIA_LINE if data.get("media_file_id") else "",
            batch=batch,
            interval=interval,
            minutes=minutes,
            text=safe(str(data.get("text", "")), limit=600),
        ),
        broadcast_confirm_kb(),
    )
    return CONFIRM_SEND


@guarded
@admin_required(Permission.BROADCAST_SEND)
async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    الخطوة 5: إنشاء الرسالة فعلياً وبدء إرسالها.

    الإنشاء والبدء عمليتان متتاليتان في الخدمة: الأولى تثبّت قائمة المستلمين،
    والثانية تفتح الباب للمهمة الدورية. أي خطأ بينهما يترك مسودة قابلة للبدء يدوياً.
    """
    await answer_callback(update)
    data = flow(context)
    if not data.get("text") or not data.get("target"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    broadcast = await services.broadcasts.create(
        admin,
        text=str(data["text"]),
        target=str(data["target"]),
        media_file_id=data.get("media_file_id"),
        media_type=data.get("media_type"),
    )
    await services.broadcasts.start(admin, broadcast.id)
    clear_flow(context)
    logger.info(
        "أطلق الأدمن %s الإذاعة #%s إلى %s مستلم",
        admin.telegram_id, broadcast.id, broadcast.total_count,
    )

    await render(
        update,
        context,
        t.BROADCAST_STARTED.format(id=broadcast.id, count=broadcast.total_count),
    )
    await _render_card(update, context, broadcast.id, as_new=True)
    return ConversationHandler.END


# ============================== التسجيل ================================ #


def _fallbacks() -> list:
    """المسارات الاحتياطية الموحّدة لمحادثة هذا القسم."""
    return [
        CallbackQueryHandler(cancel_admin_flow, pattern=pattern(NS_FLOW, "cancel")),
        CommandHandler("cancel", cancel_admin_flow),
        CommandHandler("start", exit_conversation(ADMIN_FLOW_KEY)),
    ]


def conversations() -> list[ConversationHandler]:
    """محادثة إنشاء رسالة جماعية (نص ← صورة ← شريحة ← تأكيد)."""
    new_broadcast = conversation(
        entry_points=[
            CallbackQueryHandler(start_new_broadcast, pattern=pattern(NS_ADM_BRD, "new"))
        ],
        states={
            ASK_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_broadcast_text)],
            ASK_MEDIA: [
                MessageHandler(filters.PHOTO, receive_broadcast_media),
                CallbackQueryHandler(skip_broadcast_media, pattern=pattern(NS_FLOW, "skip")),
            ],
            CHOOSE_TARGET: [
                CallbackQueryHandler(
                    choose_broadcast_target, pattern=pattern(NS_ADM_BRD, "target")
                )
            ],
            CONFIRM_SEND: [
                CallbackQueryHandler(confirm_broadcast, pattern=pattern(NS_FLOW, "confirm"))
            ],
        },
        fallbacks=_fallbacks(),
        name="admin_broadcast_new",
        per_chat=True,
        per_user=True,
    )
    return [new_broadcast]


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم الرسائل الجماعية خارج المحادثة."""
    return [
        CallbackQueryHandler(broadcast_home_screen, pattern=pattern(NS_ADM_BRD, "home")),
        CallbackQueryHandler(broadcast_card_screen, pattern=pattern(NS_ADM_BRD, "view")),
        CallbackQueryHandler(start_broadcast, pattern=pattern(NS_ADM_BRD, "start")),
        CallbackQueryHandler(pause_broadcast, pattern=pattern(NS_ADM_BRD, "pause")),
        CallbackQueryHandler(cancel_broadcast, pattern=pattern(NS_ADM_BRD, "cancel")),
    ]
