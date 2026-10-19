import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const scene = fs.readFileSync(new URL('../../tools/livery-studio/src/web/livery-scene.js', import.meta.url), 'utf8');
const qml = fs.readFileSync(new URL('../qml/pages/LiveryPage.qml', import.meta.url), 'utf8');

test('native viewer status stays small without discarding the full inspection diagnostics', () => {
  const declaration = scene.match(/function viewerStatusDiagnostics\(\) \{[\s\S]*?\n\}/);
  assert.ok(declaration, 'A compact status transport is required');
  const detailed = {
    ready: true, disposed: false, contextReleased: false, animationActive: false,
    quality: {scale: 2, source: 'mixed-original-and-vector'},
    bytes: {estimatedGpu: 130000000}, rendering: {frames: 7, triangles: 359898},
    components: {groups: Array.from({length: 10000}, (_, id) => ({id, options: ['stock', 'upgrade']}))},
    conversionCoverage: {meshes: Array.from({length: 10000}, (_, id) => ({id, uv3: true}))},
    fidelity: {manifest: {parts: 'x'.repeat(200000)}},
    wheels: {visible: true, count: 4, native: {complete: false}, measuredSizes: 'x'.repeat(100000)},
  };
  const original = JSON.stringify(detailed);
  assert.ok(original.length > 65536);
  const context = vm.createContext({viewerDiagnostics: () => detailed});
  const compact = vm.runInContext(declaration[0] + '; viewerStatusDiagnostics()', context);
  assert.ok(JSON.stringify({event: 'ready', diagnostics: compact}).length < 8192);
  assert.equal(compact.ready, true);
  assert.deepEqual(compact.quality, detailed.quality);
  assert.deepEqual(compact.bytes, detailed.bytes);
  assert.deepEqual(compact.rendering, detailed.rendering);
  assert.equal(compact.wheels.visible, true);
  assert.equal(JSON.stringify(detailed), original, 'On-demand detailed diagnostics must remain intact');
});

test('both lifecycle messages and the native polling path use compact status', () => {
  const event = scene.match(/function viewerEvent\([^]*?\n\}/)?.[0];
  assert.match(event, /diagnostics: viewerStatusDiagnostics\(\)/);
  assert.match(scene, /window\.__kfpsViewerStatusDiagnostics = viewerStatusDiagnostics/);
  assert.match(qml, /diagnostics:window\.__kfpsViewerStatusDiagnostics\?\.\(\)/);
  assert.match(scene, /window\.__kfpsViewerDiagnostics = viewerDiagnostics/);
});
