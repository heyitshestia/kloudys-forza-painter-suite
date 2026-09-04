CREATE TABLE IF NOT EXISTS github_sync_outbox (
    event_id TEXT PRIMARY KEY,
    registry_fingerprint TEXT NOT NULL UNIQUE,
    profile_id TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'dispatching', 'delivered', 'failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT,
    delivered_at TEXT,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS github_sync_outbox_status_created_idx
    ON github_sync_outbox(status, created_at);
