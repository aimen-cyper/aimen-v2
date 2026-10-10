"""
اختبارات قسم «🔌 المزودون» في لوحة التحكم (المرحلة 5).

النقاط المحروسة:
    • قائمة المزودين وبطاقة المزود تُعرضان بلا كشف المفتاح (hint فقط).
    • اختبار الاتصال وتحديث الرصيد يمرّان عبر خدمة المزودين لا عبر HTTP مباشر.
    • إيقاف/تفعيل مزود يُحفظ في القاعدة ويُسجَّل في سجل التدقيق.
    • إضافة مزود: المفتاح لا يُطبع في أي رسالة، ويُحفظ مشفّراً بـhint فقط.
    • تغيير المفتاح محجوب عن `admin` ومسموح لـ`super_admin` (صلاحية قاعدة بيانات).
    • المزامنة تحدّث التكلفة والحدود ولا تمسّ سعر البيع ولا تحذف خدمة.
    • الاستيراد ينشئ خدمة بسعر = التكلفة + الهامش، ويمنع تكرار نفس خدمة المزود.
    • إنشاء خدمة يدوياً من الكتالوج يمرّ بالتصنيف والمزود ويُنشئ خدمة حقيقية.
"""

from __future__ import annotations

import pytest
from telegram.ext import ConversationHandler

from database.models import Provider, User
from database.repositories import Repositories
from handlers.admin import catalog, providers as admin_providers
from integrations.providers.mock import MockProviderClient
from keyboards.callback_data import pack
from services import ServiceContainer
from tests.integration.test_user_interface import (
    bot,  # noqa: F401
    context,  # noqa: F401
    load_user,
    press,
    write,
)
from tests.telegram_fakes import FakeBot, FakeContext

pytestmark = pytest.mark.asyncio


# ======================================================================== #
#                            الشاشات (قراءة)                               #
# ======================================================================== #


async def test_providers_home_lists_providers(
    bot: FakeBot, context: FakeContext, admin: User, mock_provider: Provider
) -> None:
    """شاشة المزودين تعرض المزودين المسجّلين وزراً لكل واحد."""
    await load_user(bot, context, admin)
    await press(
        bot, context, admin_providers.providers_home_screen, pack("pv", "home"), admin.telegram_id
    )

    assert f"pv:view:{mock_provider.id}" in " ".join(bot.last.buttons)
    assert "المزودون" in bot.last.text or "مزود" in bot.last.text


async def test_provider_card_never_shows_full_key(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    mock_provider: Provider,
    repos: Repositories,
) -> None:
    """بطاقة المزود تعرض آخر 4 محارف فقط — لا المفتاح ولا نسخته المشفّرة."""
    await load_user(bot, context, admin)
    await press(
        bot,
        context,
        admin_providers.provider_card_screen,
        pack("pv", "view", mock_provider.id),
        admin.telegram_id,
    )

    text = bot.last.text
    assert mock_provider.name in text
    assert "mock-key-123456" not in text                      # المفتاح الخام
    assert mock_provider.api_key_enc not in text              # ولا النسخة المشفّرة
    assert "3456" in text                                     # الـhint فقط


async def test_provider_services_screen_lists_linked_services(
    bot: FakeBot, context: FakeContext, admin: User, mock_provider: Provider, mock_service
) -> None:
    """شاشة «خدماتنا من هذا المزود» تعرض الخدمات المرتبطة به فقط."""
    await load_user(bot, context, admin)
    await press(
        bot,
        context,
        admin_providers.provider_services_screen,
        pack("pv", "svcs", mock_provider.id, 1),
        admin.telegram_id,
    )

    assert mock_service.name[:20] in bot.last.text or any(
        button.startswith("ac:svc:") for button in bot.last.buttons
    )


# ======================================================================== #
#                       إجراءات: اختبار/رصيد/تفعيل                         #
# ======================================================================== #


async def test_test_connection_reports_success(
    bot: FakeBot,
    context: FakeContext,
    super_admin: User,
    mock_provider: Provider,
    mock_client: MockProviderClient,
) -> None:
    """زر «اختبار الاتصال» ينجح مع مزود سليم ويذكر الرصيد دون أي سر."""
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        admin_providers.test_provider,
        pack("pv", "test", mock_provider.id),
        super_admin.telegram_id,
    )

    texts = " ".join(message.text or "" for message in bot.sent)
    assert "✅" in texts
    assert "mock-key-123456" not in texts


