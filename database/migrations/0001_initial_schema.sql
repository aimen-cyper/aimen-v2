-- =====================================================================
-- الترحيل 0001 — المخطط الأساسي الكامل لنظام SMM Bot
-- ملاحظات:
--   * كل الطوابع الزمنية نصية بصيغة ISO-8601 بتوقيت UTC (مثال: 2026-10-01T09:00:00.000Z)
--   * كل المبالغ أعداد صحيحة بوحدة «نقطة» = 1/10000 من وحدة العملة
--   * ممنوع وضع PRAGMA أو BEGIN/COMMIT داخل ملفات الترحيل (المُرحِّل يتكفل بها)
-- =====================================================================

-- ------------------------- الأدوار والصلاحيات ------------------------- --

CREATE TABLE roles (
    code       TEXT PRIMARY KEY,
    name_ar    TEXT    NOT NULL,
    level      INTEGER NOT NULL DEFAULT 0,
    is_system  INTEGER NOT NULL DEFAULT 1 CHECK (is_system IN (0, 1)),
    created_at TEXT    NOT NULL
);

CREATE TABLE permissions (
    code         TEXT PRIMARY KEY,
    name_ar      TEXT    NOT NULL,
    group_code   TEXT    NOT NULL,
    is_dangerous INTEGER NOT NULL DEFAULT 0 CHECK (is_dangerous IN (0, 1))
);

CREATE TABLE role_permissions (
    role_code       TEXT NOT NULL REFERENCES roles(code) ON DELETE CASCADE,
    permission_code TEXT NOT NULL REFERENCES permissions(code) ON DELETE CASCADE,
    PRIMARY KEY (role_code, permission_code)
);

-- ------------------------------ المستخدمون ---------------------------- --

CREATE TABLE users (
    id                    INTEGER PRIMARY KEY,
    telegram_id           INTEGER NOT NULL UNIQUE,
    username              TEXT,
    first_name            TEXT,
    last_name             TEXT,
    balance_units         INTEGER NOT NULL DEFAULT 0 CHECK (balance_units >= 0),
    total_spent_units     INTEGER NOT NULL DEFAULT 0 CHECK (total_spent_units >= 0),
    total_deposited_units INTEGER NOT NULL DEFAULT 0 CHECK (total_deposited_units >= 0),
    role                  TEXT    NOT NULL DEFAULT 'user' REFERENCES roles(code) ON DELETE RESTRICT,
    is_banned             INTEGER NOT NULL DEFAULT 0 CHECK (is_banned IN (0, 1)),
    ban_reason            TEXT,
    banned_at             TEXT,
    blocked_bot           INTEGER NOT NULL DEFAULT 0 CHECK (blocked_bot IN (0, 1)),
    language              TEXT    NOT NULL DEFAULT 'ar',
    referrer_id           INTEGER REFERENCES users(id) ON DELETE SET NULL,
    notes                 TEXT,
    created_at            TEXT    NOT NULL,
    updated_at            TEXT    NOT NULL,
    last_activity         TEXT
);

CREATE INDEX idx_users_role        ON users(role);
CREATE INDEX idx_users_banned      ON users(is_banned);
CREATE INDEX idx_users_activity    ON users(last_activity);
CREATE INDEX idx_users_created     ON users(created_at);

-- استثناءات صلاحيات فردية تتجاوز الدور (منح أو منع لمستخدم بعينه)
CREATE TABLE user_permissions (
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission_code TEXT    NOT NULL REFERENCES permissions(code) ON DELETE CASCADE,
    allow           INTEGER NOT NULL CHECK (allow IN (0, 1)),
    granted_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      TEXT    NOT NULL,
    PRIMARY KEY (user_id, permission_code)
);

