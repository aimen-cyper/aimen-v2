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
BTN_BACK_PANEL = "🛠 لوحة التحكم"
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
    "👥 <b>المستخدمون</b>\n"
    "   الإجمالي: <b>{users_total}</b> · جديد اليوم: {users_new_today} · نشِط ٧ أيام: {users_active_7d}\n"
    "   🚫 محظورون: {users_banned}\n\n"
    "📦 <b>الطلبات</b>\n"
    "   اليوم: <b>{orders_today}</b> · ⚙️ نشطة: {active_orders}\n"
    "   ⚠️ تحتاج تدخلاً: <b>{attention_orders}</b>\n\n"
    "💵 <b>المال</b>\n"
    "   إيراد اليوم: <b>{revenue_today}</b>\n"
    "   إيراد ٧ أيام: {revenue_7d}\n"
    "   📥 إيداعات اليوم: {deposits_today}\n\n"
    "📋 <b>قيد الانتظار</b>\n"
    "   ⏳ شحن بانتظار المراجعة: <b>{pending_payments}</b>\n"
    "   🎫 تذاكر مفتوحة: <b>{open_tickets}</b>\n"
    "   🔔 إشعارات في الطابور: {queued}\n\n"
    "🩺 <b>النظام</b>\n"
    "   🛍 خدمات مفعّلة: {active_services}\n"
    "   ❗ أخطاء ٢٤ ساعة: {errors_24h}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
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
    "💵 المبلغ المحوَّل: {amount}\n"
    "{fee_line}"
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
    "💵 المبلغ المحوَّل: {amount}\n"
    "{fee_line}"
    "💵 <b>سيُضاف فعلياً: {credited}</b>\n"
    "💰 رصيد المستخدم بعد الإضافة: {balance_after}\n\n"
    "اضغط «نعم، نفّذ» للاعتماد، أو «تعديل المبلغ» لإضافة مبلغ مختلف."
)
PAYMENT_ASK_AMOUNT = (
    "✏️ أرسل المبلغ الذي سيُضاف فعلاً لرصيد المستخدم\n"
    "(المحوَّل: {amount} · الصافي بعد الرسوم: {net})"
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
    "🔁 محاولات الإرسال: {attempts}\n"
    "🔎 عمليات الفحص: {checks}"
)
ORDER_PROVIDER_LINE = "🏢 المزود: {provider} · رقمه: <code>{provider_order_id}</code>\n"
ORDER_PROGRESS_LINE = "📊 المنفَّذ: {delivered} · المتبقي: {remains}\n"
ORDER_ERROR_LINE = "⚠️ آخر خطأ: {error}\n"
ORDER_PROVIDER_STATUS_LINE = "📡 حالة المزود: {status}\n"
ORDER_LAST_OK_LINE = "✅ آخر فحص ناجح: {when}\n"
ORDER_CHECK_ERROR_LINE = "🔌 آخر خطأ فحص: {error} (إخفاقات متتالية: {streak})\n"
ORDER_NEXT_CHECK_LINE = "⏱ الفحص القادم: {when}\n"
ORDER_REFUND_LINE = "↩️ مسترجع: {amount}\n"

BTN_ORDER_RECHECK = "🔄 إعادة فحص الآن"
BTN_ORDER_CANCEL = "❌ إلغاء + استرجاع"
BTN_ORDER_FAIL = "⛔ تعليم كفاشل + استرجاع"
BTN_ORDER_LINK = "🔗 ربط رقم المزود"
BTN_ORDER_OVERRIDE = "🎚 تغيير الحالة يدوياً"
BTN_ORDER_USER = "👤 صاحب الطلب"

ORDER_RECHECK_RESULT = "🔄 نتيجة الفحص: {result}"
ORDER_ASK_CANCEL_REASON = (
    "❌ أرسل سبب إلغاء الطلب {code}.\n"
    "ℹ️ إن كان الطلب عند المزود يُتحقَّق من حالته أولاً ويُسترجع المبلغ كاملاً <b>فقط بعد أن يؤكد المزود الإلغاء</b>:"
)
ORDER_ACTION_CONFIRM = (
    "⚠️ <b>تأكيد {operation}</b>\n\n"
    "📦 {code}\n👤 {name}\n💵 سيُسترجع: {amount}\n📝 السبب: {reason}"
)
OP_ORDER_CANCEL = "الإلغاء"
OP_ORDER_FAIL = "تعليم الطلب كفاشل"
BTN_ORDER_FORCE_REFUND = "⚠️ استرجاع إجباري"
OP_ORDER_FORCE_REFUND = "الاسترجاع الإجباري (بلا تأكيد من المزود)"
ORDER_ASK_FORCE_REFUND_REASON = (
    "⚠️ <b>استرجاع إجباري</b> للطلب {code}\n"
    "سيُسترجع المبلغ للعميل <b>دون أن يؤكد المزود إلغاء الطلب</b>؛ قد يُنفَّذ الطلب فعلاً فتتحمّل الخسارة.\n"
    "يُسجَّل القرار في التدقيق. أرسل السبب:"
)
ORDER_FORCE_REFUND_WARNING = "\n\n🛑 <b>تنبيه:</b> لا يوجد تأكيد إلغاء من المزود. اضغط «تأكيد» فقط إذا كنت متأكداً."
ORDER_FORCE_REFUND_DONE = "⚠️ استُرجع {amount} للعميل قسراً للطلب {code} (مسجَّل في التدقيق)."
ORDER_CANCEL_DONE = "✅ أُلغي الطلب {code} واسترُجع {amount} للمستخدم."
ORDER_ASK_FAIL_REASON = "⛔ أرسل سبب اعتبار الطلب {code} فاشلاً (يُسترجع المبلغ للمستخدم):"
ORDER_FAIL_DONE = "⛔ عُلّم الطلب {code} كفاشل واسترُجع {amount}."
ORDER_ASK_PROVIDER_ID = (
    "🔗 أرسل رقم الطلب لدى المزود للطلب {code}\n"
    "(يُستخدم عندما يكون الطلب أُنشئ فعلاً عند المزود ولم يصلنا رقمه)."
)
ORDER_LINK_DONE = "✅ رُبط الطلب {code} برقم المزود: {provider_order_id}\n🔎 {probe}"
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
    "{priority_line}"
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
BTN_CATALOG_SEARCH = "🔎 بحث عن خدمة"
BTN_CATALOG_SEARCH_AGAIN = "🔎 بحث جديد"
CATALOG_SEARCH_ASK = (
    "🔎 <b>بحث عن خدمة</b>\n"
    "اكتب أحد التالي:\n"
    "• رقم الخدمة عندنا (مثل <code>123</code> أو <code>#123</code>)\n"
    "• رقم الخدمة لدى المزود\n"
    "• جزء من الاسم أو القسم أو اسم المزود (كلمة أو أكثر، مثل <code>instagram followers</code>)"
)
CATALOG_SEARCH_TITLE = (
    "🔎 <b>نتائج البحث:</b> {term}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "العدد: {total} · الصفحة {page} من {pages}\n"
    "🟢 مفعّلة · ⚪️ معطّلة · 🗄 مؤرشفة · الرمز بعد # = رقم الخدمة لدى المزود"
)
CATALOG_SEARCH_EMPTY = "🔎 لا نتائج لـ «{term}». جرّب كلمة أقصر أو رقماً آخر."
CATALOG_SEARCH_EXPIRED = "⚠️ انتهت صلاحية نتائج البحث. ابدأ بحثاً جديداً."
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
    "🔗 <b>الربط:</b>\n"
    "   🆔 الخدمة عندنا: <b>#{service_id}</b>\n"
    "   🏢 المزود: {provider} (<code>#{provider_id}</code>)\n"
    "   🧾 رقمها لدى المزود: <code>{provider_service_id}</code>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📂 التصنيف: {category}\n"
    "💵 سعر الألف: {price}{usd}\n"
    "🏷 تكلفة الألف من المزود: {cost}\n"
    "📈 هامش الربح: {margin}\n"
    "🔢 الحدود: {min_quantity} — {max_quantity}\n"
    "🚀 السرعة: {speed}\n"
    "💎 الجودة: {quality}\n"
    "🛡 الضمان: {guarantee}\n"
    "🔗 قاعدة الرابط: {link_rule}\n"
    "📌 الحالة: {status}\n"
    "{archived_line}"
    "{description_line}"
)
BTN_SERVICE_EDIT = "✏️ تعديل العرض"
SERVICE_EDIT_PICK = (
    "✏️ <b>تعديل بيانات العرض — #{service_id}</b>\n\n"
    "اختر الحقل. لا يؤثر هذا على السعر ولا على الطلبات القائمة."
)
SERVICE_EDIT_ASK = (
    "✏️ <b>{label}</b> — الخدمة #{service_id}\n\n"
    "الحالي: <code>{current}</code>\n\n"
    "أرسل القيمة الجديدة (حتى 60 حرفاً) أو <code>-</code> لمسحها فتظهر «غير محددة»."
)
SERVICE_EDIT_RULE_PICK = (
    "🔗 <b>قاعدة الرابط — الخدمة #{service_id}</b>\n\n"
    "الحالية: {current}\n\n"
    "اختر المنصة والنوع؛ تُرفض الروابط التي لا تطابقها قبل إنشاء الطلب."
)
SERVICE_EDIT_DONE = "✅ حُدِّث «{label}» للخدمة #{service_id}."
SERVICE_EDIT_FIELD_LABELS = {
    "speed_text": "السرعة",
    "quality_text": "الجودة",
    "guarantee_text": "الضمان",
    "link_rule": "قاعدة الرابط",
}
BTN_RULE_NONE = "🚫 بلا قيد"
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
#: أسماء مجموعات الإعدادات بالعربية (كان الزر يعرض الرمز الإنجليزي الخام مثل «⚙️ backup»)
SETTING_GROUP_LABELS = {
    "backup": "💾 النسخ الاحتياطي",
    "broadcast": "📣 الإذاعة",
    "channels": "📢 القنوات",
    "general": "⚙️ عامة",
    "limits": "🚦 الحدود",
    "maintenance": "🚧 الصيانة",
    "notifications": "🔔 الإشعارات",
    "orders": "📦 الطلبات",
    "payments": "💳 المدفوعات",
    "providers": "🔌 المزودون",
    "reports": "📊 التقارير",
    "security": "🛡️ الأمان",
    "system": "🖥 النظام",
    "tickets": "🎫 الدعم",
}


