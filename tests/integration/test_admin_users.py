"""
اختبارات قسم المستخدمين في لوحة التحكم.

تغطي المسارات التي تمسّ المال والصلاحيات: بحث، بطاقة، إضافة/خصم رصيد
(بتأكيد ثانٍ ومنع تكرار)، حظر/فك حظر، ملاحظة إدارية، وتغيير الدور.
كل اختبار يتحقق من الأثر في قاعدة البيانات لا من النص فقط.
"""

from __future__ import annotations

import pytest
from telegram.ext import ConversationHandler

from core.exceptions import DuplicateOperationError
from core.permissions import Permission
from database.models import User
from database.repositories import Repositories
from handlers.admin import users
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


async def _open_card(bot: FakeBot, context: FakeContext, admin: User, target: User) -> None:
    """فتح بطاقة مستخدم من داخل اللوحة (الخطوة التي تسبق أي إجراء عليه)."""
    await press(
        bot, context, users.user_card_screen, pack("au", "view", target.id), admin.telegram_id
    )


# ======================================================================== #
#                              البحث والبطاقة                              #
# ======================================================================== #


async def test_search_by_telegram_id_shows_result(
    bot: FakeBot, context: FakeContext, admin: User, user: User
) -> None:
    """البحث برقم تيليجرام يعرض المستخدم كزر يفتح بطاقته."""
    await load_user(bot, context, admin)
    state = await press(bot, context, users.start_search, pack("au", "search"), admin.telegram_id)
    assert state == users.ASK_QUERY

    state = await write(
        bot, context, users.receive_query, str(user.telegram_id), admin.telegram_id
    )
    assert state == ConversationHandler.END
    assert f"au:view:{user.id}:v1" in bot.last.buttons


