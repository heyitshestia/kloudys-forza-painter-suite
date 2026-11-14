'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {create} = require('../editor-catalog.js');
const options = payload => ({ VINYL_TYPE_BASES: {}, VINYL_RESOURCE_BASES: ['/mesh'],
  format: x => String(x), KfpsI18n: {t: x => x}, fetcher: async () => ({ok: true, json: async () => payload}) });
const resolved = {family: 'Racing_Icons', index: 1};
test('opposite overlapping triangles get consistent display winding without mutating resource/alpha', async () => {
  const payload = {Vertices: [{X:0,Y:0}, {X:1,Y:0}, {X:0,Y:1}, {X:-10,Y:-10}, {X:10,Y:10}],
    Indices: [0,1,2,0,2,1,3,4,3], VerticesAlpha: [255,255,255,0,0]};
  const before = JSON.stringify(payload), catalog = create(options(payload));
  assert.equal(await catalog.loadResourcePathForResolved(resolved), 'M -10 -10 M 10 10 M 0 0 L 1 0 L 0 1 Z M 0 0 L 1 0 L 0 1 Z');
  assert.equal(JSON.stringify(payload), before);
  catalog.dispose();
});
test('all 40 bundled Racing Icon paths retain all triangles with nonnegative winding', async () => {
  for (let slot = 1; slot <= 40; slot++) {
    const payload = JSON.parse(fs.readFileSync(path.join(__dirname, '../Resources/Vinyls/Racing_Icons', String(slot)), 'utf8'));
    const before = JSON.stringify(payload), catalog = create(options(payload));
    const d = await catalog.loadResourcePathForResolved({...resolved, index: slot});
    const triangles = [...d.matchAll(/M ([^ ]+) ([^ ]+) L ([^ ]+) ([^ ]+) L ([^ ]+) ([^ ]+) Z/g)];
    assert.equal(triangles.length, payload.Indices.length / 3);
    for (const match of triangles) {
      const [ax, ay, bx, by, cx, cy] = match.slice(1).map(Number);
      assert.ok((bx - ax) * (cy - ay) - (by - ay) * (cx - ax) >= 0, `slot ${slot}`);
    }
    assert.equal(JSON.stringify(payload), before); catalog.dispose();
  }
});