def setting_group_label(code: str) -> str:
    """اسم المجموعة بالعربية (يبقى الرمز كما هو لمجموعة جديدة لم تُترجَم بعد)."""
    return SETTING_GROUP_LABELS.get(code, f"⚙️ {code}")


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
BTN_LOG_PROVIDER_CALLS = "🔌 استدعاءات المزودين"
BTN_LOG_FILTER = "🔎 فلتر: {label}"
BTN_LOG_FAILED_ONLY = "❌ الفاشلة فقط"
BTN_LOG_ALL_CALLS = "📋 كل الاستدعاءات"

AUDIT_TITLE = (
    "🧾 <b>سجل التدقيق</b> · {category}\n━━━━━━━━━━━━━━━━━━━━\n"
    "{total} سجلاً · الصفحة {page} من {pages}\n\n{lines}\n\nاضغط رقم السجل لعرض تفاصيله."
)
AUDIT_EMPTY = "🧾 لا عمليات مسجّلة في هذه الفئة ({category})."
AUDIT_LINE = "{icon} <b>#{id} · {action}</b>\n   👮 {admin} · 🎯 {target}\n   🕒 {when}"

ERRORS_TITLE = (
    "❗ <b>آخر الأخطاء</b>\n━━━━━━━━━━━━━━━━━━━━\n{total} خطأً · الصفحة {page} من {pages}\n\n{lines}"
    "\n\nاضغط رقم الخطأ لعرض تفاصيله."
)
ERRORS_EMPTY = "✅ لا أخطاء مسجّلة — النظام نظيف."
ERROR_LINE = "<b>#{id} · {level}</b> · {source}\n   {message}\n   🕒 {when}"

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

#: أيقونة لكل نوع إجراء في سجل التدقيق (تُطابق الجزء الأول من اسم الإجراء الفعلي: `users.ban` ⇐ 👤)
AUDIT_ICONS: dict[str, str] = {
    "users": "👤",
    "payments": "💳",
    "orders": "📦",
    "services": "🛍",
    "providers": "🏢",
    "tickets": "🎫",
    "settings": "⚙️",
    "notifications": "🔔",
    "broadcast": "📣",
    "security": "🔐",
    "admins": "🛡",
    "admin": "🛡",
    "backup": "💾",
    "stats": "📈",
    "system": "🖥",
}

#: أسماء فئات فلتر سجل التدقيق (المفاتيح تطابق `AUDIT_CATEGORIES`)
AUDIT_CATEGORY_LABELS: dict[str, str] = {
    "all": "📋 الكل",
    "users": "👤 المستخدمون",
    "money": "💰 المال",
    "orders": "📦 الطلبات",
    "catalog": "🛍 الخدمات والمزودون",
    "tickets": "🎫 التذاكر",
    "settings": "⚙️ الإعدادات والإشعارات",
    "security": "🔐 الأمن والصلاحيات",
    "system": "🖥 النظام والنسخ",
}

AUDIT_FILTER_MENU = "🔎 <b>فلتر سجل التدقيق</b>\n━━━━━━━━━━━━━━━━━━━━\nاختر الفئة التي تريد عرضها:"

AUDIT_DETAIL = (
    "🧾 <b>سجل تدقيق #{id}</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    "⚙️ الإجراء: <code>{action}</code>\n"
    "👮 المنفّذ: {admin}\n"
    "🎯 الهدف: {target}\n"
    "📡 المصدر: {source}\n"
    "🕒 الوقت: {when}\n"
    "{blocks}"
)
AUDIT_DETAIL_BLOCK = "\n<b>{title}</b>\n<pre>{body}</pre>"
AUDIT_DETAIL_BLOCK_TITLES = {"before": "قبل التعديل", "after": "بعد التعديل", "details": "تفاصيل"}
AUDIT_DETAIL_NO_DATA = "\nℹ️ لا بيانات إضافية مسجّلة لهذه العملية."
AUDIT_NOT_FOUND = "❌ سجل التدقيق غير موجود."

ERROR_DETAIL = (
    "❗ <b>خطأ #{id}</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    "المستوى: <b>{level}</b>\n"
    "المصدر: {source}\n"
    "النوع: <code>{error_type}</code>\n"
    "🕒 الوقت: {when}\n"
    "👤 المستخدم: {user}\n"
    "🔔 أُبلغ الأدمن: {notified}\n\n"
    "<b>الرسالة</b>\n{message}\n"
    "{extra}"
)
ERROR_DETAIL_TRACE = "\n<b>أثر الاستدعاء (مقتطف)</b>\n<pre>{trace}</pre>"
ERROR_DETAIL_UPDATE = "\n<b>ملخص التحديث</b>\n<pre>{summary}</pre>"
ERROR_NOT_FOUND = "❌ سجل الخطأ غير موجود."

PROVIDER_CALLS_TITLE = (
    "🔌 <b>استدعاءات المزودين</b> · {mode}\n━━━━━━━━━━━━━━━━━━━━\n"
    "{total} استدعاءً · الصفحة {page} من {pages}\n\n{lines}\n\nاضغط رقم الاستدعاء لعرض تفاصيله."
)
PROVIDER_CALLS_EMPTY = "🔌 لا استدعاءات مسجّلة ({mode})."
PROVIDER_CALLS_MODE = {"all": "الكل", "failed": "الفاشلة فقط"}
PROVIDER_CALL_LINE = "{icon} <b>#{id} · {provider}</b> · {action}\n   {meta}\n   🕒 {when}"
PROVIDER_CALL_DETAIL = (
    "🔌 <b>استدعاء مزود #{id}</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    "المزود: {provider}\n"
    "العملية: <code>{action}</code>\n"
    "النتيجة: {result}\n"
    "HTTP: {http}\n"
    "المدة: {duration}\n"
    "الطلب المرتبط: {order}\n"
    "نوع الخطأ: <code>{error_type}</code>\n"
    "🕒 الوقت: {when}\n"
    "{extra}"
)
PROVIDER_CALL_REQUEST = "\n<b>ملخص الطلب</b>\n<pre>{body}</pre>"
PROVIDER_CALL_RESPONSE = "\n<b>مقتطف الرد</b>\n<pre>{body}</pre>"
PROVIDER_CALL_NOT_FOUND = "❌ سجل الاستدعاء غير موجود."


# ======================================================================== #
#                   المزودون وربط الـAPI (المرحلة 5)                       #
# ======================================================================== #

MENU_PROVIDERS = "🔌 المزودون"

PROVIDERS_HOME = (
    "🔌 <b>المزودون</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "المسجّلون: {total} · المفعّلون: {active}\n"
    "خدماتنا المرتبطة بمزود: {linked_services}\n\n"
    "اختر مزوداً لعرض بطاقته."
)
PROVIDERS_EMPTY = "🔌 لا يوجد أي مزود بعد. أضف مزوداً لتبدأ ربط الخدمات."

PROVIDER_CARD = (
    "🔌 <b>{name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🆔 المعرف: <code>{provider_id}</code>\n"
    "🌐 الرابط: <code>{api_url}</code>\n"
    "🔑 المفتاح: <code>••••{key_hint}</code>\n"
    "🧩 النوع: <code>{api_type}</code>\n"
    "⚡️ الحالة: {state}\n"
    "💵 الرصيد لدى المزود: {balance} {currency}{balance_equivalent}\n"
    "💱 سعر الصرف: {rate_text}\n"
    "🕒 آخر فحص رصيد: {balance_checked}\n"
    "🛍 خدماتنا منه: {services_count}\n"
    "📉 أخطاء متتالية: {failures}\n"
    "🕓 آخر نجاح: {last_success}\n"
    "{last_error_line}"
)
PROVIDER_LAST_ERROR_LINE = "⚠️ آخر خطأ: <code>{error}</code>\n"
PROVIDER_STATE_OK = "🟢 جاهز"
PROVIDER_STATE_OFF = "⚪️ متوقف يدوياً"
PROVIDER_STATE_BLOCKED = "🔴 موقوف مؤقتاً: {reason}"
PROVIDER_NOT_FOUND = "❌ المزود غير موجود."

BTN_PROVIDER_NEW = "➕ مزود جديد"
BTN_PROVIDER_MAP = "🗺 خريطة المزودين"
PROVIDER_MAP_HEADER = (
    "🗺 <b>خريطة المزودين</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "التوجيه يتم بمزود الخدمة المحفوظ في كل خدمة فقط.\n\n"
)
PROVIDER_MAP_ROW = (
    "{mark} <b>{name}</b> (#{provider_id})\n"
    "• الحالة: {state}\n"
    "• الرصيد: {balance}\n"
    "• آخر فحص: {checked}\n"
    "• خدمات مفعّلة: {services}\n"
    "• طلبات مفتوحة: {open_orders}\n"
)
PROVIDER_MAP_WARNING = "• ⚠️ {text}\n"
PROVIDER_MAP_EMPTY = "🗺 لا يوجد أي مزود بعد."
BTN_PROVIDER_TEST = "🔍 اختبار الاتصال"
BTN_PROVIDER_BALANCE = "💵 تحديث الرصيد"
BTN_PROVIDER_RATE = "💱 العملة وسعر الصرف"
BTN_PROVIDER_KEY = "🔑 تغيير المفتاح"
BTN_PROVIDER_ON = "🟢 تفعيل"
BTN_PROVIDER_OFF = "⚪️ إيقاف"
BTN_PROVIDER_SYNC = "🔄 مزامنة الخدمات"
BTN_PROVIDER_IMPORT = "⬇️ استيراد خدمة"
BTN_PROVIDER_SERVICES = "🛍 خدماتنا منه"

# ------------------------------ إضافة مزود ------------------------------ #

