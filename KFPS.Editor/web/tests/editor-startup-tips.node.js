"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../editor.js"), "utf8");
const startup = source.match(/^async function continueEditorStartup\(\) \{[\s\S]*?^\}/m)?.[0];
assert.ok(startup);

(async () => {
  const results = [];
  for (const scenario of [
    { name: "fresh", expected: ["recovery"] },
    { name: "acknowledged", handled: true, expected: [] },
    { name: "new", mode: "new", expected: ["blank", "url"] },
    { name: "explicit project", project: "saved.json", expected: [] },
    { name: "JSON browser", browse: "json", expected: ["browser"] },
    { name: "tutorial", mode: "tutorial", expected: [] },
  ]) {
    const calls = [];
    const context = vm.createContext({
      URL, URLSearchParams, startupRecoveryHandled: !!scenario.handled,
      location: { search: scenario.mode ? `?mode=${scenario.mode}` : "", href: `http://127.0.0.1/editor?mode=${scenario.mode || ""}` },
      window: { history: { replaceState: () => calls.push("url") } },
      startupProjectId: () => scenario.project || "",
      startupBrowseMode: () => scenario.browse || "",
      startBlankCanvas: async () => calls.push("blank"),
      maybeShowAutosaveRecovery: async () => calls.push("recovery"),
      openJsonBrowser: () => calls.push("browser"),
      maybeShowProjectSharingNotice: () => { calls.push("sharing-tip"); return true; },
      maybeShowLanguageNotice: () => { calls.push("language-tip"); return true; },
      maybeShowEditorUpdateNotice: () => { calls.push("update-tip"); return true; },
    });
    vm.runInContext(startup, context);
    await context.continueEditorStartup();
    assert.deepEqual(calls, scenario.expected, scenario.name);
    assert.equal(context.startupRecoveryHandled, true);
    results.push(scenario.name);
  }
  assert.match(source, /const startupHelpShown = await maybeShowStartupHelp\(\)/);
  assert.match(source, /addEventListener\("close", continueEditorStartup, \{ once: true \}\)/);
  console.log(JSON.stringify({ passed: true, startupPaths: results, initialHelpRetained: true }));
})().catch(error => { console.error(error); process.exitCode = 1; });
