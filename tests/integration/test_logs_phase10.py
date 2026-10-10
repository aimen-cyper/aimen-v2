"""
اختبارات المرحلة 10 — واجهة السجلات: فلتر فئات التدقيق، التفاصيل، الأخطاء، واستدعاءات المزودين.

تثبّت: دقة الترقيم والعدّ، عدم تسريب الأسرار في التفاصيل (حتى لو دخلت السجل قبل تسجيلها)،
تهريب HTML، رفض الفئات المزوّرة، رفض الصلاحية على الـcallback، وأن الشاشات للقراءة فقط.
"""

from __future__ import annotations

import pytest

from database.models import Provider, User
from database.repositories import Repositories
from handlers.admin import logs
from keyboards.callback_data import pack
from services import ServiceContainer
from services.audit_service import AUDIT_CATEGORIES
from tests.integration.test_user_interface import (  # إعادة استخدام أدوات الواجهة نفسها
    bot,  # noqa: F401
    context,  # noqa: F401
    load_user,
    press,
)
from tests.telegram_fakes import FakeBot, FakeContext
from texts import admin_ar as t

pytestmark = pytest.mark.asyncio

#: كل أسماء الإجراءات التي تكتبها الخدمات والسكربتات فعلياً (مستخرجة من الشيفرة)
REAL_ACTIONS = (
    "admin.create_via_script", "admin.role_change_via_script", "admins.permission.clear",
    "admins.permission.override", "backup.create", "backup.create_failed", "backup.download",
    "backup.purge", "backup.restore", "backup.send_channel", "backup.vacuum", "backup.verify",
    "broadcast.send", "notifications.templates", "orders.cancel", "orders.link_provider_id",
    "orders.refund", "orders.status.override", "payments.approve", "payments.methods",
    "payments.reject", "providers.create", "providers.key.update", "providers.update",
    "security.permission_denied", "services.archive", "services.category.create",
    "services.create", "services.price", "services.sync", "services.update", "settings.update",
    "stats.export", "system.promote_super_admin", "system.seed_super_admin", "tickets.assign",
    "tickets.close", "tickets.reply", "users.balance.credit", "users.balance.debit", "users.ban",
    "users.note", "users.register", "users.role.change", "users.unban",
)


def _categories_of(action: str) -> list[str]:
    """الفئات (غير `all`) التي تلتقط إجراءً بعينه."""
    return [
        key for key, prefixes in AUDIT_CATEGORIES.items()
        if prefixes and any(action.startswith(prefix) for prefix in prefixes)
    ]


async def _log(services: ServiceContainer, action: str, admin: User | None = None, **extra) -> None:
    """تسجيل عملية تدقيق حقيقية عبر الخدمة."""
    await services.audit.log_standalone(
        action=action, admin_id=admin.id if admin else None, target_type="x", target_id="1", **extra
    )


# ======================================================================== #
#                              الفئات والفلتر                                #
# ======================================================================== #


async def test_every_real_action_belongs_to_exactly_one_category() -> None:
    """لا إجراء يضيع من الفلاتر ولا يظهر في فئتين (العدّ يطابق المعروض)."""
    for action in REAL_ACTIONS:
        assert len(_categories_of(action)) == 1, (action, _categories_of(action))


async def test_icons_match_real_action_prefixes() -> None:
    """كل بادئة فعلية لها أيقونة (لا 🔸 افتراضية بسبب أسماء مفردة خاطئة)."""
    for action in REAL_ACTIONS:
        prefix = action.split(".", 1)[0]
        assert prefix in t.AUDIT_ICONS, prefix
        assert logs._audit_icon(action) == t.AUDIT_ICONS[prefix]
    assert logs._audit_icon("unknown.thing") == "🔸"


async def test_category_labels_cover_all_categories() -> None:
    """كل فئة لها اسم عربي ولا اسم بلا فئة."""
    assert set(t.AUDIT_CATEGORY_LABELS) == set(AUDIT_CATEGORIES)


