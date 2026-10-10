"""
المرحلة 11 — اختبار الموزّع الحقيقي (`telegram.ext.Application`) بلا شبكة.

الفرق عن بقية الاختبارات: هنا لا نستدعي المعالجات مباشرة ولا نستعمل بوتاً مزيّفاً، بل:

    تحديث JSON ⇒ `Update.de_json` ⇒ `Application.process_update` ⇒ المعالجات المسجَّلة فعلياً
    عبر `register_handlers` (المجموعات والـConversationHandler والطبقة الوسيطة ومعالج الأخطاء)
    ⇒ `Bot` حقيقي (Defaults + تسلسل JSON) ⇒ طلب HTTP يعترضه `RecordingRequest` بدل الشبكة.

وبذلك تُختبر هندسة التوجيه نفسها: أولوية المجموعات، التقاط الأزرار، الحظر، الصيانة، حد المعدل،
وأن ضغط **كل** زر يصل لمعالج حقيقي دون استثناء غير معالَج.
"""

from __future__ import annotations

import itertools
import json
import time
from collections import deque
from typing import Any

import pytest
import pytest_asyncio
from telegram import LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.ext import Application, ApplicationBuilder, Defaults, ExtBot
from telegram.request import BaseRequest, RequestData

from handlers.registry import build_handlers, register_handlers
from services import ServiceContainer

pytestmark = pytest.mark.asyncio

BOT_ID = 123456789
TOKEN = f"{BOT_ID}:AADispatcherTestDummyTokenNeverUsedOnline"
_ids = itertools.count(1)


class RecordingRequest(BaseRequest):
    """بديل طبقة HTTP: يسجّل كل استدعاء لـBot API ويردّ بما يردّ به تيليجرام عادةً."""

    def __init__(self) -> None:
        """قائمة الاستدعاءات (الطريقة، المعاملات)."""
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def initialize(self) -> None:
        """لا موارد للتهيئة."""

    async def shutdown(self) -> None:
        """لا موارد للإغلاق."""

    @property
    def read_timeout(self) -> float | None:
        """مهلة القراءة (غير مستعملة)."""
        return 1.0

    async def do_request(
        self, url: str, method: str, request_data: RequestData | None = None,
        read_timeout: Any = None, write_timeout: Any = None, connect_timeout: Any = None, pool_timeout: Any = None,
    ) -> tuple[int, bytes]:
        """تسجيل الاستدعاء وتركيب ردّ شبيه بردّ تيليجرام."""
        endpoint = url.rsplit("/", 1)[-1]
        params = dict(request_data.parameters) if request_data else {}
        self.calls.append((endpoint, params))
        if endpoint == "getMe":
            result: Any = {"id": BOT_ID, "is_bot": True, "first_name": "Bot", "username": "dispatcher_bot"}
        elif endpoint in {"sendMessage", "editMessageText", "sendPhoto", "sendDocument", "editMessageReplyMarkup"}:
            result = {
                "message_id": next(_ids), "date": int(time.time()),
                "chat": {"id": int(params.get("chat_id", 0) or 0), "type": "private"},
                "text": str(params.get("text", "")),
            }
        else:
            result = True
        return 200, json.dumps({"ok": True, "result": result}).encode()


