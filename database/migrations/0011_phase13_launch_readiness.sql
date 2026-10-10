-- =====================================================================
-- الترحيل 0011 — المرحلة 13.1 (الجاهزية للاستخدام الفعلي، ملاحظات التطوير v1.0.1)
--
-- ما يضيفه:
--   1) خدمات: link_rule (قاعدة التحقق من الرابط حسب المنصة/النوع مثل instagram:profile)،
--      speed_text / quality_text / guarantee_text (معلومات عرض اختيارية؛ NULL ⇒ «غير محددة»).
--   2) favorites: مفضلة المستخدم (مفتاح مركّب user_id+service_id ⇒ لا تكرار بنيوياً).
--   3) channel_outbox: صندوق إرسال دائم لقنوات الإدارة (تنبيهات الإدارة + توثيق الطلبات)،
--      بنفس نمط notifications: يُكتب مع الحدث في المعاملة نفسها، ويرسله job لاحقاً بمحاولات مجدولة،
--      فلا يضيع سجل عند إعادة التشغيل ولا يُكتب سجل لحدث لم يُثبَّت.
--   4) إعدادات: usd_rate، قنوات الاشتراك الإجباري الأربع، orders_log_chat_id، إشعار المستخدم الجديد.
--
-- لا حذف ولا إعادة بناء لأي جدول (ALTER ADD COLUMN وجداول جديدة وإعدادات فقط).
-- =====================================================================

ALTER TABLE services ADD COLUMN link_rule TEXT;
ALTER TABLE services ADD COLUMN speed_text TEXT;
ALTER TABLE services ADD COLUMN quality_text TEXT;
ALTER TABLE services ADD COLUMN guarantee_text TEXT;

CREATE TABLE favorites (
    user_id     INTEGER NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
    service_id  INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL,
    PRIMARY KEY (user_id, service_id)
) WITHOUT ROWID;

CREATE INDEX idx_favorites_user ON favorites(user_id, created_at);

CREATE TABLE channel_outbox (
    id              INTEGER PRIMARY KEY,
    kind            TEXT    NOT NULL CHECK (kind IN ('admin_alert', 'orders_log')),
    title           TEXT    NOT NULL DEFAULT '',
    message         TEXT    NOT NULL,
    dedupe_key      TEXT    NOT NULL UNIQUE,
    status          TEXT    NOT NULL DEFAULT 'queued'
                     CHECK (status IN ('queued', 'sent', 'failed', 'skipped')),
    attempts        INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at TEXT,
    last_error      TEXT,
    created_at      TEXT    NOT NULL,
    sent_at         TEXT
);

CREATE INDEX idx_channel_outbox_queue ON channel_outbox(status, next_attempt_at);

INSERT OR IGNORE INTO settings (key, value, value_type, group_code, name_ar, description_ar, is_editable, updated_at) VALUES
    ('usd_rate', '530', 'str', 'general', 'سعر صرف الدولار للعرض',
     'كم وحدة من عملة النظام تساوي 1$ (مثال 530). للعرض فقط: يُحسب منه السعر بالدولار في بطاقة الخدمة والطلب', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('subscription_required', 'true', 'bool', 'channels', 'الاشتراك الإجباري في القنوات',
     'عند التفعيل لا يستخدم المستخدم العادي البوت قبل الاشتراك في كل القنوات المضبوطة أدناه (الفريق الإداري معفى)', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('channel_official', '', 'str', 'channels', '📢 القناة الرسمية',
     'معرّف القناة: @username أو -100xxxxxxxxxx، ويمكن إضافة رابط الدعوة بعد مسافة (للقنوات الخاصة). فارغ = غير مطلوبة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('channel_proofs', '', 'str', 'channels', '📚 قناة توثيق/متابعة الطلبات',
     'نفس صيغة القناة الرسمية. فارغ = غير مطلوبة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('channel_updates', '', 'str', 'channels', '🔔 قناة التحديثات',
     'نفس صيغة القناة الرسمية. فارغ = غير مطلوبة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('channel_offers', '', 'str', 'channels', '🎁 قناة العروض',
     'نفس صيغة القناة الرسمية. فارغ = غير مطلوبة', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('orders_log_chat_id', '', 'str', 'channels', 'قناة توثيق الطلبات الجديدة (للنشر)',
     'قناة يُنشر فيها سجل منظم لكل طلب جديد (بيانات مقنّعة). @username أو -100xxxxxxxxxx. فارغ = لا نشر', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('new_user_alert_enabled', 'true', 'bool', 'channels', 'إشعار الإدارة بالمستخدم الجديد',
     'يُنشر في قناة تنبيهات الإدارة (admin_alert_chat_id) عند تسجيل مستخدم جديد', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
