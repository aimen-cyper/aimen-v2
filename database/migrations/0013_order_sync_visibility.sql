-- =====================================================================
-- الترحيل 0013 — v1.3.1: شفافية مزامنة الطلبات وتحديث الرسائل
--
-- لماذا؟ (المبررات من تشخيص v1.3.0)
--   1) orders.last_checked_at / last_check_ok_at / last_check_error / check_fail_streak
--      • `last_error` كان يبقى «تعذر الاتصال…» حتى بعد اكتمال الطلب؛ ولا أثر لنجاح الاستعلام.
--      • جدولة المتابعة كانت مرتبطة بـ`checks_count` (يزيد حتى عند الفشل) فيتباطأ طلب سليم إلى ساعة.
--      • الاستعلام الجماعي لا يُسجَّل بـ`order_id` في provider_requests فلا يمكن اشتقاق آخر فحص ناجح.
--   2) order_message_refs: مرجع رسائل تيليجرام القابلة للتحديث (شاشة تأكيد الطلب، إشعار الإنشاء،
--      منشور قناة التوثيق) حتى يُعدَّل نصّها عند تغيّر الحالة. فشل التعديل لا يمس حالة الطلب.
--   3) إعدادات جديدة قابلة للتعديل (لا أرقام ثابتة في الكود).
--
-- إضافي بالكامل: ALTER ADD COLUMN (nullable/DEFAULT) + جدول جديد + إعدادات INSERT OR IGNORE.
-- لا حذف ولا إعادة بناء ولا backfill. الكود القديم (1.3.0) لا يقرأ هذه الأعمدة ⇒ الرجوع آمن.
-- =====================================================================

ALTER TABLE orders ADD COLUMN last_checked_at TEXT;
ALTER TABLE orders ADD COLUMN last_check_ok_at TEXT;
ALTER TABLE orders ADD COLUMN last_check_error TEXT;
ALTER TABLE orders ADD COLUMN check_fail_streak INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS order_message_refs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    kind            TEXT    NOT NULL CHECK (kind IN ('user_confirm', 'user_notice', 'channel_post')),
    chat_id         TEXT    NOT NULL,
    message_id      INTEGER NOT NULL,
    rendered_status TEXT,
    rendered_hash   TEXT,
    fail_count      INTEGER NOT NULL DEFAULT 0,
    next_try_at     TEXT,
    is_dead         INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL,
    UNIQUE (order_id, kind)
);
CREATE INDEX IF NOT EXISTS idx_order_message_refs_live ON order_message_refs(is_dead, next_try_at);

INSERT OR IGNORE INTO settings (key, value, value_type, group_code, name_ar, description_ar, is_editable, updated_at) VALUES
    ('order_check_active_max_seconds', '300', 'int', 'orders', 'أقصى فاصل لمتابعة الطلب النشِط (ثانية)',
     'الحد الأعلى لفاصل فحص حالة الطلب النشِط عند نجاح الاستعلام. يتباطأ الفاصل تدريجياً بعمر الطلب لكنه لا يتجاوز هذه القيمة.', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('order_check_error_max_seconds', '600', 'int', 'orders', 'أقصى فاصل إعادة الفحص عند الأعطال (ثانية)',
     'عند فشل الاتصال بالمزود يتباطأ الفحص أسّياً حسب عدد الإخفاقات المتتالية لكل طلب، ولا يتجاوز هذه القيمة. فشل الاتصال لا يعني فشل الطلب.', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('order_check_round_budget_seconds', '90', 'int', 'orders', 'ميزانية جولة فحص الطلبات (ثانية)',
     'بعد هذه المدة تتوقف الجولة عن بدء فحوص جديدة وتُفرج عن الباقي للجولة التالية بدل بقائه محجوزاً.', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('order_message_refresh_enabled', 'true', 'bool', 'orders', 'تحديث رسائل الطلب تلقائياً',
     'عند التفعيل تُعدَّل رسالة تأكيد الطلب وإشعار الإنشاء ومنشور قناة التوثيق عند تغيّر حالة الطلب.', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('order_message_refresh_seconds', '15', 'int', 'orders', 'فاصل مهمة تحديث رسائل الطلبات (ثانية)',
     'كل كم ثانية تفحص المهمة الرسائل المتأخرة عن حالة الطلب وتعدّلها.', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('channel_post_ttl_hours', '72', 'int', 'general', 'مدة بقاء منشور القناة بانتظار الوجهة (ساعة)',
     'منشور قناة التوثيق بلا وجهة مضبوطة يبقى بالطابور هذه المدة بدل أن يُتخطّى نهائياً، ثم يُتخطّى.', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('block_negative_margin', 'false', 'bool', 'orders', 'منع الطلب على خدمة بهامش سالب',
     'عند التفعيل يُرفض إنشاء طلب على خدمة سعر بيعها أقل من تكلفتها لدى المزود. الافتراضي: تنبيه الأدمن فقط دون منع.', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    ('provider_status_alert_threshold', '5', 'int', 'providers', 'عتبة تنبيه أعطال استعلام الحالة',
     'عدد إخفاقات استعلام الحالة المتتالية قبل تنبيه الأدمن. هذه الأعطال لا تعطّل إنشاء طلبات جديدة.', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
