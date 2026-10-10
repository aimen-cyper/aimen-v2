# تقرير المرحلة الأولى من «ملاحظات التطوير والتحسين v1.0.1» — الإصدار 1.1.0

> **الحالة: اكتملت المرحلة الأولى (Critical + أساسية — 13 بنداً). المرحلة الثانية (14–20) لم تبدأ وتنتظر موافقتك.**
> **حدود الاختبار (بصراحة):** لا يتوفر لي توكن بوت حقيقي ولا قناة تيليجرام حقيقية ولا مزود حقيقي. كل ما يخص Telegram اختُبر عبر
> `FakeBot` الذي يحاكي واجهة PTB بما فيها الأخطاء (`Forbidden`, `BadRequest: Chat not found`, `TimedOut`, `Conflict`)،
> وكل ما يخص قاعدة البيانات اختُبر على SQLite حقيقية مؤقتة. **اختبار الاشتراك الفعلي وإرسال القنوات على حسابك هو الخطوة الوحيدة
> المتبقية عليك** (قائمة التحقق في آخر التقرير).

---

## 1) نتيجة الاختبارات

| الفحص | النتيجة |
|---|---|
| الحزمة الكاملة (`pytest tests`) | **1947 passed، 0 failed** (كانت 1790 في 1.0.1 ⇒ +157) |
| الاختبارات الجديدة للمرحلة | 141: قنوات/اشتراك/توثيق (29) · تشغيل/Render/Conflict/Health (17) · بطاقة الخدمة/المفضلة/الدولار (9) · الأدمن: استيراد دفعة/تعديل العرض/الهامش/الصرف/الرابط في الطلب (25) · قواعد الروابط (61) |
| `ruff --select F401,F841,E9` | نظيف |
| `scripts.boot_check` | 155 معالجاً، 31 محادثة، **314 زراً بلا أي زر ميت**، 12 مهمة (تحذيران متوقعان في بيئة فارغة: لا طريقة شحن، لا خدمات) |
| `scripts.demo_cycle` | الدورة الكاملة + مسار الفشل/الاسترجاع/الإشعار: «دون فقدان أي مبلغ» |
| `scripts.audit_ledger` | **0 فحص فاشل · 0 تنبيه · 12 سليم** |
| الأرقام الجديدة | schema 0011 · 71 إعداداً · 18 خدمة · 47 صلاحية · `APP_VERSION=1.1.0` |

أوامر التكرار (من مجلد المشروع): `python -m pytest -q -p no:warnings -o addopts="" tests` · `python -m scripts.boot_check` ·
`python -m scripts.demo_cycle` · `python -m scripts.audit_ledger`.

---

## 2) البنود الثلاثة عشر: ما نُفِّذ وأين وكيف اختُبر

