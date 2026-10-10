"""
اختبارات الانحدار v1.3.1 (R01…R14 + E1…E7).

كل اختبار هنا **فشل على v1.3.0 الأصلية** لسبب موثَّق في `reports/stage1_diagnosis_v1.3.0.md`، وينجح بعد الإصلاح.
الدليل المسجَّل لفشلها قبل الإصلاح في `reports/regression_evidence/`.

كل شيء Mock: عميل Perfect Panel الحقيقي بنقل httpx وهمي (`FakePanel`) أو `MockProviderClient`، وبوت وهمي — لا شبكة
ولا مزود ولا أرصدة حقيقية.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from telegram.error import Conflict
from telegram.ext import Application, ApplicationBuilder

import main as app_main
from core.enums import OrderStatus
from core.exceptions import OrderError, PermissionDeniedError
from handlers.registry import register_handlers
from integrations.providers import registry
from integrations.providers.perfect_panel import PerfectPanelClient
from tests.integration.test_phase14_statuses import FakePanel, LINK, _check, _submitted, panel  # noqa: F401
from utils.conflict_guard import ConflictGuard
from utils.datetime_utils import iso_plus_seconds

pytestmark = pytest.mark.asyncio

ROOT = Path(__file__).resolve().parents[2]
DUMMY_TOKEN = "123456789:AAregression0123456789012345678901234"


# ============================== بند 10: الإقلاع والتعارض ============================== #


async def test_r04_main_calls_run_polling_with_real_ptb_signature() -> None:
    """R04: كل وسيط يمرّره `main.py` إلى `run_polling` مقبول في توقيع PTB الحقيقي (كان `error_callback` ⇒ TypeError)."""
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "run_polling"
    ]
    assert calls, "لم يُعثر على استدعاء run_polling في main.py"
    signature = inspect.signature(Application.run_polling)
    for call in calls:
        kwargs = {keyword.arg: None for keyword in call.keywords if keyword.arg}
        signature.bind(None, **kwargs)          # يرفع TypeError لأي كلمة غير مدعومة


async def test_r05_conflict_from_polling_reaches_guard_via_real_application() -> None:
    """R05: `Application.process_error(Conflict, update=None)` (المسار الحقيقي لأخطاء getUpdates) يغذّي ConflictGuard."""
    application = ApplicationBuilder().token(DUMMY_TOKEN).build()
    register_handlers(application)
    stops: list[int] = []
    clock = SimpleNamespace(now=0.0)
    guard = ConflictGuard(lambda: stops.append(1), clock=lambda: clock.now)
    application.bot_data["conflict_guard"] = guard

    for _ in range(6):
        await application.process_error(update=None, error=Conflict("terminated by other getUpdates request"))
        clock.now += 15
    assert guard.recent_conflicts == 6
    assert guard.tripped and stops == [1]


# ============================== بند 1–2: سياسة المتابعة ============================== #


def _seconds_until(iso_value: str | None) -> float:
    """الثواني من الآن إلى موعد ISO (سالب إن كان ماضياً)."""
    from utils.datetime_utils import parse_iso, utc_now

    parsed = parse_iso(iso_value)
    assert parsed is not None, "next_check_at فارغ"
    return (parsed - utc_now()).total_seconds()


async def test_r01_active_order_poll_interval_stays_capped(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """R01: طلب نشِط يُفحص بنجاح لا يتباطأ إلى ساعة (v1.3.0: 120 ← 900 ← 1800 ← 3600)."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.status_payload = {"status": "In progress", "remains": "700", "start_count": "0", "charge": "0.5", "currency": "USD"}
    cap = await services.settings.get_int("order_check_active_max_seconds", 300)
    for round_number in range(1, 8):
        await _check(services, db, order.id)
        stored = await repos.orders.get(order.id)
        assert stored.status == OrderStatus.IN_PROGRESS
        assert _seconds_until(stored.next_check_at) <= cap + 5, f"الفحص رقم {round_number} تباطأ فوق السقف"


