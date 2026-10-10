"""
عرض حيّ للدورة الكاملة — المرحلة 2 (قبل بناء واجهة تيليجرام في المرحلة 3).

الغرض: أن ترى بعينك أن منطق العمل يعمل فعلاً من البداية للنهاية:
    تسجيل → تصفح → طلب → شحن → اعتماد → خصم → إرسال للمزود → متابعة آلية
    → إكمال → إشعار → سجل → إحصائيات
ثم المسار البديل: فشل المزود → استرجاع آمن → حركة مالية → إشعار المستخدم والأدمن.

⚠️ تنبيهات مهمة حتى لا يُفهم هذا العرض خطأً:
    • يعمل على قاعدة بيانات **مؤقتة منفصلة** (افتراضياً `data/demo_cycle.db`)
      تُحذف وتُعاد بناؤها عند كل تشغيل — لا يمس بيانات التشغيل إطلاقاً.
    • المزود هنا هو `MockProviderClient` (مزود وهمي محلي): **لا اتصال بأي شبكة
      ولا إنفاق أي مال حقيقي**. الأرقام أدناه حقيقية داخل قاعدة البيانات المؤقتة فقط.
    • الرسائل التي تُطبع بوصفها «إشعارات» هي ما كان البوت سيرسله لتيليجرام فعلاً،
      وهي مقروءة من جدول `notifications` لا مكتوبة يدوياً.

طريقة التشغيل (من داخل مجلد المشروع smm_bot):
    python -m scripts.demo_cycle
    python -m scripts.demo_cycle --keep     # إبقاء قاعدة البيانات المؤقتة بعد الانتهاء
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:                      # تشغيل مباشر بلا تثبيت الحزمة
    sys.path.insert(0, str(ROOT))

from core.enums import OrderStatus                                  # noqa: E402
from core.exceptions import InsufficientBalanceError                # noqa: E402
from core.exceptions import ProviderPermanentError                  # noqa: E402
from core.money import format_units                                 # noqa: E402
from database.database import Database                              # noqa: E402
from database.migrator import Migrator                              # noqa: E402
from database.repositories import Repositories                      # noqa: E402
from integrations.providers import registry                         # noqa: E402
from integrations.providers.mock import MockProviderClient          # noqa: E402
from services import ServiceContainer, build_services               # noqa: E402
from utils.datetime_utils import iso_plus_seconds                   # noqa: E402
from utils.logging_setup import setup_logging                       # noqa: E402
from utils.security import SecretBox, generate_encryption_key       # noqa: E402

LINE = "─" * 62


def step(number: str, title: str) -> None:
    """طباعة عنوان خطوة من الدورة."""
    print(f"\n{LINE}\n▶ {number}  {title}\n{LINE}")


def info(label: str, value: object) -> None:
    """طباعة سطر معلومة بمحاذاة ثابتة."""
    print(f"   • {label:<28} {value}")


def money(units: int) -> str:
    """عرض مبلغ بالنقاط الصحيحة بصيغة قابلة للقراءة."""
    return format_units(units, decimals=2)


class ConsoleSender:
    """بديل واجهة تيليجرام: يطبع الرسائل بدل إرسالها (لا شبكة في هذا العرض)."""

    def __init__(self, names: dict[int, str]) -> None:
        """تهيئة المرسل بخريطة معرفات تيليجرام إلى أسماء للعرض."""
        self.names = names
        self.count = 0

    async def __call__(self, telegram_id: int, title: str, message: str) -> int:
        """طباعة الرسالة كما كانت ستصل للمستخدم في تيليجرام."""
        self.count += 1
        who = self.names.get(telegram_id, str(telegram_id))
        first_line = message.strip().splitlines()[0] if message.strip() else ""
        print(f"   📨 إلى {who}: {title} — {first_line}")
        return self.count


async def build_environment(db_path: Path) -> tuple[Database, Repositories, ServiceContainer, dict]:
    """
    تجهيز قاعدة بيانات مؤقتة كاملة: ترحيلات + أدمن + مزود وهمي + خدمة + طريقة دفع.

    المخرجات: (قاعدة البيانات، المستودعات، حاوية الخدمات، قاموس الكائنات المُنشأة).
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    db = Database(db_path, read_pool_size=2)
    await db.connect()
    applied = await Migrator(db).apply_all()
    repos = Repositories(db)
    secret_box = SecretBox(generate_encryption_key())          # مفتاح مؤقت لهذا التشغيل فقط
    services = build_services(db, repos, secret_box=secret_box, settings_ttl_seconds=0)

    async with db.transaction() as tx:
        admin = await repos.users.create(
            tx, telegram_id=900900900, username="demo_admin", first_name="أدمن العرض",
            role="super_admin",
        )
        provider = await repos.providers.create(
            tx,
            currency="YER",   # عملة النظام الافتراضية: لا تحويل مطلوب
            name="MockPanel",
            api_url="https://mock.invalid/api/v2",
            api_key_enc=secret_box.encrypt("demo-key-1234567890"),
            api_key_hint="7890",
            api_type="mock",
        )
        categories = await repos.categories.list_all()
        service = await repos.services.create(
            tx,
            category_id=categories[0].id,
            provider_id=provider.id,
            provider_service_id="555",
            name="متابعين انستغرام (عرض تجريبي)",
            price_per_1000_units=10_000,          # 1.00 لكل ألف
            provider_price_per_1000_units=6_000,  # تكلفتنا من المزود
            min_quantity=100,
            max_quantity=100_000,
        )
        method = await repos.payment_methods.create(
            tx, code="demo_transfer", name_ar="حوالة بنكية (عرض)",
            instructions_ar="حوّل ثم أرسل رقم العملية",
        )

    info("ملف قاعدة البيانات", db_path)
    info("ترحيلات مطبَّقة", len(applied))
    info("أدمن العرض", f"{admin.display_name} (tg={admin.telegram_id})")
    info("المزود", f"{provider.name} — نوع {provider.api_type} — مفتاح ****{provider.api_key_hint}")
    info("الخدمة", f"{service.name} بسعر {money(service.price_per_1000_units)} لكل 1000")
    info("طريقة الدفع", method.name_ar)
    return db, repos, services, {"admin": admin, "provider": provider, "service": service, "method": method}


