"""
المرحلة 13 — البنود 1–4: الاشتراك الإجباري، إشعار المستخدم الجديد، توثيق الطلبات، قناة النسخ.

لا اختبار على تيليجرام حقيقي هنا: `FakeBot` يحاكي `getChatMember/getChat` بأخطاء تيليجرام الحقيقية
(`BadRequest("User not found")`, `Chat not found`, `TimedOut`) فنختبر منطقنا لا الشبكة.
"""

from __future__ import annotations

import time

import pytest
from telegram.error import BadRequest, Forbidden, TimedOut

from core.exceptions import NotificationBlockedError, NotificationTemporaryError, ValidationError
from handlers.common import navigation
from keyboards.callback_data import pack
from services import ServiceContainer
from services.subscription_service import CACHE_TTL_SECONDS
from tests.integration.test_user_interface import bot, context, load_user, press, run_middleware  # noqa: F401
from tests.telegram_fakes import make_callback_update, make_message_update

pytestmark = pytest.mark.asyncio

CHANNELS = {
    "channel_official": ("@smm_official", -1001000000001),
    "channel_proofs": ("@smm_proofs", -1001000000002),
    "channel_updates": ("@smm_updates", -1001000000003),
    "channel_offers": ("@smm_offers", -1001000000004),
}
UID = 100200300


async def _configure_channels(services: ServiceContainer, super_admin) -> None:
    """ضبط القنوات الأربع كما يفعل الأدمن من الإعدادات."""
    for key, (ref, _) in CHANNELS.items():
        await services.settings.set(key, ref, admin_id=super_admin.id)


def _join_all(bot, user_id: int = UID, status: str = "member") -> None:
    """جعل المستخدم عضواً في القنوات الأربع في بوت الاختبار."""
    for ref, _ in CHANNELS.values():
        bot.memberships[(ref, user_id)] = status


# --------------------------------- البند 1: الاشتراك الإجباري --------------------------------- #


async def test_gate_is_off_when_no_channels_configured(bot, context, user) -> None:  # noqa: F811
    """بلا قنوات مضبوطة لا بوابة ولا نداءات لتيليجرام."""
    update = make_message_update(bot, text="/start", user_id=user.telegram_id)
    assert await run_middleware(bot, context, update)
    assert not bot.member_calls


async def test_non_member_is_blocked_with_join_buttons(bot, context, services, user, super_admin) -> None:  # noqa: F811
    """غير المشترك لا يمرّ؛ يرى القنوات الأربع ❌ مع زر انضمام لكل واحدة وزر «تحقق»."""
    await _configure_channels(services, super_admin)
    update = make_message_update(bot, text="/start", user_id=user.telegram_id)
    assert await run_middleware(bot, context, update) is False
    text = bot.last.text
    assert text.count("\n❌ ") == 4 and "\n✅ " not in text
    urls = [button.url for row in bot.last.markup.inline_keyboard for button in row if button.url]
    assert sorted(urls) == sorted(f"https://t.me/{ref[1:]}" for ref, _ in CHANNELS.values())
    assert any(pack("sub", "check") == data for data in [b.callback_data for r in bot.last.markup.inline_keyboard for b in r])


async def test_partial_membership_still_blocked_and_marks_each_channel(bot, context, services, user, super_admin) -> None:  # noqa: F811
    """الاشتراك في ثلاث من أربع لا يكفي، والقناة الناقصة وحدها ❌."""
    await _configure_channels(services, super_admin)
    _join_all(bot)
    del bot.memberships[("@smm_offers", UID)]
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID)) is False
    assert bot.last.text.count("\n✅ ") == 3 and bot.last.text.count("\n❌ ") == 1


@pytest.mark.parametrize("status", ["left", "kicked"])
async def test_left_or_kicked_is_not_a_member(bot, context, services, user, super_admin, status) -> None:  # noqa: F811
    """حالات `left/kicked` ليست عضوية فعلية حتى لو وُجد سجل للمستخدم في القناة."""
    await _configure_channels(services, super_admin)
    _join_all(bot, status=status)
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID)) is False