-- حفظ خطوة المحادثة الحالية حتى لا يضيع المستخدم بعد إعادة تشغيل البوت
CREATE TABLE user_states (
    user_id    INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    chat_id    INTEGER,
    state      TEXT,
    data_json  TEXT NOT NULL DEFAULT '{}',
    expires_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_user_states_expires ON user_states(expires_at);

-- ------------------------------- المزودون ----------------------------- --

CREATE TABLE providers (
    id                          INTEGER PRIMARY KEY,
    name                        TEXT    NOT NULL UNIQUE,
    api_url                     TEXT    NOT NULL,
    api_key_enc                 TEXT    NOT NULL,          -- مشفّر بـ Fernet
    api_key_hint                TEXT,                      -- آخر 4 محارف للعرض فقط
    api_type                    TEXT    NOT NULL DEFAULT 'perfect_panel',
    balance_units               INTEGER NOT NULL DEFAULT 0,
    currency                    TEXT    NOT NULL DEFAULT 'USD',
    balance_checked_at          TEXT,
    low_balance_threshold_units INTEGER,
    is_active                   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    priority                    INTEGER NOT NULL DEFAULT 100,
    timeout_seconds             INTEGER NOT NULL DEFAULT 30 CHECK (timeout_seconds > 0),
    consecutive_failures        INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
    disabled_until              TEXT,                      -- تعطيل مؤقت (قاطع الدائرة)
    last_error                  TEXT,
    last_success_at             TEXT,
    created_at                  TEXT    NOT NULL,
    updated_at                  TEXT    NOT NULL
);

CREATE INDEX idx_providers_active ON providers(is_active);

CREATE TABLE provider_balance_snapshots (
    id            INTEGER PRIMARY KEY,
    provider_id   INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    balance_units INTEGER NOT NULL,
    currency      TEXT    NOT NULL DEFAULT 'USD',
    created_at    TEXT    NOT NULL
);

CREATE INDEX idx_provider_snapshots ON provider_balance_snapshots(provider_id, created_at);

-- ------------------------- التصنيفات والخدمات -------------------------- --

CREATE TABLE service_categories (
    id         INTEGER PRIMARY KEY,
    name_ar    TEXT    NOT NULL,
    name_en    TEXT,
    emoji      TEXT    NOT NULL DEFAULT '📦',
    sort_order INTEGER NOT NULL DEFAULT 100,
    is_active  INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);

CREATE INDEX idx_categories_active ON service_categories(is_active, sort_order);

CREATE TABLE services (
    id                            INTEGER PRIMARY KEY,
    category_id                   INTEGER NOT NULL REFERENCES service_categories(id) ON DELETE RESTRICT,
    provider_id                   INTEGER NOT NULL REFERENCES providers(id) ON DELETE RESTRICT,
    provider_service_id           TEXT    NOT NULL,
    name                          TEXT    NOT NULL,
    description                   TEXT,
    service_type                  TEXT    NOT NULL DEFAULT 'default'
                                   CHECK (service_type IN ('default', 'custom_comments', 'drip_feed', 'subscription')),
    price_per_1000_units          INTEGER NOT NULL CHECK (price_per_1000_units > 0),
    provider_price_per_1000_units INTEGER CHECK (provider_price_per_1000_units IS NULL OR provider_price_per_1000_units >= 0),
    min_quantity                  INTEGER NOT NULL CHECK (min_quantity > 0),
    max_quantity                  INTEGER NOT NULL CHECK (max_quantity > 0),
    dripfeed_enabled              INTEGER NOT NULL DEFAULT 0 CHECK (dripfeed_enabled IN (0, 1)),
    refill_enabled                INTEGER NOT NULL DEFAULT 0 CHECK (refill_enabled IN (0, 1)),
    cancel_enabled                INTEGER NOT NULL DEFAULT 0 CHECK (cancel_enabled IN (0, 1)),
    link_pattern                  TEXT,
    avg_time_text                 TEXT,
    is_active                     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    is_archived                   INTEGER NOT NULL DEFAULT 0 CHECK (is_archived IN (0, 1)),
    sort_order                    INTEGER NOT NULL DEFAULT 100,
    created_at                    TEXT    NOT NULL,
    updated_at                    TEXT    NOT NULL,
    CHECK (max_quantity >= min_quantity)
);

CREATE INDEX idx_services_category ON services(category_id, is_active, is_archived);
CREATE INDEX idx_services_provider ON services(provider_id, provider_service_id);

CREATE TABLE service_price_history (
    id             INTEGER PRIMARY KEY,
    service_id     INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    old_price_units INTEGER,
    new_price_units INTEGER NOT NULL,
    old_min        INTEGER,
    new_min        INTEGER,
    old_max        INTEGER,
    new_max        INTEGER,
    changed_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    source         TEXT    NOT NULL DEFAULT 'admin' CHECK (source IN ('admin', 'sync')),
    created_at     TEXT    NOT NULL
);

CREATE INDEX idx_price_history_service ON service_price_history(service_id, created_at);

-- --------------------------- طرق الدفع والشحن -------------------------- --

CREATE TABLE payment_methods (
    id               INTEGER PRIMARY KEY,
    code             TEXT    NOT NULL UNIQUE,
    name_ar          TEXT    NOT NULL,
    type             TEXT    NOT NULL DEFAULT 'manual' CHECK (type IN ('manual', 'crypto', 'gateway')),
    instructions_ar  TEXT    NOT NULL DEFAULT '',
    account_details  TEXT    NOT NULL DEFAULT '',
    min_amount_units INTEGER NOT NULL DEFAULT 0 CHECK (min_amount_units >= 0),
    max_amount_units INTEGER CHECK (max_amount_units IS NULL OR max_amount_units > 0),
    requires_proof   INTEGER NOT NULL DEFAULT 1 CHECK (requires_proof IN (0, 1)),
    is_active        INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    sort_order       INTEGER NOT NULL DEFAULT 100,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL
);

CREATE TABLE payments (
    id                    INTEGER PRIMARY KEY,
    user_id               INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    method_id             INTEGER NOT NULL REFERENCES payment_methods(id) ON DELETE RESTRICT,
    amount_units          INTEGER NOT NULL CHECK (amount_units > 0),
    credited_units        INTEGER CHECK (credited_units IS NULL OR credited_units >= 0),
    status                TEXT    NOT NULL DEFAULT 'pending'
                           CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled', 'expired')),
    transaction_reference TEXT,
    proof_file_id         TEXT,
    proof_file_type       TEXT CHECK (proof_file_type IS NULL OR proof_file_type IN ('photo', 'document')),
    user_note             TEXT,
    admin_id              INTEGER REFERENCES users(id) ON DELETE SET NULL,
    admin_note            TEXT,
    reject_reason         TEXT,
    reviewed_at           TEXT,
    expires_at            TEXT,
    created_at            TEXT    NOT NULL,
    updated_at            TEXT    NOT NULL
);

CREATE INDEX idx_payments_status  ON payments(status, created_at);
CREATE INDEX idx_payments_user    ON payments(user_id, created_at);
CREATE INDEX idx_payments_expires ON payments(status, expires_at);

-- -------------------------------- الطلبات ------------------------------ --

CREATE TABLE orders (
    id                            INTEGER PRIMARY KEY,
    public_code                   TEXT UNIQUE,
    user_id                       INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    service_id                    INTEGER NOT NULL REFERENCES services(id) ON DELETE RESTRICT,
    provider_id                   INTEGER NOT NULL REFERENCES providers(id) ON DELETE RESTRICT,
    service_name_snapshot         TEXT    NOT NULL,
    price_per_1000_snapshot_units INTEGER NOT NULL CHECK (price_per_1000_snapshot_units > 0),
    link                          TEXT    NOT NULL,
    quantity                      INTEGER NOT NULL CHECK (quantity > 0),
    cost_units                    INTEGER NOT NULL CHECK (cost_units >= 0),
    provider_cost_units           INTEGER CHECK (provider_cost_units IS NULL OR provider_cost_units >= 0),
    status                        TEXT    NOT NULL DEFAULT 'pending'
                                   CHECK (status IN ('pending', 'submitting', 'submit_uncertain', 'submitted',
                                                     'in_progress', 'partial', 'completed', 'canceled',
                                                     'failed', 'refunded')),
    provider_status               TEXT,
    provider_order_id             TEXT,
    client_request_id             TEXT    NOT NULL UNIQUE,   -- مفتاح منع الطلب المكرر
    start_count                   INTEGER,
    remains                       INTEGER,
    delivered_quantity            INTEGER,
    refund_amount_units           INTEGER NOT NULL DEFAULT 0 CHECK (refund_amount_units >= 0),
    refunded_at                   TEXT,
    submit_attempts               INTEGER NOT NULL DEFAULT 0 CHECK (submit_attempts >= 0),
    checks_count                  INTEGER NOT NULL DEFAULT 0 CHECK (checks_count >= 0),
    last_error                    TEXT,
    locked_by                     TEXT,
    locked_until                  TEXT,
    next_check_at                 TEXT,
    created_at                    TEXT    NOT NULL,
    updated_at                    TEXT    NOT NULL,
    submitted_at                  TEXT,
    completed_at                  TEXT,
    cancelled_at                  TEXT,
    CHECK (refund_amount_units <= cost_units)
);

CREATE UNIQUE INDEX idx_orders_provider_order
    ON orders(provider_id, provider_order_id)
    WHERE provider_order_id IS NOT NULL;
CREATE INDEX idx_orders_status_check ON orders(status, next_check_at);
CREATE INDEX idx_orders_user         ON orders(user_id, created_at);
CREATE INDEX idx_orders_created      ON orders(created_at);
CREATE INDEX idx_orders_service      ON orders(service_id);

CREATE TABLE order_status_history (
    id                  INTEGER PRIMARY KEY,
    order_id            INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    from_status         TEXT,
    to_status           TEXT    NOT NULL,
    actor_type          TEXT    NOT NULL DEFAULT 'system'
                         CHECK (actor_type IN ('system', 'job', 'admin', 'user', 'provider')),
    actor_id            INTEGER REFERENCES users(id) ON DELETE SET NULL,
    reason              TEXT,
    provider_status_raw TEXT,
    created_at          TEXT    NOT NULL
);

CREATE INDEX idx_order_history ON order_status_history(order_id, created_at);

-- --------------------------- الحركات المالية --------------------------- --
-- جدول «إضافة فقط»: ممنوع UPDATE أو DELETE عليه، وأي تصحيح يكون بحركة جديدة.

CREATE TABLE transactions (
    id                   INTEGER PRIMARY KEY,
    user_id              INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    order_id             INTEGER REFERENCES orders(id) ON DELETE RESTRICT,
    payment_id           INTEGER REFERENCES payments(id) ON DELETE RESTRICT,
    type                 TEXT    NOT NULL
                          CHECK (type IN ('deposit', 'order', 'refund', 'partial_refund',
                                          'manual_credit', 'manual_debit', 'withdraw', 'adjustment')),
    direction            TEXT    NOT NULL CHECK (direction IN ('credit', 'debit')),
    amount_units         INTEGER NOT NULL CHECK (amount_units > 0),
    balance_before_units INTEGER NOT NULL CHECK (balance_before_units >= 0),
    balance_after_units  INTEGER NOT NULL CHECK (balance_after_units >= 0),
    description          TEXT,
    reference            TEXT UNIQUE,          -- مفتاح منع تكرار العملية المالية
    actor_id             INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at           TEXT    NOT NULL
);

CREATE INDEX idx_tx_user    ON transactions(user_id, created_at);
CREATE INDEX idx_tx_type    ON transactions(type, created_at);
CREATE INDEX idx_tx_order   ON transactions(order_id);
CREATE INDEX idx_tx_payment ON transactions(payment_id);

-- --------------------------------- الدعم ------------------------------- --

CREATE TABLE support_tickets (
    id               INTEGER PRIMARY KEY,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    subject          TEXT    NOT NULL,
    category         TEXT    NOT NULL DEFAULT 'other'
                      CHECK (category IN ('order', 'payment', 'service', 'other')),
    related_order_id INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    status           TEXT    NOT NULL DEFAULT 'open'
                      CHECK (status IN ('open', 'pending_admin', 'pending_user', 'closed')),
    priority         TEXT    NOT NULL DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high')),
    assigned_admin   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    last_message_at  TEXT,
    closed_by        INTEGER REFERENCES users(id) ON DELETE SET NULL,
    close_reason     TEXT,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL,
    closed_at        TEXT
);

CREATE INDEX idx_tickets_status ON support_tickets(status, last_message_at);
CREATE INDEX idx_tickets_user   ON support_tickets(user_id, created_at);

CREATE TABLE support_messages (
    id                  INTEGER PRIMARY KEY,
    ticket_id           INTEGER NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
    sender_id           INTEGER REFERENCES users(id) ON DELETE SET NULL,
    sender_type         TEXT    NOT NULL CHECK (sender_type IN ('user', 'admin', 'system')),
    message             TEXT    NOT NULL,
    attachment_file_id  TEXT,
    attachment_type     TEXT,
    telegram_message_id INTEGER,
    is_read_by_user     INTEGER NOT NULL DEFAULT 0 CHECK (is_read_by_user IN (0, 1)),
    is_read_by_admin    INTEGER NOT NULL DEFAULT 0 CHECK (is_read_by_admin IN (0, 1)),
    created_at          TEXT    NOT NULL
);

CREATE INDEX idx_ticket_messages ON support_messages(ticket_id, created_at);

-- ------------------------ الإشعارات (صندوق الإرسال) --------------------- --

CREATE TABLE notifications (
    id                  INTEGER PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type                TEXT    NOT NULL,
    title               TEXT    NOT NULL DEFAULT '',
    message             TEXT    NOT NULL,
    payload_json        TEXT,
    dedupe_key          TEXT    NOT NULL UNIQUE,   -- يمنع إرسال نفس الإشعار مرتين
    status              TEXT    NOT NULL DEFAULT 'queued'
                         CHECK (status IN ('queued', 'sent', 'failed', 'skipped')),
    attempts            INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    next_attempt_at     TEXT,
    last_error          TEXT,
    telegram_message_id INTEGER,
    is_read             INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0, 1)),
    created_at          TEXT    NOT NULL,
    sent_at             TEXT
);

