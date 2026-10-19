"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.join(__dirname, "..");
const ja = JSON.parse(fs.readFileSync(path.join(root, "locales/ja.json"), "utf8"));
const sandbox = { navigator: { language: "ja-JP" }, URLSearchParams };
sandbox.window = sandbox;
for (const file of ["locales/en.js", "locales/ko.js", "locales/ja.js", "editor-i18n.js"]) {
  vm.runInNewContext(fs.readFileSync(path.join(root, file), "utf8"), sandbox, { filename: file });
}
const api = sandbox.KfpsI18n;
assert.equal(api.language, "ja");
assert.deepEqual(JSON.parse(JSON.stringify(sandbox.KfpsEditorLocales.ja)), ja);
const values = Array.from({ length: 20 }, (_, index) => `user-${index}:日本語 한국어 <&> {19}`);
for (const [key, translated] of Object.entries(ja.messages)) {
  const expected = translated.replace(/\{(\d+)\}/g, (_, index) => values[Number(index)]);
  assert.equal(api.t(key, ...values), expected, key);
}
for (const [key, value] of Object.entries(ja.families)) assert.equal(api.familyLabel(key), value, key);
for (const [key, value] of Object.entries(ja.shapeLabels)) assert.equal(api.shapeLabel(key), value, key);
assert.equal(api.t("{0} layer{1}", 1, ""), "1 レイヤー");
assert.equal(api.t("{0} layer{1}", 12, "s"), "12 レイヤー");
assert.equal(api.t("Renamed layer to {0}.", values[0]), `レイヤー名を ${values[0]} に変更しました。`);
assert.ok(api.message(`Renamed layer to ${values[0]}.`).includes(values[0]));
assert.equal(api.error("TypeError: unknown_source_diagnostic\n    at function_name:17"),
  "TypeError: unknown_source_diagnostic\n    at function_name:17");
assert.equal(api.error("Division by zero is not allowed."), ja.messages["Division by zero is not allowed."]);
assert.ok(api.recoveryPattern().test(ja.messages["Recovery pending"]));
assert.equal(api.familyLabel("Unmapped_Family"), "Unmapped Family");
assert.equal(api.shapeLabel("CUSTOM_USER_SHAPE"), "CUSTOM_USER_SHAPE");
assert.equal(api.t("Unknown future user text."), "Unknown future user text.");
console.log(`Japanese actual localization runtime: ${Object.keys(ja.messages).length} messages, `
  + `${Object.keys(ja.families).length} families, ${Object.keys(ja.shapeLabels).length} shapes; `
  + "opaque values, plural counts, diagnostics, recovery and JSON/JS pack parity passed.");