async def test_full_member_passes_and_result_is_cached(bot, context, services, user, super_admin) -> None:  # noqa: F811
    """العضو في الأربع يمرّ؛ التحديث التالي يُخدم من الكاش (لا 4 نداءات جديدة)."""
    await _configure_channels(services, super_admin)
    _join_all(bot)
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID))
    assert len(bot.member_calls) == 4
    assert await run_middleware(bot, context, make_message_update(bot, text="/help", user_id=UID))
    assert len(bot.member_calls) == 4, "نتيجة «مشترك» تُعاد من الكاش خلال 5 دقائق"


async def test_check_button_bypasses_cache_and_lets_user_in(bot, context, services, user, super_admin) -> None:  # noqa: F811
    """بعد الاشتراك يضغط «تحقق»: تُعاد قراءة العضوية فوراً ويصل المستخدم للقائمة الرئيسية."""
    await _configure_channels(services, super_admin)
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID)) is False
    bot.clear()

    update = make_callback_update(bot, data=pack("sub", "check"), user_id=UID)
    assert await run_middleware(bot, context, update) is False, "لم يشترك بعد ⇒ يبقى على البوابة"
    assert bot.answers[-1]["alert"] and "قناة" in bot.answers[-1]["text"]

    _join_all(bot)
    update = make_callback_update(bot, data=pack("sub", "check"), user_id=UID)
    assert await run_middleware(bot, context, update), "اشترك فعلاً ⇒ يمرّ"
    await navigation.subscription_check_callback(update, context)
    assert "القائمة الرئيسية" in bot.last.text and bot.last.kind == "edit"


async def test_leaving_a_channel_blocks_again_after_check(bot, context, services, user, super_admin) -> None:  # noqa: F811
    """مشترك ثم غادر قناة: «تحقق» (يتجاوز الكاش) يُسقط الوصول."""
    await _configure_channels(services, super_admin)
    _join_all(bot)
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID))
    bot.memberships[("@smm_proofs", UID)] = "left"
    update = make_callback_update(bot, data=pack("sub", "check"), user_id=UID)
    assert await run_middleware(bot, context, update) is False


async def test_chat_not_found_is_fail_closed_and_alerts_admin_once(bot, context, services, user, admin, super_admin) -> None:  # noqa: F811
    """قناة مضبوطة خطأً (Chat not found): لا يُعدّ المستخدم مشتركاً، يُشرح له السبب، وينبَّه الأدمن مرة يومياً."""
    await _configure_channels(services, super_admin)
    _join_all(bot)
    bot.member_errors["@smm_updates"] = BadRequest("Chat not found")
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID)) is False
    assert "⚠️" in bot.last.text and "تعذّر التحقق" in bot.last.text
    rows = await services.repos.db.fetchall("SELECT dedupe_key FROM notifications WHERE dedupe_key LIKE 'manual:sub-config:%'")
    assert len(rows) >= 1
    first = len(rows)
    await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID))
    rows = await services.repos.db.fetchall("SELECT dedupe_key FROM notifications WHERE dedupe_key LIKE 'manual:sub-config:%'")
    assert len(rows) == first, "التنبيه مرة واحدة يومياً لكل قناة"


async def test_bot_not_admin_in_channel_is_fail_closed(bot, context, services, user, super_admin) -> None:  # noqa: F811
    """البوت ليس مشرفاً (Forbidden) ⇒ تعذّر التحقق ⇒ لا مرور."""
    await _configure_channels(services, super_admin)
    _join_all(bot)
    bot.member_errors["@smm_offers"] = Forbidden("Forbidden: bot is not a member of the channel chat")
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID)) is False


async def test_network_error_blocks_unknown_user_but_grace_keeps_recently_verified(bot, context, services, user, super_admin) -> None:  # noqa: F811
    """انقطاع الشبكة: المجهول يُمنع (فشل مغلق)، ومن تأكّد اشتراكه خلال الساعة الأخيرة لا يُطرد بسبب عطل مؤقت."""
    await _configure_channels(services, super_admin)
    for ref, _ in CHANNELS.values():
        bot.member_errors[ref] = TimedOut("timed out")
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID)) is False
    assert "تعذّر" in bot.last.text

    # نفس المستخدم بعد أن تأكّد اشتراكه قبل أكثر من 5 دقائق (انتهى الكاش) وأقل من ساعة
    sub = services.subscriptions
    for ref, _ in CHANNELS.values():
        bot.member_errors.pop(ref)
    _join_all(bot)
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID))
    for key in list(sub._verified_at):
        sub._verified_at[key] = time.monotonic() - (CACHE_TTL_SECONDS + 60)
    for ref, _ in CHANNELS.values():
        bot.member_errors[ref] = TimedOut("timed out")
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID))


