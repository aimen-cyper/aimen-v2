"""
استيراد دفعة، بطاقة الأدمن (الربط داخلي↔مزود↔Provider ID)، تعديل حقول العرض، قواعد الروابط في الطلب،
وإدخال الهامش/الصرف (المرحلة 13 — بنود 8 و9 و10 و11).
"""

from __future__ import annotations

import pytest

from core.exceptions import InvalidLinkError, ValidationError
from handlers.admin import catalog as admin_catalog
from handlers.admin import providers as admin_providers
from keyboards.callback_data import NS_ADM_CAT, pack
from tests.integration.test_user_interface import bot, context, load_user, press, write  # noqa: F401,F811
from utils.validators import parse_margin_percent

pytestmark = pytest.mark.asyncio


async def _start_import(bot, context, admin, provider, query):  # noqa: F811
    await press(bot, context, admin_providers.start_import, pack("pv", "imp", provider.id), admin.telegram_id)
    return await write(bot, context, admin_providers.receive_import_query, query, admin.telegram_id)


async def _finish_import(bot, context, admin, margin="40"):  # noqa: F811
    await press(bot, context, admin_providers.import_continue, pack("pv", "go"), admin.telegram_id)
    category_button = next(b for b in bot.last.buttons if b.startswith("pv:cat:"))
    await press(bot, context, admin_providers.pick_import_category, category_button, admin.telegram_id)
    await write(bot, context, admin_providers.receive_margin, margin, admin.telegram_id)
    return await press(bot, context, admin_providers.confirm_import, pack("flow", "confirm"), admin.telegram_id)


# ============================ استيراد دفعة (9) ============================ #


async def test_batch_import_by_ids_creates_all_with_correct_mapping(bot, context, admin, mock_provider, mock_client, repos) -> None:  # noqa: F811
    """عدة أرقام مزود ⇒ تُحدَّد تلقائياً وتُستورد معاً، وكل خدمة تحمل رقمها لدى المزود الصحيح."""
    await load_user(bot, context, admin)
    state = await _start_import(bot, context, admin, mock_provider, "555 556")
    assert state == admin_providers.PICK_ITEM
    assert "المحدد: <b>2</b>" in bot.last.text

    await _finish_import(bot, context, admin, margin="40")
    report = " ".join(m.text or "" for m in bot.sent)
    assert "أُنشئت: <b>2</b>" in report

    by_psid = {s.provider_service_id: s for s in await repos.services.list_by_provider(mock_provider.id, limit=50, offset=0)}
    assert set(by_psid) == {"555", "556"}
    followers, likes = by_psid["555"], by_psid["556"]
    assert "Followers" in followers.name and "Likes" in likes.name
    assert followers.provider_id == likes.provider_id == mock_provider.id
    assert followers.price_per_1000_units == (followers.provider_price_per_1000_units * 140 + 50) // 100
    # التقرير يربط الرقم الداخلي برقم المزود
    assert f"<code>{followers.id}</code> ⇐ مزود <code>555</code>" in report
    assert f"<code>{likes.id}</code> ⇐ مزود <code>556</code>" in report
    # قاعدة الرابط استُنتجت للحساب والمنشور
    assert followers.link_rule == "instagram_profile" and likes.link_rule == "instagram_post"


async def test_batch_import_multi_select_with_toggle_and_skips_duplicates(bot, context, admin, mock_provider, mock_service, mock_client, repos) -> None:  # noqa: F811
    """اختيار متعدد بالأزرار: المكررة (555 موجودة) تُبلَّغ ولا تُنشأ، والجديدة تُنشأ."""
    await load_user(bot, context, admin)
    await _start_import(bot, context, admin, mock_provider, "*")
    assert "المحدد: <b>0</b>" in bot.last.text
    for index in (0, 1):
        await press(bot, context, admin_providers.pick_import_item, pack("pv", "pick", index), admin.telegram_id)
    assert "المحدد: <b>2</b>" in bot.last.text
    await press(bot, context, admin_providers.pick_import_item, pack("pv", "pick", 1), admin.telegram_id)  # إلغاء الثانية
    await press(bot, context, admin_providers.pick_import_item, pack("pv", "pick", 1), admin.telegram_id)  # وإعادتها
    await _finish_import(bot, context, admin)
    report = " ".join(m.text or "" for m in bot.sent)
    assert "أُنشئت: <b>1</b>" in report and "مكررة: <b>1</b>" in report
    assert len(await repos.services.list_by_provider(mock_provider.id, limit=50, offset=0)) == 2


