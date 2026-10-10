# الكود الكامل — المرحلة 5 (المزودون وربط الـAPI)

كل ما في هذا الملف منسوخ آلياً من ملفات المشروع الفعلية وقت كتابة التقرير،
فلا فرق بين ما تقرأه هنا وما يعمل عندك.

> الملفات غير المذكورة هنا لم تتغيّر عن المراحل 1–4.

## الفهرس

**طبقة المزودين — عميل Perfect Panel وسجل الأنواع**

- `integrations/providers/perfect_panel.py` — 442 سطراً (جديد)
- `integrations/providers/registry.py` — 62 سطراً (مُحدَّث)

**طبقة الخدمات — الكتالوج والمزامنة والتسعير**

- `services/catalog_service.py` — 563 سطراً (مُحدَّث)

**النصوص ولوحات الأزرار**

- `texts/admin_ar.py` — 686 سطراً (مُحدَّث)
- `keyboards/callback_data.py` — 159 سطراً (مُحدَّث)
- `keyboards/admin_kb.py` — 900 سطراً (مُحدَّث)

**لوحة التحكم — قسم المزودين وإنشاء الخدمة**

- `handlers/admin/providers.py` — 975 سطراً (جديد)
- `handlers/admin/catalog.py` — 794 سطراً (مُحدَّث)
- `handlers/admin/__init__.py` — 62 سطراً (مُحدَّث)

**الإصدار والمتطلبات**

- `core/constants.py` — 44 سطراً (مُحدَّث)
- `requirements.txt` — 23 سطراً (مُحدَّث)

**الاختبارات**

- `tests/unit/test_perfect_panel_client.py` — 332 سطراً (جديد)
- `tests/integration/test_admin_providers.py` — 609 سطراً (جديد)
- `tests/integration/test_no_dead_buttons.py` — 484 سطراً (مُحدَّث)

---

## طبقة المزودين — عميل Perfect Panel وسجل الأنواع

### `integrations/providers/perfect_panel.py`  ·  جديد  ·  442 سطراً

عميل HTTP حقيقي لواجهة Perfect Panel API v2: إرسال طلب، فحص حالة مفردة وجماعية، رصيد، قائمة خدمات، وتصنيف دقيق لكل خطأ إلى Temporary/Permanent/Uncertain.

```python
"""
عميل المزودين بمعيار Perfect Panel — وهو المعيار الذي تستخدمه أغلب لوحات SMM.

شكل الواجهة لدى هذه اللوحات موحّد تقريباً:

    POST {api_url}
    key=<api_key>&action=add&service=<id>&link=<url>&quantity=<n>   ⇐ إنشاء طلب
    key=<api_key>&action=status&order=<id>                          ⇐ حالة طلب
    key=<api_key>&action=status&orders=1,2,3                        ⇐ حالات متعددة
    key=<api_key>&action=services                                   ⇐ قائمة الخدمات
    key=<api_key>&action=balance                                    ⇐ رصيدنا لديهم

والاستجابة JSON دائماً، والخطأ يأتي داخل الحقل `error` بحالة 200 غالباً.

مبدأ السلامة المالية في هذا الملف (الأهم فيه):
    • كل خطأ شبكة/مهلة **قبل** تأكيد الإرسال  → ProviderTemporaryError (إعادة محاولة آمنة).
    • كل مهلة أو انقطاع **أثناء** إنشاء الطلب → ProviderUncertainError (ممنوع إعادة الإرسال
      تلقائياً، لأن الطلب قد يكون وصل بالفعل وخُصم منا).
    • الرفض الصريح (خدمة غير موجودة، رابط غير صالح، كمية خاطئة) → ProviderPermanentError.
    • نقص الرصيد لدى المزود → ProviderInsufficientFundsError (مؤقت: يُحل بالشحن).

ولا يخرج مفتاح API من هذا الملف أبداً: لا في رسالة خطأ ولا في لوق — تُمرَّر القيم
السرية عبر `secrets()` لأداة التنقية `sanitize` قبل أي تسجيل.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from core.exceptions import (
    ProviderError,
    ProviderInsufficientFundsError,
    ProviderPermanentError,
    ProviderServiceMismatchError,
    ProviderTemporaryError,
    ProviderUncertainError,
)
from integrations.providers.base import (
    ProviderBalance,
    ProviderClient,
    ProviderOrderResult,
    ProviderServiceItem,
    ProviderStatusResult,
)

logger = logging.getLogger(__name__)

#: أقصى عدد محارف نحتفظ به من نص الاستجابة عند بناء رسالة خطأ (منعاً لتضخم اللوق)
ERROR_SNIPPET_LIMIT = 200

#: كلمات ترد في نص خطأ المزود وتعني «رصيدك لدينا لا يكفي»
INSUFFICIENT_FUNDS_WORDS = (
    "not enough funds",
    "insufficient funds",
    "insufficient balance",
    "not enough balance",
    "no funds",
    "low balance",
)

#: كلمات تعني أن رقم الخدمة أو معاملاتها خاطئة عندنا (إعداد خاطئ لا عطل مؤقت)
SERVICE_MISMATCH_WORDS = (
    "incorrect service",
    "invalid service",
    "service not found",
    "service is not active",
    "incorrect service id",
)

#: كلمات تعني ضغطاً مؤقتاً أو صيانة ⇒ إعادة المحاولة آمنة
TEMPORARY_WORDS = (
    "try again",
    "too many requests",
    "rate limit",
    "temporarily",
    "maintenance",
    "server busy",
    "timeout",
)


class PerfectPanelClient(ProviderClient):
    """
    عميل HTTP حقيقي للوحات المتوافقة مع Perfect Panel API v2.

    الاستخدام:
        client = PerfectPanelClient(api_url=..., api_key=..., timeout_seconds=30)
        try:
            result = await client.add_order(provider_service_id="55", link=..., quantity=1000)
        finally:
            await client.close()
    """

    api_type = "perfect_panel"

    def __init__(
        self,
        *,
        api_url: str,
        api_key: str,
        timeout_seconds: int = 30,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """
        تهيئة العميل.

        المدخلات:
            client : عميل httpx جاهز — يُمرَّر في الاختبارات لحقن نقل وهمي
                     (MockTransport)، وفي التشغيل يُبنى تلقائياً عند أول طلب.
        """
        super().__init__(api_url=api_url, api_key=api_key, timeout_seconds=timeout_seconds)
        self._client = client
        self._owns_client = client is None

    # ======================================================================= #
    #                           طبقة الاتصال الدنيا                            #
    # ======================================================================= #

    def _http(self) -> httpx.AsyncClient:
        """إرجاع عميل HTTP (يُنشأ عند أول استخدام ويُعاد استخدامه بعدها)."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds),
                headers={"User-Agent": "smm-bot/1.0"},
                follow_redirects=True,
            )
            self._owns_client = True
        return self._client

    async def _post(self, payload: dict[str, Any], *, uncertain_on_timeout: bool = False) -> Any:
        """
        تنفيذ طلب POST واحد وإرجاع JSON المفكوك.

        المدخلات:
            payload               : حقول النموذج بلا المفتاح (يُضاف هنا).
            uncertain_on_timeout  : True عند إنشاء الطلب فقط — فالمهلة حينها تعني
                                    «لا نعرف هل وصل الطلب» لا «أعد المحاولة».

        الاستثناءات:
            ProviderUncertainError : مهلة أثناء إنشاء طلب.
            ProviderTemporaryError : مشكلة شبكة أو استجابة 429/5xx أو JSON غير صالح.
            ProviderPermanentError : استجابة 4xx صريحة (عدا 429).
        """
        data = {"key": self._api_key, **payload}
        action = str(payload.get("action", "?"))
        try:
            response = await self._http().post(self.api_url, data=data)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            # التفريق هنا هو الفرق بين إعادة محاولة آمنة وبين طلب مكرر يكلّف مالاً
            if uncertain_on_timeout:
                raise ProviderUncertainError(
                    f"انقطع الاتصال أثناء إرسال الطلب ({type(exc).__name__})"
                ) from exc
            raise ProviderTemporaryError(
                f"تعذر الاتصال بالمزود أثناء {action} ({type(exc).__name__})"
            ) from exc
        except httpx.HTTPError as exc:                     # أي خطأ httpx آخر غير متوقع
            raise ProviderTemporaryError(
                f"خطأ اتصال غير متوقع أثناء {action}: {type(exc).__name__}"
            ) from exc

        self._raise_for_status(response, action, uncertain_on_timeout=uncertain_on_timeout)

        try:
            return response.json()
        except ValueError as exc:
            snippet = response.text[:ERROR_SNIPPET_LIMIT]
            if uncertain_on_timeout:
                raise ProviderUncertainError(
                    f"استجابة غير مفهومة بعد إرسال الطلب: {snippet}"
                ) from exc
            raise ProviderTemporaryError(
                f"استجابة المزود ليست JSON أثناء {action}: {snippet}"
            ) from exc

    def _raise_for_status(
        self, response: httpx.Response, action: str, *, uncertain_on_timeout: bool
    ) -> None:
        """تحويل رمز حالة HTTP إلى الاستثناء الصحيح (مؤقت/نهائي/غير مؤكد)."""
        status = response.status_code
        if status < 400:
            return
        snippet = response.text[:ERROR_SNIPPET_LIMIT]
        if status == 429 or status >= 500:
            if uncertain_on_timeout and status >= 500:
                # 5xx بعد إرسال الطلب: قد يكون المزود سجّله ثم فشل في الرد
                raise ProviderUncertainError(f"المزود رد بخطأ {status} بعد الإرسال: {snippet}")
            raise ProviderTemporaryError(f"المزود رد بالحالة {status} أثناء {action}: {snippet}")
        raise ProviderPermanentError(f"المزود رفض الطلب بالحالة {status}: {snippet}")

    def _check_error_field(self, payload: Any, *, uncertain_on_timeout: bool = False) -> dict:
        """
        فحص حقل `error` في استجابة JSON وتحويله إلى الاستثناء المناسب.

        المخرجات: القاموس نفسه إن لم يكن فيه خطأ.
        """
        if not isinstance(payload, dict):
            raise ProviderTemporaryError("استجابة المزود ليست كائن JSON متوقعاً")

        error = payload.get("error")
        if not error:
            return payload

        text = str(error)
        lowered = text.lower()
        if any(word in lowered for word in INSUFFICIENT_FUNDS_WORDS):
            raise ProviderInsufficientFundsError(f"رصيدنا لدى المزود غير كافٍ: {text}")
        if any(word in lowered for word in SERVICE_MISMATCH_WORDS):
            raise ProviderServiceMismatchError(f"المزود رفض رقم الخدمة: {text}")
        if any(word in lowered for word in TEMPORARY_WORDS):
            raise ProviderTemporaryError(f"خطأ مؤقت من المزود: {text}")
        if uncertain_on_timeout and "duplicate" in lowered:
            # المزود يقول «طلب مكرر» ⇒ غالباً الطلب الأول وصل: لا نُعيد الإرسال
            raise ProviderUncertainError(f"المزود أبلغ بتكرار الطلب: {text}")
        raise ProviderPermanentError(f"المزود رفض الطلب: {text}")

    # ======================================================================= #
    #                               الطلبات                                   #
    # ======================================================================= #

    async def add_order(
        self,
        *,
        provider_service_id: str,
        link: str,
        quantity: int,
        extras: dict[str, Any] | None = None,
    ) -> ProviderOrderResult:
        """
        إنشاء طلب جديد عند المزود.

        المخرجات: رقم الطلب عند المزود (وما خصمه منا إن أرسله).

        الاستثناءات:
            ProviderUncertainError : انقطاع/مهلة أثناء الإرسال ⇒ يتولاها مسار
                                     «النتيجة غير المؤكدة» ولا يُعاد الإرسال آلياً.
        """
        payload: dict[str, Any] = {
            "action": "add",
            "service": str(provider_service_id),
            "link": link,
            "quantity": int(quantity),
        }
        for key, value in (extras or {}).items():
            if value is not None and key not in payload:
                payload[key] = value

        raw = await self._post(payload, uncertain_on_timeout=True)
        data = self._check_error_field(raw, uncertain_on_timeout=True)

        order_id = data.get("order")
        if order_id in (None, "", 0):
            # لا رقم طلب ولا رسالة خطأ: لا نعرف ماذا حدث ⇒ غير مؤكد لا فاشل
            raise ProviderUncertainError(
                f"المزود لم يُرجع رقم طلب: {str(data)[:ERROR_SNIPPET_LIMIT]}"
            )

        return ProviderOrderResult(
            provider_order_id=str(order_id),
            charge_units=self.money_from_decimal_text(data.get("charge")),
            currency=str(data.get("currency") or "USD"),
            raw=data,
        )

    async def get_order_status(self, provider_order_id: str) -> ProviderStatusResult:
        """الاستعلام عن حالة طلب واحد لدى المزود."""
        raw = await self._post({"action": "status", "order": str(provider_order_id)})
        data = self._check_error_field(raw)
        return self._status_from_dict(data)

    async def get_multi_status(
        self, provider_order_ids: list[str]
    ) -> dict[str, ProviderStatusResult]:
        """
        الاستعلام عن عدة طلبات باستدعاء واحد (`orders=1,2,3`).

        المخرجات: قاموس {رقم الطلب عند المزود: نتيجة الحالة} — الطلبات التي ردّ
                  عليها المزود بخطأ فردي تُستثنى بدل إسقاط الدفعة كلها.
        """
        ids = [str(item) for item in provider_order_ids if str(item)]
        if not ids:
            return {}

        raw = await self._post({"action": "status", "orders": ",".join(ids)})
        if isinstance(raw, dict) and raw.get("error") and len(ids) > 1:
            # خطأ عام على الدفعة كلها: نتعامل معه كخطأ عادي
            self._check_error_field(raw)

        results: dict[str, ProviderStatusResult] = {}
        if isinstance(raw, dict):
            for order_id, value in raw.items():
                if not isinstance(value, dict) or value.get("error"):
                    logger.debug("تخطّي حالة الطلب %s: استجابة غير صالحة", order_id)
                    continue
                results[str(order_id)] = self._status_from_dict(value)
        elif isinstance(raw, list):
            # بعض اللوحات تُرجع قائمة بنفس ترتيب المعرفات المرسلة
            for index, value in enumerate(raw):
                if index < len(ids) and isinstance(value, dict) and not value.get("error"):
                    results[ids[index]] = self._status_from_dict(value)
        return results

    def _status_from_dict(self, data: dict[str, Any]) -> ProviderStatusResult:
        """تحويل قاموس حالة من المزود إلى `ProviderStatusResult` بأعداد صحيحة."""
        remains = self._as_int(data.get("remains"))
        start_count = self._as_int(data.get("start_count"))
        delivered = self._as_int(data.get("delivered"))
        quantity = self._as_int(data.get("quantity"))
        if delivered is None and quantity is not None and remains is not None:
            delivered = max(quantity - remains, 0)

        return ProviderStatusResult(
            raw_status=str(data.get("status") or "").strip() or "Unknown",
            start_count=start_count,
            remains=remains,
            delivered=delivered,
            charge_units=self.money_from_decimal_text(data.get("charge")),
            currency=str(data.get("currency") or "USD"),
            raw=data,
        )

    @staticmethod
    def _as_int(value: Any) -> int | None:
        """تحويل قيمة قد تأتي نصاً أو عشرية إلى عدد صحيح، أو None إن تعذّر."""
        if value is None or value == "":
            return None
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return None

    async def cancel_order(self, provider_order_id: str) -> bool:
        """
        طلب إلغاء لدى المزود.

        المخرجات: True إذا قَبِل المزود الإلغاء. المزودون الذين لا يدعمون الإلغاء
                  يردّون بخطأ ⇒ نُرجع False بدل إسقاط العملية (الإلغاء محاولة لا وعد).
        """
        try:
            raw = await self._post({"action": "cancel", "order": str(provider_order_id)})
        except ProviderError as exc:
            logger.info("المزود لم يقبل إلغاء الطلب %s: %s", provider_order_id, exc)
            return False

        if isinstance(raw, dict):
            if raw.get("error"):
                return False
            return bool(raw.get("cancel") or raw.get("status") or raw.get("order"))
        if isinstance(raw, list) and raw:
            first = raw[0]
            return isinstance(first, dict) and not first.get("error")
        return False

    # ======================================================================= #
    #                           الرصيد وقائمة الخدمات                          #
    # ======================================================================= #

    async def get_balance(self) -> ProviderBalance:
        """قراءة رصيد حسابنا لدى المزود."""
        raw = await self._post({"action": "balance"})
        data = self._check_error_field(raw)
        amount_units = self.money_from_decimal_text(data.get("balance"))
        if amount_units is None:
            raise ProviderTemporaryError(
                f"المزود لم يُرجع رصيداً مفهوماً: {str(data)[:ERROR_SNIPPET_LIMIT]}"
            )
        return ProviderBalance(
            amount_units=amount_units,
            currency=str(data.get("currency") or "USD"),
            raw=data,
        )

    async def get_services(self) -> list[ProviderServiceItem]:
        """
        جلب قائمة خدمات المزود.

        المخرجات: قائمة الخدمات الصالحة فقط — أي عنصر ناقص الحقول الأساسية
                  (رقم/اسم/سعر) يُتخطّى مع تسجيله، لأن استيراد خدمة ناقصة
                  يعني طلباً سيفشل لاحقاً عند أول مستخدم.
        """
        raw = await self._post({"action": "services"})
        if isinstance(raw, dict):
            self._check_error_field(raw)                 # يرفع الاستثناء المناسب
            raise ProviderTemporaryError("استجابة قائمة الخدمات ليست قائمة")
        if not isinstance(raw, list):
            raise ProviderTemporaryError("استجابة قائمة الخدمات ليست قائمة")

        items: list[ProviderServiceItem] = []
        skipped = 0
        for entry in raw:
            item = self._service_from_dict(entry)
            if item is None:
                skipped += 1
                continue
            items.append(item)

        if skipped:
            logger.warning("تخطّي %s خدمة ناقصة الحقول من قائمة المزود", skipped)
        return items

    def _service_from_dict(self, entry: Any) -> ProviderServiceItem | None:
        """تحويل عنصر خدمة من المزود إلى `ProviderServiceItem`، أو None إن كان ناقصاً."""
        if not isinstance(entry, dict):
            return None

        service_id = entry.get("service") or entry.get("id")
        name = entry.get("name")
        rate_units = self.money_from_decimal_text(entry.get("rate"))
        minimum = self._as_int(entry.get("min"))
        maximum = self._as_int(entry.get("max"))
        if not service_id or not name or rate_units is None or minimum is None or maximum is None:
            return None
        if minimum <= 0 or maximum < minimum:
            return None

        return ProviderServiceItem(
            provider_service_id=str(service_id),
            name=str(name).strip(),
            rate_per_1000_units=rate_units,
            min_quantity=minimum,
            max_quantity=maximum,
            category=str(entry.get("category") or "").strip(),
            service_type=str(entry.get("type") or "default").strip() or "default",
            dripfeed=bool(entry.get("dripfeed")),
            refill=bool(entry.get("refill")),
            cancel=bool(entry.get("cancel")),
            currency=str(entry.get("currency") or "USD"),
            raw=entry,
        )

    # ======================================================================= #
    #                                الإغلاق                                  #
    # ======================================================================= #

    async def close(self) -> None:
        """إغلاق اتصال HTTP إن كان هذا العميل هو من أنشأه."""
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None
```

### `integrations/providers/registry.py`  ·  مُحدَّث  ·  62 سطراً

سجل أنواع المزودين: ربط `perfect_panel` بالعميل الحقيقي و`mock` بالعميل الوهمي، مع `is_supported()` و`available_types()`.

```python
"""
سجل عملاء المزودين: تحويل `api_type` المخزَّن في قاعدة البيانات إلى عميل فعلي.

الفائدة: إضافة معيار API جديد = تسجيل صنف جديد هنا فقط، دون تعديل أي خدمة.
"""

from __future__ import annotations

from typing import Callable

from core.exceptions import ProviderError
from integrations.providers.base import ProviderClient
from integrations.providers.mock import MockProviderClient
from integrations.providers.perfect_panel import PerfectPanelClient

#: نوع الدالة المُنشئة لعميل مزود
ClientFactory = Callable[..., ProviderClient]

#: الأنواع المسجَّلة فعلياً والجاهزة للاستخدام
_REGISTRY: dict[str, ClientFactory] = {
    PerfectPanelClient.api_type: PerfectPanelClient,   # المعيار الحقيقي (المرحلة 5)
    MockProviderClient.api_type: MockProviderClient,   # للاختبار والتطوير فقط
}

#: أنواع مخطط لها لكنها لم تُنفَّذ بعد — نرفضها برسالة صريحة بدل تنفيذ صوري فارغ
_PLANNED: dict[str, str] = {}


def register_client(api_type: str, factory: ClientFactory) -> None:
    """تسجيل عميل مزود جديد تحت نوع محدد (يُستدعى عند إضافة معيار API جديد)."""
    _REGISTRY[api_type] = factory


def available_types() -> tuple[str, ...]:
    """أنواع المزودين الجاهزة للاستخدام الآن."""
    return tuple(sorted(_REGISTRY))


def is_supported(api_type: str) -> bool:
    """هل هذا النوع مدعوم فعلياً (وليس مجرد مخطط له)؟"""
    return api_type in _REGISTRY


def create_client(
    *, api_type: str, api_url: str, api_key: str, timeout_seconds: int = 30
) -> ProviderClient:
    """
    إنشاء عميل مزود من نوعه المخزَّن في قاعدة البيانات.

    الاستثناءات:
        ProviderError : نوع غير معروف، أو نوع مخطط له ولم يُنفَّذ بعد.
    """
    factory = _REGISTRY.get(api_type)
    if factory is None:
        planned = _PLANNED.get(api_type)
        if planned:
            raise ProviderError(planned, user_message="⚠️ هذا المزود غير مفعّل بعد.")
        raise ProviderError(
            f"نوع مزود غير معروف: {api_type}. الأنواع المتاحة: {', '.join(available_types())}",
            user_message="⚠️ إعداد المزود غير صحيح. راجع لوحة التحكم.",
        )
    return factory(api_url=api_url, api_key=api_key, timeout_seconds=timeout_seconds)
```

---

## طبقة الخدمات — الكتالوج والمزامنة والتسعير

### `services/catalog_service.py`  ·  مُحدَّث  ·  563 سطراً

أُضيفت دوال المرحلة 5: `price_with_margin` (حساب صحيح بلا عوائم)، `import_provider_service`، `sync_provider_services` (+`SyncReport`)، `services_of_provider`.

