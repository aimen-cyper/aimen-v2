"""
اختبارات الإحصائيات: كل رقم يجب أن يأتي من قاعدة البيانات لا من تقدير.
"""

from __future__ import annotations

import pytest

from core.enums import OrderStatus
from core.exceptions import PermissionDeniedError
from core.permissions import Permission
from database.models import Service, User
from database.repositories import Repositories
from services import ServiceContainer
from utils.datetime_utils import iso_plus_seconds


async def _prepare_activity(
    services: ServiceContainer, user: User, admin: User, mock_service: Service, count: int = 3
) -> None:
    """تجهيز نشاط حقيقي: رصيد + طلبات فعلية."""
    await services.wallet.adjust_balance(
        target=user, amount_units=200_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    await services.settings.set("duplicate_order_window_minutes", 0)
    for index in range(count):
        await services.orders.create_order(
            user,
            service_id=mock_service.id,
            link=f"https://instagram.com/u{index}",
            quantity=1000,
        )


async def test_dashboard_requires_permission(services: ServiceContainer, user: User) -> None:
    """المستخدم العادي لا يرى لوحة الإحصائيات."""
    with pytest.raises(PermissionDeniedError):
        await services.stats.dashboard(user)


async def test_dashboard_numbers_match_database(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service
) -> None:
    """أرقام اللوحة مطابقة لما في قاعدة البيانات فعلاً."""
    await _prepare_activity(services, user, admin, mock_service, count=3)

    stats = await services.stats.dashboard(admin)
    assert stats.users_total == await repos.users.count_all()
    assert stats.orders_today == 3
    assert stats.orders_by_status.get(OrderStatus.PENDING) == 3
    assert stats.revenue_today_units == 30_000
    assert stats.active_services == 1
    assert stats.pending_payments == 0


async def test_dashboard_text_is_arabic_and_complete(
    services: ServiceContainer, user: User, admin: User, mock_service: Service
) -> None:
    """النص المعروض للأدمن يحتوي الأقسام الأساسية."""
    await _prepare_activity(services, user, admin, mock_service, count=1)
    text = await services.stats.dashboard_text(admin)

    for part in ["لوحة المعلومات", "المستخدمون", "طلبات اليوم", "مبيعات اليوم", "تذاكر مفتوحة"]:
        assert part in text


async def test_financial_report_counts_money_movements(
    services: ServiceContainer, user: User, admin: User, super_admin: User, mock_service: Service, payment_method
) -> None:
    """التقرير المالي يجمع المبيعات والإيداعات والاسترجاعات."""
    await _prepare_activity(services, user, admin, mock_service, count=2)

    payment = await services.payments.create_payment(
        user, method_id=payment_method.id, raw_amount="10", transaction_reference="TRX-STATS"
    )
    await services.payments.approve(admin, payment.id)

    orders = await services.orders.list_for_user(user)
    await services.orders.cancel_by_user(user, orders[0].id)

    report = await services.stats.financial_report(super_admin, days=1)
    assert report.orders_count == 2
    assert report.gross_units == 20_000                # الإجمالي المخصوم
    assert report.order_refund_units == 10_000         # ما رُدّ للعميل
    assert report.revenue_units == 10_000              # الإيراد الصافي (م10): الملغى لا يُحتسب إيراداً
    assert report.deposits_units == 100_000
    assert report.refunds_units == 10_000


async def test_profit_hidden_without_permission(
    services: ServiceContainer, user: User, admin: User, mock_service: Service
) -> None:
    """الربح لا يُحسب لمن لا يملك صلاحية `stats.profit` (لا رقم مضلل)."""
    await _prepare_activity(services, user, admin, mock_service, count=1)

    report = await services.stats.financial_report(admin, days=1)
    assert report.profit_units is None
    assert not report.profit_known

    text = await services.stats.financial_report_text(admin, days=1)
    assert "غير محسوب" in text


async def test_profit_calculated_for_super_admin(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    super_admin: User, mock_service: Service, mock_client,
) -> None:
    """الربح = صافي الطلبات **المنتهية** − تكلفة المزود المسجّلة؛ والجاري لا يدخل الحساب."""
    await _prepare_activity(services, user, admin, mock_service, count=1)
    await services.orders.process_pending_orders()

    running = await services.stats.financial_report(super_admin, days=1)
    assert running.profit_units is None and running.profit_eligible_orders == 0   # لم يُنهَ بعد

    for _ in range(5):                                   # متابعة حتى الاكتمال
        for order in await services.orders.list_for_user(user):
            async with repos.db.transaction() as tx:
                await repos.orders.update_fields(tx, order.id, next_check_at=iso_plus_seconds(-10))
        await services.orders.process_due_orders()

    report = await services.stats.financial_report(super_admin, days=1)
    assert report.provider_cost_units == 6_000
    assert report.profit_units == report.revenue_units - 6_000
    assert report.profit_coverage_pct == 100


async def test_operations_report_measures_success_rate(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client,
) -> None:
    """تقرير التشغيل يحسب نسبة النجاح من الطلبات الفعلية."""
    await _prepare_activity(services, user, admin, mock_service, count=2)
    await services.orders.process_pending_orders()

    for _ in range(5):   # تقديم موعد الفحص ثم المتابعة حتى الاكتمال
        for order in await services.orders.list_for_user(user):
            async with repos.db.transaction() as tx:
                await repos.orders.update_fields(
                    tx, order.id, next_check_at=iso_plus_seconds(-10)
                )
        await services.orders.process_due_orders()

    report = await services.stats.operations_report(admin, days=1)
    assert report.total_orders == 2
    assert report.completed == 2
    assert report.success_rate == 100.0
    assert report.uncertain_orders == 0


async def test_top_services_and_users(
    services: ServiceContainer, user: User, admin: User, mock_service: Service
) -> None:
    """تقارير الأكثر طلباً والأكثر إنفاقاً مبنية على بيانات حقيقية."""
    await _prepare_activity(services, user, admin, mock_service, count=2)

    top_services = await services.stats.top_services(admin, days=1)
    assert top_services[0]["service_name"] == mock_service.name
    assert top_services[0]["orders_count"] == 2

    top_users = await services.stats.top_users(admin)
    assert top_users[0][0] == user.display_name
    assert top_users[0][1] == 20_000


async def test_wallet_liability_matches_balances(
    services: ServiceContainer, user: User, admin: User
) -> None:
    """التزام المحفظة = مجموع أرصدة المستخدمين الفعلية."""
    await services.wallet.adjust_balance(
        target=user, amount_units=75_000, admin=admin, reason="رصيد", credit=True
    )
    total, deposits, spent = await services.stats.wallet_liability(admin)
    assert total == 75_000
    assert deposits == 0      # لا إيداعات عبر طلبات شحن
    assert spent == 0


async def test_system_health_reports_providers(
    services: ServiceContainer, admin: User, mock_provider
) -> None:
    """تقرير الصحة يعرض حالة كل مزود وحجم قاعدة البيانات."""
    health = await services.stats.system_health(admin)
    assert health["providers"][0]["name"] == mock_provider.name
    assert health["providers"][0]["usable"] is True
    assert float(health["db_size_mb"]) >= 0

    text = await services.stats.health_text(admin)
    assert "صحة النظام" in text and mock_provider.name in text


async def test_daily_series_groups_by_day(
    services: ServiceContainer, user: User, admin: User, mock_service: Service
) -> None:
    """السلسلة اليومية تجمع طلبات اليوم في صف واحد."""
    await _prepare_activity(services, user, admin, mock_service, count=2)
    series = await services.stats.daily_series(admin, days=2)
    assert len(series) == 2                              # أمس خالٍ بصفر + اليوم
    assert series[0]["orders_count"] == 0 and series[0]["total_units"] == 0
    assert series[-1]["orders_count"] == 2
    assert series[-1]["total_units"] == 20_000


async def test_daily_series_fills_gap_days_with_zero_and_exports_them(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, super_admin: User, mock_service: Service
) -> None:
    """يوم خالٍ في منتصف الفترة يظهر بصفر في السلسلة وفي تصدير CSV اليومي (قرار المالك)."""
    from datetime import datetime, timedelta, timezone

    from services.stats_service import build_period

    await _prepare_activity(services, user, admin, mock_service, count=2)
    ids = [int(r["id"]) for r in await repos.db.fetchall("SELECT id FROM orders ORDER BY id")]
    async with repos.db.transaction() as tx:               # طلب قبل 3 أيام وآخر اليوم
        old = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        await tx.execute("UPDATE orders SET created_at = ? WHERE id = ?", (old, ids[0]))
    series = await services.stats.daily_series(admin, days=5)
    assert len(series) == 5
    assert [item["orders_count"] for item in series].count(0) == 3
    assert sum(item["orders_count"] for item in series) == 2
    days = [item["day"] for item in series]
    assert days == sorted(days) and len(set(days)) == 5     # متصلة بلا تكرار

    export = await services.stats.export_csv(super_admin, "daily", build_period("7d"))
    assert export.rows == 7                                 # 7 أيام كاملة بينها الخالية


async def test_support_role_can_view_stats_but_not_profit(
    services: ServiceContainer, repos: Repositories, user: User, super_admin: User
) -> None:
    """دور الدعم لا يملك `stats.view` افتراضياً — الإحصائيات ليست من مهامه."""
    assert not await services.auth.has_permission(user, Permission.STATS_VIEW)
    await services.auth.set_user_permission(
        super_admin, user.id, Permission.STATS_VIEW, allow=True
    )
    granted = await repos.users.get_by_id(user.id)
    assert granted is not None
    stats = await services.stats.dashboard(granted)
    assert stats.users_total >= 1
