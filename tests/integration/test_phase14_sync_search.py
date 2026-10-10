"""
المرحلة الثانية (v1.0.1) — بند 17 (مزامنة الخدمات) وبند 18 (بحث الأدمن مع آلاف الخدمات).

    مزامنة: خدمات جديدة · تغيّر التكلفة · تغيّر الحدود · اختفاء/عودة · حماية العطل · سعر البيع ثابت ·
            تاريخ الطلبات سليم · كتالوج >1000 خدمة · ذرّية المعاملة · نص التقرير ضمن حد تيليجرام.
    بحث:    معرّف الخدمة · معرّف المزود · اسم · قسم · مزود · عدة كلمات · محارف LIKE الخاصة · ترقيم · أداء 10 آلاف.
"""

from __future__ import annotations

import time

import pytest

from core.enums import OrderStatus
from core.exceptions import PermissionDeniedError, ValidationError
from handlers.admin import catalog as admin_catalog
from handlers.admin import providers as admin_providers
from integrations.providers.base import ProviderServiceItem
from keyboards.callback_data import NS_ADM_CAT, pack
from tests.integration.test_user_interface import bot, context, load_user, press, write  # noqa: F401,F811
from utils.datetime_utils import iso_plus_seconds

pytestmark = pytest.mark.asyncio


def _item(psid, *, rate=6_000, lo=100, hi=100_000, name=None, service_type="default"):
    """عنصر من قائمة المزود."""
    return ProviderServiceItem(
        provider_service_id=str(psid),
        name=name or f"Provider service {psid}",
        rate_per_1000_units=rate,
        min_quantity=lo,
        max_quantity=hi,
        service_type=service_type,
    )


async def _bulk_services(db, repos, provider, count, *, start=1000, name="Bulk service"):
    """إدراج عدد كبير من الخدمات دفعة واحدة (بدل استيراد كل خدمة عبر الخدمة)."""
    category = (await repos.categories.list_all())[0]
    stamp = "2026-01-01T00:00:00.000Z"
    async with db.transaction() as tx:
        for index in range(count):
            await tx.execute(
                "INSERT INTO services (category_id, provider_id, provider_service_id, name, price_per_1000_units,"
                " provider_price_per_1000_units, min_quantity, max_quantity, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (category.id, provider.id, str(start + index), f"{name} {start + index}", 10_000, 6_000, 100, 100_000, stamp, stamp),
            )


# ============================== مزامنة (17) ============================== #


async def test_sync_updates_cost_and_limits_but_never_the_selling_price(services, repos, super_admin, mock_provider, mock_service) -> None:
    """تغيّر التكلفة والحدود لدى المزود ⇒ يتحدثان؛ سعر البيع كما هو؛ التقرير يحمل القديم والجديد والهامش."""
    report = await services.catalog.sync_provider_services(
        super_admin, provider_id=mock_provider.id, items=[_item(555, rate=7_500, lo=50, hi=20_000)]
    )
    after = await repos.services.get(mock_service.id)
    assert after.price_per_1000_units == mock_service.price_per_1000_units == 10_000      # سعر البيع ثابت
    assert after.provider_price_per_1000_units == 7_500
    assert (after.min_quantity, after.max_quantity) == (50, 20_000)
    assert report.updated == 1 and report.unchanged == 0
    change = report.cost_changes[0]
    assert (change.old_cost_units, change.new_cost_units, change.new_margin_units) == (6_000, 7_500, 2_500)
    assert [s.id for s in report.limit_changes] == [mock_service.id]
    row = await repos.settings.db.fetchone("SELECT before_json, after_json FROM audit_logs WHERE action = 'services.sync'")
    assert str(mock_service.id) in row["before_json"] and "7500" in row["after_json"]


async def test_sync_with_identical_data_changes_nothing_and_writes_no_audit(services, repos, super_admin, mock_provider, mock_service) -> None:
    """مزامنة بلا فروق ⇒ unchanged=1 ولا سجل تدقيق ولا كتابة."""
    report = await services.catalog.sync_provider_services(
        super_admin, provider_id=mock_provider.id, items=[_item(555, rate=6_000, lo=100, hi=100_000)]
    )
    assert (report.updated, report.unchanged, report.missing, report.new_items) == (0, 1, [], [])
    row = await repos.settings.db.fetchone("SELECT COUNT(*) AS n FROM audit_logs WHERE action = 'services.sync'")
    assert row["n"] == 0


