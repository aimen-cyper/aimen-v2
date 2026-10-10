"""
خدمة الإحصائيات والتقارير — أرقام حقيقية من قاعدة البيانات فقط.

المبدأ الحاكم: **لا رقم تقديري ولا بيانات وهمية**. كل قيمة هنا ناتجة عن استعلام
فعلي؛ وإن تعذّر حساب قيمة (مثل الربح بلا تكلفة مزود مسجّلة) تُعاد `None` ويُوضَّح
ذلك في العرض بدل اختراع رقم.

دلالة الأرقام (م10 — صُحِّحت عن الإصدارات السابقة):
    • **الإيراد الصافي** = Σ(cost − refund_amount) لطلبات الفترة. الطلب الملغى/الفاشل المسترجَع
      كاملاً لا يُحتسب، والجزئي يُحتسب بما بقي مخصوماً. (سابقاً كان المجموع الخام يُضخّم الإيراد.)
    • **الربح التقديري** للطلبات المنتهية (مكتمل/جزئي) المسجَّلة التكلفة فقط، مع نسبة التغطية
      معلنة؛ والتكلفة الفعلية للجزئي تُقسَّم بنسبة ما بقي مخصوماً.
    • الفترات بأيام **محلية** كاملة (Asia/Aden) لا بطرح 24 ساعة.

المحتوى:
    • لوحة المعلومات السريعة (Dashboard) وملخصات الفترات.
    • تقارير مالية (إيراد، ربح، التزامات المحفظة) وتشغيلية (نجاح، عالق، مزودون).
    • الأفضل: خدمات، عملاء؛ سلسلة يومية؛ تصدير CSV (خطِر: `stats.export`).
    • صحة النظام: الأخطاء، صندوق الإشعارات، حجم قاعدة البيانات، آخر نسخة.
"""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from collections import defaultdict
from dataclasses import dataclass, field

from core.enums import OrderStatus, TransactionType
from core.exceptions import ValidationError
from core.money import format_units, from_units
from core.permissions import Permission
from database.database import Database
from database.models import User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.provider_service import ProviderService
from services.settings_service import SettingsService
from utils.datetime_utils import (
    DEFAULT_TIMEZONE,
    day_bounds_utc,
    iso_minus_days,
    iso_plus_seconds,
    local_day_of,
    local_month_range_utc,
    local_range_utc,
    parse_iso,
    to_iso,
    to_local_text,
    utc_now_iso,
)
from utils.formatters import datetime_text
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: مفاتيح الفترات المدعومة في الواجهة (بالترتيب المعروض)
PERIOD_KEYS: tuple[str, ...] = ("today", "yesterday", "7d", "30d", "90d", "month")

#: أسماء الفترات بالعربية
PERIOD_LABELS: dict[str, str] = {
    "today": "اليوم",
    "yesterday": "أمس",
    "7d": "آخر 7 أيام",
    "30d": "آخر 30 يوماً",
    "90d": "آخر 90 يوماً",
    "month": "هذا الشهر",
}

#: أنواع التصدير المدعومة
EXPORT_KINDS: tuple[str, ...] = ("orders", "daily")

#: أول محارف خلية CSV التي تجعل Excel/Sheets يفسّرها معادلة (حقن صيغ)
_FORMULA_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r", "\n")

#: أقصى طول لخلية نصية في التصدير
_CELL_LIMIT = 200


@dataclass(frozen=True, slots=True)
class Period:
    """فترة تقرير: مفتاح + اسم عربي + حدود UTC (بداية شاملة، نهاية حصرية)."""

    key: str
    label: str
    start_iso: str
    end_iso: str


def build_period(key: str, timezone: str = DEFAULT_TIMEZONE) -> Period:
    """
    فترة من مفتاحها (`today`/`yesterday`/`7d`/`30d`/`90d`/`month`) بأيام محلية كاملة.

    الاستثناءات: ValidationError لمفتاح غير معروف (قيمة زر عبث بها مستخدم).
    """
    if key == "today":
        start, end = local_range_utc(0, 0, timezone)
    elif key == "yesterday":
        start, end = local_range_utc(1, 1, timezone)
    elif key in ("7d", "30d", "90d"):
        start, end = local_range_utc(int(key[:-1]) - 1, 0, timezone)
    elif key == "month":
        start, end = local_month_range_utc(timezone)
    else:
        raise ValidationError(f"فترة غير معروفة: {key!r}", user_message="❌ فترة غير معروفة.")
    return Period(key=key, label=PERIOD_LABELS[key], start_iso=start, end_iso=end)


