"""
المرحلة 12 — اختبارات الإصدار النهائي: اتساق الإصدار والوثائق والاعتماديات وملف البيئة.

الفكرة: كل ما يقرؤه المشغّل (README، RUNBOOK، .env.example، requirements، الوثائق المولَّدة) يجب ألا ينحرف
عن الكود. أي انحراف يُفشل الاختبار بدل أن يُكتشف على سيرفر الإنتاج.
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import re
import sys
from pathlib import Path

import pytest

from config import BASE_DIR
from core.constants import APP_VERSION
from core.permissions import PERMISSIONS
from scripts import gen_reference_docs

DOCS = BASE_DIR / "docs"
README = BASE_DIR / "README.md"
RUNBOOK = DOCS / "RUNBOOK.md"

#: اسم الوحدة عند الاستيراد ⇒ اسم الحزمة في requirements
IMPORT_TO_PACKAGE = {
    "telegram": "python-telegram-bot",
    "aiosqlite": "aiosqlite",
    "cryptography": "cryptography",
    "httpx": "httpx",
    "dotenv": "python-dotenv",
}
PRODUCTION_DIRS = ("core", "database", "handlers", "integrations", "jobs", "keyboards", "middlewares",
                   "scripts", "services", "texts", "utils")
LOCAL_TOP_LEVEL = {*PRODUCTION_DIRS, "config", "main", "tests"}


def _requirements(path: Path) -> dict[str, str]:
    """قراءة ملف requirements ⇒ {اسم الحزمة بحروف صغيرة: الإصدار المثبَّت}."""
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?==([^\s;]+)$", line)
        assert match, f"سطر غير مثبَّت بـ== في requirements: {raw!r}"
        result[match.group(1).lower()] = match.group(3)
    return result


def test_version_is_one_point_zero_and_documented() -> None:
    """الإصدار 1.3.1 مذكور في README وRUNBOOK."""
    assert APP_VERSION == "1.3.1"
    assert APP_VERSION in README.read_text(encoding="utf-8")
    assert APP_VERSION in RUNBOOK.read_text(encoding="utf-8")


def test_generated_docs_match_the_code() -> None:
    """docs/SETTINGS.md وPERMISSIONS.md مطابقان تماماً لما يولّده الكود الآن (وإلا شغّل gen_reference_docs)."""
    for path, expected in gen_reference_docs.render_all().items():
        assert path.exists(), f"{path.name} غير موجود — شغّل: python -m scripts.gen_reference_docs"
        assert path.read_text(encoding="utf-8") == expected, (
            f"{path.name} قديم عن الكود — شغّل: python -m scripts.gen_reference_docs"
        )


def test_env_example_matches_config_variables() -> None:
    """مفاتيح .env.example = كل متغيرات البيئة التي يقرؤها config.py، والأسرار فارغة."""
    source = (BASE_DIR / "config.py").read_text(encoding="utf-8")
    used = set(re.findall(r'_get_\w+\(\s*"([A-Z][A-Z0-9_]+)"', source))
    assert {"BOT_TOKEN", "SUPER_ADMIN_IDS", "ENCRYPTION_KEY"} <= used, "فشل استخراج متغيرات config.py"
    example: dict[str, str] = {}
    for raw in (BASE_DIR / ".env.example").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            example[key.strip()] = value.strip()
    assert set(example) == used, f"فرق: ناقص في .env.example={used - set(example)} · زائد={set(example) - used}"
    for secret in ("BOT_TOKEN", "ENCRYPTION_KEY"):
        assert example[secret] == "", f"{secret} يجب أن يكون فارغاً في .env.example"


def test_every_third_party_import_is_pinned_in_requirements() -> None:
    """كل مكتبة طرف ثالث مستوردة في كود الإنتاج مدرجة ومثبَّتة في requirements.txt (والاختبارات في dev)."""
    pinned = _requirements(BASE_DIR / "requirements.txt")
    stdlib = set(sys.stdlib_module_names)
    found: set[str] = set()
    for folder in (*PRODUCTION_DIRS, "."):
        base = BASE_DIR if folder == "." else BASE_DIR / folder
        for file in (base.glob("*.py") if folder == "." else base.rglob("*.py")):
            tree = ast.parse(file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module.split(".")[0]]
                found.update(n for n in names if n not in stdlib and n not in LOCAL_TOP_LEVEL and n != "__future__")
    unknown = found - set(IMPORT_TO_PACKAGE)
    assert not unknown, f"مكتبات مستوردة غير معروفة للاختبار/requirements: {sorted(unknown)}"
    for module in found:
        assert IMPORT_TO_PACKAGE[module] in pinned, f"{module} مستورد لكن {IMPORT_TO_PACKAGE[module]} ليس في requirements.txt"
    dev = _requirements(BASE_DIR / "requirements-dev.txt")
    assert {"pytest", "pytest-asyncio"} <= set(dev)


def test_docs_reference_only_existing_scripts_files_and_links() -> None:
    """كل `python -m scripts.X` وكل رابط وثيقة نسبي في README/RUNBOOK يشير إلى ملف موجود."""
    for doc in (README, RUNBOOK):
        text = doc.read_text(encoding="utf-8")
        for name in set(re.findall(r"python -m scripts\.([a-z_]+)", text)):
            assert (BASE_DIR / "scripts" / f"{name}.py").exists(), f"{doc.name} يذكر scripts.{name} وهو غير موجود"
        for target in re.findall(r"\]\(((?!https?:)[^)#]+)\)", text):
            assert (doc.parent / target).exists(), f"{doc.name}: رابط مكسور → {target}"


def test_readme_numbers_match_reality() -> None:
    """الأرقام المذكورة في README (صلاحيات، إعدادات، مهام، خدمات، معالجات) تطابق الكود."""
    from handlers.registry import build_handlers
    from jobs import JOB_LABELS
    from services import ServiceContainer

    text = README.read_text(encoding="utf-8")
    services = len(dataclasses.fields(ServiceContainer)) - 2          # ناقص db وrepos
    for number, label in (
        (len(PERMISSIONS), "صلاحية"),
        (len(asyncio.run(gen_reference_docs._settings_rows())), "إعداداً"),   # المزروعة فعلاً في القاعدة
        (len(JOB_LABELS), "مهمة"),
        (services, "خدمة"),
    ):
        assert f"{number} {label}" in text or f"({number} {label}" in text, f"README: لا يذكر «{number} {label}»"
    assert len(build_handlers()) > 100


@pytest.mark.parametrize("phase", range(0, 12))
def test_phase_reports_exist(phase: int) -> None:
    """تقارير المراحل السابقة موجودة (تقرير م12 يُسلَّم مع الإصدار)."""
    name = "PHASE0_DESIGN.md" if phase == 0 else f"PHASE{phase}_REPORT.md"
    assert (DOCS / name).exists()


def test_no_secrets_or_runtime_dirs_shipped() -> None:
    """لا .env حقيقي ولا قاعدة/نسخ/لوق داخل شجرة المشروع المسلَّمة."""
    assert not (BASE_DIR / ".env").exists()
    assert not (BASE_DIR / "data").exists() and not (BASE_DIR / "backups").exists()