CREATE INDEX idx_notifications_queue ON notifications(status, next_attempt_at);
CREATE INDEX idx_notifications_user  ON notifications(user_id, created_at);

-- --------------------------- السجلات والإعدادات ------------------------- --

CREATE TABLE audit_logs (
    id           INTEGER PRIMARY KEY,
    admin_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action       TEXT    NOT NULL,
    target_type  TEXT,
    target_id    TEXT,
    details_json TEXT,
    before_json  TEXT,
    after_json   TEXT,
    source       TEXT    NOT NULL DEFAULT 'telegram',
    created_at   TEXT    NOT NULL
);

CREATE INDEX idx_audit_admin  ON audit_logs(admin_id, created_at);
CREATE INDEX idx_audit_target ON audit_logs(target_type, target_id);
CREATE INDEX idx_audit_action ON audit_logs(action, created_at);

CREATE TABLE settings (
    key            TEXT PRIMARY KEY,
    value          TEXT    NOT NULL DEFAULT '',
    value_type     TEXT    NOT NULL DEFAULT 'str'
                    CHECK (value_type IN ('str', 'int', 'bool', 'json', 'money')),
    group_code     TEXT    NOT NULL DEFAULT 'general',
    name_ar        TEXT    NOT NULL DEFAULT '',
    description_ar TEXT,
    is_editable    INTEGER NOT NULL DEFAULT 1 CHECK (is_editable IN (0, 1)),
    updated_by     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_at     TEXT    NOT NULL
);

