"""
اختبارات طبقة المزودين: التشفير، إخفاء المفاتيح، تصنيف الأخطاء، والتعطيل التلقائي.

أهم ما يُحرَس هنا: **لا يظهر مفتاح API كاملاً في أي مكان** — لا في قاعدة
البيانات، ولا في سجل طلبات المزود، ولا في رسائل الواجهة.
"""

from __future__ import annotations

import pytest

from core.exceptions import (
    PermissionDeniedError,
    ProviderError,
    ProviderTemporaryError,
)
from database.models import User
from database.repositories import Repositories
from services import ServiceContainer

REAL_KEY = "sk-live-9f3b2c7d41ee8a56"


async def test_api_key_is_encrypted_at_rest_and_only_hinted(
    services: ServiceContainer, repos: Repositories, super_admin: User
) -> None:
    """المفتاح يُخزَّن مشفّراً ولا يُحفظ منه إلا آخر أربعة أرقام للعرض."""
    provider = await services.providers.create_provider(
        super_admin, name="PanelOne", api_url="https://panel.invalid/api/v2", api_key=REAL_KEY
    )
    stored = await repos.providers.get(provider.id)
    assert stored is not None
    assert REAL_KEY not in stored.api_key_enc
    assert stored.api_key_hint == "8a56"
    assert REAL_KEY not in (stored.api_key_hint or "")

    # ولا يظهر المفتاح في سجل التدقيق
    logs = await services.audit.by_target("provider", provider.id)
    assert logs
    assert all(REAL_KEY not in (log.after_json or "") for log in logs)


async def test_short_key_rejected_and_key_update_audited_without_the_key(
    services: ServiceContainer, repos: Repositories, super_admin: User
) -> None:
    """المفتاح القصير مرفوض، وتحديث المفتاح يُسجَّل دون كتابة المفتاح نفسه."""
    with pytest.raises(ProviderError):
        await services.providers.create_provider(
            super_admin, name="BadKey", api_url="https://panel.invalid/api/v2", api_key="123"
        )

    provider = await services.providers.create_provider(
        super_admin, name="PanelTwo", api_url="https://panel.invalid/api/v2", api_key=REAL_KEY
    )
    new_key = "sk-live-0000111122223333"
    assert await services.providers.update_api_key(super_admin, provider.id, new_key)

    updated = await repos.providers.get(provider.id)
    assert updated is not None and updated.api_key_hint == "3333"
    logs = await services.audit.by_target("provider", provider.id)
    key_logs = [log for log in logs if log.action == "providers.key.update"]
    assert key_logs and all(new_key not in (log.after_json or "") for log in key_logs)


async def test_provider_management_requires_permissions(
    services: ServiceContainer, user: User, admin: User, mock_provider
) -> None:
    """إضافة المزودين وتغيير مفاتيحهم محصورة بصلاحياتها."""
    with pytest.raises(PermissionDeniedError):
        await services.providers.create_provider(
            user, name="X", api_url="https://panel.invalid/api/v2", api_key=REAL_KEY
        )
    with pytest.raises(PermissionDeniedError):
        await services.providers.update_api_key(admin, mock_provider.id, REAL_KEY)
    with pytest.raises(PermissionDeniedError):
        await services.providers.test_connection(user, mock_provider.id)


async def test_balance_check_logs_request_without_secrets(
    services: ServiceContainer, repos: Repositories, mock_provider, mock_client
) -> None:
    """كل نداء للمزود يُسجَّل في `provider_requests` بلا أي سر."""
    balance = await services.providers.check_balance(mock_provider)
    assert balance.amount_units > 0

    rows = await repos.provider_requests.list_by_provider(mock_provider.id, limit=5)
    assert rows
    blob = " ".join(
        f"{row['request_summary']} {row['response_snippet']}" for row in rows
    )
    assert "mock-key-123456" not in blob
    assert "3456" not in blob or "api_key" not in blob


async def test_connection_test_returns_arabic_message(
    services: ServiceContainer, super_admin: User, mock_provider, mock_client
) -> None:
    """اختبار الاتصال من اللوحة يعطي رسالة عربية واضحة بلا أسرار."""
    ok, message = await services.providers.test_connection(super_admin, mock_provider.id)
    assert ok is True
    assert "الاتصال ناجح" in message
    assert "mock-key-123456" not in message

    missing_ok, missing_message = await services.providers.test_connection(super_admin, 99999)
    assert missing_ok is False and "غير موجود" in missing_message


async def test_repeated_failures_disable_provider_and_alert_admins(
    services: ServiceContainer, repos: Repositories, admin: User, mock_provider, mock_client
) -> None:
    """الأخطاء المتتالية تعطّل المزود مؤقتاً وتُنبّه الأدمن (حماية من استنزاف الطلبات)."""
    await services.settings.set("provider_failure_threshold", 3)
    await services.settings.set("provider_disable_minutes", 15)

    for _ in range(3):
        mock_client.fail_next_balance = ProviderTemporaryError("انقطاع الشبكة")
        with pytest.raises(ProviderTemporaryError):
            await services.providers.check_balance(mock_provider)

    disabled = await repos.providers.get(mock_provider.id)
    assert disabled is not None
    assert disabled.consecutive_failures >= 3
    assert disabled.disabled_until is not None
    assert not await services.providers.is_usable(disabled)

    inbox = await repos.notifications.list_for_user(admin.id)
    assert any("مزود" in item.title or "مزود" in item.message for item in inbox)


async def test_success_resets_failure_counter(
    services: ServiceContainer, repos: Repositories, mock_provider, mock_client
) -> None:
    """نجاح واحد يصفّر عدّاد الأخطاء المتتالية."""
    mock_client.fail_next_balance = ProviderTemporaryError("انقطاع مؤقت")
    with pytest.raises(ProviderTemporaryError):
        await services.providers.check_balance(mock_provider)
    assert (await repos.providers.get(mock_provider.id)).consecutive_failures == 1

    await services.providers.check_balance(mock_provider)
    assert (await repos.providers.get(mock_provider.id)).consecutive_failures == 0


async def test_disabled_provider_is_not_usable(
    services: ServiceContainer, repos: Repositories, super_admin: User, mock_provider
) -> None:
    """المزود المعطَّل يدوياً يخرج من الخدمة دون حذفه."""
    assert await services.providers.set_active(super_admin, mock_provider.id, False)
    provider = await repos.providers.get(mock_provider.id)
    assert provider is not None and provider.is_active == 0
    assert not await services.providers.is_usable(provider)

    assert await services.providers.set_active(super_admin, mock_provider.id, True)
    restored = await repos.providers.get(mock_provider.id)
    assert restored is not None and await services.providers.is_usable(restored)


async def test_health_snapshot_for_admin_panel(
    services: ServiceContainer, mock_provider, mock_client
) -> None:
    """ملخص صحة المزود يصلح للعرض المباشر في اللوحة."""
    health = await services.providers.health(mock_provider)
    assert health.provider.id == mock_provider.id
    assert health.is_usable is True
    assert health.reason


async def test_fetch_services_requires_sync_permission(
    services: ServiceContainer, user: User, super_admin: User, mock_provider, mock_client
) -> None:
    """استيراد خدمات المزود صلاحية مستقلة لا يملكها المستخدم العادي."""
    with pytest.raises(PermissionDeniedError):
        await services.providers.fetch_services(user, mock_provider)

    items = await services.providers.fetch_services(super_admin, mock_provider)
    assert items and items[0].provider_service_id
