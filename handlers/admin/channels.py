"""
قسم «📢 القنوات» في لوحة التحكم (المرحلة 13): رؤية وتشخيص كل القنوات في مكان واحد.

الشاشات:
    ch:home          : القنوات المطلوبة للاشتراك + وجهات النشر + حالة صندوق النشر.
    ch:check         : فحص فعلي عبر تيليجرام (وجود القناة، البوت مشرف، صلاحية النشر) مع شرح السبب والحل.
    ch:test:<نوع>    : إرسال رسالة اختبار حقيقية إلى وجهة التنبيهات أو التوثيق (alert|orders).

القواعد:
    • عرض الشاشة `settings.view`، والفحص والاختبار `settings.update` — على الـcallback نفسه (دفاع مزدوج).
    • تعديل القيم يتم من الإعدادات (مجموعة `channels`) وتُفحص قبل الحفظ؛ هنا قراءة وتشخيص فقط.
    • قناة النسخ الاحتياطي تُفحص ولا يُرسل إليها أي اختبار (مخصصة للنسخ فقط).
"""

from __future__ import annotations

import asyncio

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from core.exceptions import NotificationBlockedError, NotificationPermanentError, NotificationTemporaryError
from core.permissions import Permission
from handlers.admin.common import admin_required, args
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render
from jobs.telegram_sender import TelegramNotificationSender
from keyboards.admin_kb import channels_home_kb, channels_result_kb
from keyboards.callback_data import NS_ADM_CHN, pattern
from middlewares.context import require_user, services_of
from services.channel_service import KIND_ADMIN_ALERT, KIND_ORDERS_LOG, ChannelCheck
from services.subscription_service import REQUIRED_CHANNEL_SPECS
from texts import admin_ar as t
from utils.channel_ref import ChannelRefError, parse_channel_value
from utils.formatters import safe
from utils.logging_setup import get_logger

logger = get_logger(__name__)


def _value_text(ref: int | str | None) -> str:
    """نص عرض معرّف قناة (أو «غير مضبوطة»)."""
    return safe(str(ref), limit=40) if ref is not None else t.CHANNELS_UNSET


async def _subscription_refs(services) -> list[tuple[str, str, int | str | None]]:
    """القنوات الأربع: (مفتاح الإعداد، العنوان، المعرّف أو None) — القيمة المعطوبة تُعامل كغير مضبوطة."""
    items: list[tuple[str, str, int | str | None]] = []
    for key, emoji, label in REQUIRED_CHANNEL_SPECS:
        raw = (await services.settings.get_str(key, "")).strip()
        ref: int | str | None = None
        if raw:
            try:
                ref = parse_channel_value(raw).chat_id
            except ChannelRefError:
                ref = None
        items.append((key, f"{emoji} {label}", ref))
    return items


async def _destinations(services) -> list[tuple[str, str, int | str | None]]:
    """وجهات النشر الفعلية: (النوع، العنوان، المعرّف الفعلي أو None) + قناة النسخ من البيئة."""
    alert, _ = await services.channels.destination(KIND_ADMIN_ALERT)
    orders_log, _ = await services.channels.destination(KIND_ORDERS_LOG)
    return [
        ("alert", t.CHANNELS_ALERT_LABEL, alert),
        ("orders", t.CHANNELS_ORDERS_LABEL, orders_log),
        ("backup", t.CHANNELS_BACKUP_LABEL, services.backups.channel_id),
    ]


@guarded
@admin_required(Permission.SETTINGS_VIEW)
async def home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة القنوات: ما هو مضبوط الآن (بلا اتصال بتيليجرام) وحالة صندوق النشر."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    required = await services.settings.get_bool("subscription_required", True)
    subscription_lines = "\n".join(
        t.CHANNELS_LINE.format(icon="•", label=label, value=_value_text(ref))
        for _, label, ref in await _subscription_refs(services)
    )
    destination_lines = "\n".join(
        t.CHANNELS_LINE.format(icon="•", label=label, value=_value_text(ref))
        for _, label, ref in await _destinations(services)
    )
    counts = await services.repos.channel_outbox.count_by_status()
    outbox = t.CHANNELS_OUTBOX.format(
        queued=counts.get("queued", 0), sent=counts.get("sent", 0),
        failed=counts.get("failed", 0), skipped=counts.get("skipped", 0),
    )
    can_edit = await services.auth.has_permission(admin, Permission.SETTINGS_UPDATE)
    await render(
        update,
        context,
        t.CHANNELS_HOME.format(
            required=t.CHANNELS_REQUIRED_ON if required else t.CHANNELS_REQUIRED_OFF,
            subscription_lines=subscription_lines,
            destination_lines=destination_lines,
            outbox=outbox,
        ),
        channels_home_kb(can_edit=can_edit),
    )