PROVIDER_ASK_NAME = (
    "➕ <b>مزود جديد</b>\n\n"
    "أرسل اسم المزود كما تريد أن يظهر لك (مثال: <code>PanelX</code>).\n"
    "من 2 إلى 60 حرفاً."
)
PROVIDER_ASK_URL = (
    "🌐 أرسل رابط الـAPI كاملاً.\n\n"
    "عادةً ينتهي بـ <code>/api/v2</code>\n"
    "مثال: <code>https://panel.example.com/api/v2</code>"
)
PROVIDER_ASK_TYPE = (
    "🧩 اختر نوع واجهة المزود.\n\n"
    "<b>perfect_panel</b> هو المعيار الذي تستخدمه أغلب اللوحات.\n"
    "<b>mock</b> مزود وهمي للتجربة بلا شبكة ولا مال."
)
PROVIDER_ASK_CURRENCY = (
    "💱 <b>عملة المزود</b>\n\n"
    "أرسل رمز عملة حسابك لدى المزود، ثم سعر صرفها إلى عملة النظام (<b>{system}</b>).\n"
    "• عملة مختلفة: <code>USD 530</code> (يعني 1 USD = 530 {system})\n"
    "• عملة النظام نفسها: <code>{system}</code> بلا سعر\n\n"
    "⚠️ بدون سعر صحيح تُحسب التكاليف والأرباح بقيم خاطئة، لذلك يرفض النظام الإرسال حتى يُحدَّد."
)
PROVIDER_ASK_KEY = (
    "🔑 أرسل مفتاح API.\n\n"
    "⚠️ يُخزَّن مشفّراً، ولن يُعرض بعدها كاملاً في أي شاشة أو سجل.\n"
    "<b>احذف الرسالة بعد إرسالها.</b>"
)
PROVIDER_NEW_CONFIRM = (
    "📋 <b>تأكيد إضافة المزود</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🏷 الاسم: {name}\n"
    "🌐 الرابط: <code>{api_url}</code>\n"
    "🧩 النوع: <code>{api_type}</code>\n"
    "💱 العملة: <code>{currency_text}</code>\n"
    "🔑 المفتاح: <code>••••{key_hint}</code>\n\n"
    "سيُختبر الاتصال مباشرة بعد الإضافة."
)
PROVIDER_CREATED = "✅ أُضيف المزود <b>{name}</b> برقم <code>{provider_id}</code>."
PROVIDER_TYPE_UNSUPPORTED = "❌ نوع غير مدعوم. المتاح: {types}"

# ----------------------------- تغيير المفتاح ---------------------------- #

PROVIDER_ASK_NEW_KEY = (
    "🔑 أرسل المفتاح الجديد للمزود <b>{name}</b>.\n\n"
    "⚠️ المفتاح الحالي ينتهي بـ <code>{key_hint}</code> وسيُستبدل فوراً.\n"
    "<b>احذف رسالتك بعد الإرسال.</b>"
)
PROVIDER_ASK_RATE_EDIT = (
    "💱 <b>العملة وسعر الصرف — {name}</b>\n\n"
    "الحالي: <code>{current}</code>\n\n"
    "أرسل الرمز والسعر الجديدين. مثال: <code>USD 530</code> (1 USD = 530 {system})\n"
    "أو <code>{system}</code> وحدها إن كان حساب المزود بعملة النظام.\n\n"
    "ℹ️ لا تتغير تكلفة الخدمات المستوردة سابقاً إلا بعد «🔄 مزامنة»."
)
PROVIDER_RATE_UPDATED = (
    "✅ حُدِّثت عملة المزود <b>{name}</b>: <code>{current}</code>\n"
    "شغّل «🔄 مزامنة» ليُعاد حساب تكلفة خدماته المستوردة بالسعر الجديد."
)
PROVIDER_RATE_NONE = "غير محدد ⚠️"
PROVIDER_KEY_UPDATED = "✅ حُدِّث مفتاح المزود <b>{name}</b> (ينتهي بـ <code>{key_hint}</code>)."
PROVIDER_KEY_UNCHANGED = "ℹ️ لم يتغير المفتاح."

# -------------------------- الاختبار والرصيد ---------------------------- #

PROVIDER_TEST_RUNNING = "🔍 جارٍ اختبار الاتصال بالمزود…"
PROVIDER_TEST_RESULT = "{icon} <b>نتيجة الاختبار — {name}</b>\n━━━━━━━━━━━━━━━━━━━━\n{message}"
PROVIDER_BALANCE_UPDATED = "💵 رصيدنا لدى <b>{name}</b>: {balance} {currency}"
PROVIDER_TOGGLED_ON = "🟢 فُعّل المزود {name}."
PROVIDER_TOGGLED_OFF = "⚪️ أُوقف المزود {name} (لن تُرسل إليه طلبات جديدة)."

# ----------------------------- المزامنة --------------------------------- #

PROVIDER_SYNC_RUNNING = "🔄 جارٍ جلب قائمة خدمات المزود…"
PROVIDER_SYNC_RESULT = (
    "🔄 <b>نتيجة المزامنة — {name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📥 خدمات لدى المزود: {provider_items}\n"
    "🔗 خدماتنا المرتبطة به: {checked}\n"
    "✏️ حُدِّثت تكلفتها/حدودها: {updated}\n"
    "   💲 تغيّرت التكلفة: {cost_changes} · 📏 تغيّرت الحدود: {limit_changes}\n"
    "✅ بلا تغيير: {unchanged}\n"
    "🆕 جديدة لدى المزود (لم تُستورد): {new_items}\n"
    "❓ لم تعد موجودة لديه: {missing}\n"
    "{detail_lines}"
    "\nℹ️ المزامنة تُحدِّث <b>التكلفة والحدود</b> فقط — سعر البيع قرارك وحدك، ولا يُمسّ تاريخ الطلبات."
)
PROVIDER_SYNC_MISSING_LINE = "   ❓ {name} (#{service_id})\n"
PROVIDER_SYNC_COST_HEADER = "\n💲 <b>تغيّرت تكلفتها (سعر البيع كما هو):</b>\n"
PROVIDER_SYNC_COST_LINE = "   • #{service_id} {name}: {old} ⟵ {new} (هامشك الآن {margin})\n"
PROVIDER_SYNC_NEW_HEADER = "\n🆕 <b>خدمات جديدة لدى المزود</b> (استوردها من «⬇️ استيراد خدمات»):\n"
PROVIDER_SYNC_NEW_LINE = "   • {psid} — {name}\n"
PROVIDER_SYNC_DISABLED_HEADER = "\n⛔ <b>عُطِّلت لاختفائها لدى المزود</b> (ستعود تلقائياً إن عادت):\n"
PROVIDER_SYNC_RESTORED_HEADER = "\n♻️ <b>عادت لدى المزود فأُعيد تفعيلها:</b>\n"
PROVIDER_SYNC_SUSPICIOUS = (
    "\n🛑 <b>لم يُعطَّل شيء:</b> اختفاء جماعي أو قائمة فارغة من المزود يُعدّ عطلاً عنده لا حذفاً. "
    "أعد المزامنة لاحقاً.\n"
)
PROVIDER_SYNC_MORE = "   … و{count} أخرى\n"
PROVIDER_SYNC_UNSUPPORTED_HEADER = (
    "\n🚫 <b>عُطِّلت لأن نوعها لدى المزود صار غير مدعوم (غير default):</b>\n"
)
PROVIDER_SYNC_NEGATIVE_HEADER = "\n⚠️ <b>خدمات صار سعرها أقل من التكلفة:</b>\n"
PROVIDER_SYNC_NEGATIVE_LINE = "   📉 {name} — البيع {price} / التكلفة {cost}\n"

# ------------------------- استيراد خدمة من المزود ------------------------ #

PROVIDER_IMPORT_ASK_SEARCH = (
    "⬇️ <b>استيراد خدمات من {name}</b>\n\n"
    "أرسل <b>كلمة بحث</b> لتصفية قائمة المزود (مثال: <code>instagram followers</code>)\n"
    "أو أرسل <b>عدة أرقام خدمات</b> لدى المزود مفصولة بمسافة أو فاصلة (مثال: <code>101 205 330</code>)\n"
    "أو <code>*</code> لعرض القائمة كاملة.\n\n"
    "بعدها تحدّد ما تريد استيراده دفعة واحدة."
)
PROVIDER_IMPORT_RESULTS = (
    "🔎 <b>نتائج {name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "المطابق: <b>{total}</b> • المحدد: <b>{selected}</b>\n"
    "اضغط على الخدمة لتحديدها ☑️ أو إلغاء تحديدها، ثم «التالي»."
)
PROVIDER_IMPORT_CAPPED = "\n⚠️ عُرض أول {cap} نتيجة فقط من {total} — ضيّق البحث لرؤية الباقي."
PROVIDER_IMPORT_IDS_MISSING = "\n❓ أرقام غير موجودة لدى المزود: <code>{ids}</code>"
PROVIDER_IMPORT_HIDDEN_TYPES = "\n🚫 أُخفيت {count} خدمة من أنواع غير مدعومة (Package / Custom Comments / Subscriptions…)."
PROVIDER_IMPORT_NO_RESULTS = "🔍 لا خدمة تطابق «{query}» لدى هذا المزود. جرّب كلمة أخرى."
PROVIDER_IMPORT_NOTHING_SELECTED = "حدّد خدمة واحدة على الأقل أولاً"
PROVIDER_IMPORT_ASK_CATEGORY = (
    "📦 <b>تم تحديد {count} خدمة</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{lines}"
    "\nاختر التصنيف عندنا لإدراجها فيه:"
)
PROVIDER_IMPORT_ITEM_LINE = "• <code>{provider_service_id}</code> — {name} ({cost}/ألف)\n"
PROVIDER_IMPORT_MORE_LINES = "• … و{count} أخرى\n"
PROVIDER_IMPORT_ASK_MARGIN = (
    "📈 أرسل هامش الربح كرقم فقط (بلا علامة %).\n\n"
    "مثال: <code>40</code> تعني ربح 40% فوق التكلفة{example_line}\n"
    "الحد المسموح: 0 إلى 1000\n"
    "يُطبَّق نفس الهامش على كل الخدمات المحددة."
)
PROVIDER_IMPORT_MARGIN_EXAMPLE = " ⇐ تكلفة {cost} تصير بيعاً {price}"
PROVIDER_IMPORT_CONFIRM = (
    "📋 <b>تأكيد استيراد {count} خدمة</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🏷 التصنيف: {category}\n"
    "🔌 المزود: {provider}\n"
    "📈 الهامش: {margin}%\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{lines}"
)
PROVIDER_IMPORT_CONFIRM_LINE = (
    "• <code>{provider_service_id}</code> {name}\n"
    "   تكلفة {cost} ← بيع {price} (ربح {profit})\n"
)
PROVIDER_IMPORT_DONE = (
    "✅ <b>انتهى الاستيراد</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "✔️ أُنشئت: <b>{created}</b> • ⚠️ مكررة: <b>{duplicates}</b> • ❌ فشلت: <b>{failed}</b>\n"
)
PROVIDER_IMPORT_DONE_LINE = "🆔 <code>{service_id}</code> ⇐ مزود <code>{provider_service_id}</code> — {name}\n"
PROVIDER_IMPORT_DUP_LINE = "⚠️ <code>{provider_service_id}</code> {name} — مستوردة مسبقاً\n"
PROVIDER_IMPORT_FAIL_LINE = "❌ <code>{provider_service_id}</code> {name} — {reason}\n"
PROVIDER_IMPORT_SESSION_LOST = "⚠️ انتهت صلاحية نتائج البحث. أعد المحاولة من بطاقة المزود."
BTN_IMPORT_SELECT_ALL = "☑️ تحديد الكل"
BTN_IMPORT_SELECT_NONE = "⬜ مسح التحديد"
BTN_IMPORT_NEXT = "التالي ◀️ ({count})"
BTN_CONFIRM_IMPORT_BATCH = "✅ استيراد الكل"

