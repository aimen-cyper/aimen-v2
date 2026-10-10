"""اختبارات تقوية عميل Perfect Panel (المراجعة 12.1): حد حجم الاستجابة وتحويل الأعداد الصحيحة."""

from __future__ import annotations

import httpx
import pytest

import integrations.providers.perfect_panel as pp
from core.exceptions import ProviderTemporaryError, ProviderUncertainError
from integrations.providers.perfect_panel import PerfectPanelClient

pytestmark = pytest.mark.asyncio

API_URL = "https://panel.invalid/api/v2"


def _client(handler) -> PerfectPanelClient:
    """عميل بنقل وهمي."""
    return PerfectPanelClient(api_url=API_URL, api_key="k" * 12, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_oversized_response_on_read_is_temporary(monkeypatch) -> None:
    """استجابة أكبر من الحد أثناء قراءة عادية ⇒ خطأ مؤقت (لا تحميل كامل للذاكرة)."""
    monkeypatch.setattr(pp, "MAX_RESPONSE_BYTES", 1_000)
    client = _client(lambda request: httpx.Response(200, content=b"[" + b"1," * 5_000 + b"1]"))
    with pytest.raises(ProviderTemporaryError):
        await client.get_services()


async def test_oversized_response_after_add_is_uncertain(monkeypatch) -> None:
    """بعد إرسال طلب شراء: الاستجابة الضخمة ⇒ غير مؤكد (لا إعادة إرسال تلقائية)."""
    monkeypatch.setattr(pp, "MAX_RESPONSE_BYTES", 1_000)
    client = _client(lambda request: httpx.Response(200, content=b"x" * 5_000))
    with pytest.raises(ProviderUncertainError):
        await client.add_order(provider_service_id="1", link="https://a.test/u", quantity=100)


async def test_declared_content_length_over_limit_is_rejected(monkeypatch) -> None:
    """الطول المعلن في الترويسة يكفي للرفض قبل قراءة الجسم."""
    monkeypatch.setattr(pp, "MAX_RESPONSE_BYTES", 1_000)
    client = _client(lambda request: httpx.Response(200, content=b"{}", headers={"content-length": "999999"}))
    with pytest.raises(ProviderTemporaryError):
        await client.get_services()


async def test_normal_response_still_parses() -> None:
    """استجابة عادية تحت الحد تُقرأ كما كانت."""
    client = _client(lambda request: httpx.Response(200, json={"order": 7, "charge": "1.5", "currency": "USD"}))
    result = await client.add_order(provider_service_id="1", link="https://a.test/u", quantity=100)
    assert result.provider_order_id == "7"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("100", 100), (100, 100), ("100.0", 100), (" 7 ", 7), ("1e3", 1000), (0, 0),
     ("100.5", None), (1.5, None), ("nan", None), ("inf", None), ("1e400", None), ("1e30", None),
     ("abc", None), ("", None), (None, None)],
)
def test_as_int_rejects_fractions_and_non_finite(raw, expected) -> None:
    """الكسور والقيم غير المنتهية لا تُقرَّب بصمت (كان 1e400 يرفع OverflowError)."""
    assert PerfectPanelClient._as_int(raw) == expected
