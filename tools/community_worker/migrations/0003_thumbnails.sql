ALTER TABLE artworks ADD COLUMN thumbnail_hash TEXT NOT NULL DEFAULT '';

ALTER TABLE artwork_revisions ADD COLUMN thumbnail_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE artwork_revisions ADD COLUMN thumbnail_key TEXT NOT NULL DEFAULT '';
ALTER TABLE artwork_revisions ADD COLUMN thumbnail_bytes INTEGER NOT NULL DEFAULT 0;
