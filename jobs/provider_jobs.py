"""
مهام مراقبة المزودين الدورية (المرحلة 6).

لماذا؟
    المزود هو الطرف الوحيد في النظام الذي لا نتحكم به: رصيده ينفد، وواجهته
    تتعطل، ومفتاحه قد يُلغى من طرفه. بلا مراقبة دورية نكتشف ذلك من شكوى عميل.

مهمتان:
    refresh_provider_balances : تقرأ رصيدنا لدى كل مزود مفعّل وتحفظه مع لقطة
                                تاريخية، وتُطلق تنبيه «الرصيد منخفض» عند الحاجة.
    watch_provider_health     : تتابع المزودين المتعثرين — تختبرهم بلطف، وتعيد
                                تفعيل الإرسال فور تعافيهم مع إشعار الأدمن.

كلتاهما لا تُسقط بقية المزودين عند فشل واحد: الخطأ يُسجَّل ويستمر الدوران.
"""

from __future__ import annotations

from telegram.ext import ContextTypes

from core.exceptions import ProviderError
from core.permissions import Permission
from database.models import Provider
from texts import templates
from utils.datetime_utils import is_past
from utils.logging_setup import get_logger

logger = get_logger(__name__)


async def refresh_provider_balances(context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    تحديث رصيدنا لدى كل مزود مفعّل (ولقطة تاريخية + تنبيه انخفاض).

    التنبيه نفسه داخل `ProviderService.check_balance` فلا يُكرَّر منطقه هنا.

    المخرجات: عدد المزودين الذين تم تحديث رصيدهم بنجاح.
    """
    services = context.application.bot_data["services"]
    providers: list[Provider] = await services.providers.list_all(active_only=True)
    updated = 0

    for provider in providers:
        health = await services.providers.health(provider)
        if not health.is_usable:
            logger.info("تخطّي فحص رصيد %s: %s", provider.name, health.reason)
            continue
        try:
            balance = await services.providers.check_balance(provider)
        except ProviderError as exc:
            # فشل مزود واحد لا يمنع فحص البقية — والفشل مسجَّل في provider_requests
            logger.warning("تعذّر قراءة رصيد المزود %s: %s", provider.name, exc)
            continue
        updated += 1
        logger.info(
            "رصيد المزود %s: %s %s", provider.name, balance.amount_units, balance.currency
        )

    return updated


async def watch_provider_health(context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    متابعة المزودين المتعثرين وإعادة تفعيلهم عند التعافي.

    المزود يُوقَف مؤقتاً تلقائياً بعد عدد أخطاء متتالية (`_record_failure`).
    هذه المهمة تنتظر انتهاء مدة الإيقاف ثم تختبره باستدعاء خفيف (قراءة الرصيد):
        • نجح  ⇒ `record_success` يصفّر العدّاد ويمسح الإيقاف + إشعار «تعافى».
        • فشل  ⇒ يُسجَّل الفشل كالمعتاد ويبقى موقوفاً للدورة القادمة.

    المخرجات: عدد المزودين الذين تعافوا في هذه الجولة.
    """
    services = context.application.bot_data["services"]
    providers: list[Provider] = await services.providers.list_all(active_only=True)
    recovered = 0

    for provider in providers:
        failures = int(provider.consecutive_failures or 0)
        if failures == 0:
            continue
        if provider.disabled_until and not is_past(provider.disabled_until):
            logger.info("المزود %s ما زال في مدة الإيقاف المؤقت", provider.name)
            continue

        try:
            await services.providers.check_balance(provider)
        except ProviderError as exc:
            logger.warning("المزود %s ما زال متعثراً: %s", provider.name, exc)
            continue

        recovered += 1
        title, message = templates.admin_provider_recovered(
            provider_name=provider.name, failures=failures
        )
        async with services.db.transaction() as tx:
            await services.notifications.notify_admins(
                tx,
                permission=Permission.PROVIDERS_VIEW,
                token=f"provider:{provider.id}:recovered:{failures}",
                title=title,
                message=message,
            )
        logger.info("تعافى المزود %s بعد %s أخطاء متتالية", provider.name, failures)

    return recovered
