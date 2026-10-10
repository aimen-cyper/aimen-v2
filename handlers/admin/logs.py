"""
قسم «📝 السجلات» في لوحة التحكم: التدقيق والأخطاء واستدعاءات المزودين.

لماذا هذه الشاشة مهمة؟
    سجل التدقيق هو الجواب على سؤال «من فعل ماذا ومتى» — وهو شرط أساسي في
    أي نظام يتعامل مع أموال. عرضه داخل البوت يعني ألا يحتاج صاحب النظام
    فتح قاعدة البيانات ليعرف ما جرى.

الشاشات (مساحة `al`):
    al:home                       : اختيار السجل.
    al:audit:<p> / al:acat:<c>:<p>: سجل التدقيق (كل السجلات / ضمن فئة) مع ترقيم دقيق.
    al:afl[:<c>]                  : قائمة فلتر الفئات.
    al:aud:<id>:<c>:<p>           : تفاصيل سجل تدقيق (قبل/بعد/تفاصيل).
    al:errors:<p> / al:err:<id>:<p>: قائمة الأخطاء وتفصيل الخطأ.
    al:prq|prqf:<p> / al:prqd:<id>:<m>:<p> : استدعاءات المزودين (الكل/الفاشلة) وتفصيل الاستدعاء.

ملاحظات:
    • العرض للقراءة فقط — لا تعديل ولا حذف لأي سجل من الواجهة إطلاقاً.
    • كل شاشة تفحص `logs.view` على الـcallback نفسه.
    • النصوص تُنقّى من الأسرار مرة ثانية عند العرض (دفاع متعدد الطبقات) وتُهرَّب وتُقتطع.
"""

from __future__ import annotations

import json

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from core.permissions import Permission
from handlers.admin.common import (
    LOG_PAGE_SIZE,
    admin_required,
    args,
    paginate,
)
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render
from keyboards.admin_kb import (
    logs_audit_detail_kb,
    logs_audit_filter_kb,
    logs_audit_kb,
    logs_call_detail_kb,
    logs_calls_kb,
    logs_error_detail_kb,
    logs_errors_kb,
    logs_home_kb,
    logs_page_kb,
)
from keyboards.callback_data import NS_ADM_LOG, pattern
from middlewares.context import services_of
from services.audit_service import AUDIT_CATEGORIES
from texts import admin_ar as t
from utils.formatters import datetime_text, safe
from utils.security import sanitize

#: أقصى طول لكتلة JSON/نص في شاشة التفاصيل (حد رسالة تيليجرام 4096 حرفاً مع بقية الحقول)
DETAIL_BLOCK_LIMIT = 700


def _audit_icon(action: str) -> str:
    """اختيار أيقونة السطر حسب بادئة اسم الإجراء (users.ban ⇐ 👤)."""
    prefix = (action or "").split(".", 1)[0]
    return t.AUDIT_ICONS.get(prefix, "🔸")


def _pretty(raw: str | None) -> str:
    """
    تهيئة قيمة JSON مخزّنة للعرض: تنسيق مقروء، تنقية أسرار، اقتطاع، تهريب HTML.

    إن لم تكن القيمة JSON صالحاً تُعرض كنص كما هي (بعد التنقية).
    """
    if not raw:
        return ""
    try:
        text = json.dumps(json.loads(raw), ensure_ascii=False, indent=1)
    except (TypeError, ValueError):
        text = raw
    return safe(sanitize(text), limit=DETAIL_BLOCK_LIMIT)


def _category_arg(update: Update, index: int) -> str:
    """فئة الفلتر من وسائط الزر (الافتراضي all)؛ القيمة الغريبة تُرفض لاحقاً في الخدمة."""
    return args(update).arg(index) or "all"


async def _admin_label(services, cache: dict[int, str], admin_id: int | None) -> str:
    """اسم منفّذ العملية للعرض (مع تخزين مؤقت داخل الشاشة الواحدة)."""
    if not admin_id:
        return "النظام"
    if admin_id not in cache:
        user = await services.users.get(admin_id)
        cache[admin_id] = user.display_name if user else str(admin_id)
    return cache[admin_id]


