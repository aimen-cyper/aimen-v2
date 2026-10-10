"""
اختبارات المرحلة 9 — شاشة الأمان، الحدّ من الإساءة، تنبيه الأخطاء، إعادة الجدولة الحيّة.

ما تغطيه:
    1. خدمة الأمان: العدّادات، الأحداث، الفريق، فحوص الوضع، رفع الإيقاف + الصلاحيات.
    2. شاشات اللوحة: كل زر يعمل، وزر رفع الإيقاف لا يظهر ولا يُنفَّذ بلا `security.manage`.
    3. الطبقة الوسيطة: الإيقاف المؤقت الصامت، السلة الحسّاسة، تمييز الأدمن.
    4. تنبيه الأخطاء: تهدئة، تنقية، تعطيل، وعدم تسريب نص المستخدم.
    5. إعادة جدولة المهام فور تعديل الإعداد بلا إعادة تشغيل وبلا فقدان العدّادات.
"""

from __future__ import annotations

import pytest
from telegram.ext import ApplicationBuilder, ApplicationHandlerStop

from core.exceptions import PermissionDeniedError
from handlers.admin import security as security_screens
from handlers.common.errors import _describe_update, _error_fingerprint, error_handler
from jobs import reschedule_for_setting, schedule_jobs
from jobs.runner import JobRegistry
from keyboards.callback_data import NS_ADM_SEC, NS_FLOW, pack
from middlewares.context import UserContextMiddleware
from middlewares.rate_limit import AbuseGuard, RateLimiter
from services.security_service import LEVEL_BAD, LEVEL_OK, LEVEL_WARN, EnvPosture
from tests.integration.test_user_interface import bot, context, load_user, press  # noqa: F401
from tests.telegram_fakes import FakeBot, FakeContext, make_callback_update, make_message_update
from utils.fs_security import PathCheck

pytestmark = pytest.mark.asyncio


class Clock:
    """ساعة يدوية للتحكم بالزمن دون انتظار."""

    def __init__(self) -> None:
        self.now = 5000.0

    def __call__(self) -> float:
        return self.now


async def _log_event(services, event: str, user_id: int | None, **details) -> None:
    """تسجيل حدث أمني تجريبي."""
    await services.audit.log_security_event(event=event, user_id=user_id, target_type="user", target_id=user_id, details=details)


# ============================== خدمة الأمان ============================== #


async def test_counters_reflect_recent_events(services, user, admin, super_admin) -> None:
    """العدّادات تحسب كل فئة بحسب أحداثها."""
    await services.audit.log_permission_denied(user_id=user.id, permission="orders.cancel", context="t")
    await services.audit.log_permission_denied(user_id=user.id, permission="users.ban", context="t")
    await _log_event(services, "rate_limit_block", user.id)
    await _log_event(services, "hierarchy_denied", admin.id)
    await _log_event(services, "over_credit_blocked", admin.id)
    await _log_event(services, "adjust_cap_exceeded", admin.id)

    counters = await services.security.counters(super_admin)
    assert counters.permission_denied == 2
    assert counters.rate_limit_blocks == 1
    assert counters.rbac_blocks == 1
    assert counters.money_blocks == 2
    assert counters.total_events == 6
    assert counters.top_denied == ((user.id, 2),)


async def test_events_are_paginated_newest_first(services, user, super_admin) -> None:
    """صفحات الأحداث: الأحدث أولاً وعدد الصفحات صحيح، والصفحة الخارجة عن النطاق تُقصّ."""
    for index in range(11):
        await _log_event(services, "hierarchy_denied", user.id, n=index)
    first = await services.security.events(super_admin, page=1, page_size=5)
    assert first.total == 11 and first.total_pages == 3 and len(first.items) == 5
    assert first.items[0].id > first.items[-1].id
    last = await services.security.events(super_admin, page=99, page_size=5)
    assert last.page == 3 and len(last.items) == 1
    assert first.names[user.id]


