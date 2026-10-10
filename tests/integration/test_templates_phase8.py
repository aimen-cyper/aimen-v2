"""
اختبارات المرحلة 8 — قوالب الإشعارات القابلة للتحرير.

ما تغطيه:
    1. الخدمة: حفظ، تحقق من المتغيرات، إيقاف/تفعيل، استعادة الافتراضي، التدقيق.
    2. الصلاحية: `notifications.templates` من قاعدة البيانات لا من الكود.
    3. الأثر الحقيقي: اعتماد شحن فعلي يُنتج إشعاراً بالصياغة المعدَّلة.
    4. شاشات اللوحة والمحادثة، وأن رفض نص خاطئ لا يُسقط المحادثة.
"""

from __future__ import annotations

import pytest

from core.exceptions import PermissionDeniedError, ValidationError
from database.models import User
from handlers.admin import templates as templates_admin
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
from texts import templates as tpl

pytestmark = pytest.mark.asyncio


async def _audit_actions(services: ServiceContainer) -> list[str]:
    """أفعال سجل التدقيق كما هي في قاعدة البيانات (الأحدث أولاً)."""
    rows = await services.db.fetchall("SELECT action FROM audit_logs ORDER BY id DESC")
    return [row["action"] for row in rows]


async def _support_user(services: ServiceContainer) -> User:
    """مستخدم بدور دعم فني (لا يملك صلاحية القوالب افتراضياً)."""
    async with services.db.transaction() as tx:
        return await services.repos.users.create(
            tx, telegram_id=616161, username="sup8", first_name="دعم", role="support"
        )


# ======================================================================== #
#                               الخدمة                                     #
# ======================================================================== #


async def test_set_text_saves_and_changes_outgoing_messages(
    services: ServiceContainer, super_admin: User
) -> None:
    """الحفظ يُحمَّل فوراً: أول رسالة تُبنى بعده تحمل الصياغة الجديدة."""
    await services.templates.set_text(
        super_admin, "order_failed", body="⚠️ {code} تعثّر ({reason}) — رُدّ لك {refund}"
    )
    _title, body = tpl.order_failed(code="ORD-5", reason="رابط", refund_units=10_000)
    assert body == "⚠️ ORD-5 تعثّر (رابط) — رُدّ لك 1.00"


async def test_editing_title_only_keeps_default_body(
    services: ServiceContainer, super_admin: User
) -> None:
    """تعديل العنوان وحده لا يمسّ النص الافتراضي."""
    await services.templates.set_text(super_admin, "order_completed", title="🏆 تم")
    title, body = tpl.order_completed(code="ORD-1", service_name="خدمة", quantity=10)
    assert title == "🏆 تم"
    assert "تم تنفيذ الطلب ORD-1 بالكامل." in body


async def test_multiline_body_keeps_its_lines(
    services: ServiceContainer, super_admin: User
) -> None:
    """الأسطر داخل نص القالب تبقى كما كتبها الأدمن."""
    await services.templates.set_text(super_admin, "order_in_progress", body="سطر ١ {code}\n\nسطر ٣")
    _title, body = tpl.order_in_progress(code="X")
    assert body == "سطر ١ X\n\nسطر ٣"


@pytest.mark.parametrize(
    "bad_body",
    ["مرحباً {hacker}", "{code.__class__}", "{code!r}", "{code:>99999}", "{}", "   "],
)
async def test_invalid_text_is_rejected_and_nothing_saved(
    services: ServiceContainer, super_admin: User, bad_body: str
) -> None:
    """نص بمتغير غير مسموح أو تنسيق خطر أو فارغ يُرفض ولا يُحفظ شيء."""
    with pytest.raises(ValidationError):
        await services.templates.set_text(super_admin, "order_in_progress", body=bad_body)
    assert await services.repos.templates.get("order_in_progress") is None
    assert tpl.order_in_progress(code="Z")[1] == "🔄 بدأ تنفيذ الطلب Z الآن — نعمل على إنجازه ⚡"


async def test_too_long_text_is_rejected(services: ServiceContainer, super_admin: User) -> None:
    """النص الأطول من الحد الأقصى يُرفض بدل أن يقتطعه تيليجرام لاحقاً."""
    with pytest.raises(ValidationError):
        await services.templates.set_text(
            super_admin, "order_in_progress", body="ا" * (tpl.MAX_TEMPLATE_BODY + 1)
        )