async def test_filter_returns_only_category_and_counts_match(
    services: ServiceContainer, admin: User
) -> None:
    """الفلتر يعيد سجلات الفئة فقط وعدّها مطابق لما يُعرض."""
    for action in ("payments.approve", "payments.reject", "users.ban", "orders.refund", "users.balance.credit"):
        await _log(services, action, admin)

    money = await services.audit.list_filtered("money", limit=50)
    assert {e.action for e in money} == {"payments.approve", "payments.reject", "users.balance.credit"}
    assert await services.audit.count_filtered("money") == 3
    assert await services.audit.count_filtered("orders") == 1
    assert await services.audit.count_filtered("all") == await services.audit.count()


async def test_unknown_category_is_rejected_not_treated_as_all(services: ServiceContainer) -> None:
    """فئة مزوّرة تُرفض في الخدمة (لا تُعرض كل السجلات صامتةً)."""
    from core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        await services.audit.list_filtered("hax")
    with pytest.raises(ValidationError):
        await services.audit.count_filtered("")


async def test_like_wildcards_in_prefix_do_not_match_everything(
    services: ServiceContainer, repos: Repositories, admin: User
) -> None:
    """`_` و`%` في البادئة تُعامل حرفياً (حقن LIKE)."""
    await _log(services, "usersXban", admin)
    assert await repos.audit.count_by_prefixes(("users_ban",)) == 0
    assert await repos.audit.count_by_prefixes(("%",)) == 0


# ======================================================================== #
#                              شاشة التدقيق                                  #
# ======================================================================== #


async def test_audit_screen_paginates_accurately(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, admin: User
) -> None:
    """20 سجلاً بحجم صفحة 8 ⇒ 3 صفحات؛ الصفحة الأخيرة فيها المتبقي فقط."""
    start = await services.audit.count()
    for index in range(20):
        await _log(services, "payments.approve", admin, details={"n": index})
    total = start + 20
    await load_user(bot, context, admin)

    await press(bot, context, logs.audit_screen, pack("al", "acat", "money", 3), admin.telegram_id)
    assert "الصفحة 3 من 3" in bot.last.text
    assert bot.last.text.count("payments.approve") == 20 - 16

    await press(bot, context, logs.audit_screen, pack("al", "audit", 1), admin.telegram_id)
    assert f"{total} سجلاً" in bot.last.text
    detail_buttons = [b for b in bot.last.buttons if b.startswith("al:aud:")]
    assert len(detail_buttons) == 8


async def test_audit_filter_menu_and_selection(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, admin: User
) -> None:
    """قائمة الفلتر فيها كل الفئات وكل زر يعمل؛ الاختيار يعرض فئته فقط."""
    await _log(services, "tickets.close", admin)
    await _log(services, "users.ban", admin)
    await load_user(bot, context, admin)

    await press(bot, context, logs.audit_filter_screen, pack("al", "afl", "all"), admin.telegram_id)
    for key in AUDIT_CATEGORIES:
        assert pack("al", "acat", key, 1) in bot.last.buttons

    await press(bot, context, logs.audit_screen, pack("al", "acat", "tickets", 1), admin.telegram_id)
    assert "tickets.close" in bot.last.text and "users.ban" not in bot.last.text


