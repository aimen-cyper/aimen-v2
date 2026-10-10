"""
لوحات أزرار لوحة التحكم.

قاعدتان ملزمتان في هذا الملف:

1. **لا يظهر زر لا يملك الأدمن صلاحيته.** كل باني لوحة يستقبل مجموعة صلاحيات
   المستخدم (`perms`) ويبني الأزرار على أساسها. هذا لا يُغني عن فحص الصلاحية
   داخل المعالج نفسه (الزر قد يُضغط من رسالة قديمة بعد سحب الصلاحية) — الفحصان
   مطلوبان معاً.
2. **لا زر بلا معالج.** كل `callback_data` هنا يقابله معالج مسجَّل في
   `handlers/registry.py`، ويتحقق من ذلك اختبار `test_no_dead_buttons`.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from core.enums import OrderStatus, PaymentStatus
from core.order_state import allowed_next, override_targets
from core.permissions import Permission
from database.models import (
    Broadcast,
    Order,
    Payment,
    PaymentMethod,
    Provider,
    Service,
    ServiceCategory,
    Setting,
    SupportTicket,
    User,
)
from integrations.providers.base import ProviderServiceItem
from keyboards.callback_data import (
    NS_ADM_BRD,
    NS_ADM_CAT,
    NS_ADM_CHN,
    NS_ADM_LOG,
    NS_ADM_ORD,
    NS_ADM_PAY,
    NS_ADM_PMT,
    NS_ADM_PRV,
    NS_ADM_BKP,
    NS_ADM_SEC,
    NS_ADM_STATS,
    NS_ADM_SET,
    NS_ADM_TKT,
    NS_ADM_TPL,
    NS_ADM_USERS,
    NS_ADMIN,
    NS_FLOW,
    pack,
)
from keyboards.common_kb import home_button, pagination_row
from texts import admin_ar as t
from utils.formatters import money_text, order_status_text, safe, ticket_status_text

#: تصفية قوائم الطلبات في لوحة الأدمن (الرمز ⇐ الاسم والحالات المشمولة)
ADMIN_ORDER_FILTERS: dict[str, tuple[str, tuple[str, ...]]] = {
    "att": (
        t.ORDER_FILTER_ATTENTION,
        (OrderStatus.SUBMIT_UNCERTAIN, OrderStatus.FAILED),
    ),
    "act": (
        t.ORDER_FILTER_ACTIVE,
        (
            OrderStatus.PENDING,
            OrderStatus.SUBMITTING,
            OrderStatus.SUBMITTED,
            OrderStatus.IN_PROGRESS,
        ),
    ),
    "all": (t.ORDER_FILTER_ALL, ()),
}

#: تصفية قوائم طلبات الشحن في لوحة الأدمن (الرمز ⇐ الاسم والحالات المشمولة)
ADMIN_PAYMENT_FILTERS: dict[str, tuple[str, tuple[str, ...]]] = {
    "pend": (t.PAYMENT_FILTER_PENDING, (PaymentStatus.PENDING,)),
    "ok": (t.PAYMENT_FILTER_APPROVED, (PaymentStatus.APPROVED,)),
    "no": (
        t.PAYMENT_FILTER_REJECTED,
        (PaymentStatus.REJECTED, PaymentStatus.CANCELLED, PaymentStatus.EXPIRED),
    ),
    "all": (t.PAYMENT_FILTER_ALL, ()),
}

#: تصفية قوائم التذاكر في لوحة الأدمن
ADMIN_TICKET_FILTERS: dict[str, str] = {
    "open": t.TICKET_FILTER_OPEN,
    "wait": t.TICKET_FILTER_WAITING,
    "mine": t.TICKET_FILTER_MINE,
    "high": t.TICKET_FILTER_HIGH,
    "closed": t.TICKET_FILTER_CLOSED,
}

#: وصف حالة الإذاعة كما يظهر في القوائم والبطاقات
BROADCAST_STATES: dict[str, str] = {
    "draft": t.BROADCAST_STATE_DRAFT,
    "running": t.BROADCAST_STATE_RUNNING,
    "paused": t.BROADCAST_STATE_PAUSED,
    "completed": t.BROADCAST_STATE_COMPLETED,
    "cancelled": t.BROADCAST_STATE_CANCELLED,
}

#: أزرار تغيير أولوية التذكرة (الرمز المخزَّن ⇐ التسمية المعروضة)
TICKET_PRIORITIES: dict[str, str] = {
    "low": t.TICKET_PRIORITY_LOW,
    "normal": t.TICKET_PRIORITY_NORMAL,
    "high": t.TICKET_PRIORITY_HIGH,
}


# ============================= أدوات داخلية ============================= #


def _panel_row(*, with_home: bool = True) -> list[InlineKeyboardButton]:
    """صف سفلي موحّد: رجوع إلى لوحة التحكم (+ القائمة الرئيسية للمستخدم)."""
    row = [InlineKeyboardButton(t.BTN_BACK_PANEL, callback_data=pack(NS_ADMIN, "home"))]
    if with_home:
        row.append(home_button())
    return row


def _back_row(namespace: str, action: str, *args: object) -> list[InlineKeyboardButton]:
    """صف رجوع إلى شاشة أدمن محددة + لوحة التحكم."""
    return [
        InlineKeyboardButton("🔙 رجوع", callback_data=pack(namespace, action, *args)),
        InlineKeyboardButton(t.BTN_BACK_PANEL, callback_data=pack(NS_ADMIN, "home")),
    ]


def _wrap_row(buttons: list[InlineKeyboardButton], per_row: int = 3) -> list[list[InlineKeyboardButton]]:
    """تقسيم صف طويل إلى صفوف لا تتجاوز `per_row` (قاعدة التخطيط: ≤ 3 أزرار بالصف)."""
    return [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]


def _cancel_row() -> list[InlineKeyboardButton]:
    """صف إلغاء داخل محادثات الأدمن."""
    return [InlineKeyboardButton("❌ إلغاء", callback_data=pack(NS_FLOW, "cancel"))]


def back_panel_kb() -> InlineKeyboardMarkup:
    """لوحة فيها الرجوع إلى لوحة التحكم فقط (تُرفق برسائل النتائج)."""
    return InlineKeyboardMarkup([_panel_row()])


def cancel_only_kb() -> InlineKeyboardMarkup:
    """لوحة فيها زر إلغاء فقط (تُرفق بأسئلة محادثات الأدمن)."""
    return InlineKeyboardMarkup([_cancel_row()])


def confirm_cancel_kb(label: str = t.BTN_CONFIRM_DANGER) -> InlineKeyboardMarkup:
    """لوحة تأكيد عملية خطيرة (تأكيد صريح + إلغاء)."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=pack(NS_FLOW, "confirm"))], _cancel_row()]
    )


