"""
قواعد تخطيط لوحات الأزرار (WP0، بند 0) — مصدر واحد تستعمله الاختبارات ومولّد المعاينة.

القواعد (الصلبة = حدود تيليجرام، والتنسيقية = اتفاق المشروع):
    صلبة     : `callback_data` ≤ 64 بايت، ونص الزر غير فارغ، ولا `callback_data` مكرر داخل اللوحة.
    تنسيقية  : ≤ 3 أزرار بالصف، نص الزر ≤ 40 حرفاً، بلا مسافات بادئة/لاحقة، وبلا رمز إنجليزي خام (مثل «⚙️ backup»).
"""

from __future__ import annotations

import re
from typing import Iterable

MAX_BUTTONS_PER_ROW = 3
MAX_LABEL_CHARS = 40
MAX_CALLBACK_BYTES = 64

#: نص زر لا يحوي إلا حروفاً لاتينية/شرطات بعد الرموز = رمز إنجليزي خام
_RAW_CODE = re.compile(r"^[\W_]*[a-z][a-z0-9_ ]*$")


def layout_violations(rows: Iterable[Iterable]) -> list[str]:
    """مخالفات لوحة أزرار (قائمة صفوف أزرار `InlineKeyboardButton`)؛ فارغة = سليمة."""
    problems: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        row = list(row)
        if len(row) > MAX_BUTTONS_PER_ROW:
            problems.append(f"الصف {index} فيه {len(row)} أزرار (الحد {MAX_BUTTONS_PER_ROW})")
        for button in row:
            label = button.text or ""
            if not label.strip():
                problems.append(f"زر بلا نص في الصف {index}")
            if label != label.strip():
                problems.append(f"مسافة بادئة/لاحقة في «{label}»")
            if len(label) > MAX_LABEL_CHARS:
                problems.append(f"نص الزر أطول من {MAX_LABEL_CHARS}: «{label[:20]}…»")
            if _RAW_CODE.match(label):
                problems.append(f"رمز إنجليزي خام في زر: «{label}»")
            data = button.callback_data
            if data is not None:
                if len(data.encode()) > MAX_CALLBACK_BYTES:
                    problems.append(f"callback_data أطول من {MAX_CALLBACK_BYTES} بايت: {data[:24]}…")
                if data in seen:
                    problems.append(f"callback_data مكرر: {data}")
                seen.add(data)
    return problems