class Harness:
    """غلاف يبسّط إرسال التحديثات واستخراج آخر ردّ وأزراره."""

    def __init__(self, app: Application, request: RecordingRequest, services: ServiceContainer) -> None:
        """تخزين التطبيق وسجل الطلبات."""
        self.app, self.request, self.services = app, request, services

    @property
    def calls(self) -> list[tuple[str, dict[str, Any]]]:
        """كل الاستدعاءات المسجَّلة بعد التهيئة."""
        return self.request.calls

    def mark(self) -> int:
        """علامة موضع في السجل لقياس ما بعدها."""
        return len(self.request.calls)

    def since(self, mark: int, *endpoints: str) -> list[dict[str, Any]]:
        """معاملات الاستدعاءات (من نوع معيّن) بعد علامة."""
        return [p for e, p in self.request.calls[mark:] if not endpoints or e in endpoints]

    async def say(self, user_id: int, text: str, *, first_name: str = "Tester") -> None:
        """إرسال رسالة نصية (تُفسَّر كأمر إن بدأت بـ/)."""
        message: dict[str, Any] = {
            "message_id": next(_ids), "date": int(time.time()),
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": first_name},
            "text": text,
        }
        if text.startswith("/"):
            message["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
        await self.app.process_update(Update.de_json({"update_id": next(_ids), "message": message}, self.app.bot))

    def unthrottle(self, user_id: int) -> None:
        """تصفير حد المعدل وحارس الإساءة (لاختبارات التصفح الطويلة التي ليست عن الحد نفسه)."""
        self.app.bot_data["rate_limiter"].reset(user_id)
        self.app.bot_data["abuse_guard"].clear(user_id)

    async def press(self, user_id: int, data: str) -> None:
        """ضغط زر inline يحمل `callback_data`."""
        payload = {
            "update_id": next(_ids),
            "callback_query": {
                "id": f"cb{next(_ids)}", "chat_instance": "ci", "data": data,
                "from": {"id": user_id, "is_bot": False, "first_name": "Tester"},
                "message": {
                    "message_id": next(_ids), "date": int(time.time()),
                    "chat": {"id": user_id, "type": "private"},
                    "from": {"id": BOT_ID, "is_bot": True, "first_name": "Bot"}, "text": "شاشة",
                },
            },
        }
        await self.app.process_update(Update.de_json(payload, self.app.bot))

    def last_buttons(self, mark: int) -> list[str]:
        """أزرار callback في آخر رسالة/تعديل بعد العلامة."""
        for endpoint, params in reversed(self.request.calls[mark:]):
            if endpoint in {"sendMessage", "editMessageText", "editMessageReplyMarkup"} and "reply_markup" in params:
                raw = params["reply_markup"]
                markup = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
                return [b["callback_data"] for row in markup.get("inline_keyboard", []) for b in row if "callback_data" in b]
        return []

    def texts(self, mark: int) -> str:
        """نص كل ما أُرسل/عُدِّل بعد العلامة."""
        return "\n".join(str(p.get("text", "")) for p in self.since(mark, "sendMessage", "editMessageText"))

    async def error_count(self) -> int:
        """عدد سجلات الأخطاء المخزَّنة (يجب أن يبقى صفراً)."""
        row = await self.services.db.fetchone("SELECT COUNT(*) AS c FROM error_logs")
        return int(row["c"])


@pytest_asyncio.fixture
async def harness(services: ServiceContainer):
    """تطبيق حقيقي بكل المعالجات المسجَّلة وخدمات حقيقية، وشبكة مُعترَضة."""
    request = RecordingRequest()
    bot = ExtBot(TOKEN, request=request, defaults=Defaults(parse_mode=ParseMode.HTML, link_preview_options=LinkPreviewOptions(is_disabled=True)))
    app = ApplicationBuilder().bot(bot).concurrent_updates(False).build()
    app.bot_data["services"] = services
    register_handlers(app)
    await app.initialize()
    yield Harness(app, request, services)
    await app.shutdown()


async def _promote(services: ServiceContainer, telegram_id: int, role: str) -> None:
    """رفع دور مستخدم مباشرة في القاعدة (إعداد الاختبار فقط)."""
    async with services.db.transaction() as tx:
        await tx.execute("UPDATE users SET role = ? WHERE telegram_id = ?", (role, telegram_id))


# ----------------------------------- الاختبارات ----------------------------------- #


async def test_registered_handler_count_matches_registry(harness: Harness) -> None:
    """عدد المعالجات الفعلي على التطبيق = ما يبنيه السجل + الطبقة الوسيطة تعمل في المجموعة الأولى."""
    total = sum(len(handlers) for handlers in harness.app.handlers.values())
    assert total == len(build_handlers()) == 159
    assert min(harness.app.handlers) < 0 or 0 in harness.app.handlers


async def test_start_registers_user_and_shows_main_menu_with_html_defaults(harness: Harness) -> None:
    """/start لمستخدم جديد ⇒ صف في القاعدة + قائمة رئيسية بأزرار + parse_mode=HTML من Defaults."""
    mark = harness.mark()
    await harness.say(501_001, "/start")
    user = await harness.services.users.get_by_telegram(501_001)
    assert user is not None and not user.is_banned
    sent = harness.since(mark, "sendMessage")
    assert sent, "لم تُرسل أي رسالة ردّاً على /start"
    assert sent[-1]["parse_mode"] == "HTML"
    assert len(harness.last_buttons(mark)) >= 4, "القائمة الرئيسية بلا أزرار كافية"
    assert await harness.error_count() == 0


async def test_every_main_menu_button_reaches_a_real_handler(harness: Harness) -> None:
    """ضغط كل زر في القائمة الرئيسية ثم أزرار الشاشات الناتجة (BFS) ⇒ كل ضغطة تُجاب بلا خطأ."""
    uid = 501_002
    mark = harness.mark()
    await harness.say(uid, "/start")
    queue = deque(harness.last_buttons(mark))
    seen: set[str] = set()
    pressed = 0
    while queue and pressed < 150:
        data = queue.popleft()
        if data in seen:
            continue
        seen.add(data)
        before = harness.mark()
        harness.unthrottle(uid)
        await harness.press(uid, data)
        pressed += 1
        answered = harness.since(before, "answerCallbackQuery")
        replied = harness.since(before, "sendMessage", "editMessageText", "editMessageReplyMarkup")
        assert answered or replied, f"زر ميّت: {data}"
        queue.extend(b for b in harness.last_buttons(before) if b not in seen)
    assert pressed >= 10, "عدد الأزرار المفحوصة قليل جداً"
    assert await harness.error_count() == 0, "استثناء غير معالَج أثناء الضغط على الأزرار"


async def test_every_admin_panel_button_reaches_a_real_handler(harness: Harness, services: ServiceContainer) -> None:
    """نفس الفحص للوحة الأدمن الأعلى: لا زر ميّت ولا استثناء غير معالَج."""
    uid = 501_003
    await harness.say(uid, "/start")
    await _promote(services, uid, "super_admin")
    mark = harness.mark()
    await harness.say(uid, "/admin")
    start = harness.last_buttons(mark)
    assert len(start) >= 8, "لوحة الأدمن بلا أقسام كافية"
    queue = deque(start)
    seen: set[str] = set()
    history: list[str] = []
    pressed = 0
    while queue and pressed < 400:
        data = queue.popleft()
        if data in seen:
            continue
        seen.add(data)
        before = harness.mark()
        harness.unthrottle(uid)
        await harness.press(uid, data)
        pressed += 1
        history.append(data)
        assert harness.since(before), f"زر ميّت في لوحة الأدمن: {data} (سبقه: {history[-5:-1]})"
        queue.extend(b for b in harness.last_buttons(before) if b not in seen)
    assert pressed >= 30
    assert await harness.error_count() == 0, "استثناء غير معالَج في لوحة الأدمن"


async def test_regular_user_cannot_open_admin_panel(harness: Harness) -> None:
    """/admin من مستخدم عادي ⇒ لا لوحة ولا أزرار إدارية."""
    await harness.say(501_004, "/start")
    mark = harness.mark()
    await harness.say(501_004, "/admin")
    assert not harness.last_buttons(mark) or "admin" not in " ".join(harness.last_buttons(mark)).lower()
    events = await harness.services.db.fetchall("SELECT 1 FROM audit_logs WHERE action LIKE 'security.%'")
    assert events, "محاولة الدخول غير المصرّح بها لم تُسجَّل"


async def test_banned_user_gets_no_menu_and_no_state_change(harness: Harness, services: ServiceContainer) -> None:
    """مستخدم محظور: /start وضغط الأزرار لا يفتحان أي قائمة."""
    uid = 501_005
    await harness.say(uid, "/start")
    async with services.db.transaction() as tx:
        await tx.execute("UPDATE users SET is_banned = 1 WHERE telegram_id = ?", (uid,))
    mark = harness.mark()
    await harness.say(uid, "/start")
    assert not harness.last_buttons(mark), "المحظور رأى قائمة"
    mark = harness.mark()
    await harness.press(uid, "menu:main")
    assert not harness.last_buttons(mark)
    assert await harness.error_count() == 0


async def test_maintenance_blocks_user_but_not_super_admin(harness: Harness, services: ServiceContainer) -> None:
    """وضع الصيانة: المستخدم يرى رسالة الصيانة، والأدمن الأعلى يدخل لوحته."""
    admin_id, user_id = 501_006, 501_007
    await harness.say(admin_id, "/start")
    await _promote(services, admin_id, "super_admin")
    await services.settings.set("maintenance_mode", True, admin_id=None)
    await services.settings.set("maintenance_message", "صيانة تجريبية", admin_id=None)
    mark = harness.mark()
    await harness.say(user_id, "/start")
    assert "صيانة تجريبية" in harness.texts(mark)
    mark = harness.mark()
    await harness.say(admin_id, "/admin")
    assert len(harness.last_buttons(mark)) >= 8
    assert await harness.error_count() == 0


async def test_flood_is_throttled_without_crash(harness: Harness) -> None:
    """إغراق بـ60 ضغطة سريعة ⇒ يُقيَّد المستخدم ويبقى النظام سليماً (لا استثناء)."""
    uid = 501_008
    await harness.say(uid, "/start")
    mark = harness.mark()
    for _ in range(60):
        await harness.press(uid, "menu:main")
    replies = harness.since(mark, "editMessageText", "sendMessage")
    assert len(replies) < 60, "لم يُطبَّق حد المعدل"
    assert await harness.error_count() == 0


async def test_unknown_text_and_unknown_callback_are_handled_gracefully(harness: Harness) -> None:
    """نص عشوائي وcallback مجهول/تالف ⇒ ردّ لطيف أو تجاهل، دون استثناء غير معالَج."""
    uid = 501_009
    await harness.say(uid, "/start")
    for text in ("مرحبا", "/nonexistent", "a" * 3000, "<b>x</b>", "'; DROP TABLE users;--"):
        await harness.say(uid, text)
    for data in ("zzz", "x:y:z:1", "", "o:" + "9" * 40, "menu:main:v999"):
        await harness.press(uid, data or "-")
    assert await harness.error_count() == 0
    count = await harness.services.db.fetchone("SELECT COUNT(*) AS c FROM users")
    assert int(count["c"]) == 1


async def test_error_handler_reports_and_user_sees_friendly_message(harness: Harness, services: ServiceContainer, monkeypatch) -> None:
    """خلل داخلي حقيقي داخل معالج ⇒ معالج الأخطاء يسجّل ويعتذر للمستخدم بلا تسريب تفاصيل."""
    uid = 501_010
    await harness.say(uid, "/start")

    boom_calls: list[int] = []

    async def boom(*_a: Any, **_k: Any) -> Any:
        """خلل مفتعل."""
        boom_calls.append(1)
        raise RuntimeError("SECRET-INTERNAL-DETAIL")

    monkeypatch.setattr(services.wallet, "history", boom)
    monkeypatch.setattr(services.catalog, "categories", boom)
    mark = harness.mark()
    for data in harness.last_buttons(0)[:8]:
        harness.unthrottle(uid)
        await harness.press(uid, data)
    visible = harness.texts(mark)
    assert "SECRET-INTERNAL-DETAIL" not in visible, "تسريب تفاصيل داخلية للمستخدم"
    assert boom_calls, "الخلل المفتعل لم يُستدعَ أصلاً — الاختبار فارغ"
    assert visible.strip(), "المستخدم لم يتلقَّ أي اعتذار"
    assert await harness.error_count() >= 1, "الخطأ لم يُسجَّل في error_logs"
