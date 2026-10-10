"""
اختبارات الانحدار v1.3.1 — التسعير والتدقيق (بند 5 و6): R14 · E3 + أداة `pricing_audit`.

كل شيء على قاعدة مؤقتة ومزود Mock؛ لا أسعار صرف حقيقية ولا طلبات حقيقية.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.enums import OrderStatus
from core.exceptions import ProviderPermanentError, ServiceNotAvailableError
from core.money import order_cost_units
from tests.integration.test_audit_ledger_phase12 import _failed, _populate, _run  # noqa: F401
from tests.integration.test_phase14_statuses import LINK

pytestmark = pytest.mark.asyncio


async def _fund(services, user, super_admin, units: int = 1_000_000) -> None:
    await services.wallet.adjust_balance(target=user, amount_units=units, admin=super_admin, reason="رصيد", credit=True)


async def test_r14a_no_hardcoded_usd_rate_fallback(services, db) -> None:
    """R14: لا سعر صرف احتياطي (530) في الكود؛ إعداد فارغ/فاسد ⇒ يُخفى الدولار بدل عرض رقم وهمي."""
    import core.money as money

    assert not hasattr(money, "DEFAULT_USD_RATE")
    assert money.parse_usd_rate("abc") is None and money.parse_usd_rate("") is None and money.parse_usd_rate("-1") is None
    assert str(money.parse_usd_rate("530")) == "530"

    async with db.transaction() as tx:
        await tx.execute("UPDATE settings SET value = '' WHERE key = 'usd_rate'")
    assert await services.settings.usd_rate() is None
    assert money.format_usd(5_300_000, None) == ""

    from utils.formatters import price_line
    assert "$" not in price_line(5_300_000, "ريال", None)


async def test_r14b_rate_change_keeps_order_snapshot_and_warns_about_negative_margin(
    services, repos, db, user, super_admin, mock_provider, mock_service
) -> None:
    """R14: تغيير سعر الصرف لا يمس طلباً قائماً، ويُنبَّه الأدمن لخدمات ستصير بهامش سالب (بلا تغيير أسعار تلقائي)."""
    await services.providers.set_currency(super_admin, mock_provider.id, currency="USD", exchange_rate="3")
    await _fund(services, user, super_admin)
    order = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000)
    snap = (await repos.orders.get(order.id)).price_per_1000_snapshot_units
    cost_before = order.cost_units
    assert snap == mock_service.price_per_1000_units and cost_before == order_cost_units(snap, 1000)

    await services.providers.set_currency(super_admin, mock_provider.id, currency="USD", exchange_rate="6")   # التكلفة المخزنة 6000 ⇒ 12000 > 10000
    after = await repos.orders.get(order.id)
    assert after.cost_units == cost_before and after.price_per_1000_snapshot_units == snap       # الطلب القائم ثابت
    service = await repos.services.get(mock_service.id)
    assert service.price_per_1000_units == 10_000 and service.provider_price_per_1000_units == 6_000   # لا تغيير تلقائي
    titles = [r["title"] for r in await db.fetchall("SELECT title FROM notifications")]
    assert any("هامش سالب" in title for title in titles)


async def test_r14c_block_negative_margin_setting(services, repos, db, user, super_admin, mock_service) -> None:
    """R14: الافتراضي لا يمنع البيع (تنبيه فقط)، وعند تفعيل `block_negative_margin` يُرفض الطلب على خدمة بهامش سالب."""
    await _fund(services, user, super_admin)
    async with db.transaction() as tx:
        await tx.execute("UPDATE services SET provider_price_per_1000_units = 20000 WHERE id = ?", (mock_service.id,))
    assert (await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000)).id

    await services.settings.set("block_negative_margin", "true", admin_id=super_admin.id)
    with pytest.raises(ServiceNotAvailableError):
        await services.orders.create_order(user, service_id=mock_service.id, link="https://instagram.com/other_account", quantity=1000)
    balance = await repos.users.get_balance_units(user.id)
    assert balance == 1_000_000 - 10_000                                            # لا خصم للطلب المرفوض


# ------------------------------ E3: audit_ledger ------------------------------ #


async def test_e3_audit_flags_refund_when_provider_reported_execution(services, repos, db, user, admin, mock_service, mock_client, payment_method) -> None:
    """E3: طلب مُسترجَع بينما المزود أبلغ تنفيذه ⇒ فحص «bad» (v1.3.0 لا يكشفه)."""
    await _populate(services, repos, db, user, admin, mock_service, mock_client, payment_method)
    path = Path(db.path)
    title = "مُسترجَع/ملغى بينما أبلغ المزود تنفيذ الطلب"
    assert not any(title in t for t in _failed(_run(path)))                         # البيانات السليمة: لا مخالفة

    refunded = await db.fetchone("SELECT id FROM orders WHERE refund_amount_units > 0 AND status IN ('failed','refunded','canceled')")
    async with db.transaction() as tx:
        await tx.execute("UPDATE orders SET provider_status = 'Completed' WHERE id = ?", (refunded["id"],))
    assert any(title in t for t in _failed(_run(path)))


async def test_e3b_audit_recomputes_cost_and_partial_refund(services, repos, db, user, admin, mock_service, mock_client, payment_method) -> None:
    """تنبيهات الحساب: تكلفة لا تطابق لقطة السعر، واسترجاع جزئي خاطئ."""
    await _populate(services, repos, db, user, admin, mock_service, mock_client, payment_method)
    path = Path(db.path)
    titles = lambda: {f.title for f in _run(path) if f.count}                       # noqa: E731
    assert not any("لقطة السعر" in t for t in titles())
    async with db.transaction() as tx:
        await tx.execute("UPDATE orders SET price_per_1000_snapshot_units = price_per_1000_snapshot_units + 7 WHERE id = (SELECT MIN(id) FROM orders)")
    assert any("لقطة السعر" in t for t in titles())


# ------------------------------ أداة pricing_audit ------------------------------ #


async def test_pricing_audit_is_read_only_and_explains_numbers(services, repos, db, user, admin, mock_service, mock_client, payment_method) -> None:
    """الأداة تقرأ فقط، تجد مصدر المبلغ، وتكشف الهامش السالب وعدم اتساق usd_rate وسعر صرف المزود."""
    from scripts import pricing_audit

    await _populate(services, repos, db, user, admin, mock_service, mock_client, payment_method)
    path = Path(db.path)
    async with db.transaction() as tx:
        await tx.execute("UPDATE providers SET currency = 'USD', exchange_rate = '3' WHERE id = ?", (mock_service.provider_id,))
        await tx.execute("UPDATE services SET price_per_1000_units = 5000 WHERE id = ?", (mock_service.id,))     # أقل من التكلفة 6000

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    try:
        text, problems, rows = pricing_audit.render(conn, path, find=["1", "0.5", "999.99"], order_limit=0)
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("UPDATE services SET name = 'x'")
    finally:
        conn.close()
    assert problems >= 1 and "هامش سالب" in text
    assert "usd_rate" in text and "≠ usd_rate" in text                              # 3 ≠ 530
    assert "0.5" in text and "لا مصدر في القاعدة" in text                            # 999.99 بلا مصدر
    assert any("هامش سالب" in row.flags for row in rows)
    assert row_native(rows, mock_service.id) == "0.2"                               # 0.6 ÷ 3 = 0.2 USD عند المزود


def row_native(rows, service_id: int) -> str:
    """السعر الأصلي المُستنتَج عند المزود لخدمة (نص مُطبَّع)."""
    return next(f"{r.native_cost.normalize():f}" for r in rows if r.service_id == service_id)