# --------------------- إنشاء خدمة يدوياً (بلا قائمة المزود) -------------- #

SERVICE_NEW_ASK_CATEGORY = "➕ <b>خدمة جديدة</b>\n\nاختر التصنيف الذي ستُدرج فيه:"
SERVICE_NEW_ASK_PROVIDER = "🔌 اختر المزود الذي ستُرسَل إليه طلبات هذه الخدمة:"
SERVICE_NEW_ASK_PROVIDER_SERVICE_ID = (
    "🆔 أرسل رقم الخدمة لدى المزود <b>{provider}</b>.\n\n"
    "تجده في قائمة خدمات المزود (عمود <code>service</code>)."
)
SERVICE_NEW_ASK_NAME = "🛍 أرسل اسم الخدمة كما سيراه العميل (3 إلى 120 حرفاً)."
SERVICE_NEW_ASK_COST = "💵 أرسل تكلفة الألف لدى المزود (مثال: <code>0.6</code>)."
SERVICE_NEW_ASK_PRICE = (
    "💰 أرسل سعر بيع الألف للعميل.\n\n"
    "التكلفة التي أدخلتها: {cost}\n"
    "⚠️ سعر أقل من التكلفة = بيع بخسارة."
)
SERVICE_NEW_ASK_MIN = "🔢 أرسل أقل كمية مسموحة (مثال: <code>100</code>)."
SERVICE_NEW_ASK_MAX = "🔢 أرسل أكبر كمية مسموحة (أكبر من {min_q})."
SERVICE_NEW_CONFIRM = (
    "📋 <b>تأكيد إنشاء الخدمة</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🛍 الاسم: {name}\n"
    "🏷 التصنيف: {category}\n"
    "🔌 المزود: {provider} (رقم الخدمة لديه: <code>{provider_service_id}</code>)\n"
    "💵 التكلفة: {cost} / ألف\n"
    "💰 سعر البيع: {price} / ألف\n"
    "📈 الهامش: {profit} لكل ألف\n"
    "🔢 الحدود: {min_q} — {max_q}\n\n"
    "{warning}"
)
SERVICE_NEW_WARN_LOSS = "⚠️ <b>تنبيه: سعر البيع أقل من التكلفة — بيع بخسارة.</b>"
SERVICE_NEW_WARN_OK = "✅ الأرقام سليمة."
SERVICE_NEW_DONE = "✅ أُنشئت الخدمة <b>{name}</b> برقم <code>{service_id}</code> وهي مفعّلة."
SERVICE_NEW_NO_PROVIDER = (
    "⚠️ لا يوجد مزود مسجّل بعد.\n\nأضف مزوداً أولاً من قسم «🔌 المزودون»."
)
SERVICE_NEW_BAD_MAX = "❌ أكبر كمية يجب أن تكون أكبر من أقل كمية ({min_q})."
BTN_SERVICE_NEW = "➕ خدمة جديدة"

#: أسماء أنواع المزودين كما تُعرض في أزرار الاختيار
PROVIDER_TYPE_LABELS: dict[str, str] = {
    "perfect_panel": "🌐 Perfect Panel (قياسي)",
    "mock": "🧪 مزود وهمي (اختبار)",
}

PROVIDER_SERVICES_TITLE = (
    "🛍 <b>خدماتنا من {name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "العدد: {total} · الصفحة {page} من {pages}"
)
PROVIDER_KEY_TOO_SHORT = "❌ المفتاح قصير جداً (8 محارف على الأقل). أرسله كاملاً."
BTN_CONFIRM_IMPORT = "✅ نعم، استورد"

# ======================================================================== #
#                   المهام الدورية ومراقبتها (المرحلة 6)                   #
# ======================================================================== #

BTN_JOBS = "⏱ المهام الدورية"
BTN_JOB_RUN = "▶️ تشغيل الآن"

JOBS_HOME = (
    "⏱ <b>المهام الدورية</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "المهام: {total} · سليمة: {healthy} · متعثرة: {failing}\n"
    "{running_line}"
    "\n{lines}"
    "\nℹ️ هذه إحصاءات التشغيل الحالي فقط — تُصفَّر عند إعادة تشغيل البوت.\n"
    "الأخطاء نفسها محفوظة في «📋 السجلات ← الأخطاء»."
)
JOBS_RUNNING_LINE = "🏃 تعمل الآن: {names}\n"
JOBS_NONE = (
    "⏱ <b>المهام الدورية</b>\n\n"
    "لا توجد مهام مجدولة في هذه النسخة قيد التشغيل.\n"
    "إن كنت ترى هذه الرسالة والبوت يعمل فهذا خلل — راجع سجل الإقلاع."
)
JOB_LINE = (
    "{icon} <b>{label}</b>\n"
    "   ⏲ {schedule} · آخر تشغيل: {last_run}\n"
    "   🔁 جولات: {runs} · ⚠️ إخفاقات: {failures} · ⏭ تخطٍّ: {skipped}\n"
    "   ⌛️ آخر مدة: {duration} · متوسط: {average}\n"
    "{error_line}"
)
JOB_ERROR_LINE = "   🐞 آخر خطأ: <code>{error}</code>\n"
JOB_NEVER_RAN = "لم تعمل بعد"
JOB_RUN_STARTED = "▶️ شُغّلت المهمة «{label}» الآن…"
JOB_RUN_DONE = (
    "{icon} <b>انتهت المهمة «{label}»</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "⌛️ المدة: {duration}\n"
    "{result_line}"
)
JOB_RUN_OK_LINE = "✅ اكتملت بلا أخطاء."
JOB_RUN_FAIL_LINE = "❌ انتهت بخطأ: <code>{error}</code>\nالتفاصيل في «📋 السجلات ← الأخطاء»."
JOB_RUN_BUSY = "⏳ المهمة تعمل الآن بالفعل — انتظر انتهاء الجولة الحالية."
JOB_NOT_FOUND = "❌ هذه المهمة غير مجدولة في النسخة العاملة."
HEALTH_JOBS_SECTION = "\n⏱ المهام: {healthy}/{total} سليمة{failing_text}"
HEALTH_JOBS_FAILING = " · ⚠️ متعثرة: {names}"

# ======================================================================== #
#              طرق الشحن والرسوم والبحث في المدفوعات (المرحلة 7)           #
# ======================================================================== #

# --------------------------- تصفية طلبات الشحن -------------------------- #

PAYMENT_FILTER_PENDING = "⏳ معلّقة"
PAYMENT_FILTER_APPROVED = "✅ معتمدة"
PAYMENT_FILTER_REJECTED = "❌ مرفوضة"
PAYMENT_FILTER_ALL = "📋 الكل"

PAYMENTS_FILTER_TITLE = (
    "💰 <b>طلبات الشحن — {filter_name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "العدد: {count} · الصفحة {page} من {pages}"
)
PAYMENTS_FILTER_EMPTY = "📭 لا توجد طلبات شحن ضمن «{filter_name}»."

# ------------------------------ البحث ----------------------------------- #

BTN_PAYMENT_SEARCH = "🔎 بحث عن حوالة"
PAYMENT_SEARCH_ASK = (
    "🔎 <b>البحث في طلبات الشحن</b>\n\n"
    "أرسل <b>رقم العملية</b> (كلياً أو جزئياً) أو <b>رقم طلب الشحن</b>."
)
PAYMENT_SEARCH_TITLE = "🔎 <b>نتائج البحث عن «{term}»</b>\n\nعدد النتائج: {count}\n\n{lines}"
PAYMENT_SEARCH_EMPTY = (
    "🔎 لا يوجد طلب شحن مطابق لـ«{term}».\n\n"
    "تأكد من الرقم، وتذكّر أن الطلب الملغى من المستخدم يظهر أيضاً في البحث."
)

# -------------------------- الرسوم في بطاقة الطلب ----------------------- #

PAYMENT_FEE_LINE = "🧾 رسوم الطريقة: {fee}\n💵 الصافي للمستخدم: {net}\n"
PAYMENT_APPROVE_FEE_LINE = "🧾 رسوم الطريقة: {fee}\n"

# ---------------------------- شاشة طرق الشحن ---------------------------- #

