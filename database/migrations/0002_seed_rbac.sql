-- =====================================================================
-- الترحيل 0002 — زرع الأدوار والصلاحيات الافتراضية
-- المصدر المرجعي لهذه القيم هو الملف core/permissions.py
-- ويوجد اختبار آلي يتأكد من تطابق الاثنين (tests/test_permissions_seed.py)
-- =====================================================================

INSERT INTO roles (code, name_ar, level, is_system, created_at) VALUES
    ('user',        'مستخدم',     10,  1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('support',     'دعم فني',    40,  1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('admin',       'أدمن',       70,  1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    ('super_admin', 'أدمن أعلى',  100, 1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

INSERT INTO permissions (code, name_ar, group_code, is_dangerous) VALUES
    ('admin.access',             'الدخول إلى لوحة التحكم',            'general',   0),

    ('users.view',               'عرض المستخدمين والبحث عنهم',        'users',     0),
    ('users.balance.credit',     'إضافة رصيد لمستخدم',                'users',     1),
    ('users.balance.debit',      'خصم رصيد من مستخدم',                'users',     1),
    ('users.ban',                'حظر مستخدم',                        'users',     1),
    ('users.unban',              'فك حظر مستخدم',                     'users',     0),
    ('users.note',               'كتابة ملاحظة إدارية على مستخدم',    'users',     0),
    ('users.role.change',        'تغيير دور مستخدم',                  'users',     1),

    ('services.view',            'عرض الخدمات',                       'services',  0),
    ('services.create',          'إضافة خدمة',                        'services',  0),
    ('services.update',          'تعديل بيانات خدمة',                 'services',  0),
    ('services.price',           'تغيير سعر خدمة',                    'services',  1),
    ('services.archive',         'تعطيل أو أرشفة خدمة',               'services',  1),
    ('services.sync',            'استيراد ومزامنة خدمات المزود',      'services',  0),

    ('providers.view',           'عرض المزودين',                      'providers', 0),
    ('providers.create',         'إضافة مزود',                        'providers', 1),
    ('providers.update',         'تعديل مزود',                        'providers', 1),
    ('providers.key.update',     'تغيير مفتاح API للمزود',            'providers', 1),
    ('providers.test',           'اختبار اتصال المزود وفحص رصيده',    'providers', 0),

    ('orders.view',              'عرض الطلبات',                       'orders',    0),
    ('orders.recheck',           'إعادة فحص حالة طلب',                'orders',    0),
    ('orders.cancel',            'إلغاء طلب',                         'orders',    1),
    ('orders.refund',            'استرجاع مبلغ طلب',                  'orders',    1),
    ('orders.link_provider_id',  'ربط رقم الطلب عند المزود يدوياً',   'orders',    1),
    ('orders.status.override',   'تغيير حالة طلب يدوياً',             'orders',    1),

    ('payments.view',            'عرض طلبات الشحن',                   'payments',  0),
    ('payments.approve',         'اعتماد طلب شحن',                    'payments',  1),
    ('payments.reject',          'رفض طلب شحن',                       'payments',  1),
    ('payments.methods',         'إدارة طرق الدفع',                   'payments',  1),

    ('tickets.view',             'عرض تذاكر الدعم',                   'tickets',   0),
    ('tickets.reply',            'الرد على التذاكر',                  'tickets',   0),
    ('tickets.assign',           'إسناد التذاكر',                     'tickets',   0),
    ('tickets.close',            'إغلاق التذاكر',                     'tickets',   0),

    ('broadcast.send',           'إرسال رسالة جماعية',                'broadcast', 1),

    ('stats.view',               'عرض الإحصائيات',                    'stats',     0),
    ('stats.profit',             'عرض تقارير الأرباح والتكلفة',       'stats',     0),

    ('settings.view',            'عرض الإعدادات',                     'settings',  0),
    ('settings.update',          'تعديل الإعدادات العامة',            'settings',  1),
    ('settings.maintenance',     'تفعيل أو إيقاف وضع الصيانة',        'settings',  1),

    ('logs.view',                'عرض السجلات والأخطاء',              'logs',      0),

    ('backup.create',            'إنشاء نسخة احتياطية',               'backup',    1),
    ('backup.download',          'تنزيل نسخة احتياطية',               'backup',    1),

    ('admins.manage',            'إدارة الأدوار والصلاحيات',          'admins',    1);

-- الأدمن الأعلى: كل الصلاحيات
INSERT INTO role_permissions (role_code, permission_code)
SELECT 'super_admin', code FROM permissions;

-- الأدمن العادي: كل الصلاحيات عدا الحصرية للأدمن الأعلى
INSERT INTO role_permissions (role_code, permission_code)
SELECT 'admin', code FROM permissions
WHERE code NOT IN (
    'users.role.change',
    'providers.key.update',
    'orders.link_provider_id',
    'orders.status.override',
    'stats.profit',
    'backup.create',
    'backup.download',
    'admins.manage'
);

-- الدعم الفني: التذاكر + صلاحيات عرض محدودة
INSERT INTO role_permissions (role_code, permission_code)
SELECT 'support', code FROM permissions
WHERE code IN (
    'admin.access',
    'users.view',
    'services.view',
    'orders.view',
    'orders.recheck',
    'payments.view',
    'tickets.view',
    'tickets.reply',
    'tickets.assign',
    'tickets.close'
);

-- دور المستخدم العادي: لا يملك أي صلاحية إدارية (لا صفوف)
