"""
المرحلة 11 — بوابة جودة الكود (تحليل ساكن بـ`ast`) على كل شيفرة الإنتاج.

تُنفِّذ آلياً بنود «الممنوعات» و«تعريف الإنجاز» التي كانت تُراجَع يدوياً:

    • لا `except:` عارٍ ولا معالج استثناء صامت (`pass`/`continue`/نص فقط).
    • لا `except Exception/BaseException` بلا تسجيل أو إعادة رفع.
    • كل دالة لها docstring **عربي** (شرط التعليقات العربية بجانب كل دالة).
    • لا TODO/FIXME/XXX/HACK، ولا `eval/exec`، ولا `shell=True`.
    • لا أسرار مضمَّنة (توكن بوت، مفتاح Fernet، كلمة مرور/مفتاح API نصي).
    • لا `print` خارج نقاط الدخول وسكربتات CLI.
    • كل SQL يحتوي قيماً متغيرة يستعمل معاملات `?` (لا f-string فيها قيم مستخدم): نفحص أن f-strings
      في `execute/fetch*` لا تُدخل إلا أسماء مُعرَّفة من الكود (قائمة مسموح بها).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {"tests", ".venv", "venv", "__pycache__", "logs", "data", "backups", ".git", "node_modules"}
ARABIC = re.compile(r"[\u0600-\u06FF]")
#: نقاط الدخول/أدوات التطوير المسموح لها بـprint (إخراج للمشغّل)
PRINT_ALLOWED = ("scripts/", "main.py", "docs/")
#: أسرار مُعلنة كقيم وهمية صريحة (تحوي كلمة Dummy) مسموحة
DUMMY_MARK = "dummy"


def _files() -> list[Path]:
    """كل ملفات بايثون الإنتاجية في المشروع."""
    result = []
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        result.append(path)
    return result


def _parse(path: Path) -> tuple[ast.AST, str]:
    """قراءة الملف وتحليله."""
    source = path.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(path)), source


def _rel(path: Path) -> str:
    """مسار نسبي للعرض."""
    return path.relative_to(ROOT).as_posix()


def _handlers(tree: ast.AST):
    """كل معالجات except في شجرة."""
    return [node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)]


def test_there_is_production_code_to_scan() -> None:
    """حارس: ألا يصير الاختبار فارغاً لو تغيّر موضع الملفات."""
    assert len(_files()) > 100


def test_no_bare_except_and_no_silent_handlers() -> None:
    """لا `except:` عارٍ، ولا معالج جسمه pass/continue/تعبير ثابت فقط."""
    offenders = []
    for path in _files():
        tree, _ = _parse(path)
        for handler in _handlers(tree):
            if handler.type is None:
                offenders.append(f"{_rel(path)}:{handler.lineno} except عارٍ")
            silent = all(
                isinstance(stmt, (ast.Pass, ast.Continue))
                or (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant))
                for stmt in handler.body
            )
            if silent:
                offenders.append(f"{_rel(path)}:{handler.lineno} معالج صامت")
    assert not offenders, "\n".join(offenders)


def test_broad_exception_handlers_always_log_or_reraise() -> None:
    """`except Exception` مسموح فقط إن سُجّل الخطأ أو أُعيد رفعه (لا إخفاء أخطاء)."""
    offenders = []
    for path in _files():
        tree, _ = _parse(path)
        for handler in _handlers(tree):
            if handler.type is None:
                continue
            names = {ast.unparse(handler.type)} if not isinstance(handler.type, ast.Tuple) else {ast.unparse(e) for e in handler.type.elts}
            if not names & {"Exception", "BaseException"}:
                continue
            body = ast.unparse(ast.Module(body=handler.body, type_ignores=[]))
            handled = "raise" in body or "logger." in body or "log" in body.lower() or "report" in body.lower()
            if not handled:
                offenders.append(f"{_rel(path)}:{handler.lineno}")
    assert not offenders, "except واسع بلا تسجيل/رفع:\n" + "\n".join(offenders)


def test_every_function_has_arabic_docstring() -> None:
    """كل دالة (حتى الداخلية) لها docstring يحوي عربية — شرط المالك الأهم."""
    missing, not_arabic = [], []
    for path in _files():
        tree, _ = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node)
                if not doc:
                    missing.append(f"{_rel(path)}:{node.lineno} {node.name}")
                elif not ARABIC.search(doc):
                    not_arabic.append(f"{_rel(path)}:{node.lineno} {node.name}")
    assert not missing, "دوال بلا docstring:\n" + "\n".join(missing)
    assert not not_arabic, "docstring بلا عربية:\n" + "\n".join(not_arabic)


def test_no_todo_markers_eval_exec_or_shell() -> None:
    """لا علامات إنجاز ناقص ولا تنفيذ ديناميكي خطِر."""
    offenders = []
    marker = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
    for path in _files():
        tree, source = _parse(path)
        if _rel(path) != "tests/unit/test_code_quality_phase11.py":
            for number, line in enumerate(source.splitlines(), 1):
                if marker.search(line):
                    offenders.append(f"{_rel(path)}:{number} علامة ناقصة")
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                offenders.append(f"{_rel(path)}:{node.lineno} {node.func.id}")
            if isinstance(node, ast.keyword) and node.arg == "shell":
                offenders.append(f"{_rel(path)}:{node.value.lineno} shell=")
    assert not offenders, "\n".join(offenders)


def test_no_hardcoded_secrets() -> None:
    """لا توكن بوت ولا مفتاح Fernet ولا قيمة سرية نصية مضمَّنة (إلا قيماً وهمية معلنة)."""
    token = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")
    fernet = re.compile(r"\b[A-Za-z0-9_-]{43}=(?![A-Za-z0-9])")
    assign = re.compile(r"""(?i)\b(api_?key|password|passwd|secret|token)\s*=\s*["'][^"'\s]{8,}["']""")
    offenders = []
    for path in _files():
        _, source = _parse(path)
        for number, line in enumerate(source.splitlines(), 1):
            if DUMMY_MARK in line.lower():
                continue
            if token.search(line) or fernet.search(line) or assign.search(line):
                offenders.append(f"{_rel(path)}:{number}: {line.strip()[:60]}")
    assert not offenders, "\n".join(offenders)


def test_print_only_in_entrypoints_and_scripts() -> None:
    """الإخراج للمشغّل بـprint محصور في نقاط الدخول؛ الباقي يمرّ عبر logging."""
    offenders = []
    for path in _files():
        if _rel(path).startswith(PRINT_ALLOWED):
            continue
        tree, _ = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                offenders.append(f"{_rel(path)}:{node.lineno}")
    assert not offenders, "\n".join(offenders)


#: تعابير f-string مسموحة داخل SQL، كلٌّ منها روجع يدوياً: قيمته من قوائم/ثوابت في الكود لا من المستخدم
REVIEWED_SQL_EXPRESSIONS = {
    "int(self._busy_timeout_ms)",   # عدد صحيح من الإعداد (PRAGMA لا يقبل معاملات)
    "id_column",                    # اسم عمود ثابت يمرّره المستودع الداخلي
    "column",                       # يُختار من قاموس/شرط ثابت (sent_count … أو is_read_by_*)
    "self._CALL_SELECT",            # ثابت صنف
}
#: أنماط مسموحة بالاسم (قوائم علامات ? وشروط وأعمدة تُبنى من الكود)
SAFE_SQL_NAME = re.compile(r"(marks|placeholders|where|clause|columns|assignments|set_sql|order|conditions|table|filters)", re.I)


def test_sql_fstrings_never_interpolate_user_values() -> None:
    """f-string داخل استدعاء SQL لا يُدخل إلا تعابير روجعت يدوياً (قيم المستخدم عبر معاملات ? فقط)."""
    sql_methods = {"execute", "fetchone", "fetchall", "fetchval", "executemany", "scalar"}
    offenders = []
    for path in _files():
        tree, _ = _parse(path)
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in sql_methods
                and node.args
                and isinstance(node.args[0], ast.JoinedStr)
            ):
                continue
            for part in node.args[0].values:
                if not isinstance(part, ast.FormattedValue):
                    continue
                expr = ast.unparse(part.value)
                reviewed = expr in REVIEWED_SQL_EXPRESSIONS or SAFE_SQL_NAME.search(expr) or ".join(" in expr
                if not reviewed:
                    offenders.append(f"{_rel(path)}:{node.lineno} {{{expr}}}")
    assert not offenders, "قيمة غير مُراجَعة داخل SQL:\n" + "\n".join(offenders)
