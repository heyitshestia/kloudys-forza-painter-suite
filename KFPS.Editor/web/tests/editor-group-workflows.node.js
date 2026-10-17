"use strict";
const assert = require("node:assert/strict");
const api = require("../editor-layer-groups.js");
const g = id => ({ id, name: id });
const obj = (...ids) => { const o = { kloudy: {} }; api.applyPath(o, ids.map(g)); return o; };
let all, selected, commits;
function fixture(objects) {
  all = objects; selected = []; commits = 0;
  return api.create({
    scene: { all: () => all, selected: () => selected, attached: o => all.includes(o), expand() {}, focus() {} },
    edits: { commit() { commits++; } }, view: { refresh() {}, selection() {}, status() {}, failed(e) { throw e; } },
    tr: s => s,
  });
}
let a = obj("outer", "inner"), b = obj("outer", "inner"), c = obj("outer"), d = obj();
let groups = fixture([a,b,c,d]);
assert.deepEqual(api.selectionPaths([a], all), [[]], "Partial group must not accompany copied shape");
assert.deepEqual(api.selectionPaths([a,b], all), [[g("inner")],[g("inner")]], "Complete child keeps hierarchy without partial parent");
assert.deepEqual(api.selectionPaths([c], [c], { individual: true }), [[]]);
selected = [a,b,c,d];
assert.equal(groups.group(), true);
assert.deepEqual(api.objectPath(d), [g("outer")], "Group extends one full existing group");
assert.deepEqual(api.objectPath(a), [g("outer"),g("inner")]);
assert.equal(commits, 1);
assert.equal(groups.addToGroup([a,b,c,d], "inner"), false, "Cannot put ancestor in descendant");
assert.equal(commits, 1);
assert.equal(groups.addToGroup([d], "inner"), true);
assert.deepEqual(api.objectPath(d), [g("outer"),g("inner")]);
assert.equal(groups.addToGroup([d], "inner"), false, "No-op must not commit");
assert.equal(groups.addToGroup([obj()], "inner"), false, "Detached source rejected");
assert.equal(groups.addToGroup([a], "missing"), false);
selected = [a,b,c,d];
assert.equal(groups.group({ forceNew: true }), true);
assert.equal(api.objectPath(a).length, 3, "Explicit New Group nests");
assert.equal(new Set(all.map(o => api.objectPath(o)[0].id)).size, 1);
a = obj("source"); b = obj("source"); c = obj("target");
groups = fixture([a,b,c]);
assert.equal(groups.addToGroup([a], "target"), true);
assert.deepEqual(api.objectPath(a), [g("target")], "Partial group member moves individually");
assert.deepEqual(api.objectPath(b), [g("source")]);
a = obj("source"); b = obj("source"); groups = fixture([a,b,c]);
assert.equal(groups.addToGroup([a,b], "target"), true);
assert.deepEqual(api.objectPath(a), [g("target"),g("source")], "Full group moves intact");
const deep = obj(...Array.from({length:64},(_,i)=>`deep-${i}`)), loose = obj("extra");
groups = fixture([deep, loose]);
assert.equal(groups.addToGroup([loose], "deep-63"), false);
assert.equal(commits, 0);
assert.deepEqual(api.objectPath(loose), [g("extra")]);
let combinations = 0;
for (let mask = 1; mask < 256; mask++) {
  for (const target of ["outer", "inner", "target", "child", "other"]) {
    const objects = [obj("outer", "inner"), obj("outer", "inner"), obj("outer"),
      obj("target", "child"), obj("target", "child"), obj("target"), obj("other"), obj()];
    objects.forEach((object, index) => Object.assign(object, { left: index * 20, visible: index !== 1,
      color: [index * 10, 100, 200, 255], locked: index === 2 }));
    const before = objects.map(object => JSON.stringify(object));
    const native = JSON.stringify(objects.map(({ kloudy, ...rest }) => rest));
    const owner = fixture(objects);
    selected = objects.filter((_, index) => mask & (1 << index));
    const changed = owner.addToGroup(selected, target);
    assert.equal(commits, changed ? 1 : 0);
    assert.equal(JSON.stringify(objects.map(({ kloudy, ...rest }) => rest)), native);
    objects.forEach((object, index) => {
      if (!changed || !selected.includes(object)) assert.equal(JSON.stringify(object), before[index]);
    });
    // The production serializer rejects duplicate IDs, cycles and conflicting parents.
    api.cloneShapes(objects.map(object => api.fields(api.objectPath(object))));
    combinations++;
  }
}
console.log(`Group workflows: partial/full copying, extension, nesting, stale membership, depth and ${combinations} membership combinations passed`);
