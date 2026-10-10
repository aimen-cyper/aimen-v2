"""
آلة حالات الطلب (Order State Machine).

هذا الملف هو **المرجع الوحيد** لما هو مسموح وما هو ممنوع في انتقالات حالة الطلب.
لا يعتمد على قاعدة البيانات ولا على تيليجرام، لذلك يمكن اختباره مباشرة.

القاعدة الصارمة: أي انتقال غير مذكور في `ALLOWED_TRANSITIONS` يُرفض باستثناء
`InvalidStateTransitionError` — ولا يوجد أي مسار في النظام يغيّر حالة طلب دون المرور من هنا.
"""

from __future__ import annotations

from core.enums import OrderStatus
from core.exceptions import InvalidStateTransitionError

#: الحالات النهائية التي لا يجوز الانتقال منها إلى أي حالة أخرى
FINAL_STATUSES: frozenset[str] = frozenset(
    {
        OrderStatus.COMPLETED,
        OrderStatus.PARTIAL,
        OrderStatus.CANCELED,
        OrderStatus.REFUNDED,
    }
)

#: الحالات التي ما زال الطلب فيها حياً (تحتاج متابعة من النظام)
ACTIVE_STATUSES: frozenset[str] = frozenset(
    {
        OrderStatus.PENDING,
        OrderStatus.SUBMITTING,
        OrderStatus.SUBMIT_UNCERTAIN,
        OrderStatus.SUBMITTED,
        OrderStatus.IN_PROGRESS,
    }
)

#: الحالات التي تحتاج تدخلاً بشرياً (تُعرض للأدمن كتنبيه)
NEEDS_ATTENTION_STATUSES: frozenset[str] = frozenset({OrderStatus.SUBMIT_UNCERTAIN})

#: جدول الانتقالات المسموحة: من حالة → الحالات التي يجوز الانتقال إليها
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    OrderStatus.PENDING: frozenset(
        {OrderStatus.SUBMITTING, OrderStatus.CANCELED, OrderStatus.FAILED}
    ),
    OrderStatus.SUBMITTING: frozenset(
        {
            OrderStatus.SUBMITTED,
            OrderStatus.PENDING,           # فشل شبكي قبل الإرسال مع بقاء محاولات
            OrderStatus.SUBMIT_UNCERTAIN,  # مهلة/انقطاع بعد الإرسال
            OrderStatus.FAILED,
        }
    ),
    OrderStatus.SUBMIT_UNCERTAIN: frozenset({OrderStatus.SUBMITTED, OrderStatus.FAILED}),
    OrderStatus.SUBMITTED: frozenset(
        {
            OrderStatus.IN_PROGRESS,
            OrderStatus.COMPLETED,
            OrderStatus.PARTIAL,
            OrderStatus.CANCELED,
            OrderStatus.FAILED,
        }
    ),
    OrderStatus.IN_PROGRESS: frozenset(
        {OrderStatus.COMPLETED, OrderStatus.PARTIAL, OrderStatus.CANCELED, OrderStatus.FAILED}
    ),
    OrderStatus.FAILED: frozenset({OrderStatus.REFUNDED}),
    OrderStatus.CANCELED: frozenset({OrderStatus.REFUNDED}),
    OrderStatus.PARTIAL: frozenset(),
    OrderStatus.COMPLETED: frozenset(),
    OrderStatus.REFUNDED: frozenset(),
}

#: الحالات التي توجب استرجاعاً كاملاً للمبلغ فور الدخول إليها
REQUIRE_FULL_REFUND: frozenset[str] = frozenset({OrderStatus.FAILED, OrderStatus.CANCELED})

#: الحالة التي توجب استرجاعاً جزئياً بحسب المتبقي
REQUIRE_PARTIAL_REFUND: frozenset[str] = frozenset({OrderStatus.PARTIAL})

#: خريطة نصوص حالات المزود الشائعة → حالات النظام (تُقارن بحروف صغيرة بعد التنظيف)
PROVIDER_STATUS_MAP: dict[str, str] = {
    "pending": OrderStatus.SUBMITTED,
    "awaiting": OrderStatus.SUBMITTED,
    "queue": OrderStatus.SUBMITTED,
    "in queue": OrderStatus.SUBMITTED,
    "processing": OrderStatus.IN_PROGRESS,
    "in progress": OrderStatus.IN_PROGRESS,
    "inprogress": OrderStatus.IN_PROGRESS,
    "active": OrderStatus.IN_PROGRESS,
    "running": OrderStatus.IN_PROGRESS,
    "completed": OrderStatus.COMPLETED,
    "complete": OrderStatus.COMPLETED,
    "success": OrderStatus.COMPLETED,
    "partial": OrderStatus.PARTIAL,
    "canceled": OrderStatus.CANCELED,
    "cancelled": OrderStatus.CANCELED,
    "refunded": OrderStatus.CANCELED,  # المزود ردّ المبلغ ⇒ نعامله كإلغاء ثم نسترجع للمستخدم
    "error": OrderStatus.FAILED,
    "fail": OrderStatus.FAILED,
    "failed": OrderStatus.FAILED,
    "rejected": OrderStatus.FAILED,
}

