ALTER TABLE artworks ADD COLUMN uses_masks INTEGER NOT NULL DEFAULT 0
  CHECK (uses_masks IN (0, 1));

ALTER TABLE artwork_revisions ADD COLUMN uses_masks INTEGER NOT NULL DEFAULT 0
  CHECK (uses_masks IN (0, 1));