async def follow_until_final(services: ServiceContainer, repos: Repositories, order_id: int) -> None:
    """تشغيل حلقة المتابعة الآلية (كما يفعل JobQueue) حتى تستقر حالة الطلب."""
    for round_number in range(1, 9):
        order = await repos.orders.get(order_id)
        if order is None or order.status in {
            OrderStatus.COMPLETED, OrderStatus.PARTIAL, OrderStatus.REFUNDED, OrderStatus.CANCELED
        }:
            return
        async with repos.db.transaction() as tx:      # تقديم موعد الفحص بدل الانتظار الحقيقي
            await repos.orders.update_fields(tx, order_id, next_check_at=iso_plus_seconds(-5))
        report = await services.orders.process_due_orders()
        current = await repos.orders.get(order_id)
        assert current is not None
        info(
            f"دورة متابعة {round_number}",
            f"الحالة: {current.status} | منفَّذ: {current.delivered_quantity or 0}"
            f" | متبقٍ: {current.remains if current.remains is not None else '—'}"
            f" | فحوصات: {report.claimed}",
        )


async def happy_path(services: ServiceContainer, repos: Repositories, env: dict) -> None:
    """تنفيذ الدورة الكاملة الناجحة وطباعة كل خطوة."""
    admin, service, method = env["admin"], env["service"], env["method"]
    sender = ConsoleSender({admin.telegram_id: "الأدمن"})

    step("1/11", "التسجيل — أول تفاعل مع البوت")
    customer, created = await services.users.get_or_create(
        telegram_id=111222333, username="demo_client", first_name="عميل العرض"
    )
    sender.names[customer.telegram_id] = "العميل"
    info("الحساب", f"{customer.display_name} (tg={customer.telegram_id})")
    info("أُنشئ الآن؟", "نعم" if created else "كان موجوداً")
    info("الرصيد الابتدائي", money(customer.balance_units))

    step("2/11", "التصفح — التصنيفات والخدمات والتسعيرة")
    categories = await services.catalog.categories()
    info("تصنيفات بها خدمات", ", ".join(category.name_ar for category in categories))
    page = await services.catalog.services_page(categories[0].id)
    info("خدمات الصفحة الأولى", f"{page.total_items} خدمة")
    chosen = await services.catalog.get_available_service(service.id)
    quote = await services.catalog.quote(chosen, 1000)
    info("التسعيرة لـ1000 وحدة", quote.cost_text)

    step("3/11", "محاولة الطلب بلا رصيد — يجب أن تُرفض بلا أي أثر")
    try:
        await services.orders.create_order(
            customer, service_id=chosen.id, link="https://instagram.com/p/demo", quantity=1000
        )
    except InsufficientBalanceError as exc:
        info("الرفض المتوقع", exc.user_message)
    info("عدد طلبات العميل", await repos.orders.count_by_user(customer.id))

    step("4/11", "الشحن — العميل يرسل إثبات التحويل")
    payment = await services.payments.create_payment(
        customer, method_id=method.id, raw_amount="5",
        transaction_reference="DEMO-TRX-001", proof_file_id="demo-photo", proof_file_type="photo",
    )
    info("رقم طلب الشحن", payment.id)
    info("المبلغ المطلوب", money(payment.amount_units))
    info("الحالة", payment.status)
    info("الرصيد الآن", money(await services.wallet.balance_units(customer.id)))

    step("5/11", "الاعتماد — الأدمن يراجع ويعتمد")
    pending = await services.payments.pending(admin)
    info("طلبات بانتظار المراجعة", len(pending))
    transaction = await services.payments.approve(admin, payment.id)
    info("نوع الحركة المالية", transaction.type)
    info("مرجع الحركة", transaction.reference)
    info("الرصيد بعد الاعتماد", money(await services.wallet.balance_units(customer.id)))

    step("6/11", "الطلب — الخصم يتم داخل نفس معاملة الإنشاء")
    order = await services.orders.create_order(
        customer, service_id=chosen.id, link="https://instagram.com/p/demo", quantity=1000
    )
    info("رقم الطلب", order.public_code)
    info("التكلفة المخصومة", money(order.cost_units))
    info("الحالة", order.status)
    info("الرصيد بعد الخصم", money(await services.wallet.balance_units(customer.id)))

    step("7/11", "الإرسال للمزود — مهمة الخلفية تلتقط الطلب")
    batch = await services.orders.process_pending_orders()
    info("طلبات التُقطت", batch.claimed)
    info("أُرسلت بنجاح", batch.succeeded)
    submitted = await repos.orders.get(order.id)
    assert submitted is not None
    info("رقم الطلب لدى المزود", submitted.provider_order_id)
    info("تكلفتنا من المزود", money(submitted.provider_cost_units or 0))

    step("8/11", "المتابعة الآلية حتى الإكمال")
    await follow_until_final(services, repos, order.id)
    final = await repos.orders.get(order.id)
    assert final is not None
    info("الحالة النهائية", final.status)
    info("الكمية المنفَّذة", final.delivered_quantity)

    step("9/11", "الإشعارات — ما كان سيصل إلى تيليجرام")
    report = await services.notifications.dispatch_pending(sender, limit=50)
    info("أُرسل", report.sent)
    info("تخطّي (حظر البوت)", report.skipped)
    info("المتبقي في الطابور", await services.notifications.queued_count())

    step("10/11", "السجلات — حركات مالية وتدقيق وتاريخ حالات")
    for movement in await repos.transactions.list_by_user(customer.id, limit=5):
        info(movement.type, f"{money(movement.amount_units)} | الرصيد بعدها {money(movement.balance_after_units)}")
    ledger = await services.wallet.verify_ledger(customer.id)
    info("مطابقة الرصيد مع الدفتر", "متوازن ✅" if ledger.is_balanced else "اختلال ❌")
    history = await repos.orders.history(order.id)
    info("مسار حالات الطلب", " ← ".join(row.to_status for row in history))
    logs = await services.audit.by_target("payment", payment.id)
    info("سجل التدقيق للاعتماد", ", ".join(f"{log.action} بواسطة {log.admin_id}" for log in logs))

    step("11/11", "الإحصائيات — أرقام مقروءة من قاعدة البيانات")
    dashboard = await services.stats.dashboard(admin)
    info("طلبات اليوم", dashboard.orders_today)
    info("مبيعات اليوم", money(dashboard.revenue_today_units))
    financial = await services.stats.financial_report(admin, days=1)
    info("إيداعات", money(financial.deposits_units))
    info("مبيعات", money(financial.revenue_units))
    info("تكلفة المزود", money(financial.provider_cost_units))
    info("الربح", money(financial.profit_units) if financial.profit_known else "غير محسوب")
    operations = await services.stats.operations_report(admin, days=1)
    info("نسبة النجاح", f"{operations.success_rate}%")

    env["customer"] = customer
    env["sender"] = sender


