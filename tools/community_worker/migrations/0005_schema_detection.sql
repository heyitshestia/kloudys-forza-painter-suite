ALTER TABLE artworks
  ADD COLUMN source_schema TEXT NOT NULL DEFAULT 'legacy-kfps';

ALTER TABLE artworks
  ADD COLUMN schema_known INTEGER NOT NULL DEFAULT 1 CHECK (schema_known IN (0, 1));
