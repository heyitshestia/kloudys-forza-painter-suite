"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../editor-i18n.js"), "utf8");
const cases = [
  ["en-US", "ja-JP", null, "", "ja"], ["ko-KR", "JA_jp", null, "", "ja"],
  ["ja-JP", null, null, "", "ja"], ["en-US", "ja-JP", "ko", "", "ko"],
  ["en-US", "ja-JP", "en", "", "en"], ["ko-KR", "ko-KR", "ja", "", "ja"],
  ["ja-JP", "en-US", null, "", "en"], ["ja-JP", "ja-JP", "ko", "?lang=en", "en"],
  ["en-US", "en-US", "ko", "?lang=ja", "ja"], ["en-US", "ja-JP", "future", "", "ja"],
];
for (const [browser, desktop, saved, query, expected] of cases) {
  const writes = [];
  const sandbox = {
    navigator: { language: browser }, KfpsEditorSystemLanguage: desktop,
    location: { search: query }, URLSearchParams,
    localStorage: { getItem: () => saved, setItem: (...args) => writes.push(args) },
    KfpsEditorLocales: { en: { messages: { Save: "Save", "Name: {0}": "Name: {0}" } }, ja: { messages: { Save: "\u4fdd\u5b58" } } },
  };
  sandbox.window = sandbox;
  vm.runInNewContext(source, sandbox);
  assert.equal(sandbox.KfpsI18n.language, expected);
  assert.equal(sandbox.KfpsI18n.locale, { en: "en-US", ko: "ko-KR", ja: "ja-JP" }[expected]);
  assert.deepEqual(writes, [], "Language discovery must not overwrite custom preferences");
  assert.equal(sandbox.KfpsI18n.t("Name: {0}", "\u65e5\u672c\u8a9e {1} <&>"), "Name: \u65e5\u672c\u8a9e {1} <&>");
  if (expected === "ja") assert.equal(sandbox.KfpsI18n.t("Save"), "\u4fdd\u5b58");
}
console.log(JSON.stringify({ passed: true, cases: cases.length, settingsWrites: 0 }));
