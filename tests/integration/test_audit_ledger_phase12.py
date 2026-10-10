"""
المرحلة 12 — أداة التدقيق المالي `scripts.audit_ledger`:
    • تُبلغ «سليم» على بيانات حقيقية ناتجة عن الخدمات (شحن + طلب مكتمل + طلب فاشل مُسترجَع).
    • تكشف كل نوع تلاعب/تلف متعمَّد في القاعدة (كل فحص بحقنه مباشرة بـSQL).
    • للقراءة فقط (لا تكتب شيئاً)، وكود الخروج صحيح.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.enums import OrderStatus
from core.exceptions import ProviderPermanentError
from scripts import audit_ledger
from utils.datetime_utils import iso_plus_seconds

pytestmark = pytest.mark.asyncio


async def _populate(services, repos, db, user, admin, mock_service, mock_client, payment_method) -> None:
    """بناء بيانات واقعية: رصيد، طلب مكتمل، وطلب رفضه المزود نهائياً فاسترُجع بالكامل."""
    await services.wallet.adjust_balance(target=user, amount_units=500 * 10_000, admin=admin, reason="شحن للتدقيق", credit=True)
    done = await services.orders.create_order(user, service_id=mock_service.id, link="https://example.com/a", quantity=1000)
    await services.orders.process_pending_orders(limit=10)
    provider_id = (await repos.orders.get(done.id)).provider_order_id
    mock_client.advance(provider_id, to="completed")
    async with db.transaction() as tx:                        # جعل موعد المتابعة حالّاً دون انتظار
        await tx.execute("UPDATE orders SET next_check_at = ? WHERE id = ?", (iso_plus_seconds(-30), done.id))
    await services.orders.process_due_orders(limit=10)

    mock_client.fail_next_add = ProviderPermanentError("رفض المزود")
    failed = await services.orders.create_order(user, service_id=mock_service.id, link="https://example.com/f", quantity=1000)
    await services.orders.process_pending_orders(limit=10)
    assert (await repos.orders.get(done.id)).status == OrderStatus.COMPLETED
    assert (await repos.orders.get(failed.id)).refund_amount_units > 0, "الطلب الفاشل يجب أن يُسترجع ليختبر التدقيق مساراً حقيقياً"


@pytest.fixture
async def populated(services, repos, db, user, admin, mock_service, mock_client, payment_method):
    """قاعدة مليئة بالبيانات + مسار ملفها (نفس الملف الذي تعمل عليه الخدمات)."""
    await _populate(services, repos, db, user, admin, mock_service, mock_client, payment_method)
    return Path(db.path)


def _run(path: Path) -> list[audit_ledger.Finding]:
    """تشغيل التدقيق على ملف القاعدة بوضع القراءة فقط."""
    conn = audit_ledger.open_readonly(path)
    try:
        return audit_ledger.audit(conn)
    finally:
        conn.close()


def _failed(findings: list[audit_ledger.Finding]) -> set[str]:
    """عناوين الفحوص الفاشلة (الشديدة فقط)."""
    return {f.title for f in findings if f.count and f.severity == "bad"}


async def test_clean_database_reports_no_findings(populated: Path) -> None:
    """بيانات سليمة ناتجة عن الخدمات ⇒ لا فحص فاشل ولا تنبيه."""
    findings = _run(populated)
    assert len(findings) >= 11
    assert [f for f in findings if f.count] == []


async def test_cli_exit_codes_and_report(populated: Path, capsys) -> None:
    """سليم ⇒ 0 وتقرير عربي · خلل ⇒ 1 · قاعدة غير موجودة ⇒ 2."""
    assert audit_ledger.main(["--db", str(populated)]) == 0
    assert "النتيجة: 0 فحص فاشل" in capsys.readouterr().out
    conn = sqlite3.connect(populated)
    conn.execute("UPDATE users SET balance_units = balance_units + 1 WHERE telegram_id = 100200300")
    conn.commit()
    conn.close()
    assert audit_ledger.main(["--db", str(populated)]) == 1
    assert "⛔" in capsys.readouterr().out
    assert audit_ledger.main(["--db", str(populated.parent / "missing.db")]) == 2


async def test_audit_is_read_only(populated: Path) -> None:
    """الاتصال في وضع query_only: أي كتابة عبره تُرفض."""
    conn = audit_ledger.open_readonly(populated)
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("UPDATE users SET balance_units = 0")
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("UPDATE users SET balance_units = balance_units + 7", "رصيد المحفظة لا يساوي مجموع الحركات"),
        ("UPDATE transactions SET balance_before_units = balance_before_units + 1 WHERE id = (SELECT MAX(id) FROM transactions)",
         "انقطاع سلسلة الحركات أو خطأ حسابي فيها"),
        ("DELETE FROM transactions WHERE type = 'order'", "طلب بلا حركة خصم واحدة بقيمة التكلفة"),
        ("UPDATE orders SET refund_amount_units = 5", "مجموع الاسترجاعات لا يطابق حقل الاسترجاع في الطلب (أو يتجاوز التكلفة)"),
        ("UPDATE orders SET status = 'refunded'", "حالة نهائية لا تتسق مع الاسترجاع"),
        ("UPDATE orders SET status = 'in_progress'", "آخر سجل في تاريخ الحالات لا يساوي حالة الطلب"),
        ("DELETE FROM order_status_history WHERE id = (SELECT MIN(id) + 1 FROM order_status_history)",
         "انقطاع في سلسلة تاريخ حالات الطلب"),
    ],
    ids=["balance", "chain", "missing-charge", "refund-mismatch", "final-status", "history-last", "history-gap"],
)
async def test_each_tampering_is_detected(populated: Path, sql: str, expected: str) -> None:
    """كل نوع تلف متعمَّد يُكتشف بالفحص المخصص له."""
    conn = sqlite3.connect(populated)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA ignore_check_constraints = ON")
    conn.execute(sql)
    conn.commit()
    conn.close()
    assert expected in _failed(_run(populated))


async def test_payment_checks_detect_orphan_and_unapproved_deposits(
    services, repos, db, user, admin, payment_method
) -> None:
    """دفعة معتمدة بلا إيداع، وإيداع لدفعة غير معتمدة — كلاهما يُكتشف."""
    now = "2026-01-01T00:00:00Z"
    async with db.transaction() as tx:
        await tx.execute(
            "INSERT INTO payments (user_id, method_id, amount_units, credited_units, status, created_at, updated_at)"
            " VALUES (?, ?, 100000, 100000, 'approved', ?, ?)", (user.id, payment_method.id, now, now))
    title = "دفعة معتمدة بلا إيداع واحد مطابق، أو إيداع لدفعة غير معتمدة"
    assert title in _failed(_run(Path(db.path)))


async def test_stuck_submitting_is_warning_only(
    services, repos, db, user, admin, mock_service, mock_client, payment_method
) -> None:
    """طلب عالق في submitting ⇒ تنبيه (warn) لا يُفشل الخروج."""
    await services.wallet.adjust_balance(target=user, amount_units=100 * 10_000, admin=admin, reason="شحن", credit=True)
    order = await services.orders.create_order(user, service_id=mock_service.id, link="https://example.com/b", quantity=1000)
    async with db.transaction() as tx:
        await tx.execute("UPDATE orders SET status = ?, updated_at = '2020-01-01T00:00:00Z' WHERE id = ?", (OrderStatus.SUBMITTING, order.id))
        await tx.execute(
            "INSERT INTO order_status_history (order_id, from_status, to_status, actor_type, created_at)"
            " VALUES (?, ?, ?, 'system', '2020-01-01T00:00:00Z')", (order.id, order.status, OrderStatus.SUBMITTING))
    findings = _run(Path(db.path))
    stuck = [f for f in findings if f.severity == "warn"]
    assert stuck and stuck[0].count == 1
    assert _failed(findings) == set()
