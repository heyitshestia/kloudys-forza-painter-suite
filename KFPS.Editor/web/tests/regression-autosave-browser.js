async (page) => {
  const h = require(path.join(__dirname, "dense-human-fixture.cjs"));
  const assert = (value, message) => { if (!value) throw Error(message); };
  const idle = () => page.waitForFunction(() => !projectBrowserState.loading && !projectBrowserState.restoring);
  const snapshot = () => page.evaluate(() => JSON.stringify({ shapes: snapshotShapes(), guides: savedGuideState(),
    collapsed: collapsedLayerGroupIds(), reference: editorReference.sourceOverlayProjectState() }));
  const open = async () => {
    await page.locator("#loadProject").click();
    await page.locator("#recentAutosavesTab").click();
    await idle();
  };
  const checkpoint = async () => page.evaluate(async () => {
    await flushPendingAutosave();
    if (editorRecovery.backupPromise) await editorRecovery.backupPromise;
    return (await (await fetch(`${EDITOR_AUTOSAVE_API}?history=1`)).json()).entries;
  });
  const initial = await h.setup(page, output, { layers: 2400 });
  const png = await page.evaluate(() => {
    const c = document.createElement("canvas"); c.width = 512; c.height = 256;
    const context = c.getContext("2d"); context.fillStyle = "#36b8ae"; context.fillRect(0, 0, 512, 256);
    return c.toDataURL().split(",")[1];
  });
  const imagePath = path.join(output, "recovery-reference.png");
  fs.writeFileSync(imagePath, Buffer.from(png, "base64"));
  await page.locator('[data-panel="overlayPane"]').click();
  await h.fileInput(page, "#overlayInput", imagePath);
  await page.waitForFunction(() => Boolean(editorReference.image));
  await page.evaluate(() => {
    applySavedGuideState({ version: 1, gridEnabled: true, gridSize: 37, guidesVisible: true,
      guides: [{ id: "recovery-guide", x1: -500, y1: -250, x2: 500, y2: 250, constraint: "free" }] });
    pushHistory("manual recovery fixture");
  });
  await page.locator("#saveProjectAs").click();
  await page.locator("#textPromptInput").fill("Manual recovery test");
  await page.locator("#textPromptInput").press("Enter");
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  await checkpoint();
  const saved = await snapshot();
  await page.evaluate(() => {
    const object = vinylObjects()[0]; object.left += 37; object.setCoords(); pushHistory("first unsaved checkpoint");
  });
  const first = (await checkpoint())[0];
  const expected = await snapshot();
  await page.evaluate(() => {
    const object = vinylObjects()[0]; object.left += 83; object.setCoords(); pushHistory("second unsaved checkpoint");
  });
  const entries = await checkpoint();
  assert(entries.length === 2 && entries[1].id === first.id, "Previous checkpoint missing");
  const current = await snapshot();
  const processInfo = JSON.parse(fs.readFileSync(path.join(output, "process.json"), "utf8"));
  const disk = () => ["autosave.json", "autosave.previous.json", "autosave.revision.json"].map(name =>
    crypto.createHash("sha256").update(fs.readFileSync(path.join(processInfo.profile, name))).digest("hex"));
  const before = disk();
  await open();
  assert(await page.locator(".projectBrowserEntry").count() === 2, "Wrong checkpoint count in UI");
  assert(!await page.locator("#addProjectEntry").isVisible(), "Autosaves expose project-add action");
  await page.locator("#refreshProjectBrowser").click(); await idle();
  assert(JSON.stringify(before) === JSON.stringify(disk()), "Browsing changed stored autosaves");
  await page.locator(".projectBrowserEntry").nth(1).click();
  await page.locator("#selectProjectEntry").click();
  await page.locator("#confirmationDialogCancel").click(); await idle();
  assert(await snapshot() === current, "Cancel changed current work");
  assert(JSON.stringify(before) === JSON.stringify(disk()), "Cancel changed recovery files");
  await page.locator(".projectBrowserEntry").nth(1).dblclick();
  await page.locator("#confirmationDialogConfirm").click();
  await page.locator("#projectBrowserDialog").waitFor({ state: "hidden" }); await idle();
  assert(await snapshot() === expected, "Manual recovery changed geometry, groups, guides or reference");
  assert(await page.evaluate(() => documentDirty), "Unsaved recovery incorrectly marked saved");

  await open();
  await page.locator("#savedProjectsTab").click(); await idle();
  assert(await page.locator("#addProjectEntry").isVisible(), "Saved project actions missing");
  await page.locator(".projectBrowserEntry").filter({ hasText: "Manual recovery test" }).click();
  await page.locator("#selectProjectEntry").click();
  await page.locator("#confirmationDialogConfirm").click();
  await page.locator("#projectBrowserDialog").waitFor({ state: "hidden" });
  assert(await snapshot() === saved, "Saved project reload regressed");
  await checkpoint();

  // A selection must fail explicitly if both retained slots have rotated away.
  await open();
  await page.locator(".projectBrowserEntry").last().click();
  await page.evaluate(async () => {
    for (let i = 0; i < 2; i++) {
      const o = vinylObjects()[0]; o.left += 12; o.setCoords(); pushHistory("rotate displayed checkpoint");
      await flushPendingAutosave();
    }
  });
  const rotated = await snapshot();
  await page.locator("#selectProjectEntry").click(); await idle();
  assert((await page.locator("#projectBrowserStatus").innerText()).includes("no longer available"), "Stale selection did not report rotation");
  assert(await snapshot() === rotated, "Stale selection replaced current work");
  await page.locator("#refreshProjectBrowser").click(); await idle();
  await page.screenshot({ path: path.join(output, "autosaves-en.png") });
  await page.locator("#closeProjectBrowser").click();

  await page.locator("#saveProject").click();
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  await checkpoint();
  await page.evaluate(async () => {
    await clearAutosave();
    KfpsEditorPreferences.setItem("kloudyFabricLanguage", "ko");
    await KfpsEditorPreferences.flush();
  });
  await page.reload();
  await page.waitForFunction(() => window.KfpsDesktop?.ready && KfpsI18n.language === "ko");
  await page.evaluate(() => document.querySelectorAll("dialog[open]").forEach(d => d.close()));
  await open();
  assert(await page.locator("#recentAutosavesTab").innerText() === "최근 자동 저장", "Korean tab label missing");
  assert(await page.locator(".projectBrowserEntry").count() === 0, "Discarded recovery resurfaced after restart");
  assert(await page.locator("#selectProjectEntry").isDisabled(), "Empty list can load");
  const layouts = [];
  for (const size of [{ width: 1440, height: 900 }, { width: 900, height: 640 }]) {
    await page.setViewportSize(size);
    const fits = await page.evaluate(() => {
      const d = $("projectBrowserDialog"), r = d.getBoundingClientRect();
      return r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight && d.scrollWidth <= d.clientWidth + 1;
    });
    assert(fits, `Recovery dialog overflows ${size.width}`); layouts.push(size);
    await page.screenshot({ path: path.join(output, `autosaves-ko-${size.width}.png`) });
  }
  await page.locator("#recentAutosavesTab").focus();
  await page.keyboard.press("ArrowLeft"); await idle();
  assert(await page.locator("#savedProjectsTab").getAttribute("aria-selected") === "true", "Keyboard tab switch failed");
  await page.locator("#closeProjectBrowser").click();
  return { initial, readOnlyBrowseAndCancel: true, exactPreviousRestore: true, savedProjectsUnchanged: true,
    staleSelectionRejected: true, clearSurvivesRestart: true, korean: true, layouts };
}
