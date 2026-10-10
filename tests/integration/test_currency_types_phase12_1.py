"""
المرحلة 12.1 — العملة وأنواع الخدمات وتكرار الاستيراد:

    P0-5  سعر صرف لكل مزود: التحويل مرة واحدة عند حدود المزود، ورفض واضح عند اختلاف العملة بلا سعر.
    P0-6  الأنواع غير default مرفوضة في الاستيراد وتُعطَّل عند المزامنة.
    #7    استيراد نفس خدمة المزود مرتين (سباق) ينتج واحدة فقط.
"""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import replace

import pytest

from core.enums import OrderStatus
from core.exceptions import DuplicateOperationError, ProviderError, ServiceNotAvailableError, ValidationError
from database.models import Provider, Service, User
from integrations.providers.base import ProviderServiceItem, normalize_service_type
from services import ServiceContainer

pytestmark = pytest.mark.asyncio

RATE = "530"


async def _set_currency(repos, provider: Provider, currency: str, rate: str | None) -> Provider:
    """ضبط عملة مزود مباشرة في القاعدة (يتجاوز الخدمة لتجهيز الحالة)."""
    async with repos.db.transaction() as tx:
        await repos.providers.update_fields(tx, provider.id, currency=currency, exchange_rate=rate)
    refreshed = await repos.providers.get(provider.id)
    assert refreshed is not None
    return refreshed


async def _row(repos, service_id: int):
    """قراءة صف خدمة خاماً (بما فيها المعطَّلة)."""
    return await repos.db.fetchone("SELECT * FROM services WHERE id = ?", (service_id,))


def _item(pid: str, *, rate: int = 5_000, service_type: str = "default") -> ProviderServiceItem:
    """عنصر خدمة مزود للاختبار."""
    return ProviderServiceItem(
        provider_service_id=pid, name=f"خدمة اختبار {pid}", rate_per_1000_units=rate,
        min_quantity=10, max_quantity=1000, category="Test", service_type=service_type,
    )


# --------------------------------- العملة --------------------------------- #


async def test_currency_mismatch_without_rate_blocks_provider(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service, mock_provider: Provider, mock_client
) -> None:
    """مزود بـUSD والنظام YER بلا سعر: غير جاهز، لا طلبات جديدة، ولا جلب خدمات، ولا إرسال."""
    await services.wallet.adjust_balance(target=user, amount_units=100_000, admin=admin, reason="رصيد", credit=True)
    provider = await _set_currency(repos, mock_provider, "USD", None)

    health = await services.providers.health(provider)
    assert not health.is_usable and "USD" in health.reason and "YER" in health.reason

    with pytest.raises(ServiceNotAvailableError):
        await services.orders.create_order(user, service_id=mock_service.id, link="https://instagram.com/x", quantity=1000)
    with pytest.raises(ProviderError) as info:
        await services.providers.fetch_services(admin, provider)
    assert "سعر الصرف" in info.value.user_message
    assert not mock_client.calls, "لا اتصال بالمزود قبل التحقق من العملة"


async def test_order_placed_before_misconfiguration_is_never_sent_with_wrong_currency(
    services: ServiceContainer, repos, user: User, admin: User, mock_service: Service, mock_provider: Provider, mock_client
) -> None:
    """طلب أُنشئ ثم تغيّرت عملة المزود بلا سعر: يبقى منتظراً ولا يُرسل ولا يُعاد إرساله بقيمة خاطئة."""
    await services.wallet.adjust_balance(target=user, amount_units=100_000, admin=admin, reason="رصيد", credit=True)
    order = await services.orders.create_order(user, service_id=mock_service.id, link="https://instagram.com/x", quantity=1000)
    await _set_currency(repos, mock_provider, "USD", None)

    await services.orders.process_pending_orders()
    current = await repos.orders.get(order.id)
    assert current.status == OrderStatus.PENDING
    assert not [call for call in mock_client.calls if call[0] == "add"], "أُرسل الطلب رغم غياب سعر الصرف"