def skip_cancel_kb() -> InlineKeyboardMarkup:
    """لوحة تخطي خطوة اختيارية داخل محادثات الأدمن."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⏭ تخطي", callback_data=pack(NS_FLOW, "skip"))], _cancel_row()]
    )


# ============================ القائمة الرئيسية ========================== #


def admin_menu_kb(perms: set[str], *, pending_payments: int = 0, open_tickets: int = 0) -> InlineKeyboardMarkup:
    """
    قائمة لوحة التحكم — تُبنى حسب صلاحيات هذا الأدمن تحديداً.

    المدخلات:
        perms            : مجموعة صلاحيات المستخدم الحالية.
        pending_payments : عدد طلبات الشحن المعلّقة (يظهر كعدّاد على الزر).
        open_tickets     : عدد التذاكر المفتوحة (عدّاد على الزر).
    """
    rows: list[list[InlineKeyboardButton]] = []
    current: list[InlineKeyboardButton] = []

    def add(button: InlineKeyboardButton) -> None:
        """إضافة زر مع ترتيب الأزرار في صفوف من اثنين."""
        current.append(button)
        if len(current) == 2:
            rows.append(list(current))
            current.clear()

    if Permission.USERS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_USERS, callback_data=pack(NS_ADM_USERS, "home")))
    if Permission.PAYMENTS_VIEW in perms:
        label = t.MENU_PAYMENTS + (f" ({pending_payments})" if pending_payments else "")
        add(InlineKeyboardButton(label, callback_data=pack(NS_ADM_PAY, "list", "pend", 1)))
    if Permission.ORDERS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_ORDERS, callback_data=pack(NS_ADM_ORD, "list", "att", 1)))
    if Permission.TICKETS_VIEW in perms:
        label = t.MENU_TICKETS + (f" ({open_tickets})" if open_tickets else "")
        add(InlineKeyboardButton(label, callback_data=pack(NS_ADM_TKT, "list", "open", 1)))
    if Permission.SERVICES_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_CATALOG, callback_data=pack(NS_ADM_CAT, "home")))
    if Permission.PROVIDERS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_PROVIDERS, callback_data=pack(NS_ADM_PRV, "home")))
    if Permission.SETTINGS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_SETTINGS, callback_data=pack(NS_ADM_SET, "home")))
    if Permission.LOGS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_LOGS, callback_data=pack(NS_ADM_LOG, "home")))
    if Permission.BROADCAST_SEND in perms:
        add(InlineKeyboardButton(t.MENU_BROADCAST, callback_data=pack(NS_ADM_BRD, "home")))
    if Permission.NOTIFICATIONS_TEMPLATES in perms:
        add(InlineKeyboardButton(t.MENU_TEMPLATES, callback_data=pack(NS_ADM_TPL, "home")))
    if Permission.SECURITY_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_SECURITY, callback_data=pack(NS_ADM_SEC, "home")))
    if Permission.SETTINGS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_CHANNELS, callback_data=pack(NS_ADM_CHN, "home")))
    if Permission.BACKUP_CREATE in perms:
        add(InlineKeyboardButton(t.MENU_BACKUP, callback_data=pack(NS_ADM_BKP, "home")))
    if Permission.STATS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_STATS, callback_data=pack(NS_ADM_STATS, "home", "today")))
    if Permission.STATS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_HEALTH, callback_data=pack(NS_ADMIN, "health")))

    if current:
        rows.append(list(current))

    rows.append(
        [
            InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADMIN, "home")),
            home_button(),
        ]
    )
    return InlineKeyboardMarkup(rows)


#: تسميات قصيرة لأزرار «تشغيل الآن» في شاشة المهام (الوصف الكامل في نص الشاشة)
JOB_SHORT_LABELS: dict[str, str] = {
    "notifications_dispatch": "الإشعارات",
    "broadcast_dispatch": "الإذاعة",
    "orders_submit": "إرسال الطلبات",
    "orders_check": "متابعة الطلبات",
    "payments_expire": "صلاحية الشحن",
    "tickets_auto_close": "إغلاق التذاكر",
    "orders_stuck_alert": "الطلبات المتوقفة",
    "providers_balance": "أرصدة المزودين",
    "providers_health": "صحة المزودين",
    "admin_daily_digest": "الملخص اليومي",
    "database_maintenance": "صيانة القاعدة",
    "backups_auto": "النسخ الاحتياطي",
}


def health_kb() -> InlineKeyboardMarkup:
    """أزرار شاشة صحة النظام (تحديث + دخول شاشة المهام الدورية)."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADMIN, "health"))],
            [InlineKeyboardButton(t.BTN_JOBS, callback_data=pack(NS_ADMIN, "jobs"))],
            _panel_row(),
        ]
    )


def jobs_home_kb(job_names: list[str], perms: set[str]) -> InlineKeyboardMarkup:
    """
    شاشة المهام الدورية: تحديث + «تشغيل الآن» لكل مهمة لمن يملك الصلاحية.

    التشغيل اليدوي مشروط بـ`settings.maintenance` لأنه تدخل تشغيلي في إيقاع
    النظام (قد يستدعي المزود أو يرسل إشعارات) لا مجرد قراءة.
    """
    rows = [[InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADMIN, "jobs"))]]
    if Permission.SETTINGS_MAINTENANCE in perms:
        rows += [
            [
                InlineKeyboardButton(
                    f"{t.BTN_JOB_RUN} · {JOB_SHORT_LABELS.get(name, name)}",
                    callback_data=pack(NS_ADMIN, "jobrun", name),
                )
            ]
            for name in job_names
        ]
    rows.append(_back_row(NS_ADMIN, "health"))
    return InlineKeyboardMarkup(rows)


# ============================= المستخدمون =============================== #


def users_home_kb(perms: set[str]) -> InlineKeyboardMarkup:
    """شاشة المستخدمين: بحث + رجوع."""
    rows = [[InlineKeyboardButton(t.BTN_USER_SEARCH, callback_data=pack(NS_ADM_USERS, "search"))]]
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def user_results_kb(users: list[User]) -> InlineKeyboardMarkup:
    """نتائج البحث: زر لكل مستخدم."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'🚫 ' if user.is_banned else ''}{user.display_name} · {user.telegram_id}",
                callback_data=pack(NS_ADM_USERS, "view", user.id),
            )
        ]
        for user in users
    ]
    rows.append(
        [InlineKeyboardButton(t.BTN_USER_SEARCH, callback_data=pack(NS_ADM_USERS, "search"))]
    )
    rows.append(_back_row(NS_ADM_USERS, "home"))
    return InlineKeyboardMarkup(rows)


def user_card_kb(user: User, perms: set[str]) -> InlineKeyboardMarkup:
    """أزرار بطاقة المستخدم حسب الصلاحيات المتاحة."""
    rows: list[list[InlineKeyboardButton]] = []

    money_row: list[InlineKeyboardButton] = []
    if Permission.USERS_BALANCE_CREDIT in perms:
        money_row.append(
            InlineKeyboardButton(
                t.BTN_USER_CREDIT, callback_data=pack(NS_ADM_USERS, "credit", user.id)
            )
        )
    if Permission.USERS_BALANCE_DEBIT in perms:
        money_row.append(
            InlineKeyboardButton(
                t.BTN_USER_DEBIT, callback_data=pack(NS_ADM_USERS, "debit", user.id)
            )
        )
    if money_row:
        rows.append(money_row)

    state_row: list[InlineKeyboardButton] = []
    if user.is_banned and Permission.USERS_UNBAN in perms:
        state_row.append(
            InlineKeyboardButton(
                t.BTN_USER_UNBAN, callback_data=pack(NS_ADM_USERS, "unban", user.id)
            )
        )
    elif not user.is_banned and Permission.USERS_BAN in perms:
        state_row.append(
            InlineKeyboardButton(t.BTN_USER_BAN, callback_data=pack(NS_ADM_USERS, "ban", user.id))
        )
    if Permission.USERS_NOTE in perms:
        state_row.append(
            InlineKeyboardButton(t.BTN_USER_NOTE, callback_data=pack(NS_ADM_USERS, "note", user.id))
        )
    if state_row:
        rows.append(state_row)

    if Permission.USERS_ROLE_CHANGE in perms:
        rows.append(
            [InlineKeyboardButton(t.BTN_USER_ROLE, callback_data=pack(NS_ADM_USERS, "role", user.id))]
        )

    history_row: list[InlineKeyboardButton] = []
    if Permission.ORDERS_VIEW in perms:
        history_row.append(
            InlineKeyboardButton(
                t.BTN_USER_ORDERS, callback_data=pack(NS_ADM_USERS, "orders", user.id, 1)
            )
        )
    history_row.append(
        InlineKeyboardButton(t.BTN_USER_TX, callback_data=pack(NS_ADM_USERS, "tx", user.id, 1))
    )
    rows.append(history_row)

    rows.append(_back_row(NS_ADM_USERS, "home"))
    return InlineKeyboardMarkup(rows)


def user_role_kb(user: User) -> InlineKeyboardMarkup:
    """أزرار اختيار الدور الجديد للمستخدم."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'• ' if user.role == code else ''}{label}",
                callback_data=pack(NS_ADM_USERS, "setrole", user.id, code),
            )
        ]
        for code, label in t.ASSIGNABLE_ROLES.items()
    ]
    rows.append(_back_row(NS_ADM_USERS, "view", user.id))
    return InlineKeyboardMarkup(rows)