async def test_refresh_balance_saves_snapshot(
    bot: FakeBot,
    context: FakeContext,
    super_admin: User,
    mock_provider: Provider,
    mock_client: MockProviderClient,
    repos: Repositories,
) -> None:
    """تحديث الرصيد يحفظ القيمة في صف المزود (لا يكتفي بعرضها)."""
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        admin_providers.refresh_balance,
        pack("pv", "bal", mock_provider.id),
        super_admin.telegram_id,
    )

    refreshed = await repos.providers.get(mock_provider.id)
    assert refreshed.balance_units == mock_client.balance_units
    assert refreshed.balance_checked_at is not None


async def test_toggle_provider_persists_and_audits(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    mock_provider: Provider,
    repos: Repositories,
    services: ServiceContainer,
) -> None:
    """إيقاف مزود يُحفظ في القاعدة ويترك أثراً في سجل التدقيق."""
    await load_user(bot, context, admin)
    await press(
        bot,
        context,
        admin_providers.toggle_provider,
        pack("pv", "toggle", mock_provider.id),
        admin.telegram_id,
    )

    refreshed = await repos.providers.get(mock_provider.id)
    assert not refreshed.is_active

    entries = await services.audit.recent(limit=20)
    assert any("provider" in (entry.action or "") for entry in entries)


async def test_toggle_provider_blocked_without_permission(
    bot: FakeBot,
    context: FakeContext,
    user: User,
    mock_provider: Provider,
    repos: Repositories,
) -> None:
    """مستخدم عادي لا يستطيع إيقاف مزود — الحالة لا تتغير."""
    await load_user(bot, context, user)
    await press(
        bot,
        context,
        admin_providers.toggle_provider,
        pack("pv", "toggle", mock_provider.id),
        user.telegram_id,
    )

    unchanged = await repos.providers.get(mock_provider.id)
    assert unchanged.is_active


# ======================================================================== #
#                        محادثة: إضافة مزود جديد                           #
# ======================================================================== #


async def test_add_provider_flow_encrypts_key(
    bot: FakeBot,
    context: FakeContext,
    super_admin: User,
    repos: Repositories,
    mock_client: MockProviderClient,
) -> None:
    """الدورة الكاملة لإضافة مزود: المفتاح يُحفظ مشفّراً ولا يظهر في أي رسالة."""
    await load_user(bot, context, super_admin)
    secret = "super-secret-key-9876"

    state = await press(
        bot, context, admin_providers.start_new_provider, pack("pv", "new"), super_admin.telegram_id
    )
    assert state == admin_providers.ASK_NAME

    state = await write(bot, context, admin_providers.receive_provider_name, "مزود جديد", super_admin.telegram_id)
    assert state == admin_providers.ASK_URL

    state = await write(
        bot,
        context,
        admin_providers.receive_provider_url,
        "https://panel.example.com/api/v2",
        super_admin.telegram_id,
    )
    assert state == admin_providers.ASK_TYPE

    state = await press(
        bot,
        context,
        admin_providers.receive_provider_type,
        pack("pv", "type", "mock"),
        super_admin.telegram_id,
    )
    assert state == admin_providers.ASK_CURRENCY

    state = await write(bot, context, admin_providers.receive_provider_currency, "USD 530.5", super_admin.telegram_id)
    assert state == admin_providers.ASK_KEY

    state = await write(bot, context, admin_providers.receive_provider_key, secret, super_admin.telegram_id)
    assert state == admin_providers.CONFIRM_NEW
    assert "USD × 530.5" in bot.last.text
    assert secret not in bot.last.text                      # الملخص يعرض آخر 4 فقط
    assert secret[-4:] in bot.last.text

    state = await press(
        bot, context, admin_providers.confirm_new_provider, pack("flow", "confirm"), super_admin.telegram_id
    )
    assert state == ConversationHandler.END

    created = await repos.providers.get_by_name("مزود جديد")
    assert created is not None
    assert created.api_key_enc != secret                    # مشفَّر لا نص صريح
    assert created.api_key_hint == secret[-4:]
    assert created.currency == "USD" and created.exchange_rate == "530.5"
    assert secret not in " ".join(message.text or "" for message in bot.sent)


async def test_add_provider_rejects_bad_url(
    bot: FakeBot, context: FakeContext, super_admin: User
) -> None:
    """رابط API بلا بروتوكول يُرفض ولا تتقدم المحادثة."""
    await load_user(bot, context, super_admin)
    await press(bot, context, admin_providers.start_new_provider, pack("pv", "new"), super_admin.telegram_id)
    await write(bot, context, admin_providers.receive_provider_name, "مزود", super_admin.telegram_id)

    await write(bot, context, admin_providers.receive_provider_url, "panel-without-scheme", super_admin.telegram_id)
    assert "❌" in bot.last.text


