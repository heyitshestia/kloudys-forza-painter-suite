CREATE TABLE IF NOT EXISTS kofi_inbox (
    event_id TEXT PRIMARY KEY,
    payload_encrypted TEXT NOT NULL,
    received_at TEXT NOT NULL,
    imported_at TEXT
);

CREATE INDEX IF NOT EXISTS kofi_inbox_pending_idx
    ON kofi_inbox(imported_at, event_id);
