async page => {
  const h = require(path.join(__dirname, "dense-human-fixture.cjs"));
  const check = (ok, message) => { if (!ok) throw Error(message); };
  const idle = () => page.waitForFunction(() => !editorCommands.busy && !projectAdditionPending && !projectSaveInProgress);
  const close = () => page.evaluate(() => document.querySelectorAll("dialog[open]").forEach(d => d.close()));
  const choose = async name => {
    await page.locator("#loadProject").click();
    await page.locator(".projectBrowserEntry").filter({ hasText: name }).first().click();
  };
  const checks = [];
  await page.evaluate(async () => {
    const shapes = Array.from({ length: 30 }, (_, i) => ({ type: 1048677, color: [210, 80, 130, 180],
      data: [i % 10 * 35 - 150, Math.floor(i / 10) * 40, .25, .3, i * 3, .1, 0],
      editor_group_id: "self-group", editor_group_name: "Original child" }));
    await loadProjectPayload({ name: "Self addition", shapes }, "Self addition");
    await saveProject(); window.selfBefore = snapshotShapes();
  });
  await choose("Self addition");
  await page.locator("#addProjectEntry").click(); await idle();
  check(await page.evaluate(() => vinylObjects().length === 60
    && JSON.stringify(snapshotShapes().slice(0, 30)) === JSON.stringify(selfBefore)
    && new Set(snapshotShapes().map(s => s.editor_id)).size === 60
    && KfpsEditorLayerGroups.objectPath(vinylObjects()[30]).length === 2), "Self-add failed or changed existing shapes");
  checks.push("self-add is independent and retains destination save association");
  await page.locator("#saveProject").click(); await idle();

  await h.setup(page, output, { layers: 2700 });
  // The source file uses the actual project persistence boundary, not a fake browser row.
  await page.evaluate(async () => {
    window.boundarySource = { name: "Boundary piece", shapes: Array.from({ length: 300 }, (_, i) => ({
      type: i % 2 ? 1048678 : 1048677, color: [120, 170, 210, 180],
      data: [i % 20 * 24 - 240, Math.floor(i / 20) * 24 - 180, .18, .18, i % 4 * 10, 0, i === 6 ? 1 : 0],
      mask: i === 6, editor_hidden: i === 4, editor_locked: i === 5,
      editor_group_id: "boundary-child", editor_group_name: "Boundary child",
    })) };
    await editorProjects.save(boundarySource.name, boundarySource, null);
    currentProjectName = "Capacity destination"; await saveProject();
    window.boundaryBefore = JSON.stringify(snapshotShapes());
  });

  const faults = await page.evaluate(async () => {
    const results = [];
    const state = () => JSON.stringify({ shapes: snapshotShapes(), history: editorHistory.index, collapsed: collapsedLayerGroupIds(), receipt: editorProjects.association });
    const unchanged = state();
    const run = payload => queueEditorMutation(context => addProjectPayloadNow(payload, "Boundary piece", context), "add");
    for (const bad of [{ shapes: [] }, { shapes: [{ ...boundarySource.shapes[0], data: [0, 0, null, 0, 0] }] },
      { shapes: [{ ...boundarySource.shapes[0], editor_group_path: [{ id: "cycle", name: "A" }, { id: "cycle", name: "A" }] }] }]) {
      let rejected = false; try { await run(bad); } catch (_) { rejected = true; }
      if (!rejected || state() !== unchanged) throw Error("Invalid project changed current state");
    }
    results.push("invalid/empty/cyclic input rejected without changes");
    const originalBuild = makeFabricObject;
    let builds = 0;
    makeFabricObject = async (...args) => { if (++builds === 5) throw Error("Injected shape build failure"); return originalBuild(...args); };
    try {
      let rejected = false; try { await run(boundarySource); } catch (_) { rejected = true; }
      if (!rejected || state() !== unchanged) throw Error("Resource build failed non-atomically");
    } finally { makeFabricObject = originalBuild; }
    results.push("partial asynchronous shape build failure leaves no additions/history");
    const originalAdd = canvas.add;
    let installs = 0;
    canvas.add = function (...objects) { if (++installs === 8) throw Error("Injected canvas installation failure"); return originalAdd.apply(this, objects); };
    try {
      let rejected = false; try { await run(boundarySource); } catch (_) { rejected = true; }
      if (!rejected || state() !== unchanged) throw Error("Partial installation did not roll back");
    } finally { canvas.add = originalAdd; }
    results.push("partial canvas installation rolls back shapes/collapsed groups/history");
    const originalCommit = editorHistory.commit;
    editorHistory.commit = () => { throw Error("Injected history failure"); };
    try {
      let rejected = false; try { await run(boundarySource); } catch (_) { rejected = true; }
      if (!rejected || state() !== unchanged) throw Error("Failed history commit left an addition");
    } finally { editorHistory.commit = originalCommit; }
    results.push("history failure rolls back the entire addition");
    return results;
  });
  checks.push(...faults);
  await page.evaluate(() => {
    window.originalAddBuild = makeFabricObject;
    window.addGate = new Promise(resolve => { window.releaseAddGate = resolve; });
    makeFabricObject = async (...args) => { window.addBuildWaiting = true; await addGate; return originalAddBuild(...args); };
  });
  await choose("Boundary piece");
  await page.locator("#addProjectEntry").click();
  await page.waitForFunction(() => window.addBuildWaiting);
  check(await page.locator("#addProjectEntry").isDisabled(), "Add not single-flight");
  await page.locator("#closeProjectBrowser").click();
  await page.evaluate(() => { makeFabricObject = originalAddBuild; releaseAddGate(); }); await idle();
  check(await page.evaluate(() => JSON.stringify(snapshotShapes()) === boundaryBefore), "Closing browser did not cancel staged Add");
  checks.push("closing browser cancels staged copy; Add remains single-flight");

  await page.evaluate(() => {
    window.originalAddRead = readEditorDocument;
    window.lateAddGate = new Promise(resolve => { window.releaseLateAdd = resolve; });
    readEditorDocument = async (...args) => {
      if (args[0].startsWith(PROJECT_FILE_API + "?")) {
        window.lateAddWaiting = true; await lateAddGate; throw Error("Injected late project read failure");
      }
      return originalAddRead(...args);
    };
  });
  await choose("Boundary piece"); await page.locator("#addProjectEntry").click();
  await page.waitForFunction(() => window.lateAddWaiting);
  await page.locator("#closeProjectBrowser").click();
  await page.evaluate(async () => {
    readEditorDocument = originalAddRead;
    await loadProjectPayload({ name: "Replacement workspace", shapes: boundarySource.shapes.slice(0, 1) }, "Replacement workspace");
    releaseLateAdd();
  });
  await idle();
  check(await page.locator("#messageDialog").isHidden(), "A cancelled old Add showed an error over the new document");
  check(await page.evaluate(() => vinylObjects().length === 1 && currentProjectName === "Replacement workspace"), "Stale addition crossed document boundary");
  await page.evaluate(async () => {
    const listing = await readEditorDocument(PROJECT_BROWSER_API);
    const entry = listing.entries.find(e => e.title === "Capacity destination");
    const disk = await readEditorDocument(`${PROJECT_FILE_API}?id=${encodeURIComponent(entry.id)}`);
    await loadProjectPayload(disk.payload, entry.title, { receipt: disk.receipt });
  });
  check(await page.evaluate(() => JSON.stringify(snapshotShapes()) === boundaryBefore), "Reload fixture no longer matches saved destination");
  checks.push("late failed read after cancellation cannot change or show a dialog over a replacement document");

  await choose("Boundary piece"); await page.locator("#addProjectEntry").click(); await idle();
  check(await page.evaluate(() => vinylObjects().length === 3000), "Exactly 3,000 shapes was rejected");
  const full = await h.snapshot(page);
  await choose("Boundary piece"); await page.locator("#addProjectEntry").click(); await idle();
  check(await page.locator("#messageDialog").isVisible(), "Overflow was not explained");
  check(await h.snapshot(page) === full, "Overflow partially inserted shapes"); await close();
  checks.push("exactly 3,000 accepted; overflow counts hidden/locked/masks and preserves full canvas");
  await page.locator("#undoBtn").click(); await idle();
  check(await page.evaluate(() => JSON.stringify(snapshotShapes()) === boundaryBefore), "Capacity addition did not undo in one step");
  await page.locator("#redoBtn").click(); await idle();
  check(await h.snapshot(page) === full, "Capacity redo changed shapes");
  await page.locator("#saveProject").click(); await idle();

  const layouts = [];
  for (const language of ["en", "ko"]) {
    await page.evaluate(async language => { editorSettings.setItem(KfpsI18n.KEY, language); await KfpsEditorPreferences.flush(); }, language);
    await page.reload(); await page.waitForFunction(() => window.KfpsDesktop?.ready && vinylObjects().length === 3000 && !recoveryRestoreDepth);
    await close();
    await choose("Boundary piece");
    check((await page.locator("#addProjectEntry").innerText()).includes(language === "en" ? "Add to Current Project" : "현재 프로젝트에 추가"), "Add button not localized");
    for (const width of [1440, 900]) {
      await page.setViewportSize({ width, height: 900 });
      const fits = await page.evaluate(() => {
        const dialog = document.getElementById("projectBrowserDialog").getBoundingClientRect();
        const a = document.getElementById("addProjectEntry").getBoundingClientRect();
        const b = document.getElementById("selectProjectEntry").getBoundingClientRect();
        return dialog.left >= 0 && dialog.right <= innerWidth && dialog.bottom <= innerHeight
          && a.left >= dialog.left && b.right <= dialog.right && (a.right <= b.left || a.bottom <= b.top);
      });
      check(fits, `${language} ${width} Add/Load layout overlaps`);
      await page.screenshot({ path: path.join(output, `project-add-${language}-${width}.png`) });
      layouts.push({ language, width, fits });
    }
    await page.locator("#closeProjectBrowser").click();
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.evaluate(async () => {
    // Finish on an unsaved native edit so the next independent process must recover it.
    vinylObjects()[2999].left += 13; vinylObjects()[2999].setCoords(); pushHistory("restart checkpoint");
    await flushPendingAutosave();
    const recovery = await readAutosavePayload();
    if (JSON.stringify(recovery.shapes) !== JSON.stringify(snapshotShapes())) throw Error("Recovery did not store the exact added scene");
  });
  fs.writeFileSync(path.join(output, "expected-restart.json"), JSON.stringify(await page.evaluate(() => editableProjectPayload(currentProjectName))));
  return { passed: true, checks, layouts, restartExpected: path.join(output, "expected-restart.json") };
}
