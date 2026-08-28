UPDATE artworks
SET games_json = '["FH6"]',
    source_schema = 'fh6-typecode',
    schema_known = 1
WHERE id = '209cf5a3-84bf-4eec-a2b9-09ba3cd17c55'
  AND title = 'KFPS Logo';

UPDATE artwork_revisions
SET manifest_json = json_set(
  manifest_json,
  '$.games', json('["FH6"]'),
  '$.source_schema', 'fh6-typecode',
  '$.schema_label', 'FH6 type-code geometry',
  '$.schema_known', json('true')
)
WHERE artwork_id = '209cf5a3-84bf-4eec-a2b9-09ba3cd17c55'
  AND revision = 1;