async def test_events_only_include_security_prefix(services, user, super_admin, admin) -> None:
    """الأحداث الأمنية لا تخلط معها سجلات التدقيق العادية."""
    await services.users.ban(admin, user.id, "سبب كافٍ")           # سجل users.ban عادي
    result = await services.security.events(super_admin, page=1)
    assert all(item.action.startswith("security.") for item in result.items)


async def test_team_lists_staff_with_overrides(services, super_admin, admin, user) -> None:
    """الفريق يعرض غير العملاء مرتباً بالدور مع عدد الاستثناءات."""
    await services.auth.set_user_permission(super_admin, admin.id, "backup.create", allow=True)
    team = await services.security.team(super_admin)
    names = [(member.user.id, member.overrides) for member in team]
    assert names[0][0] == super_admin.id
    assert (admin.id, 1) in names
    assert user.id not in [member.user.id for member in team]


async def test_posture_healthy_defaults_have_no_bad_items(services, super_admin) -> None:
    """الوضع الافتراضي: لا «خطر»، وبه تنبيه الأدمن الأعلى الوحيد."""
    checks = await services.security.posture(super_admin, EnvPosture(alert_chat_set=True))
    assert not [c for c in checks if c.level == LEVEL_BAD]
    titles = {c.title: c for c in checks}
    assert titles["الأدمن الأعلى"].level == LEVEL_WARN          # حساب واحد فقط
    assert titles["منع التنفيذ الذاتي"].level == LEVEL_OK


async def test_posture_flags_weak_configuration(services, repos, db, super_admin, admin) -> None:
    """الإعدادات الضعيفة تظهر: تعطيل four-eyes، بلا سقوف، مزود http، استثناء خطر، ملف مفتوح."""
    await services.settings.set("security_block_self_actions", "false", admin_id=super_admin.id)
    await services.settings.set("admin_adjust_max_units", "0", admin_id=super_admin.id)
    await services.settings.set("admin_adjust_daily_max_units", "0", admin_id=super_admin.id)
    await services.settings.set("maintenance_mode", "true", admin_id=super_admin.id)
    await services.auth.set_user_permission(super_admin, admin.id, "backup.create", allow=True)
    async with db.transaction() as tx:
        await repos.providers.create(
            tx, name="Insecure", api_url="http://plain.example.com/api", api_key_enc="x", api_key_hint="1234"
        )
    insecure_file = PathCheck(path=__import__("pathlib").Path("/x/.env"), label="ملف البيئة .env (سر)", mode=0o644, insecure=True)

    checks = {c.title: c for c in await services.security.posture(
        super_admin, EnvPosture(bot_token_set=True, encryption_key_set=False, path_checks=(insecure_file,))
    )}
    assert checks["منع التنفيذ الذاتي"].level == LEVEL_WARN
    assert checks["سقف التسوية اليدوية"].level == LEVEL_WARN
    assert checks["اتصال المزودين"].level == LEVEL_BAD
    assert checks["الاستثناءات الفردية"].level == LEVEL_WARN
    assert checks["وضع الصيانة"].level == LEVEL_WARN
    assert checks["صلاحيات الملفات"].level == LEVEL_WARN
    assert checks["مفتاح تشفير مفاتيح المزودين"].level == LEVEL_BAD


async def test_clear_block_requires_manage_and_is_audited(services, repos, user, admin, super_admin) -> None:
    """رفع الإيقاف يحتاج `security.manage` (الأدمن العادي مرفوض) ويُدقَّق."""
    guard = AbuseGuard(clock=Clock())
    guard.record_violation(user.telegram_id, strikes_limit=1, block_seconds=300)

    with pytest.raises(PermissionDeniedError):
        await services.security.clear_block(admin, user.telegram_id, guard)
    assert guard.is_blocked(user.telegram_id)

    assert await services.security.clear_block(super_admin, user.telegram_id, guard) is True
    assert not guard.is_blocked(user.telegram_id)
    assert await repos.audit.count_by_action_prefix("security.block_cleared") == 1
    assert await services.security.clear_block(super_admin, user.telegram_id, guard) is False


