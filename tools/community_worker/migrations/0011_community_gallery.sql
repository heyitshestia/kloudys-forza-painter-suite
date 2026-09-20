ALTER TABLE artworks ADD COLUMN kind TEXT NOT NULL DEFAULT 'vinyl' CHECK(kind IN ('vinyl', 'livery'));
ALTER TABLE artworks ADD COLUMN car TEXT NOT NULL DEFAULT '';
ALTER TABLE artworks ADD COLUMN starts_at TEXT;
ALTER TABLE artworks ADD COLUMN ends_at TEXT;
ALTER TABLE artworks ADD COLUMN purged_at TEXT;
ALTER TABLE artworks ADD COLUMN vote_score INTEGER NOT NULL DEFAULT 0;
ALTER TABLE artworks ADD COLUMN photo_count INTEGER NOT NULL DEFAULT 0;

CREATE INDEX artworks_expiry ON artworks(ends_at) WHERE ends_at IS NOT NULL AND purged_at IS NULL;
CREATE INDEX artworks_creator_catalog ON artworks(creator_id, published_at DESC, id DESC);

CREATE TABLE artwork_votes (
  artwork_id TEXT NOT NULL REFERENCES artworks(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  value INTEGER NOT NULL CHECK(value IN (-1, 1)),
  updated_at TEXT NOT NULL,
  PRIMARY KEY(artwork_id, user_id)
);

CREATE TABLE artwork_photos (
  artwork_id TEXT NOT NULL REFERENCES artworks(id) ON DELETE CASCADE,
  position INTEGER NOT NULL CHECK(position BETWEEN 0 AND 2),
  object_key TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  PRIMARY KEY(artwork_id, position)
);
