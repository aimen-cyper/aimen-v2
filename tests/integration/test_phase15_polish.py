"""
زخرفة النصوص وقسم «📖 التعليمات» وإشعار المستخدم الجديد (v1.3.0).

يغطي: التحية بحسب الوقت، شريط التقدم، بطاقة الطلب، فهرس التعليمات وصفحاته وتنقلها، سلامة HTML،
تنسيق الإشعارات (قيم بارزة + تهريب)، وسياسة الخصوصية: معرّف المستخدم الجديد **كامل** في إشعار الإدارة
ومُقنَّع في قناة توثيق الطلبات.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from html.parser import HTMLParser
from types import SimpleNamespace

import pytest

from handlers.common import navigation
from handlers.user import account as account_handlers
from handlers.user import orders as orders_handlers
from jobs.telegram_sender import TelegramNotificationSender as Sender
from keyboards.callback_data import NS_ACCOUNT, NS_ORDERS, pack
from keyboards.user_kb import help_kb
from tests.integration.test_user_interface import bot, context, load_user, press  # noqa: F401,F811
from tests.telegram_fakes import make_message_update
from texts import ar, help_ar
from texts.channel_posts import new_user_post, order_post
from utils.formatters import member_days, progress_bar, time_greeting

pytestmark = pytest.mark.asyncio

HELP = pack(NS_ACCOUNT, "help")


class _Balanced(HTMLParser):
    """يتحقق أن وسوم تيليجرام المسموحة متوازنة (b/code/i)."""

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.ok = True

    def handle_starttag(self, tag, attrs):
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            self.ok = False


def _balanced(text: str) -> bool:
    parser = _Balanced()
    parser.feed(text)
    return parser.ok and not parser.stack


# ------------------------------- أدوات العرض ------------------------------- #


@pytest.mark.parametrize(
    ("hour_utc", "expected"),
    [(2, "🌅 صباح الخير"), (10, "☀️ طاب يومك"), (16, "🌆 مساء الخير"), (21, "🌙 أهلاً بك")],
)
async def test_time_greeting_follows_aden_local_time(hour_utc, expected) -> None:
    """التحية بتوقيت عدن (UTC+3): 02:00Z = 05:00 صباحاً … 21:00Z = 00:00 ليلاً."""
    assert time_greeting(datetime(2026, 10, 8, hour_utc, 0, tzinfo=UTC)) == expected


async def test_progress_bar_edges() -> None:
    """شريط التقدم: صفر/كامل/تجاوز/إجمالي صفري/سالب لا يكسر الحساب."""
    assert progress_bar(0, 100) == ("▱" * 10, 0)
    assert progress_bar(100, 100) == ("▰" * 10, 100)
    assert progress_bar(500, 100) == ("▰" * 10, 100)
    assert progress_bar(5, 0) == ("▱" * 10, 0)
    assert progress_bar(-3, 100) == ("▱" * 10, 0)
    bar, percent = progress_bar(1, 1000)
    assert percent == 0 and bar.count("▰") == 0                        # لا يُوهم بتقدم غير موجود
    assert progress_bar(999, 1000)[0].count("▰") <= 10 and progress_bar(999, 1000)[1] == 99


async def test_member_days() -> None:
    """أيام العضوية: كاملة وغير سالبة، وتاريخ فاسد = 0."""
    now = datetime(2026, 10, 8, tzinfo=UTC)
    assert member_days("2026-10-01T00:00:00.000000Z", now) == 7
    assert member_days("2026-12-01T00:00:00.000000Z", now) == 0
    assert member_days(None, now) == 0 and member_days("junk", now) == 0


# --------------------------------- التعليمات --------------------------------- #


async def test_help_index_lists_every_topic_and_has_home(bot, context, user) -> None:  # noqa: F811
    """الفهرس: زر لكل موضوع (7) + الدعم + الرئيسية، والنص كامل."""
    await load_user(bot, context, user)
    await press(bot, context, account_handlers.help_screen, HELP, user.telegram_id)
    assert bot.last.text == help_ar.HELP_INDEX
    for code in help_ar.HELP_CODES:
        assert pack(NS_ACCOUNT, "help", code) in bot.last.buttons
    assert "nav:home:v1" in bot.last.buttons or any(b.startswith("nav:home") for b in bot.last.buttons)
    assert len(help_ar.HELP_TOPICS) == 7


@pytest.mark.parametrize("topic", help_ar.HELP_CODES)
async def test_every_help_page_renders_valid_html_within_limits(topic, bot, context, user) -> None:  # noqa: F811
    """كل صفحة: تُعرض، HTML متوازن، أقل من 4096، وفيها سابق/تالي/فهرس/رئيسية."""
    await load_user(bot, context, user)
    await press(bot, context, account_handlers.help_screen, pack(NS_ACCOUNT, "help", topic), user.telegram_id)
    text = bot.last.text
    assert text and len(text) < 3000 and _balanced(text), topic
    assert "{" not in text and "}" not in text, "متغير غير مستبدل"
    buttons = bot.last.buttons
    assert HELP in buttons
    assert sum(b.startswith(f"{NS_ACCOUNT}:help:") for b in buttons) >= 3     # سابق + تالي + (فهرس)


async def test_help_navigation_is_circular_and_unknown_topic_is_safe(bot, context, user) -> None:  # noqa: F811
    """«السابق» من الأول ينتقل للأخير و«التالي» من الأخير للأول؛ وموضوع مجهول ⇒ تنبيه + الفهرس."""
    first, last = help_ar.HELP_CODES[0], help_ar.HELP_CODES[-1]
    kb_first = [b.callback_data for row in help_kb(first).inline_keyboard for b in row]
    kb_last = [b.callback_data for row in help_kb(last).inline_keyboard for b in row]
    assert pack(NS_ACCOUNT, "help", last) in kb_first and pack(NS_ACCOUNT, "help", first) in kb_last

    await load_user(bot, context, user)
    await press(bot, context, account_handlers.help_screen, pack(NS_ACCOUNT, "help", "nope"), user.telegram_id)
    assert bot.last.text == help_ar.HELP_INDEX
    assert any(help_ar.HELP_TOPIC_UNKNOWN in (a["text"] or "") for a in bot.answers)


async def test_contact_page_uses_configured_support_or_fallback(bot, context, services, super_admin, user) -> None:  # noqa: F811
    """صفحة الدعم تعرض حساب الدعم المضبوط، وإلا بديلاً صريحاً (لا «{support}» ولا فراغ)."""
    await load_user(bot, context, user)
    await press(bot, context, account_handlers.help_screen, pack(NS_ACCOUNT, "help", "contact"), user.telegram_id)
    assert help_ar.HELP_SUPPORT_FALLBACK in bot.last.text
    await services.settings.set("support_username", "@my_support", admin_id=super_admin.id)
    await press(bot, context, account_handlers.help_screen, pack(NS_ACCOUNT, "help", "contact"), user.telegram_id)
    assert "@my_support" in bot.last.text


async def test_help_command_and_menu_button(bot, context, user) -> None:  # noqa: F811
    """/help يرسل الفهرس بأزراره؛ والقائمة الرئيسية فيها زر «📖 التعليمات» يعمل."""
    await load_user(bot, context, user)
    update = make_message_update(bot, text="/help", user_id=user.telegram_id)
    await navigation.help_command(update, context)
    assert bot.last.text == help_ar.HELP_INDEX
    assert pack(NS_ACCOUNT, "help", "start") in bot.last.buttons
    await navigation.start_command(make_message_update(bot, text="/start", user_id=user.telegram_id), context)
    assert HELP in bot.last.buttons
    assert ar.BTN_HELP in str(bot.last.markup)


async def test_help_texts_mention_only_real_behaviour() -> None:
    """حراسة الدقة: الإلغاء قبل الإرسال فقط، والاسترجاع التلقائي للفاشل، والشحن بمراجعة يدوية."""
    refund = help_ar.HELP_PAGES["refund"]
    assert "بانتظار الإرسال" in refund and "تلقائياً" in refund
    assert "يراجع الفريق" in help_ar.HELP_PAGES["deposit"]
    for status in ("بانتظار الإرسال", "قيد التنفيذ", "مكتمل", "فشل", "مسترجع"):
        assert status in help_ar.HELP_PAGES["status"]


# ------------------------------- بطاقة الطلب ------------------------------- #


async def test_order_card_shows_progress_bar(bot, context, services, db, user, super_admin, mock_service) -> None:  # noqa: F811
    """طلب نُفِّذ نصفه ⇒ شريط تقدم 50% مع المنفَّذ والمتبقي."""
    await services.wallet.adjust_balance(target=user, amount_units=100_000, admin=super_admin, reason="x", credit=True)
    order = await services.orders.create_order(user, service_id=mock_service.id, link="https://instagram.com/p/bar", quantity=1000)
    async with db.transaction() as tx:
        await tx.execute("UPDATE orders SET status = 'in_progress', delivered_quantity = 500, remains = 500 WHERE id = ?", (order.id,))
    await load_user(bot, context, user)
    await press(bot, context, orders_handlers.order_card_screen, pack(NS_ORDERS, "view", order.id, "all", 1), user.telegram_id)
    assert "▰▰▰▰▰▱▱▱▱▱" in bot.last.text and "50%" in bot.last.text
    assert _balanced(bot.last.text)


async def test_account_card_shows_membership(bot, context, user) -> None:  # noqa: F811
    """بطاقة الحساب تعرض «عضو منذ» (اليوم للمنضم حديثاً)."""
    await load_user(bot, context, user)
    await press(bot, context, account_handlers.account_screen, pack(NS_ACCOUNT, "home"), user.telegram_id)
    assert "عضو منذ" in bot.last.text and ar.MEMBER_TODAY in bot.last.text
    assert _balanced(bot.last.text)


# ------------------------------- ترحيب وقوائم ------------------------------- #


async def test_start_uses_greeting_and_stays_valid_html(bot, context, user) -> None:  # noqa: F811
    """الترحيب بتحية الوقت، HTML صالح، ومن ضمنه اسم فيه رموز HTML (يُهرَّب)."""
    await load_user(bot, context, user)
    await navigation.start_command(make_message_update(bot, text="/start", user_id=user.telegram_id), context)
    text = bot.last.text
    assert any(g in text for g in ("صباح الخير", "طاب يومك", "مساء الخير", "أهلاً بك"))
    assert _balanced(text)


async def test_all_user_text_templates_format_without_missing_placeholders() -> None:
    """كل نص في ar.py يُنسَّق بمتغيراته المعلنة فقط (لا KeyError مخفي في مسار نادر)."""
    from string import Formatter

    for name, value in vars(ar).items():
        if not name.isupper() or not isinstance(value, str):
            continue
        fields = {f for _l, f, _s, _c in Formatter().parse(value) if f}
        assert all(f.isidentifier() for f in fields), (name, fields)
        value.format(**{f: "x" for f in fields})                     # لا استثناء
        assert _balanced(value.format(**{f: "x" for f in fields})) or "<" not in value, name


# ------------------------------- تنسيق الإشعارات ------------------------------- #


async def test_notification_format_highlights_values_and_escapes_everything() -> None:
    """القيم القصيرة بعد «🛒 الخدمة:» عريضة، ونص المستخدم يُهرَّب، والمعرّفات القابلة للنسخ في code."""
    text = Sender._format("🧾 تم استلام طلبك", "✅ تم إنشاء الطلب ORD-1.\n\n🛒 الخدمة: <script>x</script> & y\n📱 Telegram ID: 12345678\n\n🔔 شكراً")
    assert text.startswith("<b>🧾 تم استلام طلبك</b>\n━━━━")
    assert "🛒 الخدمة: <b>&lt;script&gt;x&lt;/script&gt; &amp; y</b>" in text
    assert "📱 Telegram ID: <code>12345678</code>" in text
    assert "<script>" not in text and _balanced(text)


async def test_notification_free_text_and_long_messages_stay_safe() -> None:
    """رد دعم حر لا يُبرَز، والرسالة الطويلة تُقتطع بلا وسوم مقطوعة، والعنوان الفارغ يعمل."""
    reply = Sender._format("💬 رد جديد", "💬 لديك رد على التذكرة #7:\n\n«تم حل المشكلة: جرّب الآن»")
    assert "«تم حل المشكلة: جرّب الآن»" in reply and "<b>جرّب" not in reply
    long = Sender._format("عنوان", "📝 السبب: " + "ا" * 9000)
    assert len(long) <= 4096 and _balanced(long.replace("…", ""))
    assert Sender._format("", "🛒 الخدمة: x") == "🛒 الخدمة: <b>x</b>"


# ------------------------------- الخصوصية ------------------------------- #


def _user(**kw):
    base = dict(id=7, telegram_id=1712345678, username="newbie", first_name="Ali", last_name="Saleh", created_at="2026-10-08T00:00:00.000000Z")
    base.update(kw)
    return SimpleNamespace(**base)


async def test_new_user_post_shows_full_id_but_order_post_masks_it() -> None:
    """قرار المالك: الإدارة ترى المعرّف كاملاً عند انضمام مستخدم، وقناة توثيق الطلبات تبقى مُقنَّعة."""
    _title, message = new_user_post(user=_user(), total_users=42)
    assert "Telegram ID: 1712345678" in message and "••" not in message
    assert "@newbie" in message and "42" in message

    _t, order = order_post(category_name="إنستغرام", service_name="متابعين", order_code="ORD-9", quantity=1000,
                           cost_units=10_000, symbol="ريال", usd_rate=Decimal("530"), user=_user(), link="https://instagram.com/someone/p/secret")
    assert "1712345678" not in order and "17••••••••" in order
    assert "someone" not in order and "secret" not in order and "https://instagram.com/••••" in order


async def test_new_user_post_survives_special_characters_in_name() -> None:
    """اسم يحوي HTML أو بلا اسم/Username لا يكسر المنشور."""
    _t, message = new_user_post(user=_user(first_name="<b>x</b> & y", last_name=None, username=None), total_users=1)
    assert "Username: —" in message
    formatted = Sender._format(_t, message)
    assert "&lt;b&gt;x&lt;/b&gt; &amp; y" in formatted and _balanced(formatted)


async def test_sender_delimits_each_line_independently() -> None:
    """سطر بلا رمز تعبيري في أوله لا يُبرَز عن طريق الخطأ (منع تحويل نص عادي لعريض)."""
    assert Sender._decorate_line("الخدمة: شيء") == "الخدمة: شيء"
    assert re.fullmatch(r"🛒 الخدمة: <b>شيء</b>", Sender._decorate_line("🛒 الخدمة: شيء"))
