"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.join(__dirname, "..");
const catalog = JSON.parse(fs.readFileSync(path.join(root, "locales/ko.json"), "utf8"));
const source = fs.readFileSync(path.join(root, "editor-i18n.js"), "utf8");
function fixture(system = "ko-KR", saved = null, query = "", desktopSystem = null) {
  const storage = new Map(saved ? [["kloudyFabricLanguage", saved]] : []);
  const sandbox = { KfpsEditorSystemLanguage: desktopSystem, navigator: { language: system }, location: { search: query }, URLSearchParams,
    localStorage: { getItem: key => storage.get(key) ?? null } };
  sandbox.window = sandbox;
  vm.runInNewContext(fs.readFileSync(path.join(root, "locales/en.js"), "utf8"), sandbox);
  vm.runInNewContext(fs.readFileSync(path.join(root, "locales/ko.js"), "utf8"), sandbox);
  vm.runInNewContext(source, sandbox);
  return sandbox.KfpsI18n;
}
let t = fixture();
assert.equal(t.language, "ko");
assert.equal(t.t("KFPS Vinyl Editor"), "K-FPS");
for (const [key, limit] of [
  ["Project exceeds the {0} MiB save limit. Use a smaller reference image and save again.", 100],
  ["Recovery exceeds the {0} MiB project limit. Use a smaller reference image.", 100],
  ["Reference exceeds the {0} MiB storage budget. Use a smaller image.", 50],
]) {
  assert.ok(t.t(key, limit).includes(`${limit} MiB`));
  assert.ok(!t.t(key, limit).includes("{0}"));
  assert.notEqual(t.t(key, limit), fixture("en-US").t(key, limit));
}
assert.equal(t.t("Save"), "저장");
assert.equal(t.familyLabel("Primitives"), "기본 도형");
assert.equal(t.shapeLabel("Square"), "정사각형");
assert.equal(t.familyLabel("New_Family"), "New Family");
assert.equal(t.t("Unknown future sentence."), "Unknown future sentence.");
assert.equal(t.t("Renamed layer to {0}.", "Save {1} <img> 테스트"), "레이어 이름을 Save {1} <img> 테스트(으)로 변경했습니다.");
assert.equal(t.t("{0} layer{1}", 2, "s"), "레이어 2개");
assert.equal(t.t("{0} layer{1}", 1, ""), "레이어 1개");
assert.equal(t.error("Division by zero is not allowed."), "0으로 나눌 수 없습니다.");
assert.equal(t.error("TypeError: a future diagnostic\n    at f (file:1)"), "TypeError: a future diagnostic\n    at f (file:1)");
assert.ok(!t.message('A project named "Save {1}" already exists. Choose a different name or open it before using Save.').includes("already exists"));
assert.ok(t.message('A project named "Save {1}" already exists. Choose a different name or open it before using Save.').includes("Save {1}"));
assert.ok(t.recoveryPattern().test(t.t("Recovery pending")));
assert.ok(!t.history("insert shape above").includes("above"));
assert.equal(fixture("en-US").language, "en");
assert.equal(fixture("ko-KR", "en").language, "en");
assert.equal(fixture("en-US", "ko").language, "ko");
assert.equal(fixture("ko-KR", "en", "?lang=ko").language, "ko");
assert.equal(fixture("en-US", "bad").language, "en");
assert.equal(fixture("en-US", null, "", "ko_KR").language, "ko");
assert.equal(fixture("en-US", "en", "", "ko_KR").language, "en");
t = fixture("en-US");
assert.equal(t.t("KFPS Vinyl Editor"), "KFPS Vinyl Editor");
assert.equal(t.t("Renamed layer to {0}.", "Save {1}"), "Renamed layer to Save {1}.");
assert.equal(t.familyLabel("Upper_Letters_1"), "Upper Letters 1");
assert.equal(t.shapeLabel("Square"), "Square");
assert.equal(t.error("Division by zero is not allowed."), "Division by zero is not allowed.");
// Placeholder sets must be preserved; only proven English plural suffix slots may disappear.
const slots = text => [...new Set([...text.matchAll(/\{(\d+)\}/g)].map(match => Number(match[1])))].sort((a, b) => a - b);
for (const [key, value] of Object.entries(catalog.messages)) {
  const omitted = catalog.pluralOmissions[key] || [];
  assert.deepEqual(slots(value), slots(key).filter(index => !omitted.includes(index)), `Placeholder mismatch: ${key}`);
  assert.equal(typeof value, "string");
  assert.ok(value.length > 0, `Empty translation: ${key}`);
}
// All explicit browser translation keys must exist in the authoritative catalog.
let references = 0;
const manifest = JSON.parse(fs.readFileSync(path.join(root, "../manifest.json"), "utf8"));
for (const file of manifest.web.filter(item=>item.localize).map(item=>item.path)) {
  const code = fs.readFileSync(path.join(root, file), "utf8");
  for (const match of code.matchAll(/(?:KfpsI18n\.t|\btr)\(("(?:\\.|[^"\\])*")/g)) {
    const key = JSON.parse(match[1]);
    assert.ok(Object.hasOwn(catalog.messages, key), `${file}: missing catalog key ${key}`);
    references++;
  }
}
assert.equal(Object.keys(catalog.families).length, 35);
console.log(`editor-i18n.node.js: locale selection, fallbacks, opaque user values, plural slots, errors, recovery, history, ${references} source references, ${Object.keys(catalog.messages).length} message entries passed`);

// English values are editable without renaming keys. Empty/missing packs fall back.
const sandbox = {navigator: {language: "ko"}, URLSearchParams,
  KfpsEditorLocales: {en: {messages: {Save: "Save project"}}, ko: {messages: {Save: ""}}}};
sandbox.window = sandbox;
vm.runInNewContext(source, sandbox);
assert.equal(sandbox.KfpsI18n.t("Save"), "Save project");
delete sandbox.KfpsEditorLocales.ko;
assert.equal(sandbox.KfpsI18n.t("Save"), "Save project");
delete sandbox.KfpsEditorLocales.en;
assert.equal(sandbox.KfpsI18n.t("Save"), "Save");
