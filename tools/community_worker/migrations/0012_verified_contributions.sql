-- Additive only. Authorization still defaults to legacy; readiness is explicit.
ALTER TABLE artwork_revisions ADD COLUMN credit_fingerprint TEXT;
ALTER TABLE artwork_revisions ADD COLUMN credit_fingerprint_status TEXT NOT NULL DEFAULT 'unknown'
  CHECK(credit_fingerprint_status IN ('unknown', 'qualified', 'review_required'));
ALTER TABLE artwork_revisions ADD COLUMN credit_authorship TEXT NOT NULL DEFAULT 'unknown'
  CHECK(credit_authorship IN ('unknown', 'own', 'permission'));

-- A submitted revision cannot undo a staff classification correction that
-- committed while its files were uploading. D1 rolls the whole batch back.
CREATE TRIGGER artwork_revision_classification_guard BEFORE INSERT ON artwork_revisions
WHEN json_extract(NEW.manifest_json,'$.classification') IN ('handmade','toolmade')
  AND json_extract(NEW.manifest_json,'$.classification') IS NOT
      (SELECT classification FROM artworks WHERE id=NEW.artwork_id)
BEGIN
  SELECT RAISE(ABORT,'classification_conflict');
END;

CREATE TABLE vinyl_fingerprints (
  version INTEGER NOT NULL CHECK(version = 1),
  fingerprint TEXT NOT NULL,
  artwork_id TEXT NOT NULL,
  historical_collision INTEGER NOT NULL DEFAULT 0 CHECK(historical_collision IN (0,1)),
  reserved_at TEXT NOT NULL,
  PRIMARY KEY(version, fingerprint)
);
CREATE TABLE vinyl_contributions (
  artwork_id TEXT PRIMARY KEY REFERENCES artworks(id) ON DELETE CASCADE,
  creator_id TEXT NOT NULL REFERENCES users(id),
  assertion_revision INTEGER NOT NULL,
  assertion_content_hash TEXT NOT NULL,
  assertion_source TEXT NOT NULL CHECK(assertion_source IN ('upload','owner_claim','admin')),
  asserted_at TEXT NOT NULL,
  fingerprint TEXT,
  eligible_at TEXT,
  credited_at TEXT,
  revoked_at TEXT,
  revocation_note TEXT NOT NULL DEFAULT ''
);
CREATE INDEX vinyl_contribution_creator ON vinyl_contributions(creator_id, revoked_at);
CREATE TRIGGER vinyl_credit_audit AFTER UPDATE OF credited_at,revoked_at ON vinyl_contributions
WHEN (NEW.credited_at IS NOT OLD.credited_at AND NEW.credited_at IS NOT NULL)
  OR NEW.revoked_at IS NOT OLD.revoked_at
BEGIN
  INSERT INTO moderation_events(id,artwork_id,actor,action,note,created_at)
  VALUES(lower(hex(randomblob(16))),NEW.artwork_id,
    CASE WHEN NEW.revoked_at IS NOT OLD.revoked_at THEN 'admin' ELSE 'contribution-ledger' END,
    CASE WHEN NEW.revoked_at IS NOT OLD.revoked_at THEN
      CASE WHEN NEW.revoked_at IS NULL THEN 'credit_restore' ELSE 'credit_revoke' END
      ELSE 'credit_issued' END,
    NEW.revocation_note,strftime('%Y-%m-%dT%H:%M:%fZ','now'));
END;
CREATE TABLE vinyl_publications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  artwork_id TEXT NOT NULL REFERENCES artworks(id) ON DELETE CASCADE,
  revision INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  committed_at TEXT NOT NULL,
  starts_at TEXT,
  ends_at TEXT,
  closed_at TEXT
);
CREATE UNIQUE INDEX vinyl_publication_open ON vinyl_publications(artwork_id) WHERE closed_at IS NULL;
CREATE INDEX vinyl_publication_evidence ON vinyl_publications(artwork_id, revision, content_hash);

