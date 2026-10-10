"""
أزرار مشتركة بين كل الشاشات: رجوع، إلغاء، تأكيد، تخطي، وترقيم الصفحات.

قاعدة الواجهة المعتمدة (المرحلة 0 — البند 4.4):
    • كل شاشة فيها «🔙 رجوع» وكل محادثة فيها «❌ إلغاء».
    • الترقيم موحّد: ⬅️ السابق | 📄 2/5 | التالي ➡️
    • زر عدّاد الصفحات ليس زراً ميتاً: ضغطه يعرض موضعك الحالي كتنبيه.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from keyboards.callback_data import (
    NS_FLOW,
    NS_NAV,
    pack,
)
from texts import ar

# --------------------------- أزرار مفردة ------------------------------- #


def home_button() -> InlineKeyboardButton:
    """زر العودة إلى القائمة الرئيسية."""
    return InlineKeyboardButton(ar.BTN_HOME, callback_data=pack(NS_NAV, "home"))


def back_button(namespace: str, action: str, *args: object, label: str = ar.BTN_BACK) -> InlineKeyboardButton:
    """زر رجوع إلى شاشة محددة (يُمرَّر هدفه صراحة حتى لا يضيع المستخدم)."""
    return InlineKeyboardButton(label, callback_data=pack(namespace, action, *args))


def cancel_button(label: str = ar.BTN_CANCEL) -> InlineKeyboardButton:
    """زر إلغاء المحادثة الحالية (يعمل داخل كل ConversationHandler)."""
    return InlineKeyboardButton(label, callback_data=pack(NS_FLOW, "cancel"))


def confirm_button(label: str = ar.BTN_CONFIRM) -> InlineKeyboardButton:
    """زر تأكيد الخطوة الأخيرة في المحادثة."""
    return InlineKeyboardButton(label, callback_data=pack(NS_FLOW, "confirm"))


def skip_button(label: str = ar.BTN_SKIP) -> InlineKeyboardButton:
    """زر تخطي خطوة اختيارية داخل المحادثة."""
    return InlineKeyboardButton(label, callback_data=pack(NS_FLOW, "skip"))


# --------------------------- صفوف جاهزة -------------------------------- #


def cancel_markup() -> InlineKeyboardMarkup:
    """لوحة فيها زر إلغاء فقط (تُرفق بكل سؤال داخل المحادثات)."""
    return InlineKeyboardMarkup([[cancel_button()]])


def confirm_cancel_markup() -> InlineKeyboardMarkup:
    """لوحة تأكيد/إلغاء لخطوة المراجعة النهائية."""
    return InlineKeyboardMarkup([[confirm_button(), cancel_button()]])


def skip_cancel_markup() -> InlineKeyboardMarkup:
    """لوحة تخطي/إلغاء لخطوة اختيارية."""
    return InlineKeyboardMarkup([[skip_button(), cancel_button()]])


def pagination_row(
    namespace: str, action: str, *, page: int, total_pages: int, prefix_args: tuple[object, ...] = ()
) -> list[InlineKeyboardButton]:
    """
    بناء صف ترقيم موحّد لأي قائمة.

    المدخلات:
        namespace/action : وجهة أزرار التنقل.
        page/total_pages : الصفحة الحالية وعددها الكلي.
        prefix_args      : وسائط تسبق رقم الصفحة في الزر (مثل معرف التصنيف).

    المخرجات: صف أزرار (قد يكون فارغاً إذا كانت صفحة واحدة فقط).
    """
    if total_pages <= 1:
        return []
    row: list[InlineKeyboardButton] = []
    if page > 1:
        row.append(
            InlineKeyboardButton(ar.BTN_PREV, callback_data=pack(namespace, action, *prefix_args, page - 1))
        )
    row.append(
        InlineKeyboardButton(
            f"📄 {page}/{total_pages}", callback_data=pack(NS_NAV, "page", page, total_pages)
        )
    )
    if page < total_pages:
        row.append(
            InlineKeyboardButton(ar.BTN_NEXT, callback_data=pack(namespace, action, *prefix_args, page + 1))
        )
    return row


def back_home_row(namespace: str | None = None, action: str | None = None, *args: object) -> list[InlineKeyboardButton]:
    """
    صف سفلي موحّد: رجوع (إن وُجدت وجهة) + القائمة الرئيسية.

    يُستخدم في أسفل كل شاشة حتى لا يعلق المستخدم في أي مكان.
    """
    row: list[InlineKeyboardButton] = []
    if namespace and action:
        row.append(back_button(namespace, action, *args))
    row.append(home_button())
    return row
