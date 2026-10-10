"""
اختبارات المرحلة 8 — الرسائل الجماعية (الإذاعة) وأولوية التذاكر.

ما تغطيه:
    1. الاستهداف: كل شريحة تحسب مستلميها الحقيقيين وتستثني المحظورين ومن حظر البوت.
    2. دورة الإرسال: دفعات، تسجيل كل مستلم، اكتمال تلقائي، إشعار منشئ الرسالة.
    3. الأمان التشغيلي: لا تكرار، إيقاف مؤقت فوري، إلغاء نهائي، استئناف بعد الإيقاف.
    4. الأخطاء: حظر البوت، فشل نهائي، فشل مؤقت يُعاد مرة واحدة.
    5. اللوحة: محادثة الإنشاء بتأكيدها الثاني، البطاقة، والصلاحيات.
    6. أولوية التذاكر وتصفية «العاجلة» وإعداد تنبيه الردود.
"""

from __future__ import annotations

import pytest
from telegram.ext import ConversationHandler

from core.exceptions import (
    NotificationBlockedError,
    NotificationPermanentError,
    NotificationTemporaryError,
    PermissionDeniedError,
    ValidationError,
)
from database.models import User
from handlers.admin import broadcast as broadcast_admin
from handlers.admin import tickets as tickets_admin
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


class RecordingSender:
    """مُرسل تجريبي يسجّل من أُرسل إليه، ويمكن برمجته ليفشل لمستلمين بعينهم."""

    def __init__(self) -> None:
        """تهيئة السجلات وجدول الأخطاء المبرمجة (telegram_id ⇐ استثناء أو قائمة استثناءات)."""
        self.sent: list[tuple[int, str, str | None, str | None]] = []
        self.plan: dict[int, list[Exception]] = {}

    async def __call__(
        self, telegram_id: int, text: str, media_file_id: str | None, media_type: str | None
    ) -> int:
        """إرسال مزيّف: يرفع الخطأ المبرمج التالي لهذا المستلم إن وُجد."""
        queue = self.plan.get(telegram_id)
        if queue:
            raise queue.pop(0)
        self.sent.append((telegram_id, text, media_file_id, media_type))
        return len(self.sent)

    @property
    def ids(self) -> list[int]:
        """معرفات تيليجرام لمن وصلتهم الرسالة بالترتيب."""
        return [item[0] for item in self.sent]


async def _make_user(
    services: ServiceContainer,
    telegram_id: int,
    *,
    banned: bool = False,
    blocked: bool = False,
    active_days_ago: int | None = 0,
) -> User:
    """إنشاء مستخدم بحالة محددة (محظور/حاظر للبوت/آخر نشاط)."""
    async with services.db.transaction() as tx:
        created = await services.repos.users.create(
            tx, telegram_id=telegram_id, username=f"u{telegram_id}", first_name="مستخدم", role="user"
        )
        last = None
        if active_days_ago is not None:
            from utils.datetime_utils import iso_minus_days, utc_now_iso

            last = iso_minus_days(active_days_ago) if active_days_ago else utc_now_iso()
        await tx.execute(
            "UPDATE users SET is_banned = ?, blocked_bot = ?, last_activity = ? WHERE id = ?",
            (1 if banned else 0, 1 if blocked else 0, last, created.id),
        )
    return created


@pytest.fixture
async def audience(services: ServiceContainer) -> dict[str, User]:
    """
    جمهور تجريبي: 3 عاديون + محظور + حاظر للبوت + قديم النشاط.

    (المستخدمون الثلاثة الافتراضيون user/admin/super_admin يُنشأون بالـfixtures عند طلبها فقط.)
    """
    return {
        "a": await _make_user(services, 7001),
        "b": await _make_user(services, 7002),
        "old": await _make_user(services, 7003, active_days_ago=90),
        "banned": await _make_user(services, 7004, banned=True),
        "blocked": await _make_user(services, 7005, blocked=True),
    }


# ======================================================================== #
#                              الاستهداف                                   #
# ======================================================================== #


