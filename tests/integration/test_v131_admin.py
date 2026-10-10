"""
اختبارات v1.3.1 — لوحة التحكم (بند 0) وخريطة المزودين وربط رقم المزود (بند 8 و11): E4 · WP10 · E7.

كل شيء Mock (FakeBot + مزود Mock أو نقل httpx وهمي).
"""

from __future__ import annotations

import httpx
import pytest

from core.enums import OrderStatus
from core.exceptions import PermissionDeniedError
from integrations.providers import registry
from integrations.providers.perfect_panel import PerfectPanelClient
from keyboards.callback_data import pack
from tests.admin_ui_samples import capture_admin_screens
from tests.integration.test_phase14_statuses import LINK, FakePanel, panel  # noqa: F401
from tests.integration.test_user_interface import bot, context, load_user, press  # noqa: F401
from tests.layout_rules import layout_violations

pytestmark = pytest.mark.asyncio


async def _funded_order(services, user, super_admin, service):
    await services.wallet.adjust_balance(target=user, amount_units=1_000_000, admin=super_admin, reason="رصيد", credit=True)
    return await services.orders.create_order(user, service_id=service.id, link=LINK, quantity=1000)


# ------------------------------------ E4 ------------------------------------ #


async def test_e4_admin_screens_follow_layout_rules(services, repos, super_admin, user, mock_provider, mock_service, bot, context) -> None:
    """E4: كل لوحة أدمن: ≤3 أزرار بالصف، بلا رمز إنجليزي خام، ولا callback مكرر/طويل؛ والنص بلا مسافات بادئة."""
    order = await _funded_order(services, user, super_admin, mock_service)
    await load_user(bot, context, super_admin)
    shots = await capture_admin_screens(bot, context, admin=super_admin, order=order, provider=mock_provider, service=mock_service, target_user=user)
    assert len(shots) >= 20, f"شاشات قليلة الالتقاط: {sorted(shots)}"
    problems = {}
    for name, message in shots.items():
        found = layout_violations(message.markup.inline_keyboard if message.markup else [])
        found += [f"سطر بمسافة بادئة: «{line[:30]}»" for line in message.text.split("\n") if line.startswith("  ")]
        if found:
            problems[name] = found
    assert not problems, problems


async def test_e4b_settings_groups_have_arabic_names_and_two_per_row(services, repos, super_admin, bot, context) -> None:
    """مجموعات الإعدادات بأسماء عربية (لا «⚙️ backup»)."""
    from handlers.admin import settings as admin_settings
    await load_user(bot, context, super_admin)
    await press(bot, context, admin_settings.settings_home_screen, pack("as", "home"), super_admin.telegram_id)
    labels = [label for label in bot.last.labels if label not in ("🛠 لوحة التحكم", "🏠 القائمة الرئيسية") and "صيانة" not in label]
    assert labels and not any(label.split(" ", 1)[-1].isascii() for label in labels)
    assert all(len(row) <= 2 for row in bot.last.markup.inline_keyboard[:-2])


async def test_tidy_text_strips_leading_spaces_keeps_pre() -> None:
    """التنسيق المركزي: لا مسافات بادئة، والسطر الذي يبدأ برمز يبقى كما هو، و`<pre>` لا يُمسّ."""
    from utils.formatters import tidy_text
    assert tidy_text("العنوان\n   اليوم: 3\n   🚫 محظور: 1") == "العنوان\n• اليوم: 3\n🚫 محظور: 1"
    assert tidy_text("<pre>  كود\n    متداخل</pre>") == "<pre>  كود\n    متداخل</pre>"
    assert tidy_text("سطر واحد") == "سطر واحد"


# ------------------------------- خريطة المزودين ------------------------------- #


