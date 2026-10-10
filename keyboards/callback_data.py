"""
ترميز وفك بيانات الأزرار (callback_data) بشكل مُهيكل وآمن.

لماذا ملف مستقل؟
    تيليجرام يسمح بـ64 بايت فقط لكل `callback_data`، وأي زر قديم في محادثة
    مستخدم قد يُضغط بعد تحديث البوت. لذلك نعتمد صيغة واحدة في كل المشروع:

        namespace:action:arg1:arg2...:vN

    • `namespace` يحدد الشاشة (cat / ord / wal / dep / sup / acc / nav / flow).
    • `action` يحدد الإجراء داخل الشاشة.
    • `vN` لاحقة الإصدار؛ إذا تغيّرت بنية الأزرار مستقبلاً نرفع الرقم،
      فتُرفض الأزرار القديمة برسالة واضحة بدل تنفيذ إجراء خاطئ.

قواعد ملزِمة:
    • ممنوع زر بلا معنى: كل `callback_data` يُبنى من هنا وله معالج مسجَّل
      (يتحقق من ذلك اختبار `test_no_dead_buttons`).
    • ممنوع تمرير نص حر من المستخدم داخل `callback_data` (طوله غير مضمون).
"""

from __future__ import annotations

from dataclasses import dataclass

#: إصدار بنية الأزرار الحالي — يُلحق بكل زر
CALLBACK_VERSION: int = 1

#: الحد الأقصى الذي تسمح به تيليجرام لحجم callback_data (بايت)
MAX_CALLBACK_BYTES: int = 64

#: الفاصل بين أجزاء الزر
SEPARATOR: str = ":"


class CallbackError(ValueError):
    """خطأ في بناء أو قراءة بيانات زر (بنية غير صحيحة أو طول زائد)."""


@dataclass(frozen=True, slots=True)
class Callback:
    """بيانات زر بعد فكّها: المساحة، الإجراء، الوسائط، الإصدار."""

    namespace: str
    action: str
    args: tuple[str, ...]
    version: int

    def arg(self, index: int, default: str = "") -> str:
        """قراءة وسيط نصي بموضعه مع قيمة افتراضية إن لم يوجد."""
        if index < len(self.args):
            return self.args[index]
        return default

    def int_arg(self, index: int, default: int = 0) -> int:
        """قراءة وسيط رقمي بموضعه (يُعيد الافتراضي إن كان غير رقمي)."""
        raw = self.arg(index)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    @property
    def is_current_version(self) -> bool:
        """هل هذا الزر من الإصدار الحالي لبنية الأزرار؟"""
        return self.version == CALLBACK_VERSION


def pack(namespace: str, action: str, *args: object) -> str:
    """
    بناء `callback_data` مُهيكلة والتحقق من صلاحيتها.

    المدخلات:
        namespace : مساحة الشاشة (حروف صغيرة بلا فواصل).
        action    : اسم الإجراء.
        args      : وسائط إضافية (أرقام أو كلمات قصيرة بلا الفاصل `:`).

    المخرجات: نص جاهز لوضعه في زر.

    الاستثناءات:
        CallbackError : وجود الفاصل داخل جزء، أو تجاوز حد 64 بايت.
    """
    parts = [namespace, action, *[str(arg) for arg in args]]
    for part in parts:
        if SEPARATOR in part:
            raise CallbackError(f"جزء زر يحتوي الفاصل الممنوع '{SEPARATOR}': {part!r}")
        if part == "":
            raise CallbackError("جزء زر فارغ غير مسموح")
    data = SEPARATOR.join([*parts, f"v{CALLBACK_VERSION}"])
    if len(data.encode("utf-8")) > MAX_CALLBACK_BYTES:
        raise CallbackError(f"طول callback_data تجاوز {MAX_CALLBACK_BYTES} بايت: {data!r}")
    return data


def unpack(data: str | None) -> Callback:
    """
    فكّ `callback_data` إلى أجزائها.

    المخرجات: كائن `Callback`؛ والإصدار يكون 0 إذا كان الزر قديماً بلا لاحقة إصدار.

    الاستثناءات:
        CallbackError : البيانات فارغة أو لا تحوي مساحة وإجراءً.
    """
    if not data:
        raise CallbackError("callback_data فارغة")
    parts = data.split(SEPARATOR)
    if len(parts) < 2:
        raise CallbackError(f"callback_data غير مُهيكلة: {data!r}")

    version = 0
    if parts[-1].startswith("v") and parts[-1][1:].isdigit():
        version = int(parts[-1][1:])
        parts = parts[:-1]

    namespace, action, *args = parts
    return Callback(namespace=namespace, action=action, args=tuple(args), version=version)


