"use strict";
const assert = require("node:assert/strict");
const groups = require("../editor-layer-groups.js");
const { prepareAddition } = require("../editor-projects.js");
let serial = 0;
const allocateGroupId = () => `new-${++serial}`;
const shape = (group, id = "duplicate-id") => ({
  type: 1048677, type_word: 101, data: [12, -30, -0.5, 0.8, 47, 0.25, 1],
  color: [12, 34, 56, 89], mask: true, editor_hidden: true, editor_locked: true,
  shape_name: "Named layer", editor_id: id, editor_pixel_art_generated: true,
  ...(group ? { editor_group_id: group, editor_group_name: `Name ${group}` } : {}),
});
const project = { name: "Source", shapes: [shape("a"), shape("a"), shape("b"), shape(null)],
  editor_collapsed_groups: ["a"], editor_source_overlay: { data_url: "do-not-import" }, editor_guides: { gridSize: 23 } };
const before = JSON.stringify(project);
const options = { name: "Source", count: 2996, groups, allocateGroupId };
const added = prepareAddition(project, options);
assert.equal(added.shapes.length, 4);
assert.equal(JSON.stringify(project), before, "Source is not mutated");
assert.equal(added.editor_source_overlay, undefined);
assert.equal(added.editor_guides, undefined);
assert.equal(added.shapes[0].editor_id, undefined);
assert.equal(added.shapes[0].editor_pixel_art_generated, undefined);
assert.equal(groups.shapePath(added.shapes[0]).length, 2);
assert.equal(groups.shapePath(added.shapes[3]).length, 1);
assert.equal(added.shapes[0].editor_group_id, added.shapes[1].editor_group_id);
assert.notEqual(added.shapes[0].editor_group_id, added.shapes[2].editor_group_id);
assert.deepEqual(added.collapsed, [added.shapes[0].editor_group_id, added.outer.id]);
for (let i = 0; i < project.shapes.length; i++) {
  const copy = added.shapes[i], source = project.shapes[i];
  for (const key of ["data", "color", "type", "type_word", "mask", "editor_hidden", "editor_locked", "shape_name"]) assert.deepEqual(copy[key], source[key], key);
  assert.notEqual(copy.data, source.data);
  assert.notEqual(copy.color, source.color);
}
added.shapes[0].data[0] = 999;
assert.equal(JSON.stringify(project), before, "Destination edits cannot affect source");
const repeated = prepareAddition(project, options);
assert.notEqual(repeated.outer.id, added.outer.id);
assert.notEqual(repeated.shapes[0].editor_group_id, added.shapes[0].editor_group_id);
const nested = prepareAddition({ shapes: repeated.shapes, editor_collapsed_groups: repeated.collapsed }, { ...options, count: 0, name: "Combined" });
assert.equal(groups.shapePath(nested.shapes[0]).length, 3);
assert.deepEqual(groups.shapePath(nested.shapes[0]).map(g => g.name), ["Combined", "Source", "Name a"]);
assert.equal(nested.collapsed.length, 3);
assert.throws(() => prepareAddition(project, { ...options, count: 2997 }), error => error.code === "layer_limit");
assert.throws(() => prepareAddition({ shapes: [] }, options), /no shapes/);
assert.throws(() => prepareAddition({}, options), /shapes list/);
for (const invalid of [null, {}, { ...shape("a"), data: [0, 0, NaN, 1, 0] }, { ...shape("a"), color: [1, 2, 3] },
  { ...shape("a"), color: [256, 2, 3, 255] }, { ...shape("a"), type: Infinity }]) {
  assert.throws(() => prepareAddition({ shapes: [invalid] }, { ...options, count: 0 }), /invalid/);
}
assert.throws(() => groups.shapePath({ editor_group_path: [{ id: "a", name: "A" }, { id: "a", name: "A" }] }), /invalid/);
assert.throws(() => groups.shapePath({ editor_group_id: "b", editor_group_path: [{ id: "a", name: "A" }] }), /conflicting/);
assert.throws(() => groups.shapePath({ editor_group_id: "x".repeat(257) }), /invalid/);
assert.throws(() => groups.cloneShapes([{ editor_group_id: "a", editor_group_name: "A" },
  { editor_group_id: "a", editor_group_name: "B" }]), /conflicting/);
assert.throws(() => groups.cloneShapes([
  { editor_group_path: [{ id: "a", name: "A" }, { id: "b", name: "B" }] },
  { editor_group_path: [{ id: "b", name: "B" }] },
]), /conflicting/);
const deep = { ...shape(null), editor_group_path: Array.from({ length: groups.MAX_DEPTH }, (_, i) => ({ id: `d${i}`, name: `D${i}` })) };
assert.throws(() => prepareAddition({ shapes: [deep] }, { ...options, count: 0 }), /nested/);
const copies = groups.cloneShapes(nested.shapes, { allocateGroupId });
assert.deepEqual(groups.shapePath(copies.shapes[0]).map(g => g.name), ["Combined", "Source", "Name a"]);
assert.ok(groups.shapePath(copies.shapes[0]).every((g, i) => g.id !== groups.shapePath(nested.shapes[0])[i].id));

(async () => {
  const objects = nested.shapes.map(s => ({ kloudy: {}, visible: true }));
  objects.forEach((o, i) => groups.applyPath(o, groups.shapePath(nested.shapes[i])));
  let target = nested.outer.id, answer = "Renamed", commits = 0;
  const module = groups.create({
    scene: { all: () => objects, selected: () => objects, groupIds: () => [target],
      members: ids => objects.filter(o => groups.objectPath(o).some(g => ids.includes(g.id))),
      selectedMembers: () => objects, groupName: (o, id) => groups.objectPath(o).find(g => g.id === id).name,
      attached: o => objects.includes(o), expand: () => {}, focus: id => { target = id; }, lock: (o, v) => { o.kloudy.locked = v; } },
    edits: { generation: () => 1, commit: () => commits++ },
    view: { status: () => {}, render: () => {}, refresh: () => {}, selection: () => {}, failed: e => { throw e; } },
    tr: (key, ...args) => key.replace(/\{(\d+)\}/g, (_, n) => args[n]), requestName: async () => answer,
  });
  await module.renameGroup();
  assert.equal(groups.objectPath(objects[0])[0].name, "Renamed");
  assert.equal(objects[0].kloudy.group_name, "Name a", "Parent rename preserves child name");
  module.ungroup();
  assert.equal(groups.objectPath(objects[0]).length, 2, "Ungroup only removes the selected parent");
  assert.equal(groups.objectPath(objects[3]).length, 1);
  module.group();
  assert.equal(groups.objectPath(objects[0]).length, 3, "Grouping preserves child hierarchy");
  assert.equal(groups.objectPath(objects[0])[0].id, target);
  assert.equal(commits, 3);
  objects.forEach(object => groups.applyPath(object, deep.editor_group_path));
  const deepest = JSON.stringify(objects);
  assert.equal(module.group(), false, "Nesting limit should be explained, not throw from a button handler");
  assert.equal(JSON.stringify(objects), deepest);
  assert.equal(commits, 3);
  console.log("project-add: capacity, independent copies, modifiers, hierarchy, cycles, rename/ungroup and repeated insertion passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