-- Commit-time observations are captured inside the same transaction as each
-- publication transition, including restore/approval/removal, not a later job.
CREATE TRIGGER vinyl_publication_insert AFTER INSERT ON artworks
WHEN NEW.kind = 'vinyl' AND NEW.status = 'published' AND NEW.purged_at IS NULL
BEGIN
  INSERT INTO vinyl_publications(artwork_id, revision, content_hash, committed_at, starts_at, ends_at)
  VALUES(NEW.id, NEW.current_revision, NEW.content_hash, strftime('%Y-%m-%dT%H:%M:%fZ','now'), NEW.starts_at, NEW.ends_at);
END;
CREATE TRIGGER vinyl_publication_change AFTER UPDATE ON artworks
WHEN NEW.status IS NOT OLD.status OR NEW.current_revision IS NOT OLD.current_revision
  OR NEW.content_hash IS NOT OLD.content_hash OR NEW.starts_at IS NOT OLD.starts_at
  OR NEW.ends_at IS NOT OLD.ends_at OR NEW.purged_at IS NOT OLD.purged_at
BEGIN
  UPDATE vinyl_publications SET closed_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
    WHERE artwork_id = NEW.id AND closed_at IS NULL;
  INSERT INTO vinyl_publications(artwork_id, revision, content_hash, committed_at, starts_at, ends_at)
    SELECT NEW.id, NEW.current_revision, NEW.content_hash, strftime('%Y-%m-%dT%H:%M:%fZ','now'), NEW.starts_at, NEW.ends_at
    WHERE NEW.kind = 'vinyl' AND NEW.status = 'published' AND NEW.purged_at IS NULL;
END;

-- Eligibility uses the committed window, not current visibility or cron timing.
CREATE VIEW vinyl_eligible_contributions AS
SELECT c.artwork_id, MIN(MAX(p.committed_at, COALESCE(p.starts_at,p.committed_at))) AS eligible_at
FROM vinyl_contributions c
JOIN artworks a ON a.id=c.artwork_id AND a.kind='vinyl' AND a.classification='handmade'
JOIN vinyl_fingerprints f ON f.version=1 AND f.fingerprint=c.fingerprint
  AND f.artwork_id=c.artwork_id AND f.historical_collision=0
JOIN vinyl_publications p ON p.artwork_id=c.artwork_id
  AND p.revision=c.assertion_revision AND p.content_hash=c.assertion_content_hash
WHERE MAX(p.committed_at,COALESCE(p.starts_at,p.committed_at)) <= strftime('%Y-%m-%dT%H:%M:%fZ','now')
  AND (p.ends_at IS NULL OR MAX(p.committed_at,COALESCE(p.starts_at,p.committed_at)) < p.ends_at)
  AND (p.closed_at IS NULL OR MAX(p.committed_at,COALESCE(p.starts_at,p.committed_at)) < p.closed_at)
GROUP BY c.artwork_id;

-- Do not infer earlier publication from published_at: upcoming releases use it
-- too. Snapshot only the currently committed publication at migration time.
INSERT INTO vinyl_publications(artwork_id,revision,content_hash,committed_at,starts_at,ends_at)
SELECT id,current_revision,content_hash,strftime('%Y-%m-%dT%H:%M:%fZ','now'),starts_at,ends_at
FROM artworks WHERE kind='vinyl' AND status='published' AND purged_at IS NULL;

CREATE TRIGGER vinyl_settle_before_transition BEFORE UPDATE ON artworks
WHEN NEW.status IS NOT OLD.status OR NEW.current_revision IS NOT OLD.current_revision
  OR NEW.content_hash IS NOT OLD.content_hash OR NEW.starts_at IS NOT OLD.starts_at
  OR NEW.ends_at IS NOT OLD.ends_at OR NEW.purged_at IS NOT OLD.purged_at
BEGIN
  UPDATE vinyl_contributions SET
    eligible_at=(SELECT eligible_at FROM vinyl_eligible_contributions WHERE artwork_id=OLD.id),
    credited_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
  WHERE artwork_id=OLD.id AND credited_at IS NULL AND revoked_at IS NULL
    AND EXISTS(SELECT 1 FROM service_settings WHERE key='verified_fingerprints_v1' AND value='ready')
    AND EXISTS(SELECT 1 FROM vinyl_eligible_contributions WHERE artwork_id=OLD.id);
END;