async def test_exchange_rate_converts_service_prices_and_provider_cost(
    services: ServiceContainer, repos, user: User, admin: User, super_admin: User, mock_provider: Provider, mock_client
) -> None:
    """سعر صرف 530: أسعار الاستيراد وتكلفة المزود الفعلية تُحوَّل مرة واحدة إلى عملة النظام."""
    mock_client.rate_per_1000_units = 6_000                     # 0.6 USD لكل ألف عند المزود
    mock_client.currency = "USD"
    provider = await services.providers.set_currency(super_admin, mock_provider.id, currency="usd", exchange_rate=RATE)
    assert provider.currency == "USD" and provider.exchange_rate == RATE

    items = await services.providers.fetch_services(super_admin, provider)
    assert items[0].rate_per_1000_units == 6_000 * 530 and items[0].currency == "YER"

    category = (await repos.categories.list_all())[0]
    service = await services.catalog.import_provider_service(
        super_admin, provider_id=provider.id, item=items[0], category_id=category.id, margin_percent=20
    )
    assert service.provider_price_per_1000_units == 3_180_000
    assert service.price_per_1000_units == 3_816_000            # +20% على التكلفة بعملة النظام

    await services.wallet.adjust_balance(target=user, amount_units=50_000_000, admin=admin, reason="رصيد", credit=True)
    order = await services.orders.create_order(user, service_id=service.id, link="https://instagram.com/x", quantity=1000)
    await services.orders.process_pending_orders()
    sent = await repos.orders.get(order.id)
    assert sent.status == OrderStatus.SUBMITTED
    assert sent.provider_cost_units == 6_000 * 530, "charge المزود (USD) يجب أن يُحوَّل إلى YER"


async def test_same_currency_needs_no_rate_and_balance_alert_uses_equivalent(
    services: ServiceContainer, repos, admin: User, super_admin: User, mock_provider: Provider, mock_client
) -> None:
    """تنبيه الرصيد المنخفض يقارن مكافئ الرصيد بعملة النظام لا الرقم الخام."""
    await services.settings.set("provider_low_balance_alert_units", 1_000_000, admin_id=super_admin.id)   # 100 YER
    mock_client.currency = "USD"
    provider = await services.providers.set_currency(super_admin, mock_provider.id, currency="USD", exchange_rate=RATE)

    mock_client.balance_units = 1_000 * 10_000                  # 1000 USD ≈ 530,000 YER ⇒ لا تنبيه
    await services.providers.check_balance(provider)
    low = await repos.db.fetchall("SELECT 1 FROM notifications WHERE dedupe_key LIKE 'manual:provider:%:low:%'")
    assert not low

    mock_client.balance_units = 1_000                           # 0.1 USD ≈ 53 YER ⇒ تنبيه
    await services.providers.check_balance(provider)
    low = await repos.db.fetchall("SELECT 1 FROM notifications WHERE dedupe_key LIKE 'manual:provider:%:low:%'")
    assert low
    stored = await repos.providers.get(provider.id)
    assert stored.balance_units == 1_000 and stored.currency == "USD", "العملة المسجّلة لا تتغير من استجابة API"


async def test_api_reported_currency_mismatch_is_flagged_not_overwritten(
    services: ServiceContainer, repos, admin: User, super_admin: User, mock_provider: Provider, mock_client
) -> None:
    """المزود يُبلّغ بعملة غير المسجّلة: تنبيه للأدمن وتبقى العملة المسجّلة كما هي."""
    mock_client.currency = "EUR"
    await services.providers.check_balance(mock_provider)
    stored = await repos.providers.get(mock_provider.id)
    assert stored.currency == "YER"
    rows = await repos.db.fetchall("SELECT 1 FROM notifications WHERE dedupe_key LIKE 'manual:provider:%:currency:EUR:%'")
    assert rows


async def test_set_currency_validation_and_audit(
    services: ServiceContainer, repos, admin: User, super_admin: User, mock_provider: Provider
) -> None:
    """عملة مختلفة بلا سعر مرفوضة، السعر يُطبَّع، والتغيير يُدقَّق."""
    with pytest.raises(ValidationError):
        await services.providers.set_currency(super_admin, mock_provider.id, currency="USD", exchange_rate=None)
    for bad in ("0", "-1", "abc", "NaN"):
        with pytest.raises(ValidationError):
            await services.providers.set_currency(super_admin, mock_provider.id, currency="USD", exchange_rate=bad)
    updated = await services.providers.set_currency(super_admin, mock_provider.id, currency="USD", exchange_rate="530.50")
    assert updated.exchange_rate == "530.5"
    back = await services.providers.set_currency(super_admin, mock_provider.id, currency="YER", exchange_rate=None)
    assert back.exchange_rate is None
    audit = await repos.audit.list_recent(limit=10)
    assert sum(1 for entry in audit if entry.action == "providers.set_currency") == 2


