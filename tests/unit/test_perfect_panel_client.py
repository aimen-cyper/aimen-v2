"""
اختبارات عميل Perfect Panel — بلا شبكة حقيقية (نقل httpx وهمي).

الهدف الأهم هنا ليس «هل يقرأ JSON؟» بل **تصنيف الأخطاء**: أي خطأ يُعاد معه
الإرسال بأمان، وأي خطأ ممنوع إعادة إرساله لأنه قد يكون كلّفنا مالاً فعلاً.
"""

from __future__ import annotations

import httpx
import pytest

from core.exceptions import (
    ProviderInsufficientFundsError,
    ProviderPermanentError,
    ProviderServiceMismatchError,
    ProviderTemporaryError,
    ProviderUncertainError,
)
from integrations.providers.perfect_panel import PerfectPanelClient

pytestmark = pytest.mark.asyncio

API_URL = "https://panel.invalid/api/v2"
API_KEY = "secret-key-123456"


def make_client(handler) -> PerfectPanelClient:
    """بناء عميل يستخدم نقل httpx وهمياً بدل الشبكة."""
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport)
    return PerfectPanelClient(api_url=API_URL, api_key=API_KEY, client=http)


def json_handler(payload, status: int = 200):
    """مُعالج يرد دائماً بنفس الحمولة (مع حفظ آخر طلب للفحص)."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["content"] = request.content.decode()
        captured["url"] = str(request.url)
        return httpx.Response(status, json=payload)

    handler.captured = captured      # type: ignore[attr-defined]
    return handler


# ======================================================================== #
#                            إنشاء الطلب (add)                             #
# ======================================================================== #


async def test_add_order_sends_expected_fields_and_parses_id() -> None:
    """الطلب يُرسل بالحقول المتفق عليها، ورقم الطلب والتكلفة يُقرآن صحيحاً."""
    handler = json_handler({"order": 23501, "charge": "1.2345", "currency": "USD"})
    client = make_client(handler)
    result = await client.add_order(
        provider_service_id="55", link="https://insta.test/u", quantity=1000
    )

    body = handler.captured["content"]
    assert "action=add" in body
    assert "service=55" in body
    assert "quantity=1000" in body
    assert f"key={API_KEY}" in body

    assert result.provider_order_id == "23501"
    assert result.charge_units == 12_345       # 1.2345 × 10000 بلا حساب عائم
    await client.close()


async def test_add_order_without_order_id_is_uncertain() -> None:
    """رد بلا رقم طلب وبلا خطأ = نتيجة غير مؤكدة (ممنوع إعادة الإرسال)."""
    client = make_client(json_handler({"status": "ok"}))
    with pytest.raises(ProviderUncertainError):
        await client.add_order(provider_service_id="55", link="https://x.test/u", quantity=100)
    await client.close()


async def test_timeout_while_adding_is_uncertain_not_temporary() -> None:
    """المهلة أثناء إنشاء الطلب = غير مؤكد — هذه القاعدة تمنع طلباً مكرراً مدفوعاً."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    client = make_client(handler)
    with pytest.raises(ProviderUncertainError):
        await client.add_order(provider_service_id="55", link="https://x.test/u", quantity=100)
    await client.close()