MENU_PAYMENT_METHODS = "🏦 طرق الشحن"
BTN_METHODS = "🏦 طرق الشحن"
BTN_METHOD_NEW = "➕ طريقة جديدة"
BTN_METHOD_ON = "✅ تفعيل"
BTN_METHOD_OFF = "⛔ إيقاف"
BTN_METHOD_UP = "🔼 أعلى"
BTN_METHOD_DOWN = "🔽 أسفل"
BTN_METHOD_PROOF_ON = "📎 الإثبات: إجباري"
BTN_METHOD_PROOF_OFF = "📎 الإثبات: اختياري"
BTN_METHODS_REPORT = "📊 تقرير الطرق"

METHODS_HOME = (
    "🏦 <b>طرق الشحن</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "المفعّلة: {active} من {total}\n\n"
    "{lines}\n"
    "ℹ️ الترتيب هنا هو نفسه ترتيب ظهورها للمستخدم."
)
METHODS_EMPTY = (
    "🏦 <b>طرق الشحن</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "⚠️ لا توجد أي طريقة شحن بعد، ولهذا <b>لا يستطيع أي مستخدم شحن رصيده الآن</b>.\n\n"
    "اضغط «➕ طريقة جديدة» لإضافة أول طريقة (محفظة، حوالة بنكية، عملة رقمية...)."
)
METHOD_LINE = "{state} <b>{name}</b> · {fee}\n   💵 {limits} · 📎 {proof}\n"
METHOD_STATE_ON = "🟢"
METHOD_STATE_OFF = "🔴"
METHOD_PROOF_REQUIRED = "إثبات إجباري"
METHOD_PROOF_OPTIONAL = "إثبات اختياري"

METHOD_CARD = (
    "🏦 <b>{name}</b> {state}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🔖 الكود: <code>{code}</code> · النوع: {type}\n"
    "💵 الحدود: {limits}\n"
    "🧾 الرسوم: {fee}\n"
    "📎 الإثبات: {proof}\n"
    "🔢 ترتيب العرض: {sort_order}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📋 <b>التعليمات كما يراها المستخدم:</b>\n{instructions}\n\n"
    "🏧 <b>بيانات الحساب:</b>\n{account}\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📊 الطلبات: معتمدة {approved} · معلّقة {pending}\n"
    "💰 أُضيف عبرها: {total}"
)
METHOD_TYPE_LABELS = {
    "manual": "تحويل يدوي",
    "crypto": "عملة رقمية",
    "gateway": "بوابة دفع",
}
METHOD_NO_INSTRUCTIONS = "<i>(لا توجد تعليمات — المستخدم لن يعرف كيف يحوّل!)</i>"
METHOD_NO_ACCOUNT = "<i>(لا توجد بيانات حساب — المستخدم لن يعرف لمن يحوّل!)</i>"
METHOD_NOT_FOUND = "❌ طريقة الشحن غير موجودة (ربما حُذفت أو تغيّر معرّفها)."

# ------------------------- تعديل حقول طريقة الشحن ----------------------- #

BTN_METHOD_EDIT_NAME = "✏️ الاسم"
BTN_METHOD_EDIT_INSTRUCTIONS = "📋 التعليمات"
BTN_METHOD_EDIT_ACCOUNT = "🏧 بيانات الحساب"
BTN_METHOD_EDIT_MIN = "⬇️ الحد الأدنى"
BTN_METHOD_EDIT_MAX = "⬆️ الحد الأقصى"
BTN_METHOD_EDIT_FEEP = "％ رسوم نسبية"
BTN_METHOD_EDIT_FEEF = "🧾 رسوم ثابتة"

METHOD_ASK_NAME = "✏️ أرسل اسم طريقة الشحن كما سيراه المستخدم (مثال: محفظة كريمي):"
METHOD_ASK_INSTRUCTIONS = (
    "📋 أرسل <b>تعليمات التحويل</b> كما ستظهر للمستخدم.\n\n"
    "اكتبها خطوات واضحة: إلى أين يحوّل، وماذا يرسل بعد التحويل.\n"
    "الحالي: {current}"
)
METHOD_ASK_ACCOUNT = (
    "🏧 أرسل <b>بيانات الحساب</b> التي يحوّل إليها المستخدم\n"
    "(رقم المحفظة / رقم الحساب / عنوان المحفظة الرقمية).\n\n"
    "الحالي: {current}"
)
METHOD_ASK_MIN = (
    "⬇️ أرسل <b>الحد الأدنى</b> للشحن بهذه الطريقة بالعملة ({symbol}).\n"
    "أرسل <code>0</code> لاستخدام الحد العام من الإعدادات.\n\n"
    "الحالي: {current}"
)
METHOD_ASK_MAX = (
    "⬆️ أرسل <b>الحد الأقصى</b> للشحن بهذه الطريقة بالعملة ({symbol}).\n"
    "أرسل <code>0</code> لإلغاء الحد الأقصى.\n\n"
    "الحالي: {current}"
)
METHOD_ASK_FEE_PERCENT = (
    "％ أرسل <b>نسبة الرسوم</b> المقتطعة من كل حوالة (مثال: <code>2.5</code> تعني 2.5%).\n"
    "أرسل <code>0</code> لإلغاء النسبة.\n\n"
    "الحالي: {current}\n"
    "ℹ️ الرسوم تُخصم من مبلغ الحوالة، والمستخدم يرى الصافي قبل الإرسال."
)
METHOD_ASK_FEE_FIXED = (
    "🧾 أرسل <b>الرسوم الثابتة</b> المقتطعة من كل حوالة بالعملة ({symbol}).\n"
    "أرسل <code>0</code> لإلغائها.\n\n"
    "الحالي: {current}"
)
METHOD_FIELD_SAVED = "✅ حُفظ التعديل على «{field}»."
METHOD_FIELD_UNCHANGED = "ℹ️ لا تغيير — القيمة الجديدة مطابقة للحالية."

# --------------------------- إضافة طريقة جديدة -------------------------- #

METHOD_NEW_INTRO = (
    "➕ <b>إضافة طريقة شحن</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "سنأخذ 4 خطوات: الاسم ← التعليمات ← بيانات الحساب ← النوع.\n"
    "الحدود والرسوم تُضبط بعد الإنشاء من بطاقة الطريقة.\n\n"
    "✏️ أرسل الآن <b>اسم الطريقة</b> كما سيراه المستخدم:"
)
METHOD_NEW_ASK_INSTRUCTIONS = (
    "📋 أرسل <b>تعليمات التحويل</b> للمستخدم (خطوات واضحة):"
)
METHOD_NEW_ASK_ACCOUNT = "🏧 أرسل <b>بيانات الحساب</b> (رقم المحفظة/الحساب):"
METHOD_NEW_ASK_TYPE = "🏷 اختر <b>نوع الطريقة</b>:"
BTN_METHOD_TYPE_MANUAL = "🏧 تحويل يدوي"
BTN_METHOD_TYPE_CRYPTO = "🪙 عملة رقمية"
BTN_METHOD_TYPE_GATEWAY = "💳 بوابة دفع"
METHOD_NEW_CONFIRM = (
    "🧾 <b>مراجعة الطريقة الجديدة</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🏦 الاسم: {name}\n"
    "🏷 النوع: {type}\n"
    "📋 التعليمات: {instructions}\n"
    "🏧 الحساب: {account}\n"
    "📎 الإثبات: إجباري (قابل للتغيير لاحقاً)\n"
    "🧾 الرسوم: بلا رسوم (قابلة للضبط لاحقاً)\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "⚠️ ستظهر للمستخدمين فور إنشائها."
)
METHOD_CREATED = (
    "✅ <b>أُضيفت طريقة الشحن «{name}»</b>\n\n"
    "🔖 الكود الداخلي: <code>{code}</code>\n"
    "الخطوة التالية: اضبط الحدود والرسوم من بطاقة الطريقة إن لزم."
)
METHOD_TOGGLED_ON = "✅ فُعّلت طريقة الشحن «{name}» — صارت ظاهرة للمستخدمين."
METHOD_TOGGLED_OFF = (
    "⛔ أُوقفت طريقة الشحن «{name}» — لم تعد ظاهرة للمستخدمين.\n"
    "الطلبات السابقة عبرها تبقى كما هي."
)
METHOD_PROOF_TOGGLED = "📎 إثبات التحويل صار «{state}» لطريقة «{name}»."
METHOD_MOVED = "🔀 تغيّر ترتيب «{name}»."
METHOD_MOVE_EDGE = "ℹ️ هذه الطريقة في طرف القائمة أصلاً."

# ---------------------------- تقرير طرق الشحن --------------------------- #

METHODS_REPORT_TITLE = (
    "📊 <b>تقرير طرق الشحن</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{lines}\n"
    "💰 الإجمالي المضاف: {total}\n"
    "🧾 إجمالي الرسوم المقتطعة: {fees}"
)
METHODS_REPORT_LINE = (
    "{state} <b>{name}</b>\n"
    "   ✅ معتمدة: {approved} · ⏳ معلّقة: {pending}\n"
    "   💰 أُضيف: {total} · 🧾 رسوم: {fees}\n"
)
METHODS_REPORT_EMPTY = "📊 لا توجد طرق شحن لعرض تقرير عنها."


# ======================================================================== #
#        المرحلة 8 — الدعم والإشعارات والإذاعة (رسائل جماعية وقوالب)        #
# ======================================================================== #

# ------------------------------ قائمة اللوحة ---------------------------- #

MENU_BROADCAST = "📣 الإذاعة"
MENU_TEMPLATES = "✉️ قوالب الإشعارات"

# ------------------------------- الإذاعة -------------------------------- #

BROADCAST_HOME = (
    "📣 <b>الرسائل الجماعية</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{lines}\n"
    "اختر رسالة لمتابعتها، أو أنشئ رسالة جديدة."
)
BROADCAST_EMPTY = (
    "📣 <b>الرسائل الجماعية</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "لم تُرسل أي رسالة جماعية بعد.\n\n"
    "الرسالة الجماعية تصل كل من يطابق الشريحة المختارة، "
    "وتُرسل على دفعات حتى لا يحدّ تيليجرام البوت."
)
BROADCAST_LINE = "{state} #{id} · {target} · ✅ {sent}/{total}\n"

BROADCAST_STATE_DRAFT = "📝 مسودة"
BROADCAST_STATE_RUNNING = "🚀 جارية"
BROADCAST_STATE_PAUSED = "⏸ موقوفة مؤقتاً"
BROADCAST_STATE_COMPLETED = "✅ اكتملت"
BROADCAST_STATE_CANCELLED = "🚫 ملغاة"

