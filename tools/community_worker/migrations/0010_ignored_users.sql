CREATE TABLE ignored_users (
  viewer_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  ignored_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  PRIMARY KEY(viewer_id, ignored_id),
  CHECK(viewer_id <> ignored_id)
);

CREATE INDEX ignored_users_viewer_created_idx
  ON ignored_users(viewer_id, created_at DESC);