async def test_blocked_users_listing(services, user, admin) -> None:
    """قائمة الموقوفين تعرض الاسم والمتبقي وعدد المخالفات."""
    guard = AbuseGuard(clock=Clock())
    guard.record_violation(user.telegram_id, strikes_limit=1, block_seconds=120)
    [item] = await services.security.blocked_users(admin, guard)
    assert item.telegram_id == user.telegram_id and item.name == "@tester"
    assert 100 < item.seconds_left <= 121 and item.strikes == 1
    assert await services.security.blocked_users(admin, None) == []


# ============================== شاشات اللوحة ============================== #


async def test_security_home_screen_renders_for_admin(bot, context, services, admin) -> None:  # noqa: F811
    """الأدمن يفتح الشاشة الرئيسية فيرى العدّادات والفحوص وأزرار التنقل."""
    await load_user(bot, context, admin)
    await _log_event(services, "hierarchy_denied", admin.id)
    await press(bot, context, security_screens.home_screen, "sc:home", admin.telegram_id)
    text = bot.last.text
    assert "الأمان" in text and "آخر 24 ساعة" in text and "وضع الأمان" in text
    expected = {pack(NS_ADM_SEC, "events", 1), pack(NS_ADM_SEC, "blocks"), pack(NS_ADM_SEC, "team"), pack(NS_ADM_SEC, "home")}
    assert expected <= set(bot.last.buttons)


async def test_security_screens_denied_without_permission(bot, context, services, user) -> None:  # noqa: F811
    """العميل العادي لا يفتح أي شاشة أمان."""
    await load_user(bot, context, user)
    for action, handler in (
        ("home", security_screens.home_screen),
        ("events:1", security_screens.events_screen),
        ("blocks", security_screens.blocks_screen),
        ("team", security_screens.team_screen),
        ("unblock:5", security_screens.unblock_action),
    ):
        bot.clear()
        await press(bot, context, handler, f"sc:{action}", user.telegram_id)
        assert not bot.sent, f"عُرضت شاشة {action} لعميل عادي"


async def test_security_events_and_team_screens(bot, context, services, admin, super_admin) -> None:  # noqa: F811
    """شاشتا الأحداث والفريق تعرضان محتواهما العربي وزر الرجوع."""
    await load_user(bot, context, admin)
    await press(bot, context, security_screens.events_screen, "sc:events:1", admin.telegram_id)
    assert "لا توجد أحداث" in bot.last.text

    await _log_event(services, "self_ban_blocked", admin.id)
    bot.clear()
    await press(bot, context, security_screens.events_screen, "sc:events:1", admin.telegram_id)
    assert "منع حظر النفس" in bot.last.text
    assert pack(NS_ADM_SEC, "home") in bot.last.buttons

    bot.clear()
    await press(bot, context, security_screens.team_screen, "sc:team", admin.telegram_id)
    assert "أدمن أعلى" in bot.last.text and "أدمن" in bot.last.text


