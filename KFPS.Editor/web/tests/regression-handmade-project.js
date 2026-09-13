async (page, options = {}) => {
  const h = require(path.join(__dirname, "handmade-project-fixture.cjs"));
  page.setDefaultTimeout(120000);
  const initial = await h.setup(page, output, options);
  const source = h.input(options);
  const original = await h.snapshot(page);
  const reference = await h.referenceState(page);
  await page.screenshot({ path: path.join(output, "handmade-original.png") });
  const trace = await h.monitor(page, output);
  try {
    await trace.run("original/save-as", () => h.saveAs(page, "Handmade baseline checkpoint"));
    const savedPath = path.join(h.profile(output), "projects", "Handmade baseline checkpoint.fabric-project.json");
    const saved = JSON.parse(fs.readFileSync(savedPath, "utf8"));
    h.check(JSON.stringify(saved.shapes) === original, "Saved project differs from accepted original shapes");
    h.check(saved.editor_source_overlay.data_url === source.project.editor_source_overlay.data_url, "Save changed embedded reference bytes");
    await trace.run("original/new-reopen", async () => {
      await page.locator("#newCanvas").click();
      await page.waitForFunction(() => !vinylObjects().length && !recoveryRestoreDepth);
      await h.openStored(page, "Handmade baseline checkpoint", initial.layers);
      await page.waitForFunction(dimensions => editorReference.image?.width === dimensions[0]
        && editorReference.image?.height === dimensions[1], initial.reference);
    });
    h.check(await h.snapshot(page) === original, "Reopened handmade artwork differs");
    h.check(JSON.stringify(await h.referenceState(page)) === JSON.stringify(reference), "Reopen changed reference geometry/controls");
    await page.evaluate(async () => { await flushPendingAutosave(); });
    const recovery = await page.evaluate(async () => {
      const stored = await readAutosavePayload();
      if (JSON.stringify(stored.shapes) !== JSON.stringify(snapshotShapes())) throw Error("Handmade recovery differs");
      return { server: editorRecovery.status.serverOk, browser: editorRecovery.status.browserOk, layers: stored.shapes.length };
    });
    h.check(recovery.server && recovery.browser, "Handmade recovery did not reach both stores");
    h.check(h.hash(fs.readFileSync(source.filename)) === source.sha256, "Private input was modified");
    await page.screenshot({ path: path.join(output, "handmade-reopened.png") });
    return { initial, rows: trace.rows, exactArtworkSaveReopen: true, exactReferenceBytes: true,
      exactReferenceState: true, recovery, originalUnchanged: true };
  } finally { await trace.close(); }
}