async def test_provider_map_warns_when_active_services_point_to_unusable_provider(
    services, repos, db, super_admin, user, mock_provider, mock_service, bot, context
) -> None:
    """خريطة المزودين: مزود غير جاهز وله خدمات وطلبات مفتوحة ⇒ تحذير؛ والقراءة بلا أي تغيير؛ والصلاحية مطلوبة."""
    order = await _funded_order(services, user, super_admin, mock_service)
    rows = await services.providers.provider_map(super_admin)
    row = next(r for r in rows if r.provider.id == mock_provider.id)
    assert row.usable and row.active_services == 1 and row.open_orders == 1

    async with db.transaction() as tx:                       # عملة مختلفة بلا سعر صرف ⇒ غير جاهز
        await tx.execute("UPDATE providers SET currency = 'USD', exchange_rate = NULL WHERE id = ?", (mock_provider.id,))
    row = next(r for r in await services.providers.provider_map(super_admin) if r.provider.id == mock_provider.id)
    assert not row.usable and any("غير جاهز" in w for w in row.warnings) and any("طلب مفتوح" in w for w in row.warnings)

    await load_user(bot, context, super_admin)
    from handlers.admin import providers as admin_providers
    await press(bot, context, admin_providers.providers_map_screen, pack("pv", "map"), super_admin.telegram_id)
    assert "خريطة المزودين" in bot.last.text and "غير جاهز" in bot.last.text and "ORD" not in bot.last.text
    assert (await repos.orders.get(order.id)).status == OrderStatus.PENDING             # لم تتغير أي حالة
    with pytest.raises(PermissionDeniedError):
        await services.providers.provider_map(user)


async def test_provider_map_flags_usd_rate_mismatch(services, db, super_admin, mock_provider, mock_service) -> None:
    """usd_rate للعرض لا يطابق سعر صرف مزود بالدولار ⇒ تحذير اتساق (بلا تغيير أسعار)."""
    async with db.transaction() as tx:
        await tx.execute("UPDATE providers SET currency = 'USD', exchange_rate = '3' WHERE id = ?", (mock_provider.id,))
    row = next(r for r in await services.providers.provider_map(super_admin) if r.provider.id == mock_provider.id)
    assert any("usd_rate" in w for w in row.warnings)


# ------------------------------ ربط رقم المزود ------------------------------ #


async def test_link_probe_tells_admin_what_provider_says_without_changing_anything(
    services, repos, super_admin, user, mock_provider, mock_service, mock_client
) -> None:
    """معاينة الربط: رقم صحيح ⇒ حالة المزود، رقم مجهول ⇒ تحذير؛ ولا تغيير في الطلب."""
    order = await _funded_order(services, user, super_admin, mock_service)
    await services.orders.process_pending_orders(limit=5)
    placed = await repos.orders.get(order.id)
    assert "المزود يردّ" in await services.orders.probe_provider_link(super_admin, order.id, placed.provider_order_id)
    assert "لم يتعرف" in await services.orders.probe_provider_link(super_admin, order.id, "no-such-id")
    assert (await repos.orders.get(order.id)).status == placed.status
    with pytest.raises(PermissionDeniedError):
        await services.orders.probe_provider_link(user, order.id, "1")


# ------------------------------------ E7 ------------------------------------ #


async def test_e7_add_timeout_marks_uncertain_and_never_resends(services, repos, super_admin, user, mock_service) -> None:
    """E7: مهلة `add` ⇒ submit_uncertain، وإعادة جولات الإرسال لا ترسل `add` ثانية (قد يكون المزود نفّذ)."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = dict(pair.split("=", 1) for pair in request.content.decode().split("&"))
        calls.append(body.get("action", ""))
        raise httpx.ReadTimeout("timeout", request=request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    original = dict(registry._REGISTRY)
    registry.enable_dev_types(True)
    registry.register_client("mock", lambda **kw: PerfectPanelClient(api_url=kw["api_url"], api_key=kw["api_key"], client=http))
    try:
        order = await _funded_order(services, user, super_admin, mock_service)
        for _ in range(3):
            await services.orders.process_pending_orders(limit=5)
    finally:
        registry._REGISTRY.clear()
        registry._REGISTRY.update(original)
    assert (await repos.orders.get(order.id)).status == OrderStatus.SUBMIT_UNCERTAIN
    assert calls.count("add") == 1, f"أُرسل add {calls.count('add')} مرات"
    assert (await repos.orders.get(order.id)).refund_amount_units == 0                 # لا استرجاع تلقائي بسبب مهلة