async def test_create_provider_defaults_to_system_currency_and_requires_rate_otherwise(
    services: ServiceContainer, super_admin: User
) -> None:
    """إنشاء مزود: بلا عملة ⇒ عملة النظام؛ عملة مختلفة بلا سعر ⇒ رفض."""
    created = await services.providers.create_provider(
        super_admin, name="P1", api_url="https://panel.example.com/api/v2", api_key="abcdefgh12345", api_type="mock"
    )
    assert created.currency == "YER" and created.exchange_rate is None
    with pytest.raises(ValidationError):
        await services.providers.create_provider(
            super_admin, name="P2", api_url="https://panel2.example.com/api/v2", api_key="abcdefgh12345",
            api_type="mock", currency="USD",
        )
    with_rate = await services.providers.create_provider(
        super_admin, name="P3", api_url="https://panel3.example.com/api/v2", api_key="abcdefgh12345",
        api_type="mock", currency="usd", exchange_rate="530",
    )
    assert (with_rate.currency, with_rate.exchange_rate) == ("USD", "530")


def test_parse_currency_spec() -> None:
    """تحليل «العملة [السعر]»."""
    from services.provider_service import ProviderService

    parse = ProviderService.parse_currency_spec
    assert parse("usd 530") == ("USD", "530")
    assert parse("YER") == ("YER", None)
    assert parse("SAR ٣٫٧٥".replace("٫", ".")) == ("SAR", "3.75")
    for bad in ("", "USD 1 2", "ريال 5", "U 5", "USD abc"):
        with pytest.raises(ValidationError):
            parse(bad)


def test_to_system_units_rounds_half_up_with_decimal() -> None:
    """التحويل Decimal بتقريب نصف لأعلى (لا float)."""
    from decimal import Decimal

    from services.provider_service import ProviderService

    assert ProviderService.to_system_units(1, Decimal("0.5")) == 1          # 0.5 ⇒ 1
    assert ProviderService.to_system_units(3, Decimal("0.5")) == 2          # 1.5 ⇒ 2
    assert ProviderService.to_system_units(10_000, Decimal("530.5")) == 5_305_000
    assert ProviderService.to_system_units(0, Decimal("530")) == 0


# ------------------------------- أنواع الخدمات ------------------------------- #


def test_service_type_is_normalized() -> None:
    """«Custom Comments» ⇒ custom_comments و«Default» ⇒ default."""
    assert normalize_service_type("Custom Comments") == "custom_comments"
    assert normalize_service_type("Default") == "default"
    assert normalize_service_type("") == "default" and normalize_service_type(None) == "default"
    assert normalize_service_type("Mentions-Hashtag") == "mentions_hashtag"


async def test_unsupported_types_are_rejected_on_import(
    services: ServiceContainer, repos, super_admin: User, mock_provider: Provider
) -> None:
    """الاستيراد يرفض الأنواع غير default برسالة واضحة، ويقبل default."""
    category = (await repos.categories.list_all())[0]
    for service_type in ("package", "custom_comments", "subscriptions"):
        with pytest.raises(ValidationError) as info:
            await services.catalog.import_provider_service(
                super_admin, provider_id=mock_provider.id, item=_item("900", service_type=service_type),
                category_id=category.id, margin_percent=10,
            )
        assert "غير مدعوم" in info.value.user_message
    assert await repos.services.find_by_provider_service(mock_provider.id, "900") is None

    ok = await services.catalog.import_provider_service(
        super_admin, provider_id=mock_provider.id, item=_item("901"), category_id=category.id, margin_percent=10
    )
    assert ok.service_type == "default"


async def test_sync_disables_service_whose_type_became_unsupported(
    services: ServiceContainer, repos, super_admin: User, mock_provider: Provider
) -> None:
    """المزامنة: خدمة مستوردة صار نوعها package ⇒ تُعطَّل وتُذكر في التقرير، وسعرها لا يتغير."""
    category = (await repos.categories.list_all())[0]
    keep = await services.catalog.import_provider_service(
        super_admin, provider_id=mock_provider.id, item=_item("1"), category_id=category.id, margin_percent=10
    )
    drift = await services.catalog.import_provider_service(
        super_admin, provider_id=mock_provider.id, item=_item("2"), category_id=category.id, margin_percent=10
    )
    report = await services.catalog.sync_provider_services(
        super_admin, provider_id=mock_provider.id,
        items=[_item("1"), replace(_item("2", rate=9_000), service_type="package")],
    )
    assert [service.id for service in report.unsupported] == [drift.id]
    assert (await _row(repos, drift.id))["is_active"] == 0
    assert (await _row(repos, keep.id))["is_active"] == 1
    assert (await _row(repos, drift.id))["provider_price_per_1000_units"] == 5_000

    again = await services.catalog.sync_provider_services(
        super_admin, provider_id=mock_provider.id, items=[_item("1"), _item("2", service_type="package")]
    )
    assert again.unsupported == [], "المعطَّلة مسبقاً لا تُكرَّر في كل مزامنة"


