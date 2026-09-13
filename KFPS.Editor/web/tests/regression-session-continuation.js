async page => {
  const assert = (value, message) => { if (!value) throw new Error(message); };
  const checks = [];
  const expected = await page.evaluate(async () => {
    await clearAutosave();
    await loadPayload({ shapes: Array.from({ length: 1400 }, (_, i) => ({
      type: 1048677, color: [70, 150, 210, 255], data: [i % 50 * 20 - 500, Math.floor(i / 50) * 20 - 300, .1, .1, 0, 0, 0],
      editor_group_id: `g${Math.floor(i / 20)}`, editor_group_name: `Group ${Math.floor(i / 20)}`,
    })) });
    const image = document.createElement("canvas"); image.width = image.height = 16;
    image.getContext("2d").fillRect(0, 0, 16, 16);
    await editorReference.loadOverlayImageFromUrl(image.toDataURL(), "session.png");
    currentProjectName = "Session continuation";
    await saveProject(); await flushPendingAutosave();
    const stored = await readAutosavePayload();
    if (!stored.editor_session.saved || !editorRecovery.status.serverOk) throw new Error("Successful Save discarded clean session recovery");
    return JSON.stringify({ shapes: snapshotShapes(), reference: editorReference.sourceOverlayProjectState() });
  });
  await page.reload();
  await page.waitForFunction(() => window.KfpsDesktop?.ready);
  const clean = await page.evaluate(expected => ({
    exact: expected === JSON.stringify({ shapes: snapshotShapes(), reference: editorReference.sourceOverlayProjectState() }),
    dirty: documentDirty, project: currentProjectName, retainedStartupPayload: recoveryAutosavePayload !== null,
    dialog: $("autosaveRecoveryDialog").open,
  }), expected);
  assert(clean.exact && !clean.dirty && clean.project === "Session continuation" && !clean.retainedStartupPayload && !clean.dialog, "Clean automatic continuation failed: " + JSON.stringify(clean));
  checks.push({ clean });
  const dirtyExpected = await page.evaluate(async () => {
    selectObjects(vinylObjects().slice(0, 20), "session nudge");
    nudgeSelected(7, 0); flushPendingNudgeHistory(); await flushPendingAutosave();
    const expected = JSON.stringify({ shapes: snapshotShapes(), reference: editorReference.sourceOverlayProjectState() });
    documentDirty = false;
    return expected;
  });
  await page.reload();
  await page.waitForFunction(() => window.KfpsDesktop?.ready);
  const dirty = await page.evaluate(expected => ({ exact: expected === JSON.stringify({ shapes: snapshotShapes(), reference: editorReference.sourceOverlayProjectState() }), dirty: documentDirty, dialog: $("autosaveRecoveryDialog").open }), dirtyExpected);
  assert(dirty.exact && dirty.dirty && !dirty.dialog, "Dirty automatic continuation lost work or marked it saved");
  checks.push({ dirty });
  const guarded = await page.evaluate(async () => {
    await flushPendingAutosave();
    const before = await readAutosavePayload();
    const originalRestore = editorReference.restoreSourceOverlayFromProject;
    let release, entered;
    const arrived = new Promise(resolve => { entered = resolve; });
    const gate = new Promise(resolve => { release = resolve; });
    editorReference.restoreSourceOverlayFromProject = async state => { await originalRestore(state); entered(); await gate; };
    try {
      const acceptedShapes = before.shapes.slice(0, 10);
      const loading = editorCommands.enqueue(() => loadProjectPayload({ name: "Guarded project", shapes: acceptedShapes,
        editor_source_overlay: before.editor_source_overlay }), 'session restore regression');
      await arrived;
      await flushPendingAutosave();
      const during = await readAutosavePayload();
      const close = await executeDesktopOperation("close", { action: "keep-recovery" });
      if (JSON.stringify(during.shapes) !== JSON.stringify(acceptedShapes)
        || during.editor_source_overlay.data_url !== before.editor_source_overlay.data_url
        || close.ok || recoveryRestoreDepth !== 0 || !editorCommands.busy)
        throw new Error("Accepted document was not protected during reference completion, or native close bypassed its active command");
      release(); await loading; await flushPendingAutosave();
      const after = await readAutosavePayload();
      if (after.shapes.length !== 10 || after.editor_source_overlay.data_url !== before.editor_source_overlay.data_url || !after.editor_session.saved) throw new Error("Completed restore did not checkpoint complete saved project");
      return { acceptedCheckpointBeforePresentation: true, pendingCommandCloseBlocked: true, completeCheckpoint: true };
    } finally { release?.(); editorReference.restoreSourceOverlayFromProject = originalRestore; }
  });
  checks.push(guarded);
  const failures = await page.evaluate(async () => {
    const before = await readAutosavePayload();
    const originalBuild = makeFabricObject;
    let calls = 0;
    makeFabricObject = shape => ++calls === 2 ? Promise.reject(new Error("Injected one-layer build failure")) : originalBuild(shape);
    try {
      const restored = await recoverAutosavePayload(before);
      if (restored || JSON.stringify(snapshotShapes()) !== JSON.stringify(before.shapes)) throw new Error("Partial layer restore replaced valid canvas");
      const persisted = await readAutosavePayload();
      if (persisted.recovery_revision !== before.recovery_revision) throw new Error("Failed restore changed last complete checkpoint");
    } finally { makeFabricObject = originalBuild; }
    const damaged = { ...before, editor_source_overlay: { ...before.editor_source_overlay, data_url: "data:image/png;base64,broken" } };
    if (!await recoverAutosavePayload(damaged)) throw new Error("Missing reference prevented layer recovery");
    if (editorReference.image || !editorReference.unavailable || !documentDirty) throw new Error("Reference failure was hidden or marked clean");
    vinylObjects()[0].left += 2; vinylObjects()[0].setCoords(); pushHistory("edit with unavailable reference");
    await flushPendingAutosave();
    const retained = await readAutosavePayload();
    if (retained.editor_source_overlay.data_url !== damaged.editor_source_overlay.data_url || editableProjectPayload("Preserved").editor_source_overlay.data_url !== damaged.editor_source_overlay.data_url) throw new Error("Unavailable original reference was silently discarded");
    editorReference.removeOverlay(); await flushPendingAutosave();
    if ((await readAutosavePayload()).editor_source_overlay) throw new Error("Explicit reference removal did not discard unavailable source");
    documentDirty = false;
    return { failedBuildPreserved: true, unavailableReferencePreserved: true, explicitRemoval: true };
  });
  checks.push(failures);
  const newUrl = await page.evaluate(() => location.origin + location.pathname + "?mode=new");
  await page.goto(newUrl);
  await page.waitForFunction(() => window.KfpsDesktop?.ready);
  const blank = await page.evaluate(async () => ({ count: vinylObjects().length, recovery: await readAutosavePayload(), modeConsumed: !location.search.includes("mode=") }));
  assert(blank.count === 0 && blank.recovery === null && blank.modeConsumed, "Explicit New was overridden by automatic recovery");
  checks.push({ explicitNew: true });
  const preparation = await page.evaluate(async () => {
    const image = document.createElement("canvas"); image.width = image.height = 16;
    image.getContext("2d").fillRect(0, 0, 16, 16);
    await editorReference.loadOverlayImageFromUrl(image.toDataURL(), "preparation.png");
    currentProjectName = "Reference-only preparation";
    await saveProject(); await flushPendingAutosave();
    if (documentDirty || !editorRecovery.status.serverOk) throw new Error("Reference-only project could not be saved");
    return editorReference.sourceOverlayProjectState();
  });
  await page.reload();
  await page.waitForFunction(() => window.KfpsDesktop?.ready);
  assert(await page.evaluate(expected => vinylObjects().length === 0 && !documentDirty
    && JSON.stringify(editorReference.sourceOverlayProjectState()) === JSON.stringify(expected), preparation), "Reference-only session was not restored");
  await page.evaluate(async () => {
    await startBlankCanvas();
    guideDraft = { x1: 0, y1: 0, x2: 100, y2: 0, constraint: "horizontal" };
    finishGuideDraft(); await flushPendingAutosave();
    documentDirty = false;
  });
  await page.reload();
  await page.waitForFunction(() => window.KfpsDesktop?.ready);
  assert(await page.evaluate(() => vinylObjects().length === 0 && guideState.guides.length === 1 && documentDirty), "Guide-only session was not restored");
  checks.push({ referenceOnlySavedAndRestored: true, guideOnlyRestored: true });
  return { passed: true, checks };
}
