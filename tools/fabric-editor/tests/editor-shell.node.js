"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const editorRoot = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(editorRoot, "index.html"), "utf8");
const script = fs.readFileSync(path.join(editorRoot, "editor.js"), "utf8");
const fabricAdapter = fs.readFileSync(path.join(editorRoot, "editor-fabric-adapter.js"), "utf8");
const styles = fs.readFileSync(path.join(editorRoot, "style.css"), "utf8");

const idMatches = [...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]);
const idCounts = new Map();
idMatches.forEach((id) => idCounts.set(id, (idCounts.get(id) || 0) + 1));
const duplicates = [...idCounts].filter(([, count]) => count > 1);
assert.deepEqual(duplicates, [], "HTML ids must be unique");

const unexplainedButtons = [...html.matchAll(/<button\b([^>]*)>/g)]
  .map((match) => match[1])
  .filter((attributes) => (
    !/\btitle="[^"]+"/.test(attributes)
    && !/\baria-label="[^"]+"/.test(attributes)
  ));
assert.deepEqual(
  unexplainedButtons,
  [],
  "every editor button must explain itself on hover or through an aria label",
);

[
  "projectDirtyChip",
  "newCanvas",
  "openJsonBrowser",
  "loadProject",
  "saveProject",
  "saveProjectAs",
  "shapePlacementMode",
  "toggleRightDock",
  "layersPane",
  "dockSplitter",
  "propertiesPane",
  "shapeLibraryPane",
  "textPane",
  "pixelArtPane",
  "guidesPane",
  "overlayPane",
  "historyPane",
  "historyList",
  "exportCheckPane",
  "exportIssueList",
  "textPromptDialog",
  "messageDialog",
  "confirmationDialog",
  "confirmationDialogCancel",
  "confirmationDialogConfirm",
].forEach((id) => assert.ok(idCounts.has(id), `missing editor control: ${id}`));

const referencedIds = [
  ...script.matchAll(/\$\("([^"]+)"\)/g),
].map((match) => match[1]);
const optionalLegacyIds = new Set([
  "pixelSelect",
  "textVinylBold",
  "textVinylCustomFont",
  "textVinylFontSelect",
  "textVinylItalic",
]);
const missingReferences = [...new Set(referencedIds)]
  .filter((id) => !idCounts.has(id) && !optionalLegacyIds.has(id))
  .sort();
assert.deepEqual(
  missingReferences,
  [],
  "editor.js must not reference missing required controls",
);

const panelReferences = [
  ...html.matchAll(/\bdata-panel="([^"]+)"/g),
  ...html.matchAll(/\bdata-focus-panel="([^"]+)"/g),
].map((match) => match[1]);
panelReferences.forEach((id) => {
  assert.ok(idCounts.has(id), `panel target does not exist: ${id}`);
});

assert.equal(
  idCounts.get("shapePlacementMode"),
  1,
  "placement mode must have one authoritative control",
);
assert.equal(
  (html.match(/class="dockGroup layersDock"/g) || []).length,
  1,
  "Layers must have one persistent dock",
);
assert.match(script, /window\.addEventListener\("beforeunload"/);
assert.match(script, /function exportValidation\(/);
assert.match(script, /function renderHistoryList\(/);
assert.match(script, /function copySelectedLayers\(/);
assert.match(script, /function distributeSelected\(/);
assert.match(script, /function startEditorTour\(/);
assert.match(script, /function confirmWorkspaceReplacement\(/);
assert.match(script, /function startBlankCanvas\(/);
assert.match(script, /function establishLoadedHistoryBoundary\(/);
assert.match(script, /establishLoadedHistoryBoundary\("open project"/);
assert.match(script, /establishLoadedHistoryBoundary\("recovered work"/);
assert.doesNotMatch(script, /window\.(?:prompt|alert)\s*\(/);
assert.match(script, /const EDITOR_MUTATION_HEADERS/);
assert.match(html, /editor-fabric-adapter\.js/);
assert.match(fabricAdapter, /function scenePoint\(/);
assert.match(fabricAdapter, /function replaceObjectStack\(/);
assert.match(fabricAdapter, /Fabric SVG import and serialization are disabled/);
assert.doesNotMatch(script, /\.getPointer\(/);
assert.doesNotMatch(script, /\.toSVG\(/);
assert.doesNotMatch(script, /loadSVGFrom(?:String|URL)/);
const postBlocks = [...script.matchAll(/fetch\([^;]+?method:\s*"POST"[^;]+?\);?/gs)]
  .map((match) => match[0]);
assert.ok(postBlocks.length >= 8, "all editor mutation requests should be visible");
postBlocks.forEach((block) => {
  assert.match(
    block,
    /EDITOR_MUTATION_HEADERS/,
    "every editor mutation request must include the local request header",
  );
});
assert.match(html, /Place a shape or open a vinyl JSON/);
assert.match(styles, /@media \(max-width: 1100px\)/);
assert.match(styles, /\.dockSplitter/);
assert.match(styles, /\.historyList/);
assert.match(styles, /\.exportIssue/);

console.log("editor-shell.node.js: all assertions passed");