async def test_sync_reports_new_provider_services_without_importing_them(services, repos, super_admin, mock_provider, mock_service) -> None:
    """الجديد لدى المزود يُبلَّغ به (المدعوم فقط) ولا يُستورد آلياً."""
    items = [_item(555), _item(900, name="New followers"), _item(901, name="Custom comments", service_type="custom_comments")]
    report = await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=items)
    assert [i.provider_service_id for i in report.new_items] == ["900"]
    assert await repos.services.find_by_provider_service(mock_provider.id, "900") is None


async def test_missing_service_is_disabled_not_deleted_and_orders_history_survives(
    services, repos, db, user, super_admin, mock_provider, mock_service, mock_client
) -> None:
    """اختفاء الخدمة ⇒ تعطيل بعلامة (لا حذف)؛ الطلب القائم يكمل دورته والتاريخ والسعر كما هي."""
    await services.wallet.adjust_balance(target=user, amount_units=100_000, admin=super_admin, reason="رصيد", credit=True)
    order = await services.orders.create_order(user, service_id=mock_service.id, link="https://instagram.com/keep", quantity=1000)
    before = await repos.orders.get(order.id)

    report = await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=[_item(777)])
    assert [s.id for s in report.disabled_missing] == [mock_service.id]
    gone = await repos.services.get(mock_service.id)
    assert gone.is_active == 0 and gone.disabled_by_sync == 1 and gone.provider_missing_at
    assert gone.price_per_1000_units == 10_000
    assert await repos.services.get_available(mock_service.id) is None            # لا يُباع للعملاء

    same = await repos.orders.get(order.id)                                      # الطلب لم يُمسّ
    assert (same.status, same.cost_units, same.service_id, same.quantity) == (before.status, before.cost_units, before.service_id, before.quantity)
    await services.orders.process_pending_orders()                                # ويكمل دورته
    submitted = await repos.orders.get(order.id)
    assert submitted.status == OrderStatus.SUBMITTED
    mock_client.advance(submitted.provider_order_id, to="Completed")
    async with db.transaction() as tx:
        await tx.execute("UPDATE orders SET next_check_at = ? WHERE id = ?", (iso_plus_seconds(-30), order.id))
    await services.orders.process_due_orders()
    assert (await repos.orders.get(order.id)).status == OrderStatus.COMPLETED
    assert (await repos.services.get(mock_service.id)).is_archived == 0


async def test_service_that_reappears_is_restored_but_manual_disable_is_respected(services, repos, db, super_admin, mock_provider, mock_service) -> None:
    """عودة الخدمة تعيد تفعيلها تلقائياً فقط إن كانت المزامنة هي من عطّلها؛ التعطيل اليدوي يبقى."""
    await _bulk_services(db, repos, mock_provider, 1, start=2000, name="Manual")
    manual = await repos.services.find_by_provider_service(mock_provider.id, "2000")
    await services.catalog.set_service_active(super_admin, manual.id, False)       # تعطيل يدوي

    await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=[_item(9999)])
    assert (await repos.services.get(mock_service.id)).disabled_by_sync == 1
    assert (await repos.services.get(manual.id)).disabled_by_sync == 0              # اليدوي بلا علامة

    report = await services.catalog.sync_provider_services(
        super_admin, provider_id=mock_provider.id, items=[_item(555), _item(2000)]
    )
    assert [s.id for s in report.restored] == [mock_service.id]
    back = await repos.services.get(mock_service.id)
    assert back.is_active == 1 and back.disabled_by_sync == 0 and back.provider_missing_at is None
    assert (await repos.services.get(manual.id)).is_active == 0                     # بقي معطّلاً يدوياً


async def test_admin_manual_enable_overrides_sync_flag(services, repos, super_admin, mock_provider, mock_service) -> None:
    """إن فعّل الأدمن خدمة عطّلتها المزامنة ⇒ تُمسح العلامة (القرار البشري هو الأخير)."""
    await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=[_item(1)])
    await services.catalog.set_service_active(super_admin, mock_service.id, True)
    current = await repos.services.get(mock_service.id)
    assert current.is_active == 1 and current.disabled_by_sync == 0


