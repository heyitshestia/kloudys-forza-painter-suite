import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {ASSETS, ENUMS, normalizeEditor} from '../public/editor-diagnostics.mjs';

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
