async (page, options = {}) => {
  const h = require(path.join(__dirname, 'dense-human-fixture.cjs'));
  const initial = await h.setup(page, output, { ...options, layers: 2900 });
  await page.waitForFunction(() => !editorRenderer.warmingDocument);
  const expected = await h.snapshot(page);
  await page.locator('#saveProjectAs').click();
  await h.type(page, '#textPromptInput', 'Document preparation regression');
  await page.locator('#textPromptInput').press('Enter');
  await page.waitForFunction(() => !projectSaveInProgress && !documentDirty);
  const trace = await h.monitor(page, output);
  const open = async () => {
    await page.locator('#newCanvas').click();
    await page.waitForFunction(() => !vinylObjects().length && !recoveryRestoreDepth);
    await page.locator('#loadProject').click();
    await page.locator('.projectBrowserEntry').filter({ has: page.getByText('Document preparation regression', { exact: true }) }).click();
    await page.locator('#selectProjectEntry').click();
  };
  const ready = () => page.waitForFunction(({ count, reference }) => vinylObjects().length === count
    && !documentDirty && !editorRenderer.warmingDocument
    && (!reference || editorReference.image?.width === reference[0] && editorReference.image?.height === reference[1]),
    { count: initial.layers, reference: initial.reference });
  try {
    for (let iteration = 0; iteration < 3; iteration++) {
      await trace.run(`new-open-${iteration}`, async () => {
        await open(); await ready();
        if (await h.snapshot(page) !== expected) throw Error('Prepared project artwork differs');
        await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      });
      const pixels = await page.evaluate(() => canvas.lowerCanvasEl.toDataURL('image/png'));
      const image = Buffer.from(pixels.split(',')[1], 'base64');
      fs.writeFileSync(path.join(output, `fabric-${iteration}.png`), image);
      if (options.baselinePng && !image.equals(fs.readFileSync(options.baselinePng))) throw Error('Prepared Fabric image differs from baseline');
    }
    const zoomBefore = await page.evaluate(() => {
      window.wheelDuringPreparation = null;
      document.addEventListener('wheel', event => {
        window.wheelDuringPreparation = { warming: editorRenderer.warmingDocument,
          target: event.target.className, canvas: event.target === canvas.upperCanvasEl,
          modal: document.querySelector('dialog[open]')?.id || null, at: performance.now() };
      }, { capture: true, once: true });
      return canvas.getZoom();
    });
    const bounds = await page.locator('.upper-canvas').boundingBox();
    await open();
    await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
    await page.waitForFunction(() => !document.getElementById('projectBrowserDialog').open && editorRenderer.warmingDocument);
    await page.mouse.wheel(0, -100);
    await page.waitForFunction(() => !editorRenderer.warmingDocument);
    const wheelResult = await page.evaluate(before => ({ event: window.wheelDuringPreparation,
      zoomBefore: before, zoomAfter: canvas.getZoom(), warming: editorRenderer.warmingDocument }), zoomBefore);
    fs.writeFileSync(path.join(output, 'preparation-wheel.json'), JSON.stringify(wheelResult, null, 2));
    if (!wheelResult.event?.warming || !wheelResult.event.canvas || wheelResult.zoomAfter === zoomBefore)
      throw Error('Actual wheel did not interrupt preparation and change zoom: ' + JSON.stringify(wheelResult));
    await ready();
    if (await h.snapshot(page) !== expected) throw Error('Zoom interrupted document identity or artwork');
    await page.waitForFunction(() => !editorRenderer.active);
    await page.locator('#fitView').click();
    await h.select(page, 'Human target');
    const moving = await h.geometry(page);
    await page.evaluate(() => {
      window.dragDuringPreparation = null;
      canvas.upperCanvasEl.addEventListener('mousedown', () => {
        window.dragDuringPreparation = editorRenderer.warmingDocument;
      }, { capture: true, once: true });
    });
    await open();
    await page.mouse.move(moving.grab.x, moving.grab.y);
    await page.waitForFunction(() => !document.getElementById('projectBrowserDialog').open && editorRenderer.warmingDocument);
    try {
      await page.mouse.down();
      await page.mouse.move(moving.grab.x + 18, moving.grab.y + 10, { steps: 12 });
    } finally { await page.mouse.up(); }
    if (!await page.evaluate(() => window.dragDuringPreparation)) throw Error('Mouse press missed the preparation interval');
    if (await h.snapshot(page) === expected) throw Error('Drag during preparation did not edit a shape');
    await h.undo(page, expected);
    await ready();
    await page.evaluate(() => {
      const original = fabric.Object.prototype.renderCache;
      window.restoreWarmupCache = () => { fabric.Object.prototype.renderCache = original; };
      window.warmupFaultHit = false;
      fabric.Object.prototype.renderCache = function(...args) {
        if (editorRenderer.warmingDocument) {
          window.warmupFaultHit = true;
          window.restoreWarmupCache();
          throw TypeError('Injected document cache failure');
        }
        return original.apply(this, args);
      };
    });
    try {
      await open(); await ready();
      if (!await page.evaluate(() => window.warmupFaultHit)) throw Error('Cache fault was not exercised');
      if (await h.snapshot(page) !== expected) throw Error('Cache fault changed accepted artwork');
    } finally { await page.evaluate(() => window.restoreWarmupCache()); }
    await page.evaluate(async () => {
      await flushPendingAutosave();
      if (JSON.stringify((await readAutosavePayload()).shapes) !== JSON.stringify(snapshotShapes())) throw Error('Prepared document recovery differs');
      if (canvas.lowerCanvasEl.style.visibility === 'hidden') throw Error('Ordinary canvas remained hidden');
    });
    await page.screenshot({ path: path.join(output, 'document-preparation.png') });
    return { initial, rows: trace.rows, exactArtwork: true, pixelBaselineChecked: Boolean(options.baselinePng),
      actualWheelInterrupt: true, actualDragInterruptAndUndo: true, cacheFaultRecovery: true, recoveryExact: true };
  } finally { await trace.close(); }
}
