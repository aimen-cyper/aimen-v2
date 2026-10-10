-- =====================================================================
-- الترحيل 0012 — المرحلة الثانية من ملاحظات v1.0.1 (المزامنة والبحث)
--
-- ما يضيفه:
--   1) services.provider_missing_at : متى لاحظت المزامنة لأول مرة أن الخدمة اختفت من قائمة المزود
--      (NULL ⇒ موجودة لدى المزود). لا تُحذف الخدمة ولا تُمسّ طلباتها السابقة.
--   2) services.disabled_by_sync    : 1 ⇒ عطّلتها المزامنة (اختفت لدى المزود) فتعود تلقائياً إن
--      عادت، أما التعطيل اليدوي فلا يضع هذه العلامة ولا تلغيه المزامنة أبداً.
--   3) فهرس provider_service_id وحده: البحث بمعرّف المزود (دون معرّف المزود الداخلي) يبقى سريعاً
--      مع آلاف الخدمات.
--   4) إعداد sync_auto_disable_missing: تعطيل الخدمات المختفية لدى المزود تلقائياً بعد المزامنة.
--
-- لا حذف ولا إعادة بناء لأي جدول (ALTER ADD COLUMN وفهرس وإعداد فقط).
-- =====================================================================

ALTER TABLE services ADD COLUMN provider_missing_at TEXT;
ALTER TABLE services ADD COLUMN disabled_by_sync INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_services_provider_sid ON services(provider_service_id);

INSERT OR IGNORE INTO settings (key, value, value_type, group_code, name_ar, description_ar, is_editable, updated_at) VALUES
    ('sync_auto_disable_missing', 'true', 'bool', 'general', 'تعطيل الخدمات المختفية لدى المزود عند المزامنة',
     'عند التفعيل تُعطَّل تلقائياً الخدمة التي لم تعد في قائمة المزود (لا تُحذف ولا يُمس تاريخ طلباتها) وتعود تلقائياً إن عادت. لا يُطبَّق إن أعاد المزود قائمة فارغة أو اختفى أكثر من نصف خدماتنا دفعة واحدة (يُعدّ ذلك عطلاً لا حذفاً)', 1, strftime('%Y-%m-%dT%H:%M:%fZ','now'));
