"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../editor.js"), "utf8").replace(/\r\n/g, "\n");
const extract = name => {
  const start = source.indexOf(`function ${name}(`);
  assert.ok(start >= 0, name);
  return source.slice(start, source.indexOf("\n}\n", start) + 3);
};
let selections = 0, pans = 0, renders = 0;
const object = { getCenterPoint: () => ({ x: -125, y: 420 }) };
const context = { Number, canvas: { width: 900, height: 700,
  viewportTransform: [2, .1, -.2, 2, 800, 900], getActiveObject: () => object,
  setViewportTransform(value) { this.viewportTransform = value; pans++; }, requestRenderAll() { renders++; } },
  syncCanvasObjectCoords() {}, syncSelectedShapeOutlines() {}, updateVisualGridLayer() {}, updateHud() {},
  layerDragState: null, recentLayerPointerDowns: [],
  layerListRows: new Map([['shape', { kind: 'layer', objects: [object] }]]),
  layerRowFromEventTarget: target => target.row, isLayerControlTarget: target => !!target.control,
  selectLayerEntryByKey() { selections++; }, KfpsI18n: { t: text => text } };
vm.createContext(context);
vm.runInContext(extract('centerCanvasOnObject') + extract('handleLayerDoubleClick'), context);
const event = overrides => ({ button: 0, target: { row: { dataset: { layerListKey: 'shape' } } },
  preventDefault() {}, stopPropagation() {}, ...overrides });
context.handleLayerDoubleClick(event());
assert.equal(selections, 1); assert.equal(pans, 1); assert.equal(renders, 1);
assert.deepEqual(Array.from(context.canvas.viewportTransform).slice(0, 4), [2, .1, -.2, 2]);
assert.equal(2 * -125 - .2 * 420 + context.canvas.viewportTransform[4], 450);
assert.equal(.1 * -125 + 2 * 420 + context.canvas.viewportTransform[5], 350);
for (const overrides of [{ button: 1 }, { button: 2 }, { ctrlKey: true }, { metaKey: true },
  { shiftKey: true }, { altKey: true }, { target: { control: true } }, { target: {} }]) {
  context.handleLayerDoubleClick(event(overrides));
}
for (const entry of [undefined, { kind: 'group', objects: [object] },
  { kind: 'group', objects: [object, object] }, { kind: 'layer', objects: [] },
  { kind: 'layer', objects: [object, object] }]) {
  context.layerListRows.set('shape', entry);
  context.handleLayerDoubleClick(event());
}
context.layerListRows.set('shape', { kind: 'layer', objects: [object] });
context.layerDragState = { active: true };
context.handleLayerDoubleClick(event());
context.layerDragState = null;
for (const pointer of [{ key: 'shape', control: true }, { key: 'shape', dragged: true }]) {
  context.recentLayerPointerDowns = [pointer, { key: 'shape' }];
  context.handleLayerDoubleClick(event());
}
assert.equal(selections, 1, 'Ignored gestures must not change selection');
assert.equal(pans, 1, 'Ignored gestures must not move viewport');
context.recentLayerPointerDowns = [{ key: 'other', control: true }];
context.handleLayerDoubleClick(event());
assert.equal(selections, 2);
for (const value of [NaN, Infinity, -Infinity]) {
  context.centerCanvasOnObject({ getCenterPoint: () => ({ x: value, y: 1 }) });
  context.centerCanvasOnObject({ getCenterPoint: () => ({ x: 1, y: value }) });
}
context.centerCanvasOnObject(null);
assert.equal(pans, 2, 'Invalid geometry must not change the viewport');
console.log('Layer double-click: viewport-only centering, invalid geometry, group exclusion, modifiers, controls, stale rows and drag provenance passed');
