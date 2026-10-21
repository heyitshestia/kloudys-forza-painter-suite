"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const groups = require("../editor-layer-groups.js");
const source = fs.readFileSync(path.join(__dirname, "../editor.js"), "utf8");
const body = source.slice(source.indexOf("function objectToShape("), source.indexOf("function snapshotShapes("));
const context = vm.createContext({
  KfpsEditorLayerGroups: groups,
  normalizeColor: value => value.slice(),
  hexToRgb: () => [10, 20, 30, 255],
  updateObjectScaleSigns: () => {},
  currentScaleSigns: () => [1, 1],
  fh6DataFromObject: () => [4, -8, 1.2, -0.8, 25, 0.15],
  round: value => value,
  objectEditorVisible: object => object.visible !== false,
});
vm.runInContext(body, context);
const object = {fill: "#0a141e", visible: false, kloudy: {
  type: 1048677, type_word: 101, editor_id: "layer-1", locked: true,
  group_path: [{id: "outer", name: "Outer"}, {id: "inner", name: "Inner"}],
  group_id: "inner", group_name: "Inner",
}};
const convert = options => JSON.parse(JSON.stringify(context.objectToShape(object, options)));
const legacy = convert({includeEditorMeta: false});
assert.equal(Object.keys(legacy).some(key => key.startsWith("editor_")), false);
const offline = convert({includeEditorMeta: false, includeGroups: true});
assert.deepEqual(offline.editor_group_path, object.kloudy.group_path);
assert.equal(offline.editor_group_id, "inner");
assert.equal(offline.editor_hidden, undefined);
assert.equal(offline.editor_id, undefined);
assert.deepEqual(offline.data, legacy.data);
assert.deepEqual(offline.color, legacy.color);
const project = convert({includeEditorMeta: true});
assert.equal(project.editor_hidden, true);
assert.equal(project.editor_locked, true);
assert.equal(project.editor_id, "layer-1");
assert.deepEqual(project.editor_group_path, offline.editor_group_path);
assert.match(source, /payload = \{ shapes: vinylObjects\(\)\.map\(object => objectToShape\(object, \{ includeEditorMeta: false, includeGroups: true \}\)\) \}/);
const exportBody = source.slice(source.indexOf("async function exportJson()"), source.indexOf("function liveryStudioThemeContext()"));
const button = {disabled: false};
let saved = null;
let downloaded = null;
let invalid = false;
let failSave = false;
let objects = [object, {...object, kloudy: {...object.kloudy, group_id: "other", group_name: "Other", group_path: null}}];
Object.assign(context, {
  exportSaveInProgress: false, documentGeneration: 1,
  currentProjectName: "Grouped finished artwork", loadedName: "Grouped finished artwork",
  vinylObjects: () => objects,
  refreshExportValidation: () => { button.disabled = false; return {errors: invalid ? ["invalid"] : []}; },
  KfpsI18n: {t: value => value, error: value => value},
  $: () => button,
  cleanProjectBaseName: value => value,
  flushPendingNudgeHistory: () => {},
  saveEditorJsonToAppFolder: async (name, payload) => {
    if (failSave) throw new Error("storage unavailable");
    saved = JSON.parse(JSON.stringify(payload));
    return {id: "saved", name};
  },
  setJsonBrowserSource: () => {}, refreshJsonBrowser: async () => {},
  selectJsonBrowserEntryById: () => {}, setStatus: () => {},
  showCornerNotice: () => {}, activateDockPanel: () => {},
  requestConfirmation: async () => true,
  filenameWithSuffix: name => name,
  downloadText: (name, text) => { downloaded = JSON.parse(text); },
});
vm.runInContext(exportBody, context);
(async () => {
  await context.exportJson();
  assert.deepEqual(saved.shapes.map(s => groups.shapePath(s).map(g => g.id)), [["outer", "inner"], ["other"]]);
  assert.equal(saved.shapes.some(s => s.editor_hidden !== undefined || s.editor_locked !== undefined), false);
  assert.equal(context.exportSaveInProgress, false);
  failSave = true;
  await context.exportJson();
  assert.deepEqual(downloaded, saved, "download recovery preserves the same groups");
  saved = null;
  invalid = true;
  await context.exportJson();
  assert.equal(saved, null);
  invalid = false;
  objects = [];
  await context.exportJson();
  assert.equal(saved, null);
  assert.equal(context.exportSaveInProgress, false);
  console.log("Offline groups: serializer, finished export handler, download recovery, validation and empty export passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