@guarded
@admin_required(Permission.LOGS_VIEW)
async def logs_home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة اختيار السجل."""
    await answer_callback(update)
    await render(update, context, t.LOGS_HOME, logs_home_kb())


@guarded
@admin_required(Permission.LOGS_VIEW)
async def audit_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    سجل التدقيق: آخر العمليات الإدارية مع منفّذها وهدفها ووقتها.

    الأزرار: `al:audit:<page>` (كل السجلات) و`al:acat:<category>:<page>` (ضمن فئة).
    """
    await answer_callback(update)
    services = services_of(context)
    call = args(update)
    if call.action == "acat":
        category, page_arg = _category_arg(update, 0), call.int_arg(1, 1)
    else:
        category, page_arg = "all", call.int_arg(0, 1)
    label = t.AUDIT_CATEGORY_LABELS.get(category, category)
    total = await services.audit.count_filtered(category)
    page, total_pages, offset = paginate(total, page_arg, LOG_PAGE_SIZE)
    entries = await services.audit.list_filtered(category, limit=LOG_PAGE_SIZE, offset=offset)

    if not entries:
        await render(
            update,
            context,
            t.AUDIT_EMPTY.format(category=label),
            logs_audit_kb([], category=category, page=1, total_pages=1),
        )
        return

    admins: dict[int, str] = {}
    lines: list[str] = []
    for entry in entries:
        target = f"{entry.target_type}:{entry.target_id}" if entry.target_type else "—"
        lines.append(
            t.AUDIT_LINE.format(
                id=entry.id,
                icon=_audit_icon(entry.action),
                action=safe(entry.action, limit=40),
                admin=safe(await _admin_label(services, admins, entry.admin_id), limit=25),
                target=safe(target, limit=30),
                when=datetime_text(entry.created_at),
            )
        )

    await render(
        update,
        context,
        t.AUDIT_TITLE.format(
            category=label, total=total, page=page, pages=total_pages, lines="\n\n".join(lines)
        ),
        logs_audit_kb([entry.id for entry in entries], category=category, page=page, total_pages=total_pages),
    )


@guarded
@admin_required(Permission.LOGS_VIEW)
async def audit_filter_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة فئات الفلتر (لا تغيّر أي بيانات؛ الاختيار زر `acat`)."""
    await answer_callback(update)
    category = _category_arg(update, 0)
    await render(update, context, t.AUDIT_FILTER_MENU, logs_audit_filter_kb(category if category in AUDIT_CATEGORIES else "all"))


@guarded
@admin_required(Permission.LOGS_VIEW)
async def audit_detail_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تفاصيل سجل تدقيق: الإجراء، المنفّذ، الهدف، المصدر، وقيم قبل/بعد/تفاصيل مُنقّاة."""
    await answer_callback(update)
    services = services_of(context)
    call = args(update)
    category, page = _category_arg(update, 1), max(1, call.int_arg(2, 1))
    if category not in AUDIT_CATEGORIES:
        category = "all"
    entry = await services.audit.get_entry(call.int_arg(0, 0))
    if entry is None:
        await render(update, context, t.AUDIT_NOT_FOUND, logs_audit_detail_kb(category, page))
        return
    blocks = ""
    for key, raw in (("before", entry.before_json), ("after", entry.after_json), ("details", entry.details_json)):
        body = _pretty(raw)
        if body:
            blocks += t.AUDIT_DETAIL_BLOCK.format(title=t.AUDIT_DETAIL_BLOCK_TITLES[key], body=body)
    target = f"{entry.target_type}:{entry.target_id}" if entry.target_type else "—"
    text = t.AUDIT_DETAIL.format(
        id=entry.id,
        action=safe(entry.action, limit=80),
        admin=safe(await _admin_label(services, {}, entry.admin_id), limit=40),
        target=safe(target, limit=60),
        source=safe(entry.source, limit=20),
        when=datetime_text(entry.created_at),
        blocks=blocks or t.AUDIT_DETAIL_NO_DATA,
    )
    await render(update, context, text, logs_audit_detail_kb(category, page))


