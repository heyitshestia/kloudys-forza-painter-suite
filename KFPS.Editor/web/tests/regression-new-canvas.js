async page => {
  const h = require(path.join(__dirname, "dense-human-fixture.cjs"));
  const check = (ok, message) => { if (!ok) throw Error(message); };
  const initial = await h.setup(page, output, { layers: 2400 });
  await page.evaluate(async () => {
    const image = document.createElement("canvas"); image.width = image.height = 256;
    const ctx = image.getContext("2d"); ctx.fillStyle = "#50bbdd"; ctx.fillRect(0, 0, 256, 256);
    await editorReference.loadOverlayImageFromUrl(image.toDataURL(), "new-reference.png");
    window.c8Source = { shapes: snapshotShapes(), name: "New retained source" };
    await flushPendingAutosave();
  });
  const retained = await h.snapshot(page);
  await page.locator("#newCanvas").click(); await page.locator("#confirmationDialogCancel").click();
  check(await h.snapshot(page) === retained && await page.evaluate(() => Boolean(editorReference.image)), "Cancelled New changed shapes/reference");
  await page.locator("#saveProjectAs").click(); await h.type(page, "#textPromptInput", "New retained source");
  await page.locator("#textPromptInput").press("Enter");
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  await page.evaluate(async () => {
    const saved = await readEditorDocument(`${PROJECT_FILE_API}?id=${encodeURIComponent(editorProjects.association.target_id)}`);
    c8Source = saved.payload;
  });
  const required = await page.evaluate(async () => {
    await flushPendingAutosave();
    const state = currentHistoryState(), identity = documentIdentity, association = editorProjects.association;
    const image = editorReference.image, revision = editorRecovery.revision;
    const original = syncCanvasObjectCoords;
    syncCanvasObjectCoords = () => { throw Error("Injected required New install failure"); };
    let rejected = false;
    try { await startBlankCanvas(); } catch (_) { rejected = true; }
    finally { syncCanvasObjectCoords = original; }
    return { rejected, retained: currentHistoryState() === state && documentIdentity === identity
      && editorProjects.association === association && editorReference.image === image && editorRecovery.revision === revision };
  });
  check(required.rejected && required.retained && await h.snapshot(page) === retained, "Required New failure did not retain accepted work");
  const faults = [];
  for (const site of ["updateDocumentState", "refreshLayers", "resetView", "renderHistoryList"]) {
    await page.evaluate(async site => {
      await loadProjectPayload({ ...c8Source, name: `New ${site}` }); await saveProject(); await flushPendingAutosave();
      if (documentDirty) throw Error("Fault fixture was not saved");
    }, site);
    await page.evaluate(site => {
      const originals = { updateDocumentState, refreshLayers, resetView, renderHistoryList };
      window.c8OldIdentity = documentIdentity;
      window.c8PresenterCalls = 0;
      window.c8RestorePresenter = () => { window[site] = originals[site]; };
      window[site] = (...args) => {
        if (!vinylObjects().length) { c8PresenterCalls++; throw Error(`Injected New ${site}`); }
        return originals[site](...args);
      };
    }, site);
    try {
      await page.locator("#newCanvas").click();
      await page.waitForFunction(() => !vinylObjects().length && editorHistory.entries.length === 1 && editorRecovery.status.serverOk === true);
      const state = await page.evaluate(async () => ({
        coherent: documentIdentity === c8OldIdentity + 1 && currentHistoryState().shapes.length === 0
          && currentProjectName === null && editorProjects.association === null && editorHistory.floor === -1
          && !documentDirty && !editorReference.image && !guideState.guides.length,
        injected: c8PresenterCalls > 0,
        cleared: !(await readAutosavePayload()),
      }));
      check(Object.values(state).every(Boolean), `New ${site} failed: ${JSON.stringify(state)}`);
      faults.push({ site, ...state });
    } finally {
      await page.evaluate(() => { c8RestorePresenter(); document.querySelectorAll("dialog[open]").forEach(d => d.close()); });
    }
  }
  const stale = await page.evaluate(async () => {
    const prewarm = editorRenderer.prewarmHybridMeshesForObjects;
    let release, entered;
    const barrier = new Promise(resolve => { entered = resolve; });
    editorRenderer.prewarmHybridMeshesForObjects = async objects => {
      if (!objects.length) return prewarm(objects);
      entered(); await new Promise(resolve => { release = resolve; });
    };
    try {
      const old = loadPayload(c8Source);
      await barrier; await startBlankCanvas(); release();
      return !await old && vinylObjects().length === 0 && currentHistoryState().shapes.length === 0;
    } finally { editorRenderer.prewarmHybridMeshesForObjects = prewarm; release?.(); }
  });
  check(stale, "Stale Open replaced the accepted New canvas");
  const protection = await page.evaluate(async () => {
    await loadProjectPayload({ ...c8Source, name: "New recovery failure" }); await saveProject(); await flushPendingAutosave();
    if (documentDirty) throw Error("Recovery fault fixture was not saved");
    const request = editorPersistence.request;
    editorPersistence.request = (operation, data, ...rest) => operation === "recovery" && data.payload.action === "clear"
      ? Promise.resolve({ serverOk: false, browserOk: false, retryable: true, error: "Injected clear failure" })
      : request(operation, data, ...rest);
    try {
      await startBlankCanvas();
      return { blank: vinylObjects().length === 0 && editorHistory.entries.length === 1,
        failed: editorRecovery.status.state === "failed", retry: editorRecovery.retryScheduled };
    } finally { editorPersistence.request = request; }
  });
  check(Object.values(protection).every(Boolean), "Failed recovery clear was hidden or blank state incoherent");
  await page.evaluate(async () => { await clearAutosave(); document.querySelectorAll("dialog[open]").forEach(d => d.close()); });
  await page.locator('[data-tool-mode="shapeLibrary"]').click();
  await page.locator("#shapeFamily").selectOption("Primitives"); await h.type(page, "#shapeSearch", "1048677");
  await page.locator("#shapeGrid .shapeTile img").first().click();
  await page.waitForFunction(() => vinylObjects().length === 1 && !editorCommands.busy);
  await page.locator("#undoBtn").click();
  await page.waitForFunction(() => !vinylObjects().length && !editorCommands.busy);
  await page.locator("#redoBtn").click();
  await page.waitForFunction(() => vinylObjects().length === 1 && !editorCommands.busy);
  await page.locator("#newCanvas").click(); await page.locator("#confirmationDialogConfirm").click();
  await page.waitForFunction(() => !vinylObjects().length && editorRecovery.status.serverOk === true);
  await page.screenshot({ path: path.join(output, "new-canvas-blank.png") });
  return { passed: true, initial, cancellation: true, required, faults, staleLoad: stale,
    recoveryFailure: protection, subsequentAddUndoRedo: true, restartPending: true };
}
