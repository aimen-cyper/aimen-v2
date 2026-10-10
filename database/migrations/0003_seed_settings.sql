-- =====================================================================
-- الترحيل 0003 — زرع الإعدادات الافتراضية وتصنيفات الخدمات
-- كل إعداد هنا قابل للتعديل لاحقاً من لوحة الأدمن (عدا ما is_editable = 0)
-- المبالغ مخزَّنة بالنقاط (1/10000 من وحدة العملة)
-- =====================================================================

INSERT INTO settings (key, value, value_type, group_code, name_ar, description_ar, is_editable, updated_at) VALUES
    -- عام
    ('bot_name', 'SMM Bot', 'str', 'general', 'اسم البوت', 'يظهر في رسالة الترحيل وبعض الرسائل', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('currency_code', 'YER', 'str', 'general', 'رمز العملة', 'رمز العملة المحاسبي مثل YER أو USD', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('currency_symbol', 'ريال', 'str', 'general', 'رمز العرض للعملة', 'النص الذي يظهر بجانب المبالغ', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('display_decimals', '2', 'int', 'general', 'عدد الخانات العشرية للعرض', 'لا يؤثر على دقة التخزين الداخلية', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('welcome_message', 'أهلاً بك في بوت خدمات السوشيال ميديا 👋', 'str', 'general', 'رسالة الترحيب', 'تظهر عند أمر start', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('support_username', '', 'str', 'general', 'حساب الدعم', 'معرف تيليجرام للدعم بدون علامة @', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('rules_text', 'يرجى قراءة الشروط قبل الطلب. لا يوجد استرجاع بعد اكتمال التنفيذ.', 'str', 'general', 'الشروط وسياسة الاسترجاع', 'تظهر في قسم معلومات', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('registration_enabled', '1', 'bool', 'general', 'السماح بتسجيل مستخدمين جدد', 'عند التعطيل لن يُقبل أي مستخدم جديد', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    -- الصيانة
    ('maintenance_mode', '0', 'bool', 'maintenance', 'وضع الصيانة', 'عند التفعيل يستخدم النظام الأدمن فقط', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('maintenance_message', '🚧 النظام في وضع الصيانة حالياً، نعتذر عن الإزعاج.', 'str', 'maintenance', 'رسالة الصيانة', 'تظهر للمستخدمين أثناء الصيانة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    -- الطلبات
    ('min_order_amount_units', '0', 'money', 'orders', 'الحد الأدنى لقيمة الطلب', 'صفر يعني لا يوجد حد أدنى', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('duplicate_order_window_minutes', '10', 'int', 'orders', 'نافذة كشف الطلب المكرر بالدقائق', 'خلالها يُطلب تأكيد إضافي لنفس الرابط والكمية', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('order_submit_interval_seconds', '15', 'int', 'orders', 'فاصل إرسال الطلبات للمزود', 'كل كم ثانية يعمل job الإرسال', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('order_check_interval_seconds', '120', 'int', 'orders', 'فاصل فحص حالة الطلبات', 'كل كم ثانية يعمل job فحص الحالة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('order_stuck_alert_hours', '24', 'int', 'orders', 'تنبيه الطلب العالق بالساعات', 'ينبّه الأدمن للطلب الذي لم يكتمل خلال هذه المدة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('partial_refund_enabled', '1', 'bool', 'orders', 'تفعيل الاسترجاع الجزئي', 'استرجاع قيمة الكمية غير المنفذة تلقائياً', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('auto_refund_on_provider_fail', '1', 'bool', 'orders', 'الاسترجاع التلقائي عند فشل المزود', 'إعادة المبلغ فوراً عند فشل الإرسال', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('user_cancel_before_submit', '1', 'bool', 'orders', 'السماح للمستخدم بإلغاء طلبه قبل الإرسال', 'يُسترجع المبلغ كاملاً', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('max_orders_per_day', '50', 'int', 'orders', 'أقصى عدد طلبات للمستخدم يومياً', 'حماية من إساءة الاستخدام', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    -- المدفوعات
    ('min_deposit_units', '10000', 'money', 'payments', 'الحد الأدنى للشحن', 'بالنقاط: 10000 تعادل وحدة عملة واحدة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('max_deposit_units', '100000000', 'money', 'payments', 'الحد الأقصى للشحن', 'بالنقاط', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('payment_expiry_hours', '48', 'int', 'payments', 'انتهاء صلاحية طلب الشحن بالساعات', 'يُعلَّم تلقائياً كمنتهٍ بعدها', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    -- الإشعارات
    ('notification_dispatch_seconds', '5', 'int', 'notifications', 'فاصل إرسال الإشعارات', 'كل كم ثانية يعمل job الإشعارات', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('admin_alert_chat_id', '', 'str', 'notifications', 'قناة تنبيهات الأدمن', 'معرف مجموعة أو قناة لاستقبال تنبيهات النظام', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    -- المزودون
    ('provider_low_balance_alert_units', '0', 'money', 'providers', 'حد التنبيه لرصيد المزود', 'صفر يعني بدون تنبيه', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('provider_exchange_rate', '1', 'str', 'providers', 'سعر صرف عملة المزود', 'كم وحدة من عملة العرض تعادل وحدة واحدة من عملة المزود', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('provider_failure_threshold', '5', 'int', 'providers', 'عدد الأخطاء المتتالية لتعطيل المزود', 'قاطع الدائرة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('provider_disable_minutes', '15', 'int', 'providers', 'مدة التعطيل المؤقت للمزود بالدقائق', 'بعدها يُعاد تفعيله تلقائياً', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('provider_insufficient_wait_hours', '6', 'int', 'providers', 'مهلة انتظار شحن رصيد المزود بالساعات', 'بعدها يفشل الطلب ويُسترجع المبلغ', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    -- النسخ الاحتياطي
    ('backup_interval_hours', '12', 'int', 'backup', 'فاصل النسخ الاحتياطي التلقائي بالساعات', 'صفر يعني تعطيل', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('backup_retention_days', '14', 'int', 'backup', 'مدة الاحتفاظ بالنسخ بالأيام', 'تُحذف النسخ الأقدم تلقائياً', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    -- الحدود والحماية
    ('broadcast_rate_per_second', '20', 'int', 'limits', 'سرعة الإذاعة رسالة بالثانية', 'احترام حدود تيليجرام', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('rate_limit_actions_per_minute', '25', 'int', 'limits', 'أقصى عدد إجراءات للمستخدم بالدقيقة', 'حماية من الضغط المتكرر', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('max_tickets_per_day', '5', 'int', 'limits', 'أقصى عدد تذاكر للمستخدم يومياً', 'حماية من الإزعاج', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    -- قيمة داخلية غير قابلة للتعديل من الواجهة
    ('schema_money_scale', '10000', 'int', 'system', 'مقياس المال الداخلي', 'عدد النقاط في وحدة العملة - تغييره يتطلب ترحيل بيانات', 0, strftime('%Y-%m-%dT%H:%M:%fZ','now'));

-- تصنيفات الخدمات الافتراضية (هيكلية وليست بيانات وهمية - لا تحتوي أي خدمة)
INSERT INTO service_categories (name_ar, name_en, emoji, sort_order, is_active, created_at, updated_at) VALUES
    ('انستغرام', 'Instagram', '📸', 10, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('تيك توك',  'TikTok',    '🎵', 20, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('يوتيوب',   'YouTube',   '▶️', 30, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('تيليجرام', 'Telegram',  '📢', 40, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('فيسبوك',   'Facebook',  '📘', 50, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('تويتر',    'X',         '✖️', 60, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('سناب شات', 'Snapchat',  '👻', 70, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('أخرى',     'Other',     '📦', 99, 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now'));
