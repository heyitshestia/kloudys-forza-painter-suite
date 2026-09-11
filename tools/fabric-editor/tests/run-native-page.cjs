const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

(async () => {
  const [, , port, output, ...scripts] = process.argv;
  const browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`, { noDefaults: true });
  const page = browser.contexts()[0].pages().find(p => p.url().includes("fabric-editor"));
  if (!page) throw new Error("Native editor page missing");
  page.setDefaultTimeout(120000);
  const errors = [];
  page.on("pageerror", error => errors.push(String(error)));
  if (process.env.KFPS_EDITOR_BASELINE_DIR) {
    const baseline = process.env.KFPS_EDITOR_BASELINE_DIR;
    for (const name of ["editor.js", "editor-fabric-adapter.js", "editor-core.js"]) {
      await page.route(`**/tools/fabric-editor/${name}?**`, route => route.fulfill({ path: path.join(baseline, name), contentType: "text/javascript" }));
    }
    await page.reload();
    await page.waitForFunction(() => window.KfpsDesktop?.ready);
  }
  // Disk identity alone cannot detect a stale HTTP-cached executable. Read back
  // the sources actually parsed by this renderer, then disable the debugger.
  const debuggerSession = await page.context().newCDPSession(page);
  const parsed = new Map();
  const verifiedAssets = ["editor.js", "editor-fabric-adapter.js", "editor-core.js"];
  debuggerSession.on("Debugger.scriptParsed", entry => {
    const name = entry.url.split("/").pop().split("?")[0];
    if (verifiedAssets.includes(name)) parsed.set(name, entry.scriptId);
  });
  const assetReadback = [];
  try {
    await debuggerSession.send("Debugger.enable");
    const crypto = require("node:crypto");
    const hash = value => crypto.createHash("sha256").update(value).digest("hex");
    for (const name of verifiedAssets) {
      if (!parsed.has(name)) throw new Error(`Renderer did not parse ${name}`);
      const source = await debuggerSession.send("Debugger.getScriptSource", { scriptId: parsed.get(name) });
      const expectedRoot = process.env.KFPS_EDITOR_BASELINE_DIR || path.resolve(__dirname, "..");
      const expected = hash(fs.readFileSync(path.join(expectedRoot, name)));
      const actual = hash(source.scriptSource);
      assetReadback.push({ name, expected, actual, matched: expected === actual });
      if (expected !== actual) throw new Error(`Renderer has stale/mixed executable source: ${name}`);
    }
  } finally {
    fs.writeFileSync(path.join(output, "asset-readback.json"), JSON.stringify(assetReadback, null, 2));
    await debuggerSession.send("Debugger.disable");
    await debuggerSession.detach();
  }
  const results = [];
  try {
    for (const script of scripts) {
      await page.evaluate(async () => {
        localStorage.setItem("kloudyFabricStartupHelpConfirmed", "true");
        KfpsEditorPreferences.setItem("kloudyFabricProjectSharingAcknowledged", "1");
        KfpsEditorPreferences.setItem("kloudyFabricLanguageNoticeAcknowledged", "1");
        KfpsEditorPreferences.setItem("kloudyFabricLanguage", "en");
        await KfpsEditorPreferences.flush();
        await writeStartupHelpConfirmed();
        document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close());
      });
      await page.waitForTimeout(400);
      await page.evaluate(() => document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close()));
      const start = Date.now();
      try {
        const run = eval(`(${fs.readFileSync(script, "utf8")})`);
        const result = await run(page);
        results.push({ script: path.basename(script), passed: true, ms: Date.now() - start, result });
      } catch (error) {
        results.push({ script: path.basename(script), passed: false, ms: Date.now() - start, error: String(error.stack || error) });
        process.exitCode = 1;
      }
      console.log(JSON.stringify(results.at(-1)));
      fs.writeFileSync(path.join(output, "results.json"), JSON.stringify({ results, errors }, null, 2));
      await page.screenshot({ path: path.join(output, `${path.basename(script, ".js")}.png`) });
    }
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
