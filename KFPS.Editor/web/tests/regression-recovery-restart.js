async page => {
  const expected = await page.evaluate(async () => {
    await clearAutosave();
    await loadPayload({ shapes: [{ type: 1048677, color: [10, 80, 180, 255], data: [29, 71, 1, 1, 0, 0, 0] }] });
    vinylObjects()[0].left += 39;
    vinylObjects()[0].setCoords();
    pushHistory("restart recovery");
    await flushPendingAutosave();
    if (!editorRecovery.status.serverOk) throw new Error("Recovery never reached the app folder");
    return JSON.stringify(vinylObjects().map(o => objectToShape(o, { includeEditorMeta: true })));
  });
  const url = page.url();
  const browser = page.context().browser();
  await page.context().close();
  const context = await browser.newContext();
  try {
    const reopened = await context.newPage();
    await reopened.goto(url);
    await reopened.waitForFunction(() => typeof canvas !== "undefined" && Boolean(canvas));
    const actual = await reopened.evaluate(async () => {
      document.querySelectorAll("dialog[open]").forEach(d => d.close());
      const payload = await readAutosavePayload();
      if (!payload) throw new Error("Fresh browser context did not find app-folder recovery");
      await recoverAutosavePayload(payload);
      const value = JSON.stringify(vinylObjects().map(o => objectToShape(o, { includeEditorMeta: true })));
      await clearAutosave();
      return value;
    });
    if (actual !== expected) throw new Error("Fresh-context recovery changed the saved edit");
    return { freshContextRecoveryExact: true };
  } finally { await context.close(); }
}