async def test_r02_successful_poll_clears_old_error_and_records_last_ok(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """R02: مهلة ثم تعافٍ ⇒ لا يبقى «تعذر الاتصال» ويُسجَّل آخر فحص ناجح (v1.3.0: last_error يبقى حتى بعد الاكتمال)."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.raise_on_status = httpx.ReadTimeout("slow")
    await _check(services, db, order.id)
    after_failure = await repos.orders.get(order.id)
    assert after_failure.status == OrderStatus.SUBMITTED          # فشل الاتصال ≠ فشل الطلب

    panel.raise_on_status = None
    panel.status_payload = {"status": "Completed", "remains": "0", "start_count": "0", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id)
    done = await repos.orders.get(order.id)
    assert done.status == OrderStatus.COMPLETED
    assert not done.last_error, "خطأ الاتصال القديم بقي بعد الاكتمال"
    assert after_failure.last_check_error and after_failure.check_fail_streak == 1   # الإخفاق سُجّل في حقله المستقل
    assert done.last_check_error is None and done.check_fail_streak == 0
    assert done.last_check_ok_at is not None and done.last_checked_at is not None
    assert panel.calls.count("add") == 1                           # لا إعادة إرسال بعد المهلة


async def test_r03_recheck_now_unchanged_does_not_defer_and_reports_provider_status(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """R03: `recheck_now` بلا تغيير لا يؤجّل الموعد ساعة، ويعرض حالة المزود الفعلية (v1.3.0: 'unchanged' + 3600ث)."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.status_payload = {"status": "In progress", "remains": "400", "start_count": "0", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id)
    async with db.transaction() as tx:
        await tx.execute("UPDATE orders SET checks_count = 6 WHERE id = ?", (order.id,))
    result = await services.orders.recheck_now(super_admin, order.id)
    stored = await repos.orders.get(order.id)
    cap = await services.settings.get_int("order_check_active_max_seconds", 300)
    assert _seconds_until(stored.next_check_at) <= cap + 5
    assert "In progress" in result and "400" in result and result != "unchanged"
    assert stored.last_check_ok_at is not None


async def test_e8_failure_backoff_uses_streak_not_checks_count(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """E8: تباطؤ الأعطال حسب الإخفاقات المتتالية بسقف الإعداد، ويعود للفاصل الأساسي فور النجاح."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    err_cap = await services.settings.get_int("order_check_error_max_seconds", 600)
    panel.raise_on_status = httpx.ReadTimeout("slow")
    delays = []
    for _ in range(6):
        await _check(services, db, order.id)
        delays.append(_seconds_until((await repos.orders.get(order.id)).next_check_at))
    assert all(later >= earlier - 2 for earlier, later in zip(delays, delays[1:]))
    assert max(delays) <= err_cap + 5
    assert delays[0] <= 65                                          # أول إخفاق ⇒ دقيقة لا ساعة

    panel.raise_on_status = None
    panel.status_payload = {"status": "In progress", "remains": "900", "start_count": "0", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id)
    base = await services.settings.get_int("order_check_interval_seconds", 120)
    assert _seconds_until((await repos.orders.get(order.id)).next_check_at) <= base + 5


async def test_e9_round_budget_releases_unprocessed_orders_without_failing_them(services, repos, db, user, super_admin, mock_service, panel, monkeypatch) -> None:
    """E9: بعد انتهاء ميزانية الجولة لا تُبدأ نداءات جديدة، ويُفرَج عن الطلبات للجولة التالية بلا إخفاق ولا تغيير حالة."""
    import services.order_service as order_module

    order = await _submitted(services, repos, user, super_admin, mock_service)
    async with db.transaction() as tx:
        await tx.execute("UPDATE orders SET next_check_at = ?, locked_until = NULL WHERE id = ?", (iso_plus_seconds(-30), order.id))
    ticks = iter([0.0] + [10_000.0] * 50)
    monkeypatch.setattr(order_module, "time", SimpleNamespace(monotonic=lambda: next(ticks)))   # بدون لمس time العامة
    calls_before = list(panel.calls)
    report = await services.orders.process_due_orders()
    assert report.claimed == 1 and panel.calls == calls_before          # لا نداء status أُرسل
    stored = await repos.orders.get(order.id)
    assert stored.status == OrderStatus.SUBMITTED and stored.locked_until is None
    assert stored.check_fail_streak == 0 and stored.last_check_error is None
    assert 0 < _seconds_until(stored.next_check_at) <= 10


async def test_e6_migration_0013_upgrades_existing_data_and_is_idempotent(tmp_path) -> None:
    """E6: ترحيل 0013 على قاعدة 0012 فيها طلب حقيقي الشكل: الصفوف تبقى، الأعمدة الجديدة NULL/0، وإعادة التشغيل لا تغيّر شيئاً."""
    import shutil

    from database.database import Database
    from database.migrator import Migrator
    from database.repositories import Repositories

    old_dir = tmp_path / "migrations_0012"
    old_dir.mkdir()
    for path in sorted((ROOT / "database" / "migrations").glob("*.sql")):
        if path.name < "0013":
            shutil.copy(path, old_dir / path.name)

    database = Database(tmp_path / "upgrade.db", read_pool_size=1)
    await database.connect()
    try:
        assert (await Migrator(database, old_dir).apply_all())[-1] == "0012"
        repos = Repositories(database)
        async with database.transaction() as tx:
            user = await repos.users.create(tx, telegram_id=1, username="u", first_name="U")
            provider = await repos.providers.create(
                tx, currency="YER", name="P", api_url="https://p.invalid/api", api_key_enc="ENC::x", api_key_hint="1"
            )
            category = (await repos.categories.list_all())[0]
            service = await repos.services.create(
                tx, category_id=category.id, provider_id=provider.id, provider_service_id="1", name="S",
                price_per_1000_units=10_000, provider_price_per_1000_units=6_000, min_quantity=1, max_quantity=100,
            )
            order = await repos.orders.create(
                tx, user_id=user.id, service_id=service.id, provider_id=provider.id, service_name_snapshot="S",
                price_per_1000_snapshot_units=10_000, link="https://x.invalid/a", quantity=10, cost_units=100,
                client_request_id="req-1",
            )
        assert "last_check_error" not in {row[1] for row in await database.fetchall("PRAGMA table_info(orders)")}

        migrator = Migrator(database)                      # المجلد الحقيقي (فيه 0013)
        assert await migrator.apply_all() == ["0013"]
        assert await migrator.apply_all() == []            # idempotent
        stored = await repos.orders.get(order.id)
        assert stored.cost_units == 100 and stored.status == "pending"
        assert stored.last_checked_at is None and stored.last_check_error is None and stored.check_fail_streak == 0
        tables = {row[0] for row in await database.fetchall("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "order_message_refs" in tables
        for key in ("order_check_active_max_seconds", "order_check_error_max_seconds", "order_check_round_budget_seconds"):
            assert await repos.settings.get(key) is not None
    finally:
        await database.close()


# ============================== بند 9/8: اقتران أعطال الاستعلام بتعطيل المزود ============================== #


async def test_r09_status_failures_do_not_disable_provider_for_new_orders(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """R09: 6 إخفاقات استعلام متتالية لا تعطّل المزود ولا تمنع طلباً جديداً (v1.3.0: تعطيل 15 دقيقة ⇒ رفض الطلبات)."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.raise_on_status = httpx.ReadTimeout("slow")
    for _ in range(6):
        await _check(services, db, order.id)
    provider = await repos.providers.get(order.provider_id)
    assert provider.consecutive_failures == 0 and not provider.disabled_until
    assert provider.last_error and "استعلام الحالة" in provider.last_error          # ظاهر للأدمن

    panel.raise_on_status = None
    fresh = await services.orders.create_order(user, service_id=mock_service.id, link=LINK + "-second", quantity=100)
    assert fresh.status == OrderStatus.PENDING
    stored = await repos.orders.get(order.id)
    assert stored.status == OrderStatus.SUBMITTED                                     # الطلب القديم لم يُمسّ


async def test_status_failure_alerts_admins_once_per_hour_without_disabling(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """بلوغ عتبة إخفاقات الاستعلام ⇒ تنبيه أدمن واحد (بلا تعطيل)."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.raise_on_status = httpx.ReadTimeout("slow")
    for _ in range(8):
        await _check(services, db, order.id)
    rows = await db.fetchall("SELECT title FROM notifications WHERE title LIKE ?", ("%تعذّر متابعة الطلبات%",))
    assert len(rows) >= 1
    distinct = {row["title"] for row in rows}
    assert len(distinct) == 1
    assert not (await repos.providers.get(order.provider_id)).disabled_until


# ============================== بند 7: إلغاء آمن لا يسترجع بلا تأكيد المزود ============================== #


async def _balance(repos, user_id: int) -> int:
    return await repos.users.get_balance_units(user_id)


async def _audit_actions(db, order_id: int) -> list[str]:
    rows = await db.fetchall("SELECT action FROM audit_logs WHERE target_type='order' AND target_id=?", (str(order_id),))
    return [row["action"] for row in rows]


async def test_r06a_cancel_blocked_when_provider_unreachable_no_refund(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """R06: خطأ استعلام مؤقت لا يؤدي إلى استرجاع (v1.3.0: يُلغى ويُسترجع كاملاً بلا أي تحقق)."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    before = await _balance(repos, user.id)
    panel.raise_on_status = httpx.ReadTimeout("slow")
    with pytest.raises(OrderError):
        await services.orders.admin_cancel(super_admin, order.id, "طلب العميل")
    stored = await repos.orders.get(order.id)
    assert stored.status == OrderStatus.SUBMITTED and await _balance(repos, user.id) == before
    assert "orders.cancel_blocked" in await _audit_actions(db, order.id)


async def test_r06b_cancel_syncs_completed_instead_of_refunding(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """R06: المزود يقول Completed ⇒ تُنقل الحقيقة للنظام (مكتمل) ولا يُسترجع شيء — لا خدمة + مال معاً."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    before = await _balance(repos, user.id)
    panel.status_payload = {"status": "Completed", "remains": "0", "start_count": "10", "charge": "0.5", "currency": "USD"}
    with pytest.raises(OrderError):
        await services.orders.admin_cancel(super_admin, order.id, "طلب العميل")
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED
    assert await _balance(repos, user.id) == before


async def test_r06c_cancel_not_accepted_while_processing_is_blocked(services, repos, db, user, super_admin, mock_service, panel, monkeypatch) -> None:
    """R06: الطلب ما زال يعمل والمزود لم يقبل الإلغاء ⇒ لا استرجاع ولا تغيير حالة."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    before = await _balance(repos, user.id)
    panel.status_payload = {"status": "In progress", "remains": "400", "start_count": "0", "charge": "0.5", "currency": "USD"}

    async def _refuse(self, provider_order_id):
        return False
    monkeypatch.setattr(PerfectPanelClient, "cancel_order", _refuse)
    with pytest.raises(OrderError):
        await services.orders.admin_cancel(super_admin, order.id, "طلب العميل")
    assert (await repos.orders.get(order.id)).status == OrderStatus.SUBMITTED
    assert await _balance(repos, user.id) == before


async def test_r06d_cancel_refunds_only_after_provider_confirms_canceled(services, repos, db, user, super_admin, mock_service, panel, monkeypatch) -> None:
    """R06: قَبِل المزود الإلغاء وأكّد Canceled في الاستعلام ⇒ استرجاع كامل + تدقيق بعلامة provider_verified."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    before = await _balance(repos, user.id)
    panel.status_payload = {"status": "In progress", "remains": "1000", "start_count": "0", "charge": "0.5", "currency": "USD"}

    async def _accept(self, provider_order_id):
        panel.status_payload = {"status": "Canceled", "remains": "1000", "start_count": "0", "charge": "0", "currency": "USD"}
        return True
    monkeypatch.setattr(PerfectPanelClient, "cancel_order", _accept)
    refunded = await services.orders.admin_cancel(super_admin, order.id, "طلب العميل")
    assert refunded == order.cost_units
    assert await _balance(repos, user.id) == before + refunded
    assert (await repos.orders.get(order.id)).status == OrderStatus.REFUNDED
    row = await db.fetchone("SELECT details_json FROM audit_logs WHERE action='orders.cancel' AND target_id=?", (str(order.id),))
    assert row is not None and "provider_verified" in row["details_json"] and "true" in row["details_json"].lower()


async def test_r06e_force_refund_needs_override_permission_and_is_audited(services, repos, db, user, admin, super_admin, mock_service, panel) -> None:
    """R06: الاسترجاع الإجباري (بلا تأكيد) للأدمن الأعلى فقط، يعمل مع تعذّر الاتصال، ويُدقَّق كـ forced."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    panel.raise_on_status = httpx.ReadTimeout("slow")
    with pytest.raises(PermissionDeniedError):
        await services.orders.admin_force_refund(admin, order.id, "سبب كافٍ للاختبار")
    assert (await repos.orders.get(order.id)).status == OrderStatus.SUBMITTED
    before = await _balance(repos, user.id)
    refunded = await services.orders.admin_force_refund(super_admin, order.id, "سبب كافٍ للاختبار")
    assert refunded == order.cost_units and await _balance(repos, user.id) == before + refunded
    row = await db.fetchone("SELECT details_json FROM audit_logs WHERE action='orders.force_refund' AND target_id=?", (str(order.id),))
    assert row is not None and "forced" in row["details_json"] and "unreachable" in row["details_json"]


async def test_r08_refund_and_audit_are_atomic(services, repos, db, user, super_admin, mock_service, monkeypatch) -> None:
    """R08: فشل كتابة التدقيق يُسقط الاسترجاع كله (v1.3.0: التدقيق بعد الـcommit فيبقى مال مُسترجَع بلا أثر)."""
    await services.wallet.adjust_balance(target=user, amount_units=100_000, admin=super_admin, reason="رصيد", credit=True)
    order = await services.orders.create_order(user, service_id=mock_service.id, link=LINK, quantity=1000)
    before = await _balance(repos, user.id)

    async def _boom(*args, **kwargs):
        raise RuntimeError("audit down")
    monkeypatch.setattr(services.audit, "log", _boom)
    monkeypatch.setattr(services.audit, "log_standalone", _boom)
    with pytest.raises(RuntimeError):
        await services.orders.admin_cancel(super_admin, order.id, "سبب كافٍ للاختبار")
    assert (await repos.orders.get(order.id)).status == OrderStatus.PENDING
    assert await _balance(repos, user.id) == before


# ============================== بند 3/11: مسار حالة موحّد ومصدر عرض واحد ============================== #


async def test_r10a_override_to_completed_uses_unified_transition(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """R10: التجاوز إلى «مكتمل» يضبط completed_at والمنفَّذ، يوقف المتابعة، يُشعر العميل، ويكتب التاريخ بـ admin."""
    order = await _submitted(services, repos, user, super_admin, mock_service)
    assert await services.orders.admin_override_status(super_admin, order.id, OrderStatus.COMPLETED, "تأكيد من لوحة المزود")
    stored = await repos.orders.get(order.id)
    assert stored.status == OrderStatus.COMPLETED
    assert stored.completed_at and stored.delivered_quantity == stored.quantity and stored.remains == 0
    assert stored.next_check_at is None and stored.locked_until is None
    rows = await db.fetchall("SELECT type FROM notifications WHERE user_id=?", (user.id,))
    assert "order_completed" in {row["type"] for row in rows}
    history = await db.fetchall("SELECT actor_type, reason FROM order_status_history WHERE order_id=? ORDER BY id DESC LIMIT 1", (order.id,))
    assert history[0]["actor_type"] == "admin" and "تجاوز إداري" in history[0]["reason"]
    assert "orders.status.override" in await _audit_actions(db, order.id)


async def test_r10b_override_source_is_the_shared_transition(services) -> None:
    """R10: `admin_override_status` لا يكتب الحالة بنفسه بل عبر `_transition` (نقطة الدخول الوحيدة)."""
    import inspect
    source = inspect.getsource(type(services.orders).admin_override_status)
    assert "self._transition(" in source and "update_status(" not in source


async def test_r10c_progress_is_consistent_when_provider_returns_only_remains() -> None:
    """R10: JAP يعيد `remains` فقط ⇒ المنفَّذ = الكمية − المتبقي (v1.3.0: كان 0 مع متبقٍّ 700)."""
    from types import SimpleNamespace as NS
    from utils.formatters import order_progress

    def make(**kw):
        base = dict(quantity=1000, delivered_quantity=None, remains=None)
        base.update(kw)
        return NS(**base)

    assert order_progress(make()) is None
    assert order_progress(make(remains=700)) == (300, 700)
    assert order_progress(make(delivered_quantity=250)) == (250, 750)
    assert order_progress(make(remains=0)) == (1000, 0)                      # مكتمل: لا يُخفى التقدّم
    assert order_progress(make(remains=5000)) == (0, 1000)                   # حدود صحيحة


async def test_r10d_one_money_function_across_screens(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """R10: مبلغ الطلب نفسه في OrderView وبطاقة المستخدم وقاعدة التنسيق الموحّدة (فرق وحيد: حذف .00 في الموجز)."""
    from utils.formatters import build_order_view, format_money, local_amount, money_text
    order = await _submitted(services, repos, user, super_admin, mock_service)
    view = build_order_view(order, "ر.ي")
    assert view.cost_text == format_money(order.cost_units, "ر.ي") == money_text(order.cost_units, "ر.ي")
    assert local_amount(order.cost_units, "ر.ي").replace(".00", "") == view.cost_text.replace(".00", "")
    assert view.net_text == view.cost_text and view.refund_text is None


async def test_r10e_admin_card_shows_check_error_provider_status_and_progress(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """R10: بطاقة الأدمن تعرض حالة المزود وآخر خطأ فحص وتقدّماً صحيحاً (v1.3.0: لا حالة مزود ولا خطأ فحص ولا تقدّم عند remains=0)."""
    from handlers.admin.orders import _order_card_text
    order = await _submitted(services, repos, user, super_admin, mock_service)
    context = SimpleNamespace(application=SimpleNamespace(bot_data={"services": services}))

    panel.status_payload = {"status": "In progress", "remains": "700", "start_count": "0", "charge": "0.5", "currency": "USD"}
    await _check(services, db, order.id)
    text = await _order_card_text(context, await repos.orders.get(order.id))
    assert "المنفَّذ: 300" in text and "المتبقي: 700" in text and "حالة المزود" in text and "آخر فحص ناجح" in text

    panel.raise_on_status = httpx.ReadTimeout("slow")
    await _check(services, db, order.id)
    text = await _order_card_text(context, await repos.orders.get(order.id))
    assert "آخر خطأ فحص" in text and "إخفاقات متتالية: 1" in text


async def test_r06f_force_refund_button_only_for_override_permission_on_provider_held_orders(services, repos, db, user, super_admin, mock_service, panel) -> None:
    """R06: زر «استرجاع إجباري» لا يظهر إلا بصلاحية التجاوز ولطلب عند المزود فقط."""
    from core.permissions import Permission
    from keyboards.admin_kb import admin_order_card_kb

    def callbacks(order, perms):
        markup = admin_order_card_kb(order, perms, filter_code="all", page=1)
        return [btn.callback_data for row in markup.inline_keyboard for btn in row]

    order = await _submitted(services, repos, user, super_admin, mock_service)
    assert any("frefund" in cb for cb in callbacks(order, {Permission.ORDERS_STATUS_OVERRIDE}))
    assert not any("frefund" in cb for cb in callbacks(order, {Permission.ORDERS_CANCEL}))
    from dataclasses import replace
    pending = replace(order, status=OrderStatus.PENDING)
    assert not any("frefund" in cb for cb in callbacks(pending, {Permission.ORDERS_STATUS_OVERRIDE}))