async def test_add_provider_rejects_short_key(
    bot: FakeBot, context: FakeContext, super_admin: User
) -> None:
    """مفتاح أقصر من 8 محارف يُرفض ويبقى السؤال قائماً."""
    await load_user(bot, context, super_admin)
    await press(bot, context, admin_providers.start_new_provider, pack("pv", "new"), super_admin.telegram_id)
    await write(bot, context, admin_providers.receive_provider_name, "مزود", super_admin.telegram_id)
    await write(
        bot,
        context,
        admin_providers.receive_provider_url,
        "https://panel.example.com/api/v2",
        super_admin.telegram_id,
    )
    await press(bot, context, admin_providers.receive_provider_type, pack("pv", "type", "mock"), super_admin.telegram_id)

    state = await write(bot, context, admin_providers.receive_provider_key, "123", super_admin.telegram_id)
    assert state == admin_providers.ASK_KEY
    assert "❌" in bot.last.text


# ======================================================================== #
#                       محادثة: تغيير مفتاح الـAPI                         #
# ======================================================================== #


async def test_key_update_requires_super_admin(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    mock_provider: Provider,
    repos: Repositories,
) -> None:
    """`admin` لا يملك `providers.key.update` ⇒ المحادثة لا تبدأ والمفتاح كما هو."""
    await load_user(bot, context, admin)
    await press(
        bot,
        context,
        admin_providers.start_key_update,
        pack("pv", "key", mock_provider.id),
        admin.telegram_id,
    )

    unchanged = await repos.providers.get(mock_provider.id)
    assert unchanged.api_key_enc == mock_provider.api_key_enc


async def test_key_update_changes_hint_for_super_admin(
    bot: FakeBot,
    context: FakeContext,
    super_admin: User,
    mock_provider: Provider,
    repos: Repositories,
    mock_client: MockProviderClient,
) -> None:
    """الأدمن الأعلى يغيّر المفتاح: يتبدّل الـhint والنص المشفَّر ولا يُطبع المفتاح."""
    await load_user(bot, context, super_admin)
    new_key = "brand-new-key-5555"

    state = await press(
        bot,
        context,
        admin_providers.start_key_update,
        pack("pv", "key", mock_provider.id),
        super_admin.telegram_id,
    )
    assert state == admin_providers.ASK_NEW_KEY

    state = await write(bot, context, admin_providers.receive_new_key, new_key, super_admin.telegram_id)
    assert state == ConversationHandler.END

    updated = await repos.providers.get(mock_provider.id)
    assert updated.api_key_hint == new_key[-4:]
    assert updated.api_key_enc != mock_provider.api_key_enc
    assert new_key not in " ".join(message.text or "" for message in bot.sent)


# ======================================================================== #
#                          مزامنة خدمات المزود                             #
# ======================================================================== #


async def test_sync_updates_cost_without_touching_sale_price(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    mock_provider: Provider,
    mock_service,
    mock_client: MockProviderClient,
    repos: Repositories,
) -> None:
    """المزامنة تحدّث تكلفة المزود والحدود، ولا تغيّر سعر البيع ولا تحذف شيئاً."""
    mock_client.rate_per_1000_units = 7_500
    await load_user(bot, context, admin)
    await press(
        bot,
        context,
        admin_providers.sync_provider,
        pack("pv", "sync", mock_provider.id),
        admin.telegram_id,
    )

    refreshed = await repos.services.get(mock_service.id)
    assert refreshed.provider_price_per_1000_units == 7_500
    assert refreshed.price_per_1000_units == mock_service.price_per_1000_units   # لم يُمَس
    assert refreshed.is_archived == mock_service.is_archived


async def test_sync_reports_missing_services(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    mock_provider: Provider,
    repos: Repositories,
    mock_client: MockProviderClient,
) -> None:
    """خدمة لم تعد موجودة في قائمة المزود تُذكر في التقرير ولا تُحذف تلقائياً."""
    categories = await repos.categories.list_all()
    async with repos.db.transaction() as tx:
        orphan = await repos.services.create(
            tx,
            category_id=categories[0].id,
            provider_id=mock_provider.id,
            provider_service_id="999999",            # غير موجود لدى المزود الوهمي
            name="خدمة مفقودة لدى المزود",
            price_per_1000_units=12_000,
            provider_price_per_1000_units=6_000,
            min_quantity=100,
            max_quantity=1_000,
        )

    await load_user(bot, context, admin)
    await press(
        bot,
        context,
        admin_providers.sync_provider,
        pack("pv", "sync", mock_provider.id),
        admin.telegram_id,
    )

    report = " ".join(message.text or "" for message in bot.sent)
    assert "لم تعد موجودة لديه: 1" in report
    assert orphan.name[:12] in report
    assert await repos.services.get(orphan.id) is not None        # لم تُحذف


