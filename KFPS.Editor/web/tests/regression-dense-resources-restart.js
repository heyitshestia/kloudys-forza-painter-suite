async (page, options = {}) => {
  const h = require(path.join(__dirname, 'dense-human-fixture.cjs'));
  const previous = options.previousOutput || path.join(output, '../regression-dense-resources');
  const expected = fs.readFileSync(path.join(previous, 'dense-resource-expected.json'), 'utf8');
  const count = JSON.parse(expected).length;
  await page.waitForFunction(count => window.KfpsDesktop?.ready && vinylObjects().length === count, count);
  if (await h.snapshot(page) !== expected) throw Error('New native process restored different resource artwork');
  const provenance = await page.evaluate(() => {
    const generated = vinylObjects().filter(o => o.kloudy.pixel_art_generated);
    if (!generated.length || !favorites.has('Primitives:1')) throw Error('Restart lost pixel provenance or favorite');
    return { generated: generated.length,
      independent: JSON.stringify(vinylObjects().filter(o => !o.kloudy.pixel_art_generated).map(o => objectToShape(o))) };
  });
  await page.locator('[data-tool-mode="pixelArt"]').click();
  await h.fileInput(page, '#pixelArtInput', path.join(previous, 'dense-pixel-source.svg'));
  await page.locator('#pixelArtClearPrevious').check();
  await page.locator('#generatePixelArt').click();
  await page.waitForFunction(() => !pixelArtGenerationRunning && !editorCommands.busy);
  const actual = await page.evaluate(() => ({ count: vinylObjects().length,
    generated: vinylObjects().filter(o => o.kloudy.pixel_art_generated).length,
    independent: JSON.stringify(vinylObjects().filter(o => !o.kloudy.pixel_art_generated).map(o => objectToShape(o))) }));
  if (actual.count !== count || actual.generated !== provenance.generated || actual.independent !== provenance.independent)
    throw Error('Replace previous after process restart changed independent layers or appended generated layers');
  await h.undo(page, expected);
  await page.locator('#saveProjectAs').click();
  await h.type(page, '#textPromptInput', 'Dense resource restart');
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  await page.evaluate(async () => {
    await flushPendingAutosave();
    if (JSON.stringify((await readAutosavePayload()).shapes) !== JSON.stringify(snapshotShapes())) throw Error('Restart recovery mismatch');
  });
  return { fullProcessRestart: true, layers: count, generated: provenance.generated,
    favoritePreserved: true, replacementAndUndoExact: true, independentArtworkExact: true, savedAndProtected: true };
}
