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

#: أنواع للتطوير والاختبار فقط: معطَّلة افتراضياً فلا تظهر في الواجهة ولا يُنشأ لها عميل في الإنتاج
#: (مزود وهمي «ينجح» دائماً؛ وجوده بجانب مزودين حقيقيين خطر مالي). تُفعَّل صراحةً من الاختبارات/`demo_cycle`
DEV_ONLY_TYPES: frozenset[str] = frozenset({MockProviderClient.api_type})
_dev_types_enabled = False

#: أنواع مخطط لها لكنها لم تُنفَّذ بعد — نرفضها برسالة صريحة بدل تنفيذ صوري فارغ
_PLANNED: dict[str, str] = {}


def register_client(api_type: str, factory: ClientFactory) -> None:
    """تسجيل عميل مزود جديد تحت نوع محدد (يُستدعى عند إضافة معيار API جديد)."""
    _REGISTRY[api_type] = factory


def enable_dev_types(enabled: bool = True) -> None:
    """تفعيل/تعطيل أنواع التطوير (Mock). لا تُستدعَ في مسار الإنتاج؛ للاختبارات والعرض التجريبي فقط."""
    global _dev_types_enabled
    _dev_types_enabled = bool(enabled)


def dev_types_enabled() -> bool:
    """هل أنواع التطوير مفعّلة الآن؟"""
    return _dev_types_enabled


def available_types() -> tuple[str, ...]:
    """أنواع المزودين الجاهزة للاستخدام الآن (بلا أنواع التطوير ما لم تُفعَّل)."""
    return tuple(sorted(name for name in _REGISTRY if _dev_types_enabled or name not in DEV_ONLY_TYPES))


def is_supported(api_type: str) -> bool:
    """هل هذا النوع مدعوم فعلياً الآن (مسجَّل، وليس من أنواع التطوير المعطّلة)؟"""
    return api_type in available_types()


def create_client(
    *, api_type: str, api_url: str, api_key: str, timeout_seconds: int = 30
) -> ProviderClient:
    """
    إنشاء عميل مزود من نوعه المخزَّن في قاعدة البيانات.

    الاستثناءات:
        ProviderError : نوع غير معروف، أو نوع مخطط له ولم يُنفَّذ بعد.
    """
    factory = _REGISTRY.get(api_type) if is_supported(api_type) else None
    if factory is None:
        planned = _PLANNED.get(api_type)
        if planned:
            raise ProviderError(planned, user_message="⚠️ هذا المزود غير مفعّل بعد.")
        raise ProviderError(
            f"نوع مزود غير معروف: {api_type}. الأنواع المتاحة: {', '.join(available_types())}",
            user_message="⚠️ إعداد المزود غير صحيح. راجع لوحة التحكم.",
        )
    return factory(api_url=api_url, api_key=api_key, timeout_seconds=timeout_seconds)
