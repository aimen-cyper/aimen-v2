"""
اختبارات المرحلة 10 — الإحصائيات: الفترات المحلية، شاشات الواجهة، الصلاحيات، وتصدير CSV.

تغطي: حدود الفترات (Asia/Aden)، تمييز «لا صلاحية للربح» عن «غير محسوب»، تحييد حقن الصيغ،
سقف الصفوف، غياب البيانات الخاصة من الملف، التدقيق، ورفض الصلاحية على الـcallback نفسه.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

import pytest

from core.permissions import Permission
from database.models import Service, User
from database.repositories import Repositories
from handlers.admin import stats as stats_handlers
from keyboards.callback_data import pack
from services import ServiceContainer
from services.stats_service import EXPORT_KINDS, PERIOD_KEYS, build_period
from tests.integration.test_user_interface import (  # إعادة استخدام أدوات الواجهة نفسها
    bot,  # noqa: F401
    context,  # noqa: F401
    load_user,
    press,
)
from tests.telegram_fakes import FakeBot, FakeContext
from utils.formatters import money_text

pytestmark = pytest.mark.asyncio


async def _orders(services: ServiceContainer, user: User, admin: User, mock_service: Service, count: int = 2) -> None:
    """رصيد + طلبات حقيقية (كل طلب 10_000 وحدة لكمية 1000)."""
    await services.wallet.adjust_balance(
        target=user, amount_units=10_000_000, admin=admin, reason="رصيد اختبار", credit=True
    )
    await services.settings.set("duplicate_order_window_minutes", 0)
    for index in range(count):
        await services.orders.create_order(
            user, service_id=mock_service.id, link=f"https://instagram.com/private{index}", quantity=1000
        )


def _decode(document: bytes) -> list[list[str]]:
    """فك ملف CSV المُرسَل (UTF-8 مع BOM) إلى صفوف."""
    assert document.startswith("\ufeff".encode()), "الملف بلا BOM فلن يفتحه Excel بالعربية"
    return list(csv.reader(io.StringIO(document.decode("utf-8-sig"))))


# ======================================================================== #
#                                الفترات                                    #
# ======================================================================== #


async def test_every_period_key_is_valid() -> None:
    """كل مفتاح معلن يُبنى فترة صالحة بحدّ بداية قبل النهاية."""
    for key in PERIOD_KEYS:
        period = build_period(key)
        assert period.start_iso < period.end_iso, key


async def test_today_starts_at_local_midnight_not_utc() -> None:
    """«اليوم» يبدأ عند منتصف الليل المحلي (UTC+3) لا منتصف ليل UTC، و«أمس» يتصل به بلا فجوة."""
    today, yesterday = build_period("today"), build_period("yesterday")
    start = datetime.fromisoformat(today.start_iso).astimezone(timezone.utc)
    assert start.hour == 21 and start.minute == 0, today.start_iso   # 00:00 محلياً = 21:00 UTC
    assert yesterday.end_iso == today.start_iso
    assert datetime.fromisoformat(today.end_iso) - datetime.fromisoformat(today.start_iso) == timedelta(days=1)


async def test_unknown_period_is_rejected() -> None:
    """مفتاح فترة عبث به مستخدم يُرفض ولا يُحوَّل صامتاً إلى فترة افتراضية."""
    from core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        build_period("forever")


# ======================================================================== #
#                              شاشات الواجهة                                #
# ======================================================================== #


async def test_home_screen_shows_net_revenue(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User, mock_service: Service,
) -> None:
    """شاشة الملخص تعرض الإيراد الصافي الحقيقي من قاعدة البيانات."""
    await _orders(services, user, admin, mock_service, count=2)
    await load_user(bot, context, admin)
    await press(bot, context, stats_handlers.home_screen, pack("st", "home", "today"), admin.telegram_id)

    symbol = await services.settings.money_symbol()
    assert money_text(20_000, symbol) in bot.last.text
    assert "الإحصائيات" in bot.last.text


@pytest.mark.parametrize("key", PERIOD_KEYS)
async def test_all_screens_render_for_every_period(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User,
    mock_service: Service, key: str,
) -> None:
    """كل شاشة × كل فترة تُعرض بلا استثناء وبأزرار تنقل."""
    await _orders(services, user, admin, mock_service, count=1)
    await load_user(bot, context, admin)
    for handler, action in (
        (stats_handlers.home_screen, "home"),
        (stats_handlers.services_screen, "svc"),
        (stats_handlers.buyers_screen, "usr"),
        (stats_handlers.daily_screen, "day"),
    ):
        bot.clear()
        await press(bot, context, handler, pack("st", action, key), admin.telegram_id)
        assert bot.sent, f"{action}/{key}: لا شاشة"
        assert bot.last.buttons, f"{action}/{key}: بلا أزرار"
        assert "❌" not in bot.last.text, f"{action}/{key}: {bot.last.text}"


async def test_unknown_period_button_shows_error(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """زر بفترة مزوّرة لا يُسقط البوت ويُظهر رسالة خطأ عربية."""
    await load_user(bot, context, admin)
    await press(bot, context, stats_handlers.home_screen, pack("st", "home", "forever"), admin.telegram_id)
    assert "فترة غير معروفة" in " ".join(m.text for m in bot.sent) + " ".join(str(a["text"]) for a in bot.answers)


async def test_buyers_and_services_lists_are_real(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User, mock_service: Service,
) -> None:
    """قائمتا أكثر الخدمات والعملاء تعرضان ما في الطلبات فعلاً."""
    await _orders(services, user, admin, mock_service, count=2)
    await load_user(bot, context, admin)
    await press(bot, context, stats_handlers.services_screen, pack("st", "svc", "today"), admin.telegram_id)
    assert mock_service.name in bot.last.text and "2 طلب" in bot.last.text
    await press(bot, context, stats_handlers.buyers_screen, pack("st", "usr", "today"), admin.telegram_id)
    assert "1." in bot.last.text


async def test_empty_period_screens_say_so(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """فترة بلا طلبات: رسائل «لا طلبات» لا أرقام وهمية."""
    await load_user(bot, context, admin)
    await press(bot, context, stats_handlers.services_screen, pack("st", "svc", "yesterday"), admin.telegram_id)
    assert "لا طلبات" in bot.last.text
    await press(bot, context, stats_handlers.daily_screen, pack("st", "day", "yesterday"), admin.telegram_id)
    assert bot.sent


async def test_wallet_screen(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User,
) -> None:
    """شاشة التزامات المحفظة تعرض مجموع أرصدة العملاء."""
    await services.wallet.adjust_balance(target=user, amount_units=50_000, admin=admin, reason="x", credit=True)
    await load_user(bot, context, admin)
    await press(bot, context, stats_handlers.wallet_screen, pack("st", "wal"), admin.telegram_id)
    symbol = await services.settings.money_symbol()
    assert money_text(50_000, symbol) in bot.last.text


# ======================================================================== #
#                         الصلاحيات (على الـcallback)                        #
# ======================================================================== #


async def test_user_without_stats_view_is_denied_everywhere(
    bot: FakeBot, context: FakeContext, repos: Repositories, services: ServiceContainer
) -> None:
    """دور الدعم لا يملك `stats.view`: كل شاشة تُرفض بلا عرض أي رقم."""
    async with repos.db.transaction() as tx:
        support = await repos.users.create(tx, telegram_id=555000111, username="sup", first_name="Sup", role="support")
    await load_user(bot, context, support)
    for handler, data in (
        (stats_handlers.home_screen, pack("st", "home", "today")),
        (stats_handlers.services_screen, pack("st", "svc", "today")),
        (stats_handlers.buyers_screen, pack("st", "usr", "today")),
        (stats_handlers.daily_screen, pack("st", "day", "today")),
        (stats_handlers.wallet_screen, pack("st", "wal")),
        (stats_handlers.export_menu, pack("st", "expm", "today")),
    ):
        bot.clear()
        await press(bot, context, handler, data, support.telegram_id)
        assert not bot.sent, f"سُرِّب محتوى لمستخدم بلا صلاحية: {data}"
        assert bot.answers and bot.answers[-1]["alert"] is True


async def test_profit_visible_only_with_profit_permission(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User,
    super_admin: User, mock_service: Service,
) -> None:
    """الأدمن العادي لا يرى سطر الربح إطلاقاً؛ الأدمن الأعلى يراه (حتى لو «غير محسوب»)."""
    await _orders(services, user, admin, mock_service, count=1)

    await load_user(bot, context, admin)
    await press(bot, context, stats_handlers.home_screen, pack("st", "home", "today"), admin.telegram_id)
    assert "الربح" not in bot.last.text

    bot.clear()
    await load_user(bot, context, super_admin)
    await press(bot, context, stats_handlers.home_screen, pack("st", "home", "today"), super_admin.telegram_id)
    assert "الربح التقديري" in bot.last.text
    assert "غير محسوب" in bot.last.text          # لا طلبات منتهية بعد ⇒ صراحةً لا صفر مختلق


# ======================================================================== #
#                               التصدير                                      #
# ======================================================================== #


async def test_export_requires_confirmation_step(
    bot: FakeBot, context: FakeContext, super_admin: User
) -> None:
    """شاشة التأكيد لا ترسل ملفاً ولا تُدقّق؛ النوع المجهول يُرفض."""
    await load_user(bot, context, super_admin)
    await press(bot, context, stats_handlers.export_menu, pack("st", "expm", "7d"), super_admin.telegram_id)
    assert bot.last.buttons

    bot.clear()
    await press(bot, context, stats_handlers.export_ask, pack("st", "expask", "orders", "7d"), super_admin.telegram_id)
    assert bot.sent and not any(m.kind == "document" for m in bot.sent)

    bot.clear()
    await press(bot, context, stats_handlers.export_ask, pack("st", "expask", "secrets", "7d"), super_admin.telegram_id)
    assert bot.answers[-1]["alert"] is True and not bot.sent


@pytest.mark.parametrize("kind", EXPORT_KINDS)
async def test_export_sends_csv_and_audits(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, repos: Repositories, user: User,
    admin: User, super_admin: User, mock_service: Service, kind: str,
) -> None:
    """التصدير يرسل ملف CSV كمستند محمي ويُدقَّق في `audit_logs`."""
    await _orders(services, user, admin, mock_service, count=2)
    await load_user(bot, context, super_admin)
    await press(bot, context, stats_handlers.export_action, pack("st", "exp", kind, "today"), super_admin.telegram_id)

    documents = [m for m in bot.sent if m.kind == "document"]
    assert len(documents) == 1
    sent = documents[0]
    assert sent.kwargs["filename"].endswith(".csv")
    assert sent.kwargs["protect_content"] is True
    rows = _decode(sent.kwargs["document"])
    assert len(rows) >= 2                      # رأس + بيانات
    audits = [e for e in await repos.audit.list_recent(limit=20) if e.action == "stats.export"]
    assert audits and audits[0].admin_id == super_admin.id and audits[0].target_id == kind


async def test_export_denied_without_permission(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, repos: Repositories, admin: User,
    super_admin: User,
) -> None:
    """سحب `stats.export` من الأدمن: لا ملف ولا تدقيق نجاح، ويُسجَّل الرفض أمنياً."""
    await services.auth.set_user_permission(super_admin, admin.id, Permission.STATS_EXPORT, allow=False)
    await load_user(bot, context, admin)
    await press(bot, context, stats_handlers.export_action, pack("st", "exp", "orders", "today"), admin.telegram_id)

    assert not any(m.kind == "document" for m in bot.sent)
    entries = await repos.audit.list_recent(limit=20)
    assert not any(e.action == "stats.export" for e in entries)
    assert any(e.action == "security.permission_denied" for e in entries)


async def test_export_excludes_private_data(
    services: ServiceContainer, user: User, admin: User, super_admin: User, mock_service: Service,
) -> None:
    """الملف لا يحوي رابط العميل ولا معرّف تيليجرام ولا أي مفتاح."""
    await _orders(services, user, admin, mock_service, count=2)
    exported = await services.stats.export_csv(super_admin, "orders", build_period("today"))
    text = exported.content.decode("utf-8-sig")
    assert "instagram.com" not in text and "private0" not in text
    assert str(user.telegram_id) not in text
    assert exported.rows == 2


async def test_export_neutralizes_formula_injection(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, super_admin: User,
    mock_service: Service,
) -> None:
    """اسم خدمة يبدأ بـ`=` يُسبق بفاصلة عليا فلا يُنفَّذ كمعادلة في Excel."""
    await _orders(services, user, admin, mock_service, count=1)
    order = (await services.orders.list_for_user(user))[0]
    async with repos.db.transaction() as tx:
        await tx.execute(                                  # اللقطة غير قابلة للتعديل عبر المستودع عمداً
            "UPDATE orders SET service_name_snapshot = ? WHERE id = ?",
            ('=HYPERLINK("http://evil","x")', order.id),
        )
    exported = await services.stats.export_csv(super_admin, "orders", build_period("today"))
    body = _decode(exported.content)
    service_cell = body[1][body[0].index("service")]
    assert service_cell.startswith("'="), service_cell
    for row in body[1:]:
        for cell in row:
            assert not cell.startswith(("=", "+", "@")), cell


async def test_export_row_cap_is_declared(
    services: ServiceContainer, repos: Repositories, user: User, admin: User, super_admin: User,
    mock_service: Service,
) -> None:
    """تجاوز `export_max_rows` يقطع الملف ويعلن القطع (لا قطع صامت)."""
    await _orders(services, user, admin, mock_service, count=3)
    async with repos.db.transaction() as tx:                  # تجاوز حد القاعدة الأدنى للاختبار فقط
        await tx.execute("UPDATE settings SET value = '2' WHERE key = 'export_max_rows'")
    exported = await services.stats.export_csv(super_admin, "orders", build_period("today"))
    assert exported.truncated is True
    assert exported.rows == 2


async def test_profit_columns_follow_profit_permission(
    services: ServiceContainer, user: User, admin: User, super_admin: User, mock_service: Service,
) -> None:
    """أعمدة التكلفة/الربح تظهر لمن يملك `stats.profit` فقط."""
    await _orders(services, user, admin, mock_service, count=1)
    await services.auth.set_user_permission(super_admin, admin.id, Permission.STATS_EXPORT, allow=True)
    plain = await services.stats.export_csv(admin, "orders", build_period("today"))
    full = await services.stats.export_csv(super_admin, "orders", build_period("today"))
    assert "provider_cost" not in plain.columns and "est_profit" not in plain.columns
    assert "provider_cost" in full.columns and "est_profit" in full.columns


async def test_export_unknown_kind_rejected_by_service(
    services: ServiceContainer, super_admin: User
) -> None:
    """الخدمة نفسها ترفض نوعاً غير معروف (لا اعتماد على الواجهة فقط)."""
    from core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        await services.stats.export_csv(super_admin, "users", build_period("today"))


# ======================================================================== #
#                              الملخص اليومي                                 #
# ======================================================================== #


async def test_daily_digest_is_net_and_has_no_profit_line(
    services: ServiceContainer, user: User, admin: User, mock_service: Service,
) -> None:
    """الملخص اليومي يصل لكل من يملك `stats.view` ⇒ بلا ربح ولا تكلفة، والمبيعات صافية."""
    from texts.templates import admin_daily_digest

    await _orders(services, user, admin, mock_service, count=2)
    digest = await services.stats.system_digest()
    assert digest["orders_today"] == 2 and digest["revenue_today_units"] == 20_000
    _title, message = admin_daily_digest(
        orders_today=digest["orders_today"],
        revenue_today_units=digest["revenue_today_units"],
        deposits_today_units=digest["deposits_today_units"],
        pending_payments=digest["pending_payments"],
        attention_orders=digest["attention_orders"],
        open_tickets=digest["open_tickets"],
        new_users=digest["new_users_today"],
        errors_24h=digest["errors_24h"],
        refunds_today_units=digest["refunds_today_units"],
        completed_today=digest["completed_today"],
        failed_today=digest["failed_today"],
    )
    assert "ربح" not in message and "تكلفة" not in message
    assert "صافي مبيعات" in message


# ======================================================================== #
#                       حالات حدّية إضافية للواجهة                           #
# ======================================================================== #


async def test_export_telegram_failure_is_reported_not_swallowed(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, user: User, admin: User,
    super_admin: User, mock_service: Service, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """فشل إرسال الملف عبر تيليجرام يُبلَّغ للأدمن بوضوح (والتدقيق مسجّل لأن الملف أُنشئ)."""
    from telegram.error import NetworkError

    async def broken(*_args, **_kwargs):
        raise NetworkError("انقطاع اختباري")

    await _orders(services, user, admin, mock_service, count=1)
    await load_user(bot, context, super_admin)
    monkeypatch.setattr(bot, "send_document", broken)
    await press(bot, context, stats_handlers.export_action, pack("st", "exp", "orders", "today"), super_admin.telegram_id)
    assert "تعذّر إرسال الملف" in bot.last.text


async def test_daily_screen_caps_lines_but_totals_cover_all_days(
    bot: FakeBot, context: FakeContext, services: ServiceContainer, repos: Repositories, user: User,
    admin: User, mock_service: Service,
) -> None:
    """أكثر من 31 يوماً: تُقطع الأسطر ويُعلَن القطع، والمجموع يشمل كل الأيام (لا يُخفى مال)."""
    await _orders(services, user, admin, mock_service, count=34)
    order_ids = [int(r["id"]) for r in await repos.db.fetchall("SELECT id FROM orders ORDER BY id")]
    assert len(order_ids) == 34
    async with repos.db.transaction() as tx:               # كل طلب في يوم مختلف
        for offset, order_id in enumerate(order_ids):
            when = (datetime.now(timezone.utc) - timedelta(days=offset)).isoformat()
            await tx.execute("UPDATE orders SET created_at = ? WHERE id = ?", (when, order_id))
    series = await services.stats.daily_series(admin, days=90)
    assert len(series) == 90                              # الأيام الخالية تظهر بأصفار (قرار المالك)
    assert sum(1 for item in series if item["orders_count"]) == 34

    await load_user(bot, context, admin)
    await press(bot, context, stats_handlers.daily_screen, pack("st", "day", "90d"), admin.telegram_id)
    text = bot.last.text
    assert text.count("█") + text.count("▫️") <= 31 * 8
    assert "31" in text and "90" in text                 # القطع معلن: المعروض 31 من 90
    symbol = await services.settings.money_symbol()
    assert money_text(340_000, symbol) in text         # مجموع الأيام كلها وليس المعروضة فقط