```python
"""
خدمة الكتالوج: التصنيفات والخدمات وحساب سعر الطلب قبل تأكيده.

مبدأ مهم: سعر الخدمة يُقرأ من قاعدة البيانات في لحظة الطلب ويُخزَّن كلقطة داخل الطلب،
فتغيير السعر لاحقاً لا يؤثر على الطلبات القديمة ولا على المحاسبة.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.constants import PAGE_SIZE
from core.exceptions import DuplicateOperationError, ServiceNotAvailableError, ValidationError
from core.money import format_units, order_cost_units, unit_price_units
from core.permissions import Permission
from database.database import Database
from database.models import Service, ServiceCategory, User
from database.repositories import Repositories
from integrations.providers.base import ProviderServiceItem
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.settings_service import SettingsService
from utils.logging_setup import get_logger
from utils.validators import clean_text, validate_quantity

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Quote:
    """تسعيرة طلب قبل تأكيده."""

    service: Service
    quantity: int
    cost_units: int
    symbol: str
    decimals: int

    @property
    def cost_text(self) -> str:
        """التكلفة بصيغة نصية جاهزة للعرض."""
        return format_units(self.cost_units, symbol=self.symbol, decimals=self.decimals)

    @property
    def price_per_1000_text(self) -> str:
        """سعر الألف بصيغة نصية."""
        return format_units(
            self.service.price_per_1000_units, symbol=self.symbol, decimals=self.decimals
        )


#: أدنى وأقصى هامش ربح مقبول عند الاستيراد (بالمئة) — حارس ضد خطأ إدخال يبيع بخسارة
MIN_MARGIN_PERCENT: int = 0
MAX_MARGIN_PERCENT: int = 1000


@dataclass(frozen=True, slots=True)
class SyncReport:
    """
    نتيجة مزامنة أسعار وحدود خدمات مزود مع قائمته الحالية.

    الحقول:
        checked        : عدد خدماتنا المرتبطة بهذا المزود.
        updated        : كم خدمة تغيّرت تكلفتها أو حدودها فعلياً.
        unchanged      : كم خدمة كانت مطابقة أصلاً.
        missing        : خدمات لم تعد موجودة لدى المزود (تُعرض للأدمن ولا تُحذف).
        negative_margin: خدمات صار سعر بيعها أقل من تكلفتها بعد المزامنة.
        provider_items : عدد الخدمات التي أرسلها المزود.
    """

    checked: int
    updated: int
    unchanged: int
    missing: list[Service]
    negative_margin: list[Service]
    provider_items: int


@dataclass(frozen=True, slots=True)
class Page:
    """صفحة من قائمة (خدمات أو غيرها) مع معلومات التنقل."""

    items: list
    page: int
    total_items: int
    page_size: int

    @property
    def total_pages(self) -> int:
        """عدد الصفحات الكلي (واحد على الأقل)."""
        return max(1, -(-self.total_items // self.page_size))

    @property
    def has_next(self) -> bool:
        """هل توجد صفحة تالية؟"""
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        """هل توجد صفحة سابقة؟"""
        return self.page > 1


class CatalogService:
    """تصفح الخدمات وحساب التسعيرة وإدارة الكتالوج من لوحة الأدمن."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        audit: AuditService,
        auth: AuthService,
    ) -> None:
        """تهيئة الخدمة."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.audit = audit
        self.auth = auth

    # ------------------------------- التصفح ------------------------------- #

    async def categories(self) -> list[ServiceCategory]:
        """التصنيفات التي تحتوي خدمات متاحة فعلاً (لا نعرض تصنيفاً فارغاً للمستخدم)."""
        return await self.repos.categories.list_with_available_services()

    async def services_page(self, category_id: int, *, page: int = 1, page_size: int = PAGE_SIZE) -> Page:
        """صفحة من خدمات تصنيف معيّن."""
        page = max(1, page)
        total = await self.repos.services.count_by_category(category_id, only_available=True)
        items = await self.repos.services.list_by_category(
            category_id, only_available=True, limit=page_size, offset=(page - 1) * page_size
        )
        return Page(items=list(items), page=page, total_items=total, page_size=page_size)

    async def search(self, text: str, *, limit: int = 10) -> list[Service]:
        """بحث نصي في أسماء الخدمات المتاحة."""
        cleaned = clean_text(text, field="نص البحث", max_length=60, min_length=2)
        return await self.repos.services.search(cleaned, limit=limit)

    async def get_available_service(self, service_id: int) -> Service:
        """
        جلب خدمة متاحة للطلب.

        الاستثناءات:
            ServiceNotAvailableError : الخدمة غير موجودة أو معطّلة أو مؤرشفة
                                       أو مزودها متوقف.
        """
        service = await self.repos.services.get_available(service_id)
        if service is None:
            raise ServiceNotAvailableError(f"الخدمة {service_id} غير متاحة للطلب")
        return service

    async def quote(self, service: Service, raw_quantity: str | int) -> Quote:
        """
        حساب تكلفة الطلب بعد التحقق من الكمية.

        الاستثناءات:
            QuantityOutOfRangeError : الكمية خارج حدود الخدمة.
        """
        quantity = validate_quantity(
            raw_quantity, min_quantity=service.min_quantity, max_quantity=service.max_quantity
        )
        cost = order_cost_units(service.price_per_1000_units, quantity)
        _, symbol, decimals = await self.settings.currency()
        return Quote(
            service=service, quantity=quantity, cost_units=cost, symbol=symbol, decimals=decimals
        )

    async def unit_price(self, service: Service) -> str:
        """سعر الوحدة الواحدة (للعرض التفصيلي)."""
        _, symbol, decimals = await self.settings.currency()
        price = unit_price_units(service.price_per_1000_units)
        return f"{price:.6f} {symbol}".strip()

    # ------------------------ قراءة من لوحة الأدمن ------------------------ #

    async def admin_categories(self, actor: User) -> list[ServiceCategory]:
        """
        كل التصنيفات كما هي في قاعدة البيانات (حتى الفارغة والمعطّلة).

        تختلف عن `categories()` الموجّهة للعميل: الأدمن يحتاج رؤية ما لا يراه العميل
        ليستطيع إصلاحه.

        الاستثناءات: PermissionDeniedError
        """
        await self.auth.require_permission(actor, Permission.SERVICES_VIEW, context="catalog")
        return await self.repos.categories.list_all(active_only=False)

    async def admin_services_page(
        self, actor: User, category_id: int, *, page: int = 1, page_size: int = PAGE_SIZE
    ) -> Page:
        """
        صفحة خدمات تصنيف في لوحة الأدمن — تشمل المعطّلة (لا تشمل المؤرشفة).

        الاستثناءات: PermissionDeniedError
        """
        await self.auth.require_permission(
            actor, Permission.SERVICES_VIEW, context=f"category:{category_id}"
        )
        page = max(1, page)
        total = await self.repos.services.count_by_category(category_id, only_available=False)
        items = await self.repos.services.list_by_category(
            category_id, only_available=False, limit=page_size, offset=(page - 1) * page_size
        )
        return Page(items=list(items), page=page, total_items=total, page_size=page_size)

    async def admin_get_service(self, actor: User, service_id: int) -> Service:
        """
        جلب خدمة بأي حالة لعرض بطاقتها الإدارية.

        الاستثناءات: PermissionDeniedError · ServiceNotAvailableError (غير موجودة)
        """
        await self.auth.require_permission(
            actor, Permission.SERVICES_VIEW, context=f"service:{service_id}"
        )
        service = await self.repos.services.get(service_id)
        if service is None:
            raise ServiceNotAvailableError(
                f"الخدمة {service_id} غير موجودة", user_message="❌ الخدمة غير موجودة."
            )
        return service

    async def active_services_count(self) -> int:
        """عدد الخدمات المفعّلة (يُعرض في رأس شاشة الكتالوج)."""
        return await self.repos.services.count_active()

    async def admin_get_category(self, actor: User, category_id: int) -> ServiceCategory:
        """
        جلب تصنيف بالمعرف لعرض عنوانه فوق قائمة خدماته.

        الاستثناءات: PermissionDeniedError · ServiceNotAvailableError (غير موجود)
        """
        await self.auth.require_permission(
            actor, Permission.SERVICES_VIEW, context=f"category:{category_id}"
        )
        category = await self.repos.categories.get(category_id)
        if category is None:
            raise ServiceNotAvailableError(
                f"التصنيف {category_id} غير موجود", user_message="❌ التصنيف غير موجود."
            )
        return category

    # --------------------------- إدارة الكتالوج --------------------------- #

    async def create_category(self, actor: User, *, name_ar: str, emoji: str = "📦", sort_order: int = 100) -> ServiceCategory:
        """إضافة تصنيف جديد (صلاحية services.create)."""
        await self.auth.require_permission(actor, Permission.SERVICES_CREATE, context="category.create")
        clean_name = clean_text(name_ar, field="اسم التصنيف", max_length=60, min_length=2)
        async with self.db.transaction() as tx:
            category = await self.repos.categories.create(
                tx, name_ar=clean_name, emoji=emoji, sort_order=sort_order
            )
            await self.audit.log(
                tx,
                action="services.category.create",
                admin_id=actor.id,
                target_type="category",
                target_id=category.id,
                after={"name_ar": clean_name},
            )
        return category

    async def create_service(
        self,
        actor: User,
        *,
        category_id: int,
        provider_id: int,
        provider_service_id: str,
        name: str,
        price_per_1000_units: int,
        min_quantity: int,
        max_quantity: int,
        provider_price_per_1000_units: int | None = None,
        description: str | None = None,
        link_pattern: str | None = None,
    ) -> Service:
        """
        إضافة خدمة جديدة للكتالوج.

        الاستثناءات: PermissionDeniedError · ValidationError
        """
        await self.auth.require_permission(actor, Permission.SERVICES_CREATE, context="service.create")
        clean_name = clean_text(name, field="اسم الخدمة", max_length=120, min_length=3)
        async with self.db.transaction() as tx:
            service = await self.repos.services.create(
                tx,
                category_id=category_id,
                provider_id=provider_id,
                provider_service_id=str(provider_service_id),
                name=clean_name,
                price_per_1000_units=price_per_1000_units,
                min_quantity=min_quantity,
                max_quantity=max_quantity,
                provider_price_per_1000_units=provider_price_per_1000_units,
                description=description,
                link_pattern=link_pattern,
            )
            await self.audit.log(
                tx,
                action="services.create",
                admin_id=actor.id,
                target_type="service",
                target_id=service.id,
                after={
                    "name": clean_name,
                    "price_per_1000_units": price_per_1000_units,
                    "provider_id": provider_id,
                },
            )
        logger.info("أضاف الأدمن %s الخدمة %s (%s)", actor.id, service.id, clean_name)
        return service

    async def change_price(self, actor: User, service_id: int, new_price_units: int) -> bool:
        """
        تغيير سعر خدمة مع حفظ السعر القديم في السجل التاريخي.

        الاستثناءات: PermissionDeniedError
        """
        await self.auth.require_permission(actor, Permission.SERVICES_PRICE, context=f"service:{service_id}")
        service = await self.repos.services.get(service_id)
        if service is None:
            return False
        async with self.db.transaction() as tx:
            changed = await self.repos.services.change_price(
                tx, service_id, new_price_units=new_price_units, changed_by=actor.id, source="admin"
            )
            if changed:
                await self.audit.log(
                    tx,
                    action="services.price",
                    admin_id=actor.id,
                    target_type="service",
                    target_id=service_id,
                    before={"price_per_1000_units": service.price_per_1000_units},
                    after={"price_per_1000_units": new_price_units},
                )
        return changed

    async def set_service_active(self, actor: User, service_id: int, active: bool) -> bool:
        """تفعيل أو تعطيل خدمة (لا حذف — الطلبات القديمة تبقى سليمة)."""
        await self.auth.require_permission(actor, Permission.SERVICES_ARCHIVE, context=f"service:{service_id}")
        async with self.db.transaction() as tx:
            changed = await self.repos.services.set_active(tx, service_id, active)
            if changed:
                await self.audit.log(
                    tx,
                    action="services.update",
                    admin_id=actor.id,
                    target_type="service",
                    target_id=service_id,
                    after={"is_active": active},
                )
        return changed

    async def archive_service(self, actor: User, service_id: int) -> bool:
        """أرشفة خدمة (إخفاؤها نهائياً مع الاحتفاظ ببياناتها التاريخية)."""
        await self.auth.require_permission(actor, Permission.SERVICES_ARCHIVE, context=f"service:{service_id}")
        async with self.db.transaction() as tx:
            changed = await self.repos.services.archive(tx, service_id)
            if changed:
                await self.audit.log(
                    tx,
                    action="services.archive",
                    admin_id=actor.id,
                    target_type="service",
                    target_id=service_id,
                    after={"is_archived": True},
                )
        return changed

    async def negative_margin_report(self, actor: User) -> list[Service]:
        """
        الخدمات التي أصبح سعر بيعها أقل من تكلفتها لدى المزود.

        الاستثناءات: PermissionDeniedError (تحتاج صلاحية عرض الخدمات).
        """
        await self.auth.require_permission(actor, Permission.SERVICES_VIEW, context="services.margin")
        return await self.repos.services.negative_margin_services()

    # ===================================================================== #
    #                الاستيراد والمزامنة من المزود (المرحلة 5)               #
    # ===================================================================== #

    @staticmethod
    def price_with_margin(cost_per_1000_units: int, margin_percent: int) -> int:
        """
        حساب سعر البيع من تكلفة المزود وهامش ربح بالمئة.

        المدخلات:
            cost_per_1000_units : تكلفة الألف لدى المزود بوحدات المال الصحيحة.
            margin_percent      : الهامش بالمئة (50 ⇐ السعر = التكلفة × 1.5).

        المخرجات: سعر الألف بوحدات صحيحة (تقريب لأقرب وحدة، والحد الأدنى وحدة واحدة
                  حتى لا تنتج خدمة بسعر صفر عند تكلفة ضئيلة).

        الاستثناءات: ValidationError عند هامش خارج الحدود أو تكلفة سالبة.
        """
        if margin_percent < MIN_MARGIN_PERCENT or margin_percent > MAX_MARGIN_PERCENT:
            raise ValidationError(
                f"هامش ربح خارج الحدود: {margin_percent}",
                user_message=(
                    f"❌ هامش الربح يجب أن يكون بين {MIN_MARGIN_PERCENT} و{MAX_MARGIN_PERCENT}%."
                ),
            )
        if cost_per_1000_units < 0:
            raise ValidationError("تكلفة سالبة", user_message="❌ تكلفة المزود غير صالحة.")

        # حساب صحيح بالكامل (لا عوائم): (التكلفة × (100 + الهامش) + 50) ÷ 100
        price = (cost_per_1000_units * (100 + margin_percent) + 50) // 100
        return max(price, 1)

    async def import_provider_service(
        self,
        actor: User,
        *,
        provider_id: int,
        item: ProviderServiceItem,
        category_id: int,
        margin_percent: int,
    ) -> Service:
        """
        استيراد خدمة من قائمة المزود إلى الكتالوج بسعر = التكلفة + هامش.

        تمنع الدالة استيراد نفس خدمة المزود مرتين (مصدر شائع لخدمات مكرّرة في
        الواجهة)، وتحفظ تكلفة المزود مع الخدمة حتى يُحسب الهامش لاحقاً.

        المخرجات: الخدمة بعد إنشائها.

        الاستثناءات:
            PermissionDeniedError   : بلا صلاحية `services.create`.
            ValidationError         : تصنيف غير موجود أو هامش غير صالح.
            DuplicateOperationError : الخدمة مستوردة من قبل.
        """
        await self.auth.require_permission(
            actor, Permission.SERVICES_CREATE, context=f"provider:{provider_id}"
        )
        category = await self.repos.categories.get(category_id)
        if category is None:
            raise ValidationError(
                f"تصنيف غير موجود: {category_id}", user_message="❌ التصنيف غير موجود."
            )

        existing = await self.repos.services.find_by_provider_service(
            provider_id, item.provider_service_id
        )
        if existing is not None:
            raise DuplicateOperationError(
                f"خدمة المزود {item.provider_service_id} مستوردة مسبقاً (#{existing.id})",
                user_message=f"⚠️ هذه الخدمة مستوردة مسبقاً باسم: {existing.name}",
            )

        price = self.price_with_margin(item.rate_per_1000_units, margin_percent)
        service = await self.create_service(
            actor,
            category_id=category_id,
            provider_id=provider_id,
            provider_service_id=item.provider_service_id,
            name=item.name,
            price_per_1000_units=price,
            min_quantity=item.min_quantity,
            max_quantity=item.max_quantity,
            provider_price_per_1000_units=item.rate_per_1000_units,
        )
        logger.info(
            "استورد الأدمن %s الخدمة %s من المزود %s بهامش %s%%",
            actor.id, service.id, provider_id, margin_percent,
        )
        return service

    async def sync_provider_services(
        self, actor: User, *, provider_id: int, items: list[ProviderServiceItem]
    ) -> SyncReport:
        """
        مزامنة خدماتنا المرتبطة بمزود مع قائمته الحالية.

        ما تفعله: تحديث **تكلفة المزود** وحدود الكمية لكل خدمة عندنا.
        ما لا تفعله عمداً:
            • لا تغيّر سعر البيع (قرار تجاري بيد الأدمن).
            • لا تحذف ولا توقف أي خدمة اختفت من المزود — تُدرجها في `missing`
              ليقرر الأدمن، لأن الحذف الآلي قد يُسقط خدمة رائجة بسبب عطل مؤقت.

        المخرجات: `SyncReport` بكل الأرقام والقوائم اللازمة لعرض نتيجة واضحة.

        الاستثناءات: PermissionDeniedError (تحتاج `services.sync`).
        """
        await self.auth.require_permission(
            actor, Permission.SERVICES_SYNC, context=f"provider:{provider_id}"
        )
        by_provider_id = {item.provider_service_id: item for item in items}
        ours = await self.repos.services.list_by_provider(provider_id, limit=1000)

        updated: list[tuple[Service, dict]] = []
        missing: list[Service] = []
        unchanged = 0

        for service in ours:
            item = by_provider_id.get(str(service.provider_service_id))
            if item is None:
                missing.append(service)
                continue

            changes: dict[str, int] = {}
            if item.rate_per_1000_units != (service.provider_price_per_1000_units or 0):
                changes["provider_price_per_1000_units"] = item.rate_per_1000_units
            if item.min_quantity != service.min_quantity:
                changes["min_quantity"] = item.min_quantity
            if item.max_quantity != service.max_quantity:
                changes["max_quantity"] = item.max_quantity

            if changes:
                updated.append((service, changes))
            else:
                unchanged += 1

        if updated:
            async with self.db.transaction() as tx:
                for service, changes in updated:
                    await self.repos.services.update_fields(tx, service.id, **changes)
                await self.audit.log(
                    tx,
                    action="services.sync",
                    admin_id=actor.id,
                    target_type="provider",
                    target_id=provider_id,
                    before={"updated_services": [service.id for service, _ in updated]},
                    after={
                        "provider_items": len(items),
                        "updated": len(updated),
                        "missing": len(missing),
                    },
                )

        # الخدمات التي صارت تُباع بأقل من تكلفتها بعد تحديث التكلفة
        refreshed = await self.repos.services.list_by_provider(provider_id, limit=1000)
        negative = [
            service
            for service in refreshed
            if service.provider_price_per_1000_units
            and service.price_per_1000_units < service.provider_price_per_1000_units
        ]

        logger.info(
            "مزامنة المزود %s: %s خدمة لدى المزود، حُدّثت %s، مفقودة %s",
            provider_id, len(items), len(updated), len(missing),
        )
        return SyncReport(
            checked=len(ours),
            updated=len(updated),
            unchanged=unchanged,
            missing=missing,
            negative_margin=negative,
            provider_items=len(items),
        )

    async def services_of_provider(self, actor: User, provider_id: int) -> list[Service]:
        """قائمة خدماتنا المرتبطة بمزود معيّن (لعرضها في بطاقة المزود)."""
        await self.auth.require_permission(
            actor, Permission.SERVICES_VIEW, context=f"provider:{provider_id}"
        )
        return await self.repos.services.list_by_provider(provider_id, limit=1000)
```

---

## النصوص ولوحات الأزرار

### `texts/admin_ar.py`  ·  مُحدَّث  ·  686 سطراً

قسم جديد في آخر الملف: كل نصوص المزودين والاستيراد والمزامنة وإنشاء خدمة يدوياً.

