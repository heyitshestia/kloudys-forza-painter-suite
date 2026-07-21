CREATE TABLE IF NOT EXISTS helpers (
    helper_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'revoked')),
    enrollment_hash TEXT UNIQUE,
    enrollment_expires_at TEXT,
    enrollment_used_at TEXT,
    device_id TEXT,
    credential_hash TEXT UNIQUE,
    submit_count INTEGER NOT NULL DEFAULT 0,
    reject_count INTEGER NOT NULL DEFAULT 0,
    last_submit_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS helpers_status_idx ON helpers(status);
CREATE INDEX IF NOT EXISTS helpers_credential_idx ON helpers(credential_hash);

CREATE TABLE IF NOT EXISTS profiles (
    profile_id TEXT PRIMARY KEY,
    profile_json TEXT NOT NULL,
    helper_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (helper_id) REFERENCES helpers(helper_id)
);

CREATE INDEX IF NOT EXISTS profiles_updated_idx ON profiles(updated_at DESC);

CREATE TABLE IF NOT EXISTS submissions (
    submission_id TEXT PRIMARY KEY,
    helper_id TEXT NOT NULL,
    profile_id TEXT,
    accepted INTEGER NOT NULL CHECK (accepted IN (0, 1)),
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (helper_id) REFERENCES helpers(helper_id)
);

CREATE INDEX IF NOT EXISTS submissions_helper_created_idx ON submissions(helper_id, created_at DESC);
CREATE INDEX IF NOT EXISTS submissions_created_idx ON submissions(created_at DESC);

CREATE TABLE IF NOT EXISTS registry_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_events (
    request_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    subject_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS admin_events_created_idx ON admin_events(created_at DESC);
