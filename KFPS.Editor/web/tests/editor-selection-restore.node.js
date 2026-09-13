"use strict";
const assert = require("node:assert/strict"), fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
let delegated = 0;
class ActiveSelection {
  _restoreObjectsState() { delegated++; return "original"; }
}
const window = { fabric: { version: "5.3.0", ActiveSelection } };
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../editor-fabric-adapter.js"), "utf8"), { window });
const install = window.KfpsFabricAdapter.installSelectionTranslationRestore;
const canvas = {}, other = {};
assert.equal(install(canvas), true);
assert.equal(install(canvas), true);
const selection = new ActiveSelection();
const object = { left: -15, top: 28, flipX: true, flipY: false, angle: -173.914627, scaleX: 2.225329,
  set(values) { Object.assign(this, values); }, setCoords() { this.coordinatesUpdated = true; } };
object.group = selection;
selection.canvas = canvas; selection._objects = [object];
selection.calcOwnMatrix = () => [1, 0, 0, 1, 12, -19];
assert.equal(selection._restoreObjectsState(), selection);
assert.equal(object.left, -3); assert.equal(object.top, 9);
assert.equal(object.group, undefined); assert.equal(object.coordinatesUpdated, true);
assert.equal(object.flipX, true); assert.equal(object.flipY, false);
assert.equal(object.angle, -173.914627); assert.equal(object.scaleX, 2.225329);
assert.equal(delegated, 0);
for (const matrix of [[2, 0, 0, 1, 0, 0], [1, .00000000000001, 0, 1, 0, 0],
  [1, 0, .1, 1, 0, 0], [-1, 0, 0, 1, 0, 0], [1, 0, 0, 1, Infinity, 0]]) {
  selection.calcOwnMatrix = () => matrix;
  assert.equal(selection._restoreObjectsState(), "original");
}
selection.calcOwnMatrix = () => [1, 0, 0, 1, 0, 0]; selection.canvas = other;
assert.equal(selection._restoreObjectsState(), "original");
assert.equal(delegated, 6);
assert.equal(install(other), true);
assert.equal(selection._restoreObjectsState(), selection);
assert.equal(delegated, 6);
console.log("Selection restoration: exact translation, mirror representation, transformed delegation, invalid matrix, canvas isolation and repeat installation passed");