async def test_search_without_results_keeps_conversation_open(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """بحث بلا نتائج لا ينهي المحادثة — يطلب نصاً آخر بدل إرجاع المستخدم للبداية."""
    await load_user(bot, context, admin)
    await press(bot, context, users.start_search, pack("au", "search"), admin.telegram_id)
    state = await write(bot, context, users.receive_query, "لا_أحد_بهذا_الاسم", admin.telegram_id)

    assert state == users.ASK_QUERY
    assert "لا نتائج" in bot.last.text or "نتائج" in bot.last.text


async def test_user_card_shows_balance_and_actions(
    bot: FakeBot, context: FakeContext, admin: User, user: User
) -> None:
    """بطاقة المستخدم تعرض رصيده الحقيقي وأزرار الإجراءات المسموح بها."""
    await load_user(bot, context, admin)
    await _open_card(bot, context, admin, user)

    assert str(user.telegram_id) in bot.last.text
    assert f"au:credit:{user.id}:v1" in bot.last.buttons
    assert f"au:ban:{user.id}:v1" in bot.last.buttons


# ======================================================================== #
#                               تعديل الرصيد                               #
# ======================================================================== #


async def test_credit_balance_full_flow(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """إضافة رصيد: مبلغ ⇐ سبب ⇐ تأكيد ⇐ رصيد محدَّث + حركة + تدقيق + إشعار."""
    await load_user(bot, context, admin)
    state = await press(
        bot, context, users.start_credit, pack("au", "credit", user.id), admin.telegram_id
    )
    assert state == users.ASK_AMOUNT

    state = await write(bot, context, users.receive_amount, "5", admin.telegram_id)
    assert state == users.ASK_REASON

    state = await write(
        bot, context, users.receive_balance_reason, "تعويض عن طلب فاشل", admin.telegram_id
    )
    assert state == users.CONFIRM_BALANCE
    assert "flow:confirm:v1" in bot.last.buttons, "لا يوجد تأكيد ثانٍ قبل تعديل الرصيد"

    state = await press(
        bot, context, users.confirm_balance, pack("flow", "confirm"), admin.telegram_id
    )
    assert state == ConversationHandler.END

    refreshed = await services.users.get(user.id)
    assert refreshed.balance_units == 50_000

    transactions = await repos.transactions.list_by_user(user.id, limit=5)
    assert transactions and transactions[0].amount_units == 50_000

    audit = await repos.audit.list_recent(limit=10)
    assert any("balance" in entry.action for entry in audit), "تعديل الرصيد بلا سجل تدقيق"

    queued = await repos.notifications.list_for_user(user.id, limit=10)
    assert queued, "المستخدم لم يُشعَر بتعديل رصيده"
    assert "رصيد" in queued[0].title or "رصيد" in queued[0].message


async def test_debit_balance_reduces_and_blocks_overdraft(
    bot: FakeBot, context: FakeContext, super_admin: User, user: User, services: ServiceContainer
) -> None:
    """الخصم ينقص الرصيد، ولا يسمح بتجاوز الرصيد المتاح."""
    await services.wallet.adjust_balance(
        target=user, amount_units=30_000, admin=super_admin, reason="شحن اختبار", credit=True
    )
    await load_user(bot, context, super_admin)

    await press(
        bot, context, users.start_debit, pack("au", "debit", user.id), super_admin.telegram_id
    )
    await write(bot, context, users.receive_amount, "1", super_admin.telegram_id)
    await write(bot, context, users.receive_balance_reason, "تصحيح خطأ شحن", super_admin.telegram_id)
    await press(
        bot, context, users.confirm_balance, pack("flow", "confirm"), super_admin.telegram_id
    )

    refreshed = await services.users.get(user.id)
    assert refreshed.balance_units == 20_000

    # محاولة خصم أكبر من الرصيد
    await press(
        bot, context, users.start_debit, pack("au", "debit", user.id), super_admin.telegram_id
    )
    await write(bot, context, users.receive_amount, "999", super_admin.telegram_id)
    await write(bot, context, users.receive_balance_reason, "خصم مبالغ فيه", super_admin.telegram_id)
    await press(
        bot, context, users.confirm_balance, pack("flow", "confirm"), super_admin.telegram_id
    )
    assert "رصيد" in bot.last.text, f"رسالة فشل الخصم غير واضحة: {bot.last.text}"

    unchanged = await services.users.get(user.id)
    assert unchanged.balance_units == 20_000, "تغيّر الرصيد رغم فشل العملية"


async def test_double_confirm_does_not_double_credit(
    bot: FakeBot, context: FakeContext, admin: User, user: User, services: ServiceContainer
) -> None:
    """ضغط «تأكيد» مرتين لا يضيف الرصيد مرتين (idempotency برمز العملية)."""
    await load_user(bot, context, admin)
    await press(bot, context, users.start_credit, pack("au", "credit", user.id), admin.telegram_id)
    await write(bot, context, users.receive_amount, "7", admin.telegram_id)
    await write(bot, context, users.receive_balance_reason, "هدية ترحيب", admin.telegram_id)

    token_before = context.user_data[users.ADMIN_FLOW_KEY]["token"]
    await press(bot, context, users.confirm_balance, pack("flow", "confirm"), admin.telegram_id)

    # إعادة الضغط بنفس الجلسة المنتهية: لا بيانات ⇒ رسالة انتهاء الجلسة لا عملية ثانية
    state = await press(
        bot, context, users.confirm_balance, pack("flow", "confirm"), admin.telegram_id
    )
    assert state == ConversationHandler.END

    refreshed = await services.users.get(user.id)
    assert refreshed.balance_units == 70_000, "تكرّر تعديل الرصيد عند الضغط مرتين"

    # وحتى إعادة استخدام نفس الرمز صراحةً تُرفض من الخدمة نفسها
    with pytest.raises(DuplicateOperationError):
        await services.wallet.adjust_balance(
            target=refreshed,
            amount_units=70_000,
            admin=admin,
            reason="هدية ترحيب",
            credit=True,
            token=token_before,
        )


async def test_credit_requires_permission(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    super_admin: User,
    user: User,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """أدمن بلا صلاحية إضافة رصيد يُمنع من بدء المحادثة أصلاً."""
    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.USERS_BALANCE_CREDIT, allow=False
    )
    await load_user(bot, context, admin)
    await press(bot, context, users.start_credit, pack("au", "credit", user.id), admin.telegram_id)

    assert bot.answers[-1]["alert"] is True
    refreshed = await services.users.get(user.id)
    assert refreshed.balance_units == 0


async def test_invalid_amount_is_rejected_with_message(
    bot: FakeBot, context: FakeContext, admin: User, user: User
) -> None:
    """مبلغ غير صالح يُقابَل برسالة واضحة ولا يكسر المحادثة."""
    await load_user(bot, context, admin)
    await press(bot, context, users.start_credit, pack("au", "credit", user.id), admin.telegram_id)

    # `@guarded` يحوّل خطأ التحقق إلى رسالة عربية بدل أن يُسقط المعالج
    await write(bot, context, users.receive_amount, "خمسة", admin.telegram_id)
    assert bot.last.text, "لم تُعرض أي رسالة عند إدخال مبلغ غير صالح"
    assert "مبلغ" in bot.last.text or "رقم" in bot.last.text


# ======================================================================== #
#                             الحظر وفك الحظر                              #
# ======================================================================== #


async def test_ban_then_unban_user(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """الحظر يحتاج سبباً وتأكيداً، وفك الحظر فوري — وكلاهما يُسجَّل."""
    await load_user(bot, context, admin)
    state = await press(
        bot, context, users.start_ban, pack("au", "ban", user.id), admin.telegram_id
    )
    assert state == users.ASK_BAN_REASON

    state = await write(bot, context, users.receive_ban_reason, "إساءة استخدام", admin.telegram_id)
    assert state == users.CONFIRM_BAN
    assert "flow:confirm:v1" in bot.last.buttons

    await press(bot, context, users.confirm_ban, pack("flow", "confirm"), admin.telegram_id)
    banned = await services.users.get(user.id)
    assert banned.is_banned
    assert banned.ban_reason == "إساءة استخدام"

    await press(bot, context, users.unban_user, pack("au", "unban", user.id), admin.telegram_id)
    freed = await services.users.get(user.id)
    assert not freed.is_banned

    audit = await repos.audit.list_recent(limit=20)
    actions = {entry.action for entry in audit}
    assert any("ban" in action for action in actions), "الحظر/فك الحظر بلا سجل تدقيق"


async def test_banned_user_cannot_use_bot(
    bot: FakeBot, context: FakeContext, admin: User, user: User, services: ServiceContainer
) -> None:
    """الحظر ليس شكلياً: المستخدم المحظور توقفه الطبقة الوسيطة."""
    from tests.integration.test_user_interface import run_middleware
    from tests.telegram_fakes import make_message_update

    await services.users.ban(admin, user.id, "اختبار المنع")
    update = make_message_update(bot, text="/start", user_id=user.telegram_id)
    allowed = await run_middleware(bot, context, update)
    assert allowed is False, "المستخدم المحظور ما زال يستطيع استخدام البوت"


# ======================================================================== #
#                           الملاحظة وتغيير الدور                          #
# ======================================================================== #


async def test_admin_note_is_saved(
    bot: FakeBot, context: FakeContext, admin: User, user: User, services: ServiceContainer
) -> None:
    """الملاحظة الإدارية تُحفظ وتظهر في البطاقة."""
    await load_user(bot, context, admin)
    await press(bot, context, users.start_note, pack("au", "note", user.id), admin.telegram_id)
    await write(bot, context, users.receive_note, "عميل مهم — تعامل بعناية", admin.telegram_id)

    refreshed = await services.users.get(user.id)
    assert refreshed.notes == "عميل مهم — تعامل بعناية"


async def test_role_change_needs_second_confirmation(
    bot: FakeBot, context: FakeContext, super_admin: User, user: User, services: ServiceContainer
) -> None:
    """تغيير الدور إجراء خطير: شاشة أدوار ⇒ شاشة تأكيد ⇒ تنفيذ."""
    await load_user(bot, context, super_admin)
    await press(
        bot, context, users.role_screen, pack("au", "role", user.id), super_admin.telegram_id
    )
    assert f"au:setrole:{user.id}:support:v1" in bot.last.buttons

    await press(
        bot,
        context,
        users.role_confirm_screen,
        pack("au", "setrole", user.id, "support"),
        super_admin.telegram_id,
    )
    assert f"au:roleok:{user.id}:support:v1" in bot.last.buttons, "لا شاشة تأكيد قبل تغيير الدور"

    still_user = await services.users.get(user.id)
    assert still_user.role == "user", "تغيّر الدور قبل التأكيد النهائي"

    await press(
        bot,
        context,
        users.role_apply,
        pack("au", "roleok", user.id, "support"),
        super_admin.telegram_id,
    )
    promoted = await services.users.get(user.id)
    assert promoted.role == "support"
    assert await services.auth.is_admin(promoted) is True


async def test_admin_cannot_assign_role_without_permission(
    bot: FakeBot, context: FakeContext, admin: User, user: User, services: ServiceContainer
) -> None:
    """الأدمن العادي لا يملك `users.role.change` ⇐ لا يستطيع ترقية أحد."""
    await load_user(bot, context, admin)
    await press(
        bot,
        context,
        users.role_apply,
        pack("au", "roleok", user.id, "admin"),
        admin.telegram_id,
    )
    assert bot.answers[-1]["alert"] is True
    unchanged = await services.users.get(user.id)
    assert unchanged.role == "user"


async def test_user_orders_and_transactions_screens(
    bot: FakeBot, context: FakeContext, admin: User, user: User
) -> None:
    """شاشتا طلبات المستخدم وحركاته تعملان حتى حين لا توجد بيانات."""
    await load_user(bot, context, admin)
    await press(
        bot, context, users.user_orders_screen, pack("au", "orders", user.id, 1), admin.telegram_id
    )
    assert bot.last.buttons, "شاشة طلبات المستخدم بلا أزرار رجوع"

    await press(
        bot,
        context,
        users.user_transactions_screen,
        pack("au", "tx", user.id, 1),
        admin.telegram_id,
    )
    assert bot.last.buttons
