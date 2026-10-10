"""
قسم «🛡️ الأمان» في لوحة التحكم (المرحلة 9).

الشاشات:
    sc:home         : عدّادات آخر 24 ساعة + قائمة فحوص وضع الأمان.
    sc:events:<p>   : الأحداث الأمنية من سجل التدقيق (صفحات).
    sc:blocks       : الموقوفون مؤقتاً بسبب الضغط الزائد + رفع الإيقاف.
    sc:unblock:<id> : رفع إيقاف مستخدم (يتطلب `security.manage`).
    sc:team         : طاقم الإدارة وأدوارهم واستثناءاتهم.

قواعد ملزمة:
    • كل شاشة تفحص صلاحية `security.view` على الـcallback، ورفع الإيقاف يتطلب
      `security.manage` — والخدمة تعيد الفحص داخلها (دفاع مزدوج).
    • الشاشات للقراءة ما عدا رفع الإيقاف، وهو يُدقَّق كحدث أمني.
    • لا تُعرض أي أسرار: فقط «مضبوط/غير مضبوط» وحالة الصلاحيات.
"""

from __future__ import annotations

import json

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from core.permissions import Permission
from database.models import AuditLog
from handlers.admin.common import admin_required, args, permissions_of
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render
from keyboards.admin_kb import (
    security_blocks_kb,
    security_events_kb,
    security_home_kb,
    security_team_kb,
)
from keyboards.callback_data import NS_ADM_SEC, pattern
from middlewares.context import require_user, services_of
from services.security_service import (
    LEVEL_BAD,
    LEVEL_WARN,
    EnvPosture,
    SecurityService,
)
from texts import admin_ar as t
from utils.formatters import datetime_text, safe
from utils.fs_security import check_paths
from utils.logging_setup import get_logger

logger = get_logger(__name__)


def _env_posture(context: ContextTypes.DEFAULT_TYPE) -> EnvPosture:
    """
    بناء لقطة البيئة من إعدادات التشغيل المخزّنة في `bot_data` (بلا أي قيمة سرّية).

    إن لم تتوفر الإعدادات (كما في بعض الاختبارات) نُرجع لقطة افتراضية بلا فحص ملفات.
    """
    config = context.application.bot_data.get("config")
    if config is None:
        return EnvPosture()
    return EnvPosture(
        bot_token_set=bool(config.bot_token),
        encryption_key_set=bool(config.encryption_key),
        alert_chat_set=config.admin_alert_chat_id is not None,
        path_checks=tuple(check_paths(config.sensitive_paths(), fix=False)),
    )


def _event_label(action: str) -> str:
    """اسم عربي للحدث الأمني (يُزال بادئة `security.`)."""
    code = action.removeprefix("security.")
    return t.SECURITY_EVENT_LABELS.get(code, code)


def _event_target(entry: AuditLog) -> str:
    """وصف مختصر لهدف الحدث (نوع:معرّف أو ملخص التفاصيل)."""
    if entry.target_type:
        return safe(f"{entry.target_type}:{entry.target_id}", limit=28)
    if entry.details_json:
        try:
            details = json.loads(entry.details_json)
        except ValueError:
            return safe(entry.details_json, limit=28)
        if isinstance(details, dict) and details.get("permission"):
            return safe(str(details["permission"]), limit=28)
    return "—"


@guarded
@admin_required(Permission.SECURITY_VIEW)
async def home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الشاشة الرئيسية: العدّادات وفحوص وضع الأمان."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    counters = await services.security.counters(admin)
    checks = await services.security.posture(admin, _env_posture(context))

    bad = sum(1 for check in checks if check.level == LEVEL_BAD)
    warn = sum(1 for check in checks if check.level == LEVEL_WARN)
    summary = t.SECURITY_SUMMARY_ISSUES.format(bad=bad, warn=warn) if bad or warn else t.SECURITY_SUMMARY_OK

    top = ""
    if counters.top_denied:
        names: list[str] = []
        for user_id, count in counters.top_denied:
            user = await services.users.get(user_id)
            names.append(f"{safe(user.display_name if user else str(user_id), limit=20)} ({count})")
        top = t.SECURITY_TOP_DENIED.format(items="، ".join(names))

    lines = "\n".join(
        t.SECURITY_CHECK_LINE.format(
            icon=t.SECURITY_LEVEL_ICONS.get(check.level, "•"),
            title=safe(check.title),
            detail=safe(check.detail),
        )
        for check in checks
    )
    await render(
        update,
        context,
        t.SECURITY_HOME.format(
            denied=counters.permission_denied,
            blocks=counters.rate_limit_blocks,
            rbac=counters.rbac_blocks,
            money=counters.money_blocks,
            total=counters.total_events,
            top_denied=top,
            summary=summary,
            checks=lines,
        ),
        security_home_kb(),
    )