def pattern(namespace: str, action: str | None = None) -> str:
    """
    بناء تعبير نمطي لتسجيل المعالج على مساحة (أو مساحة+إجراء) بعينها.

    مثال: `pattern("cat")` ⇒ `^cat:` و`pattern("cat", "open")` ⇒ `^cat:open(:|$)`.
    """
    if action is None:
        return rf"^{namespace}{SEPARATOR}"
    return rf"^{namespace}{SEPARATOR}{action}({SEPARATOR}|$)"


# ----------------------- مساحات الأزرار المعتمدة ------------------------- #

NS_NAV = "nav"      # التنقل بين الشاشات الرئيسية
NS_CATALOG = "cat"  # التصنيفات والخدمات
NS_NEW = "new"      # بدء طلب جديد
NS_ORDERS = "ord"   # طلباتي
NS_WALLET = "wal"   # المحفظة
NS_DEPOSIT = "dep"  # شحن الرصيد
NS_SUPPORT = "sup"  # الدعم الفني
NS_ACCOUNT = "acc"  # الحساب والإشعارات
NS_FLOW = "flow"    # أزرار داخل المحادثات (تأكيد/إلغاء/تخطي/رجوع)
NS_SUB = "sub"      # بوابة الاشتراك الإجباري (زر «تحقق»)
NS_FAV = "fav"      # المفضلة (إضافة/إزالة/عرض)

# ----------------------- مساحات لوحة الأدمن ----------------------------- #
# مختصرة عمداً: حدّ تيليجرام 64 بايت، وبعض الأزرار تحمل معرفات طويلة.

NS_ADMIN = "adm"      # لوحة التحكم والصحة العامة
NS_ADM_USERS = "au"   # إدارة المستخدمين
NS_ADM_PAY = "ap"     # مراجعة طلبات الشحن
NS_ADM_ORD = "ao"     # إدارة الطلبات
NS_ADM_TKT = "at"     # تذاكر الدعم (جانب الأدمن)
NS_ADM_CAT = "ac"     # إدارة الكتالوج (تصنيفات/خدمات)
NS_ADM_SET = "as"     # الإعدادات
NS_ADM_LOG = "al"     # السجلات (تدقيق/أخطاء)
NS_ADM_PRV = "pv"     # المزودون وربط الـAPI (المرحلة 5)
NS_ADM_PMT = "pm"     # طرق الشحن وإدارتها (المرحلة 7)
NS_ADM_BRD = "bc"     # الرسائل الجماعية (المرحلة 8)
NS_ADM_TPL = "tp"     # قوالب الإشعارات (المرحلة 8)
NS_ADM_SEC = "sc"     # شاشة الأمان (المرحلة 9)
NS_ADM_BKP = "bk"     # النسخ الاحتياطي (المرحلة 10)
NS_ADM_STATS = "st"   # الإحصائيات والتصدير (المرحلة 10)
NS_ADM_CHN = "ch"     # القنوات: تشخيص وجهات النشر وقنوات الاشتراك (المرحلة 13)

#: كل المساحات المعروفة — تُستخدم في اختبار «لا أزرار بلا وظيفة»
ALL_NAMESPACES: tuple[str, ...] = (
    NS_NAV, NS_CATALOG, NS_NEW, NS_ORDERS, NS_WALLET, NS_DEPOSIT, NS_SUPPORT, NS_ACCOUNT, NS_FLOW,
    NS_ADMIN, NS_ADM_USERS, NS_ADM_PAY, NS_ADM_ORD, NS_ADM_TKT, NS_ADM_CAT, NS_ADM_SET, NS_ADM_LOG,
    NS_ADM_PRV, NS_ADM_PMT, NS_ADM_BRD, NS_ADM_TPL, NS_ADM_SEC, NS_ADM_BKP, NS_ADM_STATS,
    NS_SUB, NS_FAV, NS_ADM_CHN,
)
