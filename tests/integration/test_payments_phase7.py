"""
اختبارات المرحلة 7 — نظام الدفع والشحن المتقدم.

ما تغطيه:
    1. إدارة طرق الشحن من الخدمة: إنشاء، تعديل محروس، ترتيب، تفعيل/إيقاف.
    2. الرسوم: حسابها، تخزينها كلقطة على الطلب، وأثرها على المبلغ المضاف.
    3. شاشات اللوحة: قائمة الطرق، البطاقة، التقرير، التصفية، البحث.
    4. الصلاحيات: من لا يملك `payments.methods` لا يرى الأزرار ولا ينفّذ.
    5. جانب المستخدم: رؤية الرسوم والصافي قبل الإرسال.
"""

from __future__ import annotations

import pytest

from core.enums import PaymentStatus
from core.exceptions import PermissionDeniedError, ValidationError
from core.money import MONEY_SCALE
from database.models import User
from database.repositories import Repositories
from handlers.admin import payment_methods as methods_admin
from handlers.admin import payments as payments_admin
from handlers.user import deposit as user_deposit
from keyboards.callback_data import pack
from services import ServiceContainer
from tests.integration.test_user_interface import (
    bot,  # noqa: F401
    context,  # noqa: F401
    load_user,
    press,
    write,
)
from tests.telegram_fakes import FakeBot, FakeContext

pytestmark = pytest.mark.asyncio


# ======================================================================== #
#                                أدوات                                     #
# ======================================================================== #


@pytest.fixture
async def fee_method(services: ServiceContainer, super_admin: User):
    """طريقة شحن برسوم 2.5% + 1 عملة ثابتة (كمحفظة إلكترونية حقيقية)."""
    method = await services.payments.create_method(
        super_admin,
        name_ar="محفظة الرسوم",
        instructions_ar="حوّل ثم أرسل رقم العملية",
        account_details="770000000",
        fee_percent_bp=250,
        fee_fixed_units=1 * MONEY_SCALE,
    )
    return method


async def _submit(services: ServiceContainer, user: User, method, amount: str = "100"):
    """إرسال طلب شحن بمبلغ محدد عبر طريقة محددة."""
    return await services.payments.create_payment(
        user,
        method_id=method.id,
        raw_amount=amount,
        transaction_reference=f"TRX-{method.id}-{amount}",
    )


# ======================================================================== #
#                      1) إدارة طرق الشحن (الخدمة)                         #
# ======================================================================== #


async def test_create_method_derives_unique_code_and_appends_to_end(
    services: ServiceContainer, super_admin: User, payment_method
) -> None:
    """الكود يُشتق تلقائياً ويكون فريداً، والطريقة الجديدة تُضاف آخر القائمة."""
    first = await services.payments.create_method(super_admin, name_ar="محفظة كريمي")
    second = await services.payments.create_method(super_admin, name_ar="محفظة كريمي")

    assert first.code != second.code
    assert second.sort_order > first.sort_order >= payment_method.sort_order
    assert first.is_active == 1


async def test_create_method_requires_methods_permission(
    services: ServiceContainer, user: User
) -> None:
    """المستخدم العادي لا يستطيع إنشاء طريقة شحن."""
    with pytest.raises(PermissionDeniedError):
        await services.payments.create_method(user, name_ar="طريقة مزيفة")


async def test_update_method_rejects_unknown_field(
    services: ServiceContainer, super_admin: User, payment_method
) -> None:
    """الحقول غير المسموحة (مثل الكود) لا تُعدَّل عبر update_method."""
    with pytest.raises(ValidationError):
        await services.payments.update_method(super_admin, payment_method.id, code="hacked")


async def test_update_method_validates_fee_range(
    services: ServiceContainer, super_admin: User, payment_method
) -> None:
    """نسبة رسوم أكبر من 100% مرفوضة قبل الوصول لقاعدة البيانات."""
    with pytest.raises(ValidationError):
        await services.payments.update_method(
            super_admin, payment_method.id, fee_percent_bp=10_001
        )
    reloaded = await services.payments.get_method(payment_method.id, require_active=False)
    assert reloaded.fee_percent_bp == 0


