"""
تعدادات النظام (Enums) — المصدر الوحيد لكل القيم النصية المسموحة في قاعدة البيانات.

مهم جداً: أي قيمة هنا يجب أن تطابق قيود CHECK في ملفات الترحيل (migrations)،
ويوجد اختبار آلي يتحقق من هذا التطابق (tests/test_schema_constraints.py).
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """أدوار المستخدمين في النظام."""

    USER = "user"
    SUPPORT = "support"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"


class OrderStatus(StrEnum):
    """حالات الطلب — راجع جدول الانتقالات في core/order_state.py (المرحلة 2)."""

    PENDING = "pending"                    # أُنشئ وخُصم الرصيد، بانتظار الإرسال للمزود
    SUBMITTING = "submitting"              # جاري الإرسال (مقفول بـ lease)
    SUBMIT_UNCERTAIN = "submit_uncertain"  # انقطاع/مهلة: لا نعرف هل وصل الطلب للمزود
    SUBMITTED = "submitted"                # المزود قبل الطلب وأعطانا رقمه
    IN_PROGRESS = "in_progress"            # قيد التنفيذ عند المزود
    PARTIAL = "partial"                    # نُفِّذ جزئياً (مع استرجاع جزئي)
    COMPLETED = "completed"                # اكتمل
    CANCELED = "canceled"                  # أُلغي (مع استرجاع كامل)
    FAILED = "failed"                      # فشل الإرسال/رفضه المزود
    REFUNDED = "refunded"                  # استُرجع كامل المبلغ بعد فشل أو إلغاء


#: الحالات النهائية التي لا يجوز الانتقال منها إلى أي حالة أخرى
FINAL_ORDER_STATUSES: frozenset[str] = frozenset(
    {OrderStatus.COMPLETED, OrderStatus.PARTIAL, OrderStatus.REFUNDED, OrderStatus.CANCELED}
)

#: الحالات النشطة التي يتابعها job فحص الحالة
ACTIVE_ORDER_STATUSES: frozenset[str] = frozenset(
    {OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS}
)


class PaymentStatus(StrEnum):
    """حالات طلب الشحن."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class TransactionType(StrEnum):
    """أنواع الحركات المالية."""

    DEPOSIT = "deposit"                # شحن رصيد معتمد
    ORDER = "order"                    # خصم قيمة طلب
    REFUND = "refund"                  # استرجاع كامل
    PARTIAL_REFUND = "partial_refund"  # استرجاع جزئي (طلب partial)
    MANUAL_CREDIT = "manual_credit"    # إضافة يدوية من الأدمن
    MANUAL_DEBIT = "manual_debit"      # خصم يدوي من الأدمن
    WITHDRAW = "withdraw"              # سحب
    ADJUSTMENT = "adjustment"          # تسوية محاسبية


class TransactionDirection(StrEnum):
    """اتجاه الحركة المالية: إضافة أم خصم."""

    CREDIT = "credit"
    DEBIT = "debit"


#: الاتجاه الافتراضي لكل نوع حركة (يمنع التناقض بين النوع والاتجاه)
TRANSACTION_DIRECTIONS: dict[str, str] = {
    TransactionType.DEPOSIT: TransactionDirection.CREDIT,
    TransactionType.ORDER: TransactionDirection.DEBIT,
    TransactionType.REFUND: TransactionDirection.CREDIT,
    TransactionType.PARTIAL_REFUND: TransactionDirection.CREDIT,
    TransactionType.MANUAL_CREDIT: TransactionDirection.CREDIT,
    TransactionType.MANUAL_DEBIT: TransactionDirection.DEBIT,
    TransactionType.WITHDRAW: TransactionDirection.DEBIT,
    TransactionType.ADJUSTMENT: TransactionDirection.CREDIT,  # قد يكون debit — يحدده المنادي
}


class ServiceType(StrEnum):
    """نوع الخدمة — v1 ينفّذ default فقط، والبقية محجوزة للتوسعة."""

    DEFAULT = "default"
    CUSTOM_COMMENTS = "custom_comments"
    DRIP_FEED = "drip_feed"
    SUBSCRIPTION = "subscription"


class TicketStatus(StrEnum):
    """حالات تذكرة الدعم."""

    OPEN = "open"
    PENDING_ADMIN = "pending_admin"
    PENDING_USER = "pending_user"
    CLOSED = "closed"


class TicketPriority(StrEnum):
    """أولوية التذكرة."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class SenderType(StrEnum):
    """نوع مرسل رسالة الدعم."""

    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"


class NotificationStatus(StrEnum):
    """حالة الإشعار في صندوق الإرسال (Outbox)."""

    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"  # المستخدم حظر البوت مثلاً


class NotificationType(StrEnum):
    """أنواع الإشعارات المرسلة للمستخدم."""

    ORDER_CREATED = "order_created"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_IN_PROGRESS = "order_in_progress"
    ORDER_COMPLETED = "order_completed"
    ORDER_PARTIAL = "order_partial"
    ORDER_FAILED = "order_failed"
    ORDER_CANCELED = "order_canceled"
    ORDER_REFUNDED = "order_refunded"
    PAYMENT_RECEIVED = "payment_received"
    PAYMENT_APPROVED = "payment_approved"
    PAYMENT_REJECTED = "payment_rejected"
    BALANCE_CREDITED = "balance_credited"
    BALANCE_DEBITED = "balance_debited"
    TICKET_REPLIED = "ticket_replied"
    TICKET_CLOSED = "ticket_closed"
    BROADCAST = "broadcast"
    SYSTEM = "system"


class ActorType(StrEnum):
    """من نفّذ تغيير الحالة (يُسجَّل في order_status_history)."""

    SYSTEM = "system"
    JOB = "job"
    ADMIN = "admin"
    USER = "user"
    PROVIDER = "provider"


class BroadcastStatus(StrEnum):
    """حالة الرسالة الجماعية."""

    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RecipientStatus(StrEnum):
    """حالة مستلم واحد ضمن رسالة جماعية."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    BLOCKED = "blocked"


class PaymentMethodType(StrEnum):
    """نوع طريقة الدفع."""

    MANUAL = "manual"
    CRYPTO = "crypto"
    GATEWAY = "gateway"


class SettingType(StrEnum):
    """نوع قيمة الإعداد لتحويلها تلقائياً عند القراءة."""

    STR = "str"
    INT = "int"
    BOOL = "bool"
    JSON = "json"
    MONEY = "money"


class BackupType(StrEnum):
    """نوع النسخة الاحتياطية."""

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    PRE_OPERATION = "pre_operation"


class ProviderAction(StrEnum):
    """نوع الاستدعاء المُسجَّل في provider_requests."""

    ADD = "add"
    STATUS = "status"
    BALANCE = "balance"
    SERVICES = "services"
    CANCEL = "cancel"
    REFILL = "refill"


def values(enum_cls: type[StrEnum]) -> tuple[str, ...]:
    """إرجاع كل قيم التعداد كـ tuple نصي (يُستخدم في الاختبارات والتحقق)."""
    return tuple(member.value for member in enum_cls)
