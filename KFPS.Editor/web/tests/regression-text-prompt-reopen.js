async (page, options = {}) => {
  const count=Number(options.layers || 2);
  page.setDefaultTimeout(15000);
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  await page.locator("#loadProject").click();
  await page.locator(".projectBrowserEntry").filter({ has: page.getByText("Enter Save As", { exact: true }) }).click();
  await page.locator("#selectProjectEntry").click();
  if (await page.locator("#confirmationDialog").isVisible()) await page.locator("#confirmationDialogConfirm").click();
  await page.locator("#projectBrowserDialog").waitFor({ state: "hidden" });
  const reopened = await page.evaluate(() => ({
    name: currentProjectName,
    dirty: documentDirty,
    shapes: vinylObjects().map(object => objectToShape(object, { includeEditorMeta: true })),
  }));
  check(reopened.name === "Enter Save As" && !reopened.dirty && reopened.shapes.length === count, "The Enter-saved project must reopen after a complete process restart");
  check(reopened.shapes.every(shape => shape.editor_group_name === "Enter Group"), "Enter-renamed groups must survive restart");
  const renamedLayerLabelPreserved = reopened.shapes.some(shape => shape.shape_name === "\ud14c\uc2a4\ud2b8 Layer");
  check(renamedLayerLabelPreserved, "Custom layer labels must survive a full process restart");
  await page.locator("#saveProjectAs").click();
  await page.locator("#textPromptInput").fill("Restart Enter Proof");
  await page.locator("#textPromptInput").press("Enter");
  await page.locator("#textPromptDialog").waitFor({ state: "hidden" });
  await page.waitForFunction(() => !projectSaveInProgress);
  check(await page.evaluate(() => currentProjectName === "Restart Enter Proof" && !documentDirty), "Save As + Enter must continue working in a fresh process");
  const persisted = await page.evaluate(async () => {
    const entries = (await (await fetch(PROJECT_BROWSER_API)).json()).entries;
    const entry = entries.find(entry => entry.title === "Restart Enter Proof");
    return (await (await fetch(`${PROJECT_FILE_API}?id=${encodeURIComponent(entry.id)}`)).json()).payload;
  });
  check(persisted.shapes.length === count, "Restart Save As must write every layer to disk");
  return { freshProcessReopen: true, savedAgainWithEnter: true, groups: true, layers: count, renamedLayerLabelPreserved };
}