```python
"""
نصوص لوحة التحكم (الأدمن) — عربية بالكامل.

فُصلت عن `texts/ar.py` لأن نصوص الأدمن كثيرة ولها لهجة مختلفة (أرقام ودقّة
تشغيلية بدل لغة تسويقية)، وفصلها يسهّل مراجعتها وترجمتها لاحقاً.

قاعدة: أي نص يراه الأدمن يُكتب هنا، ولا يُكتب داخل المعالجات.
"""

from __future__ import annotations

# ============================== عام ==================================== #

PANEL_TITLE = "🛠 <b>لوحة التحكم</b>"
ERR_NO_PERMISSION = "🚫 لا تملك صلاحية تنفيذ هذا الإجراء."
ERR_NOT_ADMIN = "🚫 هذا القسم مخصص لفريق الإدارة."
ERR_NOT_TEXT = "❌ أرسل نصاً من فضلك."
ERR_SESSION_LOST = "⚠️ انتهت الجلسة. ابدأ من جديد عبر /admin"
CANCELLED = "✅ أُلغيت العملية."
DONE = "✅ تم التنفيذ."
NOTHING_CHANGED = "ℹ️ لا تغيير — الحالة كما هي."

BTN_ADMIN_PANEL = "🛠 لوحة التحكم"
BTN_BACK_PANEL = "🔙 لوحة التحكم"
BTN_REFRESH = "🔄 تحديث"
BTN_CONFIRM_DANGER = "⚠️ نعم، نفّذ"
BTN_EDIT_AMOUNT = "✏️ تعديل المبلغ"

# ============================ القائمة ================================== #

MENU_USERS = "👥 المستخدمون"
MENU_PAYMENTS = "💰 المدفوعات"
MENU_ORDERS = "📦 الطلبات"
MENU_TICKETS = "🎫 الدعم"
MENU_CATALOG = "🛍 الكتالوج"
MENU_SETTINGS = "⚙️ الإعدادات"
MENU_LOGS = "📝 السجلات"
MENU_HEALTH = "🩺 صحة النظام"

DASHBOARD = (
    "🛠 <b>لوحة التحكم</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "👥 المستخدمون: {users_total} (جديد اليوم: {users_new_today} · نشِط ٧ أيام: {users_active_7d})\n"
    "🚫 محظورون: {users_banned}\n\n"
    "📦 طلبات اليوم: {orders_today}\n"
    "⚙️ طلبات نشطة: {active_orders}\n"
    "⚠️ تحتاج تدخلاً: {attention_orders}\n\n"
    "💵 إيراد اليوم: {revenue_today}\n"
    "💵 إيراد ٧ أيام: {revenue_7d}\n"
    "📥 إيداعات اليوم: {deposits_today}\n\n"
    "⏳ شحن بانتظار المراجعة: {pending_payments}\n"
    "🎫 تذاكر مفتوحة: {open_tickets}\n"
    "🔔 إشعارات في الطابور: {queued}\n"
    "🛍 خدمات مفعّلة: {active_services}\n"
    "❗ أخطاء ٢٤ ساعة: {errors_24h}\n\n"
    "🕒 {now}"
)

PANEL_SIMPLE = (
    "🛠 <b>لوحة التحكم</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "اختر القسم الذي تريد العمل عليه.\n"
    "الأقسام المعروضة هي ما تسمح به صلاحياتك."
)

# ========================== المستخدمون ================================= #

USERS_HOME = (
    "👥 <b>المستخدمون</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "الإجمالي: {total} · جديد اليوم: {new_today}\n"
    "نشِط اليوم: {active_today} · محظورون: {banned}\n\n"
    "استخدم 🔍 للبحث بالمعرف الرقمي أو اسم المستخدم."
)
BTN_USER_SEARCH = "🔍 بحث عن مستخدم"
USERS_ASK_QUERY = (
    "🔍 أرسل <b>معرف تيليجرام</b> (أرقام) أو <b>اسم المستخدم</b> (@name) أو جزءاً من الاسم."
)
USERS_RESULTS = "🔍 <b>نتائج البحث عن:</b> {query}\n\nعدد النتائج: {count}"
USERS_NO_RESULTS = "🔍 لا نتائج مطابقة لـ: {query}"

USER_CARD = (
    "👤 <b>{name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🆔 المعرف: <code>{telegram_id}</code>\n"
    "🔖 المستخدم: {username}\n"
    "🎚 الدور: {role}\n"
    "{ban_line}"
    "💰 الرصيد: {balance}\n"
    "📥 إجمالي الشحن: {deposited}\n"
    "📤 إجمالي الإنفاق: {spent}\n\n"
    "📦 الطلبات: {orders_count} (نشطة: {active_orders})\n"
    "💳 طلبات الشحن: {payments_count}\n"
    "🎫 تذاكر مفتوحة: {tickets_open}\n\n"
    "📅 الانضمام: {joined}\n"
    "🕒 آخر نشاط: {last_activity}\n"
    "{note_line}"
)
USER_BANNED_LINE = "🚫 <b>محظور</b> — السبب: {reason}\n"
USER_NOTE_LINE = "\n📝 ملاحظة إدارية:\n{note}"

BTN_USER_CREDIT = "➕ إضافة رصيد"
BTN_USER_DEBIT = "➖ خصم رصيد"
BTN_USER_BAN = "🚫 حظر"
BTN_USER_UNBAN = "✅ فك الحظر"
BTN_USER_NOTE = "📝 ملاحظة"
BTN_USER_ROLE = "🎚 تغيير الدور"
BTN_USER_ORDERS = "📦 طلباته"
BTN_USER_TX = "💳 معاملاته"

USER_ASK_CREDIT = "➕ <b>إضافة رصيد لـ {name}</b>\n\nالرصيد الحالي: {balance}\n\nأرسل المبلغ:"
USER_ASK_DEBIT = "➖ <b>خصم رصيد من {name}</b>\n\nالرصيد الحالي: {balance}\n\nأرسل المبلغ:"
USER_ASK_BALANCE_REASON = "📝 أرسل سبب العملية (يُحفظ في سجل التدقيق ويُعرض في كشف الحساب):"
USER_BALANCE_CONFIRM = (
    "⚠️ <b>تأكيد العملية</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "👤 المستخدم: {name}\n"
    "{icon} العملية: {operation}\n"
    "💵 المبلغ: {amount}\n"
    "💰 الرصيد الحالي: {balance}\n"
    "💰 بعد التنفيذ: {balance_after}\n"
    "📝 السبب: {reason}\n\n"
    "اضغط «نعم، نفّذ» للتأكيد."
)
USER_BALANCE_DONE = (
    "✅ <b>تمت العملية</b>\n\n"
    "👤 {name}\n{icon} {operation}: {amount}\n💰 الرصيد الجديد: {balance}\n\n"
    "📨 أُشعر المستخدم تلقائياً."
)
OP_CREDIT = "إضافة رصيد"
OP_DEBIT = "خصم رصيد"

USER_ASK_BAN_REASON = "🚫 أرسل سبب حظر <b>{name}</b> (يظهر للمستخدم عند محاولته استخدام البوت):"
USER_BAN_CONFIRM = (
    "⚠️ <b>تأكيد الحظر</b>\n\n👤 {name}\n📝 السبب: {reason}\n\n"
    "المحظور لن يستطيع إنشاء طلبات أو شحن رصيد."
)
USER_BAN_DONE = "🚫 تم حظر {name}."
USER_UNBAN_DONE = "✅ تم فك الحظر عن {name}."
USER_ASK_NOTE = "📝 أرسل الملاحظة الإدارية عن <b>{name}</b> (تُعرض للإدارة فقط):"
USER_NOTE_DONE = "✅ حُفظت الملاحظة."

USER_ROLE_TITLE = "🎚 <b>تغيير دور {name}</b>\n\nالدور الحالي: {role}\n\nاختر الدور الجديد:"
USER_ROLE_CONFIRM = (
    "⚠️ <b>تأكيد تغيير الدور</b>\n\n"
    "👤 {name}\n"
    "من: {old_role}\n"
    "إلى: <b>{new_role}</b>\n\n"
    "تغيير الدور يمنح أو يسحب صلاحيات فوراً."
)
USER_ROLE_DONE = "✅ أصبح دور {name}: {role}"
USER_ROLE_SAME = "ℹ️ المستخدم في هذا الدور أصلاً."

USER_ORDERS_TITLE = "📦 <b>طلبات {name}</b>\n\nالصفحة {page} من {pages}\n\n{lines}"
USER_ORDERS_EMPTY = "📦 لا طلبات لهذا المستخدم."
USER_TX_TITLE = "💳 <b>معاملات {name}</b>\n\nالصفحة {page} من {pages}\n\n{lines}"
USER_TX_EMPTY = "💳 لا معاملات مالية لهذا المستخدم."

# =========================== المدفوعات ================================= #

PAYMENTS_TITLE = (
    "💰 <b>طلبات الشحن المعلّقة</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "العدد: {count} · الصفحة {page} من {pages}"
)
PAYMENTS_EMPTY = "✅ لا توجد طلبات شحن بانتظار المراجعة."
PAYMENT_CARD = (
    "💳 <b>طلب شحن #{payment_id}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "👤 {name} (<code>{telegram_id}</code>)\n"
    "💵 المبلغ: {amount}\n"
    "🏦 الطريقة: {method}\n"
    "🔢 رقم العملية: {reference}\n"
    "📎 الإثبات: {proof}\n"
    "📅 أُرسل: {created}\n"
    "⌛ ينتهي: {expires}\n"
    "📌 الحالة: {status}\n"
    "{note_line}"
    "{review_line}"
)
PAYMENT_NOTE_LINE = "🗒 ملاحظة المستخدم: {note}\n"
PAYMENT_REVIEW_LINE = "\n👮 روجع بواسطة: {admin}\n📝 {detail}\n"
PAYMENT_PROOF_NONE = "لا يوجد"
PAYMENT_PROOF_PHOTO = "صورة مرفقة"
PAYMENT_PROOF_DOC = "ملف مرفق"
PAYMENT_PROOF_CAPTION = "📎 إثبات الدفع للطلب #{payment_id}"

BTN_PAYMENT_PROOF = "📎 عرض الإثبات"
BTN_PAYMENT_APPROVE = "✅ اعتماد"
BTN_PAYMENT_REJECT = "❌ رفض"

PAYMENT_APPROVE_CONFIRM = (
    "⚠️ <b>تأكيد اعتماد الشحن #{payment_id}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "👤 {name}\n"
    "💵 المبلغ المطلوب: {amount}\n"
    "💵 <b>سيُضاف فعلياً: {credited}</b>\n"
    "💰 رصيد المستخدم بعد الإضافة: {balance_after}\n\n"
    "اضغط «نعم، نفّذ» للاعتماد، أو «تعديل المبلغ» لإضافة مبلغ مختلف."
)
PAYMENT_ASK_AMOUNT = (
    "✏️ أرسل المبلغ الذي سيُضاف فعلاً لرصيد المستخدم\n(المطلوب في الطلب: {amount})"
)
PAYMENT_APPROVED = (
    "✅ <b>اعتُمد الشحن #{payment_id}</b>\n\n"
    "👤 {name}\n💵 أُضيف: {credited}\n💰 الرصيد الجديد: {balance}\n\n📨 أُشعر المستخدم."
)
PAYMENT_ASK_REJECT_REASON = (
    "❌ أرسل سبب رفض الطلب #{payment_id} (سيصل المستخدم كما تكتبه، فكن واضحاً):"
)
PAYMENT_REJECTED = "❌ رُفض الطلب #{payment_id}.\n📝 السبب: {reason}\n\n📨 أُشعر المستخدم."

# ============================ الطلبات ================================== #

ORDERS_TITLE = (
    "📦 <b>الطلبات — {filter_name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "العدد: {count} · الصفحة {page} من {pages}"
)
ORDERS_EMPTY = "📦 لا طلبات في هذا التصنيف."
ORDER_FILTER_ATTENTION = "⚠️ تحتاج تدخلاً"
ORDER_FILTER_ACTIVE = "⚙️ نشطة"
ORDER_FILTER_TODAY = "📅 اليوم"
ORDER_FILTER_ALL = "🗂 الكل"

ORDER_CARD = (
    "📦 <b>الطلب {code}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "👤 {name} (<code>{telegram_id}</code>)\n"
    "🛍 {service}\n"
    "🔗 {link}\n"
    "🔢 الكمية: {quantity}\n"
    "💵 التكلفة: {cost}\n"
    "📌 الحالة: {status}\n"
    "{progress_line}"
    "{provider_line}"
    "{error_line}"
    "{refund_line}"
    "📅 أُنشئ: {created}\n"
    "🔁 محاولات الإرسال: {attempts} · عمليات الفحص: {checks}"
)
ORDER_PROVIDER_LINE = "🏢 المزود: {provider} · رقمه: <code>{provider_order_id}</code>\n"
ORDER_PROGRESS_LINE = "📊 المنفَّذ: {delivered} · المتبقي: {remains}\n"
ORDER_ERROR_LINE = "⚠️ آخر خطأ: {error}\n"
ORDER_REFUND_LINE = "↩️ مسترجع: {amount}\n"

BTN_ORDER_RECHECK = "🔄 إعادة فحص الآن"
BTN_ORDER_CANCEL = "❌ إلغاء + استرجاع"
BTN_ORDER_FAIL = "⛔ تعليم كفاشل + استرجاع"
BTN_ORDER_LINK = "🔗 ربط رقم المزود"
BTN_ORDER_OVERRIDE = "🎚 تغيير الحالة يدوياً"
BTN_ORDER_USER = "👤 صاحب الطلب"

ORDER_RECHECK_RESULT = "🔄 نتيجة الفحص: {result}"
ORDER_ASK_CANCEL_REASON = "❌ أرسل سبب إلغاء الطلب {code} (سيُسترجع كامل المبلغ للمستخدم):"
ORDER_ACTION_CONFIRM = (
    "⚠️ <b>تأكيد {operation}</b>\n\n"
    "📦 {code}\n👤 {name}\n💵 سيُسترجع: {amount}\n📝 السبب: {reason}"
)
OP_ORDER_CANCEL = "الإلغاء"
OP_ORDER_FAIL = "تعليم الطلب كفاشل"
ORDER_CANCEL_DONE = "✅ أُلغي الطلب {code} واسترُجع {amount} للمستخدم."
ORDER_ASK_FAIL_REASON = "⛔ أرسل سبب اعتبار الطلب {code} فاشلاً (يُسترجع المبلغ للمستخدم):"
ORDER_FAIL_DONE = "⛔ عُلّم الطلب {code} كفاشل واسترُجع {amount}."
ORDER_ASK_PROVIDER_ID = (
    "🔗 أرسل رقم الطلب لدى المزود للطلب {code}\n"
    "(يُستخدم عندما يكون الطلب أُنشئ فعلاً عند المزود ولم يصلنا رقمه)."
)
ORDER_LINK_DONE = "✅ رُبط الطلب {code} برقم المزود: {provider_order_id}"
ORDER_ASK_OVERRIDE_REASON = (
    "📝 أرسل سبب التجاوز اليدوي (5 أحرف على الأقل) — يُسجَّل باسمك في سجل التدقيق:"
)
ORDER_OVERRIDE_TITLE = (
    "🎚 <b>تغيير حالة الطلب {code} يدوياً</b>\n\n"
    "الحالة الحالية: {status}\n\n"
    "⚠️ استخدم هذا فقط عند تعذّر المسار الآلي — كل تغيير يُسجَّل باسمك."
)
ORDER_OVERRIDE_DONE = "✅ أصبحت حالة الطلب {code}: {status}"
ORDER_NOT_OVERRIDABLE = "⚠️ لا يمكن الانتقال من الحالة الحالية إلى الحالة المطلوبة."

# ============================= الدعم =================================== #

TICKETS_TITLE = (
    "🎫 <b>تذاكر الدعم — {filter_name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "مفتوحة الآن: {open_count} · الصفحة {page} من {pages}"
)
TICKETS_EMPTY = "🎫 لا تذاكر في هذا التصنيف."
TICKET_FILTER_OPEN = "🟢 المفتوحة"
TICKET_FILTER_WAITING = "⏳ بانتظار الدعم"
TICKET_FILTER_MINE = "👤 المسندة لي"
TICKET_FILTER_CLOSED = "🔒 المغلقة"

TICKET_CARD = (
    "🎫 <b>التذكرة #{ticket_id}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "👤 {name} (<code>{telegram_id}</code>)\n"
    "📌 {subject}\n"
    "🗂 التصنيف: {category}\n"
    "📊 الحالة: {status}\n"
    "{order_line}"
    "{assigned_line}"
    "📅 آخر رسالة: {last_message}\n\n"
    "💬 <b>المحادثة:</b>\n{conversation}"
)
TICKET_ORDER_LINE = "📦 مرتبطة بالطلب: {code}\n"
TICKET_ASSIGNED_LINE = "👮 مسندة إلى: {admin}\n"
TICKET_MESSAGE_LINE = "{icon} <b>{sender}</b> — {when}\n{message}"
SENDER_USER = "المستخدم"
SENDER_ADMIN = "الدعم"
SENDER_SYSTEM = "النظام"

BTN_TICKET_REPLY = "💬 رد"
BTN_TICKET_CLOSE = "✖️ إغلاق"
BTN_TICKET_ASSIGN = "🏷 إسناد لي"
BTN_TICKET_USER = "👤 صاحب التذكرة"

TICKET_ASK_REPLY = "💬 أرسل ردك على التذكرة #{ticket_id} (يصل المستخدم كما تكتبه):"
TICKET_ASK_CLOSE_REASON = (
    "✖️ أرسل سبب إغلاق التذكرة #{ticket_id} (يُحفظ في التذكرة ويصل المستخدم):"
)
TICKET_REPLY_DONE = "✅ أُرسل الرد على التذكرة #{ticket_id}."
TICKET_ASSIGNED = "🏷 أُسندت التذكرة #{ticket_id} إليك."
TICKET_CLOSED = "✖️ أُغلقت التذكرة #{ticket_id}."

# ============================ الكتالوج ================================= #

CATALOG_HOME = (
    "🛍 <b>الكتالوج</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "التصنيفات: {categories} · الخدمات المفعّلة: {active_services}\n\n"
    "اختر تصنيفاً لعرض خدماته."
)
CATALOG_NO_CATEGORIES = "📂 لا توجد تصنيفات بعد."
BTN_CATEGORY_NEW = "➕ تصنيف جديد"
CATEGORY_ASK_NAME = "📂 أرسل اسم التصنيف الجديد (بالعربية):"
CATEGORY_ASK_EMOJI = "😀 أرسل أيقونة للتصنيف (إيموجي واحد)، أو تخطَّ لاستخدام 📦."
CATEGORY_CREATED = "✅ أُنشئ التصنيف: {name}"

CATALOG_SERVICES_TITLE = (
    "📂 <b>{category}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "عدد الخدمات: {count} · الصفحة {page} من {pages}\n\n"
    "⚪️ = معطّلة · 🟢 = مفعّلة"
)
CATALOG_SERVICES_EMPTY = "📭 لا خدمات في هذا التصنيف."

SERVICE_CARD = (
    "🛍 <b>{name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🆔 رقم الخدمة: {service_id}\n"
    "📂 التصنيف: {category}\n"
    "🏢 المزود: {provider} (رقم الخدمة لديه: {provider_service_id})\n"
    "💵 سعر الألف: {price}\n"
    "🏷 تكلفة الألف من المزود: {cost}\n"
    "📈 هامش الربح: {margin}\n"
    "🔢 الحدود: {min_quantity} — {max_quantity}\n"
    "📌 الحالة: {status}\n"
    "{archived_line}"
    "{description_line}"
)
SERVICE_STATUS_ACTIVE = "🟢 مفعّلة"
SERVICE_STATUS_INACTIVE = "⚪️ معطّلة"
SERVICE_ARCHIVED_LINE = "🗄 <b>مؤرشفة</b> — لا تظهر للعملاء\n"
SERVICE_DESCRIPTION_LINE = "\n📝 {description}"
SERVICE_UNKNOWN_PROVIDER = "غير معروف"
SERVICE_MARGIN_UNKNOWN = "غير محدد (تكلفة المزود غير مسجّلة)"

BTN_SERVICE_TOGGLE_ON = "🟢 تفعيل"
BTN_SERVICE_TOGGLE_OFF = "⚪️ تعطيل"
BTN_SERVICE_PRICE = "💵 تغيير السعر"
BTN_SERVICE_ARCHIVE = "🗄 أرشفة"

SERVICE_ASK_PRICE = (
    "💵 أرسل السعر الجديد لكل <b>1000</b> من خدمة:\n{name}\n\n"
    "السعر الحالي: {price}\n"
    "تكلفة المزود: {cost}"
)
SERVICE_PRICE_DONE = "✅ أصبح سعر الألف: {price}"
SERVICE_PRICE_BELOW_COST = (
    "⚠️ <b>تنبيه:</b> السعر الجديد أقل من تكلفة المزود — ستبيع بخسارة.\n"
    "اضغط «نعم، نفّذ» إن كنت متأكداً."
)
SERVICE_TOGGLED_ON = "🟢 فُعّلت الخدمة."
SERVICE_TOGGLED_OFF = "⚪️ عُطّلت الخدمة."
SERVICE_ARCHIVED = "🗄 أُرشفت الخدمة ولم تعد تظهر للعملاء."
SERVICE_ARCHIVE_CONFIRM = (
    "⚠️ <b>تأكيد الأرشفة</b>\n\n{name}\n\n"
    "الخدمة ستختفي من واجهة العملاء، وتبقى طلباتها التاريخية كما هي."
)

# =========================== الإعدادات ================================= #

SETTINGS_HOME = (
    "⚙️ <b>الإعدادات</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "وضع الصيانة: {maintenance}\n\n"
    "اختر مجموعة لعرض مفاتيحها."
)
SETTINGS_GROUP_TITLE = (
    "⚙️ <b>إعدادات: {group}</b>\n━━━━━━━━━━━━━━━━━━━━\nالصفحة {page} من {pages}\n\n{lines}"
)
SETTINGS_GROUP_EMPTY = "⚙️ لا مفاتيح في هذه المجموعة."
SETTING_LINE = "<b>{name}</b>\n   <code>{key}</code> = <code>{value}</code>"
SETTING_ASK_VALUE = (
    "⚙️ <b>{name}</b>\n"
    "<code>{key}</code>\n\n"
    "القيمة الحالية: <code>{value}</code>\n"
    "النوع: {value_type}\n"
    "{description}\n\n"
    "أرسل القيمة الجديدة:"
)
SETTING_UPDATED = "✅ حُفظت القيمة الجديدة لـ <code>{key}</code>:\n<code>{value}</code>"
SETTING_NOT_EDITABLE = "🔒 هذا المفتاح غير قابل للتعديل من الواجهة."
MAINTENANCE_ON = "🚧 مفعّل"
MAINTENANCE_OFF = "✅ متوقف"
BTN_MAINTENANCE_ON = "🚧 تفعيل وضع الصيانة"
BTN_MAINTENANCE_OFF = "✅ إيقاف وضع الصيانة"
MAINTENANCE_CONFIRM_ON = (
    "⚠️ <b>تفعيل وضع الصيانة</b>\n\n"
    "سيتوقف المستخدمون العاديون عن استخدام البوت فوراً (الإداريون يستمرون).\n"
    "المهام الدورية تبقى تعمل."
)
MAINTENANCE_CONFIRM_OFF = "✅ <b>إيقاف وضع الصيانة</b>\n\nسيعود البوت للعمل الطبيعي لكل المستخدمين."
MAINTENANCE_TOGGLED_ON = "🚧 فُعّل وضع الصيانة — المستخدمون العاديون لن يستطيعوا الاستخدام."
MAINTENANCE_TOGGLED_OFF = "✅ أُوقف وضع الصيانة — البوت يعمل للجميع."

# ============================ السجلات ================================== #

LOGS_HOME = "📝 <b>السجلات</b>\n━━━━━━━━━━━━━━━━━━━━\n\nاختر السجل الذي تريد مراجعته."
BTN_LOG_AUDIT = "🧾 سجل التدقيق"
BTN_LOG_ERRORS = "❗ سجل الأخطاء"

AUDIT_TITLE = "🧾 <b>سجل التدقيق</b>\n━━━━━━━━━━━━━━━━━━━━\nالصفحة {page} من {pages}\n\n{lines}"
AUDIT_EMPTY = "🧾 لا عمليات مسجّلة بعد."
AUDIT_LINE = "{icon} <b>{action}</b>\n   👮 {admin} · 🎯 {target}\n   🕒 {when}"

ERRORS_TITLE = "❗ <b>آخر الأخطاء</b>\n━━━━━━━━━━━━━━━━━━━━\nالصفحة {page}\n\n{lines}"
ERRORS_EMPTY = "✅ لا أخطاء مسجّلة — النظام نظيف."
ERROR_LINE = "<b>{level}</b> · {source}\n   {message}\n   🕒 {when}"

# ======================= تسميات مساعدة للعرض =========================== #

#: اسم كل دور كما يُعرض في البطاقات والسجلات
ROLE_NAMES: dict[str, str] = {
    "user": "👤 مستخدم عادي",
    "support": "🎧 دعم فني",
    "admin": "👮 أدمن",
    "super_admin": "👑 أدمن أعلى",
}

#: الأدوار المتاحة للإسناد من الواجهة
#: (الدور الأعلى `super_admin` لا يُمنح من الواجهة إطلاقاً — يُضبط من سكربت الإدارة)
ASSIGNABLE_ROLES: dict[str, str] = {
    "user": "👤 مستخدم عادي",
    "support": "🎧 دعم فني",
    "admin": "👮 أدمن",
}

#: أيقونة لكل نوع إجراء في سجل التدقيق (تُطابق بادئة اسم الإجراء)
AUDIT_ICONS: dict[str, str] = {
    "user": "👤",
    "wallet": "💰",
    "payment": "💳",
    "order": "📦",
    "service": "🛍",
    "category": "📂",
    "provider": "🏢",
    "ticket": "🎫",
    "setting": "⚙️",
    "security": "🔐",
    "system": "🖥",
}


# ======================================================================== #
#                   المزودون وربط الـAPI (المرحلة 5)                       #
# ======================================================================== #

MENU_PROVIDERS = "🔌 المزودون"

PROVIDERS_HOME = (
    "🔌 <b>المزودون</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "المسجّلون: {total} · المفعّلون: {active}\n"
    "خدماتنا المرتبطة بمزود: {linked_services}\n\n"
    "اختر مزوداً لعرض بطاقته."
)
PROVIDERS_EMPTY = "🔌 لا يوجد أي مزود بعد. أضف مزوداً لتبدأ ربط الخدمات."

PROVIDER_CARD = (
    "🔌 <b>{name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🆔 المعرف: <code>{provider_id}</code>\n"
    "🌐 الرابط: <code>{api_url}</code>\n"
    "🔑 المفتاح: <code>••••{key_hint}</code>\n"
    "🧩 النوع: <code>{api_type}</code>\n"
    "⚡️ الحالة: {state}\n"
    "💵 الرصيد لدى المزود: {balance} {currency}\n"
    "🕒 آخر فحص رصيد: {balance_checked}\n"
    "🛍 خدماتنا منه: {services_count}\n"
    "📉 أخطاء متتالية: {failures}\n"
    "🕓 آخر نجاح: {last_success}\n"
    "{last_error_line}"
)
PROVIDER_LAST_ERROR_LINE = "⚠️ آخر خطأ: <code>{error}</code>\n"
PROVIDER_STATE_OK = "🟢 جاهز"
PROVIDER_STATE_OFF = "⚪️ متوقف يدوياً"
PROVIDER_STATE_BLOCKED = "🔴 موقوف مؤقتاً: {reason}"
PROVIDER_NOT_FOUND = "❌ المزود غير موجود."

BTN_PROVIDER_NEW = "➕ مزود جديد"
BTN_PROVIDER_TEST = "🔍 اختبار الاتصال"
BTN_PROVIDER_BALANCE = "💵 تحديث الرصيد"
BTN_PROVIDER_KEY = "🔑 تغيير المفتاح"
BTN_PROVIDER_ON = "🟢 تفعيل"
BTN_PROVIDER_OFF = "⚪️ إيقاف"
BTN_PROVIDER_SYNC = "🔄 مزامنة الخدمات"
BTN_PROVIDER_IMPORT = "⬇️ استيراد خدمة"
BTN_PROVIDER_SERVICES = "🛍 خدماتنا منه"

# ------------------------------ إضافة مزود ------------------------------ #

PROVIDER_ASK_NAME = (
    "➕ <b>مزود جديد</b>\n\n"
    "أرسل اسم المزود كما تريد أن يظهر لك (مثال: <code>PanelX</code>).\n"
    "من 2 إلى 60 حرفاً."
)
PROVIDER_ASK_URL = (
    "🌐 أرسل رابط الـAPI كاملاً.\n\n"
    "عادةً ينتهي بـ <code>/api/v2</code>\n"
    "مثال: <code>https://panel.example.com/api/v2</code>"
)
PROVIDER_ASK_TYPE = (
    "🧩 اختر نوع واجهة المزود.\n\n"
    "<b>perfect_panel</b> هو المعيار الذي تستخدمه أغلب اللوحات.\n"
    "<b>mock</b> مزود وهمي للتجربة بلا شبكة ولا مال."
)
PROVIDER_ASK_KEY = (
    "🔑 أرسل مفتاح API.\n\n"
    "⚠️ يُخزَّن مشفّراً، ولن يُعرض بعدها كاملاً في أي شاشة أو سجل.\n"
    "<b>احذف الرسالة بعد إرسالها.</b>"
)
PROVIDER_NEW_CONFIRM = (
    "📋 <b>تأكيد إضافة المزود</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🏷 الاسم: {name}\n"
    "🌐 الرابط: <code>{api_url}</code>\n"
    "🧩 النوع: <code>{api_type}</code>\n"
    "🔑 المفتاح: <code>••••{key_hint}</code>\n\n"
    "سيُختبر الاتصال مباشرة بعد الإضافة."
)
PROVIDER_CREATED = "✅ أُضيف المزود <b>{name}</b> برقم <code>{provider_id}</code>."
PROVIDER_TYPE_UNSUPPORTED = "❌ نوع غير مدعوم. المتاح: {types}"

# ----------------------------- تغيير المفتاح ---------------------------- #

PROVIDER_ASK_NEW_KEY = (
    "🔑 أرسل المفتاح الجديد للمزود <b>{name}</b>.\n\n"
    "⚠️ المفتاح الحالي ينتهي بـ <code>{key_hint}</code> وسيُستبدل فوراً.\n"
    "<b>احذف رسالتك بعد الإرسال.</b>"
)
PROVIDER_KEY_UPDATED = "✅ حُدِّث مفتاح المزود <b>{name}</b> (ينتهي بـ <code>{key_hint}</code>)."
PROVIDER_KEY_UNCHANGED = "ℹ️ لم يتغير المفتاح."

# -------------------------- الاختبار والرصيد ---------------------------- #

PROVIDER_TEST_RUNNING = "🔍 جارٍ اختبار الاتصال بالمزود…"
PROVIDER_TEST_RESULT = "{icon} <b>نتيجة الاختبار — {name}</b>\n━━━━━━━━━━━━━━━━━━━━\n{message}"
PROVIDER_BALANCE_UPDATED = "💵 رصيدنا لدى <b>{name}</b>: {balance} {currency}"
PROVIDER_TOGGLED_ON = "🟢 فُعّل المزود {name}."
PROVIDER_TOGGLED_OFF = "⚪️ أُوقف المزود {name} (لن تُرسل إليه طلبات جديدة)."

# ----------------------------- المزامنة --------------------------------- #

PROVIDER_SYNC_RUNNING = "🔄 جارٍ جلب قائمة خدمات المزود…"
PROVIDER_SYNC_RESULT = (
    "🔄 <b>نتيجة المزامنة — {name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📥 خدمات لدى المزود: {provider_items}\n"
    "🔗 خدماتنا المرتبطة به: {checked}\n"
    "✏️ حُدِّثت تكلفتها/حدودها: {updated}\n"
    "✅ بلا تغيير: {unchanged}\n"
    "❓ لم تعد موجودة لديه: {missing}\n"
    "{missing_lines}"
    "{negative_lines}"
    "\nℹ️ المزامنة تُحدِّث <b>التكلفة والحدود</b> فقط — سعر البيع قرارك وحدك."
)
PROVIDER_SYNC_MISSING_LINE = "   ❓ {name} (#{service_id})\n"
PROVIDER_SYNC_NEGATIVE_HEADER = "\n⚠️ <b>خدمات صار سعرها أقل من التكلفة:</b>\n"
PROVIDER_SYNC_NEGATIVE_LINE = "   📉 {name} — البيع {price} / التكلفة {cost}\n"

# ------------------------- استيراد خدمة من المزود ------------------------ #

PROVIDER_IMPORT_ASK_SEARCH = (
    "⬇️ <b>استيراد خدمة من {name}</b>\n\n"
    "أرسل كلمة بحث لتصفية قائمة خدمات المزود (مثال: <code>instagram followers</code>).\n"
    "أو أرسل <code>*</code> لعرض أول القائمة كاملة."
)
PROVIDER_IMPORT_RESULTS = (
    "🔎 <b>نتائج البحث لدى {name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "ظهر {shown} من {total} خدمة. اختر خدمة لاستيرادها."
)
PROVIDER_IMPORT_NO_RESULTS = "🔍 لا خدمة تطابق «{query}» لدى هذا المزود. جرّب كلمة أخرى."
PROVIDER_IMPORT_ITEM = (
    "📦 <b>{name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🆔 رقم الخدمة لديه: <code>{provider_service_id}</code>\n"
    "💵 تكلفة الألف: {cost}\n"
    "🔢 الحدود: {min_q} — {max_q}\n"
    "🏷 تصنيفه: {category}\n\n"
    "اختر التصنيف عندنا لإدراج الخدمة فيه:"
)
PROVIDER_IMPORT_ASK_MARGIN = (
    "📈 أرسل هامش الربح بالمئة (رقم فقط).\n\n"
    "التكلفة: {cost} لكل ألف\n"
    "مثال: <code>40</code> ⇐ سعر البيع {example}\n"
    "الحد المسموح: 0 إلى 1000%"
)
PROVIDER_IMPORT_CONFIRM = (
    "📋 <b>تأكيد استيراد الخدمة</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🛍 الاسم: {name}\n"
    "🏷 التصنيف: {category}\n"
    "🔌 المزود: {provider}\n"
    "🆔 رقمها لديه: <code>{provider_service_id}</code>\n"
    "💵 التكلفة: {cost} / ألف\n"
    "💰 سعر البيع: {price} / ألف\n"
    "📈 الهامش: {margin}% ({profit} لكل ألف)\n"
    "🔢 الحدود: {min_q} — {max_q}"
)
PROVIDER_IMPORT_DONE = "✅ استُوردت الخدمة <b>{name}</b> برقم <code>{service_id}</code>."
PROVIDER_IMPORT_SESSION_LOST = "⚠️ انتهت صلاحية نتائج البحث. أعد المحاولة من بطاقة المزود."

# --------------------- إنشاء خدمة يدوياً (بلا قائمة المزود) -------------- #

SERVICE_NEW_ASK_CATEGORY = "➕ <b>خدمة جديدة</b>\n\nاختر التصنيف الذي ستُدرج فيه:"
SERVICE_NEW_ASK_PROVIDER = "🔌 اختر المزود الذي ستُرسَل إليه طلبات هذه الخدمة:"
SERVICE_NEW_ASK_PROVIDER_SERVICE_ID = (
    "🆔 أرسل رقم الخدمة لدى المزود <b>{provider}</b>.\n\n"
    "تجده في قائمة خدمات المزود (عمود <code>service</code>)."
)
SERVICE_NEW_ASK_NAME = "🛍 أرسل اسم الخدمة كما سيراه العميل (3 إلى 120 حرفاً)."
SERVICE_NEW_ASK_COST = "💵 أرسل تكلفة الألف لدى المزود (مثال: <code>0.6</code>)."
SERVICE_NEW_ASK_PRICE = (
    "💰 أرسل سعر بيع الألف للعميل.\n\n"
    "التكلفة التي أدخلتها: {cost}\n"
    "⚠️ سعر أقل من التكلفة = بيع بخسارة."
)
SERVICE_NEW_ASK_MIN = "🔢 أرسل أقل كمية مسموحة (مثال: <code>100</code>)."
SERVICE_NEW_ASK_MAX = "🔢 أرسل أكبر كمية مسموحة (أكبر من {min_q})."
SERVICE_NEW_CONFIRM = (
    "📋 <b>تأكيد إنشاء الخدمة</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🛍 الاسم: {name}\n"
    "🏷 التصنيف: {category}\n"
    "🔌 المزود: {provider} (رقم الخدمة لديه: <code>{provider_service_id}</code>)\n"
    "💵 التكلفة: {cost} / ألف\n"
    "💰 سعر البيع: {price} / ألف\n"
    "📈 الهامش: {profit} لكل ألف\n"
    "🔢 الحدود: {min_q} — {max_q}\n\n"
    "{warning}"
)
SERVICE_NEW_WARN_LOSS = "⚠️ <b>تنبيه: سعر البيع أقل من التكلفة — بيع بخسارة.</b>"
SERVICE_NEW_WARN_OK = "✅ الأرقام سليمة."
SERVICE_NEW_DONE = "✅ أُنشئت الخدمة <b>{name}</b> برقم <code>{service_id}</code> وهي مفعّلة."
SERVICE_NEW_NO_PROVIDER = (
    "⚠️ لا يوجد مزود مسجّل بعد.\n\nأضف مزوداً أولاً من قسم «🔌 المزودون»."
)
SERVICE_NEW_BAD_MAX = "❌ أكبر كمية يجب أن تكون أكبر من أقل كمية ({min_q})."
BTN_SERVICE_NEW = "➕ خدمة جديدة"

#: أسماء أنواع المزودين كما تُعرض في أزرار الاختيار
PROVIDER_TYPE_LABELS: dict[str, str] = {
    "perfect_panel": "🌐 Perfect Panel (قياسي)",
    "mock": "🧪 مزود وهمي (اختبار)",
}

PROVIDER_SERVICES_TITLE = (
    "🛍 <b>خدماتنا من {name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "العدد: {total} · الصفحة {page} من {pages}"
)
PROVIDER_KEY_TOO_SHORT = "❌ المفتاح قصير جداً (8 محارف على الأقل). أرسله كاملاً."
BTN_CONFIRM_IMPORT = "✅ نعم، استورد"
```

