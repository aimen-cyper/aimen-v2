"""
تدقيق تسعير للقراءة فقط (v1.3.1، بند 5) — يحدّد بالأرقام لماذا تبدو أسعار الريال غير متناسبة.

لا يغيّر هذا السكربت أي سعر ولا أي صف: الاتصال بوضع `query_only`، والملف الوحيد الذي قد يكتبه هو ملف CSV
الذي تحدده أنت بـ `--csv`. شغّله على **نسخة** من القاعدة.

ما يفحصه (كل الحسابات بأعداد صحيحة/Decimal، بلا float):
    1. لكل مزود: عملته وسعر صرفه، ومقارنته بإعداد `usd_rate` (عرض الدولار للعميل) — فرق الاثنين مصدر شائع لأسعار «غير
       متناسبة» لأن `usd_rate` للعرض فقط ولا يدخل في التسعير بينما `exchange_rate` هو ما تُحوَّل به تكلفة المزود.
    2. لكل خدمة: التكلفة المخزّنة (بعملة النظام) ⇒ السعر الأصلي المُستنتَج عند المزود (التكلفة ÷ سعر الصرف) ⇒ الهامش الفعلي %
       ⇒ تنبيه لهامش سالب أو ضعيف، ولخطأ التقريب لأربع خانات عندما يتجاوز 0.5% (خدمات رخيصة جداً).
    3. لكل طلب: إعادة حساب `cost_units` من لقطة السعر والكمية (`(السعر×الكمية+500)//1000`) ومقارنتها بالمخصوم، وإظهار
       انحراف سعر الألف التاريخي عن سعر الخدمة الحالي (طبيعي بعد تعديل السعر؛ الطلب القائم لا يتغير).
    4. `--find 43.41 36.53 …`: يبحث عن هذه المبالغ بالضبط في أسعار الخدمات والتكاليف وتكلفة الطلبات وحركات المحفظة، ويشرح من أين جاء
       كل رقم (خدمة/طلب/حركة) مع سعر الصرف المستخدم.

التشغيل:
    python -m scripts.pricing_audit --db نسخة.db
    python -m scripts.pricing_audit --db نسخة.db --find 43.41 36.53 3.98 94.74
    python -m scripts.pricing_audit --db نسخة.db --csv services.csv --orders 20

كود الخروج: 0 لا مشاكل مؤكدة · 1 وُجد هامش سالب أو خلل حسابي في طلب · 2 تعذّر فتح القاعدة.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Config, ConfigError                      # noqa: E402
from core.constants import APP_VERSION                       # noqa: E402
from core.money import MONEY_SCALE, order_cost_units         # noqa: E402

#: هامش أقل من هذه النسبة يُعدّ ضعيفاً (تنبيه فقط)
WEAK_MARGIN_PERCENT = Decimal("5")
#: خطأ التقريب النسبي (أربع خانات) الأعلى من هذا يُنبَّه إليه
ROUNDING_WARN_PERCENT = Decimal("0.5")


def money(units: int | None) -> str:
    """تنسيق وحدات صحيحة كمبلغ بأربع خانات كحد أقصى (بلا float)."""
    if units is None:
        return "—"
    sign = "-" if units < 0 else ""
    whole, frac = divmod(abs(int(units)), MONEY_SCALE)
    return f"{sign}{whole}.{frac:04d}".rstrip("0").rstrip(".") or "0"


def to_decimal(raw: object) -> Decimal | None:
    """نص ⇒ Decimal موجب، وإلا None."""
    try:
        value = Decimal(str(raw).strip().replace(",", ""))
    except (InvalidOperation, AttributeError):
        return None
    return value if value.is_finite() and value > 0 else None


def parse_units(text: str) -> int:
    """«43.41» ⇒ 434100 وحدة (بلا float)."""
    return int((Decimal(text) * MONEY_SCALE).quantize(Decimal(1), rounding=ROUND_HALF_UP))


@dataclass
class ServiceRow:
    """سطر تدقيق خدمة واحدة."""

    service_id: int
    name: str
    provider: str
    price: int
    cost: int | None
    rate: Decimal | None
    currency: str
    native_cost: Decimal | None
    margin_percent: Decimal | None
    flags: list[str]


def _factor(provider: sqlite3.Row, system_code: str) -> Decimal | None:
    """معامل تحويل عملة المزود إلى عملة النظام (مثل ProviderService.rate_state، بلا افتراض بصمت)."""
    rate = to_decimal(provider["exchange_rate"]) if provider["exchange_rate"] else None
    if rate is not None:
        return rate
    code = (provider["currency"] or "").strip().upper()
    return Decimal(1) if code and code == system_code.strip().upper() else None


def setting(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    """قيمة إعداد (نص) أو الافتراضي."""
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return default if row is None or row[0] is None else str(row[0])


def audit_providers(conn: sqlite3.Connection, system_code: str) -> tuple[list[dict], list[str]]:
    """جدول المزودين مع مقارنة `usd_rate` بسعر صرف كل مزود بعملة غير عملة النظام."""
    usd_rate = to_decimal(setting(conn, "usd_rate"))
    rows, notes = [], []
    if usd_rate is None:
        notes.append("إعداد usd_rate فارغ أو غير صالح ⇒ يُخفى مقابل الدولار في الواجهة (لا احتياطي في الكود).")
    for p in conn.execute("SELECT * FROM providers ORDER BY id"):
        factor = _factor(p, system_code)
        entry = {"id": p["id"], "name": p["name"], "currency": p["currency"] or "—", "rate": factor, "note": ""}
        code = (p["currency"] or "").strip().upper()
        if factor is None:
            entry["note"] = "عملة مختلفة بلا سعر صرف ⇒ المزود غير جاهز (لا يُفترض 1:1)"
        elif code == "USD" and usd_rate is not None and factor != usd_rate:
            entry["note"] = (f"تنبيه: سعر صرف المزود {factor.normalize():f} ≠ usd_rate {usd_rate.normalize():f} "
                             "⇒ الدولار المعروض للعميل لا يطابق سعر الصرف الذي سُعِّرت به الخدمة")
            notes.append(f"المزود #{p['id']} ({p['name']}): {entry['note']}")
        rows.append(entry)
    return rows, notes


def audit_services(conn: sqlite3.Connection, system_code: str) -> list[ServiceRow]:
    """تدقيق كل خدمة غير مؤرشفة."""
    providers = {p["id"]: p for p in conn.execute("SELECT * FROM providers")}
    out: list[ServiceRow] = []
    for s in conn.execute("SELECT * FROM services WHERE is_archived = 0 ORDER BY id"):
        provider = providers.get(s["provider_id"])
        factor = _factor(provider, system_code) if provider is not None else None
        cost = s["provider_price_per_1000_units"]
        price = s["price_per_1000_units"]
        flags: list[str] = []
        native = margin = None
        if cost is None:
            flags.append("بلا تكلفة مسجَّلة (زامن الخدمات)")
        else:
            if price < cost:
                flags.append("هامش سالب")
            if cost:
                margin = (Decimal(price - cost) * 100 / Decimal(cost)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if 0 <= margin < WEAK_MARGIN_PERCENT:
                    flags.append("هامش ضعيف")
                half_unit_error = Decimal("0.5") * 100 / Decimal(cost)         # خطأ تخزين نصف وحدة (0.00005)
                if half_unit_error > ROUNDING_WARN_PERCENT:
                    flags.append(f"خطأ تقريب حتى {half_unit_error.quantize(Decimal('0.01'))}%")
            if factor is not None:
                native = (Decimal(cost) / MONEY_SCALE / factor).quantize(Decimal("0.00000001"))
        out.append(ServiceRow(s["id"], s["name"], provider["name"] if provider else "؟", price, cost, factor,
                              (provider["currency"] if provider else "") or "—", native, margin, flags))
    return out


def audit_orders(conn: sqlite3.Connection, limit: int) -> tuple[list[dict], int]:
    """إعادة حساب تكلفة الطلبات من لقطتها ومقارنتها بالمخصوم وبسعر الخدمة الحالي."""
    rows, bad = [], 0
    query = """
        SELECT o.id, o.public_code, o.status, o.quantity, o.cost_units, o.price_per_1000_snapshot_units AS snap,
               o.refund_amount_units AS refund, s.price_per_1000_units AS current_price
          FROM orders o LEFT JOIN services s ON s.id = o.service_id ORDER BY o.id
    """
    for o in conn.execute(query):
        expected = order_cost_units(o["snap"], o["quantity"])
        problem = "" if expected == o["cost_units"] else "المخصوم لا يطابق إعادة الحساب"
        bad += bool(problem)
        drift = "" if o["current_price"] in (None, o["snap"]) else f"سعر الخدمة الآن {money(o['current_price'])} (الطلب ثابت)"
        rows.append({"id": o["id"], "code": o["public_code"], "status": o["status"], "qty": o["quantity"],
                     "snap": o["snap"], "charged": o["cost_units"], "expected": expected, "refund": o["refund"],
                     "note": problem or drift})
    return (rows if limit <= 0 else rows[:limit]), bad


def find_amounts(conn: sqlite3.Connection, amounts: list[str], system_code: str) -> list[str]:
    """البحث عن مبالغ بعينها في الخدمات/الطلبات/الحركات وشرح مصدر كل منها."""
    lines: list[str] = []
    for text in amounts:
        try:
            target = parse_units(text)
        except InvalidOperation:
            lines.append(f"• {text}: رقم غير صالح")
            continue
        hits: list[str] = []
        for s in conn.execute(
            "SELECT s.*, p.name AS pname, p.currency, p.exchange_rate FROM services s JOIN providers p ON p.id = s.provider_id "
            "WHERE s.price_per_1000_units = ? OR s.provider_price_per_1000_units = ?", (target, target)):
            kind = "سعر بيع/1000" if s["price_per_1000_units"] == target else "تكلفة/1000"
            rate = s["exchange_rate"] or "1"
            native = (Decimal(target) / MONEY_SCALE / (to_decimal(rate) or Decimal(1))).quantize(Decimal("0.0001"))
            hits.append(f"خدمة #{s['id']} «{s['name']}» ({s['pname']}، {s['currency']} × {rate}): {kind} ⇒ ≈ {native} {s['currency']} عند المزود")
        for o in conn.execute(
            "SELECT * FROM orders WHERE cost_units = ? OR price_per_1000_snapshot_units = ? OR refund_amount_units = ?",
            (target, target, target)):
            what = "تكلفة الطلب" if o["cost_units"] == target else ("لقطة سعر/1000" if o["price_per_1000_snapshot_units"] == target else "مبلغ مُسترجَع")
            hits.append(f"طلب #{o['id']} [{o['status']}] كمية {o['quantity']}: {what}؛ لقطة السعر {money(o['price_per_1000_snapshot_units'])}")
        for t in conn.execute("SELECT * FROM transactions WHERE amount_units = ?", (target,)):
            hits.append(f"حركة #{t['id']} نوع {t['type']} {t['direction']} (طلب {t['order_id'] or '—'})")
        lines.append(f"• {text} ({target} وحدة): " + ("لا مصدر في القاعدة" if not hits else ""))
        lines.extend(f"    - {hit}" for hit in hits)
    return lines


def render(conn: sqlite3.Connection, path: Path, *, find: list[str], order_limit: int) -> tuple[str, int, list[ServiceRow]]:
    """بناء التقرير النصي؛ يعيد (النص، عدد المشاكل المؤكدة، صفوف الخدمات)."""
    system_code = (setting(conn, "currency_code", "YER")).strip().upper() or "؟"
    lines = [f"💲 تدقيق التسعير (قراءة فقط) — SMM Bot {APP_VERSION}", f"القاعدة: {path}", f"عملة النظام: {system_code}",
             f"usd_rate (للعرض فقط): {setting(conn, 'usd_rate') or 'غير مضبوط'}", "─" * 56, "المزودون:"]
    providers, notes = audit_providers(conn, system_code)
    for p in providers:
        lines.append(f"  #{p['id']} {p['name']}: {p['currency']} × {p['rate'].normalize():f}" if p["rate"] else f"  #{p['id']} {p['name']}: {p['currency']} (بلا سعر)")
        if p["note"]:
            lines.append(f"      ⚠️ {p['note']}")
    services = audit_services(conn, system_code)
    lines += ["─" * 56, "الخدمات (id · بيع/1000 · تكلفة/1000 · هامش% · الأصلي عند المزود):"]
    negative = 0
    for s in services:
        negative += "هامش سالب" in s.flags
        native = f"{s.native_cost.normalize():f} {s.currency}" if s.native_cost is not None else "—"
        flag = ("  ⚠️ " + "، ".join(s.flags)) if s.flags else ""
        lines.append(f"  #{s.service_id} {s.name[:28]} · {money(s.price)} · {money(s.cost)} · {s.margin_percent if s.margin_percent is not None else '—'}% · {native}{flag}")
    orders, bad_orders = audit_orders(conn, order_limit)
    lines += ["─" * 56, "الطلبات (id · حالة · كمية · لقطة السعر · مخصوم · المتوقع · مُسترجَع):"]
    for o in orders:
        lines.append(f"  #{o['id']} {o['status']} · {o['qty']} · {money(o['snap'])} · {money(o['charged'])} · {money(o['expected'])} · {money(o['refund'])}"
                     + (f"  ⚠️ {o['note']}" if o["note"] else ""))
    if find:
        lines += ["─" * 56, "البحث عن المبالغ:"] + find_amounts(conn, find, system_code)
    if notes:
        lines += ["─" * 56, "ملاحظات:"] + [f"  • {n}" for n in notes]
    problems = negative + bad_orders
    lines += ["─" * 56, f"النتيجة: {negative} خدمة بهامش سالب · {bad_orders} طلب بحساب غير مطابق · {len(notes)} ملاحظة اتساق"]
    return "\n".join(lines), problems, services


def write_csv(path: Path, services: list[ServiceRow]) -> None:
    """تصدير جدول الخدمات (الملف الوحيد الذي تكتبه الأداة، وبطلب صريح)."""
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["service_id", "name", "provider", "price_per_1000", "cost_per_1000", "margin_percent",
                         "provider_currency", "exchange_rate", "implied_native_cost", "flags"])
        for s in services:
            writer.writerow([s.service_id, s.name, s.provider, money(s.price), money(s.cost), s.margin_percent,
                             s.currency, s.rate, s.native_cost, "; ".join(s.flags)])


def main(argv: list[str] | None = None) -> int:
    """نقطة الدخول."""
    parser = argparse.ArgumentParser(description="تدقيق تسعير للقراءة فقط")
    parser.add_argument("--db", type=Path, help="مسار نسخة القاعدة (الافتراضي DATABASE_PATH)")
    parser.add_argument("--find", nargs="*", default=[], help="مبالغ للبحث عن مصدرها مثل 43.41 36.53")
    parser.add_argument("--csv", type=Path, help="تصدير جدول الخدمات إلى CSV")
    parser.add_argument("--orders", type=int, default=0, help="عدد الطلبات المعروضة (0 = الكل)")
    args = parser.parse_args(argv)
    path = args.db
    if path is None:
        try:
            path = Config.load().database_path
        except ConfigError as exc:
            print(f"⛔ خطأ في الإعدادات: {exc}", file=sys.stderr)
            return 2
    if not path.exists():
        print(f"⛔ ملف القاعدة غير موجود: {path}", file=sys.stderr)
        return 2
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only = ON")
        text, problems, services = render(conn, path, find=args.find, order_limit=args.orders)
    except sqlite3.Error as exc:
        print(f"⛔ فشل التدقيق: {exc}", file=sys.stderr)
        return 2
    finally:
        conn.close()
    print(text)
    if args.csv:
        write_csv(args.csv, services)
        print(f"✍️ كُتب {args.csv}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