def period_for_days(days: int, timezone: str = DEFAULT_TIMEZONE) -> Period:
    """فترة «آخر N يوماً» تقويمية (تشمل اليوم) — مدخل التوافق للواجهات التي تمرّر `days`."""
    days = max(1, int(days))
    start, end = local_range_utc(days - 1, 0, timezone)
    return Period(key=f"{days}d", label=f"آخر {days} يوم", start_iso=start, end_iso=end)


def csv_safe_text(value: object) -> str:
    """
    تحييد خلية نصية قبل كتابتها في CSV.

    • الخلية التي تبدأ بـ`= + - @` أو محرف تحكم تُسبق بفاصلة عليا فلا تُنفَّذ كمعادلة عند فتح الملف.
    • تُقصّ الخلايا الطويلة ويُستبدل فيها فاصل السطر بمسافة (يحافظ على بنية الصف).
    """
    text = "" if value is None else str(value)
    text = text.replace("\r", " ").replace("\n", " ")[:_CELL_LIMIT]
    if text.startswith(_FORMULA_PREFIXES):
        text = "'" + text
    return text


def money_cell(units: int | None) -> str:
    """مبلغ للتصدير كرقم عشري ثابت (بلا رمز عملة ولا فواصل آلاف) أو فارغ إن لم يُحسب."""
    return "" if units is None else f"{from_units(units):.4f}"


@dataclass(slots=True)
class DashboardStats:
    """أرقام لوحة المعلومات الرئيسية (الإيراد صافٍ)."""

    users_total: int
    users_new_today: int
    users_active_7d: int
    users_banned: int
    orders_today: int
    orders_by_status: dict[str, int]
    revenue_today_units: int
    revenue_7d_units: int
    deposits_today_units: int
    pending_payments: int
    open_tickets: int
    queued_notifications: int
    active_services: int
    errors_24h: int

    def as_dict(self) -> dict[str, object]:
        """تحويل الأرقام إلى قاموس (لتسجيلها أو إرسالها كتقرير)."""
        return {
            "users_total": self.users_total,
            "users_new_today": self.users_new_today,
            "users_active_7d": self.users_active_7d,
            "users_banned": self.users_banned,
            "orders_today": self.orders_today,
            "orders_by_status": self.orders_by_status,
            "revenue_today_units": self.revenue_today_units,
            "revenue_7d_units": self.revenue_7d_units,
            "deposits_today_units": self.deposits_today_units,
            "pending_payments": self.pending_payments,
            "open_tickets": self.open_tickets,
            "queued_notifications": self.queued_notifications,
            "active_services": self.active_services,
            "errors_24h": self.errors_24h,
        }


@dataclass(slots=True)
class FinancialReport:
    """
    تقرير مالي لفترة محددة.

    `revenue_units` **صافٍ** (بعد الاسترجاع). `provider_cost_units` تكلفة الطلبات المغطّاة فقط
    (لا كل الطلبات). الربح `None` إن لم يكن مسموحاً أو لا توجد طلبات منتهية مغطّاة.
    """

    start_iso: str
    end_iso: str
    orders_count: int
    revenue_units: int
    provider_cost_units: int
    profit_units: int | None
    deposits_units: int
    refunds_units: int
    partial_refunds_units: int
    manual_credit_units: int
    manual_debit_units: int
    gross_units: int = 0
    order_refund_units: int = 0
    buyers: int = 0
    profit_covered_orders: int = 0
    profit_eligible_orders: int = 0

    @property
    def profit_known(self) -> bool:
        """هل الربح محسوب فعلياً؟ (يتطلب طلبات منتهية مسجَّلة التكلفة وصلاحية الربح)."""
        return self.profit_units is not None

    @property
    def profit_coverage_pct(self) -> int | None:
        """نسبة الطلبات المنتهية التي دخلت حساب الربح (None إن لم توجد طلبات منتهية)."""
        if self.profit_eligible_orders <= 0:
            return None
        return round(self.profit_covered_orders * 100 / self.profit_eligible_orders)


@dataclass(slots=True)
class OperationsReport:
    """تقرير تشغيلي عن جودة التنفيذ."""

    total_orders: int
    completed: int
    partial: int
    failed: int
    canceled: int
    refunded: int
    success_rate: float
    stuck_orders: int
    uncertain_orders: int


