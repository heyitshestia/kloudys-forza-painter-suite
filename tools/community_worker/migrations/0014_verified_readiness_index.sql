-- Cover the per-request unknown-revision check without scanning ready catalogues.
CREATE INDEX idx_artwork_revisions_credit_status_artwork
  ON artwork_revisions(credit_fingerprint_status, artwork_id);