CREATE INDEX idx_settings_group ON settings(group_code);

-- ------------------------------- الإذاعة -------------------------------- --

CREATE TABLE broadcasts (
    id                 INTEGER PRIMARY KEY,
    admin_id           INTEGER REFERENCES users(id) ON DELETE SET NULL,
    message_text       TEXT    NOT NULL DEFAULT '',
    parse_mode         TEXT,
    media_file_id      TEXT,
    media_type         TEXT,
    buttons_json       TEXT,
    target             TEXT    NOT NULL DEFAULT 'all',
    target_filter_json TEXT,
    total_count        INTEGER NOT NULL DEFAULT 0 CHECK (total_count >= 0),
    sent_count         INTEGER NOT NULL DEFAULT 0 CHECK (sent_count >= 0),
    failed_count       INTEGER NOT NULL DEFAULT 0 CHECK (failed_count >= 0),
    blocked_count      INTEGER NOT NULL DEFAULT 0 CHECK (blocked_count >= 0),
    status             TEXT    NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft', 'running', 'paused', 'completed', 'cancelled')),
    started_at         TEXT,
    finished_at        TEXT,
    created_at         TEXT    NOT NULL
);

CREATE TABLE broadcast_recipients (
    id           INTEGER PRIMARY KEY,
    broadcast_id INTEGER NOT NULL REFERENCES broadcasts(id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status       TEXT    NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'sent', 'failed', 'blocked')),
    error        TEXT,
    sent_at      TEXT,
    UNIQUE (broadcast_id, user_id)
);

