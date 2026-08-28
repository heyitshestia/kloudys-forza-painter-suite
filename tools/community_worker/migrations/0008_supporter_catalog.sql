ALTER TABLE users ADD COLUMN supporter_entitlement_id TEXT;
ALTER TABLE users ADD COLUMN supporter_verified_at TEXT;
ALTER TABLE users ADD COLUMN supporter_verified_until TEXT;

CREATE UNIQUE INDEX users_supporter_entitlement_idx
  ON users(supporter_entitlement_id)
  WHERE supporter_entitlement_id IS NOT NULL;

ALTER TABLE artworks ADD COLUMN supporter_only INTEGER NOT NULL DEFAULT 0
  CHECK (supporter_only IN (0, 1));

CREATE INDEX artworks_status_supporter_created_idx
  ON artworks(status, supporter_only, created_at DESC);
