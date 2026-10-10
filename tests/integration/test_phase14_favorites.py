"""
المرحلة الثانية (v1.0.1) — بند 19: المفضلة (إضافة · عرض · إزالة · بلا تكرار · تزامن · خدمة اختفت ثم عادت).
"""

from __future__ import annotations

import asyncio

import pytest

from handlers.user import favorites as favorites_handlers
from integrations.providers.base import ProviderServiceItem
from keyboards.callback_data import NS_FAV, pack
from tests.integration.test_user_interface import bot, context, load_user, press  # noqa: F401,F811

pytestmark = pytest.mark.asyncio


async def _many_services(db, repos, provider, count):
    """إدراج عدد من الخدمات المفعّلة."""
    category = (await repos.categories.list_all())[0]
    async with db.transaction() as tx:
        for index in range(count):
            await tx.execute(
                "INSERT INTO services (category_id, provider_id, provider_service_id, name, price_per_1000_units,"
                " min_quantity, max_quantity, created_at, updated_at) VALUES (?,?,?,?,10000,10,1000,'2026-01-01','2026-01-01')",
                (category.id, provider.id, str(7000 + index), f"Fav service {index}"),
            )
    return [await repos.services.find_by_provider_service(provider.id, str(7000 + i)) for i in range(count)]


async def test_concurrent_adds_create_one_row_and_exactly_one_true(services, user, mock_service) -> None:
    """عشر إضافات متزامنة لنفس الخدمة ⇒ صف واحد وأول واحدة فقط تعيد True."""
    results = await asyncio.gather(*[services.catalog.add_favorite(user, mock_service.id) for _ in range(10)])
    assert results.count(True) == 1 and results.count(False) == 9
    assert await services.repos.favorites.count_for_user(user.id) == 1


async def test_add_list_remove_cycle_and_idempotent_remove(services, user, mock_service) -> None:
    """إضافة ⇒ تظهر ⇒ إزالة ⇒ تختفي؛ إزالة ثانية بلا خطأ؛ إعادة الإضافة تعمل."""
    assert await services.catalog.add_favorite(user, mock_service.id) is True
    assert await services.catalog.add_favorite(user, mock_service.id) is False
    items, page, pages = await services.catalog.favorites_page(user, page=1, page_size=6)
    assert [s.id for s in items] == [mock_service.id] and (page, pages) == (1, 1)
    assert await services.catalog.is_favorite(user, mock_service.id)
    assert await services.catalog.remove_favorite(user, mock_service.id) is True
    assert await services.catalog.remove_favorite(user, mock_service.id) is False
    assert (await services.catalog.favorites_page(user, page=1, page_size=6))[0] == []
    assert await services.catalog.add_favorite(user, mock_service.id) is True


async def test_pagination_newest_first_and_page_clamping(services, db, repos, user, mock_provider) -> None:
    """14 مفضلة ⇒ 3 صفحات (6/6/2) بلا تكرار أو فقد، والصفحة الزائدة تُقصّ لآخر صفحة."""
    created = await _many_services(db, repos, mock_provider, 14)
    for service in created:
        await services.catalog.add_favorite(user, service.id)
        await asyncio.sleep(0.002)                                    # فروق زمنية لترتيب «الأحدث أولاً»
    seen = []
    for page in (1, 2, 3):
        items, current, pages = await services.catalog.favorites_page(user, page=page, page_size=6)
        assert (current, pages) == (page, 3)
        seen.extend(s.id for s in items)
    assert len(seen) == 14 and len(set(seen)) == 14
    assert seen[0] == created[-1].id                                  # الأحدث إضافةً أولاً
    items, current, _ = await services.catalog.favorites_page(user, page=99, page_size=6)
    assert current == 3 and len(items) == 2


async def test_favorite_survives_sync_disable_and_returns_when_service_reappears(services, repos, super_admin, user, mock_provider, mock_service) -> None:
    """خدمة مفضلة اختفت لدى المزود ⇒ تُخفى من القائمة (غير قابلة للطلب) دون حذف المفضلة، وتعود عند عودتها."""
    await services.catalog.add_favorite(user, mock_service.id)
    item = ProviderServiceItem("555", "Mock", 6_000, 100, 100_000)
    await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=[ProviderServiceItem("1", "x", 1, 1, 2)])
    assert (await services.catalog.favorites_page(user, page=1, page_size=6))[0] == []
    assert await services.repos.favorites.count_for_user(user.id) == 1       # الصف باقٍ
    await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=[item])
    assert [s.id for s in (await services.catalog.favorites_page(user, page=1, page_size=6))[0]] == [mock_service.id]


async def test_ui_list_shows_title_and_buttons_per_page_and_toggle_on_unavailable_is_graceful(bot, context, services, db, repos, user, mock_provider, mock_service) -> None:  # noqa: F811
    """الواجهة: العنوان والترقيم وزر الخدمة؛ وإضافة خدمة معطّلة ترد برسالة لا باستثناء."""
    created = await _many_services(db, repos, mock_provider, 8)
    for service in created:
        await services.catalog.add_favorite(user, service.id)
    await load_user(bot, context, user)
    await press(bot, context, favorites_handlers.favorites_screen, pack(NS_FAV, "list", 2), user.telegram_id)
    assert "2" in bot.last.text and sum(1 for b in bot.last.buttons if b.startswith("cat:")) >= 2
    assert pack(NS_FAV, "list", 1) in bot.last.buttons                  # زر الصفحة السابقة

    async with db.transaction() as tx:
        await tx.execute("UPDATE services SET is_active = 0 WHERE id = ?", (mock_service.id,))
    bot.clear()
    await press(bot, context, favorites_handlers.favorite_toggle, pack(NS_FAV, "add", mock_service.id, 1, 1), user.telegram_id)
    assert any("لم تعد متاحة" in (a["text"] or "") for a in bot.answers)
    assert await services.repos.favorites.count_for_user(user.id) == 8
