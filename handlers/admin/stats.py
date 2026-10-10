"""
قسم «📈 الإحصائيات» في لوحة التحكم (المرحلة 10).

الشاشات (مساحة `st`):
    st:home:<p>          : ملخص الفترة (طلبات، إيراد صافٍ، مسترجع، ربح تقديري، مستخدمون).
    st:svc:<p>           : أكثر الخدمات طلباً.
    st:usr:<p>           : أكثر العملاء إنفاقاً صافياً.
    st:day:<p>           : سلسلة يومية (بأيام محلية).
    st:wal               : التزامات المحفظة.
    st:expm:<p>          : قائمة التصدير (`stats.export`).
    st:expask:<k>:<p>    : تأكيد ثانٍ قبل التصدير.
    st:exp:<k>:<p>       : إرسال ملف CSV (يُدقَّق).

الفترات: today · yesterday · 7d · 30d · 90d · month (أيام محلية كاملة).

قواعد ملزمة:
    • كل شاشة تفحص `stats.view` على الـcallback؛ التصدير `stats.export` (والخدمة تعيد الفحص).
    • الربح يظهر لمن يملك `stats.profit` فقط (الخدمة لا تحسبه لغيره أصلاً).
    • لا أرقام تقديرية مخفية: التغطية معلنة، و«غير محسوب» يُقال صراحة.
"""

from __future__ import annotations

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler, ContextTypes

from core.permissions import Permission
from handlers.admin.common import admin_required, args, permissions_of, symbol_of
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    stats_export_confirm_kb,
    stats_export_menu_kb,
    stats_home_kb,
    stats_sub_kb,
    stats_wallet_kb,
)
from keyboards.callback_data import NS_ADM_STATS, pattern
from middlewares.context import require_user, services_of
from services.stats_service import EXPORT_KINDS, PeriodSummary, build_period
from texts import admin_ar as t
from utils.formatters import money_text, safe
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: أقصى عدد أيام تُعرض في الشاشة اليومية (حد رسالة تيليجرام 4096 حرفاً)
DAILY_MAX_LINES = 31

#: عرض شريط الاتجاه اليومي بالمربعات
BAR_WIDTH = 8


def summary_text(summary: PeriodSummary, symbol: str, *, can_see_profit: bool) -> str:
    """
    نص ملخص الفترة (دالة نقية قابلة للاختبار).

    الربح: يُعرض لمن يملك `stats.profit` فقط. إن لم تُغطَّ كل الطلبات المنتهية يُنبَّه صراحة.
    """
    report = summary.financial
    profit = ""
    if can_see_profit:
        if report.profit_units is None:
            profit = t.STATS_PROFIT_NONE
        else:
            profit = t.STATS_PROFIT_LINE.format(
                profit=money_text(report.profit_units, symbol),
                cost=money_text(report.provider_cost_units, symbol),
                pct=report.profit_coverage_pct if report.profit_coverage_pct is not None else 0,
                covered=report.profit_covered_orders,
                eligible=report.profit_eligible_orders,
            )
            if report.profit_covered_orders < report.profit_eligible_orders:
                profit += t.STATS_PROFIT_PARTIAL_NOTE
    return t.STATS_HOME.format(
        label=summary.period.label,
        orders=report.orders_count,
        active=summary.active_orders,
        finished=summary.finished_orders,
        success=(f"{summary.success_rate}%" if summary.success_rate is not None else t.STATS_NO_SUCCESS),
        gross=money_text(report.gross_units, symbol),
        refund=money_text(report.order_refund_units, symbol),
        net=money_text(report.revenue_units, symbol),
        avg=money_text(summary.avg_order_units, symbol),
        profit=profit,
        buyers=report.buyers,
        new_users=summary.new_users,
        deposits=money_text(report.deposits_units, symbol),
        credit=money_text(report.manual_credit_units, symbol),
        debit=money_text(report.manual_debit_units, symbol),
    )


