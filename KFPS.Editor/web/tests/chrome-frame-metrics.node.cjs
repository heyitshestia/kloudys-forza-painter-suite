const assert = require('node:assert/strict');
const { summarize, inspectPixels } = require('./chrome-frame-metrics.cjs');

assert.throws(() => summarize([]));
assert.throws(() => summarize([NaN]));
assert.throws(() => summarize([-1]));
assert.deepEqual(summarize([51, 12, 16, 12, 13, 16, 13, 12, 13, 12, 13, 12]), {
  samples: 12, minMs: 12, medianMs: 13, p95Ms: 51, maxMs: 51, smallSampleWarning: true,
});
assert.equal(summarize(Array.from({ length: 100 }, (_, i) => i)).p95Ms, 94);
assert.throws(() => inspectPixels(new Uint8Array(0)));
assert.throws(() => inspectPixels(new Uint8Array(3)));
assert.equal(inspectPixels(new Uint8Array(1600)).nonblank, false);
assert.equal(inspectPixels(new Uint8Array(1600).fill(255)).nonblank, false);
const scene = new Uint8Array(1600);
for (let i = 0; i < scene.length; i += 4) {
  scene[i] = (i / 4) % 255;
  scene[i + 3] = 255;
}
assert.equal(inspectPixels(scene).nonblank, true);
assert.equal(inspectPixels(scene).opaque, 400);
// One stray pixel must not turn a blank renderer into a passing scene.
scene.fill(255);
scene[0] = 0;
assert.equal(inspectPixels(scene).nonblank, false);
console.log('Chrome frame metric units: 12 assertions passed (no browser launched)');
