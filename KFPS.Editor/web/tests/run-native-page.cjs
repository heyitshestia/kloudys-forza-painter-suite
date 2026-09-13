const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { chromium } = require("playwright");

(async () => {
  const [, , port, output, ...scripts] = process.argv;
  const testOptions = JSON.parse(process.env.KFPS_TEST_OPTIONS || "{}");
  if (!testOptions || Array.isArray(testOptions) || typeof testOptions !== "object") throw Error("Test options must be a JSON object");
  const browser = await chromium.connectOverCDP(`http://127.0.0.1:${port}`, { noDefaults: true });
  const page = browser.contexts()[0].pages().find(p => p.url().includes("fabric-editor"));
  if (!page) throw new Error("Native editor page missing");
  page.setDefaultTimeout(120000);
  const errors = [], errorRecords = [];
  let activeScript = null;
  const contracts = JSON.parse(fs.readFileSync(path.join(__dirname, "workflow-contracts.json"), "utf8"));
  const { validatePageErrors } = require("./workflow-errors.cjs");
  page.on("pageerror", error => {
    const message = String(error);
    errors.push(message);
    errorRecords.push({ script: activeScript, message });
  });
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
  const appRoot = process.env.KFPS_TEST_APP_ROOT || path.resolve(__dirname, "../../..");
  const manifest = JSON.parse(fs.readFileSync(path.join(appRoot, "KFPS.Editor/manifest.json"), "utf8"));
  const verifiedAssets = manifest.web.filter(item=>["composition", "module"].includes(item.role)).map(item=>item.path);
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
      const expectedRoot = process.env.KFPS_EDITOR_BASELINE_DIR && ["editor.js", "editor-fabric-adapter.js", "editor-core.js"].includes(name)
        ? process.env.KFPS_EDITOR_BASELINE_DIR : path.join(appRoot, manifest.web_root);
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
      activeScript = path.basename(script);
      if (!testOptions.preserveStartupNotices) await page.evaluate(async () => {
        localStorage.setItem("kloudyFabricStartupHelpConfirmed", "true");
        KfpsEditorPreferences.setItem("kloudyFabricProjectSharingAcknowledged", "1");
        KfpsEditorPreferences.setItem("kloudyFabricLanguageNoticeAcknowledged", "1");
        KfpsEditorPreferences.setItem(EDITOR_UPDATE_ACK_KEY, EDITOR_UPDATE_NOTICE_VERSION);
        KfpsEditorPreferences.setItem("kloudyFabricLanguage", "en");
        await KfpsEditorPreferences.flush();
        await writeStartupHelpConfirmed();
        document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close());
      });
      await page.waitForTimeout(400);
      if (!testOptions.preserveStartupNotices) await page.evaluate(() => document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close()));
      const start = Date.now();
      try {
        const source = fs.readFileSync(script, "utf8");
        const evidence = path.join(output, 'test-inputs');
        fs.mkdirSync(evidence, { recursive: true });
        fs.writeFileSync(path.join(evidence, path.basename(script)), source);
        fs.writeFileSync(path.join(evidence, path.basename(script) + '.json'), JSON.stringify({
          sha256: crypto.createHash('sha256').update(source).digest('hex'), options: testOptions,
        }, null, 2));
        if (source.includes("page.workers") && !page.workers().some(worker => worker.url().includes("editor-persistence-worker"))) {
          // CDP cannot discover this Qt worker if it started before attachment.
          // Recreate it after all writes settle so fault tests observe a real worker.
          await page.evaluate(async () => {
            await flushPendingAutosave();
            if (editorRecovery.backupPromise) await editorRecovery.backupPromise;
            editorPersistence.reset(new Error("Regression worker attachment"));
            await editorPersistence.request("recoveryHead");
          });
        }
        const run = eval(`(${source})`);
        const result = await run(page, testOptions);
        const passed = result?.passed !== false;
        results.push({ script: path.basename(script), passed, ms: Date.now() - start, result });
        if (!passed) process.exitCode = 1;
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
  const pageErrors = validatePageErrors(errorRecords, scripts.map(script => path.basename(script)), contracts);
  fs.writeFileSync(path.join(output, "results.json"), JSON.stringify({ results, errors, pageErrors }, null, 2));
  if (!pageErrors.passed) {
    process.exitCode = 1;
    console.error("Unexpected or missing injected page errors:", JSON.stringify(pageErrors));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
