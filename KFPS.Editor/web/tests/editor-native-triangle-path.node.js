const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../editor.js'), 'utf8');
const functionSource = source.slice(source.indexOf('function isNativeTrianglePath('),
  source.indexOf('\nfunction renderNativeTriangleFill('));
const recognize = vm.runInNewContext(`${functionSource}; isNativeTrianglePath`);
const triangle = [['M', 1, 2], ['L', 3, 4], ['L', 5, 6], ['Z']];
const bounds = [['M', -90, -80], ['M', 90, 80]];

assert.equal(recognize(triangle), true);
assert.equal(recognize([...triangle, ...triangle]), true);
assert.equal(recognize([...bounds, ...triangle]), true, 'Native transparent-triangle bounds anchors must retain the fast fill');
assert.equal(recognize([...bounds, ...triangle, ...triangle]), true);
for (const invalid of [null, [], bounds, [['M', 0, 0], ...triangle],
  [...triangle, ...bounds], [...bounds, ['M', 1, 2], ['L', 3, 4], ['Q', 5, 6], ['Z']],
  [['M', NaN, 0], bounds[1], ...triangle], [['M', 0, Infinity], bounds[1], ...triangle],
  [null, ...triangle.slice(1)], [['m', 1, 2], ...triangle.slice(1)],
  [...bounds, ...triangle, ['M', 0, 0]]]) {
  assert.equal(recognize(invalid), false);
}
const frozen = Object.freeze([...bounds, ...triangle].map(segment => Object.freeze(segment)));
const before = JSON.stringify(frozen);
assert.equal(recognize(frozen), true);
assert.equal(JSON.stringify(frozen), before, 'Recognition must not alter geometry');
let fallback = null;
const fillSource = source.slice(source.indexOf('function renderNativeTriangleFill('),
  source.indexOf('\nfunction renderNativeMaskOutline('));
const fill = vm.runInNewContext(`${fillSource}; renderNativeTriangleFill`, {
  fabric: { Path: { prototype: { _renderPathCommands(context) { fallback = { owner: this, context }; } } } },
});
const stroked = { hasStroke: () => true };
const context = {};
fill.call(stroked, context);
assert.equal(fallback.owner, stroked);
assert.equal(fallback.context, context, 'Stroked triangles must keep Fabric closure semantics');
console.log('Native triangle path recognition: passed');