async def test_timeout_while_checking_status_is_temporary() -> None:
    """المهلة أثناء الاستعلام عن الحالة = خطأ مؤقت (إعادة المحاولة آمنة)."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    client = make_client(handler)
    with pytest.raises(ProviderTemporaryError):
        await client.get_order_status("23501")
    await client.close()


async def test_duplicate_order_message_is_uncertain() -> None:
    """المزود يقول «طلب مكرر» ⇒ الأرجح أن الأول وصل ⇒ غير مؤكد لا فاشل."""
    client = make_client(json_handler({"error": "Duplicate order"}))
    with pytest.raises(ProviderUncertainError):
        await client.add_order(provider_service_id="55", link="https://x.test/u", quantity=100)
    await client.close()


async def test_insufficient_funds_is_temporary_subclass() -> None:
    """«رصيد غير كافٍ» خطأ مؤقت مخصّص (يُحل بشحن حسابنا لدى المزود)."""
    client = make_client(json_handler({"error": "Not enough funds in the balance"}))
    with pytest.raises(ProviderInsufficientFundsError):
        await client.add_order(provider_service_id="55", link="https://x.test/u", quantity=100)
    await client.close()


async def test_incorrect_service_is_mismatch_error() -> None:
    """«رقم خدمة خاطئ» = إعداد خاطئ عندنا ⇒ خطأ نهائي مخصّص."""
    client = make_client(json_handler({"error": "Incorrect service ID"}))
    with pytest.raises(ProviderServiceMismatchError):
        await client.add_order(provider_service_id="999", link="https://x.test/u", quantity=100)
    await client.close()


async def test_unknown_error_text_is_permanent() -> None:
    """رفض صريح غير مصنّف = خطأ نهائي (لا إعادة محاولة بلا جدوى)."""
    client = make_client(json_handler({"error": "Link is not valid for this service"}))
    with pytest.raises(ProviderPermanentError):
        await client.add_order(provider_service_id="55", link="bad-link", quantity=100)
    await client.close()


async def test_rate_limit_text_is_temporary() -> None:
    """نص يدل على ضغط مؤقت ⇒ خطأ مؤقت لا نهائي."""
    client = make_client(json_handler({"error": "Too many requests, try again later"}))
    with pytest.raises(ProviderTemporaryError):
        await client.get_balance()
    await client.close()


async def test_http_500_during_add_is_uncertain() -> None:
    """خطأ 500 بعد إرسال الطلب: قد يكون سُجّل عندهم ⇒ غير مؤكد."""
    client = make_client(json_handler({"error": "boom"}, status=500))
    with pytest.raises(ProviderUncertainError):
        await client.add_order(provider_service_id="55", link="https://x.test/u", quantity=100)
    await client.close()


async def test_http_500_during_status_is_temporary() -> None:
    """خطأ 500 أثناء فحص الحالة = مؤقت."""
    client = make_client(json_handler({"error": "boom"}, status=500))
    with pytest.raises(ProviderTemporaryError):
        await client.get_order_status("1")
    await client.close()


async def test_http_403_is_permanent() -> None:
    """رفض 403 (مفتاح خاطئ مثلاً) = خطأ نهائي يحتاج تدخل الأدمن."""
    client = make_client(json_handler({"error": "forbidden"}, status=403))
    with pytest.raises(ProviderPermanentError):
        await client.get_balance()
    await client.close()


async def test_non_json_response_is_temporary() -> None:
    """صفحة HTML بدل JSON (لوحة تحت الصيانة) = خطأ مؤقت برسالة مفهومة."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>maintenance</html>")

    client = make_client(handler)
    with pytest.raises(ProviderTemporaryError):
        await client.get_balance()
    await client.close()


# ======================================================================== #
#                            حالة الطلب والرصيد                            #
# ======================================================================== #


async def test_status_parses_numbers_and_computes_delivered() -> None:
    """المنفَّذ يُحسب من الكمية والمتبقي حين لا يرسله المزود."""
    client = make_client(
        json_handler(
            {
                "charge": "0.5000",
                "start_count": "120",
                "status": "In progress",
                "remains": "400",
                "quantity": "1000",
                "currency": "USD",
            }
        )
    )
    status = await client.get_order_status("23501")

    assert status.raw_status == "In progress"
    assert status.start_count == 120
    assert status.remains == 400
    assert status.delivered == 600
    assert status.charge_units == 5_000
    await client.close()


async def test_multi_status_parses_dict_and_skips_errors() -> None:
    """الاستعلام الجماعي يقرأ ما نجح ويتخطّى ما فيه خطأ بدل إسقاط الدفعة."""
    handler = json_handler(
        {
            "1": {"status": "Completed", "remains": "0", "quantity": "100"},
            "2": {"error": "Incorrect order ID"},
            "3": {"status": "Pending", "remains": "50", "quantity": "50"},
        }
    )
    client = make_client(handler)
    results = await client.get_multi_status(["1", "2", "3"])

    assert set(results) == {"1", "3"}
    assert results["1"].raw_status == "Completed"
    assert results["1"].delivered == 100
    assert "orders=1%2C2%2C3" in handler.captured["content"]
    await client.close()