async def test_update_method_rejects_min_greater_than_max(
    services: ServiceContainer, super_admin: User, payment_method
) -> None:
    """حدّ أدنى أكبر من الحد الأقصى يُرفض برسالة عربية واضحة."""
    await services.payments.update_method(
        super_admin, payment_method.id, max_amount_units=50 * MONEY_SCALE
    )
    with pytest.raises(ValidationError):
        await services.payments.update_method(
            super_admin, payment_method.id, min_amount_units=90 * MONEY_SCALE
        )


async def test_update_method_keeps_instruction_lines(
    services: ServiceContainer, super_admin: User, payment_method
) -> None:
    """تعليمات التحويل تحتفظ بأسطرها (خطوات مرقّمة لا تُدمج في سطر واحد)."""
    await services.payments.update_method(
        super_admin, payment_method.id, instructions_ar="1- حوّل المبلغ\n2- أرسل الإيصال"
    )
    reloaded = await services.payments.get_method(payment_method.id, require_active=False)
    assert reloaded.instructions_ar.splitlines() == ["1- حوّل المبلغ", "2- أرسل الإيصال"]


async def test_move_method_swaps_order_and_stops_at_edges(
    services: ServiceContainer, super_admin: User, payment_method
) -> None:
    """أزرار الترتيب تبدّل الطريقتين، وفي الطرف تُرجع False بلا تغيير."""
    second = await services.payments.create_method(super_admin, name_ar="طريقة ثانية")

    assert await services.payments.move_method(super_admin, second.id, up=True) is True
    first_after = await services.payments.get_method(payment_method.id, require_active=False)
    second_after = await services.payments.get_method(second.id, require_active=False)
    assert second_after.sort_order < first_after.sort_order

    # صارت في القمة ⇒ لا جارة أعلى منها
    assert await services.payments.move_method(super_admin, second.id, up=True) is False


async def test_disabled_method_hidden_from_users_but_kept_in_history(
    services: ServiceContainer, super_admin: User, user: User, payment_method
) -> None:
    """إيقاف الطريقة يخفيها عن المستخدم ولا يحذفها ولا يمس طلباتها السابقة."""
    payment = await _submit(services, user, payment_method, amount="10")
    await services.payments.set_method_active(super_admin, payment_method.id, False)

    assert payment_method.id not in {m.id for m in await services.payments.active_methods()}
    assert payment_method.id in {
        m.id for m in await services.payments.all_methods(super_admin)
    }
    stored = await services.payments.admin_get(super_admin, payment.id)
    assert stored.method_id == payment_method.id


# ======================================================================== #
#                       2) الرسوم في دورة الشحن                            #
# ======================================================================== #


async def test_payment_stores_fee_snapshot_on_creation(
    services: ServiceContainer, user: User, fee_method
) -> None:
    """الرسوم تُحسب وتُخزَّن على الطلب: 2.5% من 100 + 1 = 3.5، والصافي 96.5."""
    payment = await _submit(services, user, fee_method, amount="100")

    assert payment.fee_units == int(3.5 * MONEY_SCALE)
    assert payment.net_units == int(96.5 * MONEY_SCALE)


async def test_changing_method_fee_does_not_touch_existing_payments(
    services: ServiceContainer, super_admin: User, user: User, fee_method
) -> None:
    """رفع الرسوم لاحقاً لا يغيّر طلباً أُرسل قبل التغيير (لقطة محفوظة)."""
    payment = await _submit(services, user, fee_method, amount="100")
    await services.payments.update_method(super_admin, fee_method.id, fee_percent_bp=5_000)

    reloaded = await services.payments.admin_get(super_admin, payment.id)
    assert reloaded.fee_units == payment.fee_units


async def test_approve_credits_net_amount_by_default(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, fee_method
) -> None:
    """الاعتماد يضيف الصافي بعد الرسوم تلقائياً — لا المبلغ المحوَّل كاملاً."""
    payment = await _submit(services, user, fee_method, amount="100")
    transaction = await services.payments.approve(admin, payment.id)

    assert transaction.amount_units == payment.net_units
    refreshed = await repos.users.get_by_id(user.id)
    assert refreshed.balance_units == payment.net_units