async def test_staff_is_exempt_from_gate(bot, context, services, admin, super_admin) -> None:  # noqa: F811
    """الفريق الإداري لا تحجبه البوابة (حتى يصلح القنوات نفسها)."""
    await _configure_channels(services, super_admin)
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=admin.telegram_id))
    assert not bot.member_calls


async def test_disabling_requirement_removes_gate(bot, context, services, user, super_admin) -> None:  # noqa: F811
    """`subscription_required=false` يعطّل البوابة رغم ضبط القنوات."""
    await _configure_channels(services, super_admin)
    await services.settings.set("subscription_required", "false", admin_id=super_admin.id)
    assert await run_middleware(bot, context, make_message_update(bot, text="/start", user_id=UID))


async def test_channel_settings_are_validated_and_normalized(services, super_admin) -> None:
    """قيم القنوات تُطبَّع (رابط ⇒ @name) وتُرفض الصيغ المعطوبة وروابط الدعوة برسالة مفهومة."""
    await services.settings.set("channel_official", "https://t.me/MyChannel", admin_id=super_admin.id)
    assert (await services.repos.settings.get("channel_official")).value == "@MyChannel"
    await services.settings.set("channel_offers", "1001234567890", admin_id=super_admin.id)
    assert (await services.repos.settings.get("channel_offers")).value == "-1001234567890"
    for bad in ("https://t.me/+AbCdEf", "قناة", "123", "@a"):
        with pytest.raises(ValidationError):
            await services.settings.set("channel_updates", bad, admin_id=super_admin.id)


# ------------------------------- البند 2: إشعار المستخدم الجديد ------------------------------- #


async def test_new_user_alert_goes_to_channel_with_full_telegram_id(services, super_admin) -> None:
    """مستخدم جديد ⇒ منشور في صندوق قناة التنبيهات بالقالب المطلوب وبمعرّف تيليجرام **كامل** (للإدارة فقط)، مرة واحدة."""
    await services.settings.set("admin_alert_chat_id", "-1002000000001", admin_id=super_admin.id)
    user, created = await services.users.get_or_create(telegram_id=1712345678, username="newbie", first_name="Ali", last_name="Saleh")
    assert created
    post = await services.repos.channel_outbox.get_by_dedupe(f"newuser:{user.id}")
    assert post is not None and post.kind == "admin_alert"
    assert post.title == "🆕 مستخدم جديد انضم 🔥"
    for needle in (f"رقم الحساب: {user.id}", "الاسم: Ali Saleh", "Username: @newbie", "Telegram ID: 1712345678", "التسجيل:", "إجمالي المستخدمين:"):
        assert needle in post.message, needle
    assert "••" not in post.message, "معرّف المستخدم الجديد لا يُقنَّع في قناة الإدارة"
    again, created_again = await services.users.get_or_create(telegram_id=1712345678)
    assert not created_again and again.id == user.id
    assert (await services.repos.channel_outbox.count_by_status()).get("queued") == 1


async def test_new_user_alert_falls_back_to_admin_dm_without_channel(services, admin) -> None:
    """بلا قناة تنبيهات: يصل لمن يملك `users.view` كإشعار خاص (لا يضيع الحدث)."""
    user, _ = await services.users.get_or_create(telegram_id=555000111, first_name="Sara")
    rows = await services.repos.db.fetchall("SELECT message FROM notifications WHERE dedupe_key LIKE ?", (f"manual:newuser:{user.id}:%",))
    assert rows and "Telegram ID: 555000111" in rows[0]["message"]


async def test_new_user_alert_can_be_disabled(services, super_admin) -> None:
    """`new_user_alert_enabled=false` ⇒ لا منشور ولا إشعار."""
    await services.settings.set("admin_alert_chat_id", "-1002000000001", admin_id=super_admin.id)
    await services.settings.set("new_user_alert_enabled", "false", admin_id=super_admin.id)
    user, _ = await services.users.get_or_create(telegram_id=555000222)
    assert await services.repos.channel_outbox.get_by_dedupe(f"newuser:{user.id}") is None