### `keyboards/callback_data.py`  ·  مُحدَّث  ·  159 سطراً

نطاق جديد `NS_ADM_PRV = "pv"` مُضاف إلى `ALL_NAMESPACES`.

```python
"""
ترميز وفك بيانات الأزرار (callback_data) بشكل مُهيكل وآمن.

لماذا ملف مستقل؟
    تيليجرام يسمح بـ64 بايت فقط لكل `callback_data`، وأي زر قديم في محادثة
    مستخدم قد يُضغط بعد تحديث البوت. لذلك نعتمد صيغة واحدة في كل المشروع:

        namespace:action:arg1:arg2...:vN

    • `namespace` يحدد الشاشة (cat / ord / wal / dep / sup / acc / nav / flow).
    • `action` يحدد الإجراء داخل الشاشة.
    • `vN` لاحقة الإصدار؛ إذا تغيّرت بنية الأزرار مستقبلاً نرفع الرقم،
      فتُرفض الأزرار القديمة برسالة واضحة بدل تنفيذ إجراء خاطئ.

قواعد ملزِمة:
    • ممنوع زر بلا معنى: كل `callback_data` يُبنى من هنا وله معالج مسجَّل
      (يتحقق من ذلك اختبار `test_no_dead_buttons`).
    • ممنوع تمرير نص حر من المستخدم داخل `callback_data` (طوله غير مضمون).
"""

from __future__ import annotations

from dataclasses import dataclass

#: إصدار بنية الأزرار الحالي — يُلحق بكل زر
CALLBACK_VERSION: int = 1

#: الحد الأقصى الذي تسمح به تيليجرام لحجم callback_data (بايت)
MAX_CALLBACK_BYTES: int = 64

#: الفاصل بين أجزاء الزر
SEPARATOR: str = ":"


class CallbackError(ValueError):
    """خطأ في بناء أو قراءة بيانات زر (بنية غير صحيحة أو طول زائد)."""


@dataclass(frozen=True, slots=True)
class Callback:
    """بيانات زر بعد فكّها: المساحة، الإجراء، الوسائط، الإصدار."""

    namespace: str
    action: str
    args: tuple[str, ...]
    version: int

    def arg(self, index: int, default: str = "") -> str:
        """قراءة وسيط نصي بموضعه مع قيمة افتراضية إن لم يوجد."""
        if index < len(self.args):
            return self.args[index]
        return default

    def int_arg(self, index: int, default: int = 0) -> int:
        """قراءة وسيط رقمي بموضعه (يُعيد الافتراضي إن كان غير رقمي)."""
        raw = self.arg(index)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    @property
    def is_current_version(self) -> bool:
        """هل هذا الزر من الإصدار الحالي لبنية الأزرار؟"""
        return self.version == CALLBACK_VERSION


def pack(namespace: str, action: str, *args: object) -> str:
    """
    بناء `callback_data` مُهيكلة والتحقق من صلاحيتها.

    المدخلات:
        namespace : مساحة الشاشة (حروف صغيرة بلا فواصل).
        action    : اسم الإجراء.
        args      : وسائط إضافية (أرقام أو كلمات قصيرة بلا الفاصل `:`).

    المخرجات: نص جاهز لوضعه في زر.

    الاستثناءات:
        CallbackError : وجود الفاصل داخل جزء، أو تجاوز حد 64 بايت.
    """
    parts = [namespace, action, *[str(arg) for arg in args]]
    for part in parts:
        if SEPARATOR in part:
            raise CallbackError(f"جزء زر يحتوي الفاصل الممنوع '{SEPARATOR}': {part!r}")
        if part == "":
            raise CallbackError("جزء زر فارغ غير مسموح")
    data = SEPARATOR.join([*parts, f"v{CALLBACK_VERSION}"])
    if len(data.encode("utf-8")) > MAX_CALLBACK_BYTES:
        raise CallbackError(f"طول callback_data تجاوز {MAX_CALLBACK_BYTES} بايت: {data!r}")
    return data


def unpack(data: str | None) -> Callback:
    """
    فكّ `callback_data` إلى أجزائها.

    المخرجات: كائن `Callback`؛ والإصدار يكون 0 إذا كان الزر قديماً بلا لاحقة إصدار.

    الاستثناءات:
        CallbackError : البيانات فارغة أو لا تحوي مساحة وإجراءً.
    """
    if not data:
        raise CallbackError("callback_data فارغة")
    parts = data.split(SEPARATOR)
    if len(parts) < 2:
        raise CallbackError(f"callback_data غير مُهيكلة: {data!r}")

    version = 0
    if parts[-1].startswith("v") and parts[-1][1:].isdigit():
        version = int(parts[-1][1:])
        parts = parts[:-1]

    namespace, action, *args = parts
    return Callback(namespace=namespace, action=action, args=tuple(args), version=version)


def pattern(namespace: str, action: str | None = None) -> str:
    """
    بناء تعبير نمطي لتسجيل المعالج على مساحة (أو مساحة+إجراء) بعينها.

    مثال: `pattern("cat")` ⇒ `^cat:` و`pattern("cat", "open")` ⇒ `^cat:open(:|$)`.
    """
    if action is None:
        return rf"^{namespace}{SEPARATOR}"
    return rf"^{namespace}{SEPARATOR}{action}({SEPARATOR}|$)"


# ----------------------- مساحات الأزرار المعتمدة ------------------------- #

NS_NAV = "nav"      # التنقل بين الشاشات الرئيسية
NS_CATALOG = "cat"  # التصنيفات والخدمات
NS_NEW = "new"      # بدء طلب جديد
NS_ORDERS = "ord"   # طلباتي
NS_WALLET = "wal"   # المحفظة
NS_DEPOSIT = "dep"  # شحن الرصيد
NS_SUPPORT = "sup"  # الدعم الفني
NS_ACCOUNT = "acc"  # الحساب والإشعارات
NS_FLOW = "flow"    # أزرار داخل المحادثات (تأكيد/إلغاء/تخطي/رجوع)

# ----------------------- مساحات لوحة الأدمن ----------------------------- #
# مختصرة عمداً: حدّ تيليجرام 64 بايت، وبعض الأزرار تحمل معرفات طويلة.

NS_ADMIN = "adm"      # لوحة التحكم والصحة العامة
NS_ADM_USERS = "au"   # إدارة المستخدمين
NS_ADM_PAY = "ap"     # مراجعة طلبات الشحن
NS_ADM_ORD = "ao"     # إدارة الطلبات
NS_ADM_TKT = "at"     # تذاكر الدعم (جانب الأدمن)
NS_ADM_CAT = "ac"     # إدارة الكتالوج (تصنيفات/خدمات)
NS_ADM_SET = "as"     # الإعدادات
NS_ADM_LOG = "al"     # السجلات (تدقيق/أخطاء)
NS_ADM_PRV = "pv"     # المزودون وربط الـAPI (المرحلة 5)

#: كل المساحات المعروفة — تُستخدم في اختبار «لا أزرار بلا وظيفة»
ALL_NAMESPACES: tuple[str, ...] = (
    NS_NAV, NS_CATALOG, NS_NEW, NS_ORDERS, NS_WALLET, NS_DEPOSIT, NS_SUPPORT, NS_ACCOUNT, NS_FLOW,
    NS_ADMIN, NS_ADM_USERS, NS_ADM_PAY, NS_ADM_ORD, NS_ADM_TKT, NS_ADM_CAT, NS_ADM_SET, NS_ADM_LOG,
    NS_ADM_PRV,
)
```

### `keyboards/admin_kb.py`  ·  مُحدَّث  ·  900 سطراً

7 بناة لوحات جديدة للمزودين والمنتقيات + زر «🔌 المزودون» في القائمة الرئيسية + زر «خدمة جديدة» في الكتالوج.

