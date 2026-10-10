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
from utils.link_rules import check_link_rule

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


def clean_multiline(
    value: str | None, *, field: str, max_length: int, min_length: int = 1
) -> str:
    """
    تنظيف نص متعدد الأسطر **مع الحفاظ على الأسطر**.

    لماذا لا نستخدم `clean_text`؟ لأنها تدمج كل شيء في سطر واحد، وبعض النصوص
    (تعليمات التحويل، نص قالب إشعار) تفقد معناها بلا أسطر.

    القواعد: تُشذَّب الفراغات داخل كل سطر، ويُمنع تكرار الأسطر الفارغة.

    الاستثناءات:
        ValidationError : النص فارغ أو أطول من المسموح.
    """
    kept: list[str] = []
    for raw_line in (value or "").splitlines():
        line = " ".join(raw_line.split())
        if not line and (not kept or not kept[-1]):
            continue  # لا نسمح بأكثر من سطر فارغ متتالٍ
        kept.append(line)
    text = "\n".join(kept).strip()
    if len(text) < min_length:
        raise ValidationError(f"حقل {field} فارغ", user_message=f"❌ الرجاء إدخال {field}.")
    if len(text) > max_length:
        raise ValidationError(
            f"حقل {field} أطول من {max_length}",
            user_message=f"❌ {field} طويل جداً (الحد الأقصى {max_length} حرفاً).",
        )
    return text


def validate_link(link: str | None, *, pattern: str | None = None, rule: str | None = None) -> str:
    """
    التحقق من رابط الطلب.

    المدخلات:
        link    : الرابط كما أدخله المستخدم.
        pattern : تعبير نمطي اختياري مرتبط بالخدمة (مثلاً روابط انستغرام فقط).
        rule    : مفتاح قاعدة منصة/نوع (`utils.link_rules.LINK_RULES`) مثل `instagram_profile`.

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
    if rule:
        check_link_rule(normalized, rule)
    return normalized


def parse_margin_percent(raw: str | None, *, minimum: int = 0, maximum: int = 1000) -> int:
    """
    تحليل هامش الربح المُدخَل: **رقم صحيح فقط** (`40` تعني ربح 40%)، بلا علامة `%`.

    الرفض برسالة عربية محددة لكل حالة: فارغ، فيه %، عشري، حروف، سالب، خارج الحدود.
    الأرقام العربية/الهندية مقبولة.

    الاستثناءات: ValidationError.
    """
    text = normalize_digits((raw or "").strip())
    example = "مثال: <code>40</code> تعني ربح 40%"
    if not text:
        raise ValidationError("هامش فارغ", user_message=f"❌ أرسل نسبة الهامش كرقم. {example}")
    if "%" in text:
        raise ValidationError(
            f"هامش فيه علامة %: {raw!r}", user_message=f"❌ اكتب الرقم فقط بلا علامة %. {example}"
        )
    if text.startswith("-"):
        raise ValidationError(
            f"هامش سالب: {raw!r}", user_message=f"❌ الهامش لا يكون سالباً (من {minimum} إلى {maximum}). {example}"
        )
    if "." in text or "," in text:
        raise ValidationError(
            f"هامش عشري: {raw!r}", user_message=f"❌ الهامش رقم صحيح بلا كسور. {example}"
        )
    if not text.isdigit():
        raise ValidationError(
            f"هامش غير رقمي: {raw!r}", user_message=f"❌ أرسل رقماً فقط بلا حروف أو رموز. {example}"
        )
    value = int(text)
    if value < minimum or value > maximum:
        raise ValidationError(
            f"هامش خارج الحدود: {value}",
            user_message=f"❌ الهامش يجب أن يكون بين {minimum} و{maximum}. {example}",
        )
    return value


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