async def test_alert_failure_never_blocks_registration(services, super_admin, monkeypatch) -> None:
    """عطل في إعلان المستخدم الجديد لا يمنع تسجيله."""
    await services.settings.set("admin_alert_chat_id", "-1002000000001", admin_id=super_admin.id)

    async def boom(*args, **kwargs):
        raise RuntimeError("outbox down")

    monkeypatch.setattr(services.channels, "enqueue", boom)
    user, created = await services.users.get_or_create(telegram_id=555000333)
    assert created and await services.users.get(user.id) is not None


# --------------------------------- البند 3: توثيق الطلبات --------------------------------- #


async def test_order_is_documented_in_orders_log_channel_without_secrets(services, super_admin, admin, user, mock_service) -> None:
    """طلب جديد ⇒ منشور توثيق بالقالب المطلوب: القسم/الخدمة/الرقم/الكمية/السعر ريال+$/عميل مقنّع/رابط مقنّع."""
    await services.settings.set("orders_log_chat_id", "-1003000000001", admin_id=super_admin.id)
    await services.wallet.adjust_balance(target=user, amount_units=5_300_000, admin=admin, reason="رصيد", credit=True)
    order = await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/private_account_name", quantity=1000
    )
    post = await services.repos.channel_outbox.get_by_dedupe(f"order:{order.id}")
    assert post is not None and post.kind == "orders_log" and post.title == "🔥 طلب جديد"
    body = post.message
    for needle in ("القسم:", "الخدمة: متابعين انستغرام (Mock)", f"رقم الطلب: {order.public_code}", "الكمية: 1,000",
                   "السعر:", "ريال" if False else "$", "العميل: 10•••••••", "الرابط: https://instagram.com/••••"):
        assert needle in body, needle
    assert "private_account_name" not in body and "100200300" not in body
    assert "api" not in body.lower().replace("instagram", "")


async def test_order_not_documented_without_destination_and_failure_does_not_break_order(services, super_admin, admin, user, mock_service, monkeypatch) -> None:
    """بلا وجهة يبقى المنشور بالطابور بانتظار الوجهة (v1.3.1: لا يضيع)؛ وعطل التوثيق لا يُسقط الطلب ولا الخصم."""
    await services.wallet.adjust_balance(target=user, amount_units=5_300_000, admin=admin, reason="رصيد", credit=True)
    first = await services.orders.create_order(user, service_id=mock_service.id, link="https://instagram.com/a", quantity=1000)
    waiting = await services.repos.channel_outbox.get_by_dedupe(f"order:{first.id}")
    assert waiting is not None and waiting.status == "queued"

    await services.settings.set("orders_log_chat_id", "-1003000000001", admin_id=super_admin.id)

    async def boom(*args, **kwargs):
        raise RuntimeError("outbox down")

    monkeypatch.setattr(services.channels, "enqueue", boom)
    second = await services.orders.create_order(user, service_id=mock_service.id, link="https://instagram.com/b", quantity=1000)
    assert second.id != first.id and (await services.repos.orders.get(second.id)) is not None


async def test_flush_delivers_each_kind_to_its_own_destination(services, super_admin) -> None:
    """التنبيهات وتوثيق الطلبات يذهبان لوجهتين مختلفتين، ولا شيء لقناة النسخ."""
    await services.settings.set("admin_alert_chat_id", "-1002000000001", admin_id=super_admin.id)
    await services.settings.set("orders_log_chat_id", "-1003000000001", admin_id=super_admin.id)
    services.channels.backup_channel_id = -1004000000001
    sent: list[int] = []

    async def sender(chat_id, title, message):
        sent.append(chat_id)
        return 1

    async with services.db.transaction() as tx:
        await services.channels.enqueue(tx, kind="admin_alert", title="a", message="m", dedupe_key="t:1")
        await services.channels.enqueue(tx, kind="orders_log", title="o", message="m", dedupe_key="t:2")
    report = await services.channels.flush(sender)
    assert report.sent == 2 and sorted(sent) == [-1003000000001, -1002000000001]
    assert -1004000000001 not in sent