| # | البند | ما نُفِّذ | أبرز الملفات | الاختبار |
|---|---|---|---|---|
| 1 | اشتراك إجباري بـ4 قنوات | بوابة في الطبقة الوسيطة تتحقق فعلياً بـ`getChatMember`؛ العضو/المشرف/المالك فقط يُعدّ مشتركاً (`left`/`kicked`/`restricted غير عضو` ⇒ لا)؛ زر «✅ تحقق» يتجاوز الكاش؛ قنوات الأربع تُضبط من «📢 القنوات» أو الإعدادات؛ **fail-closed** عند تعذّر التحقق مع تنبيه أدمن مرة واحدة؛ الفريق الإداري معفى؛ فترة سماح قصيرة لمن تحقق منه حديثاً عند خطأ شبكة | `services/subscription_service.py`، `middlewares/context.py`، `handlers/common/navigation.py`، `keyboards/user_kb.py`، `utils/channel_ref.py` | `test_phase13_channels.py` (13 اختباراً: غير مشترك/جزئي/غادر/مطرود/مشترك كامل/كاش/زر التحقق/chat-not-found/البوت ليس مشرفاً/شبكة/إعفاء الإدارة/تعطيل/تطبيع المعرفات) |
| 2 | إشعار «مستخدم جديد» للإدارة | بالقالب المطلوب (👤 مستخدم جديد 🔥، رقم الحساب، الاسم، Username، Telegram ID **مقنّع**، التسجيل، إجمالي المستخدمين) إلى `admin_alert_chat_id`، وإن لم توجد قناة ⇒ رسالة خاصة للأدمن؛ فشل الإرسال لا يمنع تسجيل المستخدم؛ قابل للإيقاف بإعداد | `services/user_service.py`، `texts/channel_posts.py`، `utils/privacy.py` | 4 اختبارات (قناة/بديل خاص/تعطيل/فشل لا يكسر التسجيل) |
| 3 | قناة توثيق الطلبات | منشور «🔥 طلب جديد» (القسم، الخدمة، رقم الطلب، الكمية، السعر ريال و$، العميل والرابط **مقنّعان**) إلى `orders_log_chat_id` عبر طابور دائم `channel_outbox` (إعادة محاولة تدريجية، منع التكرار بـ`order:{id}`)؛ لا يحوي أي سر؛ فشله لا يكسر الطلب | `services/channel_service.py`، `services/order_service.py`، `database/repositories/channel_outbox.py` | 6 اختبارات (بلا أسرار، بلا وجهة، كل نوع لوجهته، فشل دائم بلا حلقة، فشل مؤقت يُعاد) |
| 4 | قناة النسخ («Chat not found») | المعرّف يُطبَّع (`-100…`/`@name`/رابط)، **رابط الدعوة `t.me/+…` مرفوض بشرح السبب**، رفض تطابق وجهة أخرى مع قناة النسخ، رسالة تشخيص عربية عند فشل الإرسال تذكر السبب والحل، **وللنسخ فقط** (لا تنبيهات ولا توثيق فيها)؛ زر «🔍 فحص» في «📢 القنوات» | `utils/channel_ref.py`، `services/backup_service.py`، `services/channel_service.py::diagnose`، `handlers/admin/channels.py` | `test_destination_equal_to_backup_channel_is_refused`، `test_backup_delivery_error_explains_chat_not_found`، `test_diagnose_…`، شاشات الأدمن (2) |
| 5 | صفحة تفاصيل الخدمة | اسم · 🆔 رقم الخدمة · السعر/1000 بالدولار + ما يعادله + سعر الصرف · السرعة/الجودة/الضمان · الحدّان · الرصيد · «غير محددة» للناقص · أزرار 🛒 طلب / ⭐ مفضلة / 🔙 | `handlers/user/catalog.py::show_service_card`، `texts/ar.py::SERVICE_CARD`، `keyboards/user_kb.py` | `test_phase13_service_card.py` (بطاقة بحقول ناقصة، بحقول مضبوطة، الأزرار) |
| 6 | الدولار أساسي | الدولار يُعرض أولاً مع «💴 ما يعادل: 530 ريال» (يحذف `.00`) في: البطاقة، أزرار القوائم، ملخص الطلب، رسالة نجاح الطلب، منشور التوثيق، بطاقة الأدمن. **المقابل بالريال هو السعر الحقيقي المخزَّن المخصوم فعلاً**، والدولار مشتق منه بـ`usd_rate`؛ فلا ينتج اختلاف عن السعر النهائي. الرصيد يبقى بالريال | `utils/formatters.py` (`price_pair`، `local_amount`)، `core/money.py` | `test_price_pair_is_dollar_first_and_consistent`، `test_local_amount_drops_trailing_zeros` |
| 7 | تحسين /start | رسالة **واحدة** (ترحيب + قائمة) بدل رسالتين، حذف أمر `/start` والقائمة السابقة، تنقل بالتحرير (`edit`) لا برسائل جديدة، ترحيب مرتب بخطوتين، قائمة Inline من 7 أزرار (الخدمات · المفضلة · المحفظة · طلباتي · الدعم · حسابي · معلومات) | `handlers/common/navigation.py`، `texts/ar.py`، `keyboards/user_kb.py` | `test_start_sends_one_message_and_cleans_previous_menu` وتحديث اختبار القائمة (7 أزرار) |
| 8 | رقم الخدمة والربط | للمستخدم: `#id` في البطاقة وفي كل زر خدمة. للأدمن: بطاقة بقسم «🔗 الربط»: **الخدمة عندنا `#id` ⇐ المزود (`#provider_id`) ⇐ رقمها لدى المزود**؛ وقائمة خدمات الأدمن تُظهر `#id`؛ حقول السرعة/الجودة/الضمان/قاعدة الرابط قابلة للتعديل ومُدقَّقة | `handlers/admin/catalog.py`، `texts/admin_ar.py`، `keyboards/admin_kb.py`، `services/catalog_service.py::admin_set_display_field` | `test_admin_card_shows_three_way_link_and_unset_fields`، `test_edit_display_fields_and_rule_via_conversation`، `test_edit_display_is_audited_and_permission_checked` |
| 9 | استيراد دفعة | **ثلاث طرق**: كلمة بحث، **عدة أرقام خدمات لدى المزود** (مسافة/فاصلة/سطر، أرقام عربية مقبولة؛ تُحدَّد تلقائياً وتُعرض الأرقام غير الموجودة)، أو `*`. اختيار متعدد ☑️/⬜ مع صفحات وتحديد الكل/مسح. تصنيف وهامش واحد للدفعة. كل خدمة في معاملتها: **المكرر والمعيب لا يُسقطان الباقي**، تكرار الرقم داخل الدفعة يُتجاهل، حد 50 للدفعة، تقرير لكل عنصر «🆔 الرقم الداخلي ⇐ مزود الرقم»، تدقيق للدفعة | `handlers/admin/providers.py`، `services/catalog_service.py::import_provider_services`، `keyboards/admin_kb.py` | 6 اختبارات: ربط صحيح للدفعة (السعر = التكلفة×1.4، المزود/الرقم صحيحان)، اختيار متعدد وتبديل مع تجاهل المكرر، «التالي» بلا تحديد، أرقام ناقصة، تحديد الكل، عزل الفشل في طبقة الخدمة، تحليل الأرقام |
| 10 | التحقق من الرابط | `utils/link_rules.py`: 12 قاعدة (حساب/منشور لإنستغرام وتيك توك ويوتيوب وتيليجرام وفيسبوك وإكس). الرفض **قبل إنشاء الطلب والخصم** برسالة مختلفة لكل حالة (منصة مختلفة · نوع خاطئ · مشوّه) مع **مثال صحيح**؛ رسالة طلب الرابط تعرض مثال القاعدة؛ القاعدة تُستنتج عند الاستيراد (متحفظة: منصة واحدة ونوع واضح فقط) وتُعدَّل من بطاقة الأدمن | `utils/link_rules.py`، `utils/validators.py`، `handlers/user/order_flow.py`، `services/order_service.py` | `test_link_rules.py` (**25 رابطاً صحيحاً و23 خاطئاً** مُجدوَلة + رسائل + استنتاج 9 حالات)، و`test_order_rejects_wrong_link_before_any_charge` (الرصيد لا يتغير ولا يُنشأ طلب)، `test_order_flow_prompt_and_rejection_show_example` |
| 11 | الهامش «40» والصرف «530» | `parse_margin_percent`: رقم صحيح فقط (`40` تعني ربح 40%)، الأرقام العربية مقبولة؛ **`40%` تُرفض صراحةً** ومعها السالب/العشري/الحروف/خارج 0–1000/الفارغ، كل حالة برسالة ومثال. الصرف: `USD 530`؛ `530` بلا رمز و`530%` و`USD abc` و`USD -5` تُرفض برسائل محددة؛ وإعداد `usd_rate` يقبل `530` ويرفض `530%` و`530$` و`0` | `utils/validators.py`، `core/setting_rules.py`، `services/provider_service.py` | 6 حالات قبول/رفض للهامش + داخل المحادثة + الصرف + `usd_rate` |
| 12 | Super Admin من البيئة (Render) | `SUPER_ADMIN_IDS` يُزرع **عند الإقلاع** (`bootstrap_super_admins`) ويُعاد التحقق **عند أول تحديث** من أي منهم (شفاء ذاتي لقاعدة أُعيد إنشاؤها)، ويدخل حتى لو التسجيل مغلق؛ بلا Shell ولا تعديل DB؛ تحليل متسامح للمتغير (فواصل/مسافات/أرقام عربية) | `services/auth_service.py`، `main.py`، `middlewares/context.py`، `scripts/init_db.py` | `test_phase13_ops.py`: bootstrap، شفاء الأدمن في الـmiddleware، التسجيل المغلق، تحليل المتغير، زرع الأدمن |
| 13 | Conflict (أكثر من instance) | `ConflictGuard` يراقب `Conflict` بنافذة زمنية: عابر (نشر Zero-downtime) يُتجاهَل ويُسجَّل، **ومستمر ≥ 60ث ⇒ إيقاف آمن برمز 3** ورسالة تشرح السبب والحل بدل حلقة أخطاء؛ القفل المحلي `bot.lock` (رمز 2) كما كان؛ خادم صحة `GET /health` على `PORT` لمنصات Render | `utils/conflict_guard.py`، `utils/health_server.py`، `main.py`، `config.py` | ConflictGuard (عابر/مستمر/إعادة ضبط)، `main()` يخرج 3، HealthServer (200/404/405/400)، `PORT` |