async def test_blocks_screen_unblock_button_only_for_manager(bot, context, services, user, admin, super_admin) -> None:  # noqa: F811
    """زر رفع الإيقاف يظهر للأدمن الأعلى فقط، وضغطه من الأدمن العادي لا يرفع شيئاً."""
    guard = AbuseGuard(clock=Clock())
    guard.record_violation(user.telegram_id, strikes_limit=1, block_seconds=300)
    context.bot_data["abuse_guard"] = guard
    unblock_data = f"sc:unblock:{user.telegram_id}"
    unblock_button = pack(NS_ADM_SEC, "unblock", user.telegram_id)

    await load_user(bot, context, admin)
    await press(bot, context, security_screens.blocks_screen, "sc:blocks", admin.telegram_id)
    assert "@tester" in bot.last.text
    assert unblock_button not in bot.last.buttons

    bot.clear()
    await press(bot, context, security_screens.unblock_action, unblock_data, admin.telegram_id)
    assert guard.is_blocked(user.telegram_id), "رُفع الإيقاف بلا صلاحية"

    context.user_data.clear()
    await load_user(bot, context, super_admin)
    await press(bot, context, security_screens.blocks_screen, "sc:blocks", super_admin.telegram_id)
    assert unblock_button in bot.last.buttons

    bot.clear()
    await press(bot, context, security_screens.unblock_action, unblock_data, super_admin.telegram_id)
    assert not guard.is_blocked(user.telegram_id)
    assert "رُفع الإيقاف" in bot.last.text and "لا أحد موقوف" in bot.last.text


# ============================== الطبقة الوسيطة ============================== #


async def _tap(middleware, bot, context, *, user_id: int, text: str = "مرحبا", data: str | None = None) -> bool:
    """تمرير تحديث عبر الطبقة الوسيطة؛ True = مرّ، False = أُوقف."""
    update = (
        make_callback_update(bot, data=data, user_id=user_id)
        if data
        else make_message_update(bot, text=text, user_id=user_id)
    )
    try:
        await middleware(update, context)
    except ApplicationHandlerStop:
        return False
    return True


async def test_middleware_warns_then_blocks_then_ignores_silently(bot, context, services, repos, super_admin) -> None:  # noqa: F811
    """حد → تحذير → إيقاف مؤقت مُدقَّق → تجاهل صامت → عودة بعد رفع الإيقاف/انتهاء المدة."""
    await services.settings.set("rate_limit_actions_per_minute", "3", admin_id=super_admin.id)
    await services.settings.set("rate_limit_strikes_before_block", "2", admin_id=super_admin.id)
    await services.settings.set("rate_limit_block_minutes", "1", admin_id=super_admin.id)
    clock = Clock()
    guard = AbuseGuard(clock=clock)
    middleware = UserContextMiddleware(RateLimiter(clock=clock), guard)
    uid = 424_242

    assert all([await _tap(middleware, bot, context, user_id=uid) for _ in range(3)])
    bot.clear()
    assert await _tap(middleware, bot, context, user_id=uid) is False         # مخالفة 1 ⇒ تحذير
    assert "أبطئ" in bot.last.text

    bot.clear()
    clock.now += 11                                                           # بعد تهدئة التحذير لكن داخل النافذة
    assert await _tap(middleware, bot, context, user_id=uid) is False         # مخالفة 2 ⇒ إيقاف
    assert "إيقاف استخدامك" in bot.last.text
    assert guard.is_blocked(uid)
    assert await repos.audit.count_by_action_prefix("security.rate_limit_block") == 1

    bot.clear()
    assert await _tap(middleware, bot, context, user_id=uid) is False         # تجاهل صامت
    assert not bot.sent and not bot.answers

    clock.now += 61                                                           # انتهت مدة الإيقاف والنافذة
    assert await _tap(middleware, bot, context, user_id=uid) is True


async def test_middleware_sensitive_bucket_is_tighter(bot, context, services, super_admin) -> None:  # noqa: F811
    """زر التأكيد يخضع لحد أضيق من التصفح، ولا يستهلك التصفح العادي حصته."""
    await services.settings.set("rate_limit_sensitive_per_minute", "1", admin_id=super_admin.id)
    clock = Clock()
    middleware = UserContextMiddleware(RateLimiter(clock=clock), AbuseGuard(clock=clock))
    confirm = pack(NS_FLOW, "confirm")
    uid = 535_353

    assert await _tap(middleware, bot, context, user_id=uid, data=confirm) is True
    assert await _tap(middleware, bot, context, user_id=uid, data=confirm) is False
    assert await _tap(middleware, bot, context, user_id=uid, text="تصفح عادي") is True