def user_role_confirm_kb(user_id: int, role_code: str) -> InlineKeyboardMarkup:
    """تأكيد ثانٍ قبل تغيير الدور (إجراء خطير يغيّر الصلاحيات فوراً)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t.BTN_CONFIRM_DANGER,
                    callback_data=pack(NS_ADM_USERS, "roleok", user_id, role_code),
                )
            ],
            [InlineKeyboardButton("🔙 رجوع", callback_data=pack(NS_ADM_USERS, "role", user_id))],
        ]
    )


def user_list_nav_kb(
    action: str, user_id: int, *, page: int, total_pages: int
) -> InlineKeyboardMarkup:
    """ترقيم قوائم طلبات/معاملات مستخدم بعينه."""
    rows: list[list[InlineKeyboardButton]] = []
    nav = pagination_row(
        NS_ADM_USERS, action, page=page, total_pages=total_pages, prefix_args=(user_id,)
    )
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_USERS, "view", user_id))
    return InlineKeyboardMarkup(rows)


# ============================= المدفوعات ================================ #


def admin_payments_filters_row(current: str) -> list[InlineKeyboardButton]:
    """صف تصفية طلبات الشحن (المعلّق/المعتمد/المرفوض/الكل) مع تمييز الحالي."""
    return [
        InlineKeyboardButton(
            f"• {label} •" if code == current else label,
            callback_data=pack(NS_ADM_PAY, "list", code, 1),
        )
        for code, (label, _statuses) in ADMIN_PAYMENT_FILTERS.items()
    ]


def payments_list_kb(
    payments: list[Payment],
    *,
    page: int,
    total_pages: int,
    symbol: str,
    filter_code: str = "pend",
    perms: set[str] | None = None,
) -> InlineKeyboardMarkup:
    """
    قائمة طلبات الشحن: أزرار الطلبات + صف التصفية + البحث + طرق الشحن.

    المدخلات:
        filter_code : رمز التصفية الحالي (يُعاد في أزرار الصفحات والرجوع).
        perms       : صلاحيات الأدمن — زر «طرق الشحن» لا يظهر بدون صلاحيته.
    """
    permissions = perms or set()
    rows = [
        [
            InlineKeyboardButton(
                f"#{payment.id} · {money_text(payment.amount_units, symbol)}",
                callback_data=pack(NS_ADM_PAY, "view", payment.id, filter_code, page),
            )
        ]
        for payment in payments
    ]
    rows.extend(_wrap_row(admin_payments_filters_row(filter_code)))
    nav = pagination_row(
        NS_ADM_PAY, "list", page=page, total_pages=total_pages, prefix_args=(filter_code,)
    )
    if nav:
        rows.append(nav)

    tools = [InlineKeyboardButton(t.BTN_PAYMENT_SEARCH, callback_data=pack(NS_ADM_PAY, "find"))]
    if Permission.PAYMENTS_METHODS in permissions:
        tools.append(InlineKeyboardButton(t.BTN_METHODS, callback_data=pack(NS_ADM_PMT, "home")))
    rows.append(tools)
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def payments_search_kb(payments: list[Payment], *, symbol: str) -> InlineKeyboardMarkup:
    """نتائج البحث عن حوالة: زر لكل طلب مطابق + إعادة البحث."""
    rows = [
        [
            InlineKeyboardButton(
                f"#{payment.id} · {money_text(payment.amount_units, symbol)}",
                callback_data=pack(NS_ADM_PAY, "view", payment.id, "all", 1),
            )
        ]
        for payment in payments
    ]
    rows.append(
        [InlineKeyboardButton(t.BTN_PAYMENT_SEARCH, callback_data=pack(NS_ADM_PAY, "find"))]
    )
    rows.append(_back_row(NS_ADM_PAY, "list", "pend", 1))
    return InlineKeyboardMarkup(rows)


def payment_card_kb(
    payment: Payment,
    perms: set[str],
    *,
    is_pending: bool,
    filter_code: str = "pend",
    page: int = 1,
) -> InlineKeyboardMarkup:
    """أزرار بطاقة طلب الشحن (الاعتماد/الرفض تظهر للمعلّق فقط)."""
    rows: list[list[InlineKeyboardButton]] = []
    if payment.proof_file_id:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_PAYMENT_PROOF, callback_data=pack(NS_ADM_PAY, "proof", payment.id)
                )
            ]
        )
    if is_pending:
        action_row: list[InlineKeyboardButton] = []
        if Permission.PAYMENTS_APPROVE in perms:
            action_row.append(
                InlineKeyboardButton(
                    t.BTN_PAYMENT_APPROVE, callback_data=pack(NS_ADM_PAY, "ok", payment.id)
                )
            )
        if Permission.PAYMENTS_REJECT in perms:
            action_row.append(
                InlineKeyboardButton(
                    t.BTN_PAYMENT_REJECT, callback_data=pack(NS_ADM_PAY, "no", payment.id)
                )
            )
        if action_row:
            rows.append(action_row)
    if Permission.USERS_VIEW in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    "👤 صاحب الطلب", callback_data=pack(NS_ADM_USERS, "view", payment.user_id)
                )
            ]
        )
    rows.append(_back_row(NS_ADM_PAY, "list", filter_code, page))
    return InlineKeyboardMarkup(rows)


def payment_approve_kb() -> InlineKeyboardMarkup:
    """تأكيد الاعتماد مع إمكانية تعديل المبلغ المضاف."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_CONFIRM_DANGER, callback_data=pack(NS_FLOW, "confirm"))],
            [InlineKeyboardButton(t.BTN_EDIT_AMOUNT, callback_data=pack(NS_ADM_PAY, "amount"))],
            _cancel_row(),
        ]
    )


# ============================= طرق الشحن ================================ #


def payment_methods_kb(methods: list[PaymentMethod], perms: set[str]) -> InlineKeyboardMarkup:
    """
    قائمة طرق الشحن في اللوحة: زر لكل طريقة + الإضافة + التقرير.

    أزرار الإضافة لا تظهر إلا لمن يملك `payments.methods`، لأن طريقة الشحن
    تحدد إلى أين تذهب أموال العملاء فعلياً.
    """
    rows = [
        [
            InlineKeyboardButton(
                f"{t.METHOD_STATE_ON if method.is_active else t.METHOD_STATE_OFF} {method.name_ar}",
                callback_data=pack(NS_ADM_PMT, "view", method.id),
            )
        ]
        for method in methods
    ]
    actions: list[InlineKeyboardButton] = []
    if Permission.PAYMENTS_METHODS in perms:
        actions.append(
            InlineKeyboardButton(t.BTN_METHOD_NEW, callback_data=pack(NS_ADM_PMT, "new"))
        )
    actions.append(
        InlineKeyboardButton(t.BTN_METHODS_REPORT, callback_data=pack(NS_ADM_PMT, "rep"))
    )
    rows.append(actions)
    rows.append(_back_row(NS_ADM_PAY, "list", "pend", 1))
    return InlineKeyboardMarkup(rows)


def method_card_kb(method: PaymentMethod, perms: set[str]) -> InlineKeyboardMarkup:
    """
    أزرار بطاقة طريقة الشحن: تعديل الحقول، الرسوم، الحدود، الإثبات، الترتيب، التفعيل.

    كل زر هنا يقابله معالج يفحص `payments.methods` من جديد على الـcallback نفسه.
    """
    rows: list[list[InlineKeyboardButton]] = []
    if Permission.PAYMENTS_METHODS in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_EDIT_NAME,
                    callback_data=pack(NS_ADM_PMT, "edit", method.id, "name"),
                ),
                InlineKeyboardButton(
                    t.BTN_METHOD_EDIT_INSTRUCTIONS,
                    callback_data=pack(NS_ADM_PMT, "edit", method.id, "inst"),
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_EDIT_ACCOUNT,
                    callback_data=pack(NS_ADM_PMT, "edit", method.id, "acct"),
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_EDIT_MIN,
                    callback_data=pack(NS_ADM_PMT, "edit", method.id, "min"),
                ),
                InlineKeyboardButton(
                    t.BTN_METHOD_EDIT_MAX,
                    callback_data=pack(NS_ADM_PMT, "edit", method.id, "max"),
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_EDIT_FEEP,
                    callback_data=pack(NS_ADM_PMT, "edit", method.id, "feep"),
                ),
                InlineKeyboardButton(
                    t.BTN_METHOD_EDIT_FEEF,
                    callback_data=pack(NS_ADM_PMT, "edit", method.id, "feef"),
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_PROOF_ON if method.requires_proof else t.BTN_METHOD_PROOF_OFF,
                    callback_data=pack(NS_ADM_PMT, "proof", method.id),
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_UP, callback_data=pack(NS_ADM_PMT, "up", method.id)
                ),
                InlineKeyboardButton(
                    t.BTN_METHOD_DOWN, callback_data=pack(NS_ADM_PMT, "down", method.id)
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_OFF if method.is_active else t.BTN_METHOD_ON,
                    callback_data=pack(NS_ADM_PMT, "toggle", method.id),
                )
            ]
        )
    rows.append(_back_row(NS_ADM_PMT, "home"))
    return InlineKeyboardMarkup(rows)


def method_type_kb() -> InlineKeyboardMarkup:
    """اختيار نوع طريقة الشحن أثناء إنشائها (يطابق أنواع المخطط الثلاثة)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_TYPE_MANUAL, callback_data=pack(NS_ADM_PMT, "type", "manual")
                )
            ],
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_TYPE_CRYPTO, callback_data=pack(NS_ADM_PMT, "type", "crypto")
                )
            ],
            [
                InlineKeyboardButton(
                    t.BTN_METHOD_TYPE_GATEWAY, callback_data=pack(NS_ADM_PMT, "type", "gateway")
                )
            ],
            _cancel_row(),
        ]
    )


def methods_report_kb() -> InlineKeyboardMarkup:
    """أزرار شاشة تقرير طرق الشحن."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADM_PMT, "rep"))],
            _back_row(NS_ADM_PMT, "home"),
        ]
    )


