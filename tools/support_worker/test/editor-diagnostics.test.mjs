import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gzipSync} from 'node:zlib';
import {ASSETS, ENUMS, normalizeEditor} from '../public/editor-diagnostics.mjs';
import {APP_LOG_SCHEMA, describePrivateLogs} from '../public/private-logs.mjs';

test('support diagnostics retain every manifest-approved editor asset and no other paths', () => {
  const manifest = JSON.parse(readFileSync(new URL('../../../KFPS.Editor/manifest.json', import.meta.url), 'utf8'));
  const expected = manifest.web.filter(entry => entry.diagnostic === true).map(entry => entry.path);
  assert.deepEqual([...ASSETS].sort(), [...expected].sort());
  assert.deepEqual([...ENUMS.source].sort(), [...expected, 'native', 'unknown'].sort());
  const hash = 'a'.repeat(64);
  const installed_assets = Object.fromEntries(expected.map(name => [name, hash]));
  installed_assets['runtime/activity-private/state.json'] = hash;
  const clean = normalizeEditor({schema: 'kfps-editor-diagnostics/1', installed_assets});
  assert.deepEqual(clean.installed_assets, Object.fromEntries(expected.map(name => [name, hash])));
});

test('private-preview resource errors survive private-log attachment validation', async () => {
  const utc = '2026-11-14T12:00:00Z';
  const event = {schema: 'kfps-editor-diagnostics/1', session: 'a'.repeat(32), utc, serial: 1,
    kind: 'resource-error', source: 'editor-private-previews.js', error: 'unknown', line: 0};
  const text = JSON.stringify(event) + '\n';
  const bundle = {schema: APP_LOG_SCHEMA, created_at: utc, files: [{name: 'performance.jsonl',
    modified_utc: utc, source_bytes: Buffer.byteLength(text), omitted_lines: 0, text}], warnings: []};
  const attachment = new Blob([gzipSync(JSON.stringify(bundle))], {type: 'application/gzip'});

  const accepted = await describePrivateLogs(attachment);
  assert.equal(accepted.metadata.schema, APP_LOG_SCHEMA);
  assert.equal(accepted.metadata.files, 1);
  assert.deepEqual(accepted.bundle, bundle);
  assert.deepEqual(JSON.parse(accepted.bundle.files[0].text), event);
});