async def test_admin_can_override_credited_amount_above_net(
    services: ServiceContainer, user: User, admin: User, fee_method
) -> None:
    """يبقى للأدمن حق اعتماد مبلغ مختلف (تسوية خاصة) ويُسجَّل الفرق في الملاحظة."""
    payment = await _submit(services, user, fee_method, amount="100")
    transaction = await services.payments.approve(
        admin, payment.id, credited_units=100 * MONEY_SCALE
    )

    assert transaction.amount_units == 100 * MONEY_SCALE
    stored = await services.payments.admin_get(admin, payment.id)
    assert "رسوم الطريقة" in (stored.admin_note or "")


async def test_amount_smaller_than_fees_is_rejected(
    services: ServiceContainer, super_admin: User, user: User, fee_method
) -> None:
    """مبلغ لا يغطي الرسوم يُرفض عند الإنشاء بدل أن يُعتمد بصفر رصيد."""
    await services.payments.update_method(
        super_admin, fee_method.id, fee_fixed_units=20 * MONEY_SCALE, min_amount_units=0
    )
    with pytest.raises(ValidationError):
        await _submit(services, user, fee_method, amount="5")


async def test_methods_report_counts_real_rows_only(
    services: ServiceContainer, user: User, admin: User, super_admin: User, fee_method
) -> None:
    """التقرير يعكس قاعدة البيانات: معتمد ومعلّق ورسوم محصّلة فعلاً."""
    approved = await _submit(services, user, fee_method, amount="100")
    await services.payments.approve(admin, approved.id)
    await _submit(services, user, fee_method, amount="50")  # يبقى معلّقاً

    report = {row["method_id"]: row for row in await services.payments.methods_report(super_admin)}
    row = report[fee_method.id]
    assert row["approved_count"] == 1
    assert row["pending_count"] == 1
    assert row["total_units"] == approved.net_units
    assert row["fee_units"] == approved.fee_units


# ======================================================================== #
#                        3) شاشات طرق الشحن                                #
# ======================================================================== #


async def test_methods_home_warns_when_no_methods_exist(
    bot: FakeBot, context: FakeContext, super_admin: User
) -> None:
    """بلا طرق شحن: رسالة صريحة أن المستخدمين لا يستطيعون الشحن + زر الإضافة."""
    await load_user(bot, context, super_admin)
    await press(
        bot, context, methods_admin.methods_home_screen, pack("pm", "home"), super_admin.telegram_id
    )

    assert "لا يستطيع أي مستخدم شحن رصيده" in bot.last.text
    assert "pm:new:v1" in bot.last.buttons


async def test_methods_home_lists_methods_with_state_and_fees(
    bot: FakeBot, context: FakeContext, super_admin: User, fee_method
) -> None:
    """قائمة الطرق تعرض حالة كل طريقة ورسومها وحدودها."""
    await load_user(bot, context, super_admin)
    await press(
        bot, context, methods_admin.methods_home_screen, pack("pm", "home"), super_admin.telegram_id
    )

    assert "محفظة الرسوم" in bot.last.text
    assert "2.5%" in bot.last.text
    assert f"pm:view:{fee_method.id}:v1" in bot.last.buttons


async def test_method_card_shows_settings_and_usage(
    bot: FakeBot, context: FakeContext, super_admin: User, user: User, services: ServiceContainer, fee_method
) -> None:
    """بطاقة الطريقة تعرض الإعدادات وأرقام الاستخدام الحقيقية."""
    await _submit(services, user, fee_method, amount="40")
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        methods_admin.method_card_screen,
        pack("pm", "view", fee_method.id),
        super_admin.telegram_id,
    )

    assert "محفظة الرسوم" in bot.last.text
    assert "معلّقة 1" in bot.last.text
    assert f"pm:edit:{fee_method.id}:feep:v1" in bot.last.buttons


