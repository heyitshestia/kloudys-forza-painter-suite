async (page) => {
  page.setDefaultTimeout(60000);
  const result = await page.evaluate(async () => {
    await clearAutosave();
    await loadPayload({ shapes: Array.from({ length: 3000 }, (_, index) => ({
      type: 1048677, color: [100, 160, 220, 255],
      data: [(index % 60) * 20 - 600, -Math.floor(index / 60) * 20 + 500, .18, .18, 0, 0, 0],
    })) });
    const target = vinylObjects()[0];
    target.set({ left: target.left + 37 });
    target.setCoords();
    pushHistory("background recovery regression");
    await flushPendingAutosave();
    if (!editorRecovery.status.serverOk || !editorRecovery.status.browserOk) throw new Error("Both durable recovery paths must acknowledge");
    const saved = await readAutosavePayload();
    const expected = snapshotShapes();
    if (JSON.stringify(saved.shapes) !== JSON.stringify(expected)) throw new Error("Recovery changed the latest shapes");
    if (localStorage.getItem(AUTOSAVE_KEY)) throw new Error("Large synchronous browser backup is still being written");
    const workerCount = editorPersistence.pending.size;
    if (workerCount) throw new Error("Completed recovery retains pending requests");
    return { layers: saved.shapes.length, exact: true, server: true, indexedDB: true, synchronousBackupAbsent: true };
  });
  result.workerTargets = page.workers().map(worker => worker.url());
  return result;
}
