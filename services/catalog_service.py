"""
خدمة الكتالوج: التصنيفات والخدمات وحساب سعر الطلب قبل تأكيده.

مبدأ مهم: سعر الخدمة يُقرأ من قاعدة البيانات في لحظة الطلب ويُخزَّن كلقطة داخل الطلب،
فتغيير السعر لاحقاً لا يؤثر على الطلبات القديمة ولا على المحاسبة.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from core.constants import PAGE_SIZE
from core.exceptions import DuplicateOperationError, ServiceNotAvailableError, SMMBotError, ValidationError
from core.money import format_units, order_cost_units, unit_price_units
from core.permissions import Permission
from database.database import Database
from database.models import Service, ServiceCategory, User
from database.repositories import Repositories
from integrations.providers.base import SUPPORTED_SERVICE_TYPES, ProviderServiceItem
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.settings_service import SettingsService
from texts import ar
from utils.link_rules import LINK_RULES, infer_rule
from utils.logging_setup import get_logger
from utils.validators import clean_text, validate_quantity

logger = get_logger(__name__)

#: أقصى عدد خدمات في مفضلة المستخدم الواحد (حماية من تضخم الجدول)
MAX_FAVORITES = 100

#: أقصى عدد خدمات في دفعة استيراد واحدة (يبقي الرد ضمن حدود تيليجرام والمهلة)
MAX_IMPORT_BATCH = 50

#: حقول العرض القابلة للتعديل من بطاقة الأدمن ⇒ اسمها العربي للتحقق والرسائل
DISPLAY_FIELDS: dict[str, str] = {
    "speed_text": "السرعة",
    "quality_text": "الجودة",
    "guarantee_text": "الضمان",
    "link_rule": "قاعدة الرابط",
}


@dataclass(frozen=True)
class ImportOutcome:
    """نتيجة استيراد عنصر واحد من دفعة: created | duplicate | failed."""

    item: ProviderServiceItem
    status: str
    service: Service | None
    reason: str


@dataclass(frozen=True)
class BatchImportReport:
    """تقرير دفعة الاستيراد بكل عنصر على حدة."""

    outcomes: list[ImportOutcome]

    @property
    def created(self) -> list[ImportOutcome]:
        """العناصر التي أُنشئت."""
        return [o for o in self.outcomes if o.status == "created"]

    @property
    def duplicates(self) -> list[ImportOutcome]:
        """العناصر المستوردة سابقاً."""
        return [o for o in self.outcomes if o.status == "duplicate"]

    @property
    def failed(self) -> list[ImportOutcome]:
        """العناصر التي فشلت (نوع غير مدعوم، بيانات غير صالحة...)."""
        return [o for o in self.outcomes if o.status == "failed"]


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
class CostChange:
    """تغيّر تكلفة خدمة لدى المزود: سعر البيع لم يتغيّر (قرار الأدمن) فيتغيّر الهامش فقط."""

    service: Service
    old_cost_units: int
    new_cost_units: int

    @property
    def new_margin_units(self) -> int:
        """هامش الربح لكل ألف بعد التحديث (قد يكون سالباً)."""
        return self.service.price_per_1000_units - self.new_cost_units


@dataclass(frozen=True, slots=True)
class SyncReport:
    """
    نتيجة مزامنة خدمات مزود مع قائمته الحالية.

    الحقول:
        checked          : عدد خدماتنا المرتبطة بهذا المزود.
        updated          : كم خدمة تغيّرت تكلفتها أو حدودها فعلياً.
        unchanged        : كم خدمة كانت مطابقة أصلاً.
        missing          : خدمات لم تعد موجودة لدى المزود (لا تُحذف أبداً).
        negative_margin  : خدمات صار سعر بيعها أقل من تكلفتها بعد المزامنة.
        provider_items   : عدد الخدمات التي أرسلها المزود.
        unsupported      : خدمات صار نوعها لدى المزود غير مدعوم فعُطِّلت.
        new_items        : خدمات جديدة لدى المزود لم تُستورد بعد (نوعها مدعوم فقط).
        cost_changes     : الخدمات التي تغيّرت تكلفتها (قديم/جديد).
        limit_changes    : الخدمات التي تغيّرت حدود كميتها.
        disabled_missing : خدمات عطّلتها المزامنة الآن لأنها اختفت لدى المزود.
        restored         : خدمات أعادت المزامنة تفعيلها لأنها عادت للظهور لدى المزود.
        missing_suspicious: اختفاء جماعي أو قائمة فارغة ⇒ عُدَّ عطلاً ولم يُعطَّل شيء.
    """

    checked: int
    updated: int
    unchanged: int
    missing: list[Service]
    negative_margin: list[Service]
    provider_items: int
    unsupported: list[Service] = field(default_factory=list)
    new_items: list[ProviderServiceItem] = field(default_factory=list)
    cost_changes: list[CostChange] = field(default_factory=list)
    limit_changes: list[Service] = field(default_factory=list)
    disabled_missing: list[Service] = field(default_factory=list)
    restored: list[Service] = field(default_factory=list)
    missing_suspicious: bool = False


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

    # ------------------------------- المفضلة ------------------------------ #

    async def add_favorite(self, user: User, service_id: int) -> bool:
        """
        إضافة خدمة متاحة لمفضلة المستخدم (بلا تكرار: المفتاح المركّب يمنعه بنيوياً).

        المخرجات: True إن أُضيفت الآن، False إن كانت موجودة.

        الاستثناءات:
            ServiceNotAvailableError : الخدمة غير متاحة.
            ValidationError          : تجاوز الحد الأقصى `MAX_FAVORITES`.
        """
        await self.get_available_service(service_id)
        async with self.db.transaction() as tx:
            if await self.repos.favorites.exists(user.id, service_id):
                return False
            if await self.repos.favorites.count_for_user(user.id) >= MAX_FAVORITES:
                raise ValidationError(
                    "تجاوز حد المفضلة",
                    user_message=ar.FAVORITE_LIMIT.format(limit=MAX_FAVORITES),
                )
            return await self.repos.favorites.add(tx, user.id, service_id)

    async def remove_favorite(self, user: User, service_id: int) -> bool:
        """إزالة خدمة من المفضلة؛ المخرجات: True إن كانت موجودة (لا خطأ إن لم تكن)."""
        async with self.db.transaction() as tx:
            return await self.repos.favorites.remove(tx, user.id, service_id)

    async def is_favorite(self, user: User, service_id: int) -> bool:
        """هل الخدمة في مفضلة المستخدم؟"""
        return await self.repos.favorites.exists(user.id, service_id)

    async def favorites_page(self, user: User, *, page: int, page_size: int) -> tuple[list[Service], int, int]:
        """
        صفحة من مفضلة المستخدم (المتاحة للطلب فقط).

        المخرجات: (الخدمات، رقم الصفحة بعد التصحيح، عدد الصفحات).
        """
        total = await self.repos.favorites.count_available(user.id)
        pages = max(1, -(-total // page_size))
        current = min(max(1, page), pages)
        items = await self.repos.favorites.list_available(user.id, limit=page_size, offset=(current - 1) * page_size)
        return items, current, pages

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
        service_type: str = "default",
        link_rule: str | None = None,
        speed_text: str | None = None,
        quality_text: str | None = None,
        guarantee_text: str | None = None,
    ) -> Service:
        """
        إضافة خدمة جديدة للكتالوج.

        الاستثناءات: PermissionDeniedError · ValidationError · DuplicateOperationError
        (خدمة المزود نفسها موجودة — تُفحص داخل المعاملة وتحميها قيود فريدة في القاعدة ضد السباق).
        """
        await self.auth.require_permission(actor, Permission.SERVICES_CREATE, context="service.create")
        clean_name = clean_text(name, field="اسم الخدمة", max_length=120, min_length=3)
        self._ensure_supported_type(service_type, name=clean_name)
        clean_rule = self._clean_link_rule(link_rule)
        speed_text = self._clean_display_text(speed_text, "السرعة")
        quality_text = self._clean_display_text(quality_text, "الجودة")
        guarantee_text = self._clean_display_text(guarantee_text, "الضمان")
        duplicate = DuplicateOperationError(
            f"خدمة المزود {provider_service_id} مستوردة مسبقاً للمزود {provider_id}",
            user_message="⚠️ هذه الخدمة مضافة مسبقاً لهذا المزود.",
        )
        try:
            async with self.db.transaction() as tx:
                # الفحص داخل المعاملة نفسها (BEGIN IMMEDIATE) فلا يتسلل مكرر عند ضغطتين متزامنتين
                if await tx.fetchval(
                    "SELECT 1 FROM services WHERE provider_id = ? AND provider_service_id = ?",
                    (provider_id, str(provider_service_id)),
                ):
                    raise duplicate
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
                    service_type=service_type,
                    link_rule=clean_rule,
                    speed_text=speed_text,
                    quality_text=quality_text,
                    guarantee_text=guarantee_text,
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
                        "provider_service_id": str(provider_service_id),
                        "link_rule": clean_rule,
                    },
                )
        except sqlite3.IntegrityError as exc:
            if "services.provider_id" in str(exc) or "uq_services_provider_service" in str(exc):
                raise duplicate from exc          # سباق نادر تجاوز الفحص: القيد الفريد حسم الأمر
            raise
        logger.info("أضاف الأدمن %s الخدمة %s (%s)", actor.id, service.id, clean_name)
        return service

    @staticmethod
    def _ensure_supported_type(service_type: str, *, name: str) -> None:
        """
        رفض أنواع الخدمات التي لا يدعمها مسار الطلب (Package/Custom Comments/Subscriptions…).

        السبب: هذه الأنواع تحتاج حقولاً إضافية (تعليقات، اسم مستخدم، مدة…) فلو استُوردت لأُرسل طلب ناقص
        الحقول للمزود وخُصم مال العميل ثم فشل أو نُفِّذ خطأً.
        """
        if service_type not in SUPPORTED_SERVICE_TYPES:
            raise ValidationError(
                f"نوع الخدمة غير مدعوم: {service_type} ({name})",
                user_message=(
                    f"⚠️ نوع هذه الخدمة («{service_type}») غير مدعوم حالياً: يحتاج حقولاً إضافية "
                    "لا يجمعها مسار الطلب. المدعوم: الخدمات العادية (default) فقط."
                ),
            )

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

        self._ensure_supported_type(item.service_type, name=item.name)
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
            service_type=item.service_type,
            link_rule=infer_rule(item.name, item.category),
        )
        logger.info(
            "استورد الأدمن %s الخدمة %s من المزود %s بهامش %s%%",
            actor.id, service.id, provider_id, margin_percent,
        )
        return service

    async def import_provider_services(
        self,
        actor: User,
        *,
        provider_id: int,
        items: list[ProviderServiceItem],
        category_id: int,
        margin_percent: int,
    ) -> BatchImportReport:
        """
        استيراد عدة خدمات من المزود دفعة واحدة بنفس التصنيف والهامش.

        كل خدمة تُستورد في معاملتها الخاصة عبر `import_provider_service`، فيفشل العنصر المعيب أو
        المكرّر وحده دون إسقاط الباقي، ويُرجَع تقرير دقيق بحالة كل عنصر. الربط (رقم داخلي ↔ مزود ↔
        Provider Service ID) يُنشأ لكل عنصر من بياناته هو لا من موضعه في القائمة.

        الاستثناءات (قبل أي استيراد): PermissionDeniedError · ValidationError (دفعة فارغة/كبيرة،
        تصنيف غير موجود، هامش غير صالح).
        """
        await self.auth.require_permission(
            actor, Permission.SERVICES_CREATE, context=f"provider:{provider_id}"
        )
        if not items:
            raise ValidationError("دفعة فارغة", user_message="❌ لم تُحدَّد أي خدمة للاستيراد.")
        if len(items) > MAX_IMPORT_BATCH:
            raise ValidationError(
                f"دفعة أكبر من الحد: {len(items)}",
                user_message=f"❌ الحد الأقصى {MAX_IMPORT_BATCH} خدمة في الدفعة الواحدة.",
            )
        if await self.repos.categories.get(category_id) is None:
            raise ValidationError(f"تصنيف غير موجود: {category_id}", user_message="❌ التصنيف غير موجود.")
        self.price_with_margin(0, margin_percent)  # يتحقق من الهامش مرة واحدة قبل البدء

        outcomes: list[ImportOutcome] = []
        seen: set[str] = set()
        for item in items:
            if item.provider_service_id in seen:
                continue  # تكرار داخل الدفعة نفسها: يُتجاهل بصمت (ليس خطأً)
            seen.add(item.provider_service_id)
            try:
                service = await self.import_provider_service(
                    actor,
                    provider_id=provider_id,
                    item=item,
                    category_id=category_id,
                    margin_percent=margin_percent,
                )
            except DuplicateOperationError:
                outcomes.append(ImportOutcome(item, "duplicate", None, "مستوردة مسبقاً"))
            except SMMBotError as exc:
                outcomes.append(ImportOutcome(item, "failed", None, exc.user_message or str(exc)))
            else:
                outcomes.append(ImportOutcome(item, "created", service, ""))

        report = BatchImportReport(outcomes=outcomes)
        async with self.db.transaction() as tx:
            await self.audit.log(
                tx,
                action="services.import_batch",
                admin_id=actor.id,
                target_type="provider",
                target_id=provider_id,
                after={
                    "requested": len(items),
                    "created": [o.service.id for o in report.created if o.service],
                    "duplicates": len(report.duplicates),
                    "failed": len(report.failed),
                    "category_id": category_id,
                    "margin_percent": margin_percent,
                },
            )
        return report

    # ---------------------------- حقول عرض الخدمة --------------------------- #

    @staticmethod
    def _clean_link_rule(value: str | None) -> str | None:
        """قاعدة الرابط: فارغ ⇒ None؛ مفتاح غير معروف ⇒ ValidationError."""
        key = (value or "").strip()
        if not key:
            return None
        if key not in LINK_RULES:
            raise ValidationError(f"قاعدة رابط غير معروفة: {key}", user_message="❌ قاعدة الرابط غير معروفة.")
        return key

    @staticmethod
    def _clean_display_text(value: str | None, field: str) -> str | None:
        """نص عرض اختياري (سرعة/جودة/ضمان): فارغ ⇒ None وإلا نص منظَّف بحد 60 حرفاً."""
        if value is None or not value.strip():
            return None
        return clean_text(value, field=field, max_length=60, min_length=1)

    async def admin_set_display_field(self, actor: User, service_id: int, field: str, value: str | None) -> Service:
        """
        تعديل أحد حقول العرض للخدمة: `speed_text` · `quality_text` · `guarantee_text` · `link_rule`.

        القيمة الفارغة تمسح الحقل (يعود «غير محددة»/«بلا قيد»). كل تعديل يُسجَّل في سجل التدقيق
        بالقيمة قبل وبعد. لا يمسّ هذا السعر ولا الطلبات القائمة.

        الاستثناءات: PermissionDeniedError (`services.update`) · ValidationError · NotFoundError.
        """
        await self.auth.require_permission(actor, Permission.SERVICES_UPDATE, context=f"service:{service_id}")
        if field not in DISPLAY_FIELDS:
            raise ValidationError(f"حقل غير مسموح: {field}", user_message="❌ هذا الحقل غير قابل للتعديل.")
        if field == "link_rule":
            clean = self._clean_link_rule(value)
        else:
            clean = self._clean_display_text(value, DISPLAY_FIELDS[field])
        async with self.db.transaction() as tx:
            before = await self.repos.services.get(service_id)
            if before is None:
                raise ValidationError(f"خدمة غير موجودة: {service_id}", user_message="❌ الخدمة غير موجودة.")
            await self.repos.services.update_fields(tx, service_id, **{field: clean})
            await self.audit.log(
                tx,
                action="services.update",
                admin_id=actor.id,
                target_type="service",
                target_id=service_id,
                before={field: getattr(before, field)},
                after={field: clean},
            )
        updated = await self.repos.services.get(service_id)
        assert updated is not None
        return updated

    async def sync_provider_services(
        self, actor: User, *, provider_id: int, items: list[ProviderServiceItem]
    ) -> SyncReport:
        """
        مزامنة خدماتنا المرتبطة بمزود مع قائمته الحالية (كل التغييرات في معاملة واحدة ذرّية).

        ما تفعله:
            • تحديث **تكلفة المزود** وحدود الكمية لكل خدمة عندنا (وتسجيل القديم/الجديد في التدقيق).
            • اكتشاف الخدمات **الجديدة** لدى المزود (لم تُستورد) وإبلاغ الأدمن بها دون استيرادها آلياً.
            • الخدمة التي اختفت من القائمة: تُعطَّل (إن كان `sync_auto_disable_missing` مفعّلاً) بعلامة
              تمنع بيعها، وتعود تلقائياً إن ظهرت من جديد. **لا حذف أبداً**.
            • الحماية من العطل: قائمة فارغة، أو اختفاء أكثر من نصف خدماتنا (حين تتجاوز عشراً) يُعدّ
              عطلاً في المزود ⇒ لا يُعطَّل شيء ويُبلَّغ الأدمن بذلك.
        ما لا تفعله عمداً:
            • لا تغيّر سعر البيع (قرار تجاري بيد الأدمن) ولا تمسّ جدول الطلبات: الطلبات القائمة
              والتاريخية تحمل لقطتها الخاصة وتكمل دورتها حتى لو عُطّلت الخدمة.

        المخرجات: `SyncReport` بكل الأرقام والقوائم اللازمة لعرض نتيجة واضحة.

        الاستثناءات: PermissionDeniedError (تحتاج `services.sync`).
        """
        await self.auth.require_permission(
            actor, Permission.SERVICES_SYNC, context=f"provider:{provider_id}"
        )
        by_provider_id = {item.provider_service_id: item for item in items}
        auto_disable = await self.settings.get_bool("sync_auto_disable_missing", True)

        async with self.db.transaction() as tx:
            # يُقرأ داخل المعاملة نفسها فلا يتداخل مزامنتان متزامنتان على لقطتين مختلفتين
            ours = await self.repos.services.list_all_by_provider(provider_id)
            known_ids = {str(service.provider_service_id) for service in ours}

            cost_changes: list[CostChange] = []
            limit_changes: list[Service] = []
            changed_ids: set[int] = set()
            missing: list[Service] = []
            unsupported: list[Service] = []
            restored: list[Service] = []
            unchanged = 0

            for service in ours:
                item = by_provider_id.get(str(service.provider_service_id))
                if item is None:
                    missing.append(service)
                    continue

                fields: dict[str, object] = {}
                if service.provider_missing_at is not None:
                    fields["provider_missing_at"] = None          # عاد للظهور لدى المزود

                if item.service_type not in SUPPORTED_SERVICE_TYPES:
                    # النوع تغيّر لدى المزود إلى ما لا ندعمه: لا نعدّل سعره ولا نتركه يُباع
                    if service.is_active:
                        await self.repos.services.set_active(tx, service.id, False)
                        unsupported.append(service)
                    if fields:
                        await self.repos.services.update_fields(tx, service.id, **fields)
                    continue

                if item.rate_per_1000_units != (service.provider_price_per_1000_units or 0):
                    fields["provider_price_per_1000_units"] = item.rate_per_1000_units
                    cost_changes.append(
                        CostChange(service, service.provider_price_per_1000_units or 0, item.rate_per_1000_units)
                    )
                    changed_ids.add(service.id)
                limits: dict[str, int] = {}
                if item.min_quantity != service.min_quantity:
                    limits["min_quantity"] = item.min_quantity
                if item.max_quantity != service.max_quantity:
                    limits["max_quantity"] = item.max_quantity
                if limits:
                    fields.update(limits)
                    limit_changes.append(service)
                    changed_ids.add(service.id)

                # عادت لدى المزود بعد أن عطّلتها المزامنة ⇒ يُعاد تفعيلها (التعطيل اليدوي لا يُمسّ)
                came_back = bool(service.disabled_by_sync and not service.is_active and not service.is_archived)
                if came_back:
                    fields.update({"is_active": 1, "disabled_by_sync": 0})
                    restored.append(service)

                if fields:
                    await self.repos.services.update_fields(tx, service.id, **fields)
                if service.id not in changed_ids and not came_back:
                    unchanged += 1

            # ------------------------- الخدمات المختفية ------------------------- #
            suspicious = False
            disabled_missing: list[Service] = []
            if missing:
                suspicious = not items or (len(ours) >= 10 and len(missing) * 2 > len(ours))
                if auto_disable and not suspicious:
                    for service in missing:
                        if service.is_active and not service.is_archived:
                            await self.repos.services.disable_by_sync(tx, service.id)
                            disabled_missing.append(service)
                        elif service.provider_missing_at is None:
                            await self.repos.services.update_fields(
                                tx, service.id, provider_missing_at=self.repos.services.now()
                            )

            new_items = [
                item
                for item in items
                if item.provider_service_id not in known_ids and item.service_type in SUPPORTED_SERVICE_TYPES
            ]

            if cost_changes or limit_changes or disabled_missing or restored or unsupported:
                await self.audit.log(
                    tx,
                    action="services.sync",
                    admin_id=actor.id,
                    target_type="provider",
                    target_id=provider_id,
                    before={
                        "costs": {str(c.service.id): c.old_cost_units for c in cost_changes[:200]},
                    },
                    after={
                        "provider_items": len(items),
                        "updated": len(changed_ids),
                        "costs": {str(c.service.id): c.new_cost_units for c in cost_changes[:200]},
                        "limits": [service.id for service in limit_changes[:200]],
                        "missing": len(missing),
                        "disabled_missing": [service.id for service in disabled_missing[:200]],
                        "restored": [service.id for service in restored[:200]],
                        "unsupported": [service.id for service in unsupported[:200]],
                        "new_at_provider": len(new_items),
                    },
                )

        negative = await self.repos.services.negative_margin_services(provider_id)
        logger.info(
            "مزامنة المزود %s: لدى المزود %s، حُدّثت %s، جديدة %s، مفقودة %s (عُطّلت %s)، عادت %s",
            provider_id, len(items), len(changed_ids), len(new_items), len(missing),
            len(disabled_missing), len(restored),
        )
        if suspicious:
            logger.warning(
                "مزامنة المزود %s: اختفاء %s من %s خدمة (قائمة المزود %s) عُدَّ عطلاً — لم يُعطَّل شيء",
                provider_id, len(missing), len(ours), len(items),
            )
        return SyncReport(
            checked=len(ours),
            updated=len(changed_ids),
            unchanged=unchanged,
            missing=missing,
            negative_margin=negative,
            provider_items=len(items),
            unsupported=unsupported,
            new_items=new_items,
            cost_changes=cost_changes,
            limit_changes=limit_changes,
            disabled_missing=disabled_missing,
            restored=restored,
            missing_suspicious=suspicious,
        )

    async def services_of_provider(self, actor: User, provider_id: int) -> list[Service]:
        """قائمة خدماتنا المرتبطة بمزود معيّن بلا سقف (للاستعمال البرمجي؛ الواجهة تستعمل الصفحات)."""
        await self.auth.require_permission(
            actor, Permission.SERVICES_VIEW, context=f"provider:{provider_id}"
        )
        return await self.repos.services.list_all_by_provider(provider_id)

    async def provider_services_page(
        self, actor: User, provider_id: int, *, page: int = 1, page_size: int = PAGE_SIZE
    ) -> Page:
        """صفحة من خدماتنا المرتبطة بمزود (لا تحمّل آلاف الخدمات في الذاكرة لعرض صفحة واحدة)."""
        await self.auth.require_permission(
            actor, Permission.SERVICES_VIEW, context=f"provider:{provider_id}"
        )
        total = await self.repos.services.count_by_provider(provider_id)
        pages = max(1, -(-total // page_size))
        page = min(max(1, page), pages)
        items = await self.repos.services.list_by_provider(
            provider_id, limit=page_size, offset=(page - 1) * page_size
        )
        return Page(items=list(items), page=page, total_items=total, page_size=page_size)

    # ----------------------------- بحث الأدمن ----------------------------- #

    async def admin_search_services(
        self, actor: User, term: str, *, page: int = 1, page_size: int = PAGE_SIZE
    ) -> Page:
        """
        بحث الأدمن عن خدمة بأي مما يلي: معرّف الخدمة عندنا (`123` أو `#123`) · معرّف الخدمة لدى المزود ·
        جزء من الاسم · اسم القسم · اسم المزود. عدة كلمات = كلها يجب أن تتحقق (مثل «instagram followers»).

        يشمل المعطّلة والمؤرشفة (للأدمن). الأحرف الخاصة في البحث تُعامَل كنص عادي.

        الاستثناءات: PermissionDeniedError (`services.view`) · ValidationError (نص أقصر من حرفين).
        """
        await self.auth.require_permission(actor, Permission.SERVICES_VIEW, context="search")
        cleaned = clean_text(term.lstrip("#").strip() or term, field="نص البحث", max_length=60, min_length=1)
        tokens = [token for token in cleaned.split() if token][:5]
        numeric = int(tokens[0]) if len(tokens) == 1 and tokens[0].isdigit() and len(tokens[0]) <= 12 else None
        if numeric is None and not any(len(token) >= 2 for token in tokens):
            raise ValidationError("نص بحث قصير", user_message="❌ اكتب حرفين على الأقل للبحث (أو رقم الخدمة).")
        exact = numeric is not None and await self.repos.services.has_exact_id(numeric)
        total = await self.repos.services.admin_search_count(tokens, numeric=numeric, exact=exact)
        pages = max(1, -(-total // page_size))
        page = min(max(1, page), pages)
        items = await self.repos.services.admin_search(
            tokens, numeric=numeric, exact=exact, limit=page_size, offset=(page - 1) * page_size
        )
        return Page(items=list(items), page=page, total_items=total, page_size=page_size)