async def test_batch_import_requires_selection_and_reports_missing_ids(bot, context, admin, mock_provider, mock_client) -> None:  # noqa: F811
    """«التالي» بلا تحديد يُرفض بتنبيه؛ وأرقام غير موجودة تُعرض بوضوح."""
    await load_user(bot, context, admin)
    await _start_import(bot, context, admin, mock_provider, "*")
    state = await press(bot, context, admin_providers.import_continue, pack("pv", "go"), admin.telegram_id)
    assert state == admin_providers.PICK_ITEM
    assert "حدّد خدمة واحدة" in bot.answers[-1]["text"]

    await _start_import(bot, context, admin, mock_provider, "555 99999")
    assert "99999" in bot.last.text and "غير موجودة" in bot.last.text
    assert "المحدد: <b>1</b>" in bot.last.text


async def test_batch_import_select_all_and_clear(bot, context, admin, mock_provider, mock_client) -> None:  # noqa: F811
    """تحديد الكل ثم مسح التحديد."""
    await load_user(bot, context, admin)
    await _start_import(bot, context, admin, mock_provider, "Instagram")
    await press(bot, context, admin_providers.import_results_nav, pack("pv", "all"), admin.telegram_id)
    assert "المحدد: <b>2</b>" in bot.last.text
    await press(bot, context, admin_providers.import_results_nav, pack("pv", "none"), admin.telegram_id)
    assert "المحدد: <b>0</b>" in bot.last.text


async def test_batch_import_service_layer_isolates_failures(admin, mock_provider, mock_client, services, repos) -> None:  # noqa: F811
    """عنصر معيب لا يُسقط الباقي؛ وتكرار الرقم داخل الدفعة يُتجاهل."""
    from dataclasses import replace

    items = await mock_client.get_services()
    bad = replace(items[1], provider_service_id="777", service_type="package")
    category = (await repos.categories.list_all())[0]
    report = await services.catalog.import_provider_services(
        admin, provider_id=mock_provider.id, items=[items[0], items[0], bad], category_id=category.id, margin_percent=10
    )
    assert [o.status for o in report.outcomes] == ["created", "failed"]
    assert report.failed[0].item.provider_service_id == "777"
    with pytest.raises(ValidationError):
        await services.catalog.import_provider_services(
            admin, provider_id=mock_provider.id, items=[], category_id=category.id, margin_percent=10
        )


async def test_parse_provider_ids() -> None:
    """أرقام بفواصل/مسافات/سطور/أرقام عربية؛ نص مختلط ⇒ ليس وضع أرقام."""
    assert admin_providers.parse_provider_ids("101 205,330\n١٠١") == ["101", "205", "330"]
    assert admin_providers.parse_provider_ids("instagram 101") == []
    assert admin_providers.parse_provider_ids("") == []


# ========================= الهامش وسعر الصرف (11) ========================= #


@pytest.mark.parametrize(("text", "expected"), [("40", 40), ("٤٠", 40), (" 0 ", 0), ("1000", 1000)])
async def test_margin_accepts_plain_numbers(text: str, expected: int) -> None:
    """الرقم وحده (40) مقبول، بما فيه الأرقام العربية."""
    assert parse_margin_percent(text) == expected


@pytest.mark.parametrize(
    ("text", "fragment"),
    [("40%", "بلا علامة %"), ("-5", "سالباً"), ("12.5", "بلا كسور"), ("abc", "بلا حروف"), ("1001", "بين 0 و1000"), ("", "رقم")],
)
async def test_margin_rejections_are_explicit(text: str, fragment: str) -> None:
    """كل حالة رفض لها رسالة واضحة فيها مثال."""
    with pytest.raises(ValidationError) as exc:
        parse_margin_percent(text)
    assert fragment in exc.value.user_message
    assert "40" in exc.value.user_message