@guarded
@admin_required(Permission.LOGS_VIEW)
async def errors_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """سجل الأخطاء: آخر ما سجّله النظام من أعطال (ترقيم بإجمالي معروف)."""
    await answer_callback(update)
    services = services_of(context)
    total = await services.audit.count_errors()
    page, total_pages, offset = paginate(total, args(update).int_arg(0, 1), LOG_PAGE_SIZE)
    entries = await services.audit.recent_errors(limit=LOG_PAGE_SIZE, offset=offset)

    if not entries:
        await render(update, context, t.ERRORS_EMPTY, logs_page_kb("errors", page=1, total_pages=1))
        return

    lines = "\n\n".join(
        t.ERROR_LINE.format(
            id=entry["id"],
            level=safe(str(entry.get("level", "ERROR")), limit=10),
            source=safe(str(entry.get("source") or "—"), limit=30),
            message=safe(str(entry.get("message") or "—"), limit=160),
            when=datetime_text(str(entry.get("created_at") or "")),
        )
        for entry in entries
    )
    await render(
        update,
        context,
        t.ERRORS_TITLE.format(total=total, page=page, pages=total_pages, lines=lines),
        logs_errors_kb([int(entry["id"]) for entry in entries], page=page, total_pages=total_pages),
    )


@guarded
@admin_required(Permission.LOGS_VIEW)
async def error_detail_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تفاصيل خطأ: الرسالة الكاملة (مقتطعة) ومقتطف الأثر وملخص التحديث — كلها مُنقّاة."""
    await answer_callback(update)
    services = services_of(context)
    call = args(update)
    page = max(1, call.int_arg(1, 1))
    entry = await services.audit.get_error(call.int_arg(0, 0))
    if entry is None:
        await render(update, context, t.ERROR_NOT_FOUND, logs_error_detail_kb(page))
        return
    extra = ""
    if entry.get("update_summary"):
        extra += t.ERROR_DETAIL_UPDATE.format(summary=safe(sanitize(entry["update_summary"]), limit=DETAIL_BLOCK_LIMIT))
    if entry.get("traceback_snippet"):
        extra += t.ERROR_DETAIL_TRACE.format(trace=safe(sanitize(entry["traceback_snippet"]), limit=1200))
    user_label = "—"
    if entry.get("user_id"):
        user = await services.users.get(int(entry["user_id"]))
        user_label = safe(user.display_name if user else str(entry["user_id"]), limit=40)
    text = t.ERROR_DETAIL.format(
        id=entry["id"],
        level=safe(str(entry.get("level") or "ERROR"), limit=10),
        source=safe(str(entry.get("source") or "—"), limit=40),
        error_type=safe(str(entry.get("error_type") or "—"), limit=60),
        when=datetime_text(str(entry.get("created_at") or "")),
        user=user_label,
        notified="نعم" if entry.get("notified_admin") else "لا",
        message=safe(sanitize(str(entry.get("message") or "—")), limit=800),
        extra=extra,
    )
    await render(update, context, text, logs_error_detail_kb(page))


async def _calls_list(update: Update, context: ContextTypes.DEFAULT_TYPE, *, failed_only: bool) -> None:
    """عرض قائمة استدعاءات المزودين (الكل أو الفاشلة) — منطق مشترك للزرين."""
    services = services_of(context)
    mode_label = t.PROVIDER_CALLS_MODE["failed" if failed_only else "all"]
    total = await services.audit.count_provider_calls(only_failed=failed_only)
    page, total_pages, offset = paginate(total, args(update).int_arg(0, 1), LOG_PAGE_SIZE)
    rows = await services.audit.provider_calls(only_failed=failed_only, limit=LOG_PAGE_SIZE, offset=offset)
    if not rows:
        await render(
            update,
            context,
            t.PROVIDER_CALLS_EMPTY.format(mode=mode_label),
            logs_calls_kb([], failed_only=failed_only, page=1, total_pages=1),
        )
        return
    lines = "\n\n".join(
        t.PROVIDER_CALL_LINE.format(
            id=row["id"],
            icon="✅" if row["is_success"] else "❌",
            provider=safe(str(row.get("provider_name") or f"#{row['provider_id']}"), limit=30),
            action=safe(str(row["action"]), limit=12),
            meta=_call_meta(row),
            when=datetime_text(str(row.get("created_at") or "")),
        )
        for row in rows
    )
    await render(
        update,
        context,
        t.PROVIDER_CALLS_TITLE.format(mode=mode_label, total=total, page=page, pages=total_pages, lines=lines),
        logs_calls_kb([int(row["id"]) for row in rows], failed_only=failed_only, page=page, total_pages=total_pages),
    )


def _call_meta(row: dict) -> str:
    """سطر وصفي مختصر: HTTP · المدة · الطلب · نوع الخطأ (للحقول الموجودة فقط)."""
    parts: list[str] = []
    if row.get("http_status") is not None:
        parts.append(f"HTTP {row['http_status']}")
    if row.get("duration_ms") is not None:
        parts.append(f"{row['duration_ms']}ms")
    if row.get("order_id"):
        parts.append(f"طلب #{row['order_id']}")
    if row.get("error_type"):
        parts.append(safe(str(row["error_type"]), limit=30))
    return " · ".join(parts) or "—"


@guarded
@admin_required(Permission.LOGS_VIEW)
async def calls_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """سجل استدعاءات المزودين (الكل)."""
    await answer_callback(update)
    await _calls_list(update, context, failed_only=False)


@guarded
@admin_required(Permission.LOGS_VIEW)
async def calls_failed_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """سجل استدعاءات المزودين الفاشلة فقط."""
    await answer_callback(update)
    await _calls_list(update, context, failed_only=True)


@guarded
@admin_required(Permission.LOGS_VIEW)
async def call_detail_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تفاصيل استدعاء مزود: ملخص الطلب ومقتطف الرد (منقّيان من الأسرار عند التخزين والعرض)."""
    await answer_callback(update)
    services = services_of(context)
    call = args(update)
    mode = "f" if call.arg(1) == "f" else "a"
    page = max(1, call.int_arg(2, 1))
    row = await services.audit.get_provider_call(call.int_arg(0, 0))
    if row is None:
        await render(update, context, t.PROVIDER_CALL_NOT_FOUND, logs_call_detail_kb(mode, page))
        return
    extra = ""
    if row.get("request_summary"):
        extra += t.PROVIDER_CALL_REQUEST.format(body=safe(sanitize(row["request_summary"]), limit=DETAIL_BLOCK_LIMIT))
    if row.get("response_snippet"):
        extra += t.PROVIDER_CALL_RESPONSE.format(body=safe(sanitize(row["response_snippet"]), limit=DETAIL_BLOCK_LIMIT))
    text = t.PROVIDER_CALL_DETAIL.format(
        id=row["id"],
        provider=safe(str(row.get("provider_name") or f"#{row['provider_id']}"), limit=40),
        action=safe(str(row["action"]), limit=12),
        result="✅ نجح" if row["is_success"] else "❌ فشل",
        http=row["http_status"] if row.get("http_status") is not None else "—",
        duration=f"{row['duration_ms']}ms" if row.get("duration_ms") is not None else "—",
        order=f"#{row['order_id']}" if row.get("order_id") else "—",
        error_type=safe(str(row.get("error_type") or "—"), limit=60),
        when=datetime_text(str(row.get("created_at") or "")),
        extra=extra,
    )
    await render(update, context, text, logs_call_detail_kb(mode, page))


def conversations() -> list:
    """لا محادثات في قسم السجلات (عرض فقط)."""
    return []


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم السجلات."""
    table = (
        ("home", logs_home_screen),
        ("audit", audit_screen),
        ("acat", audit_screen),
        ("afl", audit_filter_screen),
        ("aud", audit_detail_screen),
        ("errors", errors_screen),
        ("err", error_detail_screen),
        ("prq", calls_screen),
        ("prqf", calls_failed_screen),
        ("prqd", call_detail_screen),
    )
    return [CallbackQueryHandler(handler, pattern=pattern(NS_ADM_LOG, action)) for action, handler in table]