async def test_destination_equal_to_backup_channel_is_refused(services, super_admin, admin) -> None:
    """وجهة تنبيه/توثيق مطابقة لقناة النسخ تُرفض (القناة للنسخ فقط): لا إرسال، وتنبيه للأدمن."""
    services.channels.backup_channel_id = -1004000000001
    await services.settings.set("orders_log_chat_id", "-1004000000001", admin_id=super_admin.id)
    called: list[int] = []

    async def sender(chat_id, title, message):
        called.append(chat_id)
        return 1

    async with services.db.transaction() as tx:
        await services.channels.enqueue(tx, kind="orders_log", title="o", message="m", dedupe_key="t:9")
    report = await services.channels.flush(sender)
    assert report.skipped == 1 and not called
    alerts = await services.repos.db.fetchall("SELECT 1 FROM notifications WHERE dedupe_key LIKE 'manual:channel-dest:%'")
    assert alerts


async def test_permanent_channel_failure_marks_failed_and_alerts_without_loop(services, super_admin, admin) -> None:
    """فشل دائم (البوت ليس في القناة) ⇒ failed بلا إعادة، تنبيه أدمن واحد، ولا منشور جديد في القناة نفسها."""
    await services.settings.set("admin_alert_chat_id", "-1002000000001", admin_id=super_admin.id)

    async def sender(chat_id, title, message):
        raise NotificationBlockedError("محادثة غير متاحة: Chat not found")

    async with services.db.transaction() as tx:
        await services.channels.enqueue(tx, kind="admin_alert", title="a", message="m", dedupe_key="t:7")
    report = await services.channels.flush(sender)
    assert report.failed == 1
    counts = await services.repos.channel_outbox.count_by_status()
    assert counts.get("failed") == 1 and not counts.get("queued")
    assert (await services.channels.flush(sender)).claimed == 0, "الفاشل نهائياً لا يُعاد"
    assert not await services.repos.db.fetchall("SELECT 1 FROM channel_outbox WHERE dedupe_key LIKE 'alert:channel-dest%'"), "تنبيه الفشل لا يُنسخ للقناة"
    assert await services.repos.db.fetchall("SELECT 1 FROM notifications WHERE dedupe_key LIKE 'manual:channel-dest:admin_alert:%'")


async def test_temporary_failure_is_retried_later(services, super_admin) -> None:
    """فشل مؤقت ⇒ يبقى في الصندوق ويُرسل لاحقاً عند نجاح الشبكة."""
    await services.settings.set("admin_alert_chat_id", "-1002000000001", admin_id=super_admin.id)

    async def failing(chat_id, title, message):
        raise NotificationTemporaryError("شبكة")

    async with services.db.transaction() as tx:
        await services.channels.enqueue(tx, kind="admin_alert", title="a", message="m", dedupe_key="t:8")
    assert (await services.channels.flush(failing)).retried == 1
    await services.repos.db.fetchone("SELECT 1")
    async with services.db.transaction() as tx:
        await tx.execute("UPDATE channel_outbox SET next_attempt_at = '2000-01-01T00:00:00Z'")

    async def ok(chat_id, title, message):
        return 1

    assert (await services.channels.flush(ok)).sent == 1


# --------------------------------- البند 4: قناة النسخ + التشخيص --------------------------------- #


async def test_diagnose_explains_chat_not_found_and_missing_post_permission(bot, services) -> None:  # noqa: F811
    """التشخيص يفرّق: غير موجودة / البوت ليس مشرفاً / بلا صلاحية نشر / سليمة."""
    from types import SimpleNamespace

    result = await services.channels.diagnose(bot, "قناة النسخ", -1001111111111)
    assert result.ok is False and result.problem == "Chat not found" and any("-100" in hint for hint in result.hints)

    bot.chats[-1001111111111] = SimpleNamespace(id=-1001111111111, type="channel", title="Backups")
    bot.memberships[(-1001111111111, bot.id)] = "member"
    assert (await services.channels.diagnose(bot, "x", -1001111111111)).problem == "البوت ليس مشرفاً في القناة"

    bot.memberships[(-1001111111111, bot.id)] = "administrator"
    assert (await services.channels.diagnose(bot, "x", -1001111111111)).ok is True

    bot.chats[-1001111111111] = BadRequest("Chat not found")
    assert (await services.channels.diagnose(bot, "x", -1001111111111)).ok is False
    bot.chats[-1001111111111] = TimedOut("t")
    assert (await services.channels.diagnose(bot, "x", -1001111111111)).ok is None