@dataclass(slots=True)
class PeriodSummary:
    """ملخص شامل لفترة (شاشة الإحصائيات الرئيسية): المال + التشغيل + المستخدمون."""

    period: Period
    financial: FinancialReport
    by_status: dict[str, int]
    new_users: int
    finished_orders: int
    success_rate: float | None
    avg_order_units: int

    @property
    def active_orders(self) -> int:
        """طلبات الفترة التي لم تنتهِ بعد."""
        return sum(
            self.by_status.get(status, 0)
            for status in (
                OrderStatus.PENDING,
                OrderStatus.SUBMITTING,
                OrderStatus.SUBMIT_UNCERTAIN,
                OrderStatus.SUBMITTED,
                OrderStatus.IN_PROGRESS,
            )
        )


@dataclass(slots=True)
class BuyerRow:
    """عميل في قائمة الأكثر إنفاقاً."""

    name: str
    orders_count: int
    net_units: int


@dataclass(slots=True)
class ExportFile:
    """ملف تصدير جاهز للإرسال."""

    filename: str
    content: bytes
    rows: int
    truncated: bool
    period: Period
    columns: list[str] = field(default_factory=list)


class StatsService:
    """تجميع الإحصائيات والتقارير للوحة الأدمن."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        auth: AuthService,
        providers: ProviderService,
        audit: AuditService | None = None,
    ) -> None:
        """تهيئة الخدمة بالاعتماديات المطلوبة (`audit` لتدقيق التصدير؛ بدونه يُرفض التصدير)."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.auth = auth
        self.providers = providers
        self.audit = audit

    # ===================================================================== #
    #                           لوحة المعلومات                              #
    # ===================================================================== #

    async def dashboard(self, actor: User) -> DashboardStats:
        """
        أرقام لوحة المعلومات السريعة (صلاحية `stats.view`) — الإيراد **صافٍ**.

        الاستثناءات: PermissionDeniedError
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)

        start_today, end_today = day_bounds_utc(0)
        week_start, week_end = local_range_utc(6, 0)
        week_ago = iso_minus_days(7)
        day_ago = iso_minus_days(1)

        return DashboardStats(
            users_total=await self.repos.users.count_all(),
            users_new_today=await self.repos.users.count_since(start_today),
            users_active_7d=await self.repos.users.count_active_since(week_ago),
            users_banned=await self.repos.users.count_banned(),
            orders_today=await self.repos.orders.count_between(start_today, end_today),
            orders_by_status=await self.repos.orders.status_counts(),
            revenue_today_units=await self.repos.orders.sum_net_between(start_today, end_today),
            revenue_7d_units=await self.repos.orders.sum_net_between(week_start, week_end),
            deposits_today_units=await self.repos.payments.sum_approved_between(
                start_today, end_today
            ),
            pending_payments=await self.repos.payments.count_pending(),
            open_tickets=await self.repos.tickets.count_open(),
            queued_notifications=await self.repos.notifications.count_queued(),
            active_services=await self.repos.services.count_active(),
            errors_24h=await self.repos.error_logs.count_since(day_ago),
        )

    async def dashboard_text(self, actor: User) -> str:
        """لوحة المعلومات كنص عربي جاهز للإرسال في تيليجرام."""
        stats = await self.dashboard(actor)
        symbol = await self.settings.money_symbol()
        by_status = stats.orders_by_status
        active = (
            by_status.get(OrderStatus.PENDING, 0)
            + by_status.get(OrderStatus.SUBMITTED, 0)
            + by_status.get(OrderStatus.IN_PROGRESS, 0)
        )
        lines = [
            "📊 <b>لوحة المعلومات</b>",
            "",
            f"👥 المستخدمون: {stats.users_total} (جديد اليوم: {stats.users_new_today})",
            f"🔥 نشطون آخر 7 أيام: {stats.users_active_7d} • محظورون: {stats.users_banned}",
            "",
            f"🧾 طلبات اليوم: {stats.orders_today} • قيد التنفيذ الآن: {active}",
            f"✅ مكتملة: {by_status.get(OrderStatus.COMPLETED, 0)} • "
            f"⚠️ جزئية: {by_status.get(OrderStatus.PARTIAL, 0)} • "
            f"❌ فاشلة: {by_status.get(OrderStatus.FAILED, 0)}",
            f"❓ غير مؤكدة: {by_status.get(OrderStatus.SUBMIT_UNCERTAIN, 0)}",
            "",
            f"💰 مبيعات اليوم (صافي): {format_units(stats.revenue_today_units, symbol=symbol)}",
            f"💰 مبيعات 7 أيام (صافي): {format_units(stats.revenue_7d_units, symbol=symbol)}",
            f"💳 إيداعات اليوم: {format_units(stats.deposits_today_units, symbol=symbol)}",
            "",
            f"🧮 طلبات شحن معلّقة: {stats.pending_payments}",
            f"🎫 تذاكر مفتوحة: {stats.open_tickets}",
            f"📨 إشعارات بانتظار الإرسال: {stats.queued_notifications}",
            f"🛒 خدمات مفعّلة: {stats.active_services}",
            f"🐞 أخطاء آخر 24 ساعة: {stats.errors_24h}",
        ]
        return "\n".join(lines)

    # ===================================================================== #
    #                           التقارير المالية                            #
    # ===================================================================== #

    async def _financial(self, actor: User, period: Period, *, include_profit: bool) -> FinancialReport:
        """بناء التقرير المالي لفترة (الفحص الأمني يجري في الدالة العامة المستدعية)."""
        start, end = period.start_iso, period.end_iso
        totals = await self.repos.orders.period_totals(start, end)
        inputs = await self.repos.orders.profit_inputs(start, end)

        can_see_profit = include_profit and await self.auth.has_permission(actor, Permission.STATS_PROFIT)
        profit: int | None = None
        if can_see_profit and inputs["covered_orders"] > 0:
            profit = inputs["covered_net_units"] - inputs["covered_cost_units"]

        tx = self.repos.transactions
        return FinancialReport(
            start_iso=start,
            end_iso=end,
            orders_count=totals["orders_count"],
            revenue_units=totals["net_units"],
            provider_cost_units=inputs["covered_cost_units"] if can_see_profit else 0,
            profit_units=profit,
            deposits_units=await self.repos.payments.sum_approved_between(start, end),
            refunds_units=await tx.sum_by_type(TransactionType.REFUND, start_iso=start, end_iso=end),
            partial_refunds_units=await tx.sum_by_type(
                TransactionType.PARTIAL_REFUND, start_iso=start, end_iso=end
            ),
            manual_credit_units=await tx.sum_by_type(TransactionType.MANUAL_CREDIT, start_iso=start, end_iso=end),
            manual_debit_units=await tx.sum_by_type(TransactionType.MANUAL_DEBIT, start_iso=start, end_iso=end),
            gross_units=totals["gross_units"],
            order_refund_units=totals["refund_units"],
            buyers=totals["buyers"],
            profit_covered_orders=inputs["covered_orders"] if can_see_profit else 0,
            profit_eligible_orders=inputs["eligible_orders"] if can_see_profit else 0,
        )

    async def financial_report(
        self, actor: User, *, days: int = 7, include_profit: bool = True, period: Period | None = None
    ) -> FinancialReport:
        """
        تقرير مالي لفترة (بالأيام أو بكائن `Period`).

        الربح يُحسب للطلبات المنتهية المسجَّلة التكلفة فقط، ويتطلب عرضه `stats.profit`؛
        وإلا `None` بدل رقم مضلل.
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        return await self._financial(actor, period or period_for_days(days), include_profit=include_profit)

    async def financial_report_text(self, actor: User, *, days: int = 7) -> str:
        """التقرير المالي كنص عربي جاهز للعرض."""
        report = await self.financial_report(actor, days=days)
        symbol = await self.settings.money_symbol()
        lines = [
            f"💼 <b>التقرير المالي — آخر {days} يوم</b>",
            "",
            f"🧾 عدد الطلبات: {report.orders_count}",
            f"💰 صافي المبيعات: {format_units(report.revenue_units, symbol=symbol)} "
            f"(الإجمالي {format_units(report.gross_units, symbol=symbol)} − المسترجع "
            f"{format_units(report.order_refund_units, symbol=symbol)})",
            f"💳 إجمالي الإيداعات المعتمدة: {format_units(report.deposits_units, symbol=symbol)}",
            f"↩️ استرجاع كامل: {format_units(report.refunds_units, symbol=symbol)}",
            f"↩️ استرجاع جزئي: {format_units(report.partial_refunds_units, symbol=symbol)}",
            f"➕ إضافات يدوية: {format_units(report.manual_credit_units, symbol=symbol)}",
            f"➖ خصومات يدوية: {format_units(report.manual_debit_units, symbol=symbol)}",
        ]
        if report.profit_known and report.profit_units is not None:
            lines.append(
                f"📈 الربح التقديري: {format_units(report.profit_units, symbol=symbol)} "
                f"(تكلفة المزود: {format_units(report.provider_cost_units, symbol=symbol)} • "
                f"تغطية {report.profit_coverage_pct}% من الطلبات المنتهية)"
            )
        else:
            lines.append("📈 الربح: غير محسوب — لا طلبات منتهية بتكلفة مزود مسجّلة، أو لا تملك صلاحية الربح.")
        return "\n".join(lines)

    async def summary(self, actor: User, period: Period, *, include_profit: bool = True) -> PeriodSummary:
        """
        ملخص شامل لفترة لشاشة الإحصائيات (`stats.view`؛ الربح لمن يملك `stats.profit` فقط).

        نسبة النجاح = (مكتمل + جزئي) ÷ الطلبات **المنتهية** (لا الجارية): الطلب الجاري لم يُحسم بعد
        فلا يُحسب فشلاً. `None` إن لم يُنهَ أي طلب.
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        financial = await self._financial(actor, period, include_profit=include_profit)
        by_status = await self.repos.orders.status_counts_between(period.start_iso, period.end_iso)
        finished = sum(
            by_status.get(status, 0)
            for status in (
                OrderStatus.COMPLETED,
                OrderStatus.PARTIAL,
                OrderStatus.FAILED,
                OrderStatus.CANCELED,
                OrderStatus.REFUNDED,
            )
        )
        succeeded = by_status.get(OrderStatus.COMPLETED, 0) + by_status.get(OrderStatus.PARTIAL, 0)
        return PeriodSummary(
            period=period,
            financial=financial,
            by_status=by_status,
            new_users=await self.repos.users.count_between(period.start_iso, period.end_iso),
            finished_orders=finished,
            success_rate=round(succeeded * 100 / finished, 1) if finished else None,
            avg_order_units=(financial.revenue_units // financial.orders_count) if financial.orders_count else 0,
        )

    async def wallet_liability(self, actor: User) -> tuple[int, int, int]:
        """
        التزامات المحفظة: (مجموع أرصدة المستخدمين، إجمالي الإيداعات، إجمالي الإنفاق).

        يساعد على معرفة المبلغ المستحق للعملاء في أي لحظة.
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        total_balance = await self.repos.users.total_balance_units()
        deposits = await self.repos.transactions.sum_by_type(TransactionType.DEPOSIT)
        spent = await self.repos.transactions.sum_by_type(TransactionType.ORDER)
        return total_balance, deposits, spent

    # ===================================================================== #
    #                          التقارير التشغيلية                           #
    # ===================================================================== #

    async def operations_report(
        self, actor: User, *, days: int = 7, period: Period | None = None
    ) -> OperationsReport:
        """
        تقرير جودة التنفيذ: نسب الاكتمال والفشل والطلبات التي تحتاج تدخلاً.
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        chosen = period or period_for_days(days)
        start_iso, end_iso = chosen.start_iso, chosen.end_iso

        total = await self.repos.orders.count_between(start_iso, end_iso)
        counts = await self.repos.orders.status_counts_between(start_iso, end_iso)
        completed = counts.get(OrderStatus.COMPLETED, 0)
        partial = counts.get(OrderStatus.PARTIAL, 0)

        stuck_hours = await self.settings.get_int("order_stuck_alert_hours", 24)
        stuck = len(
            await self.repos.orders.stuck_orders(
                before_iso=iso_plus_seconds(-max(1, stuck_hours) * 3600), limit=200
            )
        )
        uncertain = (await self.repos.orders.status_counts()).get(
            OrderStatus.SUBMIT_UNCERTAIN, 0
        )
        success_rate = round((completed + partial) * 100 / total, 1) if total else 0.0

        return OperationsReport(
            total_orders=total,
            completed=completed,
            partial=partial,
            failed=counts.get(OrderStatus.FAILED, 0),
            canceled=counts.get(OrderStatus.CANCELED, 0),
            refunded=counts.get(OrderStatus.REFUNDED, 0),
            success_rate=success_rate,
            stuck_orders=stuck,
            uncertain_orders=uncertain,
        )

    async def top_services(
        self, actor: User, *, days: int = 30, limit: int = 5, period: Period | None = None
    ) -> list[dict]:
        """أكثر الخدمات طلباً خلال فترة (اسم الخدمة، العدد، الصافي `total_units`، الإجمالي `gross_units`)."""
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        chosen = period or period_for_days(days)
        return await self.repos.orders.top_services(
            start_iso=chosen.start_iso, end_iso=chosen.end_iso, limit=limit
        )

    async def top_buyers(
        self, actor: User, *, period: Period, limit: int = 5
    ) -> list[BuyerRow]:
        """أكثر العملاء إنفاقاً صافياً خلال فترة (من طلبات الفترة نفسها لا من عدّاد تراكمي)."""
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        rows = await self.repos.orders.top_buyers(
            start_iso=period.start_iso, end_iso=period.end_iso, limit=limit
        )
        result: list[BuyerRow] = []
        for row in rows:
            user = await self.repos.users.get_by_id(int(row["user_id"]))
            result.append(
                BuyerRow(
                    name=user.display_name if user else f"#{row['user_id']}",
                    orders_count=int(row["orders_count"]),
                    net_units=int(row["net_units"]),
                )
            )
        return result

    async def top_users(
        self, actor: User, *, limit: int = 5, days: int = 30, period: Period | None = None
    ) -> list[tuple[str, int]]:
        """أكثر المستخدمين إنفاقاً صافياً: (الاسم الظاهر، الصافي). غلاف توافق فوق `top_buyers`."""
        buyers = await self.top_buyers(actor, period=period or period_for_days(days), limit=limit)
        return [(row.name, row.net_units) for row in buyers]

    async def _daily(self, period: Period) -> list[dict]:
        """
        تجميع الطلبات بأيام **محلية** مع ملء الأيام الخالية بأصفار (قرار المالك).

        الفترات محدودة (≤ 90 يوماً) فالملء آمن؛ وسقف 400 يوم حماية إضافية.
        """
        buckets = await self.repos.orders.minute_buckets(period.start_iso, period.end_iso)
        days: dict[str, dict[str, int]] = defaultdict(
            lambda: {"orders_count": 0, "gross_units": 0, "refund_units": 0}
        )
        for bucket in buckets:
            day = local_day_of(f"{bucket['minute']}:00Z")
            if day is None:
                continue
            days[day]["orders_count"] += int(bucket["orders_count"])
            days[day]["gross_units"] += int(bucket["gross_units"])
            days[day]["refund_units"] += int(bucket["refund_units"])
        for day in self._days_in(period):
            days[day]        # defaultdict: يُنشئ صفراً لليوم الخالي
        return [
            {
                "day": day,
                "orders_count": values["orders_count"],
                "gross_units": values["gross_units"],
                "refund_units": values["refund_units"],
                "total_units": values["gross_units"] - values["refund_units"],
            }
            for day, values in sorted(days.items())
        ]

    @staticmethod
    def _days_in(period: Period) -> list[str]:
        """كل الأيام المحلية `YYYY-MM-DD` التي تغطيها الفترة (من أول يوم إلى آخر يوم)."""
        end = parse_iso(period.end_iso)
        first = local_day_of(period.start_iso)
        if end is None or first is None:
            return []
        last = local_day_of(to_iso(end - timedelta(seconds=1)))
        if last is None:
            return []
        cursor, stop = date.fromisoformat(first), date.fromisoformat(last)
        result: list[str] = []
        while cursor <= stop and len(result) < 400:
            result.append(cursor.isoformat())
            cursor += timedelta(days=1)
        return result

    async def daily_series(
        self, actor: User, *, days: int = 14, period: Period | None = None
    ) -> list[dict]:
        """سلسلة يومية (محلية): عدد الطلبات، الإجمالي، المسترجع، والصافي `total_units`."""
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        return await self._daily(period or period_for_days(days))

    # ===================================================================== #
    #                               التصدير                                 #
    # ===================================================================== #

    async def export_csv(self, actor: User, kind: str, period: Period) -> ExportFile:
        """
        تصدير تقرير كملف CSV (عملية خطِرة: `stats.export`، وتُدقَّق).

        الأنواع: `orders` (طلبات الفترة) · `daily` (ملخص يومي).
        الضمانات: سقف `export_max_rows` (القطع معلن)، تحييد حقن الصيغ في كل خلية نصية،
        عدم تضمين رابط العميل ولا معرّف تيليجرام، وأعمدة الربح لمن يملك `stats.profit` فقط.
        الترميز UTF-8 مع BOM ليفتحه Excel بالعربية صحيحاً.

        الاستثناءات: PermissionDeniedError · ValidationError (نوع غير معروف).
        """
        await self.auth.require_permission(actor, Permission.STATS_EXPORT, context=f"stats.export:{kind}")
        if kind not in EXPORT_KINDS:
            raise ValidationError(f"نوع تصدير غير معروف: {kind!r}", user_message="❌ نوع تصدير غير معروف.")
        if self.audit is None:
            raise ValidationError("خدمة التدقيق غير موصولة", user_message="❌ التصدير غير متاح الآن.")
        include_profit = await self.auth.has_permission(actor, Permission.STATS_PROFIT)
        cap = max(1, await self.settings.get_int("export_max_rows", 20_000))

        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\r\n")
        if kind == "orders":
            columns, rows, truncated = await self._orders_rows(period, cap, include_profit)
        else:
            columns, rows, truncated = await self._daily_rows(period, cap)
        writer.writerow(columns)
        writer.writerows(rows)

        stamp = to_local_text(utc_now_iso(), fmt="%Y%m%d_%H%M")
        filename = f"smm_{kind}_{period.key}_{stamp}.csv"
        await self.audit.log_standalone(
            action="stats.export",
            admin_id=actor.id,
            target_type="report",
            target_id=kind,
            details={
                "period": period.key,
                "rows": len(rows),
                "truncated": truncated,
                "with_profit": include_profit and kind == "orders",
            },
            source="telegram",
        )
        return ExportFile(
            filename=filename,
            content=("\ufeff" + buffer.getvalue()).encode("utf-8"),
            rows=len(rows),
            truncated=truncated,
            period=period,
            columns=columns,
        )

    async def _orders_rows(
        self, period: Period, cap: int, include_profit: bool
    ) -> tuple[list[str], list[list[str]], bool]:
        """أعمدة وصفوف تصدير الطلبات (الأقدم أولاً) مع كشف القطع بسقف الصفوف."""
        fetched = await self.repos.orders.export_rows(period.start_iso, period.end_iso, limit=cap + 1)
        truncated = len(fetched) > cap
        fetched = fetched[:cap]
        columns = [
            "order_id", "code", "created_at_local", "user_id", "service", "quantity",
            "delivered", "status", "gross", "refund", "net",
        ]
        if include_profit:
            columns += ["provider_cost", "est_profit"]
        rows: list[list[str]] = []
        for row in fetched:
            cost, refund = int(row["cost_units"]), int(row["refund_amount_units"])
            line = [
                str(row["id"]),
                csv_safe_text(row["public_code"]),
                to_local_text(row["created_at"], fmt="%Y-%m-%d %H:%M"),
                str(row["user_id"]),
                csv_safe_text(row["service_name"]),
                str(row["quantity"]),
                "" if row["delivered_quantity"] is None else str(row["delivered_quantity"]),
                csv_safe_text(row["status"]),
                money_cell(cost),
                money_cell(refund),
                money_cell(cost - refund),
            ]
            if include_profit:
                provider_cost = row["provider_cost_units"]
                finished = row["status"] in (OrderStatus.COMPLETED, OrderStatus.PARTIAL)
                if provider_cost is None:
                    line += ["", ""]
                else:
                    effective = (int(provider_cost) * (cost - refund)) // cost if cost > 0 else int(provider_cost)
                    line += [money_cell(effective), money_cell(cost - refund - effective) if finished else ""]
            rows.append(line)
        return columns, rows, truncated

    async def _daily_rows(self, period: Period, cap: int) -> tuple[list[str], list[list[str]], bool]:
        """أعمدة وصفوف التصدير اليومي (محلي)."""
        series = await self._daily(period)
        truncated = len(series) > cap
        columns = ["day", "orders", "gross", "refund", "net"]
        rows = [
            [
                item["day"],
                str(item["orders_count"]),
                money_cell(item["gross_units"]),
                money_cell(item["refund_units"]),
                money_cell(item["total_units"]),
            ]
            for item in series[:cap]
        ]
        return columns, rows, truncated

    # ===================================================================== #
    #                            صحة النظام                                 #
    # ===================================================================== #

    async def system_digest(self) -> dict[str, int]:
        """
        أرقام الملخص اليومي — **بلا فاعل بشري**.

        لماذا بلا `actor` ولا فحص صلاحية؟ لأن المستدعي مهمة دورية لا مستخدم،
        والنتيجة لا تُعرض لأحد مباشرة: تُحوَّل إلى إشعار يوزَّع على من يملك
        `stats.view` فعلاً عبر `notify_admins`. فالحارس في مكان التوزيع لا هنا.

        المخرجات: قاموس أرقام جاهز لقالب الإشعار.
        """
        start_today, end_today = day_bounds_utc(0)
        by_status = await self.repos.orders.status_counts()
        today_status = await self.repos.orders.status_counts_between(start_today, end_today)
        totals = await self.repos.orders.period_totals(start_today, end_today)
        attention = sum(
            by_status.get(status, 0)
            for status in (OrderStatus.SUBMIT_UNCERTAIN, OrderStatus.FAILED)
        )
        return {
            "orders_today": totals["orders_count"],
            "revenue_today_units": totals["net_units"],
            "refunds_today_units": totals["refund_units"],
            "completed_today": today_status.get(OrderStatus.COMPLETED, 0) + today_status.get(OrderStatus.PARTIAL, 0),
            "failed_today": today_status.get(OrderStatus.FAILED, 0),
            "deposits_today_units": await self.repos.payments.sum_approved_between(
                start_today, end_today
            ),
            "pending_payments": await self.repos.payments.count_pending(),
            "attention_orders": attention,
            "open_tickets": await self.repos.tickets.count_open(),
            "new_users_today": await self.repos.users.count_since(start_today),
            "errors_24h": await self.repos.error_logs.count_since(iso_minus_days(1)),
        }

    async def system_health(self, actor: User) -> dict[str, object]:
        """
        مؤشرات صحة النظام: المزودون، صندوق الإشعارات، الأخطاء، حجم قاعدة البيانات.

        الاستثناءات: PermissionDeniedError
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)

        providers = await self.repos.providers.list_all()
        provider_rows: list[dict[str, object]] = []
        for provider in providers:
            health = await self.providers.health(provider)
            provider_rows.append(
                {
                    "name": provider.name,
                    "usable": health.is_usable,
                    "reason": health.reason,
                    "consecutive_failures": provider.consecutive_failures,
                    "balance_units": provider.balance_units,
                    "currency": provider.currency,
                    "last_success_at": provider.last_success_at,
                }
            )

        db_size_bytes = self.db.path.stat().st_size if self.db.path.exists() else 0
        last_backup = await self.repos.backups.latest(status="ok")
        return {
            "providers": provider_rows,
            "queued_notifications": await self.repos.notifications.count_queued(),
            "errors_24h": await self.repos.error_logs.count_since(iso_minus_days(1)),
            "db_size_mb": round(db_size_bytes / (1024 * 1024), 2),
            "db_path": str(self.db.path),
            "last_backup_at": (last_backup or {}).get("created_at"),
        }

    async def health_text(self, actor: User) -> str:
        """مؤشرات صحة النظام كنص عربي."""
        health = await self.system_health(actor)
        lines = ["🩺 <b>صحة النظام</b>", ""]

        providers = health["providers"]
        if isinstance(providers, list) and providers:
            for row in providers:
                mark = "🟢" if row["usable"] else "🔴"
                lines.append(
                    f"{mark} {row['name']} — {row['reason']} • "
                    f"رصيد: {format_units(int(row['balance_units']), symbol=str(row['currency'] or ''))}"
                )
        else:
            lines.append("⚠️ لا يوجد مزودون مسجّلون بعد.")

        lines += [
            "",
            f"📨 إشعارات بانتظار الإرسال: {health['queued_notifications']}",
            f"🐞 أخطاء آخر 24 ساعة: {health['errors_24h']}",
            f"🗄 حجم قاعدة البيانات: {health['db_size_mb']} ميغابايت",
            (
                f"💾 آخر نسخة سليمة: {datetime_text(str(health['last_backup_at']))}"
                if health["last_backup_at"]
                else "⚠️ 💾 لا توجد نسخة احتياطية سليمة بعد"
            ),
        ]
        return "\n".join(lines)