def _bar(value: int, peak: int) -> str:
    """شريط مربعات نسبي لاتجاه يومي (فارغ إن لم يوجد إيراد)."""
    if peak <= 0 or value <= 0:
        return "▫️"
    filled = max(1, round(value * BAR_WIDTH / peak))
    return "█" * filled


def _period_key(update: Update, index: int = 0) -> str:
    """مفتاح الفترة من وسائط الزر (الافتراضي: اليوم). القيم الغريبة يرفضها `build_period`."""
    return args(update).arg(index) or "today"


@guarded
@admin_required(Permission.STATS_VIEW)
async def home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ملخص الفترة المختارة."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    period = build_period(_period_key(update))
    perms = await permissions_of(context)
    summary = await services.stats.summary(admin, period)
    text = summary_text(summary, await symbol_of(context), can_see_profit=Permission.STATS_PROFIT in perms)
    await render(update, context, text, stats_home_kb(period.key, perms))


@guarded
@admin_required(Permission.STATS_VIEW)
async def services_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """أكثر الخدمات طلباً في الفترة."""
    await answer_callback(update)
    period = build_period(_period_key(update))
    rows = await services_of(context).stats.top_services(require_user(context), period=period, limit=10)
    if not rows:
        await render(update, context, t.STATS_SERVICES_EMPTY.format(label=period.label), stats_sub_kb("svc", period.key))
        return
    symbol = await symbol_of(context)
    lines = "\n".join(
        t.STATS_SERVICES_LINE.format(
            rank=index,
            name=safe(row["service_name"], limit=40),
            count=row["orders_count"],
            net=money_text(int(row["total_units"]), symbol),
        )
        for index, row in enumerate(rows, start=1)
    )
    await render(
        update, context, t.STATS_SERVICES_TITLE.format(label=period.label, lines=lines), stats_sub_kb("svc", period.key)
    )


@guarded
@admin_required(Permission.STATS_VIEW)
async def buyers_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """أكثر العملاء إنفاقاً صافياً في الفترة."""
    await answer_callback(update)
    period = build_period(_period_key(update))
    buyers = await services_of(context).stats.top_buyers(require_user(context), period=period, limit=10)
    if not buyers:
        await render(update, context, t.STATS_BUYERS_EMPTY.format(label=period.label), stats_sub_kb("usr", period.key))
        return
    symbol = await symbol_of(context)
    lines = "\n".join(
        t.STATS_BUYERS_LINE.format(
            rank=index,
            name=safe(row.name, limit=30),
            count=row.orders_count,
            net=money_text(row.net_units, symbol),
        )
        for index, row in enumerate(buyers, start=1)
    )
    await render(
        update, context, t.STATS_BUYERS_TITLE.format(label=period.label, lines=lines), stats_sub_kb("usr", period.key)
    )


@guarded
@admin_required(Permission.STATS_VIEW)
async def daily_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """سلسلة يومية بأيام محلية مع شريط اتجاه، والمجموع يشمل كل الأيام حتى المقطوعة من العرض."""
    await answer_callback(update)
    period = build_period(_period_key(update))
    series = await services_of(context).stats.daily_series(require_user(context), period=period)
    if not any(int(item["orders_count"]) for item in series):      # لا طلب في الفترة كلها
        await render(update, context, t.STATS_DAILY_EMPTY.format(label=period.label), stats_sub_kb("day", period.key))
        return
    symbol = await symbol_of(context)
    shown = series[-DAILY_MAX_LINES:]
    peak = max(int(item["total_units"]) for item in shown)
    lines = "\n".join(
        t.STATS_DAILY_LINE.format(
            day=item["day"],
            bar=_bar(int(item["total_units"]), peak),
            count=item["orders_count"],
            net=money_text(int(item["total_units"]), symbol),
        )
        for item in shown
    )
    footer = t.STATS_DAILY_FOOTER.format(
        count=sum(int(item["orders_count"]) for item in series),
        net=money_text(sum(int(item["total_units"]) for item in series), symbol),
    )
    if len(series) > len(shown):
        footer = t.STATS_DAILY_CUT.format(shown=len(shown), total=len(series)).strip() + "\n" + footer
    await render(
        update,
        context,
        t.STATS_DAILY_TITLE.format(label=period.label, lines=lines, footer=footer),
        stats_sub_kb("day", period.key),
    )