# ============================== الطلبات ================================= #


def admin_orders_filters_row(current: str) -> list[InlineKeyboardButton]:
    """صف تصفية قوائم الطلبات."""
    return [
        InlineKeyboardButton(
            f"{'• ' if code == current else ''}{label}",
            callback_data=pack(NS_ADM_ORD, "list", code, 1),
        )
        for code, (label, _statuses) in ADMIN_ORDER_FILTERS.items()
    ]


def admin_orders_kb(
    orders: list[Order], *, filter_code: str, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """قائمة الطلبات في لوحة الأدمن."""
    rows = [
        [
            InlineKeyboardButton(
                f"{order_status_text(order.status).split(' ', 1)[0]} "
                f"{order.public_code or order.id} · {money_text(order.cost_units, symbol)}",
                callback_data=pack(NS_ADM_ORD, "view", order.id, filter_code, page),
            )
        ]
        for order in orders
    ]
    rows.extend(_wrap_row(admin_orders_filters_row(filter_code)))
    nav = pagination_row(
        NS_ADM_ORD, "list", page=page, total_pages=total_pages, prefix_args=(filter_code,)
    )
    if nav:
        rows.append(nav)
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def admin_order_card_kb(
    order: Order, perms: set[str], *, filter_code: str, page: int
) -> InlineKeyboardMarkup:
    """أزرار بطاقة الطلب الإدارية (كل زر مشروط بصلاحيته وبحالة الطلب)."""
    rows: list[list[InlineKeyboardButton]] = []
    is_final = not allowed_next(order.status)

    first_row: list[InlineKeyboardButton] = []
    if Permission.ORDERS_RECHECK in perms and order.provider_order_id and not is_final:
        first_row.append(
            InlineKeyboardButton(
                t.BTN_ORDER_RECHECK, callback_data=pack(NS_ADM_ORD, "recheck", order.id)
            )
        )
    if Permission.ORDERS_LINK_PROVIDER_ID in perms and order.status == OrderStatus.SUBMIT_UNCERTAIN:
        first_row.append(
            InlineKeyboardButton(
                t.BTN_ORDER_LINK, callback_data=pack(NS_ADM_ORD, "link", order.id)
            )
        )
    if first_row:
        rows.append(first_row)

    danger_row: list[InlineKeyboardButton] = []
    if Permission.ORDERS_CANCEL in perms and not is_final:
        danger_row.append(
            InlineKeyboardButton(
                t.BTN_ORDER_CANCEL, callback_data=pack(NS_ADM_ORD, "cancel", order.id)
            )
        )
    if Permission.ORDERS_REFUND in perms and not is_final:
        danger_row.append(
            InlineKeyboardButton(t.BTN_ORDER_FAIL, callback_data=pack(NS_ADM_ORD, "fail", order.id))
        )
    if danger_row:
        rows.append(danger_row)

    if Permission.ORDERS_STATUS_OVERRIDE in perms and order.status in (OrderStatus.SUBMITTED, OrderStatus.IN_PROGRESS):
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_ORDER_FORCE_REFUND, callback_data=pack(NS_ADM_ORD, "frefund", order.id)
                )
            ]
        )

    if Permission.ORDERS_STATUS_OVERRIDE in perms and override_targets(order.status, has_provider_id=bool(order.provider_order_id)):
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_ORDER_OVERRIDE, callback_data=pack(NS_ADM_ORD, "force", order.id)
                )
            ]
        )

    if Permission.USERS_VIEW in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_ORDER_USER, callback_data=pack(NS_ADM_USERS, "view", order.user_id)
                )
            ]
        )

    rows.append(_back_row(NS_ADM_ORD, "list", filter_code, page))
    return InlineKeyboardMarkup(rows)


def order_override_kb(order: Order) -> InlineKeyboardMarkup:
    """أزرار الحالات المسموح الانتقال إليها من الحالة الحالية فقط."""
    rows = [
        [
            InlineKeyboardButton(
                order_status_text(status),
                callback_data=pack(NS_ADM_ORD, "setst", order.id, status),
            )
        ]
        for status in override_targets(order.status, has_provider_id=bool(order.provider_order_id))
    ]
    rows.append(_back_row(NS_ADM_ORD, "view", order.id, "all", 1))
    return InlineKeyboardMarkup(rows)


# =============================== الدعم ================================== #


def admin_tickets_filters_row(current: str) -> list[InlineKeyboardButton]:
    """صف تصفية قوائم التذاكر."""
    return [
        InlineKeyboardButton(
            f"{'• ' if code == current else ''}{label}",
            callback_data=pack(NS_ADM_TKT, "list", code, 1),
        )
        for code, label in ADMIN_TICKET_FILTERS.items()
    ]


def admin_tickets_kb(
    tickets: list[SupportTicket], *, filter_code: str, page: int, total_pages: int
) -> InlineKeyboardMarkup:
    """قائمة التذاكر في لوحة الأدمن."""
    rows = [
        [
            InlineKeyboardButton(
                f"{ticket_status_text(ticket.status).split(' ', 1)[0]} #{ticket.id} · "
                f"{safe(ticket.subject, limit=28)}",
                callback_data=pack(NS_ADM_TKT, "view", ticket.id),
            )
        ]
        for ticket in tickets
    ]
    rows.extend(_wrap_row(admin_tickets_filters_row(filter_code)))
    nav = pagination_row(
        NS_ADM_TKT, "list", page=page, total_pages=total_pages, prefix_args=(filter_code,)
    )
    if nav:
        rows.append(nav)
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def admin_ticket_card_kb(
    ticket: SupportTicket, perms: set[str], *, filter_code: str = "open"
) -> InlineKeyboardMarkup:
    """أزرار بطاقة التذكرة الإدارية."""
    rows: list[list[InlineKeyboardButton]] = []
    action_row: list[InlineKeyboardButton] = []
    if ticket.is_open and Permission.TICKETS_REPLY in perms:
        action_row.append(
            InlineKeyboardButton(
                t.BTN_TICKET_REPLY, callback_data=pack(NS_ADM_TKT, "reply", ticket.id)
            )
        )
    if ticket.is_open and Permission.TICKETS_CLOSE in perms:
        action_row.append(
            InlineKeyboardButton(
                t.BTN_TICKET_CLOSE, callback_data=pack(NS_ADM_TKT, "close", ticket.id)
            )
        )
    if action_row:
        rows.append(action_row)

    if ticket.is_open and Permission.TICKETS_ASSIGN in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_TICKET_ASSIGN, callback_data=pack(NS_ADM_TKT, "assign", ticket.id)
                )
            ]
        )
    # تغيير الأولوية يتبع صلاحية الإسناد (نفس صلاحية `TicketService.set_priority`)
    if ticket.is_open and Permission.TICKETS_ASSIGN in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    f"{'• ' if ticket.priority == code else ''}{label}",
                    callback_data=pack(NS_ADM_TKT, "prio", ticket.id, code),
                )
                for code, label in TICKET_PRIORITIES.items()
            ]
        )
    if Permission.USERS_VIEW in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_TICKET_USER, callback_data=pack(NS_ADM_USERS, "view", ticket.user_id)
                )
            ]
        )
    rows.append(_back_row(NS_ADM_TKT, "list", filter_code, 1))
    return InlineKeyboardMarkup(rows)


# ============================== الكتالوج ================================ #


def catalog_home_kb(categories: list[ServiceCategory], perms: set[str]) -> InlineKeyboardMarkup:
    """شاشة الكتالوج: التصنيفات + إضافة تصنيف."""
    buttons = [
        InlineKeyboardButton(category.title, callback_data=pack(NS_ADM_CAT, "cat", category.id, 1))
        for category in categories
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]       # زوجان بالصف: 8 تصنيفات لا 8 صفوف
    if Permission.SERVICES_CREATE in perms:
        rows.append(
            [
                InlineKeyboardButton(t.BTN_SERVICE_NEW, callback_data=pack(NS_ADM_CAT, "newsvc")),
                InlineKeyboardButton(t.BTN_CATEGORY_NEW, callback_data=pack(NS_ADM_CAT, "newcat")),
            ]
        )
    rows.append([InlineKeyboardButton(t.BTN_CATALOG_SEARCH, callback_data=pack(NS_ADM_CAT, "find"))])
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def catalog_search_results_kb(
    services: list[Service], *, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """نتائج بحث الأدمن: زر لكل خدمة (يفتح بطاقتها) + ترقيم + «بحث جديد» + رجوع للكتالوج."""
    rows = []
    for service in services:
        icon = "🗄" if service.is_archived else ("🟢" if service.is_active else "⚪️")
        rows.append(
            [
                InlineKeyboardButton(
                    f"{icon} #{service.id} ·{safe(service.provider_service_id, limit=10)}· "
                    f"{safe(service.name, limit=22)} · {money_text(service.price_per_1000_units, symbol)}",
                    callback_data=pack(NS_ADM_CAT, "svc", service.id),
                )
            ]
        )
    nav = pagination_row(NS_ADM_CAT, "found", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(t.BTN_CATALOG_SEARCH_AGAIN, callback_data=pack(NS_ADM_CAT, "find"))])
    rows.append(_back_row(NS_ADM_CAT, "home"))
    return InlineKeyboardMarkup(rows)