BROADCAST_CARD = (
    "📣 <b>الرسالة الجماعية #{id}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📊 الحالة: {state}\n"
    "🎯 الشريحة: {target}\n"
    "👥 المستلمون: {total}\n"
    "✅ وصلت: {sent}\n"
    "🚫 حظروا البوت: {blocked}\n"
    "⚠️ فشلت: {failed}\n"
    "⏳ متبقٍ: {pending}\n"
    "📈 التقدم: {percent}%\n"
    "{media_line}"
    "🕒 أُنشئت: {created}\n\n"
    "📄 <b>النص:</b>\n{text}"
)
BROADCAST_MEDIA_LINE = "🖼 مرفق: صورة\n"
BROADCAST_NOT_FOUND = "❌ هذه الرسالة غير موجودة."

BROADCAST_ASK_TEXT = (
    "✍️ أرسل نص الرسالة الجماعية كما تريد أن يصل المستخدم.\n\n"
    "• يمكن أن يتكوّن من عدة أسطر.\n"
    "• أقصى طول: {limit} حرفاً.\n"
    "• لا تُرسل أي رابط دفع أو بيانات حساسة."
)
BROADCAST_ASK_MEDIA = (
    "🖼 أرسل صورة لترافق الرسالة، أو اضغط «تخطي» لإرسال نص فقط.\n\n"
    "⚠️ مع الصورة يصبح الحد الأقصى للنص {limit} حرفاً."
)
BROADCAST_MEDIA_TOO_LONG = (
    "⚠️ النص أطول من {limit} حرفاً فلا يصلح كتعليق على صورة.\n"
    "اختصر النص أو أرسل الرسالة بلا صورة."
)
BROADCAST_ASK_TARGET = (
    "🎯 <b>اختر الشريحة المستهدفة</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "{lines}\n"
    "الأعداد محسوبة الآن من قاعدة البيانات، "
    "ولا تشمل المحظورين ولا من حظر البوت."
)
BROADCAST_TARGET_LINE = "{label}: {count}\n"
BROADCAST_TARGET_EMPTY = "❌ لا يوجد مستخدمون في هذه الشريحة الآن."

BROADCAST_CONFIRM = (
    "📣 <b>مراجعة قبل الإرسال</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🎯 الشريحة: {target}\n"
    "👥 ستصل إلى: {count} مستخدم\n"
    "{media_line}"
    "⏱ الإيقاع: {batch} رسالة كل {interval} ثانية (≈ {minutes} دقيقة)\n\n"
    "📄 <b>النص كما سيصل:</b>\n{text}\n\n"
    "⚠️ بعد الضغط يبدأ الإرسال فوراً، ويمكنك إيقافه مؤقتاً أو إلغاؤه في أي لحظة."
)
BROADCAST_BTN_SEND = "🚀 إرسال الآن"
BROADCAST_STARTED = (
    "🚀 بدأ إرسال الرسالة #{id} إلى {count} مستخدم.\n"
    "تابع التقدم من بطاقة الرسالة (زر 🔄 تحديث)."
)
BROADCAST_PAUSED = "⏸ أُوقفت الرسالة #{id} مؤقتاً. المتبقون لن تصلهم حتى الاستئناف."
BROADCAST_RESUMED = "▶️ استُؤنف إرسال الرسالة #{id}."
BROADCAST_CANCELLED = "🚫 أُلغيت الرسالة #{id}. من وصلته الرسالة تبقى عنده."
BROADCAST_NOTHING_TO_DO = "⚠️ لا جديد: الرسالة ليست في حالة تسمح بهذا الإجراء."

BTN_BROADCAST_NEW = "✍️ رسالة جديدة"
BTN_BROADCAST_START = "🚀 بدء الإرسال"
BTN_BROADCAST_RESUME = "▶️ استئناف"
BTN_BROADCAST_PAUSE = "⏸ إيقاف مؤقت"
BTN_BROADCAST_CANCEL = "🚫 إلغاء الرسالة"
BTN_BROADCAST_SKIP_MEDIA = "⏭ بلا صورة"

# -------------------------- قوالب الإشعارات ----------------------------- #

TEMPLATES_HOME = (
    "✉️ <b>قوالب الإشعارات</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "هذه نصوص الرسائل التي تصل عملاءك تلقائياً.\n"
    "✏️ معدّلة: {customized} من {total}\n\n"
    "{lines}\n"
    "اختر قالباً لعرضه أو تعديله. التنبيهات الداخلية للإدارة غير قابلة للتعديل."
)
TEMPLATES_GROUP_LINE = "\n<b>{group}</b>\n"
TEMPLATE_LINE = "{state} {name}\n"
TEMPLATE_STATE_DEFAULT = "▫️"
TEMPLATE_STATE_CUSTOM = "✏️"
TEMPLATE_STATE_OFF = "⏸"

TEMPLATE_CARD = (
    "✉️ <b>{name}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📊 الحالة: {state}\n"
    "🔤 المتغيرات المتاحة: {variables}\n\n"
    "📌 <b>العنوان:</b>\n{title}\n\n"
    "📄 <b>النص:</b>\n{body}"
)
TEMPLATE_STATE_TEXT_DEFAULT = "النص الافتراضي المدمج"
TEMPLATE_STATE_TEXT_CUSTOM = "نص مخصّص (مفعّل)"
TEMPLATE_STATE_TEXT_PAUSED = "نص مخصّص موقوف — يُستعمل الافتراضي"
TEMPLATE_NO_VARIABLES = "لا متغيرات"

TEMPLATE_PREVIEW = (
    "👁 <b>معاينة بقيم تجريبية</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "<b>{title}</b>\n\n{body}\n\n"
    "ℹ️ هذه معاينة فقط — لم تُرسل لأي مستخدم."
)
TEMPLATE_ASK_TITLE = (
    "📌 أرسل العنوان الجديد للقالب «{name}».\n\n"
    "العنوان الحالي:\n{current}\n\n"
    "المتغيرات المتاحة: {variables}"
)
TEMPLATE_ASK_BODY = (
    "📄 أرسل النص الجديد للقالب «{name}» (يمكن أن يكون عدة أسطر).\n\n"
    "النص الحالي:\n{current}\n\n"
    "المتغيرات المتاحة: {variables}\n"
    "⚠️ اكتب المتغير كما هو بين قوسين، وأي متغير غير معروف سيُرفض."
)
TEMPLATE_SAVED = "✅ حُفظ القالب «{name}» وسيُستعمل في الرسائل القادمة فوراً."
TEMPLATE_RESET_DONE = "↩️ عاد القالب «{name}» إلى نصه الافتراضي."
TEMPLATE_RESET_NOTHING = "ℹ️ هذا القالب يستخدم النص الافتراضي أصلاً."
TEMPLATE_ENABLED = "✅ فُعِّل النص المخصّص للقالب «{name}»."
TEMPLATE_DISABLED = "⏸ أُوقف النص المخصّص — عاد القالب للنص الافتراضي."
TEMPLATE_NOT_FOUND = "❌ هذا القالب غير موجود."

BTN_TEMPLATE_EDIT_TITLE = "📌 تعديل العنوان"
BTN_TEMPLATE_EDIT_BODY = "📄 تعديل النص"
BTN_TEMPLATE_PREVIEW = "👁 معاينة"
BTN_TEMPLATE_RESET = "↩️ استعادة الافتراضي"
BTN_TEMPLATE_DISABLE = "⏸ إيقاف التخصيص"
BTN_TEMPLATE_ENABLE = "✅ تفعيل التخصيص"
BTN_TEMPLATES_HOME = "✉️ القوالب"

# --------------------------- أولوية التذاكر ------------------------------ #

TICKET_PRIORITY_LINE = "🚦 الأولوية: {priority}\n"
TICKET_PRIORITY_LOW = "🟢 منخفضة"
TICKET_PRIORITY_NORMAL = "🟡 عادية"
TICKET_PRIORITY_HIGH = "🔴 عالية"
TICKET_PRIORITY_SET = "🚦 صارت أولوية التذكرة #{ticket_id}: {priority}"
TICKET_PRIORITY_SAME = "ℹ️ التذكرة بهذه الأولوية أصلاً."
TICKET_FILTER_HIGH = "🔴 العاجلة"


# ======================================================================== #
#                        شاشة الأمان (المرحلة 9)                           #
# ======================================================================== #

MENU_SECURITY = "🛡️ الأمان"
BTN_SECURITY_EVENTS = "📜 الأحداث الأمنية"
BTN_SECURITY_BLOCKS = "⏱ الموقوفون مؤقتاً"
BTN_SECURITY_TEAM = "👥 طاقم الإدارة"
BTN_SECURITY_UNBLOCK = "🔓 رفع الإيقاف"

SECURITY_LEVEL_ICONS: dict[str, str] = {"ok": "✅", "warn": "⚠️", "bad": "⛔"}

SECURITY_HOME = (
    "🛡️ <b>الأمان</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "<b>آخر 24 ساعة</b>\n"
    "• محاولات بلا صلاحية: <b>{denied}</b>\n"
    "• إيقافات مؤقتة (ضغط زائد): <b>{blocks}</b>\n"
    "• حواجز الأدوار والصلاحيات: <b>{rbac}</b>\n"
    "• حواجز مالية (سقف/اعتماد زائد): <b>{money}</b>\n"
    "• إجمالي الأحداث الأمنية: <b>{total}</b>\n"
    "{top_denied}\n"
    "<b>وضع الأمان</b> — {summary}\n\n"
    "{checks}"
)
SECURITY_CHECK_LINE = "{icon} <b>{title}</b>\n      {detail}"
SECURITY_SUMMARY_OK = "كل الفحوص سليمة"
SECURITY_SUMMARY_ISSUES = "{bad} خطر · {warn} تنبيه"
SECURITY_TOP_DENIED = "• الأكثر محاولة بلا صلاحية: {items}\n"