async def test_unknown_template_code_is_rejected(
    services: ServiceContainer, super_admin: User
) -> None:
    """رمز قالب غير موجود في الكتالوج لا يُنشئ صفاً."""
    with pytest.raises(ValidationError):
        await services.templates.set_text(super_admin, "not_a_template", body="x")


async def test_permission_comes_from_database(
    services: ServiceContainer, admin: User, user: User
) -> None:
    """الأدمن العادي يملك الصلاحية، ودور الدعم والمستخدم لا يملكانها."""
    await services.templates.set_text(admin, "order_in_progress", body="أدمن {code}")
    support = await _support_user(services)
    for actor in (support, user):
        with pytest.raises(PermissionDeniedError):
            await services.templates.set_text(actor, "order_in_progress", body="x {code}")
        with pytest.raises(PermissionDeniedError):
            await services.templates.overview(actor)
        with pytest.raises(PermissionDeniedError):
            await services.templates.reset(actor, "order_in_progress")


async def test_reset_restores_default_and_audits(
    services: ServiceContainer, super_admin: User
) -> None:
    """الاستعادة تحذف التخصيص فقط، والنص الأصلي يعود فوراً، والأثر مسجَّل."""
    await services.templates.set_text(super_admin, "order_in_progress", body="مخصّص {code}")
    assert await services.templates.reset(super_admin, "order_in_progress") is True
    assert tpl.order_in_progress(code="Q")[1] == "🔄 بدأ تنفيذ الطلب Q الآن — نعمل على إنجازه ⚡"
    assert await services.repos.templates.get("order_in_progress") is None
    assert await services.templates.reset(super_admin, "order_in_progress") is False
    actions = await _audit_actions(services)
    assert actions.count("notifications.templates") == 2


async def test_disable_keeps_text_and_enable_brings_it_back(
    services: ServiceContainer, super_admin: User
) -> None:
    """الإيقاف يُرجع الافتراضي دون فقد التعديل، والتفعيل يستعيده."""
    await services.templates.set_text(super_admin, "order_in_progress", body="مخصّص {code}")
    assert await services.templates.set_active(super_admin, "order_in_progress", active=False)
    assert tpl.order_in_progress(code="Q")[1] == "🔄 بدأ تنفيذ الطلب Q الآن — نعمل على إنجازه ⚡"
    row = await services.repos.templates.get("order_in_progress")
    assert row is not None and row.body == "مخصّص {code}"

    assert await services.templates.set_active(super_admin, "order_in_progress", active=True)
    assert tpl.order_in_progress(code="Q")[1] == "مخصّص Q"
    # نفس الحالة مرة ثانية لا تُحدث تغييراً ولا تدقيقاً زائداً
    assert not await services.templates.set_active(super_admin, "order_in_progress", active=True)


async def test_disable_without_customization_is_rejected(
    services: ServiceContainer, super_admin: User
) -> None:
    """لا معنى لإيقاف تخصيص غير موجود — خطأ واضح بدل نجاح صامت."""
    with pytest.raises(ValidationError):
        await services.templates.set_active(super_admin, "order_created", active=False)


async def test_set_text_records_before_and_after_in_audit(
    services: ServiceContainer, super_admin: User
) -> None:
    """التدقيق يحفظ النص قبل وبعد (الافتراضي يُسجَّل كـ«قبل» في أول تعديل)."""
    await services.templates.set_text(super_admin, "order_in_progress", body="جديد {code}")
    row = await services.db.fetchone(
        "SELECT before_json, after_json FROM audit_logs WHERE action = 'notifications.templates'"
    )
    assert "بدأ تنفيذ الطلب" in row["before_json"]
    assert "جديد" in row["after_json"]


async def test_preview_uses_sample_values_and_sends_nothing(
    services: ServiceContainer, super_admin: User
) -> None:
    """المعاينة تعرض القيم التجريبية ولا تُنشئ أي إشعار حقيقي."""
    await services.templates.set_text(super_admin, "order_failed", body="فشل {code} / {reason}")
    title, body = await services.templates.preview(super_admin, "order_failed")
    assert body == "فشل ORD-10231 / الرابط غير صحيح"
    assert await services.db.fetchval("SELECT COUNT(*) FROM notifications") == 0


