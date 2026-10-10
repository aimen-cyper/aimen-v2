# الكود الكامل — المرحلة 4 (لوحة الأدمن داخل تيليجرام + RBAC + سجل التدقيق)

كل ما في هذا الملف منسوخ آلياً من ملفات المشروع الفعلية وقت كتابة التقرير،
فلا يوجد اختلاف بين ما تقرأه هنا وما يعمل عندك.

> الملفات غير المذكورة هنا لم تتغيّر عن المراحل 1–3.

## الفهرس

**النصوص ولوحات الأزرار**

- `texts/admin_ar.py` — 473 سطراً
- `keyboards/admin_kb.py` — 713 سطراً
- `keyboards/callback_data.py` — 157 سطراً
- `keyboards/user_kb.py` — 378 سطراً

**لوحة التحكم — الأساس والأقسام الثمانية**

- `handlers/admin/__init__.py` — 61 سطراً
- `handlers/admin/common.py` — 212 سطراً
- `handlers/admin/dashboard.py` — 107 سطراً
- `handlers/admin/users.py` — 750 سطراً
- `handlers/admin/payments.py` — 406 سطراً
- `handlers/admin/orders.py` — 564 سطراً
- `handlers/admin/tickets.py` — 377 سطراً
- `handlers/admin/catalog.py` — 485 سطراً
- `handlers/admin/settings.py` — 346 سطراً
- `handlers/admin/logs.py` — 142 سطراً

**الربط والتنقل**

- `handlers/registry.py` — 286 سطراً
- `handlers/common/navigation.py` — 123 سطراً
- `core/constants.py` — 44 سطراً

**الخدمات والمستودعات المُحدَّثة**

- `services/catalog_service.py` — 353 سطراً
- `services/audit_service.py` — 145 سطراً
- `services/order_service.py` — 1369 سطراً
- `services/ticket_service.py` — 575 سطراً
- `database/repositories/orders.py` — 561 سطراً
- `database/repositories/tickets.py` — 257 سطراً

**الاختبارات الجديدة والمُحدَّثة**

- `tests/telegram_fakes.py` — 221 سطراً
- `tests/integration/test_no_dead_buttons.py` — 400 سطراً
- `tests/integration/test_admin_access.py` — 185 سطراً
- `tests/integration/test_admin_users.py` — 371 سطراً
- `tests/integration/test_admin_payments.py` — 235 سطراً
- `tests/integration/test_admin_orders.py` — 364 سطراً
- `tests/integration/test_admin_support.py` — 153 سطراً
- `tests/integration/test_admin_catalog_settings.py` — 358 سطراً

**الإجمالي:** 31 ملفاً · 11171 سطراً.

---

## النصوص ولوحات الأزرار

### `texts/admin_ar.py`

```python
"""
نصوص لوحة التحكم (الأدمن) — عربية بالكامل.

فُصلت عن `texts/ar.py` لأن نصوص الأدمن كثيرة ولها لهجة مختلفة (أرقام ودقّة
تشغيلية بدل لغة تسويقية)، وفصلها يسهّل مراجعتها وترجمتها لاحقاً.

قاعدة: أي نص يراه الأدمن يُكتب هنا، ولا يُكتب داخل المعالجات.
"""

from __future__ import annotations

# ============================== عام ==================================== #

PANEL_TITLE = "🛠 <b>لوحة التحكم</b>"
ERR_NO_PERMISSION = "🚫 لا تملك صلاحية تنفيذ هذا الإجراء."
ERR_NOT_ADMIN = "🚫 هذا القسم مخصص لفريق الإدارة."
ERR_NOT_TEXT = "❌ أرسل نصاً من فضلك."
ERR_SESSION_LOST = "⚠️ انتهت الجلسة. ابدأ من جديد عبر /admin"
CANCELLED = "✅ أُلغيت العملية."
DONE = "✅ تم التنفيذ."
NOTHING_CHANGED = "ℹ️ لا تغيير — الحالة كما هي."

BTN_ADMIN_PANEL = "🛠 لوحة التحكم"
BTN_BACK_PANEL = "🔙 لوحة التحكم"
BTN_REFRESH = "🔄 تحديث"
BTN_CONFIRM_DANGER = "⚠️ نعم، نفّذ"
BTN_EDIT_AMOUNT = "✏️ تعديل المبلغ"

# ============================ القائمة ================================== #

MENU_USERS = "👥 المستخدمون"
MENU_PAYMENTS = "💰 المدفوعات"
MENU_ORDERS = "📦 الطلبات"
MENU_TICKETS = "🎫 الدعم"
MENU_CATALOG = "🛍 الكتالوج"
MENU_SETTINGS = "⚙️ الإعدادات"
MENU_LOGS = "📝 السجلات"
MENU_HEALTH = "🩺 صحة النظام"

DASHBOARD = (
    "🛠 <b>لوحة التحكم</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "👥 المستخدمون: {users_total} (جديد اليوم: {users_new_today} · نشِط ٧ أيام: {users_active_7d})\n"
    "🚫 محظورون: {users_banned}\n\n"
    "📦 طلبات اليوم: {orders_today}\n"
    "⚙️ طلبات نشطة: {active_orders}\n"
    "⚠️ تحتاج تدخلاً: {attention_orders}\n\n"
    "💵 إيراد اليوم: {revenue_today}\n"
    "💵 إيراد ٧ أيام: {revenue_7d}\n"
    "📥 إيداعات اليوم: {deposits_today}\n\n"
    "⏳ شحن بانتظار المراجعة: {pending_payments}\n"
    "🎫 تذاكر مفتوحة: {open_tickets}\n"
    "🔔 إشعارات في الطابور: {queued}\n"
    "🛍 خدمات مفعّلة: {active_services}\n"
    "❗ أخطاء ٢٤ ساعة: {errors_24h}\n\n"
    "🕒 {now}"
)

PANEL_SIMPLE = (
    "🛠 <b>لوحة التحكم</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "اختر القسم الذي تريد العمل عليه.\n"
    "الأقسام المعروضة هي ما تسمح به صلاحياتك."
)

# ========================== المستخدمون ================================= #

USERS_HOME = (
    "👥 <b>المستخدمون</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "الإجمالي: {total} · جديد اليوم: {new_today}\n"
    "نشِط اليوم: {active_today} · محظورون: {banned}\n\n"
    "استخدم 🔍 للبحث بالمعرف الرقمي أو اسم المستخدم."
)
BTN_USER_SEARCH = "🔍 بحث عن مستخدم"
USERS_ASK_QUERY = (
    "🔍 أرسل <b>معرف تيليجرام</b> (أرقام) أو <b>اسم المستخدم</b> (@name) أو جزءاً من الاسم."
)
USERS_RESULTS = "🔍 <b>نتائج البحث عن:</b> {query}\n\nعدد النتائج: {count}"
USERS_NO_RESULTS = "🔍 لا نتائج مطابقة لـ: {query}"

USER_CARD = (
    "👤 <b>{name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🆔 المعرف: <code>{telegram_id}</code>\n"
    "🔖 المستخدم: {username}\n"
    "🎚 الدور: {role}\n"
    "{ban_line}"
    "💰 الرصيد: {balance}\n"
    "📥 إجمالي الشحن: {deposited}\n"
    "📤 إجمالي الإنفاق: {spent}\n\n"
    "📦 الطلبات: {orders_count} (نشطة: {active_orders})\n"
    "💳 طلبات الشحن: {payments_count}\n"
    "🎫 تذاكر مفتوحة: {tickets_open}\n\n"
    "📅 الانضمام: {joined}\n"
    "🕒 آخر نشاط: {last_activity}\n"
    "{note_line}"
)
USER_BANNED_LINE = "🚫 <b>محظور</b> — السبب: {reason}\n"
USER_NOTE_LINE = "\n📝 ملاحظة إدارية:\n{note}"

BTN_USER_CREDIT = "➕ إضافة رصيد"
BTN_USER_DEBIT = "➖ خصم رصيد"
BTN_USER_BAN = "🚫 حظر"
BTN_USER_UNBAN = "✅ فك الحظر"
BTN_USER_NOTE = "📝 ملاحظة"
BTN_USER_ROLE = "🎚 تغيير الدور"
BTN_USER_ORDERS = "📦 طلباته"
BTN_USER_TX = "💳 معاملاته"

USER_ASK_CREDIT = "➕ <b>إضافة رصيد لـ {name}</b>\n\nالرصيد الحالي: {balance}\n\nأرسل المبلغ:"
USER_ASK_DEBIT = "➖ <b>خصم رصيد من {name}</b>\n\nالرصيد الحالي: {balance}\n\nأرسل المبلغ:"
USER_ASK_BALANCE_REASON = "📝 أرسل سبب العملية (يُحفظ في سجل التدقيق ويُعرض في كشف الحساب):"
USER_BALANCE_CONFIRM = (
    "⚠️ <b>تأكيد العملية</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "👤 المستخدم: {name}\n"
    "{icon} العملية: {operation}\n"
    "💵 المبلغ: {amount}\n"
    "💰 الرصيد الحالي: {balance}\n"
    "💰 بعد التنفيذ: {balance_after}\n"
    "📝 السبب: {reason}\n\n"
    "اضغط «نعم، نفّذ» للتأكيد."
)
USER_BALANCE_DONE = (
    "✅ <b>تمت العملية</b>\n\n"
    "👤 {name}\n{icon} {operation}: {amount}\n💰 الرصيد الجديد: {balance}\n\n"
    "📨 أُشعر المستخدم تلقائياً."
)
OP_CREDIT = "إضافة رصيد"
OP_DEBIT = "خصم رصيد"

USER_ASK_BAN_REASON = "🚫 أرسل سبب حظر <b>{name}</b> (يظهر للمستخدم عند محاولته استخدام البوت):"
USER_BAN_CONFIRM = (
    "⚠️ <b>تأكيد الحظر</b>\n\n👤 {name}\n📝 السبب: {reason}\n\n"
    "المحظور لن يستطيع إنشاء طلبات أو شحن رصيد."
)
USER_BAN_DONE = "🚫 تم حظر {name}."
USER_UNBAN_DONE = "✅ تم فك الحظر عن {name}."
USER_ASK_NOTE = "📝 أرسل الملاحظة الإدارية عن <b>{name}</b> (تُعرض للإدارة فقط):"
USER_NOTE_DONE = "✅ حُفظت الملاحظة."

USER_ROLE_TITLE = "🎚 <b>تغيير دور {name}</b>\n\nالدور الحالي: {role}\n\nاختر الدور الجديد:"
USER_ROLE_CONFIRM = (
    "⚠️ <b>تأكيد تغيير الدور</b>\n\n"
    "👤 {name}\n"
    "من: {old_role}\n"
    "إلى: <b>{new_role}</b>\n\n"
    "تغيير الدور يمنح أو يسحب صلاحيات فوراً."
)
USER_ROLE_DONE = "✅ أصبح دور {name}: {role}"
USER_ROLE_SAME = "ℹ️ المستخدم في هذا الدور أصلاً."

USER_ORDERS_TITLE = "📦 <b>طلبات {name}</b>\n\nالصفحة {page} من {pages}\n\n{lines}"
USER_ORDERS_EMPTY = "📦 لا طلبات لهذا المستخدم."
USER_TX_TITLE = "💳 <b>معاملات {name}</b>\n\nالصفحة {page} من {pages}\n\n{lines}"
USER_TX_EMPTY = "💳 لا معاملات مالية لهذا المستخدم."

# =========================== المدفوعات ================================= #

PAYMENTS_TITLE = (
    "💰 <b>طلبات الشحن المعلّقة</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "العدد: {count} · الصفحة {page} من {pages}"
)
PAYMENTS_EMPTY = "✅ لا توجد طلبات شحن بانتظار المراجعة."
PAYMENT_CARD = (
    "💳 <b>طلب شحن #{payment_id}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "👤 {name} (<code>{telegram_id}</code>)\n"
    "💵 المبلغ: {amount}\n"
    "🏦 الطريقة: {method}\n"
    "🔢 رقم العملية: {reference}\n"
    "📎 الإثبات: {proof}\n"
    "📅 أُرسل: {created}\n"
    "⌛ ينتهي: {expires}\n"
    "📌 الحالة: {status}\n"
    "{note_line}"
    "{review_line}"
)
PAYMENT_NOTE_LINE = "🗒 ملاحظة المستخدم: {note}\n"
PAYMENT_REVIEW_LINE = "\n👮 روجع بواسطة: {admin}\n📝 {detail}\n"
PAYMENT_PROOF_NONE = "لا يوجد"
PAYMENT_PROOF_PHOTO = "صورة مرفقة"
PAYMENT_PROOF_DOC = "ملف مرفق"
PAYMENT_PROOF_CAPTION = "📎 إثبات الدفع للطلب #{payment_id}"

BTN_PAYMENT_PROOF = "📎 عرض الإثبات"
BTN_PAYMENT_APPROVE = "✅ اعتماد"
BTN_PAYMENT_REJECT = "❌ رفض"

PAYMENT_APPROVE_CONFIRM = (
    "⚠️ <b>تأكيد اعتماد الشحن #{payment_id}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "👤 {name}\n"
    "💵 المبلغ المطلوب: {amount}\n"
    "💵 <b>سيُضاف فعلياً: {credited}</b>\n"
    "💰 رصيد المستخدم بعد الإضافة: {balance_after}\n\n"
    "اضغط «نعم، نفّذ» للاعتماد، أو «تعديل المبلغ» لإضافة مبلغ مختلف."
)
PAYMENT_ASK_AMOUNT = (
    "✏️ أرسل المبلغ الذي سيُضاف فعلاً لرصيد المستخدم\n(المطلوب في الطلب: {amount})"
)
PAYMENT_APPROVED = (
    "✅ <b>اعتُمد الشحن #{payment_id}</b>\n\n"
    "👤 {name}\n💵 أُضيف: {credited}\n💰 الرصيد الجديد: {balance}\n\n📨 أُشعر المستخدم."
)
PAYMENT_ASK_REJECT_REASON = (
    "❌ أرسل سبب رفض الطلب #{payment_id} (سيصل المستخدم كما تكتبه، فكن واضحاً):"
)
PAYMENT_REJECTED = "❌ رُفض الطلب #{payment_id}.\n📝 السبب: {reason}\n\n📨 أُشعر المستخدم."

# ============================ الطلبات ================================== #

ORDERS_TITLE = (
    "📦 <b>الطلبات — {filter_name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "العدد: {count} · الصفحة {page} من {pages}"
)
ORDERS_EMPTY = "📦 لا طلبات في هذا التصنيف."
ORDER_FILTER_ATTENTION = "⚠️ تحتاج تدخلاً"
ORDER_FILTER_ACTIVE = "⚙️ نشطة"
ORDER_FILTER_TODAY = "📅 اليوم"
ORDER_FILTER_ALL = "🗂 الكل"

ORDER_CARD = (
    "📦 <b>الطلب {code}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "👤 {name} (<code>{telegram_id}</code>)\n"
    "🛍 {service}\n"
    "🔗 {link}\n"
    "🔢 الكمية: {quantity}\n"
    "💵 التكلفة: {cost}\n"
    "📌 الحالة: {status}\n"
    "{progress_line}"
    "{provider_line}"
    "{error_line}"
    "{refund_line}"
    "📅 أُنشئ: {created}\n"
    "🔁 محاولات الإرسال: {attempts} · عمليات الفحص: {checks}"
)
ORDER_PROVIDER_LINE = "🏢 المزود: {provider} · رقمه: <code>{provider_order_id}</code>\n"
ORDER_PROGRESS_LINE = "📊 المنفَّذ: {delivered} · المتبقي: {remains}\n"
ORDER_ERROR_LINE = "⚠️ آخر خطأ: {error}\n"
ORDER_REFUND_LINE = "↩️ مسترجع: {amount}\n"

BTN_ORDER_RECHECK = "🔄 إعادة فحص الآن"
BTN_ORDER_CANCEL = "❌ إلغاء + استرجاع"
BTN_ORDER_FAIL = "⛔ تعليم كفاشل + استرجاع"
BTN_ORDER_LINK = "🔗 ربط رقم المزود"
BTN_ORDER_OVERRIDE = "🎚 تغيير الحالة يدوياً"
BTN_ORDER_USER = "👤 صاحب الطلب"

ORDER_RECHECK_RESULT = "🔄 نتيجة الفحص: {result}"
ORDER_ASK_CANCEL_REASON = "❌ أرسل سبب إلغاء الطلب {code} (سيُسترجع كامل المبلغ للمستخدم):"
ORDER_ACTION_CONFIRM = (
    "⚠️ <b>تأكيد {operation}</b>\n\n"
    "📦 {code}\n👤 {name}\n💵 سيُسترجع: {amount}\n📝 السبب: {reason}"
)
OP_ORDER_CANCEL = "الإلغاء"
OP_ORDER_FAIL = "تعليم الطلب كفاشل"
ORDER_CANCEL_DONE = "✅ أُلغي الطلب {code} واسترُجع {amount} للمستخدم."
ORDER_ASK_FAIL_REASON = "⛔ أرسل سبب اعتبار الطلب {code} فاشلاً (يُسترجع المبلغ للمستخدم):"
ORDER_FAIL_DONE = "⛔ عُلّم الطلب {code} كفاشل واسترُجع {amount}."
ORDER_ASK_PROVIDER_ID = (
    "🔗 أرسل رقم الطلب لدى المزود للطلب {code}\n"
    "(يُستخدم عندما يكون الطلب أُنشئ فعلاً عند المزود ولم يصلنا رقمه)."
)
ORDER_LINK_DONE = "✅ رُبط الطلب {code} برقم المزود: {provider_order_id}"
ORDER_ASK_OVERRIDE_REASON = (
    "📝 أرسل سبب التجاوز اليدوي (5 أحرف على الأقل) — يُسجَّل باسمك في سجل التدقيق:"
)
ORDER_OVERRIDE_TITLE = (
    "🎚 <b>تغيير حالة الطلب {code} يدوياً</b>\n\n"
    "الحالة الحالية: {status}\n\n"
    "⚠️ استخدم هذا فقط عند تعذّر المسار الآلي — كل تغيير يُسجَّل باسمك."
)
ORDER_OVERRIDE_DONE = "✅ أصبحت حالة الطلب {code}: {status}"
ORDER_NOT_OVERRIDABLE = "⚠️ لا يمكن الانتقال من الحالة الحالية إلى الحالة المطلوبة."

# ============================= الدعم =================================== #

TICKETS_TITLE = (
    "🎫 <b>تذاكر الدعم — {filter_name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "مفتوحة الآن: {open_count} · الصفحة {page} من {pages}"
)
TICKETS_EMPTY = "🎫 لا تذاكر في هذا التصنيف."
TICKET_FILTER_OPEN = "🟢 المفتوحة"
TICKET_FILTER_WAITING = "⏳ بانتظار الدعم"
TICKET_FILTER_MINE = "👤 المسندة لي"
TICKET_FILTER_CLOSED = "🔒 المغلقة"

TICKET_CARD = (
    "🎫 <b>التذكرة #{ticket_id}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "👤 {name} (<code>{telegram_id}</code>)\n"
    "📌 {subject}\n"
    "🗂 التصنيف: {category}\n"
    "📊 الحالة: {status}\n"
    "{order_line}"
    "{assigned_line}"
    "📅 آخر رسالة: {last_message}\n\n"
    "💬 <b>المحادثة:</b>\n{conversation}"
)
TICKET_ORDER_LINE = "📦 مرتبطة بالطلب: {code}\n"
TICKET_ASSIGNED_LINE = "👮 مسندة إلى: {admin}\n"
TICKET_MESSAGE_LINE = "{icon} <b>{sender}</b> — {when}\n{message}"
SENDER_USER = "المستخدم"
SENDER_ADMIN = "الدعم"
SENDER_SYSTEM = "النظام"

BTN_TICKET_REPLY = "💬 رد"
BTN_TICKET_CLOSE = "✖️ إغلاق"
BTN_TICKET_ASSIGN = "🏷 إسناد لي"
BTN_TICKET_USER = "👤 صاحب التذكرة"

TICKET_ASK_REPLY = "💬 أرسل ردك على التذكرة #{ticket_id} (يصل المستخدم كما تكتبه):"
TICKET_ASK_CLOSE_REASON = (
    "✖️ أرسل سبب إغلاق التذكرة #{ticket_id} (يُحفظ في التذكرة ويصل المستخدم):"
)
TICKET_REPLY_DONE = "✅ أُرسل الرد على التذكرة #{ticket_id}."
TICKET_ASSIGNED = "🏷 أُسندت التذكرة #{ticket_id} إليك."
TICKET_CLOSED = "✖️ أُغلقت التذكرة #{ticket_id}."

# ============================ الكتالوج ================================= #

CATALOG_HOME = (
    "🛍 <b>الكتالوج</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "التصنيفات: {categories} · الخدمات المفعّلة: {active_services}\n\n"
    "اختر تصنيفاً لعرض خدماته."
)
CATALOG_NO_CATEGORIES = "📂 لا توجد تصنيفات بعد."
BTN_CATEGORY_NEW = "➕ تصنيف جديد"
CATEGORY_ASK_NAME = "📂 أرسل اسم التصنيف الجديد (بالعربية):"
CATEGORY_ASK_EMOJI = "😀 أرسل أيقونة للتصنيف (إيموجي واحد)، أو تخطَّ لاستخدام 📦."
CATEGORY_CREATED = "✅ أُنشئ التصنيف: {name}"

CATALOG_SERVICES_TITLE = (
    "📂 <b>{category}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "عدد الخدمات: {count} · الصفحة {page} من {pages}\n\n"
    "⚪️ = معطّلة · 🟢 = مفعّلة"
)
CATALOG_SERVICES_EMPTY = "📭 لا خدمات في هذا التصنيف."

SERVICE_CARD = (
    "🛍 <b>{name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🆔 رقم الخدمة: {service_id}\n"
    "📂 التصنيف: {category}\n"
    "🏢 المزود: {provider} (رقم الخدمة لديه: {provider_service_id})\n"
    "💵 سعر الألف: {price}\n"
    "🏷 تكلفة الألف من المزود: {cost}\n"
    "📈 هامش الربح: {margin}\n"
    "🔢 الحدود: {min_quantity} — {max_quantity}\n"
    "📌 الحالة: {status}\n"
    "{archived_line}"
    "{description_line}"
)
SERVICE_STATUS_ACTIVE = "🟢 مفعّلة"
SERVICE_STATUS_INACTIVE = "⚪️ معطّلة"
SERVICE_ARCHIVED_LINE = "🗄 <b>مؤرشفة</b> — لا تظهر للعملاء\n"
SERVICE_DESCRIPTION_LINE = "\n📝 {description}"
SERVICE_UNKNOWN_PROVIDER = "غير معروف"
SERVICE_MARGIN_UNKNOWN = "غير محدد (تكلفة المزود غير مسجّلة)"

BTN_SERVICE_TOGGLE_ON = "🟢 تفعيل"
BTN_SERVICE_TOGGLE_OFF = "⚪️ تعطيل"
BTN_SERVICE_PRICE = "💵 تغيير السعر"
BTN_SERVICE_ARCHIVE = "🗄 أرشفة"

SERVICE_ASK_PRICE = (
    "💵 أرسل السعر الجديد لكل <b>1000</b> من خدمة:\n{name}\n\n"
    "السعر الحالي: {price}\n"
    "تكلفة المزود: {cost}"
)
SERVICE_PRICE_DONE = "✅ أصبح سعر الألف: {price}"
SERVICE_PRICE_BELOW_COST = (
    "⚠️ <b>تنبيه:</b> السعر الجديد أقل من تكلفة المزود — ستبيع بخسارة.\n"
    "اضغط «نعم، نفّذ» إن كنت متأكداً."
)
SERVICE_TOGGLED_ON = "🟢 فُعّلت الخدمة."
SERVICE_TOGGLED_OFF = "⚪️ عُطّلت الخدمة."
SERVICE_ARCHIVED = "🗄 أُرشفت الخدمة ولم تعد تظهر للعملاء."
SERVICE_ARCHIVE_CONFIRM = (
    "⚠️ <b>تأكيد الأرشفة</b>\n\n{name}\n\n"
    "الخدمة ستختفي من واجهة العملاء، وتبقى طلباتها التاريخية كما هي."
)

# =========================== الإعدادات ================================= #

SETTINGS_HOME = (
    "⚙️ <b>الإعدادات</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "وضع الصيانة: {maintenance}\n\n"
    "اختر مجموعة لعرض مفاتيحها."
)
SETTINGS_GROUP_TITLE = (
    "⚙️ <b>إعدادات: {group}</b>\n━━━━━━━━━━━━━━━━━━━━\nالصفحة {page} من {pages}\n\n{lines}"
)
SETTINGS_GROUP_EMPTY = "⚙️ لا مفاتيح في هذه المجموعة."
SETTING_LINE = "<b>{name}</b>\n   <code>{key}</code> = <code>{value}</code>"
SETTING_ASK_VALUE = (
    "⚙️ <b>{name}</b>\n"
    "<code>{key}</code>\n\n"
    "القيمة الحالية: <code>{value}</code>\n"
    "النوع: {value_type}\n"
    "{description}\n\n"
    "أرسل القيمة الجديدة:"
)
SETTING_UPDATED = "✅ حُفظت القيمة الجديدة لـ <code>{key}</code>:\n<code>{value}</code>"
SETTING_NOT_EDITABLE = "🔒 هذا المفتاح غير قابل للتعديل من الواجهة."
MAINTENANCE_ON = "🚧 مفعّل"
MAINTENANCE_OFF = "✅ متوقف"
BTN_MAINTENANCE_ON = "🚧 تفعيل وضع الصيانة"
BTN_MAINTENANCE_OFF = "✅ إيقاف وضع الصيانة"
MAINTENANCE_CONFIRM_ON = (
    "⚠️ <b>تفعيل وضع الصيانة</b>\n\n"
    "سيتوقف المستخدمون العاديون عن استخدام البوت فوراً (الإداريون يستمرون).\n"
    "المهام الدورية تبقى تعمل."
)
MAINTENANCE_CONFIRM_OFF = "✅ <b>إيقاف وضع الصيانة</b>\n\nسيعود البوت للعمل الطبيعي لكل المستخدمين."
MAINTENANCE_TOGGLED_ON = "🚧 فُعّل وضع الصيانة — المستخدمون العاديون لن يستطيعوا الاستخدام."
MAINTENANCE_TOGGLED_OFF = "✅ أُوقف وضع الصيانة — البوت يعمل للجميع."

# ============================ السجلات ================================== #

LOGS_HOME = "📝 <b>السجلات</b>\n━━━━━━━━━━━━━━━━━━━━\n\nاختر السجل الذي تريد مراجعته."
BTN_LOG_AUDIT = "🧾 سجل التدقيق"
BTN_LOG_ERRORS = "❗ سجل الأخطاء"

AUDIT_TITLE = "🧾 <b>سجل التدقيق</b>\n━━━━━━━━━━━━━━━━━━━━\nالصفحة {page} من {pages}\n\n{lines}"
AUDIT_EMPTY = "🧾 لا عمليات مسجّلة بعد."
AUDIT_LINE = "{icon} <b>{action}</b>\n   👮 {admin} · 🎯 {target}\n   🕒 {when}"

ERRORS_TITLE = "❗ <b>آخر الأخطاء</b>\n━━━━━━━━━━━━━━━━━━━━\nالصفحة {page}\n\n{lines}"
ERRORS_EMPTY = "✅ لا أخطاء مسجّلة — النظام نظيف."
ERROR_LINE = "<b>{level}</b> · {source}\n   {message}\n   🕒 {when}"

# ======================= تسميات مساعدة للعرض =========================== #

#: اسم كل دور كما يُعرض في البطاقات والسجلات
ROLE_NAMES: dict[str, str] = {
    "user": "👤 مستخدم عادي",
    "support": "🎧 دعم فني",
    "admin": "👮 أدمن",
    "super_admin": "👑 أدمن أعلى",
}

#: الأدوار المتاحة للإسناد من الواجهة
#: (الدور الأعلى `super_admin` لا يُمنح من الواجهة إطلاقاً — يُضبط من سكربت الإدارة)
ASSIGNABLE_ROLES: dict[str, str] = {
    "user": "👤 مستخدم عادي",
    "support": "🎧 دعم فني",
    "admin": "👮 أدمن",
}

#: أيقونة لكل نوع إجراء في سجل التدقيق (تُطابق بادئة اسم الإجراء)
AUDIT_ICONS: dict[str, str] = {
    "user": "👤",
    "wallet": "💰",
    "payment": "💳",
    "order": "📦",
    "service": "🛍",
    "category": "📂",
    "provider": "🏢",
    "ticket": "🎫",
    "setting": "⚙️",
    "security": "🔐",
    "system": "🖥",
}
```

### `keyboards/admin_kb.py`

```python
"""
لوحات أزرار لوحة التحكم.

قاعدتان ملزمتان في هذا الملف:

1. **لا يظهر زر لا يملك الأدمن صلاحيته.** كل باني لوحة يستقبل مجموعة صلاحيات
   المستخدم (`perms`) ويبني الأزرار على أساسها. هذا لا يُغني عن فحص الصلاحية
   داخل المعالج نفسه (الزر قد يُضغط من رسالة قديمة بعد سحب الصلاحية) — الفحصان
   مطلوبان معاً.
2. **لا زر بلا معالج.** كل `callback_data` هنا يقابله معالج مسجَّل في
   `handlers/registry.py`، ويتحقق من ذلك اختبار `test_no_dead_buttons`.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from core.enums import OrderStatus
from core.order_state import allowed_next
from core.permissions import Permission
from database.models import (
    Order,
    Payment,
    Service,
    ServiceCategory,
    Setting,
    SupportTicket,
    User,
)
from keyboards.callback_data import (
    NS_ADM_CAT,
    NS_ADM_LOG,
    NS_ADM_ORD,
    NS_ADM_PAY,
    NS_ADM_SET,
    NS_ADM_TKT,
    NS_ADM_USERS,
    NS_ADMIN,
    NS_FLOW,
    pack,
)
from keyboards.common_kb import home_button, pagination_row
from texts import admin_ar as t
from utils.formatters import money_text, order_status_text, safe, ticket_status_text

#: تصفية قوائم الطلبات في لوحة الأدمن (الرمز ⇐ الاسم والحالات المشمولة)
ADMIN_ORDER_FILTERS: dict[str, tuple[str, tuple[str, ...]]] = {
    "att": (
        t.ORDER_FILTER_ATTENTION,
        (OrderStatus.SUBMIT_UNCERTAIN, OrderStatus.FAILED),
    ),
    "act": (
        t.ORDER_FILTER_ACTIVE,
        (
            OrderStatus.PENDING,
            OrderStatus.SUBMITTING,
            OrderStatus.SUBMITTED,
            OrderStatus.IN_PROGRESS,
        ),
    ),
    "all": (t.ORDER_FILTER_ALL, ()),
}

#: تصفية قوائم التذاكر في لوحة الأدمن
ADMIN_TICKET_FILTERS: dict[str, str] = {
    "open": t.TICKET_FILTER_OPEN,
    "wait": t.TICKET_FILTER_WAITING,
    "mine": t.TICKET_FILTER_MINE,
    "closed": t.TICKET_FILTER_CLOSED,
}


# ============================= أدوات داخلية ============================= #


def _panel_row(*, with_home: bool = True) -> list[InlineKeyboardButton]:
    """صف سفلي موحّد: رجوع إلى لوحة التحكم (+ القائمة الرئيسية للمستخدم)."""
    row = [InlineKeyboardButton(t.BTN_BACK_PANEL, callback_data=pack(NS_ADMIN, "home"))]
    if with_home:
        row.append(home_button())
    return row


def _back_row(namespace: str, action: str, *args: object) -> list[InlineKeyboardButton]:
    """صف رجوع إلى شاشة أدمن محددة + لوحة التحكم."""
    return [
        InlineKeyboardButton("🔙 رجوع", callback_data=pack(namespace, action, *args)),
        InlineKeyboardButton(t.BTN_BACK_PANEL, callback_data=pack(NS_ADMIN, "home")),
    ]


def _cancel_row() -> list[InlineKeyboardButton]:
    """صف إلغاء داخل محادثات الأدمن."""
    return [InlineKeyboardButton("❌ إلغاء", callback_data=pack(NS_FLOW, "cancel"))]


def back_panel_kb() -> InlineKeyboardMarkup:
    """لوحة فيها الرجوع إلى لوحة التحكم فقط (تُرفق برسائل النتائج)."""
    return InlineKeyboardMarkup([_panel_row()])


def cancel_only_kb() -> InlineKeyboardMarkup:
    """لوحة فيها زر إلغاء فقط (تُرفق بأسئلة محادثات الأدمن)."""
    return InlineKeyboardMarkup([_cancel_row()])


def confirm_cancel_kb(label: str = t.BTN_CONFIRM_DANGER) -> InlineKeyboardMarkup:
    """لوحة تأكيد عملية خطيرة (تأكيد صريح + إلغاء)."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(label, callback_data=pack(NS_FLOW, "confirm"))], _cancel_row()]
    )


def skip_cancel_kb() -> InlineKeyboardMarkup:
    """لوحة تخطي خطوة اختيارية داخل محادثات الأدمن."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⏭ تخطي", callback_data=pack(NS_FLOW, "skip"))], _cancel_row()]
    )


# ============================ القائمة الرئيسية ========================== #


def admin_menu_kb(perms: set[str], *, pending_payments: int = 0, open_tickets: int = 0) -> InlineKeyboardMarkup:
    """
    قائمة لوحة التحكم — تُبنى حسب صلاحيات هذا الأدمن تحديداً.

    المدخلات:
        perms            : مجموعة صلاحيات المستخدم الحالية.
        pending_payments : عدد طلبات الشحن المعلّقة (يظهر كعدّاد على الزر).
        open_tickets     : عدد التذاكر المفتوحة (عدّاد على الزر).
    """
    rows: list[list[InlineKeyboardButton]] = []
    current: list[InlineKeyboardButton] = []

    def add(button: InlineKeyboardButton) -> None:
        """إضافة زر مع ترتيب الأزرار في صفوف من اثنين."""
        current.append(button)
        if len(current) == 2:
            rows.append(list(current))
            current.clear()

    if Permission.USERS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_USERS, callback_data=pack(NS_ADM_USERS, "home")))
    if Permission.PAYMENTS_VIEW in perms:
        label = t.MENU_PAYMENTS + (f" ({pending_payments})" if pending_payments else "")
        add(InlineKeyboardButton(label, callback_data=pack(NS_ADM_PAY, "list", 1)))
    if Permission.ORDERS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_ORDERS, callback_data=pack(NS_ADM_ORD, "list", "att", 1)))
    if Permission.TICKETS_VIEW in perms:
        label = t.MENU_TICKETS + (f" ({open_tickets})" if open_tickets else "")
        add(InlineKeyboardButton(label, callback_data=pack(NS_ADM_TKT, "list", "open", 1)))
    if Permission.SERVICES_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_CATALOG, callback_data=pack(NS_ADM_CAT, "home")))
    if Permission.SETTINGS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_SETTINGS, callback_data=pack(NS_ADM_SET, "home")))
    if Permission.LOGS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_LOGS, callback_data=pack(NS_ADM_LOG, "home")))
    if Permission.STATS_VIEW in perms:
        add(InlineKeyboardButton(t.MENU_HEALTH, callback_data=pack(NS_ADMIN, "health")))

    if current:
        rows.append(list(current))

    rows.append(
        [
            InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADMIN, "home")),
            home_button(),
        ]
    )
    return InlineKeyboardMarkup(rows)


def health_kb() -> InlineKeyboardMarkup:
    """أزرار شاشة صحة النظام."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t.BTN_REFRESH, callback_data=pack(NS_ADMIN, "health"))], _panel_row()]
    )


# ============================= المستخدمون =============================== #


def users_home_kb(perms: set[str]) -> InlineKeyboardMarkup:
    """شاشة المستخدمين: بحث + رجوع."""
    rows = [[InlineKeyboardButton(t.BTN_USER_SEARCH, callback_data=pack(NS_ADM_USERS, "search"))]]
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def user_results_kb(users: list[User]) -> InlineKeyboardMarkup:
    """نتائج البحث: زر لكل مستخدم."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'🚫 ' if user.is_banned else ''}{user.display_name} · {user.telegram_id}",
                callback_data=pack(NS_ADM_USERS, "view", user.id),
            )
        ]
        for user in users
    ]
    rows.append(
        [InlineKeyboardButton(t.BTN_USER_SEARCH, callback_data=pack(NS_ADM_USERS, "search"))]
    )
    rows.append(_back_row(NS_ADM_USERS, "home"))
    return InlineKeyboardMarkup(rows)


def user_card_kb(user: User, perms: set[str]) -> InlineKeyboardMarkup:
    """أزرار بطاقة المستخدم حسب الصلاحيات المتاحة."""
    rows: list[list[InlineKeyboardButton]] = []

    money_row: list[InlineKeyboardButton] = []
    if Permission.USERS_BALANCE_CREDIT in perms:
        money_row.append(
            InlineKeyboardButton(
                t.BTN_USER_CREDIT, callback_data=pack(NS_ADM_USERS, "credit", user.id)
            )
        )
    if Permission.USERS_BALANCE_DEBIT in perms:
        money_row.append(
            InlineKeyboardButton(
                t.BTN_USER_DEBIT, callback_data=pack(NS_ADM_USERS, "debit", user.id)
            )
        )
    if money_row:
        rows.append(money_row)

    state_row: list[InlineKeyboardButton] = []
    if user.is_banned and Permission.USERS_UNBAN in perms:
        state_row.append(
            InlineKeyboardButton(
                t.BTN_USER_UNBAN, callback_data=pack(NS_ADM_USERS, "unban", user.id)
            )
        )
    elif not user.is_banned and Permission.USERS_BAN in perms:
        state_row.append(
            InlineKeyboardButton(t.BTN_USER_BAN, callback_data=pack(NS_ADM_USERS, "ban", user.id))
        )
    if Permission.USERS_NOTE in perms:
        state_row.append(
            InlineKeyboardButton(t.BTN_USER_NOTE, callback_data=pack(NS_ADM_USERS, "note", user.id))
        )
    if state_row:
        rows.append(state_row)

    if Permission.USERS_ROLE_CHANGE in perms:
        rows.append(
            [InlineKeyboardButton(t.BTN_USER_ROLE, callback_data=pack(NS_ADM_USERS, "role", user.id))]
        )

    history_row: list[InlineKeyboardButton] = []
    if Permission.ORDERS_VIEW in perms:
        history_row.append(
            InlineKeyboardButton(
                t.BTN_USER_ORDERS, callback_data=pack(NS_ADM_USERS, "orders", user.id, 1)
            )
        )
    history_row.append(
        InlineKeyboardButton(t.BTN_USER_TX, callback_data=pack(NS_ADM_USERS, "tx", user.id, 1))
    )
    rows.append(history_row)

    rows.append(_back_row(NS_ADM_USERS, "home"))
    return InlineKeyboardMarkup(rows)


def user_role_kb(user: User) -> InlineKeyboardMarkup:
    """أزرار اختيار الدور الجديد للمستخدم."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'• ' if user.role == code else ''}{label}",
                callback_data=pack(NS_ADM_USERS, "setrole", user.id, code),
            )
        ]
        for code, label in t.ASSIGNABLE_ROLES.items()
    ]
    rows.append(_back_row(NS_ADM_USERS, "view", user.id))
    return InlineKeyboardMarkup(rows)


def user_role_confirm_kb(user_id: int, role_code: str) -> InlineKeyboardMarkup:
    """تأكيد ثانٍ قبل تغيير الدور (إجراء خطير يغيّر الصلاحيات فوراً)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    t.BTN_CONFIRM_DANGER,
                    callback_data=pack(NS_ADM_USERS, "roleok", user_id, role_code),
                )
            ],
            [InlineKeyboardButton("🔙 رجوع", callback_data=pack(NS_ADM_USERS, "role", user_id))],
        ]
    )


def user_list_nav_kb(
    action: str, user_id: int, *, page: int, total_pages: int
) -> InlineKeyboardMarkup:
    """ترقيم قوائم طلبات/معاملات مستخدم بعينه."""
    rows: list[list[InlineKeyboardButton]] = []
    nav = pagination_row(
        NS_ADM_USERS, action, page=page, total_pages=total_pages, prefix_args=(user_id,)
    )
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_USERS, "view", user_id))
    return InlineKeyboardMarkup(rows)


# ============================= المدفوعات ================================ #


def payments_list_kb(
    payments: list[Payment], *, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """قائمة طلبات الشحن المعلّقة."""
    rows = [
        [
            InlineKeyboardButton(
                f"#{payment.id} · {money_text(payment.amount_units, symbol)}",
                callback_data=pack(NS_ADM_PAY, "view", payment.id),
            )
        ]
        for payment in payments
    ]
    nav = pagination_row(NS_ADM_PAY, "list", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def payment_card_kb(payment: Payment, perms: set[str], *, is_pending: bool) -> InlineKeyboardMarkup:
    """أزرار بطاقة طلب الشحن (الاعتماد/الرفض تظهر للمعلّق فقط)."""
    rows: list[list[InlineKeyboardButton]] = []
    if payment.proof_file_id:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_PAYMENT_PROOF, callback_data=pack(NS_ADM_PAY, "proof", payment.id)
                )
            ]
        )
    if is_pending:
        action_row: list[InlineKeyboardButton] = []
        if Permission.PAYMENTS_APPROVE in perms:
            action_row.append(
                InlineKeyboardButton(
                    t.BTN_PAYMENT_APPROVE, callback_data=pack(NS_ADM_PAY, "ok", payment.id)
                )
            )
        if Permission.PAYMENTS_REJECT in perms:
            action_row.append(
                InlineKeyboardButton(
                    t.BTN_PAYMENT_REJECT, callback_data=pack(NS_ADM_PAY, "no", payment.id)
                )
            )
        if action_row:
            rows.append(action_row)
    if Permission.USERS_VIEW in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    "👤 صاحب الطلب", callback_data=pack(NS_ADM_USERS, "view", payment.user_id)
                )
            ]
        )
    rows.append(_back_row(NS_ADM_PAY, "list", 1))
    return InlineKeyboardMarkup(rows)


def payment_approve_kb() -> InlineKeyboardMarkup:
    """تأكيد الاعتماد مع إمكانية تعديل المبلغ المضاف."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_CONFIRM_DANGER, callback_data=pack(NS_FLOW, "confirm"))],
            [InlineKeyboardButton(t.BTN_EDIT_AMOUNT, callback_data=pack(NS_ADM_PAY, "amount"))],
            _cancel_row(),
        ]
    )


# ============================== الطلبات ================================= #


def admin_orders_filters_row(current: str) -> list[InlineKeyboardButton]:
    """صف تصفية قوائم الطلبات."""
    return [
        InlineKeyboardButton(
            f"{'• ' if code == current else ''}{label}",
            callback_data=pack(NS_ADM_ORD, "list", code, 1),
        )
        for code, (label, _statuses) in ADMIN_ORDER_FILTERS.items()
    ]


def admin_orders_kb(
    orders: list[Order], *, filter_code: str, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """قائمة الطلبات في لوحة الأدمن."""
    rows = [
        [
            InlineKeyboardButton(
                f"{order_status_text(order.status).split(' ', 1)[0]} "
                f"{order.public_code or order.id} · {money_text(order.cost_units, symbol)}",
                callback_data=pack(NS_ADM_ORD, "view", order.id, filter_code, page),
            )
        ]
        for order in orders
    ]
    rows.append(admin_orders_filters_row(filter_code))
    nav = pagination_row(
        NS_ADM_ORD, "list", page=page, total_pages=total_pages, prefix_args=(filter_code,)
    )
    if nav:
        rows.append(nav)
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def admin_order_card_kb(
    order: Order, perms: set[str], *, filter_code: str, page: int
) -> InlineKeyboardMarkup:
    """أزرار بطاقة الطلب الإدارية (كل زر مشروط بصلاحيته وبحالة الطلب)."""
    rows: list[list[InlineKeyboardButton]] = []
    is_final = not allowed_next(order.status)

    first_row: list[InlineKeyboardButton] = []
    if Permission.ORDERS_RECHECK in perms and order.provider_order_id and not is_final:
        first_row.append(
            InlineKeyboardButton(
                t.BTN_ORDER_RECHECK, callback_data=pack(NS_ADM_ORD, "recheck", order.id)
            )
        )
    if Permission.ORDERS_LINK_PROVIDER_ID in perms and order.status == OrderStatus.SUBMIT_UNCERTAIN:
        first_row.append(
            InlineKeyboardButton(
                t.BTN_ORDER_LINK, callback_data=pack(NS_ADM_ORD, "link", order.id)
            )
        )
    if first_row:
        rows.append(first_row)

    danger_row: list[InlineKeyboardButton] = []
    if Permission.ORDERS_CANCEL in perms and not is_final:
        danger_row.append(
            InlineKeyboardButton(
                t.BTN_ORDER_CANCEL, callback_data=pack(NS_ADM_ORD, "cancel", order.id)
            )
        )
    if Permission.ORDERS_REFUND in perms and not is_final:
        danger_row.append(
            InlineKeyboardButton(t.BTN_ORDER_FAIL, callback_data=pack(NS_ADM_ORD, "fail", order.id))
        )
    if danger_row:
        rows.append(danger_row)

    if Permission.ORDERS_STATUS_OVERRIDE in perms and allowed_next(order.status):
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_ORDER_OVERRIDE, callback_data=pack(NS_ADM_ORD, "force", order.id)
                )
            ]
        )

    if Permission.USERS_VIEW in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_ORDER_USER, callback_data=pack(NS_ADM_USERS, "view", order.user_id)
                )
            ]
        )

    rows.append(_back_row(NS_ADM_ORD, "list", filter_code, page))
    return InlineKeyboardMarkup(rows)


def order_override_kb(order: Order) -> InlineKeyboardMarkup:
    """أزرار الحالات المسموح الانتقال إليها من الحالة الحالية فقط."""
    rows = [
        [
            InlineKeyboardButton(
                order_status_text(status),
                callback_data=pack(NS_ADM_ORD, "setst", order.id, status),
            )
        ]
        for status in sorted(allowed_next(order.status))
    ]
    rows.append(_back_row(NS_ADM_ORD, "view", order.id, "all", 1))
    return InlineKeyboardMarkup(rows)


# =============================== الدعم ================================== #


def admin_tickets_filters_row(current: str) -> list[InlineKeyboardButton]:
    """صف تصفية قوائم التذاكر."""
    return [
        InlineKeyboardButton(
            f"{'• ' if code == current else ''}{label}",
            callback_data=pack(NS_ADM_TKT, "list", code, 1),
        )
        for code, label in ADMIN_TICKET_FILTERS.items()
    ]


def admin_tickets_kb(
    tickets: list[SupportTicket], *, filter_code: str, page: int, total_pages: int
) -> InlineKeyboardMarkup:
    """قائمة التذاكر في لوحة الأدمن."""
    rows = [
        [
            InlineKeyboardButton(
                f"{ticket_status_text(ticket.status).split(' ', 1)[0]} #{ticket.id} · "
                f"{safe(ticket.subject, limit=28)}",
                callback_data=pack(NS_ADM_TKT, "view", ticket.id),
            )
        ]
        for ticket in tickets
    ]
    rows.append(admin_tickets_filters_row(filter_code))
    nav = pagination_row(
        NS_ADM_TKT, "list", page=page, total_pages=total_pages, prefix_args=(filter_code,)
    )
    if nav:
        rows.append(nav)
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def admin_ticket_card_kb(
    ticket: SupportTicket, perms: set[str], *, filter_code: str = "open"
) -> InlineKeyboardMarkup:
    """أزرار بطاقة التذكرة الإدارية."""
    rows: list[list[InlineKeyboardButton]] = []
    action_row: list[InlineKeyboardButton] = []
    if ticket.is_open and Permission.TICKETS_REPLY in perms:
        action_row.append(
            InlineKeyboardButton(
                t.BTN_TICKET_REPLY, callback_data=pack(NS_ADM_TKT, "reply", ticket.id)
            )
        )
    if ticket.is_open and Permission.TICKETS_CLOSE in perms:
        action_row.append(
            InlineKeyboardButton(
                t.BTN_TICKET_CLOSE, callback_data=pack(NS_ADM_TKT, "close", ticket.id)
            )
        )
    if action_row:
        rows.append(action_row)

    if ticket.is_open and Permission.TICKETS_ASSIGN in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_TICKET_ASSIGN, callback_data=pack(NS_ADM_TKT, "assign", ticket.id)
                )
            ]
        )
    if Permission.USERS_VIEW in perms:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_TICKET_USER, callback_data=pack(NS_ADM_USERS, "view", ticket.user_id)
                )
            ]
        )
    rows.append(_back_row(NS_ADM_TKT, "list", filter_code, 1))
    return InlineKeyboardMarkup(rows)


# ============================== الكتالوج ================================ #


def catalog_home_kb(categories: list[ServiceCategory], perms: set[str]) -> InlineKeyboardMarkup:
    """شاشة الكتالوج: التصنيفات + إضافة تصنيف."""
    rows = [
        [
            InlineKeyboardButton(
                category.title, callback_data=pack(NS_ADM_CAT, "cat", category.id, 1)
            )
        ]
        for category in categories
    ]
    if Permission.SERVICES_CREATE in perms:
        rows.append(
            [InlineKeyboardButton(t.BTN_CATEGORY_NEW, callback_data=pack(NS_ADM_CAT, "newcat"))]
        )
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def catalog_services_kb(
    services: list[Service], *, category_id: int, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """قائمة خدمات تصنيف في لوحة الأدمن (مع مؤشر التفعيل)."""
    rows = [
        [
            InlineKeyboardButton(
                f"{'🟢' if service.is_active else '⚪️'} {safe(service.name, limit=26)} · "
                f"{money_text(service.price_per_1000_units, symbol)}",
                callback_data=pack(NS_ADM_CAT, "svc", service.id),
            )
        ]
        for service in services
    ]
    nav = pagination_row(
        NS_ADM_CAT, "cat", page=page, total_pages=total_pages, prefix_args=(category_id,)
    )
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_CAT, "home"))
    return InlineKeyboardMarkup(rows)


def service_card_kb(service: Service, perms: set[str]) -> InlineKeyboardMarkup:
    """أزرار بطاقة الخدمة الإدارية."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    if Permission.SERVICES_UPDATE in perms and not service.is_archived:
        label = t.BTN_SERVICE_TOGGLE_OFF if service.is_active else t.BTN_SERVICE_TOGGLE_ON
        row.append(InlineKeyboardButton(label, callback_data=pack(NS_ADM_CAT, "toggle", service.id)))
    if Permission.SERVICES_PRICE in perms and not service.is_archived:
        row.append(
            InlineKeyboardButton(
                t.BTN_SERVICE_PRICE, callback_data=pack(NS_ADM_CAT, "price", service.id)
            )
        )
    if row:
        rows.append(row)
    if Permission.SERVICES_ARCHIVE in perms and not service.is_archived:
        rows.append(
            [
                InlineKeyboardButton(
                    t.BTN_SERVICE_ARCHIVE, callback_data=pack(NS_ADM_CAT, "archive", service.id)
                )
            ]
        )
    rows.append(_back_row(NS_ADM_CAT, "cat", service.category_id, 1))
    return InlineKeyboardMarkup(rows)


# ============================= الإعدادات ================================ #


def settings_home_kb(
    groups: list[str], perms: set[str], *, maintenance_on: bool
) -> InlineKeyboardMarkup:
    """مجموعات الإعدادات + مفتاح وضع الصيانة."""
    rows = [
        [InlineKeyboardButton(f"⚙️ {group}", callback_data=pack(NS_ADM_SET, "group", group, 1))]
        for group in groups
    ]
    if Permission.SETTINGS_MAINTENANCE in perms:
        label = t.BTN_MAINTENANCE_OFF if maintenance_on else t.BTN_MAINTENANCE_ON
        rows.append([InlineKeyboardButton(label, callback_data=pack(NS_ADM_SET, "maint"))])
    rows.append(_panel_row())
    return InlineKeyboardMarkup(rows)


def settings_group_kb(
    settings: list[Setting], *, group: str, page: int, total_pages: int, perms: set[str]
) -> InlineKeyboardMarkup:
    """مفاتيح مجموعة إعدادات (القابل للتعديل فقط يصبح زراً)."""
    rows: list[list[InlineKeyboardButton]] = []
    if Permission.SETTINGS_UPDATE in perms:
        rows.extend(
            [
                [
                    InlineKeyboardButton(
                        f"✏️ {safe(setting.name_ar or setting.key, limit=32)}",
                        callback_data=pack(NS_ADM_SET, "edit", setting.key),
                    )
                ]
                for setting in settings
                if setting.is_editable
            ]
        )
    nav = pagination_row(
        NS_ADM_SET, "group", page=page, total_pages=total_pages, prefix_args=(group,)
    )
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_SET, "home"))
    return InlineKeyboardMarkup(rows)


# ============================== السجلات ================================= #


def logs_home_kb() -> InlineKeyboardMarkup:
    """اختيار نوع السجل."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t.BTN_LOG_AUDIT, callback_data=pack(NS_ADM_LOG, "audit", 1))],
            [InlineKeyboardButton(t.BTN_LOG_ERRORS, callback_data=pack(NS_ADM_LOG, "errors", 1))],
            _panel_row(),
        ]
    )


def logs_page_kb(action: str, *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """ترقيم صفحات السجلات."""
    rows: list[list[InlineKeyboardButton]] = []
    nav = pagination_row(NS_ADM_LOG, action, page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(_back_row(NS_ADM_LOG, "home"))
    return InlineKeyboardMarkup(rows)
```

### `keyboards/callback_data.py`

```python
"""
ترميز وفك بيانات الأزرار (callback_data) بشكل مُهيكل وآمن.

لماذا ملف مستقل؟
    تيليجرام يسمح بـ64 بايت فقط لكل `callback_data`، وأي زر قديم في محادثة
    مستخدم قد يُضغط بعد تحديث البوت. لذلك نعتمد صيغة واحدة في كل المشروع:

        namespace:action:arg1:arg2...:vN

    • `namespace` يحدد الشاشة (cat / ord / wal / dep / sup / acc / nav / flow).
    • `action` يحدد الإجراء داخل الشاشة.
    • `vN` لاحقة الإصدار؛ إذا تغيّرت بنية الأزرار مستقبلاً نرفع الرقم،
      فتُرفض الأزرار القديمة برسالة واضحة بدل تنفيذ إجراء خاطئ.

قواعد ملزِمة:
    • ممنوع زر بلا معنى: كل `callback_data` يُبنى من هنا وله معالج مسجَّل
      (يتحقق من ذلك اختبار `test_no_dead_buttons`).
    • ممنوع تمرير نص حر من المستخدم داخل `callback_data` (طوله غير مضمون).
"""

from __future__ import annotations

from dataclasses import dataclass

#: إصدار بنية الأزرار الحالي — يُلحق بكل زر
CALLBACK_VERSION: int = 1

#: الحد الأقصى الذي تسمح به تيليجرام لحجم callback_data (بايت)
MAX_CALLBACK_BYTES: int = 64

#: الفاصل بين أجزاء الزر
SEPARATOR: str = ":"


class CallbackError(ValueError):
    """خطأ في بناء أو قراءة بيانات زر (بنية غير صحيحة أو طول زائد)."""


@dataclass(frozen=True, slots=True)
class Callback:
    """بيانات زر بعد فكّها: المساحة، الإجراء، الوسائط، الإصدار."""

    namespace: str
    action: str
    args: tuple[str, ...]
    version: int

    def arg(self, index: int, default: str = "") -> str:
        """قراءة وسيط نصي بموضعه مع قيمة افتراضية إن لم يوجد."""
        if index < len(self.args):
            return self.args[index]
        return default

    def int_arg(self, index: int, default: int = 0) -> int:
        """قراءة وسيط رقمي بموضعه (يُعيد الافتراضي إن كان غير رقمي)."""
        raw = self.arg(index)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    @property
    def is_current_version(self) -> bool:
        """هل هذا الزر من الإصدار الحالي لبنية الأزرار؟"""
        return self.version == CALLBACK_VERSION


def pack(namespace: str, action: str, *args: object) -> str:
    """
    بناء `callback_data` مُهيكلة والتحقق من صلاحيتها.

    المدخلات:
        namespace : مساحة الشاشة (حروف صغيرة بلا فواصل).
        action    : اسم الإجراء.
        args      : وسائط إضافية (أرقام أو كلمات قصيرة بلا الفاصل `:`).

    المخرجات: نص جاهز لوضعه في زر.

    الاستثناءات:
        CallbackError : وجود الفاصل داخل جزء، أو تجاوز حد 64 بايت.
    """
    parts = [namespace, action, *[str(arg) for arg in args]]
    for part in parts:
        if SEPARATOR in part:
            raise CallbackError(f"جزء زر يحتوي الفاصل الممنوع '{SEPARATOR}': {part!r}")
        if part == "":
            raise CallbackError("جزء زر فارغ غير مسموح")
    data = SEPARATOR.join([*parts, f"v{CALLBACK_VERSION}"])
    if len(data.encode("utf-8")) > MAX_CALLBACK_BYTES:
        raise CallbackError(f"طول callback_data تجاوز {MAX_CALLBACK_BYTES} بايت: {data!r}")
    return data


def unpack(data: str | None) -> Callback:
    """
    فكّ `callback_data` إلى أجزائها.

    المخرجات: كائن `Callback`؛ والإصدار يكون 0 إذا كان الزر قديماً بلا لاحقة إصدار.

    الاستثناءات:
        CallbackError : البيانات فارغة أو لا تحوي مساحة وإجراءً.
    """
    if not data:
        raise CallbackError("callback_data فارغة")
    parts = data.split(SEPARATOR)
    if len(parts) < 2:
        raise CallbackError(f"callback_data غير مُهيكلة: {data!r}")

    version = 0
    if parts[-1].startswith("v") and parts[-1][1:].isdigit():
        version = int(parts[-1][1:])
        parts = parts[:-1]

    namespace, action, *args = parts
    return Callback(namespace=namespace, action=action, args=tuple(args), version=version)


def pattern(namespace: str, action: str | None = None) -> str:
    """
    بناء تعبير نمطي لتسجيل المعالج على مساحة (أو مساحة+إجراء) بعينها.

    مثال: `pattern("cat")` ⇒ `^cat:` و`pattern("cat", "open")` ⇒ `^cat:open(:|$)`.
    """
    if action is None:
        return rf"^{namespace}{SEPARATOR}"
    return rf"^{namespace}{SEPARATOR}{action}({SEPARATOR}|$)"


# ----------------------- مساحات الأزرار المعتمدة ------------------------- #

NS_NAV = "nav"      # التنقل بين الشاشات الرئيسية
NS_CATALOG = "cat"  # التصنيفات والخدمات
NS_NEW = "new"      # بدء طلب جديد
NS_ORDERS = "ord"   # طلباتي
NS_WALLET = "wal"   # المحفظة
NS_DEPOSIT = "dep"  # شحن الرصيد
NS_SUPPORT = "sup"  # الدعم الفني
NS_ACCOUNT = "acc"  # الحساب والإشعارات
NS_FLOW = "flow"    # أزرار داخل المحادثات (تأكيد/إلغاء/تخطي/رجوع)

# ----------------------- مساحات لوحة الأدمن ----------------------------- #
# مختصرة عمداً: حدّ تيليجرام 64 بايت، وبعض الأزرار تحمل معرفات طويلة.

NS_ADMIN = "adm"      # لوحة التحكم والصحة العامة
NS_ADM_USERS = "au"   # إدارة المستخدمين
NS_ADM_PAY = "ap"     # مراجعة طلبات الشحن
NS_ADM_ORD = "ao"     # إدارة الطلبات
NS_ADM_TKT = "at"     # تذاكر الدعم (جانب الأدمن)
NS_ADM_CAT = "ac"     # إدارة الكتالوج (تصنيفات/خدمات)
NS_ADM_SET = "as"     # الإعدادات
NS_ADM_LOG = "al"     # السجلات (تدقيق/أخطاء)

#: كل المساحات المعروفة — تُستخدم في اختبار «لا أزرار بلا وظيفة»
ALL_NAMESPACES: tuple[str, ...] = (
    NS_NAV, NS_CATALOG, NS_NEW, NS_ORDERS, NS_WALLET, NS_DEPOSIT, NS_SUPPORT, NS_ACCOUNT, NS_FLOW,
    NS_ADMIN, NS_ADM_USERS, NS_ADM_PAY, NS_ADM_ORD, NS_ADM_TKT, NS_ADM_CAT, NS_ADM_SET, NS_ADM_LOG,
)
```

### `keyboards/user_kb.py`

```python
"""
لوحات أزرار واجهة العميل — كل شاشة لها دالة واحدة تبني أزرارها.

مبدأ ملزم: **لا زر بلا وظيفة**. كل `callback_data` هنا يقابله معالج مسجَّل في
`handlers/registry.py`، ويتحقق من ذلك اختبار `tests/integration/test_no_dead_buttons.py`.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from database.models import (
    Notification,
    Order,
    Payment,
    PaymentMethod,
    Service,
    ServiceCategory,
    SupportTicket,
)
from core.enums import OrderStatus, PaymentStatus
from keyboards.callback_data import (
    NS_ACCOUNT,
    NS_ADMIN,
    NS_CATALOG,
    NS_DEPOSIT,
    NS_FLOW,
    NS_NEW,
    NS_ORDERS,
    NS_SUPPORT,
    NS_WALLET,
    pack,
)
from keyboards.common_kb import back_home_row, home_button, pagination_row
from texts import admin_ar, ar
from utils.formatters import money_text, order_list_line, ticket_list_line

#: تصفية قوائم الطلبات المعروضة للمستخدم (الرمز ⇐ الحالات المشمولة)
ORDER_FILTERS: dict[str, tuple[str, tuple[str, ...]]] = {
    "all": (ar.FILTER_ALL, ()),
    "active": (
        ar.FILTER_ACTIVE,
        (
            OrderStatus.PENDING,
            OrderStatus.SUBMITTING,
            OrderStatus.SUBMIT_UNCERTAIN,
            OrderStatus.SUBMITTED,
            OrderStatus.IN_PROGRESS,
        ),
    ),
    "done": (ar.FILTER_COMPLETED, (OrderStatus.COMPLETED, OrderStatus.PARTIAL)),
    "rfnd": (
        ar.FILTER_REFUNDED,
        (OrderStatus.REFUNDED, OrderStatus.CANCELED, OrderStatus.FAILED),
    ),
}


# ============================ القائمة الرئيسية ========================== #


def main_menu_kb(*, is_admin: bool = False) -> InlineKeyboardMarkup:
    """
    القائمة الرئيسية — ست شاشات في ثلاثة صفوف.

    المدخلات:
        is_admin : يضيف صفاً سابعاً «🛠 لوحة التحكم» لمن يملك `admin.access` فقط.
                   القيمة الافتراضية False حتى لا يظهر الزر بالخطأ لمستخدم عادي
                   في أي مسار لم يتحقق من الصلاحية.
    """
    rows = [
        [
            InlineKeyboardButton(ar.BTN_SERVICES, callback_data=pack(NS_CATALOG, "list", 1)),
            InlineKeyboardButton(ar.BTN_WALLET, callback_data=pack(NS_WALLET, "home")),
        ],
        [
            InlineKeyboardButton(ar.BTN_ORDERS, callback_data=pack(NS_ORDERS, "list", "all", 1)),
            InlineKeyboardButton(ar.BTN_SUPPORT, callback_data=pack(NS_SUPPORT, "home")),
        ],
        [
            InlineKeyboardButton(ar.BTN_ACCOUNT, callback_data=pack(NS_ACCOUNT, "home")),
            InlineKeyboardButton(ar.BTN_INFO, callback_data=pack(NS_ACCOUNT, "info")),
        ],
    ]
    if is_admin:
        rows.append(
            [InlineKeyboardButton(admin_ar.BTN_ADMIN_PANEL, callback_data=pack(NS_ADMIN, "home"))]
        )
    return InlineKeyboardMarkup(rows)


# ============================== الخدمات ================================ #


def categories_kb(categories: list[ServiceCategory]) -> InlineKeyboardMarkup:
    """أزرار التصنيفات المتاحة (زرّان في كل صف)."""
    rows: list[list[InlineKeyboardButton]] = []
    for index in range(0, len(categories), 2):
        chunk = categories[index : index + 2]
        rows.append(
            [
                InlineKeyboardButton(category.title, callback_data=pack(NS_CATALOG, "open", category.id, 1))
                for category in chunk
            ]
        )
    rows.append([home_button()])
    return InlineKeyboardMarkup(rows)


def services_kb(
    services: list[Service], *, category_id: int, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """أزرار خدمات تصنيف مع ترقيم صفحات وزر رجوع للتصنيفات."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                f"{service.name} — {money_text(service.price_per_1000_units, symbol)}/1000",
                callback_data=pack(NS_CATALOG, "svc", service.id, category_id, page),
            )
        ]
        for service in services
    ]
    nav = pagination_row(
        NS_CATALOG, "open", page=page, total_pages=total_pages, prefix_args=(category_id,)
    )
    if nav:
        rows.append(nav)
    rows.append(back_home_row(NS_CATALOG, "list", 1))
    return InlineKeyboardMarkup(rows)


def service_card_kb(service: Service, *, category_id: int, page: int) -> InlineKeyboardMarkup:
    """بطاقة الخدمة: زر الطلب + الرجوع لقائمة الخدمات."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(ar.BTN_ORDER_NOW, callback_data=pack(NS_NEW, "start", service.id))],
            back_home_row(NS_CATALOG, "open", category_id, page),
        ]
    )


def insufficient_balance_kb(category_id: int, page: int) -> InlineKeyboardMarkup:
    """لوحة تُعرض عند عدم كفاية الرصيد: شحن مباشر أو رجوع."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(ar.BTN_DEPOSIT_NOW, callback_data=pack(NS_DEPOSIT, "start"))],
            back_home_row(NS_CATALOG, "open", category_id, page),
        ]
    )


# ============================== طلباتي ================================= #


def orders_filters_row(current: str) -> list[InlineKeyboardButton]:
    """صف أزرار تصفية الطلبات مع تمييز التصفية الحالية."""
    row: list[InlineKeyboardButton] = []
    for code, (label, _statuses) in ORDER_FILTERS.items():
        mark = "• " if code == current else ""
        row.append(InlineKeyboardButton(f"{mark}{label}", callback_data=pack(NS_ORDERS, "list", code, 1)))
    return row


def orders_kb(
    orders: list[Order], *, filter_code: str, page: int, total_pages: int, symbol: str
) -> InlineKeyboardMarkup:
    """قائمة طلبات المستخدم مع التصفية والترقيم."""
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                order_list_line(order, symbol=symbol),
                callback_data=pack(NS_ORDERS, "view", order.id, filter_code, page),
            )
        ]
        for order in orders
    ]
    rows.append(orders_filters_row(filter_code))
    nav = pagination_row(
        NS_ORDERS, "list", page=page, total_pages=total_pages, prefix_args=(filter_code,)
    )
    if nav:
        rows.append(nav)
    rows.append([home_button()])
    return InlineKeyboardMarkup(rows)


def order_card_kb(
    order: Order, *, filter_code: str, page: int, can_cancel: bool
) -> InlineKeyboardMarkup:
    """
    بطاقة الطلب.

    زر الإلغاء يظهر فقط عندما يسمح به منطق الخدمة فعلاً — لا زر معطّل ولا زر كاذب.
    """
    rows: list[list[InlineKeyboardButton]] = []
    if can_cancel:
        rows.append(
            [InlineKeyboardButton(ar.BTN_ORDER_CANCEL, callback_data=pack(NS_ORDERS, "cancel", order.id))]
        )
    rows.append(
        [InlineKeyboardButton(ar.BTN_ORDER_TICKET, callback_data=pack(NS_SUPPORT, "neworder", order.id))]
    )
    rows.append(back_home_row(NS_ORDERS, "list", filter_code, page))
    return InlineKeyboardMarkup(rows)


def order_cancel_confirm_kb(order_id: int) -> InlineKeyboardMarkup:
    """تأكيد إلغاء الطلب (خطوة إضافية قبل أي حركة مالية)."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(ar.BTN_CONFIRM, callback_data=pack(NS_ORDERS, "cancelyes", order_id)),
                InlineKeyboardButton(ar.BTN_BACK, callback_data=pack(NS_ORDERS, "view", order_id, "all", 1)),
            ]
        ]
    )


# ============================== المحفظة ================================ #


def wallet_kb() -> InlineKeyboardMarkup:
    """شاشة المحفظة: شحن، سجل العمليات، طلبات الشحن."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(ar.BTN_DEPOSIT_NOW, callback_data=pack(NS_DEPOSIT, "start"))],
            [
                InlineKeyboardButton(ar.BTN_WALLET_HISTORY, callback_data=pack(NS_WALLET, "history", 1)),
                InlineKeyboardButton(ar.BTN_MY_DEPOSITS, callback_data=pack(NS_DEPOSIT, "list", 1)),
            ],
            [home_button()],
        ]
    )


def history_kb(*, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """سجل العمليات المالية مع الترقيم."""
    rows: list[list[InlineKeyboardButton]] = []
    nav = pagination_row(NS_WALLET, "history", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(back_home_row(NS_WALLET, "home"))
    return InlineKeyboardMarkup(rows)


# =============================== الشحن ================================= #


def deposit_methods_kb(methods: list[PaymentMethod]) -> InlineKeyboardMarkup:
    """أزرار طرق الشحن المفعّلة."""
    rows = [
        [InlineKeyboardButton(method.name_ar, callback_data=pack(NS_DEPOSIT, "method", method.id))]
        for method in methods
    ]
    rows.append(back_home_row(NS_WALLET, "home"))
    return InlineKeyboardMarkup(rows)


def deposits_kb(payments: list[Payment], *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """قائمة طلبات الشحن السابقة مع إمكانية إلغاء المعلّق منها."""
    rows: list[list[InlineKeyboardButton]] = []
    for payment in payments:
        if payment.status == PaymentStatus.PENDING:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"🛑 إلغاء طلب #{payment.id}",
                        callback_data=pack(NS_DEPOSIT, "cancel", payment.id),
                    )
                ]
            )
    nav = pagination_row(NS_DEPOSIT, "list", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(back_home_row(NS_WALLET, "home"))
    return InlineKeyboardMarkup(rows)


# =============================== الدعم ================================= #


def support_kb() -> InlineKeyboardMarkup:
    """شاشة الدعم الرئيسية."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(ar.BTN_TICKET_NEW, callback_data=pack(NS_SUPPORT, "new"))],
            [InlineKeyboardButton(ar.BTN_TICKETS_LIST, callback_data=pack(NS_SUPPORT, "list", 1))],
            [home_button()],
        ]
    )


def ticket_categories_kb() -> InlineKeyboardMarkup:
    """أزرار تصنيفات التذكرة الجديدة."""
    rows = [
        [InlineKeyboardButton(label, callback_data=pack(NS_SUPPORT, "cat", code))]
        for code, label in ar.TICKET_CATEGORIES.items()
    ]
    rows.append([InlineKeyboardButton(ar.BTN_CANCEL, callback_data=pack(NS_FLOW, "cancel"))])
    return InlineKeyboardMarkup(rows)


def tickets_kb(tickets: list[SupportTicket], *, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """قائمة تذاكر المستخدم."""
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(ticket_list_line(ticket), callback_data=pack(NS_SUPPORT, "view", ticket.id))]
        for ticket in tickets
    ]
    nav = pagination_row(NS_SUPPORT, "list", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(back_home_row(NS_SUPPORT, "home"))
    return InlineKeyboardMarkup(rows)


def ticket_card_kb(ticket: SupportTicket) -> InlineKeyboardMarkup:
    """بطاقة التذكرة: الرد والإغلاق (تظهر فقط ما دامت مفتوحة)."""
    rows: list[list[InlineKeyboardButton]] = []
    if ticket.is_open:
        rows.append(
            [
                InlineKeyboardButton(ar.BTN_TICKET_REPLY, callback_data=pack(NS_SUPPORT, "reply", ticket.id)),
                InlineKeyboardButton(ar.BTN_TICKET_CLOSE, callback_data=pack(NS_SUPPORT, "close", ticket.id)),
            ]
        )
    else:
        rows.append(
            [InlineKeyboardButton(ar.BTN_TICKET_REPLY, callback_data=pack(NS_SUPPORT, "reply", ticket.id))]
        )
    rows.append(back_home_row(NS_SUPPORT, "list", 1))
    return InlineKeyboardMarkup(rows)


# ============================== الحساب ================================= #


def account_kb(unread: int) -> InlineKeyboardMarkup:
    """شاشة الحساب مع عدّاد الإشعارات غير المقروءة."""
    badge = f" ({unread})" if unread else ""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(ar.BTN_NOTIFICATIONS + badge, callback_data=pack(NS_ACCOUNT, "notif", 1))],
            [
                InlineKeyboardButton(ar.BTN_WALLET, callback_data=pack(NS_WALLET, "home")),
                InlineKeyboardButton(ar.BTN_ORDERS, callback_data=pack(NS_ORDERS, "list", "all", 1)),
            ],
            [home_button()],
        ]
    )


def notifications_kb(*, page: int, total_pages: int, unread: int) -> InlineKeyboardMarkup:
    """صندوق الإشعارات مع زر تعليم الكل كمقروء."""
    rows: list[list[InlineKeyboardButton]] = []
    if unread:
        rows.append(
            [InlineKeyboardButton(ar.BTN_MARK_ALL_READ, callback_data=pack(NS_ACCOUNT, "readall"))]
        )
    nav = pagination_row(NS_ACCOUNT, "notif", page=page, total_pages=total_pages)
    if nav:
        rows.append(nav)
    rows.append(back_home_row(NS_ACCOUNT, "home"))
    return InlineKeyboardMarkup(rows)


def info_kb() -> InlineKeyboardMarkup:
    """شاشة المعلومات."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(ar.BTN_SUPPORT, callback_data=pack(NS_SUPPORT, "home"))],
            [home_button()],
        ]
    )


def notifications_only_back_kb() -> InlineKeyboardMarkup:
    """لوحة رجوع بسيطة تُستخدم بعد الإجراءات السريعة."""
    return InlineKeyboardMarkup([back_home_row(NS_ACCOUNT, "home")])
```

## لوحة التحكم — الأساس والأقسام الثمانية

### `handlers/admin/__init__.py`

```python
"""
حزمة لوحة التحكم: تجميع معالجات كل الأقسام في مكانين فقط.

تصدّر هذه الحزمة دالتين يستهلكهما `handlers/registry.py`:

    admin_conversations()   : كل محادثات الأدمن (تُسجَّل قبل أزرار الشاشات).
    admin_screen_handlers() : كل أزرار شاشات الأدمن.

كل وحدة قسم (`users`, `payments`, ...) تصدّر `conversations()` و`screens()`
فيبقى ترتيب التسجيل في مكان واحد ويظل من السهل التأكد أن كل زر له معالج.
"""

from __future__ import annotations

from telegram.ext import CallbackQueryHandler, CommandHandler, ConversationHandler

from handlers.admin import (
    catalog,
    dashboard,
    logs,
    orders,
    payments,
    settings,
    tickets,
    users,
)
from keyboards.callback_data import NS_ADMIN, pattern

#: وحدات الأقسام بالترتيب الذي تُسجَّل به معالجاتها
SECTIONS = (users, payments, orders, tickets, catalog, settings, logs)

__all__ = [
    "admin_conversations",
    "admin_screen_handlers",
    "admin_command_handlers",
    "SECTIONS",
]


def admin_conversations() -> list[ConversationHandler]:
    """كل محادثات لوحة التحكم مجموعة من كل الأقسام."""
    collected: list[ConversationHandler] = []
    for section in SECTIONS:
        collected.extend(section.conversations())
    return collected


def admin_screen_handlers() -> list[CallbackQueryHandler]:
    """كل أزرار شاشات لوحة التحكم (خارج المحادثات)."""
    collected: list[CallbackQueryHandler] = [
        CallbackQueryHandler(dashboard.panel_screen, pattern=pattern(NS_ADMIN, "home")),
        CallbackQueryHandler(dashboard.health_screen, pattern=pattern(NS_ADMIN, "health")),
    ]
    for section in SECTIONS:
        collected.extend(section.screens())
    return collected


def admin_command_handlers() -> list[CommandHandler]:
    """أوامر لوحة التحكم (/admin فقط حالياً)."""
    return [CommandHandler("admin", dashboard.admin_command)]
```

### `handlers/admin/common.py`

```python
"""
الأساس المشترك لكل شاشات لوحة التحكم: فحص الصلاحية، بيانات المحادثات، أدوات العرض.

لماذا ملف مستقل؟
    القاعدة الإلزامية في تصميم المرحلة 0 (البند 5): **فحص الصلاحية يتم على
    الـcallback نفسه، لا على القائمة فقط**. إخفاء الزر وحده لا يكفي لأن الزر
    القديم يبقى في محادثة المستخدم بعد سحب صلاحيته. لذلك كل معالج أدمن يُلفّ
    بـ`@admin_required(...)` الذي:

        1. يتحقق من `admin.access` (بوابة اللوحة كلها).
        2. يتحقق من الصلاحية الدقيقة للإجراء.
        3. يترك `AuthService` يسجّل المحاولة المرفوضة في سجل التدقيق تلقائياً.
        4. يرد بتنبيه عربي ويُنهي أي محادثة جارية بدل ترك المستخدم معلّقاً.

ترتيب المزخرفات المعتمد في كل الوحدات:

        @guarded                       ← يلتقط أخطاء النظام المتوقعة (الخارجي)
        @admin_required(Permission.X)  ← يفحص الصلاحية (الداخلي)
        async def screen(update, context): ...
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from core.exceptions import PermissionDeniedError, ValidationError
from core.permissions import Permission
from database.models import User
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import back_panel_kb
from keyboards.callback_data import Callback, unpack
from middlewares.context import require_user, services_of
from services import ServiceContainer
from texts import admin_ar as t
from utils.logging_setup import get_logger
from utils.security import new_token

logger = get_logger(__name__)

Handler = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]]
_T = TypeVar("_T", bound=Handler)

#: عدد العناصر في صفحة قوائم لوحة الأدمن
PAGE_SIZE = 6

#: عدد أسطر السجلات في الصفحة (أسطر قصيرة ⇐ عدد أكبر)
LOG_PAGE_SIZE = 8

#: مفتاح واحد لبيانات كل محادثات الأدمن (محادثة واحدة نشطة لكل أدمن في كل وقت)
ADMIN_FLOW_KEY = "admin_flow"


# ============================ فحص الصلاحيات ============================= #


def admin_required(permission: str | None = None) -> Callable[[_T], _T]:
    """
    مزخرف يمنع تنفيذ معالج الأدمن إلا لمن يملك الصلاحية فعلاً.

    المدخلات:
        permission : رمز الصلاحية المطلوبة للإجراء (None ⇐ يكفي دخول اللوحة).

    المخرجات:
        نفس المعالج مغلَّفاً؛ وعند الرفض يرد بتنبيه ويُرجع `ConversationHandler.END`
        (قيمة غير ضارة خارج المحادثات، وتُنهي المحادثة داخلها).
    """

    def decorator(func: _T) -> _T:
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            """التحقق من الصلاحية قبل تمرير التحديث إلى الشاشة الفعلية."""
            services = services_of(context)
            user = require_user(context)
            try:
                await services.auth.require_permission(
                    user, Permission.ADMIN_ACCESS, context=func.__name__
                )
                if permission is not None and permission != Permission.ADMIN_ACCESS:
                    await services.auth.require_permission(
                        user, permission, context=func.__name__
                    )
            except PermissionDeniedError as exc:
                logger.warning(
                    "رفض وصول إداري: المستخدم %s ← %s (%s)",
                    user.telegram_id,
                    permission or Permission.ADMIN_ACCESS,
                    func.__name__,
                )
                await answer_callback(update, exc.user_message, alert=True)
                if update.callback_query is None:
                    await send(update, context, exc.user_message, back_panel_kb())
                clear_flow(context)
                return ConversationHandler.END
            return await func(update, context)

        #: تُقرأ في الاختبارات للتأكد أن كل معالج أدمن محميّ بصلاحية صحيحة
        wrapper.admin_permission = permission or Permission.ADMIN_ACCESS  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator


async def permissions_of(context: ContextTypes.DEFAULT_TYPE) -> set[str]:
    """
    مجموعة صلاحيات الأدمن الحالي — تُقرأ طازجة من قاعدة البيانات عند كل شاشة.

    السبب: الصلاحيات تُدار من قاعدة البيانات ويمكن سحبها أثناء الجلسة،
    والأزرار يجب أن تختفي فور ذلك.
    """
    services = services_of(context)
    return await services.auth.permissions_of(require_user(context))


def actor(context: ContextTypes.DEFAULT_TYPE) -> User:
    """الأدمن المنفِّذ للإجراء الحالي (كما حمّلته الطبقة الوسيطة)."""
    return require_user(context)


# ============================ بيانات المحادثات ========================== #


def flow(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """قراءة بيانات محادثة الأدمن الجارية (قاموس فارغ إن لم توجد)."""
    if context.user_data is None:
        return {}
    return context.user_data.get(ADMIN_FLOW_KEY) or {}


def start_flow(context: ContextTypes.DEFAULT_TYPE, **data: Any) -> dict:
    """
    بدء محادثة أدمن جديدة ببيانات أولية.

    يُولَّد مع كل محادثة `token` فريد يُمرَّر للعمليات المالية كمفتاح منع تكرار،
    فلو ضُغط زر التأكيد مرتين لا تُنفَّذ العملية مرتين.
    """
    payload = {"token": new_token(10), **data}
    if context.user_data is not None:
        context.user_data[ADMIN_FLOW_KEY] = payload
    return payload


def update_flow(context: ContextTypes.DEFAULT_TYPE, **data: Any) -> dict:
    """تحديث بيانات المحادثة الجارية دون فقدان ما سبق."""
    payload = dict(flow(context))
    payload.update(data)
    if context.user_data is not None:
        context.user_data[ADMIN_FLOW_KEY] = payload
    return payload


def clear_flow(context: ContextTypes.DEFAULT_TYPE) -> None:
    """مسح بيانات المحادثة بعد الانتهاء أو الإلغاء."""
    if context.user_data is not None:
        context.user_data.pop(ADMIN_FLOW_KEY, None)


@guarded
async def cancel_admin_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء أي محادثة أدمن جارية (زر ❌ إلغاء أو الأمر /cancel)."""
    await answer_callback(update)
    clear_flow(context)
    if update.callback_query is not None:
        await render(update, context, t.CANCELLED, back_panel_kb())
    else:
        await send(update, context, t.CANCELLED, back_panel_kb())
    return ConversationHandler.END


# ============================== أدوات العرض ============================= #


def args(update: Update) -> Callback:
    """تفكيك بيانات الزر المضغوط (namespace/action/args)."""
    return unpack(update.callback_query.data if update.callback_query else None)


def paginate(total: int, page: int, page_size: int = PAGE_SIZE) -> tuple[int, int, int]:
    """
    حساب الترقيم الموحّد لأي قائمة إدارية.

    المخرجات: (الصفحة بعد التصحيح، عدد الصفحات، إزاحة SQL).
    """
    total_pages = max(1, -(-max(0, total) // page_size))
    current = min(max(1, page), total_pages)
    return current, total_pages, (current - 1) * page_size


async def symbol_of(context: ContextTypes.DEFAULT_TYPE) -> str:
    """رمز العملة المعتمد في الإعدادات (يُعرض بجانب كل مبلغ)."""
    services: ServiceContainer = services_of(context)
    return await services.settings.money_symbol()


async def load_user_or_fail(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> User:
    """
    تحميل مستخدم بالمعرف الداخلي لعرض بطاقته أو تنفيذ إجراء عليه.

    الاستثناءات:
        ValidationError : الزر يحمل معرفاً لم يعد موجوداً (يُعرض كرسالة عربية).
    """
    services = services_of(context)
    target = await services.users.get(user_id)
    if target is None:
        raise ValidationError(
            f"المستخدم {user_id} غير موجود", user_message="❌ هذا المستخدم لم يعد موجوداً."
        )
    return target
```

### `handlers/admin/dashboard.py`

```python
"""
شاشة لوحة التحكم الرئيسية + شاشة صحة النظام + الأمر /admin.

مبدأ الشاشة: القائمة تُبنى من صلاحيات هذا الأدمن تحديداً، فأدمن الدعم يرى
«🎫 الدعم» فقط، ومراجع المدفوعات يرى «💰 المدفوعات» فقط. والأرقام الظاهرة
في الرأس تُعرض لمن يملك `stats.view` فقط.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from core.enums import OrderStatus
from core.permissions import Permission
from handlers.admin.common import admin_required, permissions_of, symbol_of
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render
from keyboards.admin_kb import admin_menu_kb, health_kb
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from utils.datetime_utils import utc_now_iso
from utils.formatters import datetime_text, money_text

#: الحالات التي تُحتسب «طلبات نشطة» في رأس اللوحة
ACTIVE_FOR_DASHBOARD = (
    OrderStatus.PENDING,
    OrderStatus.SUBMITTING,
    OrderStatus.SUBMITTED,
    OrderStatus.IN_PROGRESS,
)

#: الحالات التي تعني «يحتاج تدخل أدمن الآن»
ATTENTION_FOR_DASHBOARD = (OrderStatus.SUBMIT_UNCERTAIN, OrderStatus.FAILED)


async def _panel_text(update: Update, context: ContextTypes.DEFAULT_TYPE, perms: set[str]) -> str:
    """
    بناء نص رأس اللوحة: الأرقام الكاملة لمن يملك `stats.view`، وعنوان مختصر لغيره.

    لا نستدعي خدمة الإحصائيات أصلاً لمن لا يملك الصلاحية، حتى لا يمتلئ سجل
    التدقيق بمحاولات رفض لا ذنب للأدمن فيها (زيارته للوحة ليست محاولة اختراق).
    """
    if Permission.STATS_VIEW not in perms:
        return t.PANEL_SIMPLE

    services = services_of(context)
    admin = require_user(context)
    stats = await services.stats.dashboard(admin)
    symbol = await symbol_of(context)
    by_status = stats.orders_by_status
    return t.DASHBOARD.format(
        users_total=stats.users_total,
        users_new_today=stats.users_new_today,
        users_active_7d=stats.users_active_7d,
        users_banned=stats.users_banned,
        orders_today=stats.orders_today,
        active_orders=sum(by_status.get(status, 0) for status in ACTIVE_FOR_DASHBOARD),
        attention_orders=sum(by_status.get(status, 0) for status in ATTENTION_FOR_DASHBOARD),
        revenue_today=money_text(stats.revenue_today_units, symbol),
        revenue_7d=money_text(stats.revenue_7d_units, symbol),
        deposits_today=money_text(stats.deposits_today_units, symbol),
        pending_payments=stats.pending_payments,
        open_tickets=stats.open_tickets,
        queued=stats.queued_notifications,
        active_services=stats.active_services,
        errors_24h=stats.errors_24h,
        now=datetime_text(utc_now_iso()),
    )


@guarded
@admin_required()
async def panel_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الشاشة الرئيسية للوحة التحكم (زر «🛠 لوحة التحكم» و«🔄 تحديث»)."""
    await answer_callback(update)
    services = services_of(context)
    perms = await permissions_of(context)

    pending = (
        await services.payments.pending_count() if Permission.PAYMENTS_VIEW in perms else 0
    )
    tickets = await services.tickets.open_count() if Permission.TICKETS_VIEW in perms else 0

    await render(
        update,
        context,
        await _panel_text(update, context, perms),
        admin_menu_kb(perms, pending_payments=pending, open_tickets=tickets),
    )


@guarded
@admin_required()
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الأمر /admin — مدخل اللوحة لمن يملك `admin.access` فقط."""
    await panel_screen(update, context)


@guarded
@admin_required(Permission.STATS_VIEW)
async def health_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة صحة النظام: المزودون، الإشعارات، الأخطاء، حجم قاعدة البيانات."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    await render(update, context, await services.stats.health_text(admin), health_kb())
```

### `handlers/admin/users.py`

```python
"""
قسم «👥 المستخدمون» في لوحة التحكم.

ما ينفّذه هذا الملف:
    • البحث عن مستخدم (معرف رقمي / @username / جزء من الاسم).
    • بطاقة المستخدم الكاملة (رصيد، إنفاق، طلبات، تذاكر، حظر، ملاحظة).
    • إضافة رصيد وخصمه بمحادثة من ثلاث خطوات تنتهي بشاشة تأكيد.
    • الحظر وفك الحظر والملاحظة الإدارية وتغيير الدور.
    • استعراض طلبات المستخدم وحركاته المالية.

قواعد مطبّقة هنا حرفياً:
    • كل معالج يفحص صلاحيته بنفسه عبر `@admin_required` (لا نكتفي بإخفاء الزر).
    • كل عملية مالية تمر بشاشة تأكيد ثانية، وتحمل `token` ثابتاً طوال المحادثة
      فلا تُنفَّذ مرتين عند الضغط المزدوج (`DuplicateOperationError`).
    • تغيير الرصيد يتم حصراً عبر `WalletService.adjust_balance` — لا SQL هنا.
    • سجل التدقيق تكتبه الخدمات نفسها؛ المعالج لا يزوّر سجلاً ولا يتجاوزه.
    • المستخدم المتأثر يُشعَر عبر صندوق الإشعارات (Outbox) لا برسالة مباشرة.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from core.enums import NotificationType
from core.permissions import Permission
from handlers.admin.common import (
    ADMIN_FLOW_KEY,
    PAGE_SIZE,
    admin_required,
    args,
    cancel_admin_flow,
    clear_flow,
    flow,
    load_user_or_fail,
    paginate,
    permissions_of,
    start_flow,
    symbol_of,
    update_flow,
)
from handlers.common.fallbacks import exit_conversation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    cancel_only_kb,
    confirm_cancel_kb,
    user_card_kb,
    user_list_nav_kb,
    user_results_kb,
    user_role_confirm_kb,
    user_role_kb,
    users_home_kb,
)
from keyboards.callback_data import NS_ADM_USERS, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from texts import templates
from utils.formatters import (
    datetime_text,
    money_text,
    order_status_text,
    safe,
    transaction_line,
)
from utils.logging_setup import get_logger
from utils.validators import clean_text, parse_amount_units, validate_amount_range

logger = get_logger(__name__)

#: حالات محادثة البحث
ASK_QUERY = 0

#: حالات محادثة تعديل الرصيد
ASK_AMOUNT, ASK_REASON, CONFIRM_BALANCE = range(10, 13)

#: حالات محادثة الحظر
ASK_BAN_REASON, CONFIRM_BAN = range(20, 22)

#: حالة محادثة الملاحظة الإدارية
ASK_NOTE = 30

#: الحد الأقصى لنتائج البحث المعروضة دفعة واحدة
SEARCH_LIMIT = 8


# ============================ أدوات العرض ============================== #


async def _render_card(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, *, as_new: bool = False
) -> None:
    """
    عرض بطاقة مستخدم كاملة (تُستخدم بعد كل إجراء حتى يرى الأدمن النتيجة فوراً).

    المدخلات:
        user_id : المعرف الداخلي للمستخدم.
        as_new  : إرسال رسالة جديدة بدل تحرير الحالية (بعد انتهاء محادثة نصية).
    """
    services = services_of(context)
    target = await load_user_or_fail(context, user_id)
    summary = await services.users.summary(target)
    symbol = await symbol_of(context)
    perms = await permissions_of(context)

    text = t.USER_CARD.format(
        name=safe(target.display_name, limit=40),
        telegram_id=target.telegram_id,
        username=f"@{safe(target.username)}" if target.username else "—",
        role=t.ROLE_NAMES.get(target.role, safe(target.role)),
        ban_line=t.USER_BANNED_LINE.format(reason=safe(target.ban_reason or "—", limit=120))
        if target.is_banned
        else "",
        balance=money_text(target.balance_units, symbol),
        deposited=money_text(target.total_deposited_units, symbol),
        spent=money_text(target.total_spent_units, symbol),
        orders_count=summary.orders_count,
        active_orders=summary.active_orders,
        payments_count=summary.payments_count,
        tickets_open=summary.tickets_open,
        joined=datetime_text(target.created_at),
        last_activity=datetime_text(target.last_activity or target.created_at),
        note_line=t.USER_NOTE_LINE.format(note=safe(target.notes, limit=300))
        if target.notes
        else "",
    )
    markup = user_card_kb(target, perms)
    if as_new:
        await send(update, context, text, markup)
    else:
        await render(update, context, text, markup)


# ============================ شاشات القراءة ============================ #


@guarded
@admin_required(Permission.USERS_VIEW)
async def users_home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الشاشة الرئيسية لقسم المستخدمين: عدادات + زر البحث."""
    await answer_callback(update)
    services = services_of(context)
    counters = await services.users.counters()
    perms = await permissions_of(context)
    await render(
        update,
        context,
        t.USERS_HOME.format(
            total=counters["total"],
            new_today=counters["new_today"],
            active_today=counters["active_today"],
            banned=counters["banned"],
        ),
        users_home_kb(perms),
    )


@guarded
@admin_required(Permission.USERS_VIEW)
async def user_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة مستخدم بالمعرف الداخلي القادم من الزر."""
    await answer_callback(update)
    await _render_card(update, context, args(update).int_arg(0))


@guarded
@admin_required(Permission.ORDERS_VIEW)
async def user_orders_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة طلبات مستخدم بعينه (مرقَّمة)."""
    await answer_callback(update)
    data = args(update)
    user_id = data.int_arg(0)
    services = services_of(context)
    admin = require_user(context)
    target = await load_user_or_fail(context, user_id)
    symbol = await symbol_of(context)

    total = await services.orders.admin_count(admin, user_id=user_id)
    page, total_pages, offset = paginate(total, data.int_arg(1, 1))
    orders = await services.orders.admin_list(
        admin, user_id=user_id, limit=PAGE_SIZE, offset=offset
    )

    if not orders:
        await render(
            update,
            context,
            t.USER_ORDERS_EMPTY,
            user_list_nav_kb("orders", user_id, page=1, total_pages=1),
        )
        return

    lines = "\n\n".join(
        f"{order_status_text(order.status)}\n"
        f"   {order.public_code or order.id} · {money_text(order.cost_units, symbol)}\n"
        f"   🛍 {safe(order.service_name_snapshot, limit=38)}\n"
        f"   🕒 {datetime_text(order.created_at)}"
        for order in orders
    )
    await render(
        update,
        context,
        t.USER_ORDERS_TITLE.format(
            name=safe(target.display_name, limit=30), page=page, pages=total_pages, lines=lines
        ),
        user_list_nav_kb("orders", user_id, page=page, total_pages=total_pages),
    )


@guarded
@admin_required(Permission.USERS_VIEW)
async def user_transactions_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """كشف الحركات المالية لمستخدم بعينه (مرقَّم)."""
    await answer_callback(update)
    data = args(update)
    user_id = data.int_arg(0)
    services = services_of(context)
    target = await load_user_or_fail(context, user_id)
    symbol = await symbol_of(context)

    total = await services.wallet.history_count(user_id)
    page, total_pages, offset = paginate(total, data.int_arg(1, 1))
    transactions = await services.wallet.history(user_id, limit=PAGE_SIZE, offset=offset)

    if not transactions:
        await render(
            update,
            context,
            t.USER_TX_EMPTY,
            user_list_nav_kb("tx", user_id, page=1, total_pages=1),
        )
        return

    lines = "\n\n".join(
        transaction_line(transaction, symbol=symbol) for transaction in transactions
    )
    await render(
        update,
        context,
        t.USER_TX_TITLE.format(
            name=safe(target.display_name, limit=30), page=page, pages=total_pages, lines=lines
        ),
        user_list_nav_kb("tx", user_id, page=page, total_pages=total_pages),
    )


# ============================= محادثة البحث ============================ #


@guarded
@admin_required(Permission.USERS_VIEW)
async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء محادثة البحث عن مستخدم."""
    await answer_callback(update)
    start_flow(context)
    await render(update, context, t.USERS_ASK_QUERY, cancel_only_kb())
    return ASK_QUERY


@guarded
@admin_required(Permission.USERS_VIEW)
async def receive_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ البحث وعرض النتائج كأزرار."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_QUERY

    query = clean_text(message.text, field="نص البحث", max_length=64, min_length=1)
    services = services_of(context)
    admin = require_user(context)
    found = await services.users.search(admin, query, limit=SEARCH_LIMIT)
    clear_flow(context)

    if not found:
        await send(update, context, t.USERS_NO_RESULTS.format(query=safe(query)), cancel_only_kb())
        return ASK_QUERY

    await send(
        update,
        context,
        t.USERS_RESULTS.format(query=safe(query), count=len(found)),
        user_results_kb(found),
    )
    return ConversationHandler.END


# ========================== محادثة تعديل الرصيد ========================= #


async def _start_balance(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, credit: bool
) -> int:
    """الخطوة الأولى المشتركة بين الإضافة والخصم: سؤال المبلغ."""
    await answer_callback(update)
    user_id = args(update).int_arg(0)
    target = await load_user_or_fail(context, user_id)
    symbol = await symbol_of(context)
    start_flow(context, user_id=user_id, credit=credit)

    template = t.USER_ASK_CREDIT if credit else t.USER_ASK_DEBIT
    await render(
        update,
        context,
        template.format(
            name=safe(target.display_name, limit=30),
            balance=money_text(target.balance_units, symbol),
        ),
        cancel_only_kb(),
    )
    return ASK_AMOUNT


@guarded
@admin_required(Permission.USERS_BALANCE_CREDIT)
async def start_credit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء محادثة إضافة رصيد."""
    return await _start_balance(update, context, credit=True)


@guarded
@admin_required(Permission.USERS_BALANCE_DEBIT)
async def start_debit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء محادثة خصم رصيد."""
    return await _start_balance(update, context, credit=False)


@guarded
@admin_required()
async def receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال المبلغ والتحقق منه ثم سؤال السبب."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_AMOUNT

    units = validate_amount_range(parse_amount_units(message.text), min_units=1, label="المبلغ")
    update_flow(context, amount_units=units)
    await send(update, context, t.USER_ASK_BALANCE_REASON, cancel_only_kb())
    return ASK_REASON


@guarded
@admin_required()
async def receive_balance_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال سبب العملية ثم عرض شاشة التأكيد النهائية."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_REASON

    reason = clean_text(message.text, field="سبب العملية", max_length=200, min_length=3)
    data = update_flow(context, reason=reason)

    target = await load_user_or_fail(context, int(data["user_id"]))
    symbol = await symbol_of(context)
    credit = bool(data["credit"])
    amount = int(data["amount_units"])
    after = target.balance_units + amount if credit else target.balance_units - amount

    await send(
        update,
        context,
        t.USER_BALANCE_CONFIRM.format(
            name=safe(target.display_name, limit=30),
            icon="➕" if credit else "➖",
            operation=t.OP_CREDIT if credit else t.OP_DEBIT,
            amount=money_text(amount, symbol),
            balance=money_text(target.balance_units, symbol),
            balance_after=money_text(after, symbol),
            reason=safe(reason, limit=200),
        ),
        confirm_cancel_kb(),
    )
    return CONFIRM_BALANCE


@guarded
@admin_required()
async def confirm_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    تنفيذ تعديل الرصيد فعلياً بعد التأكيد.

    الصلاحية تُفحص هنا مرة أخرى حسب نوع العملية (إضافة/خصم) لأن المحادثة قد
    تكون بدأت قبل تغيّر صلاحيات هذا الأدمن.
    """
    await answer_callback(update)
    data = flow(context)
    if not data.get("user_id") or not data.get("amount_units"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    credit = bool(data["credit"])
    await services.auth.require_permission(
        admin,
        Permission.USERS_BALANCE_CREDIT if credit else Permission.USERS_BALANCE_DEBIT,
        context=f"user:{data['user_id']}",
    )

    target = await load_user_or_fail(context, int(data["user_id"]))
    amount = int(data["amount_units"])
    reason = str(data["reason"])
    symbol = await symbol_of(context)

    transaction = await services.wallet.adjust_balance(
        target=target,
        amount_units=amount,
        admin=admin,
        reason=reason,
        credit=credit,
        token=str(data["token"]),
    )

    # إشعار المستخدم المتأثر عبر صندوق الإشعارات (نفس الـtoken ⇐ لا تكرار)
    builder = templates.balance_credited if credit else templates.balance_debited
    title, body = builder(
        amount_units=amount,
        new_balance_units=transaction.balance_after_units,
        reason=reason,
        symbol=symbol,
    )
    async with services.db.transaction() as tx:
        await services.notifications.notify_user_manual(
            tx,
            user_id=target.id,
            token=str(data["token"]),
            title=title,
            message=body,
            type=NotificationType.SYSTEM,
        )

    logger.info(
        "عدّل الأدمن %s رصيد المستخدم %s بمقدار %s (%s)",
        admin.telegram_id, target.telegram_id, amount, "credit" if credit else "debit",
    )
    clear_flow(context)

    await render(
        update,
        context,
        t.USER_BALANCE_DONE.format(
            name=safe(target.display_name, limit=30),
            icon="➕" if credit else "➖",
            operation=t.OP_CREDIT if credit else t.OP_DEBIT,
            amount=money_text(amount, symbol),
            balance=money_text(transaction.balance_after_units, symbol),
        ),
    )
    await _render_card(update, context, target.id, as_new=True)
    return ConversationHandler.END


# ============================= محادثة الحظر ============================ #


@guarded
@admin_required(Permission.USERS_BAN)
async def start_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء محادثة حظر مستخدم (السبب إجباري)."""
    await answer_callback(update)
    user_id = args(update).int_arg(0)
    target = await load_user_or_fail(context, user_id)
    start_flow(context, user_id=user_id)
    await render(
        update,
        context,
        t.USER_ASK_BAN_REASON.format(name=safe(target.display_name, limit=30)),
        cancel_only_kb(),
    )
    return ASK_BAN_REASON


@guarded
@admin_required(Permission.USERS_BAN)
async def receive_ban_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال سبب الحظر وعرض شاشة التأكيد."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_BAN_REASON

    reason = clean_text(message.text, field="سبب الحظر", max_length=200, min_length=3)
    data = update_flow(context, reason=reason)
    target = await load_user_or_fail(context, int(data["user_id"]))
    await send(
        update,
        context,
        t.USER_BAN_CONFIRM.format(
            name=safe(target.display_name, limit=30), reason=safe(reason, limit=200)
        ),
        confirm_cancel_kb(),
    )
    return CONFIRM_BAN


@guarded
@admin_required(Permission.USERS_BAN)
async def confirm_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ الحظر (الخدمة تتكفّل بالتدقيق وإشعار المستخدم)."""
    await answer_callback(update)
    data = flow(context)
    if not data.get("user_id") or not data.get("reason"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    target = await load_user_or_fail(context, int(data["user_id"]))
    await services.users.ban(admin, target.id, str(data["reason"]))
    clear_flow(context)

    await render(update, context, t.USER_BAN_DONE.format(name=safe(target.display_name, limit=30)))
    await _render_card(update, context, target.id, as_new=True)
    return ConversationHandler.END


@guarded
@admin_required(Permission.USERS_UNBAN)
async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """فك الحظر مباشرة (إجراء غير خطير ⇐ بلا شاشة تأكيد)."""
    services = services_of(context)
    admin = require_user(context)
    user_id = args(update).int_arg(0)
    target = await load_user_or_fail(context, user_id)

    changed = await services.users.unban(admin, target.id)
    await answer_callback(
        update,
        t.USER_UNBAN_DONE.format(name=target.display_name) if changed else t.NOTHING_CHANGED,
        alert=True,
    )
    await _render_card(update, context, target.id)


# =========================== محادثة الملاحظة =========================== #


@guarded
@admin_required(Permission.USERS_NOTE)
async def start_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء محادثة كتابة ملاحظة إدارية عن مستخدم."""
    await answer_callback(update)
    user_id = args(update).int_arg(0)
    target = await load_user_or_fail(context, user_id)
    start_flow(context, user_id=user_id)
    await render(
        update,
        context,
        t.USER_ASK_NOTE.format(name=safe(target.display_name, limit=30)),
        cancel_only_kb(),
    )
    return ASK_NOTE


@guarded
@admin_required(Permission.USERS_NOTE)
async def receive_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ الملاحظة الإدارية وعرض البطاقة محدَّثة."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_NOTE

    data = flow(context)
    if not data.get("user_id"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    note = clean_text(message.text, field="الملاحظة", max_length=500, min_length=2)
    services = services_of(context)
    admin = require_user(context)
    user_id = int(data["user_id"])
    await services.users.set_note(admin, user_id, note)
    clear_flow(context)

    await send(update, context, t.USER_NOTE_DONE)
    await _render_card(update, context, user_id, as_new=True)
    return ConversationHandler.END


# ============================= تغيير الدور ============================= #


@guarded
@admin_required(Permission.USERS_ROLE_CHANGE)
async def role_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض الأدوار المتاحة للإسناد."""
    await answer_callback(update)
    target = await load_user_or_fail(context, args(update).int_arg(0))
    await render(
        update,
        context,
        t.USER_ROLE_TITLE.format(
            name=safe(target.display_name, limit=30),
            role=t.ROLE_NAMES.get(target.role, safe(target.role)),
        ),
        user_role_kb(target),
    )


@guarded
@admin_required(Permission.USERS_ROLE_CHANGE)
async def role_confirm_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة التأكيد الثانية قبل تغيير الدور (إجراء خطير)."""
    await answer_callback(update)
    data = args(update)
    target = await load_user_or_fail(context, data.int_arg(0))
    new_role = data.arg(1)

    if new_role not in t.ASSIGNABLE_ROLES:
        await answer_callback(update, t.ERR_NO_PERMISSION, alert=True)
        return
    if new_role == target.role:
        await answer_callback(update, t.USER_ROLE_SAME, alert=True)
        return

    await render(
        update,
        context,
        t.USER_ROLE_CONFIRM.format(
            name=safe(target.display_name, limit=30),
            old_role=t.ROLE_NAMES.get(target.role, safe(target.role)),
            new_role=t.ASSIGNABLE_ROLES[new_role],
        ),
        user_role_confirm_kb(target.id, new_role),
    )


@guarded
@admin_required(Permission.USERS_ROLE_CHANGE)
async def role_apply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تنفيذ تغيير الدور بعد التأكيد (التدقيق داخل `AuthService.set_role`)."""
    data = args(update)
    user_id = data.int_arg(0)
    new_role = data.arg(1)
    if new_role not in t.ASSIGNABLE_ROLES:
        await answer_callback(update, t.ERR_NO_PERMISSION, alert=True)
        return

    services = services_of(context)
    admin = require_user(context)
    target = await load_user_or_fail(context, user_id)
    changed = await services.auth.set_role(admin, target.id, new_role)

    await answer_callback(
        update,
        t.USER_ROLE_DONE.format(
            name=target.display_name, role=t.ASSIGNABLE_ROLES[new_role]
        )
        if changed
        else t.NOTHING_CHANGED,
        alert=True,
    )
    await _render_card(update, context, target.id)


# ============================== المحادثات ============================== #


def _fallbacks(name: str) -> list:
    """المسارات الاحتياطية الموحّدة لمحادثات هذا القسم."""
    return [
        CallbackQueryHandler(cancel_admin_flow, pattern=pattern(NS_FLOW, "cancel")),
        CommandHandler("cancel", cancel_admin_flow),
        CommandHandler("start", exit_conversation(name)),
    ]


def conversations() -> list[ConversationHandler]:
    """محادثات قسم المستخدمين: البحث، تعديل الرصيد، الحظر، الملاحظة."""
    search = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_search, pattern=pattern(NS_ADM_USERS, "search"))
        ],
        states={ASK_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_query)]},
        fallbacks=_fallbacks(ADMIN_FLOW_KEY),
        name="admin_user_search",
        per_chat=True,
        per_user=True,
    )

    balance = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_credit, pattern=pattern(NS_ADM_USERS, "credit")),
            CallbackQueryHandler(start_debit, pattern=pattern(NS_ADM_USERS, "debit")),
        ],
        states={
            ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_amount)],
            ASK_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_balance_reason)
            ],
            CONFIRM_BALANCE: [
                CallbackQueryHandler(confirm_balance, pattern=pattern(NS_FLOW, "confirm"))
            ],
        },
        fallbacks=_fallbacks(ADMIN_FLOW_KEY),
        name="admin_user_balance",
        per_chat=True,
        per_user=True,
    )

    ban = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_ban, pattern=pattern(NS_ADM_USERS, "ban"))],
        states={
            ASK_BAN_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ban_reason)
            ],
            CONFIRM_BAN: [
                CallbackQueryHandler(confirm_ban, pattern=pattern(NS_FLOW, "confirm"))
            ],
        },
        fallbacks=_fallbacks(ADMIN_FLOW_KEY),
        name="admin_user_ban",
        per_chat=True,
        per_user=True,
    )

    note = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_note, pattern=pattern(NS_ADM_USERS, "note"))],
        states={ASK_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_note)]},
        fallbacks=_fallbacks(ADMIN_FLOW_KEY),
        name="admin_user_note",
        per_chat=True,
        per_user=True,
    )

    return [search, balance, ban, note]


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم المستخدمين خارج المحادثات."""
    return [
        CallbackQueryHandler(users_home_screen, pattern=pattern(NS_ADM_USERS, "home")),
        CallbackQueryHandler(user_card_screen, pattern=pattern(NS_ADM_USERS, "view")),
        CallbackQueryHandler(unban_user, pattern=pattern(NS_ADM_USERS, "unban")),
        CallbackQueryHandler(role_screen, pattern=pattern(NS_ADM_USERS, "role")),
        CallbackQueryHandler(role_confirm_screen, pattern=pattern(NS_ADM_USERS, "setrole")),
        CallbackQueryHandler(role_apply, pattern=pattern(NS_ADM_USERS, "roleok")),
        CallbackQueryHandler(user_orders_screen, pattern=pattern(NS_ADM_USERS, "orders")),
        CallbackQueryHandler(user_transactions_screen, pattern=pattern(NS_ADM_USERS, "tx")),
    ]
```

### `handlers/admin/payments.py`

```python
"""
قسم «💰 المدفوعات» في لوحة التحكم: مراجعة طلبات الشحن واعتمادها أو رفضها.

المسار المعتمد (مطابق للبند 4.3 من تصميم المرحلة 0):
    قائمة المعلّق ← بطاقة الطلب ← عرض الإثبات ← (اعتماد بمبلغ قابل للتعديل
    + شاشة تأكيد) أو (رفض بسبب إجباري يصل للمستخدم).

قواعد مطبّقة:
    • إضافة الرصيد تتم داخل `PaymentService.approve` وحدها (معاملة واحدة
      تشمل: تغيير الحالة + الحركة المالية + التدقيق + إشعار المستخدم).
    • الضغط المزدوج على «اعتماد» لا يضيف الرصيد مرتين: تغيير الحالة مشروط
      بالحالة السابقة، والثانية ترفع `DuplicateOperationError` برسالة عربية.
    • المبلغ المضاف قد يختلف عن المبلغ المطلوب (حوالة ناقصة مثلاً) — ولذلك
      تُعرض شاشة تأكيد تبيّن بالضبط ما سيُضاف.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from core.enums import PaymentStatus
from core.permissions import Permission
from handlers.admin.common import (
    ADMIN_FLOW_KEY,
    PAGE_SIZE,
    admin_required,
    args,
    cancel_admin_flow,
    clear_flow,
    flow,
    paginate,
    permissions_of,
    start_flow,
    symbol_of,
    update_flow,
)
from handlers.common.fallbacks import exit_conversation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    cancel_only_kb,
    payment_approve_kb,
    payment_card_kb,
    payments_list_kb,
)
from keyboards.callback_data import NS_ADM_PAY, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from utils.formatters import datetime_text, money_text, payment_status_text, safe
from utils.logging_setup import get_logger
from utils.validators import clean_text, parse_amount_units, validate_amount_range

logger = get_logger(__name__)

#: حالات محادثة الاعتماد
CONFIRM_APPROVE, ASK_CREDITED = range(2)

#: حالة محادثة الرفض
ASK_REJECT_REASON = 10


async def _payment_card_text(context: ContextTypes.DEFAULT_TYPE, payment) -> str:
    """بناء نص بطاقة طلب الشحن (بيانات الطلب + صاحبه + حالة المراجعة)."""
    services = services_of(context)
    symbol = await symbol_of(context)
    owner = await services.users.get(payment.user_id)
    method = await services.payments.get_method(payment.method_id, require_active=False)

    proof = t.PAYMENT_PROOF_NONE
    if payment.proof_file_id:
        proof = (
            t.PAYMENT_PROOF_PHOTO if payment.proof_file_type == "photo" else t.PAYMENT_PROOF_DOC
        )

    review_line = ""
    if payment.admin_id:
        reviewer = await services.users.get(payment.admin_id)
        detail = payment.reject_reason or payment.admin_note or "—"
        review_line = t.PAYMENT_REVIEW_LINE.format(
            admin=safe(reviewer.display_name if reviewer else str(payment.admin_id), limit=30),
            detail=safe(detail, limit=200),
        )

    return t.PAYMENT_CARD.format(
        payment_id=payment.id,
        name=safe(owner.display_name if owner else "—", limit=30),
        telegram_id=owner.telegram_id if owner else "—",
        amount=money_text(payment.amount_units, symbol),
        method=safe(method.name_ar if method else "—", limit=30),
        reference=safe(payment.transaction_reference or "—", limit=40),
        proof=proof,
        created=datetime_text(payment.created_at),
        expires=datetime_text(payment.expires_at) if payment.expires_at else "—",
        status=payment_status_text(payment.status),
        note_line=t.PAYMENT_NOTE_LINE.format(note=safe(payment.user_note, limit=200))
        if payment.user_note
        else "",
        review_line=review_line,
    )


async def _render_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, payment_id: int, *, as_new: bool = False) -> None:
    """عرض بطاقة طلب شحن بعد أي إجراء عليه."""
    services = services_of(context)
    admin = require_user(context)
    payment = await services.payments.admin_get(admin, payment_id)
    perms = await permissions_of(context)
    text = await _payment_card_text(context, payment)
    markup = payment_card_kb(payment, perms, is_pending=payment.status == PaymentStatus.PENDING)
    if as_new:
        await send(update, context, text, markup)
    else:
        await render(update, context, text, markup)


# ============================= شاشات القراءة =========================== #


@guarded
@admin_required(Permission.PAYMENTS_VIEW)
async def payments_list_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة طلبات الشحن المعلّقة (أقدم أولاً حسب ترتيب الخدمة)."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    symbol = await symbol_of(context)

    total = await services.payments.pending_count()
    page, total_pages, offset = paginate(total, args(update).int_arg(0, 1))
    payments = await services.payments.pending(admin, limit=PAGE_SIZE, offset=offset)

    if not payments:
        await render(
            update, context, t.PAYMENTS_EMPTY, payments_list_kb([], page=1, total_pages=1, symbol=symbol)
        )
        return

    lines = "\n\n".join(
        f"💳 <b>#{payment.id}</b> · {money_text(payment.amount_units, symbol)}\n"
        f"   🔢 {safe(payment.transaction_reference or '—', limit=30)}\n"
        f"   🕒 {datetime_text(payment.created_at)}"
        for payment in payments
    )
    await render(
        update,
        context,
        f"{t.PAYMENTS_TITLE.format(count=total, page=page, pages=total_pages)}\n\n{lines}",
        payments_list_kb(payments, page=page, total_pages=total_pages, symbol=symbol),
    )


@guarded
@admin_required(Permission.PAYMENTS_VIEW)
async def payment_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة طلب شحن واحد."""
    await answer_callback(update)
    await _render_payment(update, context, args(update).int_arg(0))


@guarded
@admin_required(Permission.PAYMENTS_VIEW)
async def payment_proof_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إرسال ملف إثبات الدفع كما رفعه المستخدم (صورة أو مستند)."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    payment = await services.payments.admin_get(admin, args(update).int_arg(0))
    chat = update.effective_chat

    if not payment.proof_file_id or chat is None:
        await answer_callback(update, t.PAYMENT_PROOF_NONE, alert=True)
        return

    caption = t.PAYMENT_PROOF_CAPTION.format(payment_id=payment.id)
    if payment.proof_file_type == "photo":
        await context.bot.send_photo(chat_id=chat.id, photo=payment.proof_file_id, caption=caption)
    else:
        await context.bot.send_document(
            chat_id=chat.id, document=payment.proof_file_id, caption=caption
        )


# ============================ محادثة الاعتماد ========================== #


async def _approve_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, *, as_new: bool = False) -> int:
    """عرض شاشة تأكيد الاعتماد بالمبلغ الحالي (المطلوب أو المعدَّل)."""
    data = flow(context)
    services = services_of(context)
    admin = require_user(context)
    payment = await services.payments.admin_get(admin, int(data["payment_id"]))
    owner = await services.users.get(payment.user_id)
    symbol = await symbol_of(context)
    credited = int(data.get("credited_units") or payment.amount_units)

    text = t.PAYMENT_APPROVE_CONFIRM.format(
        payment_id=payment.id,
        name=safe(owner.display_name if owner else "—", limit=30),
        amount=money_text(payment.amount_units, symbol),
        credited=money_text(credited, symbol),
        balance_after=money_text((owner.balance_units if owner else 0) + credited, symbol),
    )
    if as_new:
        await send(update, context, text, payment_approve_kb())
    else:
        await render(update, context, text, payment_approve_kb())
    return CONFIRM_APPROVE


@guarded
@admin_required(Permission.PAYMENTS_APPROVE)
async def start_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء اعتماد طلب شحن: شاشة التأكيد مع المبلغ المطلوب."""
    await answer_callback(update)
    payment_id = args(update).int_arg(0)
    start_flow(context, payment_id=payment_id)
    return await _approve_confirm(update, context)


@guarded
@admin_required(Permission.PAYMENTS_APPROVE)
async def ask_credited_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """طلب مبلغ مختلف عن المبلغ المذكور في الطلب (حوالة ناقصة أو زائدة)."""
    await answer_callback(update)
    data = flow(context)
    if not data.get("payment_id"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    payment = await services.payments.admin_get(admin, int(data["payment_id"]))
    symbol = await symbol_of(context)
    await render(
        update,
        context,
        t.PAYMENT_ASK_AMOUNT.format(amount=money_text(payment.amount_units, symbol)),
        cancel_only_kb(),
    )
    return ASK_CREDITED


@guarded
@admin_required(Permission.PAYMENTS_APPROVE)
async def receive_credited_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال المبلغ المعدَّل والعودة إلى شاشة التأكيد."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_CREDITED

    units = validate_amount_range(parse_amount_units(message.text), min_units=1, label="المبلغ")
    update_flow(context, credited_units=units)
    return await _approve_confirm(update, context, as_new=True)


@guarded
@admin_required(Permission.PAYMENTS_APPROVE)
async def confirm_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """اعتماد الطلب فعلياً: إضافة الرصيد + الحركة المالية + الإشعار (داخل الخدمة)."""
    await answer_callback(update)
    data = flow(context)
    if not data.get("payment_id"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    payment_id = int(data["payment_id"])
    credited = data.get("credited_units")
    symbol = await symbol_of(context)

    transaction = await services.payments.approve(
        admin,
        payment_id,
        credited_units=int(credited) if credited else None,
        admin_note=None,
    )
    owner = await services.users.get(transaction.user_id)
    clear_flow(context)
    logger.info("اعتمد الأدمن %s طلب الشحن #%s", admin.telegram_id, payment_id)

    await render(
        update,
        context,
        t.PAYMENT_APPROVED.format(
            payment_id=payment_id,
            name=safe(owner.display_name if owner else "—", limit=30),
            credited=money_text(transaction.amount_units, symbol),
            balance=money_text(transaction.balance_after_units, symbol),
        ),
    )
    await _render_payment(update, context, payment_id, as_new=True)
    return ConversationHandler.END


# ============================= محادثة الرفض ============================ #


@guarded
@admin_required(Permission.PAYMENTS_REJECT)
async def start_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء رفض طلب شحن: السبب إجباري ويصل للمستخدم كما كُتب."""
    await answer_callback(update)
    payment_id = args(update).int_arg(0)
    start_flow(context, payment_id=payment_id)
    await render(
        update, context, t.PAYMENT_ASK_REJECT_REASON.format(payment_id=payment_id), cancel_only_kb()
    )
    return ASK_REJECT_REASON


@guarded
@admin_required(Permission.PAYMENTS_REJECT)
async def receive_reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ الرفض بعد استلام السبب (الخدمة تُشعر المستخدم وتسجّل التدقيق)."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_REJECT_REASON

    data = flow(context)
    if not data.get("payment_id"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    reason = clean_text(message.text, field="سبب الرفض", max_length=300, min_length=3)
    services = services_of(context)
    admin = require_user(context)
    payment_id = int(data["payment_id"])
    await services.payments.reject(admin, payment_id, reason)
    clear_flow(context)
    logger.info("رفض الأدمن %s طلب الشحن #%s", admin.telegram_id, payment_id)

    await send(
        update,
        context,
        t.PAYMENT_REJECTED.format(payment_id=payment_id, reason=safe(reason, limit=300)),
    )
    await _render_payment(update, context, payment_id, as_new=True)
    return ConversationHandler.END


# ============================== التسجيل ================================ #


def _fallbacks() -> list:
    """المسارات الاحتياطية الموحّدة لمحادثات هذا القسم."""
    return [
        CallbackQueryHandler(cancel_admin_flow, pattern=pattern(NS_FLOW, "cancel")),
        CommandHandler("cancel", cancel_admin_flow),
        CommandHandler("start", exit_conversation(ADMIN_FLOW_KEY)),
    ]


def conversations() -> list[ConversationHandler]:
    """محادثتا الاعتماد والرفض."""
    approve = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_approve, pattern=pattern(NS_ADM_PAY, "ok"))],
        states={
            CONFIRM_APPROVE: [
                CallbackQueryHandler(confirm_approve, pattern=pattern(NS_FLOW, "confirm")),
                CallbackQueryHandler(
                    ask_credited_amount, pattern=pattern(NS_ADM_PAY, "amount")
                ),
            ],
            ASK_CREDITED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_credited_amount)
            ],
        },
        fallbacks=_fallbacks(),
        name="admin_payment_approve",
        per_chat=True,
        per_user=True,
    )

    reject = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_reject, pattern=pattern(NS_ADM_PAY, "no"))],
        states={
            ASK_REJECT_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reject_reason)
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_payment_reject",
        per_chat=True,
        per_user=True,
    )
    return [approve, reject]


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم المدفوعات خارج المحادثات."""
    return [
        CallbackQueryHandler(payments_list_screen, pattern=pattern(NS_ADM_PAY, "list")),
        CallbackQueryHandler(payment_card_screen, pattern=pattern(NS_ADM_PAY, "view")),
        CallbackQueryHandler(payment_proof_screen, pattern=pattern(NS_ADM_PAY, "proof")),
    ]
```

### `handlers/admin/orders.py`

```python
"""
قسم «📦 الطلبات» في لوحة التحكم.

ما ينفّذه هذا الملف:
    • قوائم الطلبات مصنّفة: «تحتاج تدخلاً» (غير مؤكدة/فاشلة) · «نشطة» · «الكل».
    • بطاقة الطلب بكل تفاصيله التشغيلية (المزود، رقمه، المحاولات، آخر خطأ).
    • إعادة الفحص الفوري، الإلغاء مع استرجاع، تأكيد الفشل مع استرجاع،
      ربط رقم المزود يدوياً، وتجاوز الحالة يدوياً بسبب مكتوب.

قواعد مطبّقة:
    • لا حركة مالية في هذا الملف: الاسترجاع يتم داخل `OrderService` عبر
      `WalletService` فقط، ونحن نعرض النتيجة.
    • لا تغيير حالة بلا تحقق: كل الأزرار تمر بدوال الخدمة التي تفحص الحالة
      السابقة (`expected_statuses`) وجدول الانتقالات.
    • أزرار الإجراءات تظهر فقط حين تكون ممكنة فعلاً (حسب الحالة والصلاحية).
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from core.permissions import Permission
from handlers.admin.common import (
    ADMIN_FLOW_KEY,
    PAGE_SIZE,
    admin_required,
    args,
    cancel_admin_flow,
    clear_flow,
    flow,
    paginate,
    permissions_of,
    start_flow,
    symbol_of,
    update_flow,
)
from handlers.common.fallbacks import exit_conversation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    ADMIN_ORDER_FILTERS,
    admin_order_card_kb,
    admin_orders_kb,
    cancel_only_kb,
    confirm_cancel_kb,
    order_override_kb,
)
from keyboards.callback_data import NS_ADM_ORD, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from utils.formatters import (
    datetime_text,
    money_text,
    order_status_text,
    safe,
    short_link,
)
from utils.logging_setup import get_logger
from utils.validators import clean_text

logger = get_logger(__name__)

#: حالات محادثة الإلغاء / تأكيد الفشل (نفس التسلسل، تختلف العملية فقط)
ASK_REASON, CONFIRM_ACTION = range(2)

#: حالة محادثة ربط رقم المزود
ASK_PROVIDER_ID = 10

#: حالة محادثة تجاوز الحالة يدوياً
ASK_OVERRIDE_REASON = 20


def _filter_of(code: str) -> tuple[str, tuple[str, ...]]:
    """اسم التصفية وحالاتها (مع العودة للافتراضي عند رمز غير معروف)."""
    return ADMIN_ORDER_FILTERS.get(code, ADMIN_ORDER_FILTERS["att"])


async def _order_card_text(context: ContextTypes.DEFAULT_TYPE, order) -> str:
    """بناء نص بطاقة الطلب الإدارية."""
    services = services_of(context)
    symbol = await symbol_of(context)
    owner = await services.users.get(order.user_id)
    provider = await services.providers.get(order.provider_id)

    provider_line = ""
    if order.provider_order_id:
        provider_line = t.ORDER_PROVIDER_LINE.format(
            provider=safe(provider.name if provider else "—", limit=25),
            provider_order_id=safe(order.provider_order_id, limit=30),
        )
    progress_line = ""
    if order.delivered_quantity or order.remains:
        progress_line = t.ORDER_PROGRESS_LINE.format(
            delivered=order.delivered_quantity or 0, remains=order.remains or 0
        )
    error_line = (
        t.ORDER_ERROR_LINE.format(error=safe(order.last_error, limit=140))
        if order.last_error
        else ""
    )
    refund_line = (
        t.ORDER_REFUND_LINE.format(amount=money_text(order.refund_amount_units, symbol))
        if order.refund_amount_units
        else ""
    )

    return t.ORDER_CARD.format(
        code=safe(order.public_code or f"#{order.id}", limit=20),
        name=safe(owner.display_name if owner else "—", limit=30),
        telegram_id=owner.telegram_id if owner else "—",
        service=safe(order.service_name_snapshot, limit=45),
        link=short_link(order.link),
        quantity=order.quantity,
        cost=money_text(order.cost_units, symbol),
        status=order_status_text(order.status),
        progress_line=progress_line,
        provider_line=provider_line,
        error_line=error_line,
        refund_line=refund_line,
        created=datetime_text(order.created_at),
        attempts=order.submit_attempts,
        checks=order.checks_count,
    )


async def _render_order(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    order_id: int,
    *,
    filter_code: str = "all",
    page: int = 1,
    as_new: bool = False,
) -> None:
    """عرض بطاقة طلب بعد أي إجراء (تحرير الرسالة أو إرسال رسالة جديدة)."""
    services = services_of(context)
    admin = require_user(context)
    order = await services.orders.admin_get(admin, order_id)
    perms = await permissions_of(context)
    text = await _order_card_text(context, order)
    markup = admin_order_card_kb(order, perms, filter_code=filter_code, page=page)
    if as_new:
        await send(update, context, text, markup)
    else:
        await render(update, context, text, markup)


# ============================= شاشات القراءة =========================== #


@guarded
@admin_required(Permission.ORDERS_VIEW)
async def orders_list_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة الطلبات حسب التصفية المختارة."""
    await answer_callback(update)
    data = args(update)
    filter_code = data.arg(0, "att")
    if filter_code not in ADMIN_ORDER_FILTERS:
        filter_code = "att"
    name, statuses = _filter_of(filter_code)

    services = services_of(context)
    admin = require_user(context)
    symbol = await symbol_of(context)

    total = await services.orders.admin_count(admin, statuses=list(statuses) or None)
    page, total_pages, offset = paginate(total, data.int_arg(1, 1))
    orders = await services.orders.admin_list(
        admin, statuses=list(statuses) or None, limit=PAGE_SIZE, offset=offset
    )

    if not orders:
        await render(
            update,
            context,
            t.ORDERS_EMPTY,
            admin_orders_kb([], filter_code=filter_code, page=1, total_pages=1, symbol=symbol),
        )
        return

    lines = "\n\n".join(
        f"{order_status_text(order.status)}\n"
        f"   📦 {safe(order.public_code or f'#{order.id}', limit=20)} · "
        f"{money_text(order.cost_units, symbol)}\n"
        f"   🛍 {safe(order.service_name_snapshot, limit=36)}\n"
        f"   🕒 {datetime_text(order.created_at)}"
        for order in orders
    )
    await render(
        update,
        context,
        f"{t.ORDERS_TITLE.format(filter_name=name, count=total, page=page, pages=total_pages)}"
        f"\n\n{lines}",
        admin_orders_kb(
            orders, filter_code=filter_code, page=page, total_pages=total_pages, symbol=symbol
        ),
    )


@guarded
@admin_required(Permission.ORDERS_VIEW)
async def order_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة طلب واحد."""
    await answer_callback(update)
    data = args(update)
    await _render_order(
        update,
        context,
        data.int_arg(0),
        filter_code=data.arg(1, "all"),
        page=data.int_arg(2, 1),
    )


@guarded
@admin_required(Permission.ORDERS_RECHECK)
async def recheck_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """طلب فحص فوري لحالة الطلب لدى المزود."""
    services = services_of(context)
    admin = require_user(context)
    order_id = args(update).int_arg(0)
    result = await services.orders.recheck_now(admin, order_id)
    await answer_callback(update, t.ORDER_RECHECK_RESULT.format(result=result), alert=True)
    await _render_order(update, context, order_id)


# ===================== محادثة الإلغاء / تأكيد الفشل ==================== #


async def _start_reason_flow(
    update: Update, context: ContextTypes.DEFAULT_TYPE, *, operation: str
) -> int:
    """
    الخطوة الأولى المشتركة بين «الإلغاء» و«تعليم كفاشل»: سؤال السبب.

    المدخلات:
        operation : "cancel" أو "fail" — يحدد نص السؤال والعملية المنفَّذة لاحقاً.
    """
    await answer_callback(update)
    order_id = args(update).int_arg(0)
    services = services_of(context)
    admin = require_user(context)
    order = await services.orders.admin_get(admin, order_id)
    start_flow(context, order_id=order_id, operation=operation)

    template = t.ORDER_ASK_CANCEL_REASON if operation == "cancel" else t.ORDER_ASK_FAIL_REASON
    await render(
        update,
        context,
        template.format(code=safe(order.public_code or f"#{order.id}", limit=20)),
        cancel_only_kb(),
    )
    return ASK_REASON


@guarded
@admin_required(Permission.ORDERS_CANCEL)
async def start_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء إلغاء طلب مع استرجاع كامل."""
    return await _start_reason_flow(update, context, operation="cancel")


@guarded
@admin_required(Permission.ORDERS_REFUND)
async def start_fail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء تعليم طلب كفاشل مع استرجاع كامل."""
    return await _start_reason_flow(update, context, operation="fail")


@guarded
@admin_required(Permission.ORDERS_VIEW)
async def receive_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال السبب وعرض شاشة التأكيد مع المبلغ الذي سيُسترجع."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_REASON

    data = flow(context)
    if not data.get("order_id"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    reason = clean_text(message.text, field="السبب", max_length=200, min_length=5)
    update_flow(context, reason=reason)

    services = services_of(context)
    admin = require_user(context)
    order = await services.orders.admin_get(admin, int(data["order_id"]))
    owner = await services.users.get(order.user_id)
    symbol = await symbol_of(context)

    await send(
        update,
        context,
        t.ORDER_ACTION_CONFIRM.format(
            operation=t.OP_ORDER_CANCEL
            if data["operation"] == "cancel"
            else t.OP_ORDER_FAIL,
            code=safe(order.public_code or f"#{order.id}", limit=20),
            name=safe(owner.display_name if owner else "—", limit=30),
            amount=money_text(order.refundable_units, symbol),
            reason=safe(reason, limit=200),
        ),
        confirm_cancel_kb(),
    )
    return CONFIRM_ACTION


@guarded
@admin_required(Permission.ORDERS_VIEW)
async def confirm_reason_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ الإلغاء أو تأكيد الفشل بعد التأكيد (الاسترجاع داخل الخدمة)."""
    await answer_callback(update)
    data = flow(context)
    if not data.get("order_id") or not data.get("reason"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    order_id = int(data["order_id"])
    reason = str(data["reason"])
    operation = str(data["operation"])
    symbol = await symbol_of(context)

    if operation == "cancel":
        await services.auth.require_permission(
            admin, Permission.ORDERS_CANCEL, context=f"order:{order_id}"
        )
        refunded = await services.orders.admin_cancel(admin, order_id, reason)
        template = t.ORDER_CANCEL_DONE
    else:
        await services.auth.require_permission(
            admin, Permission.ORDERS_REFUND, context=f"order:{order_id}"
        )
        refunded = await services.orders.admin_mark_failed(admin, order_id, reason)
        template = t.ORDER_FAIL_DONE

    order = await services.orders.admin_get(admin, order_id)
    clear_flow(context)
    logger.info(
        "نفّذ الأدمن %s عملية %s على الطلب %s (استرجاع %s)",
        admin.telegram_id, operation, order_id, refunded,
    )

    await render(
        update,
        context,
        template.format(
            code=safe(order.public_code or f"#{order.id}", limit=20),
            amount=money_text(refunded, symbol),
        ),
    )
    await _render_order(update, context, order_id, as_new=True)
    return ConversationHandler.END


# ========================= محادثة ربط رقم المزود ======================= #


@guarded
@admin_required(Permission.ORDERS_LINK_PROVIDER_ID)
async def start_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء ربط الطلب برقمه عند المزود."""
    await answer_callback(update)
    order_id = args(update).int_arg(0)
    services = services_of(context)
    admin = require_user(context)
    order = await services.orders.admin_get(admin, order_id)
    start_flow(context, order_id=order_id)
    await render(
        update,
        context,
        t.ORDER_ASK_PROVIDER_ID.format(code=safe(order.public_code or f"#{order.id}", limit=20)),
        cancel_only_kb(),
    )
    return ASK_PROVIDER_ID


@guarded
@admin_required(Permission.ORDERS_LINK_PROVIDER_ID)
async def receive_provider_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ الربط (الخدمة تمنع ازدواج الرقم وتنقل الحالة إلى «أُرسل»)."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_PROVIDER_ID

    data = flow(context)
    if not data.get("order_id"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    provider_order_id = clean_text(
        message.text, field="رقم الطلب عند المزود", max_length=64, min_length=1
    )
    services = services_of(context)
    admin = require_user(context)
    order_id = int(data["order_id"])
    await services.orders.admin_link_provider_order(admin, order_id, provider_order_id)
    order = await services.orders.admin_get(admin, order_id)
    clear_flow(context)

    await send(
        update,
        context,
        t.ORDER_LINK_DONE.format(
            code=safe(order.public_code or f"#{order.id}", limit=20),
            provider_order_id=safe(provider_order_id, limit=40),
        ),
    )
    await _render_order(update, context, order_id, as_new=True)
    return ConversationHandler.END


# ======================== محادثة تجاوز الحالة ========================== #


@guarded
@admin_required(Permission.ORDERS_STATUS_OVERRIDE)
async def override_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض الحالات المسموح الانتقال إليها من حالة الطلب الحالية."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    order = await services.orders.admin_get(admin, args(update).int_arg(0))
    await render(
        update,
        context,
        t.ORDER_OVERRIDE_TITLE.format(
            code=safe(order.public_code or f"#{order.id}", limit=20),
            status=order_status_text(order.status),
        ),
        order_override_kb(order),
    )


@guarded
@admin_required(Permission.ORDERS_STATUS_OVERRIDE)
async def start_override(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بعد اختيار الحالة الجديدة: طلب سبب مكتوب (إجباري ويُسجَّل باسم الأدمن)."""
    await answer_callback(update)
    data = args(update)
    order_id = data.int_arg(0)
    new_status = data.arg(1)
    start_flow(context, order_id=order_id, new_status=new_status)
    await send(update, context, t.ORDER_ASK_OVERRIDE_REASON, cancel_only_kb())
    return ASK_OVERRIDE_REASON


@guarded
@admin_required(Permission.ORDERS_STATUS_OVERRIDE)
async def receive_override_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ تجاوز الحالة بعد استلام السبب."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_OVERRIDE_REASON

    data = flow(context)
    if not data.get("order_id") or not data.get("new_status"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    reason = clean_text(message.text, field="سبب التجاوز", max_length=200, min_length=5)
    services = services_of(context)
    admin = require_user(context)
    order_id = int(data["order_id"])
    new_status = str(data["new_status"])

    changed = await services.orders.admin_override_status(admin, order_id, new_status, reason)
    clear_flow(context)
    order = await services.orders.admin_get(admin, order_id)

    await send(
        update,
        context,
        t.ORDER_OVERRIDE_DONE.format(
            code=safe(order.public_code or f"#{order.id}", limit=20),
            status=order_status_text(order.status),
        )
        if changed
        else t.ORDER_NOT_OVERRIDABLE,
    )
    await _render_order(update, context, order_id, as_new=True)
    return ConversationHandler.END


# ============================== التسجيل ================================ #


def _fallbacks() -> list:
    """المسارات الاحتياطية الموحّدة لمحادثات هذا القسم."""
    return [
        CallbackQueryHandler(cancel_admin_flow, pattern=pattern(NS_FLOW, "cancel")),
        CommandHandler("cancel", cancel_admin_flow),
        CommandHandler("start", exit_conversation(ADMIN_FLOW_KEY)),
    ]


def conversations() -> list[ConversationHandler]:
    """محادثات قسم الطلبات: الإلغاء/الفشل، ربط رقم المزود، تجاوز الحالة."""
    reason_flow = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_cancel, pattern=pattern(NS_ADM_ORD, "cancel")),
            CallbackQueryHandler(start_fail, pattern=pattern(NS_ADM_ORD, "fail")),
        ],
        states={
            ASK_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reason)],
            CONFIRM_ACTION: [
                CallbackQueryHandler(confirm_reason_action, pattern=pattern(NS_FLOW, "confirm"))
            ],
        },
        fallbacks=_fallbacks(),
        name="admin_order_cancel",
        per_chat=True,
        per_user=True,
    )

    link_flow = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_link, pattern=pattern(NS_ADM_ORD, "link"))],
        states={
            ASK_PROVIDER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_provider_id)
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_order_link",
        per_chat=True,
        per_user=True,
    )

    override_flow = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_override, pattern=pattern(NS_ADM_ORD, "setst"))],
        states={
            ASK_OVERRIDE_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_override_reason)
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_order_override",
        per_chat=True,
        per_user=True,
    )
    return [reason_flow, link_flow, override_flow]


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم الطلبات خارج المحادثات."""
    return [
        CallbackQueryHandler(orders_list_screen, pattern=pattern(NS_ADM_ORD, "list")),
        CallbackQueryHandler(order_card_screen, pattern=pattern(NS_ADM_ORD, "view")),
        CallbackQueryHandler(recheck_order, pattern=pattern(NS_ADM_ORD, "recheck")),
        CallbackQueryHandler(override_screen, pattern=pattern(NS_ADM_ORD, "force")),
    ]
```

### `handlers/admin/tickets.py`

```python
"""
قسم «🎫 الدعم» في لوحة التحكم: قوائم التذاكر، المحادثة الكاملة، الرد، الإسناد، الإغلاق.

ما ينفّذه هذا الملف:
    • أربع قوائم: المفتوحة · بانتظار الدعم · المسندة لي · المغلقة.
    • شاشة التذكرة تعرض **كل** الرسائل بالترتيب مع تمييز المرسل.
    • الرد يصل المستخدم كإشعار، والإغلاق يحتاج سبباً مكتوباً.

قواعد مطبّقة:
    • فتح التذكرة يعلّمها «مقروءة من الأدمن» تلقائياً (داخل الخدمة).
    • لا حذف لأي رسالة أو تذكرة — الإغلاق فقط.
    • كل إجراء يسجّله `TicketService` في سجل التدقيق.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from core.enums import SenderType, TicketStatus
from core.permissions import Permission
from handlers.admin.common import (
    ADMIN_FLOW_KEY,
    PAGE_SIZE,
    admin_required,
    args,
    cancel_admin_flow,
    clear_flow,
    flow,
    paginate,
    permissions_of,
    start_flow,
)
from handlers.common.fallbacks import exit_conversation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    ADMIN_TICKET_FILTERS,
    admin_ticket_card_kb,
    admin_tickets_kb,
    cancel_only_kb,
)
from keyboards.callback_data import NS_ADM_TKT, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from services.ticket_service import OPEN_STATUSES, TICKET_CATEGORIES
from texts import admin_ar as t
from utils.formatters import datetime_text, safe, ticket_status_text
from utils.logging_setup import get_logger
from utils.validators import clean_text, validate_message

logger = get_logger(__name__)

#: حالة محادثة الرد على تذكرة
ASK_REPLY = 0

#: حالة محادثة إغلاق تذكرة
ASK_CLOSE_REASON = 10

#: عدد الرسائل المعروضة من محادثة التذكرة
CONVERSATION_LIMIT = 12

#: أيقونة كل نوع مرسل في عرض المحادثة
SENDER_ICONS: dict[str, str] = {
    SenderType.USER: "👤",
    SenderType.ADMIN: "👮",
    SenderType.SYSTEM: "🤖",
}

#: اسم كل مرسل كما يُعرض فوق رسالته
SENDER_NAMES: dict[str, str] = {
    SenderType.USER: t.SENDER_USER,
    SenderType.ADMIN: t.SENDER_ADMIN,
    SenderType.SYSTEM: t.SENDER_SYSTEM,
}


def _statuses_for(filter_code: str) -> tuple[tuple[str, ...], bool]:
    """
    الحالات المطلوبة لكل تبويب + هل يُقيَّد بالتذاكر المسندة للأدمن الحالي.

    المخرجات: (الحالات، هل التقييد بالإسناد مطلوب).
    """
    if filter_code == "wait":
        return (TicketStatus.OPEN, TicketStatus.PENDING_ADMIN), False
    if filter_code == "mine":
        return OPEN_STATUSES, True
    if filter_code == "closed":
        return (TicketStatus.CLOSED,), False
    return OPEN_STATUSES, False


async def _render_ticket(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    ticket_id: int,
    *,
    filter_code: str = "open",
    as_new: bool = False,
) -> None:
    """عرض بطاقة التذكرة مع محادثتها كاملة."""
    services = services_of(context)
    admin = require_user(context)
    ticket, messages = await services.tickets.admin_conversation(
        admin, ticket_id, limit=CONVERSATION_LIMIT
    )
    owner = await services.users.get(ticket.user_id)
    perms = await permissions_of(context)

    assigned_line = ""
    if ticket.assigned_admin:
        assignee = await services.users.get(ticket.assigned_admin)
        assigned_line = t.TICKET_ASSIGNED_LINE.format(
            admin=safe(assignee.display_name if assignee else str(ticket.assigned_admin), limit=30)
        )
    order_line = ""
    if ticket.related_order_id:
        # رمز الطلب العلني يُقرأ فقط لمن يملك صلاحية عرض الطلبات، وإلا يُعرض رقمه
        code = f"#{ticket.related_order_id}"
        if Permission.ORDERS_VIEW in perms:
            related = await services.orders.admin_get(admin, ticket.related_order_id)
            code = related.public_code or code
        order_line = t.TICKET_ORDER_LINE.format(code=safe(code, limit=20))

    conversation = "\n\n".join(
        t.TICKET_MESSAGE_LINE.format(
            icon=SENDER_ICONS.get(message.sender_type, "💬"),
            sender=SENDER_NAMES.get(message.sender_type, message.sender_type),
            when=datetime_text(message.created_at),
            message=safe(message.message, limit=600),
        )
        for message in messages
    )

    text = t.TICKET_CARD.format(
        ticket_id=ticket.id,
        name=safe(owner.display_name if owner else "—", limit=30),
        telegram_id=owner.telegram_id if owner else "—",
        subject=safe(ticket.subject, limit=80),
        category=TICKET_CATEGORIES.get(ticket.category, safe(ticket.category)),
        status=ticket_status_text(ticket.status),
        order_line=order_line,
        assigned_line=assigned_line,
        last_message=datetime_text(ticket.last_message_at or ticket.created_at),
        conversation=conversation or "—",
    )
    markup = admin_ticket_card_kb(ticket, perms, filter_code=filter_code)
    if as_new:
        await send(update, context, text, markup)
    else:
        await render(update, context, text, markup)


# ============================= شاشات القراءة =========================== #


@guarded
@admin_required(Permission.TICKETS_VIEW)
async def tickets_list_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة التذاكر حسب التبويب المختار."""
    await answer_callback(update)
    data = args(update)
    filter_code = data.arg(0, "open")
    if filter_code not in ADMIN_TICKET_FILTERS:
        filter_code = "open"

    services = services_of(context)
    admin = require_user(context)
    statuses, mine_only = _statuses_for(filter_code)
    assigned = admin.id if mine_only else None

    total = await services.tickets.admin_count(
        admin, statuses=statuses, assigned_admin=assigned
    )
    page, total_pages, offset = paginate(total, data.int_arg(1, 1))
    tickets = await services.tickets.admin_list(
        admin, statuses=statuses, assigned_admin=assigned, limit=PAGE_SIZE, offset=offset
    )
    open_count = await services.tickets.open_count()

    if not tickets:
        await render(
            update,
            context,
            t.TICKETS_EMPTY,
            admin_tickets_kb([], filter_code=filter_code, page=1, total_pages=1),
        )
        return

    lines = "\n\n".join(
        f"{ticket_status_text(ticket.status)} · <b>#{ticket.id}</b>\n"
        f"   📌 {safe(ticket.subject, limit=45)}\n"
        f"   🕒 {datetime_text(ticket.last_message_at or ticket.created_at)}"
        for ticket in tickets
    )
    await render(
        update,
        context,
        f"{t.TICKETS_TITLE.format(filter_name=ADMIN_TICKET_FILTERS[filter_code], open_count=open_count, page=page, pages=total_pages)}"
        f"\n\n{lines}",
        admin_tickets_kb(tickets, filter_code=filter_code, page=page, total_pages=total_pages),
    )


@guarded
@admin_required(Permission.TICKETS_VIEW)
async def ticket_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة التذكرة الكاملة."""
    await answer_callback(update)
    await _render_ticket(update, context, args(update).int_arg(0))


@guarded
@admin_required(Permission.TICKETS_ASSIGN)
async def assign_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إسناد التذكرة إلى الأدمن الذي ضغط الزر."""
    services = services_of(context)
    admin = require_user(context)
    ticket_id = args(update).int_arg(0)
    changed = await services.tickets.assign(admin, ticket_id, admin.id)
    await answer_callback(
        update,
        t.TICKET_ASSIGNED.format(ticket_id=ticket_id) if changed else t.NOTHING_CHANGED,
        alert=True,
    )
    await _render_ticket(update, context, ticket_id)


# ============================= محادثة الرد ============================= #


@guarded
@admin_required(Permission.TICKETS_REPLY)
async def start_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء كتابة رد على تذكرة."""
    await answer_callback(update)
    ticket_id = args(update).int_arg(0)
    start_flow(context, ticket_id=ticket_id)
    await render(update, context, t.TICKET_ASK_REPLY.format(ticket_id=ticket_id), cancel_only_kb())
    return ASK_REPLY


@guarded
@admin_required(Permission.TICKETS_REPLY)
async def receive_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إرسال الرد للمستخدم (الخدمة تُنشئ الرسالة والإشعار والتدقيق)."""
    message = update.effective_message
    if message is None or not (message.text or message.caption):
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_REPLY

    data = flow(context)
    if not data.get("ticket_id"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    body = validate_message(message.text or message.caption or "")
    attachment_id = message.photo[-1].file_id if message.photo else None
    services = services_of(context)
    admin = require_user(context)
    ticket_id = int(data["ticket_id"])

    await services.tickets.reply_as_admin(
        admin,
        ticket_id,
        body,
        attachment_file_id=attachment_id,
        attachment_type="photo" if attachment_id else None,
    )
    clear_flow(context)
    logger.info("ردّ الأدمن %s على التذكرة #%s", admin.telegram_id, ticket_id)

    await send(update, context, t.TICKET_REPLY_DONE.format(ticket_id=ticket_id))
    await _render_ticket(update, context, ticket_id, as_new=True)
    return ConversationHandler.END


# =========================== محادثة الإغلاق ============================ #


@guarded
@admin_required(Permission.TICKETS_CLOSE)
async def start_close(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء إغلاق تذكرة (سبب الإغلاق يصل المستخدم)."""
    await answer_callback(update)
    ticket_id = args(update).int_arg(0)
    start_flow(context, ticket_id=ticket_id)
    await render(
        update,
        context,
        t.TICKET_ASK_CLOSE_REASON.format(ticket_id=ticket_id),
        cancel_only_kb(),
    )
    return ASK_CLOSE_REASON


@guarded
@admin_required(Permission.TICKETS_CLOSE)
async def receive_close_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ الإغلاق بعد استلام السبب."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_CLOSE_REASON

    data = flow(context)
    if not data.get("ticket_id"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    reason = clean_text(message.text, field="سبب الإغلاق", max_length=200, min_length=3)
    services = services_of(context)
    admin = require_user(context)
    ticket_id = int(data["ticket_id"])
    await services.tickets.close(admin, ticket_id, reason)
    clear_flow(context)

    await send(update, context, t.TICKET_CLOSED.format(ticket_id=ticket_id))
    await _render_ticket(update, context, ticket_id, as_new=True)
    return ConversationHandler.END


# ============================== التسجيل ================================ #


def _fallbacks() -> list:
    """المسارات الاحتياطية الموحّدة لمحادثات هذا القسم."""
    return [
        CallbackQueryHandler(cancel_admin_flow, pattern=pattern(NS_FLOW, "cancel")),
        CommandHandler("cancel", cancel_admin_flow),
        CommandHandler("start", exit_conversation(ADMIN_FLOW_KEY)),
    ]


def conversations() -> list[ConversationHandler]:
    """محادثتا الرد والإغلاق."""
    reply = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_reply, pattern=pattern(NS_ADM_TKT, "reply"))],
        states={
            ASK_REPLY: [
                MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, receive_reply)
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_ticket_reply",
        per_chat=True,
        per_user=True,
    )

    close = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_close, pattern=pattern(NS_ADM_TKT, "close"))],
        states={
            ASK_CLOSE_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_close_reason)
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_ticket_close",
        per_chat=True,
        per_user=True,
    )
    return [reply, close]


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم الدعم خارج المحادثات."""
    return [
        CallbackQueryHandler(tickets_list_screen, pattern=pattern(NS_ADM_TKT, "list")),
        CallbackQueryHandler(ticket_card_screen, pattern=pattern(NS_ADM_TKT, "view")),
        CallbackQueryHandler(assign_ticket, pattern=pattern(NS_ADM_TKT, "assign")),
    ]
```

### `handlers/admin/catalog.py`

```python
"""
قسم «🛍 الكتالوج» في لوحة التحكم: التصنيفات والخدمات وأسعارها.

ما ينفّذه هذا الملف:
    • عرض كل التصنيفات (حتى الفارغة والمعطّلة — الأدمن يرى ما لا يراه العميل).
    • قائمة خدمات التصنيف مع مؤشر التفعيل والسعر.
    • بطاقة الخدمة: السعر، تكلفة المزود، الهامش، الحدود، الحالة.
    • تفعيل/تعطيل الخدمة، تغيير السعر (مع تحذير البيع بخسارة)، الأرشفة.
    • إنشاء تصنيف جديد.

مؤجَّل عمداً إلى المرحلة 5 (إدارة المزودين): **إنشاء خدمة جديدة** ومزامنة
خدمات المزود — لأن إنشاء خدمة يتطلب اختيار مزود ورقم خدمة لديه، وشاشات
المزودين نفسها تُبنى في تلك المرحلة. لا نعرض زراً لوظيفة غير مكتملة.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from core.permissions import Permission
from handlers.admin.common import (
    ADMIN_FLOW_KEY,
    PAGE_SIZE,
    admin_required,
    args,
    cancel_admin_flow,
    clear_flow,
    flow,
    permissions_of,
    start_flow,
    symbol_of,
    update_flow,
)
from handlers.common.fallbacks import exit_conversation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    cancel_only_kb,
    catalog_home_kb,
    catalog_services_kb,
    confirm_cancel_kb,
    service_card_kb,
    skip_cancel_kb,
)
from keyboards.callback_data import NS_ADM_CAT, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from utils.formatters import money_text, safe
from utils.logging_setup import get_logger
from utils.validators import clean_text, parse_amount_units, validate_amount_range

logger = get_logger(__name__)

#: حالات محادثة تغيير السعر
ASK_PRICE, CONFIRM_PRICE = range(2)

#: حالة محادثة الأرشفة
CONFIRM_ARCHIVE = 20

#: حالات محادثة إنشاء تصنيف
ASK_CATEGORY_NAME, ASK_CATEGORY_EMOJI = range(10, 12)


async def _render_service(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int, *, as_new: bool = False
) -> None:
    """عرض بطاقة خدمة بعد أي إجراء عليها."""
    services = services_of(context)
    admin = require_user(context)
    service = await services.catalog.admin_get_service(admin, service_id)
    category = await services.catalog.admin_get_category(admin, service.category_id)
    provider = await services.providers.get(service.provider_id)
    symbol = await symbol_of(context)
    perms = await permissions_of(context)

    margin = service.margin_units
    text = t.SERVICE_CARD.format(
        name=safe(service.name, limit=60),
        service_id=service.id,
        category=safe(category.title, limit=30),
        provider=safe(provider.name if provider else t.SERVICE_UNKNOWN_PROVIDER, limit=25),
        provider_service_id=safe(service.provider_service_id, limit=20),
        price=money_text(service.price_per_1000_units, symbol),
        cost=money_text(service.provider_price_per_1000_units, symbol)
        if service.provider_price_per_1000_units
        else "—",
        margin=money_text(margin, symbol) if margin is not None else t.SERVICE_MARGIN_UNKNOWN,
        min_quantity=service.min_quantity,
        max_quantity=service.max_quantity,
        status=t.SERVICE_STATUS_ACTIVE if service.is_active else t.SERVICE_STATUS_INACTIVE,
        archived_line=t.SERVICE_ARCHIVED_LINE if service.is_archived else "",
        description_line=t.SERVICE_DESCRIPTION_LINE.format(
            description=safe(service.description, limit=200)
        )
        if service.description
        else "",
    )
    markup = service_card_kb(service, perms)
    if as_new:
        await send(update, context, text, markup)
    else:
        await render(update, context, text, markup)


# ============================= شاشات القراءة =========================== #


@guarded
@admin_required(Permission.SERVICES_VIEW)
async def catalog_home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة الكتالوج: كل التصنيفات."""
    await answer_callback(update)
    services = services_of(context)
    admin = require_user(context)
    categories = await services.catalog.admin_categories(admin)
    perms = await permissions_of(context)
    active_services = await services.catalog.active_services_count()

    text = (
        t.CATALOG_HOME.format(categories=len(categories), active_services=active_services)
        if categories
        else t.CATALOG_NO_CATEGORIES
    )
    await render(update, context, text, catalog_home_kb(categories, perms))


@guarded
@admin_required(Permission.SERVICES_VIEW)
async def category_services_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """قائمة خدمات تصنيف (تشمل المعطّلة)."""
    await answer_callback(update)
    data = args(update)
    category_id = data.int_arg(0)
    services = services_of(context)
    admin = require_user(context)
    symbol = await symbol_of(context)

    category = await services.catalog.admin_get_category(admin, category_id)
    page_data = await services.catalog.admin_services_page(
        admin, category_id, page=data.int_arg(1, 1), page_size=PAGE_SIZE
    )

    if not page_data.items:
        await render(
            update,
            context,
            t.CATALOG_SERVICES_EMPTY,
            catalog_services_kb(
                [], category_id=category_id, page=1, total_pages=1, symbol=symbol
            ),
        )
        return

    await render(
        update,
        context,
        t.CATALOG_SERVICES_TITLE.format(
            category=safe(category.title, limit=40),
            count=page_data.total_items,
            page=page_data.page,
            pages=page_data.total_pages,
        ),
        catalog_services_kb(
            page_data.items,
            category_id=category_id,
            page=page_data.page,
            total_pages=page_data.total_pages,
            symbol=symbol,
        ),
    )


@guarded
@admin_required(Permission.SERVICES_VIEW)
async def service_card_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بطاقة خدمة واحدة."""
    await answer_callback(update)
    await _render_service(update, context, args(update).int_arg(0))


@guarded
@admin_required(Permission.SERVICES_UPDATE)
async def toggle_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تفعيل أو تعطيل خدمة (الحالة تنعكس فوراً على واجهة العملاء)."""
    services = services_of(context)
    admin = require_user(context)
    service_id = args(update).int_arg(0)
    service = await services.catalog.admin_get_service(admin, service_id)

    await services.catalog.set_service_active(admin, service_id, not service.is_active)
    await answer_callback(
        update,
        t.SERVICE_TOGGLED_OFF if service.is_active else t.SERVICE_TOGGLED_ON,
        alert=False,
    )
    await _render_service(update, context, service_id)


# =========================== محادثة تغيير السعر ======================== #


@guarded
@admin_required(Permission.SERVICES_PRICE)
async def start_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء تغيير سعر خدمة."""
    await answer_callback(update)
    service_id = args(update).int_arg(0)
    services = services_of(context)
    admin = require_user(context)
    service = await services.catalog.admin_get_service(admin, service_id)
    symbol = await symbol_of(context)
    start_flow(context, service_id=service_id)

    await render(
        update,
        context,
        t.SERVICE_ASK_PRICE.format(
            name=safe(service.name, limit=50),
            price=money_text(service.price_per_1000_units, symbol),
            cost=money_text(service.provider_price_per_1000_units, symbol)
            if service.provider_price_per_1000_units
            else "—",
        ),
        cancel_only_kb(),
    )
    return ASK_PRICE


@guarded
@admin_required(Permission.SERVICES_PRICE)
async def receive_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    استقبال السعر الجديد.

    إن كان أقل من تكلفة المزود نعرض شاشة تأكيد إضافية (بيع بخسارة)، وإلا
    نُنفّذ مباشرة لأن التغيير غير خطير ماليّاً على المستخدمين.
    """
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_PRICE

    data = flow(context)
    if not data.get("service_id"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    units = validate_amount_range(parse_amount_units(message.text), min_units=1, label="السعر")
    services = services_of(context)
    admin = require_user(context)
    service = await services.catalog.admin_get_service(admin, int(data["service_id"]))
    symbol = await symbol_of(context)

    cost = service.provider_price_per_1000_units or 0
    if cost and units < cost:
        update_flow(context, price_units=units)
        await send(update, context, t.SERVICE_PRICE_BELOW_COST, confirm_cancel_kb())
        return CONFIRM_PRICE

    await services.catalog.change_price(admin, service.id, units)
    clear_flow(context)
    await send(update, context, t.SERVICE_PRICE_DONE.format(price=money_text(units, symbol)))
    await _render_service(update, context, service.id, as_new=True)
    return ConversationHandler.END


@guarded
@admin_required(Permission.SERVICES_PRICE)
async def confirm_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تأكيد سعر أقل من تكلفة المزود."""
    await answer_callback(update)
    data = flow(context)
    if not data.get("service_id") or not data.get("price_units"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    service_id = int(data["service_id"])
    units = int(data["price_units"])
    symbol = await symbol_of(context)

    await services.catalog.change_price(admin, service_id, units)
    clear_flow(context)
    logger.info("غيّر الأدمن %s سعر الخدمة %s إلى %s", admin.telegram_id, service_id, units)

    await render(update, context, t.SERVICE_PRICE_DONE.format(price=money_text(units, symbol)))
    await _render_service(update, context, service_id, as_new=True)
    return ConversationHandler.END


# ============================ محادثة الأرشفة =========================== #


@guarded
@admin_required(Permission.SERVICES_ARCHIVE)
async def start_archive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """عرض تأكيد أرشفة الخدمة (إخفاؤها نهائياً عن العملاء)."""
    await answer_callback(update)
    service_id = args(update).int_arg(0)
    services = services_of(context)
    admin = require_user(context)
    service = await services.catalog.admin_get_service(admin, service_id)
    start_flow(context, service_id=service_id)

    await render(
        update,
        context,
        t.SERVICE_ARCHIVE_CONFIRM.format(name=safe(service.name, limit=50)),
        confirm_cancel_kb(),
    )
    return CONFIRM_ARCHIVE


@guarded
@admin_required(Permission.SERVICES_ARCHIVE)
async def confirm_archive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ الأرشفة بعد التأكيد."""
    await answer_callback(update)
    data = flow(context)
    if not data.get("service_id"):
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    service_id = int(data["service_id"])
    await services.catalog.archive_service(admin, service_id)
    clear_flow(context)

    await render(update, context, t.SERVICE_ARCHIVED)
    await _render_service(update, context, service_id, as_new=True)
    return ConversationHandler.END


# ========================== محادثة تصنيف جديد ========================== #


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def start_new_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء إنشاء تصنيف جديد."""
    await answer_callback(update)
    start_flow(context)
    await render(update, context, t.CATEGORY_ASK_NAME, cancel_only_kb())
    return ASK_CATEGORY_NAME


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def receive_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال اسم التصنيف ثم سؤال الأيقونة (قابلة للتخطي)."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_CATEGORY_NAME

    name = clean_text(message.text, field="اسم التصنيف", max_length=60, min_length=2)
    update_flow(context, name=name)
    await send(update, context, t.CATEGORY_ASK_EMOJI, skip_cancel_kb())
    return ASK_CATEGORY_EMOJI


async def _create_category(
    update: Update, context: ContextTypes.DEFAULT_TYPE, emoji: str
) -> int:
    """إنشاء التصنيف فعلياً وعرض الكتالوج محدَّثاً."""
    data = flow(context)
    if not data.get("name"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    category = await services.catalog.create_category(
        admin, name_ar=str(data["name"]), emoji=emoji
    )
    clear_flow(context)
    logger.info("أنشأ الأدمن %s التصنيف %s", admin.telegram_id, category.id)

    await send(update, context, t.CATEGORY_CREATED.format(name=safe(category.title, limit=40)))
    await catalog_home_screen(update, context)
    return ConversationHandler.END


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def receive_category_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """استقبال أيقونة التصنيف وإنشاؤه."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, skip_cancel_kb())
        return ASK_CATEGORY_EMOJI
    emoji = clean_text(message.text, field="الأيقونة", max_length=4, min_length=1)
    return await _create_category(update, context, emoji)


@guarded
@admin_required(Permission.SERVICES_CREATE)
async def skip_category_emoji(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تخطي الأيقونة واستخدام الافتراضية."""
    await answer_callback(update)
    return await _create_category(update, context, "📦")


# ============================== التسجيل ================================ #


def _fallbacks() -> list:
    """المسارات الاحتياطية الموحّدة لمحادثات هذا القسم."""
    return [
        CallbackQueryHandler(cancel_admin_flow, pattern=pattern(NS_FLOW, "cancel")),
        CommandHandler("cancel", cancel_admin_flow),
        CommandHandler("start", exit_conversation(ADMIN_FLOW_KEY)),
    ]


def conversations() -> list[ConversationHandler]:
    """محادثات الكتالوج: تغيير السعر، الأرشفة، تصنيف جديد."""
    price = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_price, pattern=pattern(NS_ADM_CAT, "price"))],
        states={
            ASK_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_price)],
            CONFIRM_PRICE: [
                CallbackQueryHandler(confirm_price, pattern=pattern(NS_FLOW, "confirm"))
            ],
        },
        fallbacks=_fallbacks(),
        name="admin_service_price",
        per_chat=True,
        per_user=True,
    )

    archive = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_archive, pattern=pattern(NS_ADM_CAT, "archive"))
        ],
        states={
            CONFIRM_ARCHIVE: [
                CallbackQueryHandler(confirm_archive, pattern=pattern(NS_FLOW, "confirm"))
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_service_archive",
        per_chat=True,
        per_user=True,
    )

    new_category = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_new_category, pattern=pattern(NS_ADM_CAT, "newcat"))
        ],
        states={
            ASK_CATEGORY_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_category_name)
            ],
            ASK_CATEGORY_EMOJI: [
                CallbackQueryHandler(skip_category_emoji, pattern=pattern(NS_FLOW, "skip")),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_category_emoji),
            ],
        },
        fallbacks=_fallbacks(),
        name="admin_new_category",
        per_chat=True,
        per_user=True,
    )
    return [price, archive, new_category]


def screens() -> list[CallbackQueryHandler]:
    """أزرار الكتالوج خارج المحادثات."""
    return [
        CallbackQueryHandler(catalog_home_screen, pattern=pattern(NS_ADM_CAT, "home")),
        CallbackQueryHandler(category_services_screen, pattern=pattern(NS_ADM_CAT, "cat")),
        CallbackQueryHandler(service_card_screen, pattern=pattern(NS_ADM_CAT, "svc")),
        CallbackQueryHandler(toggle_service, pattern=pattern(NS_ADM_CAT, "toggle")),
    ]
```

### `handlers/admin/settings.py`

```python
"""
قسم «⚙️ الإعدادات» في لوحة التحكم.

ما ينفّذه هذا الملف:
    • عرض مجموعات الإعدادات ثم مفاتيح كل مجموعة بقيمها الحالية.
    • تعديل قيمة أي مفتاح قابل للتعديل (مع فرض نوع القيمة عند الحفظ).
    • مفتاح وضع الصيانة بزر واحد مع تأكيد.

قواعد مطبّقة:
    • المفاتيح غير القابلة للتعديل (`is_editable = 0`) تُعرض ولا يظهر لها زر.
    • كل تعديل يُسجَّل في سجل التدقيق باسم الأدمن (داخل `SettingsService.set`).
    • الكاش يُبطَل تلقائياً بعد الحفظ فتسري القيمة فوراً على كل الطلبات.
"""

from __future__ import annotations

import json

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from core.exceptions import ValidationError
from core.permissions import Permission
from handlers.admin.common import (
    ADMIN_FLOW_KEY,
    PAGE_SIZE,
    admin_required,
    args,
    cancel_admin_flow,
    clear_flow,
    flow,
    paginate,
    permissions_of,
    start_flow,
)
from handlers.common.fallbacks import exit_conversation
from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.admin_kb import (
    cancel_only_kb,
    confirm_cancel_kb,
    settings_group_kb,
    settings_home_kb,
)
from keyboards.callback_data import NS_ADM_SET, NS_FLOW, pattern
from middlewares.context import require_user, services_of
from texts import admin_ar as t
from utils.formatters import safe
from utils.logging_setup import get_logger
from utils.validators import clean_text, normalize_digits

logger = get_logger(__name__)

#: حالة محادثة تعديل قيمة مفتاح
ASK_VALUE = 0

#: حالة تأكيد تبديل وضع الصيانة
CONFIRM_MAINTENANCE = 10

#: مفتاح وضع الصيانة في جدول الإعدادات
MAINTENANCE_KEY = "maintenance_mode"

#: القيم المقبولة للإعدادات المنطقية (تُطبَّع إلى true/false قبل الحفظ)
TRUE_WORDS = {"1", "true", "yes", "on", "نعم", "تفعيل", "مفعل"}
FALSE_WORDS = {"0", "false", "no", "off", "لا", "تعطيل", "معطل"}


def _normalize_value(raw: str, value_type: str) -> str:
    """
    التحقق من موافقة القيمة لنوع المفتاح وتطبيعها قبل الحفظ.

    لماذا هنا؟ طبقة الإعدادات تخزّن نصاً خاماً، فلو حُفظ نص في مفتاح رقمي
    لانفجرت القراءة لاحقاً في مكان بعيد. نمنع ذلك عند مصدر الإدخال الوحيد.

    الاستثناءات:
        ValidationError : القيمة لا تناسب نوع المفتاح.
    """
    text = raw.strip()
    if value_type == "bool":
        lowered = text.lower()
        if lowered in TRUE_WORDS:
            return "true"
        if lowered in FALSE_WORDS:
            return "false"
        raise ValidationError(
            f"قيمة منطقية غير صالحة: {text}",
            user_message="❌ أرسل true أو false (أو 1 / 0).",
        )
    if value_type in {"int", "money"}:
        cleaned = normalize_digits(text).replace(",", "").strip()
        if not cleaned.lstrip("-").isdigit():
            raise ValidationError(
                f"قيمة رقمية غير صالحة: {text}", user_message="❌ أرسل رقماً صحيحاً."
            )
        return str(int(cleaned))
    if value_type == "json":
        try:
            json.loads(text)
        except ValueError as exc:
            raise ValidationError(
                f"JSON غير صالح: {exc}", user_message="❌ النص ليس JSON صالحاً."
            ) from exc
        return text
    return text


@guarded
@admin_required(Permission.SETTINGS_VIEW)
async def settings_home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة الإعدادات: المجموعات + حالة وضع الصيانة."""
    await answer_callback(update)
    services = services_of(context)
    groups = await services.settings.groups()
    perms = await permissions_of(context)
    maintenance = await services.settings.is_maintenance()

    await render(
        update,
        context,
        t.SETTINGS_HOME.format(
            maintenance=t.MAINTENANCE_ON if maintenance else t.MAINTENANCE_OFF
        ),
        settings_home_kb(groups, perms, maintenance_on=maintenance),
    )


@guarded
@admin_required(Permission.SETTINGS_VIEW)
async def settings_group_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """مفاتيح مجموعة إعدادات مع قيمها الحالية."""
    await answer_callback(update)
    data = args(update)
    group = data.arg(0)
    services = services_of(context)
    perms = await permissions_of(context)

    items = await services.settings.group(group)
    if not items:
        await render(
            update,
            context,
            t.SETTINGS_GROUP_EMPTY,
            settings_group_kb([], group=group, page=1, total_pages=1, perms=perms),
        )
        return

    page, total_pages, offset = paginate(len(items), data.int_arg(1, 1))
    window = items[offset : offset + PAGE_SIZE]
    lines = "\n\n".join(
        t.SETTING_LINE.format(
            name=safe(item.name_ar or item.key, limit=50),
            key=safe(item.key, limit=50),
            value=safe(item.value, limit=60),
        )
        + ("" if item.is_editable else "\n   🔒 غير قابل للتعديل")
        for item in window
    )
    await render(
        update,
        context,
        t.SETTINGS_GROUP_TITLE.format(
            group=safe(group, limit=30), page=page, pages=total_pages, lines=lines
        ),
        settings_group_kb(
            window, group=group, page=page, total_pages=total_pages, perms=perms
        ),
    )


# =========================== محادثة تعديل القيمة ======================= #


@guarded
@admin_required(Permission.SETTINGS_UPDATE)
async def start_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """بدء تعديل قيمة مفتاح إعداد."""
    await answer_callback(update)
    key = args(update).arg(0)
    services = services_of(context)
    items = {item.key: item for item in await services.settings.all_settings()}
    setting = items.get(key)

    if setting is None:
        await answer_callback(update, t.ERR_SESSION_LOST, alert=True)
        return ConversationHandler.END
    if not setting.is_editable:
        await answer_callback(update, t.SETTING_NOT_EDITABLE, alert=True)
        return ConversationHandler.END

    start_flow(context, key=key, group=setting.group_code)
    await render(
        update,
        context,
        t.SETTING_ASK_VALUE.format(
            name=safe(setting.name_ar or setting.key, limit=50),
            key=safe(setting.key, limit=50),
            value=safe(setting.value, limit=80),
            value_type=safe(setting.value_type, limit=20),
            description=safe(setting.description_ar or "", limit=200),
        ),
        cancel_only_kb(),
    )
    return ASK_VALUE


@guarded
@admin_required(Permission.SETTINGS_UPDATE)
async def receive_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """حفظ القيمة الجديدة (التحقق من النوع داخل `SettingsService.set`)."""
    message = update.effective_message
    if message is None or not message.text:
        await send(update, context, t.ERR_NOT_TEXT, cancel_only_kb())
        return ASK_VALUE

    data = flow(context)
    if not data.get("key"):
        await send(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    raw = clean_text(message.text, field="القيمة", max_length=500, min_length=1)
    services = services_of(context)
    admin = require_user(context)
    key = str(data["key"])

    items = {item.key: item for item in await services.settings.all_settings()}
    setting = items.get(key)
    if setting is None or not setting.is_editable:
        clear_flow(context)
        await send(update, context, t.SETTING_NOT_EDITABLE)
        return ConversationHandler.END

    value = _normalize_value(raw, setting.value_type)
    changed = await services.settings.set(key, value, admin_id=admin.id)
    clear_flow(context)
    logger.info("عدّل الأدمن %s الإعداد %s", admin.telegram_id, key)

    await send(
        update,
        context,
        t.SETTING_UPDATED.format(key=safe(key, limit=50), value=safe(value, limit=80))
        if changed
        else t.SETTING_NOT_EDITABLE,
    )
    await settings_home_screen(update, context)
    return ConversationHandler.END


# ========================== محادثة وضع الصيانة ========================= #


@guarded
@admin_required(Permission.SETTINGS_MAINTENANCE)
async def start_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """عرض تأكيد تبديل وضع الصيانة (يؤثر على كل المستخدمين فوراً)."""
    await answer_callback(update)
    services = services_of(context)
    current = await services.settings.is_maintenance()
    start_flow(context, turn_on=not current)
    await render(
        update,
        context,
        t.MAINTENANCE_CONFIRM_OFF if current else t.MAINTENANCE_CONFIRM_ON,
        confirm_cancel_kb(),
    )
    return CONFIRM_MAINTENANCE


@guarded
@admin_required(Permission.SETTINGS_MAINTENANCE)
async def confirm_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """تنفيذ تبديل وضع الصيانة."""
    await answer_callback(update)
    data = flow(context)
    if "turn_on" not in data:
        await render(update, context, t.ERR_SESSION_LOST)
        return ConversationHandler.END

    services = services_of(context)
    admin = require_user(context)
    turn_on = bool(data["turn_on"])
    await services.settings.set(MAINTENANCE_KEY, "true" if turn_on else "false", admin_id=admin.id)
    clear_flow(context)
    logger.warning(
        "%s وضع الصيانة بواسطة الأدمن %s", "فعّل" if turn_on else "أوقف", admin.telegram_id
    )

    await render(
        update, context, t.MAINTENANCE_TOGGLED_ON if turn_on else t.MAINTENANCE_TOGGLED_OFF
    )
    await settings_home_screen(update, context)
    return ConversationHandler.END


# ============================== التسجيل ================================ #


def _fallbacks() -> list:
    """المسارات الاحتياطية الموحّدة لمحادثات هذا القسم."""
    return [
        CallbackQueryHandler(cancel_admin_flow, pattern=pattern(NS_FLOW, "cancel")),
        CommandHandler("cancel", cancel_admin_flow),
        CommandHandler("start", exit_conversation(ADMIN_FLOW_KEY)),
    ]


def conversations() -> list[ConversationHandler]:
    """محادثتا تعديل قيمة وتبديل وضع الصيانة."""
    edit = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_edit, pattern=pattern(NS_ADM_SET, "edit"))],
        states={ASK_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_value)]},
        fallbacks=_fallbacks(),
        name="admin_setting_edit",
        per_chat=True,
        per_user=True,
    )

    maintenance = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_maintenance, pattern=pattern(NS_ADM_SET, "maint"))
        ],
        states={
            CONFIRM_MAINTENANCE: [
                CallbackQueryHandler(confirm_maintenance, pattern=pattern(NS_FLOW, "confirm"))
            ]
        },
        fallbacks=_fallbacks(),
        name="admin_maintenance",
        per_chat=True,
        per_user=True,
    )
    return [edit, maintenance]


def screens() -> list[CallbackQueryHandler]:
    """أزرار الإعدادات خارج المحادثات."""
    return [
        CallbackQueryHandler(settings_home_screen, pattern=pattern(NS_ADM_SET, "home")),
        CallbackQueryHandler(settings_group_screen, pattern=pattern(NS_ADM_SET, "group")),
    ]
```

### `handlers/admin/logs.py`

```python
"""
قسم «📝 السجلات» في لوحة التحكم: سجل التدقيق وسجل الأخطاء.

لماذا هذه الشاشة مهمة؟
    سجل التدقيق هو الجواب على سؤال «من فعل ماذا ومتى» — وهو شرط أساسي في
    أي نظام يتعامل مع أموال. عرضه داخل البوت يعني ألا يحتاج صاحب النظام
    فتح قاعدة البيانات ليعرف ما جرى.

ملاحظات:
    • العرض للقراءة فقط — لا تعديل ولا حذف لأي سجل من الواجهة إطلاقاً.
    • الأخطاء تُعرض بمقتطف قصير بلا أي بيانات حساسة (التنقية تمت عند الكتابة).
"""

from __future__ import annotations

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
from keyboards.admin_kb import logs_home_kb, logs_page_kb
from keyboards.callback_data import NS_ADM_LOG, pattern
from middlewares.context import services_of
from texts import admin_ar as t
from utils.formatters import datetime_text, safe


def _audit_icon(action: str) -> str:
    """اختيار أيقونة السطر حسب بادئة اسم الإجراء (users.ban ⇐ 👤)."""
    prefix = (action or "").split(".", 1)[0]
    return t.AUDIT_ICONS.get(prefix, "🔸")


@guarded
@admin_required(Permission.LOGS_VIEW)
async def logs_home_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """شاشة اختيار السجل."""
    await answer_callback(update)
    await render(update, context, t.LOGS_HOME, logs_home_kb())


@guarded
@admin_required(Permission.LOGS_VIEW)
async def audit_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """سجل التدقيق: آخر العمليات الإدارية مع منفّذها وهدفها ووقتها."""
    await answer_callback(update)
    services = services_of(context)
    total = await services.audit.count()
    page, total_pages, offset = paginate(total, args(update).int_arg(0, 1), LOG_PAGE_SIZE)
    entries = await services.audit.recent(limit=LOG_PAGE_SIZE, offset=offset)

    if not entries:
        await render(update, context, t.AUDIT_EMPTY, logs_page_kb("audit", page=1, total_pages=1))
        return

    admins: dict[int, str] = {}
    lines: list[str] = []
    for entry in entries:
        label = "النظام"
        if entry.admin_id:
            if entry.admin_id not in admins:
                admin_user = await services.users.get(entry.admin_id)
                admins[entry.admin_id] = (
                    admin_user.display_name if admin_user else str(entry.admin_id)
                )
            label = admins[entry.admin_id]
        target = (
            f"{entry.target_type}:{entry.target_id}" if entry.target_type else "—"
        )
        lines.append(
            t.AUDIT_LINE.format(
                icon=_audit_icon(entry.action),
                action=safe(entry.action, limit=40),
                admin=safe(label, limit=25),
                target=safe(target, limit=30),
                when=datetime_text(entry.created_at),
            )
        )

    await render(
        update,
        context,
        t.AUDIT_TITLE.format(page=page, pages=total_pages, lines="\n\n".join(lines)),
        logs_page_kb("audit", page=page, total_pages=total_pages),
    )


@guarded
@admin_required(Permission.LOGS_VIEW)
async def errors_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """سجل الأخطاء: آخر ما سجّله النظام من أعطال."""
    await answer_callback(update)
    services = services_of(context)
    page = max(1, args(update).int_arg(0, 1))
    entries = await services.audit.recent_errors(
        limit=LOG_PAGE_SIZE, offset=(page - 1) * LOG_PAGE_SIZE
    )

    if not entries:
        await render(
            update, context, t.ERRORS_EMPTY, logs_page_kb("errors", page=1, total_pages=1)
        )
        return

    lines = "\n\n".join(
        t.ERROR_LINE.format(
            level=safe(str(entry.get("level", "ERROR")), limit=10),
            source=safe(str(entry.get("source") or "—"), limit=30),
            message=safe(str(entry.get("message") or "—"), limit=160),
            when=datetime_text(str(entry.get("created_at") or "")),
        )
        for entry in entries
    )
    # عدد الصفحات غير معروف مسبقاً هنا: نُظهر «التالي» ما دامت الصفحة ممتلئة
    has_more = len(entries) == LOG_PAGE_SIZE
    await render(
        update,
        context,
        t.ERRORS_TITLE.format(page=page, lines=lines),
        logs_page_kb("errors", page=page, total_pages=page + 1 if has_more else page),
    )


def conversations() -> list:
    """لا محادثات في قسم السجلات (عرض فقط)."""
    return []


def screens() -> list[CallbackQueryHandler]:
    """أزرار قسم السجلات."""
    return [
        CallbackQueryHandler(logs_home_screen, pattern=pattern(NS_ADM_LOG, "home")),
        CallbackQueryHandler(audit_screen, pattern=pattern(NS_ADM_LOG, "audit")),
        CallbackQueryHandler(errors_screen, pattern=pattern(NS_ADM_LOG, "errors")),
    ]
```

## الربط والتنقل

### `handlers/registry.py`

```python
"""
تسجيل كل معالجات البوت في مكان واحد.

لماذا ملف تسجيل مستقل؟
    • ترتيب المعالجات مهم جداً في python-telegram-bot: المحادثات قبل الأوامر
      العامة، والمسارات الاحتياطية في النهاية. تجميعها هنا يجعل الترتيب مرئياً
      ومراجعته سهلة بدل تناثره في `main.py`.
    • يتيح اختباراً آلياً يتحقق أن **كل زر في الواجهة له معالج فعلي**
      (`tests/integration/test_no_dead_buttons.py`) — تطبيقاً لقاعدة
      «ممنوع أزرار بلا وظيفة».

ترتيب المجموعات:
    المجموعة -10 : الطبقة الوسيطة (مستخدم/حظر/صيانة/حد استخدام) — تسبق كل شيء.
    المجموعة  0  : المحادثات ثم الأوامر ثم أزرار الشاشات ثم المسارات الاحتياطية.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import (
    Application,
    BaseHandler,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    TypeHandler,
    filters,
)

from handlers.admin import (
    admin_command_handlers,
    admin_conversations,
    admin_screen_handlers,
)
from handlers.common import errors, fallbacks, navigation
from handlers.user import account, catalog, deposit, order_flow, orders, support, wallet
from keyboards.callback_data import (
    NS_ACCOUNT,
    NS_CATALOG,
    NS_DEPOSIT,
    NS_NAV,
    NS_NEW,
    NS_ORDERS,
    NS_SUPPORT,
    NS_WALLET,
    pattern,
)
from middlewares.context import UserContextMiddleware
from middlewares.rate_limit import RateLimiter

#: مجموعة الطبقة الوسيطة (قبل كل المعالجات)
MIDDLEWARE_GROUP = -10

#: المجموعة الرئيسية لكل معالجات الواجهة
MAIN_GROUP = 0


def _order_conversation() -> ConversationHandler:
    """محادثة إنشاء طلب: رابط ← كمية ← تأكيد."""
    cancel_handlers = [
        CallbackQueryHandler(order_flow.cancel_order_flow, pattern=pattern("flow", "cancel")),
        CommandHandler("cancel", order_flow.cancel_order_flow),
        CommandHandler("start", fallbacks.exit_conversation(order_flow.FLOW_KEY)),
    ]
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(order_flow.start_order, pattern=pattern(NS_NEW, "start"))],
        states={
            order_flow.ASK_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, order_flow.receive_link)
            ],
            order_flow.ASK_QUANTITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, order_flow.receive_quantity)
            ],
            order_flow.CONFIRM: [
                CallbackQueryHandler(order_flow.confirm_order, pattern=pattern("flow", "confirm"))
            ],
        },
        fallbacks=cancel_handlers,
        name="order_flow",
        per_chat=True,
        per_user=True,
    )


def _deposit_conversation() -> ConversationHandler:
    """محادثة شحن الرصيد: طريقة ← مبلغ ← مرجع ← إيصال ← تأكيد."""
    cancel_handlers = [
        CallbackQueryHandler(deposit.cancel_deposit_flow, pattern=pattern("flow", "cancel")),
        CommandHandler("cancel", deposit.cancel_deposit_flow),
        CommandHandler("start", fallbacks.exit_conversation(deposit.FLOW_KEY)),
    ]
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(deposit.start_deposit, pattern=pattern(NS_DEPOSIT, "start"))],
        states={
            deposit.CHOOSE_METHOD: [
                CallbackQueryHandler(deposit.choose_method, pattern=pattern(NS_DEPOSIT, "method"))
            ],
            deposit.ASK_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, deposit.receive_amount)
            ],
            deposit.ASK_REFERENCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, deposit.receive_reference)
            ],
            deposit.ASK_PROOF: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, deposit.receive_proof),
                CallbackQueryHandler(deposit.skip_proof, pattern=pattern("flow", "skip")),
                MessageHandler(filters.TEXT & ~filters.COMMAND, deposit.receive_proof),
            ],
            deposit.CONFIRM: [
                CallbackQueryHandler(deposit.confirm_deposit, pattern=pattern("flow", "confirm"))
            ],
        },
        fallbacks=cancel_handlers,
        name="deposit_flow",
        per_chat=True,
        per_user=True,
    )


def _new_ticket_conversation() -> ConversationHandler:
    """محادثة فتح تذكرة: تصنيف ← عنوان ← شرح (أو مباشرة من بطاقة الطلب)."""
    cancel_handlers = [
        CallbackQueryHandler(support.cancel_support_flow, pattern=pattern("flow", "cancel")),
        CommandHandler("cancel", support.cancel_support_flow),
        CommandHandler("start", fallbacks.exit_conversation(support.NEW_FLOW_KEY)),
    ]
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(support.start_new_ticket, pattern=pattern(NS_SUPPORT, "new")),
            CallbackQueryHandler(
                support.start_ticket_for_order, pattern=pattern(NS_SUPPORT, "neworder")
            ),
        ],
        states={
            support.ASK_CATEGORY: [
                CallbackQueryHandler(support.choose_ticket_category, pattern=pattern(NS_SUPPORT, "cat"))
            ],
            support.ASK_SUBJECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, support.receive_subject)
            ],
            support.ASK_MESSAGE: [
                MessageHandler(
                    (filters.TEXT | filters.PHOTO) & ~filters.COMMAND, support.receive_ticket_message
                )
            ],
        },
        fallbacks=cancel_handlers,
        name="new_ticket_flow",
        per_chat=True,
        per_user=True,
    )


def _ticket_reply_conversation() -> ConversationHandler:
    """محادثة إضافة رد على تذكرة قائمة."""
    cancel_handlers = [
        CallbackQueryHandler(support.cancel_support_flow, pattern=pattern("flow", "cancel")),
        CommandHandler("cancel", support.cancel_support_flow),
        CommandHandler("start", fallbacks.exit_conversation(support.REPLY_FLOW_KEY)),
    ]
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(support.start_reply, pattern=pattern(NS_SUPPORT, "reply"))
        ],
        states={
            support.ASK_REPLY: [
                MessageHandler(
                    (filters.TEXT | filters.PHOTO) & ~filters.COMMAND, support.receive_reply
                )
            ],
        },
        fallbacks=cancel_handlers,
        name="ticket_reply_flow",
        per_chat=True,
        per_user=True,
    )


def screen_handlers() -> list[CallbackQueryHandler]:
    """
    معالجات أزرار الشاشات (خارج المحادثات).

    القائمة مرتبة حسب الشاشة، وكل سطر هنا يقابل زراً فعلياً في `keyboards/`.
    """
    return [
        # التنقل العام
        CallbackQueryHandler(navigation.home_callback, pattern=pattern(NS_NAV, "home")),
        CallbackQueryHandler(navigation.page_indicator_callback, pattern=pattern(NS_NAV, "page")),
        # الخدمات
        CallbackQueryHandler(catalog.categories_screen, pattern=pattern(NS_CATALOG, "list")),
        CallbackQueryHandler(catalog.services_screen, pattern=pattern(NS_CATALOG, "open")),
        CallbackQueryHandler(catalog.service_card_screen, pattern=pattern(NS_CATALOG, "svc")),
        # الطلبات
        CallbackQueryHandler(orders.orders_list_screen, pattern=pattern(NS_ORDERS, "list")),
        CallbackQueryHandler(orders.order_card_screen, pattern=pattern(NS_ORDERS, "view")),
        CallbackQueryHandler(orders.order_cancel_confirm, pattern=pattern(NS_ORDERS, "cancel")),
        CallbackQueryHandler(orders.order_cancel_execute, pattern=pattern(NS_ORDERS, "cancelyes")),
        # المحفظة والشحن
        CallbackQueryHandler(wallet.wallet_screen, pattern=pattern(NS_WALLET, "home")),
        CallbackQueryHandler(wallet.history_screen, pattern=pattern(NS_WALLET, "history")),
        CallbackQueryHandler(deposit.deposits_list_screen, pattern=pattern(NS_DEPOSIT, "list")),
        CallbackQueryHandler(deposit.cancel_payment, pattern=pattern(NS_DEPOSIT, "cancel")),
        # الدعم
        CallbackQueryHandler(support.support_home, pattern=pattern(NS_SUPPORT, "home")),
        CallbackQueryHandler(support.tickets_list_screen, pattern=pattern(NS_SUPPORT, "list")),
        CallbackQueryHandler(support.ticket_card_screen, pattern=pattern(NS_SUPPORT, "view")),
        CallbackQueryHandler(support.close_ticket, pattern=pattern(NS_SUPPORT, "close")),
        # الحساب والمعلومات
        CallbackQueryHandler(account.account_screen, pattern=pattern(NS_ACCOUNT, "home")),
        CallbackQueryHandler(account.notifications_screen, pattern=pattern(NS_ACCOUNT, "notif")),
        CallbackQueryHandler(account.mark_all_read, pattern=pattern(NS_ACCOUNT, "readall")),
        CallbackQueryHandler(account.info_screen, pattern=pattern(NS_ACCOUNT, "info")),
        # لوحة التحكم (كل معالج يفحص صلاحيته بنفسه عبر admin_required)
        *admin_screen_handlers(),
    ]


def conversation_handlers() -> list[ConversationHandler]:
    """
    كل المحادثات بالترتيب الذي تُسجَّل به: محادثات العميل ثم محادثات لوحة الأدمن.

    محادثات الأدمن تأتي بعد محادثات العميل ولكن **قبل** أزرار الشاشات، لأن
    نقاط دخولها أزرار يجب أن تلتقطها المحادثة لا معالج الشاشة.
    """
    return [
        _order_conversation(),
        _deposit_conversation(),
        _new_ticket_conversation(),
        _ticket_reply_conversation(),
        *admin_conversations(),
    ]


def build_handlers(limiter: RateLimiter | None = None) -> list[tuple[int, BaseHandler]]:
    """
    بناء قائمة (المجموعة، المعالج) بالترتيب الصحيح.

    الترتيب داخل المجموعة 0:
        المحادثات ← الأوامر العامة ← أزرار الشاشات ← المسارات الاحتياطية.
    السبب: المحادثة النشطة يجب أن تلتقط /start و/cancel قبل المعالج العام،
    والمسار الاحتياطي يجب أن يكون الأخير حتى لا يبتلع أزراراً صحيحة.
    """
    handlers: list[tuple[int, BaseHandler]] = [
        (MIDDLEWARE_GROUP, TypeHandler(Update, UserContextMiddleware(limiter)))
    ]

    for conversation in conversation_handlers():
        handlers.append((MAIN_GROUP, conversation))

    handlers.extend(
        [
            (MAIN_GROUP, CommandHandler("start", navigation.start_command)),
            (MAIN_GROUP, CommandHandler("help", navigation.help_command)),
            (MAIN_GROUP, CommandHandler("id", navigation.id_command)),
            (MAIN_GROUP, CommandHandler("cancel", fallbacks.cancel_command)),
        ]
    )

    for command in admin_command_handlers():
        handlers.append((MAIN_GROUP, command))

    for handler in screen_handlers():
        handlers.append((MAIN_GROUP, handler))

    handlers.extend(
        [
            (MAIN_GROUP, CallbackQueryHandler(fallbacks.unknown_callback)),
            (MAIN_GROUP, MessageHandler(filters.COMMAND, fallbacks.unknown_command)),
            (MAIN_GROUP, MessageHandler(filters.TEXT | filters.ATTACHMENT, fallbacks.free_text)),
        ]
    )
    return handlers


def register_handlers(application: Application, limiter: RateLimiter | None = None) -> int:
    """
    تسجيل كل المعالجات على التطبيق وإرجاع عددها.

    المخرجات: عدد المعالجات المسجَّلة (يُطبع في سجل الإقلاع للتأكيد).
    """
    registered = build_handlers(limiter)
    for group, handler in registered:
        application.add_handler(handler, group=group)
    application.add_error_handler(errors.error_handler)
    return len(registered)
```

### `handlers/common/navigation.py`

```python
"""
شاشة البداية والقائمة الرئيسية والأوامر العامة.

يشمل:
    /start  : تسجيل/ترحيب ثم القائمة الرئيسية.
    /help   : شرح مختصر لطريقة الاستخدام.
    /id     : عرض معرف تيليجرام (يطلبه الدعم أحياناً).
    nav:home: العودة للقائمة الرئيسية من أي شاشة.
    nav:page: زر عدّاد الصفحات — يعرض موضع المستخدم بدل أن يكون زراً صامتاً.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from handlers.common.guards import guarded
from handlers.common.ui import answer_callback, render, send
from keyboards.callback_data import unpack
from keyboards.user_kb import main_menu_kb
from middlewares.context import require_user, services_of
from texts import ar
from utils.formatters import money_text, safe


async def is_admin_user(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    هل يملك صاحب هذا التحديث حق دخول لوحة التحكم؟

    تُستدعى قبل بناء القائمة الرئيسية حتى يظهر زر «🛠 لوحة التحكم» لمن يستحقه
    فقط، وتختفي فوراً عمن سُحبت صلاحيته (تُقرأ من قاعدة البيانات كل مرة).
    """
    services = services_of(context)
    return await services.auth.is_admin(require_user(context))


async def main_menu_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    بناء نص القائمة الرئيسية بأرقام حقيقية (رصيد، طلبات نشطة، تذاكر مفتوحة).

    المخرجات: نص HTML جاهز للعرض.
    """
    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    summary = await services.users.summary(user)
    return ar.MAIN_MENU_BODY.format(
        balance=money_text(user.balance_units, symbol),
        active_orders=summary.active_orders,
        open_tickets=summary.tickets_open,
    )


@guarded
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الأمر /start: رسالة ترحيب (مختلفة للجديد) ثم القائمة الرئيسية."""
    services = services_of(context)
    user = require_user(context)
    symbol = await services.settings.money_symbol()
    is_new = bool(context.user_data and context.user_data.get("is_new_user"))

    if is_new:
        welcome = await services.settings.get_str(
            "welcome_message", "أهلاً بك في بوت خدمات التواصل الاجتماعي."
        )
        text = ar.WELCOME_NEW.format(
            name=safe(user.first_name or "", limit=30),
            welcome=safe(welcome),
            balance=money_text(user.balance_units, symbol),
        )
    else:
        text = ar.WELCOME_BACK.format(
            name=safe(user.first_name or "", limit=30),
            balance=money_text(user.balance_units, symbol),
        )

    await send(update, context, text)
    await send(
        update,
        context,
        await main_menu_text(context),
        main_menu_kb(is_admin=await is_admin_user(context)),
    )


@guarded
async def home_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """زر «القائمة الرئيسية» من أي شاشة."""
    await answer_callback(update)
    await render(
        update,
        context,
        await main_menu_text(context),
        main_menu_kb(is_admin=await is_admin_user(context)),
    )


@guarded
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الأمر /help: شرح خطوات الاستخدام والأوامر المتاحة."""
    await send(
        update, context, ar.HELP_TEXT, main_menu_kb(is_admin=await is_admin_user(context))
    )


@guarded
async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """الأمر /id: عرض معرف المستخدم في تيليجرام."""
    user = require_user(context)
    await send(update, context, ar.ID_TEXT.format(telegram_id=user.telegram_id))


@guarded
async def page_indicator_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    زر عدّاد الصفحات: يعرض موضع المستخدم الحالي كتنبيه منبثق.

    سبب وجوده: القاعدة تمنع الأزرار بلا وظيفة — فحتى زر العرض يفعل شيئاً مفيداً.
    """
    data = unpack(update.callback_query.data if update.callback_query else None)
    await answer_callback(
        update, ar.PAGE_INFO.format(page=data.int_arg(0, 1), pages=data.int_arg(1, 1))
    )
```

### `core/constants.py`

```python
"""ثوابت عامة للنظام (قيم لا تتغير أثناء التشغيل)."""

from __future__ import annotations

#: اسم المشروع وإصداره
APP_NAME: str = "SMM Telegram Bot"
APP_VERSION: str = "0.5.0-phase4"

#: مدة قفل الطلب أثناء معالجته بواسطة job (بالثواني)
ORDER_LOCK_SECONDS: int = 120

#: أقصى عدد محاولات لإرسال الطلب إلى المزود عند الفشل الآمن (قبل اعتباره فاشلاً)
MAX_SUBMIT_ATTEMPTS: int = 3

#: أقصى عدد محاولات إرسال إشعار قبل اعتباره فاشلاً
MAX_NOTIFICATION_ATTEMPTS: int = 5

#: تدرج فترات إعادة فحص حالة الطلب (بالثواني)
ORDER_CHECK_BACKOFF: tuple[int, ...] = (60, 300, 900, 1800, 3600)

#: تدرج فترات إعادة إرسال الإشعار الفاشل (بالثواني)
NOTIFICATION_BACKOFF: tuple[int, ...] = (10, 60, 300, 1800, 3600)

#: مدة صلاحية مفاتيح منع التكرار الافتراضية (بالثواني)
IDEMPOTENCY_TTL_SECONDS: int = 24 * 3600

#: طول أقصى للنصوص المُخزَّنة من استجابات المزود (منعاً لتضخم قاعدة البيانات)
PROVIDER_RESPONSE_SNIPPET_LEN: int = 500

#: عدد العناصر في صفحة القوائم داخل تيليجرام
PAGE_SIZE: int = 8

#: صيغة مراجع الحركات المالية (تُستخدم لمنع التكرار)
REF_ORDER_DEBIT: str = "order:{order_id}"
REF_ORDER_REFUND: str = "refund:order:{order_id}"
REF_ORDER_PARTIAL_REFUND: str = "partial_refund:order:{order_id}"
REF_PAYMENT_DEPOSIT: str = "payment:{payment_id}"
REF_MANUAL: str = "manual:{kind}:{admin_id}:{token}"

#: صيغة مفاتيح منع تكرار الإشعارات
NOTIF_KEY_ORDER: str = "order:{order_id}:{event}"
NOTIF_KEY_PAYMENT: str = "payment:{payment_id}:{event}"
NOTIF_KEY_TICKET: str = "ticket:{ticket_id}:{event}"
NOTIF_KEY_MANUAL: str = "manual:{token}"
```

## الخدمات والمستودعات المُحدَّثة

### `services/catalog_service.py`

```python
"""
خدمة الكتالوج: التصنيفات والخدمات وحساب سعر الطلب قبل تأكيده.

مبدأ مهم: سعر الخدمة يُقرأ من قاعدة البيانات في لحظة الطلب ويُخزَّن كلقطة داخل الطلب،
فتغيير السعر لاحقاً لا يؤثر على الطلبات القديمة ولا على المحاسبة.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.constants import PAGE_SIZE
from core.exceptions import ServiceNotAvailableError
from core.money import format_units, order_cost_units, unit_price_units
from core.permissions import Permission
from database.database import Database
from database.models import Service, ServiceCategory, User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.settings_service import SettingsService
from utils.logging_setup import get_logger
from utils.validators import clean_text, validate_quantity

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Quote:
    """تسعيرة طلب قبل تأكيده."""

    service: Service
    quantity: int
    cost_units: int
    symbol: str
    decimals: int

    @property
    def cost_text(self) -> str:
        """التكلفة بصيغة نصية جاهزة للعرض."""
        return format_units(self.cost_units, symbol=self.symbol, decimals=self.decimals)

    @property
    def price_per_1000_text(self) -> str:
        """سعر الألف بصيغة نصية."""
        return format_units(
            self.service.price_per_1000_units, symbol=self.symbol, decimals=self.decimals
        )


@dataclass(frozen=True, slots=True)
class Page:
    """صفحة من قائمة (خدمات أو غيرها) مع معلومات التنقل."""

    items: list
    page: int
    total_items: int
    page_size: int

    @property
    def total_pages(self) -> int:
        """عدد الصفحات الكلي (واحد على الأقل)."""
        return max(1, -(-self.total_items // self.page_size))

    @property
    def has_next(self) -> bool:
        """هل توجد صفحة تالية؟"""
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        """هل توجد صفحة سابقة؟"""
        return self.page > 1


class CatalogService:
    """تصفح الخدمات وحساب التسعيرة وإدارة الكتالوج من لوحة الأدمن."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        audit: AuditService,
        auth: AuthService,
    ) -> None:
        """تهيئة الخدمة."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.audit = audit
        self.auth = auth

    # ------------------------------- التصفح ------------------------------- #

    async def categories(self) -> list[ServiceCategory]:
        """التصنيفات التي تحتوي خدمات متاحة فعلاً (لا نعرض تصنيفاً فارغاً للمستخدم)."""
        return await self.repos.categories.list_with_available_services()

    async def services_page(self, category_id: int, *, page: int = 1, page_size: int = PAGE_SIZE) -> Page:
        """صفحة من خدمات تصنيف معيّن."""
        page = max(1, page)
        total = await self.repos.services.count_by_category(category_id, only_available=True)
        items = await self.repos.services.list_by_category(
            category_id, only_available=True, limit=page_size, offset=(page - 1) * page_size
        )
        return Page(items=list(items), page=page, total_items=total, page_size=page_size)

    async def search(self, text: str, *, limit: int = 10) -> list[Service]:
        """بحث نصي في أسماء الخدمات المتاحة."""
        cleaned = clean_text(text, field="نص البحث", max_length=60, min_length=2)
        return await self.repos.services.search(cleaned, limit=limit)

    async def get_available_service(self, service_id: int) -> Service:
        """
        جلب خدمة متاحة للطلب.

        الاستثناءات:
            ServiceNotAvailableError : الخدمة غير موجودة أو معطّلة أو مؤرشفة
                                       أو مزودها متوقف.
        """
        service = await self.repos.services.get_available(service_id)
        if service is None:
            raise ServiceNotAvailableError(f"الخدمة {service_id} غير متاحة للطلب")
        return service

    async def quote(self, service: Service, raw_quantity: str | int) -> Quote:
        """
        حساب تكلفة الطلب بعد التحقق من الكمية.

        الاستثناءات:
            QuantityOutOfRangeError : الكمية خارج حدود الخدمة.
        """
        quantity = validate_quantity(
            raw_quantity, min_quantity=service.min_quantity, max_quantity=service.max_quantity
        )
        cost = order_cost_units(service.price_per_1000_units, quantity)
        _, symbol, decimals = await self.settings.currency()
        return Quote(
            service=service, quantity=quantity, cost_units=cost, symbol=symbol, decimals=decimals
        )

    async def unit_price(self, service: Service) -> str:
        """سعر الوحدة الواحدة (للعرض التفصيلي)."""
        _, symbol, decimals = await self.settings.currency()
        price = unit_price_units(service.price_per_1000_units)
        return f"{price:.6f} {symbol}".strip()

    # ------------------------ قراءة من لوحة الأدمن ------------------------ #

    async def admin_categories(self, actor: User) -> list[ServiceCategory]:
        """
        كل التصنيفات كما هي في قاعدة البيانات (حتى الفارغة والمعطّلة).

        تختلف عن `categories()` الموجّهة للعميل: الأدمن يحتاج رؤية ما لا يراه العميل
        ليستطيع إصلاحه.

        الاستثناءات: PermissionDeniedError
        """
        await self.auth.require_permission(actor, Permission.SERVICES_VIEW, context="catalog")
        return await self.repos.categories.list_all(active_only=False)

    async def admin_services_page(
        self, actor: User, category_id: int, *, page: int = 1, page_size: int = PAGE_SIZE
    ) -> Page:
        """
        صفحة خدمات تصنيف في لوحة الأدمن — تشمل المعطّلة (لا تشمل المؤرشفة).

        الاستثناءات: PermissionDeniedError
        """
        await self.auth.require_permission(
            actor, Permission.SERVICES_VIEW, context=f"category:{category_id}"
        )
        page = max(1, page)
        total = await self.repos.services.count_by_category(category_id, only_available=False)
        items = await self.repos.services.list_by_category(
            category_id, only_available=False, limit=page_size, offset=(page - 1) * page_size
        )
        return Page(items=list(items), page=page, total_items=total, page_size=page_size)

    async def admin_get_service(self, actor: User, service_id: int) -> Service:
        """
        جلب خدمة بأي حالة لعرض بطاقتها الإدارية.

        الاستثناءات: PermissionDeniedError · ServiceNotAvailableError (غير موجودة)
        """
        await self.auth.require_permission(
            actor, Permission.SERVICES_VIEW, context=f"service:{service_id}"
        )
        service = await self.repos.services.get(service_id)
        if service is None:
            raise ServiceNotAvailableError(
                f"الخدمة {service_id} غير موجودة", user_message="❌ الخدمة غير موجودة."
            )
        return service

    async def active_services_count(self) -> int:
        """عدد الخدمات المفعّلة (يُعرض في رأس شاشة الكتالوج)."""
        return await self.repos.services.count_active()

    async def admin_get_category(self, actor: User, category_id: int) -> ServiceCategory:
        """
        جلب تصنيف بالمعرف لعرض عنوانه فوق قائمة خدماته.

        الاستثناءات: PermissionDeniedError · ServiceNotAvailableError (غير موجود)
        """
        await self.auth.require_permission(
            actor, Permission.SERVICES_VIEW, context=f"category:{category_id}"
        )
        category = await self.repos.categories.get(category_id)
        if category is None:
            raise ServiceNotAvailableError(
                f"التصنيف {category_id} غير موجود", user_message="❌ التصنيف غير موجود."
            )
        return category

    # --------------------------- إدارة الكتالوج --------------------------- #

    async def create_category(self, actor: User, *, name_ar: str, emoji: str = "📦", sort_order: int = 100) -> ServiceCategory:
        """إضافة تصنيف جديد (صلاحية services.create)."""
        await self.auth.require_permission(actor, Permission.SERVICES_CREATE, context="category.create")
        clean_name = clean_text(name_ar, field="اسم التصنيف", max_length=60, min_length=2)
        async with self.db.transaction() as tx:
            category = await self.repos.categories.create(
                tx, name_ar=clean_name, emoji=emoji, sort_order=sort_order
            )
            await self.audit.log(
                tx,
                action="services.category.create",
                admin_id=actor.id,
                target_type="category",
                target_id=category.id,
                after={"name_ar": clean_name},
            )
        return category

    async def create_service(
        self,
        actor: User,
        *,
        category_id: int,
        provider_id: int,
        provider_service_id: str,
        name: str,
        price_per_1000_units: int,
        min_quantity: int,
        max_quantity: int,
        provider_price_per_1000_units: int | None = None,
        description: str | None = None,
        link_pattern: str | None = None,
    ) -> Service:
        """
        إضافة خدمة جديدة للكتالوج.

        الاستثناءات: PermissionDeniedError · ValidationError
        """
        await self.auth.require_permission(actor, Permission.SERVICES_CREATE, context="service.create")
        clean_name = clean_text(name, field="اسم الخدمة", max_length=120, min_length=3)
        async with self.db.transaction() as tx:
            service = await self.repos.services.create(
                tx,
                category_id=category_id,
                provider_id=provider_id,
                provider_service_id=str(provider_service_id),
                name=clean_name,
                price_per_1000_units=price_per_1000_units,
                min_quantity=min_quantity,
                max_quantity=max_quantity,
                provider_price_per_1000_units=provider_price_per_1000_units,
                description=description,
                link_pattern=link_pattern,
            )
            await self.audit.log(
                tx,
                action="services.create",
                admin_id=actor.id,
                target_type="service",
                target_id=service.id,
                after={
                    "name": clean_name,
                    "price_per_1000_units": price_per_1000_units,
                    "provider_id": provider_id,
                },
            )
        logger.info("أضاف الأدمن %s الخدمة %s (%s)", actor.id, service.id, clean_name)
        return service

    async def change_price(self, actor: User, service_id: int, new_price_units: int) -> bool:
        """
        تغيير سعر خدمة مع حفظ السعر القديم في السجل التاريخي.

        الاستثناءات: PermissionDeniedError
        """
        await self.auth.require_permission(actor, Permission.SERVICES_PRICE, context=f"service:{service_id}")
        service = await self.repos.services.get(service_id)
        if service is None:
            return False
        async with self.db.transaction() as tx:
            changed = await self.repos.services.change_price(
                tx, service_id, new_price_units=new_price_units, changed_by=actor.id, source="admin"
            )
            if changed:
                await self.audit.log(
                    tx,
                    action="services.price",
                    admin_id=actor.id,
                    target_type="service",
                    target_id=service_id,
                    before={"price_per_1000_units": service.price_per_1000_units},
                    after={"price_per_1000_units": new_price_units},
                )
        return changed

    async def set_service_active(self, actor: User, service_id: int, active: bool) -> bool:
        """تفعيل أو تعطيل خدمة (لا حذف — الطلبات القديمة تبقى سليمة)."""
        await self.auth.require_permission(actor, Permission.SERVICES_ARCHIVE, context=f"service:{service_id}")
        async with self.db.transaction() as tx:
            changed = await self.repos.services.set_active(tx, service_id, active)
            if changed:
                await self.audit.log(
                    tx,
                    action="services.update",
                    admin_id=actor.id,
                    target_type="service",
                    target_id=service_id,
                    after={"is_active": active},
                )
        return changed

    async def archive_service(self, actor: User, service_id: int) -> bool:
        """أرشفة خدمة (إخفاؤها نهائياً مع الاحتفاظ ببياناتها التاريخية)."""
        await self.auth.require_permission(actor, Permission.SERVICES_ARCHIVE, context=f"service:{service_id}")
        async with self.db.transaction() as tx:
            changed = await self.repos.services.archive(tx, service_id)
            if changed:
                await self.audit.log(
                    tx,
                    action="services.archive",
                    admin_id=actor.id,
                    target_type="service",
                    target_id=service_id,
                    after={"is_archived": True},
                )
        return changed

    async def negative_margin_report(self, actor: User) -> list[Service]:
        """
        الخدمات التي أصبح سعر بيعها أقل من تكلفتها لدى المزود.

        الاستثناءات: PermissionDeniedError (تحتاج صلاحية عرض الخدمات).
        """
        await self.auth.require_permission(actor, Permission.SERVICES_VIEW, context="services.margin")
        return await self.repos.services.negative_margin_services()
```

### `services/audit_service.py`

```python
"""
خدمة سجل التدقيق: تسجيل كل عملية إدارية حسّاسة بمن نفّذها وما تغيّر.

قاعدة المشروع: أي إجراء إداري يمسّ المال أو الصلاحيات أو بيانات المستخدمين
يجب أن يترك أثراً في هذا السجل — والسجل لا يُحذف.
"""

from __future__ import annotations

from typing import Any

from database.database import Database, Tx
from database.models import AuditLog
from database.repositories import Repositories
from utils.logging_setup import get_logger
from utils.security import sanitize

logger = get_logger(__name__)


class AuditService:
    """كتابة وقراءة سجل التدقيق."""

    def __init__(self, db: Database, repos: Repositories) -> None:
        """تهيئة الخدمة."""
        self.db = db
        self.repos = repos

    # ------------------------------- الكتابة ------------------------------ #

    async def log(
        self,
        tx: Tx,
        *,
        action: str,
        admin_id: int | None = None,
        target_type: str | None = None,
        target_id: str | int | None = None,
        before: Any = None,
        after: Any = None,
        details: Any = None,
        source: str = "telegram",
    ) -> int | None:
        """
        تسجيل عملية داخل معاملة قائمة (حتى يسقط السجل مع العملية إن فشلت).

        ملاحظة أمنية: كل النصوص تمر على أداة تنقية الأسرار قبل التخزين.
        """
        return await self.repos.audit.log(
            tx,
            action=action,
            admin_id=admin_id,
            target_type=target_type,
            target_id=target_id,
            before=_clean(before),
            after=_clean(after),
            details=_clean(details),
            source=source,
        )

    async def log_standalone(
        self,
        *,
        action: str,
        admin_id: int | None = None,
        target_type: str | None = None,
        target_id: str | int | None = None,
        details: Any = None,
        source: str = "system",
    ) -> int | None:
        """تسجيل عملية بمعاملة مستقلة (عندما لا توجد معاملة جارية)."""
        async with self.db.transaction() as tx:
            return await self.log(
                tx,
                action=action,
                admin_id=admin_id,
                target_type=target_type,
                target_id=target_id,
                details=details,
                source=source,
            )

    async def log_permission_denied(
        self, *, user_id: int, permission: str, context: str = ""
    ) -> None:
        """
        تسجيل محاولة وصول مرفوضة.

        تُسجَّل دائماً لأنها مؤشر أمني مهم (محاولة استخدام زر إداري بلا صلاحية).
        """
        async with self.db.transaction() as tx:
            await self.repos.audit.log(
                tx,
                action="security.permission_denied",
                admin_id=user_id,
                target_type="permission",
                target_id=permission,
                details={"context": sanitize(context)},
                source="security",
            )
        logger.warning("رُفض وصول المستخدم %s إلى الصلاحية %s (%s)", user_id, permission, context)

    # ------------------------------- القراءة ------------------------------ #

    async def recent(self, *, limit: int = 20, offset: int = 0) -> list[AuditLog]:
        """أحدث عمليات التدقيق (لعرضها في اللوحة)."""
        return await self.repos.audit.list_recent(limit=limit, offset=offset)

    async def by_admin(self, admin_id: int, *, limit: int = 20, offset: int = 0) -> list[AuditLog]:
        """سجل عمليات أدمن محدد."""
        return await self.repos.audit.list_by_admin(admin_id, limit=limit, offset=offset)

    async def by_target(self, target_type: str, target_id: str | int, *, limit: int = 20) -> list[AuditLog]:
        """سجل العمليات التي جرت على هدف محدد (مستخدم، طلب، إعداد…)."""
        return await self.repos.audit.list_by_target(target_type, target_id, limit=limit)

    async def count(self) -> int:
        """إجمالي عدد السجلات."""
        return await self.repos.audit.count_all()

    async def recent_errors(self, *, limit: int = 10, offset: int = 0) -> list[dict]:
        """
        آخر الأخطاء المسجَّلة في `error_logs` (شاشة «السجلات ← الأخطاء»).

        وُضعت هنا لأن شاشة السجلات واحدة في لوحة الأدمن: التدقيق والأخطاء معاً،
        وفحص صلاحية `logs.view` يتم في طبقة المعالجات قبل الوصول إليها.
        """
        return await self.repos.error_logs.list_recent(limit=limit, offset=offset)

    async def errors_since(self, since_iso: str) -> int:
        """عدد الأخطاء منذ وقت محدد (يُعرض كمؤشر في رأس شاشة الأخطاء)."""
        return await self.repos.error_logs.count_since(since_iso)


def _clean(value: Any) -> Any:
    """تنقية القيم النصية من الأسرار قبل حفظها في السجل."""
    if value is None:
        return None
    if isinstance(value, str):
        return sanitize(value)
    if isinstance(value, dict):
        return {key: _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    return value
```

### `services/order_service.py`

```python
"""
خدمة الطلبات — قلب النظام.

المسؤوليات:
    • إنشاء الطلب: تحقق كامل ثم خصم الرصيد وإنشاء الطلب وإشعار المستخدم في معاملة واحدة.
    • إرسال الطلبات للمزود عبر عمّال (workers) مع حجز آمن يمنع المعالجة المزدوجة.
    • متابعة الحالة دورياً حتى الحالة النهائية.
    • الاسترجاع الآمن عند الفشل أو الإلغاء أو التنفيذ الجزئي.
    • أدوات الأدمن: إلغاء، ربط رقم مزود، تأكيد فشل، تجاوز حالة (مع تدقيق إجباري).

قواعد لا تُكسر:
    • كل تغيير حالة يمر عبر `core.order_state` (جدول انتقالات) **و** تحديث مشروط في
      قاعدة البيانات (`expected_statuses`) — فلا سباق ولا كتابة فوق عمل جهة أخرى.
    • كل استرجاع يمر عبر `WalletService` ويُسجَّل كحركة مالية بمرجع فريد.
    • لا إعادة إرسال تلقائي عند نتيجة غير مؤكدة (منعاً لطلب مزدوج عند المزود).
    • لا تُفتح معاملة قاعدة بيانات أثناء انتظار شبكة المزود.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from core.constants import MAX_SUBMIT_ATTEMPTS, ORDER_CHECK_BACKOFF, ORDER_LOCK_SECONDS
from core.enums import ActorType, NotificationType, OrderStatus
from core.exceptions import (
    DuplicateOperationError,
    InvalidStateTransitionError,
    OrderError,
    ProviderError,
    ProviderInsufficientFundsError,
    ProviderPermanentError,
    ProviderTemporaryError,
    ProviderUncertainError,
    RateLimitedError,
    ServiceNotAvailableError,
    ValidationError,
)
from core.money import format_units, partial_refund_units
from core.order_state import (
    assert_transition,
    can_transition,
    is_final,
    map_provider_status,
)
from core.permissions import Permission
from database.database import Database, Tx
from database.models import Order, Provider, Service, User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.catalog_service import CatalogService
from services.notification_service import NotificationService
from services.provider_service import ProviderService
from services.settings_service import SettingsService
from services.wallet_service import WalletService
from texts import templates
from utils.datetime_utils import day_bounds_utc, iso_minus_days, iso_plus_seconds, parse_iso, utc_now
from utils.logging_setup import get_logger
from utils.security import new_token, sanitize
from utils.validators import validate_link

logger = get_logger(__name__)


@dataclass(slots=True)
class BatchReport:
    """حصيلة جولة معالجة (إرسال أو فحص حالات)."""

    claimed: int = 0
    succeeded: int = 0
    retried: int = 0
    failed: int = 0
    uncertain: int = 0
    unchanged: int = 0
    completed: int = 0
    details: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, int]:
        """تحويل الحصيلة إلى قاموس للتسجيل."""
        return {
            "claimed": self.claimed,
            "succeeded": self.succeeded,
            "retried": self.retried,
            "failed": self.failed,
            "uncertain": self.uncertain,
            "unchanged": self.unchanged,
            "completed": self.completed,
        }


class OrderService:
    """دورة حياة الطلب كاملة من الإنشاء حتى الحالة النهائية."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        wallet: WalletService,
        catalog: CatalogService,
        providers: ProviderService,
        notifications: NotificationService,
        audit: AuditService,
        auth: AuthService,
    ) -> None:
        """تهيئة الخدمة بكل الاعتماديات التي تحتاجها."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.wallet = wallet
        self.catalog = catalog
        self.providers = providers
        self.notifications = notifications
        self.audit = audit
        self.auth = auth

    # ===================================================================== #
    #                              الإنشاء                                  #
    # ===================================================================== #

    async def create_order(
        self,
        user: User,
        *,
        service_id: int,
        link: str,
        quantity: str | int,
        client_request_id: str | None = None,
    ) -> Order:
        """
        إنشاء طلب جديد: تحقق كامل ← خصم الرصيد ← إنشاء الطلب ← إشعار — كلها معاملة واحدة.

        المدخلات:
            client_request_id : مفتاح المستخدم لمنع التكرار عند الضغط المزدوج.
                                إذا تكرر نفس المفتاح يُعاد الطلب الأول نفسه دون خصم جديد.

        المخرجات: الطلب بعد إنشائه (حالته `pending`).

        الاستثناءات:
            UserBannedError · MaintenanceModeError : الحساب محظور أو النظام في صيانة.
            ServiceNotAvailableError               : الخدمة أو مزودها غير متاح.
            QuantityOutOfRangeError · InvalidLinkError · InvalidAmountError
            RateLimitedError                       : تجاوز الحد اليومي للطلبات.
            DuplicateOperationError                : طلب مطابق خلال نافذة التكرار.
            InsufficientBalanceError               : الرصيد لا يكفي (لا يُنشأ الطلب أصلاً).
        """
        await self.auth.guard(user)

        # 1) مفتاح منع التكرار: إن تكرر نفس المفتاح نُعيد الطلب الأصلي دون أي خصم جديد
        request_id = (client_request_id or f"u{user.id}:{new_token(8)}").strip()[:64]
        existing = await self.repos.orders.get_by_client_request_id(request_id)
        if existing is not None:
            logger.info("إعادة استخدام الطلب %s لنفس مفتاح الطلب %s", existing.id, request_id)
            return existing

        # 2) الخدمة والمزود
        service = await self.catalog.get_available_service(service_id)
        provider = await self.repos.providers.get(service.provider_id)
        if provider is None:
            raise ServiceNotAvailableError(f"مزود الخدمة {service_id} غير موجود")
        health = await self.providers.health(provider)
        if not health.is_usable:
            raise ServiceNotAvailableError(
                f"المزود {provider.name} غير متاح: {health.reason}",
                user_message="❌ هذه الخدمة متوقفة مؤقتاً. جرّب لاحقاً.",
            )

        # 3) الرابط والكمية والتكلفة
        clean_link = validate_link(link, pattern=service.link_pattern)
        quote = await self.catalog.quote(service, quantity)

        symbol = await self.settings.money_symbol()
        min_order_units = await self.settings.get_money_units("min_order_amount_units", 0)
        if min_order_units and quote.cost_units < min_order_units:
            raise ValidationError(
                f"قيمة الطلب {quote.cost_units} أقل من الحد الأدنى {min_order_units}",
                user_message=(
                    "❌ الحد الأدنى لقيمة الطلب هو "
                    f"{format_units(min_order_units, symbol=symbol)}."
                ),
            )

        # 4) الحدود اليومية ومنع الطلب المكرر
        await self._check_daily_limit(user)
        await self._check_duplicate(user, service.id, clean_link, quote.quantity)

        # 5) المعاملة الذرّية: إنشاء + خصم + سجل + إشعار
        async with self.db.transaction() as tx:
            order = await self.repos.orders.create(
                tx,
                user_id=user.id,
                service_id=service.id,
                provider_id=provider.id,
                service_name_snapshot=service.name,
                price_per_1000_snapshot_units=service.price_per_1000_units,
                link=clean_link,
                quantity=quote.quantity,
                cost_units=quote.cost_units,
                client_request_id=request_id,
                provider_cost_units=self._provider_cost(service, quote.quantity),
            )
            public_code = f"ORD-{order.id:06d}"
            await self.repos.orders.update_fields(tx, order.id, public_code=public_code)

            await self.wallet.charge_for_order(
                tx,
                user_id=user.id,
                order_id=order.id,
                amount_units=quote.cost_units,
                description=f"طلب {service.name} × {quote.quantity}",
            )

            await self.repos.orders.add_history(
                tx,
                order_id=order.id,
                from_status=None,
                to_status=OrderStatus.PENDING,
                actor_type=ActorType.USER,
                actor_id=user.id,
                reason="إنشاء الطلب",
            )

            title, message = templates.order_created(
                code=public_code,
                service_name=service.name,
                quantity=quote.quantity,
                cost_units=quote.cost_units,
                symbol=symbol,
            )
            await self.notifications.notify_order(
                tx,
                user_id=user.id,
                order_id=order.id,
                event=NotificationType.ORDER_CREATED,
                title=title,
                message=message,
                payload={"order_id": order.id, "cost_units": quote.cost_units},
            )

        created = await self.repos.orders.get(order.id)
        if created is None:  # لا يحدث عملياً، لكن لا نُرجع قيمة غير مؤكدة أبداً
            raise OrderError(f"تعذر قراءة الطلب {order.id} بعد إنشائه")
        logger.info(
            "أنشأ المستخدم %s الطلب %s (%s × %s) بتكلفة %s",
            user.id, created.id, service.name, quote.quantity, quote.cost_units,
        )
        return created

    def _provider_cost(self, service: Service, quantity: int) -> int | None:
        """حساب تكلفة الطلب علينا لدى المزود (للأرباح) إن كان سعر المزود معروفاً."""
        if not service.provider_price_per_1000_units:
            return None
        return (service.provider_price_per_1000_units * quantity + 500) // 1000

    async def _check_daily_limit(self, user: User) -> None:
        """
        التأكد من عدم تجاوز الحد اليومي لعدد الطلبات.

        الاستثناءات: RateLimitedError عند التجاوز.
        """
        max_per_day = await self.settings.get_int("max_orders_per_day", 0)
        if max_per_day <= 0:
            return
        start_today, _ = day_bounds_utc(0)
        today_count = await self.repos.orders.count_today_by_user(user.id, start_today)
        if today_count >= max_per_day:
            raise RateLimitedError(
                f"المستخدم {user.id} تجاوز {max_per_day} طلباً اليوم",
                user_message=f"⏳ وصلت إلى الحد اليومي ({max_per_day} طلب). حاول غداً.",
            )

    async def _check_duplicate(self, user: User, service_id: int, link: str, quantity: int) -> None:
        """
        منع إنشاء طلب مطابق تماماً خلال نافذة زمنية قصيرة (ضغط مزدوج أو خطأ).

        الاستثناءات: DuplicateOperationError عند وجود طلب مطابق حديث.
        """
        window_minutes = await self.settings.get_int("duplicate_order_window_minutes", 0)
        if window_minutes <= 0:
            return
        since = iso_plus_seconds(-window_minutes * 60)
        duplicate = await self.repos.orders.find_recent_duplicate(
            user_id=user.id, service_id=service_id, link=link, quantity=quantity, since_iso=since
        )
        if duplicate is not None:
            raise DuplicateOperationError(
                f"طلب مكرر خلال {window_minutes} دقيقة (الطلب {duplicate.id})",
                user_message=(
                    f"⚠️ لديك طلب مطابق قبل قليل ({duplicate.public_code or duplicate.id}). "
                    f"إن كنت تريد طلباً إضافياً انتظر {window_minutes} دقيقة."
                ),
            )

    # ===================================================================== #
    #                        أدوات تغيير الحالة                             #
    # ===================================================================== #

    async def _transition(
        self,
        tx: Tx,
        order: Order,
        new_status: str,
        *,
        actor_type: str,
        actor_id: int | None = None,
        reason: str | None = None,
        extra: dict | None = None,
        provider_status_raw: str | None = None,
    ) -> bool:
        """
        تنفيذ انتقال حالة واحد: تحقق من الجدول ثم تحديث مشروط ثم تسجيل في التاريخ.

        المخرجات: True إذا تم التغيير فعلاً، False إذا سبقتنا جهة أخرى لتغيير الحالة
                  (وهذا ليس خطأً — بل الحماية من السباق تعمل).

        الاستثناءات:
            InvalidStateTransitionError : الانتقال ممنوع في جدول الحالات.
        """
        assert_transition(order.status, new_status, order_id=order.id)
        if order.status == new_status:
            return False  # لا تغيير فعلي

        changed = await self.repos.orders.update_status(
            tx,
            order.id,
            new_status=new_status,
            expected_statuses=[order.status],
            extra_fields=extra,
        )
        if not changed:
            logger.warning(
                "تجاهل انتقال الطلب %s (%s ← %s): تغيّرت حالته من جهة أخرى",
                order.id, order.status, new_status,
            )
            return False

        await self.repos.orders.add_history(
            tx,
            order_id=order.id,
            from_status=order.status,
            to_status=new_status,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            provider_status_raw=provider_status_raw,
        )
        return True

    async def _refund_full(
        self, tx: Tx, order: Order, *, reason: str, actor_type: str, actor_id: int | None = None
    ) -> int:
        """
        استرجاع كامل المبلغ المتبقي للطلب ثم نقله إلى الحالة `refunded`.

        المخرجات: المبلغ المسترجع فعلياً (قد يكون صفراً إن سبق استرجاعه بالكامل).
        """
        remaining = order.refundable_units
        if remaining <= 0:
            return 0

        transaction = await self.wallet.refund_order(
            tx,
            user_id=order.user_id,
            order_id=order.id,
            amount_units=remaining,
            partial=False,
            description=f"استرجاع كامل: {reason}",
        )
        if transaction is None:
            return 0

        fresh = await self.repos.orders.get(order.id)
        if fresh is not None and can_transition(fresh.status, OrderStatus.REFUNDED):
            await self._transition(
                tx, fresh, OrderStatus.REFUNDED,
                actor_type=actor_type, actor_id=actor_id, reason=reason,
                extra={"refunded_at": self.repos.orders.now()},
            )
        return remaining

    async def _fail_order(
        self,
        order: Order,
        *,
        reason: str,
        actor_type: str = ActorType.SYSTEM,
        actor_id: int | None = None,
        notify_admins: bool = True,
        auto_refund: bool | None = None,
    ) -> int:
        """
        المسار الكامل لفشل طلب: تغيير الحالة ← استرجاع كامل ← إشعار المستخدم والأدمن.

        المدخلات:
            auto_refund : None تعني «اتبع الإعداد `auto_refund_on_provider_fail`»،
                          وTrue تفرض الاسترجاع (إجراء أدمن صريح).
                          عند تعطيل الاسترجاع التلقائي يبقى المال محجوزاً ويُنبَّه الأدمن
                          لتنفيذ الاسترجاع يدوياً — ولا يُفقد مال المستخدم في الحالتين.

        المخرجات: المبلغ المسترجع (صفر إذا كان الاسترجاع التلقائي معطّلاً).
        """
        symbol = await self.settings.money_symbol()
        clean_reason = sanitize(reason)[:300]
        if auto_refund is None:
            auto_refund = await self.settings.get_bool("auto_refund_on_provider_fail", True)
        refunded = 0

        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None or is_final(current.status):
                return 0

            moved = await self._transition(
                tx, current, OrderStatus.FAILED,
                actor_type=actor_type, actor_id=actor_id, reason=clean_reason,
                extra={"last_error": clean_reason, "locked_by": None, "locked_until": None},
            )
            if not moved:
                return 0

            failed_order = await self.repos.orders.get(order.id)
            if failed_order is None:
                return 0
            if auto_refund:
                refunded = await self._refund_full(
                    tx, failed_order, reason=clean_reason, actor_type=actor_type, actor_id=actor_id
                )

            code = current.public_code or f"#{current.id}"
            title, message = templates.order_failed(
                code=code, reason=clean_reason, refund_units=refunded, symbol=symbol
            )
            await self.notifications.notify_order(
                tx,
                user_id=current.user_id,
                order_id=current.id,
                event=NotificationType.ORDER_FAILED,
                title=title,
                message=message,
            )
            if notify_admins or not auto_refund:
                admin_reason = clean_reason if auto_refund else (
                    f"{clean_reason} — ⚠️ الاسترجاع التلقائي معطّل، نفّذ الاسترجاع يدوياً"
                )
                admin_title, admin_message = templates.admin_order_failed(
                    code=code, order_id=current.id, reason=admin_reason,
                    refund_units=refunded, symbol=symbol,
                )
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.ORDERS_VIEW,
                    token=f"order:{current.id}:failed",
                    title=admin_title,
                    message=admin_message,
                )
            await self.repos.error_logs.log(
                tx,
                message=f"فشل الطلب #{current.id}: {clean_reason}",
                level="ERROR",
                source="order_service",
                error_type="OrderFailed",
                user_id=current.user_id,
            )
        logger.error("فشل الطلب %s: %s (استُرجع %s)", order.id, clean_reason, refunded)
        return refunded

    # ===================================================================== #
    #                        إرسال الطلبات للمزود                           #
    # ===================================================================== #

    async def process_pending_orders(self, *, worker: str = "submitter", limit: int = 5) -> BatchReport:
        """
        حجز دفعة من الطلبات المعلّقة وإرسالها إلى المزود.

        تُستدعى من job دوري. الحجز يمنع أن يعالج عاملان الطلب نفسه.
        """
        report = BatchReport()
        async with self.db.transaction() as tx:
            claimed = await self.repos.orders.claim_pending_for_submit(
                tx, worker=worker, limit=limit, lock_seconds=ORDER_LOCK_SECONDS
            )
        report.claimed = len(claimed)

        for order in claimed:
            outcome = await self._submit_one(order)
            if outcome == "submitted":
                report.succeeded += 1
            elif outcome == "retry":
                report.retried += 1
            elif outcome == "uncertain":
                report.uncertain += 1
            elif outcome == "failed":
                report.failed += 1
            else:
                report.unchanged += 1

        if report.claimed:
            logger.info("جولة إرسال الطلبات: %s", report.as_dict())
        return report

    async def _submit_one(self, order: Order) -> str:
        """
        إرسال طلب واحد إلى المزود ومعالجة كل النتائج الممكنة.

        المخرجات: وصف مختصر للنتيجة: submitted / retry / uncertain / failed / skipped.
        """
        service = await self.repos.services.get(order.service_id)
        provider = await self.repos.providers.get(order.provider_id)
        if service is None or provider is None:
            await self._fail_order(order, reason="بيانات الخدمة أو المزود غير موجودة")
            return "failed"

        health = await self.providers.health(provider)
        if not health.is_usable:
            await self._requeue(order, reason=f"المزود غير متاح: {health.reason}", delay_seconds=300)
            return "retry"

        try:
            result = await self.providers.submit_order(provider, service, order)
        except ProviderInsufficientFundsError as exc:
            await self._handle_insufficient_provider_funds(order, provider, str(exc))
            return "retry"
        except ProviderUncertainError as exc:
            await self._mark_uncertain(order, str(exc))
            return "uncertain"
        except ProviderPermanentError as exc:
            await self._fail_order(order, reason=f"رفض المزود الطلب: {exc}")
            return "failed"
        except ProviderTemporaryError as exc:
            if order.submit_attempts >= MAX_SUBMIT_ATTEMPTS:
                await self._fail_order(
                    order, reason=f"تعذر الإرسال بعد {order.submit_attempts} محاولات: {exc}"
                )
                return "failed"
            await self._requeue(order, reason=str(exc), delay_seconds=60 * order.submit_attempts)
            return "retry"
        except ProviderError as exc:
            # أي خطأ مزود غير مصنّف يُعامل معاملة الخطأ النهائي حفاظاً على مال المستخدم
            await self._fail_order(order, reason=f"خطأ غير متوقع من المزود: {exc}")
            return "failed"

        # نجاح: تسجيل رقم الطلب عند المزود والانتقال إلى submitted
        now = self.repos.orders.now()
        check_interval = await self.settings.get_int("order_check_interval_seconds", 120)
        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None:
                return "skipped"
            moved = await self._transition(
                tx, current, OrderStatus.SUBMITTED,
                actor_type=ActorType.JOB,
                reason="قبل المزود الطلب",
                extra={
                    "provider_order_id": result.provider_order_id,
                    "provider_cost_units": result.charge_units if result.charge_units else current.provider_cost_units,
                    "submitted_at": now,
                    "next_check_at": iso_plus_seconds(check_interval),
                    "locked_by": None,
                    "locked_until": None,
                    "last_error": None,
                },
            )
            if moved:
                title, message = templates.order_submitted(
                    code=current.public_code or f"#{current.id}",
                    service_name=current.service_name_snapshot,
                )
                await self.notifications.notify_order(
                    tx,
                    user_id=current.user_id,
                    order_id=current.id,
                    event=NotificationType.ORDER_SUBMITTED,
                    title=title,
                    message=message,
                )
        logger.info(
            "أُرسل الطلب %s إلى المزود %s برقم %s", order.id, provider.name, result.provider_order_id
        )
        return "submitted"

    async def _requeue(self, order: Order, *, reason: str, delay_seconds: int) -> None:
        """إعادة الطلب إلى `pending` مع تأجيل المحاولة القادمة (فشل مؤقت آمن)."""
        clean_reason = sanitize(reason)[:300]
        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None or current.status != OrderStatus.SUBMITTING:
                return
            await self._transition(
                tx, current, OrderStatus.PENDING,
                actor_type=ActorType.JOB,
                reason=f"إعادة جدولة: {clean_reason}",
                extra={
                    "last_error": clean_reason,
                    "locked_by": None,
                    "locked_until": None,
                    "next_check_at": iso_plus_seconds(max(30, delay_seconds)),
                },
            )
        logger.warning("أُعيد الطلب %s للانتظار: %s", order.id, clean_reason)

    async def _mark_uncertain(self, order: Order, error: str) -> None:
        """
        وضع الطلب في حالة «غير مؤكد» وتنبيه الأدمن فوراً.

        ⚠️ لا استرجاع ولا إعادة إرسال هنا: قد يكون الطلب أُنشئ فعلاً عند المزود،
        وإعادة الإرسال تعني دفع المبلغ مرتين.
        """
        clean_error = sanitize(error)[:300]
        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None or current.status != OrderStatus.SUBMITTING:
                return
            moved = await self._transition(
                tx, current, OrderStatus.SUBMIT_UNCERTAIN,
                actor_type=ActorType.JOB,
                reason=clean_error,
                extra={"last_error": clean_error, "locked_by": None, "locked_until": None},
            )
            if moved:
                code = current.public_code or f"#{current.id}"
                title, message = templates.admin_order_uncertain(
                    code=code, order_id=current.id, error=clean_error
                )
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.ORDERS_VIEW,
                    token=f"order:{current.id}:uncertain",
                    title=title,
                    message=message,
                )
                await self.repos.error_logs.log(
                    tx,
                    message=f"نتيجة إرسال غير مؤكدة للطلب #{current.id}: {clean_error}",
                    level="CRITICAL",
                    source="order_service",
                    error_type="ProviderUncertainError",
                    user_id=current.user_id,
                )
        logger.critical("الطلب %s بحالة غير مؤكدة: %s", order.id, clean_error)

    async def _handle_insufficient_provider_funds(
        self, order: Order, provider: Provider, error: str
    ) -> None:
        """
        معالجة «رصيد المزود غير كافٍ» حسب القرار D5:
        يبقى الطلب منتظراً حتى مهلة قصوى، وبعدها يفشل ويُسترجع المبلغ تلقائياً.
        """
        wait_hours = await self.settings.get_int("provider_insufficient_wait_hours", 6)
        created = parse_iso(order.created_at)
        age_hours = ((utc_now() - created).total_seconds() / 3600) if created else 0.0

        if age_hours >= wait_hours:
            await self._fail_order(
                order, reason=f"انتظر الطلب {wait_hours} ساعة ورصيد المزود لا يزال غير كافٍ"
            )
            return

        await self._requeue(order, reason=f"رصيد المزود غير كافٍ: {error}", delay_seconds=900)
        symbol = await self.settings.money_symbol()
        title, message = templates.admin_provider_low_balance(
            provider_name=provider.name, balance_units=provider.balance_units, symbol=symbol
        )
        async with self.db.transaction() as tx:
            await self.notifications.notify_admins(
                tx,
                permission=Permission.PROVIDERS_VIEW,
                token=f"provider:{provider.id}:insufficient:{day_bounds_utc(0)[0][:10]}",
                title=title,
                message=message,
            )

    # ===================================================================== #
    #                          متابعة حالة الطلبات                          #
    # ===================================================================== #

    async def process_due_orders(self, *, worker: str = "checker", limit: int = 20) -> BatchReport:
        """
        حجز دفعة من الطلبات المستحقة للفحص وتحديث حالاتها من المزود.

        تُستدعى من job دوري حتى تصل كل الطلبات إلى حالة نهائية دون تدخل بشري.
        """
        report = BatchReport()
        async with self.db.transaction() as tx:
            claimed = await self.repos.orders.claim_due_for_check(
                tx, worker=worker, limit=limit, lock_seconds=ORDER_LOCK_SECONDS
            )
        report.claimed = len(claimed)

        for order in claimed:
            outcome = await self._sync_one(order)
            if outcome in {OrderStatus.COMPLETED, OrderStatus.PARTIAL}:
                report.completed += 1
            elif outcome == OrderStatus.FAILED:
                report.failed += 1
            elif outcome == "unchanged":
                report.unchanged += 1
            else:
                report.succeeded += 1

        if report.claimed:
            logger.info("جولة فحص الطلبات: %s", report.as_dict())
        return report

    async def _sync_one(self, order: Order) -> str:
        """
        فحص حالة طلب واحد لدى المزود وتطبيق النتيجة.

        المخرجات: الحالة الجديدة، أو "unchanged" إذا لم يتغير شيء.
        """
        provider = await self.repos.providers.get(order.provider_id)
        if provider is None:
            await self._fail_order(order, reason="المزود غير موجود")
            return OrderStatus.FAILED

        try:
            status = await self.providers.fetch_status(provider, order)
        except ProviderPermanentError as exc:
            await self._release_with_backoff(order, error=str(exc))
            logger.warning("فحص الطلب %s فشل نهائياً: %s", order.id, exc)
            return "unchanged"
        except ProviderError as exc:
            await self._release_with_backoff(order, error=str(exc))
            return "unchanged"

        mapped = map_provider_status(status.raw_status)
        if mapped is None:
            await self._handle_unknown_status(order, status.raw_status)
            return "unchanged"

        if mapped == order.status:
            await self._release_with_backoff(order, progress=status)
            return "unchanged"

        if mapped == OrderStatus.IN_PROGRESS:
            await self._apply_in_progress(order, status)
            return OrderStatus.IN_PROGRESS
        if mapped == OrderStatus.COMPLETED:
            await self._apply_completed(order, status)
            return OrderStatus.COMPLETED
        if mapped == OrderStatus.PARTIAL:
            await self._apply_partial(order, status)
            return OrderStatus.PARTIAL
        if mapped == OrderStatus.CANCELED:
            await self._apply_canceled(order, reason="ألغى المزود الطلب")
            return OrderStatus.CANCELED
        if mapped == OrderStatus.FAILED:
            await self._fail_order(order, reason=f"المزود أبلغ بفشل الطلب ({status.raw_status})")
            return OrderStatus.FAILED

        # حالة معروفة لكن الانتقال إليها غير منطقي من الحالة الحالية: نسجل ونؤجل
        await self._release_with_backoff(order, error=f"انتقال غير مدعوم إلى {mapped}")
        return "unchanged"

    def _progress_fields(self, status) -> dict:
        """الحقول الرقمية المستخرجة من رد المزود (تقدّم التنفيذ)."""
        fields: dict = {"provider_status": status.raw_status}
        if status.start_count is not None:
            fields["start_count"] = status.start_count
        if status.remains is not None:
            fields["remains"] = status.remains
        if status.delivered is not None:
            fields["delivered_quantity"] = status.delivered
        return fields

    async def _apply_in_progress(self, order: Order, status) -> None:
        """نقل الطلب إلى «قيد التنفيذ» وإشعار المستخدم مرة واحدة."""
        check_interval = await self.settings.get_int("order_check_interval_seconds", 120)
        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None:
                return
            extra = self._progress_fields(status)
            extra.update({
                "locked_by": None,
                "locked_until": None,
                "next_check_at": iso_plus_seconds(check_interval),
            })
            moved = await self._transition(
                tx, current, OrderStatus.IN_PROGRESS,
                actor_type=ActorType.PROVIDER,
                reason="بدأ التنفيذ",
                extra=extra,
                provider_status_raw=status.raw_status,
            )
            if moved:
                title, message = templates.order_in_progress(
                    code=current.public_code or f"#{current.id}"
                )
                await self.notifications.notify_order(
                    tx,
                    user_id=current.user_id,
                    order_id=current.id,
                    event=NotificationType.ORDER_IN_PROGRESS,
                    title=title,
                    message=message,
                )

    async def _apply_completed(self, order: Order, status) -> None:
        """إنهاء الطلب بنجاح وإشعار المستخدم."""
        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None:
                return
            extra = self._progress_fields(status)
            extra.update({
                "completed_at": self.repos.orders.now(),
                "remains": 0,
                "delivered_quantity": status.delivered if status.delivered is not None else current.quantity,
                "locked_by": None,
                "locked_until": None,
                "next_check_at": None,
            })
            moved = await self._transition(
                tx, current, OrderStatus.COMPLETED,
                actor_type=ActorType.PROVIDER,
                reason="اكتمل التنفيذ",
                extra=extra,
                provider_status_raw=status.raw_status,
            )
            if moved:
                title, message = templates.order_completed(
                    code=current.public_code or f"#{current.id}",
                    service_name=current.service_name_snapshot,
                    quantity=current.quantity,
                )
                await self.notifications.notify_order(
                    tx,
                    user_id=current.user_id,
                    order_id=current.id,
                    event=NotificationType.ORDER_COMPLETED,
                    title=title,
                    message=message,
                )
        logger.info("اكتمل الطلب %s", order.id)

    async def _apply_partial(self, order: Order, status) -> None:
        """
        تنفيذ جزئي: حساب الاسترجاع بحسب المتبقي، تنفيذه، ثم إشعار المستخدم.

        الاسترجاع = (التكلفة × المتبقي) ÷ الكمية، مطروحاً منه ما سبق استرجاعه.
        """
        symbol = await self.settings.money_symbol()
        refund_enabled = await self.settings.get_bool("partial_refund_enabled", True)

        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None:
                return

            remains = status.remains if status.remains is not None else 0
            delivered = (
                status.delivered if status.delivered is not None else max(0, current.quantity - remains)
            )
            refund_units = 0
            if refund_enabled and remains > 0:
                refund_units = partial_refund_units(
                    cost_units=current.cost_units,
                    quantity=current.quantity,
                    remains=remains,
                    already_refunded_units=current.refund_amount_units,
                )

            extra = self._progress_fields(status)
            extra.update({
                "remains": remains,
                "delivered_quantity": delivered,
                "completed_at": self.repos.orders.now(),
                "locked_by": None,
                "locked_until": None,
                "next_check_at": None,
            })
            moved = await self._transition(
                tx, current, OrderStatus.PARTIAL,
                actor_type=ActorType.PROVIDER,
                reason=f"تنفيذ جزئي — المتبقي {remains}",
                extra=extra,
                provider_status_raw=status.raw_status,
            )
            if not moved:
                return

            refunded = 0
            if refund_units > 0:
                transaction = await self.wallet.refund_order(
                    tx,
                    user_id=current.user_id,
                    order_id=current.id,
                    amount_units=refund_units,
                    partial=True,
                    description=f"استرجاع جزئي للطلب #{current.id} (متبقي {remains})",
                )
                refunded = transaction.amount_units if transaction else 0

            title, message = templates.order_partial(
                code=current.public_code or f"#{current.id}",
                delivered=delivered,
                quantity=current.quantity,
                refund_units=refunded,
                symbol=symbol,
            )
            await self.notifications.notify_order(
                tx,
                user_id=current.user_id,
                order_id=current.id,
                event=NotificationType.ORDER_PARTIAL,
                title=title,
                message=message,
            )
        logger.info("الطلب %s نُفِّذ جزئياً (متبقي %s)", order.id, status.remains)

    async def _apply_canceled(
        self, order: Order, *, reason: str, actor_type: str = ActorType.PROVIDER, actor_id: int | None = None
    ) -> int:
        """
        إلغاء الطلب مع استرجاع كامل المبلغ وإشعار المستخدم.

        المخرجات: المبلغ المسترجع.
        """
        symbol = await self.settings.money_symbol()
        clean_reason = sanitize(reason)[:300]
        refunded = 0

        async with self.db.transaction() as tx:
            current = await self.repos.orders.get(order.id)
            if current is None or is_final(current.status):
                return 0
            moved = await self._transition(
                tx, current, OrderStatus.CANCELED,
                actor_type=actor_type, actor_id=actor_id, reason=clean_reason,
                extra={
                    "cancelled_at": self.repos.orders.now(),
                    "locked_by": None,
                    "locked_until": None,
                    "next_check_at": None,
                },
            )
            if not moved:
                return 0

            canceled_order = await self.repos.orders.get(order.id)
            if canceled_order is None:
                return 0
            refunded = await self._refund_full(
                tx, canceled_order, reason=clean_reason, actor_type=actor_type, actor_id=actor_id
            )

            code = current.public_code or f"#{current.id}"
            title, message = templates.order_canceled(
                code=code, refund_units=refunded, symbol=symbol
            )
            await self.notifications.notify_order(
                tx,
                user_id=current.user_id,
                order_id=current.id,
                event=NotificationType.ORDER_CANCELED,
                title=title,
                message=message,
            )
        logger.info("أُلغي الطلب %s (%s) واسترُجع %s", order.id, clean_reason, refunded)
        return refunded

    async def _handle_unknown_status(self, order: Order, raw_status: str | None) -> None:
        """تسجيل حالة مزود غير معروفة دون تغيير حالة الطلب (سلامة أولاً)."""
        clean = sanitize(str(raw_status))[:100]
        async with self.db.transaction() as tx:
            await self.repos.error_logs.log(
                tx,
                message=f"حالة مزود غير معروفة للطلب #{order.id}: {clean}",
                level="WARNING",
                source="order_service",
                error_type="UnknownProviderStatus",
                user_id=order.user_id,
            )
        await self._release_with_backoff(order, error=f"حالة غير معروفة: {clean}")
        logger.warning("حالة مزود غير معروفة للطلب %s: %s", order.id, clean)

    async def _release_with_backoff(self, order: Order, *, progress=None, error: str | None = None) -> None:
        """
        فك حجز الطلب وتحديد موعد الفحص القادم بتدرج تصاعدي.

        كلما تكررت الفحوص دون تغيير، تباعدت المواعيد — تخفيفاً على المزود وعلى النظام.
        """
        index = min(order.checks_count, len(ORDER_CHECK_BACKOFF) - 1)
        delay = ORDER_CHECK_BACKOFF[index]
        async with self.db.transaction() as tx:
            fields: dict = {}
            if progress is not None:
                fields.update(self._progress_fields(progress))
            if error:
                fields["last_error"] = sanitize(error)[:300]
            if fields:
                await self.repos.orders.update_fields(tx, order.id, **fields)
            await self.repos.orders.release_lock(
                tx, order.id, next_check_at=iso_plus_seconds(delay)
            )

    # ===================================================================== #
    #                        إجراءات المستخدم والأدمن                       #
    # ===================================================================== #

    async def cancel_by_user(self, user: User, order_id: int) -> int:
        """
        إلغاء المستخدم لطلبه قبل إرساله للمزود (القرار D11).

        المخرجات: المبلغ المسترجع.

        الاستثناءات:
            OrderError                  : الطلب ليس للمستخدم أو غير موجود.
            InvalidStateTransitionError : الطلب غادر حالة الانتظار (لا يمكن الإلغاء).
            ValidationError             : الإلغاء الذاتي معطّل من الإعدادات.
        """
        await self.auth.guard(user)
        if not await self.settings.get_bool("user_cancel_before_submit", True):
            raise ValidationError(
                "إلغاء المستخدم معطّل", user_message="⚠️ إلغاء الطلبات غير متاح حالياً."
            )

        order = await self.repos.orders.get(order_id)
        if order is None or order.user_id != user.id:
            raise OrderError("الطلب غير موجود", user_message="❌ لم يتم العثور على هذا الطلب.")
        if order.status != OrderStatus.PENDING:
            raise InvalidStateTransitionError(
                f"لا يمكن إلغاء الطلب {order_id} في الحالة {order.status}",
                user_message="⚠️ لا يمكن الإلغاء الآن — بدأ تنفيذ الطلب بالفعل.",
            )

        return await self._apply_canceled(
            order, reason="إلغاء بطلب المستخدم", actor_type=ActorType.USER, actor_id=user.id
        )

    async def admin_cancel(self, actor: User, order_id: int, reason: str) -> int:
        """
        إلغاء طلب من الأدمن مع استرجاع كامل (صلاحية `orders.cancel`).

        المخرجات: المبلغ المسترجع.
        """
        await self.auth.require_permission(actor, Permission.ORDERS_CANCEL, context=f"order:{order_id}")
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")
        if is_final(order.status):
            raise InvalidStateTransitionError(
                f"الطلب {order_id} في حالة نهائية ({order.status})",
                user_message="⚠️ هذا الطلب مغلق ولا يقبل الإلغاء.",
            )

        refunded = await self._apply_canceled(
            order, reason=reason, actor_type=ActorType.ADMIN, actor_id=actor.id
        )
        await self.audit.log_standalone(
            action="orders.cancel",
            admin_id=actor.id,
            target_type="order",
            target_id=order_id,
            details={"reason": reason, "refunded_units": refunded},
            source="telegram",
        )
        return refunded

    async def admin_mark_failed(self, actor: User, order_id: int, reason: str) -> int:
        """
        تأكيد الأدمن أن الطلب لم يُنشأ عند المزود (للطلبات غير المؤكدة) ⇒ فشل + استرجاع.

        المخرجات: المبلغ المسترجع.
        """
        await self.auth.require_permission(actor, Permission.ORDERS_REFUND, context=f"order:{order_id}")
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")
        if is_final(order.status):
            raise InvalidStateTransitionError(
                f"الطلب {order_id} في حالة نهائية ({order.status})",
                user_message="⚠️ هذا الطلب مغلق مسبقاً.",
            )

        refunded = await self._fail_order(
            order,
            reason=reason,
            actor_type=ActorType.ADMIN,
            actor_id=actor.id,
            notify_admins=False,
            auto_refund=True,  # قرار أدمن صريح: المال يعود فوراً
        )
        await self.audit.log_standalone(
            action="orders.refund",
            admin_id=actor.id,
            target_type="order",
            target_id=order_id,
            details={"reason": reason, "refunded_units": refunded},
            source="telegram",
        )
        return refunded

    async def admin_link_provider_order(self, actor: User, order_id: int, provider_order_id: str) -> bool:
        """
        ربط رقم الطلب عند المزود يدوياً (لطلب بحالة غير مؤكدة تبيّن أنه أُنشئ فعلاً).

        الاستثناءات:
            OrderError                  : الطلب غير موجود أو الرقم مستخدم لطلب آخر.
            InvalidStateTransitionError : حالة الطلب لا تسمح بالربط.
        """
        await self.auth.require_permission(
            actor, Permission.ORDERS_LINK_PROVIDER_ID, context=f"order:{order_id}"
        )
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")

        clean_id = str(provider_order_id).strip()
        if not clean_id:
            raise ValidationError("رقم الطلب فارغ", user_message="❌ أرسل رقم الطلب عند المزود.")
        conflict = await self.repos.orders.get_by_provider_order_id(order.provider_id, clean_id)
        if conflict is not None and conflict.id != order.id:
            raise OrderError(
                f"رقم المزود {clean_id} مرتبط بالطلب {conflict.id}",
                user_message=f"❌ هذا الرقم مرتبط بالطلب {conflict.public_code or conflict.id}.",
            )

        check_interval = await self.settings.get_int("order_check_interval_seconds", 120)
        async with self.db.transaction() as tx:
            moved = await self._transition(
                tx, order, OrderStatus.SUBMITTED,
                actor_type=ActorType.ADMIN, actor_id=actor.id,
                reason=f"ربط يدوي برقم المزود {clean_id}",
                extra={
                    "provider_order_id": clean_id,
                    "submitted_at": self.repos.orders.now(),
                    "next_check_at": iso_plus_seconds(check_interval),
                    "locked_by": None,
                    "locked_until": None,
                },
            )
            if moved:
                await self.audit.log(
                    tx,
                    action="orders.link_provider_id",
                    admin_id=actor.id,
                    target_type="order",
                    target_id=order_id,
                    before={"status": order.status, "provider_order_id": order.provider_order_id},
                    after={"status": OrderStatus.SUBMITTED, "provider_order_id": clean_id},
                )
                title, message = templates.order_submitted(
                    code=order.public_code or f"#{order.id}",
                    service_name=order.service_name_snapshot,
                )
                await self.notifications.notify_order(
                    tx,
                    user_id=order.user_id,
                    order_id=order.id,
                    event=NotificationType.ORDER_SUBMITTED,
                    title=title,
                    message=message,
                )
        return moved

    async def admin_override_status(
        self, actor: User, order_id: int, new_status: str, reason: str
    ) -> bool:
        """
        تجاوز إداري لحالة الطلب (للأدمن الأعلى فقط) — مع سبب إجباري وتدقيق كامل.

        لا يُجري أي حركة مالية: الاسترجاع يتم عبر الأدوات المخصصة له،
        حتى لا يحدث تغيير رصيد خارج المسار المحاسبي.

        الاستثناءات:
            PermissionDeniedError · ValidationError · OrderError
        """
        await self.auth.require_permission(
            actor, Permission.ORDERS_STATUS_OVERRIDE, context=f"order:{order_id}"
        )
        clean_reason = (reason or "").strip()
        if len(clean_reason) < 5:
            raise ValidationError(
                "سبب التجاوز مطلوب", user_message="❌ اكتب سبباً واضحاً للتجاوز (5 أحرف على الأقل)."
            )
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")

        async with self.db.transaction() as tx:
            changed = await self.repos.orders.update_status(
                tx, order_id, new_status=new_status, expected_statuses=[order.status]
            )
            if changed:
                await self.repos.orders.add_history(
                    tx,
                    order_id=order_id,
                    from_status=order.status,
                    to_status=new_status,
                    actor_type=ActorType.ADMIN,
                    actor_id=actor.id,
                    reason=f"تجاوز إداري: {clean_reason}",
                )
                await self.audit.log(
                    tx,
                    action="orders.status.override",
                    admin_id=actor.id,
                    target_type="order",
                    target_id=order_id,
                    before={"status": order.status},
                    after={"status": new_status, "reason": clean_reason},
                )
        if changed:
            logger.warning(
                "تجاوز إداري لحالة الطلب %s: %s ← %s بواسطة %s",
                order_id, order.status, new_status, actor.id,
            )
        return changed

    async def recheck_now(self, actor: User, order_id: int) -> str:
        """
        إعادة فحص فورية لحالة طلب من لوحة الأدمن.

        المخرجات: وصف نصي للنتيجة.
        """
        await self.auth.require_permission(actor, Permission.ORDERS_RECHECK, context=f"order:{order_id}")
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ الطلب غير موجود.")
        if not order.provider_order_id:
            return "لا يمكن الفحص: الطلب بلا رقم عند المزود."
        return await self._sync_one(order)

    # ===================================================================== #
    #                        الاسترداد بعد إعادة التشغيل                     #
    # ===================================================================== #

    async def recover_after_restart(self) -> dict[str, int]:
        """
        استرداد الحالة بعد إعادة تشغيل البوت.

        • الطلبات العالقة في `submitting` تُنقل إلى `submit_uncertain` (لا نعرف مصيرها).
        • الأقفال منتهية الصلاحية تُحرَّر ليعاد التقاط الطلبات.

        المخرجات: عدّادات ما تم استرداده.
        """
        async with self.db.transaction() as tx:
            recovered = await self.repos.orders.recover_submitting_orders(tx)
            released = await self.repos.orders.release_expired_locks(tx)

        for order_id in recovered:
            order = await self.repos.orders.get(order_id)
            if order is None:
                continue
            code = order.public_code or f"#{order.id}"
            title, message = templates.admin_order_uncertain(
                code=code, order_id=order.id, error="انقطع تشغيل البوت أثناء إرسال الطلب"
            )
            async with self.db.transaction() as tx:
                await self.notifications.notify_admins(
                    tx,
                    permission=Permission.ORDERS_VIEW,
                    token=f"order:{order.id}:uncertain",
                    title=title,
                    message=message,
                )

        if recovered or released:
            logger.warning(
                "استرداد بعد الإقلاع: %s طلب غير مؤكد، %s قفل محرَّر", len(recovered), released
            )
        return {"uncertain": len(recovered), "locks_released": released}

    async def alert_stuck_orders(self) -> int:
        """
        تنبيه الأدمن بالطلبات التي توقفت بلا تقدم لفترة طويلة.

        المخرجات: عدد الطلبات المتوقفة.
        """
        hours = await self.settings.get_int("order_stuck_alert_hours", 24)
        before = iso_plus_seconds(-hours * 3600)
        stuck = await self.repos.orders.stuck_orders(before_iso=before, limit=50)
        if not stuck:
            return 0
        title, message = templates.admin_stuck_orders(count=len(stuck), hours=hours)
        async with self.db.transaction() as tx:
            await self.notifications.notify_admins(
                tx,
                permission=Permission.ORDERS_VIEW,
                token=f"stuck:{day_bounds_utc(0)[0][:13]}",
                title=title,
                message=message,
            )
        return len(stuck)

    # ===================================================================== #
    #                                القراءة                                #
    # ===================================================================== #

    async def get_for_user(self, user: User, order_id: int) -> Order:
        """
        جلب طلب يخص المستخدم (مع منع الاطلاع على طلبات غيره).

        الاستثناءات: OrderError إذا لم يكن الطلب موجوداً أو ليس له.
        """
        order = await self.repos.orders.get(order_id)
        if order is None or order.user_id != user.id:
            raise OrderError("الطلب غير موجود", user_message="❌ لم يتم العثور على هذا الطلب.")
        return order

    async def list_for_user(
        self, user: User, *, statuses: list[str] | None = None, limit: int = 8, offset: int = 0
    ) -> list[Order]:
        """قائمة طلبات المستخدم (مع إمكانية التصفية بالحالة)."""
        return await self.repos.orders.list_by_user(
            user.id, statuses=statuses, limit=limit, offset=offset
        )

    async def count_for_user(self, user: User, *, statuses: list[str] | None = None) -> int:
        """عدد طلبات المستخدم (للتصفح بالصفحات)."""
        return await self.repos.orders.count_by_user(user.id, statuses=statuses)

    async def admin_get(self, actor: User, order_id: int) -> Order:
        """
        جلب أي طلب في النظام لعرضه في لوحة الأدمن (بعد فحص صلاحية الاطلاع).

        الاستثناءات: PermissionDeniedError · OrderError
        """
        await self.auth.require_permission(
            actor, Permission.ORDERS_VIEW, context=f"order:{order_id}"
        )
        order = await self.repos.orders.get(order_id)
        if order is None:
            raise OrderError("الطلب غير موجود", user_message="❌ لم يتم العثور على هذا الطلب.")
        return order

    async def admin_list(
        self,
        actor: User,
        *,
        statuses: Sequence[str] | None = None,
        user_id: int | None = None,
        limit: int = 8,
        offset: int = 0,
    ) -> list[Order]:
        """
        قائمة طلبات لكل المستخدمين (قوائم لوحة الأدمن) — مع تصفية بالحالة أو بالمستخدم.

        الاستثناءات: PermissionDeniedError
        """
        await self.auth.require_permission(actor, Permission.ORDERS_VIEW, context="orders:list")
        return await self.repos.orders.list_by_statuses(
            statuses, user_id=user_id, limit=limit, offset=offset
        )

    async def admin_count(
        self,
        actor: User,
        *,
        statuses: Sequence[str] | None = None,
        user_id: int | None = None,
    ) -> int:
        """عدد الطلبات المطابقة للتصفية نفسها (لحساب عدد الصفحات في لوحة الأدمن)."""
        await self.auth.require_permission(actor, Permission.ORDERS_VIEW, context="orders:count")
        return await self.repos.orders.count_by_statuses(statuses, user_id=user_id)

    async def history(self, order_id: int) -> list:
        """سجل تغيّر حالات الطلب (من ماذا إلى ماذا ومتى ومن نفّذ)."""
        return await self.repos.orders.history(order_id)

    async def status_counts(self) -> dict[str, int]:
        """عدد الطلبات في كل حالة (للوحة الأدمن)."""
        return await self.repos.orders.status_counts()

    async def recent_revenue_units(self, days: int = 1) -> int:
        """إجمالي قيمة الطلبات خلال آخر عدد أيام (للإحصائيات السريعة)."""
        return await self.repos.orders.sum_cost_between(iso_minus_days(days), self.repos.orders.now())
```

### `services/ticket_service.py`

```python
"""
خدمة الدعم الفني — التذاكر والمحادثة بين المستخدم والأدمن.

المسؤوليات:
    • فتح تذكرة جديدة بتحقق كامل (حد يومي، تذكرة مفتوحة واحدة، طول النص).
    • تبادل الرسائل بين المستخدم وفريق الدعم مع إشعار الطرف الآخر.
    • الإسناد والأولوية والإغلاق وإعادة الفتح.
    • الإغلاق التلقائي للتذاكر الراكدة عبر job دوري.

قواعد:
    • لا تُحذف التذاكر أو الرسائل إطلاقاً — الإغلاق فقط (حفظ السجل التاريخي).
    • كل إجراء أدمن على تذكرة يُسجَّل في سجل التدقيق.
    • إشعار الرد يحمل مفتاح منع تكرار خاصاً بكل رسالة، فلا يُبتلع الرد الثاني.
"""

from __future__ import annotations

from core.enums import NotificationType, SenderType, TicketPriority, TicketStatus
from core.exceptions import PermissionDeniedError, TicketError, ValidationError
from core.permissions import Permission
from database.database import Database
from database.models import SupportMessage, SupportTicket, User
from database.repositories import Repositories
from services.audit_service import AuditService
from services.auth_service import AuthService
from services.notification_service import NotificationService
from services.settings_service import SettingsService
from texts import templates
from utils.datetime_utils import day_bounds_utc, iso_plus_seconds, parse_iso, utc_now
from utils.logging_setup import get_logger
from utils.validators import validate_message, validate_subject

logger = get_logger(__name__)

#: تصنيفات التذاكر المسموحة (مطابقة لقيد CHECK في قاعدة البيانات)
TICKET_CATEGORIES: dict[str, str] = {
    "order": "مشكلة في طلب",
    "payment": "مشكلة في الشحن",
    "service": "استفسار عن خدمة",
    "other": "أخرى",
}

#: الحالات المفتوحة التي تظهر لفريق الدعم
OPEN_STATUSES: tuple[str, ...] = (
    TicketStatus.OPEN,
    TicketStatus.PENDING_ADMIN,
    TicketStatus.PENDING_USER,
)

#: طول المقتطف الظاهر في الإشعار
PREVIEW_LENGTH: int = 120


class TicketService:
    """إدارة تذاكر الدعم الفني من الفتح حتى الإغلاق."""

    def __init__(
        self,
        db: Database,
        repos: Repositories,
        settings: SettingsService,
        notifications: NotificationService,
        audit: AuditService,
        auth: AuthService,
    ) -> None:
        """تهيئة الخدمة بالاعتماديات المطلوبة."""
        self.db = db
        self.repos = repos
        self.settings = settings
        self.notifications = notifications
        self.audit = audit
        self.auth = auth

    # ===================================================================== #
    #                             فتح التذاكر                               #
    # ===================================================================== #

    async def create_ticket(
        self,
        user: User,
        *,
        subject: str,
        message: str,
        category: str = "other",
        related_order_id: int | None = None,
        attachment_file_id: str | None = None,
        attachment_type: str | None = None,
    ) -> SupportTicket:
        """
        فتح تذكرة دعم جديدة مع أول رسالة فيها.

        المخرجات: التذكرة بعد إنشائها.

        الاستثناءات:
            UserBannedError · MaintenanceModeError
            ValidationError : موضوع/نص غير صالح، تصنيف غير معروف، أو تجاوز الحد اليومي.
            TicketError     : لدى المستخدم تذكرة مفتوحة بالفعل.
        """
        await self.auth.guard(user)

        if category not in TICKET_CATEGORIES:
            raise ValidationError(
                f"تصنيف تذكرة غير معروف: {category}",
                user_message="❌ اختر تصنيفاً صحيحاً للتذكرة.",
            )
        clean_subject = validate_subject(subject)
        clean_message = validate_message(message)

        if await self.repos.tickets.has_open_ticket(user.id):
            raise TicketError(
                f"المستخدم {user.id} لديه تذكرة مفتوحة",
                user_message="📬 لديك تذكرة مفتوحة بالفعل — تابع محادثتك فيها بدل فتح تذكرة جديدة.",
            )

        await self._check_daily_limit(user)
        order_id = await self._validate_related_order(user, related_order_id)

        async with self.db.transaction() as tx:
            ticket = await self.repos.tickets.create(
                tx,
                user_id=user.id,
                subject=clean_subject,
                category=category,
                related_order_id=order_id,
            )
            await self.repos.tickets.add_message(
                tx,
                ticket_id=ticket.id,
                sender_type=SenderType.USER,
                sender_id=user.id,
                message=clean_message,
                attachment_file_id=attachment_file_id,
                attachment_type=attachment_type,
            )
            title, admin_message = templates.admin_new_ticket(
                ticket_id=ticket.id, subject=clean_subject, user_label=user.display_name
            )
            await self.notifications.notify_admins(
                tx,
                permission=Permission.TICKETS_VIEW,
                token=f"ticket:{ticket.id}:new",
                title=title,
                message=admin_message,
            )

        logger.info("فتح المستخدم %s التذكرة #%s (%s)", user.id, ticket.id, category)
        return ticket

    async def _check_daily_limit(self, user: User) -> None:
        """
        تطبيق الحد اليومي لعدد التذاكر لكل مستخدم.

        الاستثناءات: ValidationError عند التجاوز.
        """
        max_per_day = await self.settings.get_int("max_tickets_per_day", 5)
        if max_per_day <= 0:
            return
        start_today, _ = day_bounds_utc(0)
        today = await self.repos.tickets.count_today_by_user(user.id, start_today)
        if today >= max_per_day:
            raise ValidationError(
                f"المستخدم {user.id} تجاوز {max_per_day} تذاكر اليوم",
                user_message=f"⏳ وصلت للحد اليومي ({max_per_day} تذاكر). حاول غداً.",
            )

    async def _validate_related_order(self, user: User, order_id: int | None) -> int | None:
        """
        التأكد من أن الطلب المرتبط بالتذكرة يخص المستخدم نفسه.

        الاستثناءات: TicketError إذا كان الطلب لمستخدم آخر أو غير موجود.
        """
        if order_id is None:
            return None
        order = await self.repos.orders.get(order_id)
        if order is None or order.user_id != user.id:
            raise TicketError(
                f"الطلب {order_id} لا يخص المستخدم {user.id}",
                user_message="❌ رقم الطلب المرتبط غير صحيح.",
            )
        return order.id

    # ===================================================================== #
    #                              المحادثة                                 #
    # ===================================================================== #

    async def reply_as_user(
        self,
        user: User,
        ticket_id: int,
        message: str,
        *,
        attachment_file_id: str | None = None,
        attachment_type: str | None = None,
    ) -> SupportMessage:
        """
        إضافة رد من المستخدم على تذكرته وإشعار فريق الدعم.

        التذكرة المغلقة تُعاد فتحها تلقائياً ضمن مهلة `ticket_reopen_hours`.

        الاستثناءات:
            TicketError     : التذكرة غير موجودة أو ليست له أو مغلقة نهائياً.
            ValidationError : نص الرسالة غير صالح.
        """
        await self.auth.guard(user)
        ticket = await self.get_for_user(user, ticket_id)
        clean_message = validate_message(message)

        if ticket.status == TicketStatus.CLOSED:
            await self._reopen_or_fail(ticket)

        async with self.db.transaction() as tx:
            support_message = await self.repos.tickets.add_message(
                tx,
                ticket_id=ticket.id,
                sender_type=SenderType.USER,
                sender_id=user.id,
                message=clean_message,
                attachment_file_id=attachment_file_id,
                attachment_type=attachment_type,
            )
            title, admin_text = templates.admin_new_ticket(
                ticket_id=ticket.id,
                subject=f"رد جديد — {ticket.subject}",
                user_label=user.display_name,
            )
            await self.notifications.notify_admins(
                tx,
                permission=Permission.TICKETS_VIEW,
                token=f"ticket:{ticket.id}:msg:{support_message.id}",
                title=title,
                message=admin_text,
            )
        logger.info("رد المستخدم %s على التذكرة #%s", user.id, ticket_id)
        return support_message

    async def _reopen_or_fail(self, ticket: SupportTicket) -> None:
        """
        إعادة فتح تذكرة مغلقة إن كانت ضمن المهلة المسموحة.

        الاستثناءات: TicketError إذا انتهت المهلة أو كانت إعادة الفتح معطّلة.
        """
        reopen_hours = await self.settings.get_int("ticket_reopen_hours", 48)
        closed_at = parse_iso(ticket.closed_at)
        age_hours = ((utc_now() - closed_at).total_seconds() / 3600) if closed_at else 0.0

        if reopen_hours <= 0 or (closed_at is not None and age_hours > reopen_hours):
            raise TicketError(
                f"التذكرة {ticket.id} مغلقة منذ {age_hours:.1f} ساعة",
                user_message="🔒 هذه التذكرة مغلقة. افتح تذكرة جديدة لمتابعة طلبك.",
            )

        async with self.db.transaction() as tx:
            reopened = await self.repos.tickets.reopen(tx, ticket.id)
        if reopened:
            logger.info("أُعيد فتح التذكرة #%s", ticket.id)

    async def reply_as_admin(
        self,
        actor: User,
        ticket_id: int,
        message: str,
        *,
        attachment_file_id: str | None = None,
        attachment_type: str | None = None,
        close_after: bool = False,
    ) -> SupportMessage:
        """
        رد فريق الدعم على تذكرة، مع إسنادها للمُجيب إن لم تكن مُسندة.

        المدخلات:
            close_after : إغلاق التذكرة مباشرة بعد الرد.

        الاستثناءات:
            PermissionDeniedError · TicketError · ValidationError
        """
        await self.auth.require_permission(
            actor, Permission.TICKETS_REPLY, context=f"ticket:{ticket_id}"
        )
        ticket = await self._require_ticket(ticket_id)
        clean_message = validate_message(message)

        async with self.db.transaction() as tx:
            if ticket.status == TicketStatus.CLOSED:
                await self.repos.tickets.reopen(tx, ticket.id)
            if ticket.assigned_admin is None:
                await self.repos.tickets.assign(tx, ticket.id, actor.id)

            support_message = await self.repos.tickets.add_message(
                tx,
                ticket_id=ticket.id,
                sender_type=SenderType.ADMIN,
                sender_id=actor.id,
                message=clean_message,
                attachment_file_id=attachment_file_id,
                attachment_type=attachment_type,
            )
            await self.repos.tickets.mark_read(tx, ticket.id, by_admin=True)

            title, text = templates.ticket_replied(
                ticket_id=ticket.id, preview=clean_message[:PREVIEW_LENGTH]
            )
            await self.notifications.notify_user_manual(
                tx,
                user_id=ticket.user_id,
                token=f"ticket:{ticket.id}:reply:{support_message.id}",
                title=title,
                message=text,
                type=NotificationType.TICKET_REPLIED,
            )
            await self.audit.log(
                tx,
                action="tickets.reply",
                admin_id=actor.id,
                target_type="ticket",
                target_id=ticket.id,
                details={"message_id": support_message.id, "close_after": close_after},
            )

        if close_after:
            await self.close(actor, ticket_id, reason="تم حل المشكلة")
        logger.info("رد الأدمن %s على التذكرة #%s", actor.id, ticket_id)
        return support_message

    # ===================================================================== #
    #                        الإسناد والأولوية والإغلاق                     #
    # ===================================================================== #

    async def assign(self, actor: User, ticket_id: int, admin_id: int) -> bool:
        """
        إسناد التذكرة إلى أدمن معيّن.

        الاستثناءات:
            PermissionDeniedError : المنفّذ لا يملك `tickets.assign`، أو الهدف ليس أدمن.
            TicketError           : التذكرة غير موجودة.
        """
        await self.auth.require_permission(
            actor, Permission.TICKETS_ASSIGN, context=f"ticket:{ticket_id}"
        )
        ticket = await self._require_ticket(ticket_id)

        target = await self.repos.users.get_by_id(admin_id)
        if target is None or not await self.auth.is_admin(target):
            raise PermissionDeniedError(
                f"المستخدم {admin_id} ليس أدمن",
                user_message="❌ لا يمكن إسناد التذكرة لمستخدم غير إداري.",
            )

        async with self.db.transaction() as tx:
            changed = await self.repos.tickets.assign(tx, ticket_id, admin_id)
            if changed:
                await self.audit.log(
                    tx,
                    action="tickets.assign",
                    admin_id=actor.id,
                    target_type="ticket",
                    target_id=ticket_id,
                    before={"assigned_admin": ticket.assigned_admin},
                    after={"assigned_admin": admin_id},
                )
        return changed

    async def set_priority(self, actor: User, ticket_id: int, priority: str) -> bool:
        """
        تغيير أولوية التذكرة (low / normal / high).

        الاستثناءات: PermissionDeniedError · TicketError · ValidationError
        """
        await self.auth.require_permission(
            actor, Permission.TICKETS_ASSIGN, context=f"ticket:{ticket_id}"
        )
        if priority not in set(TicketPriority):
            raise ValidationError(
                f"أولوية غير معروفة: {priority}", user_message="❌ أولوية غير صحيحة."
            )
        ticket = await self._require_ticket(ticket_id)

        async with self.db.transaction() as tx:
            changed = await self.repos.tickets.update_fields(tx, ticket_id, priority=priority)
            if changed:
                await self.audit.log(
                    tx,
                    action="tickets.assign",
                    admin_id=actor.id,
                    target_type="ticket",
                    target_id=ticket_id,
                    before={"priority": ticket.priority},
                    after={"priority": priority},
                )
        return changed

    async def close(self, actor: User, ticket_id: int, reason: str = "") -> bool:
        """
        إغلاق التذكرة من فريق الدعم مع إشعار المستخدم.

        المخرجات: True عند الإغلاق الفعلي (False إذا كانت مغلقة أصلاً).
        """
        await self.auth.require_permission(
            actor, Permission.TICKETS_CLOSE, context=f"ticket:{ticket_id}"
        )
        ticket = await self._require_ticket(ticket_id)
        clean_reason = (reason or "").strip()[:200] or "تم إغلاق التذكرة"
        stamp = len(await self.repos.tickets.messages(ticket_id, limit=500))

        async with self.db.transaction() as tx:
            closed = await self.repos.tickets.close(
                tx, ticket_id, closed_by=actor.id, reason=clean_reason
            )
            if not closed:
                return False
            title, text = templates.ticket_closed(ticket_id=ticket_id, reason=clean_reason)
            await self.notifications.notify_user_manual(
                tx,
                user_id=ticket.user_id,
                token=f"ticket:{ticket_id}:closed:{stamp}",
                title=title,
                message=text,
                type=NotificationType.TICKET_CLOSED,
            )
            await self.audit.log(
                tx,
                action="tickets.close",
                admin_id=actor.id,
                target_type="ticket",
                target_id=ticket_id,
                before={"status": ticket.status},
                after={"status": TicketStatus.CLOSED, "reason": clean_reason},
            )
        logger.info("أغلق الأدمن %s التذكرة #%s", actor.id, ticket_id)
        return True

    async def close_by_user(self, user: User, ticket_id: int) -> bool:
        """إغلاق المستخدم لتذكرته بنفسه بعد حل مشكلته."""
        ticket = await self.get_for_user(user, ticket_id)
        async with self.db.transaction() as tx:
            closed = await self.repos.tickets.close(
                tx, ticket.id, closed_by=user.id, reason="أغلقها المستخدم"
            )
        if closed:
            logger.info("أغلق المستخدم %s التذكرة #%s", user.id, ticket_id)
        return closed

    async def auto_close_idle(self) -> int:
        """
        إغلاق التذاكر الراكدة (بانتظار رد المستخدم) بعد المدة المحددة في الإعدادات.

        المخرجات: عدد التذاكر التي أُغلقت.
        """
        days = await self.settings.get_int("ticket_auto_close_days", 7)
        if days <= 0:
            return 0
        cutoff = iso_plus_seconds(-days * 86400)
        idle = await self.repos.tickets.list_idle(
            statuses=(TicketStatus.PENDING_USER,), before_iso=cutoff, limit=50
        )
        closed_count = 0
        for ticket in idle:
            async with self.db.transaction() as tx:
                closed = await self.repos.tickets.close(
                    tx, ticket.id, closed_by=None, reason=f"إغلاق تلقائي بعد {days} أيام بلا رد"
                )
                if not closed:
                    continue
                title, text = templates.ticket_closed(
                    ticket_id=ticket.id, reason=f"إغلاق تلقائي بعد {days} أيام بلا رد"
                )
                await self.notifications.notify_user_manual(
                    tx,
                    user_id=ticket.user_id,
                    token=f"ticket:{ticket.id}:autoclosed",
                    title=title,
                    message=text,
                    type=NotificationType.TICKET_CLOSED,
                )
            closed_count += 1
        if closed_count:
            logger.info("أُغلقت %s تذكرة راكدة تلقائياً", closed_count)
        return closed_count

    # ===================================================================== #
    #                                القراءة                                #
    # ===================================================================== #

    async def get_for_user(self, user: User, ticket_id: int) -> SupportTicket:
        """
        جلب تذكرة تخص المستخدم نفسه.

        الاستثناءات: TicketError إذا لم توجد أو كانت لمستخدم آخر.
        """
        ticket = await self.repos.tickets.get(ticket_id)
        if ticket is None or ticket.user_id != user.id:
            raise TicketError(
                f"التذكرة {ticket_id} غير متاحة للمستخدم {user.id}",
                user_message="❌ لم يتم العثور على التذكرة.",
            )
        return ticket

    async def _require_ticket(self, ticket_id: int) -> SupportTicket:
        """
        جلب تذكرة للإدارة.

        الاستثناءات: TicketError إذا لم توجد.
        """
        ticket = await self.repos.tickets.get(ticket_id)
        if ticket is None:
            raise TicketError(
                f"التذكرة {ticket_id} غير موجودة", user_message="❌ التذكرة غير موجودة."
            )
        return ticket

    async def list_for_user(
        self, user: User, *, limit: int = 10, offset: int = 0
    ) -> list[SupportTicket]:
        """تذاكر المستخدم من الأحدث للأقدم."""
        return await self.repos.tickets.list_by_user(user.id, limit=limit, offset=offset)

    async def conversation_for_user(
        self, user: User, ticket_id: int, *, limit: int = 50
    ) -> list[SupportMessage]:
        """رسائل تذكرة المستخدم مع تعليمها كمقروءة من طرفه."""
        ticket = await self.get_for_user(user, ticket_id)
        messages = await self.repos.tickets.messages(ticket.id, limit=limit)
        async with self.db.transaction() as tx:
            await self.repos.tickets.mark_read(tx, ticket.id, by_admin=False)
        return messages

    async def admin_list(
        self,
        actor: User,
        *,
        statuses: tuple[str, ...] = OPEN_STATUSES,
        assigned_admin: int | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[SupportTicket]:
        """
        قائمة التذاكر لفريق الدعم (الافتراضي: غير المغلقة).

        المدخلات:
            statuses       : الحالات المطلوبة.
            assigned_admin : حصر النتائج بالتذاكر المسندة لأدمن بعينه (تبويب «المسندة لي»).
        """
        await self.auth.require_permission(actor, Permission.TICKETS_VIEW)
        return await self.repos.tickets.list_by_status(
            list(statuses), assigned_admin=assigned_admin, limit=limit, offset=offset
        )

    async def admin_count(
        self,
        actor: User,
        *,
        statuses: tuple[str, ...] = OPEN_STATUSES,
        assigned_admin: int | None = None,
    ) -> int:
        """عدد التذاكر المطابقة لتصفية `admin_list` (لحساب عدد الصفحات)."""
        await self.auth.require_permission(actor, Permission.TICKETS_VIEW)
        return await self.repos.tickets.count_by_status(
            list(statuses), assigned_admin=assigned_admin
        )

    async def admin_conversation(
        self, actor: User, ticket_id: int, *, limit: int = 50
    ) -> tuple[SupportTicket, list[SupportMessage]]:
        """
        فتح تذكرة في لوحة الدعم: التذكرة + رسائلها، مع تعليمها كمقروءة من الأدمن.
        """
        await self.auth.require_permission(actor, Permission.TICKETS_VIEW)
        ticket = await self._require_ticket(ticket_id)
        messages = await self.repos.tickets.messages(ticket_id, limit=limit)
        async with self.db.transaction() as tx:
            await self.repos.tickets.mark_read(tx, ticket_id, by_admin=True)
        return ticket, messages

    async def open_count(self) -> int:
        """عدد التذاكر غير المغلقة (شارة لوحة الأدمن)."""
        return await self.repos.tickets.count_open()
```

### `database/repositories/orders.py`

```python
"""
مستودع الطلبات — أهم مستودع في النظام.

يوفّر العمليات الذرّية التي تمنع أخطر مشكلتين:
    1. تغيير حالة الطلب من مكانين في نفس اللحظة  → update_status المشروط بالحالة السابقة.
    2. معالجة نفس الطلب بواسطة أكثر من job       → claim_* مع قفل زمني (lease).
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from core.constants import ORDER_LOCK_SECONDS
from database.database import Tx
from database.models import Order, OrderStatusHistory
from database.repositories.base import BaseRepository
from utils.datetime_utils import iso_plus_seconds, utc_now_iso

_ALLOWED_FIELDS = {
    "status",
    "provider_status",
    "provider_order_id",
    "provider_cost_units",
    "start_count",
    "remains",
    "delivered_quantity",
    "refund_amount_units",
    "refunded_at",
    "submit_attempts",
    "checks_count",
    "last_error",
    "locked_by",
    "locked_until",
    "next_check_at",
    "submitted_at",
    "completed_at",
    "cancelled_at",
    "public_code",
}


class OrdersRepository(BaseRepository):
    """عمليات قراءة وكتابة الطلبات."""

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, order_id: int) -> Order | None:
        """جلب طلب بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM orders WHERE id = ?", (order_id,))
        return Order.from_row(row)

    async def get_by_client_request_id(self, client_request_id: str) -> Order | None:
        """
        جلب طلب بمفتاح الطلب الفريد القادم من واجهة المستخدم.

        الفائدة: إذا ضغط المستخدم «تأكيد» مرتين، نُرجع نفس الطلب بدل إنشاء طلب جديد.
        """
        row = await self.db.fetchone(
            "SELECT * FROM orders WHERE client_request_id = ?", (client_request_id,)
        )
        return Order.from_row(row)

    async def get_by_provider_order_id(self, provider_id: int, provider_order_id: str) -> Order | None:
        """جلب طلب برقمه عند المزود (للتسوية اليدوية)."""
        row = await self.db.fetchone(
            "SELECT * FROM orders WHERE provider_id = ? AND provider_order_id = ?",
            (provider_id, str(provider_order_id)),
        )
        return Order.from_row(row)

    async def list_by_user(
        self, user_id: int, *, statuses: Sequence[str] | None = None, limit: int = 8, offset: int = 0
    ) -> list[Order]:
        """قائمة طلبات مستخدم مع إمكانية الفلترة بالحالة."""
        sql = "SELECT * FROM orders WHERE user_id = ?"
        params: list[Any] = [user_id]
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            sql += f" AND status IN ({placeholders})"
            params.extend(statuses)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = await self.db.fetchall(sql, params)
        return Order.from_rows(rows)

    async def count_by_user(self, user_id: int, *, statuses: Sequence[str] | None = None) -> int:
        """عدد طلبات مستخدم (لحساب الصفحات والحدود اليومية)."""
        where = "user_id = ?"
        params: list[Any] = [user_id]
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            where += f" AND status IN ({placeholders})"
            params.extend(statuses)
        return await self.count("orders", where, params)

    async def count_today_by_user(self, user_id: int, since_iso: str) -> int:
        """عدد طلبات المستخدم منذ بداية اليوم (لتطبيق الحد اليومي)."""
        return await self.count("orders", "user_id = ? AND created_at >= ?", (user_id, since_iso))

    async def list_by_status(self, status: str, *, limit: int = 20, offset: int = 0) -> list[Order]:
        """قائمة الطلبات حسب الحالة (للوحة الأدمن)."""
        rows = await self.db.fetchall(
            "SELECT * FROM orders WHERE status = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (status, limit, offset),
        )
        return Order.from_rows(rows)

    async def list_by_statuses(
        self,
        statuses: Sequence[str] | None = None,
        *,
        user_id: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Order]:
        """
        قائمة الطلبات لعدة حالات دفعة واحدة (قوائم لوحة الأدمن).

        المدخلات:
            statuses : الحالات المطلوبة، و`None` أو قائمة فارغة تعني كل الحالات.
            user_id  : حصر النتائج بمستخدم واحد (تبويب «طلباته» في بطاقة المستخدم).
            limit/offset : الترقيم.

        المخرجات: قائمة طلبات مرتبة من الأحدث إلى الأقدم.
        """
        where, params = self._admin_filter(statuses, user_id)
        rows = await self.db.fetchall(
            f"SELECT * FROM orders WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
        return Order.from_rows(rows)

    async def count_by_statuses(
        self, statuses: Sequence[str] | None = None, *, user_id: int | None = None
    ) -> int:
        """عدد الطلبات المطابقة لنفس مرشّحات `list_by_statuses` (لحساب عدد الصفحات)."""
        where, params = self._admin_filter(statuses, user_id)
        return await self.count("orders", where, tuple(params))

    @staticmethod
    def _admin_filter(
        statuses: Sequence[str] | None, user_id: int | None
    ) -> tuple[str, list[Any]]:
        """بناء شرط WHERE المشترك بين قائمة الأدمن وعدّادها (مصدر واحد للمنطق)."""
        clauses: list[str] = ["1 = 1"]
        params: list[Any] = []
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(statuses)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        return " AND ".join(clauses), params

    async def status_counts(self) -> dict[str, int]:
        """عدد الطلبات في كل حالة (لوحة الإحصائيات)."""
        rows = await self.db.fetchall("SELECT status, COUNT(*) AS c FROM orders GROUP BY status")
        return {row["status"]: int(row["c"]) for row in rows}

    async def find_recent_duplicate(
        self, *, user_id: int, service_id: int, link: str, quantity: int, since_iso: str
    ) -> Order | None:
        """
        كشف طلب مشابه خلال نافذة زمنية (نفس المستخدم والخدمة والرابط والكمية).

        الفائدة: تحذير المستخدم قبل تكرار الدفع بالخطأ.
        """
        row = await self.db.fetchone(
            """
            SELECT * FROM orders
             WHERE user_id = ? AND service_id = ? AND link = ? AND quantity = ?
               AND created_at >= ?
               AND status NOT IN ('failed', 'canceled', 'refunded')
             ORDER BY id DESC LIMIT 1
            """,
            (user_id, service_id, link, quantity, since_iso),
        )
        return Order.from_row(row)

    async def history(self, order_id: int) -> list[OrderStatusHistory]:
        """سجل انتقالات حالة الطلب."""
        rows = await self.db.fetchall(
            "SELECT * FROM order_status_history WHERE order_id = ? ORDER BY id", (order_id,)
        )
        return OrderStatusHistory.from_rows(rows)

    async def stuck_orders(self, *, before_iso: str, limit: int = 20) -> list[Order]:
        """الطلبات النشطة التي تجاوزت المدة المتوقعة (لتنبيه الأدمن)."""
        rows = await self.db.fetchall(
            """
            SELECT * FROM orders
             WHERE status IN ('pending', 'submitting', 'submit_uncertain', 'submitted', 'in_progress')
               AND created_at <= ?
             ORDER BY id LIMIT ?
            """,
            (before_iso, limit),
        )
        return Order.from_rows(rows)

    async def sum_cost_between(self, start_iso: str, end_iso: str) -> int:
        """إجمالي قيمة الطلبات المنشأة خلال فترة (بالنقاط)."""
        return int(
            await self.db.fetchval(
                "SELECT COALESCE(SUM(cost_units), 0) FROM orders WHERE created_at >= ? AND created_at < ?",
                (start_iso, end_iso),
                default=0,
            )
        )

    async def count_between(self, start_iso: str, end_iso: str) -> int:
        """عدد الطلبات المنشأة بين تاريخين (للإحصائيات)."""
        return await self.count("orders", "created_at >= ? AND created_at < ?", (start_iso, end_iso))

    async def count_between_by_status(
        self, start_iso: str, end_iso: str, statuses: Sequence[str]
    ) -> int:
        """عدد الطلبات بين تاريخين ضمن حالات محددة (نسبة النجاح/الفشل)."""
        placeholders = ", ".join("?" for _ in statuses)
        return await self.count(
            "orders",
            f"created_at >= ? AND created_at < ? AND status IN ({placeholders})",
            [start_iso, end_iso, *statuses],
        )

    async def top_services(
        self, *, start_iso: str, end_iso: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        """
        أكثر الخدمات طلباً خلال فترة.

        المخرجات: صفوف فيها service_name و orders_count و total_units.
        """
        rows = await self.db.fetchall(
            """
            SELECT service_name_snapshot AS service_name,
                   COUNT(*)              AS orders_count,
                   COALESCE(SUM(cost_units), 0) AS total_units
              FROM orders
             WHERE created_at >= ? AND created_at < ?
             GROUP BY service_id
             ORDER BY orders_count DESC, total_units DESC
             LIMIT ?
            """,
            (start_iso, end_iso, limit),
        )
        return [dict(row) for row in rows]

    async def daily_series(self, *, start_iso: str, end_iso: str) -> list[dict[str, Any]]:
        """
        سلسلة يومية: عدد الطلبات وقيمتها لكل يوم ضمن الفترة (لتقرير الأدمن).
        """
        rows = await self.db.fetchall(
            """
            SELECT substr(created_at, 1, 10) AS day,
                   COUNT(*)                  AS orders_count,
                   COALESCE(SUM(cost_units), 0) AS total_units
              FROM orders
             WHERE created_at >= ? AND created_at < ?
             GROUP BY day
             ORDER BY day
            """,
            (start_iso, end_iso),
        )
        return [dict(row) for row in rows]

    async def sum_provider_cost_between(self, start_iso: str, end_iso: str) -> int:
        """إجمالي تكلفة المزود خلال فترة (لحساب الربح التقريبي)."""
        return int(
            await self.db.fetchval(
                """
                SELECT COALESCE(SUM(provider_cost_units), 0) FROM orders
                 WHERE created_at >= ? AND created_at < ? AND provider_cost_units IS NOT NULL
                """,
                (start_iso, end_iso),
                default=0,
            )
        )

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        user_id: int,
        service_id: int,
        provider_id: int,
        service_name_snapshot: str,
        price_per_1000_snapshot_units: int,
        link: str,
        quantity: int,
        cost_units: int,
        client_request_id: str,
        provider_cost_units: int | None = None,
        status: str = "pending",
    ) -> Order:
        """
        إنشاء طلب جديد بحالة pending.

        ملاحظة: خصم الرصيد وتسجيل الحركة المالية يتمان في نفس المعاملة
        داخل OrderService، وليس هنا.
        """
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO orders (user_id, service_id, provider_id, service_name_snapshot,
                                price_per_1000_snapshot_units, link, quantity, cost_units,
                                provider_cost_units, status, client_request_id,
                                created_at, updated_at, next_check_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id, service_id, provider_id, service_name_snapshot,
                price_per_1000_snapshot_units, link, quantity, cost_units,
                provider_cost_units, status, client_request_id, now, now, now,
            ),
        )
        row = await tx.fetchone("SELECT * FROM orders WHERE id = ?", (result.lastrowid,))
        order = Order.from_row(row)
        assert order is not None
        return order

    async def add_history(
        self,
        tx: Tx,
        *,
        order_id: int,
        from_status: str | None,
        to_status: str,
        actor_type: str = "system",
        actor_id: int | None = None,
        reason: str | None = None,
        provider_status_raw: str | None = None,
    ) -> None:
        """تسجيل انتقال حالة في سجل الطلب (يُستدعى مع كل تغيير حالة)."""
        await tx.execute(
            """
            INSERT INTO order_status_history (order_id, from_status, to_status, actor_type,
                                              actor_id, reason, provider_status_raw, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (order_id, from_status, to_status, actor_type, actor_id, reason, provider_status_raw, self.now()),
        )

    async def update_status(
        self,
        tx: Tx,
        order_id: int,
        *,
        new_status: str,
        expected_statuses: Iterable[str],
        extra_fields: dict[str, Any] | None = None,
    ) -> bool:
        """
        تغيير حالة الطلب بشكل مشروط بالحالة الحالية (العمود الفقري لمنع التغيير العشوائي).

        المدخلات:
            new_status        : الحالة الجديدة.
            expected_statuses : الحالات المسموح الانتقال منها.
            extra_fields      : حقول إضافية تُحدَّث في نفس العبارة (رقم المزود، أوقات ...).

        المخرجات: True إذا تم التغيير فعلاً، False إذا كانت حالة الطلب مختلفة
                  (يعني أن جهة أخرى غيّرتها قبلنا — وهذا ليس خطأً بل حماية).
        """
        statuses = list(expected_statuses)
        if not statuses:
            raise ValueError("يجب تحديد الحالات المتوقعة قبل تغيير حالة الطلب.")

        fields: dict[str, Any] = {"status": new_status}
        if extra_fields:
            fields.update(extra_fields)
        set_sql, values = self._build_update(fields, _ALLOWED_FIELDS)
        set_sql += ", updated_at = ?"
        values.append(self.now())
        placeholders = ", ".join("?" for _ in statuses)
        values.append(order_id)
        values.extend(statuses)

        result = await tx.execute(
            f"UPDATE orders SET {set_sql} WHERE id = ? AND status IN ({placeholders})", values
        )
        return result.rowcount == 1

    async def update_fields(self, tx: Tx, order_id: int, **fields: Any) -> bool:
        """تعديل حقول غير حالة الطلب (تقدم التنفيذ، مواعيد الفحص ...)."""
        return await self._update_by_id(tx, "orders", order_id, fields, _ALLOWED_FIELDS)

    async def add_refund_amount(self, tx: Tx, order_id: int, amount_units: int) -> bool:
        """
        زيادة مبلغ الاسترجاع المسجَّل على الطلب دون تجاوز التكلفة.

        المخرجات: True عند النجاح، False إذا كان المبلغ سيتجاوز تكلفة الطلب
                  (حماية إضافية فوق قيد CHECK في قاعدة البيانات).
        """
        result = await tx.execute(
            """
            UPDATE orders
               SET refund_amount_units = refund_amount_units + ?,
                   refunded_at = ?, updated_at = ?
             WHERE id = ? AND refund_amount_units + ? <= cost_units
            """,
            (amount_units, self.now(), self.now(), order_id, amount_units),
        )
        return result.rowcount == 1

    # --------------------------- الأقفال والمهام --------------------------- #

    async def claim_pending_for_submit(
        self, tx: Tx, *, worker: str, limit: int = 5, lock_seconds: int = ORDER_LOCK_SECONDS
    ) -> list[Order]:
        """
        حجز دفعة من الطلبات المعلّقة لإرسالها للمزود.

        الآلية: لكل طلب مرشّح يُنفَّذ UPDATE مشروط (status='pending' وغير مقفول)؛
        من ينجح UPDATE الخاص به هو من يملك الطلب — فلا يعالجه worker آخر.

        ملاحظة: يُحترم `next_check_at` هنا أيضاً، لأن الطلب الذي فشل إرساله مؤقتاً
        يعود إلى pending بموعد محاولة مؤجَّل؛ وتجاهل الموعد يعني إغراق المزود
        بمحاولات متتالية بلا تهدئة.
        """
        now = utc_now_iso()
        candidates = await tx.fetchall(
            """
            SELECT id FROM orders
             WHERE status = 'pending'
               AND (next_check_at IS NULL OR next_check_at <= ?)
               AND (locked_until IS NULL OR locked_until < ?)
             ORDER BY id LIMIT ?
            """,
            (now, now, limit),
        )
        claimed: list[Order] = []
        for row in candidates:
            ok = await tx.execute(
                """
                UPDATE orders
                   SET status = 'submitting', locked_by = ?, locked_until = ?,
                       submit_attempts = submit_attempts + 1, updated_at = ?
                 WHERE id = ? AND status = 'pending'
                   AND (locked_until IS NULL OR locked_until < ?)
                """,
                (worker, iso_plus_seconds(lock_seconds), now, row["id"], now),
            )
            if ok.rowcount == 1:
                order_row = await tx.fetchone("SELECT * FROM orders WHERE id = ?", (row["id"],))
                order = Order.from_row(order_row)
                if order is not None:
                    claimed.append(order)
                    await self.add_history(
                        tx,
                        order_id=order.id,
                        from_status="pending",
                        to_status="submitting",
                        actor_type="job",
                        reason=f"حجز للإرسال بواسطة {worker}",
                    )
        return claimed

    async def claim_due_for_check(
        self, tx: Tx, *, worker: str, limit: int = 20, lock_seconds: int = ORDER_LOCK_SECONDS
    ) -> list[Order]:
        """
        حجز دفعة من الطلبات النشطة التي حان موعد فحص حالتها عند المزود.

        لا تُغيَّر حالة الطلب هنا — فقط يوضع قفل زمني لتفادي الفحص المزدوج.
        """
        now = utc_now_iso()
        candidates = await tx.fetchall(
            """
            SELECT id FROM orders
             WHERE status IN ('submitted', 'in_progress')
               AND provider_order_id IS NOT NULL
               AND (next_check_at IS NULL OR next_check_at <= ?)
               AND (locked_until IS NULL OR locked_until < ?)
             ORDER BY next_check_at LIMIT ?
            """,
            (now, now, limit),
        )
        claimed: list[Order] = []
        for row in candidates:
            ok = await tx.execute(
                """
                UPDATE orders
                   SET locked_by = ?, locked_until = ?, checks_count = checks_count + 1, updated_at = ?
                 WHERE id = ? AND (locked_until IS NULL OR locked_until < ?)
                """,
                (worker, iso_plus_seconds(lock_seconds), now, row["id"], now),
            )
            if ok.rowcount == 1:
                order_row = await tx.fetchone("SELECT * FROM orders WHERE id = ?", (row["id"],))
                order = Order.from_row(order_row)
                if order is not None:
                    claimed.append(order)
        return claimed

    async def release_lock(self, tx: Tx, order_id: int, *, next_check_at: str | None = None) -> None:
        """تحرير قفل الطلب بعد انتهاء المعالجة، مع تحديد موعد الفحص القادم اختيارياً."""
        if next_check_at is None:
            await tx.execute(
                "UPDATE orders SET locked_by = NULL, locked_until = NULL, updated_at = ? WHERE id = ?",
                (self.now(), order_id),
            )
        else:
            await tx.execute(
                """
                UPDATE orders SET locked_by = NULL, locked_until = NULL,
                       next_check_at = ?, updated_at = ? WHERE id = ?
                """,
                (next_check_at, self.now(), order_id),
            )

    async def release_expired_locks(self, tx: Tx) -> int:
        """
        تحرير كل الأقفال المنتهية (يُستدعى عند إقلاع البوت ضمن عملية الاسترداد).

        المخرجات: عدد الطلبات التي حُرِّرت.
        """
        result = await tx.execute(
            """
            UPDATE orders SET locked_by = NULL, locked_until = NULL, updated_at = ?
             WHERE locked_until IS NOT NULL AND locked_until < ?
            """,
            (self.now(), utc_now_iso()),
        )
        return result.rowcount

    async def recover_submitting_orders(self, tx: Tx) -> list[int]:
        """
        معالجة الطلبات العالقة في حالة submitting بعد إعادة تشغيل مفاجئ.

        القاعدة: إذا لم يُسجَّل رقم الطلب عند المزود فالنتيجة غير مؤكدة
        (ربما وصل الطلب وربما لا) ⇒ تُنقل إلى submit_uncertain لمراجعة الأدمن،
        وممنوع إعادة إرسالها تلقائياً.

        المخرجات: قائمة معرفات الطلبات التي نُقلت إلى submit_uncertain.
        """
        rows = await tx.fetchall(
            "SELECT id FROM orders WHERE status = 'submitting' AND provider_order_id IS NULL"
        )
        ids: list[int] = []
        for row in rows:
            ok = await tx.execute(
                """
                UPDATE orders SET status = 'submit_uncertain', locked_by = NULL, locked_until = NULL,
                       last_error = 'انقطاع أثناء الإرسال - تحتاج مراجعة يدوية', updated_at = ?
                 WHERE id = ? AND status = 'submitting'
                """,
                (self.now(), row["id"]),
            )
            if ok.rowcount == 1:
                ids.append(int(row["id"]))
                await self.add_history(
                    tx,
                    order_id=int(row["id"]),
                    from_status="submitting",
                    to_status="submit_uncertain",
                    actor_type="system",
                    reason="استرداد بعد إعادة تشغيل البوت",
                )
        return ids
```

### `database/repositories/tickets.py`

```python
"""مستودع الدعم الفني — التذاكر ورسائلها."""

from __future__ import annotations

from typing import Any, Sequence

from database.database import Tx
from database.models import SupportMessage, SupportTicket
from database.repositories.base import BaseRepository

_TICKET_FIELDS = {
    "subject",
    "category",
    "related_order_id",
    "status",
    "priority",
    "assigned_admin",
    "last_message_at",
    "closed_by",
    "close_reason",
    "closed_at",
}


class TicketsRepository(BaseRepository):
    """عمليات التذاكر ورسائل الدعم."""

    # ------------------------------ القراءة ------------------------------ #

    async def get(self, ticket_id: int) -> SupportTicket | None:
        """جلب تذكرة بالمعرف."""
        row = await self.db.fetchone("SELECT * FROM support_tickets WHERE id = ?", (ticket_id,))
        return SupportTicket.from_row(row)

    async def list_by_user(self, user_id: int, *, limit: int = 10, offset: int = 0) -> list[SupportTicket]:
        """تذاكر مستخدم معين."""
        rows = await self.db.fetchall(
            "SELECT * FROM support_tickets WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        )
        return SupportTicket.from_rows(rows)

    async def list_by_status(
        self,
        statuses: Sequence[str],
        *,
        assigned_admin: int | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[SupportTicket]:
        """
        التذاكر حسب الحالة (للوحة الدعم).

        المدخلات:
            statuses       : الحالات المطلوبة.
            assigned_admin : حصر النتائج بالتذاكر المسندة لأدمن بعينه (تبويب «المسندة لي»).
        """
        where, params = self._status_filter(statuses, assigned_admin)
        rows = await self.db.fetchall(
            f"""
            SELECT * FROM support_tickets WHERE {where}
             ORDER BY COALESCE(last_message_at, created_at) DESC LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        )
        return SupportTicket.from_rows(rows)

    async def count_by_status(
        self, statuses: Sequence[str], *, assigned_admin: int | None = None
    ) -> int:
        """عدد التذاكر المطابقة لنفس مرشّحات `list_by_status` (لحساب عدد الصفحات)."""
        where, params = self._status_filter(statuses, assigned_admin)
        return await self.count("support_tickets", where, tuple(params))

    @staticmethod
    def _status_filter(
        statuses: Sequence[str], assigned_admin: int | None
    ) -> tuple[str, list[Any]]:
        """بناء شرط WHERE المشترك بين قائمة التذاكر وعدّادها."""
        clauses: list[str] = []
        params: list[Any] = []
        if statuses:
            placeholders = ", ".join("?" for _ in statuses)
            clauses.append(f"status IN ({placeholders})")
            params.extend(statuses)
        else:
            clauses.append("1 = 1")
        if assigned_admin is not None:
            clauses.append("assigned_admin = ?")
            params.append(assigned_admin)
        return " AND ".join(clauses), params

    async def list_idle(
        self, *, statuses: Sequence[str], before_iso: str, limit: int = 50
    ) -> list[SupportTicket]:
        """
        التذاكر الراكدة: لم تصلها رسالة منذ تاريخ معيّن (للإغلاق التلقائي).

        المدخلات:
            statuses   : الحالات المستهدفة (عادةً pending_user).
            before_iso : أقدم وقت مقبول لآخر رسالة.
        """
        placeholders = ", ".join("?" for _ in statuses)
        rows = await self.db.fetchall(
            f"""
            SELECT * FROM support_tickets
             WHERE status IN ({placeholders})
               AND COALESCE(last_message_at, created_at) <= ?
             ORDER BY id LIMIT ?
            """,
            [*statuses, before_iso, limit],
        )
        return SupportTicket.from_rows(rows)

    async def count_open(self) -> int:
        """عدد التذاكر غير المغلقة."""
        return await self.count("support_tickets", "status != 'closed'")

    async def count_today_by_user(self, user_id: int, since_iso: str) -> int:
        """عدد تذاكر المستخدم اليوم (لتطبيق الحد اليومي ومنع الإزعاج)."""
        return await self.count(
            "support_tickets", "user_id = ? AND created_at >= ?", (user_id, since_iso)
        )

    async def messages(self, ticket_id: int, *, limit: int = 50) -> list[SupportMessage]:
        """رسائل تذكرة مرتبة زمنياً."""
        rows = await self.db.fetchall(
            "SELECT * FROM support_messages WHERE ticket_id = ? ORDER BY id LIMIT ?",
            (ticket_id, limit),
        )
        return SupportMessage.from_rows(rows)

    async def has_open_ticket(self, user_id: int) -> bool:
        """هل لدى المستخدم تذكرة مفتوحة حالياً؟ (لتوجيهه إليها بدل فتح تذكرة جديدة)."""
        row = await self.db.fetchone(
            "SELECT 1 FROM support_tickets WHERE user_id = ? AND status != 'closed' LIMIT 1",
            (user_id,),
        )
        return row is not None

    # ------------------------------ الكتابة ------------------------------ #

    async def create(
        self,
        tx: Tx,
        *,
        user_id: int,
        subject: str,
        category: str = "other",
        related_order_id: int | None = None,
        priority: str = "normal",
    ) -> SupportTicket:
        """إنشاء تذكرة جديدة بحالة open."""
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO support_tickets (user_id, subject, category, related_order_id, priority,
                                         status, last_message_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'open', ?, ?, ?)
            """,
            (user_id, subject, category, related_order_id, priority, now, now, now),
        )
        row = await tx.fetchone("SELECT * FROM support_tickets WHERE id = ?", (result.lastrowid,))
        ticket = SupportTicket.from_row(row)
        assert ticket is not None
        return ticket

    async def add_message(
        self,
        tx: Tx,
        *,
        ticket_id: int,
        sender_type: str,
        message: str,
        sender_id: int | None = None,
        attachment_file_id: str | None = None,
        attachment_type: str | None = None,
        telegram_message_id: int | None = None,
    ) -> SupportMessage:
        """
        إضافة رسالة إلى تذكرة وتحديث وقت آخر رسالة وحالة التذكرة.

        المنطق: رسالة المستخدم تجعل التذكرة بانتظار رد الأدمن، والعكس صحيح.
        """
        now = self.now()
        result = await tx.execute(
            """
            INSERT INTO support_messages (ticket_id, sender_id, sender_type, message,
                                          attachment_file_id, attachment_type, telegram_message_id,
                                          is_read_by_user, is_read_by_admin, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticket_id, sender_id, sender_type, message, attachment_file_id, attachment_type,
                telegram_message_id,
                1 if sender_type == "user" else 0,
                1 if sender_type in {"admin", "system"} else 0,
                now,
            ),
        )
        new_status = "pending_admin" if sender_type == "user" else "pending_user"
        await tx.execute(
            """
            UPDATE support_tickets
               SET last_message_at = ?, updated_at = ?,
                   status = CASE WHEN status = 'closed' THEN status ELSE ? END
             WHERE id = ?
            """,
            (now, now, new_status, ticket_id),
        )
        row = await tx.fetchone("SELECT * FROM support_messages WHERE id = ?", (result.lastrowid,))
        support_message = SupportMessage.from_row(row)
        assert support_message is not None
        return support_message

    async def update_fields(self, tx: Tx, ticket_id: int, **fields: Any) -> bool:
        """تعديل حقول التذكرة (الأولوية، الإسناد ...)."""
        return await self._update_by_id(tx, "support_tickets", ticket_id, fields, _TICKET_FIELDS)

    async def assign(self, tx: Tx, ticket_id: int, admin_id: int) -> bool:
        """إسناد التذكرة إلى أدمن معين."""
        return await self._update_by_id(
            tx, "support_tickets", ticket_id, {"assigned_admin": admin_id}, _TICKET_FIELDS
        )

    async def close(self, tx: Tx, ticket_id: int, *, closed_by: int | None, reason: str | None = None) -> bool:
        """
        إغلاق التذكرة (مشروط بأن تكون مفتوحة) — لمنع الإغلاق المزدوج.
        """
        result = await tx.execute(
            """
            UPDATE support_tickets
               SET status = 'closed', closed_by = ?, close_reason = ?, closed_at = ?, updated_at = ?
             WHERE id = ? AND status != 'closed'
            """,
            (closed_by, reason, self.now(), self.now(), ticket_id),
        )
        return result.rowcount == 1

    async def reopen(self, tx: Tx, ticket_id: int) -> bool:
        """إعادة فتح تذكرة مغلقة."""
        result = await tx.execute(
            """
            UPDATE support_tickets
               SET status = 'pending_admin', closed_by = NULL, closed_at = NULL, updated_at = ?
             WHERE id = ? AND status = 'closed'
            """,
            (self.now(), ticket_id),
        )
        return result.rowcount == 1

    async def mark_read(self, tx: Tx, ticket_id: int, *, by_admin: bool) -> None:
        """تعليم رسائل التذكرة كمقروءة من طرف الأدمن أو المستخدم."""
        column = "is_read_by_admin" if by_admin else "is_read_by_user"
        await tx.execute(
            f"UPDATE support_messages SET {column} = 1 WHERE ticket_id = ?", (ticket_id,)
        )
```

## الاختبارات الجديدة والمُحدَّثة

### `tests/telegram_fakes.py`

```python
"""
بدائل اختبارية لواجهة تيليجرام (بلا أي اتصال بالشبكة).

الفكرة: نستخدم كائنات `telegram.Update` **حقيقية** (مبنية عبر `de_json`) حتى
نختبر نفس المسارات التي تعمل في الإنتاج، لكن مع بوت مزيّف يسجّل ما كان
سيُرسَل بدل إرساله. هكذا يفحص الاختبار النص النهائي والأزرار الفعلية.
"""

from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from typing import Any

from telegram import InlineKeyboardMarkup, Update

#: عدّاد معرفات التحديثات حتى لا يتكرر رقم داخل اختبار واحد
_update_ids = itertools.count(1000)

#: معرف البوت المزيّف
BOT_ID = 999_000_111


@dataclass
class SentMessage:
    """رسالة مسجّلة (أُرسلت أو عُدِّلت) مع نصها وأزرارها."""

    kind: str                       # "send" أو "edit"
    chat_id: int | None
    text: str
    markup: InlineKeyboardMarkup | None
    kwargs: dict[str, Any] = field(default_factory=dict)

    @property
    def buttons(self) -> list[str]:
        """كل `callback_data` الموجودة في اللوحة المرافقة."""
        if self.markup is None:
            return []
        return [
            button.callback_data
            for row in self.markup.inline_keyboard
            for button in row
            if button.callback_data
        ]

    @property
    def labels(self) -> list[str]:
        """نصوص الأزرار كما يراها المستخدم."""
        if self.markup is None:
            return []
        return [button.text for row in self.markup.inline_keyboard for button in row]


class FakeMessage:
    """ردّ مبسّط يحاكي `Message` المُعاد من تيليجرام بعد الإرسال."""

    def __init__(self, message_id: int, chat_id: int, text: str) -> None:
        """تهيئة الرسالة المزيّفة بالحد الأدنى من الحقول المستخدمة."""
        self.message_id = message_id
        self.chat_id = chat_id
        self.text = text


class FakeBot:
    """
    بوت مزيّف يسجّل كل نداء بدل الاتصال بتيليجرام.

    يدعم فقط ما تستخدمه الواجهة فعلاً: الإرسال، التحرير، الرد على الأزرار،
    وإرسال الصور — وأي نداء آخر يرفع `AttributeError` واضحاً بدل الصمت.
    """

    def __init__(self) -> None:
        """تهيئة البوت المزيّف بسجلات فارغة."""
        self.sent: list[SentMessage] = []
        self.answers: list[dict[str, Any]] = []
        self.id = BOT_ID
        self.username = "fake_bot"
        self._message_ids = itertools.count(1)

    # ------------------------------ الإرسال ------------------------------ #

    async def send_message(
        self, chat_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None, **kwargs: Any
    ) -> FakeMessage:
        """تسجيل رسالة جديدة وإرجاع كائن يشبه رسالة تيليجرام."""
        self.sent.append(SentMessage("send", chat_id, text, reply_markup, kwargs))
        return FakeMessage(next(self._message_ids), chat_id, text)

    async def edit_message_text(
        self,
        text: str,
        chat_id: int | None = None,
        message_id: int | None = None,
        reply_markup: InlineKeyboardMarkup | None = None,
        **kwargs: Any,
    ) -> FakeMessage:
        """تسجيل تحرير رسالة قائمة (هذا هو المسار الطبيعي للتنقل بين الشاشات)."""
        self.sent.append(SentMessage("edit", chat_id, text, reply_markup, kwargs))
        return FakeMessage(message_id or 0, chat_id or 0, text)

    async def send_photo(self, chat_id: int, photo: Any, caption: str = "", **kwargs: Any) -> FakeMessage:
        """تسجيل إرسال صورة (يُستخدم في إشعارات الإثباتات لاحقاً)."""
        self.sent.append(SentMessage("photo", chat_id, caption, kwargs.get("reply_markup"), kwargs))
        return FakeMessage(next(self._message_ids), chat_id, caption)

    async def send_document(
        self, chat_id: int, document: Any, caption: str = "", **kwargs: Any
    ) -> FakeMessage:
        """تسجيل إرسال مستند (إثبات دفع مرفوع كملف في لوحة الأدمن)."""
        self.sent.append(
            SentMessage("document", chat_id, caption, kwargs.get("reply_markup"), kwargs)
        )
        return FakeMessage(next(self._message_ids), chat_id, caption)

    async def answer_callback_query(
        self, callback_query_id: str, text: str | None = None, show_alert: bool = False, **kwargs: Any
    ) -> bool:
        """تسجيل الرد على ضغطة زر (إزالة مؤشر الانتظار)."""
        self.answers.append({"id": callback_query_id, "text": text, "alert": show_alert})
        return True

    # ------------------------------ مساعدات ------------------------------ #

    @property
    def last(self) -> SentMessage:
        """آخر رسالة أُرسلت أو عُدِّلت."""
        if not self.sent:
            raise AssertionError("لم تُرسل أي رسالة بعد")
        return self.sent[-1]

    @property
    def texts(self) -> list[str]:
        """نصوص كل الرسائل المسجَّلة."""
        return [message.text for message in self.sent]

    def clear(self) -> None:
        """تفريغ السجلات بين خطوات الاختبار."""
        self.sent.clear()
        self.answers.clear()


class FakeApplication:
    """تطبيق مزيّف يحمل `bot_data` فقط (ما تحتاجه المعالجات)."""

    def __init__(self, bot: FakeBot, services: Any) -> None:
        """تهيئة التطبيق المزيّف بحاوية الخدمات."""
        self.bot = bot
        self.bot_data: dict[str, Any] = {"services": services}


class FakeContext:
    """سياق مزيّف يحاكي `ContextTypes.DEFAULT_TYPE` بالقدر الذي تستخدمه الواجهة."""

    def __init__(self, bot: FakeBot, services: Any) -> None:
        """تهيئة السياق ببوت وخدمات وذاكرة مستخدم فارغة."""
        self.bot = bot
        self.application = FakeApplication(bot, services)
        self.bot_data = self.application.bot_data
        self.user_data: dict[str, Any] = {}
        self.chat_data: dict[str, Any] = {}
        self.error: BaseException | None = None


def make_message_update(
    bot: FakeBot, *, text: str, user_id: int, chat_id: int | None = None, photo: bool = False
) -> Update:
    """
    بناء تحديث رسالة نصية حقيقي (أو صورة عند `photo=True`).

    المدخلات:
        text    : نص الرسالة (أو التعليق مع الصورة).
        user_id : معرف المستخدم في تيليجرام.
    """
    chat = chat_id if chat_id is not None else user_id
    message: dict[str, Any] = {
        "message_id": next(bot._message_ids),
        "date": int(time.time()),
        "chat": {"id": chat, "type": "private"},
        "from": {"id": user_id, "is_bot": False, "first_name": "Tester"},
    }
    if photo:
        message["photo"] = [
            {"file_id": "photo-file-id", "file_unique_id": "uniq", "width": 90, "height": 90}
        ]
        if text:
            message["caption"] = text
    else:
        message["text"] = text
        if text.startswith("/"):
            # تيليجرام يرفق كيان bot_command مع الأوامر — بدونه لا يلتقطها CommandHandler
            command = text.split()[0]
            message["entities"] = [
                {"type": "bot_command", "offset": 0, "length": len(command)}
            ]
    payload = {"update_id": next(_update_ids), "message": message}
    return Update.de_json(payload, bot)


def make_callback_update(
    bot: FakeBot, *, data: str, user_id: int, chat_id: int | None = None, message_id: int = 555
) -> Update:
    """بناء تحديث ضغطة زر حقيقي يحمل `callback_data` المطلوب."""
    chat = chat_id if chat_id is not None else user_id
    payload = {
        "update_id": next(_update_ids),
        "callback_query": {
            "id": f"cb-{next(_update_ids)}",
            "chat_instance": "test-instance",
            "data": data,
            "from": {"id": user_id, "is_bot": False, "first_name": "Tester"},
            "message": {
                "message_id": message_id,
                "date": int(time.time()),
                "chat": {"id": chat, "type": "private"},
                "from": {"id": BOT_ID, "is_bot": True, "first_name": "Bot", "username": "fake_bot"},
                "text": "شاشة سابقة",
            },
        },
    }
    return Update.de_json(payload, bot)
```

### `tests/integration/test_no_dead_buttons.py`

```python
"""
اختبار القاعدة الملزِمة: **لا زر بلا وظيفة**.

الطريقة:
    1. نستدعي كل باني لوحة أزرار في `keyboards/` ببيانات تجريبية.
    2. نجمع كل قيم `callback_data` الناتجة.
    3. نتأكد أن كل قيمة يلتقطها معالج مسجَّل فعلاً في `handlers/registry.py`
       (مع استبعاد المعالج الاحتياطي الشامل، وإلا لصار الاختبار بلا معنى).

كما نتحقق من العكس: كل معالج مسجَّل له نمط مفهوم وبإصدار `callback` الحالي.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest
from telegram import InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, ConversationHandler

from core.permissions import Permission
from handlers.registry import build_handlers
from keyboards import admin_kb, common_kb, user_kb
from keyboards.callback_data import CALLBACK_VERSION, unpack


def _fake_category(index: int = 1) -> SimpleNamespace:
    """تصنيف تجريبي بالحقول التي تستخدمها اللوحات فقط."""
    return SimpleNamespace(
        id=index, name_ar=f"تصنيف {index}", emoji="📱", title=f"📱 تصنيف {index}"
    )


def _fake_service(index: int = 1) -> SimpleNamespace:
    """خدمة تجريبية."""
    return SimpleNamespace(
        id=index,
        name=f"خدمة {index}",
        description="وصف",
        price_per_1000_units=10_000,
        min_quantity=100,
        max_quantity=1000,
        avg_time_text="ساعة",
        link_pattern=None,
        category_id=1,
    )


def _fake_order(index: int = 1, status: str = "pending") -> SimpleNamespace:
    """طلب تجريبي."""
    return SimpleNamespace(
        id=index,
        public_code=f"ORD-{index}",
        status=status,
        cost_units=10_000,
        quantity=1000,
        delivered_quantity=0,
        remains=1000,
        refund_amount_units=0,
        last_error=None,
        service_name_snapshot="خدمة",
        link="https://example.com/u",
        created_at="2026-01-01T10:00:00+00:00",
    )


def _fake_payment(index: int = 1, status: str = "pending") -> SimpleNamespace:
    """طلب شحن تجريبي."""
    return SimpleNamespace(
        id=index, amount_units=50_000, status=status, created_at="2026-01-01T10:00:00+00:00"
    )


def _fake_method(index: int = 1) -> SimpleNamespace:
    """طريقة دفع تجريبية."""
    return SimpleNamespace(
        id=index,
        name_ar=f"طريقة {index}",
        instructions_ar="حوّل ثم أرسل",
        account_details="123456",
        requires_proof=True,
    )


def _fake_ticket(index: int = 1, status: str = "open") -> SimpleNamespace:
    """تذكرة دعم تجريبية."""
    return SimpleNamespace(
        id=index,
        subject="مشكلة",
        status=status,
        category="other",
        last_message_at="2026-01-01T10:00:00+00:00",
        updated_at="2026-01-01T10:00:00+00:00",
        is_open=status == "open",
    )


def _fake_user(index: int = 1, *, banned: bool = False, role: str = "user") -> SimpleNamespace:
    """مستخدم تجريبي بالحقول التي تستخدمها لوحات الأدمن."""
    return SimpleNamespace(
        id=index,
        telegram_id=100_000 + index,
        username=f"user{index}",
        display_name=f"مستخدم {index}",
        is_banned=banned,
        role=role,
        balance_units=25_000,
    )


def _fake_admin_payment(index: int = 1, *, with_proof: bool = True) -> SimpleNamespace:
    """طلب شحن تجريبي كما تراه لوحة الأدمن."""
    return SimpleNamespace(
        id=index,
        user_id=index,
        amount_units=50_000,
        status="pending",
        proof_file_id="FILE123" if with_proof else None,
        proof_file_type="photo",
        created_at="2026-01-01T10:00:00+00:00",
    )


def _fake_admin_order(index: int = 1, status: str = "submit_uncertain") -> SimpleNamespace:
    """طلب تجريبي كما تراه لوحة الأدمن (بحقول المزود والقفل)."""
    order = _fake_order(index, status=status)
    order.user_id = index
    order.provider_order_id = "PRV-9" if status != "pending" else None
    order.provider_id = 1
    return order


def _fake_admin_service(index: int = 1, *, active: bool = True, archived: bool = False):
    """خدمة تجريبية بحقول الحالة التي تحتاجها بطاقة الأدمن."""
    service = _fake_service(index)
    service.is_active = active
    service.is_archived = archived
    service.provider_id = 1
    service.provider_service_id = "55"
    service.provider_price_per_1000_units = 6_000
    return service


def _fake_setting(key: str = "order_check_interval_seconds", *, editable: bool = True):
    """مفتاح إعداد تجريبي."""
    return SimpleNamespace(
        key=key,
        value="120",
        value_type="int",
        group_code="orders",
        name_ar="فاصل الفحص",
        description_ar="بالثواني",
        is_editable=editable,
    )


def admin_markups() -> list[tuple[str, InlineKeyboardMarkup]]:
    """
    كل لوحات لوحة التحكم ببيانات تجريبية.

    تُبنى بصلاحيات كاملة عمداً: هكذا يظهر **كل** زر ممكن في اللوحة ويخضع
    لفحص «لا زر بلا معالج» — بما في ذلك الأزرار التي لا يراها إلا الأدمن الأعلى.
    """
    perms = {str(permission) for permission in Permission}
    users = [_fake_user(1), _fake_user(2, banned=True)]
    orders = [_fake_admin_order(1), _fake_admin_order(2, status="in_progress")]
    payments = [_fake_admin_payment(1), _fake_admin_payment(2, with_proof=False)]
    tickets = [_fake_ticket(1), _fake_ticket(2, status="closed")]
    services = [_fake_admin_service(1), _fake_admin_service(2, active=False)]
    categories = [_fake_category(1), _fake_category(2)]

    for ticket in tickets:
        ticket.user_id = ticket.id

    return [
        ("admin_menu_kb", admin_kb.admin_menu_kb(perms, pending_payments=3, open_tickets=2)),
        ("admin_menu_kb_minimal", admin_kb.admin_menu_kb({Permission.ADMIN_ACCESS})),
        ("health_kb", admin_kb.health_kb()),
        ("back_panel_kb", admin_kb.back_panel_kb()),
        ("admin_cancel_only_kb", admin_kb.cancel_only_kb()),
        ("admin_confirm_cancel_kb", admin_kb.confirm_cancel_kb()),
        ("admin_skip_cancel_kb", admin_kb.skip_cancel_kb()),
        ("users_home_kb", admin_kb.users_home_kb(perms)),
        ("user_results_kb", admin_kb.user_results_kb(users)),
        ("user_card_kb", admin_kb.user_card_kb(_fake_user(1), perms)),
        ("user_card_kb_banned", admin_kb.user_card_kb(_fake_user(2, banned=True), perms)),
        ("user_role_kb", admin_kb.user_role_kb(_fake_user(1))),
        ("user_role_confirm_kb", admin_kb.user_role_confirm_kb(1, "support")),
        ("user_orders_nav_kb", admin_kb.user_list_nav_kb("orders", 1, page=1, total_pages=3)),
        ("user_tx_nav_kb", admin_kb.user_list_nav_kb("tx", 1, page=2, total_pages=3)),
        (
            "payments_list_kb",
            admin_kb.payments_list_kb(payments, page=1, total_pages=2, symbol="ر.ي"),
        ),
        (
            "payment_card_kb",
            admin_kb.payment_card_kb(_fake_admin_payment(1), perms, is_pending=True),
        ),
        (
            "payment_card_kb_done",
            admin_kb.payment_card_kb(
                _fake_admin_payment(2, with_proof=False), perms, is_pending=False
            ),
        ),
        ("payment_approve_kb", admin_kb.payment_approve_kb()),
        (
            "admin_orders_kb",
            admin_kb.admin_orders_kb(
                orders, filter_code="att", page=1, total_pages=2, symbol="ر.ي"
            ),
        ),
        (
            "admin_order_card_kb",
            admin_kb.admin_order_card_kb(
                _fake_admin_order(1), perms, filter_code="att", page=1
            ),
        ),
        (
            "admin_order_card_kb_final",
            admin_kb.admin_order_card_kb(
                _fake_admin_order(3, status="completed"), perms, filter_code="all", page=1
            ),
        ),
        ("order_override_kb", admin_kb.order_override_kb(_fake_admin_order(1))),
        (
            "admin_tickets_kb",
            admin_kb.admin_tickets_kb(tickets, filter_code="open", page=1, total_pages=2),
        ),
        ("admin_ticket_card_kb", admin_kb.admin_ticket_card_kb(tickets[0], perms)),
        (
            "admin_ticket_card_kb_closed",
            admin_kb.admin_ticket_card_kb(tickets[1], perms, filter_code="closed"),
        ),
        ("catalog_home_kb", admin_kb.catalog_home_kb(categories, perms)),
        (
            "catalog_services_kb",
            admin_kb.catalog_services_kb(
                services, category_id=1, page=1, total_pages=2, symbol="ر.ي"
            ),
        ),
        ("service_card_kb", admin_kb.service_card_kb(_fake_admin_service(1), perms)),
        (
            "service_card_kb_archived",
            admin_kb.service_card_kb(_fake_admin_service(2, archived=True), perms),
        ),
        (
            "settings_home_kb",
            admin_kb.settings_home_kb(["general", "orders"], perms, maintenance_on=False),
        ),
        (
            "settings_group_kb",
            admin_kb.settings_group_kb(
                [_fake_setting(), _fake_setting("locked_key", editable=False)],
                group="orders",
                page=1,
                total_pages=2,
                perms=perms,
            ),
        ),
        ("logs_home_kb", admin_kb.logs_home_kb()),
        ("logs_audit_kb", admin_kb.logs_page_kb("audit", page=2, total_pages=5)),
        ("logs_errors_kb", admin_kb.logs_page_kb("errors", page=1, total_pages=2)),
    ]


def all_markups() -> list[tuple[str, InlineKeyboardMarkup]]:
    """
    بناء كل لوحات الواجهة مرة واحدة.

    أي لوحة جديدة تُضاف في `keyboards/user_kb.py` يجب أن تُضاف هنا — وهذا مقصود:
    اللوحة التي لا تُختبر لا تُضمن أزرارها.
    """
    categories = [_fake_category(1), _fake_category(2)]
    services = [_fake_service(1), _fake_service(2)]
    orders = [_fake_order(1), _fake_order(2, status="completed")]
    tickets = [_fake_ticket(1), _fake_ticket(2, status="closed")]
    payments = [_fake_payment(1), _fake_payment(2, status="approved")]

    return [
        ("main_menu_kb", user_kb.main_menu_kb()),
        ("main_menu_kb_admin", user_kb.main_menu_kb(is_admin=True)),
        ("categories_kb", user_kb.categories_kb(categories)),
        ("categories_kb_empty", user_kb.categories_kb([])),
        (
            "services_kb",
            user_kb.services_kb(services, category_id=1, page=2, total_pages=3, symbol="ر.ي"),
        ),
        ("service_card_kb", user_kb.service_card_kb(_fake_service(1), category_id=1, page=1)),
        ("insufficient_balance_kb", user_kb.insufficient_balance_kb(1, 1)),
        (
            "orders_kb",
            user_kb.orders_kb(orders, filter_code="all", page=1, total_pages=2, symbol="ر.ي"),
        ),
        (
            "order_card_kb_cancelable",
            user_kb.order_card_kb(_fake_order(1), can_cancel=True, filter_code="all", page=1),
        ),
        (
            "order_card_kb_plain",
            user_kb.order_card_kb(
                _fake_order(2, status="completed"), can_cancel=False, filter_code="done", page=1
            ),
        ),
        ("order_cancel_confirm_kb", user_kb.order_cancel_confirm_kb(1)),
        ("wallet_kb", user_kb.wallet_kb()),
        ("history_kb", user_kb.history_kb(page=2, total_pages=4)),
        ("deposit_methods_kb", user_kb.deposit_methods_kb([_fake_method(1), _fake_method(2)])),
        ("deposits_kb", user_kb.deposits_kb(payments, page=1, total_pages=2)),
        ("support_kb", user_kb.support_kb()),
        ("ticket_categories_kb", user_kb.ticket_categories_kb()),
        ("tickets_kb", user_kb.tickets_kb(tickets, page=1, total_pages=1)),
        ("ticket_card_kb_open", user_kb.ticket_card_kb(_fake_ticket(1))),
        ("ticket_card_kb_closed", user_kb.ticket_card_kb(_fake_ticket(2, status="closed"))),
        ("account_kb", user_kb.account_kb(3)),
        ("notifications_kb", user_kb.notifications_kb(page=1, total_pages=2, unread=5)),
        ("info_kb", user_kb.info_kb()),
        ("notifications_only_back_kb", user_kb.notifications_only_back_kb()),
        ("cancel_markup", common_kb.cancel_markup()),
        ("confirm_cancel_markup", common_kb.confirm_cancel_markup()),
        ("skip_cancel_markup", common_kb.skip_cancel_markup()),
        *admin_markups(),
    ]


def registered_patterns() -> list[re.Pattern]:
    """
    كل أنماط الأزرار التي يلتقطها البوت فعلاً.

    تشمل معالجات الشاشات ومداخل المحادثات وحالاتها ومساراتها الاحتياطية،
    وتستبعد المعالج الشامل (الذي بلا نمط) لأنه شبكة أمان لا دليل تغطية.
    """
    patterns: list[re.Pattern] = []

    def collect(handler: object) -> None:
        """جمع النمط من معالج واحد (أو من محادثة كاملة)."""
        if isinstance(handler, CallbackQueryHandler):
            if handler.pattern is not None:
                patterns.append(handler.pattern)
        elif isinstance(handler, ConversationHandler):
            for entry in handler.entry_points:
                collect(entry)
            for state_handlers in handler.states.values():
                for state_handler in state_handlers:
                    collect(state_handler)
            for fallback in handler.fallbacks:
                collect(fallback)

    for _group, handler in build_handlers():
        collect(handler)
    return patterns


ALL_BUTTONS = sorted(
    {
        data
        for _name, markup in all_markups()
        for row in markup.inline_keyboard
        for button in row
        if (data := button.callback_data)
    }
)


def test_keyboards_produce_buttons() -> None:
    """تأكيد أن اللوحات فعلاً تنتج أزراراً (حماية من اختبار فارغ يمر زوراً).."""
    assert len(ALL_BUTTONS) >= 25


@pytest.mark.parametrize("callback_data", ALL_BUTTONS)
def test_every_button_has_handler(callback_data: str) -> None:
    """كل زر في الواجهة يلتقطه معالج مسجَّل — لا أزرار ميتة."""
    patterns = registered_patterns()
    matched = [pattern.pattern for pattern in patterns if pattern.search(callback_data)]
    assert matched, f"الزر {callback_data!r} بلا معالج مسجَّل في handlers/registry.py"


@pytest.mark.parametrize("callback_data", ALL_BUTTONS)
def test_every_button_is_well_formed(callback_data: str) -> None:
    """كل زر مُرمَّز بالصيغة المعتمدة وبإصدار callback الحالي."""
    data = unpack(callback_data)
    assert data.namespace
    assert data.action
    assert data.version == CALLBACK_VERSION
    assert len(callback_data.encode("utf-8")) <= 64   # حد تيليجرام الصارم


def test_no_button_matches_more_than_one_screen_handler() -> None:
    """
    لا يلتقط زرَّاً واحداً أكثر من معالج شاشة.

    التقاط زر بمعالجين يعني سلوكاً يعتمد على ترتيب التسجيل — مصدر أعطال صامتة.
    المحادثات مستثناة لأن حالاتها معزولة زمنياً (لا تعمل إلا داخل المحادثة).
    """
    from handlers.registry import screen_handlers

    patterns = [handler.pattern for handler in screen_handlers() if handler.pattern]
    for callback_data in ALL_BUTTONS:
        matches = [pattern.pattern for pattern in patterns if pattern.search(callback_data)]
        assert len(matches) <= 1, f"الزر {callback_data!r} يلتقطه أكثر من معالج: {matches}"
```

### `tests/integration/test_admin_access.py`

```python
"""
اختبارات بوابة لوحة التحكم: من يدخل؟ وماذا يرى؟ وماذا يُسجَّل عند الرفض؟

هذه الاختبارات هي الدليل العملي على أن قاعدة «الصلاحية تُفحص على الـcallback
نفسه» مطبَّقة فعلاً، لا على مستوى إخفاء الأزرار فقط.
"""

from __future__ import annotations

import pytest

from core.permissions import Permission
from database.models import User
from database.repositories import Repositories
from handlers.admin import dashboard, logs, settings, users
from handlers.common import navigation
from keyboards.callback_data import pack
from services import ServiceContainer
from tests.integration.test_user_interface import (  # إعادة استخدام أدوات الواجهة نفسها
    bot,  # noqa: F401
    context,  # noqa: F401
    load_user,
    press,
)
from tests.telegram_fakes import FakeBot, FakeContext

pytestmark = pytest.mark.asyncio


async def test_normal_user_cannot_open_panel(
    bot: FakeBot, context: FakeContext, user: User, repos: Repositories
) -> None:
    """مستخدم عادي يضغط زر لوحة التحكم ⇐ رفض واضح + تسجيل أمني."""
    await load_user(bot, context, user)
    await press(bot, context, dashboard.panel_screen, pack("adm", "home"), user.telegram_id)

    assert bot.answers[-1]["alert"] is True
    assert "صلاحية" in (bot.answers[-1]["text"] or "")
    denied = await repos.audit.list_recent(limit=5)
    assert any(entry.action == "security.permission_denied" for entry in denied), (
        "محاولة الوصول المرفوضة لم تُسجَّل في سجل التدقيق"
    )


async def test_admin_sees_panel_with_sections(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """الأدمن يرى لوحة التحكم بأقسامها وبأرقام حقيقية."""
    await load_user(bot, context, admin)
    await press(bot, context, dashboard.panel_screen, pack("adm", "home"), admin.telegram_id)

    assert bot.last.kind == "edit"
    assert "لوحة التحكم" in bot.last.text
    assert "au:home:v1" in bot.last.buttons
    assert "ap:list:1:v1" in bot.last.buttons
    assert "ao:list:att:1:v1" in bot.last.buttons


async def test_panel_hides_sections_without_permission(
    bot: FakeBot, context: FakeContext, db, repos: Repositories, services: ServiceContainer
) -> None:
    """أدمن دعم فني يرى ما يخصّه فقط — لا إعدادات ولا سجلات."""
    async with db.transaction() as tx:
        support_admin = await repos.users.create(
            tx, telegram_id=555_111, username="supporter", first_name="Supp", role="support"
        )
    await load_user(bot, context, support_admin)
    await press(
        bot, context, dashboard.panel_screen, pack("adm", "home"), support_admin.telegram_id
    )

    buttons = bot.last.buttons
    assert "at:list:open:1:v1" in buttons, "أدمن الدعم لا يرى قسم التذاكر"
    assert "as:home:v1" not in buttons, "ظهر قسم الإعدادات لمن لا يملك صلاحيته"
    assert "al:home:v1" not in buttons, "ظهر قسم السجلات لمن لا يملك صلاحيته"


async def test_section_blocked_even_if_button_pressed_directly(
    bot: FakeBot, context: FakeContext, db, repos: Repositories
) -> None:
    """الضغط المباشر على زر قسم محجوب يُرفض — إخفاء الزر ليس هو الحماية."""
    async with db.transaction() as tx:
        support_admin = await repos.users.create(
            tx, telegram_id=555_112, username="supporter2", first_name="Supp", role="support"
        )
    await load_user(bot, context, support_admin)
    await press(
        bot,
        context,
        settings.settings_home_screen,
        pack("as", "home"),
        support_admin.telegram_id,
    )
    assert bot.answers[-1]["alert"] is True
    assert not bot.sent, "عُرضت شاشة الإعدادات لمن لا يملك صلاحيتها"


async def test_permission_revoked_mid_session_blocks_action(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    super_admin: User,
    services: ServiceContainer,
) -> None:
    """سحب الصلاحية أثناء الجلسة يُغلق الزر فوراً حتى لو كان معروضاً."""
    await load_user(bot, context, admin)
    await press(bot, context, logs.audit_screen, pack("al", "audit", 1), admin.telegram_id)
    assert bot.last.kind == "edit"

    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.LOGS_VIEW, allow=False
    )
    bot.clear()
    await press(bot, context, logs.audit_screen, pack("al", "audit", 1), admin.telegram_id)
    assert bot.answers[-1]["alert"] is True
    assert not bot.sent, "شاشة السجلات ظهرت بعد سحب الصلاحية"


async def test_main_menu_shows_panel_button_for_admin_only(
    bot: FakeBot, context: FakeContext, admin: User, user: User
) -> None:
    """زر «🛠 لوحة التحكم» يظهر في القائمة الرئيسية للأدمن فقط."""
    await load_user(bot, context, admin)
    await press(bot, context, navigation.home_callback, pack("nav", "home"), admin.telegram_id)
    assert "adm:home:v1" in bot.last.buttons

    other = FakeContext(bot, context.bot_data["services"])
    bot.clear()
    await load_user(bot, other, user)
    await press(bot, other, navigation.home_callback, pack("nav", "home"), user.telegram_id)
    assert "adm:home:v1" not in bot.last.buttons


async def test_admin_command_opens_panel(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """الأمر /admin يفتح اللوحة لمن يملك صلاحية الدخول."""
    await load_user(bot, context, admin)
    from tests.integration.test_user_interface import write

    await write(bot, context, dashboard.admin_command, "/admin", admin.telegram_id)
    assert "لوحة التحكم" in bot.last.text
    assert bot.last.buttons


async def test_health_screen_requires_stats_permission(
    bot: FakeBot, context: FakeContext, admin: User, super_admin: User, services: ServiceContainer
) -> None:
    """شاشة صحة النظام تحتاج `stats.view` تحديداً."""
    await load_user(bot, context, admin)
    await press(bot, context, dashboard.health_screen, pack("adm", "health"), admin.telegram_id)
    assert "صحة النظام" in bot.last.text

    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.STATS_VIEW, allow=False
    )
    bot.clear()
    await press(bot, context, dashboard.health_screen, pack("adm", "health"), admin.telegram_id)
    assert bot.answers[-1]["alert"] is True
    assert not bot.sent


async def test_panel_without_stats_still_opens(
    bot: FakeBot, context: FakeContext, admin: User, super_admin: User, services: ServiceContainer
) -> None:
    """من لا يملك `stats.view` يدخل اللوحة بلا أرقام بدل أن يُمنع منها."""
    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.STATS_VIEW, allow=False
    )
    await load_user(bot, context, admin)
    await press(bot, context, dashboard.panel_screen, pack("adm", "home"), admin.telegram_id)

    assert "لوحة التحكم" in bot.last.text
    assert "المستخدمون:" not in bot.last.text
    assert bot.last.buttons, "اللوحة بلا أزرار"


async def test_users_screen_shows_real_counters(
    bot: FakeBot, context: FakeContext, admin: User, user: User
) -> None:
    """شاشة المستخدمين تعرض عدّادات حقيقية من قاعدة البيانات."""
    await load_user(bot, context, admin)
    await press(bot, context, users.users_home_screen, pack("au", "home"), admin.telegram_id)
    assert "الإجمالي: 2" in bot.last.text
    assert "au:search:v1" in bot.last.buttons
```

### `tests/integration/test_admin_users.py`

```python
"""
اختبارات قسم المستخدمين في لوحة التحكم.

تغطي المسارات التي تمسّ المال والصلاحيات: بحث، بطاقة، إضافة/خصم رصيد
(بتأكيد ثانٍ ومنع تكرار)، حظر/فك حظر، ملاحظة إدارية، وتغيير الدور.
كل اختبار يتحقق من الأثر في قاعدة البيانات لا من النص فقط.
"""

from __future__ import annotations

import pytest
from telegram.ext import ConversationHandler

from core.exceptions import DuplicateOperationError
from core.permissions import Permission
from database.models import User
from database.repositories import Repositories
from handlers.admin import users
from keyboards.callback_data import pack
from services import ServiceContainer
from tests.integration.test_user_interface import (
    bot,  # noqa: F401
    context,  # noqa: F401
    load_user,
    press,
    write,
)
from tests.telegram_fakes import FakeBot, FakeContext

pytestmark = pytest.mark.asyncio


async def _open_card(bot: FakeBot, context: FakeContext, admin: User, target: User) -> None:
    """فتح بطاقة مستخدم من داخل اللوحة (الخطوة التي تسبق أي إجراء عليه)."""
    await press(
        bot, context, users.user_card_screen, pack("au", "view", target.id), admin.telegram_id
    )


# ======================================================================== #
#                              البحث والبطاقة                              #
# ======================================================================== #


async def test_search_by_telegram_id_shows_result(
    bot: FakeBot, context: FakeContext, admin: User, user: User
) -> None:
    """البحث برقم تيليجرام يعرض المستخدم كزر يفتح بطاقته."""
    await load_user(bot, context, admin)
    state = await press(bot, context, users.start_search, pack("au", "search"), admin.telegram_id)
    assert state == users.ASK_QUERY

    state = await write(
        bot, context, users.receive_query, str(user.telegram_id), admin.telegram_id
    )
    assert state == ConversationHandler.END
    assert f"au:view:{user.id}:v1" in bot.last.buttons


async def test_search_without_results_keeps_conversation_open(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """بحث بلا نتائج لا ينهي المحادثة — يطلب نصاً آخر بدل إرجاع المستخدم للبداية."""
    await load_user(bot, context, admin)
    await press(bot, context, users.start_search, pack("au", "search"), admin.telegram_id)
    state = await write(bot, context, users.receive_query, "لا_أحد_بهذا_الاسم", admin.telegram_id)

    assert state == users.ASK_QUERY
    assert "لا نتائج" in bot.last.text or "نتائج" in bot.last.text


async def test_user_card_shows_balance_and_actions(
    bot: FakeBot, context: FakeContext, admin: User, user: User
) -> None:
    """بطاقة المستخدم تعرض رصيده الحقيقي وأزرار الإجراءات المسموح بها."""
    await load_user(bot, context, admin)
    await _open_card(bot, context, admin, user)

    assert str(user.telegram_id) in bot.last.text
    assert f"au:credit:{user.id}:v1" in bot.last.buttons
    assert f"au:ban:{user.id}:v1" in bot.last.buttons


# ======================================================================== #
#                               تعديل الرصيد                               #
# ======================================================================== #


async def test_credit_balance_full_flow(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """إضافة رصيد: مبلغ ⇐ سبب ⇐ تأكيد ⇐ رصيد محدَّث + حركة + تدقيق + إشعار."""
    await load_user(bot, context, admin)
    state = await press(
        bot, context, users.start_credit, pack("au", "credit", user.id), admin.telegram_id
    )
    assert state == users.ASK_AMOUNT

    state = await write(bot, context, users.receive_amount, "5", admin.telegram_id)
    assert state == users.ASK_REASON

    state = await write(
        bot, context, users.receive_balance_reason, "تعويض عن طلب فاشل", admin.telegram_id
    )
    assert state == users.CONFIRM_BALANCE
    assert "flow:confirm:v1" in bot.last.buttons, "لا يوجد تأكيد ثانٍ قبل تعديل الرصيد"

    state = await press(
        bot, context, users.confirm_balance, pack("flow", "confirm"), admin.telegram_id
    )
    assert state == ConversationHandler.END

    refreshed = await services.users.get(user.id)
    assert refreshed.balance_units == 50_000

    transactions = await repos.transactions.list_by_user(user.id, limit=5)
    assert transactions and transactions[0].amount_units == 50_000

    audit = await repos.audit.list_recent(limit=10)
    assert any("balance" in entry.action for entry in audit), "تعديل الرصيد بلا سجل تدقيق"

    queued = await repos.notifications.list_for_user(user.id, limit=10)
    assert queued, "المستخدم لم يُشعَر بتعديل رصيده"
    assert "رصيد" in queued[0].title or "رصيد" in queued[0].message


async def test_debit_balance_reduces_and_blocks_overdraft(
    bot: FakeBot, context: FakeContext, super_admin: User, user: User, services: ServiceContainer
) -> None:
    """الخصم ينقص الرصيد، ولا يسمح بتجاوز الرصيد المتاح."""
    await services.wallet.adjust_balance(
        target=user, amount_units=30_000, admin=super_admin, reason="شحن اختبار", credit=True
    )
    await load_user(bot, context, super_admin)

    await press(
        bot, context, users.start_debit, pack("au", "debit", user.id), super_admin.telegram_id
    )
    await write(bot, context, users.receive_amount, "1", super_admin.telegram_id)
    await write(bot, context, users.receive_balance_reason, "تصحيح خطأ شحن", super_admin.telegram_id)
    await press(
        bot, context, users.confirm_balance, pack("flow", "confirm"), super_admin.telegram_id
    )

    refreshed = await services.users.get(user.id)
    assert refreshed.balance_units == 20_000

    # محاولة خصم أكبر من الرصيد
    await press(
        bot, context, users.start_debit, pack("au", "debit", user.id), super_admin.telegram_id
    )
    await write(bot, context, users.receive_amount, "999", super_admin.telegram_id)
    await write(bot, context, users.receive_balance_reason, "خصم مبالغ فيه", super_admin.telegram_id)
    await press(
        bot, context, users.confirm_balance, pack("flow", "confirm"), super_admin.telegram_id
    )
    assert "رصيد" in bot.last.text, f"رسالة فشل الخصم غير واضحة: {bot.last.text}"

    unchanged = await services.users.get(user.id)
    assert unchanged.balance_units == 20_000, "تغيّر الرصيد رغم فشل العملية"


async def test_double_confirm_does_not_double_credit(
    bot: FakeBot, context: FakeContext, admin: User, user: User, services: ServiceContainer
) -> None:
    """ضغط «تأكيد» مرتين لا يضيف الرصيد مرتين (idempotency برمز العملية)."""
    await load_user(bot, context, admin)
    await press(bot, context, users.start_credit, pack("au", "credit", user.id), admin.telegram_id)
    await write(bot, context, users.receive_amount, "7", admin.telegram_id)
    await write(bot, context, users.receive_balance_reason, "هدية ترحيب", admin.telegram_id)

    token_before = context.user_data[users.ADMIN_FLOW_KEY]["token"]
    await press(bot, context, users.confirm_balance, pack("flow", "confirm"), admin.telegram_id)

    # إعادة الضغط بنفس الجلسة المنتهية: لا بيانات ⇒ رسالة انتهاء الجلسة لا عملية ثانية
    state = await press(
        bot, context, users.confirm_balance, pack("flow", "confirm"), admin.telegram_id
    )
    assert state == ConversationHandler.END

    refreshed = await services.users.get(user.id)
    assert refreshed.balance_units == 70_000, "تكرّر تعديل الرصيد عند الضغط مرتين"

    # وحتى إعادة استخدام نفس الرمز صراحةً تُرفض من الخدمة نفسها
    with pytest.raises(DuplicateOperationError):
        await services.wallet.adjust_balance(
            target=refreshed,
            amount_units=70_000,
            admin=admin,
            reason="هدية ترحيب",
            credit=True,
            token=token_before,
        )


async def test_credit_requires_permission(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    super_admin: User,
    user: User,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """أدمن بلا صلاحية إضافة رصيد يُمنع من بدء المحادثة أصلاً."""
    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.USERS_BALANCE_CREDIT, allow=False
    )
    await load_user(bot, context, admin)
    await press(bot, context, users.start_credit, pack("au", "credit", user.id), admin.telegram_id)

    assert bot.answers[-1]["alert"] is True
    refreshed = await services.users.get(user.id)
    assert refreshed.balance_units == 0


async def test_invalid_amount_is_rejected_with_message(
    bot: FakeBot, context: FakeContext, admin: User, user: User
) -> None:
    """مبلغ غير صالح يُقابَل برسالة واضحة ولا يكسر المحادثة."""
    await load_user(bot, context, admin)
    await press(bot, context, users.start_credit, pack("au", "credit", user.id), admin.telegram_id)

    # `@guarded` يحوّل خطأ التحقق إلى رسالة عربية بدل أن يُسقط المعالج
    await write(bot, context, users.receive_amount, "خمسة", admin.telegram_id)
    assert bot.last.text, "لم تُعرض أي رسالة عند إدخال مبلغ غير صالح"
    assert "مبلغ" in bot.last.text or "رقم" in bot.last.text


# ======================================================================== #
#                             الحظر وفك الحظر                              #
# ======================================================================== #


async def test_ban_then_unban_user(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """الحظر يحتاج سبباً وتأكيداً، وفك الحظر فوري — وكلاهما يُسجَّل."""
    await load_user(bot, context, admin)
    state = await press(
        bot, context, users.start_ban, pack("au", "ban", user.id), admin.telegram_id
    )
    assert state == users.ASK_BAN_REASON

    state = await write(bot, context, users.receive_ban_reason, "إساءة استخدام", admin.telegram_id)
    assert state == users.CONFIRM_BAN
    assert "flow:confirm:v1" in bot.last.buttons

    await press(bot, context, users.confirm_ban, pack("flow", "confirm"), admin.telegram_id)
    banned = await services.users.get(user.id)
    assert banned.is_banned
    assert banned.ban_reason == "إساءة استخدام"

    await press(bot, context, users.unban_user, pack("au", "unban", user.id), admin.telegram_id)
    freed = await services.users.get(user.id)
    assert not freed.is_banned

    audit = await repos.audit.list_recent(limit=20)
    actions = {entry.action for entry in audit}
    assert any("ban" in action for action in actions), "الحظر/فك الحظر بلا سجل تدقيق"


async def test_banned_user_cannot_use_bot(
    bot: FakeBot, context: FakeContext, admin: User, user: User, services: ServiceContainer
) -> None:
    """الحظر ليس شكلياً: المستخدم المحظور توقفه الطبقة الوسيطة."""
    from tests.integration.test_user_interface import run_middleware
    from tests.telegram_fakes import make_message_update

    await services.users.ban(admin, user.id, "اختبار المنع")
    update = make_message_update(bot, text="/start", user_id=user.telegram_id)
    allowed = await run_middleware(bot, context, update)
    assert allowed is False, "المستخدم المحظور ما زال يستطيع استخدام البوت"


# ======================================================================== #
#                           الملاحظة وتغيير الدور                          #
# ======================================================================== #


async def test_admin_note_is_saved(
    bot: FakeBot, context: FakeContext, admin: User, user: User, services: ServiceContainer
) -> None:
    """الملاحظة الإدارية تُحفظ وتظهر في البطاقة."""
    await load_user(bot, context, admin)
    await press(bot, context, users.start_note, pack("au", "note", user.id), admin.telegram_id)
    await write(bot, context, users.receive_note, "عميل مهم — تعامل بعناية", admin.telegram_id)

    refreshed = await services.users.get(user.id)
    assert refreshed.notes == "عميل مهم — تعامل بعناية"


async def test_role_change_needs_second_confirmation(
    bot: FakeBot, context: FakeContext, super_admin: User, user: User, services: ServiceContainer
) -> None:
    """تغيير الدور إجراء خطير: شاشة أدوار ⇒ شاشة تأكيد ⇒ تنفيذ."""
    await load_user(bot, context, super_admin)
    await press(
        bot, context, users.role_screen, pack("au", "role", user.id), super_admin.telegram_id
    )
    assert f"au:setrole:{user.id}:support:v1" in bot.last.buttons

    await press(
        bot,
        context,
        users.role_confirm_screen,
        pack("au", "setrole", user.id, "support"),
        super_admin.telegram_id,
    )
    assert f"au:roleok:{user.id}:support:v1" in bot.last.buttons, "لا شاشة تأكيد قبل تغيير الدور"

    still_user = await services.users.get(user.id)
    assert still_user.role == "user", "تغيّر الدور قبل التأكيد النهائي"

    await press(
        bot,
        context,
        users.role_apply,
        pack("au", "roleok", user.id, "support"),
        super_admin.telegram_id,
    )
    promoted = await services.users.get(user.id)
    assert promoted.role == "support"
    assert await services.auth.is_admin(promoted) is True


async def test_admin_cannot_assign_role_without_permission(
    bot: FakeBot, context: FakeContext, admin: User, user: User, services: ServiceContainer
) -> None:
    """الأدمن العادي لا يملك `users.role.change` ⇐ لا يستطيع ترقية أحد."""
    await load_user(bot, context, admin)
    await press(
        bot,
        context,
        users.role_apply,
        pack("au", "roleok", user.id, "admin"),
        admin.telegram_id,
    )
    assert bot.answers[-1]["alert"] is True
    unchanged = await services.users.get(user.id)
    assert unchanged.role == "user"


async def test_user_orders_and_transactions_screens(
    bot: FakeBot, context: FakeContext, admin: User, user: User
) -> None:
    """شاشتا طلبات المستخدم وحركاته تعملان حتى حين لا توجد بيانات."""
    await load_user(bot, context, admin)
    await press(
        bot, context, users.user_orders_screen, pack("au", "orders", user.id, 1), admin.telegram_id
    )
    assert bot.last.buttons, "شاشة طلبات المستخدم بلا أزرار رجوع"

    await press(
        bot,
        context,
        users.user_transactions_screen,
        pack("au", "tx", user.id, 1),
        admin.telegram_id,
    )
    assert bot.last.buttons
```

### `tests/integration/test_admin_payments.py`

```python
"""
اختبارات قسم المدفوعات في لوحة التحكم.

المسار الحسّاس هنا: اعتماد طلب شحن = إضافة رصيد حقيقي. لذلك نتحقق من
التأكيد الثاني، ومن تعديل المبلغ المعتمد، ومن استحالة الاعتماد مرتين،
ومن أن الرفض يحتاج سبباً ويصل للمستخدم.
"""

from __future__ import annotations

import pytest
from telegram.ext import ConversationHandler

from core.enums import PaymentStatus
from core.permissions import Permission
from database.models import Payment, User
from database.repositories import Repositories
from handlers.admin import payments
from keyboards.callback_data import pack
from services import ServiceContainer
from tests.integration.test_user_interface import (
    bot,  # noqa: F401
    context,  # noqa: F401
    load_user,
    press,
    write,
)
from tests.telegram_fakes import FakeBot, FakeContext

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def pending_payment(services: ServiceContainer, user: User, payment_method) -> Payment:
    """طلب شحن معلّق بمبلغ 5 (50000 نقطة) مع إثبات صورة."""
    return await services.payments.create_payment(
        user,
        method_id=payment_method.id,
        raw_amount="5",
        transaction_reference="TRX-77-A",
        proof_file_id="proof-file-1",
        proof_file_type="photo",
    )


async def test_pending_list_shows_payment(
    bot: FakeBot, context: FakeContext, admin: User, pending_payment: Payment
) -> None:
    """قائمة الطلبات المعلّقة تعرض الطلب كزر يفتح بطاقته."""
    await load_user(bot, context, admin)
    await press(bot, context, payments.payments_list_screen, pack("ap", "list", 1), admin.telegram_id)

    assert f"ap:view:{pending_payment.id}:v1" in bot.last.buttons
    assert "المعلّقة" in bot.last.text or "الشحن" in bot.last.text


async def test_payment_card_shows_proof_button(
    bot: FakeBot, context: FakeContext, admin: User, pending_payment: Payment
) -> None:
    """بطاقة الطلب تعرض أزرار الاعتماد والرفض وعرض الإثبات."""
    await load_user(bot, context, admin)
    await press(
        bot, context, payments.payment_card_screen, pack("ap", "view", pending_payment.id), admin.telegram_id
    )

    assert f"ap:ok:{pending_payment.id}:v1" in bot.last.buttons
    assert f"ap:no:{pending_payment.id}:v1" in bot.last.buttons
    assert f"ap:proof:{pending_payment.id}:v1" in bot.last.buttons


async def test_proof_screen_sends_photo(
    bot: FakeBot, context: FakeContext, admin: User, pending_payment: Payment
) -> None:
    """زر «عرض الإثبات» يرسل الصورة فعلاً لا رسالة نصية فارغة."""
    await load_user(bot, context, admin)
    await press(
        bot, context, payments.payment_proof_screen, pack("ap", "proof", pending_payment.id), admin.telegram_id
    )
    assert bot.last.kind == "photo"


async def test_approve_credits_balance_after_confirmation(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    pending_payment: Payment,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """الاعتماد: شاشة تأكيد ⇒ تنفيذ ⇒ رصيد + حركة + حالة الطلب + إشعار."""
    await load_user(bot, context, admin)
    state = await press(
        bot, context, payments.start_approve, pack("ap", "ok", pending_payment.id), admin.telegram_id
    )
    assert state == payments.CONFIRM_APPROVE
    assert "flow:confirm:v1" in bot.last.buttons

    before = await services.users.get(user.id)
    assert before.balance_units == 0, "تغيّر الرصيد قبل التأكيد"

    state = await press(
        bot, context, payments.confirm_approve, pack("flow", "confirm"), admin.telegram_id
    )
    assert state == ConversationHandler.END

    after = await services.users.get(user.id)
    assert after.balance_units == 50_000

    stored = await repos.payments.get(pending_payment.id)
    assert stored.status == PaymentStatus.APPROVED
    assert stored.admin_id == admin.id

    queued = await repos.notifications.list_for_user(user.id, limit=5)
    assert queued, "لم يصل المستخدم إشعار باعتماد الشحن"


async def test_approve_with_edited_amount(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    pending_payment: Payment,
    services: ServiceContainer,
) -> None:
    """تعديل المبلغ المعتمد (حوالة ناقصة) يُضيف المبلغ المعدَّل لا المطلوب."""
    await load_user(bot, context, admin)
    await press(
        bot, context, payments.start_approve, pack("ap", "ok", pending_payment.id), admin.telegram_id
    )
    state = await press(
        bot, context, payments.ask_credited_amount, pack("ap", "amount"), admin.telegram_id
    )
    assert state == payments.ASK_CREDITED

    state = await write(bot, context, payments.receive_credited_amount, "4", admin.telegram_id)
    assert state == payments.CONFIRM_APPROVE

    await press(bot, context, payments.confirm_approve, pack("flow", "confirm"), admin.telegram_id)
    after = await services.users.get(user.id)
    assert after.balance_units == 40_000, "اعتُمد المبلغ الأصلي بدل المعدَّل"


async def test_payment_cannot_be_approved_twice(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    pending_payment: Payment,
    services: ServiceContainer,
) -> None:
    """اعتماد نفس الطلب مرتين مستحيل — الرصيد لا يُضاعف."""
    await load_user(bot, context, admin)
    await press(
        bot, context, payments.start_approve, pack("ap", "ok", pending_payment.id), admin.telegram_id
    )
    await press(bot, context, payments.confirm_approve, pack("flow", "confirm"), admin.telegram_id)

    # محاولة ثانية كاملة من البطاقة
    await press(
        bot, context, payments.start_approve, pack("ap", "ok", pending_payment.id), admin.telegram_id
    )
    await press(bot, context, payments.confirm_approve, pack("flow", "confirm"), admin.telegram_id)

    after = await services.users.get(user.id)
    assert after.balance_units == 50_000, "تضاعف الرصيد باعتماد مزدوج"


async def test_reject_requires_reason_and_notifies_user(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    pending_payment: Payment,
    repos: Repositories,
    services: ServiceContainer,
) -> None:
    """الرفض يحتاج سبباً مكتوباً، ويصل المستخدم إشعار، ولا يُضاف أي رصيد."""
    await load_user(bot, context, admin)
    state = await press(
        bot, context, payments.start_reject, pack("ap", "no", pending_payment.id), admin.telegram_id
    )
    assert state == payments.ASK_REJECT_REASON

    state = await write(
        bot, context, payments.receive_reject_reason, "لا يوجد تحويل بهذا الرقم", admin.telegram_id
    )
    assert state == ConversationHandler.END

    stored = await repos.payments.get(pending_payment.id)
    assert stored.status == PaymentStatus.REJECTED
    assert stored.reject_reason == "لا يوجد تحويل بهذا الرقم"

    owner = await services.users.get(user.id)
    assert owner.balance_units == 0

    queued = await repos.notifications.list_for_user(user.id, limit=5)
    assert queued, "لم يصل المستخدم إشعار بالرفض"


async def test_short_reject_reason_is_refused(
    bot: FakeBot, context: FakeContext, admin: User, pending_payment: Payment, repos: Repositories
) -> None:
    """سبب رفض قصير جداً يُرفض ويبقى الطلب معلّقاً."""
    await load_user(bot, context, admin)
    await press(
        bot, context, payments.start_reject, pack("ap", "no", pending_payment.id), admin.telegram_id
    )
    await write(bot, context, payments.receive_reject_reason, "لا", admin.telegram_id)

    stored = await repos.payments.get(pending_payment.id)
    assert stored.status == PaymentStatus.PENDING, "رُفض الطلب بسبب غير مكتمل"


async def test_approve_blocked_without_permission(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    super_admin: User,
    pending_payment: Payment,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """سحب صلاحية الاعتماد يمنع العملية حتى لو وصل الأدمن للبطاقة."""
    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.PAYMENTS_APPROVE, allow=False
    )
    await load_user(bot, context, admin)
    await press(
        bot, context, payments.start_approve, pack("ap", "ok", pending_payment.id), admin.telegram_id
    )

    assert bot.answers[-1]["alert"] is True
    stored = await repos.payments.get(pending_payment.id)
    assert stored.status == PaymentStatus.PENDING
```

### `tests/integration/test_admin_orders.py`

```python
"""
اختبارات قسم الطلبات في لوحة التحكم.

تشمل: التصفية والبطاقة، إعادة الفحص الفوري، الإلغاء مع الاسترجاع، وضع الطلب
فاشلاً مع الاسترجاع، ربط رقم المزود يدوياً، وتغيير الحالة قسرياً بسبب مكتوب.
القاعدة المحروسة هنا: **لا استرجاع بلا حركة مالية، ولا تغيير حالة بلا تحقق**.
"""

from __future__ import annotations

import pytest
from telegram.ext import ConversationHandler

from core.enums import OrderStatus, TransactionType
from core.permissions import Permission
from database.models import Service, User
from database.repositories import Repositories
from handlers.admin import orders as admin_orders
from integrations.providers.mock import MockProviderClient
from keyboards.callback_data import pack
from services import ServiceContainer
from tests.integration.test_user_interface import (
    bot,  # noqa: F401
    context,  # noqa: F401
    load_user,
    press,
    write,
)
from tests.telegram_fakes import FakeBot, FakeContext

pytestmark = pytest.mark.asyncio

ORDER_COST = 10_000  # تكلفة طلب 1000 وحدة بسعر 10000 لكل ألف


async def _funded_order(
    services: ServiceContainer, user: User, admin: User, service: Service, *, quantity: int = 1000
):
    """شحن رصيد المستخدم ثم إنشاء طلب جاهز للاختبار."""
    await services.wallet.adjust_balance(
        target=user, amount_units=ORDER_COST * 2, admin=admin, reason="رصيد اختبار", credit=True
    )
    return await services.orders.create_order(
        user, service_id=service.id, link="https://instagram.com/test", quantity=quantity
    )


# ======================================================================== #
#                             القوائم والبطاقة                             #
# ======================================================================== #


async def test_orders_list_and_filters(
    bot: FakeBot, context: FakeContext, admin: User, user: User, mock_service: Service, services: ServiceContainer
) -> None:
    """قائمة الطلبات تعرض الطلب الحقيقي وأزرار التصفية."""
    order = await _funded_order(services, user, admin, mock_service)
    await load_user(bot, context, admin)
    await press(
        bot, context, admin_orders.orders_list_screen, pack("ao", "list", "all", 1), admin.telegram_id
    )

    assert f"ao:view:{order.id}:all:1:v1" in bot.last.buttons
    assert "ao:list:act:1:v1" in bot.last.buttons, "أزرار التصفية غير معروضة"


async def test_order_card_shows_actions(
    bot: FakeBot, context: FakeContext, super_admin: User, user: User, mock_service: Service, services: ServiceContainer
) -> None:
    """بطاقة الطلب تعرض كوده وحالته وأزرار الإجراءات المسموح بها."""
    order = await _funded_order(services, user, super_admin, mock_service)
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        admin_orders.order_card_screen,
        pack("ao", "view", order.id, "all", 1),
        super_admin.telegram_id,
    )

    assert order.public_code in bot.last.text
    assert f"ao:cancel:{order.id}:v1" in bot.last.buttons
    assert f"ao:fail:{order.id}:v1" in bot.last.buttons


# ======================================================================== #
#                          الإلغاء والفشل والاسترجاع                       #
# ======================================================================== #


async def test_admin_cancel_refunds_user(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    mock_service: Service,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """إلغاء الأدمن لطلب معلّق: سبب ⇒ تأكيد ⇒ استرجاع بحركة مالية وإشعار."""
    order = await _funded_order(services, user, admin, mock_service)
    before = await services.users.get(user.id)

    await load_user(bot, context, admin)
    state = await press(
        bot, context, admin_orders.start_cancel, pack("ao", "cancel", order.id), admin.telegram_id
    )
    assert state == admin_orders.ASK_REASON

    state = await write(
        bot, context, admin_orders.receive_reason, "طلب العميل الإلغاء", admin.telegram_id
    )
    assert state == admin_orders.CONFIRM_ACTION
    assert "flow:confirm:v1" in bot.last.buttons, "لا تأكيد ثانٍ قبل إلغاء الطلب"

    still = await repos.orders.get(order.id)
    assert still.status == OrderStatus.PENDING, "أُلغي الطلب قبل التأكيد"

    state = await press(
        bot, context, admin_orders.confirm_reason_action, pack("flow", "confirm"), admin.telegram_id
    )
    assert state == ConversationHandler.END

    canceled = await repos.orders.get(order.id)
    assert canceled.status in {OrderStatus.CANCELED, OrderStatus.REFUNDED}

    after = await services.users.get(user.id)
    assert after.balance_units == before.balance_units + ORDER_COST, "لم يُسترجع المبلغ"

    transactions = await repos.transactions.list_by_user(user.id, limit=5)
    assert any(item.type == TransactionType.REFUND for item in transactions), (
        "استرجاع بلا حركة مالية"
    )


async def test_admin_mark_failed_refunds_once(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    mock_service: Service,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """وضع الطلب فاشلاً يسترجع المبلغ مرة واحدة فقط مهما تكرر الضغط."""
    order = await _funded_order(services, user, admin, mock_service)
    before = await services.users.get(user.id)

    await load_user(bot, context, admin)
    await press(bot, context, admin_orders.start_fail, pack("ao", "fail", order.id), admin.telegram_id)
    await write(bot, context, admin_orders.receive_reason, "المزود لا يدعم الرابط", admin.telegram_id)
    await press(
        bot, context, admin_orders.confirm_reason_action, pack("flow", "confirm"), admin.telegram_id
    )

    after = await services.users.get(user.id)
    assert after.balance_units == before.balance_units + ORDER_COST

    # تكرار العملية على طلب نهائي: لا استرجاع ثانٍ
    await press(bot, context, admin_orders.start_fail, pack("ao", "fail", order.id), admin.telegram_id)
    await write(bot, context, admin_orders.receive_reason, "محاولة ثانية", admin.telegram_id)
    await press(
        bot, context, admin_orders.confirm_reason_action, pack("flow", "confirm"), admin.telegram_id
    )

    final = await services.users.get(user.id)
    assert final.balance_units == after.balance_units, "تكرّر الاسترجاع على نفس الطلب"


async def test_cancel_without_permission_is_blocked(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    super_admin: User,
    user: User,
    mock_service: Service,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """بلا صلاحية `orders.cancel` لا يبدأ الإلغاء أصلاً."""
    order = await _funded_order(services, user, super_admin, mock_service)
    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.ORDERS_CANCEL, allow=False
    )
    await load_user(bot, context, admin)
    await press(bot, context, admin_orders.start_cancel, pack("ao", "cancel", order.id), admin.telegram_id)

    assert bot.answers[-1]["alert"] is True
    unchanged = await repos.orders.get(order.id)
    assert unchanged.status == OrderStatus.PENDING


# ======================================================================== #
#                       المزود: فحص فوري وربط رقم الطلب                     #
# ======================================================================== #


async def test_recheck_now_updates_status(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    mock_service: Service,
    mock_client: MockProviderClient,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """إعادة الفحص الفوري تستجلب حالة المزود وتحدّث الطلب."""
    order = await _funded_order(services, user, admin, mock_service)
    await services.orders.process_pending_orders()
    submitted = await repos.orders.get(order.id)
    assert submitted.provider_order_id, "لم يُرسل الطلب للمزود"

    mock_client.advance(submitted.provider_order_id, to="Completed", delivered=submitted.quantity)
    await load_user(bot, context, admin)
    await press(
        bot, context, admin_orders.recheck_order, pack("ao", "recheck", order.id), admin.telegram_id
    )

    rechecked = await repos.orders.get(order.id)
    assert rechecked.status == OrderStatus.COMPLETED
    assert bot.answers, "لم يُرد البوت على زر إعادة الفحص"


async def test_recheck_without_provider_order_id_explains(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    mock_service: Service,
    services: ServiceContainer,
) -> None:
    """طلب بلا رقم عند المزود: رسالة واضحة بدل عطل صامت."""
    order = await _funded_order(services, user, admin, mock_service)
    await load_user(bot, context, admin)
    await press(
        bot, context, admin_orders.recheck_order, pack("ao", "recheck", order.id), admin.telegram_id
    )
    assert bot.answers[-1]["text"], "لا رسالة توضح تعذّر الفحص"


async def test_link_provider_order_id(
    bot: FakeBot,
    context: FakeContext,
    super_admin: User,
    user: User,
    mock_service: Service,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """ربط رقم طلب المزود يدوياً لطلب نتيجته غير مؤكدة."""
    order = await _funded_order(services, user, super_admin, mock_service)
    async with repos.db.transaction() as tx:
        await repos.orders.update_fields(tx, order.id, status=OrderStatus.SUBMIT_UNCERTAIN)

    await load_user(bot, context, super_admin)
    state = await press(
        bot, context, admin_orders.start_link, pack("ao", "link", order.id), super_admin.telegram_id
    )
    assert state == admin_orders.ASK_PROVIDER_ID

    state = await write(bot, context, admin_orders.receive_provider_id, "PRV-55512", super_admin.telegram_id)
    assert state == ConversationHandler.END

    linked = await repos.orders.get(order.id)
    assert linked.provider_order_id == "PRV-55512"
    assert linked.status == OrderStatus.SUBMITTED


# ======================================================================== #
#                            تغيير الحالة قسرياً                           #
# ======================================================================== #


async def test_override_status_requires_reason(
    bot: FakeBot,
    context: FakeContext,
    super_admin: User,
    user: User,
    mock_service: Service,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """التغيير القسري للحالة يحتاج سبباً مكتوباً ويُسجَّل في التدقيق."""
    order = await _funded_order(services, user, super_admin, mock_service)
    await load_user(bot, context, super_admin)

    await press(
        bot, context, admin_orders.override_screen, pack("ao", "force", order.id), super_admin.telegram_id
    )
    assert any(button.startswith(f"ao:setst:{order.id}") for button in bot.last.buttons), (
        "شاشة التغيير القسري لا تعرض الحالات المسموح بها"
    )

    state = await press(
        bot,
        context,
        admin_orders.start_override,
        pack("ao", "setst", order.id, OrderStatus.CANCELED),
        super_admin.telegram_id,
    )
    assert state == admin_orders.ASK_OVERRIDE_REASON

    state = await write(
        bot, context, admin_orders.receive_override_reason, "تسوية يدوية بعد اتفاق مع العميل", super_admin.telegram_id
    )
    assert state == ConversationHandler.END

    changed = await repos.orders.get(order.id)
    assert changed.status == OrderStatus.CANCELED

    audit = await repos.audit.list_recent(limit=10)
    assert any("status" in entry.action or "override" in entry.action for entry in audit), (
        "التغيير القسري بلا سجل تدقيق"
    )


async def test_override_rejects_short_reason(
    bot: FakeBot,
    context: FakeContext,
    super_admin: User,
    user: User,
    mock_service: Service,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """سبب قصير لا يكفي لتغيير حالة طلب قسرياً."""
    order = await _funded_order(services, user, super_admin, mock_service)
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        admin_orders.start_override,
        pack("ao", "setst", order.id, OrderStatus.FAILED),
        super_admin.telegram_id,
    )
    await write(bot, context, admin_orders.receive_override_reason, "خطأ", super_admin.telegram_id)

    unchanged = await repos.orders.get(order.id)
    assert unchanged.status == OrderStatus.PENDING, "تغيّرت الحالة رغم السبب الناقص"


async def test_override_blocked_for_plain_admin(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    mock_service: Service,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """التغيير القسري حكر على من يملك `orders.status.override` (ليس الأدمن العادي)."""
    order = await _funded_order(services, user, admin, mock_service)
    await load_user(bot, context, admin)
    await press(
        bot,
        context,
        admin_orders.start_override,
        pack("ao", "setst", order.id, OrderStatus.COMPLETED),
        admin.telegram_id,
    )
    assert bot.answers[-1]["alert"] is True
    unchanged = await repos.orders.get(order.id)
    assert unchanged.status == OrderStatus.PENDING
```

### `tests/integration/test_admin_support.py`

```python
"""
اختبارات قسم التذاكر في لوحة التحكم.

المطلوب إثباته: الأدمن يرى المحادثة كاملة، ردّه يصل للمستخدم فعلاً (إشعار
+ رسالة محفوظة)، الإسناد يمنع ازدواج العمل، والإغلاق لا يحذف التاريخ.
"""

from __future__ import annotations

import pytest
from telegram.ext import ConversationHandler

from core.enums import TicketStatus
from core.permissions import Permission
from database.models import SupportTicket, User
from database.repositories import Repositories
from handlers.admin import tickets as admin_tickets
from keyboards.callback_data import pack
from services import ServiceContainer
from tests.integration.test_user_interface import (
    bot,  # noqa: F401
    context,  # noqa: F401
    load_user,
    press,
    write,
)
from tests.telegram_fakes import FakeBot, FakeContext

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def ticket(services: ServiceContainer, user: User) -> SupportTicket:
    """تذكرة دعم مفتوحة أنشأها المستخدم."""
    return await services.tickets.create_ticket(
        user, subject="لم يصل طلبي", category="order", message="مرّ يومان ولم يصل شيء"
    )


async def test_tickets_list_shows_open_ticket(
    bot: FakeBot, context: FakeContext, admin: User, ticket: SupportTicket
) -> None:
    """قائمة التذاكر المفتوحة تعرض التذكرة وأزرار التصفية."""
    await load_user(bot, context, admin)
    await press(
        bot, context, admin_tickets.tickets_list_screen, pack("at", "list", "open", 1), admin.telegram_id
    )
    assert f"at:view:{ticket.id}:v1" in bot.last.buttons
    assert "at:list:mine:1:v1" in bot.last.buttons


async def test_ticket_card_shows_conversation(
    bot: FakeBot, context: FakeContext, admin: User, ticket: SupportTicket
) -> None:
    """بطاقة التذكرة تعرض نص رسالة المستخدم وأزرار الرد والإغلاق."""
    await load_user(bot, context, admin)
    await press(
        bot, context, admin_tickets.ticket_card_screen, pack("at", "view", ticket.id), admin.telegram_id
    )

    assert "مرّ يومان" in bot.last.text
    assert f"at:reply:{ticket.id}:v1" in bot.last.buttons
    assert f"at:close:{ticket.id}:v1" in bot.last.buttons


async def test_reply_reaches_user(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    ticket: SupportTicket,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """رد الأدمن يُحفظ في المحادثة ويصل المستخدم كإشعار."""
    await load_user(bot, context, admin)
    state = await press(
        bot, context, admin_tickets.start_reply, pack("at", "reply", ticket.id), admin.telegram_id
    )
    assert state == admin_tickets.ASK_REPLY

    state = await write(
        bot, context, admin_tickets.receive_reply, "تم تسريع طلبك، شكراً لصبرك", admin.telegram_id
    )
    assert state == ConversationHandler.END

    messages = await repos.tickets.messages(ticket.id, limit=10)
    assert any(item.sender_type == "admin" for item in messages), "لم يُحفظ رد الأدمن"

    queued = await repos.notifications.list_for_user(user.id, limit=5)
    assert queued, "لم يصل المستخدم إشعار برد الدعم"


async def test_assign_ticket_to_self(
    bot: FakeBot, context: FakeContext, admin: User, ticket: SupportTicket, repos: Repositories
) -> None:
    """الإسناد يربط التذكرة بالأدمن الحالي (منع ازدواج الردود)."""
    await load_user(bot, context, admin)
    await press(
        bot, context, admin_tickets.assign_ticket, pack("at", "assign", ticket.id), admin.telegram_id
    )

    stored = await repos.tickets.get(ticket.id)
    assert stored.assigned_admin == admin.id


async def test_close_ticket_keeps_history(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    ticket: SupportTicket,
    repos: Repositories,
) -> None:
    """الإغلاق يغيّر الحالة فقط — الرسائل تبقى محفوظة (لا حذف تاريخي)."""
    await load_user(bot, context, admin)
    state = await press(
        bot, context, admin_tickets.start_close, pack("at", "close", ticket.id), admin.telegram_id
    )
    assert state == admin_tickets.ASK_CLOSE_REASON

    state = await write(
        bot, context, admin_tickets.receive_close_reason, "تم حل المشكلة", admin.telegram_id
    )
    assert state == ConversationHandler.END

    stored = await repos.tickets.get(ticket.id)
    assert stored.status == TicketStatus.CLOSED

    messages = await repos.tickets.messages(ticket.id, limit=10)
    assert messages, "اختفت رسائل التذكرة بعد الإغلاق"


async def test_reply_requires_permission(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    super_admin: User,
    ticket: SupportTicket,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """بلا صلاحية `tickets.reply` لا يمكن الرد."""
    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.TICKETS_REPLY, allow=False
    )
    await load_user(bot, context, admin)
    await press(
        bot, context, admin_tickets.start_reply, pack("at", "reply", ticket.id), admin.telegram_id
    )

    assert bot.answers[-1]["alert"] is True
    messages = await repos.tickets.messages(ticket.id, limit=10)
    assert all(item.sender_type != "admin" for item in messages)
```

### `tests/integration/test_admin_catalog_settings.py`

```python
"""
اختبارات أقسام: الكتالوج، الإعدادات، السجلات في لوحة التحكم.

النقاط المحروسة:
    • تغيير السعر يُحفظ، والبيع بخسارة يحتاج تأكيداً ثانياً.
    • إيقاف/أرشفة خدمة لا يحذفها ولا يكسر طلبات قائمة.
    • قيمة الإعداد تُطبَّع حسب نوعها (لا نص في حقل رقمي).
    • وضع الصيانة يمنع المستخدمين فعلاً ولا يمنع الأدمن.
    • السجلات للقراءة فقط وتعرض أحداثاً حقيقية.
"""

from __future__ import annotations

import pytest
from telegram.ext import ConversationHandler

from core.permissions import Permission
from database.models import Service, User
from database.repositories import Repositories
from handlers.admin import catalog, logs, settings as admin_settings
from keyboards.callback_data import pack
from services import ServiceContainer
from tests.integration.test_user_interface import (
    bot,  # noqa: F401
    context,  # noqa: F401
    load_user,
    press,
    write,
)
from tests.telegram_fakes import FakeBot, FakeContext

pytestmark = pytest.mark.asyncio


# ======================================================================== #
#                                الكتالوج                                  #
# ======================================================================== #


async def test_catalog_home_lists_categories(
    bot: FakeBot, context: FakeContext, admin: User, service: Service
) -> None:
    """شاشة الكتالوج تعرض التصنيفات وعدد الخدمات الفعّالة."""
    await load_user(bot, context, admin)
    await press(bot, context, catalog.catalog_home_screen, pack("ac", "home"), admin.telegram_id)

    assert any(button.startswith("ac:cat:") for button in bot.last.buttons)
    assert "الخدمات" in bot.last.text or "التصنيفات" in bot.last.text


async def test_service_card_and_toggle(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    service: Service,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """بطاقة الخدمة تعرض السعر والهامش، وزر الإيقاف يعمل فوراً ويُسجَّل."""
    await load_user(bot, context, admin)
    await press(
        bot, context, catalog.service_card_screen, pack("ac", "svc", service.id), admin.telegram_id
    )
    assert service.name in bot.last.text
    assert f"ac:toggle:{service.id}:v1" in bot.last.buttons

    await press(
        bot, context, catalog.toggle_service, pack("ac", "toggle", service.id), admin.telegram_id
    )
    stored = await repos.services.get(service.id)
    assert not stored.is_active, "لم تتوقف الخدمة بعد الضغط على زر التبديل"

    await press(
        bot, context, catalog.toggle_service, pack("ac", "toggle", service.id), admin.telegram_id
    )
    restored = await repos.services.get(service.id)
    assert restored.is_active, "لم تُعَد الخدمة للعمل"


async def test_price_change_is_saved_with_history(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    service: Service,
    repos: Repositories,
) -> None:
    """تغيير السعر يُحفظ ويُسجَّل في تاريخ الأسعار."""
    await load_user(bot, context, admin)
    state = await press(
        bot, context, catalog.start_price, pack("ac", "price", service.id), admin.telegram_id
    )
    assert state == catalog.ASK_PRICE

    state = await write(bot, context, catalog.receive_price, "2", admin.telegram_id)
    assert state == ConversationHandler.END

    stored = await repos.services.get(service.id)
    assert stored.price_per_1000_units == 20_000

    history = await repos.services.price_history(service.id, limit=5)
    assert history, "تغيير السعر بلا سجل تاريخي"


async def test_price_below_cost_needs_confirmation(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    service: Service,
    repos: Repositories,
) -> None:
    """سعر أقل من تكلفة المزود = بيع بخسارة ⇒ تأكيد ثانٍ إجباري."""
    await load_user(bot, context, admin)
    await press(bot, context, catalog.start_price, pack("ac", "price", service.id), admin.telegram_id)

    state = await write(bot, context, catalog.receive_price, "0.3", admin.telegram_id)
    assert state == catalog.CONFIRM_PRICE
    assert "flow:confirm:v1" in bot.last.buttons

    not_yet = await repos.services.get(service.id)
    assert not_yet.price_per_1000_units == 10_000, "طُبِّق السعر الخاسر قبل التأكيد"

    state = await press(bot, context, catalog.confirm_price, pack("flow", "confirm"), admin.telegram_id)
    assert state == ConversationHandler.END

    stored = await repos.services.get(service.id)
    assert stored.price_per_1000_units == 3_000


async def test_archive_service_requires_confirmation(
    bot: FakeBot,
    context: FakeContext,
    super_admin: User,
    service: Service,
    repos: Repositories,
) -> None:
    """الأرشفة إجراء خطير: تأكيد ثانٍ، ثم إخفاء الخدمة دون حذفها."""
    await load_user(bot, context, super_admin)
    state = await press(
        bot, context, catalog.start_archive, pack("ac", "archive", service.id), super_admin.telegram_id
    )
    assert state == catalog.CONFIRM_ARCHIVE
    assert "flow:confirm:v1" in bot.last.buttons

    state = await press(
        bot, context, catalog.confirm_archive, pack("flow", "confirm"), super_admin.telegram_id
    )
    assert state == ConversationHandler.END

    stored = await repos.services.get(service.id)
    assert stored is not None, "حُذفت الخدمة بدل أرشفتها"
    assert stored.is_archived


async def test_new_category_flow_with_skipped_emoji(
    bot: FakeBot,
    context: FakeContext,
    super_admin: User,
    repos: Repositories,
) -> None:
    """إنشاء تصنيف جديد مع تخطي الأيقونة ⇒ أيقونة افتراضية لا قيمة فارغة."""
    await load_user(bot, context, super_admin)
    state = await press(
        bot, context, catalog.start_new_category, pack("ac", "newcat"), super_admin.telegram_id
    )
    assert state == catalog.ASK_CATEGORY_NAME

    state = await write(bot, context, catalog.receive_category_name, "تيك توك", super_admin.telegram_id)
    assert state == catalog.ASK_CATEGORY_EMOJI
    assert "flow:skip:v1" in bot.last.buttons

    state = await press(
        bot, context, catalog.skip_category_emoji, pack("flow", "skip"), super_admin.telegram_id
    )
    assert state == ConversationHandler.END

    created = [item for item in await repos.categories.list_all(active_only=False) if item.name_ar == "تيك توك"]
    assert created, "لم يُنشأ التصنيف"
    assert created[0].emoji, "التصنيف بلا أيقونة"


async def test_catalog_write_actions_need_permission(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    super_admin: User,
    service: Service,
    services: ServiceContainer,
    repos: Repositories,
) -> None:
    """سحب صلاحية تعديل السعر يمنع المحادثة من البدء."""
    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.SERVICES_PRICE, allow=False
    )
    await load_user(bot, context, admin)
    await press(bot, context, catalog.start_price, pack("ac", "price", service.id), admin.telegram_id)

    assert bot.answers[-1]["alert"] is True
    stored = await repos.services.get(service.id)
    assert stored.price_per_1000_units == 10_000


# ======================================================================== #
#                                الإعدادات                                 #
# ======================================================================== #


async def test_settings_home_and_group(
    bot: FakeBot, context: FakeContext, super_admin: User
) -> None:
    """شاشة الإعدادات تعرض المجموعات، وشاشة المجموعة تعرض مفاتيحها."""
    await load_user(bot, context, super_admin)
    await press(
        bot, context, admin_settings.settings_home_screen, pack("as", "home"), super_admin.telegram_id
    )
    group_buttons = [button for button in bot.last.buttons if button.startswith("as:group:")]
    assert group_buttons, "لا مجموعات إعدادات معروضة"

    await press(bot, context, admin_settings.settings_group_screen, group_buttons[0], super_admin.telegram_id)
    assert any(button.startswith("as:edit:") for button in bot.last.buttons), "لا مفاتيح للتعديل"


async def test_edit_integer_setting(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer
) -> None:
    """تعديل مفتاح رقمي يُحفظ ويُقرأ فوراً بالقيمة الجديدة."""
    await load_user(bot, context, super_admin)
    state = await press(
        bot,
        context,
        admin_settings.start_edit,
        pack("as", "edit", "order_check_interval_seconds"),
        super_admin.telegram_id,
    )
    assert state == admin_settings.ASK_VALUE

    state = await write(bot, context, admin_settings.receive_value, "300", super_admin.telegram_id)
    assert state == ConversationHandler.END
    assert await services.settings.get_int("order_check_interval_seconds") == 300


async def test_invalid_setting_value_is_refused(
    bot: FakeBot, context: FakeContext, super_admin: User, services: ServiceContainer
) -> None:
    """نص غير رقمي في مفتاح من نوع int يُرفض ولا يفسد الإعداد."""
    before = await services.settings.get_int("order_check_interval_seconds")
    await load_user(bot, context, super_admin)
    await press(
        bot,
        context,
        admin_settings.start_edit,
        pack("as", "edit", "order_check_interval_seconds"),
        super_admin.telegram_id,
    )
    await write(bot, context, admin_settings.receive_value, "ليست رقماً", super_admin.telegram_id)

    assert await services.settings.get_int("order_check_interval_seconds") == before


async def test_maintenance_toggle_blocks_users_not_admins(
    bot: FakeBot,
    context: FakeContext,
    super_admin: User,
    user: User,
    services: ServiceContainer,
) -> None:
    """وضع الصيانة: تأكيد ⇒ تفعيل ⇒ المستخدم ممنوع والأدمن يعمل ⇒ إيقافه يعيد الوضع."""
    await load_user(bot, context, super_admin)
    state = await press(
        bot, context, admin_settings.start_maintenance, pack("as", "maint"), super_admin.telegram_id
    )
    assert state == admin_settings.CONFIRM_MAINTENANCE
    assert "flow:confirm:v1" in bot.last.buttons
    assert await services.settings.is_maintenance() is False, "فُعِّلت الصيانة قبل التأكيد"

    await press(
        bot, context, admin_settings.confirm_maintenance, pack("flow", "confirm"), super_admin.telegram_id
    )
    assert await services.settings.is_maintenance() is True

    from core.exceptions import MaintenanceModeError

    with pytest.raises(MaintenanceModeError):
        await services.auth.guard(user)
    await services.auth.guard(super_admin)  # الأدمن يستثنى من المنع

    await press(
        bot, context, admin_settings.start_maintenance, pack("as", "maint"), super_admin.telegram_id
    )
    await press(
        bot, context, admin_settings.confirm_maintenance, pack("flow", "confirm"), super_admin.telegram_id
    )
    assert await services.settings.is_maintenance() is False


async def test_maintenance_needs_dedicated_permission(
    bot: FakeBot, context: FakeContext, admin: User, super_admin: User, services: ServiceContainer
) -> None:
    """بلا صلاحية `settings.maintenance` لا يمكن تبديل وضع الصيانة."""
    await services.auth.set_user_permission(
        super_admin, admin.id, Permission.SETTINGS_MAINTENANCE, allow=False
    )
    await load_user(bot, context, admin)
    await press(bot, context, admin_settings.start_maintenance, pack("as", "maint"), admin.telegram_id)

    assert bot.answers[-1]["alert"] is True
    assert await services.settings.is_maintenance() is False


# ======================================================================== #
#                                 السجلات                                  #
# ======================================================================== #


async def test_audit_screen_shows_real_actions(
    bot: FakeBot,
    context: FakeContext,
    admin: User,
    user: User,
    services: ServiceContainer,
) -> None:
    """سجل التدقيق يعرض عملية حقيقية جرت للتو (لا بيانات تجريبية)."""
    await services.users.set_note(admin, user.id, "ملاحظة لأجل السجل")
    await load_user(bot, context, admin)
    await press(bot, context, logs.audit_screen, pack("al", "audit", 1), admin.telegram_id)

    assert "note" in bot.last.text or "ملاحظة" in bot.last.text
    assert bot.last.buttons, "شاشة السجل بلا أزرار تنقل"


async def test_errors_screen_lists_logged_error(
    bot: FakeBot, context: FakeContext, admin: User, repos: Repositories
) -> None:
    """شاشة الأخطاء تعرض الأخطاء المسجَّلة فعلاً في قاعدة البيانات."""
    async with repos.db.transaction() as tx:
        await repos.error_logs.log(
            tx,
            error_type="ValueError",
            message="خطأ اختباري للعرض",
            traceback_snippet="line 1",
            source="tests",
        )
    await load_user(bot, context, admin)
    await press(bot, context, logs.errors_screen, pack("al", "errors", 1), admin.telegram_id)

    assert "خطأ اختباري للعرض" in bot.last.text or "ValueError" in bot.last.text


async def test_logs_are_read_only(
    bot: FakeBot, context: FakeContext, admin: User
) -> None:
    """شاشات السجلات لا تحتوي أي زر تعديل أو حذف — قراءة فقط."""
    await load_user(bot, context, admin)
    await press(bot, context, logs.logs_home_screen, pack("al", "home"), admin.telegram_id)

    for button in bot.last.buttons:
        assert not any(word in button for word in ("del", "edit", "clear")), (
            f"زر تعديل/حذف في شاشة سجلات للقراءة فقط: {button}"
        )
```