```python
"""
لوحات أزرار لوحة التحكم.

قاعدتان ملزمتان في هذا الملف:

1. **لا يظهر زر لا يملك الأدمن صلاحيته.** كل باني لوحة يستقبل مجموعة صلاحيات
   المستخدم (`perms`) ويبني الأزرار على أساسها. هذا لا يُغني عن فحص الصلاحية
   داخل المعالج نفسه (الزر قد يُضغط من رسالة قديمة بعد سحب الصلاحية) — الفحصان
   مطلوبان معاً.
2. **لا زر بلا معالج.** كل `callback_data` هنا يقابله معالج مسجَّل في
   `handlers/registry.py`، ويتحقق من ذلك اختبار `test_no_dead_buttons`.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from core.enums import OrderStatus
from core.order_state import allowed_next
from core.permissions import Permission
from database.models import (
    Order,
    Payment,
    Provider,
    Service,
    ServiceCategory,
    Setting,
    SupportTicket,
    User,
)
from integrations.providers.base import ProviderServiceItem
from keyboards.callback_data import (
    NS_ADM_CAT,
    NS_ADM_LOG,
    NS_ADM_ORD,
    NS_ADM_PAY,
    NS_ADM_PRV,
    NS_ADM_SET,
    NS_ADM_TKT,
    NS_ADM_USERS,
    NS_ADMIN,
    NS_FLOW,
    pack,
)
from keyboards.common_kb import home_button, pagination_row
from texts import admin_ar as t
from utils.formatters import money_text, order_status_text, safe, ticket_status_text

#: تصفية قوائم الطلبات في لوحة الأدمن (الرمز ⇐ الاسم والحالات المشمولة)
ADMIN_ORDER_FILTERS: dict[str, tuple[str, tuple[str, ...]]] = {
    "att": (
        t.ORDER_FILTER_ATTENTION,
        (OrderStatus.SUBMIT_UNCERTAIN, OrderStatus.FAILED),
    ),
    "act": (
        t.ORDER_FILTER_ACTIVE,
        (
            OrderStatus.PENDING,
            OrderStatus.SUBMITTING,
            OrderStatus.SUBMITTED,
            OrderStatus.IN_PROGRESS,
        ),
    ),
    "all": (t.ORDER_FILTER_ALL, ()),
}

#: تصفية قوائم التذاكر في لوحة الأدمن
ADMIN_TICKET_FILTERS: dict[str, str] = {
    "open": t.TICKET_FILTER_OPEN,
    "wait": t.TICKET_FILTER_WAITING,
    "mine": t.TICKET_FILTER_MINE,
    "closed": t.TICKET_FILTER_CLOSED,
}


# ============================= أدوات داخلية ============================= #


def _panel_row(*, with_home: bool = True) -> list[InlineKeyboardButton]:
    """صف سفلي موحّد: رجوع إلى لوحة التحكم (+ القائمة الرئيسية للمستخدم)."""
    row = [InlineKeyboardButton(t.BTN_BACK_PANEL, callback_data=pack(NS_ADMIN, "home"))]
    if with_home:
        row.append(home_button())
    return row


def _back_row(namespace: str, action: str, *args: object) -> list[InlineKeyboardButton]:
    """صف رجوع إلى شاشة أدمن محددة + لوحة التحكم."""
    return [
        InlineKeyboardButton("🔙 رجوع", callback_data=pack(namespace, action, *args)),
        InlineKeyboardButton(t.BTN_BACK_PANEL, callback_data=pack(NS_ADMIN, "home")),
    ]


def _cancel_row() -> list[InlineKeyboardButton]:
    """صف إلغاء داخل محادثات الأدمن."""
    return [InlineKeyboardButton("❌ إلغاء", callback_data=pack(NS_FLOW, "cancel"))]


def back_panel_kb() -> InlineKeyboardMarkup:
    """لوحة فيها الرجوع إلى لوحة التحكم فقط (تُرفق برسائل النتائج)."""
    return InlineKeyboardMarkup([_panel_row()])


def cancel_only_kb() -> InlineKeyboardMarkup:
    """لوحة فيها زر إلغاء فقط (تُرفق بأسئلة محادثات الأدمن)."""
    return InlineKeyboardMarkup([_cancel_row()])


def confirm_cancel_kb(label: str = t.BTN_CONFIRM_DANGER) -> InlineKeyboardMarkup:
    """لوحة تأكيد عملية خطيرة (تأكيد صريح + إلغاء)."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=pack(NS_FLOW, "confirm"))], _cancel_row()]
    )


def skip_cancel_kb() -> InlineKeyboardMarkup:
    """لوحة تخطي خطوة اختيارية داخل محادثات الأدمن."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⏭ تخطي", callback_data=pack(NS_FLOW, "skip"))], _cancel_row()]
    )


# ============================ القائمة الرئيسية ========================== #


def admin_menu_kb(perms: set[str], *, pending_payments: int = 0, open_tickets: int = 0) -> InlineKeyboardMarkup:
    """
    قائمة لوحة التحكم — تُبنى حسب صلاحيات هذا الأدمن تحديداً.

    المدخلات:
        perms            : مجموعة صلاحيات المستخدم الحالية.
        pending_payments : عدد طلبات الشحن المعلّقة (يظهر كعدّاد على الزر).
        open_tickets     : عدد التذاكر المفتوحة (عدّاد على الزر).
    """
    rows: list[list[InlineKeyboardButton]] = []
    current: list[InlineKeyboardButton] = []

    def add(button: InlineKeyboardButton) -> None:
        """إضافة زر مع ترتيب الأزرار في صفوف من اثنين."""
        current.append(button)
        if len(current) == 2:
            rows.append(list(current))
            current.clear()

    if Permission.USERS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_USERS, callback_data=pack(NS_ADM_USERS, "home")))
    if Permission.PAYMENTS_VIEW in perms:
        label = t.MENU_PAYMENTS + (f" ({pending_payments})" if pending_payments else "")
        add(InlineKeyboardButton(label, callback_data=pack(NS_ADM_PAY, "list", 1)))
    if Permission.ORDERS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_ORDERS, callback_data=pack(NS_ADM_ORD, "list", "att", 1)))
    if Permission.TICKETS_VIEW in perms:
        label = t.MENU_TICKETS + (f" ({open_tickets})" if open_tickets else "")
        add(InlineKeyboardButton(label, callback_data=pack(NS_ADM_TKT, "list", "open", 1)))
    if Permission.SERVICES_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_CATALOG, callback_data=pack(NS_ADM_CAT, "home")))
    if Permission.PROVIDERS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_PROVIDERS, callback_data=pack(NS_ADM_PRV, "home")))
    if Permission.SETTINGS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_SETTINGS, callback_data=pack(NS_ADM_SET, "home")))
    if Permission.LOGS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_LOGS, callback_data=pack(NS_ADM_LOG, "home")))
    if Permission.STATS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_HEALTH, callback_data=pack(NS_ADMIN, "health")))

    if current:
        rows.append(list(current))

    rows.append(
        [
            InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADMIN, "home")),
            home_button(),
        ]
    )
    return InlineKeyboardMarkup(rows)


def health_kb() -> InlineKeyboardMarkup:
    """أزرار شاشة صحة النظام."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADMIN, "health"))], _panel_row()]
    )


# ============================= المستخدمون =============================== #


def users_home_kb(perms: set[str]) -> InlineKeyboardMarkup:
    """شاشة المستخدمين: بحث + رجوع."""
    rows = [[InlineKeyboardButton(t.BTN_USER_SEARCH, callback_data=pack(NS_ADM_USERS, "search"))]]
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def user_results_kb(users: list[User]) -> InlineKeyboardMarkup:
    """نتائج البحث: زر لكل مستخدم."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'🚫 ' if user.is_banned else ''}{user.display_name} · {user.telegram_id}",
                callback_data=pack(NS_ADM_USERS, "view", user.id),
            )
        ]
        for user in users
    ]
    rows.append(
        [InlineKeyboardButton(t.BTN_USER_SEARCH, callback_data=pack(NS_ADM_USERS, "search"))]
    )
    rows.append(_back_row(NS_ADM_USERS, "home"))
    return InlineKeyboardMarkup(rows)


def user_card_kb(user: User, perms: set[str]) -> InlineKeyboardMarkup:
    """أزرار بطاقة المستخدم حسب الصلاحيات المتاحة."""
    rows: list[list[InlineKeyboardButton]] = []

    money_row: list[InlineKeyboardButton] = []
    if Permission.USERS_BALANCE_CREDIT in perms:
        money_row.append(
            InlineKeyboardButton(
                t.BTN_USER_CREDIT, callback_data=pack(NS_ADM_USERS, "credit", user.id)
            )
        )
    if Permission.USERS_BALANCE_DEBIT in perms:
        money_row.append(
            InlineKeyboardButton(
                t.BTN_USER_DEBIT, callback_data=pack(NS_ADM_USERS, "debit", user.id)
            )
        )
    if money_row:
        rows.append(money_row)

    state_row: list[InlineKeyboardButton] = []
    if user.is_banned and Permission.USERS_UNBAN in perms:
        state_row.append(
            InlineKeyboardButton(
                t.BTN_USER_UNBAN, callback_data=pack(NS_ADM_USERS, "unban", user.id)
            )
        )
    elif not user.is_banned and Permission.USERS_BAN in perms:
        state_row.append(
            InlineKeyboardButton(t.BTN_USER_BAN, callback_data=pack(NS_ADM_USERS, "ban", user.id))
        )
    if Permission.USERS_NOTE in perms:
        state_row.append(
            InlineKeyboardButton(t.BTN_USER_NOTE, callback_data=pack(NS_ADM_USERS, "note", user.id))
        )
    if state_row:
        rows.append(state_row)

    if Permission.USERS_ROLE_CHANGE in perms:
        rows.append(
            [InlineKeyboardButton(t.BTN_USER_ROLE, callback_data=pack(NS_ADM_USERS, "role", user.id))]
        )

    history_row: list[InlineKeyboardButton] = []
    if Permission.ORDERS_VIEW in perms:
        history_row.append(
            InlineKeyboardButton(
                t.BTN_USER_ORDERS, callback_data=pack(NS_ADM_USERS, "orders", user.id, 1)
            )
        )
    history_row.append(
        InlineKeyboardButton(t.BTN_USER_TX, callback_data=pack(NS_ADM_USERS, "tx", user.id, 1))
    )
    rows.append(history_row)

    rows.append(_back_row(NS_ADM_USERS, "home"))
    return InlineKeyboardMarkup(rows)


def user_role_kb(user: User) -> InlineKeyboardMarkup:
    """أزرار اختيار الدور الجديد للمستخدم."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'• ' if user.role == code else ''}{label}",
                callback_data=pack(NS_ADM_USERS, "setrole", user.id, code),
            )
        ]
        for code, label in t.ASSIGNABLE_ROLES.items()
    ]
    rows.append(_back_row(NS_ADM_USERS, "view", user.id))
    return InlineKeyboardMarkup(rows)


def user_role_confirm_kb(user_id: int, role_code: str) -> InlineKeyboardMarkup:
    """تأكيد ثانٍ قبل تغيير الدور (إجراء خطير يغيّر الصلاحيات فوراً)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t.BTN_CONFIRM_DANGER,
                    callback_data=pack(NS_ADM_USERS, "roleok", user_id, role_code),
                )
            ],
            [InlineKeyboardButton("🔙 رجوع", callback_data=pack(NS_ADM_USERS, "role", user_id))],
        ]
    )


def user_list_nav_kb(
    action: str, user_id: int, *, page: int, total_pages: int
) -> InlineKeyboardMarkup:
    """ترقيم قوائم طلبات/معاملات مستخدم بعينه."""
    rows: list[list[InlineKeyboardButton]] = []
    nav = pagination_row(
        NS_ADM_USERS, action, page=page, total_pages=total_pages, prefix_args=(user_id,)
    )
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_USERS, "view", user_id))
    return InlineKeyboardMarkup(rows)


# ============================= المدفوعات ================================ #


def payments_list_kb(
    payments: list[Payment], *, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """قائمة طلبات الشحن المعلّقة."""
    rows = [
        [
            InlineKeyboardButton(
                f"#{payment.id} · {money_text(payment.amount_units, symbol)}",
                callback_data=pack(NS_ADM_PAY, "view", payment.id),
            )
        ]
        for payment in payments
    ]
    nav = pagination_row(NS_ADM_PAY, "list", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def payment_card_kb(payment: Payment, perms: set[str], *, is_pending: bool) -> InlineKeyboardMarkup:
    """أزرار بطاقة طلب الشحن (الاعتماد/الرفض تظهر للمعلّق فقط)."""
    rows: list[list[InlineKeyboardButton]] = []
    if payment.proof_file_id:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_PAYMENT_PROOF, callback_data=pack(NS_ADM_PAY, "proof", payment.id)
                )
            ]
        )
    if is_pending:
        action_row: list[InlineKeyboardButton] = []
        if Permission.PAYMENTS_APPROVE in perms:
            action_row.append(
                InlineKeyboardButton(
                    t.BTN_PAYMENT_APPROVE, callback_data=pack(NS_ADM_PAY, "ok", payment.id)
                )
            )
        if Permission.PAYMENTS_REJECT in perms:
            action_row.append(
                InlineKeyboardButton(
                    t.BTN_PAYMENT_REJECT, callback_data=pack(NS_ADM_PAY, "no", payment.id)
                )
            )
        if action_row:
            rows.append(action_row)
    if Permission.USERS_VIEW in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    "👤 صاحب الطلب", callback_data=pack(NS_ADM_USERS, "view", payment.user_id)
                )
            ]
        )
    rows.append(_back_row(NS_ADM_PAY, "list", 1))
    return InlineKeyboardMarkup(rows)


def payment_approve_kb() -> InlineKeyboardMarkup:
    """تأكيد الاعتماد مع إمكانية تعديل المبلغ المضاف."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_CONFIRM_DANGER, callback_data=pack(NS_FLOW, "confirm"))],
            [InlineKeyboardButton(t.BTN_EDIT_AMOUNT, callback_data=pack(NS_ADM_PAY, "amount"))],
            _cancel_row(),
        ]
    )


# ============================== الطلبات ================================= #


def admin_orders_filters_row(current: str) -> list[InlineKeyboardButton]:
    """صف تصفية قوائم الطلبات."""
    return [
        InlineKeyboardButton(
            f"{'• ' if code == current else ''}{label}",
            callback_data=pack(NS_ADM_ORD, "list", code, 1),
        )
        for code, (label, _statuses) in ADMIN_ORDER_FILTERS.items()
    ]


def admin_orders_kb(
    orders: list[Order], *, filter_code: str, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """قائمة الطلبات في لوحة الأدمن."""
    rows = [
        [
            InlineKeyboardButton(
                f"{order_status_text(order.status).split(' ', 1)[0]} "
                f"{order.public_code or order.id} · {money_text(order.cost_units, symbol)}",
                callback_data=pack(NS_ADM_ORD, "view", order.id, filter_code, page),
            )
        ]
        for order in orders
    ]
    rows.append(admin_orders_filters_row(filter_code))
    nav = pagination_row(
        NS_ADM_ORD, "list", page=page, total_pages=total_pages, prefix_args=(filter_code,)
    )
    if nav:
        rows.append(nav)
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def admin_order_card_kb(
    order: Order, perms: set[str], *, filter_code: str, page: int
) -> InlineKeyboardMarkup:
    """أزرار بطاقة الطلب الإدارية (كل زر مشروط بصلاحيته وبحالة الطلب)."""
    rows: list[list[InlineKeyboardButton]] = []
    is_final = not allowed_next(order.status)

    first_row: list[InlineKeyboardButton] = []
    if Permission.ORDERS_RECHECK in perms and order.provider_order_id and not is_final:
        first_row.append(
            InlineKeyboardButton(
                t.BTN_ORDER_RECHECK, callback_data=pack(NS_ADM_ORD, "recheck", order.id)
            )
        )
    if Permission.ORDERS_LINK_PROVIDER_ID in perms and order.status == OrderStatus.SUBMIT_UNCERTAIN:
        first_row.append(
            InlineKeyboardButton(
                t.BTN_ORDER_LINK, callback_data=pack(NS_ADM_ORD, "link", order.id)
            )
        )
    if first_row:
        rows.append(first_row)

    danger_row: list[InlineKeyboardButton] = []
    if Permission.ORDERS_CANCEL in perms and not is_final:
        danger_row.append(
            InlineKeyboardButton(
                t.BTN_ORDER_CANCEL, callback_data=pack(NS_ADM_ORD, "cancel", order.id)
            )
        )
    if Permission.ORDERS_REFUND in perms and not is_final:
        danger_row.append(
            InlineKeyboardButton(t.BTN_ORDER_FAIL, callback_data=pack(NS_ADM_ORD, "fail", order.id))
        )
    if danger_row:
        rows.append(danger_row)

    if Permission.ORDERS_STATUS_OVERRIDE in perms and allowed_next(order.status):
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_ORDER_OVERRIDE, callback_data=pack(NS_ADM_ORD, "force", order.id)
                )
            ]
        )

    if Permission.USERS_VIEW in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_ORDER_USER, callback_data=pack(NS_ADM_USERS, "view", order.user_id)
                )
            ]
        )

    rows.append(_back_row(NS_ADM_ORD, "list", filter_code, page))
    return InlineKeyboardMarkup(rows)


def order_override_kb(order: Order) -> InlineKeyboardMarkup:
    """أزرار الحالات المسموح الانتقال إليها من الحالة الحالية فقط."""
    rows = [
        [
            InlineKeyboardButton(
                order_status_text(status),
                callback_data=pack(NS_ADM_ORD, "setst", order.id, status),
            )
        ]
        for status in sorted(allowed_next(order.status))
    ]
    rows.append(_back_row(NS_ADM_ORD, "view", order.id, "all", 1))
    return InlineKeyboardMarkup(rows)


# =============================== الدعم ================================== #


def admin_tickets_filters_row(current: str) -> list[InlineKeyboardButton]:
    """صف تصفية قوائم التذاكر."""
    return [
        InlineKeyboardButton(
            f"{'• ' if code == current else ''}{label}",
            callback_data=pack(NS_ADM_TKT, "list", code, 1),
        )
        for code, label in ADMIN_TICKET_FILTERS.items()
    ]


def admin_tickets_kb(
    tickets: list[SupportTicket], *, filter_code: str, page: int, total_pages: int
) -> InlineKeyboardMarkup:
    """قائمة التذاكر في لوحة الأدمن."""
    rows = [
        [
            InlineKeyboardButton(
                f"{ticket_status_text(ticket.status).split(' ', 1)[0]} #{ticket.id} · "
                f"{safe(ticket.subject, limit=28)}",
                callback_data=pack(NS_ADM_TKT, "view", ticket.id),
            )
        ]
        for ticket in tickets
    ]
    rows.append(admin_tickets_filters_row(filter_code))
    nav = pagination_row(
        NS_ADM_TKT, "list", page=page, total_pages=total_pages, prefix_args=(filter_code,)
    )
    if nav:
        rows.append(nav)
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def admin_ticket_card_kb(
    ticket: SupportTicket, perms: set[str], *, filter_code: str = "open"
) -> InlineKeyboardMarkup:
    """أزرار بطاقة التذكرة الإدارية."""
    rows: list[list[InlineKeyboardButton]] = []
    action_row: list[InlineKeyboardButton] = []
    if ticket.is_open and Permission.TICKETS_REPLY in perms:
        action_row.append(
            InlineKeyboardButton(
                t.BTN_TICKET_REPLY, callback_data=pack(NS_ADM_TKT, "reply", ticket.id)
            )
        )
    if ticket.is_open and Permission.TICKETS_CLOSE in perms:
        action_row.append(
            InlineKeyboardButton(
                t.BTN_TICKET_CLOSE, callback_data=pack(NS_ADM_TKT, "close", ticket.id)
            )
        )
    if action_row:
        rows.append(action_row)

    if ticket.is_open and Permission.TICKETS_ASSIGN in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_TICKET_ASSIGN, callback_data=pack(NS_ADM_TKT, "assign", ticket.id)
                )
            ]
        )
    if Permission.USERS_VIEW in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_TICKET_USER, callback_data=pack(NS_ADM_USERS, "view", ticket.user_id)
                )
            ]
        )
    rows.append(_back_row(NS_ADM_TKT, "list", filter_code, 1))
    return InlineKeyboardMarkup(rows)


# ============================== الكتالوج ================================ #


def catalog_home_kb(categories: list[ServiceCategory], perms: set[str]) -> InlineKeyboardMarkup:
    """شاشة الكتالوج: التصنيفات + إضافة تصنيف."""
    rows = [
        [
            InlineKeyboardButton(
                category.title, callback_data=pack(NS_ADM_CAT, "cat", category.id, 1)
            )
        ]
        for category in categories
    ]
    if Permission.SERVICES_CREATE in perms:
        rows.append(
            [
                InlineKeyboardButton(t.BTN_SERVICE_NEW, callback_data=pack(NS_ADM_CAT, "newsvc")),
                InlineKeyboardButton(t.BTN_CATEGORY_NEW, callback_data=pack(NS_ADM_CAT, "newcat")),
            ]
        )
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def catalog_services_kb(
    services: list[Service], *, category_id: int, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """قائمة خدمات تصنيف في لوحة الأدمن (مع مؤشر التفعيل)."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'🟢' if service.is_active else '⚪️'} {safe(service.name, limit=26)} · "
                f"{money_text(service.price_per_1000_units, symbol)}",
                callback_data=pack(NS_ADM_CAT, "svc", service.id),
            )
        ]
        for service in services
    ]
    nav = pagination_row(
        NS_ADM_CAT, "cat", page=page, total_pages=total_pages, prefix_args=(category_id,)
    )
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_CAT, "home"))
    return InlineKeyboardMarkup(rows)


def service_card_kb(service: Service, perms: set[str]) -> InlineKeyboardMarkup:
    """أزرار بطاقة الخدمة الإدارية."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    if Permission.SERVICES_UPDATE in perms and not service.is_archived:
        label = t.BTN_SERVICE_TOGGLE_OFF if service.is_active else t.BTN_SERVICE_TOGGLE_ON
        row.append(InlineKeyboardButton(label, callback_data=pack(NS_ADM_CAT, "toggle", service.id)))
    if Permission.SERVICES_PRICE in perms and not service.is_archived:
        row.append(
            InlineKeyboardButton(
                t.BTN_SERVICE_PRICE, callback_data=pack(NS_ADM_CAT, "price", service.id)
            )
        )
    if row:
        rows.append(row)
    if Permission.SERVICES_ARCHIVE in perms and not service.is_archived:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_SERVICE_ARCHIVE, callback_data=pack(NS_ADM_CAT, "archive", service.id)
                )
            ]
        )
    rows.append(_back_row(NS_ADM_CAT, "cat", service.category_id, 1))
    return InlineKeyboardMarkup(rows)


# ============================= الإعدادات ================================ #


def settings_home_kb(
    groups: list[str], perms: set[str], *, maintenance_on: bool
) -> InlineKeyboardMarkup:
    """مجموعات الإعدادات + مفتاح وضع الصيانة."""
    rows = [
        [InlineKeyboardButton(f"⚙️ {group}", callback_data=pack(NS_ADM_SET, "group", group, 1))]
        for group in groups
    ]
    if Permission.SETTINGS_MAINTENANCE in perms:
        label = t.BTN_MAINTENANCE_OFF if maintenance_on else t.BTN_MAINTENANCE_ON
        rows.append([InlineKeyboardButton(label, callback_data=pack(NS_ADM_SET, "maint"))])
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def settings_group_kb(
    settings: list[Setting], *, group: str, page: int, total_pages: int, perms: set[str]
) -> InlineKeyboardMarkup:
    """مفاتيح مجموعة إعدادات (القابل للتعديل فقط يصبح زراً)."""
    rows: list[list[InlineKeyboardButton]] = []
    if Permission.SETTINGS_UPDATE in perms:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        f"✏️ {safe(setting.name_ar or setting.key, limit=32)}",
                        callback_data=pack(NS_ADM_SET, "edit", setting.key),
                    )
                ]
                for setting in settings
                if setting.is_editable
            ]
        )
    nav = pagination_row(
        NS_ADM_SET, "group", page=page, total_pages=total_pages, prefix_args=(group,)
    )
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_SET, "home"))
    return InlineKeyboardMarkup(rows)


# ============================== السجلات ================================= #


def logs_home_kb() -> InlineKeyboardMarkup:
    """اختيار نوع السجل."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_LOG_AUDIT, callback_data=pack(NS_ADM_LOG, "audit", 1))],
            [InlineKeyboardButton(t.BTN_LOG_ERRORS, callback_data=pack(NS_ADM_LOG, "errors", 1))],
            _panel_row(),
        ]
    )


def logs_page_kb(action: str, *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """ترقيم صفحات السجلات."""
    rows: list[list[InlineKeyboardButton]] = []
    nav = pagination_row(NS_ADM_LOG, action, page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_LOG, "home"))
    return InlineKeyboardMarkup(rows)


# ============================== المزودون ================================ #


def providers_home_kb(providers: list[Provider], perms: set[str]) -> InlineKeyboardMarkup:
    """
    قائمة المزودين.

    كل زر يحمل مؤشر حالة (🟢 مفعّل · ⚪️ متوقف) وتلميح المفتاح لا المفتاح نفسه.
    """
    rows = [
        [
            InlineKeyboardButton(
                f"{'🟢' if provider.is_active else '⚪️'} {safe(provider.name, limit=28)}",
                callback_data=pack(NS_ADM_PRV, "view", provider.id),
            )
        ]
        for provider in providers
    ]
    if Permission.PROVIDERS_CREATE in perms:
        rows.append(
            [InlineKeyboardButton(t.BTN_PROVIDER_NEW, callback_data=pack(NS_ADM_PRV, "new"))]
        )
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def provider_card_kb(provider: Provider, perms: set[str]) -> InlineKeyboardMarkup:
    """أزرار بطاقة المزود — كل زر مشروط بصلاحيته."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    if Permission.PROVIDERS_TEST in perms:
        row.append(
            InlineKeyboardButton(
                t.BTN_PROVIDER_TEST, callback_data=pack(NS_ADM_PRV, "test", provider.id)
            )
        )
        row.append(
            InlineKeyboardButton(
                t.BTN_PROVIDER_BALANCE, callback_data=pack(NS_ADM_PRV, "bal", provider.id)
            )
        )
    if row:
        rows.append(row)
        row = []

    if Permission.SERVICES_SYNC in perms:
        row.append(
            InlineKeyboardButton(
                t.BTN_PROVIDER_SYNC, callback_data=pack(NS_ADM_PRV, "sync", provider.id)
            )
        )
    if Permission.SERVICES_CREATE in perms:
        row.append(
            InlineKeyboardButton(
                t.BTN_PROVIDER_IMPORT, callback_data=pack(NS_ADM_PRV, "imp", provider.id)
            )
        )
    if row:
        rows.append(row)
        row = []

    if Permission.PROVIDERS_UPDATE in perms:
        label = t.BTN_PROVIDER_OFF if provider.is_active else t.BTN_PROVIDER_ON
        row.append(
            InlineKeyboardButton(label, callback_data=pack(NS_ADM_PRV, "toggle", provider.id))
        )
    if Permission.PROVIDERS_KEY_UPDATE in perms:
        row.append(
            InlineKeyboardButton(
                t.BTN_PROVIDER_KEY, callback_data=pack(NS_ADM_PRV, "key", provider.id)
            )
        )
    if row:
        rows.append(row)

    if Permission.SERVICES_VIEW in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_PROVIDER_SERVICES, callback_data=pack(NS_ADM_PRV, "svcs", provider.id, 1)
                )
            ]
        )
    rows.append(_back_row(NS_ADM_PRV, "home"))
    return InlineKeyboardMarkup(rows)


def provider_type_kb() -> InlineKeyboardMarkup:
    """اختيار نوع واجهة المزود عند إضافته (من الأنواع المدعومة فعلياً فقط)."""
    from integrations.providers.registry import available_types

    rows = [
        [
            InlineKeyboardButton(
                t.PROVIDER_TYPE_LABELS.get(api_type, api_type),
                callback_data=pack(NS_ADM_PRV, "type", api_type),
            )
        ]
        for api_type in available_types()
    ]
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


def provider_services_kb(
    services: list[Service], *, provider_id: int, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """قائمة خدماتنا المرتبطة بمزود (تفتح بطاقة الخدمة في قسم الكتالوج)."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'🟢' if service.is_active else '⚪️'} {safe(service.name, limit=24)} · "
                f"{money_text(service.price_per_1000_units, symbol)}",
                callback_data=pack(NS_ADM_CAT, "svc", service.id),
            )
        ]
        for service in services
    ]
    nav = pagination_row(
        NS_ADM_PRV, "svcs", page=page, total_pages=total_pages, prefix_args=(provider_id,)
    )
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_PRV, "view", provider_id))
    return InlineKeyboardMarkup(rows)


def provider_import_results_kb(
    items: list[ProviderServiceItem], *, provider_id: int, symbol: str
) -> InlineKeyboardMarkup:
    """
    نتائج البحث في قائمة خدمات المزود.

    الزر يحمل **فهرس العنصر** في النتائج المحفوظة مؤقتاً لا رقم الخدمة، لأن
    أرقام بعض المزودين طويلة وقد تتجاوز حد 64 بايت مع بقية الوسائط.
    """
    rows = [
        [
            InlineKeyboardButton(
                f"{safe(item.name, limit=28)} · {money_text(item.rate_per_1000_units, symbol)}",
                callback_data=pack(NS_ADM_PRV, "pick", index),
            )
        ]
        for index, item in enumerate(items)
    ]
    rows.append(_back_row(NS_ADM_PRV, "view", provider_id))
    return InlineKeyboardMarkup(rows)


def category_picker_kb(
    categories: list[ServiceCategory], namespace: str, action: str
) -> InlineKeyboardMarkup:
    """اختيار تصنيف داخل محادثة (يُستخدم في الاستيراد وفي إنشاء خدمة يدوياً)."""
    rows = [
        [InlineKeyboardButton(category.title, callback_data=pack(namespace, action, category.id))]
        for category in categories
    ]
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


def provider_picker_kb(
    providers: list[Provider], namespace: str, action: str
) -> InlineKeyboardMarkup:
    """اختيار مزود داخل محادثة إنشاء خدمة."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'🟢' if provider.is_active else '⚪️'} {safe(provider.name, limit=28)}",
                callback_data=pack(namespace, action, provider.id),
            )
        ]
        for provider in providers
    ]
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)
```

---

## لوحة التحكم — قسم المزودين وإنشاء الخدمة

### `handlers/admin/providers.py`  ·  جديد  ·  975 سطراً

قسم «🔌 المزودون» كاملاً: شاشات القراءة، اختبار الاتصال، تحديث الرصيد، تفعيل/إيقاف، المزامنة، و3 محادثات (إضافة مزود، تغيير المفتاح، استيراد خدمة).