async def test_overview_flags_customized_templates(
    services: ServiceContainer, super_admin: User
) -> None:
    """القائمة تميّز المعدَّل من الافتراضي وتغطي كل الكتالوج."""
    await services.templates.set_text(super_admin, "order_failed", title="🔴 فشل")
    items = {item["code"]: item for item in await services.templates.overview(super_admin)}
    assert len(items) == len(tpl.TEMPLATES)
    assert items["order_failed"]["is_customized"] and items["order_failed"]["is_active"]
    assert not items["order_created"]["is_customized"]


async def test_startup_recovery_loads_saved_templates(
    services: ServiceContainer, super_admin: User
) -> None:
    """بعد إعادة التشغيل (ذاكرة فارغة) يُعاد تحميل القوالب المحفوظة قبل أي إرسال."""
    await services.templates.set_text(super_admin, "order_in_progress", body="محفوظ {code}")
    tpl.clear_overrides()  # محاكاة إقلاع جديد
    assert tpl.order_in_progress(code="A")[1] != "محفوظ A"

    report = await services.startup_recovery()
    assert report["templates_loaded"] == 1
    assert tpl.order_in_progress(code="A")[1] == "محفوظ A"


async def test_real_payment_approval_uses_customized_wording(
    services: ServiceContainer, super_admin: User, admin: User, user: User, payment_method
) -> None:
    """الأثر الحقيقي: اعتماد شحن فعلي يُنتج إشعاراً بنص الأدمن المعدَّل."""
    await services.templates.set_text(
        super_admin,
        "payment_approved",
        title="💚 وصلت دفعتك",
        body="شكراً! أُضيف {amount} ورصيدك {balance}",
    )
    payment = await services.payments.create_payment(
        user,
        method_id=payment_method.id,
        raw_amount="5",
        transaction_reference="TRX-T8-1",
        proof_file_id="proof",
        proof_file_type="photo",
    )
    await services.payments.approve(admin, payment.id)

    row = await services.db.fetchone(
        "SELECT title, message FROM notifications WHERE type = 'payment_approved'"
    )
    assert row["title"] == "💚 وصلت دفعتك"
    assert row["message"] == "شكراً! أُضيف 5.00 ريال ورصيدك 5.00 ريال"


# ======================================================================== #
#                              شاشات اللوحة                                #
# ======================================================================== #


async def test_templates_home_lists_groups_and_counts(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer  # noqa: F811
) -> None:
    """القائمة تعرض المجموعات وعدّاد المعدَّل وزراً لكل قالب."""
    await services.templates.set_text(super_admin, "order_failed", title="🔴 فشل")
    await load_user(bot, context, super_admin)
    await press(bot, context, templates_admin.templates_home_screen, pack("tp", "home"), super_admin.telegram_id)

    assert "قوالب الإشعارات" in bot.last.text
    assert "معدّلة: 1 من" in bot.last.text
    assert "📦 الطلبات" in bot.last.text and "👛 الرصيد" in bot.last.text
    assert pack("tp", "view", "order_failed") in bot.last.buttons


async def test_card_shows_variables_and_hides_reset_when_default(
    bot: FakeBot, context: FakeContext, super_admin: User  # noqa: F811
) -> None:
    """بطاقة القالب الافتراضي: متغيراته ظاهرة، ولا زر استعادة بلا تخصيص."""
    await load_user(bot, context, super_admin)
    await press(
        bot, context, templates_admin.template_card_screen,
        pack("tp", "view", "order_created"), super_admin.telegram_id,
    )
    assert "{service_name}" in bot.last.text
    assert "النص الافتراضي المدمج" in bot.last.text
    assert pack("tp", "reset", "order_created") not in bot.last.buttons
    assert pack("tp", "edit", "order_created", "body") in bot.last.buttons


async def test_edit_conversation_saves_and_shows_card(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer  # noqa: F811
) -> None:
    """محادثة التعديل الكاملة: الزر ← النص ← حفظ ← بطاقة جديدة بزر الاستعادة."""
    await load_user(bot, context, super_admin)
    state = await press(
        bot, context, templates_admin.start_edit,
        pack("tp", "edit", "order_in_progress", "body"), super_admin.telegram_id,
    )
    assert state == templates_admin.ASK_VALUE
    assert "{code}" in bot.last.text

    result = await write(
        bot, context, templates_admin.receive_value, "🚀 طلبك {code} انطلق", super_admin.telegram_id
    )
    assert result is not None and result != templates_admin.ASK_VALUE
    assert tpl.order_in_progress(code="K")[1] == "🚀 طلبك K انطلق"
    assert pack("tp", "reset", "order_in_progress") in bot.last.buttons