# --------------------------- تكرار الاستيراد (سباق) --------------------------- #


async def test_concurrent_import_creates_one_service_only(
    services: ServiceContainer, repos, super_admin: User, mock_provider: Provider
) -> None:
    """ضغطتا استيراد متزامنتان لنفس الخدمة: واحدة تنجح والأخرى DuplicateOperationError."""
    category = (await repos.categories.list_all())[0]

    async def attempt():
        return await services.catalog.import_provider_service(
            super_admin, provider_id=mock_provider.id, item=_item("777"), category_id=category.id, margin_percent=10
        )

    results = await asyncio.gather(*(attempt() for _ in range(4)), return_exceptions=True)
    assert sum(isinstance(r, Service) for r in results) == 1
    assert sum(isinstance(r, DuplicateOperationError) for r in results) == 3
    count = await repos.db.fetchval(
        "SELECT COUNT(*) FROM services WHERE provider_id = ? AND provider_service_id = '777'", (mock_provider.id,)
    )
    assert count == 1


async def test_unique_index_blocks_duplicates_at_database_level(
    repos, mock_provider: Provider, mock_service: Service
) -> None:
    """حتى لو تجاوز الكود الفحص، القيد الفريد يمنع تكرار (المزود، خدمة المزود)."""
    with pytest.raises(sqlite3.IntegrityError):
        async with repos.db.transaction() as tx:
            await repos.services.create(
                tx, category_id=mock_service.category_id, provider_id=mock_provider.id,
                provider_service_id=mock_service.provider_service_id, name="نسخة مكررة",
                price_per_1000_units=1, min_quantity=1, max_quantity=10,
            )


async def test_migration_0010_schema(repos) -> None:
    """الترحيل 0010: عمود exchange_rate موجود والإعداد الميت محذوف."""
    columns = {row["name"] for row in await repos.db.fetchall("PRAGMA table_info(providers)")}
    assert "exchange_rate" in columns
    keys = {row["key"] for row in await repos.db.fetchall("SELECT key FROM settings")}
    assert "provider_exchange_rate" not in keys


# ------------------------------ سباق الإعدادات (#8) ------------------------------ #


async def test_concurrent_min_max_deposit_updates_cannot_cross(
    services: ServiceContainer, repos, super_admin: User
) -> None:
    """رفع الأدنى وخفض الأعلى متزامنين: لا يُسمح بالنتيجة أدنى > أعلى."""
    await services.settings.set("min_deposit_units", 100_000, admin_id=super_admin.id)
    await services.settings.set("max_deposit_units", 1_000_000, admin_id=super_admin.id)

    results = await asyncio.gather(
        services.settings.set("min_deposit_units", 900_000, admin_id=super_admin.id),
        services.settings.set("max_deposit_units", 500_000, admin_id=super_admin.id),
        return_exceptions=True,
    )
    assert sum(isinstance(r, ValidationError) for r in results) == 1, "أحد التعديلين يجب أن يُرفض"
    low = int((await repos.settings.get("min_deposit_units")).value)
    high = int((await repos.settings.get("max_deposit_units")).value)
    assert low <= high


# --------------------------- حدود طريقة الدفع عند الإنشاء (#9) --------------------------- #


async def test_create_payment_method_rejects_inverted_limits(services: ServiceContainer, repos, super_admin: User) -> None:
    """إنشاء طريقة بأدنى > أقصى مرفوض ولا تُنشأ أي صف."""
    with pytest.raises(ValidationError):
        await services.payments.create_method(
            super_admin, name_ar="طريقة معكوسة", min_amount_units=900_000, max_amount_units=100_000
        )
    assert await repos.db.fetchval("SELECT COUNT(*) FROM payment_methods WHERE name_ar = 'طريقة معكوسة'") == 0
    ok = await services.payments.create_method(
        super_admin, name_ar="طريقة سليمة", min_amount_units=100_000, max_amount_units=900_000
    )
    assert ok.min_amount_units == 100_000