async def test_toggle_method_switches_visibility_for_users(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer, fee_method
) -> None:
    """زر الإيقاف يُخفي الطريقة عن المستخدمين فوراً ويُعلم الأدمن بذلك."""
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        methods_admin.toggle_method,
        pack("pm", "toggle", fee_method.id),
        super_admin.telegram_id,
    )

    assert "أُوقفت طريقة الشحن" in " ".join(message.text for message in bot.sent)
    assert fee_method.id not in {m.id for m in await services.payments.active_methods()}


async def test_toggle_proof_flips_requirement(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer, fee_method
) -> None:
    """زر الإثبات ينقل الطريقة بين «إجباري» و«اختياري»."""
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        methods_admin.toggle_proof,
        pack("pm", "proof", fee_method.id),
        super_admin.telegram_id,
    )

    reloaded = await services.payments.get_method(fee_method.id, require_active=False)
    assert not reloaded.requires_proof


async def test_edit_fee_percent_flow_updates_method(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer, fee_method
) -> None:
    """محادثة تعديل النسبة: «1.25» تُخزَّن 125 نقطة أساس."""
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        methods_admin.start_edit_field,
        pack("pm", "edit", fee_method.id, "feep"),
        super_admin.telegram_id,
    )
    await write(bot, context, methods_admin.receive_field_value, "1.25", super_admin.telegram_id)

    reloaded = await services.payments.get_method(fee_method.id, require_active=False)
    assert reloaded.fee_percent_bp == 125


async def test_edit_max_limit_with_zero_clears_it(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer, fee_method
) -> None:
    """إرسال 0 في الحد الأقصى يعني «بلا حد» (NULL) لا صفراً."""
    await services.payments.update_method(
        super_admin, fee_method.id, max_amount_units=90 * MONEY_SCALE
    )
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        methods_admin.start_edit_field,
        pack("pm", "edit", fee_method.id, "max"),
        super_admin.telegram_id,
    )
    await write(bot, context, methods_admin.receive_field_value, "0", super_admin.telegram_id)

    reloaded = await services.payments.get_method(fee_method.id, require_active=False)
    assert reloaded.max_amount_units is None


async def test_new_method_conversation_creates_visible_method(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer
) -> None:
    """محادثة الإضافة الكاملة تُنشئ طريقة ظاهرة للمستخدمين فوراً."""
    await load_user(bot, context, super_admin)
    await press(bot, context, methods_admin.start_new_method, pack("pm", "new"), super_admin.telegram_id)
    await write(bot, context, methods_admin.receive_method_name, "بنك اليمن", super_admin.telegram_id)
    await write(
        bot,
        context,
        methods_admin.receive_method_instructions,
        "1- حوّل\n2- أرسل الإيصال",
        super_admin.telegram_id,
    )
    await write(bot, context, methods_admin.receive_method_account, "123-456", super_admin.telegram_id)
    await press(
        bot,
        context,
        methods_admin.receive_method_type,
        pack("pm", "type", "manual"),
        super_admin.telegram_id,
    )
    await press(bot, context, methods_admin.confirm_new_method, pack("flow", "confirm"), super_admin.telegram_id)

    names = {method.name_ar for method in await services.payments.active_methods()}
    assert "بنك اليمن" in names


async def test_methods_report_screen_shows_totals(
    bot: FakeBot, context: FakeContext, super_admin: User, user: User, admin: User, services: ServiceContainer, fee_method
) -> None:
    """شاشة التقرير تجمع المضاف والرسوم عبر كل الطرق."""
    payment = await _submit(services, user, fee_method, amount="100")
    await services.payments.approve(admin, payment.id)

    await load_user(bot, context, super_admin)
    await press(
        bot, context, methods_admin.methods_report_screen, pack("pm", "rep"), super_admin.telegram_id
    )

    assert "تقرير طرق الشحن" in bot.last.text
    assert "إجمالي الرسوم المقتطعة" in bot.last.text