def _format_check(label: str, result: ChannelCheck) -> str:
    """سطر/أسطر نتيجة فحص قناة واحدة."""
    value = _value_text(result.ref)
    if result.ref is None:
        return t.CHANNELS_CHECK_UNSET.format(label=label)
    if result.ok is True:
        title = f" ({safe(result.title, limit=30)})" if result.title else ""
        return t.CHANNELS_CHECK_OK.format(label=label, value=value, title=title)
    if result.ok is None:
        return t.CHANNELS_CHECK_UNKNOWN.format(label=label, value=value, problem=safe(result.problem, limit=80))
    hints = "".join(t.CHANNELS_HINT.format(hint=safe(hint, limit=140)) for hint in result.hints)
    return t.CHANNELS_CHECK_BAD.format(label=label, value=value, problem=safe(result.problem, limit=100), hints=hints)


@guarded
@admin_required(Permission.SETTINGS_UPDATE)
async def check_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """فحص فعلي لكل القنوات المضبوطة بالتوازي (قنوات الاشتراك + الوجهات + النسخ)."""
    await answer_callback(update, "🔍")
    services = services_of(context)
    jobs: list[tuple[str, int | str | None, bool]] = []
    for _, label, ref in await _subscription_refs(services):
        jobs.append((label, ref, False))
    for _, label, ref in await _destinations(services):
        jobs.append((label, ref, True))
    results = await asyncio.gather(
        *(services.channels.diagnose(context.bot, label, ref, needs_post=needs_post) for label, ref, needs_post in jobs)
    )
    lines = "\n".join(_format_check(label, result) for (label, _, _), result in zip(jobs, results))
    await render(update, context, t.CHANNELS_CHECK_TITLE.format(lines=lines), channels_result_kb())


@guarded
@admin_required(Permission.SETTINGS_UPDATE)
async def test_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إرسال رسالة اختبار حقيقية إلى وجهة التنبيهات أو التوثيق والإبلاغ بنتيجة واضحة."""
    await answer_callback(update)
    services = services_of(context)
    kind_code = args(update).arg(0)
    kind, label = (
        (KIND_ADMIN_ALERT, t.CHANNELS_ALERT_LABEL) if kind_code == "alert" else (KIND_ORDERS_LOG, t.CHANNELS_ORDERS_LABEL)
    )
    destination, reason = await services.channels.destination(kind)
    if destination is None:
        text = t.CHANNELS_TEST_NO_DEST.format(label=label, reason=safe(reason, limit=80))
    else:
        sender = TelegramNotificationSender(context.bot)
        try:
            await sender(destination, t.CHANNELS_TEST_TITLE, t.CHANNELS_TEST_BODY)
        except (NotificationBlockedError, NotificationPermanentError, NotificationTemporaryError) as exc:
            text = t.CHANNELS_TEST_FAIL.format(label=label, reason=safe(str(exc), limit=160))
        else:
            text = t.CHANNELS_TEST_OK.format(label=label)
    await render(update, context, text, channels_result_kb())


def conversations() -> list:
    """لا محادثات في هذا القسم (تعديل القيم عبر الإعدادات)."""
    return []


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم القنوات."""
    return [
        CallbackQueryHandler(home_screen, pattern=pattern(NS_ADM_CHN, "home")),
        CallbackQueryHandler(check_screen, pattern=pattern(NS_ADM_CHN, "check")),
        CallbackQueryHandler(test_action, pattern=pattern(NS_ADM_CHN, "test")),
    ]