**أُنجز أيضاً (مطلوب ضمنياً أو سبق به المرحلة الثانية):**
- **⭐ المفضلة** (إضافة/عرض/إزالة/بلا تكرار/حد 100/خاصة بكل مستخدم/تختفي المعطّلة دون حذف) لأنها جزء من بطاقة الخدمة (بند 5). اختباراتها 4 ضمن `test_phase13_service_card.py`. **سأعيد التحقق منها ضمن بند 19 في المرحلة الثانية.**
- تنظيف `channel_outbox` اليومي (>30 يوماً، للمنتهي فقط) + اختبار.
- اختبار يثبّت ترتيب `except` (BadRequest دائم / TimedOut مؤقت) في مُرسل الإشعارات، بعد أن اكتشفت أن `BadRequest` فرع من `NetworkError` في PTB وأصلحت ثلاثة مواضع (الاشتراك، التشخيص، المرسل).

---

## 3) الملفات الجديدة والمعدَّلة ووظيفة كل منها

**جديدة:** `database/migrations/0011_phase13_launch_readiness.sql` (جدولا `channel_outbox` و`favorites` وأعمدة `link_rule/speed_text/quality_text/guarantee_text`) ·
`utils/channel_ref.py` (تحليل معرّف القناة) · `utils/privacy.py` (إخفاء معرّف/رابط/Username) · `utils/link_rules.py` (قواعد الروابط) ·
`utils/conflict_guard.py` · `utils/health_server.py` · `database/repositories/{channel_outbox,favorites}.py` ·
`services/channel_service.py` (طابور القنوات والتشخيص) · `services/subscription_service.py` (التحقق من العضوية) ·
`handlers/admin/channels.py` (شاشة «📢 القنوات») · `handlers/user/favorites.py` · `texts/channel_posts.py` (قوالب المنشورات) ·
اختبارات: `test_phase13_{channels,ops,service_card,admin_catalog}.py` و`tests/unit/test_link_rules.py`.