async def test_support_without_methods_permission_cannot_open_methods(
    bot: FakeBot, context: FakeContext, db, repos: Repositories
) -> None:
    """دور الدعم يرى المدفوعات لكنه لا يفتح شاشة طرق الشحن ولا يرى زرها."""
    async with db.transaction() as tx:
        support = await repos.users.create(
            tx, telegram_id=515151, username="supportman", first_name="دعم", role="support"
        )

    await load_user(bot, context, support)
    await press(
        bot, context, methods_admin.methods_home_screen, pack("pm", "home"), support.telegram_id
    )
    assert not bot.sent  # الرفض يحدث قبل إرسال أي شاشة
    assert bot.answers and "صلاحية" in bot.answers[-1]["text"]

    bot.clear()
    await press(
        bot, context, payments_admin.payments_list_screen, pack("ap", "list", "pend", 1), support.telegram_id
    )
    assert "pm:home:v1" not in bot.last.buttons


# ======================================================================== #
#                    4) تصفية طلبات الشحن والبحث                           #
# ======================================================================== #


async def test_payments_list_filters_by_status(
    bot: FakeBot, context: FakeContext, admin: User, user: User, services: ServiceContainer, payment_method
) -> None:
    """تصفية «معتمدة» تعرض المعتمد فقط ولا تعرض المعلّق."""
    approved = await _submit(services, user, payment_method, amount="20")
    await services.payments.approve(admin, approved.id)
    pending = await _submit(services, user, payment_method, amount="30")

    await load_user(bot, context, admin)
    await press(
        bot, context, payments_admin.payments_list_screen, pack("ap", "list", "ok", 1), admin.telegram_id
    )

    assert f"#{approved.id}" in bot.last.text
    assert f"#{pending.id}" not in bot.last.text
    assert f"ap:view:{approved.id}:ok:1:v1" in bot.last.buttons


async def test_payments_list_all_filter_includes_every_status(
    bot: FakeBot, context: FakeContext, admin: User, user: User, services: ServiceContainer, payment_method
) -> None:
    """تصفية «الكل» تشمل المعلّق والمعتمد معاً."""
    approved = await _submit(services, user, payment_method, amount="20")
    await services.payments.approve(admin, approved.id)
    pending = await _submit(services, user, payment_method, amount="30")

    await load_user(bot, context, admin)
    await press(
        bot, context, payments_admin.payments_list_screen, pack("ap", "list", "all", 1), admin.telegram_id
    )

    assert f"#{approved.id}" in bot.last.text and f"#{pending.id}" in bot.last.text


async def test_search_finds_payment_by_reference(
    bot: FakeBot, context: FakeContext, admin: User, user: User, services: ServiceContainer, payment_method
) -> None:
    """البحث برقم العملية يفتح الطلب المطابق كزر مباشر."""
    payment = await _submit(services, user, payment_method, amount="25")

    await load_user(bot, context, admin)
    await press(bot, context, payments_admin.start_search, pack("ap", "find"), admin.telegram_id)
    await write(
        bot, context, payments_admin.receive_search_term, payment.transaction_reference, admin.telegram_id
    )

    assert f"ap:view:{payment.id}:all:1:v1" in bot.last.buttons