async def test_middleware_staff_gets_higher_limits(bot, context, services, admin, super_admin) -> None:  # noqa: F811
    """الفريق الإداري له حد عام أعلى، فلا يُخنق أثناء التنقل بين الشاشات."""
    await services.settings.set("rate_limit_actions_per_minute", "3", admin_id=super_admin.id)
    clock = Clock()
    middleware = UserContextMiddleware(RateLimiter(clock=clock), AbuseGuard(clock=clock))
    results = [await _tap(middleware, bot, context, user_id=admin.telegram_id) for _ in range(12)]
    assert all(results)
    regular = [await _tap(middleware, bot, context, user_id=616_161) for _ in range(5)]
    assert regular == [True, True, True, False, False]


# ============================== تنبيه الأخطاء ============================== #


def _raise_here(message: str) -> BaseException:
    """رفع واستلام استثناء حقيقي ليحمل traceback (مطلوب للبصمة)."""
    try:
        raise RuntimeError(message)
    except RuntimeError as exc:
        return exc


def _raise_there(message: str) -> BaseException:
    """نفس النوع من موضع مختلف ⇒ بصمة مختلفة."""
    try:
        raise RuntimeError(message)
    except RuntimeError as exc:
        return exc


async def _alerts_for(services, user) -> list:
    """إشعارات «خطأ غير متوقع» التي وصلت مستخدماً."""
    items = await services.repos.notifications.list_for_user(user.id)
    return [item for item in items if "خطأ غير متوقع" in item.title]


async def test_error_alert_goes_to_log_viewers_with_sanitized_snippet(services, admin, super_admin, user) -> None:
    """التنبيه يصل من يملك `logs.view` فقط، منقّى، بلا traceback."""
    fake_bot = FakeBot()
    ctx = FakeContext(fake_bot, services)
    ctx.error = _raise_here("فشل api_key=SUPERSECRET12345 أثناء الإرسال")
    await error_handler(None, ctx)

    admin_alerts = await _alerts_for(services, admin)
    assert len(admin_alerts) == 1 and len(await _alerts_for(services, super_admin)) == 1
    assert not await _alerts_for(services, user)
    body = admin_alerts[0].message
    assert "RuntimeError" in body and "SUPERSECRET12345" not in body and "Traceback" not in body


async def test_error_alert_is_throttled_per_fingerprint(services, admin) -> None:
    """الخطأ نفسه لا يُنبَّه به ثانية في فترة التهدئة، والخطأ من موضع آخر يُنبَّه."""
    ctx = FakeContext(FakeBot(), services)
    for _ in range(3):
        ctx.error = _raise_here("نفس الخطأ")
        await error_handler(None, ctx)
    assert len(await _alerts_for(services, admin)) == 1

    ctx.error = _raise_there("خطأ من مكان آخر")
    await error_handler(None, ctx)
    assert len(await _alerts_for(services, admin)) == 2
    assert _error_fingerprint(_raise_here("a")) != _error_fingerprint(_raise_there("a"))


async def test_error_alert_can_be_disabled(services, admin, super_admin) -> None:
    """الإعداد يعطّل التنبيه، لكن الخطأ يبقى مخزَّناً في السجل."""
    await services.settings.set("error_alert_enabled", "false", admin_id=super_admin.id)
    ctx = FakeContext(FakeBot(), services)
    ctx.error = _raise_here("خطأ صامت")
    await error_handler(None, ctx)
    assert not await _alerts_for(services, admin)
    assert await services.repos.error_logs.count_since("2000-01-01T00:00:00Z") == 1


async def test_error_handler_does_not_log_plain_user_text(bot) -> None:  # noqa: F811
    """وصف التحديث لا يحمل نص المستخدم العادي (قد يكون مفتاح API) لكنه يحمل اسم الأمر."""
    secret_text = make_message_update(bot, text="my-provider-key-ABCDEF123456", user_id=5)
    command = make_message_update(bot, text="/admin now", user_id=5)
    assert "ABCDEF123456" not in _describe_update(secret_text)
    assert "/admin" in _describe_update(command)


