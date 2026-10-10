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
from keyboards.callback_data import NS_ADMIN, pattern

#: وحدات الأقسام بالترتيب الذي تُسجَّل به معالجاتها
SECTIONS = (
    users,
    payments,
    payment_methods,
    orders,
    tickets,
    catalog,
    providers,
    settings,
    logs,
    broadcast,
    templates,
    security,
    channels,
    backup,
    stats,
    system,
)

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