# ======================================================================== #
#                     محادثة: استيراد خدمة من المزود                       #
# ======================================================================== #


async def _import_service(
    bot: FakeBot,
    context: FakeContext,
    actor: User,
    provider: Provider,
    *,
    query: str = "Followers",
    margin: str = "50",
) -> int:
    """تنفيذ دورة استيراد كاملة وإرجاع الحالة النهائية (أداة للاختبارات)."""
    await press(
        bot, context, admin_providers.start_import, pack("pv", "imp", provider.id), actor.telegram_id
    )
    await write(bot, context, admin_providers.receive_import_query, query, actor.telegram_id)
    await press(bot, context, admin_providers.pick_import_item, pack("pv", "pick", 0), actor.telegram_id)
    await press(bot, context, admin_providers.import_continue, pack("pv", "go"), actor.telegram_id)

    category_button = next(
        button for button in bot.last.buttons if button.startswith("pv:cat:")
    )
    await press(bot, context, admin_providers.pick_import_category, category_button, actor.telegram_id)
    await write(bot, context, admin_providers.receive_margin, margin, actor.telegram_id)
    return await press(
        bot, context, admin_providers.confirm_import, pack("flow", "confirm"), actor.telegram_id
    )


async def test_import_creates_service_with_margin(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    mock_provider: Provider,
    mock_client: MockProviderClient,
    repos: Repositories,
) -> None:
    """الاستيراد ينشئ خدمة سعرها = تكلفة المزود + الهامش المطلوب."""
    mock_client.rate_per_1000_units = 6_000
    await load_user(bot, context, admin)

    state = await _import_service(bot, context, admin, mock_provider, margin="50")
    assert state == ConversationHandler.END

    created = await repos.services.find_by_provider_service(mock_provider.id, "555")
    assert created is not None
    assert created.provider_price_per_1000_units == 6_000
    assert created.price_per_1000_units == 9_000              # 6000 + 50%
    assert created.min_quantity == 100
    assert created.max_quantity == 100_000


async def test_import_rejects_duplicate_provider_service(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    mock_provider: Provider,
    mock_service,
    mock_client: MockProviderClient,
    repos: Repositories,
) -> None:
    """استيراد خدمة مرتبطة أصلاً يُرفض — لا تُنشأ نسخة ثانية لنفس خدمة المزود."""
    await load_user(bot, context, admin)
    before = len(await repos.services.list_by_provider(mock_provider.id, limit=50, offset=0))

    await _import_service(bot, context, admin, mock_provider, margin="40")

    after = len(await repos.services.list_by_provider(mock_provider.id, limit=50, offset=0))
    assert after == before
    report = " ".join(message.text or "" for message in bot.sent)
    assert "مكررة: <b>1</b>" in report and "مستوردة مسبقاً" in report


async def test_import_rejects_non_numeric_margin(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    mock_provider: Provider,
    mock_client: MockProviderClient,
) -> None:
    """هامش غير رقمي يُرفض برسالة واضحة بدل إنشاء خدمة بسعر خاطئ."""
    await load_user(bot, context, admin)
    await press(
        bot, context, admin_providers.start_import, pack("pv", "imp", mock_provider.id), admin.telegram_id
    )
    await write(bot, context, admin_providers.receive_import_query, "Followers", admin.telegram_id)
    await press(bot, context, admin_providers.pick_import_item, pack("pv", "pick", 0), admin.telegram_id)
    await press(bot, context, admin_providers.import_continue, pack("pv", "go"), admin.telegram_id)
    category_button = next(button for button in bot.last.buttons if button.startswith("pv:cat:"))
    await press(bot, context, admin_providers.pick_import_category, category_button, admin.telegram_id)

    await write(bot, context, admin_providers.receive_margin, "كثير", admin.telegram_id)
    assert "❌" in bot.last.text