async def test_balance_is_parsed_into_units() -> None:
    """الرصيد يُحوَّل إلى وحدات صحيحة (لا عوائم في المال)."""
    client = make_client(json_handler({"balance": "100.4567", "currency": "USD"}))
    balance = await client.get_balance()

    assert balance.amount_units == 1_004_567
    assert balance.currency == "USD"
    await client.close()


async def test_balance_without_number_is_temporary_error() -> None:
    """رصيد غير مفهوم لا يُترجم إلى صفر — يُرفع خطأ بدل تضليل الأدمن."""
    client = make_client(json_handler({"balance": "n/a"}))
    with pytest.raises(ProviderTemporaryError):
        await client.get_balance()
    await client.close()


# ======================================================================== #
#                             قائمة الخدمات                                #
# ======================================================================== #


async def test_services_list_is_parsed_and_invalid_entries_skipped() -> None:
    """الخدمات الناقصة تُتخطّى: استيراد خدمة بلا حدود = طلب يفشل عند أول عميل."""
    client = make_client(
        json_handler(
            [
                {
                    "service": 11,
                    "name": "Instagram Followers",
                    "rate": "0.9000",
                    "min": "50",
                    "max": "100000",
                    "category": "Instagram",
                    "type": "Default",
                    "refill": True,
                },
                {"service": 12, "name": "بلا سعر", "min": "10", "max": "100"},
                {"service": 13, "name": "حدود مقلوبة", "rate": "1.0", "min": "100", "max": "10"},
                "نص غريب",
            ]
        )
    )
    items = await client.get_services()

    assert len(items) == 1
    item = items[0]
    assert item.provider_service_id == "11"
    assert item.rate_per_1000_units == 9_000
    assert item.min_quantity == 50
    assert item.max_quantity == 100_000
    assert item.refill is True
    await client.close()


async def test_services_error_response_raises() -> None:
    """خطأ في قائمة الخدمات يُرفع بدل إرجاع قائمة فارغة مضلِّلة."""
    client = make_client(json_handler({"error": "Invalid API key"}))
    with pytest.raises(ProviderPermanentError):
        await client.get_services()
    await client.close()


# ======================================================================== #
#                                الإلغاء                                   #
# ======================================================================== #


async def test_cancel_returns_false_when_not_supported() -> None:
    """المزود الذي لا يدعم الإلغاء يرد بخطأ ⇒ False لا استثناء."""
    client = make_client(json_handler({"error": "Cancel is not supported"}))
    assert await client.cancel_order("23501") is False
    await client.close()


async def test_cancel_returns_true_on_accept() -> None:
    """قبول الإلغاء يُترجم إلى True."""
    client = make_client(json_handler({"cancel": 1}))
    assert await client.cancel_order("23501") is True
    await client.close()


# ======================================================================== #
#                          عدم تسريب مفتاح API                             #
# ======================================================================== #


async def test_api_key_never_appears_in_error_messages() -> None:
    """رسائل الأخطاء لا تحمل المفتاح أبداً (حتى لو ردّده المزود في استجابته)."""
    client = make_client(json_handler({"error": f"Invalid key {API_KEY}"}, status=200))
    with pytest.raises(ProviderPermanentError) as excinfo:
        await client.get_balance()

    from utils.security import sanitize

    assert API_KEY not in sanitize(str(excinfo.value), client.secrets())
    await client.close()


async def test_secrets_exposes_key_for_sanitizer_only() -> None:
    """`secrets()` هي القناة الوحيدة لتمرير المفتاح إلى أداة التنقية."""
    client = make_client(json_handler({"balance": "1.0"}))
    assert client.secrets() == (API_KEY,)
    await client.close()