**معدَّلة (أهمها):** `services/catalog_service.py` (مفضلة، استيراد دفعة، حقول العرض، قواعد الروابط) · `handlers/admin/{providers,catalog}.py` (استيراد متعدد، تعديل العرض، بطاقة الربط) ·
`handlers/user/{catalog,order_flow}.py` · `middlewares/context.py` (بوابة الاشتراك + شفاء الأدمن) · `main.py` · `services/{auth,order,user,notification,backup,provider}_service.py` ·
`keyboards/{user_kb,admin_kb,callback_data}.py` · `texts/{ar,admin_ar}.py` · `config.py` · `core/{money,setting_rules,constants}.py` · `jobs/{maintenance,notification}_jobs.py` · `utils/{validators,formatters}.py` ·
الوثائق: `README.md`، `docs/RUNBOOK.md` (قسم جديد §10: Render/Super Admin/Conflict/القنوات + ترقية 1.1.0)، `docs/SETTINGS.md`، `docs/PERMISSIONS.md`، `.env.example`.

الكود الكامل: [`PHASE13_CODE.md`](PHASE13_CODE.md) (الملفات الأطول من 760 سطراً مسلَّمة كاملة في المشروع ومُفهرسة هناك).

---

## 4) طريقة التشغيل والاختبار

```
cd smm_bot && pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env     # BOT_TOKEN · ENCRYPTION_KEY · SUPER_ADMIN_IDS · (اختياري) ADMIN_ALERT_CHAT_ID / BACKUP_CHANNEL_ID / PORT
python -m scripts.init_db && python -m scripts.boot_check && python main.py
```
الترحيل 0011 يُطبَّق تلقائياً عند الإقلاع بعد أخذ نسخة أمان. `requirements.txt` **لم يتغير** (لم تُضف مكتبة جديدة).