async def test_edit_conversation_stays_open_on_bad_variable(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer  # noqa: F811
) -> None:
    """نص بمتغير مجهول: رسالة توضح المسموح، والمحادثة تبقى للمحاولة من جديد."""
    await load_user(bot, context, super_admin)
    await press(
        bot, context, templates_admin.start_edit,
        pack("tp", "edit", "order_in_progress", "body"), super_admin.telegram_id,
    )
    result = await write(
        bot, context, templates_admin.receive_value, "مرحباً {hacker}", super_admin.telegram_id
    )
    assert result is None  # الحارس يُبقي المستخدم في نفس الخطوة
    assert "غير مسموحة" in bot.last.text and "{code}" in bot.last.text
    assert await services.repos.templates.get("order_in_progress") is None


async def test_preview_toggle_reset_buttons_work(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer  # noqa: F811
) -> None:
    """أزرار المعاينة والإيقاف والاستعادة تعمل وتُحدّث البطاقة."""
    await services.templates.set_text(super_admin, "order_in_progress", body="مخصّص {code}")
    await load_user(bot, context, super_admin)

    await press(bot, context, templates_admin.template_preview_screen,
                pack("tp", "prev", "order_in_progress"), super_admin.telegram_id)
    assert "مخصّص ORD-10231" in bot.last.text and "معاينة" in bot.last.text

    await press(bot, context, templates_admin.toggle_template,
                pack("tp", "toggle", "order_in_progress"), super_admin.telegram_id)
    assert "موقوف" in bot.last.text
    assert tpl.order_in_progress(code="Q")[1] == "🔄 بدأ تنفيذ الطلب Q الآن — نعمل على إنجازه ⚡"

    await press(bot, context, templates_admin.reset_template,
                pack("tp", "reset", "order_in_progress"), super_admin.telegram_id)
    assert "النص الافتراضي المدمج" in bot.last.text
    assert await services.repos.templates.get("order_in_progress") is None


async def test_support_role_cannot_open_templates_screen(
    bot: FakeBot, context: FakeContext, services: ServiceContainer  # noqa: F811
) -> None:
    """الدعم لا يفتح الشاشة (فحص الصلاحية على الـcallback) ولا يصله شيء."""
    support = await _support_user(services)
    await load_user(bot, context, support)
    await press(bot, context, templates_admin.templates_home_screen,
                pack("tp", "home"), support.telegram_id)
    assert not bot.sent
    assert bot.answers


async def test_panel_menu_shows_templates_button_by_permission(
    services: ServiceContainer, super_admin: User
) -> None:
    """زرا الإذاعة والقوالب في قائمة اللوحة يظهران بالصلاحية فقط."""
    from keyboards.admin_kb import admin_menu_kb

    support = await _support_user(services)
    full = {b.callback_data for row in admin_menu_kb(await services.auth.permissions_of(super_admin)).inline_keyboard for b in row}
    limited = {b.callback_data for row in admin_menu_kb(await services.auth.permissions_of(support)).inline_keyboard for b in row}
    assert pack("tp", "home") in full and pack("bc", "home") in full
    assert pack("tp", "home") not in limited and pack("bc", "home") not in limited


# ======================================================================== #
#                         الترحيل 0007 (المخطط والبذور)                    #
# ======================================================================== #


async def test_migration_0007_creates_table_permission_and_settings(
    services: ServiceContainer,
) -> None:
    """الترحيل يضيف الجدول والصلاحية وأدوارها والإعدادات الأربعة بقيمها الافتراضية."""
    db = services.db
    latest = await db.fetchval("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1")
    assert str(latest) >= "0007"
    assert await db.fetchval("SELECT COUNT(*) FROM notification_templates") == 0  # لا بذور للقوالب

    roles = {
        row["role_code"]
        for row in await db.fetchall(
            "SELECT role_code FROM role_permissions WHERE permission_code = 'notifications.templates'"
        )
    }
    assert roles == {"super_admin", "admin"}

    expected = {
        "broadcast_batch_size": "20",
        "broadcast_interval_seconds": "5",
        "broadcast_active_days": "30",
        "ticket_reply_notify_admins": "1",
    }
    for key, value in expected.items():
        assert await services.repos.settings.get_raw(key) == value, key

    index = await db.fetchval(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'idx_broadcasts_status'"
    )
    assert index == "idx_broadcasts_status"