#: الحالات العربية للعرض في الواجهة
STATUS_LABELS_AR: dict[str, str] = {
    OrderStatus.PENDING: "⏳ بانتظار الإرسال",
    OrderStatus.SUBMITTING: "📤 جاري الإرسال",
    OrderStatus.SUBMIT_UNCERTAIN: "❓ غير مؤكد (قيد المراجعة)",
    OrderStatus.SUBMITTED: "✅ أُرسل للمزود",
    OrderStatus.IN_PROGRESS: "🔄 قيد التنفيذ",
    OrderStatus.PARTIAL: "🟡 مكتمل جزئياً",
    OrderStatus.COMPLETED: "🎉 مكتمل",
    OrderStatus.CANCELED: "🚫 ملغي",
    OrderStatus.FAILED: "❌ فاشل",
    OrderStatus.REFUNDED: "💰 مسترجع",
}


def can_transition(from_status: str, to_status: str) -> bool:
    """
    هل يجوز الانتقال من حالة إلى أخرى؟

    ملاحظة: الانتقال إلى نفس الحالة مسموح دائماً ويُعامل كـ«لا تغيير» (no-op)
    لأن فحص الحالة الدوري قد يعيد نفس النتيجة.
    """
    if from_status == to_status:
        return True
    return to_status in ALLOWED_TRANSITIONS.get(from_status, frozenset())


def assert_transition(from_status: str, to_status: str, *, order_id: int | None = None) -> None:
    """
    التحقق من الانتقال ورفع استثناء واضح عند المخالفة.

    الاستثناءات:
        InvalidStateTransitionError : الانتقال غير مسموح في جدول الحالات.
    """
    if can_transition(from_status, to_status):
        return
    where = f" للطلب #{order_id}" if order_id else ""
    raise InvalidStateTransitionError(
        f"انتقال غير مسموح{where}: {from_status} ← {to_status}",
        user_message="⚠️ لا يمكن تنفيذ هذا الإجراء على الطلب في حالته الحالية.",
    )


def is_final(status: str) -> bool:
    """هل الطلب في حالة نهائية لا تقبل أي تغيير لاحق؟"""
    return status in FINAL_STATUSES


def is_active(status: str) -> bool:
    """هل الطلب ما زال يحتاج متابعة من النظام؟"""
    return status in ACTIVE_STATUSES


def allowed_next(status: str) -> frozenset[str]:
    """الحالات التي يمكن الانتقال إليها من الحالة الحالية."""
    return ALLOWED_TRANSITIONS.get(status, frozenset())


def sources_for(to_status: str) -> tuple[str, ...]:
    """
    الحالات التي يجوز أن يأتي منها هذا الانتقال.

    تُستخدم مباشرة كـ`expected_statuses` في تحديث الحالة المشروط داخل قاعدة البيانات،
    فيصبح منع السباق مضموناً من مصدر واحد بدل تكرار القوائم يدوياً في كل مكان.
    """
    return tuple(
        source for source, targets in ALLOWED_TRANSITIONS.items() if to_status in targets
    )


def requires_full_refund(to_status: str) -> bool:
    """هل الدخول إلى هذه الحالة يوجب استرجاع كامل المبلغ؟"""
    return to_status in REQUIRE_FULL_REFUND


def requires_partial_refund(to_status: str) -> bool:
    """هل الدخول إلى هذه الحالة يوجب استرجاعاً جزئياً؟"""
    return to_status in REQUIRE_PARTIAL_REFUND


def map_provider_status(raw_status: str | None) -> str | None:
    """
    تحويل نص حالة المزود إلى حالة النظام.

    المخرجات: حالة معروفة، أو None إذا كان النص غير معروف
              (المتصل مسؤول عن تسجيل تحذير وعدم تغيير الحالة).
    """
    if not raw_status:
        return None
    key = " ".join(str(raw_status).strip().lower().split())
    return PROVIDER_STATUS_MAP.get(key)


def label_ar(status: str) -> str:
    """الاسم العربي للحالة كما يُعرض للمستخدم."""
    return STATUS_LABELS_AR.get(status, status)


#: حالات ممنوع الوصول إليها بالتجاوز الإداري اليدوي (إرسال/مال): إعادة الطلب لحالات الإرسال قد تُرسله مرتين،
#: و«ملغى/مسترجع» حالتان ماليتان لهما أداتان مخصصتان (حركة مالية + استرجاع)
OVERRIDE_FORBIDDEN_TARGETS: frozenset[str] = frozenset(
    {
        OrderStatus.PENDING,
        OrderStatus.SUBMITTING,
        OrderStatus.SUBMIT_UNCERTAIN,
        OrderStatus.CANCELED,
        OrderStatus.REFUNDED,
    }
)

#: حالات تفترض أن للطلب رقماً عند المزود (لا معنى لها بدونه)
OVERRIDE_NEEDS_PROVIDER_ID: frozenset[str] = frozenset(
    {OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS, OrderStatus.COMPLETED, OrderStatus.PARTIAL}
)


def override_targets(status: str, *, has_provider_id: bool) -> list[str]:
    """
    الحالات التي يجوز التجاوز اليدوي إليها من حالة معينة (للأزرار والتحقق): آلة الحالات ∩ سياسة التجاوز.

    فارغة تعني أن التجاوز غير متاح (قيد الإرسال/غير مؤكد/نهائي). `submitting` و`submit_uncertain` لهما
    مساراتهما الخاصة («🔗 ربط رقم المزود» و«⛔ تعليم كفاشل + استرجاع»).
    """
    if status in (OrderStatus.SUBMITTING, OrderStatus.SUBMIT_UNCERTAIN):
        return []
    return sorted(
        target
        for target in allowed_next(status)
        if target not in OVERRIDE_FORBIDDEN_TARGETS
        and (target not in OVERRIDE_NEEDS_PROVIDER_ID or has_provider_id)
    )
