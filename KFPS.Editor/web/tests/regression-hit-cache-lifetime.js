async (page, options = {}) => {
  const h = require(path.join(__dirname, 'dense-human-fixture.cjs'));
  const initial = await h.setup(page, output, { ...options, layers: 2800 });
  await h.select(page, 'Human target');
  await page.locator('[data-tool-mode="select"]').click();
  const result = await page.evaluate(() => {
    const target = selectedVinylObjects()[0];
    canvas.renderAll();
    const point = target.getCenterPoint();
    const before = { cache: target._cacheCanvas, context: target._cacheContext,
      dirty: target.dirty, ownCaching: target.ownCaching, width: target.cacheWidth, height: target.cacheHeight };
    if (!before.cache || !before.context) throw Error('No established target drawing cache');
    for (let i = 0; i < 20; i++) KfpsFabricAdapter.visiblePixelAt(canvas, target, point);
    const visiblePixelPreserved = target._cacheCanvas === before.cache && target._cacheContext === before.context
      && target.cacheWidth === before.width && target.cacheHeight === before.height && target.dirty === before.dirty;
    canvas.renderAll();
    const existing = target._cacheCanvas;
    const screen = fabric.util.transformPoint(point, canvas.viewportTransform);
    for (let i = 0; i < 20; i++) canvas.isTargetTransparent(target, screen.x, screen.y);
    const fabricHitPreserved = target._cacheCanvas === existing;
    return { visiblePixelPreserved, fabricHitPreserved };
  });
  if (!result.visiblePixelPreserved || !result.fabricHitPreserved) throw Error('Pixel picking discarded the drawing cache: ' + JSON.stringify(result));
  const fields = await page.evaluate(() => {
    const target = selectedVinylObjects()[0];
    canvas.renderAll();
    const before = { cache: target._cacheCanvas, context: target._cacheContext,
      dirty: true, ownCaching: target.ownCaching, width: target.cacheWidth, height: target.cacheHeight };
    target.dirty = true;
    const render = target._render;
    target._render = () => { throw Error('Injected hit-render failure'); };
    let failed = false;
    try { KfpsFabricAdapter.visiblePixelAt(canvas, target, target.getCenterPoint()); }
    catch (error) { failed = error.message === 'Injected hit-render failure'; }
    finally { target._render = render; }
    if (!failed || target._cacheCanvas !== before.cache || target._cacheContext !== before.context
      || !target.dirty || target.ownCaching !== before.ownCaching || target.cacheWidth !== before.width || target.cacheHeight !== before.height)
      throw Error('Hit failure lost retained cache/dirty state');
    window.hitCache = target._cacheCanvas;
    window.hitCreates = 0;
    const create = target._createCacheCanvas;
    target._createCacheCanvas = function (...args) { hitCreates++; return create.apply(this, args); };
    return true;
  });
  const trace = await h.monitor(page, output);
  try {
    for (let i = 0; i < 12; i++) {
      await trace.run('real-pointer-drag-' + i, async () => {
        const p = await h.geometry(page);
        await h.drag(page, p.grab, { x: p.grab.x + (i % 2 ? -10 : 10), y: p.grab.y + (i % 2 ? -7 : 7) });
      });
    }
    const creates = await page.evaluate(() => {
      const target = selectedVinylObjects()[0];
      if (target._cacheCanvas !== hitCache) throw Error('Real pointer movement replaced the drawing cache');
      return hitCreates;
    });
    if (creates) throw Error('Real pointer path recreated drawing caches: ' + creates);
    await page.evaluate(async () => {
      await flushPendingAutosave();
      if (JSON.stringify((await readAutosavePayload()).shapes) !== JSON.stringify(snapshotShapes())) throw Error('Recovery differs after pixel cache test');
    });
    return { initial, ...result, failurePreserved: fields, creates, rows: trace.rows };
  } finally { await trace.close(); }
}
