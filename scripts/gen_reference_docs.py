"""
توليد المراجع الآلية للمشغّل من مصدر الحقيقة (الكود + ترحيلات القاعدة).

الاستخدام (من مجلد المشروع):
    python -m scripts.gen_reference_docs           # يكتب docs/SETTINGS.md و docs/PERMISSIONS.md
    python -m scripts.gen_reference_docs --check   # يفشل (رمز 1) إن كان أي ملف قديماً عن الكود

لماذا؟ جداول الإعدادات والصلاحيات تتغير عبر المراحل؛ كتابتها يدوياً تعني توثيقاً كاذباً مع الوقت.
اختبار `test_release_phase12` يستدعي نفس الدالة ويفشل لو تخلّف التوثيق عن الكود.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

from config import BASE_DIR
from core.permissions import PERMISSIONS, ROLE_DEFAULTS, ROLES
from core.setting_rules import GENERIC_MONEY_MAX, SETTING_RULES
from database.database import Database
from database.migrator import Migrator

DOCS_DIR = BASE_DIR / "docs"
TYPE_AR = {"str": "نص", "int": "عدد صحيح", "bool": "نعم/لا", "json": "JSON", "money": "مبلغ (وحدات صحيحة)"}
GROUP_AR = {
    "general": "عامة", "orders": "الطلبات", "payments": "الشحن", "notifications": "الإشعارات",
    "security": "الأمان", "providers": "المزودون", "tickets": "الدعم الفني", "backup": "النسخ الاحتياطي",
    "reports": "التقارير", "stats": "الإحصائيات", "users": "المستخدمون", "catalog": "الكتالوج",
    "system": "النظام", "broadcast": "الإذاعة", "jobs": "المهام", "channels": "القنوات",
}


def _cell(value: object, limit: int = 70) -> str:
    """نص صالح لخلية جدول Markdown (بلا أسطر جديدة أو `|`) مع اقتطاف الطويل."""
    text = " ".join(str(value if value is not None else "").split()).replace("|", "¦")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _range_text(key: str, value_type: str) -> str:
    """وصف النطاق المسموح لإعداد من قواعد `SETTING_RULES`."""
    rule = SETTING_RULES.get(key)
    if rule is None:
        return "ضمن الحدود العامة"
    parts: list[str] = []
    if rule.minimum is not None or rule.maximum is not None:
        high = "∞" if rule.maximum is None or rule.maximum >= GENERIC_MONEY_MAX else f"{rule.maximum:,}"
        parts.append(f"{(rule.minimum if rule.minimum is not None else 0):,} … {high}")
    if rule.max_length:
        parts.append(f"حتى {rule.max_length} حرفاً")
    if rule.hint:
        parts.append(rule.hint)
    if rule.allow_empty:
        parts.append("يقبل الفراغ")
    return "؛ ".join(parts) or ("نعم/لا" if value_type == "bool" else "—")


async def _settings_rows() -> list[dict]:
    """الإعدادات المزروعة فعلاً بعد تطبيق كل الترحيلات على قاعدة مؤقتة."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "reference.db")
        await db.connect()
        try:
            await Migrator(db).apply_all()
            rows = await db.fetchall(
                "SELECT key, value, value_type, group_code, name_ar, description_ar, is_editable "
                "FROM settings ORDER BY group_code, key"
            )
            return [dict(row) for row in rows]
        finally:
            await db.close()


def render_settings(rows: list[dict]) -> str:
    """نص `SETTINGS.md`: كل إعداد مع قيمته الافتراضية ونطاقه المسموح."""
    lines = [
        "# مرجع الإعدادات",
        "",
        "> **مولَّد آلياً** بالأمر `python -m scripts.gen_reference_docs` من ترحيلات القاعدة وقواعد "
        "`core/setting_rules.py` — لا تعدّله يدوياً (اختبار الإصدار يفشل إن تخلّف عن الكود).",
        "",
        f"عدد الإعدادات: **{len(rows)}** — تُعدَّل من البوت: «⚙️ الإعدادات»، وكل قيمة تُفحص قبل الحفظ "
        "بمصدر واحد (`SettingsService.set`) وتُدقَّق التغييرات.",
    ]
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["group_code"], []).append(row)
    for group, items in groups.items():
        lines += ["", f"## {GROUP_AR.get(group, group)} (`{group}`)", "",
                  "| المفتاح | الاسم | النوع | الافتراضي | النطاق المسموح | قابل للتعديل |",
                  "|---|---|---|---|---|---|"]
        for row in items:
            lines.append(
                f"| `{row['key']}` | {_cell(row['name_ar'], 40)} | {TYPE_AR.get(row['value_type'], row['value_type'])} "
                f"| `{_cell(row['value'], 40)}` | {_cell(_range_text(row['key'], row['value_type']), 80)} "
                f"| {'نعم' if row['is_editable'] else 'لا'} |"
            )
    return "\n".join(lines) + "\n"


