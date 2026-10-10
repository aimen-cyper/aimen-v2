"""
اختبارات كتالوج الخدمات: التصفح، التسعير، وإدارة الأسعار.
"""

from __future__ import annotations

import pytest

from core.exceptions import (
    PermissionDeniedError,
    QuantityOutOfRangeError,
    ServiceNotAvailableError,
)
from database.models import Service, User
from database.repositories import Repositories
from services import ServiceContainer


async def test_categories_show_only_those_with_services(
    services: ServiceContainer, service: Service
) -> None:
    """لا يُعرض تصنيف فارغ للمستخدم."""
    categories = await services.catalog.categories()
    assert len(categories) == 1
    assert categories[0].id == service.category_id


async def test_services_page_navigation(
    services: ServiceContainer, service: Service
) -> None:
    """صفحات الخدمات تحسب العدد الكلي وأزرار التنقل بدقة."""
    page = await services.catalog.services_page(service.category_id, page=1, page_size=10)
    assert page.total_items == 1
    assert page.total_pages == 1
    assert not page.has_next and not page.has_prev
    assert page.items[0].id == service.id


async def test_search_finds_service_by_name(services: ServiceContainer, service: Service) -> None:
    """البحث النصي يجد الخدمة باسمها العربي."""
    results = await services.catalog.search("انستغرام")
    assert any(item.id == service.id for item in results)


async def test_quote_calculates_cost_correctly(
    services: ServiceContainer, service: Service
) -> None:
    """التسعيرة = السعر لكل ألف × الكمية ÷ 1000، مع نص جاهز للعرض."""
    quote = await services.catalog.quote(service, 1000)
    assert quote.quantity == 1000
    assert quote.cost_units == 10_000
    assert "1.00" in quote.cost_text

    half = await services.catalog.quote(service, 500)
    assert half.cost_units == 5_000


async def test_quote_rejects_out_of_range_quantity(
    services: ServiceContainer, service: Service
) -> None:
    """الكمية خارج حدود الخدمة تُرفض قبل أي خصم."""
    with pytest.raises(QuantityOutOfRangeError):
        await services.catalog.quote(service, 10)
    with pytest.raises(QuantityOutOfRangeError):
        await services.catalog.quote(service, 999_999)


async def test_disabled_service_is_not_orderable(
    services: ServiceContainer, repos: Repositories, service: Service, super_admin: User
) -> None:
    """الخدمة المعطّلة تختفي من الطلب لكنها تبقى في قاعدة البيانات (لا حذف)."""
    await services.catalog.set_service_active(super_admin, service.id, False)

    with pytest.raises(ServiceNotAvailableError):
        await services.catalog.get_available_service(service.id)

    stored = await repos.services.get(service.id)
    assert stored is not None and stored.is_active == 0


async def test_price_change_requires_permission_and_keeps_history(
    services: ServiceContainer, repos: Repositories, service: Service, user: User, admin: User
) -> None:
    """تغيير السعر محمي بصلاحية، ويحفظ السعر القديم في السجل التاريخي."""
    with pytest.raises(PermissionDeniedError):
        await services.catalog.change_price(user, service.id, 20_000)

    assert await services.catalog.change_price(admin, service.id, 20_000)
    updated = await repos.services.get(service.id)
    assert updated is not None and updated.price_per_1000_units == 20_000

    history = await repos.services.price_history(service.id)
    assert history and int(history[0]["old_price_units"]) == 10_000


async def test_old_orders_keep_their_price_snapshot(
    services: ServiceContainer, repos: Repositories, mock_service: Service,
    user: User, admin: User,
) -> None:
    """تغيير السعر لا يمس الطلبات القديمة (السعر مخزَّن كلقطة داخل الطلب)."""
    await services.wallet.adjust_balance(
        target=user, amount_units=100_000, admin=admin, reason="رصيد", credit=True
    )
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/x", quantity=1000
    )
    await services.catalog.change_price(admin, mock_service.id, 50_000)

    stored = await repos.orders.get(order.id)
    assert stored is not None
    assert stored.price_per_1000_snapshot_units == 10_000
    assert stored.cost_units == 10_000


async def test_negative_margin_report(
    services: ServiceContainer, repos: Repositories, service: Service, admin: User
) -> None:
    """تقرير الهامش السالب يكشف الخدمات التي تُباع بأقل من تكلفتها."""
    assert await services.catalog.negative_margin_report(admin) == []

    await services.catalog.change_price(admin, service.id, 3_000)  # أقل من تكلفة المزود 6000
    flagged = await services.catalog.negative_margin_report(admin)
    assert [item.id for item in flagged] == [service.id]


async def test_admin_can_create_category_and_service(
    services: ServiceContainer, super_admin: User, provider
) -> None:
    """إنشاء تصنيف وخدمة من لوحة الأدمن مع التحقق من المدخلات."""
    category = await services.catalog.create_category(super_admin, name_ar="واتساب", emoji="💬")
    new_service = await services.catalog.create_service(
        super_admin,
        category_id=category.id,
        provider_id=provider.id,
        provider_service_id="777",
        name="أعضاء قناة واتساب",
        price_per_1000_units=25_000,
        min_quantity=50,
        max_quantity=5_000,
        provider_price_per_1000_units=15_000,
    )
    assert new_service.category_id == category.id
    assert new_service.available
