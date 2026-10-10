"""
يولّد `docs/ADMIN_UI_PREVIEW.md` من الكود الفعلي لشاشات الأدمن (معاينة النص واللوحة كما يراها المشرف).

أداة تطوير: تبني قاعدة مؤقتة وبيانات عيّنة (مزود Mock وخدمة وطلب) وتشغّل كل شاشة عبر معالجها الحقيقي على `FakeBot`
(من `tests/`)، ثم تكتب النص ولوحة الأزرار بجانب نتيجة فحص التخطيط. لا شبكة ولا مزود حقيقي ولا أسرار.

    python -m scripts.gen_admin_ui_preview
"""

from __future__ import annotations

import asyncio
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.constants import APP_VERSION                                    # noqa: E402
from database.database import Database                                    # noqa: E402
from database.migrator import Migrator                                    # noqa: E402
from database.repositories import Repositories                            # noqa: E402
from integrations.providers import registry                              # noqa: E402
from services import build_services                                       # noqa: E402
from tests.admin_ui_samples import capture_admin_screens                  # noqa: E402
from tests.integration.test_user_interface import load_user               # noqa: E402
from tests.telegram_fakes import FakeBot, FakeContext                     # noqa: E402
from tests.layout_rules import layout_violations                          # noqa: E402
from utils.security import SecretBox, generate_encryption_key             # noqa: E402

OUT = ROOT / "docs" / "ADMIN_UI_PREVIEW.md"


def to_markdown_text(html: str) -> str:
    """HTML تيليجرام ⇒ نص مقروء (`**` للعريض و`` ` `` للثابت)."""
    text = re.sub(r"</?b>", "**", html)
    text = re.sub(r"</?code>", "`", text)
    text = re.sub(r"</?i>", "_", text)
    return re.sub(r"<[^>]+>", "", text)


async def build() -> str:
    """بناء بيانات العيّنة وتجميع المعاينة."""
    registry.enable_dev_types(True)                                    # نوع Mock للمعاينة فقط (يُعطَّل في النهاية)
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "preview.db", read_pool_size=2)
        await db.connect()
        try:
            await Migrator(db).apply_all()
            repos = Repositories(db)
            box = SecretBox(generate_encryption_key())
            services = build_services(db, repos, secret_box=box, settings_ttl_seconds=0)
            async with db.transaction() as tx:
                admin = await repos.users.create(tx, telegram_id=777777777, username="root", first_name="Root", role="super_admin")
                customer = await repos.users.create(tx, telegram_id=100200300, username="tester", first_name="Tester")
                provider = await repos.providers.create(
                    tx, currency="YER", name="MockProvider", api_url="https://mock.invalid/api/v2",
                    api_key_enc=box.encrypt("preview-key-000000"), api_key_hint="0000", api_type="mock",
                )
                category = (await repos.categories.list_all())[0]
                service = await repos.services.create(
                    tx, category_id=category.id, provider_id=provider.id, provider_service_id="555",
                    name="متابعين انستغرام (Mock)", price_per_1000_units=10_000, provider_price_per_1000_units=6_000,
                    min_quantity=100, max_quantity=100_000,
                )
            await services.wallet.adjust_balance(target=customer, amount_units=1_000_000, admin=admin, reason="عيّنة", credit=True)
            order = await services.orders.create_order(customer, service_id=service.id, link="https://instagram.com/p/sample", quantity=1000)
            bot = FakeBot()
            context = FakeContext(bot, services)
            await load_user(bot, context, admin)
            shots = await capture_admin_screens(bot, context, admin=admin, order=order, provider=provider, service=service, target_user=customer)
        finally:
            registry.enable_dev_types(False)
            await db.close()

    lines = [
        f"# معاينة شاشات لوحة التحكم (v{APP_VERSION})",
        "> مولَّدة آلياً من الكود الفعلي بـ `python -m scripts.gen_admin_ui_preview` على بيانات عيّنة؛ لا تُحرَّر يدوياً.",
        "> `**نص**` = عريض و`` `نص` `` = خط ثابت. الأزرار: كل سطر `[ ]` = صف في لوحة المفاتيح.",
        "",
    ]
    for name, message in shots.items():
        rows = message.markup.inline_keyboard if message.markup else []
        problems = layout_violations(rows)
        lines += [f"## {name}", "", "```text", to_markdown_text(message.text), "```", ""]
        if rows:
            lines += ["```text"] + ["  ".join(f"[{b.text}]" for b in row) for row in rows] + ["```", ""]
        lines += [("✅ التخطيط مطابق للقواعد" if not problems else "⚠️ " + "؛ ".join(problems)), ""]
    return "\n".join(lines)


def main() -> int:
    """نقطة الدخول."""
    OUT.write_text(asyncio.run(build()), encoding="utf-8")
    print(f"✍️ كُتب {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
