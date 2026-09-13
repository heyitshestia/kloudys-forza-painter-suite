async (page, options) => {
  if (!options.expected) throw Error('Supply the previous construction run expected-shapes.json');
  const expected = JSON.parse(fs.readFileSync(options.expected, 'utf8'));
  await page.locator('#loadProject').click();
  await page.locator('.projectBrowserEntry').filter({ has: page.getByText('Incremental reference study', { exact: true }) }).click();
  await page.locator('#selectProjectEntry').click();
  await page.waitForFunction(() => !recoveryRestoreDepth && !documentDirty && vinylObjects().length === 3000 && !!editorReference.image);
  const actual = await page.evaluate(() => snapshotShapes());
  if (JSON.stringify(actual) !== JSON.stringify(expected)) throw Error('New process changed the constructed project');
  await page.locator('[data-tool-mode="select"]').click();
  await page.evaluate(() => { selectObjects([vinylObjects()[0]], 'restart continuation fixture'); canvas.upperCanvasEl.focus(); });
  await page.keyboard.press('Shift+ArrowRight');
  await page.waitForFunction(() => documentDirty);
  await page.evaluate(async expected => {
    const shapes = snapshotShapes();
    if (JSON.stringify(shapes[0]) === JSON.stringify(expected[0])) throw Error('Restarted document cannot be edited');
    if (JSON.stringify(shapes.slice(1)) !== JSON.stringify(expected.slice(1))) throw Error('Continuation changed unrelated shapes');
    await flushPendingAutosave();
    if (JSON.stringify((await readAutosavePayload()).shapes) !== JSON.stringify(shapes)) throw Error('Continued work was not protected');
  }, expected);
  await page.locator('#saveProject').click();
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  return { layers: 3000, newProcessExactReopen: true, reference: true, continuedEdit: true, exactRecovery: true, saved: true };
}
