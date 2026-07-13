CREATE TABLE IF NOT EXISTS licenses (
    key_id TEXT PRIMARY KEY,
    signature_sha256 TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'revoked')),
    device_id TEXT,
    activated_at TEXT,
    conflict_count INTEGER NOT NULL DEFAULT 0,
    first_conflict_at TEXT,
    last_conflict_at TEXT,
    reset_count INTEGER NOT NULL DEFAULT 0,
    last_reset_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS licenses_status_idx ON licenses(status);
CREATE INDEX IF NOT EXISTS licenses_last_conflict_idx ON licenses(last_conflict_at);

CREATE TABLE IF NOT EXISTS admin_events (
    request_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    key_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS admin_events_created_idx ON admin_events(created_at);