def catalog_services_kb(
    services: list[Service], *, category_id: int, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """قائمة خدمات تصنيف في لوحة الأدمن (مع مؤشر التفعيل)."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'🟢' if service.is_active else '⚪️'} #{service.id} {safe(service.name, limit=24)} · "
                f"{money_text(service.price_per_1000_units, symbol)}",
                callback_data=pack(NS_ADM_CAT, "svc", service.id),
            )
        ]
        for service in services
    ]
    nav = pagination_row(
        NS_ADM_CAT, "cat", page=page, total_pages=total_pages, prefix_args=(category_id,)
    )
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_CAT, "home"))
    return InlineKeyboardMarkup(rows)


def service_card_kb(service: Service, perms: set[str]) -> InlineKeyboardMarkup:
    """أزرار بطاقة الخدمة الإدارية."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    if Permission.SERVICES_UPDATE in perms and not service.is_archived:
        label = t.BTN_SERVICE_TOGGLE_OFF if service.is_active else t.BTN_SERVICE_TOGGLE_ON
        row.append(InlineKeyboardButton(label, callback_data=pack(NS_ADM_CAT, "toggle", service.id)))
    if Permission.SERVICES_PRICE in perms and not service.is_archived:
        row.append(
            InlineKeyboardButton(
                t.BTN_SERVICE_PRICE, callback_data=pack(NS_ADM_CAT, "price", service.id)
            )
        )
    if row:
        rows.append(row)
    if Permission.SERVICES_UPDATE in perms and not service.is_archived:
        rows.append(
            [InlineKeyboardButton(t.BTN_SERVICE_EDIT, callback_data=pack(NS_ADM_CAT, "edit", service.id))]
        )
    if Permission.SERVICES_ARCHIVE in perms and not service.is_archived:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_SERVICE_ARCHIVE, callback_data=pack(NS_ADM_CAT, "archive", service.id)
                )
            ]
        )
    rows.append(_back_row(NS_ADM_CAT, "cat", service.category_id, 1))
    return InlineKeyboardMarkup(rows)


def service_edit_fields_kb() -> InlineKeyboardMarkup:
    """اختيار حقل العرض المراد تعديله (داخل محادثة التعديل)."""
    rows = [
        [InlineKeyboardButton("🚀 السرعة", callback_data=pack(NS_ADM_CAT, "fld", "speed")),
         InlineKeyboardButton("💎 الجودة", callback_data=pack(NS_ADM_CAT, "fld", "quality"))],
        [InlineKeyboardButton("🛡 الضمان", callback_data=pack(NS_ADM_CAT, "fld", "guarantee")),
         InlineKeyboardButton("🔗 قاعدة الرابط", callback_data=pack(NS_ADM_CAT, "fld", "rule"))],
        _cancel_row(),
    ]
    return InlineKeyboardMarkup(rows)


def service_rule_picker_kb(rules: list, *, current: str | None) -> InlineKeyboardMarkup:
    """
    اختيار قاعدة الرابط: «بلا قيد» ثم كل القواعد (✔️ على الحالية).

    الزر يحمل ترتيب القاعدة (يبدأ من 1؛ 0 = بلا قيد) لا مفتاحها النصي، ويبقى callback_data قصيراً.
    """
    rows = [[InlineKeyboardButton(("✔️ " if not current else "") + t.BTN_RULE_NONE, callback_data=pack(NS_ADM_CAT, "rul", 0))]]
    for position, rule in enumerate(rules, start=1):
        mark = "✔️ " if rule.key == current else ""
        rows.append(
            [InlineKeyboardButton(f"{mark}{rule.label}", callback_data=pack(NS_ADM_CAT, "rul", position))]
        )
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


# ============================= الإعدادات ================================ #


def settings_home_kb(
    groups: list[str], perms: set[str], *, maintenance_on: bool
) -> InlineKeyboardMarkup:
    """مجموعات الإعدادات + مفتاح وضع الصيانة."""
    buttons = [
        InlineKeyboardButton(t.setting_group_label(group), callback_data=pack(NS_ADM_SET, "group", group, 1))
        for group in groups
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    if Permission.SETTINGS_MAINTENANCE in perms:
        label = t.BTN_MAINTENANCE_OFF if maintenance_on else t.BTN_MAINTENANCE_ON
        rows.append([InlineKeyboardButton(label, callback_data=pack(NS_ADM_SET, "maint"))])
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def settings_group_kb(
    settings: list[Setting], *, group: str, page: int, total_pages: int, perms: set[str]
) -> InlineKeyboardMarkup:
    """مفاتيح مجموعة إعدادات (القابل للتعديل فقط يصبح زراً)."""
    rows: list[list[InlineKeyboardButton]] = []
    if Permission.SETTINGS_UPDATE in perms:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        f"✏️ {safe(setting.name_ar or setting.key, limit=32)}",
                        callback_data=pack(NS_ADM_SET, "edit", setting.key),
                    )
                ]
                for setting in settings
                if setting.is_editable
            ]
        )
    nav = pagination_row(
        NS_ADM_SET, "group", page=page, total_pages=total_pages, prefix_args=(group,)
    )
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_SET, "home"))
    return InlineKeyboardMarkup(rows)


# ============================== السجلات ================================= #


def logs_home_kb() -> InlineKeyboardMarkup:
    """اختيار نوع السجل."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_LOG_AUDIT, callback_data=pack(NS_ADM_LOG, "audit", 1))],
            [InlineKeyboardButton(t.BTN_LOG_ERRORS, callback_data=pack(NS_ADM_LOG, "errors", 1))],
            [InlineKeyboardButton(t.BTN_LOG_PROVIDER_CALLS, callback_data=pack(NS_ADM_LOG, "prq", 1))],
            _panel_row(),
        ]
    )


def logs_page_kb(action: str, *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """ترقيم صفحات السجلات."""
    rows: list[list[InlineKeyboardButton]] = []
    nav = pagination_row(NS_ADM_LOG, action, page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_LOG, "home"))
    return InlineKeyboardMarkup(rows)


def _id_buttons(ids: list[int], namespace: str, action: str, *tail: object) -> list[list[InlineKeyboardButton]]:
    """أزرار «#المعرّف» لفتح تفاصيل عناصر الصفحة (4 في الصف)."""
    buttons = [
        InlineKeyboardButton(f"#{item_id}", callback_data=pack(namespace, action, item_id, *tail))
        for item_id in ids
    ]
    return [buttons[i : i + 4] for i in range(0, len(buttons), 4)]