# ====================== إعادة الجدولة الحيّة للمهام ====================== #


def _interval_of(application, name: str) -> float:
    """فترة تكرار مهمة مجدولة فعلاً على JobQueue."""
    [job] = application.job_queue.get_jobs_by_name(name)
    return job.job.trigger.interval.total_seconds()


@pytest.fixture
def app_with_jobs(services):
    """تطبيق حقيقي (غير مشغَّل) للتحقق من الجدولة الفعلية."""
    return ApplicationBuilder().token("123456789:AAJobsTestDummyTokenNotUsedAtAll").build()


async def test_changing_interval_setting_reschedules_job_live(app_with_jobs, services, super_admin) -> None:
    """تعديل فترة المتابعة من الإعدادات يغيّر جدول المهمة فوراً مع إبقاء عدّاداتها."""
    registry = JobRegistry()
    try:
        await schedule_jobs(app_with_jobs, services, registry=registry)
        assert _interval_of(app_with_jobs, "orders_check") == 120
        registry.stats["orders_check"].runs = 7
        submit_before = _interval_of(app_with_jobs, "orders_submit")

        await services.settings.set("order_check_interval_seconds", "300", admin_id=super_admin.id)

        assert _interval_of(app_with_jobs, "orders_check") == 300
        assert len(app_with_jobs.job_queue.get_jobs_by_name("orders_check")) == 1, "تكرر تسجيل المهمة"
        assert registry.stats["orders_check"].interval_seconds == 300
        assert registry.stats["orders_check"].runs == 7, "ضاعت عدّادات المهمة"
        assert _interval_of(app_with_jobs, "orders_submit") == submit_before, "تأثرت مهمة غير معنية"
    finally:
        await app_with_jobs.shutdown()


async def test_unrelated_setting_does_not_touch_jobs(app_with_jobs, services, super_admin) -> None:
    """مفتاح لا يخص المهام لا يعيد جدولة شيء."""
    registry = JobRegistry()
    try:
        await schedule_jobs(app_with_jobs, services, registry=registry)
        assert await reschedule_for_setting(app_with_jobs, services, "bot_name", registry=registry) == []
        await services.settings.set("bot_name", "متجري", admin_id=super_admin.id)
        assert len(app_with_jobs.job_queue.jobs()) == 13
    finally:
        await app_with_jobs.shutdown()


async def test_daily_job_hour_change_reschedules(app_with_jobs, services, super_admin) -> None:
    """تغيير ساعة الملخص اليومي يعيد جدولة المهمة اليومية."""
    registry = JobRegistry()
    try:
        await schedule_jobs(app_with_jobs, services, registry=registry)
        await services.settings.set("admin_digest_hour", "7", admin_id=super_admin.id)
        [job] = app_with_jobs.job_queue.get_jobs_by_name("admin_daily_digest")
        assert "07:00" in registry.stats["admin_daily_digest"].schedule_text
        assert job is not None
    finally:
        await app_with_jobs.shutdown()


async def test_failure_threshold_change_reinstalls_all_jobs_once_each(app_with_jobs, services, super_admin) -> None:
    """تغيير عتبة التنبيه يعيد تركيب كل المهام بلا تكرار أو فقدان."""
    registry = JobRegistry()
    try:
        await schedule_jobs(app_with_jobs, services, registry=registry)
        await services.settings.set("job_failure_alert_threshold", "5", admin_id=super_admin.id)
        assert len(app_with_jobs.job_queue.jobs()) == 13
        names = [job.name for job in app_with_jobs.job_queue.jobs()]
        assert len(names) == len(set(names))
    finally:
        await app_with_jobs.shutdown()
