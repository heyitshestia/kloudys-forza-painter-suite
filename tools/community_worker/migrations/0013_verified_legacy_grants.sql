-- Permanent grants are independent of the expiring supporter/theme fields.
CREATE TABLE verified_legacy_grants (
  user_id TEXT PRIMARY KEY REFERENCES users(id),
  github_provider_id TEXT NOT NULL UNIQUE,
  entitlement_id TEXT NOT NULL UNIQUE,
  granted_at TEXT NOT NULL,
  license_created_at TEXT,
  eligibility_cutoff TEXT NOT NULL,
  source TEXT NOT NULL CHECK(source IN ('signed_legacy_proof','active_entitlement_snapshot')),
  proof_sha256 TEXT,
  verified_at TEXT NOT NULL
);
CREATE TRIGGER verified_legacy_grant_audit AFTER INSERT ON verified_legacy_grants
BEGIN
  INSERT INTO moderation_events(id,artwork_id,actor,action,note,created_at)
  VALUES(lower(hex(randomblob(16))),NULL,NEW.user_id,'verified_legacy_granted',
    json_object('source',NEW.source,'cutoff',NEW.eligibility_cutoff,'proof_sha256',NEW.proof_sha256),NEW.granted_at);
END;