def logs_audit_kb(ids: list[int], *, category: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """سجل التدقيق: أزرار تفاصيل + ترقيم ضمن الفئة + زر الفلتر."""
    rows = _id_buttons(ids, NS_ADM_LOG, "aud", category, page)
    nav = pagination_row(NS_ADM_LOG, "acat", page=page, total_pages=total_pages, prefix_args=(category,))
    if nav:
        rows.append(nav)
    label = t.AUDIT_CATEGORY_LABELS.get(category, category)
    rows.append([InlineKeyboardButton(t.BTN_LOG_FILTER.format(label=label), callback_data=pack(NS_ADM_LOG, "afl", category))])
    rows.append(_back_row(NS_ADM_LOG, "home"))
    return InlineKeyboardMarkup(rows)


def logs_audit_filter_kb(current: str) -> InlineKeyboardMarkup:
    """قائمة اختيار فئة سجل التدقيق (الفئة الحالية بعلامة ✔)."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'✔ ' if key == current else ''}{label}", callback_data=pack(NS_ADM_LOG, "acat", key, 1)
            )
        ]
        for key, label in t.AUDIT_CATEGORY_LABELS.items()
    ]
    rows.append(_back_row(NS_ADM_LOG, "acat", current, 1))
    return InlineKeyboardMarkup(rows)


def logs_audit_detail_kb(category: str, page: int) -> InlineKeyboardMarkup:
    """تفاصيل سجل تدقيق: رجوع لنفس الصفحة والفئة."""
    return InlineKeyboardMarkup([_back_row(NS_ADM_LOG, "acat", category, page)])


def logs_errors_kb(ids: list[int], *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """سجل الأخطاء: أزرار تفاصيل + ترقيم."""
    rows = _id_buttons(ids, NS_ADM_LOG, "err", page)
    nav = pagination_row(NS_ADM_LOG, "errors", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_LOG, "home"))
    return InlineKeyboardMarkup(rows)


def logs_error_detail_kb(page: int) -> InlineKeyboardMarkup:
    """تفاصيل خطأ: رجوع لنفس الصفحة."""
    return InlineKeyboardMarkup([_back_row(NS_ADM_LOG, "errors", page)])


def logs_calls_kb(ids: list[int], *, failed_only: bool, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """سجل استدعاءات المزودين: تفاصيل + ترقيم + تبديل «الفاشلة فقط/الكل»."""
    mode = "f" if failed_only else "a"
    list_action = "prqf" if failed_only else "prq"
    rows = _id_buttons(ids, NS_ADM_LOG, "prqd", mode, page)
    nav = pagination_row(NS_ADM_LOG, list_action, page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    toggle = (
        InlineKeyboardButton(t.BTN_LOG_ALL_CALLS, callback_data=pack(NS_ADM_LOG, "prq", 1))
        if failed_only
        else InlineKeyboardButton(t.BTN_LOG_FAILED_ONLY, callback_data=pack(NS_ADM_LOG, "prqf", 1))
    )
    rows.append([toggle])
    rows.append(_back_row(NS_ADM_LOG, "home"))
    return InlineKeyboardMarkup(rows)


def logs_call_detail_kb(mode: str, page: int) -> InlineKeyboardMarkup:
    """تفاصيل استدعاء مزود: رجوع لنفس القائمة والصفحة."""
    return InlineKeyboardMarkup([_back_row(NS_ADM_LOG, "prqf" if mode == "f" else "prq", page)])


# ============================== المزودون ================================ #


def providers_home_kb(providers: list[Provider], perms: set[str]) -> InlineKeyboardMarkup:
    """
    قائمة المزودين.

    كل زر يحمل مؤشر حالة (🟢 مفعّل · ⚪️ متوقف) وتلميح المفتاح لا المفتاح نفسه.
    """
    rows = [
        [
            InlineKeyboardButton(
                f"{'🟢' if provider.is_active else '⚪️'} {safe(provider.name, limit=28)}",
                callback_data=pack(NS_ADM_PRV, "view", provider.id),
            )
        ]
        for provider in providers
    ]
    if Permission.PROVIDERS_CREATE in perms:
        rows.append(
            [InlineKeyboardButton(t.BTN_PROVIDER_NEW, callback_data=pack(NS_ADM_PRV, "new"))]
        )
    rows.append([InlineKeyboardButton(t.BTN_PROVIDER_MAP, callback_data=pack(NS_ADM_PRV, "map"))])
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def provider_map_kb() -> InlineKeyboardMarkup:
    """لوحة «خريطة المزودين»: تحديث + رجوع إلى المزودين."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔄 تحديث", callback_data=pack(NS_ADM_PRV, "map"))], _back_row(NS_ADM_PRV, "home")]
    )


def provider_card_kb(provider: Provider, perms: set[str]) -> InlineKeyboardMarkup:
    """أزرار بطاقة المزود — كل زر مشروط بصلاحيته."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    if Permission.PROVIDERS_TEST in perms:
        row.append(
            InlineKeyboardButton(
                t.BTN_PROVIDER_TEST, callback_data=pack(NS_ADM_PRV, "test", provider.id)
            )
        )
        row.append(
            InlineKeyboardButton(
                t.BTN_PROVIDER_BALANCE, callback_data=pack(NS_ADM_PRV, "bal", provider.id)
            )
        )
    if row:
        rows.append(row)
        row = []

    if Permission.SERVICES_SYNC in perms:
        row.append(
            InlineKeyboardButton(
                t.BTN_PROVIDER_SYNC, callback_data=pack(NS_ADM_PRV, "sync", provider.id)
            )
        )
    if Permission.SERVICES_CREATE in perms:
        row.append(
            InlineKeyboardButton(
                t.BTN_PROVIDER_IMPORT, callback_data=pack(NS_ADM_PRV, "imp", provider.id)
            )
        )
    if row:
        rows.append(row)
        row = []

    if Permission.PROVIDERS_UPDATE in perms:
        label = t.BTN_PROVIDER_OFF if provider.is_active else t.BTN_PROVIDER_ON
        row.append(
            InlineKeyboardButton(label, callback_data=pack(NS_ADM_PRV, "toggle", provider.id))
        )
    if Permission.PROVIDERS_KEY_UPDATE in perms:
        row.append(
            InlineKeyboardButton(
                t.BTN_PROVIDER_KEY, callback_data=pack(NS_ADM_PRV, "key", provider.id)
            )
        )
    if row:
        rows.append(row)

    if Permission.PROVIDERS_UPDATE in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_PROVIDER_RATE, callback_data=pack(NS_ADM_PRV, "cur", provider.id)
                )
            ]
        )

    if Permission.SERVICES_VIEW in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_PROVIDER_SERVICES, callback_data=pack(NS_ADM_PRV, "svcs", provider.id, 1)
                )
            ]
        )
    rows.append(_back_row(NS_ADM_PRV, "home"))
    return InlineKeyboardMarkup(rows)


def provider_type_kb() -> InlineKeyboardMarkup:
    """اختيار نوع واجهة المزود عند إضافته (من الأنواع المدعومة فعلياً فقط)."""
    from integrations.providers.registry import available_types

    rows = [
        [
            InlineKeyboardButton(
                t.PROVIDER_TYPE_LABELS.get(api_type, api_type),
                callback_data=pack(NS_ADM_PRV, "type", api_type),
            )
        ]
        for api_type in available_types()
    ]
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


def provider_services_kb(
    services: list[Service], *, provider_id: int, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """قائمة خدماتنا المرتبطة بمزود (تفتح بطاقة الخدمة في قسم الكتالوج)."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'🟢' if service.is_active else '⚪️'} {safe(service.name, limit=24)} · "
                f"{money_text(service.price_per_1000_units, symbol)}",
                callback_data=pack(NS_ADM_CAT, "svc", service.id),
            )
        ]
        for service in services
    ]
    nav = pagination_row(
        NS_ADM_PRV, "svcs", page=page, total_pages=total_pages, prefix_args=(provider_id,)
    )
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_PRV, "view", provider_id))
    return InlineKeyboardMarkup(rows)


def provider_import_results_kb(
    entries: list[tuple[int, ProviderServiceItem]],
    *,
    provider_id: int,
    symbol: str,
    selected: set[int],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    """
    نتائج البحث في قائمة خدمات المزود مع **تحديد متعدد**.

    `entries` = (الفهرس الكلي في النتائج المحفوظة، العنصر) لصفحة واحدة. الزر يحمل الفهرس لا رقم
    الخدمة لأن أرقام بعض المزودين طويلة وقد تتجاوز حد 64 بايت. ☑️ = محدد، ⬜ = غير محدد.
    صف التحكم: تحديد كل النتائج / مسح التحديد، ثم «التالي» (مع عدد المحدد) والرجوع.
    """
    rows = [
        [
            InlineKeyboardButton(
                f"{'☑️' if index in selected else '⬜'} #{safe(item.provider_service_id, limit=12)} · "
                f"{safe(item.name, limit=26)} · {money_text(item.rate_per_1000_units, symbol)}",
                callback_data=pack(NS_ADM_PRV, "pick", index),
            )
        ]
        for index, item in entries
    ]
    nav = pagination_row(NS_ADM_PRV, "pg", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(t.BTN_IMPORT_SELECT_ALL, callback_data=pack(NS_ADM_PRV, "all")),
            InlineKeyboardButton(t.BTN_IMPORT_SELECT_NONE, callback_data=pack(NS_ADM_PRV, "none")),
        ]
    )
    rows.append(
        [InlineKeyboardButton(t.BTN_IMPORT_NEXT.format(count=len(selected)), callback_data=pack(NS_ADM_PRV, "go"))]
    )
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


def category_picker_kb(
    categories: list[ServiceCategory], namespace: str, action: str
) -> InlineKeyboardMarkup:
    """اختيار تصنيف داخل محادثة (يُستخدم في الاستيراد وفي إنشاء خدمة يدوياً)."""
    rows = [
        [InlineKeyboardButton(category.title, callback_data=pack(namespace, action, category.id))]
        for category in categories
    ]
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