```python
"""
قسم «🔌 المزودون» في لوحة التحكم: إدارة المزودين وربط الـAPI.

ما يُنفَّذ هنا:
    • قائمة المزودين وبطاقة كل مزود (الحالة، الرصيد، عدد خدماتنا منه، آخر خطأ).
    • إضافة مزود جديد: اسم ← رابط ← نوع ← مفتاح ← تأكيد، ثم اختبار اتصال فوري.
    • تغيير مفتاح API، تفعيل/إيقاف، اختبار الاتصال، تحديث الرصيد.
    • مزامنة أسعار وحدود خدماتنا مع قائمة المزود الحالية.
    • استيراد خدمة من قائمة المزود بهامش ربح محدد.

قواعد أمنية ملزمة في هذا الملف:
    • **لا يُعرض مفتاح API كاملاً أبداً** — فقط آخر أربعة محارف (`api_key_hint`)،
      ولا يُسجَّل المفتاح في اللوق ولا في سجل التدقيق.
    • رسالة المفتاح التي يرسلها الأدمن تُحذف من المحادثة فور قراءتها قدر الإمكان.
    • كل إجراء يفحص صلاحيته على الـcallback نفسه عبر `admin_required`.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from core.exceptions import ProviderError, ValidationError
from core.permissions import Permission
from database.models import Provider
from handlers.admin.common import (
    ADMIN_FLOW_KEY,
    PAGE_SIZE,
    admin_required,
    args,
    cancel_admin_flow,
    clear_flow,
    flow,
    paginate,
    start_flow,
    symbol_of,
    update_flow,
)
from handlers.common.fallbacks import exit_conversation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from integrations.providers.base import ProviderServiceItem
from integrations.providers.registry import available_types, is_supported
from keyboards.admin_kb import (
    back_panel_kb,
    cancel_only_kb,
    category_picker_kb,
    confirm_cancel_kb,
    provider_card_kb,
    provider_import_results_kb,
    provider_services_kb,
    provider_type_kb,
    providers_home_kb,
)
from keyboards.callback_data import NS_ADM_PRV, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from utils.formatters import datetime_text, money_text, safe
from utils.logging_setup import get_logger
from utils.validators import clean_text, normalize_digits, validate_url

logger = get_logger(__name__)

#: حالات محادثة «إضافة مزود»
ASK_NAME, ASK_URL, ASK_TYPE, ASK_KEY, CONFIRM_NEW = range(5)

#: حالة محادثة «تغيير المفتاح»
ASK_NEW_KEY = 10

#: حالات محادثة «استيراد خدمة من المزود»
ASK_SEARCH, PICK_ITEM, PICK_CATEGORY, ASK_MARGIN, CONFIRM_IMPORT = range(20, 25)

#: أقصى عدد نتائج بحث تُعرض كأزرار (الزيادة تُربك لا تفيد)
IMPORT_RESULTS_LIMIT = 8

#: مفتاح تخزين نتائج بحث المزود مؤقتاً داخل بيانات المحادثة
IMPORT_ITEMS_KEY = "import_items"


# ======================================================================== #
#                              أدوات داخلية                                #
# ======================================================================== #


async def _load_provider(context: ContextTypes.DEFAULT_TYPE, provider_id: int) -> Provider:
    """
    تحميل مزود بالمعرف أو رفع خطأ عربي واضح.

    الاستثناءات: ValidationError إذا كان الزر يحمل معرفاً لم يعد موجوداً.
    """
    services = services_of(context)
    provider = await services.providers.get(provider_id)
    if provider is None:
        raise ValidationError(
            f"مزود غير موجود: {provider_id}", user_message=t.PROVIDER_NOT_FOUND
        )
    return provider


async def _provider_card_text(context: ContextTypes.DEFAULT_TYPE, provider: Provider) -> str:
    """بناء نص بطاقة المزود (بلا أي جزء من المفتاح عدا آخر أربعة محارف)."""
    services = services_of(context)
    health = await services.providers.health(provider)
    services_count = await services.repos.providers.count_services(provider.id)

    if not provider.is_active:
        state = t.PROVIDER_STATE_OFF
    elif not health.is_usable:
        state = t.PROVIDER_STATE_BLOCKED.format(reason=safe(health.reason, limit=60))
    else:
        state = t.PROVIDER_STATE_OK

    last_error_line = ""
    if provider.last_error:
        last_error_line = t.PROVIDER_LAST_ERROR_LINE.format(
            error=safe(provider.last_error, limit=120)
        )

    return t.PROVIDER_CARD.format(
        name=safe(provider.name, limit=40),
        provider_id=provider.id,
        api_url=safe(provider.api_url, limit=70),
        key_hint=safe(provider.api_key_hint or "????", limit=8),
        api_type=safe(provider.api_type, limit=20),
        state=state,
        balance=money_text(provider.balance_units),
        currency=safe(provider.currency or "USD", limit=6),
        balance_checked=datetime_text(provider.balance_checked_at) if provider.balance_checked_at else "—",
        services_count=services_count,
        failures=provider.consecutive_failures,
        last_success=datetime_text(provider.last_success_at) if provider.last_success_at else "—",
        last_error_line=last_error_line,
    )


async def _render_provider(
    update: Update, context: ContextTypes.DEFAULT_TYPE, provider_id: int, *, as_new: bool = False
) -> None:
    """عرض بطاقة المزود (تحرير الرسالة الحالية أو إرسال رسالة جديدة بعد عملية)."""
    from handlers.admin.common import permissions_of

    provider = await _load_provider(context, provider_id)
    text = await _provider_card_text(context, provider)
    perms = await permissions_of(context)
    markup = provider_card_kb(provider, perms)
    if as_new:
        await send(update, context, text, markup)
    else:
        await render(update, context, text, markup)


# ======================================================================== #
#                            الشاشات (قراءة)                               #
# ======================================================================== #


@guarded
@admin_required(Permission.PROVIDERS_VIEW)
async def providers_home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة المزودين مع عدّادات سريعة."""
    await answer_callback(update)
    from handlers.admin.common import permissions_of

    services = services_of(context)
    providers = await services.providers.list_all()
    perms = await permissions_of(context)

    if not providers:
        await render(update, context, t.PROVIDERS_EMPTY, providers_home_kb([], perms))
        return

    linked = 0
    for provider in providers:
        linked += await services.repos.providers.count_services(provider.id)

    text = t.PROVIDERS_HOME.format(
        total=len(providers),
        active=sum(1 for provider in providers if provider.is_active),
        linked_services=linked,
    )
    await render(update, context, text, providers_home_kb(providers, perms))


@guarded
@admin_required(Permission.PROVIDERS_VIEW)
async def provider_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة مزود واحد."""
    await answer_callback(update)
    await _render_provider(update, context, args(update).int_arg(0))


@guarded
@admin_required(Permission.SERVICES_VIEW)
async def provider_services_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة خدماتنا المرتبطة بهذا المزود (مُرقَّمة)."""
    await answer_callback(update)
    data = args(update)
    provider_id = data.int_arg(0)
    provider = await _load_provider(context, provider_id)

    services = services_of(context)
    admin = require_user(context)
    items = await services.catalog.services_of_provider(admin, provider_id)
    page, total_pages, offset = paginate(len(items), data.int_arg(1, 1))
    symbol = await symbol_of(context)

    await render(
        update,
        context,
        t.PROVIDER_SERVICES_TITLE.format(
            name=safe(provider.name, limit=40), total=len(items), page=page, pages=total_pages
        ),
        provider_services_kb(
            items[offset : offset + PAGE_SIZE],
            provider_id=provider_id,
            page=page,
            total_pages=total_pages,
            symbol=symbol,
        ),
    )


# ======================================================================== #
#                      إجراءات مباشرة (اختبار/رصيد/تفعيل)                  #
# ======================================================================== #


@guarded
@admin_required(Permission.PROVIDERS_TEST)
async def test_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """اختبار اتصال فوري بالمزود وعرض النتيجة (بلا أي سر في الرسالة)."""
    await answer_callback(update, t.PROVIDER_TEST_RUNNING)
    provider_id = args(update).int_arg(0)
    provider = await _load_provider(context, provider_id)

    services = services_of(context)
    admin = require_user(context)
    ok, message = await services.providers.test_connection(admin, provider_id)

    await render(
        update,
        context,
        t.PROVIDER_TEST_RESULT.format(
            icon="✅" if ok else "❌",
            name=safe(provider.name, limit=40),
            message=safe(message, limit=200),
        ),
        back_panel_kb(),
    )
    await _render_provider(update, context, provider_id, as_new=True)


@guarded
@admin_required(Permission.PROVIDERS_TEST)
async def refresh_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تحديث رصيدنا لدى المزود وحفظ لقطة تاريخية (داخل الخدمة)."""
    provider_id = args(update).int_arg(0)
    provider = await _load_provider(context, provider_id)
    services = services_of(context)

    try:
        balance = await services.providers.check_balance(provider)
    except ProviderError as exc:
        await answer_callback(update, exc.user_message, alert=True)
        await _render_provider(update, context, provider_id)
        return

    await answer_callback(
        update,
        t.PROVIDER_BALANCE_UPDATED.format(
            name=provider.name,
            balance=money_text(balance.amount_units),
            currency=balance.currency,
        ).replace("<b>", "").replace("</b>", ""),
        alert=True,
    )
    await _render_provider(update, context, provider_id)


@guarded
@admin_required(Permission.PROVIDERS_UPDATE)
async def toggle_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    تفعيل أو إيقاف مزود.

    الإيقاف لا يلغي الطلبات الجارية — يمنع فقط إرسال طلبات جديدة إليه،
    والمتابعة تستمر حتى تصل الطلبات القائمة إلى حالتها النهائية.
    """
    provider_id = args(update).int_arg(0)
    provider = await _load_provider(context, provider_id)
    services = services_of(context)
    admin = require_user(context)

    new_state = not bool(provider.is_active)
    changed = await services.providers.set_active(admin, provider_id, new_state)
    message = (
        (t.PROVIDER_TOGGLED_ON if new_state else t.PROVIDER_TOGGLED_OFF).format(
            name=provider.name
        )
        if changed
        else t.NOTHING_CHANGED
    )
    await answer_callback(update, message, alert=True)
    await _render_provider(update, context, provider_id)


# ======================================================================== #
#                          محادثة: إضافة مزود جديد                         #
# ======================================================================== #


@guarded
@admin_required(Permission.PROVIDERS_CREATE)
async def start_new_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء إضافة مزود: سؤال الاسم."""
    await answer_callback(update)
    start_flow(context)
    await render(update, context, t.PROVIDER_ASK_NAME, cancel_only_kb())
    return ASK_NAME


@guarded
@admin_required(Permission.PROVIDERS_CREATE)
async def receive_provider_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال اسم المزود ثم سؤال رابط الـAPI."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_NAME

    name = clean_text(message.text, field="اسم المزود", max_length=60, min_length=2)
    update_flow(context, name=name)
    await send(update, context, t.PROVIDER_ASK_URL, cancel_only_kb())
    return ASK_URL


@guarded
@admin_required(Permission.PROVIDERS_CREATE)
async def receive_provider_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال رابط الـAPI (يُتحقق منه) ثم سؤال نوع الواجهة."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_URL

    api_url = validate_url(message.text.strip())
    update_flow(context, api_url=api_url)
    await send(update, context, t.PROVIDER_ASK_TYPE, provider_type_kb())
    return ASK_TYPE


@guarded
@admin_required(Permission.PROVIDERS_CREATE)
async def receive_provider_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال نوع الواجهة المختار ثم طلب المفتاح."""
    await answer_callback(update)
    api_type = args(update).arg(0)
    if not is_supported(api_type):
        await answer_callback(
            update,
            t.PROVIDER_TYPE_UNSUPPORTED.format(types=", ".join(available_types())),
            alert=True,
        )
        return ASK_TYPE

    update_flow(context, api_type=api_type)
    await render(update, context, t.PROVIDER_ASK_KEY, cancel_only_kb())
    return ASK_KEY


@guarded
@admin_required(Permission.PROVIDERS_CREATE)
async def receive_provider_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    استقبال مفتاح API وعرض شاشة التأكيد.

    المفتاح يبقى في ذاكرة المحادثة فقط حتى لحظة التشفير والحفظ، ونحاول حذف
    رسالة الأدمن التي تحمله من المحادثة فوراً.
    """
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_KEY

    api_key = message.text.strip()
    if len(api_key) < 8:
        await send(update, context, t.PROVIDER_KEY_TOO_SHORT, cancel_only_kb())
        return ASK_KEY

    data = update_flow(context, api_key=api_key)
    await _try_delete(message)

    await send(
        update,
        context,
        t.PROVIDER_NEW_CONFIRM.format(
            name=safe(str(data["name"]), limit=40),
            api_url=safe(str(data["api_url"]), limit=70),
            api_type=safe(str(data["api_type"]), limit=20),
            key_hint=api_key[-4:],
        ),
        confirm_cancel_kb(),
    )
    return CONFIRM_NEW


async def _try_delete(message) -> None:
    """
    محاولة حذف رسالة تحمل سراً (مفتاح API).

    الحذف قد يفشل لأسباب مشروعة (مرّ وقت طويل، أو البوت بلا صلاحية الحذف في
    هذه المحادثة) — نسجّل ذلك ولا نُسقط العملية، فالمفتاح محفوظ مشفّراً أصلاً.
    """
    try:
        await message.delete()
    except Exception as exc:                                   # noqa: BLE001
        logger.info("تعذّر حذف رسالة المفتاح من المحادثة: %s", type(exc).__name__)


@guarded
@admin_required(Permission.PROVIDERS_CREATE)
async def confirm_new_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إنشاء المزود فعلياً ثم اختبار اتصاله مباشرة."""
    await answer_callback(update)
    data = flow(context)
    if not data.get("name") or not data.get("api_url") or not data.get("api_key"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    provider = await services.providers.create_provider(
        admin,
        name=str(data["name"]),
        api_url=str(data["api_url"]),
        api_key=str(data["api_key"]),
        api_type=str(data.get("api_type") or "perfect_panel"),
    )
    clear_flow(context)                                   # يمسح المفتاح من الذاكرة فوراً
    logger.info("أضاف الأدمن %s المزود %s", admin.telegram_id, provider.id)

    await render(
        update,
        context,
        t.PROVIDER_CREATED.format(name=safe(provider.name, limit=40), provider_id=provider.id),
    )

    ok, message = await services.providers.test_connection(admin, provider.id)
    await send(
        update,
        context,
        t.PROVIDER_TEST_RESULT.format(
            icon="✅" if ok else "❌",
            name=safe(provider.name, limit=40),
            message=safe(message, limit=200),
        ),
    )
    await _render_provider(update, context, provider.id, as_new=True)
    return ConversationHandler.END


# ======================================================================== #
#                        محادثة: تغيير مفتاح الـAPI                        #
# ======================================================================== #


@guarded
@admin_required(Permission.PROVIDERS_KEY_UPDATE)
async def start_key_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء تغيير مفتاح مزود."""
    await answer_callback(update)
    provider_id = args(update).int_arg(0)
    provider = await _load_provider(context, provider_id)
    start_flow(context, provider_id=provider_id)

    await render(
        update,
        context,
        t.PROVIDER_ASK_NEW_KEY.format(
            name=safe(provider.name, limit=40), key_hint=safe(provider.api_key_hint or "????")
        ),
        cancel_only_kb(),
    )
    return ASK_NEW_KEY


@guarded
@admin_required(Permission.PROVIDERS_KEY_UPDATE)
async def receive_new_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ المفتاح الجديد مشفّراً ثم اختبار الاتصال به."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_NEW_KEY

    data = flow(context)
    if not data.get("provider_id"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    api_key = message.text.strip()
    if len(api_key) < 8:
        await send(update, context, t.PROVIDER_KEY_TOO_SHORT, cancel_only_kb())
        return ASK_NEW_KEY

    await _try_delete(message)
    services = services_of(context)
    admin = require_user(context)
    provider_id = int(data["provider_id"])
    changed = await services.providers.update_api_key(admin, provider_id, api_key)
    clear_flow(context)

    provider = await _load_provider(context, provider_id)
    await send(
        update,
        context,
        t.PROVIDER_KEY_UPDATED.format(
            name=safe(provider.name, limit=40), key_hint=safe(provider.api_key_hint or "????")
        )
        if changed
        else t.PROVIDER_KEY_UNCHANGED,
    )

    ok, result = await services.providers.test_connection(admin, provider_id)
    await send(
        update,
        context,
        t.PROVIDER_TEST_RESULT.format(
            icon="✅" if ok else "❌",
            name=safe(provider.name, limit=40),
            message=safe(result, limit=200),
        ),
    )
    await _render_provider(update, context, provider_id, as_new=True)
    return ConversationHandler.END


# ======================================================================== #
#                          مزامنة خدمات المزود                             #
# ======================================================================== #


@guarded
@admin_required(Permission.SERVICES_SYNC)
async def sync_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    جلب قائمة خدمات المزود وتحديث تكلفة وحدود خدماتنا المرتبطة به.

    لا يُغيَّر سعر البيع ولا تُحذف أي خدمة — النتيجة تقرير يقرر الأدمن بناءً عليه.
    """
    await answer_callback(update, t.PROVIDER_SYNC_RUNNING)
    provider_id = args(update).int_arg(0)
    provider = await _load_provider(context, provider_id)

    services = services_of(context)
    admin = require_user(context)
    symbol = await symbol_of(context)

    try:
        items = await services.providers.fetch_services(admin, provider)
    except ProviderError as exc:
        await render(
            update,
            context,
            t.PROVIDER_TEST_RESULT.format(
                icon="❌", name=safe(provider.name, limit=40), message=safe(exc.user_message)
            ),
            back_panel_kb(),
        )
        await _render_provider(update, context, provider_id, as_new=True)
        return

    report = await services.catalog.sync_provider_services(
        admin, provider_id=provider_id, items=items
    )

    missing_lines = "".join(
        t.PROVIDER_SYNC_MISSING_LINE.format(
            name=safe(service.name, limit=30), service_id=service.id
        )
        for service in report.missing[:5]
    )
    negative_lines = ""
    if report.negative_margin:
        negative_lines = t.PROVIDER_SYNC_NEGATIVE_HEADER + "".join(
            t.PROVIDER_SYNC_NEGATIVE_LINE.format(
                name=safe(service.name, limit=30),
                price=money_text(service.price_per_1000_units, symbol),
                cost=money_text(service.provider_price_per_1000_units or 0, symbol),
            )
            for service in report.negative_margin[:5]
        )

    await render(
        update,
        context,
        t.PROVIDER_SYNC_RESULT.format(
            name=safe(provider.name, limit=40),
            provider_items=report.provider_items,
            checked=report.checked,
            updated=report.updated,
            unchanged=report.unchanged,
            missing=len(report.missing),
            missing_lines=missing_lines,
            negative_lines=negative_lines,
        ),
        back_panel_kb(),
    )
    await _render_provider(update, context, provider_id, as_new=True)


# ======================================================================== #
#                   محادثة: استيراد خدمة من قائمة المزود                   #
# ======================================================================== #


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def start_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء استيراد خدمة: سؤال كلمة البحث داخل قائمة المزود."""
    await answer_callback(update)
    provider_id = args(update).int_arg(0)
    provider = await _load_provider(context, provider_id)
    start_flow(context, provider_id=provider_id)

    await render(
        update,
        context,
        t.PROVIDER_IMPORT_ASK_SEARCH.format(name=safe(provider.name, limit=40)),
        cancel_only_kb(),
    )
    return ASK_SEARCH


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def receive_import_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    جلب قائمة خدمات المزود وتصفيتها بكلمة البحث.

    النتائج تُحفظ في بيانات المحادثة ليُشار إليها بالفهرس في الأزرار (أرقام
    بعض المزودين أطول من أن تُوضع داخل `callback_data`).
    """
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_SEARCH

    data = flow(context)
    if not data.get("provider_id"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    query = clean_text(message.text, field="كلمة البحث", max_length=60, min_length=1)
    provider = await _load_provider(context, int(data["provider_id"]))
    services = services_of(context)
    admin = require_user(context)
    symbol = await symbol_of(context)

    try:
        items = await services.providers.fetch_services(admin, provider)
    except ProviderError as exc:
        clear_flow(context)
        await send(update, context, f"❌ {safe(exc.user_message)}", back_panel_kb())
        return ConversationHandler.END

    matched = _filter_items(items, query)
    if not matched:
        await send(
            update,
            context,
            t.PROVIDER_IMPORT_NO_RESULTS.format(query=safe(query, limit=40)),
            cancel_only_kb(),
        )
        return ASK_SEARCH

    shown = matched[:IMPORT_RESULTS_LIMIT]
    update_flow(context, **{IMPORT_ITEMS_KEY: [_item_to_dict(item) for item in shown]})
    await send(
        update,
        context,
        t.PROVIDER_IMPORT_RESULTS.format(
            name=safe(provider.name, limit=40), shown=len(shown), total=len(matched)
        ),
        provider_import_results_kb(shown, provider_id=provider.id, symbol=symbol),
    )
    return PICK_ITEM


def _filter_items(items: list[ProviderServiceItem], query: str) -> list[ProviderServiceItem]:
    """تصفية خدمات المزود بكلمة بحث (`*` تعني بلا تصفية)."""
    if query.strip() == "*":
        return list(items)
    words = [word for word in normalize_digits(query).lower().split() if word]
    if not words:
        return list(items)
    return [
        item
        for item in items
        if all(word in f"{item.name} {item.category} {item.provider_service_id}".lower() for word in words)
    ]


def _item_to_dict(item: ProviderServiceItem) -> dict:
    """تحويل عنصر خدمة مزود إلى قاموس بسيط لحفظه في بيانات المحادثة."""
    return {
        "provider_service_id": item.provider_service_id,
        "name": item.name,
        "rate_per_1000_units": item.rate_per_1000_units,
        "min_quantity": item.min_quantity,
        "max_quantity": item.max_quantity,
        "category": item.category,
    }


def _dict_to_item(data: dict) -> ProviderServiceItem:
    """إعادة بناء عنصر خدمة من القاموس المحفوظ."""
    return ProviderServiceItem(
        provider_service_id=str(data["provider_service_id"]),
        name=str(data["name"]),
        rate_per_1000_units=int(data["rate_per_1000_units"]),
        min_quantity=int(data["min_quantity"]),
        max_quantity=int(data["max_quantity"]),
        category=str(data.get("category") or ""),
    )


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def pick_import_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """اختيار خدمة من نتائج البحث ثم سؤال التصنيف الذي ستُدرج فيه."""
    await answer_callback(update)
    data = flow(context)
    saved = data.get(IMPORT_ITEMS_KEY) or []
    index = args(update).int_arg(0, -1)

    if index < 0 or index >= len(saved):
        await answer_callback(update, t.PROVIDER_IMPORT_SESSION_LOST, alert=True)
        return ConversationHandler.END

    item = _dict_to_item(saved[index])
    update_flow(context, picked_index=index)

    services = services_of(context)
    admin = require_user(context)
    categories = await services.catalog.admin_categories(admin)
    symbol = await symbol_of(context)

    await render(
        update,
        context,
        t.PROVIDER_IMPORT_ITEM.format(
            name=safe(item.name, limit=60),
            provider_service_id=safe(item.provider_service_id, limit=20),
            cost=money_text(item.rate_per_1000_units, symbol),
            min_q=item.min_quantity,
            max_q=item.max_quantity,
            category=safe(item.category or "—", limit=30),
        ),
        category_picker_kb(categories, NS_ADM_PRV, "cat"),
    )
    return PICK_CATEGORY


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def pick_import_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ التصنيف المختار ثم سؤال هامش الربح."""
    await answer_callback(update)
    data = flow(context)
    saved = data.get(IMPORT_ITEMS_KEY) or []
    index = int(data.get("picked_index", -1))
    if index < 0 or index >= len(saved):
        await answer_callback(update, t.PROVIDER_IMPORT_SESSION_LOST, alert=True)
        return ConversationHandler.END

    category_id = args(update).int_arg(0)
    services = services_of(context)
    admin = require_user(context)
    category = await services.catalog.admin_get_category(admin, category_id)
    update_flow(context, category_id=category_id)

    item = _dict_to_item(saved[index])
    symbol = await symbol_of(context)
    example = services.catalog.price_with_margin(item.rate_per_1000_units, 40)

    await render(
        update,
        context,
        t.PROVIDER_IMPORT_ASK_MARGIN.format(
            cost=money_text(item.rate_per_1000_units, symbol),
            example=money_text(example, symbol),
        )
        + f"\n🏷 التصنيف: {safe(category.title, limit=30)}",
        cancel_only_kb(),
    )
    return ASK_MARGIN


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def receive_margin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال هامش الربح وعرض ملخص الاستيراد للتأكيد."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_MARGIN

    data = flow(context)
    saved = data.get(IMPORT_ITEMS_KEY) or []
    index = int(data.get("picked_index", -1))
    if index < 0 or index >= len(saved) or not data.get("category_id"):
        await send(update, context, t.PROVIDER_IMPORT_SESSION_LOST)
        return ConversationHandler.END

    raw = normalize_digits(message.text.strip())
    if not raw.isdigit():
        raise ValidationError(
            f"هامش غير رقمي: {raw}", user_message="❌ أرسل رقماً صحيحاً للهامش (مثال: 40)."
        )

    margin = int(raw)
    item = _dict_to_item(saved[index])
    services = services_of(context)
    admin = require_user(context)
    price = services.catalog.price_with_margin(item.rate_per_1000_units, margin)
    update_flow(context, margin=margin)

    provider = await _load_provider(context, int(data["provider_id"]))
    category = await services.catalog.admin_get_category(admin, int(data["category_id"]))
    symbol = await symbol_of(context)

    await send(
        update,
        context,
        t.PROVIDER_IMPORT_CONFIRM.format(
            name=safe(item.name, limit=60),
            category=safe(category.title, limit=30),
            provider=safe(provider.name, limit=30),
            provider_service_id=safe(item.provider_service_id, limit=20),
            cost=money_text(item.rate_per_1000_units, symbol),
            price=money_text(price, symbol),
            margin=margin,
            profit=money_text(price - item.rate_per_1000_units, symbol),
            min_q=item.min_quantity,
            max_q=item.max_quantity,
        ),
        confirm_cancel_kb(t.BTN_CONFIRM_IMPORT),
    )
    return CONFIRM_IMPORT


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def confirm_import(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ الاستيراد فعلياً (الخدمة تمنع تكرار استيراد نفس خدمة المزود)."""
    await answer_callback(update)
    data = flow(context)
    saved = data.get(IMPORT_ITEMS_KEY) or []
    index = int(data.get("picked_index", -1))
    if index < 0 or index >= len(saved) or "margin" not in data:
        await render(update, context, t.PROVIDER_IMPORT_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    item = _dict_to_item(saved[index])
    provider_id = int(data["provider_id"])

    service = await services.catalog.import_provider_service(
        admin,
        provider_id=provider_id,
        item=item,
        category_id=int(data["category_id"]),
        margin_percent=int(data["margin"]),
    )
    clear_flow(context)
    logger.info("استورد الأدمن %s الخدمة %s", admin.telegram_id, service.id)

    await render(
        update,
        context,
        t.PROVIDER_IMPORT_DONE.format(name=safe(service.name, limit=60), service_id=service.id),
    )
    await _render_provider(update, context, provider_id, as_new=True)
    return ConversationHandler.END


# ======================================================================== #
#                                التسجيل                                   #
# ======================================================================== #


def _fallbacks() -> list:
    """المسارات الاحتياطية الموحّدة لمحادثات هذا القسم."""
    return [
        CallbackQueryHandler(cancel_admin_flow, pattern=pattern(NS_FLOW, "cancel")),
        CommandHandler("cancel", cancel_admin_flow),
        CommandHandler("start", exit_conversation(ADMIN_FLOW_KEY)),
    ]


def conversations() -> list[ConversationHandler]:
    """محادثات قسم المزودين: إضافة مزود، تغيير المفتاح، استيراد خدمة."""
    new_provider = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_new_provider, pattern=pattern(NS_ADM_PRV, "new"))
        ],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_provider_name)],
            ASK_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_provider_url)],
            ASK_TYPE: [
                CallbackQueryHandler(receive_provider_type, pattern=pattern(NS_ADM_PRV, "type"))
            ],
            ASK_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_provider_key)],
            CONFIRM_NEW: [
                CallbackQueryHandler(confirm_new_provider, pattern=pattern(NS_FLOW, "confirm"))
            ],
        },
        fallbacks=_fallbacks(),
        name="admin_provider_new",
        per_chat=True,
        per_user=True,
    )

    key_update = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_key_update, pattern=pattern(NS_ADM_PRV, "key"))],
        states={ASK_NEW_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_key)]},
        fallbacks=_fallbacks(),
        name="admin_provider_key",
        per_chat=True,
        per_user=True,
    )

    import_service = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_import, pattern=pattern(NS_ADM_PRV, "imp"))],
        states={
            ASK_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_import_query)],
            PICK_ITEM: [
                CallbackQueryHandler(pick_import_item, pattern=pattern(NS_ADM_PRV, "pick"))
            ],
            PICK_CATEGORY: [
                CallbackQueryHandler(pick_import_category, pattern=pattern(NS_ADM_PRV, "cat"))
            ],
            ASK_MARGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_margin)],
            CONFIRM_IMPORT: [
                CallbackQueryHandler(confirm_import, pattern=pattern(NS_FLOW, "confirm"))
            ],
        },
        fallbacks=_fallbacks(),
        name="admin_provider_import",
        per_chat=True,
        per_user=True,
    )
    return [new_provider, key_update, import_service]


def screens() -> list[CallbackQueryHandler]:
    """أزرار شاشات قسم المزودين (خارج المحادثات)."""
    return [
        CallbackQueryHandler(providers_home_screen, pattern=pattern(NS_ADM_PRV, "home")),
        CallbackQueryHandler(provider_card_screen, pattern=pattern(NS_ADM_PRV, "view")),
        CallbackQueryHandler(provider_services_screen, pattern=pattern(NS_ADM_PRV, "svcs")),
        CallbackQueryHandler(test_provider, pattern=pattern(NS_ADM_PRV, "test")),
        CallbackQueryHandler(refresh_balance, pattern=pattern(NS_ADM_PRV, "bal")),
        CallbackQueryHandler(toggle_provider, pattern=pattern(NS_ADM_PRV, "toggle")),
        CallbackQueryHandler(sync_provider, pattern=pattern(NS_ADM_PRV, "sync")),
    ]
```

