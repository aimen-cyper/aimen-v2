# مرجع الأدوار والصلاحيات

> **مولَّد آلياً** بالأمر `python -m scripts.gen_reference_docs` من `core/permissions.py`. هذه **القيم الافتراضية** المزروعة عند التهيئة؛ الصلاحيات الفعلية تُقرأ من جداول `role_permissions` و`user_permissions` في قاعدة البيانات (لا أدمن ثابت في الكود). ⚠️ = صلاحية خطِرة: منحها فردياً لغير الأدمن الأعلى محجوب، ويرصد «فحص الأمان» أي استثناء ممنوح لها.

عدد الصلاحيات: **47** (منها خطِرة: **25**).

| الصلاحية | الوصف | المجموعة | دعم فني | أدمن | أدمن أعلى |
|---|---|---|---|---|---|
| `admin.access` | الدخول إلى لوحة التحكم | general | ✅ | ✅ | ✅ |
| `users.view` | عرض المستخدمين والبحث عنهم | users | ✅ | ✅ | ✅ |
| `users.balance.credit` ⚠️ | إضافة رصيد لمستخدم | users | — | ✅ | ✅ |
| `users.balance.debit` ⚠️ | خصم رصيد من مستخدم | users | — | ✅ | ✅ |
| `users.ban` ⚠️ | حظر مستخدم | users | — | ✅ | ✅ |
| `users.unban` | فك حظر مستخدم | users | — | ✅ | ✅ |
| `users.note` | كتابة ملاحظة إدارية على مستخدم | users | — | ✅ | ✅ |
| `users.role.change` ⚠️ | تغيير دور مستخدم | users | — | — | ✅ |
| `services.view` | عرض الخدمات | services | ✅ | ✅ | ✅ |
| `services.create` | إضافة خدمة | services | — | ✅ | ✅ |
| `services.update` | تعديل بيانات خدمة | services | — | ✅ | ✅ |
| `services.price` ⚠️ | تغيير سعر خدمة | services | — | ✅ | ✅ |
| `services.archive` ⚠️ | تعطيل أو أرشفة خدمة | services | — | ✅ | ✅ |
| `services.sync` | استيراد ومزامنة خدمات المزود | services | — | ✅ | ✅ |
| `providers.view` | عرض المزودين | providers | — | ✅ | ✅ |
| `providers.create` ⚠️ | إضافة مزود | providers | — | ✅ | ✅ |
| `providers.update` ⚠️ | تعديل مزود | providers | — | ✅ | ✅ |
| `providers.key.update` ⚠️ | تغيير مفتاح API للمزود | providers | — | — | ✅ |
| `providers.test` | اختبار اتصال المزود وفحص رصيده | providers | — | ✅ | ✅ |
| `orders.view` | عرض الطلبات | orders | ✅ | ✅ | ✅ |
| `orders.recheck` | إعادة فحص حالة طلب | orders | ✅ | ✅ | ✅ |
| `orders.cancel` ⚠️ | إلغاء طلب | orders | — | ✅ | ✅ |
| `orders.refund` ⚠️ | استرجاع مبلغ طلب | orders | — | ✅ | ✅ |
| `orders.link_provider_id` ⚠️ | ربط رقم الطلب عند المزود يدوياً | orders | — | — | ✅ |
| `orders.status.override` ⚠️ | تغيير حالة طلب يدوياً | orders | — | — | ✅ |
| `payments.view` | عرض طلبات الشحن | payments | ✅ | ✅ | ✅ |
| `payments.approve` ⚠️ | اعتماد طلب شحن | payments | — | ✅ | ✅ |
| `payments.reject` ⚠️ | رفض طلب شحن | payments | — | ✅ | ✅ |
| `payments.methods` ⚠️ | إدارة طرق الدفع | payments | — | ✅ | ✅ |
| `tickets.view` | عرض تذاكر الدعم | tickets | ✅ | ✅ | ✅ |
| `tickets.reply` | الرد على التذاكر | tickets | ✅ | ✅ | ✅ |
| `tickets.assign` | إسناد التذاكر | tickets | ✅ | ✅ | ✅ |
| `tickets.close` | إغلاق التذاكر | tickets | ✅ | ✅ | ✅ |
| `broadcast.send` ⚠️ | إرسال رسالة جماعية | broadcast | — | ✅ | ✅ |
| `notifications.templates` ⚠️ | تعديل قوالب الإشعارات | broadcast | — | ✅ | ✅ |
| `stats.view` | عرض الإحصائيات | stats | — | ✅ | ✅ |
| `stats.profit` | عرض تقارير الأرباح والتكلفة | stats | — | — | ✅ |
| `stats.export` ⚠️ | تصدير التقارير كملفات CSV | stats | — | ✅ | ✅ |
| `settings.view` | عرض الإعدادات | settings | — | ✅ | ✅ |
| `settings.update` ⚠️ | تعديل الإعدادات العامة | settings | — | ✅ | ✅ |
| `settings.maintenance` ⚠️ | تفعيل أو إيقاف وضع الصيانة | settings | — | ✅ | ✅ |
| `logs.view` | عرض السجلات والأخطاء | logs | — | ✅ | ✅ |
| `backup.create` ⚠️ | إنشاء نسخة احتياطية | backup | — | — | ✅ |
| `backup.download` ⚠️ | تنزيل نسخة احتياطية | backup | — | — | ✅ |
| `admins.manage` ⚠️ | إدارة الأدوار والصلاحيات | admins | — | — | ✅ |
| `security.view` | عرض شاشة الأمان | security | — | ✅ | ✅ |
| `security.manage` ⚠️ | إدارة الحماية (رفع الإيقاف المؤقت) | security | — | — | ✅ |

المستخدم العادي (`user`) بلا أي صلاحية إدارية. أول أدمن أعلى يُزرع من `SUPER_ADMIN_IDS`، وتغيير دور مستخدم يتم من شاشته في «👥 المستخدمون» (🎚 تغيير الدور) أو بـ`python -m scripts.create_admin`. الاستثناءات الفردية (منح/منع صلاحية لشخص) تدعمها `AuthService.set_user_permission` لكن **لا شاشة لها في البوت** بعد.