def render_permissions() -> str:
    """نص `PERMISSIONS.md`: كتالوج الصلاحيات ومن يملكها افتراضياً (قابلة للتغيير من قاعدة البيانات)."""
    names = {role.code: role.name_ar for role in ROLES}
    columns = ["support", "admin", "super_admin"]
    lines = [
        "# مرجع الأدوار والصلاحيات",
        "",
        "> **مولَّد آلياً** بالأمر `python -m scripts.gen_reference_docs` من `core/permissions.py`. "
        "هذه **القيم الافتراضية** المزروعة عند التهيئة؛ الصلاحيات الفعلية تُقرأ من جداول "
        "`role_permissions` و`user_permissions` في قاعدة البيانات (لا أدمن ثابت في الكود). "
        "⚠️ = صلاحية خطِرة: منحها فردياً لغير الأدمن الأعلى محجوب، ويرصد «فحص الأمان» أي استثناء ممنوح لها.",
        "",
        f"عدد الصلاحيات: **{len(PERMISSIONS)}** (منها خطِرة: **{sum(p.is_dangerous for p in PERMISSIONS)}**).",
        "",
        "| الصلاحية | الوصف | المجموعة | " + " | ".join(names[c] for c in columns) + " |",
        "|---|---|---|" + "|".join("---" for _ in columns) + "|",
    ]
    for perm in PERMISSIONS:
        marks = ["✅" if perm.code in ROLE_DEFAULTS.get(c, ()) else "—" for c in columns]
        flag = " ⚠️" if perm.is_dangerous else ""
        lines.append(f"| `{perm.code}`{flag} | {_cell(perm.name_ar, 60)} | {perm.group_code} | " + " | ".join(marks) + " |")
    lines += ["", "المستخدم العادي (`user`) بلا أي صلاحية إدارية. أول أدمن أعلى يُزرع من `SUPER_ADMIN_IDS`، "
              "وتغيير دور مستخدم يتم من شاشته في «👥 المستخدمون» (🎚 تغيير الدور) أو بـ`python -m scripts.create_admin`. "
              "الاستثناءات الفردية (منح/منع صلاحية لشخص) تدعمها `AuthService.set_user_permission` لكن **لا شاشة لها في البوت** بعد."]
    return "\n".join(lines) + "\n"


def render_all() -> dict[Path, str]:
    """كل الملفات المولَّدة: مسارها ⇒ نصها الحالي المتوقَّع."""
    rows = asyncio.run(_settings_rows())
    return {DOCS_DIR / "SETTINGS.md": render_settings(rows), DOCS_DIR / "PERMISSIONS.md": render_permissions()}


def main(argv: list[str] | None = None) -> int:
    """كتابة المراجع أو التحقق من حداثتها (`--check`). رمز الخروج 1 إن كانت قديمة."""
    parser = argparse.ArgumentParser(description="توليد مراجع الإعدادات والصلاحيات")
    parser.add_argument("--check", action="store_true", help="تحقق فقط دون كتابة")
    args = parser.parse_args(argv)
    stale = 0
    for path, text in render_all().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if args.check:
            if current != text:
                print(f"❌ قديم: {path.relative_to(BASE_DIR)} — شغّل: python -m scripts.gen_reference_docs")
                stale = 1
            else:
                print(f"✅ حديث: {path.relative_to(BASE_DIR)}")
        else:
            path.write_text(text, encoding="utf-8")
            print(f"✍️  كُتب {path.relative_to(BASE_DIR)}")
    return stale


if __name__ == "__main__":
    sys.exit(main())