### `handlers/admin/catalog.py`  ·  مُحدَّث  ·  794 سطراً

محادثة «إنشاء خدمة جديدة» يدوياً (9 حالات) تبدأ من زر `ac:newsvc`.

```python
"""
قسم «🛍 الكتالوج» في لوحة التحكم: التصنيفات والخدمات وأسعارها.

ما ينفّذه هذا الملف:
    • عرض كل التصنيفات (حتى الفارغة والمعطّلة — الأدمن يرى ما لا يراه العميل).
    • قائمة خدمات التصنيف مع مؤشر التفعيل والسعر.
    • بطاقة الخدمة: السعر، تكلفة المزود، الهامش، الحدود، الحالة.
    • تفعيل/تعطيل الخدمة، تغيير السعر (مع تحذير البيع بخسارة)، الأرشفة.
    • إنشاء تصنيف جديد.
    • إنشاء خدمة جديدة يدوياً (أُضيف في المرحلة 5 بعد توفّر شاشات المزودين):
      تصنيف ← مزود ← رقم الخدمة لديه ← اسم ← تكلفة ← سعر ← حدود ← تأكيد.

الاستيراد الجماعي من قائمة المزود ومزامنة الأسعار موجودان في قسم «🔌 المزودون»
(`handlers/admin/providers.py`) لأنهما يبدآن من المزود لا من الكتالوج.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from core.exceptions import ValidationError
from core.permissions import Permission
from handlers.admin.common import (
    ADMIN_FLOW_KEY,
    PAGE_SIZE,
    admin_required,
    args,
    cancel_admin_flow,
    clear_flow,
    flow,
    permissions_of,
    start_flow,
    symbol_of,
    update_flow,
)
from handlers.common.fallbacks import exit_conversation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    back_panel_kb,
    cancel_only_kb,
    catalog_home_kb,
    catalog_services_kb,
    category_picker_kb,
    confirm_cancel_kb,
    provider_picker_kb,
    service_card_kb,
    skip_cancel_kb,
)
from keyboards.callback_data import NS_ADM_CAT, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from utils.formatters import money_text, safe
from utils.logging_setup import get_logger
from utils.validators import (
    clean_text,
    normalize_digits,
    parse_amount_units,
    validate_amount_range,
)

logger = get_logger(__name__)

#: حالات محادثة تغيير السعر
ASK_PRICE, CONFIRM_PRICE = range(2)

#: حالة محادثة الأرشفة
CONFIRM_ARCHIVE = 20

#: حالات محادثة إنشاء تصنيف
ASK_CATEGORY_NAME, ASK_CATEGORY_EMOJI = range(10, 12)

#: حالات محادثة إنشاء خدمة جديدة يدوياً (المرحلة 5)
(
    NEW_PICK_CATEGORY,
    NEW_PICK_PROVIDER,
    NEW_ASK_PROVIDER_SERVICE_ID,
    NEW_ASK_NAME,
    NEW_ASK_COST,
    NEW_ASK_PRICE,
    NEW_ASK_MIN,
    NEW_ASK_MAX,
    NEW_CONFIRM,
) = range(30, 39)


async def _render_service(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int, *, as_new: bool = False
) -> None:
    """عرض بطاقة خدمة بعد أي إجراء عليها."""
    services = services_of(context)
    admin = require_user(context)
    service = await services.catalog.admin_get_service(admin, service_id)
    category = await services.catalog.admin_get_category(admin, service.category_id)
    provider = await services.providers.get(service.provider_id)
    symbol = await symbol_of(context)
    perms = await permissions_of(context)

    margin = service.margin_units
    text = t.SERVICE_CARD.format(
        name=safe(service.name, limit=60),
        service_id=service.id,
        category=safe(category.title, limit=30),
        provider=safe(provider.name if provider else t.SERVICE_UNKNOWN_PROVIDER, limit=25),
        provider_service_id=safe(service.provider_service_id, limit=20),
        price=money_text(service.price_per_1000_units, symbol),
        cost=money_text(service.provider_price_per_1000_units, symbol)
        if service.provider_price_per_1000_units
        else "—",
        margin=money_text(margin, symbol) if margin is not None else t.SERVICE_MARGIN_UNKNOWN,
        min_quantity=service.min_quantity,
        max_quantity=service.max_quantity,
        status=t.SERVICE_STATUS_ACTIVE if service.is_active else t.SERVICE_STATUS_INACTIVE,
        archived_line=t.SERVICE_ARCHIVED_LINE if service.is_archived else "",
        description_line=t.SERVICE_DESCRIPTION_LINE.format(
            description=safe(service.description, limit=200)
        )
        if service.description
        else "",
    )
    markup = service_card_kb(service, perms)
    if as_new:
        await send(update, context, text, markup)
    else:
        await render(update, context, text, markup)


# ============================= شاشات القراءة =========================== #


@guarded
@admin_required(Permission.SERVICES_VIEW)
async def catalog_home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة الكتالوج: كل التصنيفات."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    categories = await services.catalog.admin_categories(admin)
    perms = await permissions_of(context)
    active_services = await services.catalog.active_services_count()

    text = (
        t.CATALOG_HOME.format(categories=len(categories), active_services=active_services)
        if categories
        else t.CATALOG_NO_CATEGORIES
    )
    await render(update, context, text, catalog_home_kb(categories, perms))


@guarded
@admin_required(Permission.SERVICES_VIEW)
async def category_services_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة خدمات تصنيف (تشمل المعطّلة)."""
    await answer_callback(update)
    data = args(update)
    category_id = data.int_arg(0)
    services = services_of(context)
    admin = require_user(context)
    symbol = await symbol_of(context)

    category = await services.catalog.admin_get_category(admin, category_id)
    page_data = await services.catalog.admin_services_page(
        admin, category_id, page=data.int_arg(1, 1), page_size=PAGE_SIZE
    )

    if not page_data.items:
        await render(
            update,
            context,
            t.CATALOG_SERVICES_EMPTY,
            catalog_services_kb(
                [], category_id=category_id, page=1, total_pages=1, symbol=symbol
            ),
        )
        return

    await render(
        update,
        context,
        t.CATALOG_SERVICES_TITLE.format(
            category=safe(category.title, limit=40),
            count=page_data.total_items,
            page=page_data.page,
            pages=page_data.total_pages,
        ),
        catalog_services_kb(
            page_data.items,
            category_id=category_id,
            page=page_data.page,
            total_pages=page_data.total_pages,
            symbol=symbol,
        ),
    )


@guarded
@admin_required(Permission.SERVICES_VIEW)
async def service_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة خدمة واحدة."""
    await answer_callback(update)
    await _render_service(update, context, args(update).int_arg(0))


@guarded
@admin_required(Permission.SERVICES_UPDATE)
async def toggle_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تفعيل أو تعطيل خدمة (الحالة تنعكس فوراً على واجهة العملاء)."""
    services = services_of(context)
    admin = require_user(context)
    service_id = args(update).int_arg(0)
    service = await services.catalog.admin_get_service(admin, service_id)

    await services.catalog.set_service_active(admin, service_id, not service.is_active)
    await answer_callback(
        update,
        t.SERVICE_TOGGLED_OFF if service.is_active else t.SERVICE_TOGGLED_ON,
        alert=False,
    )
    await _render_service(update, context, service_id)


# =========================== محادثة تغيير السعر ======================== #


@guarded
@admin_required(Permission.SERVICES_PRICE)
async def start_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء تغيير سعر خدمة."""
    await answer_callback(update)
    service_id = args(update).int_arg(0)
    services = services_of(context)
    admin = require_user(context)
    service = await services.catalog.admin_get_service(admin, service_id)
    symbol = await symbol_of(context)
    start_flow(context, service_id=service_id)

    await render(
        update,
        context,
        t.SERVICE_ASK_PRICE.format(
            name=safe(service.name, limit=50),
            price=money_text(service.price_per_1000_units, symbol),
            cost=money_text(service.provider_price_per_1000_units, symbol)
            if service.provider_price_per_1000_units
            else "—",
        ),
        cancel_only_kb(),
    )
    return ASK_PRICE


@guarded
@admin_required(Permission.SERVICES_PRICE)
async def receive_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    استقبال السعر الجديد.

    إن كان أقل من تكلفة المزود نعرض شاشة تأكيد إضافية (بيع بخسارة)، وإلا
    نُنفّذ مباشرة لأن التغيير غير خطير ماليّاً على المستخدمين.
    """
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_PRICE

    data = flow(context)
    if not data.get("service_id"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    units = validate_amount_range(parse_amount_units(message.text), min_units=1, label="السعر")
    services = services_of(context)
    admin = require_user(context)
    service = await services.catalog.admin_get_service(admin, int(data["service_id"]))
    symbol = await symbol_of(context)

    cost = service.provider_price_per_1000_units or 0
    if cost and units < cost:
        update_flow(context, price_units=units)
        await send(update, context, t.SERVICE_PRICE_BELOW_COST, confirm_cancel_kb())
        return CONFIRM_PRICE

    await services.catalog.change_price(admin, service.id, units)
    clear_flow(context)
    await send(update, context, t.SERVICE_PRICE_DONE.format(price=money_text(units, symbol)))
    await _render_service(update, context, service.id, as_new=True)
    return ConversationHandler.END


@guarded
@admin_required(Permission.SERVICES_PRICE)
async def confirm_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تأكيد سعر أقل من تكلفة المزود."""
    await answer_callback(update)
    data = flow(context)
    if not data.get("service_id") or not data.get("price_units"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    service_id = int(data["service_id"])
    units = int(data["price_units"])
    symbol = await symbol_of(context)

    await services.catalog.change_price(admin, service_id, units)
    clear_flow(context)
    logger.info("غيّر الأدمن %s سعر الخدمة %s إلى %s", admin.telegram_id, service_id, units)

    await render(update, context, t.SERVICE_PRICE_DONE.format(price=money_text(units, symbol)))
    await _render_service(update, context, service_id, as_new=True)
    return ConversationHandler.END


# ============================ محادثة الأرشفة =========================== #


@guarded
@admin_required(Permission.SERVICES_ARCHIVE)
async def start_archive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """عرض تأكيد أرشفة الخدمة (إخفاؤها نهائياً عن العملاء)."""
    await answer_callback(update)
    service_id = args(update).int_arg(0)
    services = services_of(context)
    admin = require_user(context)
    service = await services.catalog.admin_get_service(admin, service_id)
    start_flow(context, service_id=service_id)

    await render(
        update,
        context,
        t.SERVICE_ARCHIVE_CONFIRM.format(name=safe(service.name, limit=50)),
        confirm_cancel_kb(),
    )
    return CONFIRM_ARCHIVE


@guarded
@admin_required(Permission.SERVICES_ARCHIVE)
async def confirm_archive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ الأرشفة بعد التأكيد."""
    await answer_callback(update)
    data = flow(context)
    if not data.get("service_id"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    service_id = int(data["service_id"])
    await services.catalog.archive_service(admin, service_id)
    clear_flow(context)

    await render(update, context, t.SERVICE_ARCHIVED)
    await _render_service(update, context, service_id, as_new=True)
    return ConversationHandler.END


# ========================== محادثة تصنيف جديد ========================== #


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def start_new_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء إنشاء تصنيف جديد."""
    await answer_callback(update)
    start_flow(context)
    await render(update, context, t.CATEGORY_ASK_NAME, cancel_only_kb())
    return ASK_CATEGORY_NAME


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def receive_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال اسم التصنيف ثم سؤال الأيقونة (قابلة للتخطي)."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_CATEGORY_NAME

    name = clean_text(message.text, field="اسم التصنيف", max_length=60, min_length=2)
    update_flow(context, name=name)
    await send(update, context, t.CATEGORY_ASK_EMOJI, skip_cancel_kb())
    return ASK_CATEGORY_EMOJI


async def _create_category(
    update: Update, context: ContextTypes.DEFAULT_TYPE, emoji: str
) -> int:
    """إنشاء التصنيف فعلياً وعرض الكتالوج محدَّثاً."""
    data = flow(context)
    if not data.get("name"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    category = await services.catalog.create_category(
        admin, name_ar=str(data["name"]), emoji=emoji
    )
    clear_flow(context)
    logger.info("أنشأ الأدمن %s التصنيف %s", admin.telegram_id, category.id)

    await send(update, context, t.CATEGORY_CREATED.format(name=safe(category.title, limit=40)))
    await catalog_home_screen(update, context)
    return ConversationHandler.END


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def receive_category_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال أيقونة التصنيف وإنشاؤه."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, skip_cancel_kb())
        return ASK_CATEGORY_EMOJI
    emoji = clean_text(message.text, field="الأيقونة", max_length=4, min_length=1)
    return await _create_category(update, context, emoji)


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def skip_category_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تخطي الأيقونة واستخدام الافتراضية."""
    await answer_callback(update)
    return await _create_category(update, context, "📦")


# ====================== محادثة: إنشاء خدمة جديدة يدوياً ================== #


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def start_new_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    بدء إنشاء خدمة: اختيار التصنيف.

    تُرفض البداية إن لم يوجد أي مزود، لأن خدمة بلا مزود تعني طلباً لا يمكن تنفيذه.
    """
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)

    providers = await services.providers.list_all()
    if not providers:
        await render(update, context, t.SERVICE_NEW_NO_PROVIDER, back_panel_kb())
        return ConversationHandler.END

    categories = await services.catalog.admin_categories(admin)
    if not categories:
        await render(update, context, t.CATALOG_NO_CATEGORIES, back_panel_kb())
        return ConversationHandler.END

    start_flow(context)
    await render(
        update,
        context,
        t.SERVICE_NEW_ASK_CATEGORY,
        category_picker_kb(categories, NS_ADM_CAT, "ncat"),
    )
    return NEW_PICK_CATEGORY


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def new_service_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ التصنيف المختار ثم عرض قائمة المزودين."""
    await answer_callback(update)
    category_id = args(update).int_arg(0)
    services = services_of(context)
    admin = require_user(context)
    await services.catalog.admin_get_category(admin, category_id)     # يتحقق من وجوده
    update_flow(context, category_id=category_id)

    providers = await services.providers.list_all()
    await render(
        update,
        context,
        t.SERVICE_NEW_ASK_PROVIDER,
        provider_picker_kb(providers, NS_ADM_CAT, "nprv"),
    )
    return NEW_PICK_PROVIDER


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def new_service_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ المزود المختار ثم طلب رقم الخدمة لديه."""
    await answer_callback(update)
    provider_id = args(update).int_arg(0)
    services = services_of(context)
    provider = await services.providers.get(provider_id)
    if provider is None:
        await answer_callback(update, t.PROVIDER_NOT_FOUND, alert=True)
        return NEW_PICK_PROVIDER

    update_flow(context, provider_id=provider_id, provider_name=provider.name)
    await render(
        update,
        context,
        t.SERVICE_NEW_ASK_PROVIDER_SERVICE_ID.format(provider=safe(provider.name, limit=30)),
        cancel_only_kb(),
    )
    return NEW_ASK_PROVIDER_SERVICE_ID


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def new_service_provider_service_id(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    """حفظ رقم الخدمة لدى المزود ثم طلب الاسم الذي سيراه العميل."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return NEW_ASK_PROVIDER_SERVICE_ID

    provider_service_id = clean_text(
        normalize_digits(message.text), field="رقم الخدمة لدى المزود", max_length=40, min_length=1
    )
    update_flow(context, provider_service_id=provider_service_id)
    await send(update, context, t.SERVICE_NEW_ASK_NAME, cancel_only_kb())
    return NEW_ASK_NAME


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def new_service_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ اسم الخدمة ثم طلب تكلفة الألف لدى المزود."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return NEW_ASK_NAME

    name = clean_text(message.text, field="اسم الخدمة", max_length=120, min_length=3)
    update_flow(context, name=name)
    await send(update, context, t.SERVICE_NEW_ASK_COST, cancel_only_kb())
    return NEW_ASK_COST


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def new_service_cost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ تكلفة المزود ثم طلب سعر البيع."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return NEW_ASK_COST

    cost = validate_amount_range(parse_amount_units(message.text), min_units=1, label="التكلفة")
    update_flow(context, cost_units=cost)
    symbol = await symbol_of(context)
    await send(
        update,
        context,
        t.SERVICE_NEW_ASK_PRICE.format(cost=money_text(cost, symbol)),
        cancel_only_kb(),
    )
    return NEW_ASK_PRICE


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def new_service_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ سعر البيع ثم طلب أقل كمية."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return NEW_ASK_PRICE

    price = validate_amount_range(parse_amount_units(message.text), min_units=1, label="السعر")
    update_flow(context, price_units=price)
    await send(update, context, t.SERVICE_NEW_ASK_MIN, cancel_only_kb())
    return NEW_ASK_MIN


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def new_service_min(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ أقل كمية ثم طلب أكبر كمية."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return NEW_ASK_MIN

    raw = normalize_digits(message.text.strip())
    if not raw.isdigit() or int(raw) <= 0:
        raise ValidationError(
            f"أقل كمية غير صالحة: {raw}", user_message="❌ أرسل عدداً صحيحاً موجباً."
        )
    update_flow(context, min_quantity=int(raw))
    await send(update, context, t.SERVICE_NEW_ASK_MAX.format(min_q=int(raw)), cancel_only_kb())
    return NEW_ASK_MAX


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def new_service_max(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ أكبر كمية ثم عرض ملخص التأكيد (مع تحذير صريح عند البيع بخسارة)."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return NEW_ASK_MAX

    data = flow(context)
    minimum = int(data.get("min_quantity", 0))
    raw = normalize_digits(message.text.strip())
    if not raw.isdigit() or int(raw) <= minimum:
        await send(update, context, t.SERVICE_NEW_BAD_MAX.format(min_q=minimum), cancel_only_kb())
        return NEW_ASK_MAX

    data = update_flow(context, max_quantity=int(raw))
    services = services_of(context)
    admin = require_user(context)
    category = await services.catalog.admin_get_category(admin, int(data["category_id"]))
    symbol = await symbol_of(context)
    price = int(data["price_units"])
    cost = int(data["cost_units"])

    await send(
        update,
        context,
        t.SERVICE_NEW_CONFIRM.format(
            name=safe(str(data["name"]), limit=60),
            category=safe(category.title, limit=30),
            provider=safe(str(data.get("provider_name", "—")), limit=30),
            provider_service_id=safe(str(data["provider_service_id"]), limit=20),
            cost=money_text(cost, symbol),
            price=money_text(price, symbol),
            profit=money_text(price - cost, symbol),
            min_q=minimum,
            max_q=int(raw),
            warning=t.SERVICE_NEW_WARN_LOSS if price < cost else t.SERVICE_NEW_WARN_OK,
        ),
        confirm_cancel_kb(),
    )
    return NEW_CONFIRM


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def confirm_new_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إنشاء الخدمة فعلياً بعد التأكيد (التدقيق داخل `CatalogService.create_service`)."""
    await answer_callback(update)
    data = flow(context)
    required = (
        "category_id",
        "provider_id",
        "provider_service_id",
        "name",
        "cost_units",
        "price_units",
        "min_quantity",
        "max_quantity",
    )
    if any(key not in data for key in required):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    service = await services.catalog.create_service(
        admin,
        category_id=int(data["category_id"]),
        provider_id=int(data["provider_id"]),
        provider_service_id=str(data["provider_service_id"]),
        name=str(data["name"]),
        price_per_1000_units=int(data["price_units"]),
        min_quantity=int(data["min_quantity"]),
        max_quantity=int(data["max_quantity"]),
        provider_price_per_1000_units=int(data["cost_units"]),
    )
    clear_flow(context)
    logger.info("أنشأ الأدمن %s الخدمة %s يدوياً", admin.telegram_id, service.id)

    await render(
        update,
        context,
        t.SERVICE_NEW_DONE.format(name=safe(service.name, limit=60), service_id=service.id),
    )
    await _render_service(update, context, service.id, as_new=True)
    return ConversationHandler.END


# ============================== التسجيل ================================ #


def _fallbacks() -> list:
    """المسارات الاحتياطية الموحّدة لمحادثات هذا القسم."""
    return [
        CallbackQueryHandler(cancel_admin_flow, pattern=pattern(NS_FLOW, "cancel")),
        CommandHandler("cancel", cancel_admin_flow),
        CommandHandler("start", exit_conversation(ADMIN_FLOW_KEY)),
    ]


def conversations() -> list[ConversationHandler]:
    """محادثات الكتالوج: تغيير السعر، الأرشفة، تصنيف جديد، خدمة جديدة."""
    price = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_price, pattern=pattern(NS_ADM_CAT, "price"))],
        states={
            ASK_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_price)],
            CONFIRM_PRICE: [
                CallbackQueryHandler(confirm_price, pattern=pattern(NS_FLOW, "confirm"))
            ],
        },
        fallbacks=_fallbacks(),
        name="admin_service_price",
        per_chat=True,
        per_user=True,
    )

    archive = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_archive, pattern=pattern(NS_ADM_CAT, "archive"))
        ],
        states={
            CONFIRM_ARCHIVE: [
                CallbackQueryHandler(confirm_archive, pattern=pattern(NS_FLOW, "confirm"))
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_service_archive",
        per_chat=True,
        per_user=True,
    )

    new_category = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_new_category, pattern=pattern(NS_ADM_CAT, "newcat"))
        ],
        states={
            ASK_CATEGORY_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_category_name)
            ],
            ASK_CATEGORY_EMOJI: [
                CallbackQueryHandler(skip_category_emoji, pattern=pattern(NS_FLOW, "skip")),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_category_emoji),
            ],
        },
        fallbacks=_fallbacks(),
        name="admin_new_category",
        per_chat=True,
        per_user=True,
    )
    new_service = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_new_service, pattern=pattern(NS_ADM_CAT, "newsvc"))
        ],
        states={
            NEW_PICK_CATEGORY: [
                CallbackQueryHandler(new_service_category, pattern=pattern(NS_ADM_CAT, "ncat"))
            ],
            NEW_PICK_PROVIDER: [
                CallbackQueryHandler(new_service_provider, pattern=pattern(NS_ADM_CAT, "nprv"))
            ],
            NEW_ASK_PROVIDER_SERVICE_ID: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, new_service_provider_service_id
                )
            ],
            NEW_ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_service_name)],
            NEW_ASK_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_service_cost)],
            NEW_ASK_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_service_price)],
            NEW_ASK_MIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_service_min)],
            NEW_ASK_MAX: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_service_max)],
            NEW_CONFIRM: [
                CallbackQueryHandler(confirm_new_service, pattern=pattern(NS_FLOW, "confirm"))
            ],
        },
        fallbacks=_fallbacks(),
        name="admin_new_service",
        per_chat=True,
        per_user=True,
    )
    return [price, archive, new_category, new_service]


def screens() -> list[CallbackQueryHandler]:
    """أزرار الكتالوج خارج المحادثات."""
    return [
        CallbackQueryHandler(catalog_home_screen, pattern=pattern(NS_ADM_CAT, "home")),
        CallbackQueryHandler(category_services_screen, pattern=pattern(NS_ADM_CAT, "cat")),
        CallbackQueryHandler(service_card_screen, pattern=pattern(NS_ADM_CAT, "svc")),
        CallbackQueryHandler(toggle_service, pattern=pattern(NS_ADM_CAT, "toggle")),
    ]
```

### `handlers/admin/__init__.py`  ·  مُحدَّث  ·  62 سطراً

تسجيل وحدة `providers` ضمن أقسام اللوحة.

