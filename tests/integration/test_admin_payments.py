"""
اختبارات قسم المدفوعات في لوحة التحكم.

المسار الحسّاس هنا: اعتماد طلب شحن = إضافة رصيد حقيقي. لذلك نتحقق من
التأكيد الثاني، ومن تعديل المبلغ المعتمد، ومن استحالة الاعتماد مرتين،
ومن أن الرفض يحتاج سبباً ويصل للمستخدم.
"""

from __future__ import annotations

import pytest
from telegram.ext import ConversationHandler

from core.enums import PaymentStatus
from core.permissions import Permission
from database.models import Payment, User
from database.repositories import Repositories
from handlers.admin import payments
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


@pytest.fixture
async def pending_payment(services: ServiceContainer, user: User, payment_method) -> Payment:
    """طلب شحن معلّق بمبلغ 5 (50000 نقطة) مع إثبات صورة."""
    return await services.payments.create_payment(
        user,
        method_id=payment_method.id,
        raw_amount="5",
        transaction_reference="TRX-77-A",
        proof_file_id="proof-file-1",
        proof_file_type="photo",
    )


async def test_pending_list_shows_payment(
    bot: FakeBot, context: FakeContext, admin: User, pending_payment: Payment
) -> None:
    """قائمة الطلبات المعلّقة تعرض الطلب كزر يفتح بطاقته."""
    await load_user(bot, context, admin)
    await press(bot, context, payments.payments_list_screen, pack("ap", "list", 1), admin.telegram_id)

    assert f"ap:view:{pending_payment.id}:pend:1:v1" in bot.last.buttons
    assert "المعلّقة" in bot.last.text or "الشحن" in bot.last.text


async def test_payment_card_shows_proof_button(
    bot: FakeBot, context: FakeContext, admin: User, pending_payment: Payment
) -> None:
    """بطاقة الطلب تعرض أزرار الاعتماد والرفض وعرض الإثبات."""
    await load_user(bot, context, admin)
    await press(
        bot, context, payments.payment_card_screen, pack("ap", "view", pending_payment.id), admin.telegram_id
    )

    assert f"ap:ok:{pending_payment.id}:v1" in bot.last.buttons
    assert f"ap:no:{pending_payment.id}:v1" in bot.last.buttons
    assert f"ap:proof:{pending_payment.id}:v1" in bot.last.buttons


async def test_proof_screen_sends_photo(
    bot: FakeBot, context: FakeContext, admin: User, pending_payment: Payment
) -> None:
    """زر «عرض الإثبات» يرسل الصورة فعلاً لا رسالة نصية فارغة."""
    await load_user(bot, context, admin)
    await press(
        bot, context, payments.payment_proof_screen, pack("ap", "proof", pending_payment.id), admin.telegram_id
    )
    assert bot.last.kind == "photo"


