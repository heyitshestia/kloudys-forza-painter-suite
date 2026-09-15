'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { create } = require('../editor-catalog.js');
const bases = { Primitives: 1048677, Community_Vinyls_1: 1050677, Upper_Letters_1: 1050477 };
const mesh = { Vertices: [{ X: 0, Y: 0 }, { X: 1, Y: 0 }, { X: 0, Y: 1 }], Indices: [0, 1, 2] };
const resolved = { family: 'Primitives', index: 1, typeCode: 1048677 };
const response = value => ({ ok: true, json: async () => value });
const options = fetcher => ({ VINYL_TYPE_BASES: bases, VINYL_RESOURCE_BASES: ['/primary', '/fallback'],
  format: value => String(Math.round(Number(value) * 1000000) / 1000000),
  KfpsI18n: { t: (key, value) => key.replace('{0}', value) }, fetcher, requestTimeoutMs: 30 });

test('one payload request serves concurrent paths/outlines/payloads, and caches survive reuse', async () => {
  let count = 0;
  const catalog = create(options(async () => { count++; return response(mesh); }));
  const [path, outline, payload, ...same] = await Promise.all([
    catalog.loadResourcePathForResolved(resolved), catalog.loadResourceOutlinePathForResolved(resolved),
    catalog.loadResourcePayloadForResolved(resolved),
    ...Array.from({ length: 12 }, () => catalog.loadResourcePayloadForResolved(resolved)),
  ]);
  assert.equal(path, 'M 0 0 L 1 0 L 0 1 Z');
  assert.equal(outline, 'M 0 0 L 1 0 M 1 0 L 0 1 M 0 1 L 0 0');
  assert.equal(count, 1);
  same.forEach(value => assert.equal(value, payload));
  assert.equal(await catalog.loadResourcePathForResolved(resolved), path);
  assert.equal(count, 1);
  assert.equal(catalog.payloads.get(catalog.resourceCacheKey(resolved)), payload);
  assert.equal(catalog.payloads.set, undefined);
  catalog.dispose();
});

test('fallback base is remembered, failed requests retry, malformed JSON is not silently hidden', async () => {
  const seen = [];
  let fail = true;
  const catalog = create(options(async url => {
    seen.push(url);
    return fail || url.startsWith('/primary') ? { ok: false } : response(mesh);
  }));
  await assert.rejects(catalog.loadResourcePayloadForResolved(resolved), /Missing shape/);
  fail = false;
  await catalog.loadResourcePayloadForResolved(resolved);
  assert.equal(catalog.vinylResourceUrl('Primitives', 2), '/fallback/Primitives/2');
  await catalog.loadResourcePayloadForResolved({ ...resolved, index: 2 });
  assert.deepEqual(seen, ['/primary/Primitives/1', '/fallback/Primitives/1', '/primary/Primitives/1', '/fallback/Primitives/1', '/fallback/Primitives/2']);
  catalog.dispose();
  const broken = create(options(async () => ({ ok: true, json: async () => { throw new SyntaxError('bad JSON'); } })));
  await assert.rejects(broken.loadResourcePayloadForResolved(resolved), SyntaxError);
  broken.dispose();
});

test('metadata installs together; names/words failure preserves both and retry works', async () => {
  let version = 1, calls = 0, broken = false;
  const catalog = create(options(async url => {
    calls++;
    if (broken && url.endsWith('shape-words.json')) return { ok: false, status: 503 };
    return response({ families: { Primitives: { 1: url.endsWith('shape-names.json') ? `Name ${version}` : 101 } } });
  }));
  await Promise.all([catalog.loadMetadata(), catalog.loadMetadata()]);
  assert.equal(calls, 2);
  const names = catalog.names, words = catalog.words;
  version = 2; broken = true;
  await assert.rejects(catalog.loadMetadata(), /shape-words HTTP 503/);
  assert.equal(catalog.names, names); assert.equal(catalog.words, words);
  broken = false; await catalog.loadMetadata();
  assert.equal(catalog.shapeDisplayName('Primitives', 1), 'Name 2');
  catalog.dispose();
});