@guarded
@admin_required(Permission.STATS_VIEW)
async def wallet_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """التزامات المحفظة: ما يدين به النظام للعملاء الآن."""
    await answer_callback(update)
    balance, deposits, spent = await services_of(context).stats.wallet_liability(require_user(context))
    symbol = await symbol_of(context)
    await render(
        update,
        context,
        t.STATS_WALLET.format(
            balance=money_text(balance, symbol), deposits=money_text(deposits, symbol), spent=money_text(spent, symbol)
        ),
        stats_wallet_kb(),
    )


@guarded
@admin_required(Permission.STATS_EXPORT)
async def export_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة اختيار نوع التقرير للتصدير."""
    await answer_callback(update)
    period = build_period(_period_key(update))
    cap = await services_of(context).settings.get_int("export_max_rows", 20_000)
    await render(
        update, context, t.STATS_EXPORT_MENU.format(label=period.label, cap=cap), stats_export_menu_kb(period.key)
    )


def _kind_of(update: Update) -> str:
    """نوع التصدير من وسائط الزر؛ أي قيمة غير معروفة تُنقل كما هي لترفضها الخدمة."""
    return args(update).arg(0)


@guarded
@admin_required(Permission.STATS_EXPORT)
async def export_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة التأكيد الثانٍ للتصدير (لا يُنشأ أي ملف هنا)."""
    await answer_callback(update)
    kind = _kind_of(update)
    period = build_period(_period_key(update, 1))
    if kind not in EXPORT_KINDS:
        await answer_callback(update, "❌ نوع تصدير غير معروف.", alert=True)
        return
    await render(
        update,
        context,
        t.STATS_EXPORT_ASK.format(kind=t.STATS_EXPORT_KIND_LABELS[kind], label=period.label),
        stats_export_confirm_kb(kind, period.key),
    )


@guarded
@admin_required(Permission.STATS_EXPORT)
async def export_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إنشاء ملف CSV وإرساله لمحادثة الأدمن (الخدمة تتحقق من الصلاحية وتُدقّق)."""
    await answer_callback(update, "⏳ جارٍ التجهيز…")
    kind = _kind_of(update)
    period = build_period(_period_key(update, 1))
    chat = update.effective_chat
    if chat is None:
        logger.warning("تصدير بلا محادثة فعّالة")
        return
    exported = await services_of(context).stats.export_csv(require_user(context), kind, period)
    caption = t.STATS_EXPORT_CAPTION.format(
        kind=t.STATS_EXPORT_KIND_LABELS.get(kind, kind),
        label=period.label,
        rows=exported.rows,
        cut=t.STATS_EXPORT_CUT if exported.truncated else "",
    )
    try:
        await context.bot.send_document(
            chat_id=chat.id,
            document=exported.content,
            filename=exported.filename,
            caption=caption,
            protect_content=True,
        )
    except TelegramError as exc:
        logger.error("فشل إرسال ملف التصدير: %s", type(exc).__name__, exc_info=True)
        await send(update, context, f"❌ تعذّر إرسال الملف عبر تيليجرام: {safe(str(exc), limit=120)}")
        return
    await send(update, context, t.STATS_EXPORT_DONE.format(rows=exported.rows), stats_export_menu_kb(period.key))


def conversations() -> list:
    """لا محادثات في قسم الإحصائيات — شاشات وأزرار فقط."""
    return []


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم الإحصائيات."""
    table = (
        ("home", home_screen),
        ("svc", services_screen),
        ("usr", buyers_screen),
        ("day", daily_screen),
        ("wal", wallet_screen),
        ("expm", export_menu),
        ("expask", export_ask),
        ("exp", export_action),
    )
    return [CallbackQueryHandler(handler, pattern=pattern(NS_ADM_STATS, action)) for action, handler in table]