async def failure_path(services: ServiceContainer, repos: Repositories, env: dict, client: MockProviderClient) -> None:
    """تنفيذ المسار البديل: رفض المزود للطلب ثم الاسترجاع الآمن."""
    customer, sender = env["customer"], env["sender"]
    service = env["service"]

    step("بديل 1/4", "طلب جديد — لكن المزود سيرفضه هذه المرة")
    await services.settings.set("duplicate_order_window_minutes", 0)
    client.always_fail_add = ProviderPermanentError("الخدمة غير متاحة لدى المزود")
    before = await services.wallet.balance_units(customer.id)
    order = await services.orders.create_order(
        customer, service_id=service.id, link="https://instagram.com/p/fail-demo", quantity=1000
    )
    info("رقم الطلب", order.public_code)
    info("الرصيد قبل", money(before))
    info("الرصيد بعد الخصم", money(await services.wallet.balance_units(customer.id)))

    step("بديل 2/4", "المزود يرفض — فشل + استرجاع كامل في معاملة واحدة")
    batch = await services.orders.process_pending_orders()
    info("فشل", batch.failed)
    failed = await repos.orders.get(order.id)
    assert failed is not None
    info("الحالة النهائية", failed.status)
    info("المبلغ المسترجَع", money(failed.refund_amount_units))
    info("سبب الفشل", failed.last_error)

    step("بديل 3/4", "الحركة المالية والرصيد")
    movements = await repos.transactions.list_by_user(customer.id, limit=2)
    for movement in movements:
        info(movement.type, f"{money(movement.amount_units)} | مرجع {movement.reference}")
    info("الرصيد بعد الاسترجاع", money(await services.wallet.balance_units(customer.id)))
    info("المال المفقود", money(before - await services.wallet.balance_units(customer.id)))
    ledger = await services.wallet.verify_ledger(customer.id)
    info("مطابقة الدفتر", "متوازن ✅" if ledger.is_balanced else "اختلال ❌")

    step("بديل 4/4", "إشعار العميل والأدمن + منع إعادة الإرسال")
    await services.notifications.dispatch_pending(sender, limit=50)
    again = await services.orders.process_pending_orders()
    info("محاولات إرسال جديدة للطلب الفاشل", again.claimed)
    errors = await repos.error_logs.list_recent(limit=3)
    info("أحدث خطأ مسجَّل", errors[0]["message"] if errors else "—")


