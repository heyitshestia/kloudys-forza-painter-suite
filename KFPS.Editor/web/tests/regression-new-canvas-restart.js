async page => {
  const h = require(path.join(__dirname, "dense-human-fixture.cjs"));
  const state = await page.evaluate(async () => ({ blank: vinylObjects().length === 0,
    baseline: editorHistory.entries.length === 1 && !currentHistoryState().shapes.length, project: currentProjectName,
    recovery: await readAutosavePayload(), reference: Boolean(editorReference.image) }));
  if (!state.blank || !state.baseline || state.project || state.recovery || state.reference)
    throw Error(`Restart resurrected pre-New work or lost baseline: ${JSON.stringify(state)}`);
  await page.locator('[data-tool-mode="shapeLibrary"]').click();
  await page.locator("#shapeFamily").selectOption("Primitives"); await h.type(page, "#shapeSearch", "1048677");
  await page.locator("#shapeGrid .shapeTile img").first().click();
  await page.waitForFunction(() => vinylObjects().length === 1 && !editorCommands.busy);
  await page.locator("#undoBtn").click();
  await page.waitForFunction(() => !vinylObjects().length && !editorCommands.busy);
  await page.locator("#redoBtn").click();
  await page.waitForFunction(() => vinylObjects().length === 1 && !editorCommands.busy);
  await page.locator("#saveProjectAs").click(); await h.type(page, "#textPromptInput", "After New restart");
  await page.locator("#textPromptInput").press("Enter");
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  await page.evaluate(async () => {
    await flushPendingAutosave();
    if (JSON.stringify((await readAutosavePayload()).shapes) !== JSON.stringify(snapshotShapes())) throw Error("Post-New recovery differs");
  });
  return { passed: true, fullProcessRestart: true, previousRecoveryRetired: true, subsequentSaveRecoveryExact: true };
}