async def test_empty_provider_list_is_treated_as_outage_not_deletion(services, repos, super_admin, mock_provider, mock_service) -> None:
    """قائمة فارغة من المزود ⇒ عطل: لا يُعطَّل شيء ويُعلَّم التقرير."""
    report = await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=[])
    assert report.missing_suspicious and report.disabled_missing == []
    assert (await repos.services.get(mock_service.id)).is_active == 1


async def test_mass_disappearance_is_treated_as_outage(services, repos, db, super_admin, mock_provider) -> None:
    """اختفاء أكثر من نصف 12 خدمة دفعة واحدة ⇒ عطل؛ واختفاء القليل ⇒ تعطيل عادي."""
    await _bulk_services(db, repos, mock_provider, 12)
    keep = [_item(1000 + i) for i in range(5)]
    report = await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=keep)
    assert report.missing_suspicious and len(report.missing) == 7 and report.disabled_missing == []

    keep = [_item(1000 + i) for i in range(10)]                                      # اختفاء خدمتين فقط
    report = await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=keep)
    assert not report.missing_suspicious and len(report.disabled_missing) == 2
    assert await repos.services.count_active() == 10


async def test_auto_disable_can_be_switched_off(services, repos, super_admin, mock_provider, mock_service) -> None:
    """مع إيقاف الإعداد: تُدرج المفقودة في التقرير فقط ولا تُعطَّل."""
    await services.settings.set("sync_auto_disable_missing", "false", admin_id=super_admin.id)
    report = await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=[_item(1)])
    assert [s.id for s in report.missing] == [mock_service.id] and report.disabled_missing == []
    assert (await repos.services.get(mock_service.id)).is_active == 1


async def test_type_change_to_unsupported_disables_without_touching_price(services, repos, super_admin, mock_provider, mock_service) -> None:
    """تغيّر النوع لدى المزود إلى غير default ⇒ تعطيل وعدم تحديث تكلفته."""
    report = await services.catalog.sync_provider_services(
        super_admin, provider_id=mock_provider.id, items=[_item(555, rate=9_999, service_type="custom_comments")]
    )
    assert [s.id for s in report.unsupported] == [mock_service.id]
    after = await repos.services.get(mock_service.id)
    assert after.is_active == 0 and after.provider_price_per_1000_units == 6_000


async def test_sync_handles_a_catalog_larger_than_1000_services(services, repos, db, super_admin, mock_provider) -> None:
    """كتالوج 1500 خدمة: كلها تُفحص وتُحدَّث (كان السقف الصامت 1000)، وبزمن معقول."""
    await _bulk_services(db, repos, mock_provider, 1500)
    items = [_item(1000 + i, rate=6_500) for i in range(1500)]
    started = time.perf_counter()
    report = await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=items)
    elapsed = time.perf_counter() - started
    assert report.checked == 1500 and report.updated == 1500 and len(report.cost_changes) == 1500
    assert report.missing == [] and elapsed < 15
    row = await db.fetchone("SELECT COUNT(*) AS n FROM services WHERE provider_price_per_1000_units = 6500")
    assert row["n"] == 1500
    assert len(await services.catalog.services_of_provider(super_admin, mock_provider.id)) == 1500


async def test_sync_is_atomic_when_a_write_fails_midway(services, repos, db, super_admin, mock_provider, monkeypatch) -> None:
    """فشل أثناء المزامنة ⇒ لا تحديث جزئي (معاملة واحدة)."""
    await _bulk_services(db, repos, mock_provider, 5)
    original = repos.services.update_fields
    calls = {"n": 0}

    async def flaky(tx, service_id, **fields):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("boom")
        return await original(tx, service_id, **fields)

    monkeypatch.setattr(repos.services, "update_fields", flaky)
    with pytest.raises(RuntimeError):
        await services.catalog.sync_provider_services(
            super_admin, provider_id=mock_provider.id, items=[_item(1000 + i, rate=8_000) for i in range(5)]
        )
    row = await db.fetchone("SELECT COUNT(*) AS n FROM services WHERE provider_price_per_1000_units = 8000")
    assert row["n"] == 0


