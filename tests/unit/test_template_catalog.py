"""
اختبارات طبقة قوالب الإشعارات (المرحلة 8) — منطق خالص بلا قاعدة بيانات.

الحارس الأهم هنا: **كل قالب افتراضي يجب أن يُعرَض بقيمه التجريبية بلا خطأ**،
وأن تتطابق متغيراته المعلنة مع ما كُتب فعلاً في نصه. غير ذلك = رسالة عميل
تنهار وقت الإرسال أو متغير معلَن لا يعمل.
"""

from __future__ import annotations

import pytest

from texts import templates as tpl


@pytest.fixture(autouse=True)
def _clean_overrides():
    """لا تتسرب القوالب المخصّصة بين الاختبارات."""
    tpl.clear_overrides()
    yield
    tpl.clear_overrides()


@pytest.mark.parametrize("definition", tpl.TEMPLATES, ids=lambda d: d.code)
def test_every_default_template_renders_with_its_sample(definition: tpl.TemplateDef) -> None:
    """كل قالب افتراضي يُعرَض بقيمه التجريبية دون KeyError أو نص مبتور."""
    title, body = tpl.render(definition.code, **definition.sample)
    assert title and body is not None
    assert "{" not in title and "}" not in title
    assert "{" not in body and "}" not in body


@pytest.mark.parametrize("definition", tpl.TEMPLATES, ids=lambda d: d.code)
def test_declared_variables_match_the_text(definition: tpl.TemplateDef) -> None:
    """المتغيرات المعلنة = المستخدمة فعلاً في العنوان والنص (لا زيادة ولا نقص)."""
    used = set(tpl.placeholders_in(definition.title)) | set(tpl.placeholders_in(definition.body))
    assert used == set(definition.variables)
    assert set(definition.sample) == set(definition.variables)


def test_codes_are_unique_and_groups_known() -> None:
    """رموز القوالب فريدة ومجموعاتها معرَّفة."""
    codes = [item.code for item in tpl.TEMPLATES]
    assert len(codes) == len(set(codes))
    assert {item.group for item in tpl.TEMPLATES} <= set(tpl.TEMPLATE_GROUPS)


def test_wrappers_keep_the_original_wording() -> None:
    """الدوال القديمة تُنتج نفس النص حرفياً بعد نقلها إلى طبقة القوالب (لا تراجع)."""
    title, body = tpl.order_failed(code="ORD-1", reason="رابط خاطئ", refund_units=250_000)
    assert title == "❌ تعذّر تنفيذ طلبك"
    assert body == (
        "😔 الطلب ORD-1 لم يُنفَّذ.\n\n"
        "📝 السبب: رابط خاطئ\n"
        "💰 أُعيد كامل المبلغ إلى رصيدك: 25.00\n\n"
        "🔄 يمكنك المحاولة مرة أخرى، أو تواصل مع 🎫 الدعم."
    )
    _title, body = tpl.order_created(
        code="ORD-2", service_name="خدمة", quantity=1500, cost_units=10_000
    )
    assert "🔢 الكمية: 1,500" in body and "💵 المبلغ المخصوم: 1.00" in body


def test_payment_received_fee_block_only_when_fee_exists() -> None:
    """سطرا الرسوم يظهران عند وجود رسوم فقط، ولا يتركان سطراً فارغاً عند غيابها."""
    _t, with_fee = tpl.payment_received(
        payment_id=5, amount_units=2_000_000, fee_units=60_000, net_units=1_940_000
    )
    assert "🧾 رسوم الطريقة: 6.00" in with_fee
    assert "💵 المتوقع إضافته: 194.00" in with_fee
    _t, no_fee = tpl.payment_received(payment_id=5, amount_units=2_000_000)
    assert "رسوم" not in no_fee
    assert no_fee == "📥 طلب الشحن #5 بمبلغ 200.00 قيد المراجعة ⏳\n🔔 سنعلمك فور اعتماده."


def test_ticket_closed_reason_is_optional() -> None:
    """سبب الإغلاق يظهر فقط حين يُذكر."""
    assert tpl.ticket_closed(ticket_id=3, reason="")[1] == "🔒 تم إغلاق التذكرة #3.\n\n🌹 شكراً لتواصلك معنا."
    assert tpl.ticket_closed(ticket_id=3, reason="تم الحل")[1].startswith("🔒 تم إغلاق التذكرة #3.\n📝 تم الحل")


def test_custom_template_replaces_default() -> None:
    """القالب المخصّص يحلّ محل الافتراضي عند البناء."""
    tpl.set_overrides({"order_in_progress": ("🔥 جاري", "طلبك {code} انطلق")})
    assert tpl.order_in_progress(code="ORD-9") == ("🔥 جاري", "طلبك ORD-9 انطلق")
    tpl.clear_overrides()
    assert tpl.order_in_progress(code="ORD-9")[0] == "🔄 طلبك قيد التنفيذ"


def test_broken_custom_template_falls_back_to_default() -> None:
    """قالب مخصّص بمتغير غير موجود لا يُسقط الرسالة — يُستعمل الافتراضي."""
    tpl.set_overrides({"order_in_progress": ("عنوان", "طلب {nonexistent}")})
    title, body = tpl.order_in_progress(code="ORD-9")
    assert title == "🔄 طلبك قيد التنفيذ"
    assert body == "🔄 بدأ تنفيذ الطلب ORD-9 الآن — نعمل على إنجازه ⚡"


def test_unknown_template_code_is_a_programming_error() -> None:
    """رمز غير معرَّف يُكشف فوراً بدل أن يُنتج رسالة فارغة."""
    with pytest.raises(KeyError):
        tpl.render("does_not_exist")


@pytest.mark.parametrize(
    "text",
    [
        "{code.__class__}",       # وصول لخاصية
        "{code[0]}",              # فهرسة
        "{amount:>9999999}",      # تنسيق يصنع رسالة ضخمة
        "{amount!r}",             # تحويل
        "{}",                     # موضعي فارغ
        "{0}",                    # موضعي رقمي
        "{secret}",               # متغير غير معلَن
    ],
)
def test_dangerous_placeholders_are_rejected(text: str) -> None:
    """كل ما قد يسرّب داخلياتٍ أو يضخّم الرسالة يُرفض قبل الحفظ."""
    assert tpl.invalid_placeholders(text, ("code", "amount")) != []


def test_valid_placeholders_and_escaped_braces_pass() -> None:
    """المتغيرات المعلنة والأقواس المهرَّبة `{{ }}` مقبولة."""
    assert tpl.invalid_placeholders("طلب {code} بمبلغ {amount}", ("code", "amount")) == []
    assert tpl.invalid_placeholders("قوس {{حرفي}} هنا", ("code",)) == []


def test_set_overrides_replaces_everything() -> None:
    """استبدال الذاكرة كاملةً: القديم يختفي، لا دمج صامت."""
    tpl.set_overrides({"order_created": ("a", "b")})
    tpl.set_overrides({"order_failed": ("c", "d")})
    assert set(tpl.active_overrides()) == {"order_failed"}