SECURITY_EVENTS_TITLE = (
    "📜 <b>الأحداث الأمنية</b> — صفحة {page}/{pages}\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n{lines}"
)
SECURITY_EVENTS_EMPTY = "📜 <b>الأحداث الأمنية</b>\n\nلا توجد أحداث أمنية مسجَّلة بعد — وهذا جيد."
SECURITY_EVENT_LINE = "🔐 <b>{label}</b>\n      {who} · {target} · {when}"

#: اسم عربي مقروء لكل حدث أمني (الغائب يُعرض كما هو)
SECURITY_EVENT_LABELS: dict[str, str] = {
    "permission_denied": "رفض صلاحية",
    "hierarchy_denied": "منع التصرف على أعلى منه رتبة",
    "self_action_blocked": "منع تنفيذ ذاتي",
    "self_role_change_blocked": "منع تغيير دور نفسه",
    "role_escalation_blocked": "منع رفع دور فوق المسموح",
    "last_super_admin_protected": "حماية آخر أدمن أعلى",
    "self_permission_change_blocked": "منع تعديل صلاحيات نفسه",
    "grant_unowned_permission_blocked": "منع منح صلاحية لا يملكها",
    "grant_dangerous_permission_blocked": "منع منح صلاحية خطرة",
    "self_ban_blocked": "منع حظر النفس",
    "super_admin_ban_blocked": "منع حظر أدمن أعلى",
    "over_credit_blocked": "منع اعتماد مبلغ أكبر من المطلوب",
    "adjust_cap_exceeded": "تجاوز سقف التسوية",
    "adjust_daily_cap_exceeded": "تجاوز السقف اليومي للتسويات",
    "rate_limit_block": "إيقاف مؤقت (ضغط زائد)",
    "block_cleared": "رفع إيقاف مؤقت",
    "ssrf_blocked": "حجب رابط مزود غير آمن",
}

SECURITY_BLOCKS_TITLE = (
    "⏱ <b>الموقوفون مؤقتاً</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n{lines}\n"
    "<i>الإيقاف في الذاكرة ويزول تلقائياً بانتهاء مدته أو بإعادة تشغيل البوت.</i>"
)
SECURITY_BLOCKS_EMPTY = (
    "⏱ <b>الموقوفون مؤقتاً</b>\n\nلا أحد موقوف الآن."
)
SECURITY_BLOCK_LINE = "• <b>{name}</b> (<code>{telegram_id}</code>) — متبقٍ {left} · مخالفات {strikes}"
SECURITY_UNBLOCKED = "🔓 رُفع الإيقاف عن <b>{name}</b>."
SECURITY_UNBLOCK_NOT_BLOCKED = "هذا المستخدم لم يعد موقوفاً."

SECURITY_TEAM_TITLE = (
    "👥 <b>طاقم الإدارة</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n{lines}\n"
    "<i>تغيير الأدوار والصلاحيات من «المستخدمون».</i>"
)
SECURITY_TEAM_EMPTY = "👥 <b>طاقم الإدارة</b>\n\nلا يوجد طاقم إدارة مسجَّل."
SECURITY_TEAM_LINE = "{icon} <b>{name}</b> — {role}{extras}"
SECURITY_ROLE_LABELS: dict[str, str] = {
    "super_admin": "أدمن أعلى",
    "admin": "أدمن",
    "support": "دعم فني",
}


# ======================================================================== #
#                 النسخ الاحتياطي والاستعادة (المرحلة 10)                  #
# ======================================================================== #

MENU_BACKUP = "💾 النسخ الاحتياطي"
BTN_BACKUP_NEW = "🆕 نسخة الآن"
BTN_BACKUP_LIST = "📋 سجل النسخ"
BTN_BACKUP_VACUUM = "🧹 ضغط القاعدة"
BTN_BACKUP_GUIDE = "📖 دليل الاستعادة"
BTN_BACKUP_VERIFY = "🔍 فحص النسخة"
BTN_BACKUP_CHANNEL = "📤 إرسال للقناة"
BTN_BACKUP_DOWNLOAD = "⬇️ تنزيل لمحادثتي"
BTN_BACKUP_CONFIRM_DL = "✅ نعم، أرسل الملف"
BTN_BACKUP_CONFIRM_VAC = "✅ نعم، اضغط القاعدة"

BACKUP_STATUS_LABELS: dict[str, str] = {
    "ok": "✅ سليمة",
    "failed": "❌ فاشلة",
    "corrupt": "⛔ تالفة",
    "missing": "❓ الملف مفقود",
    "purged": "🗑 حُذف ملفها (الاحتفاظ)",
}
BACKUP_TYPE_LABELS: dict[str, str] = {
    "manual": "يدوية",
    "scheduled": "مجدولة",
    "pre_operation": "قبل عملية",
}

BACKUP_HOME = (
    "💾 <b>النسخ الاحتياطي</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "{health}\n\n"
    "• آخر نسخة سليمة: <b>{last}</b>\n"
    "• النسخ السليمة المحفوظة: <b>{ok_count}</b> ({ok_size})\n"
    "• نسخ بها مشكلة: <b>{bad_count}</b>\n"
    "• النسخ التلقائي: <b>{auto}</b>\n"
    "• الاحتفاظ: <b>{retention} يوماً</b> (لا يقل عن {min_keep} نسخ)\n"
    "• نسخة خارج السيرفر: <b>{offsite}</b>\n"
    "• حجم القاعدة: <b>{db_size}</b> · المتاح على القرص: <b>{free}</b>\n"
    "{notice}"
)
BACKUP_HEALTH_OK = "✅ النسخ الاحتياطي سليم"
BACKUP_HEALTH_NONE = "⛔ لا توجد أي نسخة سليمة بعد — خذ نسخة الآن"
BACKUP_HEALTH_OVERDUE = "⚠️ النسخ متأخر عن موعده"
BACKUP_HEALTH_AUTO_OFF = "⚠️ النسخ التلقائي معطّل — أنت تعتمد على النسخ اليدوي"
BACKUP_AUTO_ON = "كل {hours} ساعة"
BACKUP_AUTO_OFF = "معطّل"
BACKUP_OFFSITE_ON = "✅ تُرسل للقناة"
BACKUP_OFFSITE_NO_CHANNEL = "⚠️ لا — BACKUP_CHANNEL_ID غير مضبوط (النسخ على نفس السيرفر فقط)"
BACKUP_OFFSITE_DISABLED = "⚠️ لا — الإرسال للقناة معطّل في الإعدادات"
BACKUP_NEVER = "لا شيء بعد"

BACKUP_LIST_TITLE = "📋 <b>سجل النسخ</b> — صفحة {page}/{pages}\n━━━━━━━━━━━━━━━━━━━━\n\n{lines}"
BACKUP_LIST_EMPTY = "📋 <b>سجل النسخ</b>\n\nلا توجد نسخ مسجَّلة بعد."
BACKUP_LIST_LINE = "{status} <b>#{id}</b> · {type} · {size}\n      {when}{channel}"
BACKUP_LIST_CHANNEL_MARK = " · 📤"

BACKUP_VIEW = (
    "💾 <b>نسخة #{id}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "• الحالة: {status}\n"
    "• النوع: <b>{type}</b>\n"
    "• الملف: <code>{filename}</code>\n"
    "• الحجم: <b>{size}</b>\n"
    "• أُنشئت: <b>{created}</b> — بواسطة {by}\n"
    "• إصدار المخطَّط: <code>{schema}</code>\n"
    "• آخر فحص: <b>{verified}</b>\n"
    "• خارج السيرفر: <b>{channel}</b>\n"
    "• البصمة: <code>{sha}</code>\n"
    "{error}{notice}"
)
BACKUP_VIEW_ERROR = "\n⚠️ <b>سبب المشكلة:</b> {error}\n"
BACKUP_VIEW_NEVER = "لم تُفحص بعد"
BACKUP_VIEW_CHANNEL_SENT = "أُرسلت {when}"
BACKUP_VIEW_CHANNEL_NO = "لم تُرسل"
BACKUP_BY_SYSTEM = "النظام"

BACKUP_CREATED = "\n✅ تم إنشاء النسخة <b>#{id}</b> ({size}).\n"
BACKUP_CREATED_CHANNEL_FAIL = "⚠️ لكن إرسالها للقناة فشل — ستُعاد المحاولة تلقائياً.\n"
BACKUP_VERIFY_OK = "\n✅ الفحص ناجح: {message}\n"
BACKUP_VERIFY_FAIL = "\n⛔ الفحص فشل: {message}\n"
BACKUP_CHANNEL_DONE = "\n📤 أُرسلت النسخة إلى قناة النسخ.\n"
BACKUP_DOWNLOAD_DONE = "\n⬇️ أُرسل الملف إلى محادثتك — احذفه بعد حفظه.\n"
BACKUP_DOWNLOAD_ASK = (
    "⚠️ <b>تنزيل نسخة #{id}</b>\n\n"
    "الملف يحوي <b>كل بيانات النظام</b>: المستخدمون، الأرصدة، الطلبات، ومفاتيح المزودين "
    "(مشفّرة بـ<code>ENCRYPTION_KEY</code>). من يملكه مع المفتاح يملك النظام.\n\n"
    "• لا تُحوّله لأي أحد ولا تحفظه في مكان غير مشفّر.\n"
    "• يُسجَّل التنزيل في سجل التدقيق باسمك.\n\n"
    "هل تريد إرساله إلى هذه المحادثة؟"
)
BACKUP_VACUUM_ASK = (
    "🧹 <b>ضغط قاعدة البيانات</b>\n\n"
    "يُعيد بناء الملف ليسترد المساحة الفارغة. أثناء الضغط (ثوانٍ لقاعدة صغيرة، وأكثر للكبيرة) "
    "تتوقف الكتابة فيتأخر البوت قليلاً.\n\n"
    "سأأخذ <b>نسخة أمان</b> أولاً، وإن فشلت يُلغى الضغط. المتابعة؟"
)
BACKUP_VACUUM_DONE = (
    "\n🧹 تم الضغط: <b>{before}</b> ← <b>{after}</b>\n"
    "نسخة الأمان: <b>#{safety}</b>\n"
)
BACKUP_NOT_FOUND = "❌ هذه النسخة غير موجودة."

