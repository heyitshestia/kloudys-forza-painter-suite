async page => page.evaluate(async () => {
  const assert = (v, m) => { if (!v) throw new Error(m); };
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const x = () => objectToShape(vinylObjects()[0], { includeEditorMeta: true }).data[0];
  const check = async label => {
    const expected = x();
    await flushPendingAutosave();
    const payload = await readAutosavePayload();
    assert(payload?.shapes[0].data[0] === expected, `${label} left stale recovery`);
    return expected;
  };
  try {
    await clearAutosave();
    await loadPayload({ shapes: [{ type: 1048677, color: [180, 80, 140, 255], data: [0, 0, 1, 1, 0, 0, 0] }] });
    const originalX = x();
    for (let i = 0; i < 3; i++) { vinylObjects()[0].left += 23; vinylObjects()[0].setCoords(); pushHistory(`history recovery ${i}`); }
    const endIndex = editorHistory.index;
    await check("edit");
    await undo(); await check("Undo");
    await redo(); await check("Redo");
    await jumpToHistory(0); assert(x() === originalX, "History jump did not restore the baseline"); await check("history jump");
    await jumpToHistory(endIndex); await check("history return");
    const beforeNudge = x();
    selectObjects([vinylObjects()[0]], "held nudge recovery");
    currentProjectName = `held-nudge-${Date.now()}`;
    await saveProject();
    const started = performance.now();
    let firstRecoveryMs = null;
    for (let i = 0; i < 32; i++) {
      nudgeSelected(1, 0);
      assert(documentDirty, "Pending nudge appeared saved");
      await sleep(100);
      if (firstRecoveryMs === null && editorRecovery.status.state === "saved") {
        const stored = await readAutosavePayload();
        if (stored?.shapes[0].data[0] !== beforeNudge) firstRecoveryMs = performance.now() - started;
      }
    }
    assert(firstRecoveryMs !== null && firstRecoveryMs < 2700, "Holding a nudge postponed recovery indefinitely");
    flushPendingNudgeHistory();
    await check("held nudge final position");
    return { undoRedoAndHistoryRecovery: true, heldNudgeFirstRecoveryMs: firstRecoveryMs };
  } finally { await clearAutosave(); }
})