def provider_picker_kb(
    providers: list[Provider], namespace: str, action: str
) -> InlineKeyboardMarkup:
    """اختيار مزود داخل محادثة إنشاء خدمة."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'🟢' if provider.is_active else '⚪️'} {safe(provider.name, limit=28)}",
                callback_data=pack(namespace, action, provider.id),
            )
        ]
        for provider in providers
    ]
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


# ====================== المرحلة 8: الإذاعة والقوالب ===================== #


def broadcast_home_kb(broadcasts: list[Broadcast], perms: set[str]) -> InlineKeyboardMarkup:
    """
    شاشة الرسائل الجماعية: آخر الرسائل + زر إنشاء رسالة جديدة.

    زر الإنشاء يظهر فقط لمن يملك `broadcast.send` — والمعالج يفحصه مجدداً.
    """
    rows = [
        [
            InlineKeyboardButton(
                f"#{item.id} · {BROADCAST_STATES.get(item.status, item.status)} "
                f"· {item.sent_count}/{item.total_count}",
                callback_data=pack(NS_ADM_BRD, "view", item.id),
            )
        ]
        for item in broadcasts
    ]
    if Permission.BROADCAST_SEND in perms:
        rows.append(
            [InlineKeyboardButton(t.BTN_BROADCAST_NEW, callback_data=pack(NS_ADM_BRD, "new"))]
        )
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def broadcast_target_kb(rows_data: list[tuple[str, str, int]]) -> InlineKeyboardMarkup:
    """أزرار اختيار شريحة الاستهداف، وكل زر يحمل عدد مستلميها الحقيقي الآن."""
    rows = [
        [
            InlineKeyboardButton(
                f"{label} ({count})", callback_data=pack(NS_ADM_BRD, "target", code)
            )
        ]
        for code, label, count in rows_data
    ]
    rows.append(_cancel_row())
    return InlineKeyboardMarkup(rows)


def broadcast_media_kb() -> InlineKeyboardMarkup:
    """خطوة الصورة: تخطٍ صريح أو إلغاء (لا خطوة صامتة بلا زر)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t.BTN_BROADCAST_SKIP_MEDIA, callback_data=pack(NS_FLOW, "skip")
                )
            ],
            _cancel_row(),
        ]
    )


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    """تأكيد الإرسال الجماعي (خطوة ثانية إلزامية قبل أي إرسال فعلي)."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BROADCAST_BTN_SEND, callback_data=pack(NS_FLOW, "confirm"))],
            _cancel_row(),
        ]
    )


def broadcast_card_kb(broadcast: Broadcast, perms: set[str]) -> InlineKeyboardMarkup:
    """
    أزرار بطاقة الرسالة الجماعية حسب حالتها.

    المسودة/الموقوفة ⇐ بدء أو استئناف · الجارية ⇐ إيقاف مؤقت · وكلاهما يقبل الإلغاء.
    المكتملة والملغاة بلا أزرار تحكم (لا يمكن إعادة إرسالها فيُستلم النص مرتين).
    """
    rows: list[list[InlineKeyboardButton]] = []
    can_send = Permission.BROADCAST_SEND in perms
    actions: list[InlineKeyboardButton] = []

    if can_send and broadcast.status == "draft":
        actions.append(
            InlineKeyboardButton(
                t.BTN_BROADCAST_START, callback_data=pack(NS_ADM_BRD, "start", broadcast.id)
            )
        )
    if can_send and broadcast.status == "paused":
        actions.append(
            InlineKeyboardButton(
                t.BTN_BROADCAST_RESUME, callback_data=pack(NS_ADM_BRD, "start", broadcast.id)
            )
        )
    if can_send and broadcast.status == "running":
        actions.append(
            InlineKeyboardButton(
                t.BTN_BROADCAST_PAUSE, callback_data=pack(NS_ADM_BRD, "pause", broadcast.id)
            )
        )
    if actions:
        rows.append(actions)

    if can_send and broadcast.status in ("draft", "running", "paused"):
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_BROADCAST_CANCEL, callback_data=pack(NS_ADM_BRD, "cancel", broadcast.id)
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                t.BTN_REFRESH, callback_data=pack(NS_ADM_BRD, "view", broadcast.id)
            )
        ]
    )
    rows.append(_back_row(NS_ADM_BRD, "home"))
    return InlineKeyboardMarkup(rows)


def templates_home_kb(items: list[dict]) -> InlineKeyboardMarkup:
    """قائمة قوالب الإشعارات (زر لكل قالب) مع علامة المعدَّل منها."""
    rows = [
        [
            InlineKeyboardButton(
                f"{t.TEMPLATE_STATE_CUSTOM if item['is_customized'] else t.TEMPLATE_STATE_DEFAULT}"
                f" {item['name_ar']}",
                callback_data=pack(NS_ADM_TPL, "view", item["code"]),
            )
        ]
        for item in items
    ]
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def template_card_kb(code: str, *, is_customized: bool, is_active: bool) -> InlineKeyboardMarkup:
    """
    أزرار بطاقة القالب: تعديل العنوان/النص، معاينة، إيقاف التخصيص، واستعادة الافتراضي.

    «استعادة الافتراضي» تظهر فقط عند وجود تخصيص فعلي — لا زر بلا أثر.
    """
    rows = [
        [
            InlineKeyboardButton(
                t.BTN_TEMPLATE_EDIT_TITLE, callback_data=pack(NS_ADM_TPL, "edit", code, "title")
            ),
            InlineKeyboardButton(
                t.BTN_TEMPLATE_EDIT_BODY, callback_data=pack(NS_ADM_TPL, "edit", code, "body")
            ),
        ],
        [
            InlineKeyboardButton(
                t.BTN_TEMPLATE_PREVIEW, callback_data=pack(NS_ADM_TPL, "prev", code)
            )
        ],
    ]
    if is_customized:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_TEMPLATE_DISABLE if is_active else t.BTN_TEMPLATE_ENABLE,
                    callback_data=pack(NS_ADM_TPL, "toggle", code),
                ),
                InlineKeyboardButton(
                    t.BTN_TEMPLATE_RESET, callback_data=pack(NS_ADM_TPL, "reset", code)
                ),
            ]
        )
    rows.append(_back_row(NS_ADM_TPL, "home"))
    return InlineKeyboardMarkup(rows)


def template_preview_kb(code: str) -> InlineKeyboardMarkup:
    """زر العودة من المعاينة إلى بطاقة القالب نفسه."""
    return InlineKeyboardMarkup([_back_row(NS_ADM_TPL, "view", code)])


# ============================== الأمان (م9) ================================ #

#: أقصى عدد أزرار «رفع الإيقاف» في الشاشة الواحدة (حدود لوحة تيليجرام)
SECURITY_UNBLOCK_BUTTONS_MAX = 8


def security_home_kb() -> InlineKeyboardMarkup:
    """الشاشة الرئيسية للأمان: تحديث + الأحداث + الموقوفون + الفريق."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADM_SEC, "home"))],
            [
                InlineKeyboardButton(t.BTN_SECURITY_EVENTS, callback_data=pack(NS_ADM_SEC, "events", 1)),
                InlineKeyboardButton(t.BTN_SECURITY_BLOCKS, callback_data=pack(NS_ADM_SEC, "blocks")),
            ],
            [InlineKeyboardButton(t.BTN_SECURITY_TEAM, callback_data=pack(NS_ADM_SEC, "team"))],
            _panel_row(),
        ]
    )


def security_events_kb(*, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """ترقيم صفحات الأحداث الأمنية + رجوع."""
    rows: list[list[InlineKeyboardButton]] = []
    nav = pagination_row(NS_ADM_SEC, "events", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_SEC, "home"))
    return InlineKeyboardMarkup(rows)


def security_blocks_kb(telegram_ids: list[tuple[int, str]], perms: set[str]) -> InlineKeyboardMarkup:
    """
    شاشة الموقوفين: زر «رفع الإيقاف» لكل موقوف لمن يملك `security.manage` فقط.

    المدخلات:
        telegram_ids : قائمة (معرّف تيليجرام، اسم العرض).
    """
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADM_SEC, "blocks"))]
    ]
    if Permission.SECURITY_MANAGE in perms:
        for telegram_id, name in telegram_ids[:SECURITY_UNBLOCK_BUTTONS_MAX]:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"{t.BTN_SECURITY_UNBLOCK} · {safe(name, limit=20)}",
                        callback_data=pack(NS_ADM_SEC, "unblock", telegram_id),
                    )
                ]
            )
    rows.append(_back_row(NS_ADM_SEC, "home"))
    return InlineKeyboardMarkup(rows)


