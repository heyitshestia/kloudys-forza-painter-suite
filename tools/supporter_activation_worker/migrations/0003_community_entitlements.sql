ALTER TABLE licenses ADD COLUMN community_subject_hash TEXT;
ALTER TABLE licenses ADD COLUMN community_entitlement_id TEXT;
ALTER TABLE licenses ADD COLUMN community_bound_at TEXT;

CREATE UNIQUE INDEX licenses_community_entitlement_idx
  ON licenses(community_entitlement_id)
  WHERE community_entitlement_id IS NOT NULL;
