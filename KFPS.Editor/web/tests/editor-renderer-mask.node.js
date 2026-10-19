const test = require('node:test');
const assert = require('node:assert/strict');
const { drawNativeMaskOutline } = require('../editor-renderer.js');

function fixture(overrides = {}) {
  const calls = [], paths = [];
  global.Path2D = class {
    constructor(data) { this.data = data; paths.push(this); }
    addPath(path, matrix) { this.added = { path, matrix }; }
  };
  const object = { type: 'path', kloudyMaskOutline: true, objectCaching: false,
    strokeUniform: true, fill: 'rgba(255,36,79,.001)', stroke: '#ff244f', strokeWidth: 4,
    globalCompositeOperation: 'source-over', scaleX: .4, scaleY: .32,
    pathOffset: { x: .123456789, y: -2.345678901 },
    path: [['M', 1.123456789, 3.987654321], ['L', 8, 9], ['L', -7, 6], ['Z']],
    _setFillStyles: () => calls.push('fillStyle'), _setStrokeStyles: () => calls.push('strokeStyle'),
    _setLineDash: () => calls.push('dash'), ...overrides };
  const context = { save: () => calls.push('save'), restore: () => calls.push('restore'),
    scale: (...args) => calls.push(['scale', ...args]), fill: (...args) => calls.push(['fill', ...args]),
    stroke: (...args) => calls.push(['stroke', ...args]) };
  return { object, context, calls, paths };
}

test('mask UI retains every coordinate and closure without decimal truncation', () => {
  const f = fixture();
  assert.equal(drawNativeMaskOutline(f.object, f.context), true);
  assert.equal(f.paths[0].data, f.object.path.map(p => p[0] === 'Z' ? 'Z' :
    `${p[0]} ${p[1] - f.object.pathOffset.x} ${p[2] - f.object.pathOffset.y}`).join(' '));
  assert.deepEqual(f.paths[1].added.matrix, { a: .4, b: 0, c: 0, d: .32, e: 0, f: 0 });
  assert.deepEqual(f.calls.map(c => Array.isArray(c) ? c[0] : c),
    ['save', 'fillStyle', 'fill', 'restore', 'save', 'scale', 'dash', 'strokeStyle', 'stroke', 'restore']);
});

test('mask paths are reused and invalidated by scale, offset or source replacement', () => {
  const f = fixture();
  drawNativeMaskOutline(f.object, f.context); drawNativeMaskOutline(f.object, f.context);
  assert.equal(f.paths.length, 2);
  f.object.scaleX = .7; drawNativeMaskOutline(f.object, f.context);
  assert.equal(f.paths.length, 3);
  f.object.pathOffset = { x: 2, y: 3 }; drawNativeMaskOutline(f.object, f.context);
  assert.equal(f.paths.length, 5);
  f.object.path = f.object.path.map(p => p.slice()); drawNativeMaskOutline(f.object, f.context);
  assert.equal(f.paths.length, 7);
});

test('transparent-triangle bounds anchors keep the exact fast mask outline', () => {
  const f = fixture();
  f.object.path = [['M', -90, -80], ['M', 90, 80], ...f.object.path];
  assert.equal(drawNativeMaskOutline(f.object, f.context), true);
  assert.equal(f.paths[0].data, f.object.path.map(p => p[0] === 'Z' ? 'Z' :
    `${p[0]} ${p[1] - f.object.pathOffset.x} ${p[2] - f.object.pathOffset.y}`).join(' '));
  drawNativeMaskOutline(f.object, f.context);
  assert.equal(f.paths.length, 2);
});

test('ordinary artwork and unsupported mask paint states always use Fabric', () => {
  for (const change of [{ kloudyMaskOutline: false }, { objectCaching: true }, { group: {} },
    { shadow: {} }, { clipPath: {} }, { backgroundColor: 'red' }, { paintFirst: 'stroke' },
    { strokeUniform: false }, { fill: {} }, { stroke: {} }, { globalCompositeOperation: 'destination-out' },
    { scaleX: 0 }, { scaleY: NaN }, { pathOffset: null }, { path: [['C', 1, 2]] },
    { path: [['M', -90, -80], ['M', 90, 80]] },
    { path: [null, ['L', 1, 2], ['L', 3, 4], ['Z']] },
    { path: [['M', NaN, 0], ['M', 90, 80], ['M', 0, 0], ['L', 1, 2], ['L', 3, 4], ['Z']] }]) {
    const f = fixture(change);
    assert.equal(drawNativeMaskOutline(f.object, f.context), false);
    assert.deepEqual(f.calls, []);
  }
  const f = fixture(); delete global.Path2D;
  assert.equal(drawNativeMaskOutline(f.object, f.context), false);
});

test('partial Path2D implementations fall back before drawing', () => {
  const f = fixture();
  delete global.Path2D.prototype.addPath;
  assert.equal(drawNativeMaskOutline(f.object, f.context), false);
  assert.deepEqual(f.calls, []);
  assert.equal(f.paths.length, 0);
});

test('mask draw exceptions restore the paint state', () => {
  for (const operation of ['fill', 'stroke']) {
    const f = fixture(); f.context[operation] = () => { throw Error('injected'); };
    assert.throws(() => drawNativeMaskOutline(f.object, f.context), /injected/);
    assert.equal(f.calls.at(-1), 'restore');
  }
});