def security_team_kb() -> InlineKeyboardMarkup:
    """شاشة الفريق: رجوع فقط (عرض للقراءة)."""
    return InlineKeyboardMarkup([_back_row(NS_ADM_SEC, "home")])


# ============================ النسخ الاحتياطي (م10) ============================ #


def backup_home_kb() -> InlineKeyboardMarkup:
    """الشاشة الرئيسية للنسخ: نسخة الآن، السجل، ضغط القاعدة، دليل الاستعادة."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_BACKUP_NEW, callback_data=pack(NS_ADM_BKP, "new"))],
            [
                InlineKeyboardButton(t.BTN_BACKUP_LIST, callback_data=pack(NS_ADM_BKP, "list", 1)),
                InlineKeyboardButton(t.BTN_BACKUP_VACUUM, callback_data=pack(NS_ADM_BKP, "vacask")),
            ],
            [InlineKeyboardButton(t.BTN_BACKUP_GUIDE, callback_data=pack(NS_ADM_BKP, "guide"))],
            [InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADM_BKP, "home"))],
            _panel_row(),
        ]
    )


def backup_list_kb(items: list[tuple[int, str]], *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """سجل النسخ: زر لكل نسخة (رقم + حالتها) + ترقيم + رجوع."""
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(label, callback_data=pack(NS_ADM_BKP, "view", backup_id, page))]
        for backup_id, label in items
    ]
    nav = pagination_row(NS_ADM_BKP, "list", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_BKP, "home"))
    return InlineKeyboardMarkup(rows)


def backup_view_kb(backup_id: int, page: int, perms: set[str], *, channel_ready: bool, usable: bool) -> InlineKeyboardMarkup:
    """
    تفاصيل نسخة: فحص + (إرسال للقناة/تنزيل لمن يملك `backup.download` وللنسخة السليمة فقط).

    المدخلات:
        channel_ready : قناة النسخ مضبوطة (وإلا لا معنى لزر الإرسال).
        usable        : النسخة سليمة ولها ملف (وإلا لا يظهر إرسال/تنزيل).
    """
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(t.BTN_BACKUP_VERIFY, callback_data=pack(NS_ADM_BKP, "verify", backup_id, page))]
    ]
    if usable and Permission.BACKUP_DOWNLOAD in perms:
        if channel_ready:
            rows.append(
                [InlineKeyboardButton(t.BTN_BACKUP_CHANNEL, callback_data=pack(NS_ADM_BKP, "chan", backup_id, page))]
            )
        rows.append(
            [InlineKeyboardButton(t.BTN_BACKUP_DOWNLOAD, callback_data=pack(NS_ADM_BKP, "dlask", backup_id, page))]
        )
    rows.append(_back_row(NS_ADM_BKP, "list", page))
    return InlineKeyboardMarkup(rows)


def backup_confirm_kb(confirm_label: str, confirm_action: str, *args: object, back: tuple[str, tuple[object, ...]]) -> InlineKeyboardMarkup:
    """شاشة تأكيد ثانٍ: زر التنفيذ + إلغاء يعيد للشاشة السابقة."""
    back_action, back_args = back
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(confirm_label, callback_data=pack(NS_ADM_BKP, confirm_action, *args))],
            [InlineKeyboardButton("❌ إلغاء", callback_data=pack(NS_ADM_BKP, back_action, *back_args))],
        ]
    )


def backup_guide_kb() -> InlineKeyboardMarkup:
    """دليل الاستعادة: رجوع فقط."""
    return InlineKeyboardMarkup([_back_row(NS_ADM_BKP, "home")])


# ============================ الإحصائيات (م10) ============================ #


def _stats_period_rows(action: str, current: str, *, extra: tuple[object, ...] = ()) -> list[list[InlineKeyboardButton]]:
    """صفّا أزرار الفترات (3+3) تُعلَّم فيها الفترة الحالية بنقطة، وتحمل `extra` قبل مفتاح الفترة."""
    from services.stats_service import PERIOD_KEYS, PERIOD_LABELS

    buttons = [
        InlineKeyboardButton(
            ("• " if key == current else "") + PERIOD_LABELS[key],
            callback_data=pack(NS_ADM_STATS, action, *extra, key),
        )
        for key in PERIOD_KEYS
    ]
    return [buttons[:3], buttons[3:]]


def stats_home_kb(period: str, perms: set[str]) -> InlineKeyboardMarkup:
    """الشاشة الرئيسية للإحصائيات: الفترات + الأقسام الفرعية + التصدير لمن يملك `stats.export`."""
    rows = _stats_period_rows("home", period)
    rows.append(
        [
            InlineKeyboardButton(t.BTN_STATS_SERVICES, callback_data=pack(NS_ADM_STATS, "svc", period)),
            InlineKeyboardButton(t.BTN_STATS_BUYERS, callback_data=pack(NS_ADM_STATS, "usr", period)),
            InlineKeyboardButton(t.BTN_STATS_DAILY, callback_data=pack(NS_ADM_STATS, "day", period)),
        ]
    )
    last = [InlineKeyboardButton(t.BTN_STATS_WALLET, callback_data=pack(NS_ADM_STATS, "wal"))]
    if Permission.STATS_EXPORT in perms:
        last.append(InlineKeyboardButton(t.BTN_STATS_EXPORT, callback_data=pack(NS_ADM_STATS, "expm", period)))
    rows.append(last)
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def stats_sub_kb(action: str, period: str) -> InlineKeyboardMarkup:
    """شاشة فرعية (خدمات/عملاء/يومي): تبديل الفترة + رجوع للملخص."""
    rows = _stats_period_rows(action, period)
    rows.append(_back_row(NS_ADM_STATS, "home", period))
    return InlineKeyboardMarkup(rows)


def stats_wallet_kb() -> InlineKeyboardMarkup:
    """شاشة التزامات المحفظة: تحديث + رجوع."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADM_STATS, "wal"))],
            _back_row(NS_ADM_STATS, "home", "today"),
        ]
    )


def stats_export_menu_kb(period: str) -> InlineKeyboardMarkup:
    """قائمة التصدير: نوع التقرير (يقود لشاشة تأكيد) + رجوع."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_STATS_EXPORT_ORDERS, callback_data=pack(NS_ADM_STATS, "expask", "orders", period))],
            [InlineKeyboardButton(t.BTN_STATS_EXPORT_DAILY, callback_data=pack(NS_ADM_STATS, "expask", "daily", period))],
            _back_row(NS_ADM_STATS, "home", period),
        ]
    )


def stats_export_confirm_kb(kind: str, period: str) -> InlineKeyboardMarkup:
    """تأكيد ثانٍ للتصدير + إلغاء يعود لقائمة التصدير."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_STATS_EXPORT_CONFIRM, callback_data=pack(NS_ADM_STATS, "exp", kind, period))],
            [InlineKeyboardButton("❌ إلغاء", callback_data=pack(NS_ADM_STATS, "expm", period))],
        ]
    )


# ============================ القنوات (المرحلة 13) ============================ #


def channels_home_kb(*, can_edit: bool) -> InlineKeyboardMarkup:
    """
    أزرار شاشة القنوات.

    المدخلات:
        can_edit : يملك `settings.update` — الفحص والاختبار والتعديل تتطلبها (عرض الشاشة يكفيه settings.view).
    """
    rows: list[list[InlineKeyboardButton]] = []
    if can_edit:
        rows.append([InlineKeyboardButton(t.BTN_CHANNELS_CHECK, callback_data=pack(NS_ADM_CHN, "check"))])
        rows.append(
            [
                InlineKeyboardButton(t.BTN_CHANNELS_TEST_ALERT, callback_data=pack(NS_ADM_CHN, "test", "alert")),
                InlineKeyboardButton(t.BTN_CHANNELS_TEST_ORDERS, callback_data=pack(NS_ADM_CHN, "test", "orders")),
            ]
        )
        rows.append([InlineKeyboardButton(t.BTN_CHANNELS_EDIT, callback_data=pack(NS_ADM_SET, "group", "channels", 1))])
    rows.append([InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADM_CHN, "home"))])
    rows.append([InlineKeyboardButton(t.BTN_BACK_PANEL, callback_data=pack(NS_ADMIN, "home"))])
    return InlineKeyboardMarkup(rows)


def channels_result_kb() -> InlineKeyboardMarkup:
    """رجوع من نتيجة الفحص/الاختبار إلى شاشة القنوات."""
    return InlineKeyboardMarkup([_back_row(NS_ADM_CHN, "home")])