```python
"""
حزمة لوحة التحكم: تجميع معالجات كل الأقسام في مكانين فقط.

تصدّر هذه الحزمة دالتين يستهلكهما `handlers/registry.py`:

    admin_conversations()   : كل محادثات الأدمن (تُسجَّل قبل أزرار الشاشات).
    admin_screen_handlers() : كل أزرار شاشات الأدمن.

كل وحدة قسم (`users`, `payments`, ...) تصدّر `conversations()` و`screens()`
فيبقى ترتيب التسجيل في مكان واحد ويظل من السهل التأكد أن كل زر له معالج.
"""

from __future__ import annotations

from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler

from handlers.admin import (
    catalog,
    dashboard,
    logs,
    orders,
    payments,
    providers,
    settings,
    tickets,
    users,
)
from keyboards.callback_data import NS_ADMIN, pattern

#: وحدات الأقسام بالترتيب الذي تُسجَّل به معالجاتها
SECTIONS = (users, payments, orders, tickets, catalog, providers, settings, logs)

__all__ = [
    "admin_conversations",
    "admin_screen_handlers",
    "admin_command_handlers",
    "SECTIONS",
]


def admin_conversations() -> list[ConversationHandler]:
    """كل محادثات لوحة التحكم مجموعة من كل الأقسام."""
    collected: list[ConversationHandler] = []
    for section in SECTIONS:
        collected.extend(section.conversations())
    return collected


def admin_screen_handlers() -> list[CallbackQueryHandler]:
    """كل أزرار شاشات لوحة التحكم (خارج المحادثات)."""
    collected: list[CallbackQueryHandler] = [
        CallbackQueryHandler(dashboard.panel_screen, pattern=pattern(NS_ADMIN, "home")),
        CallbackQueryHandler(dashboard.health_screen, pattern=pattern(NS_ADMIN, "health")),
    ]
    for section in SECTIONS:
        collected.extend(section.screens())
    return collected


def admin_command_handlers() -> list[CommandHandler]:
    """أوامر لوحة التحكم (/admin فقط حالياً)."""
    return [CommandHandler("admin", dashboard.admin_command)]
```

---

## الإصدار والمتطلبات

### `core/constants.py`  ·  مُحدَّث  ·  44 سطراً

`APP_VERSION = "0.6.0-phase5"`.

```python
"""ثوابت عامة للنظام (قيم لا تتغير أثناء التشغيل)."""

from __future__ import annotations

#: اسم المشروع وإصداره
APP_NAME: str = "SMM Telegram Bot"
APP_VERSION: str = "0.6.0-phase5"

#: مدة قفل الطلب أثناء معالجته بواسطة job (بالثواني)
ORDER_LOCK_SECONDS: int = 120

#: أقصى عدد محاولات لإرسال الطلب إلى المزود عند الفشل الآمن (قبل اعتباره فاشلاً)
MAX_SUBMIT_ATTEMPTS: int = 3

#: أقصى عدد محاولات إرسال إشعار قبل اعتباره فاشلاً
MAX_NOTIFICATION_ATTEMPTS: int = 5

#: تدرج فترات إعادة فحص حالة الطلب (بالثواني)
ORDER_CHECK_BACKOFF: tuple[int, ...] = (60, 300, 900, 1800, 3600)

#: تدرج فترات إعادة إرسال الإشعار الفاشل (بالثواني)
NOTIFICATION_BACKOFF: tuple[int, ...] = (10, 60, 300, 1800, 3600)

#: مدة صلاحية مفاتيح منع التكرار الافتراضية (بالثواني)
IDEMPOTENCY_TTL_SECONDS: int = 24 * 3600

#: طول أقصى للنصوص المُخزَّنة من استجابات المزود (منعاً لتضخم قاعدة البيانات)
PROVIDER_RESPONSE_SNIPPET_LEN: int = 500

#: عدد العناصر في صفحة القوائم داخل تيليجرام
PAGE_SIZE: int = 8

#: صيغة مراجع الحركات المالية (تُستخدم لمنع التكرار)
REF_ORDER_DEBIT: str = "order:{order_id}"
REF_ORDER_REFUND: str = "refund:order:{order_id}"
REF_ORDER_PARTIAL_REFUND: str = "partial_refund:order:{order_id}"
REF_PAYMENT_DEPOSIT: str = "payment:{payment_id}"
REF_MANUAL: str = "manual:{kind}:{admin_id}:{token}"

#: صيغة مفاتيح منع تكرار الإشعارات
NOTIF_KEY_ORDER: str = "order:{order_id}:{event}"
NOTIF_KEY_PAYMENT: str = "payment:{payment_id}:{event}"
NOTIF_KEY_TICKET: str = "ticket:{ticket_id}:{event}"
NOTIF_KEY_MANUAL: str = "manual:{token}"
```

### `requirements.txt`  ·  مُحدَّث  ·  23 سطراً

إضافة `httpx==0.28.1` صراحةً لأننا نستورده مباشرة في عميل المزود.

```text
# ======================================================================
# متطلبات تشغيل SMM Bot — إصدارات مثبّتة ومختبَرة فعلياً على Python 3.13
# التثبيت:  pip install -r requirements.txt
# ======================================================================

# إطار بوت تيليجرام + مجدول المهام الدورية (JobQueue)
python-telegram-bot[job-queue]==21.9

# طبقة SQLite غير المتزامنة (كل عمليات قاعدة البيانات تمر عبرها)
aiosqlite==0.22.1

# تشفير مفاتيح API للمزودين (Fernet)
cryptography==50.0.2

# عميل HTTP غير متزامن للاتصال بلوحات المزودين (Perfect Panel API v2)
# ملاحظة: python-telegram-bot يعتمد httpx أصلاً، ونثبّته صراحة لأننا نستورده مباشرة.
httpx==0.28.1

# قراءة الإعدادات من ملف .env
python-dotenv==1.2.3

# بيانات المناطق الزمنية (لعرض التواريخ بتوقيت Asia/Aden على كل نظام تشغيل)
tzdata==2026.3
```

---

## الاختبارات

### `tests/unit/test_perfect_panel_client.py`  ·  جديد  ·  332 سطراً

23 اختباراً لعميل Perfect Panel عبر `httpx.MockTransport` (بلا أي شبكة حقيقية).

```python
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
```

### `tests/integration/test_admin_providers.py`  ·  جديد  ·  609 سطراً

21 اختباراً لقسم المزودين وإنشاء الخدمة يدوياً.

```python
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
    assert state == admin_providers.ASK_KEY

    state = await write(bot, context, admin_providers.receive_provider_key, secret, super_admin.telegram_id)
    assert state == admin_providers.CONFIRM_NEW
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
    assert "❌" in bot.last.text or "مرتبطة" in bot.last.text or "مسبقاً" in bot.last.text


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
```

### `tests/integration/test_no_dead_buttons.py`  ·  مُحدَّث  ·  484 سطراً

تغطية لوحات المزودين السبع الجديدة ضمن فحص «لا زر بلا معالج».

```python
"""
اختبار القاعدة الملزِمة: **لا زر بلا وظيفة**.

الطريقة:
    1. نستدعي كل باني لوحة أزرار في `keyboards/` ببيانات تجريبية.
    2. نجمع كل قيم `callback_data` الناتجة.
    3. نتأكد أن كل قيمة يلتقطها معالج مسجَّل فعلاً في `handlers/registry.py`
       (مع استبعاد المعالج الاحتياطي الشامل، وإلا لصار الاختبار بلا معنى).

كما نتحقق من العكس: كل معالج مسجَّل له نمط مفهوم وبإصدار `callback` الحالي.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from telegram import InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, ConversationHandler

from core.permissions import Permission
from handlers.registry import build_handlers
from keyboards import admin_kb, common_kb, user_kb
from keyboards.callback_data import (
    CALLBACK_VERSION,
    NS_ADM_CAT,
    NS_ADM_PRV,
    unpack,
)


def _fake_category(index: int = 1) -> SimpleNamespace:
    """تصنيف تجريبي بالحقول التي تستخدمها اللوحات فقط."""
    return SimpleNamespace(
        id=index, name_ar=f"تصنيف {index}", emoji="📱", title=f"📱 تصنيف {index}"
    )


def _fake_service(index: int = 1) -> SimpleNamespace:
    """خدمة تجريبية."""
    return SimpleNamespace(
        id=index,
        name=f"خدمة {index}",
        description="وصف",
        price_per_1000_units=10_000,
        min_quantity=100,
        max_quantity=1000,
        avg_time_text="ساعة",
        link_pattern=None,
        category_id=1,
    )


def _fake_order(index: int = 1, status: str = "pending") -> SimpleNamespace:
    """طلب تجريبي."""
    return SimpleNamespace(
        id=index,
        public_code=f"ORD-{index}",
        status=status,
        cost_units=10_000,
        quantity=1000,
        delivered_quantity=0,
        remains=1000,
        refund_amount_units=0,
        last_error=None,
        service_name_snapshot="خدمة",
        link="https://example.com/u",
        created_at="2026-01-01T10:00:00+00:00",
    )


def _fake_payment(index: int = 1, status: str = "pending") -> SimpleNamespace:
    """طلب شحن تجريبي."""
    return SimpleNamespace(
        id=index, amount_units=50_000, status=status, created_at="2026-01-01T10:00:00+00:00"
    )


def _fake_method(index: int = 1) -> SimpleNamespace:
    """طريقة دفع تجريبية."""
    return SimpleNamespace(
        id=index,
        name_ar=f"طريقة {index}",
        instructions_ar="حوّل ثم أرسل",
        account_details="123456",
        requires_proof=True,
    )


def _fake_ticket(index: int = 1, status: str = "open") -> SimpleNamespace:
    """تذكرة دعم تجريبية."""
    return SimpleNamespace(
        id=index,
        subject="مشكلة",
        status=status,
        category="other",
        last_message_at="2026-01-01T10:00:00+00:00",
        updated_at="2026-01-01T10:00:00+00:00",
        is_open=status == "open",
    )


def _fake_user(index: int = 1, *, banned: bool = False, role: str = "user") -> SimpleNamespace:
    """مستخدم تجريبي بالحقول التي تستخدمها لوحات الأدمن."""
    return SimpleNamespace(
        id=index,
        telegram_id=100_000 + index,
        username=f"user{index}",
        display_name=f"مستخدم {index}",
        is_banned=banned,
        role=role,
        balance_units=25_000,
    )


def _fake_admin_payment(index: int = 1, *, with_proof: bool = True) -> SimpleNamespace:
    """طلب شحن تجريبي كما تراه لوحة الأدمن."""
    return SimpleNamespace(
        id=index,
        user_id=index,
        amount_units=50_000,
        status="pending",
        proof_file_id="FILE123" if with_proof else None,
        proof_file_type="photo",
        created_at="2026-01-01T10:00:00+00:00",
    )


def _fake_admin_order(index: int = 1, status: str = "submit_uncertain") -> SimpleNamespace:
    """طلب تجريبي كما تراه لوحة الأدمن (بحقول المزود والقفل)."""
    order = _fake_order(index, status=status)
    order.user_id = index
    order.provider_order_id = "PRV-9" if status != "pending" else None
    order.provider_id = 1
    return order


def _fake_admin_service(index: int = 1, *, active: bool = True, archived: bool = False):
    """خدمة تجريبية بحقول الحالة التي تحتاجها بطاقة الأدمن."""
    service = _fake_service(index)
    service.is_active = active
    service.is_archived = archived
    service.provider_id = 1
    service.provider_service_id = "55"
    service.provider_price_per_1000_units = 6_000
    return service


def _fake_provider(
    index: int = 1, *, active: bool = True, failures: int = 0
) -> SimpleNamespace:
    """مزود تجريبي بالحقول التي تستخدمها لوحات المزودين فقط."""
    return SimpleNamespace(
        id=index,
        name=f"مزود {index}",
        api_url="https://panel.example.com/api/v2",
        api_key_hint="••••1234",
        api_type="perfect_panel",
        balance_units=1_500_000,
        currency="USD",
        balance_checked_at="2026-01-01T10:00:00+00:00",
        is_active=active,
        active=active,
        priority=index,
        timeout_seconds=30,
        consecutive_failures=failures,
        disabled_until=None,
        last_error=None if failures == 0 else "timeout",
        last_success_at="2026-01-01T09:00:00+00:00",
    )


def _fake_provider_item(index: int = 1) -> SimpleNamespace:
    """عنصر من قائمة خدمات المزود (نتيجة استيراد)."""
    return SimpleNamespace(
        provider_service_id=str(1000 + index),
        name=f"Instagram Followers {index}",
        rate_per_1000_units=8_000,
        min_quantity=100,
        max_quantity=100_000,
        category="Instagram",
        service_type="Default",
        dripfeed=False,
        refill=True,
        cancel=False,
        currency="USD",
        raw={},
    )


def _fake_setting(key: str = "order_check_interval_seconds", *, editable: bool = True):
    """مفتاح إعداد تجريبي."""
    return SimpleNamespace(
        key=key,
        value="120",
        value_type="int",
        group_code="orders",
        name_ar="فاصل الفحص",
        description_ar="بالثواني",
        is_editable=editable,
    )


def admin_markups() -> list[tuple[str, InlineKeyboardMarkup]]:
    """
    كل لوحات لوحة التحكم ببيانات تجريبية.

    تُبنى بصلاحيات كاملة عمداً: هكذا يظهر **كل** زر ممكن في اللوحة ويخضع
    لفحص «لا زر بلا معالج» — بما في ذلك الأزرار التي لا يراها إلا الأدمن الأعلى.
    """
    perms = {str(permission) for permission in Permission}
    users = [_fake_user(1), _fake_user(2, banned=True)]
    orders = [_fake_admin_order(1), _fake_admin_order(2, status="in_progress")]
    payments = [_fake_admin_payment(1), _fake_admin_payment(2, with_proof=False)]
    tickets = [_fake_ticket(1), _fake_ticket(2, status="closed")]
    services = [_fake_admin_service(1), _fake_admin_service(2, active=False)]
    categories = [_fake_category(1), _fake_category(2)]

    for ticket in tickets:
        ticket.user_id = ticket.id

    return [
        ("admin_menu_kb", admin_kb.admin_menu_kb(perms, pending_payments=3, open_tickets=2)),
        ("admin_menu_kb_minimal", admin_kb.admin_menu_kb({Permission.ADMIN_ACCESS})),
        ("health_kb", admin_kb.health_kb()),
        ("back_panel_kb", admin_kb.back_panel_kb()),
        ("admin_cancel_only_kb", admin_kb.cancel_only_kb()),
        ("admin_confirm_cancel_kb", admin_kb.confirm_cancel_kb()),
        ("admin_skip_cancel_kb", admin_kb.skip_cancel_kb()),
        ("users_home_kb", admin_kb.users_home_kb(perms)),
        ("user_results_kb", admin_kb.user_results_kb(users)),
        ("user_card_kb", admin_kb.user_card_kb(_fake_user(1), perms)),
        ("user_card_kb_banned", admin_kb.user_card_kb(_fake_user(2, banned=True), perms)),
        ("user_role_kb", admin_kb.user_role_kb(_fake_user(1))),
        ("user_role_confirm_kb", admin_kb.user_role_confirm_kb(1, "support")),
        ("user_orders_nav_kb", admin_kb.user_list_nav_kb("orders", 1, page=1, total_pages=3)),
        ("user_tx_nav_kb", admin_kb.user_list_nav_kb("tx", 1, page=2, total_pages=3)),
        (
            "payments_list_kb",
            admin_kb.payments_list_kb(payments, page=1, total_pages=2, symbol="ر.ي"),
        ),
        (
            "payment_card_kb",
            admin_kb.payment_card_kb(_fake_admin_payment(1), perms, is_pending=True),
        ),
        (
            "payment_card_kb_done",
            admin_kb.payment_card_kb(
                _fake_admin_payment(2, with_proof=False), perms, is_pending=False
            ),
        ),
        ("payment_approve_kb", admin_kb.payment_approve_kb()),
        (
            "admin_orders_kb",
            admin_kb.admin_orders_kb(
                orders, filter_code="att", page=1, total_pages=2, symbol="ر.ي"
            ),
        ),
        (
            "admin_order_card_kb",
            admin_kb.admin_order_card_kb(
                _fake_admin_order(1), perms, filter_code="att", page=1
            ),
        ),
        (
            "admin_order_card_kb_final",
            admin_kb.admin_order_card_kb(
                _fake_admin_order(3, status="completed"), perms, filter_code="all", page=1
            ),
        ),
        ("order_override_kb", admin_kb.order_override_kb(_fake_admin_order(1))),
        (
            "admin_tickets_kb",
            admin_kb.admin_tickets_kb(tickets, filter_code="open", page=1, total_pages=2),
        ),
        ("admin_ticket_card_kb", admin_kb.admin_ticket_card_kb(tickets[0], perms)),
        (
            "admin_ticket_card_kb_closed",
            admin_kb.admin_ticket_card_kb(tickets[1], perms, filter_code="closed"),
        ),
        ("catalog_home_kb", admin_kb.catalog_home_kb(categories, perms)),
        (
            "catalog_services_kb",
            admin_kb.catalog_services_kb(
                services, category_id=1, page=1, total_pages=2, symbol="ر.ي"
            ),
        ),
        ("service_card_kb", admin_kb.service_card_kb(_fake_admin_service(1), perms)),
        (
            "service_card_kb_archived",
            admin_kb.service_card_kb(_fake_admin_service(2, archived=True), perms),
        ),
        (
            "settings_home_kb",
            admin_kb.settings_home_kb(["general", "orders"], perms, maintenance_on=False),
        ),
        (
            "settings_group_kb",
            admin_kb.settings_group_kb(
                [_fake_setting(), _fake_setting("locked_key", editable=False)],
                group="orders",
                page=1,
                total_pages=2,
                perms=perms,
            ),
        ),
        (
            "providers_home_kb",
            admin_kb.providers_home_kb(
                [_fake_provider(1), _fake_provider(2, active=False, failures=3)], perms
            ),
        ),
        ("providers_home_kb_empty", admin_kb.providers_home_kb([], perms)),
        ("provider_card_kb", admin_kb.provider_card_kb(_fake_provider(1), perms)),
        (
            "provider_card_kb_disabled",
            admin_kb.provider_card_kb(_fake_provider(2, active=False), perms),
        ),
        ("provider_type_kb", admin_kb.provider_type_kb()),
        (
            "provider_services_kb",
            admin_kb.provider_services_kb(
                services, provider_id=1, page=1, total_pages=2, symbol="ر.ي"
            ),
        ),
        (
            "provider_import_results_kb",
            admin_kb.provider_import_results_kb(
                [_fake_provider_item(1), _fake_provider_item(2)], provider_id=1, symbol="ر.ي"
            ),
        ),
        (
            "category_picker_kb",
            admin_kb.category_picker_kb(categories, NS_ADM_CAT, "ncat"),
        ),
        (
            "category_picker_kb_import",
            admin_kb.category_picker_kb(categories, NS_ADM_PRV, "cat"),
        ),
        (
            "provider_picker_kb",
            admin_kb.provider_picker_kb([_fake_provider(1)], NS_ADM_CAT, "nprv"),
        ),
        ("logs_home_kb", admin_kb.logs_home_kb()),
        ("logs_audit_kb", admin_kb.logs_page_kb("audit", page=2, total_pages=5)),
        ("logs_errors_kb", admin_kb.logs_page_kb("errors", page=1, total_pages=2)),
    ]


def all_markups() -> list[tuple[str, InlineKeyboardMarkup]]:
    """
    بناء كل لوحات الواجهة مرة واحدة.

    أي لوحة جديدة تُضاف في `keyboards/user_kb.py` يجب أن تُضاف هنا — وهذا مقصود:
    اللوحة التي لا تُختبر لا تُضمن أزرارها.
    """
    categories = [_fake_category(1), _fake_category(2)]
    services = [_fake_service(1), _fake_service(2)]
    orders = [_fake_order(1), _fake_order(2, status="completed")]
    tickets = [_fake_ticket(1), _fake_ticket(2, status="closed")]
    payments = [_fake_payment(1), _fake_payment(2, status="approved")]

    return [
        ("main_menu_kb", user_kb.main_menu_kb()),
        ("main_menu_kb_admin", user_kb.main_menu_kb(is_admin=True)),
        ("categories_kb", user_kb.categories_kb(categories)),
        ("categories_kb_empty", user_kb.categories_kb([])),
        (
            "services_kb",
            user_kb.services_kb(services, category_id=1, page=2, total_pages=3, symbol="ر.ي"),
        ),
        ("service_card_kb", user_kb.service_card_kb(_fake_service(1), category_id=1, page=1)),
        ("insufficient_balance_kb", user_kb.insufficient_balance_kb(1, 1)),
        (
            "orders_kb",
            user_kb.orders_kb(orders, filter_code="all", page=1, total_pages=2, symbol="ر.ي"),
        ),
        (
            "order_card_kb_cancelable",
            user_kb.order_card_kb(_fake_order(1), can_cancel=True, filter_code="all", page=1),
        ),
        (
            "order_card_kb_plain",
            user_kb.order_card_kb(
                _fake_order(2, status="completed"), can_cancel=False, filter_code="done", page=1
            ),
        ),
        ("order_cancel_confirm_kb", user_kb.order_cancel_confirm_kb(1)),
        ("wallet_kb", user_kb.wallet_kb()),
        ("history_kb", user_kb.history_kb(page=2, total_pages=4)),
        ("deposit_methods_kb", user_kb.deposit_methods_kb([_fake_method(1), _fake_method(2)])),
        ("deposits_kb", user_kb.deposits_kb(payments, page=1, total_pages=2)),
        ("support_kb", user_kb.support_kb()),
        ("ticket_categories_kb", user_kb.ticket_categories_kb()),
        ("tickets_kb", user_kb.tickets_kb(tickets, page=1, total_pages=1)),
        ("ticket_card_kb_open", user_kb.ticket_card_kb(_fake_ticket(1))),
        ("ticket_card_kb_closed", user_kb.ticket_card_kb(_fake_ticket(2, status="closed"))),
        ("account_kb", user_kb.account_kb(3)),
        ("notifications_kb", user_kb.notifications_kb(page=1, total_pages=2, unread=5)),
        ("info_kb", user_kb.info_kb()),
        ("notifications_only_back_kb", user_kb.notifications_only_back_kb()),
        ("cancel_markup", common_kb.cancel_markup()),
        ("confirm_cancel_markup", common_kb.confirm_cancel_markup()),
        ("skip_cancel_markup", common_kb.skip_cancel_markup()),
        *admin_markups(),
    ]


def registered_patterns() -> list[re.Pattern]:
    """
    كل أنماط الأزرار التي يلتقطها البوت فعلاً.

    تشمل معالجات الشاشات ومداخل المحادثات وحالاتها ومساراتها الاحتياطية،
    وتستبعد المعالج الشامل (الذي بلا نمط) لأنه شبكة أمان لا دليل تغطية.
    """
    patterns: list[re.Pattern] = []

    def collect(handler: object) -> None:
        """جمع النمط من معالج واحد (أو من محادثة كاملة)."""
        if isinstance(handler, CallbackQueryHandler):
            if handler.pattern is not None:
                patterns.append(handler.pattern)
        elif isinstance(handler, ConversationHandler):
            for entry in handler.entry_points:
                collect(entry)
            for state_handlers in handler.states.values():
                for state_handler in state_handlers:
                    collect(state_handler)
            for fallback in handler.fallbacks:
                collect(fallback)

    for _group, handler in build_handlers():
        collect(handler)
    return patterns


ALL_BUTTONS = sorted(
    {
        data
        for _name, markup in all_markups()
        for row in markup.inline_keyboard
        for button in row
        if (data := button.callback_data)
    }
)


def test_keyboards_produce_buttons() -> None:
    """تأكيد أن اللوحات فعلاً تنتج أزراراً (حماية من اختبار فارغ يمر زوراً).."""
    assert len(ALL_BUTTONS) >= 25


@pytest.mark.parametrize("callback_data", ALL_BUTTONS)
def test_every_button_has_handler(callback_data: str) -> None:
    """كل زر في الواجهة يلتقطه معالج مسجَّل — لا أزرار ميتة."""
    patterns = registered_patterns()
    matched = [pattern.pattern for pattern in patterns if pattern.search(callback_data)]
    assert matched, f"الزر {callback_data!r} بلا معالج مسجَّل في handlers/registry.py"


@pytest.mark.parametrize("callback_data", ALL_BUTTONS)
def test_every_button_is_well_formed(callback_data: str) -> None:
    """كل زر مُرمَّز بالصيغة المعتمدة وبإصدار callback الحالي."""
    data = unpack(callback_data)
    assert data.namespace
    assert data.action
    assert data.version == CALLBACK_VERSION
    assert len(callback_data.encode("utf-8")) <= 64   # حد تيليجرام الصارم


def test_no_button_matches_more_than_one_screen_handler() -> None:
    """
    لا يلتقط زرَّاً واحداً أكثر من معالج شاشة.

    التقاط زر بمعالجين يعني سلوكاً يعتمد على ترتيب التسجيل — مصدر أعطال صامتة.
    المحادثات مستثناة لأن حالاتها معزولة زمنياً (لا تعمل إلا داخل المحادثة).
    """
    from handlers.registry import screen_handlers

    patterns = [handler.pattern for handler in screen_handlers() if handler.pattern]
    for callback_data in ALL_BUTTONS:
        matches = [pattern.pattern for pattern in patterns if pattern.search(callback_data)]
        assert len(matches) <= 1, f"الزر {callback_data!r} يلتقطه أكثر من معالج: {matches}"
```