---

## 5) قرارات تصميمية ومشاكل/قيود أحتاج أن تعرفها

1. **بوابة الاشتراك fail-closed:** إن لم يستطع البوت التحقق من قناة (معرّف خاطئ/البوت ليس مشرفاً) يُمنع غير المتحقَّق منهم **بدل السماح للجميع**، ويصل الأدمن تنبيه واحد يشرح السبب. إن لم تُضبط أي قناة فلا بوابة. **لذلك اضبط القنوات الأربع واضغط «🔍 فحص» قبل الإعلان.**
2. **الهامش `40%` يُرفض** عمداً (حسب نصّ البند: «40 لا 40%»). إن فضّلت قبوله بتجريد العلامة فهو تعديل سطر واحد — أخبرني.
3. **استنتاج قاعدة الرابط متحفظ:** الخدمات القديمة بلا قاعدة تبقى بالتحقق العام فقط (لا نخمّن ونمنع طلباً صحيحاً). اضبط قاعدة خدماتك الحالية من «✏️ تعديل العرض». أسماء ملتبسة («Followers + Likes» أو منصتان) تُترك بلا قاعدة.
4. **`/health` يعيد 200 دائماً** ما دامت العملية حية (لا يفحص تيليجرام/المزود)؛ غرضه إبقاء Web Service على Render حياً فقط.
5. **Render:** نظام الملفات المجاني مؤقت؛ بلا Persistent Disk تُمسح SQLite عند كل نشر (موثّق في RUNBOOK §10.2). ما زال قرار الاستضافة غير محسوم ولذلك دُعمت الحالتان (Web Service/Worker).
6. **Super Admin من البيئة هو مصدر الحقيقة:** خفض دوره من البوت يُعاد عند إعادة التشغيل أو أول تحديث منه (لإزالته نهائياً احذفه من المتغير).
7. **قيود ثابتة:** لا Telegram حقيقي · عملية واحدة · Conflict عبر مضيفين مختلفين لا يمنعه القفل المحلي (يكتشفه الحارس بعد ≥60ث فيوقف البوت) · نسخة القناة غير مشفّرة (قرارك) · الأنواع غير `default` غير مدعومة.
8. **مُرحَّل للمرحلة الثانية (بند 20):** `handlers/common/errors.py::error_handler` يعدّ `BadRequest` كشبكة مؤقتة فيُخفي أخطاء الكود؛ لم ألمسه الآن (خارج نطاق المرحلة الأولى) وسأعالجه ضمن معالجة Timeout/ConnectError.

---

## 6) قائمة تحقق قصيرة لك على بيئتك الفعلية (لا أستطيع تنفيذها من هنا)

1. أنشئ قناة اختبار، أضف البوت **مشرفاً** (نشر رسائل)، ضع معرّفها `-100…` في «📢 القنوات» ثم «🔍 فحص» ⇒ يجب أن يظهر ✅ وعنوان القناة.
2. بحساب عادي غير مشترك: /start ⇒ شاشة الاشتراك؛ اشترك واضغط «✅ تحقق» ⇒ القائمة الرئيسية؛ غادر القناة ثم اضغط أي زر ⇒ تعود البوابة.
3. سجّل حساباً جديداً ⇒ وصول «👤 مستخدم جديد 🔥» لقناة التنبيهات بمعرّف مقنّع. أنشئ طلباً ⇒ «🔥 طلب جديد» في قناة التوثيق.
4. «💾 النسخ الاحتياطي ← 🆕 نسخة الآن» ⇒ وصول الملف لقناة النسخ فقط.
5. على Render: ضع `SUPER_ADMIN_IDS` فقط وانشر ⇒ /admin يعمل مباشرة بلا تعديل DB. شغّل نسخة محلية بنفس التوكن ⇒ بعد ≥60ث يخرج أحدهما برمز 3 مع رسالة Conflict المفهومة.
6. استورد دفعة من مزودك الحقيقي: `101 205 330` ثم تحقق أن بطاقات الأدمن تُظهر الرقم الداخلي ⇐ المزود ⇐ رقمه لديه.

⛔ **توقفت هنا حسب تعليماتك.** لن أبدأ المرحلة الثانية (14–20) إلا بعد موافقتك الصريحة.
