import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {gzipSync} from 'node:zlib';
import {ENUMS, NUMBERS, BOOLEANS, validStudioRecord} from '../public/studio-diagnostics.mjs';
import {APP_LOG_SCHEMA, LOG_SCHEMA, describePrivateLogs} from '../public/private-logs.mjs';
import {redact} from '../public/protocol.mjs';

const record = () => ({schema_version: 1, utc: '2026-10-19T12:00:00Z', session: 'a'.repeat(16),
  sequence: 1, event: 'render', frame_ms: 16.67, shape_count: 3000,
  canvas_width: 1760, canvas_height: 1040, ready: true, app_version: '3.1.105'});
const archive = () => ({schema: APP_LOG_SCHEMA, created_at: '2026-10-19T12:00:00Z', warnings: [],
  files: [{name: 'studio-performance-0000.log', modified_utc: '2026-10-19T12:00:00Z',
    source_bytes: 1024, omitted_lines: 0, text: JSON.stringify(record()) + '\n'}]});
const compressed = value => new Blob([gzipSync(JSON.stringify(value))]);

test('Studio collector and support service use identical privacy field contracts', () => {
  const root = fileURLToPath(new URL('../../../', import.meta.url));
  const python = `import json, sys
sys.path.insert(0, 'KFPS.UI/src')
from kfps_ui.support_studio import _contract
c=_contract()
assert c is not None, 'Materialize the installed Studio package before release qualification'
print(json.dumps(dict(enums={k:sorted(v) for k,v in c.ENUMS.items()}, numbers=c.NUMBERS, bools=sorted(c.BOOLEANS))))`;
  const output = execFileSync(process.platform === 'win32' ? 'py' : 'python3',
    [...(process.platform === 'win32' ? ['-3.12'] : []), '-c', python], {cwd: root, encoding: 'utf8'});
  const contract = JSON.parse(output);
  assert.deepEqual(Object.fromEntries(Object.entries(ENUMS).map(([k,v]) => [k, [...v].sort()])), contract.enums);
  assert.deepEqual(NUMBERS, contract.numbers);
  assert.deepEqual([...BOOLEANS].sort(), contract.bools);
});

test('Studio records reject unknown content, wrong types and invalid bounds', () => {
  assert(validStudioRecord(record()));
  for (const change of [{path: 'PRIVATE'}, {key: 'PRIVATE'}, {shapes: []}, {event: 'PRIVATE'},
    {host: 'PRIVATE'}, {app_version: 'PRIVATE'}, {schema_version: true}, {sequence: 0},
    {sequence: 2**53}, {session: '../PRIVATE'}, {utc: 'PRIVATE'}, {frame_ms: Infinity},
    {frame_ms: -1}, {shape_count: 1.5}, {canvas_width: 32769}, {ready: 1}, {ready: 'true'},
    {pixel_ratio: 8.1}, {http_status: 600}]) assert(!validStudioRecord({...record(), ...change}), JSON.stringify(change));
});

test('only three bounded Studio log files are accepted, under the application schema', async () => {
  const value = archive();
  value.files = [0,1,2].map(i => ({...value.files[0], name: `studio-performance-000${i}.log`}));
  const result = await describePrivateLogs(compressed(value), {redact});
  assert.equal(result.metadata.files, 3);
  for (const mutate of [v => {v.schema = LOG_SCHEMA;},
    v => {v.files[0].name = 'studio-performance-0003.log';},
    v => {v.files[0].name = '../studio.jsonl';},
    v => {v.files[0].text = JSON.stringify({...record(), key: 'PRIVATE'});},
    v => {v.files[0].text = '{"invalid":"PRIVATE"';},
    v => {v.files[0].source_bytes = 256 * 1024 + 1;},
    v => {v.files[0].text = v.files[0].text.repeat(2000);}]) {
    const bad = archive(); mutate(bad);
    await assert.rejects(describePrivateLogs(compressed(bad), {redact}));
  }
});