BACKUP_GUIDE = (
    "📖 <b>دليل استعادة نسخة</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "الاستعادة تتم <b>من السيرفر والبوت متوقف</b> — ليست زراً هنا عمداً، حتى لا يُستغل "
    "حساب أدمن مخترَق في إرجاع النظام لحالة قديمة.\n\n"
    "<b>الخطوات:</b>\n"
    "1) أوقف البوت.\n"
    "2) اعرض النسخ: <code>python -m scripts.restore_backup --list</code>\n"
    "3) استعد: <code>python -m scripts.restore_backup --latest</code>\n"
    "    أو <code>--id 12</code> أو <code>--file المسار</code>\n"
    "4) اكتب <code>RESTORE</code> عند السؤال.\n"
    "5) شغّل البوت.\n\n"
    "<b>ما يفعله السكربت:</b> يتحقق من البصمة والسلامة والمخطَّط، يحفظ القاعدة الحالية "
    "(لا يحذفها)، يستبدل الملف ذرّياً، ويسجّل العملية في التدقيق.\n\n"
    "<b>على سيرفر جديد:</b> انسخ ملف النسخة من قناة النسخ، ضع <code>.env</code> "
    "<b>بنفس ENCRYPTION_KEY</b> (بدونه لا تُفك مفاتيح المزودين)، ثم نفّذ الأمر أعلاه بـ<code>--file</code>.\n\n"
    "⚠️ كل ما حدث بعد وقت النسخة يضيع. راجع طلبات المزود والشحنات المعلّقة بعد الاستعادة."
)


# ======================================================================== #
#                      شاشة الإحصائيات (المرحلة 10)                        #
# ======================================================================== #

MENU_STATS = "📈 الإحصائيات"
BTN_STATS_SERVICES = "🏆 الخدمات"
BTN_STATS_BUYERS = "👥 العملاء"
BTN_STATS_DAILY = "📅 يومياً"
BTN_STATS_WALLET = "💼 المحفظة"
BTN_STATS_EXPORT = "📤 تصدير CSV"
BTN_STATS_EXPORT_ORDERS = "🧾 الطلبات (CSV)"
BTN_STATS_EXPORT_DAILY = "📅 الملخص اليومي (CSV)"
BTN_STATS_EXPORT_CONFIRM = "✅ نعم، صدّر وأرسل الملف"

STATS_HOME = (
    "📈 <b>الإحصائيات — {label}</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "🧾 الطلبات: <b>{orders}</b> (جارية {active} · منتهية {finished})\n"
    "✅ نسبة النجاح: <b>{success}</b>\n\n"
    "💰 إجمالي المخصوم: <b>{gross}</b>\n"
    "↩️ المسترجَع: <b>{refund}</b>\n"
    "💵 <b>الإيراد الصافي: {net}</b>\n"
    "🧮 متوسط الطلب (صافي): <b>{avg}</b>\n"
    "{profit}\n"
    "👥 مشترون: <b>{buyers}</b> · مستخدمون جدد: <b>{new_users}</b>\n"
    "💳 إيداعات معتمدة: <b>{deposits}</b>\n"
    "➕ إضافات يدوية: <b>{credit}</b> · ➖ خصومات يدوية: <b>{debit}</b>\n\n"
    "ℹ️ <i>الفترة بوقت إنشاء الطلب وبتوقيت عدن. الصافي = المخصوم − المسترجَع.</i>"
)
STATS_PROFIT_LINE = (
    "\n📈 الربح التقديري: <b>{profit}</b>\n"
    "      تكلفة المزود: {cost} · تغطية {pct}% ({covered}/{eligible} طلباً منتهياً)\n"
)
STATS_PROFIT_NONE = "\n📈 الربح التقديري: <b>غير محسوب</b>\n      لا طلبات منتهية بتكلفة مزود مسجّلة في هذه الفترة.\n"
STATS_PROFIT_PARTIAL_NOTE = "      ⚠️ الأرقام تخص الطلبات المغطّاة فقط، لا كل الطلبات.\n"
STATS_NO_SUCCESS = "— (لا طلبات منتهية)"

STATS_SERVICES_TITLE = "🏆 <b>أكثر الخدمات طلباً — {label}</b>\n━━━━━━━━━━━━━━━━━━━━\n\n{lines}"
STATS_SERVICES_LINE = "{rank}. <b>{name}</b>\n      {count} طلب · صافي {net}"
STATS_SERVICES_EMPTY = "🏆 <b>أكثر الخدمات طلباً — {label}</b>\n\nلا طلبات في هذه الفترة."

STATS_BUYERS_TITLE = "👥 <b>أكثر العملاء إنفاقاً — {label}</b>\n━━━━━━━━━━━━━━━━━━━━\n\n{lines}"
STATS_BUYERS_LINE = "{rank}. <b>{name}</b>\n      {count} طلب · صافي {net}"
STATS_BUYERS_EMPTY = "👥 <b>أكثر العملاء إنفاقاً — {label}</b>\n\nلا إنفاق صافٍ في هذه الفترة."

STATS_DAILY_TITLE = "📅 <b>يومياً — {label}</b>\n━━━━━━━━━━━━━━━━━━━━\n\n{lines}\n\n{footer}"
STATS_DAILY_LINE = "<code>{day}</code> {bar} {count} طلب · {net}"
STATS_DAILY_EMPTY = "📅 <b>يومياً — {label}</b>\n\nلا طلبات في هذه الفترة."
STATS_DAILY_FOOTER = "المجموع: <b>{count}</b> طلب · صافي <b>{net}</b>"
STATS_DAILY_CUT = "\n(عُرضت أحدث {shown} يوماً من {total}؛ المجموع أدناه يشمل الكل)"

STATS_WALLET = (
    "💼 <b>التزامات المحفظة</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "💳 مجموع أرصدة العملاء الآن: <b>{balance}</b>\n"
    "   (هذا ما تدين به لهم)\n"
    "➕ إجمالي ما أُودع عبر الشحن: <b>{deposits}</b>\n"
    "🛒 إجمالي ما أُنفق على الطلبات: <b>{spent}</b>"
)

STATS_EXPORT_MENU = (
    "📤 <b>تصدير CSV — {label}</b>\n\n"
    "اختر التقرير. الملفات تحوي بيانات تجارية حسّاسة، وكل تصدير يُسجَّل في التدقيق باسمك.\n"
    "• لا يشمل روابط العملاء ولا معرّفات تيليجرام.\n"
    "• الحد الأقصى {cap} صفاً للملف."
)
STATS_EXPORT_ASK = (
    "⚠️ <b>تأكيد التصدير</b>\n\n"
    "التقرير: <b>{kind}</b>\n"
    "الفترة: <b>{label}</b>\n\n"
    "سيُرسل الملف إلى هذه المحادثة. لا تحوّله لمن لا يحق له رؤية الأرقام. المتابعة؟"
)
STATS_EXPORT_KIND_LABELS: dict[str, str] = {"orders": "الطلبات", "daily": "الملخص اليومي"}
STATS_EXPORT_CAPTION = "📤 {kind} — {label}\nالصفوف: {rows}{cut}"
STATS_EXPORT_CUT = " ⚠️ قُطع عند الحد الأقصى — ضيّق الفترة للحصول على الكل."
STATS_EXPORT_DONE = "✅ أُرسل الملف ({rows} صفاً)."


# ============================ القنوات (المرحلة 13) ============================ #

MENU_CHANNELS = "📢 القنوات"
CHANNELS_HOME = (
    "📢 <b>القنوات</b>\n\n"
    "🔒 الاشتراك الإجباري: <b>{required}</b>\n"
    "{subscription_lines}\n\n"
    "📤 <b>وجهات النشر</b>\n"
    "{destination_lines}\n\n"
    "📬 الصندوق: {outbox}\n\n"
    "ℹ️ قناة النسخ الاحتياطي مخصصة للنسخ فقط ولا يُنشر فيها غيرها."
)
CHANNELS_REQUIRED_ON = "مفعّل"
CHANNELS_REQUIRED_OFF = "معطّل"
CHANNELS_LINE = "{icon} {label}: {value}"
CHANNELS_UNSET = "غير مضبوطة"
CHANNELS_OUTBOX = "بانتظار {queued} · أُرسل {sent} · فشل {failed} · متجاوَز {skipped}"
CHANNELS_ALERT_LABEL = "🔔 تنبيهات الإدارة + المستخدمون الجدد"
CHANNELS_ORDERS_LABEL = "🧾 توثيق الطلبات"
CHANNELS_BACKUP_LABEL = "💾 النسخ الاحتياطي (من البيئة)"

BTN_CHANNELS_CHECK = "🔍 فحص الاتصال الآن"
BTN_CHANNELS_TEST_ALERT = "🧪 اختبار التنبيهات"
BTN_CHANNELS_TEST_ORDERS = "🧪 اختبار التوثيق"
BTN_CHANNELS_EDIT = "⚙️ تعديل القنوات"

CHANNELS_CHECK_TITLE = "🔍 <b>نتيجة فحص القنوات</b>\n\n{lines}\n\nيُفحص: وجود القناة، وكون البوت مشرفاً فيها، وصلاحية النشر للوجهات."
CHANNELS_CHECK_OK = "✅ {label}: {value} — سليمة{title}"
CHANNELS_CHECK_BAD = "❌ {label}: {value}\n   السبب: {problem}{hints}"
CHANNELS_CHECK_UNKNOWN = "⚠️ {label}: {value} — {problem}"
CHANNELS_CHECK_UNSET = "➖ {label}: غير مضبوطة"
CHANNELS_HINT = "\n   ↳ {hint}"
CHANNELS_TEST_OK = "✅ أُرسلت رسالة الاختبار إلى {label}."
CHANNELS_TEST_FAIL = "❌ تعذّر الإرسال إلى {label}: {reason}"
CHANNELS_TEST_NO_DEST = "➖ {label} غير مضبوطة (أو تتعارض مع قناة النسخ): {reason}"
CHANNELS_TEST_TITLE = "🧪 اختبار القناة"
CHANNELS_TEST_BODY = "رسالة اختبار من لوحة التحكم — يمكنك تجاهلها."