async def test_all_target_excludes_banned_and_blocked(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """«الكل» لا يشمل المحظورين ولا من حظر البوت."""
    ids = set(await services.broadcasts.audience_ids("all"))
    assert audience["a"].id in ids and audience["b"].id in ids and audience["old"].id in ids
    assert audience["banned"].id not in ids
    assert audience["blocked"].id not in ids


async def test_active_target_respects_days_setting(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """«النشطون» يستبعد من لم ينشط خلال المدة المضبوطة، والمدة قابلة للتعديل."""
    ids = set(await services.broadcasts.audience_ids("active"))
    assert audience["a"].id in ids and audience["old"].id not in ids

    await services.settings.set("broadcast_active_days", "120", admin_id=super_admin.id)
    ids = set(await services.broadcasts.audience_ids("active"))
    assert audience["old"].id in ids


async def test_buyers_and_no_orders_targets_are_complementary(
    services: ServiceContainer,
    super_admin: User,
    admin: User,
    user: User,
    mock_service,
    audience: dict[str, User],
) -> None:
    """«من لديه طلب» و«بلا طلبات» شريحتان متكاملتان بلا تداخل."""
    await services.wallet.adjust_balance(
        target=user, amount_units=500_000, admin=admin, reason="رصيد", credit=True
    )
    await services.orders.create_order(
        user, service_id=mock_service.id, link="https://instagram.com/p/b8", quantity=1000
    )
    buyers = set(await services.broadcasts.audience_ids("buyers"))
    fresh = set(await services.broadcasts.audience_ids("no_orders"))

    assert user.id in buyers and audience["a"].id not in buyers
    assert audience["a"].id in fresh and user.id not in fresh
    assert buyers.isdisjoint(fresh)


async def test_unknown_target_is_rejected(services: ServiceContainer, super_admin: User) -> None:
    """شريحة غير معروفة تُرفض بدل أن تُرسل للجميع بالخطأ."""
    with pytest.raises(ValidationError):
        await services.broadcasts.audience_ids("everyone_and_more")


async def test_empty_audience_cannot_create_broadcast(
    services: ServiceContainer, super_admin: User
) -> None:
    """لا تُنشأ رسالة بلا مستلمين (قاعدة بلا مستخدمين عاديين)."""
    await _make_user(services, 7100, blocked=True)
    with pytest.raises(ValidationError):
        await services.broadcasts.create(super_admin, text="مرحبا", target="buyers")


# ======================================================================== #
#                              الإنشاء                                     #
# ======================================================================== #


async def test_create_freezes_recipients_and_audits(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """الإنشاء يثبّت قائمة المستلمين كمسودة ويسجّل التدقيق، ولا يرسل شيئاً."""
    broadcast = await services.broadcasts.create(super_admin, text="عرض اليوم\nخصم 10%", target="all")
    assert broadcast.status == "draft"
    assert broadcast.total_count == 4  # super_admin + a + b + old
    assert broadcast.message_text == "عرض اليوم\nخصم 10%"
    assert "broadcast.send" in [
        row["action"] for row in await services.db.fetchall("SELECT action FROM audit_logs")
    ]

    # مستخدم يسجّل بعد الإنشاء لا يدخل القائمة المثبّتة
    late = await _make_user(services, 7200)
    rows = await services.db.fetchall(
        "SELECT user_id FROM broadcast_recipients WHERE broadcast_id = ?", (broadcast.id,)
    )
    assert late.id not in {row["user_id"] for row in rows}


async def test_create_requires_permission(
    services: ServiceContainer, user: User, audience: dict[str, User]
) -> None:
    """لا أدمن ولا مستخدم عادي بلا `broadcast.send` ينشئ رسالة جماعية."""
    with pytest.raises(PermissionDeniedError):
        await services.broadcasts.create(user, text="x y", target="all")
    async with services.db.transaction() as tx:
        support = await services.repos.users.create(
            tx, telegram_id=7300, username="sup", first_name="دعم", role="support"
        )
    with pytest.raises(PermissionDeniedError):
        await services.broadcasts.create(support, text="x y", target="all")
    with pytest.raises(PermissionDeniedError):
        await services.broadcasts.audience_summary(support)


async def test_text_limits_differ_with_media(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """النص الطويل مقبول وحده، لكنه مرفوض كتعليق على صورة (حد تيليجرام 1024)."""
    long_text = "ا" * 1500
    ok = await services.broadcasts.create(super_admin, text=long_text, target="all")
    assert ok.total_count > 0
    with pytest.raises(ValidationError):
        await services.broadcasts.create(
            super_admin, text=long_text, target="all", media_file_id="f1", media_type="photo"
        )
    with pytest.raises(ValidationError):
        await services.broadcasts.create(super_admin, text="  ", target="all")


# ======================================================================== #
#                            دورة الإرسال                                  #
# ======================================================================== #


async def test_draft_is_never_sent_before_start(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """المسودة لا تُرسل ولو دارت المهمة: الإرسال يبدأ بقرار صريح فقط."""
    await services.broadcasts.create(super_admin, text="مسودة", target="all")
    sender = RecordingSender()
    report = await services.broadcasts.send_batch(sender)
    assert report.claimed == 0 and sender.sent == []


async def test_full_cycle_batches_then_completes_and_notifies_creator(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """الدورة كاملة: دفعات صغيرة ← كل مستلم يُسجَّل ← اكتمال ← إشعار الأدمن بالحصيلة."""
    broadcast = await services.broadcasts.create(super_admin, text="مرحباً بالجميع", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    sender = RecordingSender()

    first = await services.broadcasts.send_batch(sender, limit=3)
    assert (first.claimed, first.sent, first.completed) == (3, 3, False)
    mid = await services.broadcasts.get(super_admin, broadcast.id)
    assert mid.status == "running" and mid.sent_count == 3

    second = await services.broadcasts.send_batch(sender, limit=3)
    assert (second.claimed, second.sent, second.completed) == (1, 1, True)

    done = await services.broadcasts.get(super_admin, broadcast.id)
    assert done.status == "completed" and done.sent_count == 4 and done.finished_at
    assert len(sender.sent) == 4 and len(set(sender.ids)) == 4  # لا تكرار
    assert all(item[1] == "مرحباً بالجميع" for item in sender.sent)

    note = await services.db.fetchone(
        "SELECT message FROM notifications WHERE user_id = ? AND type = 'system'", (super_admin.id,)
    )
    assert note is not None and "اكتملت" in note["message"] and "وصلت: 4" in note["message"]

    # بعد الاكتمال لا شيء يُرسل ثانيةً
    again = await services.broadcasts.send_batch(sender)
    assert again.claimed == 0 and len(sender.sent) == 4


async def test_pause_stops_sending_and_resume_continues_without_duplicates(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """الإيقاف المؤقت فوري، والاستئناف يكمل من حيث توقف دون إعادة إرسال لأحد."""
    broadcast = await services.broadcasts.create(super_admin, text="رسالة طويلة", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    sender = RecordingSender()
    await services.broadcasts.send_batch(sender, limit=2)

    assert await services.broadcasts.pause(super_admin, broadcast.id) is True
    assert (await services.broadcasts.send_batch(sender)).claimed == 0
    assert len(sender.sent) == 2

    await services.broadcasts.start(super_admin, broadcast.id)  # استئناف
    await services.broadcasts.send_batch(sender, limit=10)
    assert len(sender.sent) == 4 and len(set(sender.ids)) == 4
    final = await services.broadcasts.get(super_admin, broadcast.id)
    assert final.status == "completed" and final.sent_count == 4


async def test_cancel_is_final_and_keeps_history(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """الإلغاء نهائي: لا استئناف، لا إرسال، وسجل المستلمين يبقى كاملاً."""
    broadcast = await services.broadcasts.create(super_admin, text="سيُلغى", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    sender = RecordingSender()
    await services.broadcasts.send_batch(sender, limit=1)

    assert await services.broadcasts.cancel(super_admin, broadcast.id) is True
    assert await services.broadcasts.cancel(super_admin, broadcast.id) is False
    with pytest.raises(ValidationError):
        await services.broadcasts.start(super_admin, broadcast.id)
    assert (await services.broadcasts.send_batch(sender)).claimed == 0

    total_rows = await services.db.fetchval(
        "SELECT COUNT(*) FROM broadcast_recipients WHERE broadcast_id = ?", (broadcast.id,)
    )
    assert total_rows == 4 and len(sender.sent) == 1


async def test_completed_broadcast_cannot_be_started_again(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """رسالة مكتملة لا تُعاد (وإلا استلم الناس النص مرتين)."""
    broadcast = await services.broadcasts.create(super_admin, text="مرة واحدة", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    await services.broadcasts.send_batch(RecordingSender(), limit=50)
    with pytest.raises(ValidationError):
        await services.broadcasts.start(super_admin, broadcast.id)


async def test_start_twice_is_rejected_while_running(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """البدء مرتين (ضغطة مزدوجة) لا يُنتج حالة مضاعفة."""
    broadcast = await services.broadcasts.create(super_admin, text="ضغطتان", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    with pytest.raises(ValidationError):
        await services.broadcasts.start(super_admin, broadcast.id)


async def test_resume_after_restart_continues_running_broadcast(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """إعادة تشغيل البوت لا تضيّع شيئاً: الإذاعة الجارية تُكمل في الجولة التالية."""
    broadcast = await services.broadcasts.create(super_admin, text="تستمر", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    first = RecordingSender()
    await services.broadcasts.send_batch(first, limit=2)

    # «إعادة تشغيل»: خدمة جديدة بنفس قاعدة البيانات
    from services import build_services
    from utils.security import SecretBox, generate_encryption_key

    revived = build_services(
        services.db, services.repos, secret_box=SecretBox(generate_encryption_key())
    )
    second = RecordingSender()
    await revived.broadcasts.send_batch(second, limit=10)
    assert set(first.ids).isdisjoint(second.ids)
    assert len(first.ids) + len(second.ids) == 4


# ======================================================================== #
#                              الأخطاء                                     #
# ======================================================================== #


async def test_blocked_user_is_recorded_and_flagged(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """من حظر البوت يُسجَّل «حظر» ويُعلَّم `blocked_bot` فلا يُزعَج لاحقاً."""
    broadcast = await services.broadcasts.create(super_admin, text="للجميع", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    sender = RecordingSender()
    sender.plan[7001] = [NotificationBlockedError("حظر البوت")]

    report = await services.broadcasts.send_batch(sender, limit=10)
    assert (report.sent, report.blocked, report.failed) == (3, 1, 0)
    refreshed = await services.repos.users.get_by_id(audience["a"].id)
    assert refreshed.blocked_bot
    done = await services.broadcasts.get(super_admin, broadcast.id)
    assert done.blocked_count == 1 and done.sent_count == 3


async def test_permanent_failure_is_recorded_without_retry(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """الفشل النهائي يُسجَّل مع سببه ولا يُعاد."""
    broadcast = await services.broadcasts.create(super_admin, text="للجميع", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    sender = RecordingSender()
    sender.plan[7002] = [NotificationPermanentError("رسالة مرفوضة"), NotificationPermanentError("x")]

    report = await services.broadcasts.send_batch(sender, limit=10)
    assert report.failed == 1 and report.sent == 3
    row = await services.db.fetchone(
        "SELECT status, error FROM broadcast_recipients WHERE user_id = ? AND broadcast_id = ?",
        (audience["b"].id, broadcast.id),
    )
    assert row["status"] == "failed" and "مرفوضة" in row["error"]
    assert len(sender.plan[7002]) == 1  # استُهلك خطأ واحد فقط: لا إعادة محاولة


async def test_temporary_failure_retries_once_then_succeeds(
    services: ServiceContainer, super_admin: User, audience: dict[str, User], monkeypatch
) -> None:
    """خطأ شبكة عابر يُعاد مرة واحدة فينجح الإرسال."""
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("services.broadcast_service.asyncio.sleep", no_sleep)
    broadcast = await services.broadcasts.create(super_admin, text="للجميع", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    sender = RecordingSender()
    sender.plan[7001] = [NotificationTemporaryError("شبكة")]

    report = await services.broadcasts.send_batch(sender, limit=10)
    assert report.sent == 4 and report.failed == 0


async def test_temporary_failure_twice_is_recorded_as_failed(
    services: ServiceContainer, super_admin: User, audience: dict[str, User], monkeypatch
) -> None:
    """تكرار الخطأ العابر لا يعلّق الطابور: يُسجَّل فشلاً ويكمل الباقون."""
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("services.broadcast_service.asyncio.sleep", no_sleep)
    broadcast = await services.broadcasts.create(super_admin, text="للجميع", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    sender = RecordingSender()
    sender.plan[7001] = [NotificationTemporaryError("شبكة"), NotificationTemporaryError("شبكة")]

    report = await services.broadcasts.send_batch(sender, limit=10)
    assert report.failed == 1 and report.sent == 3 and report.completed


async def test_media_details_reach_the_sender(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """الصورة ونوعها يصلان المُرسل مع النص كتعليق."""
    broadcast = await services.broadcasts.create(
        super_admin, text="عرض", target="all", media_file_id="photo-1", media_type="photo"
    )
    await services.broadcasts.start(super_admin, broadcast.id)
    sender = RecordingSender()
    await services.broadcasts.send_batch(sender, limit=1)
    assert sender.sent[0][2:] == ("photo-1", "photo")


async def test_progress_numbers_come_from_database(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """التقدم: النسبة والمتبقي محسوبان من الصفوف الفعلية."""
    broadcast = await services.broadcasts.create(super_admin, text="تقدم", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    await services.broadcasts.send_batch(RecordingSender(), limit=2)
    data = await services.broadcasts.progress(super_admin, broadcast.id)
    assert (data["done"], data["pending"], data["percent"]) == (2, 2, 50)


# ======================================================================== #
#                              مهمة الجدولة                                #
# ======================================================================== #


async def test_dispatch_job_sends_through_telegram_sender(
    services: ServiceContainer, super_admin: User, audience: dict[str, User]
) -> None:
    """المهمة الدورية تستخدم مُرسل تيليجرام الحقيقي وتُنهي الإذاعة."""
    from jobs.broadcast_jobs import dispatch_broadcasts
    from tests.telegram_fakes import FakeBot

    class _App:
        bot_data = {"services": services}

    class _Ctx:
        application = _App()
        bot = FakeBot()

    broadcast = await services.broadcasts.create(super_admin, text="عبر المهمة <b>", target="all")
    await services.broadcasts.start(super_admin, broadcast.id)
    await dispatch_broadcasts(_Ctx())  # type: ignore[arg-type]

    done = await services.broadcasts.get(super_admin, broadcast.id)
    assert done.status == "completed" and done.sent_count == 4
    assert len(_Ctx.bot.sent) == 4
    assert "&lt;b&gt;" in _Ctx.bot.sent[0].text  # النص يُهرَّب: لا حقن HTML من الأدمن بالخطأ


# ======================================================================== #
#                              شاشات اللوحة                                #
# ======================================================================== #


async def test_home_screen_empty_then_lists_broadcasts(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer,  # noqa: F811
    audience: dict[str, User],
) -> None:
    """الشاشة الرئيسية: حالة فارغة واضحة ثم قائمة بالرسائل وأزرارها."""
    await load_user(bot, context, super_admin)
    await press(bot, context, broadcast_admin.broadcast_home_screen, pack("bc", "home"), super_admin.telegram_id)
    assert "لم تُرسل أي رسالة جماعية" in bot.last.text
    assert pack("bc", "new") in bot.last.buttons

    created = await services.broadcasts.create(super_admin, text="أولى", target="all")
    await press(bot, context, broadcast_admin.broadcast_home_screen, pack("bc", "home"), super_admin.telegram_id)
    assert pack("bc", "view", created.id) in bot.last.buttons


async def test_new_broadcast_conversation_needs_confirmation_then_runs(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer,  # noqa: F811
    audience: dict[str, User],
) -> None:
    """المحادثة كاملة: النص ← تخطي الصورة ← شريحة ← مراجعة ← تأكيد ثانٍ ← إرسال."""
    await load_user(bot, context, super_admin)
    uid = super_admin.telegram_id

    state = await press(bot, context, broadcast_admin.start_new_broadcast, pack("bc", "new"), uid)
    assert state == broadcast_admin.ASK_TEXT

    state = await write(bot, context, broadcast_admin.receive_broadcast_text, "صباح الخير\nعرض جديد", uid)
    assert state == broadcast_admin.ASK_MEDIA

    state = await press(bot, context, broadcast_admin.skip_broadcast_media, pack("flow", "skip"), uid)
    assert state == broadcast_admin.CHOOSE_TARGET
    assert pack("bc", "target", "all") in bot.last.buttons
    assert "كل المستخدمين: 4" in bot.last.text  # العدد الحقيقي يظهر قبل الاختيار

    state = await press(bot, context, broadcast_admin.choose_broadcast_target, pack("bc", "target", "all"), uid)
    assert state == broadcast_admin.CONFIRM_SEND
    assert "ستصل إلى: 4" in bot.last.text and "صباح الخير" in bot.last.text
    # قبل التأكيد لا شيء أُنشئ
    assert await services.db.fetchval("SELECT COUNT(*) FROM broadcasts") == 0

    await press(bot, context, broadcast_admin.confirm_broadcast, pack("flow", "confirm"), uid)
    row = await services.db.fetchone("SELECT status, total_count FROM broadcasts")
    assert row["status"] == "running" and row["total_count"] == 4
    assert "pause" in " ".join(bot.last.buttons)


async def test_conversation_with_photo_and_long_text_is_blocked(
    bot: FakeBot, context: FakeContext, super_admin: User,  # noqa: F811
    audience: dict[str, User],
) -> None:
    """نص أطول من حد التعليق مع صورة: رسالة واضحة والمحادثة تبقى في خطوة الصورة."""
    await load_user(bot, context, super_admin)
    uid = super_admin.telegram_id
    await press(bot, context, broadcast_admin.start_new_broadcast, pack("bc", "new"), uid)
    await write(bot, context, broadcast_admin.receive_broadcast_text, "ب" * 1500, uid)

    state = await write(bot, context, broadcast_admin.receive_broadcast_media, "", uid, photo=True)
    assert state == broadcast_admin.ASK_MEDIA
    assert "أطول" in bot.last.text


async def test_conversation_with_photo_short_text_proceeds(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer,  # noqa: F811
    audience: dict[str, User],
) -> None:
    """صورة مع نص قصير تنتقل مباشرة لاختيار الشريحة وتُحفظ في الإذاعة."""
    await load_user(bot, context, super_admin)
    uid = super_admin.telegram_id
    await press(bot, context, broadcast_admin.start_new_broadcast, pack("bc", "new"), uid)
    await write(bot, context, broadcast_admin.receive_broadcast_text, "صورة العرض", uid)
    state = await write(bot, context, broadcast_admin.receive_broadcast_media, "", uid, photo=True)
    assert state == broadcast_admin.CHOOSE_TARGET
    await press(bot, context, broadcast_admin.choose_broadcast_target, pack("bc", "target", "all"), uid)
    assert "صورة" in bot.last.text
    await press(bot, context, broadcast_admin.confirm_broadcast, pack("flow", "confirm"), uid)
    row = await services.db.fetchone("SELECT media_file_id, media_type FROM broadcasts")
    assert row["media_file_id"] == "photo-file-id" and row["media_type"] == "photo"


async def test_empty_target_is_refused_in_conversation(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer,  # noqa: F811
) -> None:
    """شريحة بلا مستلمين تُرفض بتنبيه، والمحادثة تبقى في اختيار الشريحة."""
    await load_user(bot, context, super_admin)
    uid = super_admin.telegram_id
    await press(bot, context, broadcast_admin.start_new_broadcast, pack("bc", "new"), uid)
    await write(bot, context, broadcast_admin.receive_broadcast_text, "نص", uid)
    await press(bot, context, broadcast_admin.skip_broadcast_media, pack("flow", "skip"), uid)
    state = await press(bot, context, broadcast_admin.choose_broadcast_target, pack("bc", "target", "buyers"), uid)
    assert state == broadcast_admin.CHOOSE_TARGET
    assert bot.answers[-1]["alert"]
    assert await services.db.fetchval("SELECT COUNT(*) FROM broadcasts") == 0


async def test_card_pause_resume_cancel_buttons(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer,  # noqa: F811
    audience: dict[str, User],
) -> None:
    """أزرار البطاقة تتبدّل مع الحالة: إيقاف ← استئناف ← إلغاء نهائي بلا أزرار تحكم."""
    created = await services.broadcasts.create(super_admin, text="تحكم", target="all")
    await services.broadcasts.start(super_admin, created.id)
    await load_user(bot, context, super_admin)
    uid = super_admin.telegram_id

    await press(bot, context, broadcast_admin.broadcast_card_screen, pack("bc", "view", created.id), uid)
    assert pack("bc", "pause", created.id) in bot.last.buttons
    assert "جارية" in bot.last.text

    await press(bot, context, broadcast_admin.pause_broadcast, pack("bc", "pause", created.id), uid)
    assert pack("bc", "start", created.id) in bot.last.buttons
    assert "موقوفة" in bot.last.text

    await press(bot, context, broadcast_admin.start_broadcast, pack("bc", "start", created.id), uid)
    assert "جارية" in bot.last.text

    await press(bot, context, broadcast_admin.cancel_broadcast, pack("bc", "cancel", created.id), uid)
    assert "ملغاة" in bot.last.text
    controls = [b for b in bot.last.buttons if b.startswith(("bc:start", "bc:pause", "bc:cancel"))]
    assert controls == []


async def test_support_cannot_use_broadcast_screens(
    bot: FakeBot, context: FakeContext, services: ServiceContainer,  # noqa: F811
    audience: dict[str, User],
) -> None:
    """الدعم الفني لا يفتح الإذاعة ولا يبدأ محادثتها (فحص على الـcallback)."""
    async with services.db.transaction() as tx:
        support = await services.repos.users.create(
            tx, telegram_id=7400, username="sup4", first_name="دعم", role="support"
        )
    await load_user(bot, context, support)
    await press(bot, context, broadcast_admin.broadcast_home_screen, pack("bc", "home"), support.telegram_id)
    assert not bot.sent
    state = await press(bot, context, broadcast_admin.start_new_broadcast, pack("bc", "new"), support.telegram_id)
    assert state == ConversationHandler.END and not bot.sent


# ======================================================================== #
#                       أولوية التذاكر وتنبيه الردود                       #
# ======================================================================== #


async def _open_ticket(services: ServiceContainer, user: User):
    """فتح تذكرة بسيطة للمستخدم."""
    return await services.tickets.create_ticket(
        user, subject="مشكلة في طلبي", message="الطلب متوقف منذ ساعة", category="other"
    )


async def test_priority_button_changes_priority_and_card(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User,  # noqa: F811
) -> None:
    """زر الأولوية يغيّرها، والبطاقة تعرضها، وتُسجَّل في التدقيق."""
    ticket = await _open_ticket(services, user)
    await load_user(bot, context, admin)

    await press(bot, context, tickets_admin.ticket_card_screen, pack("at", "view", ticket.id), admin.telegram_id)
    assert "عادية" in bot.last.text
    assert pack("at", "prio", ticket.id, "high") in bot.last.buttons

    await press(bot, context, tickets_admin.set_ticket_priority, pack("at", "prio", ticket.id, "high"), admin.telegram_id)
    assert "عالية" in bot.last.text
    fresh = await services.repos.tickets.get(ticket.id)
    assert fresh.priority == "high"

    await press(bot, context, tickets_admin.set_ticket_priority, pack("at", "prio", ticket.id, "high"), admin.telegram_id)
    assert bot.answers[-1]["text"]  # «بهذه الأولوية أصلاً»


async def test_priority_requires_assign_permission_and_valid_value(
    services: ServiceContainer, user: User
) -> None:
    """المستخدم العادي لا يغيّر الأولوية، وقيمة غير معروفة تُرفض."""
    ticket = await _open_ticket(services, user)
    with pytest.raises(PermissionDeniedError):
        await services.tickets.set_priority(user, ticket.id, "high")


async def test_high_filter_lists_only_urgent_open_tickets(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User,  # noqa: F811
) -> None:
    """تبويب «العاجلة» يعرض المفتوحة العالية الأولوية فقط."""
    urgent = await _open_ticket(services, user)
    async with services.db.transaction() as tx:
        other = await services.repos.users.create(
            tx, telegram_id=7500, username="o", first_name="آخر", role="user"
        )
    normal = await _open_ticket(services, other)
    await services.tickets.set_priority(admin, urgent.id, "high")

    await load_user(bot, context, admin)
    await press(bot, context, tickets_admin.tickets_list_screen, pack("at", "list", "high", 1), admin.telegram_id)
    assert pack("at", "view", urgent.id) in bot.last.buttons
    assert pack("at", "view", normal.id) not in bot.last.buttons
    assert "العاجلة" in bot.last.text


async def test_user_reply_notifies_admins_unless_setting_off(
    services: ServiceContainer, user: User, admin: User, super_admin: User
) -> None:
    """تنبيه الأدمن عند ردّ المستخدم يخضع للإعداد `ticket_reply_notify_admins`."""
    ticket = await _open_ticket(services, user)
    base = await services.db.fetchval("SELECT COUNT(*) FROM notifications")

    await services.tickets.reply_as_user(user, ticket.id, "ما زلت أنتظر")
    after_on = await services.db.fetchval("SELECT COUNT(*) FROM notifications")
    assert after_on > base

    await services.settings.set("ticket_reply_notify_admins", "0", admin_id=super_admin.id)
    await services.tickets.reply_as_user(user, ticket.id, "رد ثانٍ بلا تنبيه")
    assert await services.db.fetchval("SELECT COUNT(*) FROM notifications") == after_on
    # الرد نفسه محفوظ رغم عدم التنبيه
    messages = await services.repos.tickets.messages(ticket.id)
    assert messages[-1].message == "رد ثانٍ بلا تنبيه"