@guarded
@admin_required(Permission.SECURITY_VIEW)
async def events_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """صفحة من الأحداث الأمنية (الأحدث أولاً)."""
    await answer_callback(update)
    services = services_of(context)
    result = await services.security.events(require_user(context), page=args(update).int_arg(0, 1))
    if not result.items:
        await render(update, context, t.SECURITY_EVENTS_EMPTY, security_events_kb(page=1, total_pages=1))
        return
    lines = "\n\n".join(
        t.SECURITY_EVENT_LINE.format(
            label=safe(_event_label(entry.action), limit=45),
            who=safe(result.names.get(entry.admin_id or 0, "النظام"), limit=22),
            target=_event_target(entry),
            when=datetime_text(entry.created_at),
        )
        for entry in result.items
    )
    await render(
        update,
        context,
        t.SECURITY_EVENTS_TITLE.format(page=result.page, pages=result.total_pages, lines=lines),
        security_events_kb(page=result.page, total_pages=result.total_pages),
    )


async def _show_blocks(update: Update, context: ContextTypes.DEFAULT_TYPE, *, notice: str = "") -> None:
    """عرض شاشة الموقوفين (مشتركة بين فتحها ورفع الإيقاف)."""
    services = services_of(context)
    guard = context.application.bot_data.get("abuse_guard")
    blocked = await services.security.blocked_users(require_user(context), guard)
    perms = await permissions_of(context)
    if not blocked:
        await render(update, context, notice + t.SECURITY_BLOCKS_EMPTY, security_blocks_kb([], perms))
        return
    lines = "\n".join(
        t.SECURITY_BLOCK_LINE.format(
            name=safe(item.name, limit=25),
            telegram_id=item.telegram_id,
            left=SecurityService.seconds_text(item.seconds_left),
            strikes=item.strikes,
        )
        for item in blocked
    )
    await render(
        update,
        context,
        notice + t.SECURITY_BLOCKS_TITLE.format(lines=lines),
        security_blocks_kb([(item.telegram_id, item.name) for item in blocked], perms),
    )


@guarded
@admin_required(Permission.SECURITY_VIEW)
async def blocks_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة الموقوفين مؤقتاً الآن."""
    await answer_callback(update)
    await _show_blocks(update, context)


@guarded
@admin_required(Permission.SECURITY_MANAGE)
async def unblock_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """رفع إيقاف مؤقت عن مستخدم محدد (يُدقَّق كحدث أمني)."""
    await answer_callback(update)
    services = services_of(context)
    telegram_id = args(update).int_arg(0, 0)
    guard = context.application.bot_data.get("abuse_guard")
    user = await services.users.get_by_telegram(telegram_id) if telegram_id else None
    cleared = await services.security.clear_block(require_user(context), telegram_id, guard)
    name = safe(user.display_name if user else str(telegram_id), limit=25)
    notice = (
        t.SECURITY_UNBLOCKED.format(name=name) if cleared else t.SECURITY_UNBLOCK_NOT_BLOCKED
    ) + "\n\n"
    await _show_blocks(update, context, notice=notice)


@guarded
@admin_required(Permission.SECURITY_VIEW)
async def team_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """طاقم الإدارة مرتباً بالدور."""
    await answer_callback(update)
    services = services_of(context)
    members = await services.security.team(require_user(context))
    if not members:
        await render(update, context, t.SECURITY_TEAM_EMPTY, security_team_kb())
        return
    lines: list[str] = []
    for member in members:
        extras = []
        if member.overrides:
            extras.append(f"استثناءات: {member.overrides}")
        if member.is_banned:
            extras.append("محظور")
        lines.append(
            t.SECURITY_TEAM_LINE.format(
                icon="⛔" if member.is_banned else "👤",
                name=safe(member.user.display_name, limit=25),
                role=t.SECURITY_ROLE_LABELS.get(str(member.user.role), str(member.user.role)),
                extras=f" · {' · '.join(extras)}" if extras else "",
            )
        )
    await render(
        update, context, t.SECURITY_TEAM_TITLE.format(lines="\n".join(lines)), security_team_kb()
    )


def conversations() -> list:
    """لا محادثات في قسم الأمان (شاشات وأزرار فورية)."""
    return []


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم الأمان."""
    return [
        CallbackQueryHandler(home_screen, pattern=pattern(NS_ADM_SEC, "home")),
        CallbackQueryHandler(events_screen, pattern=pattern(NS_ADM_SEC, "events")),
        CallbackQueryHandler(blocks_screen, pattern=pattern(NS_ADM_SEC, "blocks")),
        CallbackQueryHandler(unblock_action, pattern=pattern(NS_ADM_SEC, "unblock")),
        CallbackQueryHandler(team_screen, pattern=pattern(NS_ADM_SEC, "team")),
    ]
