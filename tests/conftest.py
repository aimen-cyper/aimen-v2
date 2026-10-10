"""
تهيئة بيئة الاختبارات.

كل اختبار يحصل على قاعدة بيانات مؤقتة جديدة مع تطبيق كامل الترحيلات،
حتى تكون الاختبارات مستقلة تماماً عن بعضها وعن بيانات التشغيل الحقيقية.

تنظيم الاختبارات:
    tests/unit/        : منطق خالص بلا قاعدة بيانات (مال، حالات، تحقق، صلاحيات).
    tests/integration/ : خدمة واحدة مع قاعدة بيانات حقيقية (مؤقتة).
    tests/e2e/         : الدورة الكاملة عبر كل الخدمات معاً.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio

# إضافة جذر المشروع إلى مسار الاستيراد حتى تعمل الاستيرادات المطلقة
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.database import Database  # noqa: E402
from database.migrator import Migrator  # noqa: E402
from database.repositories import Repositories  # noqa: E402
from integrations.providers import registry  # noqa: E402
from integrations.providers.mock import MockProviderClient  # noqa: E402
from services import ServiceContainer, build_services  # noqa: E402
from texts import templates as templates_module  # noqa: E402
from utils import net_security  # noqa: E402
from utils.security import SecretBox, clear_registered_secrets, generate_encryption_key  # noqa: E402


@pytest.fixture(autouse=True)
def _enable_dev_provider_types():
    """الاختبارات تستعمل المزود الوهمي: نفعّل أنواع التطوير ونعيد الحالة بعد كل اختبار (الإنتاج: معطّلة)."""
    previous = registry.dev_types_enabled()
    registry.enable_dev_types(True)
    yield
    registry.enable_dev_types(previous)


@pytest.fixture(autouse=True)
def _reset_template_overrides():
    """
    تصفير قوالب الإشعارات المخصّصة قبل وبعد كل اختبار (المرحلة 8).

    ذاكرة القوالب عامة على مستوى الوحدة، فبدون هذا التصفير يتسرّب قالب
    عدّله اختبارٌ ما إلى اختبار آخر فيفشل لسبب لا علاقة له به.
    """
    templates_module.clear_overrides()
    yield
    templates_module.clear_overrides()


@pytest.fixture(autouse=True)
def _reset_security_globals():
    """
    تصفير الحالة الأمنية العامة قبل وبعد كل اختبار (المرحلة 9).

    الأسرار المسجَّلة وذاكرة نتائج DNS عامتان على مستوى الوحدة؛ تركهما يتسرّب
    بين الاختبارات يخفي أخطاء (قيمة تُحذف من نص اختبار آخر دون سبب ظاهر).
    """
    clear_registered_secrets()
    net_security.clear_dns_cache()
    yield
    clear_registered_secrets()
    net_security.clear_dns_cache()


@pytest_asyncio.fixture
async def db(tmp_path: Path):
    """قاعدة بيانات مؤقتة مع تطبيق كل الترحيلات."""
    database = Database(tmp_path / "test.db", read_pool_size=2)
    await database.connect()
    await Migrator(database).apply_all()
    try:
        yield database
    finally:
        await database.close()


@pytest_asyncio.fixture
async def repos(db: Database) -> Repositories:
    """حاوية المستودعات على قاعدة بيانات الاختبار."""
    return Repositories(db)


@pytest.fixture
def secret_box() -> SecretBox:
    """صندوق تشفير بمفتاح مؤقت يُولَّد لكل اختبار (لا مفاتيح ثابتة في الكود)."""
    return SecretBox(generate_encryption_key())


@pytest_asyncio.fixture
async def services(db: Database, repos: Repositories, secret_box: SecretBox) -> ServiceContainer:
    """
    حاوية الخدمات كاملة الربط.

    `settings_ttl_seconds=0` يلغي كاش الإعدادات حتى يرى الاختبار أي تعديل فوراً.
    """
    return build_services(db, repos, secret_box=secret_box, settings_ttl_seconds=0)


@pytest_asyncio.fixture
async def user(db: Database, repos: Repositories):
    """مستخدم اختباري جاهز برصيد صفر."""
    async with db.transaction() as tx:
        return await repos.users.create(
            tx, telegram_id=100200300, username="tester", first_name="Tester"
        )


@pytest_asyncio.fixture
async def admin(db: Database, repos: Repositories):
    """مستخدم بدور admin (الصلاحيات تأتي من جدول الأدوار المزروع في الترحيل 0002)."""
    async with db.transaction() as tx:
        return await repos.users.create(
            tx, telegram_id=900900900, username="bossadmin", first_name="Admin", role="admin"
        )


@pytest_asyncio.fixture
async def super_admin(db: Database, repos: Repositories):
    """مستخدم بدور super_admin (يملك كل الصلاحيات)."""
    async with db.transaction() as tx:
        return await repos.users.create(
            tx, telegram_id=777777777, username="root", first_name="Root", role="super_admin"
        )


@pytest_asyncio.fixture
async def provider(db: Database, repos: Repositories):
    """مزود اختباري (المفتاح هنا نص وهمي مشفَّر شكلياً — لا يُستخدم للاتصال)."""
    async with db.transaction() as tx:
        return await repos.providers.create(
            tx,
            currency="YER",   # عملة النظام الافتراضية: لا تحويل مطلوب
            name="TestProvider",
            api_url="https://example.invalid/api/v2",
            api_key_enc="ENC::dummy-not-a-real-key",
            api_key_hint="1234",
        )


@pytest.fixture
def mock_client() -> MockProviderClient:
    """
    عميل مزود وهمي **مشترك**: يُعاد نفس الكائن لكل استدعاء داخل الاختبار.

    السبب: `ProviderService.client_for` يبني عميلاً جديداً في كل عملية، بينما يحتاج
    المزود الوهمي الاحتفاظ بحالة الطلبات بين الإرسال وفحص الحالة.
    """
    shared = MockProviderClient()
    registry.register_client("mock", lambda **_kwargs: shared)
    try:
        yield shared
    finally:
        registry.register_client("mock", MockProviderClient)  # إعادة السجل كما كان


@pytest_asyncio.fixture
async def mock_provider(db: Database, repos: Repositories, secret_box: SecretBox):
    """مزود من نوع mock بمفتاح مشفَّر فعلياً (يُفك عند الاتصال)."""
    async with db.transaction() as tx:
        return await repos.providers.create(
            tx,
            currency="YER",   # عملة النظام الافتراضية: لا تحويل مطلوب
            name="MockProvider",
            api_url="https://mock.invalid/api/v2",
            api_key_enc=secret_box.encrypt("mock-key-123456"),
            api_key_hint="3456",
            api_type="mock",
        )


@pytest_asyncio.fixture
async def service(db: Database, repos: Repositories, provider):
    """خدمة اختبارية بسعر 1.0000 لكل ألف (10000 نقطة)."""
    categories = await repos.categories.list_all()
    async with db.transaction() as tx:
        return await repos.services.create(
            tx,
            category_id=categories[0].id,
            provider_id=provider.id,
            provider_service_id="555",
            name="متابعين انستغرام اختبار",
            price_per_1000_units=10_000,
            provider_price_per_1000_units=6_000,
            min_quantity=100,
            max_quantity=10_000,
        )


@pytest_asyncio.fixture
async def mock_service(db: Database, repos: Repositories, mock_provider):
    """خدمة مرتبطة بالمزود الوهمي (تُستخدم في اختبارات الدورة الكاملة)."""
    categories = await repos.categories.list_all()
    async with db.transaction() as tx:
        return await repos.services.create(
            tx,
            category_id=categories[0].id,
            provider_id=mock_provider.id,
            provider_service_id="555",
            name="متابعين انستغرام (Mock)",
            price_per_1000_units=10_000,     # 1.0000 لكل ألف ⇒ طلب 1000 يكلف 10000 نقطة
            provider_price_per_1000_units=6_000,
            min_quantity=100,
            max_quantity=100_000,
        )


@pytest_asyncio.fixture
async def payment_method(db: Database, repos: Repositories):
    """طريقة دفع يدوية للاختبار."""
    async with db.transaction() as tx:
        return await repos.payment_methods.create(
            tx, code="test_wallet", name_ar="محفظة اختبار", instructions_ar="حوّل ثم أرسل الإثبات"
        )


@pytest.fixture
def anyio_backend() -> str:
    """تثبيت backend الخاص بالاختبارات غير المتزامنة."""
    return "asyncio"
