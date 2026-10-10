"""
شاشة لوحة التحكم الرئيسية + شاشة صحة النظام + الأمر /admin.

مبدأ الشاشة: القائمة تُبنى من صلاحيات هذا الأدمن تحديداً، فأدمن الدعم يرى
«🎫 الدعم» فقط، ومراجع المدفوعات يرى «💰 المدفوعات» فقط. والأرقام الظاهرة
في الرأس تُعرض لمن يملك `stats.view` فقط.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from core.enums import OrderStatus
from core.permissions import Permission
from handlers.admin.common import admin_required, permissions_of, symbol_of
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render
from jobs import JOB_LABELS
from jobs.runner import JOB_REGISTRY
from keyboards.admin_kb import admin_menu_kb, health_kb
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from utils.datetime_utils import utc_now_iso
from utils.formatters import datetime_text, money_text

#: الحالات التي تُحتسب «طلبات نشطة» في رأس اللوحة
ACTIVE_FOR_DASHBOARD = (
    OrderStatus.PENDING,
    OrderStatus.SUBMITTING,
    OrderStatus.SUBMITTED,
    OrderStatus.IN_PROGRESS,
)

#: الحالات التي تعني «يحتاج تدخل أدمن الآن»
ATTENTION_FOR_DASHBOARD = (OrderStatus.SUBMIT_UNCERTAIN, OrderStatus.FAILED)


async def _panel_text(update: Update, context: ContextTypes.DEFAULT_TYPE, perms: set[str]) -> str:
    """
    بناء نص رأس اللوحة: الأرقام الكاملة لمن يملك `stats.view`، وعنوان مختصر لغيره.

    لا نستدعي خدمة الإحصائيات أصلاً لمن لا يملك الصلاحية، حتى لا يمتلئ سجل
    التدقيق بمحاولات رفض لا ذنب للأدمن فيها (زيارته للوحة ليست محاولة اختراق).
    """
    if Permission.STATS_VIEW not in perms:
        return t.PANEL_SIMPLE

    services = services_of(context)
    admin = require_user(context)
    stats = await services.stats.dashboard(admin)
    symbol = await symbol_of(context)
    by_status = stats.orders_by_status
    return t.DASHBOARD.format(
        users_total=stats.users_total,
        users_new_today=stats.users_new_today,
        users_active_7d=stats.users_active_7d,
        users_banned=stats.users_banned,
        orders_today=stats.orders_today,
        active_orders=sum(by_status.get(status, 0) for status in ACTIVE_FOR_DASHBOARD),
        attention_orders=sum(by_status.get(status, 0) for status in ATTENTION_FOR_DASHBOARD),
        revenue_today=money_text(stats.revenue_today_units, symbol),
        revenue_7d=money_text(stats.revenue_7d_units, symbol),
        deposits_today=money_text(stats.deposits_today_units, symbol),
        pending_payments=stats.pending_payments,
        open_tickets=stats.open_tickets,
        queued=stats.queued_notifications,
        active_services=stats.active_services,
        errors_24h=stats.errors_24h,
        now=datetime_text(utc_now_iso()),
    )


@guarded
@admin_required()
async def panel_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الشاشة الرئيسية للوحة التحكم (زر «🛠 لوحة التحكم» و«🔄 تحديث»)."""
    await answer_callback(update)
    services = services_of(context)
    perms = await permissions_of(context)

    pending = (
        await services.payments.pending_count() if Permission.PAYMENTS_VIEW in perms else 0
    )
    tickets = await services.tickets.open_count() if Permission.TICKETS_VIEW in perms else 0

    await render(
        update,
        context,
        await _panel_text(update, context, perms),
        admin_menu_kb(perms, pending_payments=pending, open_tickets=tickets),
    )


@guarded
@admin_required()
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الأمر /admin — مدخل اللوحة لمن يملك `admin.access` فقط."""
    await panel_screen(update, context)


def _jobs_health_line() -> str:
    """
    سطر حالة المهام الدورية داخل شاشة صحة النظام (المرحلة 6).

    مصدره سجل التشغيل في الذاكرة؛ إن كانت الجدولة لم تتم بعد (كما في بعض
    الاختبارات) يُرجع نصاً فارغاً بدل ادّعاء حالة لا نعرفها.
    """
    jobs = JOB_REGISTRY.snapshot()
    if not jobs:
        return ""
    failing = [job for job in jobs if not job.is_healthy]
    failing_text = (
        t.HEALTH_JOBS_FAILING.format(
            names="، ".join(JOB_LABELS.get(job.name, job.name) for job in failing)
        )
        if failing
        else ""
    )
    return t.HEALTH_JOBS_SECTION.format(
        healthy=len(jobs) - len(failing), total=len(jobs), failing_text=failing_text
    )


@guarded
@admin_required(Permission.STATS_VIEW)
async def health_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة صحة النظام: المزودون، المهام الدورية، الإشعارات، الأخطاء، حجم القاعدة."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    text = await services.stats.health_text(admin) + _jobs_health_line()
    await render(update, context, text, health_kb())
