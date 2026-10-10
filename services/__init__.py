"""
حزمة الخدمات — طبقة منطق العمل بين الواجهة (المرحلة 3+) وقاعدة البيانات.

لماذا حاوية خدمات؟
    الخدمات مترابطة (الطلبات تحتاج المحفظة والمزودين والإشعارات...). بدل أن تبني كل
    نقطة دخول اعتمادياتها بنفسها — فتتسرب الأخطاء وتتكرر الكائنات — تُبنى هنا مرة
    واحدة بترتيب صحيح، ويُمرَّر كائن `ServiceContainer` واحد إلى بقية النظام.

ترتيب البناء (من الأدنى اعتماداً إلى الأعلى):
    settings → audit → notifications → auth → wallet → users → catalog
    → providers → orders → payments → tickets → stats → templates → broadcasts → security → backups
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from database.database import Database
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.backup_service import BackupService
from services.broadcast_service import BroadcastService
from services.catalog_service import CatalogService
from services.channel_service import ChannelService
from services.notification_service import NotificationService
from services.order_message_service import OrderMessageService
from services.order_service import OrderService
from services.payment_service import PaymentService
from services.provider_service import ProviderService
from services.security_service import SecurityService
from services.settings_service import SettingsService
from services.stats_service import StatsService
from services.subscription_service import SubscriptionService
from services.template_service import TemplateService
from services.ticket_service import TicketService
from services.user_service import UserService
from services.wallet_service import WalletService
from utils.logging_setup import get_logger
from utils.security import SecretBox

logger = get_logger(__name__)

__all__ = [
    "AuditService",
    "AuthService",
    "BackupService",
    "BroadcastService",
    "CatalogService",
    "NotificationService",
    "OrderMessageService",
    "OrderService",
    "PaymentService",
    "ProviderService",
    "ServiceContainer",
    "SecurityService",
    "SettingsService",
    "StatsService",
    "TemplateService",
    "TicketService",
    "UserService",
    "WalletService",
    "build_services",
]


@dataclass(slots=True)
class ServiceContainer:
    """
    حاوية تضم نسخة واحدة من كل خدمة، جاهزة للتمرير إلى معالجات تيليجرام والمهام.

    الاستخدام:
        services = build_services(db, repos, secret_box=box, super_admin_ids=(123,))
        user, is_new = await services.users.get_or_create(...)
        order = await services.orders.create_order(user, service_id=1, link="...", quantity=100)
    """

    db: Database
    repos: Repositories
    settings: SettingsService
    audit: AuditService
    notifications: NotificationService
    auth: AuthService
    wallet: WalletService
    users: UserService
    catalog: CatalogService
    providers: ProviderService
    orders: OrderService
    payments: PaymentService
    tickets: TicketService
    stats: StatsService
    templates: TemplateService
    broadcasts: BroadcastService
    security: SecurityService
    backups: BackupService
    channels: ChannelService
    subscriptions: SubscriptionService
    order_messages: OrderMessageService

    def invalidate_caches(self) -> None:
        """
        إبطال الذاكرة المؤقتة للإعدادات بعد أي تعديل خارجي عليها.

        ملاحظة: عملاء المزودين تُفتح وتُغلق داخل كل عملية (`client.close()` في finally)،
        فلا توجد جلسات شبكة معلّقة تحتاج إغلاقاً عند إيقاف البوت.
        """
        self.settings.invalidate()

    async def startup_recovery(self) -> dict[str, int]:
        """
        إجراءات الاسترداد التي تُنفَّذ مرة واحدة عند إقلاع البوت.

        تشمل: تحرير الأقفال المنتهية ونقل الطلبات العالقة في الإرسال إلى «غير مؤكد».

        المخرجات: عدّادات ما تم استرداده.
        """
        report = await self.orders.recover_after_restart()
        # المرحلة 8: تحميل قوالب الإشعارات المخصّصة قبل إرسال أول رسالة،
        # وإلا خرجت أول الإشعارات بالنص الافتراضي رغم تعديل الأدمن له.
        report["templates_loaded"] = await self.templates.refresh_cache()
        logger.info("استرداد الإقلاع: %s", report)
        return report


def build_services(
    db: Database,
    repos: Repositories | None = None,
    *,
    secret_box: SecretBox,
    super_admin_ids: tuple[int, ...] = (),
    settings_ttl_seconds: float | None = None,
    backup_dir: Path | None = None,
    backup_channel_id: int | str | None = None,
    admin_alert_chat_id: int | str | None = None,
    app_version: str = "",
) -> ServiceContainer:
    """
    بناء كل الخدمات وربط اعتمادياتها بالترتيب الصحيح.

    المدخلات:
        db                   : اتصال قاعدة البيانات (مفتوح مسبقاً).
        repos                : المستودعات (تُبنى تلقائياً إن لم تُمرَّر).
        secret_box           : صندوق التشفير لمفاتيح المزودين (إجباري — لا مفاتيح واضحة).
        super_admin_ids      : معرفات الأدمن الأعلى من ملف البيئة (مسار طوارئ فقط).
        settings_ttl_seconds : مدة صلاحية كاش الإعدادات (يُستخدم 0 في الاختبارات لإلغاء الكاش).
        backup_dir           : مجلد النسخ الاحتياطية (الافتراضي: `backups` بجوار ملف القاعدة).
        backup_channel_id    : قناة النسخ الخارجية (None ⇒ غير مضبوطة)؛ مخصصة للنسخ فقط.
        admin_alert_chat_id  : `ADMIN_ALERT_CHAT_ID` من البيئة (بديل الإعداد إن لم يُضبط).
        app_version          : إصدار التطبيق (يُدوَّن في الملف الجانبي لكل نسخة).

    المخرجات: حاوية الخدمات الجاهزة للاستخدام.
    """
    repositories = repos if repos is not None else Repositories(db)

    settings = (
        SettingsService(db, repositories, ttl_seconds=settings_ttl_seconds)
        if settings_ttl_seconds is not None
        else SettingsService(db, repositories)
    )
    audit = AuditService(db, repositories)
    notifications = NotificationService(db, repositories, settings)
    auth = AuthService(db, repositories, settings, audit, super_admin_ids=super_admin_ids)
    wallet = WalletService(db, repositories, settings=settings, auth=auth)
    channels = ChannelService(
        db, repositories, settings, notifications,
        alert_chat_fallback=admin_alert_chat_id, backup_channel_id=backup_channel_id,
    )
    users = UserService(db, repositories, settings, audit, auth, notifications, channels)
    catalog = CatalogService(db, repositories, settings, audit, auth)
    providers = ProviderService(
        db, repositories, settings, audit, auth, notifications, secret_box
    )
    orders = OrderService(
        db, repositories, settings, wallet, catalog, providers, notifications, audit, auth, channels
    )
    payments = PaymentService(db, repositories, settings, wallet, notifications, audit, auth)
    tickets = TicketService(db, repositories, settings, notifications, audit, auth)
    stats = StatsService(db, repositories, settings, auth, providers, audit)
    template_service = TemplateService(db, repositories, auth, audit)
    broadcasts = BroadcastService(db, repositories, auth, audit, notifications, settings)

    backups = BackupService(
        db, repositories, settings, audit, auth, notifications,
        backup_dir=backup_dir if backup_dir is not None else db.path.parent / "backups",
        channel_id=backup_channel_id,
        app_version=app_version,
    )
    security = SecurityService(db, repositories, settings, auth, audit, backups)
    subscriptions = SubscriptionService(db, repositories, settings, notifications)
    order_messages = OrderMessageService(db, repositories, settings)
    notifications.order_notice_hook = order_messages.register

    logger.info("تم بناء طبقة الخدمات (%s خدمة)", 19)
    return ServiceContainer(
        db=db,
        repos=repositories,
        settings=settings,
        audit=audit,
        notifications=notifications,
        auth=auth,
        wallet=wallet,
        users=users,
        catalog=catalog,
        providers=providers,
        orders=orders,
        payments=payments,
        tickets=tickets,
        stats=stats,
        templates=template_service,
        broadcasts=broadcasts,
        security=security,
        backups=backups,
        channels=channels,
        subscriptions=subscriptions,
        order_messages=order_messages,
    )