async def run(keep: bool) -> int:
    """تشغيل العرض كاملاً وإرجاع كود الخروج."""
    db_path = ROOT / "data" / "demo_cycle.db"
    # السجلات إلى الملف فقط حتى لا تتداخل أسطر اللوق مع خطوات العرض
    setup_logging(ROOT / "logs" / "demo_cycle.log", "INFO", console=False)
    print("\n🧪 عرض الدورة الكاملة — المرحلة 2 (مزود وهمي، قاعدة بيانات مؤقتة، بلا شبكة)")
    shared_client = MockProviderClient()
    registry.enable_dev_types(True)                                    # العرض التجريبي وحده يسمح بالمزود الوهمي
    registry.register_client("mock", lambda **_kwargs: shared_client)   # عميل واحد يحتفظ بحالته

    db, repos, services, env = await build_environment(db_path)
    try:
        await happy_path(services, repos, env)
        await failure_path(services, repos, env, shared_client)
        print(f"\n{LINE}\n✅ انتهى العرض: الدورة الكاملة والمسار البديل نُفِّذا دون فقدان أي مبلغ.\n{LINE}")
    finally:
        await db.close()
        registry.register_client("mock", MockProviderClient)
        if not keep and db_path.exists():
            db_path.unlink()
            print(f"🧹 حُذفت قاعدة البيانات المؤقتة: {db_path}")
        elif keep:
            print(f"💾 أُبقيت قاعدة البيانات المؤقتة: {db_path}")
    return 0


def main() -> int:
    """نقطة الدخول: قراءة الخيارات ثم تشغيل العرض."""
    parser = argparse.ArgumentParser(description="عرض حيّ للدورة الكاملة (المرحلة 2)")
    parser.add_argument("--keep", action="store_true", help="إبقاء قاعدة البيانات المؤقتة بعد الانتهاء")
    args = parser.parse_args()
    return asyncio.run(run(args.keep))


if __name__ == "__main__":
    raise SystemExit(main())