async def test_margin_message_in_flow_has_example(bot, context, admin, mock_provider, mock_client) -> None:  # noqa: F811
    """داخل المحادثة: «40%» تُرفض وتبقى المحادثة بانتظار رقم صحيح."""
    await load_user(bot, context, admin)
    await _start_import(bot, context, admin, mock_provider, "555")
    await press(bot, context, admin_providers.import_continue, pack("pv", "go"), admin.telegram_id)
    category_button = next(b for b in bot.last.buttons if b.startswith("pv:cat:"))
    await press(bot, context, admin_providers.pick_import_category, category_button, admin.telegram_id)
    assert "بلا علامة %" in bot.last.text and "<code>40</code>" in bot.last.text
    await write(bot, context, admin_providers.receive_margin, "40%", admin.telegram_id)
    assert "بلا علامة %" in bot.last.text and bot.last.text.startswith("❌")


async def test_exchange_rate_input_messages(services) -> None:
    """سعر الصرف: 530 مقبول مع الرمز؛ بدون رمز/بحروف/بـ% يُرفض برسالة واضحة."""
    assert services.providers.parse_currency_spec("USD 530") == ("USD", "530")
    assert services.providers.parse_currency_spec("USD ٥٣٠") == ("USD", "530")
    for text, fragment in (("530", "رمز العملة قبل"), ("USD 530%", "بلا علامة %"), ("USD abc", "بلا حروف"), ("USD -5", "أكبر من صفر")):
        with pytest.raises(ValidationError) as exc:
            services.providers.parse_currency_spec(text)
        assert fragment in exc.value.user_message, text


async def test_usd_rate_setting_accepts_530_and_rejects_percent(services) -> None:
    """إعداد usd_rate: «530» يُقبل، و«530%» و«530$» يُرفضان."""
    await services.settings.set("usd_rate", "530", admin_id=None)
    assert str(await services.settings.usd_rate()) == "530"
    for bad in ("530%", "530$", "-1", "0"):
        with pytest.raises(ValidationError):
            await services.settings.set("usd_rate", bad, admin_id=None)


# ===================== بطاقة الأدمن وتعديل العرض (5/8) ===================== #


async def test_admin_card_shows_three_way_link_and_unset_fields(bot, context, admin, mock_service) -> None:  # noqa: F811
    """البطاقة: رقم الخدمة الداخلي ثم المزود ثم رقمها لديه، والدولار، و«غير محددة»."""
    await load_user(bot, context, admin)
    await press(bot, context, admin_catalog.service_card_screen, pack(NS_ADM_CAT, "svc", mock_service.id), admin.telegram_id)
    text = bot.last.text
    assert f"#{mock_service.id}" in text
    assert "MockProvider" in text and f"<code>#{mock_service.provider_id}</code>" in text
    assert "رقمها لدى المزود: <code>555</code>" in text
    assert "$" in text and text.count("غير محددة") == 3
    assert "بلا قيد" in text
    assert pack(NS_ADM_CAT, "edit", mock_service.id) in bot.last.buttons


async def test_admin_service_list_buttons_show_internal_id(bot, context, admin, mock_service) -> None:  # noqa: F811
    """قائمة خدمات التصنيف للأدمن تُظهر الرقم الداخلي."""
    await load_user(bot, context, admin)
    await press(bot, context, admin_catalog.category_services_screen, pack(NS_ADM_CAT, "cat", mock_service.category_id, 1), admin.telegram_id)
    assert any(f"#{mock_service.id} " in label for label in bot.last.labels)


async def test_edit_display_fields_and_rule_via_conversation(bot, context, admin, mock_service, repos) -> None:  # noqa: F811
    """تعديل السرعة نصاً، ثم مسحها بـ«-»، ثم ضبط قاعدة الرابط من القائمة."""
    await load_user(bot, context, admin)
    sid = mock_service.id
    await press(bot, context, admin_catalog.start_edit_display, pack(NS_ADM_CAT, "edit", sid), admin.telegram_id)
    state = await press(bot, context, admin_catalog.pick_edit_field, pack(NS_ADM_CAT, "fld", "speed"), admin.telegram_id)
    assert state == admin_catalog.EDIT_ASK_VALUE
    await write(bot, context, admin_catalog.receive_edit_value, "1000 في الساعة", admin.telegram_id)
    assert (await repos.services.get(sid)).speed_text == "1000 في الساعة"
    assert "1000 في الساعة" in bot.last.text

    await press(bot, context, admin_catalog.start_edit_display, pack(NS_ADM_CAT, "edit", sid), admin.telegram_id)
    await press(bot, context, admin_catalog.pick_edit_field, pack(NS_ADM_CAT, "fld", "speed"), admin.telegram_id)
    await write(bot, context, admin_catalog.receive_edit_value, "-", admin.telegram_id)
    assert (await repos.services.get(sid)).speed_text is None

    await press(bot, context, admin_catalog.start_edit_display, pack(NS_ADM_CAT, "edit", sid), admin.telegram_id)
    state = await press(bot, context, admin_catalog.pick_edit_field, pack(NS_ADM_CAT, "fld", "rule"), admin.telegram_id)
    assert state == admin_catalog.EDIT_PICK_RULE
    await press(bot, context, admin_catalog.pick_edit_rule, pack(NS_ADM_CAT, "rul", 1), admin.telegram_id)  # أول قاعدة
    assert (await repos.services.get(sid)).link_rule == "instagram_profile"
    assert "حساب انستغرام" in bot.last.text