async def test_import_search_with_no_results_stays_in_state(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    mock_provider: Provider,
    mock_client: MockProviderClient,
) -> None:
    """بحث بلا نتائج يُعيد السؤال بدل إنهاء المحادثة."""
    await load_user(bot, context, admin)
    await press(
        bot, context, admin_providers.start_import, pack("pv", "imp", mock_provider.id), admin.telegram_id
    )

    state = await write(
        bot, context, admin_providers.receive_import_query, "لا-يوجد-شيء-بهذا-الاسم", admin.telegram_id
    )
    assert state == admin_providers.ASK_SEARCH


# ======================================================================== #
#                   إنشاء خدمة يدوياً من شاشة الكتالوج                     #
# ======================================================================== #


async def test_manual_service_creation_flow(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    mock_provider: Provider,
    repos: Repositories,
) -> None:
    """إنشاء خدمة يدوياً: تصنيف ← مزود ← رقم ← اسم ← تكلفة ← سعر ← حدود ← تأكيد."""
    await load_user(bot, context, admin)

    state = await press(bot, context, catalog.start_new_service, pack("ac", "newsvc"), admin.telegram_id)
    assert state == catalog.NEW_PICK_CATEGORY

    category_button = next(button for button in bot.last.buttons if button.startswith("ac:ncat:"))
    state = await press(bot, context, catalog.new_service_category, category_button, admin.telegram_id)
    assert state == catalog.NEW_PICK_PROVIDER

    state = await press(
        bot,
        context,
        catalog.new_service_provider,
        pack("ac", "nprv", mock_provider.id),
        admin.telegram_id,
    )
    assert state == catalog.NEW_ASK_PROVIDER_SERVICE_ID

    await write(bot, context, catalog.new_service_provider_service_id, "777", admin.telegram_id)
    await write(bot, context, catalog.new_service_name, "خدمة يدوية للاختبار", admin.telegram_id)
    await write(bot, context, catalog.new_service_cost, "0.6", admin.telegram_id)
    await write(bot, context, catalog.new_service_price, "1.2", admin.telegram_id)
    await write(bot, context, catalog.new_service_min, "100", admin.telegram_id)
    state = await write(bot, context, catalog.new_service_max, "5000", admin.telegram_id)
    assert state == catalog.NEW_CONFIRM

    state = await press(
        bot, context, catalog.confirm_new_service, pack("flow", "confirm"), admin.telegram_id
    )
    assert state == ConversationHandler.END

    created = await repos.services.find_by_provider_service(mock_provider.id, "777")
    assert created is not None
    assert created.price_per_1000_units == 12_000
    assert created.provider_price_per_1000_units == 6_000
    assert created.min_quantity == 100
    assert created.max_quantity == 5_000


async def test_manual_service_rejects_max_below_min(
    bot: FakeBot, context: FakeContext, admin: User, mock_provider: Provider
) -> None:
    """أكبر كمية أصغر من أقل كمية تُرفض ولا تُنشأ خدمة بحدود مستحيلة."""
    await load_user(bot, context, admin)
    await press(bot, context, catalog.start_new_service, pack("ac", "newsvc"), admin.telegram_id)
    category_button = next(button for button in bot.last.buttons if button.startswith("ac:ncat:"))
    await press(bot, context, catalog.new_service_category, category_button, admin.telegram_id)
    await press(
        bot, context, catalog.new_service_provider, pack("ac", "nprv", mock_provider.id), admin.telegram_id
    )
    await write(bot, context, catalog.new_service_provider_service_id, "778", admin.telegram_id)
    await write(bot, context, catalog.new_service_name, "خدمة حدود خاطئة", admin.telegram_id)
    await write(bot, context, catalog.new_service_cost, "0.6", admin.telegram_id)
    await write(bot, context, catalog.new_service_price, "1.2", admin.telegram_id)
    await write(bot, context, catalog.new_service_min, "500", admin.telegram_id)

    state = await write(bot, context, catalog.new_service_max, "100", admin.telegram_id)
    assert state == catalog.NEW_ASK_MAX
    assert "❌" in bot.last.text


async def test_manual_service_blocked_without_permission(
    bot: FakeBot, context: FakeContext, user: User, mock_provider: Provider, repos: Repositories
) -> None:
    """مستخدم بلا صلاحية `services.create` لا يبدأ إنشاء خدمة أصلاً."""
    await load_user(bot, context, user)
    before = await repos.services.count_active()
    await press(bot, context, catalog.start_new_service, pack("ac", "newsvc"), user.telegram_id)

    assert bot.answers, "كان يجب تنبيه المستخدم بالرفض"
    assert not bot.sent                                   # لا شاشة إنشاء تُعرض أصلاً
    assert await repos.services.count_active() == before
