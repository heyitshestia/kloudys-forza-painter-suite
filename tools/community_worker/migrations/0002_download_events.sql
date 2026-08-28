CREATE TABLE download_events (
  artwork_id TEXT NOT NULL REFERENCES artworks(id) ON DELETE CASCADE,
  subject_hash TEXT NOT NULL,
  day_bucket INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY(artwork_id, subject_hash, day_bucket)
);

CREATE INDEX download_events_day_idx ON download_events(day_bucket);