async def test_edit_display_is_audited_and_permission_checked(admin, user, mock_service, services, repos) -> None:  # noqa: F811
    """كل تعديل يُسجَّل بقيمتي قبل/بعد؛ ومستخدم عادي مرفوض؛ وحقل غير مسموح مرفوض."""
    from core.exceptions import PermissionDeniedError

    await services.catalog.admin_set_display_field(admin, mock_service.id, "quality_text", "عالية")
    count = await services.db.fetchval(
        "SELECT COUNT(*) FROM audit_logs WHERE action='services.update' AND target_id=?", (str(mock_service.id),)
    )
    assert count == 1
    with pytest.raises(PermissionDeniedError):
        await services.catalog.admin_set_display_field(user, mock_service.id, "quality_text", "x")
    with pytest.raises(ValidationError):
        await services.catalog.admin_set_display_field(admin, mock_service.id, "price_per_1000_units", "1")
    with pytest.raises(ValidationError):
        await services.catalog.admin_set_display_field(admin, mock_service.id, "link_rule", "no_such_rule")


# ===================== الرابط في مسار الطلب (10) ===================== #


async def test_order_rejects_wrong_link_before_any_charge(user, mock_service, services, repos) -> None:  # noqa: F811
    """رابط منشور لخدمة «حساب» يُرفض قبل إنشاء الطلب والخصم؛ والصحيح يمر."""
    from core.money import to_units
    from decimal import Decimal

    async with services.db.transaction() as tx:
        await tx.execute("UPDATE services SET link_rule='instagram_profile' WHERE id=?", (mock_service.id,))
        await tx.execute("UPDATE users SET balance_units=? WHERE id=?", (to_units(Decimal("1000")), user.id))
    fresh = await services.users.get(user.id)
    before = fresh.balance_units

    for bad in ("https://instagram.com/p/AbCdEf123/", "https://tiktok.com/@someone", "https://example.com/x"):
        with pytest.raises(InvalidLinkError):
            await services.orders.create_order(fresh, service_id=mock_service.id, link=bad, quantity=1000)
    assert (await services.users.get(user.id)).balance_units == before
    assert await services.db.fetchval("SELECT COUNT(*) FROM orders") == 0

    order = await services.orders.create_order(
        fresh, service_id=mock_service.id, link="https://instagram.com/some.user", quantity=1000
    )
    assert order.id and (await services.users.get(user.id)).balance_units < before


async def test_order_flow_prompt_and_rejection_show_example(bot, context, user, mock_service, services) -> None:  # noqa: F811
    """رسالة طلب الرابط تعرض مثال القاعدة، وإدخال رابط خاطئ يعيد السؤال بمثال صحيح."""
    from handlers.user import order_flow

    async with services.db.transaction() as tx:
        await tx.execute("UPDATE services SET link_rule='instagram_post' WHERE id=?", (mock_service.id,))
    await load_user(bot, context, user)
    await press(bot, context, order_flow.start_order, pack("new", "start", mock_service.id), user.telegram_id)
    assert "https://instagram.com/p/AbCdEf123/" in bot.last.text and "منشور/ريلز انستغرام" in bot.last.text
    state = await write(bot, context, order_flow.receive_link, "https://instagram.com/username", user.telegram_id)
    assert state is None  # @guarded يعرض الخطأ ويُبقي المحادثة في حالتها (الانتظار لرابط)
    assert "❌" in bot.last.text and "https://instagram.com/p/AbCdEf123/" in bot.last.text
    state = await write(bot, context, order_flow.receive_link, "https://instagram.com/p/AbCdEf123/", user.telegram_id)
    assert state == order_flow.ASK_QUANTITY
