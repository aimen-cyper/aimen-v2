"""
عيّنات شاشات لوحة التحكم الحقيقية (للاختبار ولتوليد `docs/ADMIN_UI_PREVIEW.md`).

كل شاشة تُشغَّل عبر معالجها الفعلي على `FakeBot` وبيانات عيّنة (مزود Mock وخدمة وطلب ودفعة ومستخدم)، ثم تُلتقط
الرسالة المعروضة (نصاً ولوحة أزرار). لا شبكة ولا مزود حقيقي.
"""

from __future__ import annotations

from typing import Any

from handlers.admin import (
    backup,
    broadcast,
    catalog,
    channels,
    dashboard,
    logs,
    orders,
    payment_methods,
    payments,
    providers,
    security,
    settings,
    stats,
    system,
    templates,
    tickets,
    users,
)
from keyboards.callback_data import pack
from tests.integration.test_user_interface import press
from tests.telegram_fakes import SentMessage


async def capture_admin_screens(bot, context, *, admin, order, provider, service, target_user) -> dict[str, SentMessage]:
    """تشغيل شاشات الأدمن الرئيسية وإرجاع آخر رسالة لكل منها (الاسم ⇒ الرسالة)."""
    plan: list[tuple[str, Any, str]] = [
        ("لوحة التحكم", dashboard.panel_screen, pack("adm", "home")),
        ("صحة النظام", dashboard.health_screen, pack("adm", "health")),
        ("المهام الخلفية", system.jobs_screen, pack("adm", "jobs")),
        ("المزودون", providers.providers_home_screen, pack("pv", "home")),
        ("خريطة المزودين", getattr(providers, "providers_map_screen", None), pack("pv", "map")),
        ("بطاقة مزود", providers.provider_card_screen, pack("pv", "view", provider.id)),
        ("خدمات المزود", providers.provider_services_screen, pack("pv", "svcs", provider.id, 1)),
        ("الطلبات", orders.orders_list_screen, pack("ao", "list", "all", 1)),
        ("بطاقة طلب", orders.order_card_screen, pack("ao", "view", order.id, "all", 1)),
        ("المستخدمون", users.users_home_screen, pack("au", "home")),
        ("بطاقة مستخدم", users.user_card_screen, pack("au", "view", target_user.id)),
        ("الكتالوج", catalog.catalog_home_screen, pack("ac", "home")),
        ("بطاقة خدمة", catalog.service_card_screen, pack("ac", "svc", service.id)),
        ("المدفوعات", payments.payments_list_screen, pack("ap", "list", "all", 1)),
        ("طرق الشحن", payment_methods.methods_home_screen, pack("pm", "home")),
        ("الإعدادات", settings.settings_home_screen, pack("as", "home")),
        ("إعدادات الطلبات", settings.settings_group_screen, pack("as", "group", "orders", 1)),
        ("السجلات", logs.logs_home_screen, pack("al", "home")),
        ("القنوات", channels.home_screen, pack("ch", "home")),
        ("الأمان", security.home_screen, pack("sc", "home")),
        ("النسخ الاحتياطي", backup.home_screen, pack("bk", "home")),
        ("الإحصائيات", stats.home_screen, pack("st", "home", "today")),
        ("القوالب", templates.templates_home_screen, pack("tp", "home")),
        ("الرسائل الجماعية", broadcast.broadcast_home_screen, pack("bc", "home")),
        ("التذاكر", tickets.tickets_list_screen, pack("at", "list", "all", 1)),
    ]
    captured: dict[str, SentMessage] = {}
    for name, handler, data in plan:
        if handler is None:                      # شاشة غير موجودة في الإصدار المختبَر (الأصل 1.3.0)
            continue
        bot.clear()
        await press(bot, context, handler, data, admin.telegram_id)
        if bot.sent:
            captured[name] = bot.last
    return captured