async def test_empty_category_says_so(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """فئة بلا سجلات: رسالة واضحة وأزرار عودة."""
    await load_user(bot, context, admin)
    await press(bot, context, logs.audit_screen, pack("al", "acat", "catalog", 1), admin.telegram_id)
    assert "لا عمليات" in bot.last.text and bot.last.buttons


async def test_forged_category_button_shows_error(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """زر بفئة مزوّرة لا يُسقط البوت ولا يعرض شيئاً من السجلات."""
    await load_user(bot, context, admin)
    await press(bot, context, logs.audit_screen, pack("al", "acat", "hax", 1), admin.telegram_id)
    shown = " ".join(m.text for m in bot.sent) + " ".join(str(a["text"]) for a in bot.answers)
    assert "فئة سجل غير معروفة" in shown


# ======================================================================== #
#                             تفاصيل سجل التدقيق                             #
# ======================================================================== #


async def test_audit_detail_shows_before_after(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, repos: Repositories, admin: User
) -> None:
    """التفاصيل تعرض الإجراء والمنفّذ وقيم قبل/بعد بتنسيق مقروء."""
    async with repos.db.transaction() as tx:
        entry_id = await services.audit.log(
            tx, action="settings.update", admin_id=admin.id, target_type="setting", target_id="min_order",
            before={"value": "20000"}, after={"value": "30000"}, details={"note": "اختبار"},
        )
    await load_user(bot, context, admin)
    await press(bot, context, logs.audit_detail_screen, pack("al", "aud", entry_id, "settings", 1), admin.telegram_id)

    text = bot.last.text
    assert "settings.update" in text and "20000" in text and "30000" in text
    assert t.AUDIT_DETAIL_BLOCK_TITLES["before"] in text and t.AUDIT_DETAIL_BLOCK_TITLES["after"] in text
    assert pack("al", "acat", "settings", 1) in bot.last.buttons          # الرجوع لنفس الفئة والصفحة


async def test_audit_detail_escapes_html(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, repos: Repositories, admin: User
) -> None:
    """نص يحوي وسوم HTML لا يكسر العرض (يُهرَّب)."""
    async with repos.db.transaction() as tx:
        entry_id = await services.audit.log(
            tx, action="users.note", admin_id=admin.id, details={"note": "<b>خطر</b><script>x</script>"}
        )
    await load_user(bot, context, admin)
    await press(bot, context, logs.audit_detail_screen, pack("al", "aud", entry_id, "all", 1), admin.telegram_id)
    assert "<script>" not in bot.last.text and "&lt;script&gt;" in bot.last.text


async def test_audit_detail_redacts_secrets_even_for_legacy_rows(
    bot: FakeBot, context: FakeContext, repos: Repositories, admin: User, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """سر دخل السجل قبل تسجيله كسرّ معروف لا يظهر في التفاصيل (تنقية ثانية عند العرض)."""
    import utils.security as security

    monkeypatch.setattr(security, "_KNOWN_SECRETS", set(security._KNOWN_SECRETS))
    secret = "LEGACY-SECRET-VALUE-9876543210"
    async with repos.db.transaction() as tx:               # إدخال خام يتجاوز تنقية الكتابة
        cursor = await tx.execute(
            "INSERT INTO audit_logs (admin_id, action, details_json, source, created_at) VALUES (?,?,?,?,?)",
            (admin.id, "providers.update", f'{{"leak": "{secret}"}}', "telegram", "2026-01-01T00:00:00+00:00"),
        )
        entry_id = cursor.lastrowid
    security.register_secret(secret)

    await load_user(bot, context, admin)
    await press(bot, context, logs.audit_detail_screen, pack("al", "aud", entry_id, "all", 1), admin.telegram_id)
    assert secret not in bot.last.text and "***" in bot.last.text


async def test_audit_detail_truncates_long_values(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, repos: Repositories, admin: User
) -> None:
    """قيمة ضخمة تُقتطع فلا تتجاوز حد رسالة تيليجرام."""
    async with repos.db.transaction() as tx:
        entry_id = await services.audit.log(
            tx, action="settings.update", admin_id=admin.id,
            before={"v": "ب" * 5000}, after={"v": "ا" * 5000}, details={"v": "ج" * 5000},
        )
    await load_user(bot, context, admin)
    await press(bot, context, logs.audit_detail_screen, pack("al", "aud", entry_id, "all", 1), admin.telegram_id)
    assert len(bot.last.text) < 4096


async def test_audit_detail_missing_entry(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """معرّف غير موجود: رسالة واضحة لا استثناء."""
    await load_user(bot, context, admin)
    await press(bot, context, logs.audit_detail_screen, pack("al", "aud", 999999, "all", 1), admin.telegram_id)
    assert t.AUDIT_NOT_FOUND in bot.last.text


# ======================================================================== #
#                                  الأخطاء                                  #
# ======================================================================== #


async def _error(repos: Repositories, **kwargs) -> int:
    """تسجيل خطأ اختباري وإرجاع معرّفه."""
    async with repos.db.transaction() as tx:
        return await repos.error_logs.log(tx, **{"message": "خطأ", "source": "tests", **kwargs})


async def test_errors_screen_counts_and_paginates(
    bot: FakeBot, context: FakeContext, repos: Repositories, admin: User
) -> None:
    """11 خطأً ⇒ صفحتان بإجمالي دقيق وأزرار تفاصيل."""
    for index in range(11):
        await _error(repos, message=f"عطل رقم {index}")
    await load_user(bot, context, admin)
    await press(bot, context, logs.errors_screen, pack("al", "errors", 1), admin.telegram_id)
    assert "11 خطأً" in bot.last.text and "الصفحة 1 من 2" in bot.last.text
    assert len([b for b in bot.last.buttons if b.startswith("al:err:")]) == 8

    await press(bot, context, logs.errors_screen, pack("al", "errors", 2), admin.telegram_id)
    assert len([b for b in bot.last.buttons if b.startswith("al:err:")]) == 3


async def test_error_detail_shows_trace_and_redacts(
    bot: FakeBot, context: FakeContext, repos: Repositories, admin: User, user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """تفاصيل الخطأ: النوع والأثر والمستخدم وملخص التحديث؛ والأسرار المسجّلة لاحقاً تُخفى."""
    import utils.security as security

    monkeypatch.setattr(security, "_KNOWN_SECRETS", set(security._KNOWN_SECRETS))
    secret = "TRACE-SECRET-VALUE-1234567890"
    error_id = await _error(
        repos, error_type="KeyError", message="فشل <b>حرج</b>", user_id=user.id,
        traceback_snippet=f"File x.py line 3\n  token={secret}", update_summary="callback:st:home",
    )
    security.register_secret(secret)

    await load_user(bot, context, admin)
    await press(bot, context, logs.error_detail_screen, pack("al", "err", error_id, 1), admin.telegram_id)
    text = bot.last.text
    assert "KeyError" in text and "File x.py" in text and "callback:st:home" in text
    assert secret not in text
    assert "<b>حرج</b>" not in text and "&lt;b&gt;" in text


async def test_error_detail_missing(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """خطأ غير موجود: رسالة واضحة."""
    await load_user(bot, context, admin)
    await press(bot, context, logs.error_detail_screen, pack("al", "err", 424242, 1), admin.telegram_id)
    assert t.ERROR_NOT_FOUND in bot.last.text


# ======================================================================== #
#                           استدعاءات المزودين                                #
# ======================================================================== #


async def _calls(repos: Repositories, provider: Provider) -> None:
    """استدعاءان ناجحان وآخر فاشل."""
    async with repos.db.transaction() as tx:
        await repos.provider_requests.log(
            tx, provider_id=provider.id, action="balance", is_success=True, http_status=200,
            duration_ms=120, response_snippet='{"balance": "10"}',
        )
        await repos.provider_requests.log(
            tx, provider_id=provider.id, action="status", is_success=True, http_status=200, duration_ms=80,
        )
        await repos.provider_requests.log(
            tx, provider_id=provider.id, action="add", is_success=False, http_status=500, duration_ms=2000,
            error_type="ProviderTemporaryError", request_summary="service=1 qty=1000",
            response_snippet="Internal <error>",
        )


async def test_provider_calls_list_and_failed_filter(
    bot: FakeBot, context: FakeContext, repos: Repositories, provider: Provider, admin: User
) -> None:
    """القائمة تعرض الكل مع اسم المزود؛ وفلتر «الفاشلة» يعرض الفاشل فقط."""
    await _calls(repos, provider)
    await load_user(bot, context, admin)

    await press(bot, context, logs.calls_screen, pack("al", "prq", 1), admin.telegram_id)
    assert "3 استدعاءً" in bot.last.text and provider.name in bot.last.text
    assert len([b for b in bot.last.buttons if b.startswith("al:prqd:")]) == 3
    assert pack("al", "prqf", 1) in bot.last.buttons

    await press(bot, context, logs.calls_failed_screen, pack("al", "prqf", 1), admin.telegram_id)
    assert "1 استدعاءً" in bot.last.text and "ProviderTemporaryError" in bot.last.text
    assert len([b for b in bot.last.buttons if b.startswith("al:prqd:")]) == 1
    assert pack("al", "prq", 1) in bot.last.buttons


async def test_provider_call_detail(
    bot: FakeBot, context: FakeContext, repos: Repositories, provider: Provider, admin: User
) -> None:
    """تفاصيل الاستدعاء الفاشل: HTTP والمدة والخطأ وملخص الطلب ومقتطف الرد (مهرَّب)."""
    await _calls(repos, provider)
    failed = (await repos.provider_requests.list_page(only_failed=True, limit=1))[0]
    await load_user(bot, context, admin)
    await press(bot, context, logs.call_detail_screen, pack("al", "prqd", failed["id"], "f", 1), admin.telegram_id)

    text = bot.last.text
    assert "500" in text and "2000ms" in text and "ProviderTemporaryError" in text
    assert "service=1 qty=1000" in text and "Internal &lt;error&gt;" in text
    assert pack("al", "prqf", 1) in bot.last.buttons


async def test_provider_call_detail_never_shows_api_key(
    bot: FakeBot, context: FakeContext, repos: Repositories, provider: Provider, admin: User,
) -> None:
    """مفتاح مزود ظهر في ملخص الطلب يُنقّى عند التخزين ولا يصل للشاشة."""
    key = "sk_live_ABCDEFGHIJKLMNOP1234"
    async with repos.db.transaction() as tx:
        await repos.provider_requests.log(
            tx, provider_id=provider.id, action="add", is_success=False,
            request_summary=f"key={key} service=1", secrets=(key,),
        )
    row = (await repos.provider_requests.list_page(limit=1))[0]
    await load_user(bot, context, admin)
    await press(bot, context, logs.call_detail_screen, pack("al", "prqd", row["id"], "a", 1), admin.telegram_id)
    assert key not in bot.last.text


async def test_provider_calls_empty_and_missing(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """لا استدعاءات: رسالة واضحة؛ معرّف غير موجود: رسالة لا استثناء."""
    await load_user(bot, context, admin)
    await press(bot, context, logs.calls_screen, pack("al", "prq", 1), admin.telegram_id)
    assert "لا استدعاءات" in bot.last.text
    await press(bot, context, logs.call_detail_screen, pack("al", "prqd", 777, "a", 1), admin.telegram_id)
    assert t.PROVIDER_CALL_NOT_FOUND in bot.last.text


# ======================================================================== #
#                       الصلاحيات والقراءة فقط                                #
# ======================================================================== #


async def test_new_log_screens_require_logs_view(
    bot: FakeBot, context: FakeContext, repos: Repositories, services: ServiceContainer
) -> None:
    """دور الدعم (بلا `logs.view`) مرفوض في كل شاشة جديدة: لا محتوى ولا تلميح."""
    async with repos.db.transaction() as tx:
        support = await repos.users.create(tx, telegram_id=555000222, username="sup2", first_name="S", role="support")
    await load_user(bot, context, support)
    for handler, data in (
        (logs.audit_screen, pack("al", "acat", "money", 1)),
        (logs.audit_filter_screen, pack("al", "afl", "all")),
        (logs.audit_detail_screen, pack("al", "aud", 1, "all", 1)),
        (logs.error_detail_screen, pack("al", "err", 1, 1)),
        (logs.calls_screen, pack("al", "prq", 1)),
        (logs.calls_failed_screen, pack("al", "prqf", 1)),
        (logs.call_detail_screen, pack("al", "prqd", 1, "a", 1)),
    ):
        bot.clear()
        await press(bot, context, handler, data, support.telegram_id)
        assert not bot.sent, data
        assert bot.answers[-1]["alert"] is True


async def test_log_screens_are_read_only(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, repos: Repositories,
    provider: Provider, admin: User,
) -> None:
    """لا زر حذف/تعديل/مسح في أي شاشة سجلات جديدة."""
    await _log(services, "users.ban", admin)
    await _error(repos)
    await _calls(repos, provider)
    entry = (await services.audit.list_filtered("all", limit=1))[0]
    err = (await services.audit.recent_errors(limit=1))[0]
    call = (await repos.provider_requests.list_page(limit=1))[0]
    await load_user(bot, context, admin)
    for handler, data in (
        (logs.audit_screen, pack("al", "acat", "users", 1)),
        (logs.audit_filter_screen, pack("al", "afl", "users")),
        (logs.audit_detail_screen, pack("al", "aud", entry.id, "all", 1)),
        (logs.errors_screen, pack("al", "errors", 1)),
        (logs.error_detail_screen, pack("al", "err", err["id"], 1)),
        (logs.calls_screen, pack("al", "prq", 1)),
        (logs.call_detail_screen, pack("al", "prqd", call["id"], "a", 1)),
    ):
        bot.clear()
        await press(bot, context, handler, data, admin.telegram_id)
        for button in bot.last.buttons:
            assert not any(word in button for word in ("del", "edit", "clear", "purge")), button