CREATE INDEX idx_broadcast_recipients ON broadcast_recipients(broadcast_id, status);

-- --------------------- منع التكرار والسجلات التشخيصية ------------------- --

CREATE TABLE idempotency_keys (
    key         TEXT PRIMARY KEY,
    scope       TEXT    NOT NULL,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    result_json TEXT,
    created_at  TEXT    NOT NULL,
    expires_at  TEXT    NOT NULL
);

CREATE INDEX idx_idempotency_expires ON idempotency_keys(expires_at);

CREATE TABLE provider_requests (
    id               INTEGER PRIMARY KEY,
    provider_id      INTEGER NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    order_id         INTEGER REFERENCES orders(id) ON DELETE SET NULL,
    action           TEXT    NOT NULL CHECK (action IN ('add', 'status', 'balance', 'services', 'cancel', 'refill')),
    request_summary  TEXT,        -- ملخص بدون أي مفتاح سري
    http_status      INTEGER,
    response_snippet TEXT,        -- مقتطع منقّى من الاستجابة
    duration_ms      INTEGER,
    is_success       INTEGER NOT NULL DEFAULT 0 CHECK (is_success IN (0, 1)),
    error_type       TEXT,
    created_at       TEXT    NOT NULL
);

CREATE INDEX idx_provider_requests ON provider_requests(provider_id, created_at);
CREATE INDEX idx_provider_req_order ON provider_requests(order_id);

CREATE TABLE error_logs (
    id                 INTEGER PRIMARY KEY,
    level              TEXT    NOT NULL DEFAULT 'ERROR',
    source             TEXT    NOT NULL DEFAULT 'app',
    error_type         TEXT,
    message            TEXT    NOT NULL,
    traceback_snippet  TEXT,
    user_id            INTEGER REFERENCES users(id) ON DELETE SET NULL,
    update_summary     TEXT,
    notified_admin     INTEGER NOT NULL DEFAULT 0 CHECK (notified_admin IN (0, 1)),
    created_at         TEXT    NOT NULL
);

CREATE INDEX idx_error_logs ON error_logs(created_at);

CREATE TABLE backups (
    id          INTEGER PRIMARY KEY,
    filename    TEXT    NOT NULL,
    path        TEXT    NOT NULL,
    size_bytes  INTEGER NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
    sha256      TEXT,
    type        TEXT    NOT NULL DEFAULT 'manual' CHECK (type IN ('manual', 'scheduled', 'pre_operation')),
    created_by  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    status      TEXT    NOT NULL DEFAULT 'ok',
    created_at  TEXT    NOT NULL
);

CREATE INDEX idx_backups_created ON backups(created_at);
