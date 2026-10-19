-- No account, installation ID, address, user agent or event payload is retained.
CREATE TABLE activity_totals (
  kind TEXT NOT NULL CHECK (kind IN ('day','week','month')),
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  installations INTEGER NOT NULL DEFAULT 0 CHECK (installations >= 0),
  PRIMARY KEY (kind, period_start)
) WITHOUT ROWID;

CREATE TABLE activity_tokens (
  kind TEXT NOT NULL CHECK (kind IN ('day','week','month')),
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  token_hash TEXT NOT NULL CHECK (length(token_hash) = 64),
  expires_at INTEGER NOT NULL,
  PRIMARY KEY (kind, period_start, token_hash)
) WITHOUT ROWID;
CREATE INDEX activity_tokens_expiry ON activity_tokens(expires_at);

-- Deduplication and the aggregate increment are one database operation.
CREATE TRIGGER activity_token_count AFTER INSERT ON activity_tokens BEGIN
  INSERT INTO activity_totals(kind, period_start, period_end, installations)
    VALUES (NEW.kind, NEW.period_start, NEW.period_end, 1)
    ON CONFLICT(kind, period_start) DO UPDATE SET installations = installations + 1;
END;

CREATE TABLE activity_budgets (
  -- Cleanup reserves deletion slots, not incoming requests.
  kind TEXT NOT NULL CHECK (kind IN ('minute','day','cleanup')),
  window_start INTEGER NOT NULL,
  requests INTEGER NOT NULL CHECK (requests > 0),
  PRIMARY KEY (kind, window_start)
) WITHOUT ROWID;

CREATE TABLE activity_metadata (
  key TEXT PRIMARY KEY CHECK (key = 'collection_started_day'),
  value TEXT NOT NULL
) WITHOUT ROWID;