test('full and compact ranges precede display metadata; explicit words only fill unknown identities', async () => {
  const catalog = create(options(async () => response({ families: { Conflict: { 7: 101, 8: 65500 } } })));
  await catalog.loadMetadata();
  for (const [family, base] of Object.entries(bases)) for (let index = 1; index <= 40; index++) {
    const type = base + index - 1;
    assert.equal(catalog.resourceToTypeCode(family, index), type);
    for (const value of [type, type & 65535]) {
      const identity = catalog.typeCodeToResource(value);
      assert.equal(identity.family, family); assert.equal(identity.index, index);
    }
  }
  assert.equal(catalog.typeCodeToResource(65500).family, 'Conflict');
  assert.equal(catalog.typeCodeToResource(999), null);
  assert.throws(() => catalog.resourceToShapeWord('Missing', 1), /Unknown shape family/);
  catalog.dispose();
});

test('deadline covers a hung JSON body; terminal disposal cancels all I/O and ignores late results', async () => {
  let finish;
  const signals = [];
  const catalog = create({ ...options(async (_url, { signal }) => {
    signals.push(signal);
    return { ok: true, json: () => new Promise(resolve => { finish = resolve; }) };
  }), VINYL_RESOURCE_BASES: ['/primary'] });
  await assert.rejects(catalog.loadResourcePayloadForResolved(resolved), /Missing shape/);
  assert.equal(signals[0].aborted, true);
  finish(mesh);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(catalog.payloads.has(catalog.resourceCacheKey(resolved)), false);
  const pending = catalog.loadResourcePayloadForResolved(resolved);
  await new Promise(resolve => setImmediate(resolve));
  catalog.dispose(); catalog.dispose();
  await assert.rejects(pending, { name: 'AbortError' });
  assert.equal(signals.at(-1).aborted, true);
  finish(mesh);
  await assert.rejects(catalog.loadMetadata(), { name: 'AbortError' });
  await assert.rejects(catalog.loadResourcePathForResolved(resolved), { name: 'AbortError' });
  assert.equal(signals.length, 2);
});

test('one failed metadata response cancels its peer without cancelling unrelated shape loading', async () => {
  let peerSignal;
  const catalog = create(options(async (url, { signal }) => {
    if (url.endsWith('shape-names.json')) { peerSignal = signal; return new Promise(() => {}); }
    if (url.endsWith('shape-words.json')) return { ok: false, status: 500 };
    return response(mesh);
  }));
  const shape = catalog.loadResourcePayloadForResolved(resolved);
  await assert.rejects(catalog.loadMetadata(), /HTTP 500/);
  assert.equal(peerSignal.aborted, true);
  assert.equal(await shape, mesh);
  catalog.dispose();
});

test('transparent fill triangles are omitted while original bounds remain in the path', async () => {
  const payload = {
    Vertices: [...mesh.Vertices, { X: -4, Y: -5 }, { X: 4, Y: -5 }, { X: 0, Y: 6 }],
    Indices: [0, 1, 2, 3, 4, 5], VerticesAlpha: Buffer.from([255, 255, 255, 0, 0, 0]).toString('base64'),
  };
  const catalog = create(options(async () => response(payload)));
  const path = await catalog.loadResourcePathForResolved(resolved);
  assert.equal(path, 'M -4 -5 M 4 6 M 0 0 L 1 0 L 0 1 Z');
  const outline = await catalog.loadResourceOutlinePathForResolved(resolved);
  assert.equal(outline, 'M 0 0 L 1 0 M 1 0 L 0 1 M 0 1 L 0 0');
  catalog.dispose();
});

test('all 880 font meshes omit exactly their zero-alpha triangles without losing visible triangles', async () => {
  const fs = require('node:fs'), path = require('node:path');
  let count = 0;
  const catalog = create(options(async url => response(JSON.parse(fs.readFileSync(
    path.join(__dirname, '../Resources/Vinyls', url.replace(/^\/primary\//, '')), 'utf8')))));
  for (let font = 1; font <= 11; font++) for (const block of ['Upper', 'Lower']) for (let index = 1; index <= 40; index++) {
    const resource = { family: `${block}_Letters_${font}`, index };
    const payload = await catalog.loadResourcePayloadForResolved(resource);
    const alpha = Buffer.from(payload.VerticesAlpha, 'base64');
    let visible = 0, hidden = 0;
    for (let i = 0; i < payload.Indices.length; i += 3) {
      if (payload.Indices.slice(i, i + 3).some(k => alpha[k] !== 0)) visible++;
      else hidden++;
    }
    assert.equal(hidden, 4, JSON.stringify(resource));
    const d = await catalog.loadResourcePathForResolved(resource);
    assert.equal((d.match(/ Z/g) || []).length, visible, JSON.stringify(resource));
    assert.equal((d.match(/M /g) || []).length, visible + 2, JSON.stringify(resource));
    count++;
  }
  assert.equal(count, 880);
  catalog.dispose();
});
