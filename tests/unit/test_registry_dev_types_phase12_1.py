"""المزود الوهمي مخفي ومرفوض في الإنتاج ما لم تُفعَّل أنواع التطوير صراحةً (المراجعة 12.1، البند 18)."""

from __future__ import annotations

import pytest

from core.exceptions import ProviderError
from integrations.providers import registry


def test_mock_hidden_and_unsupported_by_default() -> None:
    """افتراضياً (حالة الإنتاج): لا يظهر في القائمة، ولا يُعدّ مدعوماً، ولا يُنشأ له عميل."""
    registry.enable_dev_types(False)
    assert "mock" not in registry.available_types()
    assert not registry.is_supported("mock")
    assert registry.is_supported("perfect_panel")
    with pytest.raises(ProviderError):
        registry.create_client(api_type="mock", api_url="https://x.test", api_key="k" * 10)


def test_mock_available_once_enabled() -> None:
    """بعد التفعيل الصريح يعمل كما كان (الاختبارات و`demo_cycle`)."""
    registry.enable_dev_types(True)
    assert "mock" in registry.available_types()
    assert registry.create_client(api_type="mock", api_url="https://x.test", api_key="k" * 10) is not None