async def test_search_reports_no_results_clearly(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """بحث بلا نتائج يعطي رسالة صريحة لا قائمة فارغة."""
    await load_user(bot, context, admin)
    await press(bot, context, payments_admin.start_search, pack("ap", "find"), admin.telegram_id)
    await write(bot, context, payments_admin.receive_search_term, "TRX-NOPE", admin.telegram_id)

    assert "لا يوجد طلب شحن مطابق" in bot.last.text


async def test_payment_card_shows_fee_and_net(
    bot: FakeBot, context: FakeContext, admin: User, user: User, services: ServiceContainer, fee_method
) -> None:
    """بطاقة الطلب تفصل المبلغ المحوَّل عن الرسوم وعن الصافي."""
    payment = await _submit(services, user, fee_method, amount="100")

    await load_user(bot, context, admin)
    await press(
        bot,
        context,
        payments_admin.payment_card_screen,
        pack("ap", "view", payment.id, "pend", 1),
        admin.telegram_id,
    )

    assert "رسوم الطريقة" in bot.last.text
    assert "الصافي للمستخدم" in bot.last.text


# ======================================================================== #
#                       5) جانب المستخدم (الشفافية)                        #
# ======================================================================== #


async def test_user_sees_fee_notice_when_choosing_method(
    bot: FakeBot, context: FakeContext, user: User, fee_method
) -> None:
    """المستخدم يرى رسوم الطريقة قبل أن يكتب المبلغ."""
    await load_user(bot, context, user)
    await press(
        bot, context, user_deposit.choose_method, pack("dep", "method", fee_method.id), user.telegram_id
    )

    assert "رسوم هذه الطريقة" in bot.last.text


async def test_user_summary_shows_net_amount(
    bot: FakeBot, context: FakeContext, user: User, fee_method
) -> None:
    """مراجعة الطلب تُظهر ما سيُضاف فعلاً للرصيد بعد خصم الرسوم."""
    await load_user(bot, context, user)
    await press(
        bot, context, user_deposit.choose_method, pack("dep", "method", fee_method.id), user.telegram_id
    )
    await write(bot, context, user_deposit.receive_amount, "100", user.telegram_id)
    await write(bot, context, user_deposit.receive_reference, "TRX-USER-1", user.telegram_id)
    await press(bot, context, user_deposit.skip_proof, pack("flow", "skip"), user.telegram_id)

    assert "سيُضاف لرصيدك" in bot.last.text
    assert "96.50" in bot.last.text


async def test_fee_display_can_be_switched_off(
    bot: FakeBot, context: FakeContext, user: User, services: ServiceContainer, fee_method
) -> None:
    """إعداد `deposit_fee_visible` يخفي تفصيل الرسوم عن المستخدم دون تعطيلها."""
    await services.settings.set("deposit_fee_visible", "0")

    await load_user(bot, context, user)
    await press(
        bot, context, user_deposit.choose_method, pack("dep", "method", fee_method.id), user.telegram_id
    )

    assert "رسوم هذه الطريقة" not in bot.last.text


async def test_user_cannot_deposit_when_no_active_methods(
    bot: FakeBot, context: FakeContext, user: User, super_admin: User, services: ServiceContainer, payment_method
) -> None:
    """بلا طرق مفعّلة يرى المستخدم رسالة واضحة بدل قائمة فارغة."""
    await services.payments.set_method_active(super_admin, payment_method.id, False)

    await load_user(bot, context, user)
    await press(bot, context, user_deposit.start_deposit, pack("dep", "start"), user.telegram_id)

    assert "لا توجد طرق شحن مفعّلة" in bot.last.text


async def test_full_deposit_cycle_with_fees_credits_net_balance(
    bot: FakeBot,
    context: FakeContext,
    user: User,
    admin: User,
    services: ServiceContainer,
    repos: Repositories,
    fee_method,
) -> None:
    """
    الدورة الكاملة مع رسوم: المستخدم يرسل ← الأدمن يعتمد ← يُضاف الصافي.

    هذه هي الضمانة النهائية للمرحلة 7: ما يراه المستخدم في المراجعة هو
    بالضبط ما يصل رصيده بعد الاعتماد.
    """
    await load_user(bot, context, user)
    await press(
        bot, context, user_deposit.choose_method, pack("dep", "method", fee_method.id), user.telegram_id
    )
    await write(bot, context, user_deposit.receive_amount, "200", user.telegram_id)
    await write(bot, context, user_deposit.receive_reference, "TRX-CYCLE-7", user.telegram_id)
    await press(bot, context, user_deposit.skip_proof, pack("flow", "skip"), user.telegram_id)
    await press(bot, context, user_deposit.confirm_deposit, pack("flow", "confirm"), user.telegram_id)

    payment = (await services.payments.list_for_user(user, limit=1))[0]
    assert payment.status == PaymentStatus.PENDING
    assert payment.fee_units == int(6 * MONEY_SCALE)  # 2.5% من 200 = 5 + 1 ثابت

    transaction = await services.payments.approve(admin, payment.id)
    refreshed = await repos.users.get_by_id(user.id)

    assert transaction.amount_units == int(194 * MONEY_SCALE)
    assert refreshed.balance_units == int(194 * MONEY_SCALE)
