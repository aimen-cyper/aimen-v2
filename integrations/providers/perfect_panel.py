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
from decimal import Decimal, InvalidOperation
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
    normalize_service_type,
)
from utils.net_security import ensure_public_host

logger = logging.getLogger(__name__)

#: أقصى عدد محارف نحتفظ به من نص الاستجابة عند بناء رسالة خطأ (منعاً لتضخم اللوق)
ERROR_SNIPPET_LIMIT = 200

#: أقصى حجم لجسم استجابة المزود (بالبايت). قائمة خدمات كبيرة بضعة ميغابايت؛ ما فوق ذلك استجابة شاذة
#: أو خبيثة تستهلك الذاكرة، فنقطعها أثناء القراءة (التدفق) لا بعد تحميلها كاملة
MAX_RESPONSE_BYTES = 10 * 1024 * 1024

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


class _ResponseTooLarge(Exception):
    """داخلي: جسم استجابة المزود تجاوز الحد المسموح (يُحوَّل إلى خطأ مزود مصنَّف في `_post`)."""


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
                # ممنوع تتبّع التحويلات: الطلب يحمل مفتاح المزود، وتحويل 307/308
                # يعيد إرسال الجسم نفسه إلى مضيف آخر فيُسرَّب المفتاح.
                follow_redirects=False,
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
        if self._owns_client:
            # حماية SSRF: لا نرسل المفتاح إلى نطاق يشير لعنوان داخلي (لا يُفحص عند حقن عميل اختبار)
            await ensure_public_host(self.api_url)
        try:
            response = await self._read_limited(data)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            # التفريق هنا هو الفرق بين إعادة محاولة آمنة وبين طلب مكرر يكلّف مالاً
            if uncertain_on_timeout:
                raise ProviderUncertainError(
                    f"انقطع الاتصال أثناء إرسال الطلب ({type(exc).__name__})"
                ) from exc
            raise ProviderTemporaryError(
                f"تعذر الاتصال بالمزود أثناء {action} ({type(exc).__name__})"
            ) from exc
        except _ResponseTooLarge as exc:
            if uncertain_on_timeout:                       # الطلب قد يكون سُجّل لدى المزود: لا نعيد الإرسال
                raise ProviderUncertainError(f"استجابة المزود أكبر من الحد المسموح بعد الإرسال ({exc})") from exc
            raise ProviderTemporaryError(f"استجابة المزود أكبر من الحد المسموح أثناء {action} ({exc})") from exc
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

    async def _read_limited(self, data: dict[str, Any]) -> httpx.Response:
        """
        POST مع قراءة الجسم بالتدفق وقطعها عند `MAX_RESPONSE_BYTES`.

        المخرجات: استجابة كاملة الجسم (مفكوكة الضغط) صالحة لـ`.json()`/`.text`.
        الاستثناءات: `_ResponseTooLarge` (داخلي) يحوّله `_post` إلى مؤقت/غير مؤكد حسب السياق.
        """
        async with self._http().stream("POST", self.api_url, data=data) as streamed:
            declared = streamed.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > MAX_RESPONSE_BYTES:
                raise _ResponseTooLarge(f"حجم الاستجابة المعلن {declared} بايت")
            body = bytearray()
            async for chunk in streamed.aiter_bytes():
                body += chunk
                if len(body) > MAX_RESPONSE_BYTES:
                    raise _ResponseTooLarge(f"تجاوزت الاستجابة {MAX_RESPONSE_BYTES} بايت")
            return httpx.Response(streamed.status_code, content=bytes(body), request=streamed.request)

    def _raise_for_status(
        self, response: httpx.Response, action: str, *, uncertain_on_timeout: bool
    ) -> None:
        """تحويل رمز حالة HTTP إلى الاستثناء الصحيح (مؤقت/نهائي/غير مؤكد)."""
        status = response.status_code
        if 300 <= status < 400:
            # لا نتبع التحويلات (انظر _http) — نعدّه خطأ إعداد دائماً لا مؤقتاً
            raise ProviderPermanentError(
                f"المزود يعيد توجيه الطلب (HTTP {status}) — صحّح رابط API ليشير للعنوان النهائي مباشرة"
            )
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
            number = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            return None
        # لا NaN/Infinity، ولا أسس هائلة، ولا كسور (1.5 ليست «1»): القيمة المبهمة تُعامَل كغير معروفة
        if not number.is_finite() or number.adjusted() > 18 or number != number.to_integral_value():
            return None
        return int(number)

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
            service_type=normalize_service_type(entry.get("type")),
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
