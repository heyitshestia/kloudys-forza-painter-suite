ALTER TABLE artworks
  ADD COLUMN classification TEXT NOT NULL DEFAULT 'toolmade'
  CHECK (classification IN ('handmade', 'toolmade'));

CREATE INDEX artworks_status_classification_created_idx
  ON artworks(status, classification, created_at DESC);
