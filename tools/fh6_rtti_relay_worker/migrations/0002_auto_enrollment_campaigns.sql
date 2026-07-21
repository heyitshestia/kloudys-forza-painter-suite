CREATE TABLE IF NOT EXISTS auto_enrollment_campaigns (
    campaign_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'revoked')),
    code_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    max_devices INTEGER NOT NULL
        CHECK (max_devices >= 1 AND max_devices <= 500),
    enrolled_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS auto_enrollment_campaigns_status_idx
    ON auto_enrollment_campaigns(status, expires_at);

ALTER TABLE helpers ADD COLUMN campaign_id TEXT;

CREATE INDEX IF NOT EXISTS helpers_campaign_idx ON helpers(campaign_id);
CREATE UNIQUE INDEX IF NOT EXISTS helpers_campaign_device_unique
    ON helpers(campaign_id, device_id)
    WHERE campaign_id IS NOT NULL AND device_id IS NOT NULL;