async def test_sync_requires_the_sync_permission(services, user, mock_provider, mock_service) -> None:
    """مستخدم عادي لا يزامن."""
    with pytest.raises(PermissionDeniedError):
        await services.catalog.sync_provider_services(user, provider_id=mock_provider.id, items=[_item(555)])


async def test_negative_margin_after_sync_is_reported_for_that_provider_only(services, repos, super_admin, mock_provider, mock_service) -> None:
    """تكلفة صارت فوق سعر البيع ⇒ تُدرج في تحذير الهامش السالب (والسعر لا يُعدَّل)."""
    report = await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=[_item(555, rate=12_000)])
    assert [s.id for s in report.negative_margin] == [mock_service.id]
    assert (await repos.services.get(mock_service.id)).price_per_1000_units == 10_000


async def test_sync_report_text_stays_under_telegram_limit_and_shows_every_category(services, repos, db, super_admin, mock_provider) -> None:
    """مئات التغييرات ⇒ نص التقرير مقتطع ضمن 4096 حرفاً ويحوي الفئات (تكلفة/جديدة/معطّلة)."""
    await _bulk_services(db, repos, mock_provider, 300)
    items = [_item(1000 + i, rate=7_000) for i in range(280)] + [_item(5000 + i, name="X" * 60) for i in range(40)]
    report = await services.catalog.sync_provider_services(super_admin, provider_id=mock_provider.id, items=items)
    text = admin_providers.sync_report_text(mock_provider.name, report, "﷼")
    assert len(text) < 4096
    for needle in ("تغيّرت تكلفتها", "خدمات جديدة لدى المزود", "و275 أخرى", "جديدة لدى المزود (لم تُستورد): 40"):
        assert needle in text
    assert report.missing_suspicious is False and len(report.disabled_missing) == 20
    assert "عُطِّلت لاختفائها" in text


async def test_sync_button_end_to_end_through_the_handler(bot, context, super_admin, mock_provider, mock_service, mock_client) -> None:  # noqa: F811
    """زر «مزامنة الخدمات»: يجلب قائمة Mock (555/556) ويعرض التقرير بالجديد (556) دون استيراده."""
    await load_user(bot, context, super_admin)
    await press(bot, context, admin_providers.sync_provider, pack("pv", "sync", mock_provider.id), super_admin.telegram_id)
    text = " ".join(m.text or "" for m in bot.sent)
    assert "نتيجة المزامنة" in text and "جديدة لدى المزود (لم تُستورد): 1" in text and "556" in text


# ============================== بحث الأدمن (18) ============================== #


async def _seed_search(services, repos, db, super_admin, mock_provider):
    """مجموعة خدمات متنوعة: أسماء/أقسام/معرّفات مزود، مع معطّلة ومؤرشفة."""
    cat_ig = (await repos.categories.list_all())[0]
    async with db.transaction() as tx:
        cat_tt = await repos.categories.create(tx, name_ar="تيك توك", emoji="🎵")
    rows = [
        ("2511", "Instagram Followers Fast", cat_ig.id),
        ("2512", "Instagram Likes", cat_ig.id),
        ("3001", "TikTok Views 100%", cat_tt.id),
        ("3002", "TikTok_Likes", cat_tt.id),
    ]
    async with db.transaction() as tx:
        for psid, name, category_id in rows:
            await tx.execute(
                "INSERT INTO services (category_id, provider_id, provider_service_id, name, price_per_1000_units,"
                " min_quantity, max_quantity, created_at, updated_at) VALUES (?,?,?,?,10000,10,1000,'2026-01-01','2026-01-01')",
                (category_id, mock_provider.id, psid, name),
            )
    return {psid: await repos.services.find_by_provider_service(mock_provider.id, psid) for psid, *_ in rows}, cat_ig, cat_tt