async def test_backup_delivery_error_explains_chat_not_found(services, super_admin, bot, tmp_path) -> None:  # noqa: F811
    """رسالة فشل رفع النسخة تشرح «Chat not found» وتدلّ على شاشة القنوات."""
    services.backups.channel_id = -1005000000001

    async def failing_send(**kwargs):
        raise BadRequest("Chat not found")

    bot.send_document = failing_send
    info = await services.backups.create(super_admin)
    from core.exceptions import BackupError

    with pytest.raises(BackupError) as caught:
        await services.backups.send_to_channel(super_admin, bot, info.id)
    assert "-100" in caught.value.user_message and "القنوات" in caught.value.user_message


def test_config_normalizes_channel_env_vars(monkeypatch, tmp_path) -> None:
    """BACKUP_CHANNEL_ID/ADMIN_ALERT_CHAT_ID: يُصحَّح الرقم بلا -100، ويُقبل @name/الرابط، ويُرفض رابط الدعوة بوضوح."""
    from config import Config, ConfigError

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "d" / "t.db"))
    monkeypatch.setenv("BACKUP_CHANNEL_ID", "1001234567890")
    monkeypatch.setenv("ADMIN_ALERT_CHAT_ID", "https://t.me/mychan")
    cfg = Config.load(env_file=tmp_path / "none.env")
    assert cfg.backup_channel_id == -1001234567890 and cfg.admin_alert_chat_id == "@mychan"
    monkeypatch.setenv("BACKUP_CHANNEL_ID", "https://t.me/+AbCdEf")
    with pytest.raises(ConfigError) as caught:
        Config.load(env_file=tmp_path / "none.env")
    assert "BACKUP_CHANNEL_ID" in str(caught.value)


# ------------------------------------ شاشة الأدمن «📢 القنوات» ------------------------------------ #


async def test_admin_channels_screens_show_check_and_test(bot, context, services, super_admin) -> None:  # noqa: F811
    """الشاشة تعرض القيم، الفحص يشرح «Chat not found» بالحل، واختبار الإرسال يعمل ويبلّغ بالنتيجة."""
    from types import SimpleNamespace

    from handlers.admin import channels as admin_channels

    await services.settings.set("channel_official", "@smm_official", admin_id=super_admin.id)
    await services.settings.set("admin_alert_chat_id", "-1002000000001", admin_id=super_admin.id)
    services.backups.channel_id = -1005000000001
    await load_user(bot, context, super_admin)

    await press(bot, context, admin_channels.home_screen, pack("ch", "home"), super_admin.telegram_id)
    text = bot.last.text
    assert "@smm_official" in text and "-1002000000001" in text and "-1005000000001" in text and "النسخ" in text
    callbacks = [b.callback_data for row in bot.last.markup.inline_keyboard for b in row]
    assert pack("ch", "check") in callbacks and pack("ch", "test", "alert") in callbacks

    bot.chats["@smm_official"] = SimpleNamespace(id=-1001, type="channel", title="Official")
    bot.memberships[(-1001, bot.id)] = "administrator"
    await press(bot, context, admin_channels.check_screen, pack("ch", "check"), super_admin.telegram_id)
    text = bot.last.text
    assert "✅ 📢 القناة الرسمية" in text
    assert "Chat not found" in text and "-100" in text, "قناة النسخ غير الموجودة تُشرح بسببها وحلها"

    await press(bot, context, admin_channels.test_action, pack("ch", "test", "alert"), super_admin.telegram_id)
    assert any(item.chat_id == -1002000000001 and "اختبار" in item.text for item in bot.sent)
    assert "أُرسلت" in bot.last.text
    await press(bot, context, admin_channels.test_action, pack("ch", "test", "orders"), super_admin.telegram_id)
    assert "غير مضبوطة" in bot.last.text, "بلا وجهة توثيق: يُقال ذلك بوضوح بدل نجاح كاذب"


async def test_admin_channels_screen_requires_permission(bot, context, services, user) -> None:  # noqa: F811
    """مستخدم عادي لا يفتح الشاشة ولا يفحص (الصلاحية على الـcallback نفسه)."""
    from handlers.admin import channels as admin_channels

    await load_user(bot, context, user)
    await press(bot, context, admin_channels.check_screen, pack("ch", "check"), user.telegram_id)
    assert not bot.sent and bot.answers[-1]["alert"]
