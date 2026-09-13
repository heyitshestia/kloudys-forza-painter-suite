async page => {
  const floor = await page.evaluate(async () => {
    await clearAutosave();
    const future = Date.now() * 1000 + 365 * 86400 * 1000000;
    const result = await editorPersistence.request("recovery", {
      payload: { action: "clear", shapes: [], recovery_revision: future },
    });
    if (!result.serverOk || !result.browserOk) throw Error("Fixture floor was not stored");
    localStorage.removeItem(AUTOSAVE_CLEAR_KEY);
    return future;
  });
  const url = new URL(page.url());
  url.searchParams.set("mode", "new");
  await page.goto(url.href);
  await page.waitForFunction(() => window.KfpsDesktop?.ready);
  return page.evaluate(async floor => {
    if (editorRecovery.revision <= floor) throw Error("New bypassed the recovery revision floor");
    await loadPayload({ shapes: [{ type: 1048677, color: [20, 100, 200, 255], data: [0, 0, 1, 1, 0, 0, 0] }] });
    vinylObjects()[0].left += 20;
    pushHistory("clock rollback fixture");
    await flushPendingAutosave();
    if (!editorRecovery.status.serverOk || !editorRecovery.status.browserOk) throw Error("New edit was rejected after clock rollback");
    const recovery = await readAutosavePayload();
    if (recovery?.recovery_revision !== editorRecovery.revision || recovery.shapes.length !== 1) throw Error("Recovery did not reopen");
    const result = { passed: true, floor, revision: editorRecovery.revision, reopened: true };
    await clearAutosave(); documentDirty = false;
    return result;
  }, floor);
}
