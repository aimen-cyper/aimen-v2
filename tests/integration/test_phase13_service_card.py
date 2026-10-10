"""
بطاقة الخدمة والدولار ورقم الخدمة والمفضلة (المرحلة 13 — بنود 5 و6 و8 و19).

كلها عبر FakeBot ومعالجات حقيقية وقاعدة SQLite مؤقتة؛ لا Telegram حقيقي.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.money import to_units
from handlers.user import catalog as catalog_handlers
from handlers.user import favorites as favorites_handlers
from keyboards.callback_data import NS_CATALOG, NS_FAV, NS_NEW, pack
from keyboards.user_kb import service_button_label
from services.catalog_service import MAX_FAVORITES
from tests.integration.test_user_interface import bot, context, load_user, press, write  # noqa: F401,F811
from utils.formatters import local_amount, price_pair

pytestmark = pytest.mark.asyncio


async def _open_card(bot, context, user, service_id, category_id=1, page=1):  # noqa: F811
    await load_user(bot, context, user)
    await press(bot, context, catalog_handlers.service_card_screen,
                pack(NS_CATALOG, "svc", service_id, category_id, page), user.telegram_id)
    return bot.last


async def test_local_amount_drops_trailing_zeros() -> None:
    """530.00 ⇒ «530 ريال»، و530.50 تبقى، والآلاف بفاصلة."""
    assert local_amount(to_units(Decimal("530")), "ريال") == "530 ريال"
    assert local_amount(to_units(Decimal("530.5")), "ريال") == "530.50 ريال"
    assert local_amount(to_units(Decimal("12345")), "ريال") == "12,345 ريال"


async def test_price_pair_is_dollar_first_and_consistent() -> None:
    """$1.00 مقابل 530 ريال عند الصرف 530 — والمقابل هو المبلغ الحقيقي."""
    usd, local = price_pair(to_units(Decimal("530")), "ريال", Decimal("530"))
    assert usd == "$1.00"
    assert local == "530 ريال"


async def test_card_shows_id_dollar_rate_and_unset_fields(bot, context, user, mock_service, services) -> None:  # noqa: F811
    """البطاقة: الرقم، الدولار، المقابل، الصرف، «غير محددة» للناقص، حدّان، زرا طلب ومفضلة."""
    await services.settings.set("usd_rate", "530", admin_id=None)
    await services.repos.settings.get("usd_rate")
    msg = await _open_card(bot, context, user, mock_service.id)
    text = msg.text
    assert f"#{mock_service.id}" in text
    assert "💵 السعر لكل 1000: <b>$" in text
    assert "💴 ما يعادل:" in text and "ريال" in text
    assert "1$ = 530" in text
    assert text.count("غير محددة") >= 2  # الجودة والضمان لم تُضبطا
    assert "الحد الأدنى" in text and "الحد الأقصى" in text
    buttons = msg.buttons
    assert pack(NS_NEW, "start", mock_service.id) in buttons
    assert pack(NS_FAV, "add", mock_service.id, 1, 1) in buttons


async def test_card_uses_provided_speed_quality_guarantee(bot, context, user, mock_service, services) -> None:  # noqa: F811
    """الحقول المضبوطة تظهر كما هي لا «غير محددة»."""
    async with services.db.transaction() as tx:
        await tx.execute(
            "UPDATE services SET speed_text=?, quality_text=?, guarantee_text=? WHERE id=?",
            ("1000/ساعة", "عالية", "30 يوماً", mock_service.id),
        )
    text = (await _open_card(bot, context, user, mock_service.id)).text
    assert "1000/ساعة" in text and "عالية" in text and "30 يوماً" in text
    assert "غير محددة" not in text


async def test_service_button_label_has_id_and_fits_telegram_limit(mock_service) -> None:
    """زر الخدمة يحمل الرقم والسعر ولا يتجاوز 64 حرفاً مهما طال الاسم."""
    from dataclasses import replace

    long = replace(mock_service, name="اسم خدمة طويل جداً " * 10)
    label = service_button_label(long, symbol="ريال", usd_rate=Decimal("530"))
    assert label.startswith(f"#{long.id} · ")
    assert "$" in label and len(label) <= 64


async def test_favorite_add_toggle_no_duplicates_and_remove(bot, context, user, mock_service, services) -> None:  # noqa: F811
    """إضافة ⇒ البطاقة تعرض «إزالة»؛ إضافة ثانية لا تكرر؛ إزالة ⇒ تعود «مفضلة»."""
    await load_user(bot, context, user)
    for _ in range(2):
        await press(bot, context, favorites_handlers.favorite_toggle,
                    pack(NS_FAV, "add", mock_service.id, 1, 1), user.telegram_id)
    assert await services.repos.favorites.count_for_user(user.id) == 1
    assert pack(NS_FAV, "del", mock_service.id, 1, 1) in bot.last.buttons

    await press(bot, context, favorites_handlers.favorite_toggle,
                pack(NS_FAV, "del", mock_service.id, 1, 1), user.telegram_id)
    assert await services.repos.favorites.count_for_user(user.id) == 0
    assert pack(NS_FAV, "add", mock_service.id, 1, 1) in bot.last.buttons


async def test_favorites_list_empty_and_filled_and_back_from_card(bot, context, user, mock_service, services) -> None:  # noqa: F811
    """قائمة فارغة ⇒ رسالة إرشاد؛ بعد الإضافة تظهر الخدمة؛ البطاقة منها ترجع للمفضلة لا للتصنيف."""
    await load_user(bot, context, user)
    await press(bot, context, favorites_handlers.favorites_screen, pack(NS_FAV, "list", 1), user.telegram_id)
    assert "لا توجد خدمات" in (bot.last.text or "")

    await services.catalog.add_favorite(user, mock_service.id)
    await press(bot, context, favorites_handlers.favorites_screen, pack(NS_FAV, "list", 1), user.telegram_id)
    assert f"#{mock_service.id}" in str(bot.last.markup)
    card = await _open_card(bot, context, user, mock_service.id, category_id=0)
    assert pack(NS_FAV, "list", 1) in card.buttons
    assert pack(NS_CATALOG, "open", 0, 1) not in card.buttons


async def test_favorites_are_per_user_and_hide_unavailable(user, admin, mock_service, services) -> None:  # noqa: F811
    """مفضلة كل مستخدم منفصلة، والخدمة المعطّلة تختفي من القائمة دون حذفها."""
    await services.catalog.add_favorite(user, mock_service.id)
    items, _, _ = await services.catalog.favorites_page(admin, page=1, page_size=6)
    assert items == []
    items, _, _ = await services.catalog.favorites_page(user, page=1, page_size=6)
    assert [s.id for s in items] == [mock_service.id]
    async with services.db.transaction() as tx:
        await tx.execute("UPDATE services SET is_active=0 WHERE id=?", (mock_service.id,))
    items, _, _ = await services.catalog.favorites_page(user, page=1, page_size=6)
    assert items == []
    assert await services.repos.favorites.count_for_user(user.id) == 1


async def test_favorite_limit_is_enforced(user, mock_service, services, monkeypatch) -> None:  # noqa: F811
    """تجاوز الحد يُرفض برسالة عربية واضحة ولا يُكتب شيء؛ والحد الافتراضي 100."""
    from core.exceptions import ValidationError
    from services import catalog_service

    assert MAX_FAVORITES == 100
    monkeypatch.setattr(catalog_service, "MAX_FAVORITES", 0)
    with pytest.raises(ValidationError) as exc:
        await services.catalog.add_favorite(user, mock_service.id)
    assert "للحد الأقصى" in exc.value.user_message
    assert await services.repos.favorites.count_for_user(user.id) == 0
