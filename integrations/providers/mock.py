"""
مزود وهمي للاختبار والتطوير — ⚠️ لا يتصل بأي شبكة ولا ينفق أي مال حقيقي.

الغرض منه واحد فقط: تشغيل الدورة الكاملة (إرسال → متابعة → إكمال/فشل) في الاختبارات
وفي بيئة التطوير دون الحاجة إلى حساب حقيقي لدى مزود.

مصرَّح به في `registry` باسم النوع `mock` فقط، ولا يُستخدم في الإنتاج:
أي مزود حقيقي يجب أن يكون `api_type = 'perfect_panel'` (يُنفَّذ في المرحلة 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.exceptions import (
    ProviderInsufficientFundsError,
    ProviderPermanentError,
    ProviderTemporaryError,
    ProviderUncertainError,
)
from core.money import MONEY_SCALE
from integrations.providers.base import (
    ProviderBalance,
    ProviderClient,
    ProviderOrderResult,
    ProviderServiceItem,
    ProviderStatusResult,
)


@dataclass
class MockOrderState:
    """حالة طلب وهمي داخل المزود الاختباري."""

    provider_order_id: str
    quantity: int
    delivered: int = 0
    status: str = "Pending"
    charge_units: int = 0
    raw_extras: dict[str, Any] = field(default_factory=dict)


class MockProviderClient(ProviderClient):
    """
    مزود اختباري قابل للبرمجة بالكامل.

    أمثلة الاستخدام في الاختبارات:
        client = MockProviderClient()                       # يعمل بشكل طبيعي
        client.fail_next_add = ProviderPermanentError(...)  # يرفض الطلب القادم
        client.advance("1001", to="Completed")              # يقفز بالطلب إلى الاكتمال
    """

    api_type = "mock"

    def __init__(
        self,
        *,
        api_url: str = "https://mock.invalid/api/v2",
        api_key: str = "mock-key",
        timeout_seconds: int = 5,
        balance_units: int = 1_000 * MONEY_SCALE,
        rate_per_1000_units: int = 6_000,
        currency: str = "YER",
    ) -> None:
        """تهيئة المزود الوهمي برصيد وسعر افتراضيين."""
        super().__init__(api_url=api_url, api_key=api_key, timeout_seconds=timeout_seconds)
        self.balance_units = balance_units
        self.rate_per_1000_units = rate_per_1000_units
        #: عملة حساب المزود الوهمي — افتراضياً عملة النظام الافتراضية فلا يلزم سعر صرف في الدورة التجريبية
        self.currency = currency
        self.orders: dict[str, MockOrderState] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []   # سجل الاستدعاءات للتحقق في الاختبارات
        self._next_id = 1000

        #: استثناء يُرفع عند أول استدعاء لـadd_order ثم يُصفَّر (لمحاكاة فشل مؤقت)
        self.fail_next_add: Exception | None = None
        #: استثناء دائم يُرفع في كل استدعاء لـadd_order
        self.always_fail_add: Exception | None = None
        #: استثناء يُرفع عند أول استعلام حالة ثم يُصفَّر
        self.fail_next_status: Exception | None = None
        #: استثناء يُرفع عند أول فحص رصيد ثم يُصفَّر (لاختبار تعطيل المزود)
        self.fail_next_balance: Exception | None = None
        #: عدد الوحدات التي يسلّمها المزود في كل فحص حالة (محاكاة التقدم)
        self.delivery_step_ratio: float = 0.5
        #: هل ينهي الطلب تلقائياً عند اكتمال التسليم؟
        self.auto_complete: bool = True

    # ------------------------------ الطلبات ------------------------------ #

    async def add_order(
        self, *, provider_service_id: str, link: str, quantity: int, extras: dict[str, Any] | None = None
    ) -> ProviderOrderResult:
        """إنشاء طلب وهمي، أو رفع الاستثناء المبرمَج مسبقاً لمحاكاة الفشل."""
        self.calls.append(("add", {"service": provider_service_id, "link": link, "quantity": quantity}))

        if self.always_fail_add is not None:
            raise self.always_fail_add
        if self.fail_next_add is not None:
            error, self.fail_next_add = self.fail_next_add, None
            raise error

        charge_units = (self.rate_per_1000_units * quantity + 500) // 1000
        if charge_units > self.balance_units:
            raise ProviderInsufficientFundsError(
                "رصيد الحساب لدى المزود الوهمي غير كافٍ لتنفيذ الطلب."
            )

        self._next_id += 1
        provider_order_id = str(self._next_id)
        self.balance_units -= charge_units
        self.orders[provider_order_id] = MockOrderState(
            provider_order_id=provider_order_id,
            quantity=quantity,
            charge_units=charge_units,
            raw_extras=dict(extras or {}),
        )
        return ProviderOrderResult(
            provider_order_id=provider_order_id,
            charge_units=charge_units,
            raw={"order": provider_order_id},
        )

    async def get_order_status(self, provider_order_id: str) -> ProviderStatusResult:
        """إرجاع حالة الطلب الوهمي مع تقديم التنفيذ خطوة في كل استعلام."""
        self.calls.append(("status", {"order": provider_order_id}))

        if self.fail_next_status is not None:
            error, self.fail_next_status = self.fail_next_status, None
            raise error

        state = self.orders.get(provider_order_id)
        if state is None:
            raise ProviderPermanentError(f"الطلب {provider_order_id} غير موجود لدى المزود.")

        if state.status in {"Pending", "In progress"} and self.auto_complete:
            step = max(1, int(state.quantity * self.delivery_step_ratio))
            state.delivered = min(state.quantity, state.delivered + step)
            state.status = "Completed" if state.delivered >= state.quantity else "In progress"

        return ProviderStatusResult(
            raw_status=state.status,
            start_count=0,
            remains=max(0, state.quantity - state.delivered),
            delivered=state.delivered,
            charge_units=state.charge_units,
            raw={"status": state.status, "remains": state.quantity - state.delivered},
        )

    async def cancel_order(self, provider_order_id: str) -> bool:
        """إلغاء طلب وهمي (مدعوم في المزود الاختباري)."""
        self.calls.append(("cancel", {"order": provider_order_id}))
        state = self.orders.get(provider_order_id)
        if state is None or state.status in {"Completed", "Canceled"}:
            return False
        state.status = "Canceled"
        self.balance_units += state.charge_units
        return True

    # ------------------------------ الحساب ------------------------------- #

    async def get_balance(self) -> ProviderBalance:
        """رصيد الحساب الوهمي، أو الاستثناء المبرمَج لمحاكاة فشل الاتصال."""
        self.calls.append(("balance", {}))
        if self.fail_next_balance is not None:
            error, self.fail_next_balance = self.fail_next_balance, None
            raise error
        return ProviderBalance(amount_units=self.balance_units, currency=self.currency, raw={"balance": "mock"})

    async def get_services(self) -> list[ProviderServiceItem]:
        """قائمة خدمات وهمية ثابتة للاستيراد التجريبي."""
        self.calls.append(("services", {}))
        return [
            ProviderServiceItem(
                provider_service_id="555",
                name="Mock Instagram Followers",
                rate_per_1000_units=self.rate_per_1000_units,
                min_quantity=100,
                max_quantity=100_000,
                category="Instagram",
            ),
            ProviderServiceItem(
                provider_service_id="556",
                name="Mock Instagram Likes",
                rate_per_1000_units=self.rate_per_1000_units // 2,
                min_quantity=50,
                max_quantity=50_000,
                category="Instagram",
            ),
        ]

    # ------------------------ أدوات التحكم للاختبار ----------------------- #

    def advance(self, provider_order_id: str, *, to: str, delivered: int | None = None) -> None:
        """تحريك طلب وهمي إلى حالة محددة (لمحاكاة partial/canceled في الاختبارات)."""
        state = self.orders[provider_order_id]
        state.status = to
        if delivered is not None:
            state.delivered = delivered

    def schedule_temporary_failure(self, message: str = "انقطاع مؤقت في الشبكة") -> None:
        """برمجة فشل مؤقت في الاستدعاء القادم لإنشاء الطلب."""
        self.fail_next_add = ProviderTemporaryError(message)

    def schedule_uncertain_failure(self, message: str = "انتهت المهلة بعد الإرسال") -> None:
        """برمجة نتيجة غير مؤكدة في الاستدعاء القادم (أخطر حالة)."""
        self.fail_next_add = ProviderUncertainError(message)

    def schedule_permanent_failure(self, message: str = "المزود رفض الطلب") -> None:
        """برمجة رفض نهائي في الاستدعاء القادم."""
        self.fail_next_add = ProviderPermanentError(message)
