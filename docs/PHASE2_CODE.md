# الكود الكامل — المرحلة 2 (الخدمات الأساسية)

يجمع هذا الملف محتوى **كل** ملفات المرحلة 2 كما هي في المشروع، مرتبة حسب الطبقة.
الملفات نفسها داخل `smm_bot/` وهي المصدر الرسمي؛ هذا الملف للمراجعة والنسخ فقط.

ملفات المرحلة 1 (قاعدة البيانات والمستودعات) موجودة في `docs/PHASE1_CODE.md` ولم تتغير
في هذه المرحلة إلا في موضع واحد موثّق في التقرير (`database/repositories/orders.py`).

## الفهرس

- **آلات الحالات والثوابت — core/**
  - `core/order_state.py` — 198 سطر
  - `core/payment_state.py` — 83 سطر
  - `core/constants.py` — 44 سطر
- **الأدوات والنصوص**
  - `utils/validators.py` — 278 سطر
  - `texts/__init__.py` — 1 سطر
  - `texts/templates.py` — 257 سطر
- **طبقة المزودين — integrations/providers/**
  - `integrations/__init__.py` — 1 سطر
  - `integrations/providers/__init__.py` — 29 سطر
  - `integrations/providers/base.py` — 158 سطر
  - `integrations/providers/registry.py` — 62 سطر
  - `integrations/providers/mock.py` — 208 سطر
- **ترحيل إعدادات المرحلة 2**
  - `database/migrations/0004_phase2_settings.sql` — 13 سطر
- **طبقة الخدمات — services/**
  - `services/__init__.py` — 162 سطر
  - `services/settings_service.py` — 155 سطر
  - `services/audit_service.py` — 132 سطر
  - `services/auth_service.py` — 205 سطر
  - `services/user_service.py` — 274 سطر
  - `services/wallet_service.py` — 359 سطر
  - `services/notification_service.py` — 319 سطر
  - `services/catalog_service.py` — 285 سطر
  - `services/provider_service.py` — 477 سطر
  - `services/order_service.py` — 1324 سطر
  - `services/payment_service.py` — 676 سطر
  - `services/ticket_service.py` — 548 سطر
  - `services/stats_service.py` — 411 سطر
- **أدوات التشغيل — scripts/**
  - `scripts/demo_cycle.py` — 342 سطر
- **الاختبارات — tests/**
  - `tests/conftest.py` — 187 سطر
  - `tests/unit/test_order_state.py` — 157 سطر
  - `tests/unit/test_payment_state.py` — 82 سطر
  - `tests/unit/test_permission_catalog.py` — 64 سطر
  - `tests/unit/test_validators.py` — 197 سطر
  - `tests/integration/test_wallet_service.py` — 340 سطر
  - `tests/integration/test_auth_service.py` — 150 سطر
  - `tests/integration/test_catalog_service.py` — 143 سطر
  - `tests/integration/test_order_service.py` — 561 سطر
  - `tests/integration/test_payment_service.py` — 283 سطر
  - `tests/integration/test_ticket_service.py` — 226 سطر
  - `tests/integration/test_provider_service.py` — 176 سطر
  - `tests/integration/test_notification_service.py` — 187 سطر
  - `tests/integration/test_stats_service.py` — 201 سطر
  - `tests/e2e/test_full_cycle.py` — 327 سطر

**الإجمالي: 41 ملفاً / 10282 سطراً.**

---

# آلات الحالات والثوابت — core/

## `core/order_state.py`

```python
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
```

## `core/payment_state.py`

```python
"""
آلة حالات طلب الشحن (Payment State Machine).

طلب الشحن أبسط من الطلب: يبدأ `pending` ثم ينتهي إلى حالة نهائية واحدة لا رجعة فيها.
الهدف من الملف هو منع أي «اعتماد مزدوج» أو «رفض بعد الاعتماد» على مستوى المنطق،
إضافةً إلى الحماية الموجودة أصلاً في قاعدة البيانات.
"""

from __future__ import annotations

from core.enums import PaymentStatus
from core.exceptions import InvalidStateTransitionError

#: الحالات النهائية لطلب الشحن
FINAL_STATUSES: frozenset[str] = frozenset(
    {
        PaymentStatus.APPROVED,
        PaymentStatus.REJECTED,
        PaymentStatus.CANCELLED,
        PaymentStatus.EXPIRED,
    }
)

#: جدول الانتقالات المسموحة
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    PaymentStatus.PENDING: frozenset(
        {
            PaymentStatus.APPROVED,
            PaymentStatus.REJECTED,
            PaymentStatus.CANCELLED,
            PaymentStatus.EXPIRED,
        }
    ),
    PaymentStatus.APPROVED: frozenset(),
    PaymentStatus.REJECTED: frozenset(),
    PaymentStatus.CANCELLED: frozenset(),
    PaymentStatus.EXPIRED: frozenset(),
}

#: الحالة الوحيدة التي تُضيف رصيداً للمستخدم
CREDITING_STATUS: str = PaymentStatus.APPROVED

#: تسميات عربية للعرض
STATUS_LABELS_AR: dict[str, str] = {
    PaymentStatus.PENDING: "⏳ قيد المراجعة",
    PaymentStatus.APPROVED: "✅ معتمد",
    PaymentStatus.REJECTED: "❌ مرفوض",
    PaymentStatus.CANCELLED: "🚫 ملغي",
    PaymentStatus.EXPIRED: "⌛ منتهي الصلاحية",
}


def can_transition(from_status: str, to_status: str) -> bool:
    """هل يجوز نقل طلب الشحن من حالة إلى أخرى؟"""
    if from_status == to_status:
        return False  # طلب الشحن لا يُعاد تعيينه لنفس الحالة (يعني محاولة اعتماد مزدوج)
    return to_status in ALLOWED_TRANSITIONS.get(from_status, frozenset())


def assert_transition(from_status: str, to_status: str, *, payment_id: int | None = None) -> None:
    """
    التحقق من الانتقال ورفع استثناء واضح عند المخالفة.

    الاستثناءات:
        InvalidStateTransitionError : محاولة تعديل طلب شحن محسوم مسبقاً.
    """
    if can_transition(from_status, to_status):
        return
    where = f" لطلب الشحن #{payment_id}" if payment_id else ""
    raise InvalidStateTransitionError(
        f"انتقال غير مسموح{where}: {from_status} ← {to_status}",
        user_message="⚠️ تمت معالجة طلب الشحن هذا مسبقاً.",
    )


def is_final(status: str) -> bool:
    """هل حُسم طلب الشحن نهائياً؟"""
    return status in FINAL_STATUSES


def label_ar(status: str) -> str:
    """الاسم العربي لحالة طلب الشحن."""
    return STATUS_LABELS_AR.get(status, status)
```

## `core/constants.py`

```python
"""ثوابت عامة للنظام (قيم لا تتغير أثناء التشغيل)."""

from __future__ import annotations

#: اسم المشروع وإصداره
APP_NAME: str = "SMM Telegram Bot"
APP_VERSION: str = "0.3.0-phase2"

#: مدة قفل الطلب أثناء معالجته بواسطة job (بالثواني)
ORDER_LOCK_SECONDS: int = 120

#: أقصى عدد محاولات لإرسال الطلب إلى المزود عند الفشل الآمن (قبل اعتباره فاشلاً)
MAX_SUBMIT_ATTEMPTS: int = 3

#: أقصى عدد محاولات إرسال إشعار قبل اعتباره فاشلاً
MAX_NOTIFICATION_ATTEMPTS: int = 5

#: تدرج فترات إعادة فحص حالة الطلب (بالثواني)
ORDER_CHECK_BACKOFF: tuple[int, ...] = (60, 300, 900, 1800, 3600)

#: تدرج فترات إعادة إرسال الإشعار الفاشل (بالثواني)
NOTIFICATION_BACKOFF: tuple[int, ...] = (10, 60, 300, 1800, 3600)

#: مدة صلاحية مفاتيح منع التكرار الافتراضية (بالثواني)
IDEMPOTENCY_TTL_SECONDS: int = 24 * 3600

#: طول أقصى للنصوص المُخزَّنة من استجابات المزود (منعاً لتضخم قاعدة البيانات)
PROVIDER_RESPONSE_SNIPPET_LEN: int = 500

#: عدد العناصر في صفحة القوائم داخل تيليجرام
PAGE_SIZE: int = 8

#: صيغة مراجع الحركات المالية (تُستخدم لمنع التكرار)
REF_ORDER_DEBIT: str = "order:{order_id}"
REF_ORDER_REFUND: str = "refund:order:{order_id}"
REF_ORDER_PARTIAL_REFUND: str = "partial_refund:order:{order_id}"
REF_PAYMENT_DEPOSIT: str = "payment:{payment_id}"
REF_MANUAL: str = "manual:{kind}:{admin_id}:{token}"

#: صيغة مفاتيح منع تكرار الإشعارات
NOTIF_KEY_ORDER: str = "order:{order_id}:{event}"
NOTIF_KEY_PAYMENT: str = "payment:{payment_id}:{event}"
NOTIF_KEY_TICKET: str = "ticket:{ticket_id}:{event}"
NOTIF_KEY_MANUAL: str = "manual:{token}"
```

# الأدوات والنصوص

## `utils/validators.py`

```python
"""
التحقق من مدخلات المستخدم.

كل مُدخل قادم من تيليجرام يمر من هنا قبل أن يصل إلى طبقة الخدمات:
لا رابط بلا فحص، ولا كمية بلا حدود، ولا مبلغ بلا تحقق.
كل دالة إما تُرجع قيمة نظيفة جاهزة للتخزين أو ترفع استثناءً برسالة عربية واضحة.
"""

from __future__ import annotations

import re
from decimal import Decimal
from urllib.parse import urlparse

from core.exceptions import (
    InvalidAmountError,
    InvalidLinkError,
    QuantityOutOfRangeError,
    ValidationError,
)
from core.money import to_units

#: أقصى طول مقبول للرابط (حماية من إغراق قاعدة البيانات)
MAX_LINK_LENGTH: int = 500

#: أقصى طول لنص رسالة الدعم
MAX_MESSAGE_LENGTH: int = 2000

#: أقصى طول لعنوان التذكرة
MAX_SUBJECT_LENGTH: int = 100

#: أقصى طول لرقم الحوالة/المرجع
MAX_REFERENCE_LENGTH: int = 64

#: الأرقام العربية-الهندية وما يقابلها
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

#: صيغة مرجع الحوالة المسموحة (أرقام وحروف وشرطات فقط)
_REFERENCE_RE = re.compile(r"^[A-Za-z0-9\-_/.]{3,64}$")

#: صيغة اسم المستخدم في تيليجرام
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")


def normalize_digits(text: str) -> str:
    """تحويل الأرقام العربية-الهندية (٠١٢…) إلى أرقام لاتينية ليقبلها النظام."""
    return text.translate(_ARABIC_DIGITS)


def clean_text(value: str | None, *, field: str, max_length: int, min_length: int = 1) -> str:
    """
    تنظيف نص عام: إزالة الفراغات الزائدة والتحقق من الطول.

    الاستثناءات:
        ValidationError : النص فارغ أو أطول من المسموح.
    """
    text = " ".join((value or "").split())
    if len(text) < min_length:
        raise ValidationError(
            f"حقل {field} فارغ", user_message=f"❌ الرجاء إدخال {field}."
        )
    if len(text) > max_length:
        raise ValidationError(
            f"حقل {field} أطول من {max_length}",
            user_message=f"❌ {field} طويل جداً (الحد الأقصى {max_length} حرفاً).",
        )
    return text


def validate_link(link: str | None, *, pattern: str | None = None) -> str:
    """
    التحقق من رابط الطلب.

    المدخلات:
        link    : الرابط كما أدخله المستخدم.
        pattern : تعبير نمطي اختياري مرتبط بالخدمة (مثلاً روابط انستغرام فقط).

    المخرجات: الرابط بعد التنظيف.

    الاستثناءات:
        InvalidLinkError : رابط فارغ أو بلا بروتوكول صحيح أو لا يطابق نمط الخدمة.
    """
    text = (link or "").strip()
    if not text:
        raise InvalidLinkError("رابط فارغ", user_message="❌ الرجاء إرسال الرابط.")
    if len(text) > MAX_LINK_LENGTH:
        raise InvalidLinkError(
            "رابط طويل جداً", user_message="❌ الرابط طويل جداً، تأكد من نسخه بشكل صحيح."
        )
    if any(ch.isspace() for ch in text):
        raise InvalidLinkError(
            "الرابط يحتوي فراغات", user_message="❌ الرابط يحتوي مسافات — أرسل الرابط وحده."
        )

    parsed = urlparse(text if "://" in text else f"https://{text}")
    if parsed.scheme not in {"http", "https"}:
        raise InvalidLinkError(
            f"بروتوكول غير مدعوم: {parsed.scheme}",
            user_message="❌ الرابط يجب أن يبدأ بـ http أو https.",
        )
    host = (parsed.hostname or "").strip()
    if "." not in host or host.startswith(".") or host.endswith("."):
        raise InvalidLinkError(
            f"نطاق غير صالح: {host}", user_message="❌ الرابط غير صالح. تأكد منه وأعد الإرسال."
        )

    normalized = text if "://" in text else f"https://{text}"
    if pattern:
        try:
            matcher = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            # نمط الخدمة نفسه خاطئ: لا نُسقط طلب المستخدم بسببه، بل نُبلغ كخطأ إعداد
            raise ValidationError(
                f"نمط رابط غير صالح في إعداد الخدمة: {pattern} ({exc})",
                user_message="⚠️ إعداد هذه الخدمة غير مكتمل. أبلغ الدعم من فضلك.",
            ) from exc
        if not matcher.search(normalized):
            raise InvalidLinkError(
                "الرابط لا يطابق نمط الخدمة",
                user_message="❌ هذا الرابط لا يناسب هذه الخدمة. تأكد من المنصة المطلوبة.",
            )
    return normalized


def validate_quantity(raw_quantity: str | int, *, min_quantity: int, max_quantity: int) -> int:
    """
    التحقق من الكمية المطلوبة ضمن حدود الخدمة.

    الاستثناءات:
        QuantityOutOfRangeError : الكمية ليست رقماً صحيحاً أو خارج الحدود.
    """
    if isinstance(raw_quantity, bool):  # bool نوع فرعي من int — نمنعه صراحة
        raise QuantityOutOfRangeError("قيمة كمية غير صالحة")
    if isinstance(raw_quantity, int):
        quantity = raw_quantity
    else:
        text = normalize_digits(str(raw_quantity)).strip().replace(",", "")
        if not text.isdigit():
            raise QuantityOutOfRangeError(
                f"كمية غير رقمية: {raw_quantity}", user_message="❌ أرسل الكمية كرقم صحيح فقط."
            )
        quantity = int(text)

    if quantity < min_quantity or quantity > max_quantity:
        raise QuantityOutOfRangeError(
            f"الكمية {quantity} خارج [{min_quantity}, {max_quantity}]",
            user_message=(
                f"❌ الكمية يجب أن تكون بين {min_quantity:,} و {max_quantity:,}."
            ),
        )
    return quantity


def parse_amount_units(raw_amount: str | int | Decimal) -> int:
    """
    تحويل مبلغ مُدخل من المستخدم إلى وحدات صحيحة للتخزين.

    يقبل: "1500" · "1,500.50" · "١٥٠٠" · Decimal.

    الاستثناءات:
        InvalidAmountError : نص غير رقمي أو مبلغ صفر/سالب.
    """
    if isinstance(raw_amount, str):
        cleaned = normalize_digits(raw_amount).replace(",", "").replace("٫", ".").strip()
    else:
        cleaned = raw_amount
    try:
        units = to_units(cleaned)
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise InvalidAmountError(
            f"مبلغ غير صالح: {raw_amount!r}", user_message="❌ أرسل المبلغ كرقم صحيح."
        ) from exc
    if units <= 0:
        raise InvalidAmountError(
            f"مبلغ غير موجب: {raw_amount!r}", user_message="❌ المبلغ يجب أن يكون أكبر من صفر."
        )
    return units


def validate_amount_range(
    amount_units: int, *, min_units: int = 0, max_units: int | None = None, label: str = "المبلغ"
) -> int:
    """
    التحقق من أن المبلغ ضمن الحد الأدنى والأقصى المسموحين.

    الاستثناءات:
        InvalidAmountError : خارج الحدود، مع رسالة توضّح الحدود للمستخدم.
    """
    from core.money import format_units  # استيراد داخلي لتفادي الاعتماد الدائري عند الإقلاع

    if min_units and amount_units < min_units:
        raise InvalidAmountError(
            f"{label} أقل من الحد الأدنى",
            user_message=f"❌ الحد الأدنى {format_units(min_units)}.",
        )
    if max_units is not None and max_units > 0 and amount_units > max_units:
        raise InvalidAmountError(
            f"{label} أكبر من الحد الأقصى",
            user_message=f"❌ الحد الأقصى {format_units(max_units)}.",
        )
    return amount_units


def validate_transaction_reference(reference: str | None, *, required: bool = True) -> str | None:
    """
    التحقق من رقم الحوالة الذي يكتبه المستخدم عند الشحن.

    الاستثناءات:
        ValidationError : مرجع مطلوب وغير موجود، أو يحتوي رموزاً غير مسموحة.
    """
    text = normalize_digits((reference or "").strip())
    if not text:
        if required:
            raise ValidationError(
                "رقم الحوالة مطلوب", user_message="❌ الرجاء إرسال رقم عملية التحويل."
            )
        return None
    if not _REFERENCE_RE.match(text):
        raise ValidationError(
            f"مرجع غير صالح: {text!r}",
            user_message="❌ رقم العملية غير صالح (أرقام وحروف إنجليزية فقط، 3 محارف على الأقل).",
        )
    return text[:MAX_REFERENCE_LENGTH]


def validate_telegram_id(raw_id: str | int) -> int:
    """
    التحقق من معرف تيليجرام رقمي.

    الاستثناءات:
        ValidationError : قيمة غير رقمية أو خارج المدى المنطقي.
    """
    text = normalize_digits(str(raw_id)).strip()
    if not text.lstrip("-").isdigit():
        raise ValidationError(
            f"معرف تيليجرام غير رقمي: {raw_id!r}", user_message="❌ أرسل معرف تيليجرام كرقم."
        )
    value = int(text)
    if value <= 0 or value > 10**13:
        raise ValidationError(
            f"معرف تيليجرام خارج المدى: {value}", user_message="❌ معرف تيليجرام غير صالح."
        )
    return value


def normalize_username(username: str | None) -> str | None:
    """تنظيف اسم المستخدم (إزالة @) وإرجاع None إن كان غير صالح."""
    if not username:
        return None
    text = username.strip().lstrip("@")
    return text if _USERNAME_RE.match(text) else None


def validate_subject(subject: str | None) -> str:
    """التحقق من عنوان تذكرة الدعم."""
    return clean_text(subject, field="عنوان التذكرة", max_length=MAX_SUBJECT_LENGTH, min_length=3)


def validate_message(message: str | None) -> str:
    """التحقق من نص رسالة الدعم."""
    return clean_text(message, field="نص الرسالة", max_length=MAX_MESSAGE_LENGTH, min_length=2)


def validate_url(url: str | None, *, field: str = "رابط API") -> str:
    """
    التحقق من رابط إداري (مثل رابط API للمزود).

    الاستثناءات:
        ValidationError : الرابط فارغ أو بلا بروتوكول http/https.
    """
    text = (url or "").strip()
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValidationError(
            f"{field} غير صالح: {text!r}",
            user_message=f"❌ {field} يجب أن يبدأ بـ https:// ويحتوي نطاقاً صحيحاً.",
        )
    return text
```

## `texts/__init__.py`

```python
"""النصوص العربية المركزية (قوالب الإشعارات ونصوص الواجهة)."""
```

## `texts/templates.py`

```python
"""
قوالب نصوص الإشعارات العربية.

كل نص يصل إلى المستخدم أو الأدمن مكتوب هنا في مكان واحد — لا نصوص متناثرة داخل الخدمات.
كل دالة تُرجع زوجاً: (العنوان، النص) جاهزاً للإرسال عبر تيليجرام.
"""

from __future__ import annotations

from core.money import format_units
from core.order_state import label_ar as order_label

#: الرمز الافتراضي للعملة عند عدم تمريره (تُقرأ القيمة الحقيقية من الإعدادات)
DEFAULT_SYMBOL = ""


def money(units: int, symbol: str = DEFAULT_SYMBOL, decimals: int = 2) -> str:
    """تنسيق مبلغ للعرض داخل نصوص الإشعارات."""
    return format_units(units, symbol=symbol, decimals=decimals)


# --------------------------------- الطلبات --------------------------------- #


def order_created(*, code: str, service_name: str, quantity: int, cost_units: int, symbol: str = "") -> tuple[str, str]:
    """إشعار إنشاء الطلب وخصم قيمته."""
    return (
        "🧾 تم استلام طلبك",
        f"تم إنشاء الطلب {code} بنجاح.\n\n"
        f"🛒 الخدمة: {service_name}\n"
        f"🔢 الكمية: {quantity:,}\n"
        f"💵 المبلغ المخصوم: {money(cost_units, symbol)}\n\n"
        f"سيبدأ التنفيذ خلال دقائق، وسنعلمك بكل تحديث.",
    )


def order_submitted(*, code: str, service_name: str) -> tuple[str, str]:
    """إشعار قبول المزود للطلب."""
    return (
        "📤 تم إرسال طلبك للتنفيذ",
        f"الطلب {code} ({service_name}) أصبح لدى المزود وبدأ دوره في التنفيذ.",
    )


def order_in_progress(*, code: str) -> tuple[str, str]:
    """إشعار بدء التنفيذ الفعلي."""
    return ("🔄 طلبك قيد التنفيذ", f"بدأ تنفيذ الطلب {code} الآن.")


def order_completed(*, code: str, service_name: str, quantity: int) -> tuple[str, str]:
    """إشعار اكتمال الطلب."""
    return (
        "🎉 اكتمل طلبك",
        f"تم تنفيذ الطلب {code} بالكامل.\n\n"
        f"🛒 الخدمة: {service_name}\n"
        f"🔢 الكمية: {quantity:,}\n\n"
        f"شكراً لثقتك 🌟",
    )


def order_partial(*, code: str, delivered: int, quantity: int, refund_units: int, symbol: str = "") -> tuple[str, str]:
    """إشعار التنفيذ الجزئي مع الاسترجاع."""
    return (
        "🟡 تم تنفيذ طلبك جزئياً",
        f"الطلب {code} نُفِّذ جزئياً.\n\n"
        f"✅ المنفَّذ: {delivered:,} من {quantity:,}\n"
        f"💰 أُعيد إلى رصيدك: {money(refund_units, symbol)}\n\n"
        f"المبلغ المسترجع متاح في محفظتك الآن.",
    )


def order_failed(*, code: str, reason: str, refund_units: int, symbol: str = "") -> tuple[str, str]:
    """إشعار فشل الطلب مع الاسترجاع الكامل."""
    return (
        "❌ تعذّر تنفيذ طلبك",
        f"الطلب {code} لم يُنفَّذ.\n\n"
        f"📝 السبب: {reason}\n"
        f"💰 أُعيد كامل المبلغ إلى رصيدك: {money(refund_units, symbol)}\n\n"
        f"يمكنك المحاولة مرة أخرى أو التواصل مع الدعم.",
    )


def order_canceled(*, code: str, refund_units: int, symbol: str = "") -> tuple[str, str]:
    """إشعار إلغاء الطلب مع الاسترجاع."""
    return (
        "🚫 تم إلغاء طلبك",
        f"أُلغي الطلب {code}.\n💰 أُعيد المبلغ إلى رصيدك: {money(refund_units, symbol)}",
    )


def order_refunded(*, code: str, refund_units: int, symbol: str = "") -> tuple[str, str]:
    """إشعار إتمام الاسترجاع."""
    return (
        "💰 تم استرجاع مبلغ طلبك",
        f"أُضيف مبلغ {money(refund_units, symbol)} إلى رصيدك بخصوص الطلب {code}.",
    )


def order_status_changed(*, code: str, status: str) -> tuple[str, str]:
    """إشعار عام بتغيّر حالة الطلب (يُستخدم للحالات غير المذكورة أعلاه)."""
    return ("ℹ️ تحديث على طلبك", f"الطلب {code}: {order_label(status)}")


# -------------------------------- المدفوعات -------------------------------- #


def payment_received(*, payment_id: int, amount_units: int, symbol: str = "") -> tuple[str, str]:
    """إشعار استلام طلب الشحن (قيد المراجعة)."""
    return (
        "📥 تم استلام طلب الشحن",
        f"طلب الشحن #{payment_id} بمبلغ {money(amount_units, symbol)} قيد المراجعة.\n"
        f"سنعلمك فور اعتماده.",
    )


def payment_approved(*, payment_id: int, credited_units: int, new_balance_units: int, symbol: str = "") -> tuple[str, str]:
    """إشعار اعتماد الشحن وإضافة الرصيد."""
    return (
        "✅ تم اعتماد شحن رصيدك",
        f"طلب الشحن #{payment_id} اعتُمد.\n\n"
        f"💵 المبلغ المضاف: {money(credited_units, symbol)}\n"
        f"👛 رصيدك الآن: {money(new_balance_units, symbol)}",
    )


def payment_rejected(*, payment_id: int, reason: str) -> tuple[str, str]:
    """إشعار رفض طلب الشحن."""
    return (
        "❌ تم رفض طلب الشحن",
        f"طلب الشحن #{payment_id} مرفوض.\n📝 السبب: {reason}\n\n"
        f"إن كنت ترى أن هذا خطأ، تواصل مع الدعم.",
    )


def payment_expired(*, payment_id: int) -> tuple[str, str]:
    """إشعار انتهاء صلاحية طلب الشحن."""
    return (
        "⌛ انتهت صلاحية طلب الشحن",
        f"طلب الشحن #{payment_id} انتهت مهلته دون مراجعة. يمكنك إنشاء طلب جديد.",
    )


# --------------------------------- الرصيد ---------------------------------- #


def balance_credited(*, amount_units: int, new_balance_units: int, reason: str, symbol: str = "") -> tuple[str, str]:
    """إشعار إضافة رصيد يدوية من الإدارة."""
    return (
        "💰 تمت إضافة رصيد",
        f"أضافت الإدارة {money(amount_units, symbol)} إلى رصيدك.\n"
        f"📝 السبب: {reason}\n👛 رصيدك الآن: {money(new_balance_units, symbol)}",
    )


def balance_debited(*, amount_units: int, new_balance_units: int, reason: str, symbol: str = "") -> tuple[str, str]:
    """إشعار خصم رصيد يدوي من الإدارة."""
    return (
        "➖ تم خصم رصيد",
        f"خصمت الإدارة {money(amount_units, symbol)} من رصيدك.\n"
        f"📝 السبب: {reason}\n👛 رصيدك الآن: {money(new_balance_units, symbol)}",
    )


# ---------------------------------- الدعم ---------------------------------- #


def ticket_replied(*, ticket_id: int, preview: str) -> tuple[str, str]:
    """إشعار وصول رد من الدعم."""
    return (
        "💬 رد جديد من الدعم",
        f"لديك رد على التذكرة #{ticket_id}:\n\n«{preview}»",
    )


def ticket_closed(*, ticket_id: int, reason: str) -> tuple[str, str]:
    """إشعار إغلاق التذكرة."""
    body = f"تم إغلاق التذكرة #{ticket_id}."
    if reason:
        body += f"\n📝 {reason}"
    return ("✅ تم إغلاق تذكرتك", body)


# -------------------------------- الحسابات --------------------------------- #


def account_banned(*, reason: str) -> tuple[str, str]:
    """إشعار حظر الحساب."""
    return ("🚫 تم حظر حسابك", f"تم إيقاف حسابك عن استخدام البوت.\n📝 السبب: {reason}")


def account_unbanned() -> tuple[str, str]:
    """إشعار رفع الحظر."""
    return ("✅ تم رفع الحظر", "أصبح بإمكانك استخدام البوت مجدداً. نتمنى لك تجربة طيبة.")


# ---------------------------- تنبيهات الإدارة ------------------------------ #


def admin_order_uncertain(*, code: str, order_id: int, error: str) -> tuple[str, str]:
    """تنبيه أدمن: نتيجة إرسال غير مؤكدة تحتاج قراراً بشرياً."""
    return (
        "❗ طلب بحالة غير مؤكدة",
        f"الطلب {code} (#{order_id}) انقطع أثناء الإرسال ولا نعرف هل وصل للمزود.\n"
        f"📝 التفاصيل: {error}\n\n"
        f"المطلوب: تحقق من لوحة المزود ثم اربط رقم الطلب أو أكّد الفشل ليُسترجع المبلغ.",
    )


def admin_order_failed(*, code: str, order_id: int, reason: str, refund_units: int, symbol: str = "") -> tuple[str, str]:
    """تنبيه أدمن: فشل طلب واسترجاع مبلغه."""
    return (
        "❌ فشل طلب واسترجاع تلقائي",
        f"الطلب {code} (#{order_id}) فشل.\n📝 السبب: {reason}\n"
        f"💰 المبلغ المسترجع: {money(refund_units, symbol)}",
    )


def admin_provider_disabled(*, provider_name: str, failures: int, minutes: int) -> tuple[str, str]:
    """تنبيه أدمن: تعطيل مؤقت لمزود بعد أخطاء متتالية."""
    return (
        "🔌 تعطيل مؤقت لمزود",
        f"المزود «{provider_name}» توقف مؤقتاً بعد {failures} أخطاء متتالية.\n"
        f"⏱ سيُعاد تفعيله تلقائياً بعد {minutes} دقيقة.",
    )


def admin_provider_low_balance(*, provider_name: str, balance_units: int, symbol: str = "") -> tuple[str, str]:
    """تنبيه أدمن: رصيد المزود قارب على النفاد."""
    return (
        "⚠️ رصيد مزود منخفض",
        f"رصيد حسابنا لدى «{provider_name}» أصبح {money(balance_units, symbol)}.\n"
        f"اشحن الحساب قبل توقف الطلبات.",
    )


def admin_new_payment(*, payment_id: int, amount_units: int, user_label: str, symbol: str = "") -> tuple[str, str]:
    """تنبيه أدمن: طلب شحن جديد بانتظار المراجعة."""
    return (
        "📥 طلب شحن جديد",
        f"طلب شحن #{payment_id} من {user_label} بمبلغ {money(amount_units, symbol)} ينتظر المراجعة.",
    )


def admin_new_ticket(*, ticket_id: int, subject: str, user_label: str) -> tuple[str, str]:
    """تنبيه أدمن: تذكرة دعم جديدة."""
    return (
        "🎫 تذكرة دعم جديدة",
        f"التذكرة #{ticket_id} من {user_label}\n📌 الموضوع: {subject}",
    )


def admin_stuck_orders(*, count: int, hours: int) -> tuple[str, str]:
    """تنبيه أدمن: طلبات متوقفة بلا تقدم."""
    return (
        "⏰ طلبات متوقفة",
        f"يوجد {count} طلب لم يتقدم منذ أكثر من {hours} ساعة. راجعها في لوحة الطلبات.",
    )
```

# طبقة المزودين — integrations/providers/

## `integrations/__init__.py`

```python
"""حزمة التكاملات الخارجية (مزودو الخدمات وبوابات الدفع)."""
```

## `integrations/providers/__init__.py`

```python
"""عملاء مزودي خدمات SMM."""

from integrations.providers.base import (
    ProviderBalance,
    ProviderClient,
    ProviderOrderResult,
    ProviderServiceItem,
    ProviderStatusResult,
)
from integrations.providers.mock import MockProviderClient
from integrations.providers.registry import (
    available_types,
    create_client,
    is_supported,
    register_client,
)

__all__ = [
    "ProviderBalance",
    "ProviderClient",
    "ProviderOrderResult",
    "ProviderServiceItem",
    "ProviderStatusResult",
    "MockProviderClient",
    "available_types",
    "create_client",
    "is_supported",
    "register_client",
]
```

## `integrations/providers/base.py`

```python
"""
الواجهة المجردة لمزودي الخدمات (Provider Client).

الفكرة: بقية النظام لا يعرف شيئاً عن شكل API أي مزود — يتعامل فقط مع هذه الواجهة
وأنواع البيانات المعرَّفة هنا. إضافة مزود بمعيار مختلف = ملف جديد يطبّق `ProviderClient`
دون لمس أي سطر في الخدمات أو الواجهة.

تصنيف الأخطاء (مهم جداً لسلامة المال):
    • ProviderTemporaryError        → آمن لإعادة المحاولة (شبكة/حد معدل).
    • ProviderInsufficientFundsError → مؤقت كذلك، لكن سببه رصيدنا لدى المزود.
    • ProviderPermanentError        → لا فائدة من إعادة المحاولة (رفض صريح) ⇒ فشل + استرجاع.
    • ProviderUncertainError        → لا نعرف هل وصل الطلب ⇒ ممنوع إعادة الإرسال آلياً.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.money import MONEY_SCALE


@dataclass(frozen=True, slots=True)
class ProviderOrderResult:
    """نتيجة إنشاء طلب عند المزود."""

    provider_order_id: str          # رقم الطلب عند المزود (لا يكون فارغاً أبداً)
    charge_units: int | None = None  # ما خصمه المزود منا (بوحدات المال) إن أرسله
    currency: str = "USD"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderStatusResult:
    """نتيجة الاستعلام عن حالة طلب لدى المزود."""

    raw_status: str                  # نص الحالة كما ورد من المزود
    start_count: int | None = None   # العدد قبل البدء
    remains: int | None = None       # المتبقي
    delivered: int | None = None     # المنفَّذ فعلياً (إن أرسله المزود)
    charge_units: int | None = None
    currency: str = "USD"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderBalance:
    """رصيد حسابنا لدى المزود."""

    amount_units: int
    currency: str = "USD"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderServiceItem:
    """خدمة واحدة كما يعرضها المزود (تُستخدم في الاستيراد والمزامنة)."""

    provider_service_id: str
    name: str
    rate_per_1000_units: int          # سعر المزود بوحدات المال
    min_quantity: int
    max_quantity: int
    category: str = ""
    service_type: str = "default"
    dripfeed: bool = False
    refill: bool = False
    cancel: bool = False
    currency: str = "USD"
    raw: dict[str, Any] = field(default_factory=dict)


class ProviderClient(ABC):
    """
    الواجهة التي يجب أن يطبّقها كل عميل مزود.

    ملاحظات للمطوّر:
        • كل الدوال غير متزامنة ولا تفتح أي معاملة قاعدة بيانات.
        • ممنوع أن يُرجع أي عميل مفتاح API أو يضعه في نص خطأ — استخدم `secrets()`
          لتمرير القيم الحساسة إلى أداة التنقية قبل أي تسجيل.
    """

    #: المعرّف النصي لنوع المزود (يطابق عمود providers.api_type)
    api_type: str = "base"

    def __init__(self, *, api_url: str, api_key: str, timeout_seconds: int = 30) -> None:
        """تهيئة العميل ببيانات الاتصال (المفتاح يبقى داخل الكائن ولا يُسجَّل)."""
        self.api_url = api_url
        self._api_key = api_key
        self.timeout_seconds = timeout_seconds

    def secrets(self) -> tuple[str, ...]:
        """القيم السرية التي يجب حذفها من أي نص قبل تسجيله (تُمرَّر إلى sanitize)."""
        return (self._api_key,) if self._api_key else ()

    @abstractmethod
    async def add_order(
        self, *, provider_service_id: str, link: str, quantity: int, extras: dict[str, Any] | None = None
    ) -> ProviderOrderResult:
        """إنشاء طلب جديد عند المزود وإرجاع رقمه."""

    @abstractmethod
    async def get_order_status(self, provider_order_id: str) -> ProviderStatusResult:
        """الاستعلام عن حالة طلب واحد."""

    @abstractmethod
    async def get_balance(self) -> ProviderBalance:
        """قراءة رصيد حسابنا لدى المزود."""

    @abstractmethod
    async def get_services(self) -> list[ProviderServiceItem]:
        """جلب قائمة خدمات المزود (للاستيراد والمزامنة)."""

    async def get_multi_status(self, provider_order_ids: list[str]) -> dict[str, ProviderStatusResult]:
        """
        الاستعلام عن عدة طلبات دفعة واحدة.

        التطبيق الافتراضي يستدعي `get_order_status` لكل طلب؛ المزود الذي يدعم
        الاستعلام الجماعي يعيد تعريف هذه الدالة لتوفير الاستدعاءات.
        """
        results: dict[str, ProviderStatusResult] = {}
        for provider_order_id in provider_order_ids:
            results[provider_order_id] = await self.get_order_status(provider_order_id)
        return results

    async def cancel_order(self, provider_order_id: str) -> bool:
        """
        طلب إلغاء لدى المزود.

        المخرجات: False افتراضياً لأن أغلب اللوحات لا تدعم الإلغاء —
                  المزود الذي يدعمه يعيد تعريف الدالة.
        """
        return False

    async def refill_order(self, provider_order_id: str) -> bool:
        """طلب إعادة تعبئة (refill) — غير مدعوم افتراضياً."""
        return False

    async def close(self) -> None:
        """إغلاق أي موارد شبكة مفتوحة (اتصالات/جلسات). افتراضياً لا شيء."""
        return None

    def money_from_decimal_text(self, text: str | float | int | None) -> int | None:
        """
        تحويل مبلغ نصي من المزود (مثل "1.2345") إلى وحدات صحيحة.

        المخرجات: عدد الوحدات، أو None إذا كانت القيمة غير قابلة للتحويل
                  (لا نُسقط العملية بسبب حقل تكلفة غير مفهوم).
        """
        if text is None or text == "":
            return None
        try:
            from decimal import Decimal

            return int((Decimal(str(text)) * MONEY_SCALE).to_integral_value())
        except (ArithmeticError, ValueError, TypeError):
            return None
```

## `integrations/providers/registry.py`

```python
"""
سجل عملاء المزودين: تحويل `api_type` المخزَّن في قاعدة البيانات إلى عميل فعلي.

الفائدة: إضافة معيار API جديد = تسجيل صنف جديد هنا فقط، دون تعديل أي خدمة.
"""

from __future__ import annotations

from typing import Callable

from core.exceptions import ProviderError
from integrations.providers.base import ProviderClient
from integrations.providers.mock import MockProviderClient

#: نوع الدالة المُنشئة لعميل مزود
ClientFactory = Callable[..., ProviderClient]

#: الأنواع المسجَّلة فعلياً والجاهزة للاستخدام
_REGISTRY: dict[str, ClientFactory] = {
    MockProviderClient.api_type: MockProviderClient,
}

#: أنواع مخطط لها لكنها لم تُنفَّذ بعد — نرفضها برسالة صريحة بدل تنفيذ صوري فارغ
_PLANNED: dict[str, str] = {
    "perfect_panel": "عميل perfect_panel يُنفَّذ في المرحلة 5 (ربط APIs الحقيقية).",
}


def register_client(api_type: str, factory: ClientFactory) -> None:
    """تسجيل عميل مزود جديد تحت نوع محدد (يُستدعى عند إضافة معيار API جديد)."""
    _REGISTRY[api_type] = factory


def available_types() -> tuple[str, ...]:
    """أنواع المزودين الجاهزة للاستخدام الآن."""
    return tuple(sorted(_REGISTRY))


def is_supported(api_type: str) -> bool:
    """هل هذا النوع مدعوم فعلياً (وليس مجرد مخطط له)؟"""
    return api_type in _REGISTRY


def create_client(
    *, api_type: str, api_url: str, api_key: str, timeout_seconds: int = 30
) -> ProviderClient:
    """
    إنشاء عميل مزود من نوعه المخزَّن في قاعدة البيانات.

    الاستثناءات:
        ProviderError : نوع غير معروف، أو نوع مخطط له ولم يُنفَّذ بعد.
    """
    factory = _REGISTRY.get(api_type)
    if factory is None:
        planned = _PLANNED.get(api_type)
        if planned:
            raise ProviderError(planned, user_message="⚠️ هذا المزود غير مفعّل بعد.")
        raise ProviderError(
            f"نوع مزود غير معروف: {api_type}. الأنواع المتاحة: {', '.join(available_types())}",
            user_message="⚠️ إعداد المزود غير صحيح. راجع لوحة التحكم.",
        )
    return factory(api_url=api_url, api_key=api_key, timeout_seconds=timeout_seconds)
```

## `integrations/providers/mock.py`

```python
"""
مزود وهمي للاختبار والتطوير — ⚠️ لا يتصل بأي شبكة ولا ينفق أي مال حقيقي.

الغرض منه واحد فقط: تشغيل الدورة الكاملة (إرسال → متابعة → إكمال/فشل) في الاختبارات
وفي بيئة التطوير دون الحاجة إلى حساب حقيقي لدى مزود.

مصرَّح به في `registry` باسم النوع `mock` فقط، ولا يُستخدم في الإنتاج:
أي مزود حقيقي يجب أن يكون `api_type = 'perfect_panel'` (يُنفَّذ في المرحلة 5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.exceptions import (
    ProviderInsufficientFundsError,
    ProviderPermanentError,
    ProviderTemporaryError,
    ProviderUncertainError,
)
from core.money import MONEY_SCALE
from integrations.providers.base import (
    ProviderBalance,
    ProviderClient,
    ProviderOrderResult,
    ProviderServiceItem,
    ProviderStatusResult,
)


@dataclass
class MockOrderState:
    """حالة طلب وهمي داخل المزود الاختباري."""

    provider_order_id: str
    quantity: int
    delivered: int = 0
    status: str = "Pending"
    charge_units: int = 0
    raw_extras: dict[str, Any] = field(default_factory=dict)


class MockProviderClient(ProviderClient):
    """
    مزود اختباري قابل للبرمجة بالكامل.

    أمثلة الاستخدام في الاختبارات:
        client = MockProviderClient()                       # يعمل بشكل طبيعي
        client.fail_next_add = ProviderPermanentError(...)  # يرفض الطلب القادم
        client.advance("1001", to="Completed")              # يقفز بالطلب إلى الاكتمال
    """

    api_type = "mock"

    def __init__(
        self,
        *,
        api_url: str = "https://mock.invalid/api/v2",
        api_key: str = "mock-key",
        timeout_seconds: int = 5,
        balance_units: int = 1_000 * MONEY_SCALE,
        rate_per_1000_units: int = 6_000,
    ) -> None:
        """تهيئة المزود الوهمي برصيد وسعر افتراضيين."""
        super().__init__(api_url=api_url, api_key=api_key, timeout_seconds=timeout_seconds)
        self.balance_units = balance_units
        self.rate_per_1000_units = rate_per_1000_units
        self.orders: dict[str, MockOrderState] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []   # سجل الاستدعاءات للتحقق في الاختبارات
        self._next_id = 1000

        #: استثناء يُرفع عند أول استدعاء لـadd_order ثم يُصفَّر (لمحاكاة فشل مؤقت)
        self.fail_next_add: Exception | None = None
        #: استثناء دائم يُرفع في كل استدعاء لـadd_order
        self.always_fail_add: Exception | None = None
        #: استثناء يُرفع عند أول استعلام حالة ثم يُصفَّر
        self.fail_next_status: Exception | None = None
        #: استثناء يُرفع عند أول فحص رصيد ثم يُصفَّر (لاختبار تعطيل المزود)
        self.fail_next_balance: Exception | None = None
        #: عدد الوحدات التي يسلّمها المزود في كل فحص حالة (محاكاة التقدم)
        self.delivery_step_ratio: float = 0.5
        #: هل ينهي الطلب تلقائياً عند اكتمال التسليم؟
        self.auto_complete: bool = True

    # ------------------------------ الطلبات ------------------------------ #

    async def add_order(
        self, *, provider_service_id: str, link: str, quantity: int, extras: dict[str, Any] | None = None
    ) -> ProviderOrderResult:
        """إنشاء طلب وهمي، أو رفع الاستثناء المبرمَج مسبقاً لمحاكاة الفشل."""
        self.calls.append(("add", {"service": provider_service_id, "link": link, "quantity": quantity}))

        if self.always_fail_add is not None:
            raise self.always_fail_add
        if self.fail_next_add is not None:
            error, self.fail_next_add = self.fail_next_add, None
            raise error

        charge_units = (self.rate_per_1000_units * quantity + 500) // 1000
        if charge_units > self.balance_units:
            raise ProviderInsufficientFundsError(
                "رصيد الحساب لدى المزود الوهمي غير كافٍ لتنفيذ الطلب."
            )

        self._next_id += 1
        provider_order_id = str(self._next_id)
        self.balance_units -= charge_units
        self.orders[provider_order_id] = MockOrderState(
            provider_order_id=provider_order_id,
            quantity=quantity,
            charge_units=charge_units,
            raw_extras=dict(extras or {}),
        )
        return ProviderOrderResult(
            provider_order_id=provider_order_id,
            charge_units=charge_units,
            raw={"order": provider_order_id},
        )

    async def get_order_status(self, provider_order_id: str) -> ProviderStatusResult:
        """إرجاع حالة الطلب الوهمي مع تقديم التنفيذ خطوة في كل استعلام."""
        self.calls.append(("status", {"order": provider_order_id}))

        if self.fail_next_status is not None:
            error, self.fail_next_status = self.fail_next_status, None
            raise error

        state = self.orders.get(provider_order_id)
        if state is None:
            raise ProviderPermanentError(f"الطلب {provider_order_id} غير موجود لدى المزود.")

        if state.status in {"Pending", "In progress"} and self.auto_complete:
            step = max(1, int(state.quantity * self.delivery_step_ratio))
            state.delivered = min(state.quantity, state.delivered + step)
            state.status = "Completed" if state.delivered >= state.quantity else "In progress"

        return ProviderStatusResult(
            raw_status=state.status,
            start_count=0,
            remains=max(0, state.quantity - state.delivered),
            delivered=state.delivered,
            charge_units=state.charge_units,
            raw={"status": state.status, "remains": state.quantity - state.delivered},
        )

    async def cancel_order(self, provider_order_id: str) -> bool:
        """إلغاء طلب وهمي (مدعوم في المزود الاختباري)."""
        self.calls.append(("cancel", {"order": provider_order_id}))
        state = self.orders.get(provider_order_id)
        if state is None or state.status in {"Completed", "Canceled"}:
            return False
        state.status = "Canceled"
        self.balance_units += state.charge_units
        return True

    # ------------------------------ الحساب ------------------------------- #

    async def get_balance(self) -> ProviderBalance:
        """رصيد الحساب الوهمي، أو الاستثناء المبرمَج لمحاكاة فشل الاتصال."""
        self.calls.append(("balance", {}))
        if self.fail_next_balance is not None:
            error, self.fail_next_balance = self.fail_next_balance, None
            raise error
        return ProviderBalance(amount_units=self.balance_units, currency="USD", raw={"balance": "mock"})

    async def get_services(self) -> list[ProviderServiceItem]:
        """قائمة خدمات وهمية ثابتة للاستيراد التجريبي."""
        self.calls.append(("services", {}))
        return [
            ProviderServiceItem(
                provider_service_id="555",
                name="Mock Instagram Followers",
                rate_per_1000_units=self.rate_per_1000_units,
                min_quantity=100,
                max_quantity=100_000,
                category="Instagram",
            ),
            ProviderServiceItem(
                provider_service_id="556",
                name="Mock Instagram Likes",
                rate_per_1000_units=self.rate_per_1000_units // 2,
                min_quantity=50,
                max_quantity=50_000,
                category="Instagram",
            ),
        ]

    # ------------------------ أدوات التحكم للاختبار ----------------------- #

    def advance(self, provider_order_id: str, *, to: str, delivered: int | None = None) -> None:
        """تحريك طلب وهمي إلى حالة محددة (لمحاكاة partial/canceled في الاختبارات)."""
        state = self.orders[provider_order_id]
        state.status = to
        if delivered is not None:
            state.delivered = delivered

    def schedule_temporary_failure(self, message: str = "انقطاع مؤقت في الشبكة") -> None:
        """برمجة فشل مؤقت في الاستدعاء القادم لإنشاء الطلب."""
        self.fail_next_add = ProviderTemporaryError(message)

    def schedule_uncertain_failure(self, message: str = "انتهت المهلة بعد الإرسال") -> None:
        """برمجة نتيجة غير مؤكدة في الاستدعاء القادم (أخطر حالة)."""
        self.fail_next_add = ProviderUncertainError(message)

    def schedule_permanent_failure(self, message: str = "المزود رفض الطلب") -> None:
        """برمجة رفض نهائي في الاستدعاء القادم."""
        self.fail_next_add = ProviderPermanentError(message)
```

# ترحيل إعدادات المرحلة 2

## `database/migrations/0004_phase2_settings.sql`

```sql
-- =====================================================================
-- الترحيل 0004 — إعدادات أضافتها المرحلة 2 (خدمات النواة)
-- السبب: خدمات الشحن والدعم تحتاج حدوداً قابلة للتحكم من لوحة الأدمن
--        بدل أرقام ثابتة في الكود.
-- =====================================================================

INSERT OR IGNORE INTO settings (key, value, value_type, group_code, name_ar, description_ar, is_editable, updated_at) VALUES
    ('max_pending_payments_per_user', '3', 'int', 'payments', 'أقصى عدد طلبات شحن معلّقة للمستخدم',
     'يمنع تكديس طلبات شحن غير مراجَعة من نفس المستخدم', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('ticket_auto_close_days', '7', 'int', 'limits', 'إغلاق التذاكر المجابة تلقائياً بعد (أيام)',
     'صفر يعني عدم الإغلاق التلقائي', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('ticket_reopen_hours', '48', 'int', 'limits', 'مهلة إعادة فتح التذكرة المغلقة بالساعات',
     'بعدها يجب فتح تذكرة جديدة - صفر يعني منع إعادة الفتح', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
```

# طبقة الخدمات — services/

## `services/__init__.py`

```python
"""
حزمة الخدمات — طبقة منطق العمل بين الواجهة (المرحلة 3+) وقاعدة البيانات.

لماذا حاوية خدمات؟
    الخدمات مترابطة (الطلبات تحتاج المحفظة والمزودين والإشعارات...). بدل أن تبني كل
    نقطة دخول اعتمادياتها بنفسها — فتتسرب الأخطاء وتتكرر الكائنات — تُبنى هنا مرة
    واحدة بترتيب صحيح، ويُمرَّر كائن `ServiceContainer` واحد إلى بقية النظام.

ترتيب البناء (من الأدنى اعتماداً إلى الأعلى):
    settings → audit → notifications → auth → wallet → users → catalog
    → providers → orders → payments → tickets → stats
"""

from __future__ import annotations

from dataclasses import dataclass

from database.database import Database
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.catalog_service import CatalogService
from services.notification_service import NotificationService
from services.order_service import OrderService
from services.payment_service import PaymentService
from services.provider_service import ProviderService
from services.settings_service import SettingsService
from services.stats_service import StatsService
from services.ticket_service import TicketService
from services.user_service import UserService
from services.wallet_service import WalletService
from utils.logging_setup import get_logger
from utils.security import SecretBox

logger = get_logger(__name__)

__all__ = [
    "AuditService",
    "AuthService",
    "CatalogService",
    "NotificationService",
    "OrderService",
    "PaymentService",
    "ProviderService",
    "ServiceContainer",
    "SettingsService",
    "StatsService",
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
        logger.info("استرداد الإقلاع: %s", report)
        return report


def build_services(
    db: Database,
    repos: Repositories | None = None,
    *,
    secret_box: SecretBox,
    super_admin_ids: tuple[int, ...] = (),
    settings_ttl_seconds: float | None = None,
) -> ServiceContainer:
    """
    بناء كل الخدمات وربط اعتمادياتها بالترتيب الصحيح.

    المدخلات:
        db                   : اتصال قاعدة البيانات (مفتوح مسبقاً).
        repos                : المستودعات (تُبنى تلقائياً إن لم تُمرَّر).
        secret_box           : صندوق التشفير لمفاتيح المزودين (إجباري — لا مفاتيح واضحة).
        super_admin_ids      : معرفات الأدمن الأعلى من ملف البيئة (مسار طوارئ فقط).
        settings_ttl_seconds : مدة صلاحية كاش الإعدادات (يُستخدم 0 في الاختبارات لإلغاء الكاش).

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
    wallet = WalletService(db, repositories)
    users = UserService(db, repositories, settings, audit, auth, notifications)
    catalog = CatalogService(db, repositories, settings, audit, auth)
    providers = ProviderService(
        db, repositories, settings, audit, auth, notifications, secret_box
    )
    orders = OrderService(
        db, repositories, settings, wallet, catalog, providers, notifications, audit, auth
    )
    payments = PaymentService(db, repositories, settings, wallet, notifications, audit, auth)
    tickets = TicketService(db, repositories, settings, notifications, audit, auth)
    stats = StatsService(db, repositories, settings, auth, providers)

    logger.info("تم بناء طبقة الخدمات (%s خدمة)", 12)
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
    )
```

## `services/settings_service.py`

```python
"""
خدمة الإعدادات: قراءة إعدادات النظام من قاعدة البيانات مع ذاكرة مؤقتة قصيرة.

لماذا ذاكرة مؤقتة؟ لأن كل طلب مستخدم يقرأ عدة إعدادات (الصيانة، الحدود، العملة…)،
وقراءتها من القرص في كل مرة إهدار. المدة قصيرة (ثوانٍ) والتعديل من اللوحة يُبطلها فوراً،
فلا يحدث تأخير في ظهور أي تغيير.
"""

from __future__ import annotations

import time
from typing import Any

from database.database import Database
from database.models import Setting
from database.repositories import Repositories
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: مدة صلاحية الذاكرة المؤقتة بالثواني
CACHE_TTL_SECONDS: float = 20.0


class SettingsService:
    """واجهة واحدة لقراءة وتعديل إعدادات النظام."""

    def __init__(self, db: Database, repos: Repositories, *, ttl_seconds: float = CACHE_TTL_SECONDS) -> None:
        """تهيئة الخدمة بقاعدة البيانات ومستودعاتها ومدة صلاحية الذاكرة المؤقتة."""
        self.db = db
        self.repos = repos
        self._ttl = ttl_seconds
        self._cache: dict[str, str] = {}
        self._expires_at: float = 0.0

    # ------------------------------ الداخلية ------------------------------ #

    async def _values(self) -> dict[str, str]:
        """إرجاع كل الإعدادات كقاموس، مع إعادة التحميل عند انتهاء صلاحية الذاكرة."""
        now = time.monotonic()
        if now >= self._expires_at or not self._cache:
            self._cache = await self.repos.settings.as_dict()
            self._expires_at = now + self._ttl
        return self._cache

    def invalidate(self) -> None:
        """إبطال الذاكرة المؤقتة فوراً (بعد أي تعديل على الإعدادات)."""
        self._cache = {}
        self._expires_at = 0.0

    # ------------------------------- القراءة ------------------------------ #

    async def get_str(self, key: str, default: str = "") -> str:
        """قراءة إعداد نصي."""
        values = await self._values()
        raw = values.get(key)
        return raw if raw not in (None, "") else default

    async def get_int(self, key: str, default: int = 0) -> int:
        """قراءة إعداد رقمي (يُرجع الافتراضي إذا كانت القيمة تالفة، مع تسجيل تحذير)."""
        values = await self._values()
        raw = values.get(key)
        if raw is None or raw == "":
            return default
        try:
            return int(str(raw).strip())
        except ValueError:
            logger.warning("قيمة الإعداد %s ليست رقماً صحيحاً: %r — استُخدم الافتراضي", key, raw)
            return default

    async def get_bool(self, key: str, default: bool = False) -> bool:
        """قراءة إعداد منطقي (يقبل 1/true/yes/on)."""
        values = await self._values()
        raw = values.get(key)
        if raw is None or raw == "":
            return default
        return str(raw).strip().lower() in {"1", "true", "yes", "on", "نعم"}

    async def get_money_units(self, key: str, default: int = 0) -> int:
        """قراءة إعداد مالي مخزَّن بوحدات صحيحة."""
        return await self.get_int(key, default)

    async def get_json(self, key: str, default: Any = None) -> Any:
        """قراءة إعداد بصيغة JSON."""
        return await self.repos.settings.get_json(key, default)

    async def currency(self) -> tuple[str, str, int]:
        """
        بيانات العملة المعروضة.

        المخرجات: (رمز العملة النصي، الرمز المختصر للعرض، عدد الخانات العشرية).
        """
        code = await self.get_str("currency_code", "YER")
        symbol = await self.get_str("currency_symbol", code)
        decimals = await self.get_int("display_decimals", 2)
        return code, symbol, decimals

    async def money_symbol(self) -> str:
        """رمز العملة المستخدم في نصوص الإشعارات."""
        _, symbol, _ = await self.currency()
        return symbol

    async def is_maintenance(self) -> bool:
        """هل النظام في وضع الصيانة؟"""
        return await self.get_bool("maintenance_mode", False)

    async def maintenance_message(self) -> str:
        """نص رسالة الصيانة المعروضة للمستخدمين."""
        return await self.get_str(
            "maintenance_message", "🚧 النظام في صيانة مؤقتة. نعتذر عن الإزعاج."
        )

    async def registration_enabled(self) -> bool:
        """هل التسجيل مفتوح للمستخدمين الجدد؟"""
        return await self.get_bool("registration_enabled", True)

    async def all_settings(self) -> list[Setting]:
        """كل الإعدادات بتفاصيلها (لعرضها في لوحة الأدمن)."""
        return await self.repos.settings.all()

    async def group(self, group_code: str) -> list[Setting]:
        """إعدادات مجموعة واحدة (عامة، طلبات، مدفوعات…)."""
        return await self.repos.settings.by_group(group_code)

    async def groups(self) -> list[str]:
        """أسماء مجموعات الإعدادات."""
        return await self.repos.settings.groups()

    # ------------------------------- الكتابة ------------------------------ #

    async def set(self, key: str, value: Any, *, admin_id: int | None = None) -> bool:
        """
        تعديل قيمة إعداد قابل للتعديل، مع تسجيل العملية في سجل التدقيق.

        المخرجات: True عند التعديل، False إذا كان الإعداد غير موجود أو محمياً من التعديل.
        """
        before = await self.repos.settings.get_raw(key)
        async with self.db.transaction() as tx:
            changed = await self.repos.settings.set(tx, key, value, updated_by=admin_id)
            if changed:
                await self.repos.audit.log(
                    tx,
                    action="settings.update",
                    admin_id=admin_id,
                    target_type="setting",
                    target_id=key,
                    before={"value": before},
                    after={"value": str(value)},
                )
        if changed:
            self.invalidate()
            logger.info("تم تعديل الإعداد %s بواسطة الأدمن %s", key, admin_id)
        else:
            logger.warning("رُفض تعديل الإعداد %s (غير موجود أو غير قابل للتعديل)", key)
        return changed
```

## `services/audit_service.py`

```python
"""
خدمة سجل التدقيق: تسجيل كل عملية إدارية حسّاسة بمن نفّذها وما تغيّر.

قاعدة المشروع: أي إجراء إداري يمسّ المال أو الصلاحيات أو بيانات المستخدمين
يجب أن يترك أثراً في هذا السجل — والسجل لا يُحذف.
"""

from __future__ import annotations

from typing import Any

from database.database import Database, Tx
from database.models import AuditLog
from database.repositories import Repositories
from utils.logging_setup import get_logger
from utils.security import sanitize

logger = get_logger(__name__)


class AuditService:
    """كتابة وقراءة سجل التدقيق."""

    def __init__(self, db: Database, repos: Repositories) -> None:
        """تهيئة الخدمة."""
        self.db = db
        self.repos = repos

    # ------------------------------- الكتابة ------------------------------ #

    async def log(
        self,
        tx: Tx,
        *,
        action: str,
        admin_id: int | None = None,
        target_type: str | None = None,
        target_id: str | int | None = None,
        before: Any = None,
        after: Any = None,
        details: Any = None,
        source: str = "telegram",
    ) -> int | None:
        """
        تسجيل عملية داخل معاملة قائمة (حتى يسقط السجل مع العملية إن فشلت).

        ملاحظة أمنية: كل النصوص تمر على أداة تنقية الأسرار قبل التخزين.
        """
        return await self.repos.audit.log(
            tx,
            action=action,
            admin_id=admin_id,
            target_type=target_type,
            target_id=target_id,
            before=_clean(before),
            after=_clean(after),
            details=_clean(details),
            source=source,
        )

    async def log_standalone(
        self,
        *,
        action: str,
        admin_id: int | None = None,
        target_type: str | None = None,
        target_id: str | int | None = None,
        details: Any = None,
        source: str = "system",
    ) -> int | None:
        """تسجيل عملية بمعاملة مستقلة (عندما لا توجد معاملة جارية)."""
        async with self.db.transaction() as tx:
            return await self.log(
                tx,
                action=action,
                admin_id=admin_id,
                target_type=target_type,
                target_id=target_id,
                details=details,
                source=source,
            )

    async def log_permission_denied(
        self, *, user_id: int, permission: str, context: str = ""
    ) -> None:
        """
        تسجيل محاولة وصول مرفوضة.

        تُسجَّل دائماً لأنها مؤشر أمني مهم (محاولة استخدام زر إداري بلا صلاحية).
        """
        async with self.db.transaction() as tx:
            await self.repos.audit.log(
                tx,
                action="security.permission_denied",
                admin_id=user_id,
                target_type="permission",
                target_id=permission,
                details={"context": sanitize(context)},
                source="security",
            )
        logger.warning("رُفض وصول المستخدم %s إلى الصلاحية %s (%s)", user_id, permission, context)

    # ------------------------------- القراءة ------------------------------ #

    async def recent(self, *, limit: int = 20, offset: int = 0) -> list[AuditLog]:
        """أحدث عمليات التدقيق (لعرضها في اللوحة)."""
        return await self.repos.audit.list_recent(limit=limit, offset=offset)

    async def by_admin(self, admin_id: int, *, limit: int = 20, offset: int = 0) -> list[AuditLog]:
        """سجل عمليات أدمن محدد."""
        return await self.repos.audit.list_by_admin(admin_id, limit=limit, offset=offset)

    async def by_target(self, target_type: str, target_id: str | int, *, limit: int = 20) -> list[AuditLog]:
        """سجل العمليات التي جرت على هدف محدد (مستخدم، طلب، إعداد…)."""
        return await self.repos.audit.list_by_target(target_type, target_id, limit=limit)

    async def count(self) -> int:
        """إجمالي عدد السجلات."""
        return await self.repos.audit.count_all()


def _clean(value: Any) -> Any:
    """تنقية القيم النصية من الأسرار قبل حفظها في السجل."""
    if value is None:
        return None
    if isinstance(value, str):
        return sanitize(value)
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    return value
```

## `services/auth_service.py`

```python
"""
خدمة الصلاحيات والحماية.

كل إجراء حسّاس يمر من هنا مرتين:
    1. في طبقة الواجهة قبل عرض الزر أو تنفيذه.
    2. داخل الخدمة نفسها قبل تنفيذ العملية (دفاع في العمق).

لا يوجد أي أدمن مكتوب في الكود: الأدوار والصلاحيات كلها في قاعدة البيانات،
و`SUPER_ADMIN_IDS` في ملف البيئة تُستخدم للزرع الأولي والطوارئ فقط.
"""

from __future__ import annotations

from core.enums import Role
from core.exceptions import MaintenanceModeError, PermissionDeniedError, UserBannedError
from core.permissions import Permission
from database.database import Database
from database.models import User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.settings_service import SettingsService
from utils.logging_setup import get_logger

logger = get_logger(__name__)

#: الأدوار التي يُسمح لها بالعمل أثناء وضع الصيانة
MAINTENANCE_BYPASS_ROLES: frozenset[str] = frozenset({Role.ADMIN, Role.SUPER_ADMIN})


class AuthService:
    """التحقق من الصلاحيات والحظر ووضع الصيانة."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        audit: AuditService,
        *,
        super_admin_ids: tuple[int, ...] = (),
    ) -> None:
        """تهيئة الخدمة مع قائمة الأدمن الأعلى القادمة من ملف البيئة (للطوارئ فقط)."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.audit = audit
        self.super_admin_ids = tuple(super_admin_ids)

    # ------------------------------ الصلاحيات ----------------------------- #

    async def permissions_of(self, user: User) -> set[str]:
        """كل الصلاحيات الفعلية للمستخدم (صلاحيات دوره + استثناءاته الفردية)."""
        return await self.repos.rbac.effective_permissions(user.id, user.role)

    async def has_permission(self, user: User, permission: str) -> bool:
        """هل يملك المستخدم هذه الصلاحية؟"""
        return await self.repos.rbac.has_permission(user.id, user.role, permission)

    async def require_permission(self, user: User, permission: str, *, context: str = "") -> None:
        """
        التأكد من امتلاك الصلاحية وإلا رفع استثناء وتسجيل المحاولة.

        الاستثناءات:
            PermissionDeniedError : المستخدم لا يملك الصلاحية (تُسجَّل المحاولة في سجل التدقيق).
        """
        if await self.has_permission(user, permission):
            return
        await self.audit.log_permission_denied(
            user_id=user.id, permission=permission, context=context
        )
        raise PermissionDeniedError(
            f"المستخدم {user.id} لا يملك الصلاحية {permission}"
        )

    async def is_admin(self, user: User) -> bool:
        """هل يملك المستخدم حق دخول لوحة التحكم أصلاً؟"""
        return await self.has_permission(user, Permission.ADMIN_ACCESS)

    def is_emergency_super_admin(self, telegram_id: int) -> bool:
        """
        هل هذا المعرف ضمن قائمة الطوارئ في ملف البيئة؟

        تُستخدم فقط عند تعذّر الوصول لقاعدة البيانات أو لإصلاح دور مفقود،
        ولا تمنح أي صلاحية بمفردها داخل المسارات العادية.
        """
        return telegram_id in self.super_admin_ids

    # -------------------------------- الحظر ------------------------------- #

    async def ensure_not_banned(self, user: User) -> None:
        """
        رفض تنفيذ أي إجراء لمستخدم محظور.

        الاستثناءات:
            UserBannedError : الحساب محظور، مع ذكر السبب إن وُجد.
        """
        if not user.is_banned:
            return
        reason = f" السبب: {user.ban_reason}" if user.ban_reason else ""
        raise UserBannedError(
            f"المستخدم {user.id} محظور", user_message=f"🚫 حسابك محظور من استخدام البوت.{reason}"
        )

    # ------------------------------- الصيانة ------------------------------ #

    async def ensure_available(self, user: User) -> None:
        """
        التأكد أن النظام يعمل (ليس في صيانة) — مع استثناء الأدمن.

        الاستثناءات:
            MaintenanceModeError : النظام في وضع الصيانة والمستخدم ليس أدمن.
        """
        if user.role in MAINTENANCE_BYPASS_ROLES:
            return
        if await self.settings.is_maintenance():
            raise MaintenanceModeError(
                "النظام في وضع الصيانة", user_message=await self.settings.maintenance_message()
            )

    async def guard(self, user: User, *, permission: str | None = None, context: str = "") -> None:
        """
        فحص شامل يُستدعى في بداية أي إجراء: الحظر ثم الصيانة ثم الصلاحية.

        الاستثناءات: UserBannedError · MaintenanceModeError · PermissionDeniedError
        """
        await self.ensure_not_banned(user)
        await self.ensure_available(user)
        if permission:
            await self.require_permission(user, permission, context=context)

    # ------------------------- إدارة أدوار المستخدمين --------------------- #

    async def set_role(self, actor: User, target_user_id: int, new_role: str) -> bool:
        """
        تغيير دور مستخدم (صلاحية `users.role.change` — للأدمن الأعلى فقط افتراضياً).

        المخرجات: True عند التغيير الفعلي.

        الاستثناءات:
            PermissionDeniedError : المنفّذ لا يملك الصلاحية.
            ValueError            : دور غير معروف.
        """
        await self.require_permission(actor, Permission.USERS_ROLE_CHANGE, context=f"user:{target_user_id}")
        valid_roles = {row["code"] for row in await self.repos.rbac.list_roles()}
        if new_role not in valid_roles:
            raise ValueError(f"دور غير معروف: {new_role}")

        target = await self.repos.users.get_by_id(target_user_id)
        if target is None:
            return False

        async with self.db.transaction() as tx:
            changed = await self.repos.users.set_role(tx, target_user_id, new_role)
            if changed:
                await self.audit.log(
                    tx,
                    action="users.role.change",
                    admin_id=actor.id,
                    target_type="user",
                    target_id=target_user_id,
                    before={"role": target.role},
                    after={"role": new_role},
                )
        if changed:
            logger.info("غيّر الأدمن %s دور المستخدم %s إلى %s", actor.id, target_user_id, new_role)
        return changed

    async def set_user_permission(
        self, actor: User, target_user_id: int, permission: str, *, allow: bool
    ) -> None:
        """
        منح أو منع صلاحية لمستخدم بعينه (استثناء فردي يتقدم على دوره).

        الاستثناءات:
            PermissionDeniedError : المنفّذ لا يملك صلاحية إدارة الأدمن.
        """
        await self.require_permission(actor, Permission.ADMINS_MANAGE, context=f"user:{target_user_id}")
        async with self.db.transaction() as tx:
            await self.repos.rbac.set_user_override(
                tx, target_user_id, permission, allow=allow, granted_by=actor.id
            )
            await self.audit.log(
                tx,
                action="admins.permission.override",
                admin_id=actor.id,
                target_type="user",
                target_id=target_user_id,
                after={"permission": permission, "allow": allow},
            )

    async def clear_user_permission(self, actor: User, target_user_id: int, permission: str) -> bool:
        """إزالة استثناء فردي وإعادة المستخدم إلى صلاحيات دوره."""
        await self.require_permission(actor, Permission.ADMINS_MANAGE, context=f"user:{target_user_id}")
        async with self.db.transaction() as tx:
            removed = await self.repos.rbac.clear_user_override(tx, target_user_id, permission)
            if removed:
                await self.audit.log(
                    tx,
                    action="admins.permission.clear",
                    admin_id=actor.id,
                    target_type="user",
                    target_id=target_user_id,
                    after={"permission": permission},
                )
        return removed
```

## `services/user_service.py`

```python
"""
خدمة المستخدمين: التسجيل التلقائي عند أول استخدام، وتحديث البيانات، والحظر.

ملاحظة: هذه الخدمة لا تلمس الرصيد إطلاقاً — كل ما يتعلق بالمال في `WalletService`.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.enums import NotificationType
from core.exceptions import ValidationError
from core.permissions import Permission
from database.database import Database
from database.models import User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.notification_service import NotificationService
from services.settings_service import SettingsService
from texts import templates
from utils.datetime_utils import day_bounds_utc, utc_now_iso
from utils.logging_setup import get_logger
from utils.validators import clean_text, normalize_username

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class UserSummary:
    """ملخص حساب المستخدم كما يُعرض له أو للأدمن."""

    user: User
    orders_count: int
    active_orders: int
    tickets_open: int
    payments_count: int


class UserService:
    """كل ما يخص حساب المستخدم عدا المال."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        audit: AuditService,
        auth: AuthService,
        notifications: NotificationService,
    ) -> None:
        """تهيئة الخدمة بالاعتماديات التي تحتاجها."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.audit = audit
        self.auth = auth
        self.notifications = notifications

    # ------------------------------ التسجيل ------------------------------- #

    async def get_or_create(
        self,
        *,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        referrer_telegram_id: int | None = None,
    ) -> tuple[User, bool]:
        """
        جلب المستخدم أو إنشاؤه عند أول تفاعل مع البوت.

        المخرجات: (المستخدم، هل أُنشئ الآن؟)

        الاستثناءات:
            ValidationError : التسجيل مغلق من الإعدادات ومحاولة إنشاء حساب جديد.
        """
        existing = await self.repos.users.get_by_telegram_id(telegram_id)
        clean_username = normalize_username(username)

        if existing is not None:
            await self._refresh_profile(existing, clean_username, first_name, last_name)
            return (await self.repos.users.get_by_telegram_id(telegram_id) or existing), False

        if not await self.settings.registration_enabled():
            raise ValidationError(
                "التسجيل مغلق حالياً",
                user_message="🚧 التسجيل متوقف مؤقتاً. حاول لاحقاً أو تواصل مع الدعم.",
            )

        referrer_id: int | None = None
        if referrer_telegram_id and referrer_telegram_id != telegram_id:
            referrer = await self.repos.users.get_by_telegram_id(referrer_telegram_id)
            referrer_id = referrer.id if referrer else None

        async with self.db.transaction() as tx:
            created = await self.repos.users.create(
                tx,
                telegram_id=telegram_id,
                username=clean_username,
                first_name=first_name,
                last_name=last_name,
                referrer_id=referrer_id,
            )
            await self.audit.log(
                tx,
                action="users.register",
                admin_id=None,
                target_type="user",
                target_id=created.id,
                details={"telegram_id": telegram_id, "referrer_id": referrer_id},
                source="bot",
            )
        logger.info("تسجيل مستخدم جديد %s (تيليجرام %s)", created.id, telegram_id)
        return created, True

    async def _refresh_profile(
        self, user: User, username: str | None, first_name: str | None, last_name: str | None
    ) -> None:
        """تحديث بيانات الملف الشخصي إذا تغيّرت في تيليجرام (بدون كتابة بلا داعٍ)."""
        if (user.username or None) == username and (user.first_name or None) == (first_name or None) \
                and (user.last_name or None) == (last_name or None):
            return
        async with self.db.transaction() as tx:
            await self.repos.users.update_profile(
                tx, user.id, username=username, first_name=first_name, last_name=last_name
            )

    async def touch_activity(self, user_id: int) -> None:
        """تحديث وقت آخر نشاط للمستخدم (يُستدعى مع كل تفاعل)."""
        async with self.db.transaction() as tx:
            await self.repos.users.touch_activity(tx, user_id)

    async def mark_bot_blocked(self, user_id: int, blocked: bool = True) -> None:
        """تسجيل أن المستخدم حظر البوت (أو ألغى الحظر) لإيقاف الإشعارات عنه."""
        async with self.db.transaction() as tx:
            await self.repos.users.set_blocked_bot(tx, user_id, blocked)

    # ------------------------------- القراءة ------------------------------ #

    async def get(self, user_id: int) -> User | None:
        """جلب مستخدم بالمعرف الداخلي."""
        return await self.repos.users.get_by_id(user_id)

    async def get_by_telegram(self, telegram_id: int) -> User | None:
        """جلب مستخدم بمعرف تيليجرام."""
        return await self.repos.users.get_by_telegram_id(telegram_id)

    async def search(self, actor: User, query: str, *, limit: int = 10, offset: int = 0) -> list[User]:
        """
        بحث الأدمن عن مستخدم بالمعرف أو الاسم.

        الاستثناءات: PermissionDeniedError إذا لم يملك صلاحية `users.view`.
        """
        await self.auth.require_permission(actor, Permission.USERS_VIEW, context="users.search")
        return await self.repos.users.search(query, limit=limit, offset=offset)

    async def summary(self, user: User) -> UserSummary:
        """ملخص حساب: عدد الطلبات والطلبات النشطة والتذاكر المفتوحة وطلبات الشحن."""
        from core.order_state import ACTIVE_STATUSES

        orders_count = await self.repos.orders.count_by_user(user.id)
        active = await self.repos.orders.count_by_user(user.id, statuses=sorted(ACTIVE_STATUSES))
        tickets = await self.repos.tickets.list_by_user(user.id, limit=50)
        payments = await self.repos.payments.list_by_user(user.id, limit=50)
        return UserSummary(
            user=user,
            orders_count=orders_count,
            active_orders=active,
            tickets_open=sum(1 for ticket in tickets if ticket.status != "closed"),
            payments_count=len(payments),
        )

    async def counters(self) -> dict[str, int]:
        """عدادات عامة عن المستخدمين (للوحة الإحصائيات السريعة)."""
        start_today, _ = day_bounds_utc(0)
        return {
            "total": await self.repos.users.count_all(),
            "new_today": await self.repos.users.count_since(start_today),
            "active_today": await self.repos.users.count_active_since(start_today),
            "banned": await self.repos.users.count_banned(),
        }

    # -------------------------- إجراءات إدارية ---------------------------- #

    async def ban(self, actor: User, target_user_id: int, reason: str) -> bool:
        """
        حظر مستخدم مع تسجيل السبب وإشعاره.

        الاستثناءات: PermissionDeniedError · ValidationError (سبب فارغ).
        """
        await self.auth.require_permission(actor, Permission.USERS_BAN, context=f"user:{target_user_id}")
        clean_reason = clean_text(reason, field="سبب الحظر", max_length=200, min_length=3)

        target = await self.repos.users.get_by_id(target_user_id)
        if target is None:
            return False
        if target.role in {"admin", "super_admin"} and actor.role != "super_admin":
            raise ValidationError(
                "محاولة حظر أدمن بدون صلاحية عليا",
                user_message="🚫 لا يمكنك حظر حساب إداري.",
            )

        async with self.db.transaction() as tx:
            changed = await self.repos.users.set_ban(tx, target_user_id, banned=True, reason=clean_reason)
            if changed:
                title, message = templates.account_banned(reason=clean_reason)
                await self.notifications.notify_user_manual(
                    tx,
                    user_id=target_user_id,
                    token=f"ban:{target_user_id}:{utc_now_iso()}",
                    title=title,
                    message=message,
                    type=NotificationType.SYSTEM,
                )
                await self.audit.log(
                    tx,
                    action="users.ban",
                    admin_id=actor.id,
                    target_type="user",
                    target_id=target_user_id,
                    before={"is_banned": target.is_banned},
                    after={"is_banned": True, "reason": clean_reason},
                )
        if changed:
            logger.warning("حظر الأدمن %s المستخدم %s: %s", actor.id, target_user_id, clean_reason)
        return changed

    async def unban(self, actor: User, target_user_id: int) -> bool:
        """رفع الحظر عن مستخدم وإشعاره."""
        await self.auth.require_permission(actor, Permission.USERS_UNBAN, context=f"user:{target_user_id}")
        target = await self.repos.users.get_by_id(target_user_id)
        if target is None or not target.is_banned:
            return False

        async with self.db.transaction() as tx:
            changed = await self.repos.users.set_ban(tx, target_user_id, banned=False)
            if changed:
                title, message = templates.account_unbanned()
                await self.notifications.notify_user_manual(
                    tx,
                    user_id=target_user_id,
                    token=f"unban:{target_user_id}:{utc_now_iso()}",
                    title=title,
                    message=message,
                )
                await self.audit.log(
                    tx,
                    action="users.unban",
                    admin_id=actor.id,
                    target_type="user",
                    target_id=target_user_id,
                    before={"is_banned": True},
                    after={"is_banned": False},
                )
        return changed

    async def set_note(self, actor: User, target_user_id: int, note: str) -> bool:
        """كتابة ملاحظة إدارية على حساب مستخدم (تظهر للأدمن فقط)."""
        await self.auth.require_permission(actor, Permission.USERS_NOTE, context=f"user:{target_user_id}")
        clean_note = clean_text(note, field="الملاحظة", max_length=500, min_length=1)
        async with self.db.transaction() as tx:
            changed = await self.repos.users.update_fields(tx, target_user_id, notes=clean_note)
            if changed:
                await self.audit.log(
                    tx,
                    action="users.note",
                    admin_id=actor.id,
                    target_type="user",
                    target_id=target_user_id,
                    after={"note": clean_note},
                )
        return changed
```

## `services/wallet_service.py`

```python
"""
خدمة المحفظة — **الجهة الوحيدة في النظام التي تعدّل رصيد المستخدم**.

قواعد غير قابلة للكسر:
    1. لا تعديل للرصيد خارج هذه الخدمة (المستودعات تُستدعى من هنا فقط).
    2. كل تغيير في الرصيد يرافقه صف في `transactions` داخل **نفس المعاملة** —
       لا خصم بلا حركة، ولا استرجاع بلا حركة.
    3. كل حركة لها `reference` فريد، فحتى لو استُدعيت العملية مرتين لن تُنفَّذ مرتين.
    4. الخصم يستخدم تحديثاً مشروطاً (`balance_units >= amount`) فلا يمكن أن يصبح الرصيد سالباً.
    5. الدوال التي تأخذ `tx` لا تفتح معاملة بنفسها — المتصل يضمن الذرّية مع بقية العملية
       (مثلاً: إنشاء الطلب + الخصم + الإشعار في معاملة واحدة).
"""

from __future__ import annotations

from dataclasses import dataclass

from core.constants import (
    REF_MANUAL,
    REF_ORDER_DEBIT,
    REF_ORDER_PARTIAL_REFUND,
    REF_ORDER_REFUND,
    REF_PAYMENT_DEPOSIT,
)
from core.enums import TransactionType
from core.exceptions import (
    DuplicateOperationError,
    InsufficientBalanceError,
    InvalidAmountError,
    WalletError,
)
from database.database import Database, Tx
from database.models import Transaction, User
from database.repositories import Repositories
from utils.logging_setup import get_logger
from utils.security import new_token

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LedgerCheck:
    """نتيجة مطابقة الرصيد المخزَّن مع مجموع دفتر الحركات."""

    user_id: int
    stored_units: int
    ledger_units: int

    @property
    def is_balanced(self) -> bool:
        """هل الرصيد مطابق للدفتر؟"""
        return self.stored_units == self.ledger_units

    @property
    def difference_units(self) -> int:
        """الفرق بين المخزَّن والدفتر (صفر يعني سلامة محاسبية)."""
        return self.stored_units - self.ledger_units


class WalletService:
    """كل عمليات المال: إيداع، خصم، استرجاع، تسويات يدوية."""

    def __init__(self, db: Database, repos: Repositories) -> None:
        """تهيئة الخدمة."""
        self.db = db
        self.repos = repos

    # ------------------------------- القراءة ------------------------------ #

    async def balance_units(self, user_id: int) -> int:
        """الرصيد الحالي بوحدات المال الصحيحة."""
        return await self.repos.users.get_balance_units(user_id)

    async def history(self, user_id: int, *, limit: int = 10, offset: int = 0) -> list[Transaction]:
        """آخر حركات المستخدم المالية."""
        return await self.repos.transactions.list_by_user(user_id, limit=limit, offset=offset)

    async def history_count(self, user_id: int) -> int:
        """إجمالي عدد حركات المستخدم (للتصفح بالصفحات)."""
        return await self.repos.transactions.count_by_user(user_id)

    async def order_transactions(self, order_id: int) -> list[Transaction]:
        """كل الحركات المالية المرتبطة بطلب (خصم + استرجاعات)."""
        return await self.repos.transactions.list_by_order(order_id)

    async def verify_ledger(self, user_id: int) -> LedgerCheck:
        """
        مطابقة محاسبية: هل رصيد المستخدم = مجموع حركاته؟

        تُستخدم في الاختبارات وفي تقرير الأدمن لاكتشاف أي خلل مبكراً.
        """
        stored = await self.repos.users.get_balance_units(user_id)
        ledger = await self.repos.transactions.user_balance_from_ledger(user_id)
        check = LedgerCheck(user_id=user_id, stored_units=stored, ledger_units=ledger)
        if not check.is_balanced:
            logger.error(
                "اختلال محاسبي للمستخدم %s: الرصيد %s ودفتر الحركات %s",
                user_id, stored, ledger,
            )
        return check

    # ------------------------------ أدوات داخلية -------------------------- #

    @staticmethod
    def _validate_amount(amount_units: int) -> int:
        """
        التأكد أن المبلغ عدد صحيح موجب.

        الاستثناءات:
            InvalidAmountError : مبلغ صفر أو سالب أو ليس عدداً صحيحاً.
        """
        if isinstance(amount_units, bool) or not isinstance(amount_units, int):
            raise InvalidAmountError(f"المبلغ يجب أن يكون عدداً صحيحاً: {amount_units!r}")
        if amount_units <= 0:
            raise InvalidAmountError(f"المبلغ يجب أن يكون أكبر من صفر: {amount_units}")
        return amount_units

    async def _ensure_new_reference(self, reference: str) -> None:
        """
        رفض تكرار عملية بنفس المرجع قبل محاولة الكتابة.

        الحماية النهائية هي قيد UNIQUE في قاعدة البيانات، وهذا الفحص لإعطاء رسالة أوضح.
        """
        if await self.repos.transactions.exists_reference(reference):
            raise DuplicateOperationError(f"عملية مكررة بالمرجع {reference}")

    # -------------------------------- الخصم ------------------------------- #

    async def charge_for_order(
        self, tx: Tx, *, user_id: int, order_id: int, amount_units: int, description: str = ""
    ) -> Transaction:
        """
        خصم قيمة طلب من رصيد المستخدم وتسجيل الحركة — داخل معاملة المتصل.

        المخرجات: الحركة المالية المُنشأة.

        الاستثناءات:
            InsufficientBalanceError : الرصيد لا يكفي (لم يُخصم شيء).
            DuplicateOperationError  : سبق خصم هذا الطلب.
        """
        self._validate_amount(amount_units)
        reference = REF_ORDER_DEBIT.format(order_id=order_id)
        await self._ensure_new_reference(reference)

        before = await self.repos.users.get_balance_units(user_id)
        debited = await self.repos.users.try_debit(tx, user_id, amount_units)
        if not debited:
            raise InsufficientBalanceError(
                f"رصيد المستخدم {user_id} ({before}) لا يكفي لخصم {amount_units}"
            )
        after = before - amount_units

        transaction = await self.repos.transactions.insert(
            tx,
            user_id=user_id,
            type=TransactionType.ORDER,
            amount_units=amount_units,
            balance_before_units=before,
            balance_after_units=after,
            order_id=order_id,
            reference=reference,
            description=description or f"خصم قيمة الطلب #{order_id}",
        )
        logger.info("خصم %s وحدة من المستخدم %s للطلب %s", amount_units, user_id, order_id)
        return transaction

    # ------------------------------ الاسترجاع ----------------------------- #

    async def refund_order(
        self,
        tx: Tx,
        *,
        user_id: int,
        order_id: int,
        amount_units: int,
        partial: bool = False,
        description: str = "",
    ) -> Transaction | None:
        """
        استرجاع مبلغ طلب (كامل أو جزئي) مع تسجيل الحركة وتحديث مبلغ الاسترجاع على الطلب.

        المخرجات: الحركة المالية، أو None إذا كان الاسترجاع قد نُفِّذ مسبقاً
                  (لا نرفع خطأ لأن إعادة المحاولة سلوك طبيعي في المهام الدورية).

        الاستثناءات:
            InvalidAmountError : مبلغ غير صالح.
            WalletError        : مبلغ الاسترجاع يتجاوز تكلفة الطلب.
        """
        self._validate_amount(amount_units)
        reference = (
            REF_ORDER_PARTIAL_REFUND.format(order_id=order_id)
            if partial
            else REF_ORDER_REFUND.format(order_id=order_id)
        )
        if await self.repos.transactions.exists_reference(reference):
            logger.info("تجاهل استرجاع مكرر للطلب %s (المرجع %s موجود)", order_id, reference)
            return None

        # تسجيل مبلغ الاسترجاع على الطلب أولاً: التحديث مشروط بعدم تجاوز التكلفة
        recorded = await self.repos.orders.add_refund_amount(tx, order_id, amount_units)
        if not recorded:
            raise WalletError(
                f"مبلغ الاسترجاع {amount_units} يتجاوز تكلفة الطلب #{order_id} أو الطلب غير موجود"
            )

        before = await self.repos.users.get_balance_units(user_id)
        credited = await self.repos.users.refund_spent(tx, user_id, amount_units)
        if not credited:
            raise WalletError(f"تعذر إعادة المبلغ لرصيد المستخدم {user_id}")
        after = before + amount_units

        transaction = await self.repos.transactions.insert(
            tx,
            user_id=user_id,
            type=TransactionType.PARTIAL_REFUND if partial else TransactionType.REFUND,
            amount_units=amount_units,
            balance_before_units=before,
            balance_after_units=after,
            order_id=order_id,
            reference=reference,
            description=description or (
                f"استرجاع جزئي للطلب #{order_id}" if partial else f"استرجاع كامل للطلب #{order_id}"
            ),
        )
        logger.info(
            "استرجاع %s وحدة للمستخدم %s (طلب %s، جزئي=%s)", amount_units, user_id, order_id, partial
        )
        return transaction

    # ------------------------------- الإيداع ------------------------------ #

    async def credit_from_payment(
        self, tx: Tx, *, user_id: int, payment_id: int, amount_units: int, actor_id: int | None = None
    ) -> Transaction:
        """
        إضافة رصيد بعد اعتماد طلب شحن — داخل نفس معاملة اعتماد الدفعة.

        الاستثناءات:
            DuplicateOperationError : سبق إيداع هذه الدفعة (نفس المرجع).
        """
        self._validate_amount(amount_units)
        reference = REF_PAYMENT_DEPOSIT.format(payment_id=payment_id)
        await self._ensure_new_reference(reference)

        before = await self.repos.users.get_balance_units(user_id)
        credited = await self.repos.users.credit(tx, user_id, amount_units, count_as_deposit=True)
        if not credited:
            raise WalletError(f"تعذر إضافة الرصيد للمستخدم {user_id}")
        after = before + amount_units

        transaction = await self.repos.transactions.insert(
            tx,
            user_id=user_id,
            type=TransactionType.DEPOSIT,
            amount_units=amount_units,
            balance_before_units=before,
            balance_after_units=after,
            payment_id=payment_id,
            reference=reference,
            description=f"شحن رصيد عبر طلب الدفع #{payment_id}",
            actor_id=actor_id,
        )
        logger.info("إيداع %s وحدة للمستخدم %s من الدفعة %s", amount_units, user_id, payment_id)
        return transaction

    # --------------------------- التسويات اليدوية -------------------------- #

    async def manual_credit(
        self, tx: Tx, *, user_id: int, amount_units: int, admin_id: int, reason: str, token: str | None = None
    ) -> Transaction:
        """
        إضافة رصيد يدوية من الإدارة (مع مرجع فريد يمنع التكرار عند الضغط المزدوج).

        الاستثناءات:
            InvalidAmountError · DuplicateOperationError
        """
        self._validate_amount(amount_units)
        reference = REF_MANUAL.format(kind="credit", admin_id=admin_id, token=token or new_token(8))
        await self._ensure_new_reference(reference)

        before = await self.repos.users.get_balance_units(user_id)
        if not await self.repos.users.credit(tx, user_id, amount_units):
            raise WalletError(f"تعذر إضافة الرصيد للمستخدم {user_id}")
        after = before + amount_units

        return await self.repos.transactions.insert(
            tx,
            user_id=user_id,
            type=TransactionType.MANUAL_CREDIT,
            amount_units=amount_units,
            balance_before_units=before,
            balance_after_units=after,
            reference=reference,
            description=reason,
            actor_id=admin_id,
        )

    async def manual_debit(
        self, tx: Tx, *, user_id: int, amount_units: int, admin_id: int, reason: str, token: str | None = None
    ) -> Transaction:
        """
        خصم رصيد يدوي من الإدارة (لا يسمح بجعل الرصيد سالباً).

        الاستثناءات:
            InsufficientBalanceError · DuplicateOperationError
        """
        self._validate_amount(amount_units)
        reference = REF_MANUAL.format(kind="debit", admin_id=admin_id, token=token or new_token(8))
        await self._ensure_new_reference(reference)

        before = await self.repos.users.get_balance_units(user_id)
        if not await self.repos.users.try_debit(tx, user_id, amount_units):
            raise InsufficientBalanceError(
                f"رصيد المستخدم {user_id} ({before}) لا يكفي لخصم {amount_units}"
            )
        after = before - amount_units

        return await self.repos.transactions.insert(
            tx,
            user_id=user_id,
            type=TransactionType.MANUAL_DEBIT,
            amount_units=amount_units,
            balance_before_units=before,
            balance_after_units=after,
            reference=reference,
            description=reason,
            actor_id=admin_id,
        )

    async def adjust_balance(
        self, *, target: User, amount_units: int, admin: User, reason: str, credit: bool, token: str | None = None
    ) -> Transaction:
        """
        واجهة عالية المستوى للوحة الأدمن: تفتح معاملتها بنفسها وتُرجع الحركة.

        الاستثناءات: InvalidAmountError · InsufficientBalanceError · DuplicateOperationError
        """
        async with self.db.transaction() as tx:
            if credit:
                transaction = await self.manual_credit(
                    tx, user_id=target.id, amount_units=amount_units,
                    admin_id=admin.id, reason=reason, token=token,
                )
            else:
                transaction = await self.manual_debit(
                    tx, user_id=target.id, amount_units=amount_units,
                    admin_id=admin.id, reason=reason, token=token,
                )
            await self.repos.audit.log(
                tx,
                action="users.balance.credit" if credit else "users.balance.debit",
                admin_id=admin.id,
                target_type="user",
                target_id=target.id,
                before={"balance_units": transaction.balance_before_units},
                after={"balance_units": transaction.balance_after_units},
                details={"reason": reason, "amount_units": amount_units},
            )
        return transaction
```

## `services/notification_service.py`

```python
"""
خدمة الإشعارات (Outbox Pattern).

المبدأ: لا نرسل رسالة تيليجرام أثناء معاملة قاعدة البيانات — بل نضع الإشعار في طابور
داخل نفس المعاملة التي غيّرت الحالة. النتيجة:
    • لا حدث بلا إشعار (لأن الإشعار يُحفظ مع الحدث نفسه).
    • لا إشعار بلا حدث (لأن الإشعار يسقط مع تراجع المعاملة).
    • فشل تيليجرام لا يُسقط العملية المالية إطلاقاً.

الإرسال الفعلي يتم لاحقاً عبر `dispatch_pending` التي يستدعيها job دوري (المرحلة 6)،
وهي تأخذ دالة إرسال من الخارج حتى تبقى هذه الطبقة مستقلة تماماً عن مكتبة تيليجرام.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from core.constants import (
    NOTIF_KEY_MANUAL,
    NOTIF_KEY_ORDER,
    NOTIF_KEY_PAYMENT,
    NOTIF_KEY_TICKET,
)
from core.enums import NotificationType
from core.exceptions import (
    NotificationBlockedError,
    NotificationPermanentError,
    NotificationTemporaryError,
)
from database.database import Database, Tx
from database.models import Notification
from database.repositories import Repositories
from services.settings_service import SettingsService
from utils.logging_setup import get_logger
from utils.security import sanitize

logger = get_logger(__name__)

#: توقيع دالة الإرسال التي تُمرَّر من طبقة تيليجرام
#: تُرجع معرف الرسالة المرسلة (أو None) وترفع أحد استثناءات الإشعارات عند الفشل.
NotificationSender = Callable[[int, str, str], Awaitable[int | None]]


@dataclass(slots=True)
class DispatchReport:
    """حصيلة جولة إرسال واحدة من الطابور."""

    claimed: int = 0
    sent: int = 0
    failed: int = 0
    skipped: int = 0

    def as_dict(self) -> dict[str, int]:
        """تحويل الحصيلة إلى قاموس للتسجيل في اللوق."""
        return {
            "claimed": self.claimed,
            "sent": self.sent,
            "failed": self.failed,
            "skipped": self.skipped,
        }


class NotificationService:
    """إدراج الإشعارات في الطابور وإرسالها لاحقاً بأمان."""

    def __init__(self, db: Database, repos: Repositories, settings: SettingsService) -> None:
        """تهيئة الخدمة."""
        self.db = db
        self.repos = repos
        self.settings = settings

    # ------------------------------- الإدراج ------------------------------ #

    async def enqueue(
        self,
        tx: Tx,
        *,
        user_id: int,
        type: str,
        title: str,
        message: str,
        dedupe_key: str,
        payload: dict[str, Any] | None = None,
    ) -> int | None:
        """
        وضع إشعار في الطابور داخل معاملة قائمة.

        المخرجات: معرف الإشعار، أو None إذا كان `dedupe_key` موجوداً مسبقاً
                  (أي أن الإشعار أُرسل أو مجدول أصلاً — وهذا سلوك مقصود لمنع التكرار).
        """
        import json

        return await self.repos.notifications.enqueue(
            tx,
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            dedupe_key=dedupe_key,
            payload_json=json.dumps(payload, ensure_ascii=False) if payload else None,
        )

    async def notify_order(
        self,
        tx: Tx,
        *,
        user_id: int,
        order_id: int,
        event: str,
        title: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> int | None:
        """إشعار متعلق بطلب، بمفتاح منع تكرار مبني على (الطلب + الحدث)."""
        return await self.enqueue(
            tx,
            user_id=user_id,
            type=event,
            title=title,
            message=message,
            dedupe_key=NOTIF_KEY_ORDER.format(order_id=order_id, event=event),
            payload=payload,
        )

    async def notify_payment(
        self,
        tx: Tx,
        *,
        user_id: int,
        payment_id: int,
        event: str,
        title: str,
        message: str,
    ) -> int | None:
        """إشعار متعلق بطلب شحن."""
        return await self.enqueue(
            tx,
            user_id=user_id,
            type=event,
            title=title,
            message=message,
            dedupe_key=NOTIF_KEY_PAYMENT.format(payment_id=payment_id, event=event),
        )

    async def notify_ticket(
        self, tx: Tx, *, user_id: int, ticket_id: int, event: str, title: str, message: str
    ) -> int | None:
        """إشعار متعلق بتذكرة دعم."""
        return await self.enqueue(
            tx,
            user_id=user_id,
            type=event,
            title=title,
            message=message,
            dedupe_key=NOTIF_KEY_TICKET.format(ticket_id=ticket_id, event=event),
        )

    async def notify_user_manual(
        self, tx: Tx, *, user_id: int, token: str, title: str, message: str, type: str = NotificationType.SYSTEM
    ) -> int | None:
        """إشعار يدوي/عام بمفتاح منع تكرار يحدده المتصل."""
        return await self.enqueue(
            tx,
            user_id=user_id,
            type=type,
            title=title,
            message=message,
            dedupe_key=NOTIF_KEY_MANUAL.format(token=token),
        )

    async def notify_admins(
        self,
        tx: Tx,
        *,
        permission: str,
        token: str,
        title: str,
        message: str,
        type: str = NotificationType.SYSTEM,
    ) -> int:
        """
        إرسال تنبيه لكل من يملك صلاحية معينة (مثل `orders.view` أو `payments.approve`).

        المخرجات: عدد الإشعارات التي أُدرجت فعلاً (المكررة لا تُحتسب).

        ملاحظة: نستخدم الصلاحية لا الدور، حتى يصل التنبيه لمن مُنح الصلاحية استثناءً.
        """
        admins = await self._users_with_permission(permission)
        inserted = 0
        for user_id in admins:
            notification_id = await self.enqueue(
                tx,
                user_id=user_id,
                type=type,
                title=title,
                message=message,
                dedupe_key=NOTIF_KEY_MANUAL.format(token=f"{token}:{user_id}"),
            )
            if notification_id is not None:
                inserted += 1
        return inserted

    async def _users_with_permission(self, permission: str) -> list[int]:
        """
        جلب معرفات المستخدمين الذين يملكون صلاحية محددة (من الدور أو باستثناء فردي).

        يستثني المحظورين ومن حظروا البوت حتى لا نُراكم إشعارات لا تصل.
        """
        rows = await self.db.fetchall(
            """
            SELECT DISTINCT u.id
              FROM users u
              LEFT JOIN role_permissions rp ON rp.role_code = u.role AND rp.permission_code = ?
              LEFT JOIN user_permissions up ON up.user_id = u.id AND up.permission_code = ?
             WHERE u.is_banned = 0
               AND u.blocked_bot = 0
               AND (
                     (rp.permission_code IS NOT NULL AND COALESCE(up.allow, 1) = 1)
                  OR up.allow = 1
                   )
            """,
            (permission, permission),
        )
        return [row["id"] for row in rows]

    # ------------------------------- الإرسال ------------------------------ #

    async def dispatch_pending(
        self, sender: NotificationSender, *, limit: int = 25, lease_seconds: int = 60
    ) -> DispatchReport:
        """
        إرسال دفعة من الإشعارات المنتظرة.

        المدخلات:
            sender : دالة غير متزامنة (telegram_id, title, message) → معرف الرسالة.
                     يجب أن ترفع NotificationBlockedError إذا حظر المستخدم البوت،
                     وNotificationTemporaryError عند فشل قابل لإعادة المحاولة.

        المخرجات: تقرير مختصر بعدد ما أُرسل وفشل وتُخطّي.

        ملاحظة مهمة: الحجز والإرسال والتعليم تتم في معاملات منفصلة قصيرة،
        فلا تبقى قاعدة البيانات مقفولة أثناء انتظار الشبكة.
        """
        report = DispatchReport()

        async with self.db.transaction() as tx:
            batch = await self.repos.notifications.claim_batch(
                tx, limit=limit, lease_seconds=lease_seconds
            )
        report.claimed = len(batch)
        if not batch:
            return report

        for notification in batch:
            telegram_id = await self._telegram_id_for(notification.user_id)
            if telegram_id is None:
                async with self.db.transaction() as tx:
                    await self.repos.notifications.mark_skipped(
                        tx, notification.id, "المستخدم غير موجود"
                    )
                report.skipped += 1
                continue

            try:
                message_id = await sender(telegram_id, notification.title, notification.message)
            except NotificationBlockedError as exc:
                await self._handle_blocked(notification, str(exc))
                report.skipped += 1
            except NotificationTemporaryError as exc:
                async with self.db.transaction() as tx:
                    await self.repos.notifications.mark_failed(
                        tx, notification.id, error=sanitize(str(exc))
                    )
                report.failed += 1
            except NotificationPermanentError as exc:
                async with self.db.transaction() as tx:
                    await self.repos.notifications.mark_failed(
                        tx, notification.id, error=sanitize(str(exc)), permanent=True
                    )
                report.failed += 1
            else:
                async with self.db.transaction() as tx:
                    await self.repos.notifications.mark_sent(tx, notification.id, message_id)
                report.sent += 1

        logger.info("جولة إرسال إشعارات: %s", report.as_dict())
        return report

    async def _handle_blocked(self, notification: Notification, error: str) -> None:
        """تعليم الإشعار كمتخطى وتسجيل أن المستخدم حظر البوت (فلا نزعجه بإشعارات لاحقة)."""
        async with self.db.transaction() as tx:
            await self.repos.notifications.mark_skipped(tx, notification.id, sanitize(error))
            await self.repos.users.set_blocked_bot(tx, notification.user_id, True)
        logger.info("المستخدم %s حظر البوت — تم تخطي الإشعار %s", notification.user_id, notification.id)

    async def _telegram_id_for(self, user_id: int) -> int | None:
        """جلب معرف تيليجرام لمستخدم داخلي."""
        user = await self.repos.users.get_by_id(user_id)
        return user.telegram_id if user else None

    # ------------------------------- القراءة ------------------------------ #

    async def user_inbox(self, user_id: int, *, limit: int = 10, offset: int = 0) -> list[Notification]:
        """آخر إشعارات المستخدم لعرضها داخل البوت."""
        return await self.repos.notifications.list_for_user(user_id, limit=limit, offset=offset)

    async def unread_count(self, user_id: int) -> int:
        """عدد الإشعارات غير المقروءة."""
        return await self.repos.notifications.count_unread(user_id)

    async def mark_all_read(self, user_id: int) -> int:
        """تعليم كل إشعارات المستخدم كمقروءة."""
        async with self.db.transaction() as tx:
            return await self.repos.notifications.mark_read_for_user(tx, user_id)

    async def queued_count(self) -> int:
        """عدد الإشعارات المنتظرة في الطابور (مؤشر صحة النظام)."""
        return await self.repos.notifications.count_queued()
```

## `services/catalog_service.py`

```python
"""
خدمة الكتالوج: التصنيفات والخدمات وحساب سعر الطلب قبل تأكيده.

مبدأ مهم: سعر الخدمة يُقرأ من قاعدة البيانات في لحظة الطلب ويُخزَّن كلقطة داخل الطلب،
فتغيير السعر لاحقاً لا يؤثر على الطلبات القديمة ولا على المحاسبة.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.constants import PAGE_SIZE
from core.exceptions import ServiceNotAvailableError
from core.money import format_units, order_cost_units, unit_price_units
from core.permissions import Permission
from database.database import Database
from database.models import Service, ServiceCategory, User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.settings_service import SettingsService
from utils.logging_setup import get_logger
from utils.validators import clean_text, validate_quantity

logger = get_logger(__name__)


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

    async def unit_price(self, service: Service) -> str:
        """سعر الوحدة الواحدة (للعرض التفصيلي)."""
        _, symbol, decimals = await self.settings.currency()
        price = unit_price_units(service.price_per_1000_units)
        return f"{price:.6f} {symbol}".strip()

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
    ) -> Service:
        """
        إضافة خدمة جديدة للكتالوج.

        الاستثناءات: PermissionDeniedError · ValidationError
        """
        await self.auth.require_permission(actor, Permission.SERVICES_CREATE, context="service.create")
        clean_name = clean_text(name, field="اسم الخدمة", max_length=120, min_length=3)
        async with self.db.transaction() as tx:
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
                },
            )
        logger.info("أضاف الأدمن %s الخدمة %s (%s)", actor.id, service.id, clean_name)
        return service

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
```

## `services/provider_service.py`

```python
"""
خدمة المزودين: إدارة بياناتهم، وتشفير مفاتيحهم، والاتصال بهم بأمان.

قواعد صارمة:
    • مفتاح API يُخزَّن مشفّراً، ولا يُفك إلا لحظة الاستدعاء داخل هذه الخدمة.
    • لا يظهر المفتاح في أي سجل أو رسالة خطأ (كل النصوص تمر على `sanitize`).
    • كل استدعاء خارجي يُسجَّل في `provider_requests` بنجاحه أو فشله ومدته.
    • قاطع دائرة: بعد عدد أخطاء متتالية يُعطَّل المزود مؤقتاً ويُنبَّه الأدمن.
    • لا تُفتح معاملة قاعدة بيانات أثناء انتظار الشبكة.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from core.enums import ProviderAction
from core.exceptions import (
    ProviderError,
    ProviderPermanentError,
    ProviderTemporaryError,
    ProviderUncertainError,
)
from core.permissions import Permission
from database.database import Database
from database.models import Order, Provider, Service, User
from database.repositories import Repositories
from integrations.providers.base import (
    ProviderBalance,
    ProviderClient,
    ProviderOrderResult,
    ProviderServiceItem,
    ProviderStatusResult,
)
from integrations.providers.registry import create_client, is_supported
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.notification_service import NotificationService
from services.settings_service import SettingsService
from texts import templates
from utils.datetime_utils import is_past, iso_plus_seconds
from utils.logging_setup import get_logger
from utils.security import SecretBox, secret_hint
from utils.validators import clean_text, validate_url

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    """حالة صحة مزود كما تُعرض في لوحة الأدمن."""

    provider: Provider
    is_usable: bool
    reason: str


class ProviderService:
    """كل تعامل مع مزودي الخدمات يمر من هنا."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        audit: AuditService,
        auth: AuthService,
        notifications: NotificationService,
        secret_box: SecretBox,
    ) -> None:
        """تهيئة الخدمة مع صندوق التشفير المسؤول عن مفاتيح المزودين."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.audit = audit
        self.auth = auth
        self.notifications = notifications
        self.secret_box = secret_box

    # ------------------------------- القراءة ------------------------------ #

    async def get(self, provider_id: int) -> Provider | None:
        """جلب مزود بالمعرف."""
        return await self.repos.providers.get(provider_id)

    async def list_all(self, *, active_only: bool = False) -> list[Provider]:
        """قائمة المزودين (كلهم أو المفعّلون فقط)."""
        return await self.repos.providers.list_all(active_only=active_only)

    async def health(self, provider: Provider) -> ProviderHealth:
        """
        تقييم جاهزية المزود للاستخدام الآن.

        المخرجات: كائن يوضح هل يمكن الإرسال إليه ولماذا لا، بصيغة عربية للعرض.
        """
        if not provider.is_active:
            return ProviderHealth(provider, False, "المزود معطّل يدوياً")
        if provider.disabled_until and not is_past(provider.disabled_until):
            return ProviderHealth(provider, False, "المزود موقوف مؤقتاً بعد أخطاء متتالية")
        if not is_supported(provider.api_type):
            return ProviderHealth(provider, False, f"نوع API غير مدعوم: {provider.api_type}")
        return ProviderHealth(provider, True, "جاهز")

    async def is_usable(self, provider: Provider) -> bool:
        """هل يمكن إرسال طلبات لهذا المزود الآن؟"""
        return (await self.health(provider)).is_usable

    # ------------------------------ الإدارة ------------------------------- #

    async def create_provider(
        self,
        actor: User,
        *,
        name: str,
        api_url: str,
        api_key: str,
        api_type: str = "perfect_panel",
        currency: str = "USD",
        timeout_seconds: int = 30,
    ) -> Provider:
        """
        إضافة مزود جديد مع تشفير مفتاحه قبل التخزين.

        الاستثناءات: PermissionDeniedError · ValidationError · EncryptionError
        """
        await self.auth.require_permission(actor, Permission.PROVIDERS_CREATE, context="provider.create")
        clean_name = clean_text(name, field="اسم المزود", max_length=60, min_length=2)
        clean_gateway = validate_url(api_url)
        key = (api_key or "").strip()
        if len(key) < 8:
            raise ProviderError(
                "مفتاح API قصير جداً", user_message="❌ مفتاح API غير صالح."
            )

        async with self.db.transaction() as tx:
            provider = await self.repos.providers.create(
                tx,
                name=clean_name,
                api_url=clean_gateway,
                api_key_enc=self.secret_box.encrypt(key),
                api_key_hint=secret_hint(key),
                api_type=api_type,
                currency=currency,
                timeout_seconds=timeout_seconds,
            )
            await self.audit.log(
                tx,
                action="providers.create",
                admin_id=actor.id,
                target_type="provider",
                target_id=provider.id,
                after={"name": clean_name, "api_url": clean_gateway, "api_type": api_type},
            )
        logger.info("أضاف الأدمن %s المزود %s (%s)", actor.id, provider.id, clean_name)
        return provider

    async def update_api_key(self, actor: User, provider_id: int, new_key: str) -> bool:
        """
        تحديث مفتاح API لمزود (يُخزَّن مشفّراً، ولا يُسجَّل في أي مكان).

        الاستثناءات: PermissionDeniedError · ProviderError
        """
        await self.auth.require_permission(
            actor, Permission.PROVIDERS_KEY_UPDATE, context=f"provider:{provider_id}"
        )
        key = (new_key or "").strip()
        if len(key) < 8:
            raise ProviderError("مفتاح API قصير جداً", user_message="❌ مفتاح API غير صالح.")

        async with self.db.transaction() as tx:
            changed = await self.repos.providers.update_fields(
                tx,
                provider_id,
                api_key_enc=self.secret_box.encrypt(key),
                api_key_hint=secret_hint(key),
            )
            if changed:
                # لا نُسجّل المفتاح نفسه — فقط أن التغيير حدث ومن نفّذه
                await self.audit.log(
                    tx,
                    action="providers.key.update",
                    admin_id=actor.id,
                    target_type="provider",
                    target_id=provider_id,
                    after={"api_key_hint": secret_hint(key)},
                )
        return changed

    async def set_active(self, actor: User, provider_id: int, active: bool) -> bool:
        """تفعيل أو تعطيل مزود يدوياً."""
        await self.auth.require_permission(
            actor, Permission.PROVIDERS_UPDATE, context=f"provider:{provider_id}"
        )
        async with self.db.transaction() as tx:
            changed = await self.repos.providers.set_active(tx, provider_id, active)
            if changed:
                await self.audit.log(
                    tx,
                    action="providers.update",
                    admin_id=actor.id,
                    target_type="provider",
                    target_id=provider_id,
                    after={"is_active": active},
                )
        return changed

    # ------------------------------ الاتصال ------------------------------- #

    def client_for(self, provider: Provider) -> ProviderClient:
        """
        بناء عميل اتصال للمزود بعد فك تشفير مفتاحه.

        الاستثناءات:
            EncryptionError : المفتاح المخزَّن لا يُفك بمفتاح التشفير الحالي.
            ProviderError   : نوع API غير مدعوم.
        """
        api_key = self.secret_box.decrypt(provider.api_key_enc)
        return create_client(
            api_type=provider.api_type,
            api_url=provider.api_url,
            api_key=api_key,
            timeout_seconds=provider.timeout_seconds,
        )

    async def _log_request(
        self,
        *,
        provider: Provider,
        action: str,
        is_success: bool,
        started: float,
        request_summary: str,
        response_snippet: str,
        error_type: str | None = None,
        order_id: int | None = None,
        secrets: tuple[str, ...] = (),
    ) -> None:
        """تسجيل استدعاء المزود في قاعدة البيانات بعد تنقيته من الأسرار."""
        duration_ms = int((time.monotonic() - started) * 1000)
        async with self.db.transaction() as tx:
            await self.repos.provider_requests.log(
                tx,
                provider_id=provider.id,
                action=action,
                is_success=is_success,
                order_id=order_id,
                request_summary=request_summary,
                response_snippet=response_snippet,
                duration_ms=duration_ms,
                error_type=error_type,
                secrets=secrets,
            )

    async def _record_success(self, provider: Provider) -> None:
        """تصفير عدّاد الأخطاء بعد نجاح الاتصال."""
        async with self.db.transaction() as tx:
            await self.repos.providers.record_success(tx, provider.id)

    async def _record_failure(self, provider: Provider, error: str) -> int:
        """
        تسجيل خطأ متتالٍ، وتعطيل المزود مؤقتاً عند بلوغ الحد، مع تنبيه الأدمن.

        المخرجات: عدد الأخطاء المتتالية بعد هذا الخطأ.
        """
        threshold = await self.settings.get_int("provider_failure_threshold", 5)
        disable_minutes = await self.settings.get_int("provider_disable_minutes", 15)

        async with self.db.transaction() as tx:
            current = await self.repos.providers.record_failure(tx, provider.id, error)
            if current >= threshold:
                await self.repos.providers.update_fields(
                    tx, provider.id, disabled_until=iso_plus_seconds(disable_minutes * 60)
                )
                title, message = templates.admin_provider_disabled(
                    provider_name=provider.name, failures=current, minutes=disable_minutes
                )
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.PROVIDERS_VIEW,
                    token=f"provider:{provider.id}:disabled:{current}",
                    title=title,
                    message=message,
                )
                logger.error(
                    "تعطيل مؤقت للمزود %s بعد %s أخطاء متتالية", provider.name, current
                )
        return current

    # ------------------------------ العمليات ------------------------------ #

    async def submit_order(self, provider: Provider, service: Service, order: Order) -> ProviderOrderResult:
        """
        إرسال طلب إلى المزود.

        المخرجات: نتيجة فيها رقم الطلب عند المزود.

        الاستثناءات:
            ProviderTemporaryError  : فشل مؤقت — يُعاد المحاولة لاحقاً.
            ProviderUncertainError  : نتيجة غير مؤكدة — ممنوع إعادة الإرسال آلياً.
            ProviderPermanentError  : رفض نهائي — فشل الطلب واسترجاع المبلغ.
        """
        client = self.client_for(provider)
        summary = f"add service={service.provider_service_id} quantity={order.quantity} link={order.link}"
        started = time.monotonic()
        try:
            result = await client.add_order(
                provider_service_id=service.provider_service_id,
                link=order.link,
                quantity=order.quantity,
            )
        except ProviderUncertainError as exc:
            await self._log_request(
                provider=provider, action=ProviderAction.ADD, is_success=False, started=started,
                request_summary=summary, response_snippet=str(exc),
                error_type=type(exc).__name__, order_id=order.id, secrets=client.secrets(),
            )
            await self._record_failure(provider, str(exc))
            raise
        except ProviderError as exc:
            await self._log_request(
                provider=provider, action=ProviderAction.ADD, is_success=False, started=started,
                request_summary=summary, response_snippet=str(exc),
                error_type=type(exc).__name__, order_id=order.id, secrets=client.secrets(),
            )
            await self._record_failure(provider, str(exc))
            raise
        finally:
            await client.close()

        if not result.provider_order_id:
            raise ProviderPermanentError("المزود لم يُرجع رقم طلب صالحاً")

        await self._log_request(
            provider=provider, action=ProviderAction.ADD, is_success=True, started=started,
            request_summary=summary, response_snippet=str(result.raw)[:500],
            order_id=order.id, secrets=client.secrets(),
        )
        await self._record_success(provider)
        return result

    async def fetch_status(self, provider: Provider, order: Order) -> ProviderStatusResult:
        """
        الاستعلام عن حالة طلب لدى المزود.

        الاستثناءات: ProviderTemporaryError · ProviderPermanentError
        """
        if not order.provider_order_id:
            raise ProviderPermanentError(f"الطلب #{order.id} بلا رقم عند المزود")

        client = self.client_for(provider)
        started = time.monotonic()
        try:
            result = await client.get_order_status(order.provider_order_id)
        except ProviderError as exc:
            await self._log_request(
                provider=provider, action=ProviderAction.STATUS, is_success=False, started=started,
                request_summary=f"status order={order.provider_order_id}", response_snippet=str(exc),
                error_type=type(exc).__name__, order_id=order.id, secrets=client.secrets(),
            )
            await self._record_failure(provider, str(exc))
            raise
        finally:
            await client.close()

        await self._log_request(
            provider=provider, action=ProviderAction.STATUS, is_success=True, started=started,
            request_summary=f"status order={order.provider_order_id}",
            response_snippet=str(result.raw)[:500], order_id=order.id, secrets=client.secrets(),
        )
        await self._record_success(provider)
        return result

    async def check_balance(self, provider: Provider) -> ProviderBalance:
        """
        قراءة رصيدنا لدى المزود وتحديثه في قاعدة البيانات مع لقطة تاريخية.

        يُرسل تنبيهاً للأدمن إذا نزل الرصيد تحت الحد المحدد.
        """
        client = self.client_for(provider)
        started = time.monotonic()
        try:
            balance = await client.get_balance()
        except ProviderError as exc:
            await self._log_request(
                provider=provider, action=ProviderAction.BALANCE, is_success=False, started=started,
                request_summary="balance", response_snippet=str(exc),
                error_type=type(exc).__name__, secrets=client.secrets(),
            )
            await self._record_failure(provider, str(exc))
            raise
        finally:
            await client.close()

        async with self.db.transaction() as tx:
            await self.repos.providers.update_balance(
                tx, provider.id, balance.amount_units, currency=balance.currency
            )
            await self.repos.providers.add_balance_snapshot(
                tx, provider.id, balance.amount_units, currency=balance.currency
            )

        threshold = provider.low_balance_threshold_units or await self.settings.get_int(
            "provider_low_balance_alert_units", 0
        )
        if threshold and balance.amount_units < threshold:
            symbol = await self.settings.money_symbol()
            title, message = templates.admin_provider_low_balance(
                provider_name=provider.name, balance_units=balance.amount_units, symbol=symbol
            )
            async with self.db.transaction() as tx:
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.PROVIDERS_VIEW,
                    token=f"provider:{provider.id}:low:{balance.amount_units}",
                    title=title,
                    message=message,
                )

        await self._log_request(
            provider=provider, action=ProviderAction.BALANCE, is_success=True, started=started,
            request_summary="balance", response_snippet=f"amount_units={balance.amount_units}",
            secrets=client.secrets(),
        )
        await self._record_success(provider)
        return balance

    async def fetch_services(self, actor: User, provider: Provider) -> list[ProviderServiceItem]:
        """
        جلب قائمة خدمات المزود (تمهيداً للاستيراد في المرحلة 5).

        الاستثناءات: PermissionDeniedError · ProviderError
        """
        await self.auth.require_permission(
            actor, Permission.SERVICES_SYNC, context=f"provider:{provider.id}"
        )
        client = self.client_for(provider)
        started = time.monotonic()
        try:
            items = await client.get_services()
        except ProviderError as exc:
            await self._log_request(
                provider=provider, action=ProviderAction.SERVICES, is_success=False, started=started,
                request_summary="services", response_snippet=str(exc),
                error_type=type(exc).__name__, secrets=client.secrets(),
            )
            await self._record_failure(provider, str(exc))
            raise
        finally:
            await client.close()

        await self._log_request(
            provider=provider, action=ProviderAction.SERVICES, is_success=True, started=started,
            request_summary="services", response_snippet=f"count={len(items)}", secrets=client.secrets(),
        )
        await self._record_success(provider)
        return items

    async def test_connection(self, actor: User, provider_id: int) -> tuple[bool, str]:
        """
        اختبار اتصال المزود من لوحة الأدمن.

        المخرجات: (نجح؟، رسالة عربية للعرض) — لا تحتوي الرسالة أي سر.
        """
        await self.auth.require_permission(
            actor, Permission.PROVIDERS_TEST, context=f"provider:{provider_id}"
        )
        provider = await self.repos.providers.get(provider_id)
        if provider is None:
            return False, "المزود غير موجود."
        try:
            balance = await self.check_balance(provider)
        except ProviderTemporaryError as exc:
            return False, f"فشل مؤقت في الاتصال: {exc.user_message}"
        except ProviderError as exc:
            return False, f"فشل الاتصال: {exc.user_message}"
        symbol = provider.currency or "USD"
        return True, f"الاتصال ناجح ✅ — الرصيد: {balance.amount_units / 10_000:.4f} {symbol}"
```

## `services/order_service.py`

```python
"""
خدمة الطلبات — قلب النظام.

المسؤوليات:
    • إنشاء الطلب: تحقق كامل ثم خصم الرصيد وإنشاء الطلب وإشعار المستخدم في معاملة واحدة.
    • إرسال الطلبات للمزود عبر عمّال (workers) مع حجز آمن يمنع المعالجة المزدوجة.
    • متابعة الحالة دورياً حتى الحالة النهائية.
    • الاسترجاع الآمن عند الفشل أو الإلغاء أو التنفيذ الجزئي.
    • أدوات الأدمن: إلغاء، ربط رقم مزود، تأكيد فشل، تجاوز حالة (مع تدقيق إجباري).

قواعد لا تُكسر:
    • كل تغيير حالة يمر عبر `core.order_state` (جدول انتقالات) **و** تحديث مشروط في
      قاعدة البيانات (`expected_statuses`) — فلا سباق ولا كتابة فوق عمل جهة أخرى.
    • كل استرجاع يمر عبر `WalletService` ويُسجَّل كحركة مالية بمرجع فريد.
    • لا إعادة إرسال تلقائي عند نتيجة غير مؤكدة (منعاً لطلب مزدوج عند المزود).
    • لا تُفتح معاملة قاعدة بيانات أثناء انتظار شبكة المزود.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.constants import MAX_SUBMIT_ATTEMPTS, ORDER_CHECK_BACKOFF, ORDER_LOCK_SECONDS
from core.enums import ActorType, NotificationType, OrderStatus
from core.exceptions import (
    DuplicateOperationError,
    InvalidStateTransitionError,
    OrderError,
    ProviderError,
    ProviderInsufficientFundsError,
    ProviderPermanentError,
    ProviderTemporaryError,
    ProviderUncertainError,
    RateLimitedError,
    ServiceNotAvailableError,
    ValidationError,
)
from core.money import format_units, partial_refund_units
from core.order_state import (
    assert_transition,
    can_transition,
    is_final,
    map_provider_status,
)
from core.permissions import Permission
from database.database import Database, Tx
from database.models import Order, Provider, Service, User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.catalog_service import CatalogService
from services.notification_service import NotificationService
from services.provider_service import ProviderService
from services.settings_service import SettingsService
from services.wallet_service import WalletService
from texts import templates
from utils.datetime_utils import day_bounds_utc, iso_minus_days, iso_plus_seconds, parse_iso, utc_now
from utils.logging_setup import get_logger
from utils.security import new_token, sanitize
from utils.validators import validate_link

logger = get_logger(__name__)


@dataclass(slots=True)
class BatchReport:
    """حصيلة جولة معالجة (إرسال أو فحص حالات)."""

    claimed: int = 0
    succeeded: int = 0
    retried: int = 0
    failed: int = 0
    uncertain: int = 0
    unchanged: int = 0
    completed: int = 0
    details: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, int]:
        """تحويل الحصيلة إلى قاموس للتسجيل."""
        return {
            "claimed": self.claimed,
            "succeeded": self.succeeded,
            "retried": self.retried,
            "failed": self.failed,
            "uncertain": self.uncertain,
            "unchanged": self.unchanged,
            "completed": self.completed,
        }


class OrderService:
    """دورة حياة الطلب كاملة من الإنشاء حتى الحالة النهائية."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        wallet: WalletService,
        catalog: CatalogService,
        providers: ProviderService,
        notifications: NotificationService,
        audit: AuditService,
        auth: AuthService,
    ) -> None:
        """تهيئة الخدمة بكل الاعتماديات التي تحتاجها."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.wallet = wallet
        self.catalog = catalog
        self.providers = providers
        self.notifications = notifications
        self.audit = audit
        self.auth = auth

    # ===================================================================== #
    #                              الإنشاء                                  #
    # ===================================================================== #

    async def create_order(
        self,
        user: User,
        *,
        service_id: int,
        link: str,
        quantity: str | int,
        client_request_id: str | None = None,
    ) -> Order:
        """
        إنشاء طلب جديد: تحقق كامل ← خصم الرصيد ← إنشاء الطلب ← إشعار — كلها معاملة واحدة.

        المدخلات:
            client_request_id : مفتاح المستخدم لمنع التكرار عند الضغط المزدوج.
                                إذا تكرر نفس المفتاح يُعاد الطلب الأول نفسه دون خصم جديد.

        المخرجات: الطلب بعد إنشائه (حالته `pending`).

        الاستثناءات:
            UserBannedError · MaintenanceModeError : الحساب محظور أو النظام في صيانة.
            ServiceNotAvailableError               : الخدمة أو مزودها غير متاح.
            QuantityOutOfRangeError · InvalidLinkError · InvalidAmountError
            RateLimitedError                       : تجاوز الحد اليومي للطلبات.
            DuplicateOperationError                : طلب مطابق خلال نافذة التكرار.
            InsufficientBalanceError               : الرصيد لا يكفي (لا يُنشأ الطلب أصلاً).
        """
        await self.auth.guard(user)

        # 1) مفتاح منع التكرار: إن تكرر نفس المفتاح نُعيد الطلب الأصلي دون أي خصم جديد
        request_id = (client_request_id or f"u{user.id}:{new_token(8)}").strip()[:64]
        existing = await self.repos.orders.get_by_client_request_id(request_id)
        if existing is not None:
            logger.info("إعادة استخدام الطلب %s لنفس مفتاح الطلب %s", existing.id, request_id)
            return existing

        # 2) الخدمة والمزود
        service = await self.catalog.get_available_service(service_id)
        provider = await self.repos.providers.get(service.provider_id)
        if provider is None:
            raise ServiceNotAvailableError(f"مزود الخدمة {service_id} غير موجود")
        health = await self.providers.health(provider)
        if not health.is_usable:
            raise ServiceNotAvailableError(
                f"المزود {provider.name} غير متاح: {health.reason}",
                user_message="❌ هذه الخدمة متوقفة مؤقتاً. جرّب لاحقاً.",
            )

        # 3) الرابط والكمية والتكلفة
        clean_link = validate_link(link, pattern=service.link_pattern)
        quote = await self.catalog.quote(service, quantity)

        symbol = await self.settings.money_symbol()
        min_order_units = await self.settings.get_money_units("min_order_amount_units", 0)
        if min_order_units and quote.cost_units < min_order_units:
            raise ValidationError(
                f"قيمة الطلب {quote.cost_units} أقل من الحد الأدنى {min_order_units}",
                user_message=(
                    "❌ الحد الأدنى لقيمة الطلب هو "
                    f"{format_units(min_order_units, symbol=symbol)}."
                ),
            )

        # 4) الحدود اليومية ومنع الطلب المكرر
        await self._check_daily_limit(user)
        await self._check_duplicate(user, service.id, clean_link, quote.quantity)

        # 5) المعاملة الذرّية: إنشاء + خصم + سجل + إشعار
        async with self.db.transaction() as tx:
            order = await self.repos.orders.create(
                tx,
                user_id=user.id,
                service_id=service.id,
                provider_id=provider.id,
                service_name_snapshot=service.name,
                price_per_1000_snapshot_units=service.price_per_1000_units,
                link=clean_link,
                quantity=quote.quantity,
                cost_units=quote.cost_units,
                client_request_id=request_id,
                provider_cost_units=self._provider_cost(service, quote.quantity),
            )
            public_code = f"ORD-{order.id:06d}"
            await self.repos.orders.update_fields(tx, order.id, public_code=public_code)

            await self.wallet.charge_for_order(
                tx,
                user_id=user.id,
                order_id=order.id,
                amount_units=quote.cost_units,
                description=f"طلب {service.name} × {quote.quantity}",
            )

            await self.repos.orders.add_history(
                tx,
                order_id=order.id,
                from_status=None,
                to_status=OrderStatus.PENDING,
                actor_type=ActorType.USER,
                actor_id=user.id,
                reason="إنشاء الطلب",
            )

            title, message = templates.order_created(
                code=public_code,
                service_name=service.name,
                quantity=quote.quantity,
                cost_units=quote.cost_units,
                symbol=symbol,
            )
            await self.notifications.notify_order(
                tx,
                user_id=user.id,
                order_id=order.id,
                event=NotificationType.ORDER_CREATED,
                title=title,
                message=message,
                payload={"order_id": order.id, "cost_units": quote.cost_units},
            )

        created = await self.repos.orders.get(order.id)
        if created is None:  # لا يحدث عملياً، لكن لا نُرجع قيمة غير مؤكدة أبداً
            raise OrderError(f"تعذر قراءة الطلب {order.id} بعد إنشائه")
        logger.info(
            "أنشأ المستخدم %s الطلب %s (%s × %s) بتكلفة %s",
            user.id, created.id, service.name, quote.quantity, quote.cost_units,
        )
        return created

    def _provider_cost(self, service: Service, quantity: int) -> int | None:
        """حساب تكلفة الطلب علينا لدى المزود (للأرباح) إن كان سعر المزود معروفاً."""
        if not service.provider_price_per_1000_units:
            return None
        return (service.provider_price_per_1000_units * quantity + 500) // 1000

    async def _check_daily_limit(self, user: User) -> None:
        """
        التأكد من عدم تجاوز الحد اليومي لعدد الطلبات.

        الاستثناءات: RateLimitedError عند التجاوز.
        """
        max_per_day = await self.settings.get_int("max_orders_per_day", 0)
        if max_per_day <= 0:
            return
        start_today, _ = day_bounds_utc(0)
        today_count = await self.repos.orders.count_today_by_user(user.id, start_today)
        if today_count >= max_per_day:
            raise RateLimitedError(
                f"المستخدم {user.id} تجاوز {max_per_day} طلباً اليوم",
                user_message=f"⏳ وصلت إلى الحد اليومي ({max_per_day} طلب). حاول غداً.",
            )

    async def _check_duplicate(self, user: User, service_id: int, link: str, quantity: int) -> None:
        """
        منع إنشاء طلب مطابق تماماً خلال نافذة زمنية قصيرة (ضغط مزدوج أو خطأ).

        الاستثناءات: DuplicateOperationError عند وجود طلب مطابق حديث.
        """
        window_minutes = await self.settings.get_int("duplicate_order_window_minutes", 0)
        if window_minutes <= 0:
            return
        since = iso_plus_seconds(-window_minutes * 60)
        duplicate = await self.repos.orders.find_recent_duplicate(
            user_id=user.id, service_id=service_id, link=link, quantity=quantity, since_iso=since
        )
        if duplicate is not None:
            raise DuplicateOperationError(
                f"طلب مكرر خلال {window_minutes} دقيقة (الطلب {duplicate.id})",
                user_message=(
                    f"⚠️ لديك طلب مطابق قبل قليل ({duplicate.public_code or duplicate.id}). "
                    f"إن كنت تريد طلباً إضافياً انتظر {window_minutes} دقيقة."
                ),
            )

    # ===================================================================== #
    #                        أدوات تغيير الحالة                             #
    # ===================================================================== #

    async def _transition(
        self,
        tx: Tx,
        order: Order,
        new_status: str,
        *,
        actor_type: str,
        actor_id: int | None = None,
        reason: str | None = None,
        extra: dict | None = None,
        provider_status_raw: str | None = None,
    ) -> bool:
        """
        تنفيذ انتقال حالة واحد: تحقق من الجدول ثم تحديث مشروط ثم تسجيل في التاريخ.

        المخرجات: True إذا تم التغيير فعلاً، False إذا سبقتنا جهة أخرى لتغيير الحالة
                  (وهذا ليس خطأً — بل الحماية من السباق تعمل).

        الاستثناءات:
            InvalidStateTransitionError : الانتقال ممنوع في جدول الحالات.
        """
        assert_transition(order.status, new_status, order_id=order.id)
        if order.status == new_status:
            return False  # لا تغيير فعلي

        changed = await self.repos.orders.update_status(
            tx,
            order.id,
            new_status=new_status,
            expected_statuses=[order.status],
            extra_fields=extra,
        )
        if not changed:
            logger.warning(
                "تجاهل انتقال الطلب %s (%s ← %s): تغيّرت حالته من جهة أخرى",
                order.id, order.status, new_status,
            )
            return False

        await self.repos.orders.add_history(
            tx,
            order_id=order.id,
            from_status=order.status,
            to_status=new_status,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            provider_status_raw=provider_status_raw,
        )
        return True

    async def _refund_full(
        self, tx: Tx, order: Order, *, reason: str, actor_type: str, actor_id: int | None = None
    ) -> int:
        """
        استرجاع كامل المبلغ المتبقي للطلب ثم نقله إلى الحالة `refunded`.

        المخرجات: المبلغ المسترجع فعلياً (قد يكون صفراً إن سبق استرجاعه بالكامل).
        """
        remaining = order.refundable_units
        if remaining <= 0:
            return 0

        transaction = await self.wallet.refund_order(
            tx,
            user_id=order.user_id,
            order_id=order.id,
            amount_units=remaining,
            partial=False,
            description=f"استرجاع كامل: {reason}",
        )
        if transaction is None:
            return 0

        fresh = await self.repos.orders.get(order.id)
        if fresh is not None and can_transition(fresh.status, OrderStatus.REFUNDED):
            await self._transition(
                tx, fresh, OrderStatus.REFUNDED,
                actor_type=actor_type, actor_id=actor_id, reason=reason,
                extra={"refunded_at": self.repos.orders.now()},
            )
        return remaining

    async def _fail_order(
        self,
        order: Order,
        *,
        reason: str,
        actor_type: str = ActorType.SYSTEM,
        actor_id: int | None = None,
        notify_admins: bool = True,
        auto_refund: bool | None = None,
    ) -> int:
        """
        المسار الكامل لفشل طلب: تغيير الحالة ← استرجاع كامل ← إشعار المستخدم والأدمن.

        المدخلات:
            auto_refund : None تعني «اتبع الإعداد `auto_refund_on_provider_fail`»،
                          وTrue تفرض الاسترجاع (إجراء أدمن صريح).
                          عند تعطيل الاسترجاع التلقائي يبقى المال محجوزاً ويُنبَّه الأدمن
                          لتنفيذ الاسترجاع يدوياً — ولا يُفقد مال المستخدم في الحالتين.

        المخرجات: المبلغ المسترجع (صفر إذا كان الاسترجاع التلقائي معطّلاً).
        """
        symbol = await self.settings.money_symbol()
        clean_reason = sanitize(reason)[:300]
        if auto_refund is None:
            auto_refund = await self.settings.get_bool("auto_refund_on_provider_fail", True)
        refunded = 0

        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None or is_final(current.status):
                return 0

            moved = await self._transition(
                tx, current, OrderStatus.FAILED,
                actor_type=actor_type, actor_id=actor_id, reason=clean_reason,
                extra={"last_error": clean_reason, "locked_by": None, "locked_until": None},
            )
            if not moved:
                return 0

            failed_order = await self.repos.orders.get(order.id)
            if failed_order is None:
                return 0
            if auto_refund:
                refunded = await self._refund_full(
                    tx, failed_order, reason=clean_reason, actor_type=actor_type, actor_id=actor_id
                )

            code = current.public_code or f"#{current.id}"
            title, message = templates.order_failed(
                code=code, reason=clean_reason, refund_units=refunded, symbol=symbol
            )
            await self.notifications.notify_order(
                tx,
                user_id=current.user_id,
                order_id=current.id,
                event=NotificationType.ORDER_FAILED,
                title=title,
                message=message,
            )
            if notify_admins or not auto_refund:
                admin_reason = clean_reason if auto_refund else (
                    f"{clean_reason} — ⚠️ الاسترجاع التلقائي معطّل، نفّذ الاسترجاع يدوياً"
                )
                admin_title, admin_message = templates.admin_order_failed(
                    code=code, order_id=current.id, reason=admin_reason,
                    refund_units=refunded, symbol=symbol,
                )
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.ORDERS_VIEW,
                    token=f"order:{current.id}:failed",
                    title=admin_title,
                    message=admin_message,
                )
            await self.repos.error_logs.log(
                tx,
                message=f"فشل الطلب #{current.id}: {clean_reason}",
                level="ERROR",
                source="order_service",
                error_type="OrderFailed",
                user_id=current.user_id,
            )
        logger.error("فشل الطلب %s: %s (استُرجع %s)", order.id, clean_reason, refunded)
        return refunded

    # ===================================================================== #
    #                        إرسال الطلبات للمزود                           #
    # ===================================================================== #

    async def process_pending_orders(self, *, worker: str = "submitter", limit: int = 5) -> BatchReport:
        """
        حجز دفعة من الطلبات المعلّقة وإرسالها إلى المزود.

        تُستدعى من job دوري. الحجز يمنع أن يعالج عاملان الطلب نفسه.
        """
        report = BatchReport()
        async with self.db.transaction() as tx:
            claimed = await self.repos.orders.claim_pending_for_submit(
                tx, worker=worker, limit=limit, lock_seconds=ORDER_LOCK_SECONDS
            )
        report.claimed = len(claimed)

        for order in claimed:
            outcome = await self._submit_one(order)
            if outcome == "submitted":
                report.succeeded += 1
            elif outcome == "retry":
                report.retried += 1
            elif outcome == "uncertain":
                report.uncertain += 1
            elif outcome == "failed":
                report.failed += 1
            else:
                report.unchanged += 1

        if report.claimed:
            logger.info("جولة إرسال الطلبات: %s", report.as_dict())
        return report

    async def _submit_one(self, order: Order) -> str:
        """
        إرسال طلب واحد إلى المزود ومعالجة كل النتائج الممكنة.

        المخرجات: وصف مختصر للنتيجة: submitted / retry / uncertain / failed / skipped.
        """
        service = await self.repos.services.get(order.service_id)
        provider = await self.repos.providers.get(order.provider_id)
        if service is None or provider is None:
            await self._fail_order(order, reason="بيانات الخدمة أو المزود غير موجودة")
            return "failed"

        health = await self.providers.health(provider)
        if not health.is_usable:
            await self._requeue(order, reason=f"المزود غير متاح: {health.reason}", delay_seconds=300)
            return "retry"

        try:
            result = await self.providers.submit_order(provider, service, order)
        except ProviderInsufficientFundsError as exc:
            await self._handle_insufficient_provider_funds(order, provider, str(exc))
            return "retry"
        except ProviderUncertainError as exc:
            await self._mark_uncertain(order, str(exc))
            return "uncertain"
        except ProviderPermanentError as exc:
            await self._fail_order(order, reason=f"رفض المزود الطلب: {exc}")
            return "failed"
        except ProviderTemporaryError as exc:
            if order.submit_attempts >= MAX_SUBMIT_ATTEMPTS:
                await self._fail_order(
                    order, reason=f"تعذر الإرسال بعد {order.submit_attempts} محاولات: {exc}"
                )
                return "failed"
            await self._requeue(order, reason=str(exc), delay_seconds=60 * order.submit_attempts)
            return "retry"
        except ProviderError as exc:
            # أي خطأ مزود غير مصنّف يُعامل معاملة الخطأ النهائي حفاظاً على مال المستخدم
            await self._fail_order(order, reason=f"خطأ غير متوقع من المزود: {exc}")
            return "failed"

        # نجاح: تسجيل رقم الطلب عند المزود والانتقال إلى submitted
        now = self.repos.orders.now()
        check_interval = await self.settings.get_int("order_check_interval_seconds", 120)
        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None:
                return "skipped"
            moved = await self._transition(
                tx, current, OrderStatus.SUBMITTED,
                actor_type=ActorType.JOB,
                reason="قبل المزود الطلب",
                extra={
                    "provider_order_id": result.provider_order_id,
                    "provider_cost_units": result.charge_units if result.charge_units else current.provider_cost_units,
                    "submitted_at": now,
                    "next_check_at": iso_plus_seconds(check_interval),
                    "locked_by": None,
                    "locked_until": None,
                    "last_error": None,
                },
            )
            if moved:
                title, message = templates.order_submitted(
                    code=current.public_code or f"#{current.id}",
                    service_name=current.service_name_snapshot,
                )
                await self.notifications.notify_order(
                    tx,
                    user_id=current.user_id,
                    order_id=current.id,
                    event=NotificationType.ORDER_SUBMITTED,
                    title=title,
                    message=message,
                )
        logger.info(
            "أُرسل الطلب %s إلى المزود %s برقم %s", order.id, provider.name, result.provider_order_id
        )
        return "submitted"

    async def _requeue(self, order: Order, *, reason: str, delay_seconds: int) -> None:
        """إعادة الطلب إلى `pending` مع تأجيل المحاولة القادمة (فشل مؤقت آمن)."""
        clean_reason = sanitize(reason)[:300]
        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None or current.status != OrderStatus.SUBMITTING:
                return
            await self._transition(
                tx, current, OrderStatus.PENDING,
                actor_type=ActorType.JOB,
                reason=f"إعادة جدولة: {clean_reason}",
                extra={
                    "last_error": clean_reason,
                    "locked_by": None,
                    "locked_until": None,
                    "next_check_at": iso_plus_seconds(max(30, delay_seconds)),
                },
            )
        logger.warning("أُعيد الطلب %s للانتظار: %s", order.id, clean_reason)

    async def _mark_uncertain(self, order: Order, error: str) -> None:
        """
        وضع الطلب في حالة «غير مؤكد» وتنبيه الأدمن فوراً.

        ⚠️ لا استرجاع ولا إعادة إرسال هنا: قد يكون الطلب أُنشئ فعلاً عند المزود،
        وإعادة الإرسال تعني دفع المبلغ مرتين.
        """
        clean_error = sanitize(error)[:300]
        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None or current.status != OrderStatus.SUBMITTING:
                return
            moved = await self._transition(
                tx, current, OrderStatus.SUBMIT_UNCERTAIN,
                actor_type=ActorType.JOB,
                reason=clean_error,
                extra={"last_error": clean_error, "locked_by": None, "locked_until": None},
            )
            if moved:
                code = current.public_code or f"#{current.id}"
                title, message = templates.admin_order_uncertain(
                    code=code, order_id=current.id, error=clean_error
                )
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.ORDERS_VIEW,
                    token=f"order:{current.id}:uncertain",
                    title=title,
                    message=message,
                )
                await self.repos.error_logs.log(
                    tx,
                    message=f"نتيجة إرسال غير مؤكدة للطلب #{current.id}: {clean_error}",
                    level="CRITICAL",
                    source="order_service",
                    error_type="ProviderUncertainError",
                    user_id=current.user_id,
                )
        logger.critical("الطلب %s بحالة غير مؤكدة: %s", order.id, clean_error)

    async def _handle_insufficient_provider_funds(
        self, order: Order, provider: Provider, error: str
    ) -> None:
        """
        معالجة «رصيد المزود غير كافٍ» حسب القرار D5:
        يبقى الطلب منتظراً حتى مهلة قصوى، وبعدها يفشل ويُسترجع المبلغ تلقائياً.
        """
        wait_hours = await self.settings.get_int("provider_insufficient_wait_hours", 6)
        created = parse_iso(order.created_at)
        age_hours = ((utc_now() - created).total_seconds() / 3600) if created else 0.0

        if age_hours >= wait_hours:
            await self._fail_order(
                order, reason=f"انتظر الطلب {wait_hours} ساعة ورصيد المزود لا يزال غير كافٍ"
            )
            return

        await self._requeue(order, reason=f"رصيد المزود غير كافٍ: {error}", delay_seconds=900)
        symbol = await self.settings.money_symbol()
        title, message = templates.admin_provider_low_balance(
            provider_name=provider.name, balance_units=provider.balance_units, symbol=symbol
        )
        async with self.db.transaction() as tx:
            await self.notifications.notify_admins(
                tx,
                permission=Permission.PROVIDERS_VIEW,
                token=f"provider:{provider.id}:insufficient:{day_bounds_utc(0)[0][:10]}",
                title=title,
                message=message,
            )

    # ===================================================================== #
    #                          متابعة حالة الطلبات                          #
    # ===================================================================== #

    async def process_due_orders(self, *, worker: str = "checker", limit: int = 20) -> BatchReport:
        """
        حجز دفعة من الطلبات المستحقة للفحص وتحديث حالاتها من المزود.

        تُستدعى من job دوري حتى تصل كل الطلبات إلى حالة نهائية دون تدخل بشري.
        """
        report = BatchReport()
        async with self.db.transaction() as tx:
            claimed = await self.repos.orders.claim_due_for_check(
                tx, worker=worker, limit=limit, lock_seconds=ORDER_LOCK_SECONDS
            )
        report.claimed = len(claimed)

        for order in claimed:
            outcome = await self._sync_one(order)
            if outcome in {OrderStatus.COMPLETED, OrderStatus.PARTIAL}:
                report.completed += 1
            elif outcome == OrderStatus.FAILED:
                report.failed += 1
            elif outcome == "unchanged":
                report.unchanged += 1
            else:
                report.succeeded += 1

        if report.claimed:
            logger.info("جولة فحص الطلبات: %s", report.as_dict())
        return report

    async def _sync_one(self, order: Order) -> str:
        """
        فحص حالة طلب واحد لدى المزود وتطبيق النتيجة.

        المخرجات: الحالة الجديدة، أو "unchanged" إذا لم يتغير شيء.
        """
        provider = await self.repos.providers.get(order.provider_id)
        if provider is None:
            await self._fail_order(order, reason="المزود غير موجود")
            return OrderStatus.FAILED

        try:
            status = await self.providers.fetch_status(provider, order)
        except ProviderPermanentError as exc:
            await self._release_with_backoff(order, error=str(exc))
            logger.warning("فحص الطلب %s فشل نهائياً: %s", order.id, exc)
            return "unchanged"
        except ProviderError as exc:
            await self._release_with_backoff(order, error=str(exc))
            return "unchanged"

        mapped = map_provider_status(status.raw_status)
        if mapped is None:
            await self._handle_unknown_status(order, status.raw_status)
            return "unchanged"

        if mapped == order.status:
            await self._release_with_backoff(order, progress=status)
            return "unchanged"

        if mapped == OrderStatus.IN_PROGRESS:
            await self._apply_in_progress(order, status)
            return OrderStatus.IN_PROGRESS
        if mapped == OrderStatus.COMPLETED:
            await self._apply_completed(order, status)
            return OrderStatus.COMPLETED
        if mapped == OrderStatus.PARTIAL:
            await self._apply_partial(order, status)
            return OrderStatus.PARTIAL
        if mapped == OrderStatus.CANCELED:
            await self._apply_canceled(order, reason="ألغى المزود الطلب")
            return OrderStatus.CANCELED
        if mapped == OrderStatus.FAILED:
            await self._fail_order(order, reason=f"المزود أبلغ بفشل الطلب ({status.raw_status})")
            return OrderStatus.FAILED

        # حالة معروفة لكن الانتقال إليها غير منطقي من الحالة الحالية: نسجل ونؤجل
        await self._release_with_backoff(order, error=f"انتقال غير مدعوم إلى {mapped}")
        return "unchanged"

    def _progress_fields(self, status) -> dict:
        """الحقول الرقمية المستخرجة من رد المزود (تقدّم التنفيذ)."""
        fields: dict = {"provider_status": status.raw_status}
        if status.start_count is not None:
            fields["start_count"] = status.start_count
        if status.remains is not None:
            fields["remains"] = status.remains
        if status.delivered is not None:
            fields["delivered_quantity"] = status.delivered
        return fields

    async def _apply_in_progress(self, order: Order, status) -> None:
        """نقل الطلب إلى «قيد التنفيذ» وإشعار المستخدم مرة واحدة."""
        check_interval = await self.settings.get_int("order_check_interval_seconds", 120)
        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None:
                return
            extra = self._progress_fields(status)
            extra.update({
                "locked_by": None,
                "locked_until": None,
                "next_check_at": iso_plus_seconds(check_interval),
            })
            moved = await self._transition(
                tx, current, OrderStatus.IN_PROGRESS,
                actor_type=ActorType.PROVIDER,
                reason="بدأ التنفيذ",
                extra=extra,
                provider_status_raw=status.raw_status,
            )
            if moved:
                title, message = templates.order_in_progress(
                    code=current.public_code or f"#{current.id}"
                )
                await self.notifications.notify_order(
                    tx,
                    user_id=current.user_id,
                    order_id=current.id,
                    event=NotificationType.ORDER_IN_PROGRESS,
                    title=title,
                    message=message,
                )

    async def _apply_completed(self, order: Order, status) -> None:
        """إنهاء الطلب بنجاح وإشعار المستخدم."""
        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None:
                return
            extra = self._progress_fields(status)
            extra.update({
                "completed_at": self.repos.orders.now(),
                "remains": 0,
                "delivered_quantity": status.delivered if status.delivered is not None else current.quantity,
                "locked_by": None,
                "locked_until": None,
                "next_check_at": None,
            })
            moved = await self._transition(
                tx, current, OrderStatus.COMPLETED,
                actor_type=ActorType.PROVIDER,
                reason="اكتمل التنفيذ",
                extra=extra,
                provider_status_raw=status.raw_status,
            )
            if moved:
                title, message = templates.order_completed(
                    code=current.public_code or f"#{current.id}",
                    service_name=current.service_name_snapshot,
                    quantity=current.quantity,
                )
                await self.notifications.notify_order(
                    tx,
                    user_id=current.user_id,
                    order_id=current.id,
                    event=NotificationType.ORDER_COMPLETED,
                    title=title,
                    message=message,
                )
        logger.info("اكتمل الطلب %s", order.id)

    async def _apply_partial(self, order: Order, status) -> None:
        """
        تنفيذ جزئي: حساب الاسترجاع بحسب المتبقي، تنفيذه، ثم إشعار المستخدم.

        الاسترجاع = (التكلفة × المتبقي) ÷ الكمية، مطروحاً منه ما سبق استرجاعه.
        """
        symbol = await self.settings.money_symbol()
        refund_enabled = await self.settings.get_bool("partial_refund_enabled", True)

        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None:
                return

            remains = status.remains if status.remains is not None else 0
            delivered = (
                status.delivered if status.delivered is not None else max(0, current.quantity - remains)
            )
            refund_units = 0
            if refund_enabled and remains > 0:
                refund_units = partial_refund_units(
                    cost_units=current.cost_units,
                    quantity=current.quantity,
                    remains=remains,
                    already_refunded_units=current.refund_amount_units,
                )

            extra = self._progress_fields(status)
            extra.update({
                "remains": remains,
                "delivered_quantity": delivered,
                "completed_at": self.repos.orders.now(),
                "locked_by": None,
                "locked_until": None,
                "next_check_at": None,
            })
            moved = await self._transition(
                tx, current, OrderStatus.PARTIAL,
                actor_type=ActorType.PROVIDER,
                reason=f"تنفيذ جزئي — المتبقي {remains}",
                extra=extra,
                provider_status_raw=status.raw_status,
            )
            if not moved:
                return

            refunded = 0
            if refund_units > 0:
                transaction = await self.wallet.refund_order(
                    tx,
                    user_id=current.user_id,
                    order_id=current.id,
                    amount_units=refund_units,
                    partial=True,
                    description=f"استرجاع جزئي للطلب #{current.id} (متبقي {remains})",
                )
                refunded = transaction.amount_units if transaction else 0

            title, message = templates.order_partial(
                code=current.public_code or f"#{current.id}",
                delivered=delivered,
                quantity=current.quantity,
                refund_units=refunded,
                symbol=symbol,
            )
            await self.notifications.notify_order(
                tx,
                user_id=current.user_id,
                order_id=current.id,
                event=NotificationType.ORDER_PARTIAL,
                title=title,
                message=message,
            )
        logger.info("الطلب %s نُفِّذ جزئياً (متبقي %s)", order.id, status.remains)

    async def _apply_canceled(
        self, order: Order, *, reason: str, actor_type: str = ActorType.PROVIDER, actor_id: int | None = None
    ) -> int:
        """
        إلغاء الطلب مع استرجاع كامل المبلغ وإشعار المستخدم.

        المخرجات: المبلغ المسترجع.
        """
        symbol = await self.settings.money_symbol()
        clean_reason = sanitize(reason)[:300]
        refunded = 0

        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None or is_final(current.status):
                return 0
            moved = await self._transition(
                tx, current, OrderStatus.CANCELED,
                actor_type=actor_type, actor_id=actor_id, reason=clean_reason,
                extra={
                    "cancelled_at": self.repos.orders.now(),
                    "locked_by": None,
                    "locked_until": None,
                    "next_check_at": None,
                },
            )
            if not moved:
                return 0

            canceled_order = await self.repos.orders.get(order.id)
            if canceled_order is None:
                return 0
            refunded = await self._refund_full(
                tx, canceled_order, reason=clean_reason, actor_type=actor_type, actor_id=actor_id
            )

            code = current.public_code or f"#{current.id}"
            title, message = templates.order_canceled(
                code=code, refund_units=refunded, symbol=symbol
            )
            await self.notifications.notify_order(
                tx,
                user_id=current.user_id,
                order_id=current.id,
                event=NotificationType.ORDER_CANCELED,
                title=title,
                message=message,
            )
        logger.info("أُلغي الطلب %s (%s) واسترُجع %s", order.id, clean_reason, refunded)
        return refunded

    async def _handle_unknown_status(self, order: Order, raw_status: str | None) -> None:
        """تسجيل حالة مزود غير معروفة دون تغيير حالة الطلب (سلامة أولاً)."""
        clean = sanitize(str(raw_status))[:100]
        async with self.db.transaction() as tx:
            await self.repos.error_logs.log(
                tx,
                message=f"حالة مزود غير معروفة للطلب #{order.id}: {clean}",
                level="WARNING",
                source="order_service",
                error_type="UnknownProviderStatus",
                user_id=order.user_id,
            )
        await self._release_with_backoff(order, error=f"حالة غير معروفة: {clean}")
        logger.warning("حالة مزود غير معروفة للطلب %s: %s", order.id, clean)

    async def _release_with_backoff(self, order: Order, *, progress=None, error: str | None = None) -> None:
        """
        فك حجز الطلب وتحديد موعد الفحص القادم بتدرج تصاعدي.

        كلما تكررت الفحوص دون تغيير، تباعدت المواعيد — تخفيفاً على المزود وعلى النظام.
        """
        index = min(order.checks_count, len(ORDER_CHECK_BACKOFF) - 1)
        delay = ORDER_CHECK_BACKOFF[index]
        async with self.db.transaction() as tx:
            fields: dict = {}
            if progress is not None:
                fields.update(self._progress_fields(progress))
            if error:
                fields["last_error"] = sanitize(error)[:300]
            if fields:
                await self.repos.orders.update_fields(tx, order.id, **fields)
            await self.repos.orders.release_lock(
                tx, order.id, next_check_at=iso_plus_seconds(delay)
            )

    # ===================================================================== #
    #                        إجراءات المستخدم والأدمن                       #
    # ===================================================================== #

    async def cancel_by_user(self, user: User, order_id: int) -> int:
        """
        إلغاء المستخدم لطلبه قبل إرساله للمزود (القرار D11).

        المخرجات: المبلغ المسترجع.

        الاستثناءات:
            OrderError                  : الطلب ليس للمستخدم أو غير موجود.
            InvalidStateTransitionError : الطلب غادر حالة الانتظار (لا يمكن الإلغاء).
            ValidationError             : الإلغاء الذاتي معطّل من الإعدادات.
        """
        await self.auth.guard(user)
        if not await self.settings.get_bool("user_cancel_before_submit", True):
            raise ValidationError(
                "إلغاء المستخدم معطّل", user_message="⚠️ إلغاء الطلبات غير متاح حالياً."
            )

        order = await self.repos.orders.get(order_id)
        if order is None or order.user_id != user.id:
            raise OrderError("الطلب غير موجود", user_message="❌ لم يتم العثور على هذا الطلب.")
        if order.status != OrderStatus.PENDING:
            raise InvalidStateTransitionError(
                f"لا يمكن إلغاء الطلب {order_id} في الحالة {order.status}",
                user_message="⚠️ لا يمكن الإلغاء الآن — بدأ تنفيذ الطلب بالفعل.",
            )

        return await self._apply_canceled(
            order, reason="إلغاء بطلب المستخدم", actor_type=ActorType.USER, actor_id=user.id
        )

    async def admin_cancel(self, actor: User, order_id: int, reason: str) -> int:
        """
        إلغاء طلب من الأدمن مع استرجاع كامل (صلاحية `orders.cancel`).

        المخرجات: المبلغ المسترجع.
        """
        await self.auth.require_permission(actor, Permission.ORDERS_CANCEL, context=f"order:{order_id}")
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")
        if is_final(order.status):
            raise InvalidStateTransitionError(
                f"الطلب {order_id} في حالة نهائية ({order.status})",
                user_message="⚠️ هذا الطلب مغلق ولا يقبل الإلغاء.",
            )

        refunded = await self._apply_canceled(
            order, reason=reason, actor_type=ActorType.ADMIN, actor_id=actor.id
        )
        await self.audit.log_standalone(
            action="orders.cancel",
            admin_id=actor.id,
            target_type="order",
            target_id=order_id,
            details={"reason": reason, "refunded_units": refunded},
            source="telegram",
        )
        return refunded

    async def admin_mark_failed(self, actor: User, order_id: int, reason: str) -> int:
        """
        تأكيد الأدمن أن الطلب لم يُنشأ عند المزود (للطلبات غير المؤكدة) ⇒ فشل + استرجاع.

        المخرجات: المبلغ المسترجع.
        """
        await self.auth.require_permission(actor, Permission.ORDERS_REFUND, context=f"order:{order_id}")
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")
        if is_final(order.status):
            raise InvalidStateTransitionError(
                f"الطلب {order_id} في حالة نهائية ({order.status})",
                user_message="⚠️ هذا الطلب مغلق مسبقاً.",
            )

        refunded = await self._fail_order(
            order,
            reason=reason,
            actor_type=ActorType.ADMIN,
            actor_id=actor.id,
            notify_admins=False,
            auto_refund=True,  # قرار أدمن صريح: المال يعود فوراً
        )
        await self.audit.log_standalone(
            action="orders.refund",
            admin_id=actor.id,
            target_type="order",
            target_id=order_id,
            details={"reason": reason, "refunded_units": refunded},
            source="telegram",
        )
        return refunded

    async def admin_link_provider_order(self, actor: User, order_id: int, provider_order_id: str) -> bool:
        """
        ربط رقم الطلب عند المزود يدوياً (لطلب بحالة غير مؤكدة تبيّن أنه أُنشئ فعلاً).

        الاستثناءات:
            OrderError                  : الطلب غير موجود أو الرقم مستخدم لطلب آخر.
            InvalidStateTransitionError : حالة الطلب لا تسمح بالربط.
        """
        await self.auth.require_permission(
            actor, Permission.ORDERS_LINK_PROVIDER_ID, context=f"order:{order_id}"
        )
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")

        clean_id = str(provider_order_id).strip()
        if not clean_id:
            raise ValidationError("رقم الطلب فارغ", user_message="❌ أرسل رقم الطلب عند المزود.")
        conflict = await self.repos.orders.get_by_provider_order_id(order.provider_id, clean_id)
        if conflict is not None and conflict.id != order.id:
            raise OrderError(
                f"رقم المزود {clean_id} مرتبط بالطلب {conflict.id}",
                user_message=f"❌ هذا الرقم مرتبط بالطلب {conflict.public_code or conflict.id}.",
            )

        check_interval = await self.settings.get_int("order_check_interval_seconds", 120)
        async with self.db.transaction() as tx:
            moved = await self._transition(
                tx, order, OrderStatus.SUBMITTED,
                actor_type=ActorType.ADMIN, actor_id=actor.id,
                reason=f"ربط يدوي برقم المزود {clean_id}",
                extra={
                    "provider_order_id": clean_id,
                    "submitted_at": self.repos.orders.now(),
                    "next_check_at": iso_plus_seconds(check_interval),
                    "locked_by": None,
                    "locked_until": None,
                },
            )
            if moved:
                await self.audit.log(
                    tx,
                    action="orders.link_provider_id",
                    admin_id=actor.id,
                    target_type="order",
                    target_id=order_id,
                    before={"status": order.status, "provider_order_id": order.provider_order_id},
                    after={"status": OrderStatus.SUBMITTED, "provider_order_id": clean_id},
                )
                title, message = templates.order_submitted(
                    code=order.public_code or f"#{order.id}",
                    service_name=order.service_name_snapshot,
                )
                await self.notifications.notify_order(
                    tx,
                    user_id=order.user_id,
                    order_id=order.id,
                    event=NotificationType.ORDER_SUBMITTED,
                    title=title,
                    message=message,
                )
        return moved

    async def admin_override_status(
        self, actor: User, order_id: int, new_status: str, reason: str
    ) -> bool:
        """
        تجاوز إداري لحالة الطلب (للأدمن الأعلى فقط) — مع سبب إجباري وتدقيق كامل.

        لا يُجري أي حركة مالية: الاسترجاع يتم عبر الأدوات المخصصة له،
        حتى لا يحدث تغيير رصيد خارج المسار المحاسبي.

        الاستثناءات:
            PermissionDeniedError · ValidationError · OrderError
        """
        await self.auth.require_permission(
            actor, Permission.ORDERS_STATUS_OVERRIDE, context=f"order:{order_id}"
        )
        clean_reason = (reason or "").strip()
        if len(clean_reason) < 5:
            raise ValidationError(
                "سبب التجاوز مطلوب", user_message="❌ اكتب سبباً واضحاً للتجاوز (5 أحرف على الأقل)."
            )
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")

        async with self.db.transaction() as tx:
            changed = await self.repos.orders.update_status(
                tx, order_id, new_status=new_status, expected_statuses=[order.status]
            )
            if changed:
                await self.repos.orders.add_history(
                    tx,
                    order_id=order_id,
                    from_status=order.status,
                    to_status=new_status,
                    actor_type=ActorType.ADMIN,
                    actor_id=actor.id,
                    reason=f"تجاوز إداري: {clean_reason}",
                )
                await self.audit.log(
                    tx,
                    action="orders.status.override",
                    admin_id=actor.id,
                    target_type="order",
                    target_id=order_id,
                    before={"status": order.status},
                    after={"status": new_status, "reason": clean_reason},
                )
        if changed:
            logger.warning(
                "تجاوز إداري لحالة الطلب %s: %s ← %s بواسطة %s",
                order_id, order.status, new_status, actor.id,
            )
        return changed

    async def recheck_now(self, actor: User, order_id: int) -> str:
        """
        إعادة فحص فورية لحالة طلب من لوحة الأدمن.

        المخرجات: وصف نصي للنتيجة.
        """
        await self.auth.require_permission(actor, Permission.ORDERS_RECHECK, context=f"order:{order_id}")
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")
        if not order.provider_order_id:
            return "لا يمكن الفحص: الطلب بلا رقم عند المزود."
        return await self._sync_one(order)

    # ===================================================================== #
    #                        الاسترداد بعد إعادة التشغيل                     #
    # ===================================================================== #

    async def recover_after_restart(self) -> dict[str, int]:
        """
        استرداد الحالة بعد إعادة تشغيل البوت.

        • الطلبات العالقة في `submitting` تُنقل إلى `submit_uncertain` (لا نعرف مصيرها).
        • الأقفال منتهية الصلاحية تُحرَّر ليعاد التقاط الطلبات.

        المخرجات: عدّادات ما تم استرداده.
        """
        async with self.db.transaction() as tx:
            recovered = await self.repos.orders.recover_submitting_orders(tx)
            released = await self.repos.orders.release_expired_locks(tx)

        for order_id in recovered:
            order = await self.repos.orders.get(order_id)
            if order is None:
                continue
            code = order.public_code or f"#{order.id}"
            title, message = templates.admin_order_uncertain(
                code=code, order_id=order.id, error="انقطع تشغيل البوت أثناء إرسال الطلب"
            )
            async with self.db.transaction() as tx:
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.ORDERS_VIEW,
                    token=f"order:{order.id}:uncertain",
                    title=title,
                    message=message,
                )

        if recovered or released:
            logger.warning(
                "استرداد بعد الإقلاع: %s طلب غير مؤكد، %s قفل محرَّر", len(recovered), released
            )
        return {"uncertain": len(recovered), "locks_released": released}

    async def alert_stuck_orders(self) -> int:
        """
        تنبيه الأدمن بالطلبات التي توقفت بلا تقدم لفترة طويلة.

        المخرجات: عدد الطلبات المتوقفة.
        """
        hours = await self.settings.get_int("order_stuck_alert_hours", 24)
        before = iso_plus_seconds(-hours * 3600)
        stuck = await self.repos.orders.stuck_orders(before_iso=before, limit=50)
        if not stuck:
            return 0
        title, message = templates.admin_stuck_orders(count=len(stuck), hours=hours)
        async with self.db.transaction() as tx:
            await self.notifications.notify_admins(
                tx,
                permission=Permission.ORDERS_VIEW,
                token=f"stuck:{day_bounds_utc(0)[0][:13]}",
                title=title,
                message=message,
            )
        return len(stuck)

    # ===================================================================== #
    #                                القراءة                                #
    # ===================================================================== #

    async def get_for_user(self, user: User, order_id: int) -> Order:
        """
        جلب طلب يخص المستخدم (مع منع الاطلاع على طلبات غيره).

        الاستثناءات: OrderError إذا لم يكن الطلب موجوداً أو ليس له.
        """
        order = await self.repos.orders.get(order_id)
        if order is None or order.user_id != user.id:
            raise OrderError("الطلب غير موجود", user_message="❌ لم يتم العثور على هذا الطلب.")
        return order

    async def list_for_user(
        self, user: User, *, statuses: list[str] | None = None, limit: int = 8, offset: int = 0
    ) -> list[Order]:
        """قائمة طلبات المستخدم (مع إمكانية التصفية بالحالة)."""
        return await self.repos.orders.list_by_user(
            user.id, statuses=statuses, limit=limit, offset=offset
        )

    async def count_for_user(self, user: User, *, statuses: list[str] | None = None) -> int:
        """عدد طلبات المستخدم (للتصفح بالصفحات)."""
        return await self.repos.orders.count_by_user(user.id, statuses=statuses)

    async def history(self, order_id: int) -> list:
        """سجل تغيّر حالات الطلب (من ماذا إلى ماذا ومتى ومن نفّذ)."""
        return await self.repos.orders.history(order_id)

    async def status_counts(self) -> dict[str, int]:
        """عدد الطلبات في كل حالة (للوحة الأدمن)."""
        return await self.repos.orders.status_counts()

    async def recent_revenue_units(self, days: int = 1) -> int:
        """إجمالي قيمة الطلبات خلال آخر عدد أيام (للإحصائيات السريعة)."""
        return await self.repos.orders.sum_cost_between(iso_minus_days(days), self.repos.orders.now())
```

## `services/payment_service.py`

```python
"""
خدمة الشحن (الإيداع) — من إرسال إثبات التحويل حتى إضافة الرصيد.

المسؤوليات:
    • عرض طرق الشحن المفعّلة وحدودها.
    • إنشاء طلب شحن بعد تحقق كامل (مبلغ، رقم حوالة، إثبات، حدود، تكرار).
    • اعتماد/رفض الطلب من الأدمن مع إضافة الرصيد عبر المحفظة المركزية فقط.
    • انتهاء صلاحية الطلبات القديمة تلقائياً.
    • إدارة طرق الدفع من لوحة الأدمن.

قواعد لا تُكسر:
    • الاعتماد يغيّر الحالة بشكل مشروط (`expected_status='pending'`) قبل إضافة أي رصيد،
      فلو ضغط أدمنان الزر في نفس اللحظة يُضاف الرصيد مرة واحدة فقط.
    • إضافة الرصيد تتم حصراً عبر `WalletService.credit_from_payment` بمرجع فريد.
    • رقم الحوالة لا يُقبل مرتين (كشف إعادة استخدام إثبات الدفع).
    • كل إجراء أدمن يُسجَّل في سجل التدقيق داخل نفس المعاملة.
"""

from __future__ import annotations

from core.enums import NotificationType, PaymentStatus
from core.money import format_units
from core.payment_state import assert_transition, is_final
from core.permissions import Permission
from database.database import Database
from database.models import Payment, PaymentMethod, Transaction, User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.notification_service import NotificationService
from services.settings_service import SettingsService
from services.wallet_service import WalletService
from texts import templates
from core.exceptions import (
    DuplicateOperationError,
    PaymentError,
    ValidationError,
)
from utils.datetime_utils import iso_plus_seconds, utc_now_iso
from utils.logging_setup import get_logger
from utils.security import sanitize
from utils.validators import (
    clean_text,
    parse_amount_units,
    validate_amount_range,
    validate_transaction_reference,
)

logger = get_logger(__name__)

#: أقصى طول لملاحظة المستخدم على طلب الشحن
MAX_USER_NOTE = 300


class PaymentService:
    """دورة حياة طلب الشحن كاملة."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        wallet: WalletService,
        notifications: NotificationService,
        audit: AuditService,
        auth: AuthService,
    ) -> None:
        """تهيئة الخدمة بالاعتماديات المطلوبة."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.wallet = wallet
        self.notifications = notifications
        self.audit = audit
        self.auth = auth

    # ===================================================================== #
    #                              طرق الشحن                                #
    # ===================================================================== #

    async def active_methods(self) -> list[PaymentMethod]:
        """طرق الشحن المفعّلة كما تُعرض للمستخدم."""
        return await self.repos.payment_methods.list_all(active_only=True)

    async def all_methods(self, actor: User) -> list[PaymentMethod]:
        """كل طرق الشحن (للوحة الأدمن) — تتطلب صلاحية إدارة طرق الدفع."""
        await self.auth.require_permission(actor, Permission.PAYMENTS_METHODS)
        return await self.repos.payment_methods.list_all()

    async def get_method(self, method_id: int, *, require_active: bool = True) -> PaymentMethod:
        """
        جلب طريقة شحن بالمعرف.

        الاستثناءات:
            ValidationError : الطريقة غير موجودة أو متوقفة.
        """
        method = await self.repos.payment_methods.get(method_id)
        if method is None:
            raise ValidationError(
                f"طريقة الدفع {method_id} غير موجودة",
                user_message="❌ طريقة الشحن غير متاحة.",
            )
        if require_active and not method.is_active:
            raise ValidationError(
                f"طريقة الدفع {method_id} متوقفة",
                user_message="⚠️ طريقة الشحن هذه متوقفة حالياً، اختر طريقة أخرى.",
            )
        return method

    async def method_limits(self, method: PaymentMethod) -> tuple[int, int]:
        """
        الحدان الأدنى والأقصى الفعليان للشحن بهذه الطريقة.

        القاعدة: حد الطريقة إن وُجد، وإلا الحد العام من الإعدادات.
        """
        min_global = await self.settings.get_money_units("min_deposit_units", 0)
        max_global = await self.settings.get_money_units("max_deposit_units", 0)
        min_units = method.min_amount_units or min_global
        max_units = method.max_amount_units or max_global
        return min_units, max_units

    async def limits_text(self, method: PaymentMethod) -> str:
        """نص جاهز يوضّح حدود الشحن للمستخدم."""
        min_units, max_units = await self.method_limits(method)
        symbol = await self.settings.money_symbol()
        parts = []
        if min_units:
            parts.append(f"الحد الأدنى: {format_units(min_units, symbol=symbol)}")
        if max_units:
            parts.append(f"الحد الأقصى: {format_units(max_units, symbol=symbol)}")
        return " • ".join(parts) if parts else "لا توجد حدود محددة"

    # ===================================================================== #
    #                           إنشاء طلب الشحن                             #
    # ===================================================================== #

    async def create_payment(
        self,
        user: User,
        *,
        method_id: int,
        raw_amount: str | int,
        transaction_reference: str | None = None,
        proof_file_id: str | None = None,
        proof_file_type: str | None = None,
        user_note: str | None = None,
    ) -> Payment:
        """
        إنشاء طلب شحن جديد بحالة «بانتظار المراجعة».

        المخرجات: طلب الشحن بعد إنشائه.

        الاستثناءات:
            UserBannedError · MaintenanceModeError : الحساب محظور أو النظام في صيانة.
            ValidationError                        : طريقة متوقفة · إثبات ناقص · تجاوز عدد الطلبات المعلّقة.
            InvalidAmountError                     : مبلغ غير صالح أو خارج الحدود.
            DuplicateOperationError                : رقم الحوالة مستخدم في طلب سابق.
        """
        await self.auth.guard(user)
        method = await self.get_method(method_id)

        amount_units = parse_amount_units(raw_amount)
        min_units, max_units = await self.method_limits(method)
        validate_amount_range(
            amount_units, min_units=min_units, max_units=max_units, label="مبلغ الشحن"
        )

        reference = validate_transaction_reference(
            transaction_reference, required=bool(method.requires_proof)
        )
        if method.requires_proof and not proof_file_id and not reference:
            raise ValidationError(
                "إثبات الدفع مطلوب",
                user_message="❌ أرسل صورة إيصال التحويل أو رقم العملية.",
            )

        if reference:
            duplicate = await self.repos.payments.find_duplicate_reference(reference)
            if duplicate is not None:
                raise DuplicateOperationError(
                    f"رقم الحوالة {reference} مستخدم في الطلب {duplicate.id}",
                    user_message=(
                        "⚠️ رقم العملية هذا مُستخدم في طلب شحن سابق. "
                        "تواصل مع الدعم إن كان هناك خطأ."
                    ),
                )

        await self._check_pending_limit(user)

        note = (
            clean_text(user_note, field="الملاحظة", max_length=MAX_USER_NOTE, min_length=0)
            if user_note
            else None
        )
        expiry_hours = await self.settings.get_int("payment_expiry_hours", 48)
        symbol = await self.settings.money_symbol()

        async with self.db.transaction() as tx:
            payment = await self.repos.payments.create(
                tx,
                user_id=user.id,
                method_id=method.id,
                amount_units=amount_units,
                transaction_reference=reference,
                proof_file_id=proof_file_id,
                proof_file_type=proof_file_type,
                user_note=note,
                expires_at=iso_plus_seconds(expiry_hours * 3600) if expiry_hours > 0 else None,
            )

            title, message = templates.payment_received(
                payment_id=payment.id, amount_units=amount_units, symbol=symbol
            )
            await self.notifications.notify_payment(
                tx,
                user_id=user.id,
                payment_id=payment.id,
                event=NotificationType.PAYMENT_RECEIVED,
                title=title,
                message=message,
            )

            admin_title, admin_message = templates.admin_new_payment(
                payment_id=payment.id,
                amount_units=amount_units,
                user_label=user.display_name,
                symbol=symbol,
            )
            await self.notifications.notify_admins(
                tx,
                permission=Permission.PAYMENTS_APPROVE,
                token=f"payment:{payment.id}:new",
                title=admin_title,
                message=admin_message,
            )

        logger.info(
            "طلب شحن جديد #%s من المستخدم %s بمبلغ %s عبر %s",
            payment.id, user.id, amount_units, method.code,
        )
        return payment

    async def _check_pending_limit(self, user: User) -> None:
        """
        منع تكديس طلبات شحن معلّقة من نفس المستخدم.

        الاستثناءات: ValidationError عند تجاوز العدد المسموح.
        """
        max_pending = await self.settings.get_int("max_pending_payments_per_user", 3)
        if max_pending <= 0:
            return
        pending = await self.repos.payments.count_pending_by_user(user.id)
        if pending >= max_pending:
            raise ValidationError(
                f"المستخدم {user.id} لديه {pending} طلب شحن معلّق",
                user_message=(
                    f"⏳ لديك {pending} طلب شحن بانتظار المراجعة. "
                    "انتظر مراجعتها قبل إرسال طلب جديد."
                ),
            )

    # ===================================================================== #
    #                          القراءة والعرض                               #
    # ===================================================================== #

    async def get_for_user(self, user: User, payment_id: int) -> Payment:
        """
        جلب طلب شحن يخص المستخدم نفسه.

        الاستثناءات: PaymentError إذا لم يوجد أو كان لمستخدم آخر.
        """
        payment = await self.repos.payments.get(payment_id)
        if payment is None or payment.user_id != user.id:
            raise PaymentError(
                f"طلب الشحن {payment_id} غير متاح للمستخدم {user.id}",
                user_message="❌ لم يتم العثور على طلب الشحن.",
            )
        return payment

    async def list_for_user(self, user: User, *, limit: int = 10, offset: int = 0) -> list[Payment]:
        """آخر طلبات الشحن للمستخدم."""
        return await self.repos.payments.list_by_user(user.id, limit=limit, offset=offset)

    async def admin_get(self, actor: User, payment_id: int) -> Payment:
        """
        جلب طلب شحن من لوحة الأدمن.

        الاستثناءات: PermissionDeniedError · PaymentError
        """
        await self.auth.require_permission(actor, Permission.PAYMENTS_VIEW)
        payment = await self.repos.payments.get(payment_id)
        if payment is None:
            raise PaymentError(
                f"طلب الشحن {payment_id} غير موجود", user_message="❌ طلب الشحن غير موجود."
            )
        return payment

    async def pending(self, actor: User, *, limit: int = 10, offset: int = 0) -> list[Payment]:
        """قائمة طلبات الشحن بانتظار المراجعة."""
        await self.auth.require_permission(actor, Permission.PAYMENTS_VIEW)
        return await self.repos.payments.list_pending(limit=limit, offset=offset)

    async def pending_count(self) -> int:
        """عدد طلبات الشحن المعلّقة (لشارة لوحة الأدمن)."""
        return await self.repos.payments.count_pending()

    async def approved_total_units(self, start_iso: str, end_iso: str) -> int:
        """مجموع المبالغ المعتمدة بين تاريخين (للإحصائيات)."""
        return await self.repos.payments.sum_approved_between(start_iso, end_iso)

    # ===================================================================== #
    #                        الاعتماد والرفض والإلغاء                       #
    # ===================================================================== #

    async def approve(
        self,
        actor: User,
        payment_id: int,
        *,
        credited_units: int | None = None,
        admin_note: str | None = None,
    ) -> Transaction:
        """
        اعتماد طلب شحن وإضافة الرصيد للمستخدم.

        المدخلات:
            credited_units : المبلغ المعتمد فعلياً إن اختلف عن المطلوب (تحويل ناقص مثلاً).

        المخرجات: الحركة المالية التي أُنشئت.

        الاستثناءات:
            PermissionDeniedError       : لا يملك صلاحية `payments.approve`.
            PaymentError                : الطلب غير موجود.
            InvalidStateTransitionError : الطلب ليس بانتظار المراجعة.
            DuplicateOperationError     : عالجه أدمن آخر قبل لحظات.
            InvalidAmountError          : مبلغ اعتماد غير صالح.
        """
        await self.auth.require_permission(
            actor, Permission.PAYMENTS_APPROVE, context=f"payment:{payment_id}"
        )
        payment = await self._load_pending(payment_id, PaymentStatus.APPROVED)

        amount_units = int(credited_units) if credited_units is not None else payment.amount_units
        if amount_units <= 0:
            raise ValidationError(
                f"مبلغ اعتماد غير صالح: {amount_units}",
                user_message="❌ المبلغ المعتمد يجب أن يكون أكبر من صفر.",
            )
        note = sanitize(admin_note)[:300] if admin_note else None
        if amount_units != payment.amount_units:
            diff_note = f"اعتُمد {amount_units} بدل {payment.amount_units}"
            note = f"{note} | {diff_note}" if note else diff_note

        symbol = await self.settings.money_symbol()
        async with self.db.transaction() as tx:
            changed = await self.repos.payments.set_status(
                tx,
                payment_id,
                new_status=PaymentStatus.APPROVED,
                expected_status=PaymentStatus.PENDING,
                admin_id=actor.id,
                credited_units=amount_units,
                admin_note=note,
            )
            if not changed:
                raise DuplicateOperationError(
                    f"طلب الشحن {payment_id} عولج مسبقاً",
                    user_message="⚠️ هذا الطلب تمت معالجته بالفعل (ربما من أدمن آخر).",
                )

            transaction = await self.wallet.credit_from_payment(
                tx,
                user_id=payment.user_id,
                payment_id=payment.id,
                amount_units=amount_units,
                actor_id=actor.id,
            )

            await self.audit.log(
                tx,
                action="payments.approve",
                admin_id=actor.id,
                target_type="payment",
                target_id=payment_id,
                before={"status": payment.status, "amount_units": payment.amount_units},
                after={"status": PaymentStatus.APPROVED, "credited_units": amount_units},
                details={"note": note},
            )

            title, message = templates.payment_approved(
                payment_id=payment.id,
                credited_units=amount_units,
                new_balance_units=transaction.balance_after_units,
                symbol=symbol,
            )
            await self.notifications.notify_payment(
                tx,
                user_id=payment.user_id,
                payment_id=payment.id,
                event=NotificationType.PAYMENT_APPROVED,
                title=title,
                message=message,
            )

        logger.info(
            "اعتمد الأدمن %s طلب الشحن #%s للمستخدم %s بمبلغ %s",
            actor.id, payment_id, payment.user_id, amount_units,
        )
        return transaction

    async def reject(self, actor: User, payment_id: int, reason: str) -> bool:
        """
        رفض طلب شحن مع سبب إجباري يصل للمستخدم.

        المخرجات: True عند الرفض الفعلي.

        الاستثناءات:
            PermissionDeniedError · PaymentError · InvalidStateTransitionError
            ValidationError         : السبب قصير جداً.
            DuplicateOperationError : عولج الطلب مسبقاً.
        """
        await self.auth.require_permission(
            actor, Permission.PAYMENTS_REJECT, context=f"payment:{payment_id}"
        )
        clean_reason = (reason or "").strip()
        if len(clean_reason) < 3:
            raise ValidationError(
                "سبب الرفض مطلوب", user_message="❌ اكتب سبب الرفض ليظهر للمستخدم."
            )
        clean_reason = sanitize(clean_reason)[:300]
        payment = await self._load_pending(payment_id, PaymentStatus.REJECTED)

        async with self.db.transaction() as tx:
            changed = await self.repos.payments.set_status(
                tx,
                payment_id,
                new_status=PaymentStatus.REJECTED,
                expected_status=PaymentStatus.PENDING,
                admin_id=actor.id,
                reject_reason=clean_reason,
            )
            if not changed:
                raise DuplicateOperationError(
                    f"طلب الشحن {payment_id} عولج مسبقاً",
                    user_message="⚠️ هذا الطلب تمت معالجته بالفعل.",
                )

            await self.audit.log(
                tx,
                action="payments.reject",
                admin_id=actor.id,
                target_type="payment",
                target_id=payment_id,
                before={"status": payment.status},
                after={"status": PaymentStatus.REJECTED, "reason": clean_reason},
            )

            title, message = templates.payment_rejected(
                payment_id=payment.id, reason=clean_reason
            )
            await self.notifications.notify_payment(
                tx,
                user_id=payment.user_id,
                payment_id=payment.id,
                event=NotificationType.PAYMENT_REJECTED,
                title=title,
                message=message,
            )

        logger.info("رفض الأدمن %s طلب الشحن #%s: %s", actor.id, payment_id, clean_reason)
        return True

    async def cancel_by_user(self, user: User, payment_id: int) -> bool:
        """
        إلغاء المستخدم لطلب شحن أرسله بالخطأ (ما دام لم يُراجَع بعد).

        المخرجات: True عند الإلغاء الفعلي.

        الاستثناءات:
            PaymentError · InvalidStateTransitionError
        """
        payment = await self.get_for_user(user, payment_id)
        assert_transition(payment.status, PaymentStatus.CANCELLED, payment_id=payment_id)

        async with self.db.transaction() as tx:
            changed = await self.repos.payments.set_status(
                tx,
                payment_id,
                new_status=PaymentStatus.CANCELLED,
                expected_status=PaymentStatus.PENDING,
                admin_note="ألغاه المستخدم",
            )
        if changed:
            logger.info("ألغى المستخدم %s طلب الشحن #%s", user.id, payment_id)
        return changed

    async def _load_pending(self, payment_id: int, target_status: str) -> Payment:
        """
        جلب طلب شحن والتأكد من صلاحية الانتقال إلى الحالة المطلوبة.

        الاستثناءات:
            PaymentError                : الطلب غير موجود.
            InvalidStateTransitionError : الحالة الحالية لا تسمح بالإجراء.
        """
        payment = await self.repos.payments.get(payment_id)
        if payment is None:
            raise PaymentError(
                f"طلب الشحن {payment_id} غير موجود", user_message="❌ طلب الشحن غير موجود."
            )
        assert_transition(payment.status, target_status, payment_id=payment_id)
        return payment

    # ===================================================================== #
    #                          انتهاء الصلاحية                              #
    # ===================================================================== #

    async def expire_due(self, *, limit: int = 50) -> int:
        """
        تعليم طلبات الشحن المنتهية صلاحيتها (job دوري) وإشعار أصحابها.

        المخرجات: عدد الطلبات التي انتهت صلاحيتها.
        """
        expired = await self.repos.payments.list_expired_pending(limit=limit)
        if not expired:
            return 0

        count = 0
        for payment in expired:
            if is_final(payment.status):
                continue
            async with self.db.transaction() as tx:
                changed = await self.repos.payments.set_status(
                    tx,
                    payment.id,
                    new_status=PaymentStatus.EXPIRED,
                    expected_status=PaymentStatus.PENDING,
                    admin_note="انتهت صلاحية الطلب تلقائياً",
                )
                if not changed:
                    continue
                title, message = templates.payment_expired(payment_id=payment.id)
                await self.notifications.notify_payment(
                    tx,
                    user_id=payment.user_id,
                    payment_id=payment.id,
                    event=NotificationType.SYSTEM,
                    title=title,
                    message=message,
                )
            count += 1

        if count:
            logger.info("انتهت صلاحية %s طلب شحن", count)
        return count

    # ===================================================================== #
    #                        إدارة طرق الدفع (أدمن)                         #
    # ===================================================================== #

    async def create_method(
        self,
        actor: User,
        *,
        code: str,
        name_ar: str,
        instructions_ar: str = "",
        account_details: str = "",
        min_amount_units: int = 0,
        max_amount_units: int | None = None,
        requires_proof: bool = True,
        sort_order: int = 100,
    ) -> PaymentMethod:
        """
        إضافة طريقة شحن جديدة (صلاحية `payments.methods`).

        الاستثناءات:
            PermissionDeniedError · ValidationError (كود مكرر أو بيانات ناقصة)
        """
        await self.auth.require_permission(actor, Permission.PAYMENTS_METHODS)
        clean_code = clean_text(code, field="كود الطريقة", max_length=32).lower().replace(" ", "_")
        clean_name = clean_text(name_ar, field="اسم الطريقة", max_length=64)

        if await self.repos.payment_methods.get_by_code(clean_code) is not None:
            raise ValidationError(
                f"كود طريقة الدفع {clean_code} مستخدم",
                user_message="❌ يوجد طريقة شحن بنفس الكود.",
            )

        async with self.db.transaction() as tx:
            method = await self.repos.payment_methods.create(
                tx,
                code=clean_code,
                name_ar=clean_name,
                instructions_ar=instructions_ar.strip(),
                account_details=account_details.strip(),
                min_amount_units=max(0, int(min_amount_units)),
                max_amount_units=max_amount_units,
                requires_proof=requires_proof,
                sort_order=sort_order,
            )
            await self.audit.log(
                tx,
                action="payments.methods",
                admin_id=actor.id,
                target_type="payment_method",
                target_id=method.id,
                after={"code": clean_code, "name_ar": clean_name, "action": "create"},
            )
        logger.info("أضاف الأدمن %s طريقة شحن %s", actor.id, clean_code)
        return method

    async def update_method(self, actor: User, method_id: int, **fields) -> bool:
        """
        تعديل بيانات طريقة شحن (التعليمات، الحدود، الترتيب...).

        المخرجات: True عند حدوث تعديل فعلي.
        """
        await self.auth.require_permission(actor, Permission.PAYMENTS_METHODS)
        method = await self.get_method(method_id, require_active=False)
        if not fields:
            return False

        async with self.db.transaction() as tx:
            changed = await self.repos.payment_methods.update_fields(tx, method_id, **fields)
            if changed:
                await self.audit.log(
                    tx,
                    action="payments.methods",
                    admin_id=actor.id,
                    target_type="payment_method",
                    target_id=method_id,
                    before={"code": method.code},
                    after={"action": "update", **fields},
                )
        return changed

    async def set_method_active(self, actor: User, method_id: int, active: bool) -> bool:
        """تفعيل أو إيقاف طريقة شحن دون حذفها (حفاظاً على الطلبات التاريخية)."""
        await self.auth.require_permission(actor, Permission.PAYMENTS_METHODS)
        method = await self.get_method(method_id, require_active=False)

        async with self.db.transaction() as tx:
            changed = await self.repos.payment_methods.update_fields(
                tx, method_id, is_active=1 if active else 0
            )
            if changed:
                await self.audit.log(
                    tx,
                    action="payments.methods",
                    admin_id=actor.id,
                    target_type="payment_method",
                    target_id=method_id,
                    before={"is_active": method.is_active},
                    after={"is_active": 1 if active else 0},
                )
        if changed:
            logger.info(
                "%s الأدمن %s طريقة الشحن %s",
                "فعّل" if active else "أوقف", actor.id, method.code,
            )
        return changed

    async def method_usage_report(self, actor: User) -> list[tuple[str, int, int]]:
        """
        تقرير استخدام طرق الشحن: (اسم الطريقة، عدد الطلبات المعتمدة، إجمالي المبالغ).

        يساعد الأدمن على معرفة الطريقة الأكثر استخداماً فعلياً.
        """
        await self.auth.require_permission(actor, Permission.PAYMENTS_VIEW)
        rows = await self.repos.payments.usage_by_method()
        return [(row["name_ar"], int(row["approved_count"]), int(row["total_units"] or 0)) for row in rows]

    async def mark_reviewed_now(self, payment_id: int) -> str:
        """وقت المراجعة الحالي بصيغة ISO (يُستخدم في العرض بعد الاعتماد مباشرة)."""
        payment = await self.repos.payments.get(payment_id)
        return payment.reviewed_at if payment and payment.reviewed_at else utc_now_iso()
```

## `services/ticket_service.py`

```python
"""
خدمة الدعم الفني — التذاكر والمحادثة بين المستخدم والأدمن.

المسؤوليات:
    • فتح تذكرة جديدة بتحقق كامل (حد يومي، تذكرة مفتوحة واحدة، طول النص).
    • تبادل الرسائل بين المستخدم وفريق الدعم مع إشعار الطرف الآخر.
    • الإسناد والأولوية والإغلاق وإعادة الفتح.
    • الإغلاق التلقائي للتذاكر الراكدة عبر job دوري.

قواعد:
    • لا تُحذف التذاكر أو الرسائل إطلاقاً — الإغلاق فقط (حفظ السجل التاريخي).
    • كل إجراء أدمن على تذكرة يُسجَّل في سجل التدقيق.
    • إشعار الرد يحمل مفتاح منع تكرار خاصاً بكل رسالة، فلا يُبتلع الرد الثاني.
"""

from __future__ import annotations

from core.enums import NotificationType, SenderType, TicketPriority, TicketStatus
from core.exceptions import PermissionDeniedError, TicketError, ValidationError
from core.permissions import Permission
from database.database import Database
from database.models import SupportMessage, SupportTicket, User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.notification_service import NotificationService
from services.settings_service import SettingsService
from texts import templates
from utils.datetime_utils import day_bounds_utc, iso_plus_seconds, parse_iso, utc_now
from utils.logging_setup import get_logger
from utils.validators import validate_message, validate_subject

logger = get_logger(__name__)

#: تصنيفات التذاكر المسموحة (مطابقة لقيد CHECK في قاعدة البيانات)
TICKET_CATEGORIES: dict[str, str] = {
    "order": "مشكلة في طلب",
    "payment": "مشكلة في الشحن",
    "service": "استفسار عن خدمة",
    "other": "أخرى",
}

#: الحالات المفتوحة التي تظهر لفريق الدعم
OPEN_STATUSES: tuple[str, ...] = (
    TicketStatus.OPEN,
    TicketStatus.PENDING_ADMIN,
    TicketStatus.PENDING_USER,
)

#: طول المقتطف الظاهر في الإشعار
PREVIEW_LENGTH: int = 120


class TicketService:
    """إدارة تذاكر الدعم الفني من الفتح حتى الإغلاق."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        notifications: NotificationService,
        audit: AuditService,
        auth: AuthService,
    ) -> None:
        """تهيئة الخدمة بالاعتماديات المطلوبة."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.notifications = notifications
        self.audit = audit
        self.auth = auth

    # ===================================================================== #
    #                             فتح التذاكر                               #
    # ===================================================================== #

    async def create_ticket(
        self,
        user: User,
        *,
        subject: str,
        message: str,
        category: str = "other",
        related_order_id: int | None = None,
        attachment_file_id: str | None = None,
        attachment_type: str | None = None,
    ) -> SupportTicket:
        """
        فتح تذكرة دعم جديدة مع أول رسالة فيها.

        المخرجات: التذكرة بعد إنشائها.

        الاستثناءات:
            UserBannedError · MaintenanceModeError
            ValidationError : موضوع/نص غير صالح، تصنيف غير معروف، أو تجاوز الحد اليومي.
            TicketError     : لدى المستخدم تذكرة مفتوحة بالفعل.
        """
        await self.auth.guard(user)

        if category not in TICKET_CATEGORIES:
            raise ValidationError(
                f"تصنيف تذكرة غير معروف: {category}",
                user_message="❌ اختر تصنيفاً صحيحاً للتذكرة.",
            )
        clean_subject = validate_subject(subject)
        clean_message = validate_message(message)

        if await self.repos.tickets.has_open_ticket(user.id):
            raise TicketError(
                f"المستخدم {user.id} لديه تذكرة مفتوحة",
                user_message="📬 لديك تذكرة مفتوحة بالفعل — تابع محادثتك فيها بدل فتح تذكرة جديدة.",
            )

        await self._check_daily_limit(user)
        order_id = await self._validate_related_order(user, related_order_id)

        async with self.db.transaction() as tx:
            ticket = await self.repos.tickets.create(
                tx,
                user_id=user.id,
                subject=clean_subject,
                category=category,
                related_order_id=order_id,
            )
            await self.repos.tickets.add_message(
                tx,
                ticket_id=ticket.id,
                sender_type=SenderType.USER,
                sender_id=user.id,
                message=clean_message,
                attachment_file_id=attachment_file_id,
                attachment_type=attachment_type,
            )
            title, admin_message = templates.admin_new_ticket(
                ticket_id=ticket.id, subject=clean_subject, user_label=user.display_name
            )
            await self.notifications.notify_admins(
                tx,
                permission=Permission.TICKETS_VIEW,
                token=f"ticket:{ticket.id}:new",
                title=title,
                message=admin_message,
            )

        logger.info("فتح المستخدم %s التذكرة #%s (%s)", user.id, ticket.id, category)
        return ticket

    async def _check_daily_limit(self, user: User) -> None:
        """
        تطبيق الحد اليومي لعدد التذاكر لكل مستخدم.

        الاستثناءات: ValidationError عند التجاوز.
        """
        max_per_day = await self.settings.get_int("max_tickets_per_day", 5)
        if max_per_day <= 0:
            return
        start_today, _ = day_bounds_utc(0)
        today = await self.repos.tickets.count_today_by_user(user.id, start_today)
        if today >= max_per_day:
            raise ValidationError(
                f"المستخدم {user.id} تجاوز {max_per_day} تذاكر اليوم",
                user_message=f"⏳ وصلت للحد اليومي ({max_per_day} تذاكر). حاول غداً.",
            )

    async def _validate_related_order(self, user: User, order_id: int | None) -> int | None:
        """
        التأكد من أن الطلب المرتبط بالتذكرة يخص المستخدم نفسه.

        الاستثناءات: TicketError إذا كان الطلب لمستخدم آخر أو غير موجود.
        """
        if order_id is None:
            return None
        order = await self.repos.orders.get(order_id)
        if order is None or order.user_id != user.id:
            raise TicketError(
                f"الطلب {order_id} لا يخص المستخدم {user.id}",
                user_message="❌ رقم الطلب المرتبط غير صحيح.",
            )
        return order.id

    # ===================================================================== #
    #                              المحادثة                                 #
    # ===================================================================== #

    async def reply_as_user(
        self,
        user: User,
        ticket_id: int,
        message: str,
        *,
        attachment_file_id: str | None = None,
        attachment_type: str | None = None,
    ) -> SupportMessage:
        """
        إضافة رد من المستخدم على تذكرته وإشعار فريق الدعم.

        التذكرة المغلقة تُعاد فتحها تلقائياً ضمن مهلة `ticket_reopen_hours`.

        الاستثناءات:
            TicketError     : التذكرة غير موجودة أو ليست له أو مغلقة نهائياً.
            ValidationError : نص الرسالة غير صالح.
        """
        await self.auth.guard(user)
        ticket = await self.get_for_user(user, ticket_id)
        clean_message = validate_message(message)

        if ticket.status == TicketStatus.CLOSED:
            await self._reopen_or_fail(ticket)

        async with self.db.transaction() as tx:
            support_message = await self.repos.tickets.add_message(
                tx,
                ticket_id=ticket.id,
                sender_type=SenderType.USER,
                sender_id=user.id,
                message=clean_message,
                attachment_file_id=attachment_file_id,
                attachment_type=attachment_type,
            )
            title, admin_text = templates.admin_new_ticket(
                ticket_id=ticket.id,
                subject=f"رد جديد — {ticket.subject}",
                user_label=user.display_name,
            )
            await self.notifications.notify_admins(
                tx,
                permission=Permission.TICKETS_VIEW,
                token=f"ticket:{ticket.id}:msg:{support_message.id}",
                title=title,
                message=admin_text,
            )
        logger.info("رد المستخدم %s على التذكرة #%s", user.id, ticket_id)
        return support_message

    async def _reopen_or_fail(self, ticket: SupportTicket) -> None:
        """
        إعادة فتح تذكرة مغلقة إن كانت ضمن المهلة المسموحة.

        الاستثناءات: TicketError إذا انتهت المهلة أو كانت إعادة الفتح معطّلة.
        """
        reopen_hours = await self.settings.get_int("ticket_reopen_hours", 48)
        closed_at = parse_iso(ticket.closed_at)
        age_hours = ((utc_now() - closed_at).total_seconds() / 3600) if closed_at else 0.0

        if reopen_hours <= 0 or (closed_at is not None and age_hours > reopen_hours):
            raise TicketError(
                f"التذكرة {ticket.id} مغلقة منذ {age_hours:.1f} ساعة",
                user_message="🔒 هذه التذكرة مغلقة. افتح تذكرة جديدة لمتابعة طلبك.",
            )

        async with self.db.transaction() as tx:
            reopened = await self.repos.tickets.reopen(tx, ticket.id)
        if reopened:
            logger.info("أُعيد فتح التذكرة #%s", ticket.id)

    async def reply_as_admin(
        self,
        actor: User,
        ticket_id: int,
        message: str,
        *,
        attachment_file_id: str | None = None,
        attachment_type: str | None = None,
        close_after: bool = False,
    ) -> SupportMessage:
        """
        رد فريق الدعم على تذكرة، مع إسنادها للمُجيب إن لم تكن مُسندة.

        المدخلات:
            close_after : إغلاق التذكرة مباشرة بعد الرد.

        الاستثناءات:
            PermissionDeniedError · TicketError · ValidationError
        """
        await self.auth.require_permission(
            actor, Permission.TICKETS_REPLY, context=f"ticket:{ticket_id}"
        )
        ticket = await self._require_ticket(ticket_id)
        clean_message = validate_message(message)

        async with self.db.transaction() as tx:
            if ticket.status == TicketStatus.CLOSED:
                await self.repos.tickets.reopen(tx, ticket.id)
            if ticket.assigned_admin is None:
                await self.repos.tickets.assign(tx, ticket.id, actor.id)

            support_message = await self.repos.tickets.add_message(
                tx,
                ticket_id=ticket.id,
                sender_type=SenderType.ADMIN,
                sender_id=actor.id,
                message=clean_message,
                attachment_file_id=attachment_file_id,
                attachment_type=attachment_type,
            )
            await self.repos.tickets.mark_read(tx, ticket.id, by_admin=True)

            title, text = templates.ticket_replied(
                ticket_id=ticket.id, preview=clean_message[:PREVIEW_LENGTH]
            )
            await self.notifications.notify_user_manual(
                tx,
                user_id=ticket.user_id,
                token=f"ticket:{ticket.id}:reply:{support_message.id}",
                title=title,
                message=text,
                type=NotificationType.TICKET_REPLIED,
            )
            await self.audit.log(
                tx,
                action="tickets.reply",
                admin_id=actor.id,
                target_type="ticket",
                target_id=ticket.id,
                details={"message_id": support_message.id, "close_after": close_after},
            )

        if close_after:
            await self.close(actor, ticket_id, reason="تم حل المشكلة")
        logger.info("رد الأدمن %s على التذكرة #%s", actor.id, ticket_id)
        return support_message

    # ===================================================================== #
    #                        الإسناد والأولوية والإغلاق                     #
    # ===================================================================== #

    async def assign(self, actor: User, ticket_id: int, admin_id: int) -> bool:
        """
        إسناد التذكرة إلى أدمن معيّن.

        الاستثناءات:
            PermissionDeniedError : المنفّذ لا يملك `tickets.assign`، أو الهدف ليس أدمن.
            TicketError           : التذكرة غير موجودة.
        """
        await self.auth.require_permission(
            actor, Permission.TICKETS_ASSIGN, context=f"ticket:{ticket_id}"
        )
        ticket = await self._require_ticket(ticket_id)

        target = await self.repos.users.get_by_id(admin_id)
        if target is None or not await self.auth.is_admin(target):
            raise PermissionDeniedError(
                f"المستخدم {admin_id} ليس أدمن",
                user_message="❌ لا يمكن إسناد التذكرة لمستخدم غير إداري.",
            )

        async with self.db.transaction() as tx:
            changed = await self.repos.tickets.assign(tx, ticket_id, admin_id)
            if changed:
                await self.audit.log(
                    tx,
                    action="tickets.assign",
                    admin_id=actor.id,
                    target_type="ticket",
                    target_id=ticket_id,
                    before={"assigned_admin": ticket.assigned_admin},
                    after={"assigned_admin": admin_id},
                )
        return changed

    async def set_priority(self, actor: User, ticket_id: int, priority: str) -> bool:
        """
        تغيير أولوية التذكرة (low / normal / high).

        الاستثناءات: PermissionDeniedError · TicketError · ValidationError
        """
        await self.auth.require_permission(
            actor, Permission.TICKETS_ASSIGN, context=f"ticket:{ticket_id}"
        )
        if priority not in set(TicketPriority):
            raise ValidationError(
                f"أولوية غير معروفة: {priority}", user_message="❌ أولوية غير صحيحة."
            )
        ticket = await self._require_ticket(ticket_id)

        async with self.db.transaction() as tx:
            changed = await self.repos.tickets.update_fields(tx, ticket_id, priority=priority)
            if changed:
                await self.audit.log(
                    tx,
                    action="tickets.assign",
                    admin_id=actor.id,
                    target_type="ticket",
                    target_id=ticket_id,
                    before={"priority": ticket.priority},
                    after={"priority": priority},
                )
        return changed

    async def close(self, actor: User, ticket_id: int, reason: str = "") -> bool:
        """
        إغلاق التذكرة من فريق الدعم مع إشعار المستخدم.

        المخرجات: True عند الإغلاق الفعلي (False إذا كانت مغلقة أصلاً).
        """
        await self.auth.require_permission(
            actor, Permission.TICKETS_CLOSE, context=f"ticket:{ticket_id}"
        )
        ticket = await self._require_ticket(ticket_id)
        clean_reason = (reason or "").strip()[:200] or "تم إغلاق التذكرة"
        stamp = len(await self.repos.tickets.messages(ticket_id, limit=500))

        async with self.db.transaction() as tx:
            closed = await self.repos.tickets.close(
                tx, ticket_id, closed_by=actor.id, reason=clean_reason
            )
            if not closed:
                return False
            title, text = templates.ticket_closed(ticket_id=ticket_id, reason=clean_reason)
            await self.notifications.notify_user_manual(
                tx,
                user_id=ticket.user_id,
                token=f"ticket:{ticket_id}:closed:{stamp}",
                title=title,
                message=text,
                type=NotificationType.TICKET_CLOSED,
            )
            await self.audit.log(
                tx,
                action="tickets.close",
                admin_id=actor.id,
                target_type="ticket",
                target_id=ticket_id,
                before={"status": ticket.status},
                after={"status": TicketStatus.CLOSED, "reason": clean_reason},
            )
        logger.info("أغلق الأدمن %s التذكرة #%s", actor.id, ticket_id)
        return True

    async def close_by_user(self, user: User, ticket_id: int) -> bool:
        """إغلاق المستخدم لتذكرته بنفسه بعد حل مشكلته."""
        ticket = await self.get_for_user(user, ticket_id)
        async with self.db.transaction() as tx:
            closed = await self.repos.tickets.close(
                tx, ticket.id, closed_by=user.id, reason="أغلقها المستخدم"
            )
        if closed:
            logger.info("أغلق المستخدم %s التذكرة #%s", user.id, ticket_id)
        return closed

    async def auto_close_idle(self) -> int:
        """
        إغلاق التذاكر الراكدة (بانتظار رد المستخدم) بعد المدة المحددة في الإعدادات.

        المخرجات: عدد التذاكر التي أُغلقت.
        """
        days = await self.settings.get_int("ticket_auto_close_days", 7)
        if days <= 0:
            return 0
        cutoff = iso_plus_seconds(-days * 86400)
        idle = await self.repos.tickets.list_idle(
            statuses=(TicketStatus.PENDING_USER,), before_iso=cutoff, limit=50
        )
        closed_count = 0
        for ticket in idle:
            async with self.db.transaction() as tx:
                closed = await self.repos.tickets.close(
                    tx, ticket.id, closed_by=None, reason=f"إغلاق تلقائي بعد {days} أيام بلا رد"
                )
                if not closed:
                    continue
                title, text = templates.ticket_closed(
                    ticket_id=ticket.id, reason=f"إغلاق تلقائي بعد {days} أيام بلا رد"
                )
                await self.notifications.notify_user_manual(
                    tx,
                    user_id=ticket.user_id,
                    token=f"ticket:{ticket.id}:autoclosed",
                    title=title,
                    message=text,
                    type=NotificationType.TICKET_CLOSED,
                )
            closed_count += 1
        if closed_count:
            logger.info("أُغلقت %s تذكرة راكدة تلقائياً", closed_count)
        return closed_count

    # ===================================================================== #
    #                                القراءة                                #
    # ===================================================================== #

    async def get_for_user(self, user: User, ticket_id: int) -> SupportTicket:
        """
        جلب تذكرة تخص المستخدم نفسه.

        الاستثناءات: TicketError إذا لم توجد أو كانت لمستخدم آخر.
        """
        ticket = await self.repos.tickets.get(ticket_id)
        if ticket is None or ticket.user_id != user.id:
            raise TicketError(
                f"التذكرة {ticket_id} غير متاحة للمستخدم {user.id}",
                user_message="❌ لم يتم العثور على التذكرة.",
            )
        return ticket

    async def _require_ticket(self, ticket_id: int) -> SupportTicket:
        """
        جلب تذكرة للإدارة.

        الاستثناءات: TicketError إذا لم توجد.
        """
        ticket = await self.repos.tickets.get(ticket_id)
        if ticket is None:
            raise TicketError(
                f"التذكرة {ticket_id} غير موجودة", user_message="❌ التذكرة غير موجودة."
            )
        return ticket

    async def list_for_user(
        self, user: User, *, limit: int = 10, offset: int = 0
    ) -> list[SupportTicket]:
        """تذاكر المستخدم من الأحدث للأقدم."""
        return await self.repos.tickets.list_by_user(user.id, limit=limit, offset=offset)

    async def conversation_for_user(
        self, user: User, ticket_id: int, *, limit: int = 50
    ) -> list[SupportMessage]:
        """رسائل تذكرة المستخدم مع تعليمها كمقروءة من طرفه."""
        ticket = await self.get_for_user(user, ticket_id)
        messages = await self.repos.tickets.messages(ticket.id, limit=limit)
        async with self.db.transaction() as tx:
            await self.repos.tickets.mark_read(tx, ticket.id, by_admin=False)
        return messages

    async def admin_list(
        self, actor: User, *, statuses: tuple[str, ...] = OPEN_STATUSES, limit: int = 10, offset: int = 0
    ) -> list[SupportTicket]:
        """قائمة التذاكر لفريق الدعم (الافتراضي: غير المغلقة)."""
        await self.auth.require_permission(actor, Permission.TICKETS_VIEW)
        return await self.repos.tickets.list_by_status(list(statuses), limit=limit, offset=offset)

    async def admin_conversation(
        self, actor: User, ticket_id: int, *, limit: int = 50
    ) -> tuple[SupportTicket, list[SupportMessage]]:
        """
        فتح تذكرة في لوحة الدعم: التذكرة + رسائلها، مع تعليمها كمقروءة من الأدمن.
        """
        await self.auth.require_permission(actor, Permission.TICKETS_VIEW)
        ticket = await self._require_ticket(ticket_id)
        messages = await self.repos.tickets.messages(ticket_id, limit=limit)
        async with self.db.transaction() as tx:
            await self.repos.tickets.mark_read(tx, ticket_id, by_admin=True)
        return ticket, messages

    async def open_count(self) -> int:
        """عدد التذاكر غير المغلقة (شارة لوحة الأدمن)."""
        return await self.repos.tickets.count_open()
```

## `services/stats_service.py`

```python
"""
خدمة الإحصائيات والتقارير — أرقام حقيقية من قاعدة البيانات فقط.

المبدأ الحاكم: **لا رقم تقديري ولا بيانات وهمية**. كل قيمة هنا ناتجة عن استعلام
فعلي؛ وإن تعذّر حساب قيمة (مثل الربح بلا سعر مزود) تُعاد `None` ويُوضَّح ذلك
في العرض بدل اختراع رقم.

المحتوى:
    • لوحة المعلومات السريعة (Dashboard).
    • تقارير مالية: إيراد، ربح، التزامات المحفظة.
    • تقارير تشغيلية: نسبة النجاح، الطلبات العالقة، صحة المزودين.
    • صحة النظام: الأخطاء، صندوق الإشعارات، حجم قاعدة البيانات.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.enums import OrderStatus, TransactionType
from core.money import format_units
from core.permissions import Permission
from database.database import Database
from database.models import User
from database.repositories import Repositories
from services.auth_service import AuthService
from services.provider_service import ProviderService
from services.settings_service import SettingsService
from utils.datetime_utils import day_bounds_utc, iso_minus_days, iso_plus_seconds, utc_now_iso
from utils.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class DashboardStats:
    """أرقام لوحة المعلومات الرئيسية."""

    users_total: int
    users_new_today: int
    users_active_7d: int
    users_banned: int
    orders_today: int
    orders_by_status: dict[str, int]
    revenue_today_units: int
    revenue_7d_units: int
    deposits_today_units: int
    pending_payments: int
    open_tickets: int
    queued_notifications: int
    active_services: int
    errors_24h: int

    def as_dict(self) -> dict[str, object]:
        """تحويل الأرقام إلى قاموس (لتسجيلها أو إرسالها كتقرير)."""
        return {
            "users_total": self.users_total,
            "users_new_today": self.users_new_today,
            "users_active_7d": self.users_active_7d,
            "users_banned": self.users_banned,
            "orders_today": self.orders_today,
            "orders_by_status": self.orders_by_status,
            "revenue_today_units": self.revenue_today_units,
            "revenue_7d_units": self.revenue_7d_units,
            "deposits_today_units": self.deposits_today_units,
            "pending_payments": self.pending_payments,
            "open_tickets": self.open_tickets,
            "queued_notifications": self.queued_notifications,
            "active_services": self.active_services,
            "errors_24h": self.errors_24h,
        }


@dataclass(slots=True)
class FinancialReport:
    """تقرير مالي لفترة محددة."""

    start_iso: str
    end_iso: str
    orders_count: int
    revenue_units: int
    provider_cost_units: int
    profit_units: int | None
    deposits_units: int
    refunds_units: int
    partial_refunds_units: int
    manual_credit_units: int
    manual_debit_units: int

    @property
    def profit_known(self) -> bool:
        """هل الربح محسوب فعلياً؟ (يتطلب تسجيل أسعار المزود على الخدمات)."""
        return self.profit_units is not None


@dataclass(slots=True)
class OperationsReport:
    """تقرير تشغيلي عن جودة التنفيذ."""

    total_orders: int
    completed: int
    partial: int
    failed: int
    canceled: int
    refunded: int
    success_rate: float
    stuck_orders: int
    uncertain_orders: int


class StatsService:
    """تجميع الإحصائيات والتقارير للوحة الأدمن."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        auth: AuthService,
        providers: ProviderService,
    ) -> None:
        """تهيئة الخدمة بالاعتماديات المطلوبة."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.auth = auth
        self.providers = providers

    # ===================================================================== #
    #                           لوحة المعلومات                              #
    # ===================================================================== #

    async def dashboard(self, actor: User) -> DashboardStats:
        """
        أرقام لوحة المعلومات السريعة (صلاحية `stats.view`).

        الاستثناءات: PermissionDeniedError
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)

        start_today, end_today = day_bounds_utc(0)
        week_ago = iso_minus_days(7)
        day_ago = iso_minus_days(1)

        return DashboardStats(
            users_total=await self.repos.users.count_all(),
            users_new_today=await self.repos.users.count_since(start_today),
            users_active_7d=await self.repos.users.count_active_since(week_ago),
            users_banned=await self.repos.users.count_banned(),
            orders_today=await self.repos.orders.count_between(start_today, end_today),
            orders_by_status=await self.repos.orders.status_counts(),
            revenue_today_units=await self.repos.orders.sum_cost_between(start_today, end_today),
            revenue_7d_units=await self.repos.orders.sum_cost_between(week_ago, utc_now_iso()),
            deposits_today_units=await self.repos.payments.sum_approved_between(
                start_today, end_today
            ),
            pending_payments=await self.repos.payments.count_pending(),
            open_tickets=await self.repos.tickets.count_open(),
            queued_notifications=await self.repos.notifications.count_queued(),
            active_services=await self.repos.services.count_active(),
            errors_24h=await self.repos.error_logs.count_since(day_ago),
        )

    async def dashboard_text(self, actor: User) -> str:
        """لوحة المعلومات كنص عربي جاهز للإرسال في تيليجرام."""
        stats = await self.dashboard(actor)
        symbol = await self.settings.money_symbol()
        by_status = stats.orders_by_status
        active = (
            by_status.get(OrderStatus.PENDING, 0)
            + by_status.get(OrderStatus.SUBMITTED, 0)
            + by_status.get(OrderStatus.IN_PROGRESS, 0)
        )
        lines = [
            "📊 <b>لوحة المعلومات</b>",
            "",
            f"👥 المستخدمون: {stats.users_total} (جديد اليوم: {stats.users_new_today})",
            f"🔥 نشطون آخر 7 أيام: {stats.users_active_7d} • محظورون: {stats.users_banned}",
            "",
            f"🧾 طلبات اليوم: {stats.orders_today} • قيد التنفيذ الآن: {active}",
            f"✅ مكتملة: {by_status.get(OrderStatus.COMPLETED, 0)} • "
            f"⚠️ جزئية: {by_status.get(OrderStatus.PARTIAL, 0)} • "
            f"❌ فاشلة: {by_status.get(OrderStatus.FAILED, 0)}",
            f"❓ غير مؤكدة: {by_status.get(OrderStatus.SUBMIT_UNCERTAIN, 0)}",
            "",
            f"💰 مبيعات اليوم: {format_units(stats.revenue_today_units, symbol=symbol)}",
            f"💰 مبيعات 7 أيام: {format_units(stats.revenue_7d_units, symbol=symbol)}",
            f"💳 إيداعات اليوم: {format_units(stats.deposits_today_units, symbol=symbol)}",
            "",
            f"🧮 طلبات شحن معلّقة: {stats.pending_payments}",
            f"🎫 تذاكر مفتوحة: {stats.open_tickets}",
            f"📨 إشعارات بانتظار الإرسال: {stats.queued_notifications}",
            f"🛒 خدمات مفعّلة: {stats.active_services}",
            f"🐞 أخطاء آخر 24 ساعة: {stats.errors_24h}",
        ]
        return "\n".join(lines)

    # ===================================================================== #
    #                           التقارير المالية                            #
    # ===================================================================== #

    async def financial_report(
        self, actor: User, *, days: int = 7, include_profit: bool = True
    ) -> FinancialReport:
        """
        تقرير مالي لفترة بالأيام.

        الربح يُحسب فقط إذا كانت تكلفة المزود مسجّلة على الطلبات؛ وإلا تُعاد None
        بدل رقم مضلل. ويتطلب عرضه صلاحية `stats.profit`.
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        start_iso = iso_minus_days(days)
        end_iso = utc_now_iso()

        revenue = await self.repos.orders.sum_cost_between(start_iso, end_iso)
        provider_cost = await self.repos.orders.sum_provider_cost_between(start_iso, end_iso)
        orders_count = await self.repos.orders.count_between(start_iso, end_iso)

        profit: int | None = None
        if include_profit and await self.auth.has_permission(actor, Permission.STATS_PROFIT):
            profit = (revenue - provider_cost) if provider_cost > 0 else None

        return FinancialReport(
            start_iso=start_iso,
            end_iso=end_iso,
            orders_count=orders_count,
            revenue_units=revenue,
            provider_cost_units=provider_cost,
            profit_units=profit,
            deposits_units=await self.repos.payments.sum_approved_between(start_iso, end_iso),
            refunds_units=await self.repos.transactions.sum_by_type(
                TransactionType.REFUND, start_iso=start_iso, end_iso=end_iso
            ),
            partial_refunds_units=await self.repos.transactions.sum_by_type(
                TransactionType.PARTIAL_REFUND, start_iso=start_iso, end_iso=end_iso
            ),
            manual_credit_units=await self.repos.transactions.sum_by_type(
                TransactionType.MANUAL_CREDIT, start_iso=start_iso, end_iso=end_iso
            ),
            manual_debit_units=await self.repos.transactions.sum_by_type(
                TransactionType.MANUAL_DEBIT, start_iso=start_iso, end_iso=end_iso
            ),
        )

    async def financial_report_text(self, actor: User, *, days: int = 7) -> str:
        """التقرير المالي كنص عربي جاهز للعرض."""
        report = await self.financial_report(actor, days=days)
        symbol = await self.settings.money_symbol()
        lines = [
            f"💼 <b>التقرير المالي — آخر {days} يوم</b>",
            "",
            f"🧾 عدد الطلبات: {report.orders_count}",
            f"💰 إجمالي المبيعات: {format_units(report.revenue_units, symbol=symbol)}",
            f"💳 إجمالي الإيداعات المعتمدة: {format_units(report.deposits_units, symbol=symbol)}",
            f"↩️ استرجاع كامل: {format_units(report.refunds_units, symbol=symbol)}",
            f"↩️ استرجاع جزئي: {format_units(report.partial_refunds_units, symbol=symbol)}",
            f"➕ إضافات يدوية: {format_units(report.manual_credit_units, symbol=symbol)}",
            f"➖ خصومات يدوية: {format_units(report.manual_debit_units, symbol=symbol)}",
        ]
        if report.profit_known and report.profit_units is not None:
            lines.append(
                f"📈 الربح التقديري: {format_units(report.profit_units, symbol=symbol)} "
                f"(تكلفة المزود: {format_units(report.provider_cost_units, symbol=symbol)})"
            )
        else:
            lines.append("📈 الربح: غير محسوب — سجّل أسعار المزود على الخدمات لحسابه.")
        return "\n".join(lines)

    async def wallet_liability(self, actor: User) -> tuple[int, int, int]:
        """
        التزامات المحفظة: (مجموع أرصدة المستخدمين، إجمالي الإيداعات، إجمالي الإنفاق).

        يساعد على معرفة المبلغ المستحق للعملاء في أي لحظة.
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        total_balance = await self.repos.users.total_balance_units()
        deposits = await self.repos.transactions.sum_by_type(TransactionType.DEPOSIT)
        spent = await self.repos.transactions.sum_by_type(TransactionType.ORDER)
        return total_balance, deposits, spent

    # ===================================================================== #
    #                          التقارير التشغيلية                           #
    # ===================================================================== #

    async def operations_report(self, actor: User, *, days: int = 7) -> OperationsReport:
        """
        تقرير جودة التنفيذ: نسب الاكتمال والفشل والطلبات التي تحتاج تدخلاً.
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        start_iso = iso_minus_days(days)
        end_iso = utc_now_iso()

        total = await self.repos.orders.count_between(start_iso, end_iso)
        completed = await self.repos.orders.count_between_by_status(
            start_iso, end_iso, [OrderStatus.COMPLETED]
        )
        partial = await self.repos.orders.count_between_by_status(
            start_iso, end_iso, [OrderStatus.PARTIAL]
        )
        failed = await self.repos.orders.count_between_by_status(
            start_iso, end_iso, [OrderStatus.FAILED]
        )
        canceled = await self.repos.orders.count_between_by_status(
            start_iso, end_iso, [OrderStatus.CANCELED]
        )
        refunded = await self.repos.orders.count_between_by_status(
            start_iso, end_iso, [OrderStatus.REFUNDED]
        )

        stuck_hours = await self.settings.get_int("order_stuck_alert_hours", 24)
        stuck = len(
            await self.repos.orders.stuck_orders(
                before_iso=iso_plus_seconds(-max(1, stuck_hours) * 3600), limit=200
            )
        )
        uncertain = (await self.repos.orders.status_counts()).get(
            OrderStatus.SUBMIT_UNCERTAIN, 0
        )
        success_rate = round((completed + partial) * 100 / total, 1) if total else 0.0

        return OperationsReport(
            total_orders=total,
            completed=completed,
            partial=partial,
            failed=failed,
            canceled=canceled,
            refunded=refunded,
            success_rate=success_rate,
            stuck_orders=stuck,
            uncertain_orders=uncertain,
        )

    async def top_services(self, actor: User, *, days: int = 30, limit: int = 5) -> list[dict]:
        """أكثر الخدمات طلباً خلال فترة (اسم الخدمة، العدد، القيمة)."""
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        return await self.repos.orders.top_services(
            start_iso=iso_minus_days(days), end_iso=utc_now_iso(), limit=limit
        )

    async def top_users(self, actor: User, *, limit: int = 5) -> list[tuple[str, int]]:
        """أكثر المستخدمين إنفاقاً: (الاسم الظاهر، إجمالي الإنفاق)."""
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        users = await self.repos.users.top_spenders(limit=limit)
        return [(user.display_name, user.total_spent_units) for user in users]

    async def daily_series(self, actor: User, *, days: int = 14) -> list[dict]:
        """سلسلة يومية بعدد الطلبات وقيمتها (لرسم اتجاه بسيط نصياً)."""
        await self.auth.require_permission(actor, Permission.STATS_VIEW)
        return await self.repos.orders.daily_series(
            start_iso=iso_minus_days(days), end_iso=utc_now_iso()
        )

    # ===================================================================== #
    #                            صحة النظام                                 #
    # ===================================================================== #

    async def system_health(self, actor: User) -> dict[str, object]:
        """
        مؤشرات صحة النظام: المزودون، صندوق الإشعارات، الأخطاء، حجم قاعدة البيانات.

        الاستثناءات: PermissionDeniedError
        """
        await self.auth.require_permission(actor, Permission.STATS_VIEW)

        providers = await self.repos.providers.list_all()
        provider_rows: list[dict[str, object]] = []
        for provider in providers:
            health = await self.providers.health(provider)
            provider_rows.append(
                {
                    "name": provider.name,
                    "usable": health.is_usable,
                    "reason": health.reason,
                    "consecutive_failures": provider.consecutive_failures,
                    "balance_units": provider.balance_units,
                    "last_success_at": provider.last_success_at,
                }
            )

        db_size_bytes = self.db.path.stat().st_size if self.db.path.exists() else 0
        return {
            "providers": provider_rows,
            "queued_notifications": await self.repos.notifications.count_queued(),
            "errors_24h": await self.repos.error_logs.count_since(iso_minus_days(1)),
            "db_size_mb": round(db_size_bytes / (1024 * 1024), 2),
            "db_path": str(self.db.path),
        }

    async def health_text(self, actor: User) -> str:
        """مؤشرات صحة النظام كنص عربي."""
        health = await self.system_health(actor)
        symbol = await self.settings.money_symbol()
        lines = ["🩺 <b>صحة النظام</b>", ""]

        providers = health["providers"]
        if isinstance(providers, list) and providers:
            for row in providers:
                mark = "🟢" if row["usable"] else "🔴"
                lines.append(
                    f"{mark} {row['name']} — {row['reason']} • "
                    f"رصيد: {format_units(int(row['balance_units']), symbol=symbol)}"
                )
        else:
            lines.append("⚠️ لا يوجد مزودون مسجّلون بعد.")

        lines += [
            "",
            f"📨 إشعارات بانتظار الإرسال: {health['queued_notifications']}",
            f"🐞 أخطاء آخر 24 ساعة: {health['errors_24h']}",
            f"🗄 حجم قاعدة البيانات: {health['db_size_mb']} ميغابايت",
        ]
        return "\n".join(lines)
```

# أدوات التشغيل — scripts/

## `scripts/demo_cycle.py`

```python
"""
عرض حيّ للدورة الكاملة — المرحلة 2 (قبل بناء واجهة تيليجرام في المرحلة 3).

الغرض: أن ترى بعينك أن منطق العمل يعمل فعلاً من البداية للنهاية:
    تسجيل → تصفح → طلب → شحن → اعتماد → خصم → إرسال للمزود → متابعة آلية
    → إكمال → إشعار → سجل → إحصائيات
ثم المسار البديل: فشل المزود → استرجاع آمن → حركة مالية → إشعار المستخدم والأدمن.

⚠️ تنبيهات مهمة حتى لا يُفهم هذا العرض خطأً:
    • يعمل على قاعدة بيانات **مؤقتة منفصلة** (افتراضياً `data/demo_cycle.db`)
      تُحذف وتُعاد بناؤها عند كل تشغيل — لا يمس بيانات التشغيل إطلاقاً.
    • المزود هنا هو `MockProviderClient` (مزود وهمي محلي): **لا اتصال بأي شبكة
      ولا إنفاق أي مال حقيقي**. الأرقام أدناه حقيقية داخل قاعدة البيانات المؤقتة فقط.
    • الرسائل التي تُطبع بوصفها «إشعارات» هي ما كان البوت سيرسله لتيليجرام فعلاً،
      وهي مقروءة من جدول `notifications` لا مكتوبة يدوياً.

طريقة التشغيل (من داخل مجلد المشروع smm_bot):
    python -m scripts.demo_cycle
    python -m scripts.demo_cycle --keep     # إبقاء قاعدة البيانات المؤقتة بعد الانتهاء
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:                      # تشغيل مباشر بلا تثبيت الحزمة
    sys.path.insert(0, str(ROOT))

from core.enums import OrderStatus                                  # noqa: E402
from core.exceptions import InsufficientBalanceError                # noqa: E402
from core.exceptions import ProviderPermanentError                  # noqa: E402
from core.money import format_units                                 # noqa: E402
from database.database import Database                              # noqa: E402
from database.migrator import Migrator                              # noqa: E402
from database.repositories import Repositories                      # noqa: E402
from integrations.providers import registry                         # noqa: E402
from integrations.providers.mock import MockProviderClient          # noqa: E402
from services import ServiceContainer, build_services               # noqa: E402
from utils.datetime_utils import iso_plus_seconds                   # noqa: E402
from utils.logging_setup import setup_logging                       # noqa: E402
from utils.security import SecretBox, generate_encryption_key       # noqa: E402

LINE = "─" * 62


def step(number: str, title: str) -> None:
    """طباعة عنوان خطوة من الدورة."""
    print(f"\n{LINE}\n▶ {number}  {title}\n{LINE}")


def info(label: str, value: object) -> None:
    """طباعة سطر معلومة بمحاذاة ثابتة."""
    print(f"   • {label:<28} {value}")


def money(units: int) -> str:
    """عرض مبلغ بالنقاط الصحيحة بصيغة قابلة للقراءة."""
    return format_units(units, decimals=2)


class ConsoleSender:
    """بديل واجهة تيليجرام: يطبع الرسائل بدل إرسالها (لا شبكة في هذا العرض)."""

    def __init__(self, names: dict[int, str]) -> None:
        """تهيئة المرسل بخريطة معرفات تيليجرام إلى أسماء للعرض."""
        self.names = names
        self.count = 0

    async def __call__(self, telegram_id: int, title: str, message: str) -> int:
        """طباعة الرسالة كما كانت ستصل للمستخدم في تيليجرام."""
        self.count += 1
        who = self.names.get(telegram_id, str(telegram_id))
        first_line = message.strip().splitlines()[0] if message.strip() else ""
        print(f"   📨 إلى {who}: {title} — {first_line}")
        return self.count


async def build_environment(db_path: Path) -> tuple[Database, Repositories, ServiceContainer, dict]:
    """
    تجهيز قاعدة بيانات مؤقتة كاملة: ترحيلات + أدمن + مزود وهمي + خدمة + طريقة دفع.

    المخرجات: (قاعدة البيانات، المستودعات، حاوية الخدمات، قاموس الكائنات المُنشأة).
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    db = Database(db_path, read_pool_size=2)
    await db.connect()
    applied = await Migrator(db).apply_all()
    repos = Repositories(db)
    secret_box = SecretBox(generate_encryption_key())          # مفتاح مؤقت لهذا التشغيل فقط
    services = build_services(db, repos, secret_box=secret_box, settings_ttl_seconds=0)

    async with db.transaction() as tx:
        admin = await repos.users.create(
            tx, telegram_id=900900900, username="demo_admin", first_name="أدمن العرض",
            role="super_admin",
        )
        provider = await repos.providers.create(
            tx,
            name="MockPanel",
            api_url="https://mock.invalid/api/v2",
            api_key_enc=secret_box.encrypt("demo-key-1234567890"),
            api_key_hint="7890",
            api_type="mock",
        )
        categories = await repos.categories.list_all()
        service = await repos.services.create(
            tx,
            category_id=categories[0].id,
            provider_id=provider.id,
            provider_service_id="555",
            name="متابعين انستغرام (عرض تجريبي)",
            price_per_1000_units=10_000,          # 1.00 لكل ألف
            provider_price_per_1000_units=6_000,  # تكلفتنا من المزود
            min_quantity=100,
            max_quantity=100_000,
        )
        method = await repos.payment_methods.create(
            tx, code="demo_transfer", name_ar="حوالة بنكية (عرض)",
            instructions_ar="حوّل ثم أرسل رقم العملية",
        )

    info("ملف قاعدة البيانات", db_path)
    info("ترحيلات مطبَّقة", len(applied))
    info("أدمن العرض", f"{admin.display_name} (tg={admin.telegram_id})")
    info("المزود", f"{provider.name} — نوع {provider.api_type} — مفتاح ****{provider.api_key_hint}")
    info("الخدمة", f"{service.name} بسعر {money(service.price_per_1000_units)} لكل 1000")
    info("طريقة الدفع", method.name_ar)
    return db, repos, services, {"admin": admin, "provider": provider, "service": service, "method": method}


async def follow_until_final(services: ServiceContainer, repos: Repositories, order_id: int) -> None:
    """تشغيل حلقة المتابعة الآلية (كما يفعل JobQueue) حتى تستقر حالة الطلب."""
    for round_number in range(1, 9):
        order = await repos.orders.get(order_id)
        if order is None or order.status in {
            OrderStatus.COMPLETED, OrderStatus.PARTIAL, OrderStatus.REFUNDED, OrderStatus.CANCELED
        }:
            return
        async with repos.db.transaction() as tx:      # تقديم موعد الفحص بدل الانتظار الحقيقي
            await repos.orders.update_fields(tx, order_id, next_check_at=iso_plus_seconds(-5))
        report = await services.orders.process_due_orders()
        current = await repos.orders.get(order_id)
        assert current is not None
        info(
            f"دورة متابعة {round_number}",
            f"الحالة: {current.status} | منفَّذ: {current.delivered_quantity or 0}"
            f" | متبقٍ: {current.remains if current.remains is not None else '—'}"
            f" | فحوصات: {report.claimed}",
        )


async def happy_path(services: ServiceContainer, repos: Repositories, env: dict) -> None:
    """تنفيذ الدورة الكاملة الناجحة وطباعة كل خطوة."""
    admin, service, method = env["admin"], env["service"], env["method"]
    sender = ConsoleSender({admin.telegram_id: "الأدمن"})

    step("1/11", "التسجيل — أول تفاعل مع البوت")
    customer, created = await services.users.get_or_create(
        telegram_id=111222333, username="demo_client", first_name="عميل العرض"
    )
    sender.names[customer.telegram_id] = "العميل"
    info("الحساب", f"{customer.display_name} (tg={customer.telegram_id})")
    info("أُنشئ الآن؟", "نعم" if created else "كان موجوداً")
    info("الرصيد الابتدائي", money(customer.balance_units))

    step("2/11", "التصفح — التصنيفات والخدمات والتسعيرة")
    categories = await services.catalog.categories()
    info("تصنيفات بها خدمات", ", ".join(category.name_ar for category in categories))
    page = await services.catalog.services_page(categories[0].id)
    info("خدمات الصفحة الأولى", f"{page.total_items} خدمة")
    chosen = await services.catalog.get_available_service(service.id)
    quote = await services.catalog.quote(chosen, 1000)
    info("التسعيرة لـ1000 وحدة", quote.cost_text)

    step("3/11", "محاولة الطلب بلا رصيد — يجب أن تُرفض بلا أي أثر")
    try:
        await services.orders.create_order(
            customer, service_id=chosen.id, link="https://instagram.com/p/demo", quantity=1000
        )
    except InsufficientBalanceError as exc:
        info("الرفض المتوقع", exc.user_message)
    info("عدد طلبات العميل", await repos.orders.count_by_user(customer.id))

    step("4/11", "الشحن — العميل يرسل إثبات التحويل")
    payment = await services.payments.create_payment(
        customer, method_id=method.id, raw_amount="5",
        transaction_reference="DEMO-TRX-001", proof_file_id="demo-photo", proof_file_type="photo",
    )
    info("رقم طلب الشحن", payment.id)
    info("المبلغ المطلوب", money(payment.amount_units))
    info("الحالة", payment.status)
    info("الرصيد الآن", money(await services.wallet.balance_units(customer.id)))

    step("5/11", "الاعتماد — الأدمن يراجع ويعتمد")
    pending = await services.payments.pending(admin)
    info("طلبات بانتظار المراجعة", len(pending))
    transaction = await services.payments.approve(admin, payment.id)
    info("نوع الحركة المالية", transaction.type)
    info("مرجع الحركة", transaction.reference)
    info("الرصيد بعد الاعتماد", money(await services.wallet.balance_units(customer.id)))

    step("6/11", "الطلب — الخصم يتم داخل نفس معاملة الإنشاء")
    order = await services.orders.create_order(
        customer, service_id=chosen.id, link="https://instagram.com/p/demo", quantity=1000
    )
    info("رقم الطلب", order.public_code)
    info("التكلفة المخصومة", money(order.cost_units))
    info("الحالة", order.status)
    info("الرصيد بعد الخصم", money(await services.wallet.balance_units(customer.id)))

    step("7/11", "الإرسال للمزود — مهمة الخلفية تلتقط الطلب")
    batch = await services.orders.process_pending_orders()
    info("طلبات التُقطت", batch.claimed)
    info("أُرسلت بنجاح", batch.succeeded)
    submitted = await repos.orders.get(order.id)
    assert submitted is not None
    info("رقم الطلب لدى المزود", submitted.provider_order_id)
    info("تكلفتنا من المزود", money(submitted.provider_cost_units or 0))

    step("8/11", "المتابعة الآلية حتى الإكمال")
    await follow_until_final(services, repos, order.id)
    final = await repos.orders.get(order.id)
    assert final is not None
    info("الحالة النهائية", final.status)
    info("الكمية المنفَّذة", final.delivered_quantity)

    step("9/11", "الإشعارات — ما كان سيصل إلى تيليجرام")
    report = await services.notifications.dispatch_pending(sender, limit=50)
    info("أُرسل", report.sent)
    info("تخطّي (حظر البوت)", report.skipped)
    info("المتبقي في الطابور", await services.notifications.queued_count())

    step("10/11", "السجلات — حركات مالية وتدقيق وتاريخ حالات")
    for movement in await repos.transactions.list_by_user(customer.id, limit=5):
        info(movement.type, f"{money(movement.amount_units)} | الرصيد بعدها {money(movement.balance_after_units)}")
    ledger = await services.wallet.verify_ledger(customer.id)
    info("مطابقة الرصيد مع الدفتر", "متوازن ✅" if ledger.is_balanced else "اختلال ❌")
    history = await repos.orders.history(order.id)
    info("مسار حالات الطلب", " ← ".join(row.to_status for row in history))
    logs = await services.audit.by_target("payment", payment.id)
    info("سجل التدقيق للاعتماد", ", ".join(f"{log.action} بواسطة {log.admin_id}" for log in logs))

    step("11/11", "الإحصائيات — أرقام مقروءة من قاعدة البيانات")
    dashboard = await services.stats.dashboard(admin)
    info("طلبات اليوم", dashboard.orders_today)
    info("مبيعات اليوم", money(dashboard.revenue_today_units))
    financial = await services.stats.financial_report(admin, days=1)
    info("إيداعات", money(financial.deposits_units))
    info("مبيعات", money(financial.revenue_units))
    info("تكلفة المزود", money(financial.provider_cost_units))
    info("الربح", money(financial.profit_units) if financial.profit_known else "غير محسوب")
    operations = await services.stats.operations_report(admin, days=1)
    info("نسبة النجاح", f"{operations.success_rate}%")

    env["customer"] = customer
    env["sender"] = sender


async def failure_path(services: ServiceContainer, repos: Repositories, env: dict, client: MockProviderClient) -> None:
    """تنفيذ المسار البديل: رفض المزود للطلب ثم الاسترجاع الآمن."""
    customer, sender = env["customer"], env["sender"]
    service = env["service"]

    step("بديل 1/4", "طلب جديد — لكن المزود سيرفضه هذه المرة")
    await services.settings.set("duplicate_order_window_minutes", 0)
    client.always_fail_add = ProviderPermanentError("الخدمة غير متاحة لدى المزود")
    before = await services.wallet.balance_units(customer.id)
    order = await services.orders.create_order(
        customer, service_id=service.id, link="https://instagram.com/p/fail-demo", quantity=1000
    )
    info("رقم الطلب", order.public_code)
    info("الرصيد قبل", money(before))
    info("الرصيد بعد الخصم", money(await services.wallet.balance_units(customer.id)))

    step("بديل 2/4", "المزود يرفض — فشل + استرجاع كامل في معاملة واحدة")
    batch = await services.orders.process_pending_orders()
    info("فشل", batch.failed)
    failed = await repos.orders.get(order.id)
    assert failed is not None
    info("الحالة النهائية", failed.status)
    info("المبلغ المسترجَع", money(failed.refund_amount_units))
    info("سبب الفشل", failed.last_error)

    step("بديل 3/4", "الحركة المالية والرصيد")
    movements = await repos.transactions.list_by_user(customer.id, limit=2)
    for movement in movements:
        info(movement.type, f"{money(movement.amount_units)} | مرجع {movement.reference}")
    info("الرصيد بعد الاسترجاع", money(await services.wallet.balance_units(customer.id)))
    info("المال المفقود", money(before - await services.wallet.balance_units(customer.id)))
    ledger = await services.wallet.verify_ledger(customer.id)
    info("مطابقة الدفتر", "متوازن ✅" if ledger.is_balanced else "اختلال ❌")

    step("بديل 4/4", "إشعار العميل والأدمن + منع إعادة الإرسال")
    await services.notifications.dispatch_pending(sender, limit=50)
    again = await services.orders.process_pending_orders()
    info("محاولات إرسال جديدة للطلب الفاشل", again.claimed)
    errors = await repos.error_logs.list_recent(limit=3)
    info("أحدث خطأ مسجَّل", errors[0]["message"] if errors else "—")


async def run(keep: bool) -> int:
    """تشغيل العرض كاملاً وإرجاع كود الخروج."""
    db_path = ROOT / "data" / "demo_cycle.db"
    # السجلات إلى الملف فقط حتى لا تتداخل أسطر اللوق مع خطوات العرض
    setup_logging(ROOT / "logs" / "demo_cycle.log", "INFO", console=False)
    print("\n🧪 عرض الدورة الكاملة — المرحلة 2 (مزود وهمي، قاعدة بيانات مؤقتة، بلا شبكة)")
    shared_client = MockProviderClient()
    registry.register_client("mock", lambda **_kwargs: shared_client)   # عميل واحد يحتفظ بحالته

    db, repos, services, env = await build_environment(db_path)
    try:
        await happy_path(services, repos, env)
        await failure_path(services, repos, env, shared_client)
        print(f"\n{LINE}\n✅ انتهى العرض: الدورة الكاملة والمسار البديل نُفِّذا دون فقدان أي مبلغ.\n{LINE}")
    finally:
        await db.close()
        registry.register_client("mock", MockProviderClient)
        if not keep and db_path.exists():
            db_path.unlink()
            print(f"🧹 حُذفت قاعدة البيانات المؤقتة: {db_path}")
        elif keep:
            print(f"💾 أُبقيت قاعدة البيانات المؤقتة: {db_path}")
    return 0


def main() -> int:
    """نقطة الدخول: قراءة الخيارات ثم تشغيل العرض."""
    parser = argparse.ArgumentParser(description="عرض حيّ للدورة الكاملة (المرحلة 2)")
    parser.add_argument("--keep", action="store_true", help="إبقاء قاعدة البيانات المؤقتة بعد الانتهاء")
    args = parser.parse_args()
    return asyncio.run(run(args.keep))


if __name__ == "__main__":
    raise SystemExit(main())
```

# الاختبارات — tests/

## `tests/conftest.py`

```python
"""
تهيئة بيئة الاختبارات.

كل اختبار يحصل على قاعدة بيانات مؤقتة جديدة مع تطبيق كامل الترحيلات،
حتى تكون الاختبارات مستقلة تماماً عن بعضها وعن بيانات التشغيل الحقيقية.

تنظيم الاختبارات:
    tests/unit/        : منطق خالص بلا قاعدة بيانات (مال، حالات، تحقق، صلاحيات).
    tests/integration/ : خدمة واحدة مع قاعدة بيانات حقيقية (مؤقتة).
    tests/e2e/         : الدورة الكاملة عبر كل الخدمات معاً.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import pytest_asyncio

# إضافة جذر المشروع إلى مسار الاستيراد حتى تعمل الاستيرادات المطلقة
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database.database import Database  # noqa: E402
from database.migrator import Migrator  # noqa: E402
from database.repositories import Repositories  # noqa: E402
from integrations.providers import registry  # noqa: E402
from integrations.providers.mock import MockProviderClient  # noqa: E402
from services import ServiceContainer, build_services  # noqa: E402
from utils.security import SecretBox, generate_encryption_key  # noqa: E402


@pytest_asyncio.fixture
async def db(tmp_path: Path):
    """قاعدة بيانات مؤقتة مع تطبيق كل الترحيلات."""
    database = Database(tmp_path / "test.db", read_pool_size=2)
    await database.connect()
    await Migrator(database).apply_all()
    try:
        yield database
    finally:
        await database.close()


@pytest_asyncio.fixture
async def repos(db: Database) -> Repositories:
    """حاوية المستودعات على قاعدة بيانات الاختبار."""
    return Repositories(db)


@pytest.fixture
def secret_box() -> SecretBox:
    """صندوق تشفير بمفتاح مؤقت يُولَّد لكل اختبار (لا مفاتيح ثابتة في الكود)."""
    return SecretBox(generate_encryption_key())


@pytest_asyncio.fixture
async def services(db: Database, repos: Repositories, secret_box: SecretBox) -> ServiceContainer:
    """
    حاوية الخدمات كاملة الربط.

    `settings_ttl_seconds=0` يلغي كاش الإعدادات حتى يرى الاختبار أي تعديل فوراً.
    """
    return build_services(db, repos, secret_box=secret_box, settings_ttl_seconds=0)


@pytest_asyncio.fixture
async def user(db: Database, repos: Repositories):
    """مستخدم اختباري جاهز برصيد صفر."""
    async with db.transaction() as tx:
        return await repos.users.create(
            tx, telegram_id=100200300, username="tester", first_name="Tester"
        )


@pytest_asyncio.fixture
async def admin(db: Database, repos: Repositories):
    """مستخدم بدور admin (الصلاحيات تأتي من جدول الأدوار المزروع في الترحيل 0002)."""
    async with db.transaction() as tx:
        return await repos.users.create(
            tx, telegram_id=900900900, username="bossadmin", first_name="Admin", role="admin"
        )


@pytest_asyncio.fixture
async def super_admin(db: Database, repos: Repositories):
    """مستخدم بدور super_admin (يملك كل الصلاحيات)."""
    async with db.transaction() as tx:
        return await repos.users.create(
            tx, telegram_id=777777777, username="root", first_name="Root", role="super_admin"
        )


@pytest_asyncio.fixture
async def provider(db: Database, repos: Repositories):
    """مزود اختباري (المفتاح هنا نص وهمي مشفَّر شكلياً — لا يُستخدم للاتصال)."""
    async with db.transaction() as tx:
        return await repos.providers.create(
            tx,
            name="TestProvider",
            api_url="https://example.invalid/api/v2",
            api_key_enc="ENC::dummy-not-a-real-key",
            api_key_hint="1234",
        )


@pytest.fixture
def mock_client() -> MockProviderClient:
    """
    عميل مزود وهمي **مشترك**: يُعاد نفس الكائن لكل استدعاء داخل الاختبار.

    السبب: `ProviderService.client_for` يبني عميلاً جديداً في كل عملية، بينما يحتاج
    المزود الوهمي الاحتفاظ بحالة الطلبات بين الإرسال وفحص الحالة.
    """
    shared = MockProviderClient()
    registry.register_client("mock", lambda **_kwargs: shared)
    try:
        yield shared
    finally:
        registry.register_client("mock", MockProviderClient)  # إعادة السجل كما كان


@pytest_asyncio.fixture
async def mock_provider(db: Database, repos: Repositories, secret_box: SecretBox):
    """مزود من نوع mock بمفتاح مشفَّر فعلياً (يُفك عند الاتصال)."""
    async with db.transaction() as tx:
        return await repos.providers.create(
            tx,
            name="MockProvider",
            api_url="https://mock.invalid/api/v2",
            api_key_enc=secret_box.encrypt("mock-key-123456"),
            api_key_hint="3456",
            api_type="mock",
        )


@pytest_asyncio.fixture
async def service(db: Database, repos: Repositories, provider):
    """خدمة اختبارية بسعر 1.0000 لكل ألف (10000 نقطة)."""
    categories = await repos.categories.list_all()
    async with db.transaction() as tx:
        return await repos.services.create(
            tx,
            category_id=categories[0].id,
            provider_id=provider.id,
            provider_service_id="555",
            name="متابعين انستغرام اختبار",
            price_per_1000_units=10_000,
            provider_price_per_1000_units=6_000,
            min_quantity=100,
            max_quantity=10_000,
        )


@pytest_asyncio.fixture
async def mock_service(db: Database, repos: Repositories, mock_provider):
    """خدمة مرتبطة بالمزود الوهمي (تُستخدم في اختبارات الدورة الكاملة)."""
    categories = await repos.categories.list_all()
    async with db.transaction() as tx:
        return await repos.services.create(
            tx,
            category_id=categories[0].id,
            provider_id=mock_provider.id,
            provider_service_id="555",
            name="متابعين انستغرام (Mock)",
            price_per_1000_units=10_000,     # 1.0000 لكل ألف ⇒ طلب 1000 يكلف 10000 نقطة
            provider_price_per_1000_units=6_000,
            min_quantity=100,
            max_quantity=100_000,
        )


@pytest_asyncio.fixture
async def payment_method(db: Database, repos: Repositories):
    """طريقة دفع يدوية للاختبار."""
    async with db.transaction() as tx:
        return await repos.payment_methods.create(
            tx, code="test_wallet", name_ar="محفظة اختبار", instructions_ar="حوّل ثم أرسل الإثبات"
        )


@pytest.fixture
def anyio_backend() -> str:
    """تثبيت backend الخاص بالاختبارات غير المتزامنة."""
    return "asyncio"
```

## `tests/unit/test_order_state.py`

```python
"""
اختبارات آلة حالات الطلب — بلا قاعدة بيانات.

أهميتها: هذه الجداول هي الحارس الذي يمنع «تغيير حالة الطلب من أي مكان».
أي تعديل يفتح انتقالاً خطيراً (مثل completed ← pending) يجب أن يُسقط هذه الاختبارات.
"""

from __future__ import annotations

import pytest

from core.enums import OrderStatus
from core.exceptions import InvalidStateTransitionError
from core.order_state import (
    ACTIVE_STATUSES,
    ALLOWED_TRANSITIONS,
    FINAL_STATUSES,
    allowed_next,
    assert_transition,
    can_transition,
    is_active,
    is_final,
    label_ar,
    map_provider_status,
    requires_full_refund,
    requires_partial_refund,
    sources_for,
)


def test_every_status_has_an_entry() -> None:
    """كل حالة معرّفة في الـEnum لها صف في جدول الانتقالات (ولو فارغاً)."""
    assert set(ALLOWED_TRANSITIONS) == set(OrderStatus)


def test_final_statuses_have_no_exit_except_refund() -> None:
    """الحالات النهائية لا تخرج إلا إلى refunded (لتسجيل إعادة المال بعد الإلغاء)."""
    for status in FINAL_STATUSES:
        assert allowed_next(status) <= {OrderStatus.REFUNDED}


def test_completed_is_terminal() -> None:
    """الطلب المكتمل لا يُعاد فتحه بأي شكل."""
    assert is_final(OrderStatus.COMPLETED)
    assert allowed_next(OrderStatus.COMPLETED) == frozenset()
    assert not can_transition(OrderStatus.COMPLETED, OrderStatus.PENDING)
    assert not can_transition(OrderStatus.COMPLETED, OrderStatus.IN_PROGRESS)


def test_happy_path_transitions_allowed() -> None:
    """المسار الطبيعي للطلب مسموح خطوة بخطوة."""
    path = [
        OrderStatus.PENDING,
        OrderStatus.SUBMITTING,
        OrderStatus.SUBMITTED,
        OrderStatus.IN_PROGRESS,
        OrderStatus.COMPLETED,
    ]
    for current, nxt in zip(path, path[1:]):
        assert can_transition(current, nxt), f"ممنوع خطأً: {current} ← {nxt}"


def test_failure_path_transitions_allowed() -> None:
    """مسار الفشل: submitting ← failed ← refunded."""
    assert can_transition(OrderStatus.SUBMITTING, OrderStatus.FAILED)
    assert can_transition(OrderStatus.FAILED, OrderStatus.REFUNDED)
    assert can_transition(OrderStatus.CANCELED, OrderStatus.REFUNDED)


def test_same_status_is_treated_as_no_op() -> None:
    """
    الانتقال إلى نفس الحالة مسموح بوصفه «لا تغيير».

    السبب: فحص الحالة الدوري قد يعيد نفس النتيجة مرات كثيرة، ولا يصح أن يُعتبر خطأً.
    منع التكرار الفعلي يتم في `OrderService._transition` الذي يتوقف قبل أي كتابة
    أو إشعار عندما تكون الحالة الجديدة مطابقة للحالية.
    """
    for status in OrderStatus:
        assert can_transition(status, status)
        assert status not in allowed_next(status)


def test_skipping_submission_is_rejected() -> None:
    """ممنوع القفز من pending إلى completed دون المرور بالمزود."""
    assert not can_transition(OrderStatus.PENDING, OrderStatus.COMPLETED)
    assert not can_transition(OrderStatus.PENDING, OrderStatus.IN_PROGRESS)


def test_assert_transition_raises_with_order_id() -> None:
    """رسالة الخطأ تذكر رقم الطلب لتسهيل التتبع."""
    with pytest.raises(InvalidStateTransitionError) as error:
        assert_transition(OrderStatus.COMPLETED, OrderStatus.PENDING, order_id=77)
    assert "77" in str(error.value)


def test_uncertain_cannot_be_resubmitted_automatically() -> None:
    """الحالة غير المؤكدة لا تعود إلى pending — فإعادة الإرسال تعني طلباً مكرراً."""
    assert OrderStatus.PENDING not in allowed_next(OrderStatus.SUBMIT_UNCERTAIN)
    assert allowed_next(OrderStatus.SUBMIT_UNCERTAIN) == frozenset(
        {OrderStatus.SUBMITTED, OrderStatus.FAILED}
    )


def test_active_statuses_are_not_final() -> None:
    """لا تتداخل مجموعة الحالات النشطة مع النهائية."""
    assert ACTIVE_STATUSES.isdisjoint(FINAL_STATUSES)
    assert is_active(OrderStatus.IN_PROGRESS)
    assert not is_active(OrderStatus.COMPLETED)


def test_sources_for_is_inverse_of_allowed_next() -> None:
    """دالة المصادر تعطي عكس جدول الانتقالات بدقة."""
    for status in OrderStatus:
        for source in sources_for(status):
            assert status in allowed_next(source)


def test_refund_requirements() -> None:
    """الفشل والإلغاء يوجبان استرجاعاً كاملاً، والتنفيذ الجزئي استرجاعاً جزئياً."""
    assert requires_full_refund(OrderStatus.FAILED)
    assert requires_full_refund(OrderStatus.CANCELED)
    assert requires_partial_refund(OrderStatus.PARTIAL)
    assert not requires_full_refund(OrderStatus.COMPLETED)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Pending", OrderStatus.SUBMITTED),
        ("In progress", OrderStatus.IN_PROGRESS),
        ("Processing", OrderStatus.IN_PROGRESS),
        ("Completed", OrderStatus.COMPLETED),
        ("completed", OrderStatus.COMPLETED),
        ("  COMPLETED  ", OrderStatus.COMPLETED),
        ("Partial", OrderStatus.PARTIAL),
        ("Canceled", OrderStatus.CANCELED),
        ("Cancelled", OrderStatus.CANCELED),
        ("Fail", OrderStatus.FAILED),
    ],
)
def test_provider_status_mapping(raw: str, expected: str) -> None:
    """نصوص المزودين الشائعة تُترجم إلى حالات النظام بشكل صحيح."""
    assert map_provider_status(raw) == expected


def test_unknown_provider_status_returns_none() -> None:
    """الحالة المجهولة تُعاد None — فلا نغيّر حالة الطلب بالتخمين."""
    assert map_provider_status("Something New") is None
    assert map_provider_status("") is None
    assert map_provider_status(None) is None


def test_labels_are_arabic_for_all_statuses() -> None:
    """لكل حالة تسمية عربية للعرض."""
    for status in OrderStatus:
        label = label_ar(status)
        assert label and label != status
```

## `tests/unit/test_payment_state.py`

```python
"""
اختبارات آلة حالات طلب الشحن.

القاعدة الحاكمة: طلب الشحن يُعالَج مرة واحدة فقط. أي انتقال يسمح بإعادة
معالجة طلب معتمد = خطر إضافة الرصيد مرتين.
"""

from __future__ import annotations

import pytest

from core.enums import PaymentStatus
from core.exceptions import InvalidStateTransitionError
from core.payment_state import (
    ALLOWED_TRANSITIONS,
    CREDITING_STATUS,
    FINAL_STATUSES,
    assert_transition,
    can_transition,
    is_final,
    label_ar,
)


def test_every_status_has_an_entry() -> None:
    """كل حالة دفع لها صف في جدول الانتقالات."""
    assert set(ALLOWED_TRANSITIONS) == set(PaymentStatus)


def test_pending_can_go_to_all_final_states() -> None:
    """الطلب المعلّق يمكن أن ينتهي بالاعتماد أو الرفض أو الإلغاء أو انتهاء الصلاحية."""
    assert ALLOWED_TRANSITIONS[PaymentStatus.PENDING] == frozenset(
        {
            PaymentStatus.APPROVED,
            PaymentStatus.REJECTED,
            PaymentStatus.CANCELLED,
            PaymentStatus.EXPIRED,
        }
    )


def test_final_states_are_closed() -> None:
    """الحالات النهائية مغلقة تماماً — لا إعادة اعتماد ولا إعادة فتح."""
    for status in FINAL_STATUSES:
        assert is_final(status)
        assert ALLOWED_TRANSITIONS[status] == frozenset()


def test_approved_cannot_be_reprocessed() -> None:
    """ممنوع إعادة اعتماد طلب معتمد (حماية من إضافة الرصيد مرتين)."""
    assert not can_transition(PaymentStatus.APPROVED, PaymentStatus.APPROVED)
    assert not can_transition(PaymentStatus.APPROVED, PaymentStatus.PENDING)
    assert not can_transition(PaymentStatus.REJECTED, PaymentStatus.APPROVED)


def test_same_status_is_rejected_for_payments() -> None:
    """
    بخلاف الطلبات، لا يُسمح هنا بالانتقال من الحالة إلى نفسها.

    السبب: كل انتقال في الدفع يحمل أثراً مالياً، فإعادة الحالة نفسها تعني
    محاولة ثانية لتنفيذ نفس العملية.
    """
    for status in PaymentStatus:
        assert not can_transition(status, status)


def test_assert_transition_mentions_payment_id() -> None:
    """رسالة الخطأ تذكر رقم طلب الشحن."""
    with pytest.raises(InvalidStateTransitionError) as error:
        assert_transition(PaymentStatus.APPROVED, PaymentStatus.REJECTED, payment_id=42)
    assert "42" in str(error.value)


def test_crediting_status_is_approved() -> None:
    """الحالة الوحيدة التي تضيف رصيداً هي approved."""
    assert CREDITING_STATUS == PaymentStatus.APPROVED


def test_labels_are_arabic() -> None:
    """لكل حالة تسمية عربية."""
    for status in PaymentStatus:
        assert label_ar(status) not in {"", status}
```

## `tests/unit/test_permission_catalog.py`

```python
"""
حارس كتالوج الصلاحيات.

الهدف: منع أخطر خطأ صامت في نظام الصلاحيات — أن يُكتب كود يستخدم
`Permission.X` بقيمة لا توجد في كتالوج `PERMISSIONS` المزروع في قاعدة البيانات،
فتفشل عمليات التحقق دائماً (أو تنجح دائماً) دون أن ينتبه أحد.

هذا الاختبار يفشل فوراً عند إضافة صلاحية في مكان ونسيانها في الآخر.
"""

from __future__ import annotations

from core.enums import Role
from core.permissions import PERMISSIONS, ROLE_DEFAULTS, Permission


def test_enum_matches_catalog_exactly() -> None:
    """قيم الـEnum مطابقة تماماً لأكواد الكتالوج — لا زيادة ولا نقصان."""
    enum_values = {member.value for member in Permission}
    catalog_codes = {item.code for item in PERMISSIONS}
    assert enum_values == catalog_codes, (
        f"فرق بين Enum والكتالوج: "
        f"زائد في Enum={sorted(enum_values - catalog_codes)} · "
        f"ناقص من Enum={sorted(catalog_codes - enum_values)}"
    )


def test_catalog_codes_are_unique() -> None:
    """لا يوجد كود صلاحية مكرر في الكتالوج."""
    codes = [item.code for item in PERMISSIONS]
    assert len(codes) == len(set(codes))


def test_enum_member_names_follow_code() -> None:
    """اسم عضو الـEnum مشتق من الكود (نقاط وشرطات ← شرطة سفلية بحروف كبيرة)."""
    for member in Permission:
        expected = member.value.replace(".", "_").upper()
        assert member.name == expected, f"اسم غير متوافق: {member.name} ≠ {expected}"


def test_role_defaults_reference_existing_codes() -> None:
    """كل صلاحية مذكورة في خرائط الأدوار موجودة فعلاً في الكتالوج."""
    catalog_codes = {item.code for item in PERMISSIONS}
    for role, codes in ROLE_DEFAULTS.items():
        unknown = set(codes) - catalog_codes
        assert not unknown, f"الدور {role} يشير إلى صلاحيات غير معرّفة: {sorted(unknown)}"


def test_super_admin_has_all_permissions() -> None:
    """الأدمن الأعلى يملك كل الصلاحيات دون استثناء."""
    assert set(ROLE_DEFAULTS[Role.SUPER_ADMIN]) == {item.code for item in PERMISSIONS}


def test_plain_user_has_no_admin_permissions() -> None:
    """المستخدم العادي لا يملك أي صلاحية إدارية."""
    assert set(ROLE_DEFAULTS[Role.USER]) == set()


def test_admin_cannot_manage_admins_by_default() -> None:
    """الأدمن العادي لا يملك إدارة المدراء ولا تغيير الأدوار (تبقى للأدمن الأعلى)."""
    admin_permissions = set(ROLE_DEFAULTS[Role.ADMIN])
    assert Permission.ADMINS_MANAGE not in admin_permissions
    assert Permission.USERS_ROLE_CHANGE not in admin_permissions
    assert Permission.ADMIN_ACCESS in admin_permissions
```

## `tests/unit/test_validators.py`

```python
"""
اختبارات التحقق من مدخلات المستخدم.

كل مُدخل من تيليجرام يمر عبر هذه الدوال، فأي ثغرة هنا تصل مباشرة إلى
قاعدة البيانات أو إلى المزود.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.exceptions import (
    InvalidAmountError,
    InvalidLinkError,
    QuantityOutOfRangeError,
    ValidationError,
)
from utils.validators import (
    clean_text,
    normalize_digits,
    normalize_username,
    parse_amount_units,
    validate_amount_range,
    validate_link,
    validate_message,
    validate_quantity,
    validate_subject,
    validate_telegram_id,
    validate_transaction_reference,
    validate_url,
)


# ------------------------------- الأرقام -------------------------------- #


def test_normalize_arabic_digits() -> None:
    """الأرقام العربية-الهندية تُحوَّل إلى أرقام لاتينية."""
    assert normalize_digits("١٢٣٤٥") == "12345"
    assert normalize_digits("۱۲۳") == "123"
    assert normalize_digits("abc 7") == "abc 7"


# -------------------------------- الروابط -------------------------------- #


@pytest.mark.parametrize(
    "link",
    [
        "https://instagram.com/username",
        "http://tiktok.com/@user/video/123",
        "instagram.com/user",  # بلا بروتوكول — يُضاف تلقائياً
    ],
)
def test_valid_links_accepted(link: str) -> None:
    """الروابط الصحيحة تُقبل وتُعاد بصيغة كاملة."""
    result = validate_link(link)
    assert result.startswith("http")


@pytest.mark.parametrize(
    "link",
    ["", "   ", "ftp://example.com/file", "not a link", "https://localhost", "http://" + "a" * 600],
)
def test_invalid_links_rejected(link: str) -> None:
    """الروابط الفارغة أو ذات البروتوكول غير المدعوم أو بلا نطاق تُرفض."""
    with pytest.raises(InvalidLinkError):
        validate_link(link)


def test_link_pattern_enforced() -> None:
    """نمط الخدمة يمنع إرسال رابط من منصة أخرى."""
    pattern = r"instagram\.com"
    assert validate_link("https://instagram.com/user", pattern=pattern)
    with pytest.raises(InvalidLinkError):
        validate_link("https://tiktok.com/@user", pattern=pattern)


def test_broken_service_pattern_reports_configuration_error() -> None:
    """نمط خاطئ في إعداد الخدمة يُبلَّغ كخطأ إعداد لا كخطأ من المستخدم."""
    with pytest.raises(ValidationError):
        validate_link("https://instagram.com/user", pattern="[unclosed")


# -------------------------------- الكميات -------------------------------- #


def test_quantity_within_range() -> None:
    """الكمية ضمن الحدود تُقبل، وتُقبل أيضاً مكتوبة بأرقام عربية أو بفواصل."""
    assert validate_quantity(500, min_quantity=100, max_quantity=1000) == 500
    assert validate_quantity("١٠٠٠", min_quantity=100, max_quantity=1000) == 1000
    assert validate_quantity("1,000", min_quantity=100, max_quantity=1000) == 1000


@pytest.mark.parametrize("raw", [50, 5000, "abc", "", "-100", True])
def test_quantity_out_of_range_rejected(raw) -> None:
    """الكميات خارج الحدود أو غير الرقمية تُرفض."""
    with pytest.raises(QuantityOutOfRangeError):
        validate_quantity(raw, min_quantity=100, max_quantity=1000)


# -------------------------------- المبالغ -------------------------------- #


def test_parse_amount_units_variants() -> None:
    """المبلغ يُقبل بصيغ متعددة ويُحوَّل إلى وحدات صحيحة (×10000)."""
    assert parse_amount_units("1") == 10_000
    assert parse_amount_units("1.5") == 15_000
    assert parse_amount_units("1,500") == 15_000_000
    assert parse_amount_units(Decimal("2.25")) == 22_500
    assert parse_amount_units("١٠") == 100_000


@pytest.mark.parametrize("raw", ["0", "-5", "abc", ""])
def test_invalid_amounts_rejected(raw: str) -> None:
    """المبالغ الصفرية والسالبة وغير الرقمية تُرفض."""
    with pytest.raises(InvalidAmountError):
        parse_amount_units(raw)


def test_amount_range_enforced() -> None:
    """حدود المبلغ تُطبَّق من الطرفين."""
    assert validate_amount_range(50_000, min_units=10_000, max_units=100_000) == 50_000
    with pytest.raises(InvalidAmountError):
        validate_amount_range(5_000, min_units=10_000, max_units=100_000)
    with pytest.raises(InvalidAmountError):
        validate_amount_range(500_000, min_units=10_000, max_units=100_000)


def test_zero_max_means_no_upper_limit() -> None:
    """الحد الأقصى صفر يعني «بلا حد أقصى»."""
    assert validate_amount_range(10_000_000, min_units=0, max_units=0) == 10_000_000


# ------------------------------ أرقام الحوالات ----------------------------- #


def test_transaction_reference_accepted() -> None:
    """مرجع الحوالة المكوَّن من أرقام/حروف إنجليزية يُقبل."""
    assert validate_transaction_reference("TRX-99812") == "TRX-99812"
    assert validate_transaction_reference("١٢٣٤٥") == "12345"


def test_transaction_reference_required_and_format() -> None:
    """المرجع مطلوب عند الطلب، والرموز غير المسموحة تُرفض."""
    with pytest.raises(ValidationError):
        validate_transaction_reference("", required=True)
    with pytest.raises(ValidationError):
        validate_transaction_reference("ab")          # قصير جداً
    with pytest.raises(ValidationError):
        validate_transaction_reference("حوالة ١٢٣")   # حروف عربية ومسافات
    assert validate_transaction_reference(None, required=False) is None


# ------------------------------- نصوص عامة ------------------------------- #


def test_clean_text_trims_and_limits() -> None:
    """تنظيف النص يوحّد الفراغات ويفرض الحد الأقصى."""
    assert clean_text("  مرحبا   بك  ", field="الاسم", max_length=20) == "مرحبا بك"
    with pytest.raises(ValidationError):
        clean_text("x" * 50, field="الاسم", max_length=20)
    with pytest.raises(ValidationError):
        clean_text("   ", field="الاسم", max_length=20)


def test_subject_and_message_validation() -> None:
    """عنوان التذكرة ونصها يخضعان لحدود الطول."""
    assert validate_subject("مشكلة في طلب") == "مشكلة في طلب"
    assert validate_message("لم يصلني الطلب") == "لم يصلني الطلب"
    with pytest.raises(ValidationError):
        validate_subject("")
    with pytest.raises(ValidationError):
        validate_message("x" * 5000)


def test_telegram_id_and_username() -> None:
    """معرف تيليجرام رقمي موجب، واسم المستخدم بلا @ وبطول صحيح."""
    assert validate_telegram_id("123456789") == 123456789
    with pytest.raises(ValidationError):
        validate_telegram_id("-5")
    with pytest.raises(ValidationError):
        validate_telegram_id("abc")
    assert normalize_username("@Tester_1") == "Tester_1"
    assert normalize_username("ab") is None
    assert normalize_username(None) is None


def test_validate_url_for_provider_api() -> None:
    """رابط API المزود يجب أن يكون http(s) صحيحاً."""
    assert validate_url("https://panel.example.com/api/v2") == "https://panel.example.com/api/v2"
    with pytest.raises(ValidationError):
        validate_url("javascript:alert(1)")
    with pytest.raises(ValidationError):
        validate_url("")
```

## `tests/integration/test_wallet_service.py`

```python
"""
اختبارات المحفظة — الخدمة المالية المركزية.

هذه أهم اختبارات المشروع: أي خلل هنا يعني مالاً ضائعاً أو رصيداً سالباً.
تشمل: الخصم، الاسترجاع (الكامل والجزئي)، منع التكرار، التسويات اليدوية،
تدقيق الدفتر، واختبار السباق (50 خصماً متزامناً على رصيد يكفي 10 فقط).
"""

from __future__ import annotations

import asyncio

import pytest

from core.enums import TransactionType
from core.exceptions import (
    DuplicateOperationError,
    InsufficientBalanceError,
    InvalidAmountError,
    WalletError,
)
from database.database import Database
from database.models import Service, User
from database.repositories import Repositories
from services import ServiceContainer

ORDER_COST = 10_000  # 1.0000 من وحدة العملة


async def _make_order(db: Database, repos: Repositories, user: User, service: Service, index: int):
    """إنشاء صف طلب خام للاختبار (بلا خصم) — الخصم يتم عبر المحفظة في الاختبار نفسه."""
    async with db.transaction() as tx:
        return await repos.orders.create(
            tx,
            user_id=user.id,
            service_id=service.id,
            provider_id=service.provider_id,
            service_name_snapshot=service.name,
            price_per_1000_snapshot_units=service.price_per_1000_units,
            link=f"https://instagram.com/u{index}",
            quantity=1000,
            cost_units=ORDER_COST,
            client_request_id=f"test-{index}",
        )


async def _credit(services: ServiceContainer, user: User, amount_units: int, admin: User) -> None:
    """شحن رصيد اختباري عبر المسار الرسمي (تسوية يدوية من الأدمن)."""
    await services.wallet.adjust_balance(
        target=user, amount_units=amount_units, admin=admin, reason="رصيد اختباري", credit=True
    )


# ------------------------------- الخصم ---------------------------------- #


async def test_charge_debits_and_records_transaction(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, admin: User, service: Service
) -> None:
    """الخصم ينقص الرصيد ويكتب حركة مالية بنفس المعاملة."""
    await _credit(services, user, 50_000, admin)
    order = await _make_order(db, repos, user, service, 1)

    async with db.transaction() as tx:
        transaction = await services.wallet.charge_for_order(
            tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
        )

    assert transaction.type == TransactionType.ORDER
    assert transaction.balance_before_units == 50_000
    assert transaction.balance_after_units == 40_000
    assert await services.wallet.balance_units(user.id) == 40_000

    refreshed = await repos.users.get_by_id(user.id)
    assert refreshed is not None and refreshed.total_spent_units == ORDER_COST


async def test_charge_without_balance_raises_and_changes_nothing(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, service: Service
) -> None:
    """الخصم بلا رصيد كافٍ يرفع استثناءً ولا يغيّر شيئاً."""
    order = await _make_order(db, repos, user, service, 2)

    with pytest.raises(InsufficientBalanceError):
        async with db.transaction() as tx:
            await services.wallet.charge_for_order(
                tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
            )

    assert await services.wallet.balance_units(user.id) == 0
    assert await repos.transactions.count_by_user(user.id) == 0


async def test_double_charge_for_same_order_rejected(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, admin: User, service: Service
) -> None:
    """لا يُخصم الطلب الواحد مرتين (مرجع العملية فريد)."""
    await _credit(services, user, 50_000, admin)
    order = await _make_order(db, repos, user, service, 3)

    async with db.transaction() as tx:
        await services.wallet.charge_for_order(
            tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
        )

    with pytest.raises(DuplicateOperationError):
        async with db.transaction() as tx:
            await services.wallet.charge_for_order(
                tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
            )

    assert await services.wallet.balance_units(user.id) == 40_000


@pytest.mark.parametrize("amount", [0, -1])
async def test_invalid_amounts_rejected(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, service: Service, amount: int
) -> None:
    """المبالغ غير الموجبة مرفوضة في كل العمليات المالية."""
    order = await _make_order(db, repos, user, service, 4)
    with pytest.raises(InvalidAmountError):
        async with db.transaction() as tx:
            await services.wallet.charge_for_order(
                tx, user_id=user.id, order_id=order.id, amount_units=amount
            )


# ------------------------------ الاسترجاع -------------------------------- #


async def test_full_refund_returns_money_once(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, admin: User, service: Service
) -> None:
    """الاسترجاع الكامل يعيد المبلغ مرة واحدة فقط، وإعادة المحاولة لا تضاعفه."""
    await _credit(services, user, 50_000, admin)
    order = await _make_order(db, repos, user, service, 5)

    async with db.transaction() as tx:
        await services.wallet.charge_for_order(
            tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
        )
    async with db.transaction() as tx:
        first = await services.wallet.refund_order(
            tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
        )
    async with db.transaction() as tx:
        second = await services.wallet.refund_order(
            tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
        )

    assert first is not None and first.type == TransactionType.REFUND
    assert second is None, "الاسترجاع المكرر يجب أن يُتجاهل بهدوء لا أن يضاعف المال"
    assert await services.wallet.balance_units(user.id) == 50_000

    refreshed_order = await repos.orders.get(order.id)
    assert refreshed_order is not None
    assert refreshed_order.refund_amount_units == ORDER_COST
    assert refreshed_order.refunded_at is not None


async def test_partial_refund_cannot_exceed_order_cost(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, admin: User, service: Service
) -> None:
    """مجموع الاسترجاعات لا يتجاوز تكلفة الطلب أبداً."""
    await _credit(services, user, 50_000, admin)
    order = await _make_order(db, repos, user, service, 6)
    async with db.transaction() as tx:
        await services.wallet.charge_for_order(
            tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
        )

    async with db.transaction() as tx:
        await services.wallet.refund_order(
            tx, user_id=user.id, order_id=order.id, amount_units=4_000, partial=True
        )

    with pytest.raises(WalletError):
        async with db.transaction() as tx:
            await services.wallet.refund_order(
                tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
            )

    assert await services.wallet.balance_units(user.id) == 44_000
    refreshed = await repos.orders.get(order.id)
    assert refreshed is not None and refreshed.refund_amount_units == 4_000


# ---------------------------- الإيداع والتسوية ---------------------------- #


async def test_credit_from_payment_counts_as_deposit(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, payment_method
) -> None:
    """الإيداع المعتمد يزيد الرصيد ويزيد إجمالي الإيداعات."""
    async with db.transaction() as tx:
        payment = await repos.payments.create(
            tx, user_id=user.id, method_id=payment_method.id, amount_units=30_000
        )
    async with db.transaction() as tx:
        transaction = await services.wallet.credit_from_payment(
            tx, user_id=user.id, payment_id=payment.id, amount_units=30_000
        )

    assert transaction.type == TransactionType.DEPOSIT
    refreshed = await repos.users.get_by_id(user.id)
    assert refreshed is not None
    assert refreshed.balance_units == 30_000
    assert refreshed.total_deposited_units == 30_000

    with pytest.raises(DuplicateOperationError):
        async with db.transaction() as tx:
            await services.wallet.credit_from_payment(
                tx, user_id=user.id, payment_id=payment.id, amount_units=30_000
            )


async def test_manual_adjustments_write_audit_log(
    services: ServiceContainer, repos: Repositories, user: User, admin: User
) -> None:
    """التسوية اليدوية تُسجَّل في سجل التدقيق باسم الأدمن المنفّذ."""
    await services.wallet.adjust_balance(
        target=user, amount_units=20_000, admin=admin, reason="تعويض", credit=True
    )
    await services.wallet.adjust_balance(
        target=user, amount_units=5_000, admin=admin, reason="تصحيح خطأ", credit=False
    )

    assert await services.wallet.balance_units(user.id) == 15_000
    logs = await repos.audit.list_by_admin(admin.id, limit=10)
    actions = {log.action for log in logs}
    assert "users.balance.credit" in actions
    assert "users.balance.debit" in actions


async def test_manual_debit_cannot_overdraw(
    services: ServiceContainer, user: User, admin: User
) -> None:
    """الخصم اليدوي لا يجعل الرصيد سالباً."""
    await _credit(services, user, 10_000, admin)
    with pytest.raises(InsufficientBalanceError):
        await services.wallet.adjust_balance(
            target=user, amount_units=99_000, admin=admin, reason="خصم كبير", credit=False
        )
    assert await services.wallet.balance_units(user.id) == 10_000


# ------------------------------ تدقيق الدفتر ------------------------------ #


async def test_ledger_matches_stored_balance(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, admin: User, service: Service
) -> None:
    """الرصيد المخزَّن يساوي مجموع دفتر الحركات بعد سلسلة عمليات."""
    await _credit(services, user, 100_000, admin)
    order = await _make_order(db, repos, user, service, 7)
    async with db.transaction() as tx:
        await services.wallet.charge_for_order(
            tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
        )
    async with db.transaction() as tx:
        await services.wallet.refund_order(
            tx, user_id=user.id, order_id=order.id, amount_units=2_000, partial=True
        )

    check = await services.wallet.verify_ledger(user.id)
    assert check.is_balanced, f"اختلال محاسبي بمقدار {check.difference_units}"
    assert check.difference_units == 0


# ------------------------------ اختبار السباق ----------------------------- #


async def test_fifty_concurrent_charges_never_overdraw(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, admin: User, service: Service
) -> None:
    """
    الاختبار الإلزامي: 50 خصماً متزامناً على رصيد يكفي 10 عمليات فقط.

    المتوقع: ينجح 10 بالضبط، ويفشل 40 بـInsufficientBalanceError،
    والرصيد النهائي صفر — لا رصيد سالب ولا خصم ضائع.
    """
    await _credit(services, user, ORDER_COST * 10, admin)
    orders = [await _make_order(db, repos, user, service, 100 + i) for i in range(50)]

    async def charge(order_id: int) -> bool:
        """محاولة خصم واحدة مستقلة بمعاملتها الخاصة."""
        try:
            async with db.transaction() as tx:
                await services.wallet.charge_for_order(
                    tx, user_id=user.id, order_id=order_id, amount_units=ORDER_COST
                )
            return True
        except InsufficientBalanceError:
            return False

    results = await asyncio.gather(*(charge(order.id) for order in orders))

    assert sum(results) == 10, f"نجح {sum(results)} خصماً بدل 10 بالضبط"
    assert await services.wallet.balance_units(user.id) == 0

    charge_transactions = [
        transaction
        for transaction in await repos.transactions.list_by_user(user.id, limit=100)
        if transaction.type == TransactionType.ORDER
    ]
    assert len(charge_transactions) == 10
    assert all(transaction.balance_after_units >= 0 for transaction in charge_transactions)

    check = await services.wallet.verify_ledger(user.id)
    assert check.is_balanced


async def test_concurrent_refunds_credit_once(
    db: Database, repos: Repositories, services: ServiceContainer, user: User, admin: User, service: Service
) -> None:
    """عشر محاولات استرجاع متزامنة لنفس الطلب تُعيد المبلغ مرة واحدة فقط."""
    await _credit(services, user, 50_000, admin)
    order = await _make_order(db, repos, user, service, 200)
    async with db.transaction() as tx:
        await services.wallet.charge_for_order(
            tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
        )

    async def refund() -> bool:
        """محاولة استرجاع واحدة."""
        try:
            async with db.transaction() as tx:
                transaction = await services.wallet.refund_order(
                    tx, user_id=user.id, order_id=order.id, amount_units=ORDER_COST
                )
            return transaction is not None
        except WalletError:
            return False

    results = await asyncio.gather(*(refund() for _ in range(10)))

    assert sum(results) == 1
    assert await services.wallet.balance_units(user.id) == 50_000
    refreshed = await repos.orders.get(order.id)
    assert refreshed is not None and refreshed.refund_amount_units == ORDER_COST
```

## `tests/integration/test_auth_service.py`

```python
"""
اختبارات الصلاحيات والحماية.

القاعدة المعتمدة: لا أدمن ثابت في الكود — كل شيء من قاعدة البيانات،
ويمكن منح أو منع أي صلاحية لمستخدم بعينه دون تغيير دوره.
"""

from __future__ import annotations

import pytest

from core.enums import Role
from core.exceptions import (
    MaintenanceModeError,
    PermissionDeniedError,
    UserBannedError,
)
from core.permissions import Permission
from database.database import Database
from database.models import User
from database.repositories import Repositories
from services import ServiceContainer


async def test_role_permissions_come_from_database(
    services: ServiceContainer, user: User, admin: User, super_admin: User
) -> None:
    """الصلاحيات تُقرأ من جدول الأدوار لا من ثوابت في الكود."""
    assert await services.auth.permissions_of(user) == set()
    assert await services.auth.has_permission(admin, Permission.ORDERS_VIEW)
    assert not await services.auth.has_permission(admin, Permission.ADMINS_MANAGE)
    assert await services.auth.has_permission(super_admin, Permission.ADMINS_MANAGE)


async def test_require_permission_records_denied_attempt(
    services: ServiceContainer, repos: Repositories, user: User
) -> None:
    """محاولة الوصول غير المصرّح بها تُرفض وتُسجَّل في سجل التدقيق."""
    with pytest.raises(PermissionDeniedError):
        await services.auth.require_permission(user, Permission.STATS_VIEW, context="dashboard")

    logs = await repos.audit.list_recent(limit=5)
    assert any(log.action == "security.permission_denied" for log in logs)


async def test_banned_user_is_blocked_everywhere(
    services: ServiceContainer, user: User, admin: User
) -> None:
    """المستخدم المحظور يُمنع من أي إجراء."""
    await services.users.ban(admin, user.id, reason="سلوك مسيء")
    banned = await services.users.get(user.id)
    assert banned is not None

    with pytest.raises(UserBannedError):
        await services.auth.guard(banned)

    await services.users.unban(admin, user.id)
    restored = await services.users.get(user.id)
    assert restored is not None
    await services.auth.guard(restored)  # لا يرفع استثناءً بعد رفع الحظر


async def test_maintenance_mode_blocks_users_not_admins(
    services: ServiceContainer, user: User, admin: User, super_admin: User
) -> None:
    """وضع الصيانة يوقف المستخدمين ويُبقي الأدمن قادراً على العمل."""
    await services.settings.set("maintenance_mode", True)

    with pytest.raises(MaintenanceModeError):
        await services.auth.guard(user)

    await services.auth.guard(admin)
    await services.auth.guard(super_admin)

    await services.settings.set("maintenance_mode", False)
    await services.auth.guard(user)


async def test_individual_permission_override(
    services: ServiceContainer, db: Database, repos: Repositories, super_admin: User
) -> None:
    """يمكن منح صلاحية واحدة لمستخدم عادي دون ترقيته إلى أدمن."""
    async with db.transaction() as tx:
        helper = await repos.users.create(tx, telegram_id=321321321, first_name="Helper")

    assert not await services.auth.has_permission(helper, Permission.TICKETS_REPLY)

    await services.auth.set_user_permission(
        super_admin, helper.id, Permission.TICKETS_REPLY, allow=True
    )
    assert await services.auth.has_permission(helper, Permission.TICKETS_REPLY)
    assert helper.role == Role.USER  # الدور لم يتغير

    await services.auth.clear_user_permission(super_admin, helper.id, Permission.TICKETS_REPLY)
    assert not await services.auth.has_permission(helper, Permission.TICKETS_REPLY)


async def test_deny_override_beats_role_permission(
    services: ServiceContainer, repos: Repositories, admin: User, super_admin: User
) -> None:
    """المنع الفردي يتقدّم على صلاحية الدور."""
    assert await services.auth.has_permission(admin, Permission.ORDERS_CANCEL)

    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.ORDERS_CANCEL, allow=False
    )
    refreshed = await repos.users.get_by_id(admin.id)
    assert refreshed is not None
    assert not await services.auth.has_permission(refreshed, Permission.ORDERS_CANCEL)


async def test_role_change_requires_super_admin(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, super_admin: User
) -> None:
    """ترقية المستخدمين صلاحية حصرية للأدمن الأعلى."""
    with pytest.raises(PermissionDeniedError):
        await services.auth.set_role(admin, user.id, Role.ADMIN)

    assert await services.auth.set_role(super_admin, user.id, Role.SUPPORT)
    promoted = await repos.users.get_by_id(user.id)
    assert promoted is not None and promoted.role == Role.SUPPORT
    assert await services.auth.has_permission(promoted, Permission.TICKETS_REPLY)
    assert not await services.auth.has_permission(promoted, Permission.ORDERS_CANCEL)


async def test_support_role_scope(
    services: ServiceContainer, repos: Repositories, user: User, super_admin: User
) -> None:
    """دور الدعم يرى ولا يغيّر: لا اعتماد مدفوعات ولا تعديل أسعار."""
    await services.auth.set_role(super_admin, user.id, Role.SUPPORT)
    support = await repos.users.get_by_id(user.id)
    assert support is not None

    assert await services.auth.has_permission(support, Permission.TICKETS_VIEW)
    assert await services.auth.has_permission(support, Permission.PAYMENTS_VIEW)
    assert not await services.auth.has_permission(support, Permission.PAYMENTS_APPROVE)
    assert not await services.auth.has_permission(support, Permission.SERVICES_PRICE)


async def test_emergency_super_admin_list_is_isolated(
    db: Database, repos: Repositories, secret_box, user: User
) -> None:
    """قائمة الطوارئ في ملف البيئة لا تمنح صلاحيات بذاتها داخل المسارات العادية."""
    from services import build_services

    container = build_services(
        db, repos, secret_box=secret_box, super_admin_ids=(user.telegram_id,), settings_ttl_seconds=0
    )
    assert container.auth.is_emergency_super_admin(user.telegram_id)
    assert not await container.auth.has_permission(user, Permission.ADMIN_ACCESS)
```

## `tests/integration/test_catalog_service.py`

```python
"""
اختبارات كتالوج الخدمات: التصفح، التسعير، وإدارة الأسعار.
"""

from __future__ import annotations

import pytest

from core.exceptions import (
    PermissionDeniedError,
    QuantityOutOfRangeError,
    ServiceNotAvailableError,
)
from database.models import Service, User
from database.repositories import Repositories
from services import ServiceContainer


async def test_categories_show_only_those_with_services(
    services: ServiceContainer, service: Service
) -> None:
    """لا يُعرض تصنيف فارغ للمستخدم."""
    categories = await services.catalog.categories()
    assert len(categories) == 1
    assert categories[0].id == service.category_id


async def test_services_page_navigation(
    services: ServiceContainer, service: Service
) -> None:
    """صفحات الخدمات تحسب العدد الكلي وأزرار التنقل بدقة."""
    page = await services.catalog.services_page(service.category_id, page=1, page_size=10)
    assert page.total_items == 1
    assert page.total_pages == 1
    assert not page.has_next and not page.has_prev
    assert page.items[0].id == service.id


async def test_search_finds_service_by_name(services: ServiceContainer, service: Service) -> None:
    """البحث النصي يجد الخدمة باسمها العربي."""
    results = await services.catalog.search("انستغرام")
    assert any(item.id == service.id for item in results)


async def test_quote_calculates_cost_correctly(
    services: ServiceContainer, service: Service
) -> None:
    """التسعيرة = السعر لكل ألف × الكمية ÷ 1000، مع نص جاهز للعرض."""
    quote = await services.catalog.quote(service, 1000)
    assert quote.quantity == 1000
    assert quote.cost_units == 10_000
    assert "1.00" in quote.cost_text

    half = await services.catalog.quote(service, 500)
    assert half.cost_units == 5_000


async def test_quote_rejects_out_of_range_quantity(
    services: ServiceContainer, service: Service
) -> None:
    """الكمية خارج حدود الخدمة تُرفض قبل أي خصم."""
    with pytest.raises(QuantityOutOfRangeError):
        await services.catalog.quote(service, 10)
    with pytest.raises(QuantityOutOfRangeError):
        await services.catalog.quote(service, 999_999)


async def test_disabled_service_is_not_orderable(
    services: ServiceContainer, repos: Repositories, service: Service, super_admin: User
) -> None:
    """الخدمة المعطّلة تختفي من الطلب لكنها تبقى في قاعدة البيانات (لا حذف)."""
    await services.catalog.set_service_active(super_admin, service.id, False)

    with pytest.raises(ServiceNotAvailableError):
        await services.catalog.get_available_service(service.id)

    stored = await repos.services.get(service.id)
    assert stored is not None and stored.is_active == 0


async def test_price_change_requires_permission_and_keeps_history(
    services: ServiceContainer, repos: Repositories, service: Service, user: User, admin: User
) -> None:
    """تغيير السعر محمي بصلاحية، ويحفظ السعر القديم في السجل التاريخي."""
    with pytest.raises(PermissionDeniedError):
        await services.catalog.change_price(user, service.id, 20_000)

    assert await services.catalog.change_price(admin, service.id, 20_000)
    updated = await repos.services.get(service.id)
    assert updated is not None and updated.price_per_1000_units == 20_000

    history = await repos.services.price_history(service.id)
    assert history and int(history[0]["old_price_units"]) == 10_000


async def test_old_orders_keep_their_price_snapshot(
    services: ServiceContainer, repos: Repositories, mock_service: Service,
    user: User, admin: User,
) -> None:
    """تغيير السعر لا يمس الطلبات القديمة (السعر مخزَّن كلقطة داخل الطلب)."""
    await services.wallet.adjust_balance(
        target=user, amount_units=100_000, admin=admin, reason="رصيد", credit=True
    )
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/x", quantity=1000
    )
    await services.catalog.change_price(admin, mock_service.id, 50_000)

    stored = await repos.orders.get(order.id)
    assert stored is not None
    assert stored.price_per_1000_snapshot_units == 10_000
    assert stored.cost_units == 10_000


async def test_negative_margin_report(
    services: ServiceContainer, repos: Repositories, service: Service, admin: User
) -> None:
    """تقرير الهامش السالب يكشف الخدمات التي تُباع بأقل من تكلفتها."""
    assert await services.catalog.negative_margin_report(admin) == []

    await services.catalog.change_price(admin, service.id, 3_000)  # أقل من تكلفة المزود 6000
    flagged = await services.catalog.negative_margin_report(admin)
    assert [item.id for item in flagged] == [service.id]


async def test_admin_can_create_category_and_service(
    services: ServiceContainer, super_admin: User, provider
) -> None:
    """إنشاء تصنيف وخدمة من لوحة الأدمن مع التحقق من المدخلات."""
    category = await services.catalog.create_category(super_admin, name_ar="واتساب", emoji="💬")
    new_service = await services.catalog.create_service(
        super_admin,
        category_id=category.id,
        provider_id=provider.id,
        provider_service_id="777",
        name="أعضاء قناة واتساب",
        price_per_1000_units=25_000,
        min_quantity=50,
        max_quantity=5_000,
        provider_price_per_1000_units=15_000,
    )
    assert new_service.category_id == category.id
    assert new_service.available
```

## `tests/integration/test_order_service.py`

```python
"""
اختبارات خدمة الطلبات — قلب النظام.

تغطي: الإنشاء والخصم الذرّي، منع التكرار، الحدود، الإرسال للمزود،
المتابعة حتى الاكتمال، التنفيذ الجزئي، الفشل والاسترجاع، النتيجة غير المؤكدة،
إجراءات الأدمن، والاسترداد بعد إعادة التشغيل.
"""

from __future__ import annotations

import asyncio

import pytest

from core.enums import OrderStatus, TransactionType
from core.exceptions import (
    DuplicateOperationError,
    InsufficientBalanceError,
    InvalidStateTransitionError,
    PermissionDeniedError,
    ProviderPermanentError,
    ProviderTemporaryError,
    ProviderUncertainError,
    RateLimitedError,
    ValidationError,
)
from database.database import Database
from database.models import Service, User
from database.repositories import Repositories
from integrations.providers.mock import MockProviderClient
from services import ServiceContainer
from utils.datetime_utils import iso_plus_seconds

ORDER_COST = 10_000  # تكلفة طلب 1000 وحدة بسعر 10000/ألف


async def _fund(services: ServiceContainer, user: User, admin: User, amount_units: int) -> None:
    """شحن رصيد اختباري عبر المسار الرسمي للمحفظة."""
    await services.wallet.adjust_balance(
        target=user, amount_units=amount_units, admin=admin, reason="رصيد اختبار", credit=True
    )


async def _create(
    services: ServiceContainer, user: User, service: Service, *, link: str = "https://instagram.com/test", quantity: int = 1000
):
    """اختصار لإنشاء طلب."""
    return await services.orders.create_order(
        user, service_id=service.id, link=link, quantity=quantity
    )


async def _make_due(repos: Repositories, order_id: int) -> None:
    """تقديم موعد الفحص/المحاولة إلى الماضي (محاكاة مرور الوقت في الاختبار)."""
    async with repos.db.transaction() as tx:
        await repos.orders.update_fields(tx, order_id, next_check_at=iso_plus_seconds(-10))


# ============================== الإنشاء ================================= #


async def test_create_order_charges_balance_and_records_everything(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service
) -> None:
    """الإنشاء الناجح: خصم + سجل حالة + إشعار + رمز عام للطلب."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)

    assert order.status == OrderStatus.PENDING
    assert order.public_code == f"ORD-{order.id:06d}"
    assert order.cost_units == ORDER_COST
    assert await services.wallet.balance_units(user.id) == 40_000

    transactions = await repos.transactions.list_by_order(order.id)
    assert len(transactions) == 1 and transactions[0].type == TransactionType.ORDER

    history = await repos.orders.history(order.id)
    assert history[0].to_status == OrderStatus.PENDING

    inbox = await repos.notifications.list_for_user(user.id)
    assert any("order_created" == item.type for item in inbox)


async def test_create_order_without_balance_leaves_no_trace(
    services: ServiceContainer, repos: Repositories, user: User, mock_service: Service
) -> None:
    """فشل الخصم يُلغي إنشاء الطلب بالكامل (ذرّية المعاملة)."""
    with pytest.raises(InsufficientBalanceError):
        await _create(services, user, mock_service)

    assert await repos.orders.count_by_user(user.id) == 0
    assert await repos.transactions.count_by_user(user.id) == 0


async def test_same_client_request_id_returns_same_order(
    services: ServiceContainer, user: User, admin: User, mock_service: Service
) -> None:
    """الضغط المزدوج بنفس المفتاح يُعيد الطلب الأول بلا خصم جديد."""
    await _fund(services, user, admin, 50_000)
    first = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/a", quantity=1000,
        client_request_id="same-key",
    )
    second = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/a", quantity=1000,
        client_request_id="same-key",
    )

    assert first.id == second.id
    assert await services.wallet.balance_units(user.id) == 40_000


async def test_duplicate_order_window_blocks_identical_order(
    services: ServiceContainer, user: User, admin: User, mock_service: Service
) -> None:
    """طلب مطابق خلال نافذة التكرار يُرفض برسالة واضحة."""
    await _fund(services, user, admin, 50_000)
    await _create(services, user, mock_service, link="https://instagram.com/same")

    with pytest.raises(DuplicateOperationError):
        await _create(services, user, mock_service, link="https://instagram.com/same")


async def test_daily_order_limit_enforced(
    services: ServiceContainer, user: User, admin: User, mock_service: Service
) -> None:
    """الحد اليومي لعدد الطلبات مطبَّق من الإعدادات."""
    await services.settings.set("max_orders_per_day", 1)
    await _fund(services, user, admin, 50_000)
    await _create(services, user, mock_service, link="https://instagram.com/one")

    with pytest.raises(RateLimitedError):
        await _create(services, user, mock_service, link="https://instagram.com/two")


async def test_minimum_order_amount_enforced(
    services: ServiceContainer, user: User, admin: User, mock_service: Service
) -> None:
    """الحد الأدنى لقيمة الطلب يمنع الطلبات الصغيرة جداً."""
    await services.settings.set("min_order_amount_units", 20_000)
    await _fund(services, user, admin, 50_000)

    with pytest.raises(ValidationError):
        await _create(services, user, mock_service, quantity=1000)  # قيمته 10000 فقط


async def test_banned_user_cannot_order(
    services: ServiceContainer, user: User, admin: User, mock_service: Service
) -> None:
    """المستخدم المحظور لا يستطيع إنشاء طلب."""
    await _fund(services, user, admin, 50_000)
    await services.users.ban(admin, user.id, reason="مخالفة")
    banned = await services.users.get(user.id)
    assert banned is not None

    from core.exceptions import UserBannedError

    with pytest.raises(UserBannedError):
        await _create(services, user=banned, service=mock_service)


# ============================== الإرسال ================================= #


async def test_submit_pending_order_to_provider(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """الطلب المعلّق يُرسل للمزود ويحصل على رقم عنده."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)

    report = await services.orders.process_pending_orders()
    assert report.claimed == 1 and report.succeeded == 1

    submitted = await repos.orders.get(order.id)
    assert submitted is not None
    assert submitted.status == OrderStatus.SUBMITTED
    assert submitted.provider_order_id
    assert submitted.locked_by is None
    assert any(call[0] == "add" for call in mock_client.calls)


async def test_full_delivery_completes_order(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """المتابعة الدورية تنقل الطلب إلى in_progress ثم completed."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    await services.orders.process_pending_orders()

    for _ in range(4):
        await _make_due(repos, order.id)
        await services.orders.process_due_orders()
        current = await repos.orders.get(order.id)
        assert current is not None
        if current.status == OrderStatus.COMPLETED:
            break

    final = await repos.orders.get(order.id)
    assert final is not None
    assert final.status == OrderStatus.COMPLETED
    assert final.remains == 0
    assert final.completed_at is not None
    assert final.refund_amount_units == 0
    assert await services.wallet.balance_units(user.id) == 40_000


async def test_partial_delivery_triggers_partial_refund(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """التنفيذ الجزئي يسترجع قيمة الكمية غير المنفَّذة تلقائياً."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    await services.orders.process_pending_orders()

    submitted = await repos.orders.get(order.id)
    assert submitted is not None and submitted.provider_order_id
    mock_client.advance(submitted.provider_order_id, to="Partial", delivered=600)

    await _make_due(repos, order.id)
    await services.orders.process_due_orders()

    final = await repos.orders.get(order.id)
    assert final is not None
    assert final.status == OrderStatus.PARTIAL
    assert final.delivered_quantity == 600
    assert final.refund_amount_units == 4_000          # 40% من 10000
    assert await services.wallet.balance_units(user.id) == 44_000

    refunds = [
        transaction for transaction in await repos.transactions.list_by_order(order.id)
        if transaction.type == TransactionType.PARTIAL_REFUND
    ]
    assert len(refunds) == 1


async def test_provider_cancellation_refunds_fully(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """إلغاء المزود للطلب يُعيد كامل المبلغ وينقله إلى refunded."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    await services.orders.process_pending_orders()

    submitted = await repos.orders.get(order.id)
    assert submitted is not None and submitted.provider_order_id
    mock_client.advance(submitted.provider_order_id, to="Canceled")

    await _make_due(repos, order.id)
    await services.orders.process_due_orders()

    final = await repos.orders.get(order.id)
    assert final is not None
    assert final.status == OrderStatus.REFUNDED
    assert final.refund_amount_units == ORDER_COST
    assert await services.wallet.balance_units(user.id) == 50_000


# ============================== الإخفاقات =============================== #


async def test_permanent_provider_failure_refunds_and_alerts(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """رفض المزود النهائي ⇒ فشل + استرجاع كامل + إشعار المستخدم والأدمن + سجل خطأ."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    mock_client.always_fail_add = ProviderPermanentError("الخدمة غير موجودة لدى المزود")

    report = await services.orders.process_pending_orders()
    assert report.failed == 1

    final = await repos.orders.get(order.id)
    assert final is not None
    assert final.status == OrderStatus.REFUNDED
    assert final.refund_amount_units == ORDER_COST
    assert await services.wallet.balance_units(user.id) == 50_000

    user_inbox = await repos.notifications.list_for_user(user.id)
    assert any(item.type == "order_failed" for item in user_inbox)
    admin_inbox = await repos.notifications.list_for_user(admin.id)
    assert admin_inbox, "يجب تنبيه الأدمن عند فشل الطلب"

    errors = await repos.error_logs.list_recent(limit=10)
    assert any("فشل الطلب" in row["message"] for row in errors)


async def test_temporary_failure_retries_then_fails_after_max_attempts(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """الفشل المؤقت يُعيد الطلب للانتظار، وبعد استنفاد المحاولات يفشل ويُسترجع المبلغ."""
    from core.constants import MAX_SUBMIT_ATTEMPTS

    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    mock_client.always_fail_add = ProviderTemporaryError("انقطاع مؤقت")

    statuses = []
    for _ in range(MAX_SUBMIT_ATTEMPTS + 1):
        await _make_due(repos, order.id)
        await services.orders.process_pending_orders()
        current = await repos.orders.get(order.id)
        assert current is not None
        statuses.append(current.status)
        if current.status == OrderStatus.REFUNDED:
            break

    assert OrderStatus.PENDING in statuses, "يجب أن يعود الطلب للانتظار بعد الفشل المؤقت"
    final = await repos.orders.get(order.id)
    assert final is not None
    assert final.status == OrderStatus.REFUNDED
    assert final.submit_attempts >= MAX_SUBMIT_ATTEMPTS
    assert await services.wallet.balance_units(user.id) == 50_000


async def test_uncertain_result_is_never_resubmitted(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """
    النتيجة غير المؤكدة: لا استرجاع ولا إعادة إرسال — تدخّل أدمن فقط.

    هذا أخطر سيناريو: إعادة الإرسال تعني طلباً مكرراً عند المزود ومالاً مهدوراً.
    """
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    mock_client.always_fail_add = ProviderUncertainError("انتهت المهلة بعد الإرسال")

    report = await services.orders.process_pending_orders()
    assert report.uncertain == 1

    current = await repos.orders.get(order.id)
    assert current is not None
    assert current.status == OrderStatus.SUBMIT_UNCERTAIN
    assert current.refund_amount_units == 0
    assert await services.wallet.balance_units(user.id) == 40_000  # المال ما زال محجوزاً

    # جولة إرسال جديدة يجب ألا تلتقطه إطلاقاً
    calls_before = len(mock_client.calls)
    second = await services.orders.process_pending_orders()
    assert second.claimed == 0
    assert len(mock_client.calls) == calls_before

    admin_inbox = await repos.notifications.list_for_user(admin.id)
    assert admin_inbox, "يجب تنبيه الأدمن فوراً بالحالة غير المؤكدة"


async def test_unknown_provider_status_does_not_change_order(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """حالة مزود غير معروفة تُسجَّل كتحذير ولا تغيّر حالة الطلب."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    await services.orders.process_pending_orders()

    submitted = await repos.orders.get(order.id)
    assert submitted is not None and submitted.provider_order_id
    mock_client.advance(submitted.provider_order_id, to="Weird New Status")

    await _make_due(repos, order.id)
    await services.orders.process_due_orders()

    unchanged = await repos.orders.get(order.id)
    assert unchanged is not None
    assert unchanged.status == OrderStatus.SUBMITTED
    errors = await repos.error_logs.list_recent(limit=10)
    assert any("حالة مزود غير معروفة" in row["message"] for row in errors)


# ========================== إجراءات المستخدم والأدمن ===================== #


async def test_user_can_cancel_before_submission(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service
) -> None:
    """إلغاء المستخدم قبل الإرسال يعيد كامل المبلغ."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)

    refunded = await services.orders.cancel_by_user(user, order.id)
    assert refunded == ORDER_COST

    final = await repos.orders.get(order.id)
    assert final is not None and final.status == OrderStatus.REFUNDED
    assert await services.wallet.balance_units(user.id) == 50_000


async def test_user_cannot_cancel_after_submission(
    services: ServiceContainer, user: User, admin: User, mock_service: Service, mock_client: MockProviderClient
) -> None:
    """بعد الإرسال للمزود لا يملك المستخدم حق الإلغاء."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    await services.orders.process_pending_orders()

    with pytest.raises(InvalidStateTransitionError):
        await services.orders.cancel_by_user(user, order.id)


async def test_user_cannot_touch_another_users_order(
    services: ServiceContainer, db: Database, repos: Repositories, user: User, admin: User, mock_service: Service
) -> None:
    """لا يرى المستخدم طلبات غيره ولا يلغيها."""
    from core.exceptions import OrderError

    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)

    async with db.transaction() as tx:
        other = await repos.users.create(tx, telegram_id=555000111, first_name="Other")

    with pytest.raises(OrderError):
        await services.orders.get_for_user(other, order.id)
    with pytest.raises(OrderError):
        await services.orders.cancel_by_user(other, order.id)


async def test_admin_mark_failed_refunds_uncertain_order(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """تأكيد الأدمن أن الطلب لم يصل المزود ⇒ استرجاع كامل وتسجيل تدقيق."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    mock_client.always_fail_add = ProviderUncertainError("مهلة")
    await services.orders.process_pending_orders()

    refunded = await services.orders.admin_mark_failed(admin, order.id, "تأكدنا أنه لم يصل المزود")
    assert refunded == ORDER_COST

    final = await repos.orders.get(order.id)
    assert final is not None and final.status == OrderStatus.REFUNDED
    assert await services.wallet.balance_units(user.id) == 50_000

    logs = await services.audit.by_target("order", order.id)
    assert any(log.action == "orders.refund" for log in logs)


async def test_admin_link_provider_order_requires_super_admin(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, super_admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """ربط رقم المزود يدوياً صلاحية للأدمن الأعلى فقط، وينقل الطلب إلى submitted."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)
    mock_client.always_fail_add = ProviderUncertainError("مهلة")
    await services.orders.process_pending_orders()

    with pytest.raises(PermissionDeniedError):
        await services.orders.admin_link_provider_order(admin, order.id, "99887")

    assert await services.orders.admin_link_provider_order(super_admin, order.id, "99887")
    linked = await repos.orders.get(order.id)
    assert linked is not None
    assert linked.status == OrderStatus.SUBMITTED
    assert linked.provider_order_id == "99887"


async def test_status_override_requires_reason_and_logs_audit(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, super_admin: User, mock_service: Service
) -> None:
    """التجاوز الإداري يتطلب سبباً واضحاً ويُسجَّل كاملاً."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)

    with pytest.raises(ValidationError):
        await services.orders.admin_override_status(super_admin, order.id, OrderStatus.FAILED, "x")

    assert await services.orders.admin_override_status(
        super_admin, order.id, OrderStatus.FAILED, "طلب تجريبي أُنشئ بالخطأ"
    )
    logs = await services.audit.by_target("order", order.id)
    assert any(log.action == "orders.status.override" for log in logs)


# ============================ الاسترداد والسباق ========================== #


async def test_recover_after_restart_marks_submitting_as_uncertain(
    services: ServiceContainer, db: Database, repos: Repositories, user: User, admin: User, mock_service: Service
) -> None:
    """الطلب العالق في submitting بعد إعادة التشغيل يصبح غير مؤكد ويُنبَّه الأدمن."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)

    async with db.transaction() as tx:   # محاكاة انقطاع أثناء الإرسال
        await repos.orders.update_status(
            tx, order.id, new_status=OrderStatus.SUBMITTING,
            expected_statuses=[OrderStatus.PENDING],
            extra_fields={"locked_by": "worker-1", "locked_until": iso_plus_seconds(-5)},
        )

    report = await services.orders.recover_after_restart()
    assert report["uncertain"] == 1

    recovered = await repos.orders.get(order.id)
    assert recovered is not None
    assert recovered.status == OrderStatus.SUBMIT_UNCERTAIN
    assert await repos.notifications.list_for_user(admin.id)


async def test_concurrent_order_creation_respects_balance(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service
) -> None:
    """
    50 طلباً متزامناً برصيد يكفي 10 فقط ⇒ 10 طلبات بالضبط في قاعدة البيانات.

    يضمن أن الخصم وإنشاء الطلب ذرّيان معاً: لا طلب بلا خصم ولا خصم بلا طلب.
    """
    await services.settings.set("max_orders_per_day", 0)        # تعطيل الحد اليومي
    await services.settings.set("duplicate_order_window_minutes", 0)
    await _fund(services, user, admin, ORDER_COST * 10)

    async def attempt(index: int) -> bool:
        """محاولة إنشاء طلب واحد."""
        try:
            await services.orders.create_order(
                user,
                service_id=mock_service.id,
                link=f"https://instagram.com/user{index}",
                quantity=1000,
                client_request_id=f"race-{index}",
            )
            return True
        except InsufficientBalanceError:
            return False

    results = await asyncio.gather(*(attempt(i) for i in range(50)))

    assert sum(results) == 10
    assert await repos.orders.count_by_user(user.id) == 10
    assert await services.wallet.balance_units(user.id) == 0
    assert (await services.wallet.verify_ledger(user.id)).is_balanced


async def test_two_workers_never_submit_the_same_order_twice(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client: MockProviderClient,
) -> None:
    """عاملان متزامنان لا يرسلان الطلب نفسه مرتين (قفل الحجز)."""
    await _fund(services, user, admin, 50_000)
    order = await _create(services, user, mock_service)

    first, second = await asyncio.gather(
        services.orders.process_pending_orders(worker="w1"),
        services.orders.process_pending_orders(worker="w2"),
    )

    assert first.claimed + second.claimed == 1
    add_calls = [call for call in mock_client.calls if call[0] == "add"]
    assert len(add_calls) == 1

    final = await repos.orders.get(order.id)
    assert final is not None and final.status == OrderStatus.SUBMITTED
```

## `tests/integration/test_payment_service.py`

```python
"""
اختبارات خدمة الشحن: من إرسال الإثبات حتى إضافة الرصيد.

التركيز على المال: لا إيداع مزدوج، ولا اعتماد طلب معالَج، ولا رصيد يُضاف
خارج المحفظة المركزية.
"""

from __future__ import annotations

import asyncio

import pytest

from core.enums import PaymentStatus, TransactionType
from core.exceptions import (
    DuplicateOperationError,
    InvalidAmountError,
    InvalidStateTransitionError,
    PermissionDeniedError,
    ValidationError,
)
from database.database import Database
from database.models import User
from database.repositories import Repositories
from services import ServiceContainer
from utils.datetime_utils import iso_plus_seconds


async def _submit(services: ServiceContainer, user: User, method, *, amount: str = "5", reference: str = "TRX-1001"):
    """اختصار لإرسال طلب شحن."""
    return await services.payments.create_payment(
        user,
        method_id=method.id,
        raw_amount=amount,
        transaction_reference=reference,
        proof_file_id="file-id-123",
        proof_file_type="photo",
    )


# ============================== الإنشاء ================================= #


async def test_create_payment_notifies_user_and_admins(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, payment_method
) -> None:
    """طلب الشحن يُنشأ معلّقاً مع إشعار للمستخدم وتنبيه للأدمن."""
    payment = await _submit(services, user, payment_method)

    assert payment.status == PaymentStatus.PENDING
    assert payment.amount_units == 50_000
    assert payment.expires_at is not None

    user_inbox = await repos.notifications.list_for_user(user.id)
    assert any(item.type == "payment_received" for item in user_inbox)
    assert await repos.notifications.list_for_user(admin.id)

    # لم يُضف أي رصيد قبل الاعتماد
    assert await services.wallet.balance_units(user.id) == 0


async def test_amount_below_minimum_rejected(
    services: ServiceContainer, user: User, payment_method
) -> None:
    """المبلغ الأقل من الحد الأدنى يُرفض قبل إنشاء أي صف."""
    with pytest.raises(InvalidAmountError):
        await _submit(services, user, payment_method, amount="0.5")


async def test_reference_cannot_be_reused(
    services: ServiceContainer, user: User, payment_method
) -> None:
    """رقم الحوالة الواحد لا يُستخدم في طلبين (كشف إعادة استخدام الإثبات)."""
    await _submit(services, user, payment_method, reference="TRX-SAME")
    with pytest.raises(DuplicateOperationError):
        await _submit(services, user, payment_method, reference="TRX-SAME")


async def test_pending_payments_limit(
    services: ServiceContainer, user: User, payment_method
) -> None:
    """لا يُسمح بتكديس طلبات شحن معلّقة أكثر من الحد المسموح."""
    await services.settings.set("max_pending_payments_per_user", 2)
    await _submit(services, user, payment_method, reference="TRX-A")
    await _submit(services, user, payment_method, reference="TRX-B")

    with pytest.raises(ValidationError):
        await _submit(services, user, payment_method, reference="TRX-C")


async def test_proof_required_when_method_requires_it(
    services: ServiceContainer, user: User, payment_method
) -> None:
    """طريقة تتطلب إثباتاً لا تقبل طلباً بلا رقم حوالة."""
    with pytest.raises(ValidationError):
        await services.payments.create_payment(
            user, method_id=payment_method.id, raw_amount="5", transaction_reference=None
        )


# ============================== الاعتماد ================================ #


async def test_approve_credits_balance_once(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, payment_method
) -> None:
    """الاعتماد يضيف الرصيد مرة واحدة ويكتب حركة إيداع وسجل تدقيق وإشعاراً."""
    payment = await _submit(services, user, payment_method)
    transaction = await services.payments.approve(admin, payment.id)

    assert transaction.type == TransactionType.DEPOSIT
    assert await services.wallet.balance_units(user.id) == 50_000

    updated = await repos.payments.get(payment.id)
    assert updated is not None
    assert updated.status == PaymentStatus.APPROVED
    assert updated.credited_units == 50_000
    assert updated.admin_id == admin.id
    assert updated.reviewed_at is not None

    logs = await services.audit.by_target("payment", payment.id)
    assert any(log.action == "payments.approve" for log in logs)

    inbox = await repos.notifications.list_for_user(user.id)
    assert any(item.type == "payment_approved" for item in inbox)


async def test_approve_twice_is_blocked(
    services: ServiceContainer, user: User, admin: User, payment_method
) -> None:
    """لا يُعتمد الطلب مرتين (ولا يُضاف الرصيد مرتين)."""
    payment = await _submit(services, user, payment_method)
    await services.payments.approve(admin, payment.id)

    with pytest.raises(InvalidStateTransitionError):
        await services.payments.approve(admin, payment.id)

    assert await services.wallet.balance_units(user.id) == 50_000


async def test_two_admins_approving_together_credit_once(
    services: ServiceContainer, user: User, admin: User, super_admin: User, payment_method
) -> None:
    """اعتمادان متزامنان من أدمنين مختلفين ⇒ إيداع واحد فقط."""
    payment = await _submit(services, user, payment_method)

    results = await asyncio.gather(
        services.payments.approve(admin, payment.id),
        services.payments.approve(super_admin, payment.id),
        return_exceptions=True,
    )
    successes = [item for item in results if not isinstance(item, Exception)]
    failures = [item for item in results if isinstance(item, Exception)]

    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], (DuplicateOperationError, InvalidStateTransitionError))
    assert await services.wallet.balance_units(user.id) == 50_000


async def test_approve_with_different_amount(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, payment_method
) -> None:
    """يمكن اعتماد مبلغ مختلف عن المطلوب (تحويل ناقص) مع توثيق الفرق."""
    payment = await _submit(services, user, payment_method, amount="10")
    await services.payments.approve(admin, payment.id, credited_units=70_000, admin_note="وصل ناقصاً")

    assert await services.wallet.balance_units(user.id) == 70_000
    updated = await repos.payments.get(payment.id)
    assert updated is not None
    assert updated.credited_units == 70_000
    assert updated.admin_note and "70000" in updated.admin_note.replace(" ", "")


# =============================== الرفض ================================== #


async def test_reject_requires_reason_and_notifies(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, payment_method
) -> None:
    """الرفض يحتاج سبباً يصل للمستخدم، ولا يضيف أي رصيد."""
    payment = await _submit(services, user, payment_method)

    with pytest.raises(ValidationError):
        await services.payments.reject(admin, payment.id, "")

    assert await services.payments.reject(admin, payment.id, "الإيصال غير واضح")
    updated = await repos.payments.get(payment.id)
    assert updated is not None
    assert updated.status == PaymentStatus.REJECTED
    assert updated.reject_reason == "الإيصال غير واضح"
    assert await services.wallet.balance_units(user.id) == 0

    inbox = await repos.notifications.list_for_user(user.id)
    assert any(item.type == "payment_rejected" for item in inbox)


async def test_rejected_payment_cannot_be_approved(
    services: ServiceContainer, user: User, admin: User, payment_method
) -> None:
    """الطلب المرفوض مغلق نهائياً."""
    payment = await _submit(services, user, payment_method)
    await services.payments.reject(admin, payment.id, "مكرر")

    with pytest.raises(InvalidStateTransitionError):
        await services.payments.approve(admin, payment.id)


# ======================= الإلغاء وانتهاء الصلاحية ======================== #


async def test_user_can_cancel_pending_payment(
    services: ServiceContainer, repos: Repositories, user: User, payment_method
) -> None:
    """المستخدم يلغي طلب شحن أرسله بالخطأ."""
    payment = await _submit(services, user, payment_method)
    assert await services.payments.cancel_by_user(user, payment.id)

    updated = await repos.payments.get(payment.id)
    assert updated is not None and updated.status == PaymentStatus.CANCELLED


async def test_expired_payments_are_closed_and_user_notified(
    services: ServiceContainer, db: Database, repos: Repositories, user: User, payment_method
) -> None:
    """الطلبات منتهية الصلاحية تُغلق تلقائياً ويُشعَر أصحابها."""
    payment = await _submit(services, user, payment_method)
    async with db.transaction() as tx:
        await repos.payments.update_fields(tx, payment.id, expires_at=iso_plus_seconds(-60))

    assert await services.payments.expire_due() == 1
    updated = await repos.payments.get(payment.id)
    assert updated is not None and updated.status == PaymentStatus.EXPIRED
    assert await services.wallet.balance_units(user.id) == 0


# ============================ الصلاحيات والإدارة ========================= #


async def test_plain_user_cannot_approve_or_list(
    services: ServiceContainer, user: User, payment_method
) -> None:
    """المستخدم العادي لا يرى طابور المراجعة ولا يعتمد الطلبات."""
    payment = await _submit(services, user, payment_method)

    with pytest.raises(PermissionDeniedError):
        await services.payments.approve(user, payment.id)
    with pytest.raises(PermissionDeniedError):
        await services.payments.pending(user)


async def test_method_management_requires_permission(
    services: ServiceContainer, user: User, super_admin: User
) -> None:
    """إدارة طرق الدفع محصورة بمن يملك صلاحية `payments.methods`."""
    with pytest.raises(PermissionDeniedError):
        await services.payments.create_method(user, code="x", name_ar="طريقة")

    method = await services.payments.create_method(
        super_admin, code="Kuraimi Bank", name_ar="بنك الكريمي", min_amount_units=20_000
    )
    assert method.code == "kuraimi_bank"

    assert await services.payments.set_method_active(super_admin, method.id, False)
    methods = await services.payments.active_methods()
    assert method.id not in {item.id for item in methods}


async def test_method_limits_override_global_settings(
    services: ServiceContainer, super_admin: User, user: User
) -> None:
    """حد الطريقة يتقدّم على الحد العام في الإعدادات."""
    method = await services.payments.create_method(
        super_admin, code="big_only", name_ar="تحويلات كبيرة", min_amount_units=100_000,
        requires_proof=False,
    )
    min_units, _ = await services.payments.method_limits(method)
    assert min_units == 100_000

    with pytest.raises(InvalidAmountError):
        await services.payments.create_payment(
            user, method_id=method.id, raw_amount="5", transaction_reference=None
        )
```

## `tests/integration/test_ticket_service.py`

```python
"""
اختبارات خدمة الدعم الفني: التذاكر والمحادثة والإغلاق.
"""

from __future__ import annotations

import pytest

from core.enums import TicketStatus
from core.exceptions import PermissionDeniedError, TicketError, ValidationError
from database.database import Database
from database.models import User
from database.repositories import Repositories
from services import ServiceContainer
from utils.datetime_utils import iso_plus_seconds


async def _open_ticket(services: ServiceContainer, user: User, *, subject: str = "مشكلة في طلبي"):
    """اختصار لفتح تذكرة."""
    return await services.tickets.create_ticket(
        user, subject=subject, message="لم يصلني الطلب حتى الآن", category="order"
    )


async def test_create_ticket_adds_first_message_and_alerts_admins(
    services: ServiceContainer, repos: Repositories, user: User, admin: User
) -> None:
    """فتح التذكرة يضيف الرسالة الأولى وينبّه فريق الدعم."""
    ticket = await _open_ticket(services, user)

    assert ticket.status == TicketStatus.OPEN
    messages = await repos.tickets.messages(ticket.id)
    assert len(messages) == 1
    assert messages[0].sender_type == "user"
    assert await repos.notifications.list_for_user(admin.id)


async def test_only_one_open_ticket_per_user(services: ServiceContainer, user: User) -> None:
    """لا يفتح المستخدم تذكرتين في وقت واحد — يُوجَّه إلى تذكرته القائمة."""
    await _open_ticket(services, user)
    with pytest.raises(TicketError):
        await _open_ticket(services, user, subject="مشكلة أخرى")


async def test_daily_ticket_limit(services: ServiceContainer, user: User, admin: User) -> None:
    """الحد اليومي لعدد التذاكر مطبَّق."""
    await services.settings.set("max_tickets_per_day", 1)
    ticket = await _open_ticket(services, user)
    await services.tickets.close(admin, ticket.id, "تم الحل")

    with pytest.raises(ValidationError):
        await _open_ticket(services, user, subject="تذكرة ثانية اليوم")


async def test_invalid_category_and_wrong_order_rejected(
    services: ServiceContainer, user: User
) -> None:
    """التصنيف غير المعروف أو ربط طلب ليس للمستخدم مرفوضان."""
    with pytest.raises(ValidationError):
        await services.tickets.create_ticket(
            user, subject="س", message="نص الرسالة", category="unknown"
        )
    with pytest.raises(TicketError):
        await services.tickets.create_ticket(
            user, subject="استفسار", message="نص الرسالة", related_order_id=99999
        )


async def test_conversation_flow_between_user_and_support(
    services: ServiceContainer, repos: Repositories, user: User, admin: User
) -> None:
    """تبادل الرسائل يقلب حالة التذكرة بين انتظار الدعم وانتظار المستخدم."""
    ticket = await _open_ticket(services, user)

    after_user = await repos.tickets.get(ticket.id)
    assert after_user is not None and after_user.status == TicketStatus.PENDING_ADMIN

    await services.tickets.reply_as_admin(admin, ticket.id, "أهلاً بك، نراجع طلبك الآن")
    after_admin = await repos.tickets.get(ticket.id)
    assert after_admin is not None
    assert after_admin.status == TicketStatus.PENDING_USER
    assert after_admin.assigned_admin == admin.id

    inbox = await repos.notifications.list_for_user(user.id)
    assert any(item.type == "ticket_replied" for item in inbox)

    await services.tickets.reply_as_user(user, ticket.id, "شكراً، في انتظاركم")
    after_second = await repos.tickets.get(ticket.id)
    assert after_second is not None and after_second.status == TicketStatus.PENDING_ADMIN
    assert len(await repos.tickets.messages(ticket.id)) == 3


async def test_each_admin_reply_sends_its_own_notification(
    services: ServiceContainer, repos: Repositories, user: User, admin: User
) -> None:
    """كل رد من الدعم يُنتج إشعاراً مستقلاً (منع التكرار لا يبتلع الردود)."""
    ticket = await _open_ticket(services, user)
    await services.tickets.reply_as_admin(admin, ticket.id, "الرد الأول")
    await services.tickets.reply_as_admin(admin, ticket.id, "الرد الثاني")

    inbox = await repos.notifications.list_for_user(user.id)
    replies = [item for item in inbox if item.type == "ticket_replied"]
    assert len(replies) == 2


async def test_close_notifies_user_and_blocks_further_admin_duplicates(
    services: ServiceContainer, repos: Repositories, user: User, admin: User
) -> None:
    """الإغلاق يُشعر المستخدم، وإغلاق مغلق لا يفعل شيئاً."""
    ticket = await _open_ticket(services, user)
    assert await services.tickets.close(admin, ticket.id, "تم حل المشكلة")
    assert not await services.tickets.close(admin, ticket.id, "مرة أخرى")

    closed = await repos.tickets.get(ticket.id)
    assert closed is not None
    assert closed.status == TicketStatus.CLOSED
    assert closed.closed_by == admin.id

    inbox = await repos.notifications.list_for_user(user.id)
    assert any(item.type == "ticket_closed" for item in inbox)


async def test_user_reply_reopens_recently_closed_ticket(
    services: ServiceContainer, repos: Repositories, user: User, admin: User
) -> None:
    """الرد على تذكرة أُغلقت حديثاً يعيد فتحها بدل إجبار المستخدم على تذكرة جديدة."""
    ticket = await _open_ticket(services, user)
    await services.tickets.close(admin, ticket.id, "تم الحل")

    await services.tickets.reply_as_user(user, ticket.id, "المشكلة عادت")
    reopened = await repos.tickets.get(ticket.id)
    assert reopened is not None
    assert reopened.status == TicketStatus.PENDING_ADMIN
    assert reopened.closed_at is None


async def test_reply_blocked_when_reopen_disabled(
    services: ServiceContainer, user: User, admin: User
) -> None:
    """عند تعطيل إعادة الفتح، التذكرة المغلقة تبقى مغلقة."""
    await services.settings.set("ticket_reopen_hours", 0)
    ticket = await _open_ticket(services, user)
    await services.tickets.close(admin, ticket.id, "تم الحل")

    with pytest.raises(TicketError):
        await services.tickets.reply_as_user(user, ticket.id, "محاولة متأخرة")


async def test_user_cannot_read_or_reply_to_others_tickets(
    services: ServiceContainer, db: Database, repos: Repositories, user: User
) -> None:
    """تذاكر المستخدمين معزولة تماماً."""
    ticket = await _open_ticket(services, user)
    async with db.transaction() as tx:
        other = await repos.users.create(tx, telegram_id=444333222, first_name="Other")

    with pytest.raises(TicketError):
        await services.tickets.get_for_user(other, ticket.id)
    with pytest.raises(TicketError):
        await services.tickets.reply_as_user(other, ticket.id, "تطفل")


async def test_support_actions_require_permissions(
    services: ServiceContainer, user: User, admin: User
) -> None:
    """إجراءات فريق الدعم محمية بالصلاحيات."""
    ticket = await _open_ticket(services, user)

    with pytest.raises(PermissionDeniedError):
        await services.tickets.reply_as_admin(user, ticket.id, "رد غير مصرح")
    with pytest.raises(PermissionDeniedError):
        await services.tickets.admin_list(user)
    with pytest.raises(PermissionDeniedError):
        await services.tickets.close(user, ticket.id, "إغلاق غير مصرح")

    assert await services.tickets.admin_list(admin)


async def test_assign_only_to_admins_and_priority_validated(
    services: ServiceContainer, db: Database, repos: Repositories, user: User, admin: User
) -> None:
    """الإسناد لا يكون إلا لأدمن، والأولوية من القيم المعروفة فقط."""
    ticket = await _open_ticket(services, user)
    async with db.transaction() as tx:
        plain = await repos.users.create(tx, telegram_id=222111000, first_name="Plain")

    with pytest.raises(PermissionDeniedError):
        await services.tickets.assign(admin, ticket.id, plain.id)
    assert await services.tickets.assign(admin, ticket.id, admin.id)

    with pytest.raises(ValidationError):
        await services.tickets.set_priority(admin, ticket.id, "urgent")
    assert await services.tickets.set_priority(admin, ticket.id, "high")


async def test_auto_close_idle_tickets(
    services: ServiceContainer, db: Database, repos: Repositories, user: User, admin: User
) -> None:
    """التذاكر الراكدة بانتظار رد المستخدم تُغلق تلقائياً بعد المدة المحددة."""
    await services.settings.set("ticket_auto_close_days", 3)
    ticket = await _open_ticket(services, user)
    await services.tickets.reply_as_admin(admin, ticket.id, "بانتظار ردك")

    async with db.transaction() as tx:   # محاكاة مرور 10 أيام بلا رد
        await repos.tickets.update_fields(
            tx, ticket.id, last_message_at=iso_plus_seconds(-10 * 86400)
        )

    assert await services.tickets.auto_close_idle() == 1
    closed = await repos.tickets.get(ticket.id)
    assert closed is not None and closed.status == TicketStatus.CLOSED


async def test_reading_conversation_marks_messages_read(
    services: ServiceContainer, repos: Repositories, user: User, admin: User
) -> None:
    """فتح المحادثة من الطرفين يعلّم الرسائل كمقروءة."""
    ticket = await _open_ticket(services, user)
    await services.tickets.reply_as_admin(admin, ticket.id, "رد الدعم")

    messages = await services.tickets.conversation_for_user(user, ticket.id)
    assert messages and all(message.is_read_by_user == 1 for message in await repos.tickets.messages(ticket.id))

    _, admin_messages = await services.tickets.admin_conversation(admin, ticket.id)
    assert admin_messages
    assert all(message.is_read_by_admin == 1 for message in await repos.tickets.messages(ticket.id))
```

## `tests/integration/test_provider_service.py`

```python
"""
اختبارات طبقة المزودين: التشفير، إخفاء المفاتيح، تصنيف الأخطاء، والتعطيل التلقائي.

أهم ما يُحرَس هنا: **لا يظهر مفتاح API كاملاً في أي مكان** — لا في قاعدة
البيانات، ولا في سجل طلبات المزود، ولا في رسائل الواجهة.
"""

from __future__ import annotations

import pytest

from core.exceptions import (
    PermissionDeniedError,
    ProviderError,
    ProviderTemporaryError,
)
from database.database import Database
from database.models import User
from database.repositories import Repositories
from services import ServiceContainer

REAL_KEY = "sk-live-9f3b2c7d41ee8a56"


async def test_api_key_is_encrypted_at_rest_and_only_hinted(
    services: ServiceContainer, repos: Repositories, super_admin: User
) -> None:
    """المفتاح يُخزَّن مشفّراً ولا يُحفظ منه إلا آخر أربعة أرقام للعرض."""
    provider = await services.providers.create_provider(
        super_admin, name="PanelOne", api_url="https://panel.invalid/api/v2", api_key=REAL_KEY
    )
    stored = await repos.providers.get(provider.id)
    assert stored is not None
    assert REAL_KEY not in stored.api_key_enc
    assert stored.api_key_hint == "8a56"
    assert REAL_KEY not in (stored.api_key_hint or "")

    # ولا يظهر المفتاح في سجل التدقيق
    logs = await services.audit.by_target("provider", provider.id)
    assert logs
    assert all(REAL_KEY not in (log.after_json or "") for log in logs)


async def test_short_key_rejected_and_key_update_audited_without_the_key(
    services: ServiceContainer, repos: Repositories, super_admin: User
) -> None:
    """المفتاح القصير مرفوض، وتحديث المفتاح يُسجَّل دون كتابة المفتاح نفسه."""
    with pytest.raises(ProviderError):
        await services.providers.create_provider(
            super_admin, name="BadKey", api_url="https://panel.invalid/api/v2", api_key="123"
        )

    provider = await services.providers.create_provider(
        super_admin, name="PanelTwo", api_url="https://panel.invalid/api/v2", api_key=REAL_KEY
    )
    new_key = "sk-live-0000111122223333"
    assert await services.providers.update_api_key(super_admin, provider.id, new_key)

    updated = await repos.providers.get(provider.id)
    assert updated is not None and updated.api_key_hint == "3333"
    logs = await services.audit.by_target("provider", provider.id)
    key_logs = [log for log in logs if log.action == "providers.key.update"]
    assert key_logs and all(new_key not in (log.after_json or "") for log in key_logs)


async def test_provider_management_requires_permissions(
    services: ServiceContainer, user: User, admin: User, mock_provider
) -> None:
    """إضافة المزودين وتغيير مفاتيحهم محصورة بصلاحياتها."""
    with pytest.raises(PermissionDeniedError):
        await services.providers.create_provider(
            user, name="X", api_url="https://panel.invalid/api/v2", api_key=REAL_KEY
        )
    with pytest.raises(PermissionDeniedError):
        await services.providers.update_api_key(admin, mock_provider.id, REAL_KEY)
    with pytest.raises(PermissionDeniedError):
        await services.providers.test_connection(user, mock_provider.id)


async def test_balance_check_logs_request_without_secrets(
    services: ServiceContainer, repos: Repositories, mock_provider, mock_client
) -> None:
    """كل نداء للمزود يُسجَّل في `provider_requests` بلا أي سر."""
    balance = await services.providers.check_balance(mock_provider)
    assert balance.amount_units > 0

    rows = await repos.provider_requests.list_by_provider(mock_provider.id, limit=5)
    assert rows
    blob = " ".join(
        f"{row['request_summary']} {row['response_snippet']}" for row in rows
    )
    assert "mock-key-123456" not in blob
    assert "3456" not in blob or "api_key" not in blob


async def test_connection_test_returns_arabic_message(
    services: ServiceContainer, super_admin: User, mock_provider, mock_client
) -> None:
    """اختبار الاتصال من اللوحة يعطي رسالة عربية واضحة بلا أسرار."""
    ok, message = await services.providers.test_connection(super_admin, mock_provider.id)
    assert ok is True
    assert "الاتصال ناجح" in message
    assert "mock-key-123456" not in message

    missing_ok, missing_message = await services.providers.test_connection(super_admin, 99999)
    assert missing_ok is False and "غير موجود" in missing_message


async def test_repeated_failures_disable_provider_and_alert_admins(
    services: ServiceContainer, repos: Repositories, admin: User, mock_provider, mock_client
) -> None:
    """الأخطاء المتتالية تعطّل المزود مؤقتاً وتُنبّه الأدمن (حماية من استنزاف الطلبات)."""
    await services.settings.set("provider_failure_threshold", 3)
    await services.settings.set("provider_disable_minutes", 15)

    for _ in range(3):
        mock_client.fail_next_balance = ProviderTemporaryError("انقطاع الشبكة")
        with pytest.raises(ProviderTemporaryError):
            await services.providers.check_balance(mock_provider)

    disabled = await repos.providers.get(mock_provider.id)
    assert disabled is not None
    assert disabled.consecutive_failures >= 3
    assert disabled.disabled_until is not None
    assert not await services.providers.is_usable(disabled)

    inbox = await repos.notifications.list_for_user(admin.id)
    assert any("مزود" in item.title or "مزود" in item.message for item in inbox)


async def test_success_resets_failure_counter(
    services: ServiceContainer, repos: Repositories, mock_provider, mock_client
) -> None:
    """نجاح واحد يصفّر عدّاد الأخطاء المتتالية."""
    mock_client.fail_next_balance = ProviderTemporaryError("انقطاع مؤقت")
    with pytest.raises(ProviderTemporaryError):
        await services.providers.check_balance(mock_provider)
    assert (await repos.providers.get(mock_provider.id)).consecutive_failures == 1

    await services.providers.check_balance(mock_provider)
    assert (await repos.providers.get(mock_provider.id)).consecutive_failures == 0


async def test_disabled_provider_is_not_usable(
    services: ServiceContainer, repos: Repositories, super_admin: User, mock_provider
) -> None:
    """المزود المعطَّل يدوياً يخرج من الخدمة دون حذفه."""
    assert await services.providers.set_active(super_admin, mock_provider.id, False)
    provider = await repos.providers.get(mock_provider.id)
    assert provider is not None and provider.is_active == 0
    assert not await services.providers.is_usable(provider)

    assert await services.providers.set_active(super_admin, mock_provider.id, True)
    restored = await repos.providers.get(mock_provider.id)
    assert restored is not None and await services.providers.is_usable(restored)


async def test_health_snapshot_for_admin_panel(
    services: ServiceContainer, mock_provider, mock_client
) -> None:
    """ملخص صحة المزود يصلح للعرض المباشر في اللوحة."""
    health = await services.providers.health(mock_provider)
    assert health.provider.id == mock_provider.id
    assert health.is_usable is True
    assert health.reason


async def test_fetch_services_requires_sync_permission(
    services: ServiceContainer, user: User, super_admin: User, mock_provider, mock_client
) -> None:
    """استيراد خدمات المزود صلاحية مستقلة لا يملكها المستخدم العادي."""
    with pytest.raises(PermissionDeniedError):
        await services.providers.fetch_services(user, mock_provider)

    items = await services.providers.fetch_services(super_admin, mock_provider)
    assert items and items[0].provider_service_id
```

## `tests/integration/test_notification_service.py`

```python
"""
اختبارات صندوق الإشعارات (Outbox).

المبدأ: الإشعار يُكتب في قاعدة البيانات داخل معاملة العملية، ثم تُرسله مهمة
مستقلة. فشل الإرسال لا يُسقط العملية المالية، والمستخدم الذي حظر البوت لا
يُستنزف عليه الطابور.
"""

from __future__ import annotations

from core.enums import NotificationType
from core.exceptions import (
    NotificationBlockedError,
    NotificationPermanentError,
    NotificationTemporaryError,
)
from core.permissions import Permission
from database.database import Database
from database.models import User
from database.repositories import Repositories
from services import ServiceContainer


class FakeSender:
    """مرسل وهمي يسجّل ما أُرسل ويُمكن برمجته ليفشل (بديل تيليجرام في الاختبار)."""

    def __init__(self, *, error: Exception | None = None) -> None:
        """تهيئة المرسل مع استثناء اختياري يُرفع عند كل إرسال."""
        self.sent: list[tuple[int, str, str]] = []
        self.error = error

    async def __call__(self, telegram_id: int, title: str, message: str) -> int:
        """محاكاة إرسال رسالة وإرجاع معرف رسالة تيليجرام."""
        if self.error is not None:
            raise self.error
        self.sent.append((telegram_id, title, message))
        return 1_000 + len(self.sent)


async def _enqueue(services: ServiceContainer, db: Database, user: User, token: str = "t1") -> int | None:
    """إدراج إشعار يدوي في الطابور."""
    async with db.transaction() as tx:
        return await services.notifications.notify_user_manual(
            tx, user_id=user.id, token=token, title="عنوان", message="نص الإشعار"
        )


async def test_enqueue_then_dispatch_marks_sent(
    services: ServiceContainer, db: Database, repos: Repositories, user: User
) -> None:
    """الإشعار يُدرج أولاً ثم يُرسل ويُعلَّم كمُرسل."""
    await _enqueue(services, db, user)
    assert await services.notifications.queued_count() == 1

    sender = FakeSender()
    report = await services.notifications.dispatch_pending(sender)

    assert report.claimed == 1 and report.sent == 1
    assert sender.sent[0][0] == user.telegram_id
    assert await services.notifications.queued_count() == 0


async def test_duplicate_token_is_not_enqueued_twice(
    services: ServiceContainer, db: Database, user: User
) -> None:
    """مفتاح منع التكرار يمنع إدراج نفس الإشعار مرتين."""
    first = await _enqueue(services, db, user, token="same")
    second = await _enqueue(services, db, user, token="same")

    assert first is not None
    assert second is None
    assert await services.notifications.queued_count() == 1


async def test_blocked_user_is_skipped_and_flagged(
    services: ServiceContainer, db: Database, repos: Repositories, user: User
) -> None:
    """من يحظر البوت يُعلَّم في قاعدة البيانات ولا تُعاد المحاولة عليه."""
    await _enqueue(services, db, user)
    report = await services.notifications.dispatch_pending(
        FakeSender(error=NotificationBlockedError("bot was blocked by the user"))
    )

    assert report.skipped == 1 and report.sent == 0
    refreshed = await repos.users.get_by_id(user.id)
    assert refreshed is not None and refreshed.blocked_bot == 1


async def test_temporary_failure_keeps_notification_for_retry(
    services: ServiceContainer, db: Database, repos: Repositories, user: User
) -> None:
    """الفشل المؤقت يُبقي الإشعار لإعادة المحاولة لاحقاً."""
    await _enqueue(services, db, user)
    first = await services.notifications.dispatch_pending(
        FakeSender(error=NotificationTemporaryError("timeout"))
    )
    assert first.failed == 1

    notification = (await repos.notifications.list_for_user(user.id))[0]
    assert notification.status in {"queued", "failed"}
    assert notification.attempts >= 1


async def test_permanent_failure_stops_retrying(
    services: ServiceContainer, db: Database, repos: Repositories, user: User
) -> None:
    """الفشل النهائي يوقف المحاولات ولا يبقى الإشعار في الطابور."""
    await _enqueue(services, db, user)
    await services.notifications.dispatch_pending(
        FakeSender(error=NotificationPermanentError("chat not found"))
    )
    assert await services.notifications.queued_count() == 0


async def test_notify_admins_targets_permission_holders_only(
    services: ServiceContainer, db: Database, repos: Repositories,
    user: User, admin: User, super_admin: User,
) -> None:
    """تنبيه الأدمن يذهب لمن يملك الصلاحية فقط، لا لكل من له دور إداري."""
    async with db.transaction() as tx:
        count = await services.notifications.notify_admins(
            tx,
            permission=Permission.ORDERS_VIEW,
            token="test-alert",
            title="تنبيه",
            message="طلب يحتاج مراجعة",
        )

    assert count == 2  # admin + super_admin
    assert await repos.notifications.list_for_user(admin.id)
    assert await repos.notifications.list_for_user(super_admin.id)
    assert not await repos.notifications.list_for_user(user.id)


async def test_notify_admins_respects_individual_denial(
    services: ServiceContainer, db: Database, repos: Repositories, admin: User, super_admin: User
) -> None:
    """من مُنع فردياً من صلاحية لا يصله تنبيهها."""
    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.PAYMENTS_APPROVE, allow=False
    )
    async with db.transaction() as tx:
        await services.notifications.notify_admins(
            tx,
            permission=Permission.PAYMENTS_APPROVE,
            token="payment-alert",
            title="شحن جديد",
            message="طلب شحن بانتظار المراجعة",
        )

    assert not await repos.notifications.list_for_user(admin.id)
    assert await repos.notifications.list_for_user(super_admin.id)


async def test_unread_count_and_mark_all_read(
    services: ServiceContainer, db: Database, user: User
) -> None:
    """عدّاد غير المقروء يعمل ويمكن تصفيره دفعة واحدة."""
    await _enqueue(services, db, user, token="a")
    await _enqueue(services, db, user, token="b")
    assert await services.notifications.unread_count(user.id) == 2

    assert await services.notifications.mark_all_read(user.id) == 2
    assert await services.notifications.unread_count(user.id) == 0


async def test_order_notifications_use_event_specific_keys(
    services: ServiceContainer, db: Database, repos: Repositories, user: User
) -> None:
    """إشعارات الطلب الواحد تختلف بحسب الحدث فلا يبتلع أحدها الآخر."""
    async with db.transaction() as tx:
        first = await services.notifications.notify_order(
            tx, user_id=user.id, order_id=1, event=NotificationType.ORDER_CREATED,
            title="أُنشئ", message="تم إنشاء طلبك",
        )
        second = await services.notifications.notify_order(
            tx, user_id=user.id, order_id=1, event=NotificationType.ORDER_COMPLETED,
            title="اكتمل", message="اكتمل طلبك",
        )
        third = await services.notifications.notify_order(
            tx, user_id=user.id, order_id=1, event=NotificationType.ORDER_CREATED,
            title="أُنشئ مجدداً", message="تكرار",
        )

    assert first is not None and second is not None
    assert third is None, "نفس الحدث لنفس الطلب يجب ألا يتكرر"
    assert len(await repos.notifications.list_for_user(user.id)) == 2
```

## `tests/integration/test_stats_service.py`

```python
"""
اختبارات الإحصائيات: كل رقم يجب أن يأتي من قاعدة البيانات لا من تقدير.
"""

from __future__ import annotations

import pytest

from core.enums import OrderStatus
from core.exceptions import PermissionDeniedError
from core.permissions import Permission
from database.models import Service, User
from database.repositories import Repositories
from services import ServiceContainer
from utils.datetime_utils import iso_plus_seconds


async def _prepare_activity(
    services: ServiceContainer, user: User, admin: User, mock_service: Service, count: int = 3
) -> None:
    """تجهيز نشاط حقيقي: رصيد + طلبات فعلية."""
    await services.wallet.adjust_balance(
        target=user, amount_units=200_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    await services.settings.set("duplicate_order_window_minutes", 0)
    for index in range(count):
        await services.orders.create_order(
            user,
            service_id=mock_service.id,
            link=f"https://instagram.com/u{index}",
            quantity=1000,
        )


async def test_dashboard_requires_permission(services: ServiceContainer, user: User) -> None:
    """المستخدم العادي لا يرى لوحة الإحصائيات."""
    with pytest.raises(PermissionDeniedError):
        await services.stats.dashboard(user)


async def test_dashboard_numbers_match_database(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, mock_service: Service
) -> None:
    """أرقام اللوحة مطابقة لما في قاعدة البيانات فعلاً."""
    await _prepare_activity(services, user, admin, mock_service, count=3)

    stats = await services.stats.dashboard(admin)
    assert stats.users_total == await repos.users.count_all()
    assert stats.orders_today == 3
    assert stats.orders_by_status.get(OrderStatus.PENDING) == 3
    assert stats.revenue_today_units == 30_000
    assert stats.active_services == 1
    assert stats.pending_payments == 0


async def test_dashboard_text_is_arabic_and_complete(
    services: ServiceContainer, user: User, admin: User, mock_service: Service
) -> None:
    """النص المعروض للأدمن يحتوي الأقسام الأساسية."""
    await _prepare_activity(services, user, admin, mock_service, count=1)
    text = await services.stats.dashboard_text(admin)

    for part in ["لوحة المعلومات", "المستخدمون", "طلبات اليوم", "مبيعات اليوم", "تذاكر مفتوحة"]:
        assert part in text


async def test_financial_report_counts_money_movements(
    services: ServiceContainer, user: User, admin: User, super_admin: User, mock_service: Service, payment_method
) -> None:
    """التقرير المالي يجمع المبيعات والإيداعات والاسترجاعات."""
    await _prepare_activity(services, user, admin, mock_service, count=2)

    payment = await services.payments.create_payment(
        user, method_id=payment_method.id, raw_amount="10", transaction_reference="TRX-STATS"
    )
    await services.payments.approve(admin, payment.id)

    orders = await services.orders.list_for_user(user)
    await services.orders.cancel_by_user(user, orders[0].id)

    report = await services.stats.financial_report(super_admin, days=1)
    assert report.orders_count == 2
    assert report.revenue_units == 20_000
    assert report.deposits_units == 100_000
    assert report.refunds_units == 10_000


async def test_profit_hidden_without_permission(
    services: ServiceContainer, user: User, admin: User, mock_service: Service
) -> None:
    """الربح لا يُحسب لمن لا يملك صلاحية `stats.profit` (لا رقم مضلل)."""
    await _prepare_activity(services, user, admin, mock_service, count=1)

    report = await services.stats.financial_report(admin, days=1)
    assert report.profit_units is None
    assert not report.profit_known

    text = await services.stats.financial_report_text(admin, days=1)
    assert "غير محسوب" in text


async def test_profit_calculated_for_super_admin(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    super_admin: User, mock_service: Service, mock_client,
) -> None:
    """الأدمن الأعلى يرى الربح = المبيعات ناقص تكلفة المزود المسجّلة."""
    await _prepare_activity(services, user, admin, mock_service, count=1)
    await services.orders.process_pending_orders()

    report = await services.stats.financial_report(super_admin, days=1)
    assert report.provider_cost_units == 6_000
    assert report.profit_units == report.revenue_units - 6_000


async def test_operations_report_measures_success_rate(
    services: ServiceContainer, repos: Repositories, user: User, admin: User,
    mock_service: Service, mock_client,
) -> None:
    """تقرير التشغيل يحسب نسبة النجاح من الطلبات الفعلية."""
    await _prepare_activity(services, user, admin, mock_service, count=2)
    await services.orders.process_pending_orders()

    for _ in range(5):   # تقديم موعد الفحص ثم المتابعة حتى الاكتمال
        for order in await services.orders.list_for_user(user):
            async with repos.db.transaction() as tx:
                await repos.orders.update_fields(
                    tx, order.id, next_check_at=iso_plus_seconds(-10)
                )
        await services.orders.process_due_orders()

    report = await services.stats.operations_report(admin, days=1)
    assert report.total_orders == 2
    assert report.completed == 2
    assert report.success_rate == 100.0
    assert report.uncertain_orders == 0


async def test_top_services_and_users(
    services: ServiceContainer, user: User, admin: User, mock_service: Service
) -> None:
    """تقارير الأكثر طلباً والأكثر إنفاقاً مبنية على بيانات حقيقية."""
    await _prepare_activity(services, user, admin, mock_service, count=2)

    top_services = await services.stats.top_services(admin, days=1)
    assert top_services[0]["service_name"] == mock_service.name
    assert top_services[0]["orders_count"] == 2

    top_users = await services.stats.top_users(admin)
    assert top_users[0][0] == user.display_name
    assert top_users[0][1] == 20_000


async def test_wallet_liability_matches_balances(
    services: ServiceContainer, user: User, admin: User
) -> None:
    """التزام المحفظة = مجموع أرصدة المستخدمين الفعلية."""
    await services.wallet.adjust_balance(
        target=user, amount_units=75_000, admin=admin, reason="رصيد", credit=True
    )
    total, deposits, spent = await services.stats.wallet_liability(admin)
    assert total == 75_000
    assert deposits == 0      # لا إيداعات عبر طلبات شحن
    assert spent == 0


async def test_system_health_reports_providers(
    services: ServiceContainer, admin: User, mock_provider
) -> None:
    """تقرير الصحة يعرض حالة كل مزود وحجم قاعدة البيانات."""
    health = await services.stats.system_health(admin)
    assert health["providers"][0]["name"] == mock_provider.name
    assert health["providers"][0]["usable"] is True
    assert float(health["db_size_mb"]) >= 0

    text = await services.stats.health_text(admin)
    assert "صحة النظام" in text and mock_provider.name in text


async def test_daily_series_groups_by_day(
    services: ServiceContainer, user: User, admin: User, mock_service: Service
) -> None:
    """السلسلة اليومية تجمع طلبات اليوم في صف واحد."""
    await _prepare_activity(services, user, admin, mock_service, count=2)
    series = await services.stats.daily_series(admin, days=2)
    assert len(series) == 1
    assert series[0]["orders_count"] == 2
    assert series[0]["total_units"] == 20_000


async def test_support_role_can_view_stats_but_not_profit(
    services: ServiceContainer, repos: Repositories, user: User, super_admin: User
) -> None:
    """دور الدعم لا يملك `stats.view` افتراضياً — الإحصائيات ليست من مهامه."""
    assert not await services.auth.has_permission(user, Permission.STATS_VIEW)
    await services.auth.set_user_permission(
        super_admin, user.id, Permission.STATS_VIEW, allow=True
    )
    granted = await repos.users.get_by_id(user.id)
    assert granted is not None
    stats = await services.stats.dashboard(granted)
    assert stats.users_total >= 1
```

## `tests/e2e/test_full_cycle.py`

```python
"""
اختبار القبول النهائي للمرحلة 2 — الدورة الكاملة كما طلبها المالك:

    تسجيل → تصفح → طلب → شحن → اعتماد → خصم → إرسال للمزود → متابعة آلية
    → إكمال → إشعار → سجل → إحصائيات

والمسار البديل:

    فشل المزود → استرجاع آمن → حركة مالية → إشعار المستخدم والأدمن

كل خطوة هنا تمرّ عبر الخدمات الحقيقية ولا شيء فيها وهمي إلا واجهة المزود
(`MockProviderClient`) وواجهة إرسال رسائل تيليجرام (`CollectingSender`)، لأن
الاثنين شبكة خارجية.
"""

from __future__ import annotations

import pytest

from core.enums import (
    FINAL_ORDER_STATUSES,
    NotificationType,
    OrderStatus,
    PaymentStatus,
    TransactionType,
)
from core.exceptions import InsufficientBalanceError, ProviderPermanentError
from database.database import Database
from database.models import Service, User
from database.repositories import Repositories
from services import ServiceContainer
from utils.datetime_utils import iso_plus_seconds


class CollectingSender:
    """بديل واجهة تيليجرام: يجمع الرسائل المرسلة ليُتحقق منها في الاختبار."""

    def __init__(self) -> None:
        """تهيئة قائمة الرسائل المجمّعة."""
        self.messages: list[tuple[int, str, str]] = []

    async def __call__(self, telegram_id: int, title: str, message: str) -> int:
        """محاكاة إرسال رسالة وإرجاع معرف رسالة."""
        self.messages.append((telegram_id, title, message))
        return len(self.messages)

    def to(self, telegram_id: int) -> list[tuple[str, str]]:
        """كل ما وصل إلى مستخدم بعينه (عنوان، نص)."""
        return [(title, body) for chat_id, title, body in self.messages if chat_id == telegram_id]


async def _follow_until_final(
    services: ServiceContainer, repos: Repositories, order_id: int, *, rounds: int = 8
) -> None:
    """تشغيل حلقة المتابعة الآلية مع تقديم مواعيد الفحص حتى تستقر حالة الطلب."""
    for _ in range(rounds):
        order = await repos.orders.get(order_id)
        assert order is not None
        if order.status in FINAL_ORDER_STATUSES:
            return
        async with repos.db.transaction() as tx:
            await repos.orders.update_fields(tx, order_id, next_check_at=iso_plus_seconds(-10))
        await services.orders.process_due_orders()


# ======================================================================== #
#                         المسار الكامل الناجح                              #
# ======================================================================== #


async def test_full_happy_cycle_from_registration_to_statistics(
    services: ServiceContainer,
    db: Database,
    repos: Repositories,
    admin: User,
    super_admin: User,
    mock_service: Service,
    mock_client,
    payment_method,
) -> None:
    """الدورة الكاملة من /start حتى ظهور الطلب في الإحصائيات وسجلات التدقيق."""

    # 1) التسجيل — أول تفاعل مع البوت ينشئ الحساب برصيد صفر
    customer, created = await services.users.get_or_create(
        telegram_id=555000111, username="ClientOne", first_name="عميل"
    )
    assert created is True
    assert customer.balance_units == 0
    again, created_again = await services.users.get_or_create(telegram_id=555000111)
    assert created_again is False and again.id == customer.id

    # 2) التصفح — التصنيفات ثم خدمات التصنيف ثم التسعيرة
    categories = await services.catalog.categories()
    assert categories
    page = await services.catalog.services_page(categories[0].id)
    assert any(item.id == mock_service.id for item in page.items)
    chosen = await services.catalog.get_available_service(mock_service.id)
    quote = await services.catalog.quote(chosen, 1000)
    assert quote.cost_units == 10_000

    # 3) محاولة الطلب بلا رصيد — تُرفض ولا تترك أي أثر
    with pytest.raises(InsufficientBalanceError):
        await services.orders.create_order(
            customer, service_id=chosen.id, link="https://instagram.com/p/abc", quantity=1000
        )
    assert await repos.orders.count_by_user(customer.id) == 0

    # 4) الشحن — المستخدم يرسل إثبات تحويل
    payment = await services.payments.create_payment(
        customer,
        method_id=payment_method.id,
        raw_amount="5",
        transaction_reference="TRX-E2E-1",
        proof_file_id="proof-file",
        proof_file_type="photo",
    )
    assert payment.status == PaymentStatus.PENDING
    assert await services.wallet.balance_units(customer.id) == 0

    # 5) الاعتماد — الأدمن يعتمد فيُضاف الرصيد عبر المحفظة المركزية وحدها
    deposit_tx = await services.payments.approve(admin, payment.id)
    assert deposit_tx.type == TransactionType.DEPOSIT
    assert await services.wallet.balance_units(customer.id) == 50_000

    # 6) الطلب — الخصم يتم داخل نفس معاملة إنشاء الطلب
    order = await services.orders.create_order(
        customer, service_id=chosen.id, link="https://instagram.com/p/abc", quantity=1000
    )
    assert order.status == OrderStatus.PENDING
    assert order.cost_units == 10_000
    assert order.public_code == f"ORD-{order.id:06d}"
    assert await services.wallet.balance_units(customer.id) == 40_000

    # 7) الإرسال للمزود — مهمة الخلفية تلتقط الطلب وترسله
    batch = await services.orders.process_pending_orders()
    assert (batch.claimed, batch.succeeded, batch.failed) == (1, 1, 0)
    after_submit = await repos.orders.get(order.id)
    assert after_submit is not None
    assert after_submit.status == OrderStatus.SUBMITTED
    assert after_submit.provider_order_id is not None
    assert after_submit.provider_cost_units == 6_000
    assert mock_client.calls[0][0] == "add"

    # 8) المتابعة الآلية حتى الإكمال
    await _follow_until_final(services, repos, order.id)
    completed = await repos.orders.get(order.id)
    assert completed is not None
    assert completed.status == OrderStatus.COMPLETED
    assert completed.delivered_quantity == 1000
    assert completed.remains == 0
    assert completed.completed_at is not None

    # 9) الإشعارات — تصل فعلاً إلى تيليجرام عبر مهمة الإرسال
    sender = CollectingSender()
    report = await services.notifications.dispatch_pending(sender, limit=50)
    assert report.sent >= 3
    customer_titles = " | ".join(title for title, _ in sender.to(customer.telegram_id))
    assert "طلب" in customer_titles
    types = {item.type for item in await repos.notifications.list_for_user(customer.id)}
    assert {
        NotificationType.PAYMENT_APPROVED,
        NotificationType.ORDER_CREATED,
        NotificationType.ORDER_COMPLETED,
    } <= types
    assert await services.notifications.queued_count() == 0

    # 10) السجلات — حركات مالية متوازنة وسجل تدقيق لإجراء الأدمن
    movements = await repos.transactions.list_by_user(customer.id, limit=10)
    assert [item.type for item in movements] == [TransactionType.ORDER, TransactionType.DEPOSIT]
    ledger = await services.wallet.verify_ledger(customer.id)
    assert ledger.is_balanced
    assert ledger.stored_units == 40_000
    approve_logs = await services.audit.by_target("payment", payment.id)
    assert any(log.action == "payments.approve" and log.admin_id == admin.id for log in approve_logs)
    statuses = [row.to_status for row in await repos.orders.history(order.id)]
    assert statuses[0] == OrderStatus.PENDING
    assert OrderStatus.SUBMITTED in statuses
    assert statuses[-1] == OrderStatus.COMPLETED

    # 11) الإحصائيات — الدورة ظاهرة بأرقام حقيقية
    dashboard = await services.stats.dashboard(admin)
    assert dashboard.orders_today == 1
    assert dashboard.revenue_today_units == 10_000
    assert dashboard.orders_by_status.get(OrderStatus.COMPLETED) == 1

    financial = await services.stats.financial_report(super_admin, days=1)
    assert financial.deposits_units == 50_000
    assert financial.revenue_units == 10_000
    assert financial.refunds_units == 0
    assert financial.profit_units == 4_000          # 10000 مبيعات − 6000 تكلفة مزود

    operations = await services.stats.operations_report(admin, days=1)
    assert operations.total_orders == 1 and operations.completed == 1
    assert operations.success_rate == 100.0


# ======================================================================== #
#                      المسار البديل: فشل المزود                           #
# ======================================================================== #


async def test_provider_failure_cycle_refunds_and_alerts_everyone(
    services: ServiceContainer,
    db: Database,
    repos: Repositories,
    user: User,
    admin: User,
    mock_service: Service,
    mock_client,
) -> None:
    """فشل المزود ⇒ استرجاع كامل موثّق + إشعار المستخدم والأدمن + مال لا يضيع."""
    await services.wallet.adjust_balance(
        target=user, amount_units=60_000, admin=admin, reason="رصيد افتتاحي", credit=True
    )
    before = await services.wallet.balance_units(user.id)

    mock_client.always_fail_add = ProviderPermanentError("الخدمة غير موجودة لدى المزود")

    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/fail", quantity=1000
    )
    assert await services.wallet.balance_units(user.id) == before - 10_000

    await services.orders.process_pending_orders()

    failed = await repos.orders.get(order.id)
    assert failed is not None
    assert failed.status == OrderStatus.REFUNDED        # فشل ثم استرجاع كامل
    assert failed.refund_amount_units == 10_000
    assert failed.last_error

    # المال عاد كاملاً ومعه حركة مالية موثّقة ودفتر متوازن
    assert await services.wallet.balance_units(user.id) == before
    movements = await repos.transactions.list_by_user(user.id, limit=5)
    assert movements[0].type == TransactionType.REFUND
    assert movements[0].amount_units == 10_000
    assert movements[0].reference == f"refund:order:{order.id}"
    assert (await services.wallet.verify_ledger(user.id)).is_balanced

    # الخطأ مسجَّل للمتابعة الفنية
    errors = await repos.error_logs.list_recent(limit=10)
    assert any("فشل الطلب" in str(row["message"]) for row in errors)

    # إشعار المستخدم وتنبيه الأدمن — كلاهما يصل فعلاً
    sender = CollectingSender()
    await services.notifications.dispatch_pending(sender, limit=50)
    user_inbox = await repos.notifications.list_for_user(user.id)
    user_types = {item.type for item in user_inbox}
    assert NotificationType.ORDER_FAILED in user_types
    failure_text = " ".join(item.message for item in user_inbox if item.type == NotificationType.ORDER_FAILED)
    assert "استرجاع" in failure_text or "أُعيد" in failure_text, "رسالة الفشل يجب أن تُطمئن المستخدم بعودة المبلغ"
    assert sender.to(user.telegram_id)
    assert sender.to(admin.telegram_id), "يجب تنبيه الأدمن بفشل المزود"

    # لا إعادة إرسال للطلب الفاشل مهما تكررت دورات المعالجة
    assert (await services.orders.process_pending_orders()).claimed == 0
    await _follow_until_final(services, repos, order.id, rounds=3)
    still = await repos.orders.get(order.id)
    assert still is not None and still.status == OrderStatus.REFUNDED
    assert await services.wallet.balance_units(user.id) == before


async def test_cycle_survives_restart_without_losing_or_duplicating_money(
    services: ServiceContainer,
    db: Database,
    repos: Repositories,
    user: User,
    admin: User,
    mock_service: Service,
    mock_client,
) -> None:
    """سقوط البوت أثناء الإرسال: لا طلب مكرر لدى المزود ولا مال ضائع."""
    await services.wallet.adjust_balance(
        target=user, amount_units=100_000, admin=admin, reason="رصيد", credit=True
    )
    await services.settings.set("duplicate_order_window_minutes", 0)

    orders = [
        await services.orders.create_order(
            user, service_id=mock_service.id, link=f"https://instagram.com/p/{index}", quantity=1000
        )
        for index in range(3)
    ]

    # محاكاة الانقطاع: طلب عالق في "جاري الإرسال" بلا رقم لدى المزود
    async with db.transaction() as tx:
        await repos.orders.update_fields(
            tx, orders[0].id, status=OrderStatus.SUBMITTING,
            locked_by="worker-crashed", locked_until=iso_plus_seconds(-30),
        )

    recovered = await services.orders.recover_after_restart()
    assert recovered["uncertain"] == 1
    stuck = await repos.orders.get(orders[0].id)
    assert stuck is not None and stuck.status == OrderStatus.SUBMIT_UNCERTAIN

    # بقية الطلبات تُستأنف طبيعياً، والطلب غير المؤكد لا يُرسل تلقائياً أبداً
    batch = await services.orders.process_pending_orders()
    assert batch.claimed == 2 and batch.succeeded == 2
    await _follow_until_final(services, repos, orders[1].id)
    await _follow_until_final(services, repos, orders[2].id)

    add_calls = [call for call in mock_client.calls if call[0] == "add"]
    assert len(add_calls) == 2
    assert {call[1]["link"] for call in add_calls} == {
        "https://instagram.com/p/1", "https://instagram.com/p/2"
    }

    # الأدمن نُبِّه للطلب غير المؤكد ليحسمه يدوياً
    admin_inbox = await repos.notifications.list_for_user(admin.id)
    assert any("مؤكد" in (item.title or "") or "مؤكد" in (item.message or "") for item in admin_inbox)

    # الحسم اليدوي: الأدمن يؤكد أن المزود لم يستلم الطلب ⇒ استرجاع كامل
    refunded_units = await services.orders.admin_mark_failed(
        admin, orders[0].id, "تأكدنا من المزود: الطلب لم يصله"
    )
    assert refunded_units == 10_000
    resolved = await repos.orders.get(orders[0].id)
    assert resolved is not None and resolved.status == OrderStatus.REFUNDED

    # المحصلة النهائية: دفتر متوازن، ولا مال مفقود ولا مضاعف
    ledger = await services.wallet.verify_ledger(user.id)
    assert ledger.is_balanced
    final_orders = await services.orders.list_for_user(user)
    spent = sum(order.cost_units - order.refund_amount_units for order in final_orders)
    assert await services.wallet.balance_units(user.id) == 100_000 - spent
    assert spent == 20_000
```

