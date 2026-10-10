"""
نماذج البيانات (Data Models) — تمثيل صفوف الجداول ككائنات Python.

لماذا dataclasses بدل ORM كامل؟
    • خفيفة وسريعة ولا تُخفي ما يحدث في SQL.
    • تُبقي كل عبارات SQL ظاهرة في المستودعات (repositories) مما يسهّل
      مراجعتها أمنياً ونقلها لاحقاً إلى PostgreSQL.

كل نموذج يوفّر from_row لتحويل صف قاعدة البيانات إلى كائن، مع تجاهل أي أعمدة إضافية.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Iterable, Mapping, TypeVar

from core.money import from_units

_T = TypeVar("_T", bound="BaseModel")


@dataclass(slots=True)
class BaseModel:
    """أساس كل النماذج: يوفّر التحويل من صف قاعدة بيانات إلى كائن."""

    @classmethod
    def from_row(cls: type[_T], row: Mapping[str, Any] | None) -> _T | None:
        """تحويل صف واحد إلى كائن النموذج، أو None إذا لم يوجد صف."""
        if row is None:
            return None
        allowed = {f.name for f in fields(cls)}
        data = {key: row[key] for key in row.keys() if key in allowed}
        return cls(**data)  # type: ignore[arg-type]

    @classmethod
    def from_rows(cls: type[_T], rows: Iterable[Mapping[str, Any]]) -> list[_T]:
        """تحويل مجموعة صفوف إلى قائمة كائنات."""
        result: list[_T] = []
        for row in rows:
            item = cls.from_row(row)
            if item is not None:
                result.append(item)
        return result


# ------------------------------- المستخدمون ------------------------------- #


@dataclass(slots=True)
class User(BaseModel):
    """مستخدم البوت (عميل أو أدمن)."""

    id: int
    telegram_id: int
    created_at: str
    updated_at: str
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    balance_units: int = 0
    total_spent_units: int = 0
    total_deposited_units: int = 0
    role: str = "user"
    is_banned: int = 0
    ban_reason: str | None = None
    banned_at: str | None = None
    blocked_bot: int = 0
    language: str = "ar"
    referrer_id: int | None = None
    notes: str | None = None
    last_activity: str | None = None

    @property
    def balance(self):
        """الرصيد كقيمة عشرية للعرض فقط (التخزين والحساب يبقى بالنقاط)."""
        return from_units(self.balance_units)

    @property
    def display_name(self) -> str:
        """اسم مناسب للعرض في لوحة الأدمن."""
        if self.username:
            return f"@{self.username}"
        return self.first_name or f"ID:{self.telegram_id}"

    @property
    def banned(self) -> bool:
        """هل المستخدم محظور؟"""
        return bool(self.is_banned)


# -------------------------------- المزودون -------------------------------- #


@dataclass(slots=True)
class Provider(BaseModel):
    """مزود خدمات SMM خارجي."""

    id: int
    name: str
    api_url: str
    api_key_enc: str
    created_at: str
    updated_at: str
    api_key_hint: str | None = None
    api_type: str = "perfect_panel"
    balance_units: int = 0
    currency: str = "USD"
    #: سعر الصرف: 1 وحدة من `currency` = X من عملة النظام (نص Decimal)؛ None ⇒ لا سعر (يُقبل فقط عند تطابق العملتين)
    exchange_rate: str | None = None
    balance_checked_at: str | None = None
    low_balance_threshold_units: int | None = None
    is_active: int = 1
    priority: int = 100
    timeout_seconds: int = 30
    consecutive_failures: int = 0
    disabled_until: str | None = None
    last_error: str | None = None
    last_success_at: str | None = None

    @property
    def active(self) -> bool:
        """هل المزود مفعّل؟ (التعطيل المؤقت يُفحص في ProviderService)."""
        return bool(self.is_active)


# --------------------------- التصنيفات والخدمات ---------------------------- #


@dataclass(slots=True)
class ServiceCategory(BaseModel):
    """تصنيف خدمات (منصة مثل انستغرام أو تيك توك)."""

    id: int
    name_ar: str
    created_at: str
    updated_at: str
    name_en: str | None = None
    emoji: str = "📦"
    sort_order: int = 100
    is_active: int = 1

    @property
    def title(self) -> str:
        """العنوان المعروض على الزر."""
        return f"{self.emoji} {self.name_ar}"


@dataclass(slots=True)
class Service(BaseModel):
    """خدمة معروضة للبيع."""

    id: int
    category_id: int
    provider_id: int
    provider_service_id: str
    name: str
    price_per_1000_units: int
    min_quantity: int
    max_quantity: int
    created_at: str
    updated_at: str
    description: str | None = None
    service_type: str = "default"
    provider_price_per_1000_units: int | None = None
    dripfeed_enabled: int = 0
    refill_enabled: int = 0
    cancel_enabled: int = 0
    link_pattern: str | None = None
    avg_time_text: str | None = None
    is_active: int = 1
    is_archived: int = 0
    sort_order: int = 100
    link_rule: str | None = None
    speed_text: str | None = None
    quality_text: str | None = None
    guarantee_text: str | None = None
    provider_missing_at: str | None = None
    disabled_by_sync: int = 0

    @property
    def available(self) -> bool:
        """هل الخدمة متاحة للطلب الآن؟"""
        return bool(self.is_active) and not bool(self.is_archived)

    @property
    def margin_units(self) -> int | None:
        """هامش الربح لكل ألف (None إذا لم تُسجَّل تكلفة المزود)."""
        if self.provider_price_per_1000_units is None:
            return None
        return self.price_per_1000_units - self.provider_price_per_1000_units


# --------------------------------- الطلبات -------------------------------- #


@dataclass(slots=True)
class Order(BaseModel):
    """طلب عميل على خدمة."""

    id: int
    user_id: int
    service_id: int
    provider_id: int
    service_name_snapshot: str
    price_per_1000_snapshot_units: int
    link: str
    quantity: int
    cost_units: int
    client_request_id: str
    created_at: str
    updated_at: str
    public_code: str | None = None
    provider_cost_units: int | None = None
    status: str = "pending"
    provider_status: str | None = None
    provider_order_id: str | None = None
    start_count: int | None = None
    remains: int | None = None
    delivered_quantity: int | None = None
    refund_amount_units: int = 0
    refunded_at: str | None = None
    submit_attempts: int = 0
    checks_count: int = 0
    last_error: str | None = None
    locked_by: str | None = None
    locked_until: str | None = None
    next_check_at: str | None = None
    submitted_at: str | None = None
    completed_at: str | None = None
    cancelled_at: str | None = None
    # v1.3.1 (ترحيل 0013): شفافية المتابعة — آخر فحص ومحاولة ناجحة وآخر خطأ فحص وعدد الإخفاقات المتتالية
    last_checked_at: str | None = None
    last_check_ok_at: str | None = None
    last_check_error: str | None = None
    check_fail_streak: int = 0

    @property
    def refundable_units(self) -> int:
        """المبلغ المتبقي القابل للاسترجاع (التكلفة ناقص ما استُرجع)."""
        return max(0, self.cost_units - self.refund_amount_units)


@dataclass(slots=True)
class OrderStatusHistory(BaseModel):
    """سجل انتقال حالة طلب."""

    id: int
    order_id: int
    to_status: str
    created_at: str
    from_status: str | None = None
    actor_type: str = "system"
    actor_id: int | None = None
    reason: str | None = None
    provider_status_raw: str | None = None


# ----------------------------- الحركات المالية ----------------------------- #


@dataclass(slots=True)
class Transaction(BaseModel):
    """حركة مالية في دفتر الأستاذ (إضافة فقط — لا تُعدَّل ولا تُحذف)."""

    id: int
    user_id: int
    type: str
    direction: str
    amount_units: int
    balance_before_units: int
    balance_after_units: int
    created_at: str
    order_id: int | None = None
    payment_id: int | None = None
    description: str | None = None
    reference: str | None = None
    actor_id: int | None = None

    @property
    def signed_amount_units(self) -> int:
        """المبلغ بإشارته (موجب للإضافة وسالب للخصم) لعرضه في السجل."""
        return self.amount_units if self.direction == "credit" else -self.amount_units


# -------------------------------- المدفوعات -------------------------------- #


@dataclass(slots=True)
class PaymentMethod(BaseModel):
    """طريقة شحن رصيد قابلة للتهيئة من لوحة الأدمن."""

    id: int
    code: str
    name_ar: str
    created_at: str
    updated_at: str
    type: str = "manual"
    instructions_ar: str = ""
    account_details: str = ""
    min_amount_units: int = 0
    max_amount_units: int | None = None
    requires_proof: int = 1
    is_active: int = 1
    sort_order: int = 100
    fee_percent_bp: int = 0      # رسوم نسبية بنقاط الأساس (250 = 2.5%)
    fee_fixed_units: int = 0     # رسوم ثابتة بالنقاط تُخصم من كل حوالة

    @property
    def has_fees(self) -> bool:
        """هل لهذه الطريقة رسوم تُخصم من مبلغ الحوالة؟"""
        return self.fee_percent_bp > 0 or self.fee_fixed_units > 0


@dataclass(slots=True)
class Payment(BaseModel):
    """طلب شحن رصيد."""

    id: int
    user_id: int
    method_id: int
    amount_units: int
    created_at: str
    updated_at: str
    credited_units: int | None = None
    status: str = "pending"
    transaction_reference: str | None = None
    proof_file_id: str | None = None
    proof_file_type: str | None = None
    user_note: str | None = None
    admin_id: int | None = None
    admin_note: str | None = None
    reject_reason: str | None = None
    reviewed_at: str | None = None
    expires_at: str | None = None
    fee_units: int = 0           # لقطة رسوم الطريقة وقت الإرسال (لا تتغير لاحقاً)

    @property
    def net_units(self) -> int:
        """
        المبلغ الصافي المتوقع إضافته للرصيد = المبلغ المحوَّل − الرسوم.

        يُستخدم كقيمة افتراضية في شاشة الاعتماد، ويبقى للأدمن حق تعديله.
        """
        return max(0, int(self.amount_units) - int(self.fee_units or 0))


# ---------------------------------- الدعم ---------------------------------- #


@dataclass(slots=True)
class SupportTicket(BaseModel):
    """تذكرة دعم فني."""

    id: int
    user_id: int
    subject: str
    created_at: str
    updated_at: str
    category: str = "other"
    related_order_id: int | None = None
    status: str = "open"
    priority: str = "normal"
    assigned_admin: int | None = None
    last_message_at: str | None = None
    closed_by: int | None = None
    close_reason: str | None = None
    closed_at: str | None = None

    @property
    def is_open(self) -> bool:
        """هل التذكرة ما زالت مفتوحة؟"""
        return self.status != "closed"


@dataclass(slots=True)
class SupportMessage(BaseModel):
    """رسالة داخل تذكرة دعم."""

    id: int
    ticket_id: int
    sender_type: str
    message: str
    created_at: str
    sender_id: int | None = None
    attachment_file_id: str | None = None
    attachment_type: str | None = None
    telegram_message_id: int | None = None
    is_read_by_user: int = 0
    is_read_by_admin: int = 0


# -------------------------------- الإشعارات -------------------------------- #


@dataclass(slots=True)
class Notification(BaseModel):
    """إشعار في صندوق الإرسال (Outbox)."""

    id: int
    user_id: int
    type: str
    message: str
    dedupe_key: str
    created_at: str
    title: str = ""
    payload_json: str | None = None
    status: str = "queued"
    attempts: int = 0
    next_attempt_at: str | None = None
    last_error: str | None = None
    telegram_message_id: int | None = None
    is_read: int = 0
    sent_at: str | None = None


@dataclass(slots=True)
class ChannelPost(BaseModel):
    """منشور في صندوق إرسال القنوات الإدارية (تنبيهات الإدارة / توثيق الطلبات)."""

    id: int
    kind: str
    message: str
    dedupe_key: str
    created_at: str
    title: str = ""
    status: str = "queued"
    attempts: int = 0
    next_attempt_at: str | None = None
    last_error: str | None = None
    sent_at: str | None = None


@dataclass(slots=True)
class OrderMessageRef(BaseModel):
    """مرجع رسالة تيليجرام تعرض حالة طلب (تُعدَّل عند تغيّر الحالة). `rendered_hash` = مفتاح حالة الطلب وقت آخر عرض."""

    id: int
    order_id: int
    kind: str
    chat_id: str
    message_id: int
    created_at: str
    updated_at: str
    rendered_status: str | None = None
    rendered_hash: str | None = None
    fail_count: int = 0
    next_try_at: str | None = None
    is_dead: int = 0
    last_error: str | None = None


# ------------------------------ الإعدادات والسجل ---------------------------- #


@dataclass(slots=True)
class Setting(BaseModel):
    """إعداد عام من جدول settings."""

    key: str
    value: str
    updated_at: str
    value_type: str = "str"
    group_code: str = "general"
    name_ar: str = ""
    description_ar: str | None = None
    is_editable: int = 1
    updated_by: int | None = None


@dataclass(slots=True)
class AuditLog(BaseModel):
    """سجل عملية إدارية حساسة."""

    id: int
    action: str
    created_at: str
    admin_id: int | None = None
    target_type: str | None = None
    target_id: str | None = None
    details_json: str | None = None
    before_json: str | None = None
    after_json: str | None = None
    source: str = "telegram"


@dataclass(slots=True)
class Broadcast(BaseModel):
    """رسالة جماعية."""

    id: int
    created_at: str
    admin_id: int | None = None
    message_text: str = ""
    parse_mode: str | None = None
    media_file_id: str | None = None
    media_type: str | None = None
    buttons_json: str | None = None
    target: str = "all"
    target_filter_json: str | None = None
    total_count: int = 0
    sent_count: int = 0
    failed_count: int = 0
    blocked_count: int = 0
    status: str = "draft"
    started_at: str | None = None
    finished_at: str | None = None


@dataclass(slots=True)
class NotificationTemplate(BaseModel):
    """قالب إشعار مخصّص من لوحة التحكم (المرحلة 8) — غيابه يعني استعمال النص الافتراضي."""

    code: str
    title: str
    body: str
    updated_at: str
    is_active: int = 1
    updated_by: int | None = None

    @property
    def enabled(self) -> bool:
        """هل القالب المخصّص مفعّل فعلاً (وإلا يعود النظام للنص المدمج)؟"""
        return bool(self.is_active)
