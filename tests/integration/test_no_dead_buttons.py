"""
اختبار القاعدة الملزِمة: **لا زر بلا وظيفة**.

الطريقة:
    1. نستدعي كل باني لوحة أزرار في `keyboards/` ببيانات تجريبية.
    2. نجمع كل قيم `callback_data` الناتجة.
    3. نتأكد أن كل قيمة يلتقطها معالج مسجَّل فعلاً في `handlers/registry.py`
       (مع استبعاد المعالج الاحتياطي الشامل، وإلا لصار الاختبار بلا معنى).

كما نتحقق من العكس: كل معالج مسجَّل له نمط مفهوم وبإصدار `callback` الحالي.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from telegram import InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, ConversationHandler

from core.permissions import Permission
from handlers.registry import build_handlers
from keyboards import admin_kb, common_kb, user_kb
from keyboards.callback_data import (
    CALLBACK_VERSION,
    NS_ADM_CAT,
    NS_ADM_PRV,
    unpack,
)


def _fake_category(index: int = 1) -> SimpleNamespace:
    """تصنيف تجريبي بالحقول التي تستخدمها اللوحات فقط."""
    return SimpleNamespace(
        id=index, name_ar=f"تصنيف {index}", emoji="📱", title=f"📱 تصنيف {index}"
    )


def _fake_service(index: int = 1) -> SimpleNamespace:
    """خدمة تجريبية."""
    return SimpleNamespace(
        id=index,
        name=f"خدمة {index}",
        description="وصف",
        price_per_1000_units=10_000,
        min_quantity=100,
        max_quantity=1000,
        avg_time_text="ساعة",
        link_pattern=None,
        category_id=1,
    )


def _fake_order(index: int = 1, status: str = "pending") -> SimpleNamespace:
    """طلب تجريبي."""
    return SimpleNamespace(
        id=index,
        public_code=f"ORD-{index}",
        status=status,
        cost_units=10_000,
        quantity=1000,
        delivered_quantity=0,
        remains=1000,
        refund_amount_units=0,
        last_error=None,
        service_name_snapshot="خدمة",
        link="https://example.com/u",
        created_at="2026-01-01T10:00:00+00:00",
    )


def _fake_payment(index: int = 1, status: str = "pending") -> SimpleNamespace:
    """طلب شحن تجريبي."""
    return SimpleNamespace(
        id=index, amount_units=50_000, status=status, created_at="2026-01-01T10:00:00+00:00"
    )


def _fake_method(index: int = 1, *, active: bool = True) -> SimpleNamespace:
    """طريقة دفع تجريبية (بحقول الرسوم والحدود التي أضافتها المرحلة 7)."""
    return SimpleNamespace(
        id=index,
        code=f"method_{index}",
        name_ar=f"طريقة {index}",
        type="manual",
        instructions_ar="حوّل ثم أرسل",
        account_details="123456",
        requires_proof=True,
        is_active=active,
        sort_order=index * 10,
        min_amount_units=10_000,
        max_amount_units=None,
        fee_percent_bp=250,
        fee_fixed_units=0,
    )


def _fake_ticket(index: int = 1, status: str = "open") -> SimpleNamespace:
    """تذكرة دعم تجريبية."""
    return SimpleNamespace(
        id=index,
        subject="مشكلة",
        status=status,
        category="other",
        last_message_at="2026-01-01T10:00:00+00:00",
        updated_at="2026-01-01T10:00:00+00:00",
        is_open=status == "open",
        priority="normal",
    )


def _fake_broadcast(index: int = 1, status: str = "draft") -> SimpleNamespace:
    """رسالة جماعية تجريبية (المرحلة 8)."""
    return SimpleNamespace(
        id=index,
        status=status,
        sent_count=3,
        total_count=10,
        failed_count=0,
        blocked_count=0,
        message_text="نص",
        target="all",
        media_file_id=None,
        created_at="2026-01-01T10:00:00+00:00",
    )


def _fake_template_item(code: str = "order_created", *, custom: bool = False) -> dict:
    """عنصر قائمة قوالب الإشعارات (المرحلة 8)."""
    return {
        "code": code,
        "name_ar": "إنشاء الطلب",
        "group": "orders",
        "group_name": "📦 الطلبات",
        "is_customized": custom,
        "is_active": custom,
        "updated_at": None,
    }


def _fake_ticket_with_priority() -> SimpleNamespace:
    """تذكرة مفتوحة بأولوية عالية (لتغطية زر الأولوية المحدَّد)."""
    ticket = _fake_ticket(5)
    ticket.priority = "high"
    ticket.user_id = 5
    return ticket


def _fake_user(index: int = 1, *, banned: bool = False, role: str = "user") -> SimpleNamespace:
    """مستخدم تجريبي بالحقول التي تستخدمها لوحات الأدمن."""
    return SimpleNamespace(
        id=index,
        telegram_id=100_000 + index,
        username=f"user{index}",
        display_name=f"مستخدم {index}",
        is_banned=banned,
        role=role,
        balance_units=25_000,
    )


def _fake_admin_payment(index: int = 1, *, with_proof: bool = True) -> SimpleNamespace:
    """طلب شحن تجريبي كما تراه لوحة الأدمن."""
    return SimpleNamespace(
        id=index,
        user_id=index,
        amount_units=50_000,
        status="pending",
        proof_file_id="FILE123" if with_proof else None,
        proof_file_type="photo",
        created_at="2026-01-01T10:00:00+00:00",
    )


def _fake_admin_order(index: int = 1, status: str = "submit_uncertain") -> SimpleNamespace:
    """طلب تجريبي كما تراه لوحة الأدمن (بحقول المزود والقفل)."""
    order = _fake_order(index, status=status)
    order.user_id = index
    order.provider_order_id = "PRV-9" if status != "pending" else None
    order.provider_id = 1
    return order


def _fake_admin_service(index: int = 1, *, active: bool = True, archived: bool = False):
    """خدمة تجريبية بحقول الحالة التي تحتاجها بطاقة الأدمن."""
    service = _fake_service(index)
    service.is_active = active
    service.is_archived = archived
    service.provider_id = 1
    service.provider_service_id = "55"
    service.provider_price_per_1000_units = 6_000
    return service


def _fake_provider(
    index: int = 1, *, active: bool = True, failures: int = 0
) -> SimpleNamespace:
    """مزود تجريبي بالحقول التي تستخدمها لوحات المزودين فقط."""
    return SimpleNamespace(
        id=index,
        name=f"مزود {index}",
        api_url="https://panel.example.com/api/v2",
        api_key_hint="••••1234",
        api_type="perfect_panel",
        balance_units=1_500_000,
        currency="USD",
        balance_checked_at="2026-01-01T10:00:00+00:00",
        is_active=active,
        active=active,
        priority=index,
        timeout_seconds=30,
        consecutive_failures=failures,
        disabled_until=None,
        last_error=None if failures == 0 else "timeout",
        last_success_at="2026-01-01T09:00:00+00:00",
    )


def _fake_provider_item(index: int = 1) -> SimpleNamespace:
    """عنصر من قائمة خدمات المزود (نتيجة استيراد)."""
    return SimpleNamespace(
        provider_service_id=str(1000 + index),
        name=f"Instagram Followers {index}",
        rate_per_1000_units=8_000,
        min_quantity=100,
        max_quantity=100_000,
        category="Instagram",
        service_type="Default",
        dripfeed=False,
        refill=True,
        cancel=False,
        currency="USD",
        raw={},
    )


def _fake_setting(key: str = "order_check_interval_seconds", *, editable: bool = True):
    """مفتاح إعداد تجريبي."""
    return SimpleNamespace(
        key=key,
        value="120",
        value_type="int",
        group_code="orders",
        name_ar="فاصل الفحص",
        description_ar="بالثواني",
        is_editable=editable,
    )


def admin_markups() -> list[tuple[str, InlineKeyboardMarkup]]:
    """
    كل لوحات لوحة التحكم ببيانات تجريبية.

    تُبنى بصلاحيات كاملة عمداً: هكذا يظهر **كل** زر ممكن في اللوحة ويخضع
    لفحص «لا زر بلا معالج» — بما في ذلك الأزرار التي لا يراها إلا الأدمن الأعلى.
    """
    perms = {str(permission) for permission in Permission}
    users = [_fake_user(1), _fake_user(2, banned=True)]
    orders = [_fake_admin_order(1), _fake_admin_order(2, status="in_progress")]
    payments = [_fake_admin_payment(1), _fake_admin_payment(2, with_proof=False)]
    tickets = [_fake_ticket(1), _fake_ticket(2, status="closed")]
    services = [_fake_admin_service(1), _fake_admin_service(2, active=False)]
    categories = [_fake_category(1), _fake_category(2)]

    for ticket in tickets:
        ticket.user_id = ticket.id

    return [
        ("admin_menu_kb", admin_kb.admin_menu_kb(perms, pending_payments=3, open_tickets=2)),
        ("admin_menu_kb_minimal", admin_kb.admin_menu_kb({Permission.ADMIN_ACCESS})),
        ("health_kb", admin_kb.health_kb()),
        (
            "jobs_home_kb",
            admin_kb.jobs_home_kb(["orders_check", "providers_balance"], perms),
        ),
        ("jobs_home_kb_readonly", admin_kb.jobs_home_kb(["orders_check"], {Permission.STATS_VIEW})),
        ("back_panel_kb", admin_kb.back_panel_kb()),
        ("admin_cancel_only_kb", admin_kb.cancel_only_kb()),
        ("admin_confirm_cancel_kb", admin_kb.confirm_cancel_kb()),
        ("admin_skip_cancel_kb", admin_kb.skip_cancel_kb()),
        ("users_home_kb", admin_kb.users_home_kb(perms)),
        ("user_results_kb", admin_kb.user_results_kb(users)),
        ("user_card_kb", admin_kb.user_card_kb(_fake_user(1), perms)),
        ("user_card_kb_banned", admin_kb.user_card_kb(_fake_user(2, banned=True), perms)),
        ("user_role_kb", admin_kb.user_role_kb(_fake_user(1))),
        ("user_role_confirm_kb", admin_kb.user_role_confirm_kb(1, "support")),
        ("user_orders_nav_kb", admin_kb.user_list_nav_kb("orders", 1, page=1, total_pages=3)),
        ("user_tx_nav_kb", admin_kb.user_list_nav_kb("tx", 1, page=2, total_pages=3)),
        (
            "payments_list_kb",
            admin_kb.payments_list_kb(
                payments, page=1, total_pages=2, symbol="ر.ي", perms=perms
            ),
        ),
        (
            "payments_list_kb_all_filter",
            admin_kb.payments_list_kb(
                payments,
                page=2,
                total_pages=3,
                symbol="ر.ي",
                filter_code="all",
                perms={Permission.PAYMENTS_VIEW},
            ),
        ),
        ("payments_search_kb", admin_kb.payments_search_kb(payments, symbol="ر.ي")),
        (
            "payment_methods_kb",
            admin_kb.payment_methods_kb(
                [_fake_method(1), _fake_method(2, active=False)], perms
            ),
        ),
        ("payment_methods_kb_empty", admin_kb.payment_methods_kb([], perms)),
        (
            "payment_methods_kb_readonly",
            admin_kb.payment_methods_kb([_fake_method(1)], {Permission.PAYMENTS_VIEW}),
        ),
        ("method_card_kb", admin_kb.method_card_kb(_fake_method(1), perms)),
        (
            "method_card_kb_off",
            admin_kb.method_card_kb(_fake_method(2, active=False), perms),
        ),
        (
            "method_card_kb_readonly",
            admin_kb.method_card_kb(_fake_method(1), {Permission.PAYMENTS_VIEW}),
        ),
        ("method_type_kb", admin_kb.method_type_kb()),
        ("methods_report_kb", admin_kb.methods_report_kb()),
        (
            "payment_card_kb",
            admin_kb.payment_card_kb(_fake_admin_payment(1), perms, is_pending=True),
        ),
        (
            "payment_card_kb_done",
            admin_kb.payment_card_kb(
                _fake_admin_payment(2, with_proof=False), perms, is_pending=False
            ),
        ),
        ("payment_approve_kb", admin_kb.payment_approve_kb()),
        (
            "admin_orders_kb",
            admin_kb.admin_orders_kb(
                orders, filter_code="att", page=1, total_pages=2, symbol="ر.ي"
            ),
        ),
        (
            "admin_order_card_kb",
            admin_kb.admin_order_card_kb(
                _fake_admin_order(1), perms, filter_code="att", page=1
            ),
        ),
        (
            "admin_order_card_kb_final",
            admin_kb.admin_order_card_kb(
                _fake_admin_order(3, status="completed"), perms, filter_code="all", page=1
            ),
        ),
        ("order_override_kb", admin_kb.order_override_kb(_fake_admin_order(1))),
        (
            "admin_tickets_kb",
            admin_kb.admin_tickets_kb(tickets, filter_code="open", page=1, total_pages=2),
        ),
        ("admin_ticket_card_kb", admin_kb.admin_ticket_card_kb(tickets[0], perms)),
        (
            "admin_ticket_card_kb_closed",
            admin_kb.admin_ticket_card_kb(tickets[1], perms, filter_code="closed"),
        ),
        ("catalog_home_kb", admin_kb.catalog_home_kb(categories, perms)),
        (
            "catalog_services_kb",
            admin_kb.catalog_services_kb(
                services, category_id=1, page=1, total_pages=2, symbol="ر.ي"
            ),
        ),
        ("service_card_kb", admin_kb.service_card_kb(_fake_admin_service(1), perms)),
        (
            "service_card_kb_archived",
            admin_kb.service_card_kb(_fake_admin_service(2, archived=True), perms),
        ),
        (
            "settings_home_kb",
            admin_kb.settings_home_kb(["general", "orders"], perms, maintenance_on=False),
        ),
        (
            "settings_group_kb",
            admin_kb.settings_group_kb(
                [_fake_setting(), _fake_setting("locked_key", editable=False)],
                group="orders",
                page=1,
                total_pages=2,
                perms=perms,
            ),
        ),
        (
            "providers_home_kb",
            admin_kb.providers_home_kb(
                [_fake_provider(1), _fake_provider(2, active=False, failures=3)], perms
            ),
        ),
        ("providers_home_kb_empty", admin_kb.providers_home_kb([], perms)),
        ("provider_card_kb", admin_kb.provider_card_kb(_fake_provider(1), perms)),
        (
            "provider_card_kb_disabled",
            admin_kb.provider_card_kb(_fake_provider(2, active=False), perms),
        ),
        ("provider_type_kb", admin_kb.provider_type_kb()),
        (
            "provider_services_kb",
            admin_kb.provider_services_kb(
                services, provider_id=1, page=1, total_pages=2, symbol="ر.ي"
            ),
        ),
        (
            "provider_import_results_kb",
            admin_kb.provider_import_results_kb(
                [(0, _fake_provider_item(1)), (1, _fake_provider_item(2))],
                provider_id=1,
                symbol="ر.ي",
                selected={0},
                page=1,
                total_pages=2,
            ),
        ),
        (
            "category_picker_kb",
            admin_kb.category_picker_kb(categories, NS_ADM_CAT, "ncat"),
        ),
        (
            "category_picker_kb_import",
            admin_kb.category_picker_kb(categories, NS_ADM_PRV, "cat"),
        ),
        (
            "provider_picker_kb",
            admin_kb.provider_picker_kb([_fake_provider(1)], NS_ADM_CAT, "nprv"),
        ),
        ("logs_home_kb", admin_kb.logs_home_kb()),
        ("logs_audit_kb", admin_kb.logs_page_kb("audit", page=2, total_pages=5)),
        ("logs_errors_kb", admin_kb.logs_page_kb("errors", page=1, total_pages=2)),
        # ------------------------- المرحلة 10 ------------------------- #
        ("logs_audit_filtered_kb", admin_kb.logs_audit_kb([5, 4, 3, 2, 1], category="money", page=2, total_pages=4)),
        ("logs_audit_filter_kb", admin_kb.logs_audit_filter_kb("orders")),
        ("logs_audit_detail_kb", admin_kb.logs_audit_detail_kb("security", 3)),
        ("logs_errors_list_kb", admin_kb.logs_errors_kb([9, 8, 7], page=2, total_pages=3)),
        ("logs_error_detail_kb", admin_kb.logs_error_detail_kb(2)),
        ("logs_calls_kb", admin_kb.logs_calls_kb([3, 2, 1], failed_only=False, page=1, total_pages=2)),
        ("logs_calls_failed_kb", admin_kb.logs_calls_kb([3, 2], failed_only=True, page=2, total_pages=3)),
        ("logs_call_detail_kb", admin_kb.logs_call_detail_kb("f", 2)),
        ("stats_home_kb_full", admin_kb.stats_home_kb("7d", perms)),
        ("stats_home_kb_view_only", admin_kb.stats_home_kb("month", {Permission.STATS_VIEW})),
        ("stats_sub_svc_kb", admin_kb.stats_sub_kb("svc", "30d")),
        ("stats_sub_usr_kb", admin_kb.stats_sub_kb("usr", "yesterday")),
        ("stats_sub_day_kb", admin_kb.stats_sub_kb("day", "90d")),
        ("stats_wallet_kb", admin_kb.stats_wallet_kb()),
        ("stats_export_menu_kb", admin_kb.stats_export_menu_kb("today")),
        ("stats_export_confirm_orders_kb", admin_kb.stats_export_confirm_kb("orders", "7d")),
        ("stats_export_confirm_daily_kb", admin_kb.stats_export_confirm_kb("daily", "month")),
        # ------------------------- المرحلة 8 ------------------------- #
        ("admin_ticket_card_kb_high", admin_kb.admin_ticket_card_kb(
            _fake_ticket_with_priority(), perms, filter_code="high"
        )),
        ("broadcast_home_kb", admin_kb.broadcast_home_kb(
            [_fake_broadcast(1), _fake_broadcast(2, "running")], perms
        )),
        ("broadcast_home_kb_empty", admin_kb.broadcast_home_kb([], perms)),
        ("broadcast_target_kb", admin_kb.broadcast_target_kb(
            [("all", "كل المستخدمين", 10), ("buyers", "المشترون", 4)]
        )),
        ("broadcast_media_kb", admin_kb.broadcast_media_kb()),
        ("broadcast_confirm_kb", admin_kb.broadcast_confirm_kb()),
        ("broadcast_card_kb_draft", admin_kb.broadcast_card_kb(_fake_broadcast(1, "draft"), perms)),
        ("broadcast_card_kb_running", admin_kb.broadcast_card_kb(_fake_broadcast(2, "running"), perms)),
        ("broadcast_card_kb_paused", admin_kb.broadcast_card_kb(_fake_broadcast(3, "paused"), perms)),
        ("broadcast_card_kb_done", admin_kb.broadcast_card_kb(_fake_broadcast(4, "completed"), perms)),
        ("templates_home_kb", admin_kb.templates_home_kb(
            [_fake_template_item(), _fake_template_item("order_failed", custom=True)]
        )),
        ("template_card_kb_default", admin_kb.template_card_kb(
            "order_created", is_customized=False, is_active=False
        )),
        ("template_card_kb_custom", admin_kb.template_card_kb(
            "order_created", is_customized=True, is_active=True
        )),
        ("template_card_kb_paused", admin_kb.template_card_kb(
            "order_created", is_customized=True, is_active=False
        )),
        ("template_preview_kb", admin_kb.template_preview_kb("order_created")),
        # ------------------------- المرحلة 9 ------------------------- #
        ("security_home_kb", admin_kb.security_home_kb()),
        ("security_events_kb", admin_kb.security_events_kb(page=2, total_pages=4)),
        ("security_events_kb_single", admin_kb.security_events_kb(page=1, total_pages=1)),
        ("security_blocks_kb_manager", admin_kb.security_blocks_kb(
            [(111, "@a"), (222, "@b")], {Permission.SECURITY_VIEW, Permission.SECURITY_MANAGE}
        )),
        ("security_blocks_kb_viewer", admin_kb.security_blocks_kb([(111, "@a")], {Permission.SECURITY_VIEW})),
        ("security_blocks_kb_empty", admin_kb.security_blocks_kb([], set())),
        ("security_team_kb", admin_kb.security_team_kb()),
    ]


def all_markups() -> list[tuple[str, InlineKeyboardMarkup]]:
    """
    بناء كل لوحات الواجهة مرة واحدة.

    أي لوحة جديدة تُضاف في `keyboards/user_kb.py` يجب أن تُضاف هنا — وهذا مقصود:
    اللوحة التي لا تُختبر لا تُضمن أزرارها.
    """
    categories = [_fake_category(1), _fake_category(2)]
    services = [_fake_service(1), _fake_service(2)]
    orders = [_fake_order(1), _fake_order(2, status="completed")]
    tickets = [_fake_ticket(1), _fake_ticket(2, status="closed")]
    payments = [_fake_payment(1), _fake_payment(2, status="approved")]

    return [
        ("main_menu_kb", user_kb.main_menu_kb()),
        ("main_menu_kb_admin", user_kb.main_menu_kb(is_admin=True)),
        ("categories_kb", user_kb.categories_kb(categories)),
        ("categories_kb_empty", user_kb.categories_kb([])),
        (
            "services_kb",
            user_kb.services_kb(services, category_id=1, page=2, total_pages=3, symbol="ر.ي"),
        ),
        ("service_card_kb", user_kb.service_card_kb(_fake_service(1), category_id=1, page=1)),
        ("insufficient_balance_kb", user_kb.insufficient_balance_kb(1, 1)),
        (
            "orders_kb",
            user_kb.orders_kb(orders, filter_code="all", page=1, total_pages=2, symbol="ر.ي"),
        ),
        (
            "order_card_kb_cancelable",
            user_kb.order_card_kb(_fake_order(1), can_cancel=True, filter_code="all", page=1),
        ),
        (
            "order_card_kb_plain",
            user_kb.order_card_kb(
                _fake_order(2, status="completed"), can_cancel=False, filter_code="done", page=1
            ),
        ),
        ("order_cancel_confirm_kb", user_kb.order_cancel_confirm_kb(1)),
        ("wallet_kb", user_kb.wallet_kb()),
        ("history_kb", user_kb.history_kb(page=2, total_pages=4)),
        ("deposit_methods_kb", user_kb.deposit_methods_kb([_fake_method(1), _fake_method(2)])),
        ("deposits_kb", user_kb.deposits_kb(payments, page=1, total_pages=2)),
        ("support_kb", user_kb.support_kb()),
        ("ticket_categories_kb", user_kb.ticket_categories_kb()),
        ("tickets_kb", user_kb.tickets_kb(tickets, page=1, total_pages=1)),
        ("ticket_card_kb_open", user_kb.ticket_card_kb(_fake_ticket(1))),
        ("ticket_card_kb_closed", user_kb.ticket_card_kb(_fake_ticket(2, status="closed"))),
        ("account_kb", user_kb.account_kb(3)),
        ("notifications_kb", user_kb.notifications_kb(page=1, total_pages=2, unread=5)),
        ("info_kb", user_kb.info_kb()),
        ("help_index_kb", user_kb.help_kb(None)),
        ("help_start_kb", user_kb.help_kb("start")),
        ("help_deposit_kb", user_kb.help_kb("deposit")),
        ("help_order_kb", user_kb.help_kb("order")),
        ("help_status_kb", user_kb.help_kb("status")),
        ("help_refund_kb", user_kb.help_kb("refund")),
        ("help_faq_kb", user_kb.help_kb("faq")),
        ("help_contact_kb", user_kb.help_kb("contact")),
        ("notifications_only_back_kb", user_kb.notifications_only_back_kb()),
        ("cancel_markup", common_kb.cancel_markup()),
        ("confirm_cancel_markup", common_kb.confirm_cancel_markup()),
        ("skip_cancel_markup", common_kb.skip_cancel_markup()),
        *admin_markups(),
    ]


def registered_patterns() -> list[re.Pattern]:
    """
    كل أنماط الأزرار التي يلتقطها البوت فعلاً.

    تشمل معالجات الشاشات ومداخل المحادثات وحالاتها ومساراتها الاحتياطية،
    وتستبعد المعالج الشامل (الذي بلا نمط) لأنه شبكة أمان لا دليل تغطية.
    """
    patterns: list[re.Pattern] = []

    def collect(handler: object) -> None:
        """جمع النمط من معالج واحد (أو من محادثة كاملة)."""
        if isinstance(handler, CallbackQueryHandler):
            if handler.pattern is not None:
                patterns.append(handler.pattern)
        elif isinstance(handler, ConversationHandler):
            for entry in handler.entry_points:
                collect(entry)
            for state_handlers in handler.states.values():
                for state_handler in state_handlers:
                    collect(state_handler)
            for fallback in handler.fallbacks:
                collect(fallback)

    for _group, handler in build_handlers():
        collect(handler)
    return patterns


ALL_BUTTONS = sorted(
    {
        data
        for _name, markup in all_markups()
        for row in markup.inline_keyboard
        for button in row
        if (data := button.callback_data)
    }
)


def test_keyboards_produce_buttons() -> None:
    """تأكيد أن اللوحات فعلاً تنتج أزراراً (حماية من اختبار فارغ يمر زوراً).."""
    assert len(ALL_BUTTONS) >= 25


@pytest.mark.parametrize("callback_data", ALL_BUTTONS)
def test_every_button_has_handler(callback_data: str) -> None:
    """كل زر في الواجهة يلتقطه معالج مسجَّل — لا أزرار ميتة."""
    patterns = registered_patterns()
    matched = [pattern.pattern for pattern in patterns if pattern.search(callback_data)]
    assert matched, f"الزر {callback_data!r} بلا معالج مسجَّل في handlers/registry.py"


@pytest.mark.parametrize("callback_data", ALL_BUTTONS)
def test_every_button_is_well_formed(callback_data: str) -> None:
    """كل زر مُرمَّز بالصيغة المعتمدة وبإصدار callback الحالي."""
    data = unpack(callback_data)
    assert data.namespace
    assert data.action
    assert data.version == CALLBACK_VERSION
    assert len(callback_data.encode("utf-8")) <= 64   # حد تيليجرام الصارم


def test_no_button_matches_more_than_one_screen_handler() -> None:
    """
    لا يلتقط زرَّاً واحداً أكثر من معالج شاشة.

    التقاط زر بمعالجين يعني سلوكاً يعتمد على ترتيب التسجيل — مصدر أعطال صامتة.
    المحادثات مستثناة لأن حالاتها معزولة زمنياً (لا تعمل إلا داخل المحادثة).
    """
    from handlers.registry import screen_handlers

    patterns = [handler.pattern for handler in screen_handlers() if handler.pattern]
    for callback_data in ALL_BUTTONS:
        matches = [pattern.pattern for pattern in patterns if pattern.search(callback_data)]
        assert len(matches) <= 1, f"الزر {callback_data!r} يلتقطه أكثر من معالج: {matches}"
