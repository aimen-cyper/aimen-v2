"""
الواجهة المجردة لمزودي الخدمات (Provider Client).

الفكرة: بقية النظام لا يعرف شيئاً عن شكل API أي مزود — يتعامل فقط مع هذه الواجهة
وأنواع البيانات المعرَّفة هنا. إضافة مزود بمعيار مختلف = ملف جديد يطبّق `ProviderClient`
دون لمس أي سطر في الخدمات أو الواجهة.

تصنيف الأخطاء (مهم جداً لسلامة المال):
    • ProviderTemporaryError        → آمن لإعادة المحاولة (شبكة/حد معدل).
    • ProviderInsufficientFundsError → مؤقت كذلك، لكن سببه رصيدنا لدى المزود.
    • ProviderPermanentError        → لا فائدة من إعادة المحاولة (رفض صريح) ⇒ فشل + استرجاع.
    • ProviderUncertainError        → لا نعرف هل وصل الطلب ⇒ ممنوع إعادة الإرسال آلياً.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.money import MONEY_SCALE


#: أنواع الخدمات التي يدعمها النظام فعلاً: الطلب العادي (رابط + كمية) فقط. الأنواع الأخرى
#: (Package/Custom Comments/Subscriptions/…) تحتاج حقولاً إضافية (تعليقات، اسم مستخدم، مدة…) لا يجمعها مسار الطلب.
SUPPORTED_SERVICE_TYPES: frozenset[str] = frozenset({"default"})


def normalize_service_type(raw: Any) -> str:
    """توحيد نوع الخدمة القادم من المزود: أحرف صغيرة وشرطة سفلية بدل المسافات («Custom Comments» ⇒ custom_comments)."""
    text = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    return text or "default"


@dataclass(frozen=True, slots=True)
class ProviderOrderResult:
    """نتيجة إنشاء طلب عند المزود."""

    provider_order_id: str          # رقم الطلب عند المزود (لا يكون فارغاً أبداً)
    charge_units: int | None = None  # ما خصمه المزود منا (بوحدات المال) إن أرسله
    currency: str = "USD"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderStatusResult:
    """نتيجة الاستعلام عن حالة طلب لدى المزود."""

    raw_status: str                  # نص الحالة كما ورد من المزود
    start_count: int | None = None   # العدد قبل البدء
    remains: int | None = None       # المتبقي
    delivered: int | None = None     # المنفَّذ فعلياً (إن أرسله المزود)
    charge_units: int | None = None
    currency: str = "USD"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderBalance:
    """رصيد حسابنا لدى المزود."""

    amount_units: int
    currency: str = "USD"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderServiceItem:
    """خدمة واحدة كما يعرضها المزود (تُستخدم في الاستيراد والمزامنة)."""

    provider_service_id: str
    name: str
    rate_per_1000_units: int          # سعر المزود بوحدات المال
    min_quantity: int
    max_quantity: int
    category: str = ""
    service_type: str = "default"
    dripfeed: bool = False
    refill: bool = False
    cancel: bool = False
    currency: str = "USD"
    raw: dict[str, Any] = field(default_factory=dict)


class ProviderClient(ABC):
    """
    الواجهة التي يجب أن يطبّقها كل عميل مزود.

    ملاحظات للمطوّر:
        • كل الدوال غير متزامنة ولا تفتح أي معاملة قاعدة بيانات.
        • ممنوع أن يُرجع أي عميل مفتاح API أو يضعه في نص خطأ — استخدم `secrets()`
          لتمرير القيم الحساسة إلى أداة التنقية قبل أي تسجيل.
    """

    #: المعرّف النصي لنوع المزود (يطابق عمود providers.api_type)
    api_type: str = "base"

    def __init__(self, *, api_url: str, api_key: str, timeout_seconds: int = 30) -> None:
        """تهيئة العميل ببيانات الاتصال (المفتاح يبقى داخل الكائن ولا يُسجَّل)."""
        self.api_url = api_url
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds

    def secrets(self) -> tuple[str, ...]:
        """القيم السرية التي يجب حذفها من أي نص قبل تسجيله (تُمرَّر إلى sanitize)."""
        return (self._api_key,) if self._api_key else ()

    @abstractmethod
    async def add_order(
        self, *, provider_service_id: str, link: str, quantity: int, extras: dict[str, Any] | None = None
    ) -> ProviderOrderResult:
        """إنشاء طلب جديد عند المزود وإرجاع رقمه."""

    @abstractmethod
    async def get_order_status(self, provider_order_id: str) -> ProviderStatusResult:
        """الاستعلام عن حالة طلب واحد."""

    @abstractmethod
    async def get_balance(self) -> ProviderBalance:
        """قراءة رصيد حسابنا لدى المزود."""

    @abstractmethod
    async def get_services(self) -> list[ProviderServiceItem]:
        """جلب قائمة خدمات المزود (للاستيراد والمزامنة)."""

    async def get_multi_status(self, provider_order_ids: list[str]) -> dict[str, ProviderStatusResult]:
        """
        الاستعلام عن عدة طلبات دفعة واحدة.

        التطبيق الافتراضي يستدعي `get_order_status` لكل طلب؛ المزود الذي يدعم
        الاستعلام الجماعي يعيد تعريف هذه الدالة لتوفير الاستدعاءات.
        """
        results: dict[str, ProviderStatusResult] = {}
        for provider_order_id in provider_order_ids:
            results[provider_order_id] = await self.get_order_status(provider_order_id)
        return results

    async def cancel_order(self, provider_order_id: str) -> bool:
        """
        طلب إلغاء لدى المزود.

        المخرجات: False افتراضياً لأن أغلب اللوحات لا تدعم الإلغاء —
                  المزود الذي يدعمه يعيد تعريف الدالة.
        """
        return False

    async def refill_order(self, provider_order_id: str) -> bool:
        """طلب إعادة تعبئة (refill) — غير مدعوم افتراضياً."""
        return False

    async def close(self) -> None:
        """إغلاق أي موارد شبكة مفتوحة (اتصالات/جلسات). افتراضياً لا شيء."""
        return None

    def money_from_decimal_text(self, text: str | float | int | None) -> int | None:
        """
        تحويل مبلغ نصي من المزود (مثل "1.2345") إلى وحدات صحيحة.

        المخرجات: عدد الوحدات، أو None إذا كانت القيمة غير قابلة للتحويل
                  (لا نُسقط العملية بسبب حقل تكلفة غير مفهوم).
        """
        if text is None or text == "":
            return None
        try:
            from decimal import Decimal

            return int((Decimal(str(text)) * MONEY_SCALE).to_integral_value())
        except (ArithmeticError, ValueError, TypeError):
            return None
