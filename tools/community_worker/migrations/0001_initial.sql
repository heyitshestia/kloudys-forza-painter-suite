PRAGMA foreign_keys = ON;

CREATE TABLE users (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL CHECK (provider IN ('github', 'local-test')),
  provider_id TEXT NOT NULL,
  provider_login TEXT NOT NULL,
  username TEXT,
  username_norm TEXT UNIQUE,
  bio TEXT NOT NULL DEFAULT '',
  website_url TEXT NOT NULL DEFAULT '',
  avatar_url TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  suspended_at TEXT,
  UNIQUE(provider, provider_id)
);

CREATE TRIGGER users_username_immutable
BEFORE UPDATE OF username ON users
WHEN OLD.username IS NOT NULL AND NEW.username IS NOT OLD.username
BEGIN
  SELECT RAISE(ABORT, 'username_immutable');
END;

CREATE TABLE sessions (
  token_hash TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);
CREATE INDEX sessions_user_idx ON sessions(user_id);

CREATE TABLE artworks (
  id TEXT PRIMARY KEY,
  creator_id TEXT NOT NULL REFERENCES users(id),
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL,
  tags_json TEXT NOT NULL,
  games_json TEXT NOT NULL,
  license TEXT NOT NULL,
  schema_version INTEGER NOT NULL DEFAULT 1,
  shape_count INTEGER NOT NULL,
  group_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL CHECK (status IN ('pending', 'published', 'rejected', 'removed')),
  rejection_reason TEXT NOT NULL DEFAULT '',
  featured INTEGER NOT NULL DEFAULT 0 CHECK (featured IN (0, 1)),
  current_revision INTEGER NOT NULL DEFAULT 1,
  content_hash TEXT NOT NULL,
  preview_hash TEXT NOT NULL,
  download_count INTEGER NOT NULL DEFAULT 0,
  favorite_count INTEGER NOT NULL DEFAULT 0,
  report_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  published_at TEXT
);
CREATE INDEX artworks_status_created_idx ON artworks(status, created_at DESC);
CREATE INDEX artworks_status_category_idx ON artworks(status, category, created_at DESC);
CREATE INDEX artworks_creator_idx ON artworks(creator_id, status, updated_at DESC);
CREATE INDEX artworks_popular_idx ON artworks(status, download_count DESC, favorite_count DESC);
CREATE UNIQUE INDEX artworks_active_content_hash_idx
  ON artworks(content_hash)
  WHERE status <> 'removed';

CREATE TABLE artwork_revisions (
  artwork_id TEXT NOT NULL REFERENCES artworks(id) ON DELETE CASCADE,
  revision INTEGER NOT NULL,
  content_hash TEXT NOT NULL,
  preview_hash TEXT NOT NULL,
  design_key TEXT NOT NULL,
  preview_key TEXT NOT NULL,
  design_bytes INTEGER NOT NULL,
  preview_bytes INTEGER NOT NULL,
  shape_count INTEGER NOT NULL,
  manifest_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'published', 'rejected', 'removed')),
  rejection_reason TEXT NOT NULL DEFAULT '',
  change_note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  PRIMARY KEY(artwork_id, revision),
  UNIQUE(content_hash)
);

CREATE TABLE favorites (
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  artwork_id TEXT NOT NULL REFERENCES artworks(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  PRIMARY KEY(user_id, artwork_id)
);

CREATE TABLE follows (
  follower_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  creator_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  PRIMARY KEY(follower_id, creator_id),
  CHECK(follower_id <> creator_id)
);

CREATE TABLE reports (
  id TEXT PRIMARY KEY,
  reporter_id TEXT NOT NULL REFERENCES users(id),
  artwork_id TEXT NOT NULL REFERENCES artworks(id),
  reason TEXT NOT NULL,
  details TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'dismissed')),
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  UNIQUE(reporter_id, artwork_id, status)
);
CREATE INDEX reports_status_idx ON reports(status, created_at);

CREATE TABLE moderation_events (
  id TEXT PRIMARY KEY,
  artwork_id TEXT REFERENCES artworks(id),
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE rate_limits (
  subject_hash TEXT NOT NULL,
  action TEXT NOT NULL,
  window_start INTEGER NOT NULL,
  event_count INTEGER NOT NULL,
  PRIMARY KEY(subject_hash, action, window_start)
);

CREATE VIRTUAL TABLE artwork_search USING fts5(
  artwork_id UNINDEXED,
  title,
  description,
  creator,
  tags
);

CREATE TABLE reserved_usernames (
  username_norm TEXT PRIMARY KEY
);
INSERT INTO reserved_usernames(username_norm) VALUES
  ('admin'), ('administrator'), ('api'), ('community'), ('help'),
  ('kfps'), ('kloudy'), ('moderator'), ('official'), ('staff'), ('support');
