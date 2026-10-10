"""اختبارات حماية SSRF عبر مسار المزودين، وحمايات سكربتات التشغيل (المرحلة 9)."""

from __future__ import annotations

import stat
from pathlib import Path

import httpx
import pytest

from core.exceptions import ProviderPermanentError, ValidationError
from database.database import Database
from database.migrator import Migrator
from database.repositories import Repositories
from integrations.providers.perfect_panel import PerfectPanelClient
from utils import net_security

pytestmark = pytest.mark.asyncio


# ================================ SSRF ================================ #


@pytest.mark.parametrize(
    "url",
    [
        "http://panel.example.com/api/v2",
        "https://127.0.0.1/api/v2",
        "https://169.254.169.254/latest",
        "https://panel.example.com:8080/api/v2",
        "https://localhost/api",
    ],
)
async def test_create_provider_rejects_unsafe_urls(services, super_admin, url: str) -> None:
    """إنشاء مزود برابط غير آمن يُرفض قبل حفظ أي شيء."""
    with pytest.raises(ValidationError):
        await services.providers.create_provider(
            super_admin, name="Bad", api_url=url, api_key="key-1234567890"
        )
    assert await services.repos.providers.list_all() == []


async def test_create_provider_accepts_public_https(services, super_admin) -> None:
    """رابط https عام صحيح يُقبل (المسار الطبيعي لم يتأثر)."""
    provider = await services.providers.create_provider(
        super_admin, name="Good", api_url="https://panel.example.com/api/v2", api_key="key-1234567890"
    )
    assert provider.api_url == "https://panel.example.com/api/v2"


async def test_real_client_refuses_private_literal_ip_before_any_network() -> None:
    """العميل الحقيقي (بلا حقن) يرفض عنواناً داخلياً قبل أي اتصال أو إرسال للمفتاح."""
    client = PerfectPanelClient(api_url="https://10.0.0.5/api/v2", api_key="key-1234567890")
    with pytest.raises(ProviderPermanentError):
        await client.get_balance()


async def test_real_client_refuses_domain_resolving_to_private(monkeypatch: pytest.MonkeyPatch) -> None:
    """نطاق يبدو عاماً لكنه يُحلّ لعنوان داخلي (DNS rebinding الساذج) يُرفض."""

    async def private_resolver(host: str) -> list[str]:
        return ["192.168.1.20"]

    monkeypatch.setattr(net_security, "_system_resolver", private_resolver)
    client = PerfectPanelClient(api_url="https://evil.example.com/api/v2", api_key="key-1234567890")
    with pytest.raises(ProviderPermanentError):
        await client.get_balance()


async def test_injected_test_client_skips_dns_check() -> None:
    """عميل الاختبار المحقون لا يُفحص DNS له (قرار موثّق) فيعمل بلا شبكة."""
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"balance": "5.0", "currency": "USD"}))
    client = PerfectPanelClient(
        api_url="https://panel.invalid/api/v2", api_key="key-1234567890", client=httpx.AsyncClient(transport=transport)
    )
    balance = await client.get_balance()
    assert balance.amount_units == 50_000 and balance.currency == "USD"


# ============================== سكربت create_admin ============================== #


@pytest.fixture
async def script_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """بيئة معزولة لسكربتات CLI: قاعدة مؤقتة جاهزة المخطط ومتغيرات بيئة موجَّهة لها."""
    db_path = tmp_path / "data" / "smm.db"
    db_path.parent.mkdir()
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("LOG_FILE", str(tmp_path / "logs" / "bot.log"))
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    for key in ("BOT_TOKEN", "ENCRYPTION_KEY", "SUPER_ADMIN_IDS"):
        monkeypatch.delenv(key, raising=False)
    database = Database(db_path)
    await database.connect()
    await Migrator(database).apply_all()
    repos = Repositories(database)
    async with database.transaction() as tx:
        await repos.users.create(tx, telegram_id=111, first_name="Root", role="super_admin")
    await database.close()
    return db_path


async def _role_of(db_path: Path, telegram_id: int) -> str | None:
    """قراءة دور مستخدم من ملف القاعدة مباشرة."""
    database = Database(db_path)
    await database.connect()
    try:
        user = await Repositories(database).users.get_by_telegram_id(telegram_id)
        return user.role if user else None
    finally:
        await database.close()


async def test_create_admin_refuses_to_demote_last_super_admin(script_env, capsys) -> None:
    """تنزيل آخر أدمن أعلى مرفوض بلا --force ويبقى دوره."""
    from scripts.create_admin import run

    assert await run(111, "user") == 1
    assert await _role_of(script_env, 111) == "super_admin"
    assert "آخر أدمن أعلى" in capsys.readouterr().out


async def test_create_admin_force_allows_demotion(script_env) -> None:
    """--force يسمح بالتنزيل عند الضرورة."""
    from scripts.create_admin import run

    assert await run(111, "user", force=True) == 0
    assert await _role_of(script_env, 111) == "user"


async def test_create_admin_allows_demotion_when_another_super_exists(script_env) -> None:
    """بوجود أدمن أعلى آخر فعّال يجوز تنزيل الأول بلا --force."""
    from scripts.create_admin import run

    assert await run(222, "super_admin") == 0
    assert await run(111, "admin") == 0
    assert await _role_of(script_env, 111) == "admin"


@pytest.mark.parametrize("telegram_id", [0, -5])
async def test_create_admin_rejects_non_positive_ids(script_env, telegram_id: int) -> None:
    """معرّف غير موجب خطأ إدخال لا ينشئ مستخدماً."""
    from scripts.create_admin import run

    assert await run(telegram_id, "admin") == 2
    assert await _role_of(script_env, telegram_id) is None


async def test_create_admin_leaves_database_private(script_env) -> None:
    """بعد تشغيل السكربت يبقى ملف القاعدة مقصوراً على المالك."""
    from scripts.create_admin import run

    script_env.chmod(0o644)
    assert await run(333, "admin") == 0
    assert stat.S_IMODE(script_env.stat().st_mode) == 0o600