async def test_admin_search_by_every_key(services, repos, db, super_admin, mock_provider) -> None:
    """معرّف الخدمة (مع #) · معرّف المزود · الاسم · القسم · المزود · عدة كلمات."""
    found, cat_ig, cat_tt = await _seed_search(services, repos, db, super_admin, mock_provider)

    async def ids(term):
        return [s.provider_service_id for s in (await services.catalog.admin_search_services(super_admin, term)).items]

    assert await ids(f"#{found['2511'].id}") == ["2511"]
    assert await ids(str(found["3001"].id)) == ["3001"]
    assert await ids("2512") == ["2512"]                                    # معرّف المزود
    assert await ids("followers") == ["2511"]                               # اسم (غير حساس لحالة الأحرف)
    assert await ids("تيك") == ["3001", "3002"]                             # اسم القسم
    assert await ids(mock_provider.name) == ["2511", "2512", "3001", "3002"]  # اسم المزود
    assert await ids("tiktok likes") == ["3002"]                            # كل الكلمات يجب أن تتحقق
    assert await ids("tiktok followers") == []                              # كلمة غائبة ⇒ لا نتيجة
    assert await ids("tiktok views") == ["3001"]
    assert await ids("instagram likes") == ["2512"]
    assert await ids("zzzz-nothing") == []


async def test_admin_search_numeric_prefers_exact_matches_and_falls_back_to_text(services, repos, db, super_admin, mock_provider) -> None:
    """رقم يطابق معرّف خدمة ⇒ المطابقة التامة وحدها؛ رقم بلا مطابقة تامة ⇒ بحث نصي (اسم يحوي الرقم)."""
    found, *_ = await _seed_search(services, repos, db, super_admin, mock_provider)
    target = found["2512"]
    async with db.transaction() as tx:
        await tx.execute("UPDATE services SET name = ? WHERE id = ?", (f"Package {target.id} deluxe", found["2511"].id))
    page = await services.catalog.admin_search_services(super_admin, str(target.id))
    assert [s.id for s in page.items] == [target.id]                          # لا يغرق بالنتائج الجزئية
    async with db.transaction() as tx:
        await tx.execute("UPDATE services SET name = 'Package 8888 deluxe' WHERE id = ?", (found["2511"].id,))
    fallback = await services.catalog.admin_search_services(super_admin, "8888")
    assert [s.id for s in fallback.items] == [found["2511"].id]


async def test_admin_search_includes_disabled_and_archived_and_treats_wildcards_literally(services, repos, db, super_admin, mock_provider) -> None:
    """الأدمن يرى المعطّلة والمؤرشفة، و`%`/`_` نص عادي لا أحرف بدل."""
    found, *_ = await _seed_search(services, repos, db, super_admin, mock_provider)
    await services.catalog.set_service_active(super_admin, found["2511"].id, False)
    async with db.transaction() as tx:
        await repos.services.archive(tx, found["2512"].id)
    page = await services.catalog.admin_search_services(super_admin, "instagram")
    assert {s.provider_service_id for s in page.items} == {"2511", "2512"}
    assert [s.provider_service_id for s in (await services.catalog.admin_search_services(super_admin, "100%")).items] == ["3001"]
    assert [s.provider_service_id for s in (await services.catalog.admin_search_services(super_admin, "tok_")).items] == ["3002"]
    assert (await services.catalog.admin_search_services(super_admin, "tok_v")).items == []   # _ ليس حرف بدل
    assert (await services.catalog.admin_search_services(super_admin, "%%")).items == []     # لا يطابق كل شيء
    assert (await services.catalog.admin_search_services(super_admin, "a_b")).items == []


async def test_admin_search_validation_permission_and_pagination(services, repos, db, user, super_admin, mock_provider) -> None:
    """نص قصير يُرفض، العادي ممنوع، والصفحات تعمل (والصفحة الزائدة تُقصّ لآخر صفحة)."""
    with pytest.raises(ValidationError):
        await services.catalog.admin_search_services(super_admin, "a")
    with pytest.raises(PermissionDeniedError):
        await services.catalog.admin_search_services(user, "followers")
    await _bulk_services(db, repos, mock_provider, 23)
    first = await services.catalog.admin_search_services(super_admin, "Bulk service", page=1, page_size=8)
    third = await services.catalog.admin_search_services(super_admin, "Bulk service", page=3, page_size=8)
    beyond = await services.catalog.admin_search_services(super_admin, "Bulk service", page=99, page_size=8)
    assert (first.total_items, first.total_pages, len(first.items)) == (23, 3, 8)
    assert len(third.items) == 7 and beyond.page == 3
    seen = {s.id for p in (first, await services.catalog.admin_search_services(super_admin, "Bulk service", page=2, page_size=8), third) for s in p.items}
    assert len(seen) == 23                                                   # لا تكرار ولا فقد بين الصفحات


