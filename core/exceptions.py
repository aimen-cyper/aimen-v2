"""
استثناءات المشروع — كل خطأ متوقع له صنف خاص به.

الفائدة: التعامل مع كل حالة خطأ برسالة مناسبة للمستخدم دون كشف التفاصيل الداخلية،
وبدون استخدام «except: pass» في أي مكان.
"""

from __future__ import annotations


class SMMBotError(Exception):
    """الصنف الأب لكل أخطاء المشروع."""

    #: رسالة عربية مبسطة تُعرض للمستخدم النهائي
    user_message: str = "حدث خطأ غير متوقع. حاول لاحقاً."

    def __init__(self, message: str | None = None, *, user_message: str | None = None) -> None:
        """تخزين الرسالة التقنية (للسجل) والرسالة العربية المبسطة (للمستخدم)."""
        super().__init__(message or self.__class__.__doc__ or "")
        if user_message:
            self.user_message = user_message


# ----------------------------- قاعدة البيانات ----------------------------- #


class DatabaseError(SMMBotError):
    """خطأ عام في قاعدة البيانات."""

    user_message = "تعذر تنفيذ العملية حالياً. حاول بعد قليل."


class DatabaseLockedError(DatabaseError):
    """قاعدة البيانات مقفولة بعد استنفاد محاولات إعادة المحاولة."""


class MigrationError(DatabaseError):
    """خطأ أثناء تطبيق ترحيلات قاعدة البيانات."""


class MigrationChecksumError(MigrationError):
    """تم تعديل ملف ترحيل سبق تطبيقه — ممنوع لأنه يفسد تطابق المخطط."""


# ------------------------------- المال والرصيد ----------------------------- #


class WalletError(SMMBotError):
    """خطأ في عمليات المحفظة."""


class InsufficientBalanceError(WalletError):
    """الرصيد غير كافٍ لإتمام العملية."""

    user_message = "❌ رصيدك غير كافٍ لإتمام هذه العملية."


class InvalidAmountError(WalletError):
    """قيمة المبلغ غير صالحة (صفر أو سالبة أو غير رقمية)."""

    user_message = "❌ المبلغ المُدخل غير صالح."


class DuplicateOperationError(SMMBotError):
    """العملية نُفِّذت مسبقاً بنفس المرجع (حماية من التكرار)."""

    user_message = "⚠️ هذه العملية تم تنفيذها مسبقاً."


# -------------------------------- الطلبات --------------------------------- #


class OrderError(SMMBotError):
    """خطأ عام في الطلبات."""


class InvalidStateTransitionError(OrderError):
    """محاولة انتقال حالة غير مسموح بها."""

    user_message = "⚠️ لا يمكن تنفيذ هذا الإجراء على الطلب في حالته الحالية."


class ServiceNotAvailableError(OrderError):
    """الخدمة غير مفعّلة أو محذوفة."""

    user_message = "❌ هذه الخدمة غير متاحة حالياً."


class QuantityOutOfRangeError(OrderError):
    """الكمية خارج الحد الأدنى/الأقصى للخدمة."""

    user_message = "❌ الكمية خارج الحدود المسموحة لهذه الخدمة."


class InvalidLinkError(OrderError):
    """الرابط غير صالح أو لا يطابق نوع الخدمة."""

    user_message = "❌ الرابط غير صالح. تأكد منه وأعد الإرسال."


# ------------------------------- المدفوعات -------------------------------- #


class PaymentError(SMMBotError):
    """خطأ عام في طلبات الشحن (غير موجود، لا يخص المستخدم، بيانات ناقصة)."""

    user_message = "❌ تعذر تنفيذ العملية على طلب الشحن."


# --------------------------------- الدعم ---------------------------------- #


class TicketError(SMMBotError):
    """خطأ عام في تذاكر الدعم (غير موجودة، مغلقة، أو ليست للمستخدم)."""

    user_message = "❌ تعذر تنفيذ العملية على التذكرة."


# -------------------------------- المزودون -------------------------------- #


class ProviderError(SMMBotError):
    """خطأ عام في التعامل مع مزود الخدمة."""

    user_message = "⚠️ تعذر الاتصال بمزود الخدمة حالياً."


class ProviderTemporaryError(ProviderError):
    """خطأ مؤقت — يمكن إعادة المحاولة بأمان."""


class ProviderPermanentError(ProviderError):
    """خطأ نهائي من المزود — لا فائدة من إعادة المحاولة."""


class ProviderUncertainError(ProviderError):
    """نتيجة غير مؤكدة (مهلة/انقطاع) — ممنوع إعادة الإرسال تلقائياً."""


# -------------------------------- الصلاحيات -------------------------------- #


class PermissionDeniedError(SMMBotError):
    """المستخدم لا يملك الصلاحية المطلوبة."""

    user_message = "🚫 لا تملك صلاحية تنفيذ هذا الإجراء."


class UserBannedError(SMMBotError):
    """المستخدم محظور من استخدام البوت."""

    user_message = "🚫 حسابك محظور من استخدام البوت."


class MaintenanceModeError(SMMBotError):
    """النظام في وضع الصيانة."""

    user_message = "🚧 النظام في وضع الصيانة حالياً. حاول لاحقاً."


class RateLimitedError(SMMBotError):
    """تجاوز المستخدم الحد المسموح من الطلبات."""

    user_message = "⏳ أبطئ قليلاً، لقد أرسلت طلبات كثيرة."


# ---------------------------------- الأمان --------------------------------- #


class EncryptionError(SMMBotError):
    """خطأ في تشفير/فك تشفير الأسرار."""

    user_message = "تعذر تنفيذ العملية لأسباب أمنية."


class ValidationError(SMMBotError):
    """خطأ في التحقق من صحة المدخلات."""

    user_message = "❌ المدخلات غير صحيحة."


class ProviderInsufficientFundsError(ProviderTemporaryError):
    """رصيد حسابنا لدى المزود غير كافٍ — خطأ مؤقت يُنتظر حله بشحن الحساب."""

    user_message = "⏳ طلبك في الانتظار، سيبدأ التنفيذ قريباً."


class ProviderServiceMismatchError(ProviderPermanentError):
    """المزود لا يعرف رقم الخدمة المرسل أو رفض معاملاتها (إعداد خاطئ عندنا)."""

    user_message = "❌ هذه الخدمة غير متاحة حالياً لدى المزود."


# ------------------------------- الإشعارات -------------------------------- #


class NotificationError(SMMBotError):
    """خطأ عام أثناء إرسال إشعار."""


class NotificationTemporaryError(NotificationError):
    """فشل مؤقت في الإرسال (شبكة/حد معدل) — يُعاد المحاولة لاحقاً."""


class NotificationBlockedError(NotificationError):
    """المستخدم حظر البوت أو أوقف المحادثة — لا فائدة من إعادة المحاولة."""


class NotificationPermanentError(NotificationError):
    """فشل نهائي في الإرسال (رسالة غير صالحة مثلاً) — لا يُعاد المحاولة."""


# ------------------------------ النسخ الاحتياطي ----------------------------- #


class BackupError(SMMBotError):
    """فشل في إنشاء نسخة احتياطية أو فحصها أو إرسالها."""

    user_message = "❌ تعذّرت عملية النسخ الاحتياطي. راجع سجل الأخطاء."


class BackupBusyError(BackupError):
    """نسخة أخرى قيد الإنشاء الآن (لا نُنشئ نسختين متزامنتين)."""

    user_message = "⏳ هناك نسخة احتياطية قيد الإنشاء الآن. انتظر انتهاءها."
