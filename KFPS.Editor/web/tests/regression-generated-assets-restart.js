async page => {
  const h = require(path.join(__dirname, "dense-human-fixture.cjs"));
  const prior = path.join(output, "../regression-generated-assets");
  const expected = JSON.parse(fs.readFileSync(path.join(prior, "expected.json")));
  const check = (ok, message) => { if (!ok) throw Error(message); };
  await page.waitForFunction(count => vinylObjects().length === count, expected.original.length);
  check(await h.snapshot(page) === JSON.stringify(expected.original), "Fresh native process changed project/provenance");
  await page.locator('[data-panel="assetsPane"]').click();
  await page.waitForFunction(() => !editorAssetLibrary.busy);
  for (const asset of expected.assets) {
    const before = await h.snapshot(page);
    await page.locator(`[data-asset-id="${asset.entry.id}"] .assetActions > button`).click();
    await page.waitForFunction(() => !editorAssetLibrary.busy && !editorCommands.busy);
    const result = await page.evaluate(({ before, payload }) => {
      const current = snapshotShapes(), inserted = current.slice(before.length);
      const shapes = payload.payload?.shapes || payload.shapes;
      const dx = inserted[0]?.data[0] - shapes[0]?.data[0], dy = inserted[0]?.data[1] - shapes[0]?.data[1];
      const appearance = (s, original) => s.type === original.type && JSON.stringify(s.color) === JSON.stringify(original.color)
        && Boolean(s.mask) === Boolean(original.mask) && s.data.length === original.data.length
        && s.data.every((value, i) => Math.abs(value - original.data[i] - (i === 0 ? dx : i === 1 ? dy : 0)) < .0001);
      return { previousExact: JSON.stringify(current.slice(0, before.length)) === JSON.stringify(before),
        independent: inserted.every(s => !s.editor_pixel_art_generated),
        appearanceExact: inserted.length === shapes.length && inserted.every((s, i) => appearance(s, shapes[i])),
        uniqueIds: new Set(current.map(s => s.editor_id)).size === current.length };
    }, { before: JSON.parse(before), payload: asset.payload });
    check(Object.values(result).every(Boolean), `Asset restart insertion failed: ${asset.entry.name} ${JSON.stringify(result)}`);
  }
  const independent = await page.evaluate(() => JSON.stringify(vinylObjects().filter(o => !o.kloudy.pixel_art_generated).map(o => objectToShape(o))));
  const oldIds = await page.evaluate(() => vinylObjects().filter(o => o.kloudy.pixel_art_generated).map(o => o.kloudy.editor_id));
  await page.locator('[data-tool-mode="pixelArt"]').click();
  await h.fileInput(page, "#pixelArtInput", path.join(prior, "pixel-source.svg"));
  await page.locator("#pixelArtClearPrevious").check(); await page.locator("#generatePixelArt").click();
  await page.waitForFunction(() => !pixelArtGenerationRunning && !editorCommands.busy);
  const result = await page.evaluate(({ independent, oldIds, count }) => ({
    independentExact: JSON.stringify(vinylObjects().filter(o => !o.kloudy.pixel_art_generated).map(o => objectToShape(o))) === independent,
    originalReplaced: oldIds.every(id => !vinylObjects().some(o => o.kloudy.editor_id === id)),
    generatedCount: vinylObjects().filter(o => o.kloudy.pixel_art_generated).length === count,
    flatExport: vinylObjects().every(o => !Object.hasOwn(objectToShape(o, { includeEditorMeta: false }), "editor_pixel_art_generated")),
  }), { independent, oldIds, count: expected.generated });
  check(Object.values(result).every(Boolean), `Clear previous failed: ${JSON.stringify(result)}`);
  await page.locator("#saveProject").click();
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  await page.evaluate(async () => { await flushPendingAutosave(); });
  await page.screenshot({ path: path.join(output, "generated-assets-restart.png") });
  return { passed: true, fullProcessRestart: true, ...result, insertedAssets: expected.assets.length };
}