async def test_admin_search_is_fast_with_ten_thousand_services(services, repos, db, super_admin, mock_provider) -> None:
    """10 آلاف خدمة: كل أنواع البحث تنتهي بزمن قصير والنتائج صحيحة."""
    await _bulk_services(db, repos, mock_provider, 10_000, start=100_000)
    target = await repos.services.find_by_provider_service(mock_provider.id, "107777")
    timings = {}
    for label, term, expected_total in (
        ("by_id", str(target.id), 1),
        ("by_psid", "107777", 1),
        ("by_name", "Bulk service 107777", 1),
        ("by_text", "Bulk service", 10_000),
        ("two_words", "bulk 1077", 101),
    ):
        started = time.perf_counter()
        page = await services.catalog.admin_search_services(super_admin, term)
        timings[label] = time.perf_counter() - started
        assert page.total_items == expected_total, label
    assert max(timings.values()) < 1.0, timings


# ----------------------------- واجهة البحث ----------------------------- #


async def test_search_button_flow_results_pagination_and_open_card(bot, context, db, repos, super_admin, mock_provider) -> None:  # noqa: F811
    """الزر ⇐ سؤال ⇐ نتائج بأزرار ⇐ صفحة ثانية ⇐ فتح بطاقة خدمة."""
    await _bulk_services(db, repos, mock_provider, 15)
    await load_user(bot, context, super_admin)
    state = await press(bot, context, admin_catalog.start_search, pack(NS_ADM_CAT, "find"), super_admin.telegram_id)
    assert state == admin_catalog.ASK_SEARCH_TERM and "بحث عن خدمة" in bot.last.text
    await write(bot, context, admin_catalog.receive_search_term, "bulk service", super_admin.telegram_id)
    assert "العدد: 15" in bot.last.text and "الصفحة 1 من" in bot.last.text
    service_buttons = [b for b in bot.last.buttons if b.startswith("ac:svc:")]
    assert len(service_buttons) >= 5 and pack(NS_ADM_CAT, "find") in bot.last.buttons

    await press(bot, context, admin_catalog.search_page_screen, pack(NS_ADM_CAT, "found", 2), super_admin.telegram_id)
    assert "الصفحة 2 من" in bot.last.text
    await press(bot, context, admin_catalog.service_card_screen, service_buttons[0], super_admin.telegram_id)
    assert "Bulk service" in bot.last.text


async def test_search_button_empty_short_and_expired_cases(bot, context, super_admin, mock_provider, mock_service) -> None:  # noqa: F811
    """لا نتائج ⇒ رسالة واضحة؛ نص قصير ⇒ تبقى الخطوة؛ صفحة بلا بحث محفوظ ⇒ انتهت الصلاحية."""
    await load_user(bot, context, super_admin)
    await press(bot, context, admin_catalog.start_search, pack(NS_ADM_CAT, "find"), super_admin.telegram_id)
    state = await write(bot, context, admin_catalog.receive_search_term, "x", super_admin.telegram_id)
    assert state is None and "حرفين" in bot.last.text
    await write(bot, context, admin_catalog.receive_search_term, "nothing-here", super_admin.telegram_id)
    assert "لا نتائج" in bot.last.text
    context.user_data.pop(admin_catalog.SEARCH_TERM_KEY, None)
    await press(bot, context, admin_catalog.search_page_screen, pack(NS_ADM_CAT, "found", 2), super_admin.telegram_id)
    assert "انتهت صلاحية" in bot.last.text


async def test_provider_services_screen_paginates_beyond_1000(bot, context, db, repos, super_admin, mock_provider) -> None:  # noqa: F811
    """بطاقة «خدماتنا من المزود» تعرض العدد الكلي الصحيح (1200) وتصفح بلا سقف."""
    await _bulk_services(db, repos, mock_provider, 1200)
    await load_user(bot, context, super_admin)
    await press(bot, context, admin_providers.provider_services_screen, pack("pv", "svcs", mock_provider.id, 2), super_admin.telegram_id)
    assert "العدد: 1200" in bot.last.text and "الصفحة 2 من" in bot.last.text
