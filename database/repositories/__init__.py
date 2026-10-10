"""
حزمة المستودعات + حاوية موحدة للوصول إليها.

الاستخدام في الطبقات الأعلى:
    repos = Repositories(db)
    user = await repos.users.get_by_telegram_id(123)
"""

from __future__ import annotations

from database.database import Database
from database.repositories.audit import AuditRepository
from database.repositories.base import BaseRepository
from database.repositories.broadcasts import BroadcastsRepository
from database.repositories.categories import CategoriesRepository
from database.repositories.channel_outbox import ChannelOutboxRepository
from database.repositories.order_message_refs import OrderMessageRefsRepository
from database.repositories.favorites import FavoritesRepository
from database.repositories.idempotency import IdempotencyRepository
from database.repositories.misc import (
    BackupsRepository,
    ErrorLogsRepository,
    ProviderRequestsRepository,
)
from database.repositories.notifications import NotificationsRepository
from database.repositories.orders import OrdersRepository
from database.repositories.payments import PaymentMethodsRepository, PaymentsRepository
from database.repositories.providers import ProvidersRepository
from database.repositories.rbac import RbacRepository
from database.repositories.services import ServicesRepository
from database.repositories.settings import SettingsRepository
from database.repositories.templates import NotificationTemplatesRepository
from database.repositories.tickets import TicketsRepository
from database.repositories.transactions import TransactionsRepository
from database.repositories.users import UsersRepository

__all__ = [
    "Repositories",
    "BaseRepository",
    "UsersRepository",
    "RbacRepository",
    "SettingsRepository",
    "ProvidersRepository",
    "CategoriesRepository",
    "ServicesRepository",
    "OrdersRepository",
    "TransactionsRepository",
    "PaymentsRepository",
    "PaymentMethodsRepository",
    "TicketsRepository",
    "NotificationsRepository",
    "NotificationTemplatesRepository",
    "AuditRepository",
    "BroadcastsRepository",
    "IdempotencyRepository",
    "ProviderRequestsRepository",
    "ErrorLogsRepository",
    "BackupsRepository",
    "ChannelOutboxRepository",
    "OrderMessageRefsRepository",
    "FavoritesRepository",
]


class Repositories:
    """حاوية تجمع كل المستودعات على نفس اتصال قاعدة البيانات."""

    def __init__(self, db: Database) -> None:
        """إنشاء نسخة واحدة من كل مستودع ومشاركتها مع بقية النظام."""
        self.db = db
        self.users = UsersRepository(db)
        self.rbac = RbacRepository(db)
        self.settings = SettingsRepository(db)
        self.templates = NotificationTemplatesRepository(db)
        self.providers = ProvidersRepository(db)
        self.categories = CategoriesRepository(db)
        self.services = ServicesRepository(db)
        self.orders = OrdersRepository(db)
        self.transactions = TransactionsRepository(db)
        self.payments = PaymentsRepository(db)
        self.payment_methods = PaymentMethodsRepository(db)
        self.tickets = TicketsRepository(db)
        self.notifications = NotificationsRepository(db)
        self.audit = AuditRepository(db)
        self.broadcasts = BroadcastsRepository(db)
        self.idempotency = IdempotencyRepository(db)
        self.provider_requests = ProviderRequestsRepository(db)
        self.error_logs = ErrorLogsRepository(db)
        self.backups = BackupsRepository(db)
        self.channel_outbox = ChannelOutboxRepository(db)
        self.order_message_refs = OrderMessageRefsRepository(db)
        self.favorites = FavoritesRepository(db)
