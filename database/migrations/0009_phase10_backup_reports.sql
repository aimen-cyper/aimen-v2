-- =====================================================================
-- الترحيل 0009 — المرحلة 10 (النسخ الاحتياطي والتقارير)
--
-- لماذا هذا الترحيل؟
--   1) جدول `backups` وُلد في المرحلة 1 بلا أي كود فوقه. النسخ الفعلية تحتاج
--      أعمدة تثبت أن النسخة سليمة وأين وُزِّعت:
--        verified_at        : آخر مرة أُعيد فيها فحص الملف (بصمة + سلامة SQLite).
--        schema_version     : إصدار مخطط القاعدة داخل النسخة (يمنع استعادة نسخة
--                             أحدث من الكود، ويُعرض للأدمن).
--        channel_message_id : رقم رسالة النسخة في قناة النسخ الخارجية (قرار D7).
--        channel_sent_at    : وقت إرسالها للقناة (NULL ⇒ لم تُرسل).
--        error_text         : سبب الفشل (للنسخ الفاشلة فقط، منقّى من الأسرار).
--   2) تصدير التقارير ملفات CSV تحوي بيانات مالية ومعرّفات مستخدمين، فتحتاج
--      صلاحية مستقلة (stats.export) لا تمنحها stats.view.
--   3) إعدادات تحكّم جديدة: إرسال النسخ للقناة، الحد الأدنى للنسخ المحفوظة مهما
--      قصرت مدة الاحتفاظ، وسقف صفوف التصدير.
--
-- ملاحظات تقنية:
--   • لا حذف ولا إعادة بناء لأي جدول — ALTER ADD COLUMN وصفوف بذور فقط.
--   • نسخة «حُذف ملفها» لا يُحذف سجلها: حالتها تصير 'purged' فيبقى الأثر.
-- =====================================================================

-- ------------------------------ أعمدة النسخ ------------------------------ --
ALTER TABLE backups ADD COLUMN verified_at        TEXT;
ALTER TABLE backups ADD COLUMN schema_version     TEXT;
ALTER TABLE backups ADD COLUMN channel_message_id INTEGER;
ALTER TABLE backups ADD COLUMN channel_sent_at    TEXT;
ALTER TABLE backups ADD COLUMN error_text         TEXT;

CREATE INDEX IF NOT EXISTS idx_backups_status ON backups(status, id DESC);

-- ----------------------------- صلاحية جديدة ---------------------------- --
INSERT OR IGNORE INTO permissions (code, name_ar, group_code, is_dangerous) VALUES
    ('stats.export', 'تصدير التقارير كملفات CSV', 'stats', 1);

-- للأدمن والأدمن الأعلى (الدعم الفني لا يصدّر بيانات مالية).
INSERT OR IGNORE INTO role_permissions (role_code, permission_code) VALUES
    ('super_admin', 'stats.export'),
    ('admin',       'stats.export');

-- ----------------------------- إعدادات جديدة --------------------------- --
INSERT OR IGNORE INTO settings (key, value, value_type, group_code, name_ar, description_ar, is_editable, updated_at) VALUES
    ('backup_send_to_channel', 'true', 'bool', 'backup', 'إرسال النسخ لقناة النسخ الخارجية',
     'يعمل فقط إذا ضُبط BACKUP_CHANNEL_ID في ملف البيئة. القناة يجب أن تكون خاصة: النسخة تحوي بيانات العملاء', 1,
     strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('backup_min_keep', '5', 'int', 'backup', 'أقل عدد نسخ سليمة يُحتفظ بها دائماً',
     'سياسة الاحتفاظ بالأيام لا تحذف آخر هذا العدد من النسخ السليمة مهما كان عمرها. القيمة بين 1 و100', 1,
     strftime('%Y-%m-%dT%H:%M:%fZ','now')),

    ('export_max_rows', '20000', 'int', 'reports', 'أقصى عدد صفوف في ملف التصدير الواحد',
     'يحمي البوت من ملف ضخم يستهلك الذاكرة أو يتجاوز حد تيليجرام. القيمة بين 100 و100000', 1,
     strftime('%Y-%m-%dT%H:%M:%fZ','now'));

-- فاصل النسخ: الصفر يعني «تعطيل النسخ التلقائي» كما كان موصوفاً في الوصف منذ البداية
UPDATE settings
   SET description_ar = 'صفر يعني تعطيل النسخ التلقائي (يبقى النسخ اليدوي متاحاً). القيمة بين 0 و720'
 WHERE key = 'backup_interval_hours';
