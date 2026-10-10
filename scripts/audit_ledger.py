"""
تدقيق مالي للقراءة فقط (المرحلة 12) — يطابق أرصدة المحافظ مع دفتر الحركات وحالة الطلبات والمدفوعات.

لماذا؟ الأرصدة تُعدَّل من خدمة واحدة فقط، لكن المشغّل يحتاج أداة مستقلة تثبت (أو تنفي) سلامة
البيانات بعد استعادة نسخة أو ترقية أو تعديل يدوي على القاعدة. هذه الأداة تُشغَّل في أي وقت
(حتى والبوت يعمل) ولا تكتب أي شيء: الاتصال في وضع `query_only`.

الفحوص:
    1. سلامة ملف SQLite (`PRAGMA integrity_check`) والمفاتيح الأجنبية.
    2. رصيد كل مستخدم = مجموع حركاته (دائن − مدين)، ولا رصيد سالب.
    3. سلسلة الحركات: رصيد «قبل» كل حركة = رصيد «بعد» السابقة، والحساب الحسابي صحيح.
    4. لكل طلب حركة خصم واحدة بالضبط بقيمة التكلفة.
    5. مجموع استرجاعات الطلب = `orders.refund_amount_units` ولا يتجاوز التكلفة.
    6. اتساق الحالة النهائية مع الاسترجاع (مكتمل بلا استرجاع، مُسترجَع بالكامل).
    7. تاريخ حالات الطلب سلسلة متصلة وآخر سجل فيه = حالته الحالية.
    8. كل دفعة معتمدة لها إيداع واحد بقيمة `credited_units`، ولا إيداع لدفعة غير معتمدة.
    9. طلبات عالقة في `submitting` أكثر من 10 دقائق (تنبيه، لا خطأ مالي).
   10. (v1.3.1) **طلب مُسترجَع/ملغى/فاشل بمبلغ مُسترجَع بينما أبلغ المزود تنفيذه** (آخر `provider_status` أو أي حالة سابقة في
       التاريخ من: Completed / In progress / Processing / Partial) — الخطر: العميل حصل على الخدمة واستعاد ماله معاً. خلل (bad).
   11. (v1.3.1) تنبيهات حسابية: تكلفة الطلب ≠ (لقطة السعر × الكمية)، واسترجاع جزئي ≠ (التكلفة × المتبقي) ÷ الكمية.

طريقة التشغيل (من مجلد المشروع):
    python -m scripts.audit_ledger               # يقرأ DATABASE_PATH من .env
    python -m scripts.audit_ledger --db path.db  # أو نسخة/قاعدة محددة (مثلاً نسخة مستعادة للمعاينة)
    python -m scripts.audit_ledger --limit 50    # عدد الأمثلة المعروضة لكل فحص (الافتراضي 10)

كود الخروج: 0 سليم (قد توجد تنبيهات) · 1 اكتُشف خلل مالي/بنيوي · 2 تعذّر فتح القاعدة.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:                      # تشغيل مباشر بلا تثبيت الحزمة
    sys.path.insert(0, str(ROOT))

from config import Config, ConfigError                      # noqa: E402
from core.constants import APP_VERSION                       # noqa: E402
from core.money import MONEY_SCALE                           # noqa: E402

STUCK_SUBMITTING_MINUTES = 10                  # بعد هذه المدة يُعدّ الطلب في `submitting` عالقاً


@dataclass
class Finding:
    """نتيجة فحص واحد: عنوانه، شدته، عدد المخالفات، وأمثلة منها."""

    title: str                                  # اسم الفحص بالعربية
    severity: str                               # "bad" خلل · "warn" تنبيه
    count: int = 0                              # عدد المخالفات الكلي
    samples: list[str] = field(default_factory=list)   # أمثلة (سقف --limit)


def _units(value: int) -> str:
    """تنسيق وحدات مالية صحيحة كمبلغ مقروء (بلا حسابات عائمة)."""
    sign = "-" if value < 0 else ""
    whole, frac = divmod(abs(int(value)), MONEY_SCALE)
    return f"{sign}{whole}.{frac:04d}".rstrip("0").rstrip(".") or "0"


def _scan(conn: sqlite3.Connection, title: str, severity: str, sql: str, fmt, limit: int, params=()) -> Finding:
    """تنفيذ استعلام يعيد صفوف المخالفات فقط، وتحويله إلى `Finding` بأمثلة مقروءة."""
    rows = conn.execute(sql, params).fetchall()
    return Finding(title, severity, len(rows), [fmt(row) for row in rows[:limit]])


def audit(conn: sqlite3.Connection, *, limit: int = 10, now: datetime | None = None) -> list[Finding]:
    """
    تشغيل كل الفحوص على اتصال للقراءة فقط وإرجاع نتائجها بالترتيب.

    المدخلات: اتصال sqlite3 · limit عدد الأمثلة لكل فحص · now للاختبار.
    المخرجات: قائمة `Finding` (count=0 تعني أن الفحص سليم).
    """
    conn.row_factory = sqlite3.Row
    out: list[Finding] = []

    integrity = [row[0] for row in conn.execute("PRAGMA integrity_check").fetchall()]
    bad_integrity = [] if integrity == ["ok"] else integrity
    out.append(Finding("سلامة ملف القاعدة (integrity_check)", "bad", len(bad_integrity), bad_integrity[:limit]))
    out.append(_scan(conn, "انتهاكات المفاتيح الأجنبية", "bad", "PRAGMA foreign_key_check",
                     lambda r: f"جدول {r[0]} صف {r[1]} ⇒ {r[2]}", limit))

    out.append(_scan(
        conn, "رصيد المحفظة لا يساوي مجموع الحركات", "bad",
        """
        SELECT u.id, u.telegram_id, u.balance_units AS stored,
               COALESCE((SELECT SUM(CASE WHEN t.direction = 'credit' THEN t.amount_units ELSE -t.amount_units END)
                           FROM transactions t WHERE t.user_id = u.id), 0) AS ledger
          FROM users u
         WHERE u.balance_units <> ledger
         ORDER BY u.id
        """,
        lambda r: f"مستخدم #{r['id']} (tg {r['telegram_id']}): مخزَّن {_units(r['stored'])} ≠ دفتر {_units(r['ledger'])}",
        limit,
    ))
    out.append(_scan(conn, "رصيد سالب", "bad", "SELECT id, balance_units FROM users WHERE balance_units < 0",
                     lambda r: f"مستخدم #{r['id']}: {_units(r['balance_units'])}", limit))

    out.append(_scan(
        conn, "انقطاع سلسلة الحركات أو خطأ حسابي فيها", "bad",
        """
        SELECT id, user_id, balance_before_units AS before, balance_after_units AS after, direction, amount_units,
               prev_after
          FROM (SELECT t.*, LAG(balance_after_units, 1, 0) OVER (PARTITION BY user_id ORDER BY id) AS prev_after
                  FROM transactions t)
         WHERE before <> prev_after
            OR after <> before + CASE WHEN direction = 'credit' THEN amount_units ELSE -amount_units END
         ORDER BY id
        """,
        lambda r: (f"حركة #{r['id']} (مستخدم #{r['user_id']}): قبل {_units(r['before'])} "
                   f"/ السابقة {_units(r['prev_after'])} / بعد {_units(r['after'])}"),
        limit,
    ))

    out.append(_scan(
        conn, "طلب بلا حركة خصم واحدة بقيمة التكلفة", "bad",
        """
        SELECT o.id, o.cost_units, COUNT(t.id) AS n, COALESCE(SUM(t.amount_units), 0) AS total
          FROM orders o
          LEFT JOIN transactions t ON t.order_id = o.id AND t.type = 'order' AND t.direction = 'debit'
         GROUP BY o.id
        HAVING n <> 1 OR total <> o.cost_units
         ORDER BY o.id
        """,
        lambda r: f"طلب #{r['id']}: التكلفة {_units(r['cost_units'])} · حركات الخصم {r['n']} بمجموع {_units(r['total'])}",
        limit,
    ))
    out.append(_scan(
        conn, "مجموع الاسترجاعات لا يطابق حقل الاسترجاع في الطلب (أو يتجاوز التكلفة)", "bad",
        """
        SELECT o.id, o.cost_units, o.refund_amount_units AS stored, COALESCE(SUM(t.amount_units), 0) AS ledger
          FROM orders o
          LEFT JOIN transactions t ON t.order_id = o.id AND t.type IN ('refund', 'partial_refund')
                                  AND t.direction = 'credit'
         GROUP BY o.id
        HAVING stored <> ledger OR ledger > o.cost_units
         ORDER BY o.id
        """,
        lambda r: f"طلب #{r['id']}: مخزَّن {_units(r['stored'])} · دفتر {_units(r['ledger'])} · تكلفة {_units(r['cost_units'])}",
        limit,
    ))
    out.append(_scan(
        conn, "حالة نهائية لا تتسق مع الاسترجاع", "bad",
        """
        SELECT id, status, cost_units, refund_amount_units AS refund FROM orders
         WHERE (status = 'completed' AND refund <> 0)
            OR (status IN ('refunded', 'canceled') AND refund <> cost_units)
            OR (status = 'partial' AND refund >= cost_units)
            OR (status IN ('pending', 'submitting', 'submit_uncertain', 'submitted', 'in_progress') AND refund <> 0)
         ORDER BY id
        """,
        lambda r: f"طلب #{r['id']} [{r['status']}]: تكلفة {_units(r['cost_units'])} · مُسترجَع {_units(r['refund'])}",
        limit,
    ))
    out.append(_scan(
        conn, "آخر سجل في تاريخ الحالات لا يساوي حالة الطلب", "bad",
        """
        SELECT o.id, o.status, h.to_status
          FROM orders o
          JOIN order_status_history h ON h.id = (SELECT MAX(id) FROM order_status_history WHERE order_id = o.id)
         WHERE h.to_status <> o.status
         ORDER BY o.id
        """,
        lambda r: f"طلب #{r['id']}: الحالة {r['status']} ≠ آخر سجل {r['to_status']}",
        limit,
    ))

    out.append(_scan(
        conn, "انقطاع في سلسلة تاريخ حالات الطلب", "bad",
        """
        SELECT order_id, id, from_status, prev_to
          FROM (SELECT h.*, LAG(to_status) OVER (PARTITION BY order_id ORDER BY id) AS prev_to
                  FROM order_status_history h)
         WHERE COALESCE(from_status, '') <> COALESCE(prev_to, '')
         ORDER BY id
        """,
        lambda r: f"طلب #{r['order_id']} سجل #{r['id']}: من «{r['from_status']}» لكن السابق انتهى «{r['prev_to']}»",
        limit,
    ))

    out.append(_scan(
        conn, "دفعة معتمدة بلا إيداع واحد مطابق، أو إيداع لدفعة غير معتمدة", "bad",
        """
        SELECT p.id, p.status, p.credited_units AS credited, COUNT(t.id) AS n, COALESCE(SUM(t.amount_units), 0) AS total
          FROM payments p
          LEFT JOIN transactions t ON t.payment_id = p.id AND t.type = 'deposit'
         GROUP BY p.id
        HAVING (p.status = 'approved' AND (n <> 1 OR p.credited_units IS NULL OR total <> p.credited_units))
            OR (p.status <> 'approved' AND n > 0)
         ORDER BY p.id
        """,
        lambda r: f"دفعة #{r['id']} [{r['status']}]: المعتمد {_units(r['credited'] or 0)} · إيداعات {r['n']} بمجموع {_units(r['total'])}",
        limit,
    ))

    reference = now or datetime.now(timezone.utc)
    cutoff = (reference - timedelta(minutes=STUCK_SUBMITTING_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    out.append(_scan(
        conn, f"طلبات عالقة في «submitting» أكثر من {STUCK_SUBMITTING_MINUTES} دقائق", "warn",
        "SELECT id, updated_at FROM orders WHERE status = 'submitting' AND replace(substr(updated_at, 1, 19), 'T', ' ') < ? ORDER BY id",
        lambda r: f"طلب #{r['id']} منذ {r['updated_at']}",
        limit, (cutoff,),
    ))

    # ------------------------------ فحوص v1.3.1 ------------------------------ #
    executed = "('completed', 'in progress', 'inprogress', 'processing', 'partial')"
    out.append(_scan(
        conn, "مُسترجَع/ملغى بينما أبلغ المزود تنفيذ الطلب (قد يكون العميل حصل على الخدمة واستعاد ماله)", "bad",
        f"""
        SELECT o.id, o.status, o.refund_amount_units AS refund, o.provider_status,
               (SELECT h.provider_status_raw FROM order_status_history h
                 WHERE h.order_id = o.id AND lower(trim(COALESCE(h.provider_status_raw, ''))) IN {executed}
                 ORDER BY h.id DESC LIMIT 1) AS seen
          FROM orders o
         WHERE o.status IN ('refunded', 'canceled', 'failed') AND o.refund_amount_units > 0
           AND (lower(trim(COALESCE(o.provider_status, ''))) IN {executed}
                OR EXISTS (SELECT 1 FROM order_status_history h
                            WHERE h.order_id = o.id
                              AND lower(trim(COALESCE(h.provider_status_raw, ''))) IN {executed}))
         ORDER BY o.id
        """,
        lambda r: (f"طلب #{r['id']} [{r['status']}]: مُسترجَع {_units(r['refund'])} · "
                   f"حالة المزود «{r['provider_status'] or r['seen']}» — راجع لوحة المزود قبل أي إجراء"),
        limit,
    ))
    out.append(_scan(
        conn, "تكلفة الطلب لا تطابق لقطة السعر × الكمية", "warn",
        """
        SELECT id, cost_units, price_per_1000_snapshot_units AS price, quantity,
               (price_per_1000_snapshot_units * quantity + 500) / 1000 AS expected
          FROM orders WHERE cost_units <> expected ORDER BY id
        """,
        lambda r: f"طلب #{r['id']}: مخصوم {_units(r['cost_units'])} ≠ المتوقع {_units(r['expected'])} (كمية {r['quantity']})",
        limit,
    ))
    out.append(_scan(
        conn, "استرجاع جزئي لا يطابق (التكلفة × المتبقي) ÷ الكمية", "warn",
        """
        SELECT id, cost_units, quantity, remains, refund_amount_units AS refund,
               (cost_units * remains) / quantity AS expected
          FROM orders WHERE status = 'partial' AND remains IS NOT NULL AND refund_amount_units <> expected
         ORDER BY id
        """,
        lambda r: f"طلب #{r['id']}: مُسترجَع {_units(r['refund'])} ≠ المتوقع {_units(r['expected'])} (متبقي {r['remains']} من {r['quantity']})",
        limit,
    ))
    return out


def open_readonly(path: Path) -> sqlite3.Connection:
    """فتح القاعدة بوضع `query_only` (يرفض أي كتابة حتى لو وُجد خطأ في الأداة نفسها)."""
    if not path.exists():
        raise FileNotFoundError(f"ملف القاعدة غير موجود: {path}")
    conn = sqlite3.connect(str(path), timeout=10)
    conn.execute("PRAGMA query_only = ON")
    return conn


def render(findings: list[Finding], path: Path) -> str:
    """تنسيق التقرير النصي النهائي مع الملخص."""
    lines = [f"🧮 تدقيق مالي — SMM Bot {APP_VERSION}", f"القاعدة: {path}", "─" * 44]
    for item in findings:
        if item.count == 0:
            lines.append(f"  ✅ {item.title}")
            continue
        mark = "⛔" if item.severity == "bad" else "⚠️ "
        lines.append(f"  {mark} {item.title}: {item.count}")
        lines.extend(f"       • {sample}" for sample in item.samples)
        if item.count > len(item.samples):
            lines.append(f"       … و{item.count - len(item.samples)} أخرى (زد --limit لعرضها)")
    bad = sum(1 for f in findings if f.count and f.severity == "bad")
    warn = sum(1 for f in findings if f.count and f.severity == "warn")
    lines += ["─" * 44, f"النتيجة: {bad} فحص فاشل · {warn} تنبيه · {len(findings) - bad - warn} سليم"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """نقطة الدخول: قراءة الوسائط، تشغيل التدقيق، طباعة التقرير، وإرجاع رمز الخروج."""
    parser = argparse.ArgumentParser(description="تدقيق مالي للقراءة فقط")
    parser.add_argument("--db", type=Path, help="مسار قاعدة بيانات محددة (الافتراضي DATABASE_PATH)")
    parser.add_argument("--limit", type=int, default=10, help="عدد الأمثلة لكل فحص")
    args = parser.parse_args(argv)

    path = args.db
    if path is None:
        try:
            path = Config.load().database_path
        except ConfigError as exc:
            print(f"⛔ خطأ في الإعدادات: {exc}", file=sys.stderr)
            return 2
    try:
        conn = open_readonly(path)
    except (FileNotFoundError, sqlite3.Error) as exc:
        print(f"⛔ تعذّر فتح القاعدة: {exc}", file=sys.stderr)
        return 2
    try:
        findings = audit(conn, limit=max(1, args.limit))
    except sqlite3.Error as exc:
        print(f"⛔ فشل التدقيق (هل نُفّذت الترحيلات؟ شغّل init_db): {exc}", file=sys.stderr)
        return 2
    finally:
        conn.close()
    print(render(findings, path))
    return 1 if any(f.count and f.severity == "bad" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