async def test_approve_credits_balance_after_confirmation(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    pending_payment: Payment,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """الاعتماد: شاشة تأكيد ⇒ تنفيذ ⇒ رصيد + حركة + حالة الطلب + إشعار."""
    await load_user(bot, context, admin)
    state = await press(
        bot, context, payments.start_approve, pack("ap", "ok", pending_payment.id), admin.telegram_id
    )
    assert state == payments.CONFIRM_APPROVE
    assert "flow:confirm:v1" in bot.last.buttons

    before = await services.users.get(user.id)
    assert before.balance_units == 0, "تغيّر الرصيد قبل التأكيد"

    state = await press(
        bot, context, payments.confirm_approve, pack("flow", "confirm"), admin.telegram_id
    )
    assert state == ConversationHandler.END

    after = await services.users.get(user.id)
    assert after.balance_units == 50_000

    stored = await repos.payments.get(pending_payment.id)
    assert stored.status == PaymentStatus.APPROVED
    assert stored.admin_id == admin.id

    queued = await repos.notifications.list_for_user(user.id, limit=5)
    assert queued, "لم يصل المستخدم إشعار باعتماد الشحن"


async def test_approve_with_edited_amount(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    pending_payment: Payment,
    services: ServiceContainer,
) -> None:
    """تعديل المبلغ المعتمد (حوالة ناقصة) يُضيف المبلغ المعدَّل لا المطلوب."""
    await load_user(bot, context, admin)
    await press(
        bot, context, payments.start_approve, pack("ap", "ok", pending_payment.id), admin.telegram_id
    )
    state = await press(
        bot, context, payments.ask_credited_amount, pack("ap", "amount"), admin.telegram_id
    )
    assert state == payments.ASK_CREDITED

    state = await write(bot, context, payments.receive_credited_amount, "4", admin.telegram_id)
    assert state == payments.CONFIRM_APPROVE

    await press(bot, context, payments.confirm_approve, pack("flow", "confirm"), admin.telegram_id)
    after = await services.users.get(user.id)
    assert after.balance_units == 40_000, "اعتُمد المبلغ الأصلي بدل المعدَّل"


async def test_payment_cannot_be_approved_twice(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    pending_payment: Payment,
    services: ServiceContainer,
) -> None:
    """اعتماد نفس الطلب مرتين مستحيل — الرصيد لا يُضاعف."""
    await load_user(bot, context, admin)
    await press(
        bot, context, payments.start_approve, pack("ap", "ok", pending_payment.id), admin.telegram_id
    )
    await press(bot, context, payments.confirm_approve, pack("flow", "confirm"), admin.telegram_id)

    # محاولة ثانية كاملة من البطاقة
    await press(
        bot, context, payments.start_approve, pack("ap", "ok", pending_payment.id), admin.telegram_id
    )
    await press(bot, context, payments.confirm_approve, pack("flow", "confirm"), admin.telegram_id)

    after = await services.users.get(user.id)
    assert after.balance_units == 50_000, "تضاعف الرصيد باعتماد مزدوج"


async def test_reject_requires_reason_and_notifies_user(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    pending_payment: Payment,
    repos: Repositories,
    services: ServiceContainer,
) -> None:
    """الرفض يحتاج سبباً مكتوباً، ويصل المستخدم إشعار، ولا يُضاف أي رصيد."""
    await load_user(bot, context, admin)
    state = await press(
        bot, context, payments.start_reject, pack("ap", "no", pending_payment.id), admin.telegram_id
    )
    assert state == payments.ASK_REJECT_REASON

    state = await write(
        bot, context, payments.receive_reject_reason, "لا يوجد تحويل بهذا الرقم", admin.telegram_id
    )
    assert state == ConversationHandler.END

    stored = await repos.payments.get(pending_payment.id)
    assert stored.status == PaymentStatus.REJECTED
    assert stored.reject_reason == "لا يوجد تحويل بهذا الرقم"

    owner = await services.users.get(user.id)
    assert owner.balance_units == 0

    queued = await repos.notifications.list_for_user(user.id, limit=5)
    assert queued, "لم يصل المستخدم إشعار بالرفض"


async def test_short_reject_reason_is_refused(
    bot: FakeBot, context: FakeContext, admin: User, pending_payment: Payment, repos: Repositories
) -> None:
    """سبب رفض قصير جداً يُرفض ويبقى الطلب معلّقاً."""
    await load_user(bot, context, admin)
    await press(
        bot, context, payments.start_reject, pack("ap", "no", pending_payment.id), admin.telegram_id
    )
    await write(bot, context, payments.receive_reject_reason, "لا", admin.telegram_id)

    stored = await repos.payments.get(pending_payment.id)
    assert stored.status == PaymentStatus.PENDING, "رُفض الطلب بسبب غير مكتمل"


async def test_approve_blocked_without_permission(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    super_admin: User,
    pending_payment: Payment,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """سحب صلاحية الاعتماد يمنع العملية حتى لو وصل الأدمن للبطاقة."""
    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.PAYMENTS_APPROVE, allow=False
    )
    await load_user(bot, context, admin)
    await press(
        bot, context, payments.start_approve, pack("ap", "ok", pending_payment.id), admin.telegram_id
    )

    assert bot.answers[-1]["alert"] is True
    stored = await repos.payments.get(pending_payment.id)
    assert stored.status == PaymentStatus.PENDING
